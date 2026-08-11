"""
Backend Flask : authentification, gestion des portails (caméras d'entrée),
flux caméra en temps réel, exécution du pipeline de détection, historique
SQLite avec export CSV.
"""
import csv
import io
import os
import secrets
import sqlite3
import threading
import time
from functools import wraps

import cv2
import numpy as np
from flask import Flask, Response, abort, redirect, render_template, request, send_from_directory, session, url_for
from werkzeug.security import check_password_hash

import db
from passage_tracker import SuiviPassage
from pipeline import annotate_frame, run_pipeline

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or os.urandom(24)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 Mo max par upload (/analyser)

# Hors de static/ volontairement : static/ est servi sans authentification par
# Flask, ce qui exposerait les photos de camions à quiconque devine un nom de
# fichier. Voir la route protégée /captures/<filename> plus bas.
CAPTURES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "captures")
os.makedirs(CAPTURES_DIR, exist_ok=True)

INFER_INTERVAL = 0.7  # secondes entre deux inférences YOLO sur le flux live
PORTAIL_POLL_INTERVAL = 1.0  # secondes entre deux vérifications du portail actif

# Enregistrement automatique du passage d'un camion (voir camera_worker) :
# un camion doit être détecté en continu au moins DUREE_MIN_PRESENCE avant
# d'être enregistré (filtre le bruit/faux positif d'une seule image), et
# doit être absent depuis au moins DUREE_GRACE_ABSENCE avant d'être
# considéré comme reparti (tolère une image manquée au milieu du passage).
DUREE_MIN_PRESENCE = 1.5
DUREE_GRACE_ABSENCE = 1.0

db.init_db()

state_lock = threading.Lock()
latest_frame = None
latest_annotated_frame = None
latest_result = {"camion_detecte": False}
camera_ok = False

# Suivi de passage pour la caméra navigateur (getUserMedia) : indépendant du
# camera_worker (webcam locale au serveur), car en déploiement cloud le
# serveur n'a pas de caméra physique — c'est l'appareil qui ouvre la page
# (téléphone, PC) qui fournit les images via /analyser_frame.
suivi_navigateur = SuiviPassage(DUREE_MIN_PRESENCE, DUREE_GRACE_ABSENCE)
derniere_image_navigateur = None

params_lock = threading.Lock()
current_params = db.get_parametres()


def get_current_params():
    with params_lock:
        return dict(current_params)


def resolve_camera_source(camera_source):
    return int(camera_source) if camera_source.isdigit() else camera_source


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("utilisateur"):
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def get_csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(16)
    return session["csrf_token"]


app.jinja_env.globals["csrf_token"] = get_csrf_token


@app.before_request
def verifier_csrf():
    if request.method == "POST":
        token_session = session.get("csrf_token")
        token_formulaire = request.form.get("csrf_token")
        # Les deux doivent être présents ET identiques : si aucune session n'a
        # encore émis de token, une requête forgée sans token ne doit pas
        # passer simplement parce que les deux valeurs sont "None".
        if not token_session or not token_formulaire or token_formulaire != token_session:
            abort(403)


def _enregistrer_passage(portail_id, image, statut, ratio_bleu, confiance):
    """Sauvegarde automatique d'un passage de camion détecté (voir camera_worker)."""
    filename = f"auto_{int(time.time())}.jpg"
    cv2.imwrite(os.path.join(CAPTURES_DIR, filename), image)
    db.add_detection(
        portail_id=portail_id,
        statut=statut,
        ratio_bleu=ratio_bleu,
        confiance=confiance,
        image_path=filename,
    )


