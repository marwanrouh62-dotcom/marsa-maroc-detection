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


def extract_benne_roi(frame, bbox, top_ratio=0.45, left_margin=0.05, right_margin=0.05, top_margin=0.05):
    """
    Approxime la zone de la bâche à partir de la bounding box du camion.

    Hypothèse par défaut (vue de côté, à calibrer sur site selon l'angle
    réel de la caméra du portail) : sur un camion benne bâché, la bâche
    forme un bombé au-dessus de la caisse, dans la partie HAUTE du camion
    (au-dessus des parois métalliques et du châssis/roues qui occupent le
    bas). `top_margin` exclut une fine bande tout en haut (ciel, antenne...),
    `top_ratio` définit la fraction de hauteur analysée à partir de là.

    `left_margin`/`right_margin` sont volontairement indépendants (pas une
    seule marge symétrique) : sur une caméra fixe qui voit le camion de
    face/3-4, la cabine occupe un côté entier de la bbox (pas juste un
    petit bord) et doit être exclue via une grande marge de CE côté (ex.
    left_margin=0.65 si la cabine est à gauche), tout en gardant l'autre
    côté (la caisse/le conteneur) presque intact.
    """
    x1, y1, x2, y2 = bbox
    h = y2 - y1
    w = x2 - x1
    roi_y1 = y1 + int(h * top_margin)
    roi_y2 = y1 + int(h * (top_margin + top_ratio))
    roi_x1 = x1 + int(w * left_margin)
    roi_x2 = x2 - int(w * right_margin)
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
