"""
Évalue le pipeline complet (avec bascule automatique modèle cabine/caisse ->
heuristique géométrique) sur les 6 photos réelles de référence.

⚠️ Ces mêmes photos ont majoritairement servi à l'entraînement (voir
preparer_dataset.py) — ce n'est pas une évaluation indépendante /
généralisable, seulement une vérification de non-régression du mécanisme.
"""
import os
import sys

import cv2

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pipeline import annotate_frame, run_pipeline  # noqa: E402

CAS_DE_TEST = [
    ("camion_bache_1", "test_images/camion_bache_1.jpg", "Chargé"),
    ("camion_bache_2", "test_images/camion_bache_2.png", "Chargé"),
    ("camion_benne_bache_haut", "test_images/camion_benne_bache_haut.jpg", "Chargé"),
    ("conteneur_sans_bache", "test_images/camion_conteneur_sans_bache.png", "Vide"),
    ("cabine_bleue_sans_bache", "test_images/camion_bleu_cabine_sans_bache_2.jpg", "Vide"),
    ("3quart_caisse_blanche", "test_images/camion_3quart_caisse_blanche.jpg", "Vide"),
]


def main():
    corrects = 0
    header = f"{'photo':30s} {'source ROI':12s} {'% bleu':8s} {'statut':10s} {'attendu':10s}"
    print(header)
    print("-" * len(header))

    for nom, path, attendu in CAS_DE_TEST:
        frame = cv2.imread(path)
        resultat = run_pipeline(frame, use_modele_caisse=True)
        bon = attendu in resultat["statut"]
        corrects += bon
        marque = "OK" if bon else "FAUX"
        print(
            f"{nom:30s} {resultat.get('roi_source', '-'):12s} "
            f"{resultat['ratio_bleu'] * 100:6.1f}% {resultat['statut']:10s} {attendu:10s} {marque}"
        )
        annotated = annotate_frame(frame.copy(), resultat)
        cv2.imwrite(f"dataset_cabine_caisse/eval_{path.split('/')[-1]}", annotated)

    print(f"\n{corrects}/{len(CAS_DE_TEST)} corrects")


if __name__ == "__main__":
    main()