def camera_worker():
    global latest_frame, latest_annotated_frame, latest_result, camera_ok

    cap = None
    current_portail_id = None
    last_infer = 0.0
    last_portail_check = 0.0
    suivi = SuiviPassage(DUREE_MIN_PRESENCE, DUREE_GRACE_ABSENCE)
    derniere_image_avec_camion = None

    while True:
        try:
            now = time.time()

            if now - last_portail_check >= PORTAIL_POLL_INTERVAL:
                last_portail_check = now
                portail = db.get_portail_actif()
                if portail and portail["id"] != current_portail_id:
                    if cap is not None:
                        cap.release()
                    cap = cv2.VideoCapture(resolve_camera_source(portail["camera_source"]))
                    current_portail_id = portail["id"]

            if cap is None:
                time.sleep(0.5)
                continue

            ret, frame = cap.read()
            if not ret:
                with state_lock:
                    camera_ok = False
                time.sleep(0.5)
                continue

            with state_lock:
                camera_ok = True
                result = latest_result

            if now - last_infer >= INFER_INTERVAL:
                p = get_current_params()
                result = run_pipeline(
                    frame,
                    threshold=float(p["seuil_bleu"]),
                    top_ratio=float(p["top_ratio"]),
                    left_margin=float(p["left_margin"]),
                    right_margin=float(p["right_margin"]),
                )
                last_infer = now

                if result["camion_detecte"]:
                    derniere_image_avec_camion = annotate_frame(frame.copy(), result)

                passage_termine = suivi.observer(result, now)
                if passage_termine is not None and derniere_image_avec_camion is not None:
                    portail_actuel = db.get_portail_actif()
                    if portail_actuel:
                        _enregistrer_passage(
                            portail_actuel["id"],
                            derniere_image_avec_camion,
                            passage_termine["statut"],
                            passage_termine["ratio_bleu"],
                            passage_termine["confiance"],
                        )

            annotated = annotate_frame(frame.copy(), result)
            with state_lock:
                latest_frame = frame
                latest_annotated_frame = annotated
                latest_result = result
        except Exception as exc:
            # Le thread caméra tourne seul en tâche de fond : une exception non
            # rattrapée ici (paramètre corrompu, erreur pilote caméra...) le
            # tuerait silencieusement et figerait le flux en direct pour de bon.
            print(f"[camera_worker] erreur ignorée : {exc}")
            with state_lock:
                camera_ok = False
            time.sleep(1.0)


threading.Thread(target=camera_worker, daemon=True).start()


def gen_mjpeg():
    while True:
        with state_lock:
            frame = latest_annotated_frame
        if frame is None:
            time.sleep(0.05)
            continue
        ok, buffer = cv2.imencode(".jpg", frame)
        if not ok:
            continue
        yield (
            b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n"
        )
        time.sleep(0.03)


@app.route("/login", methods=["GET", "POST"])
def login():
    erreur = None
    if request.method == "POST":
        identifiant = request.form.get("identifiant", "")
        mot_de_passe = request.form.get("mot_de_passe", "")
        utilisateur = db.get_utilisateur(identifiant)
        if utilisateur and check_password_hash(utilisateur["mot_de_passe_hash"], mot_de_passe):
            session["utilisateur"] = identifiant
            return redirect(request.args.get("next") or url_for("index"))
        erreur = "Identifiant ou mot de passe incorrect."
    return render_template("login.html", erreur=erreur)


@app.route("/logout")
def logout():
    session.pop("utilisateur", None)
    return redirect(url_for("login"))


