"""
Jour 2 - Pipeline complet de test : détection camion (YOLO) + extraction ROI
benne + analyse HSV -> statut Chargé/Vide.

Usage:
    python detect_status.py                     # capture depuis la webcam
    python detect_status.py --image path.jpg
    python detect_status.py --video path.mp4
    python detect_status.py --image path.jpg --threshold 0.25 --top-ratio 0.3
"""
import argparse
import sys

import cv2

from pipeline import annotate_frame, run_pipeline


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


def main():
    parser = argparse.ArgumentParser(description="Pipeline camion + bâche bleue")
    parser.add_argument("--image", help="Chemin vers une image de test")
    parser.add_argument("--video", help="Chemin vers une vidéo de test")
    parser.add_argument("--threshold", type=float, default=0.30, help="Seuil % pixels bleus")
    parser.add_argument("--top-ratio", type=float, default=0.35, help="Fraction haute de la bbox exclue (cabine)")
    parser.add_argument("--side-margin", type=float, default=0.05, help="Marge latérale rognée de la ROI")
    args = parser.parse_args()

    frame = grab_frame(args.image, args.video)
    result = run_pipeline(frame, threshold=args.threshold, top_ratio=args.top_ratio, side_margin=args.side_margin)

    if not result["camion_detecte"]:
        print("Aucun camion détecté.")
    else:
        print(f"Camion détecté ({result['label']}) - confiance={result['confiance']:.2f} - bbox={result['bbox']}")
        print(
            f"ROI benne={result['roi_box']} - % pixels bleus={result['ratio_bleu'] * 100:.1f}% "
            f"- seuil={args.threshold * 100:.0f}% -> {result['statut']}"
        )

    annotated = annotate_frame(frame, result)
    cv2.imwrite("status_output.jpg", annotated)
    print("Résultat sauvegardé dans status_output.jpg")


if __name__ == "__main__":
    main()
