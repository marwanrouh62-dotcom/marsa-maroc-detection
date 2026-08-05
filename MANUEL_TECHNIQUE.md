# Manuel technique — Détection de remplissage des camions (Marsa Maroc)

## 1. Architecture

100% Python, exécution locale.

- **Détection camion** : YOLOv8n pré-entraîné (COCO, `yolov8n.pt`), classes retenues : `truck` (7), `bus` (5).
- **Détection bâche** : extraction d'une ROI dans la bbox du camion, conversion HSV, seuillage sur la teinte bleue.
- **Backend** : Flask (serveur de dev), flux vidéo en MJPEG.
- **Stockage** : SQLite (`marsa_maroc.db`).
- **Frontend** : Flask + Jinja2 (pas de framework JS).

## 2. Structure des fichiers

| Fichier | Rôle |
|---|---|
| `pipeline.py` | Pipeline de détection partagé (YOLO + ROI + HSV), utilisé par le CLI et le backend. |
| `tarp_analysis.py` | Extraction ROI benne + calcul % pixels bleus + décision Chargé/Vide. Constantes HSV et seuil par défaut. |
| `db.py` | Accès SQLite : portails, détections, paramètres réglables, corrections manuelles, utilisateurs. |
| `app.py` | Serveur Flask : authentification par session, thread caméra en continu (avec bascule dynamique de portail actif), flux `/video_feed`, routes `/`, `/capturer`, `/historique` (+ export CSV), `/portails`, `/parametres`. |
| `detect_truck.py` | Script CLI Jour 1 : détection camion seule (démo/debug). |
| `detect_status.py` | Script CLI Jour 2+ : pipeline complet camion + bâche sur image/vidéo/webcam. |
| `test_conditions.py` | Script de test de robustesse (luminosité, contraste, flou, angle) sur images réelles. |
| `templates/` | Pages Jinja2 (`base.html`, `index.html`, `historique.html`, `parametres.html`, `portails.html`, `login.html`). |
| `static/css/style.css` | Feuille de style unique partagée par toutes les pages. |
| `test_images/` | Photos de test réelles + variantes générées, utilisées pour valider le pipeline. |
| `static/captures/` | Images annotées enregistrées via le bouton "Enregistrer". |
| `RAPPORT_TESTS.md` | Rapport de tests consolidé (détection, HSV, robustesse, fonctionnel). |

## 3. Base de données (SQLite)

- **`portails`** : `id`, `nom`, `camera_source` (index webcam ou URL RTSP), `actif`. Portail initial : "Terminal Polyvalent" (`camera_source = "0"`). Un seul portail `actif=1` à la fois (`db.set_portail_actif()` désactive les autres).
- **`detections`** : `id`, `portail_id`, `statut`, `ratio_bleu`, `confiance`, `image_path`, `horodatage`, `statut_original`, `corrige`.
- **`parametres`** : `cle`/`valeur` — `seuil_bleu` (défaut 0.30), `top_ratio` (défaut 0.35), `side_margin` (défaut 0.05).
- **`utilisateurs`** : `id`, `identifiant`, `mot_de_passe_hash` (Werkzeug `generate_password_hash`). Compte `admin`/`admin123` créé automatiquement si la table est vide au premier démarrage.

`db.init_db()` crée le schéma et migre automatiquement les colonnes manquantes sur une base existante (`ALTER TABLE`).

## 3bis. Authentification et multi-portails

