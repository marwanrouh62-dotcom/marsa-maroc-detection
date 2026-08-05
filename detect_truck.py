"""
Jour 1 - Détection camion avec YOLOv8 pré-entraîné (COCO).
Capture une image (webcam ou fichier), détecte les camions et
extrait la bounding box du camion le plus confiant.

Usage:
    python detect_truck.py                   # capture depuis la webcam
    python detect_truck.py --image path.jpg  # depuis un fichier image
    python detect_truck.py --video path.mp4  # depuis un fichier vidéo (1re frame lisible)
"""
import argparse
import sys

import cv2

from pipeline import detect_truck_bbox


def grab_frame(image_path, video_path):
    if image_path:
        frame = cv2.imread(image_path)
        if frame is None:
            sys.exit(f"Impossible de lire l'image : {image_path}")
        return frame

    source = video_path if video_path else 0
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        sys.exit(f"Impossible d'ouvrir la source vidéo : {source}")
    ret, frame = cap.read()
    cap.release()
    if not ret:
        sys.exit("Aucune frame capturée.")
    return frame


def annotate_and_save(frame, detection, out_path="detection_output.jpg"):
    if detection is not None:
        (x1, y1, x2, y2), label, conf = detection
        cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 0, 0), 2)
        cv2.putText(
            frame, f"{label} {conf:.2f}", (x1, max(y1 - 10, 0)),
            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2,
        )
    cv2.imwrite(out_path, frame)
    print(f"Résultat sauvegardé dans {out_path}")


def main():
    parser = argparse.ArgumentParser(description="Détection de camion via YOLOv8 pré-entraîné")
    parser.add_argument("--image", help="Chemin vers une image de test")
    parser.add_argument("--video", help="Chemin vers une vidéo de test")
    args = parser.parse_args()

    frame = grab_frame(args.image, args.video)
    detection = detect_truck_bbox(frame)

    if detection is None:
        print("Aucun camion détecté dans l'image.")
    else:
        (x1, y1, x2, y2), label, conf = detection
        print(f"Camion détecté ({label}) - confiance={conf:.2f} - bbox=({x1}, {y1}, {x2}, {y2})")

    annotate_and_save(frame, detection)


if __name__ == "__main__":
    main()
