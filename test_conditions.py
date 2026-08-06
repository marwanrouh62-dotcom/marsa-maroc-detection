"""
Jour 6 - Tests sur différentes conditions (luminosité, contraste, angle, flou)
et vérification de la robustesse du seuil HSV.

Génère des variantes des images de test réelles (test_images/) simulant :
- luminosité faible / forte
- contraste faible / fort
- flou (mise au point / distance)
- rotation légère (angle de caméra)

Puis exécute le pipeline complet sur chaque variante et rapporte le statut.
"""
import os

import cv2

from pipeline import annotate_frame, run_pipeline

TEST_IMAGES = [
    "test_images/camion_bache_1.jpg",
    "test_images/camion_bache_2.png",
    "test_images/camion_conteneur_sans_bache.png",
]
OUT_DIR = "test_images/conditions"


def adjust_brightness_contrast(img, alpha=1.0, beta=0):
    return cv2.convertScaleAbs(img, alpha=alpha, beta=beta)


def rotate(img, angle):
    h, w = img.shape[:2]
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(img, matrix, (w, h), borderMode=cv2.BORDER_REPLICATE)


def blur(img, ksize=9):
    return cv2.GaussianBlur(img, (ksize, ksize), 0)


def build_variants(img):
    return {
        "original": img,
        # Luminosité simulée par un facteur multiplicatif (photons en moins, teinte
        # préservée) : c'est ainsi qu'une caméra réagit à la lumière ambiante.
        # Une simulation additive (beta) déforme artificiellement la teinte (cf. Jour 6).
        "faible luminosité (alpha=0.35)": adjust_brightness_contrast(img, alpha=0.35, beta=0),
        "forte luminosité (alpha=1.6)": adjust_brightness_contrast(img, alpha=1.6, beta=0),
        "faible contraste (alpha=0.5)": adjust_brightness_contrast(img, alpha=0.5, beta=40),
        "fort contraste (alpha=1.8)": adjust_brightness_contrast(img, alpha=1.8, beta=-40),
        "flou (ksize=9)": blur(img, 9),
        "angle -12deg": rotate(img, -12),
        "angle +12deg": rotate(img, 12),
    }


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    header = f"{'image':30s} {'variante':30s} {'camion':7s} {'conf':6s} {'%bleu':7s} {'statut':10s}"
    print(header)
    print("-" * len(header))

    for path in TEST_IMAGES:
        base = cv2.imread(path)
        if base is None:
            print(f"Impossible de lire {path}")
            continue

        base_name = os.path.splitext(os.path.basename(path))[0]
        for variant_name, variant_img in build_variants(base).items():
            result = run_pipeline(variant_img)
            camion = "oui" if result["camion_detecte"] else "non"
            conf = f"{result['confiance']:.2f}" if result.get("confiance") is not None else "-"
            ratio = f"{result['ratio_bleu'] * 100:.1f}%" if result.get("ratio_bleu") is not None else "-"
            statut = result.get("statut", "-")
            print(f"{base_name:30s} {variant_name:30s} {camion:7s} {conf:6s} {ratio:7s} {statut:10s}")

            annotated = annotate_frame(variant_img.copy(), result)
            out_name = f"{base_name}__{variant_name.replace(' ', '_').replace('/', '-')}.jpg"
            cv2.imwrite(os.path.join(OUT_DIR, out_name), annotated)


if __name__ == "__main__":
    main()