- **Auth** : session Flask (`app.secret_key = os.urandom(24)`, régénérée à chaque démarrage — les sessions ne survivent pas à un redémarrage du serveur, acceptable pour un usage local). Décorateur `login_required` sur toutes les routes sauf `/login`. Mot de passe vérifié via `werkzeug.security.check_password_hash`.
- **Multi-portails** : le thread caméra (`camera_worker` dans `app.py`) relit `db.get_portail_actif()` toutes les `PORTAIL_POLL_INTERVAL` (1s) et rouvre la capture vidéo si le portail actif a changé (`cv2.VideoCapture` fermé/rouvert). Une seule caméra est donc pilotée à la fois — le multi-portails ici gère plusieurs configurations de caméra, pas plusieurs flux simultanés (limite matérielle du poste local, pas de l'architecture DB).

## 4. Pipeline de détection (`pipeline.run_pipeline`)

1. `detect_truck_bbox()` : inférence YOLOv8n, garde la détection `truck`/`bus` la plus confiante (seuil de confiance 0.4).
2. `extract_benne_roi()` : approxime la benne comme la partie basse/arrière de la bbox (exclut le haut = cabine via `top_ratio`, rogne les bords via `side_margin`). **Heuristique non calibrée sur un vrai portail** — à ajuster selon l'angle de caméra réel (paramètres réglables en interface).
3. `blue_pixel_ratio()` : conversion BGR→HSV, `cv2.inRange` avec `BLUE_HSV_LOWER=(90,60,15)` / `BLUE_HSV_UPPER=(130,255,255)`.
4. `decide_status()` : `ratio >= seuil_bleu` → "Chargé", sinon "Vide".

### Choix du seuil V minimum (15, pas 40)

Testé en Jour 6 : un seuil V trop élevé (40) fait passer les vrais camions bâchés en faux "Vide" sous faible luminosité, car l'atténuation lumineuse réelle (multiplicative) fait chuter V bien plus que la teinte (H) ou la saturation (S). V=15 avec S≥60 reste sélectif (pas de faux positif sur asphalte/gris, vérifié).

## 5. Limite connue

La règle de décision est basée uniquement sur la couleur bleue de la bâche, comme demandé au cahier des charges (pas de dataset custom). Un camion chargé mais **sans bâche bleue** (ex. porte-conteneur) sera classé "Vide" par le système — ce n'est pas un bug mais une limite assumée de l'approche colorimétrique. Validé sur photo réelle (21.6% de bleu résiduel, provenant du bras de grue bleu de l'engin, sous le seuil de 30%).

## 6. Tests effectués

- Détection camion sur image d'exemple Ultralytics (`bus.jpg`) et 3 photos réelles (2 camions bâchés bleu, 1 porte-conteneur sans bâche).
- Analyse HSV validée sur ROI synthétiques (bleu pur, gris, mixte 40%).
- Robustesse (`test_conditions.py`) : 24 combinaisons (3 photos × luminosité/contraste/flou/angle ±12°) — 0 erreur de classification après correctif du seuil V.

## 7. Lancement

```
.venv\Scripts\python.exe app.py
```
Serveur sur `http://127.0.0.1:5000`. Dépendances dans `requirements.txt` (`pip install -r requirements.txt`).

## 8. Limites de déploiement actuelles

- Authentification basique (session + mot de passe), pas de SSO (explicitement exclu du cahier des charges). Pas de gestion des rôles (agent/superviseur/administrateur) ni de page de changement de mot de passe dans cette version — un seul niveau d'accès.
- Multi-portails : un seul flux caméra actif à la fois (voir §3bis) — adapté à un poste de contrôle local avec une caméra à la fois, pas à une supervision multi-portails simultanée.
- Clé de session générée aléatoirement à chaque démarrage (déconnexion de tous les agents à chaque redémarrage du serveur).

## 9. Déploiement cloud (Render, Railway, etc.)

### Différences avec le déploiement local

- **Pas de webcam** : un serveur cloud n'a pas de caméra USB locale. Deux options :
  - configurer un portail avec une **URL RTSP** d'une caméra IP accessible depuis internet (`camera_source` accepte déjà n'importe quelle chaîne non numérique, aucun changement de code requis) ;
  - utiliser la page **"Analyser une photo"** (`/analyser`) qui exécute le pipeline sur une image envoyée manuellement — pas de flux vidéo requis. C'est le mode principal d'utilisation en environnement cloud sans caméra IP.
- La page d'accueil détecte automatiquement l'absence de flux (`camera_ok`) et affiche un message avec lien vers "Analyser une photo" au lieu de planter.

### Fichiers de déploiement fournis

- **`Dockerfile`** : image `python:3.11-slim`, installe `libgl1`/`libglib2.0-0` (dépendances système d'OpenCV), lance `gunicorn` avec **`--workers 1`**. Un seul worker est volontaire : le thread caméra (`camera_worker`) et les connexions SQLite ne sont pas conçus pour tourner en plusieurs processus simultanés — plusieurs workers dupliqueraient le thread caméra et pourraient créer des conflits d'accès à la source vidéo.
- **`Procfile`** / **`runtime.txt`** : pour un déploiement par buildpack (sans Docker) sur des plateformes qui le supportent.
- **`app.py`** lit le port depuis la variable d'environnement `PORT` (fournie automatiquement par Render/Railway) et écoute sur `0.0.0.0`.

### Persistance des données

⚠️ **`marsa_maroc.db` et `static/captures/` sont écrits sur le disque du conteneur.** Sur la plupart des offres gratuites (Render, Railway), le système de fichiers est **éphémère** : historique et images capturées sont perdus à chaque redéploiement ou redémarrage du conteneur, sauf si un volume/disque persistant est attaché (fonctionnalité généralement payante). À prévoir avant une mise en production réelle.

### Ressources nécessaires

`torch` + `ultralytics` + `opencv` représentent une installation lourde (~1-2 Go une fois installés) et une consommation mémoire significative à l'exécution. Les paliers gratuits les plus limités (souvent 512 Mo de RAM) risquent d'être insuffisants ou de rendre le build très lent — prévoir un palier avec au moins 1-2 Go de RAM.

### `requirements.txt`

Réduit aux dépendances directement utilisées par l'application (`Flask`, `opencv-python-headless`, `ultralytics`, `numpy`, `gunicorn`) — l'ancien fichier (généré par `pip freeze` sur l'environnement de développement) contenait aussi des frameworks explorés puis non retenus (Streamlit, FastAPI...), inutiles au runtime et alourdissant le build cloud.
