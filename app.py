"""
Backend Flask : authentification, gestion des portails (caméras d'entrée),
flux caméra en temps réel, exécution du pipeline de détection, historique
SQLite avec export CSV.
"""
import csv
import io
import os
import threading
import time
from functools import wraps

import cv2
import numpy as np
from flask import Flask, Response, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

import db
from pipeline import annotate_frame, run_pipeline

app = Flask(__name__)
app.secret_key = os.urandom(24)

CAPTURES_DIR = os.path.join(app.static_folder, "captures")
os.makedirs(CAPTURES_DIR, exist_ok=True)

INFER_INTERVAL = 0.7  # secondes entre deux inférences YOLO sur le flux live
PORTAIL_POLL_INTERVAL = 1.0  # secondes entre deux vérifications du portail actif

db.init_db()

state_lock = threading.Lock()
latest_frame = None
latest_annotated_frame = None
latest_result = {"camion_detecte": False}
camera_ok = False

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


def camera_worker():
    global latest_frame, latest_annotated_frame, latest_result, camera_ok

    cap = None
    current_portail_id = None
    last_infer = 0.0
    last_portail_check = 0.0

    while True:
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
                side_margin=float(p["side_margin"]),
            )
            last_infer = now

        annotated = annotate_frame(frame.copy(), result)
        with state_lock:
            latest_frame = frame
            latest_annotated_frame = annotated
            latest_result = result


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
        image_path=f"captures/{filename}",
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
            side_margin=float(p["side_margin"]),
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
                image_path=f"captures/{filename}",
            )

        resultat = {
            "statut": statut,
            "ratio_bleu": result.get("ratio_bleu", 0.0),
            "confiance": result.get("confiance"),
            "image_path": f"captures/{filename}",
        }
        return render_template("analyser.html", active="analyser", resultat=resultat, erreur=None)

    return render_template("analyser.html", active="analyser", resultat=None, erreur=None)


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
    return redirect(request.referrer or url_for("historique"))


@app.route("/parametres", methods=["GET", "POST"])
@login_required
def parametres():
    global current_params

    if request.method == "POST":
        for cle in ("seuil_bleu", "top_ratio", "side_margin"):
            valeur = request.form.get(cle)
            if valeur:
                db.set_parametre(cle, valeur)
        with params_lock:
            current_params = db.get_parametres()
        return redirect(url_for("parametres", enregistre="1"))

    return render_template(
        "parametres.html", params=get_current_params(), enregistre=request.args.get("enregistre"),
        active="parametres",
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
                db.add_portail(nom, camera_source)
        elif action == "activer":
            portail_id = request.form.get("portail_id")
            if portail_id:
                db.set_portail_actif(int(portail_id))
        return redirect(url_for("portails"))

    return render_template("portails.html", portails=db.list_portails(), active="portails")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
