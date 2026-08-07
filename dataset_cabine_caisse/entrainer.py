"""
Entraîne un modèle YOLOv8n fine-tuné pour détecter "cabine" et "caisse"
séparément, à partir du jeu de données jouet préparé par preparer_dataset.py.

⚠️ 5 images d'entraînement / 2 de validation : suffisant pour prouver que le
mécanisme (entraînement + intégration) fonctionne de bout en bout, très
insuffisant pour un modèle fiable en production. Voir MANUEL_TECHNIQUE.md.
"""
import os

from ultralytics import YOLO

DATA_YAML = os.path.join(os.path.dirname(__file__), "data.yaml")
MODELE_BASE = os.path.join(os.path.dirname(__file__), "..", "yolov8n.pt")


def main():
    model = YOLO(MODELE_BASE)
    model.train(
        data=DATA_YAML,
        epochs=60,
        imgsz=640,
        batch=4,
        patience=0,
        project=os.path.dirname(__file__),
        name="entrainement",
        exist_ok=True,
        verbose=False,
    )


if __name__ == "__main__":
    main()
