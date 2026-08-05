# Détection de remplissage des camions — Marsa Maroc

Application web 100% Python de détection automatique de l'état de remplissage des camions (chargé/vide) par vision par ordinateur, pour les portails d'entrée de terminaux portuaires.

- **Détection camion** : YOLOv8n pré-entraîné (COCO), sans dataset personnalisé.
- **Détection de chargement** : analyse colorimétrique HSV de la bâche bleue sur la zone de la benne.
- **Backend** : Flask + SQLite.
- **Frontend** : Flask + Jinja2 (pas de JS framework).

## Fonctionnalités

- Flux caméra en direct avec statut incrusté en temps réel (Chargé / Vide).
- Analyse à la demande par upload de photo (utile sans caméra locale, ex. déploiement cloud).
- Historique horodaté, filtrable par date/statut, exportable en CSV.
- Correction manuelle d'un statut mal détecté, avec traçabilité de la valeur d'origine.
- Seuils de détection réglables depuis l'interface, appliqués en direct.
- Gestion de plusieurs portails (caméras d'entrée), avec bascule entre sources.
- Authentification par session.

## Démarrage local

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
python app.py
```

Ouvrir `http://127.0.0.1:5000`. Identifiant par défaut : voir `MANUEL_UTILISATEUR.md` (à changer immédiatement après premier déploiement).

## Déploiement cloud (Docker)

Un `Dockerfile` et un `Procfile` sont fournis pour un déploiement sur Render, Railway ou équivalent.

⚠️ Un serveur cloud n'a pas accès à une webcam locale — utilisez soit une caméra IP (URL RTSP) comme source de portail, soit la page "Analyser une photo" (upload manuel).

## Documentation

- [`MANUEL_UTILISATEUR.md`](MANUEL_UTILISATEUR.md) — utilisation de l'application.
- [`MANUEL_TECHNIQUE.md`](MANUEL_TECHNIQUE.md) — architecture, base de données, pipeline de détection, déploiement.
- [`RAPPORT_TESTS.md`](RAPPORT_TESTS.md) — tests effectués (détection, robustesse, fonctionnel).

## Limites connues

- La détection de chargement se base uniquement sur la couleur bleue de la bâche (règle métier du cahier des charges) — un camion chargé sans bâche bleue sera classé "Vide".
- Un seul flux caméra actif à la fois (voir `MANUEL_TECHNIQUE.md`).
