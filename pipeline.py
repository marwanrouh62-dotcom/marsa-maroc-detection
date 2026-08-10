"""
Pipeline de détection partagé : camion (YOLO) + ROI benne + analyse HSV bâche bleue.
Utilisé par le script CLI (detect_status.py) et par le backend Flask (app.py).
"""
import os

import cv2
from ultralytics import YOLO

from tarp_analysis import blue_pixel_ratio, decide_status, extract_benne_roi

TRUCK_CLASSES = {7: "truck", 5: "bus"}
# YOLOv8s plutôt que YOLOv8n : confiance moyenne mesurée 0.86 -> 0.92 sur les
# 6 photos de référence (jusqu'à 0.66 -> 0.94 sur le cas le plus faible),
# pour un coût d'environ 300-400ms/inférence au lieu de ~180ms — largement
# dans le budget de INFER_INTERVAL (0.7s) sur un CPU modeste.
MODEL_PATH = "yolov8s.pt"
CONF_THRESHOLD = 0.4

# Modèle optionnel fine-tuné pour détecter "cabine"/"caisse" séparément
# (voir dataset_cabine_caisse/). S'il existe, la ROI vient directement de sa
# détection de la caisse (fonctionne quel que soit l'angle de caméra) ; sinon
# on retombe sur l'heuristique géométrique (extract_benne_roi, calibrée pour
# une vue de côté par défaut).
CABINE_CAISSE_MODEL_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "dataset_cabine_caisse", "entrainement", "weights", "best.pt"
)
CAISSE_CLASS_ID = 1  # voir dataset_cabine_caisse/preparer_dataset.py : CLASSES = ["cabine", "caisse"]
CAISSE_CONF_THRESHOLD = 0.25

_model = None
_cabine_caisse_model = None
_cabine_caisse_disponible = None


def get_model():
    global _model
    if _model is None:
        _model = YOLO(MODEL_PATH)
    return _model


def get_cabine_caisse_model():
    global _cabine_caisse_model, _cabine_caisse_disponible
    if _cabine_caisse_disponible is None:
        _cabine_caisse_disponible = os.path.exists(CABINE_CAISSE_MODEL_PATH)
    if _cabine_caisse_disponible and _cabine_caisse_model is None:
        _cabine_caisse_model = YOLO(CABINE_CAISSE_MODEL_PATH)
    return _cabine_caisse_model


def detect_truck_bbox(frame):
    model = get_model()
    results = model.predict(frame, conf=CONF_THRESHOLD, verbose=False)[0]
    best_box, best_conf = None, -1.0
    for box in results.boxes:
        cls_id = int(box.cls[0])
        if cls_id not in TRUCK_CLASSES:
            continue
        conf = float(box.conf[0])
        if conf > best_conf:
            best_conf, best_box = conf, box

    if best_box is None:
        return None
    x1, y1, x2, y2 = map(int, best_box.xyxy[0].tolist())
    return (x1, y1, x2, y2), TRUCK_CLASSES[int(best_box.cls[0])], best_conf


def detect_caisse_bbox(frame):
    """Détecte la caisse via le modèle fine-tuné, s'il est disponible.
    Retourne (bbox, confiance) ou None (modèle absent ou rien détecté) —
    l'appelant doit alors se rabattre sur l'heuristique géométrique."""
    model = get_cabine_caisse_model()
    if model is None:
        return None

    results = model.predict(frame, conf=CAISSE_CONF_THRESHOLD, verbose=False)[0]
    best_box, best_conf = None, -1.0
    for box in results.boxes:
        if int(box.cls[0]) != CAISSE_CLASS_ID:
            continue
        conf = float(box.conf[0])
        if conf > best_conf:
            best_conf, best_box = conf, box

    if best_box is None:
        return None
    x1, y1, x2, y2 = map(int, best_box.xyxy[0].tolist())
    return (x1, y1, x2, y2), best_conf


def run_pipeline(
    frame, threshold=0.35, top_ratio=0.45, left_margin=0.05, right_margin=0.05, use_modele_caisse=False
):
    """
    Exécute le pipeline complet sur une frame et renvoie un dict de résultat.

    `use_modele_caisse` : désactivé par défaut. Le modèle fine-tuné
    cabine/caisse (dataset_cabine_caisse/) est entraîné sur seulement 5
    images — testé sur la suite de robustesse (test_conditions.py), il peut
    être confiant mais géométriquement imprécis sur des variantes qu'il n'a
    jamais vues (luminosité, flou...), ce qui a fait RÉGRESSER des cas
    auparavant corrects (voir RAPPORT_TESTS.md §9.2). Le seuil de confiance
    seul ne suffit pas à s'en protéger. À activer explicitement pour tester
    le modèle (voir dataset_cabine_caisse/evaluer.py), pas en usage courant
    tant qu'il n'est pas entraîné sur beaucoup plus de données.
    """
    detection = detect_truck_bbox(frame)
    if detection is None:
        return {"camion_detecte": False}

    bbox, label, conf = detection

    caisse_detection = detect_caisse_bbox(frame) if use_modele_caisse else None
    roi_source = "modele"
    if caisse_detection is not None:
        roi_box, _caisse_conf = caisse_detection
        x1, y1, x2, y2 = roi_box
        roi = frame[y1:y2, x1:x2]
    else:
        roi_source = "heuristique"
        roi, roi_box = extract_benne_roi(
            frame, bbox, top_ratio=top_ratio, left_margin=left_margin, right_margin=right_margin
        )

    ratio = blue_pixel_ratio(roi)
    statut = decide_status(ratio, threshold=threshold)

    return {
        "camion_detecte": True,
        "bbox": bbox,
        "label": label,
        "confiance": conf,
        "roi_box": roi_box,
        "roi_source": roi_source,
        "ratio_bleu": ratio,
        "statut": statut,
    }


def annotate_frame(frame, result):
    if result.get("bbox"):
        x1, y1, x2, y2 = result["bbox"]
        cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 0, 0), 2)
    if result.get("roi_box"):
        rx1, ry1, rx2, ry2 = result["roi_box"]
        cv2.rectangle(frame, (rx1, ry1), (rx2, ry2), (0, 255, 0), 2)
    if result.get("statut"):
        label = f"{result['statut']} ({result['ratio_bleu'] * 100:.1f}% bleu)"
        y_text = max(result["bbox"][1] - 10, 20)
        cv2.putText(frame, label, (10, y_text), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
    else:
        cv2.putText(frame, "Aucun camion detecte", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
    return frame
