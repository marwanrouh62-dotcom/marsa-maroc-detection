"""
Pipeline de détection partagé : camion (YOLO) + ROI benne + analyse HSV bâche bleue.
Utilisé par le script CLI (detect_status.py) et par le backend Flask (app.py).
"""
import cv2
from ultralytics import YOLO

from tarp_analysis import blue_pixel_ratio, decide_status, extract_benne_roi

TRUCK_CLASSES = {7: "truck", 5: "bus"}
MODEL_PATH = "yolov8n.pt"
CONF_THRESHOLD = 0.4

_model = None


def get_model():
    global _model
    if _model is None:
        _model = YOLO(MODEL_PATH)
    return _model


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


def run_pipeline(frame, threshold=0.35, top_ratio=0.45, side_margin=0.05):
    """Exécute le pipeline complet sur une frame et renvoie un dict de résultat."""
    detection = detect_truck_bbox(frame)
    if detection is None:
        return {"camion_detecte": False}

    bbox, label, conf = detection
    roi, roi_box = extract_benne_roi(frame, bbox, top_ratio=top_ratio, side_margin=side_margin)
    ratio = blue_pixel_ratio(roi)
    statut = decide_status(ratio, threshold=threshold)

    return {
        "camion_detecte": True,
        "bbox": bbox,
        "label": label,
        "confiance": conf,
        "roi_box": roi_box,
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
