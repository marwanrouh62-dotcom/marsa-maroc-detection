"""
Prépare le jeu de données d'entraînement pour le modèle cabine/caisse.

Annotations manuelles (bboxes en pixels, déterminées par inspection visuelle
des 7 photos réelles disponibles dans test_images/). Convertit au format YOLO
(classe x_centre y_centre largeur hauteur, normalisé [0,1]) et copie les
images dans dataset_cabine_caisse/images/{train,val}/.

⚠️ 7 images est un jeu de données jouet, très insuffisant pour un modèle
fiable en production — voir MANUEL_TECHNIQUE.md. Ce script sert de point de
départ / démonstration du mécanisme, pas d'un entraînement définitif.
"""
import os
import shutil

import cv2

CLASSES = ["cabine", "caisse"]

# (chemin_image, largeur, hauteur, [(classe, x1,y1,x2,y2), ...])
ANNOTATIONS = [
    ("camion_3quart_caisse_blanche.jpg", 1600, 1157, [
        ("cabine", 560, 420, 930, 950),
        ("caisse", 920, 420, 1090, 780),
    ]),
    ("camion_bache_1.jpg", 635, 335, [
        ("cabine", 485, 95, 572, 260),
        ("caisse", 115, 5, 485, 230),
    ]),
    ("camion_bache_2.png", 1024, 683, [
        ("cabine", 16, 175, 175, 590),
        ("caisse", 175, 87, 978, 610),
    ]),
    ("camion_benne_bache_haut.jpg", 940, 575, [
        ("cabine", 82, 192, 335, 460),
        ("caisse", 330, 220, 857, 483),
    ]),
    ("camion_bleu_cabine_sans_bache.jpg", 626, 313, [
        ("cabine", 195, 107, 347, 246),
        ("caisse", 132, 128, 250, 215),
    ]),
    ("camion_bleu_cabine_sans_bache_2.jpg", 626, 313, [
        ("cabine", 198, 81, 275, 212),
        ("caisse", 270, 87, 440, 195),
    ]),
    ("camion_conteneur_sans_bache.png", 603, 335, [
        ("cabine", 440, 6, 598, 330),
        ("caisse", 30, 15, 420, 215),
    ]),
]

# 2 images gardées aussi en "validation" — avec seulement 7 images au total,
# ce n'est pas un vrai jeu de val indépendant (fuite train/val), juste ce
# qu'il faut pour qu'ultralytics puisse calculer une métrique pendant
# l'entraînement de démonstration.
VAL_IMAGES = {"camion_bache_1.jpg", "camion_conteneur_sans_bache.png"}

SRC_DIR = os.path.join(os.path.dirname(__file__), "..", "test_images")
DST_DIR = os.path.dirname(__file__)


def to_yolo_line(classe, x1, y1, x2, y2, img_w, img_h):
    cls_id = CLASSES.index(classe)
    xc = (x1 + x2) / 2 / img_w
    yc = (y1 + y2) / 2 / img_h
    w = (x2 - x1) / img_w
    h = (y2 - y1) / img_h
    return f"{cls_id} {xc:.6f} {yc:.6f} {w:.6f} {h:.6f}"


def main():
    for filename, img_w, img_h, boxes in ANNOTATIONS:
        split = "val" if filename in VAL_IMAGES else "train"
        src_path = os.path.join(SRC_DIR, filename)

        frame = cv2.imread(src_path)
        if frame is None:
            print(f"ATTENTION: image introuvable, ignorée : {src_path}")
            continue
        actual_h, actual_w = frame.shape[:2]
        if (actual_w, actual_h) != (img_w, img_h):
            print(f"ATTENTION: dimensions différentes pour {filename} "
                  f"(attendu {img_w}x{img_h}, trouvé {actual_w}x{actual_h})")

        dst_img = os.path.join(DST_DIR, "images", split, filename)
        shutil.copyfile(src_path, dst_img)

        label_name = os.path.splitext(filename)[0] + ".txt"
        dst_label = os.path.join(DST_DIR, "labels", split, label_name)
        with open(dst_label, "w") as f:
            for classe, x1, y1, x2, y2 in boxes:
                f.write(to_yolo_line(classe, x1, y1, x2, y2, img_w, img_h) + "\n")

        print(f"{split:5s} {filename:40s} -> {len(boxes)} boîtes")

    data_yaml = os.path.join(DST_DIR, "data.yaml")
    with open(data_yaml, "w") as f:
        f.write(f"path: {os.path.abspath(DST_DIR)}\n")
        f.write("train: images/train\n")
        f.write("val: images/val\n")
        f.write(f"nc: {len(CLASSES)}\n")
        f.write(f"names: {CLASSES}\n")
    print(f"\nConfig écrite : {data_yaml}")


if __name__ == "__main__":
    main()