@app.route("/video_feed")
@login_required
def video_feed():
    return Response(gen_mjpeg(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/captures/<path:filename>")
@login_required
def voir_capture(filename):
    return send_from_directory(CAPTURES_DIR, filename)


@app.route("/")
@login_required
def index():
    portail = db.get_portail_actif()
    detections = db.list_detections(portail_id=portail["id"], limit=10) if portail else []
    with state_lock:
        cam_ok = camera_ok
    return render_template(
        "index.html", portail=portail, detections=detections, active="accueil", camera_ok=cam_ok
    )


@app.route("/capturer", methods=["POST"])
@login_required
def capturer():
    portail = db.get_portail_actif()
    with state_lock:
        frame = latest_frame
        result = dict(latest_result)
        ok = camera_ok

    if not portail or not ok or frame is None:
        return redirect(url_for("index", erreur="camera"))

    annotated = annotate_frame(frame.copy(), result)
    filename = f"capture_{int(time.time())}.jpg"
    cv2.imwrite(os.path.join(CAPTURES_DIR, filename), annotated)

    statut = result["statut"] if result.get("camion_detecte") else "Aucun camion"
    db.add_detection(
        portail_id=portail["id"],
        statut=statut,
        ratio_bleu=result.get("ratio_bleu", 0.0),
        confiance=result.get("confiance"),
        image_path=filename,
    )

    return redirect(url_for("index"))


@app.route("/analyser", methods=["GET", "POST"])
@login_required
def analyser():
    """
    Analyse d'une photo envoyée manuellement (pas de flux caméra requis).
    Utile en déploiement cloud, où le serveur n'a pas accès à une webcam locale.
    """
    if request.method == "POST":
        fichier = request.files.get("image")
        if not fichier or fichier.filename == "":
            return render_template("analyser.html", active="analyser", resultat=None, erreur="fichier")

        data = np.frombuffer(fichier.read(), np.uint8)
        frame = cv2.imdecode(data, cv2.IMREAD_COLOR)
        if frame is None:
            return render_template("analyser.html", active="analyser", resultat=None, erreur="format")

        p = get_current_params()
        result = run_pipeline(
            frame,
            threshold=float(p["seuil_bleu"]),
            top_ratio=float(p["top_ratio"]),
            left_margin=float(p["left_margin"]),
            right_margin=float(p["right_margin"]),
        )
        annotated = annotate_frame(frame.copy(), result)

        filename = f"upload_{int(time.time())}.jpg"
        cv2.imwrite(os.path.join(CAPTURES_DIR, filename), annotated)

        statut = result["statut"] if result.get("camion_detecte") else "Aucun camion"
        portail = db.get_portail_actif()
        if portail:
            db.add_detection(
                portail_id=portail["id"],
                statut=statut,
                ratio_bleu=result.get("ratio_bleu", 0.0),
                confiance=result.get("confiance"),
                image_path=filename,
            )

        resultat = {
            "statut": statut,
            "ratio_bleu": result.get("ratio_bleu", 0.0),
            "confiance": result.get("confiance"),
            "image_path": filename,
        }
        return render_template("analyser.html", active="analyser", resultat=resultat, erreur=None)

    return render_template("analyser.html", active="analyser", resultat=None, erreur=None)


@app.route("/camera_web")
@login_required
def camera_web():
    return render_template("camera_web.html", active="camera_web")


@app.route("/analyser_frame", methods=["POST"])
@login_required
def analyser_frame():
    """
    Reçoit une image capturée par la caméra du navigateur (getUserMedia côté
    client) et l'analyse comme le ferait camera_worker pour une webcam locale.
    Alimente le même suivi de passage automatique (voir SuiviPassage).
    """
    global derniere_image_navigateur

    fichier = request.files.get("image")
    if not fichier:
        return {"erreur": "image manquante"}, 400

    data = np.frombuffer(fichier.read(), np.uint8)
    frame = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if frame is None:
        return {"erreur": "format invalide"}, 400

    p = get_current_params()
    result = run_pipeline(
        frame,
        threshold=float(p["seuil_bleu"]),
        top_ratio=float(p["top_ratio"]),
        left_margin=float(p["left_margin"]),
        right_margin=float(p["right_margin"]),
    )

    now = time.time()
    with state_lock:
        if result["camion_detecte"]:
            derniere_image_navigateur = annotate_frame(frame.copy(), result)

        passage_termine = suivi_navigateur.observer(result, now)
        if passage_termine is not None and derniere_image_navigateur is not None:
            portail_actuel = db.get_portail_actif()
            if portail_actuel:
                _enregistrer_passage(
                    portail_actuel["id"],
                    derniere_image_navigateur,
                    passage_termine["statut"],
                    passage_termine["ratio_bleu"],
                    passage_termine["confiance"],
                )

    return {
        "camion_detecte": result["camion_detecte"],
        "statut": result.get("statut"),
        "ratio_bleu": result.get("ratio_bleu", 0.0),
        "confiance": result.get("confiance"),
        "en_cours": suivi_navigateur.en_cours,
    }


@app.route("/historique")
@login_required
def historique():
    portail = db.get_portail_actif()
    date = request.args.get("date") or None
    statut = request.args.get("statut") or None
    detections = (
        db.list_detections(portail_id=portail["id"], limit=200, date=date, statut=statut)
        if portail else []
    )
    return render_template(
        "historique.html", portail=portail, detections=detections, date=date or "", statut=statut or "",
        active="historique",
    )


@app.route("/historique/export.csv")
@login_required
def export_csv():
    portail = db.get_portail_actif()
    date = request.args.get("date") or None
    statut = request.args.get("statut") or None
    detections = (
        db.list_detections(portail_id=portail["id"], limit=100000, date=date, statut=statut)
        if portail else []
    )

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        ["horodatage", "statut", "pourcentage_bleu", "confiance", "corrige", "statut_detecte_original", "image"]
    )
    for d in detections:
        writer.writerow([
            d["horodatage"],
            d["statut"],
            round(d["ratio_bleu"] * 100, 1),
            round(d["confiance"] * 100, 1) if d["confiance"] is not None else "",
            "oui" if d["corrige"] else "non",
            d["statut_original"] or "",
            d["image_path"] or "",
        ])

    return Response(
        buffer.getvalue().encode("utf-8-sig"),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=historique_detections.csv"},
    )


@app.route("/historique/corriger/<int:detection_id>", methods=["POST"])
@login_required
def corriger(detection_id):
    nouveau_statut = request.form.get("statut")
    if nouveau_statut in ("Chargé", "Vide"):
        db.corriger_detection(detection_id, nouveau_statut)
    return redirect(url_for("historique"))


# Bornes de validation des paramètres réglables : reflète les min/max des
# champs HTML, mais vérifiées côté serveur (le client peut envoyer n'importe
# quoi). Une valeur hors bornes ou non numérique tuerait sinon silencieusement
# le thread caméra à la prochaine inférence.
BORNES_PARAMETRES = {
    "seuil_bleu": (0.0, 1.0),
    "top_ratio": (0.0, 0.9),
    "left_margin": (0.0, 0.85),
    "right_margin": (0.0, 0.85),
}


@app.route("/parametres", methods=["GET", "POST"])
@login_required
def parametres():
    global current_params

    if request.method == "POST":
        erreurs = []
        for cle, (mini, maxi) in BORNES_PARAMETRES.items():
            valeur = request.form.get(cle)
            if not valeur:
                continue
            try:
                nombre = float(valeur)
            except ValueError:
                erreurs.append(f"{cle} : doit être un nombre.")
                continue
            if not (mini <= nombre <= maxi):
                erreurs.append(f"{cle} : doit être entre {mini} et {maxi}.")
                continue
            db.set_parametre(cle, nombre)

        with params_lock:
            current_params = db.get_parametres()

        if erreurs:
            return render_template(
                "parametres.html", params=get_current_params(), enregistre=None,
                erreurs=erreurs, active="parametres",
            )
        return redirect(url_for("parametres", enregistre="1"))

    return render_template(
        "parametres.html", params=get_current_params(), enregistre=request.args.get("enregistre"),
        erreurs=None, active="parametres",
    )


@app.route("/portails", methods=["GET", "POST"])
@login_required
def portails():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "ajouter":
            nom = request.form.get("nom", "").strip()
            camera_source = request.form.get("camera_source", "").strip()
            if nom and camera_source:
                try:
                    db.add_portail(nom, camera_source)
                except sqlite3.IntegrityError:
                    return render_template(
                        "portails.html", portails=db.list_portails(), active="portails",
                        erreur=f"Un portail nommé « {nom} » existe déjà — choisissez un autre nom.",
                    )
        elif action == "activer":
            portail_id = request.form.get("portail_id")
            if portail_id:
                db.set_portail_actif(int(portail_id))
        return redirect(url_for("portails"))

    return render_template("portails.html", portails=db.list_portails(), active="portails", erreur=None)


@app.route("/compte", methods=["GET", "POST"])
@login_required
def compte():
    erreur = None
    succes = None

    if request.method == "POST":
        actuel = request.form.get("mot_de_passe_actuel", "")
        nouveau = request.form.get("nouveau_mot_de_passe", "")
        confirmation = request.form.get("confirmation", "")
        utilisateur = db.get_utilisateur(session["utilisateur"])

        if not check_password_hash(utilisateur["mot_de_passe_hash"], actuel):
            erreur = "Mot de passe actuel incorrect."
        elif len(nouveau) < 8:
            erreur = "Le nouveau mot de passe doit faire au moins 8 caractères."
        elif nouveau != confirmation:
            erreur = "La confirmation ne correspond pas au nouveau mot de passe."
        else:
            db.set_mot_de_passe(session["utilisateur"], nouveau)
            succes = "Mot de passe changé."

    return render_template("compte.html", active="compte", erreur=erreur, succes=succes)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
