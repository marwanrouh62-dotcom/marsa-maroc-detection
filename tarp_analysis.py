"""
Jour 2 - Module de détection de la bâche bleue.
Extraction de la ROI "benne" à partir de la bounding box du camion,
conversion HSV et calcul du % de pixels bleus pour décider Chargé/Vide.
"""
import cv2
import numpy as np

# Plage HSV du bleu (bâche). H sur [0,179] côté OpenCV.
# V min bas (15) car en faible luminosité le bleu reste saturé (S) mais s'assombrit
# fortement (V) ; S min élevé (60) reste le vrai discriminant face au gris/asphalte.
# À calibrer sur site selon la couleur exacte de la bâche et l'éclairage.
BLUE_HSV_LOWER = (90, 60, 15)
BLUE_HSV_UPPER = (130, 255, 255)

# Seuil de décision : au-delà de ce % de pixels bleus dans la ROI -> "Chargé".
BLUE_RATIO_THRESHOLD = 0.35


def extract_benne_roi(frame, bbox, top_ratio=0.45, side_margin=0.05, top_margin=0.05):
    """
    Approxime la zone de la bâche à partir de la bounding box du camion.

    Hypothèse (à calibrer sur site selon l'angle de la caméra du portail) :
    sur un camion benne bâché, la bâche forme un bombé au-dessus de la caisse,
    dans la partie HAUTE du camion (au-dessus des parois métalliques et du
    châssis/roues qui occupent le bas). `top_margin` exclut une fine bande
    tout en haut (ciel, antenne...), `top_ratio` définit la fraction de
    hauteur analysée à partir de là, `side_margin` rogne les bords latéraux.
    """
    x1, y1, x2, y2 = bbox
    h = y2 - y1
    w = x2 - x1
    roi_y1 = y1 + int(h * top_margin)
    roi_y2 = y1 + int(h * (top_margin + top_ratio))
    roi_x1 = x1 + int(w * side_margin)
    roi_x2 = x2 - int(w * side_margin)
    roi_box = (roi_x1, roi_y1, roi_x2, roi_y2)
    return frame[roi_y1:roi_y2, roi_x1:roi_x2], roi_box


def blue_pixel_ratio(roi_bgr):
    """Calcule le % de pixels dans la plage bleue HSV pour une ROI donnée."""
    if roi_bgr.size == 0:
        return 0.0
    hsv = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, BLUE_HSV_LOWER, BLUE_HSV_UPPER)
    return float(np.count_nonzero(mask)) / mask.size


def decide_status(ratio, threshold=BLUE_RATIO_THRESHOLD):
    return "Chargé" if ratio >= threshold else "Vide"
