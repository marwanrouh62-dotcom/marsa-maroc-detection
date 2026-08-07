"""
Base SQLite : portails (caméras d'entrée), historique des détections,
paramètres réglables et comptes utilisateurs.
"""
import sqlite3
from datetime import datetime

from werkzeug.security import generate_password_hash

DB_PATH = "marsa_maroc.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS portails (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nom TEXT NOT NULL UNIQUE,
    camera_source TEXT NOT NULL DEFAULT '0',
    actif INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS detections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    portail_id INTEGER NOT NULL,
    statut TEXT NOT NULL,
    ratio_bleu REAL NOT NULL,
    confiance REAL,
    image_path TEXT,
    horodatage TEXT NOT NULL,
    statut_original TEXT,
    corrige INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (portail_id) REFERENCES portails (id)
);

CREATE TABLE IF NOT EXISTS parametres (
    cle TEXT PRIMARY KEY,
    valeur TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS utilisateurs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    identifiant TEXT NOT NULL UNIQUE,
    mot_de_passe_hash TEXT NOT NULL
);
"""

# Portails connus au démarrage : nom -> source caméra (index webcam ou URL RTSP).
PORTAILS_INITIAUX = {
    "Terminal Polyvalent": "0",
}

# Seuils/paramètres de détection réglables depuis l'interface (Jour 5).
PARAMETRES_INITIAUX = {
    "seuil_bleu": "0.35",
    "top_ratio": "0.45",
    "left_margin": "0.05",
    "right_margin": "0.05",
}

# Compte admin créé au premier démarrage si aucun utilisateur n'existe.
# À changer après le premier déploiement (voir manuel utilisateur).
ADMIN_INITIAL = ("admin", "admin123")


def _migrer_colonnes_detections(conn):
    colonnes = {row["name"] for row in conn.execute("PRAGMA table_info(detections)")}
    if "statut_original" not in colonnes:
        conn.execute("ALTER TABLE detections ADD COLUMN statut_original TEXT")
    if "corrige" not in colonnes:
        conn.execute("ALTER TABLE detections ADD COLUMN corrige INTEGER NOT NULL DEFAULT 0")


def _migrer_side_margin(conn):
    """side_margin (marge symétrique) remplacé par left_margin/right_margin
    (marges indépendantes, nécessaires pour exclure une cabine qui occupe
    tout un côté de la bbox sur une vue de face/3-4)."""
    row = conn.execute("SELECT valeur FROM parametres WHERE cle = 'side_margin'").fetchone()
    if row is None:
        return
    for cle in ("left_margin", "right_margin"):
        conn.execute("INSERT OR IGNORE INTO parametres (cle, valeur) VALUES (?, ?)", (cle, row["valeur"]))
    conn.execute("DELETE FROM parametres WHERE cle = 'side_margin'")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    conn.executescript(SCHEMA)
    _migrer_colonnes_detections(conn)
    _migrer_side_margin(conn)
    for nom, camera_source in PORTAILS_INITIAUX.items():
        conn.execute(
            "INSERT OR IGNORE INTO portails (nom, camera_source) VALUES (?, ?)",
            (nom, camera_source),
        )
    for cle, valeur in PARAMETRES_INITIAUX.items():
        conn.execute(
            "INSERT OR IGNORE INTO parametres (cle, valeur) VALUES (?, ?)",
            (cle, valeur),
        )
    nb_utilisateurs = conn.execute("SELECT COUNT(*) AS n FROM utilisateurs").fetchone()["n"]
    if nb_utilisateurs == 0:
        identifiant, mot_de_passe = ADMIN_INITIAL
        conn.execute(
            "INSERT INTO utilisateurs (identifiant, mot_de_passe_hash) VALUES (?, ?)",
            (identifiant, generate_password_hash(mot_de_passe)),
        )
    conn.commit()
    conn.close()


def set_mot_de_passe(identifiant, nouveau_mot_de_passe):
    conn = get_connection()
    conn.execute(
        "UPDATE utilisateurs SET mot_de_passe_hash = ? WHERE identifiant = ?",
        (generate_password_hash(nouveau_mot_de_passe), identifiant),
    )
    conn.commit()
    conn.close()


def get_utilisateur(identifiant):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM utilisateurs WHERE identifiant = ?", (identifiant,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_parametres():
    conn = get_connection()
    rows = conn.execute("SELECT cle, valeur FROM parametres").fetchall()
    conn.close()
    return {row["cle"]: row["valeur"] for row in rows}


def set_parametre(cle, valeur):
    conn = get_connection()
    conn.execute("UPDATE parametres SET valeur = ? WHERE cle = ?", (str(valeur), cle))
    conn.commit()
    conn.close()


def corriger_detection(detection_id, nouveau_statut):
    conn = get_connection()
    row = conn.execute(
        "SELECT statut, statut_original FROM detections WHERE id = ?", (detection_id,)
    ).fetchone()
    if row is None:
        conn.close()
        return
    statut_original = row["statut_original"] or row["statut"]
    conn.execute(
        "UPDATE detections SET statut = ?, statut_original = ?, corrige = 1 WHERE id = ?",
        (nouveau_statut, statut_original, detection_id),
    )
    conn.commit()
    conn.close()


def list_portails():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM portails").fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_portail_by_nom(nom):
    conn = get_connection()
    row = conn.execute("SELECT * FROM portails WHERE nom = ?", (nom,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_portail_actif():
    conn = get_connection()
    row = conn.execute("SELECT * FROM portails WHERE actif = 1 LIMIT 1").fetchone()
    conn.close()
    return dict(row) if row else None


def add_portail(nom, camera_source):
    conn = get_connection()
    conn.execute(
        "INSERT INTO portails (nom, camera_source, actif) VALUES (?, ?, 0)",
        (nom, camera_source),
    )
    conn.commit()
    conn.close()


def set_portail_actif(portail_id):
    conn = get_connection()
    conn.execute("UPDATE portails SET actif = 0")
    conn.execute("UPDATE portails SET actif = 1 WHERE id = ?", (portail_id,))
    conn.commit()
    conn.close()


def add_detection(portail_id, statut, ratio_bleu, confiance=None, image_path=None):
    conn = get_connection()
    conn.execute(
        """INSERT INTO detections (portail_id, statut, ratio_bleu, confiance, image_path, horodatage)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (portail_id, statut, ratio_bleu, confiance, image_path, datetime.now().isoformat(timespec="seconds")),
    )
    conn.commit()
    conn.close()


def list_detections(portail_id=None, limit=100, date=None, statut=None):
    query = "SELECT * FROM detections WHERE 1=1"
    params = []
    if portail_id:
        query += " AND portail_id = ?"
        params.append(portail_id)
    if date:
        query += " AND horodatage LIKE ?"
        params.append(f"{date}%")
    if statut:
        query += " AND statut = ?"
        params.append(statut)
    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)

    conn = get_connection()
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(row) for row in rows]


if __name__ == "__main__":
    init_db()
    print("Base initialisée :", DB_PATH)
    for portail in list_portails():
        print(" -", portail)
