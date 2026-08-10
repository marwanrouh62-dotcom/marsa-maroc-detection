"""
Tests unitaires de SuiviPassage (enregistrement automatique du passage d'un
camion) avec des séquences temporelles synthétiques — pas besoin d'un vrai
camion devant la caméra pour vérifier cette logique.
"""
from passage_tracker import SuiviPassage


def _resultat(charge, ratio=0.5, confiance=0.9):
    return {
        "camion_detecte": True,
        "statut": "Chargé" if charge else "Vide",
        "ratio_bleu": ratio,
        "confiance": confiance,
    }


def _absence():
    return {"camion_detecte": False}


def test_passage_normal_est_enregistre_une_fois():
    suivi = SuiviPassage(duree_min_presence=1.5, duree_grace_absence=1.0)
    resultats = [suivi.observer(_resultat(True), t) for t in [0.0, 0.7, 1.4, 2.1, 2.8]]
    resultats.append(suivi.observer(_absence(), 3.5))  # grâce pas écoulée
    resultats.append(suivi.observer(_absence(), 4.0))  # grâce écoulée -> finalise

    finalises = [r for r in resultats if r is not None]
    assert len(finalises) == 1, f"attendu 1 enregistrement, obtenu {len(finalises)}"
    assert finalises[0]["statut"] == "Chargé"


def test_detection_isolee_nest_pas_enregistree():
    suivi = SuiviPassage(duree_min_presence=1.5, duree_grace_absence=1.0)
    r1 = suivi.observer(_resultat(True), 10.0)
    r2 = suivi.observer(_absence(), 10.7)
    r3 = suivi.observer(_absence(), 11.5)
    assert r1 is None and r2 is None and r3 is None, "une détection isolée (bruit) ne doit pas être enregistrée"


def test_image_ratee_au_milieu_ne_coupe_pas_le_passage():
    suivi = SuiviPassage(duree_min_presence=1.5, duree_grace_absence=1.0)
    sequence = [(0.0, True), (0.7, True), (1.4, False), (2.1, True), (2.8, True), (3.5, False), (4.6, False)]
    resultats = [suivi.observer(_resultat(True) if present else _absence(), t) for t, present in sequence]
    finalises = [r for r in resultats if r is not None]
    assert len(finalises) == 1, "une seule image ratée ne doit pas scinder un passage réel en deux"


def test_vote_majoritaire():
    suivi = SuiviPassage(duree_min_presence=1.5, duree_grace_absence=1.0)
    for t, charge in [(0.0, False), (0.7, False), (1.4, True), (2.1, False)]:
        suivi.observer(_resultat(charge), t)
    resultat_final = suivi.observer(_absence(), 3.5)
    assert resultat_final is not None
    assert resultat_final["statut"] == "Vide", "3 lectures Vide contre 1 Chargé -> Vide majoritaire"


def main():
    tests = [
        test_passage_normal_est_enregistre_une_fois,
        test_detection_isolee_nest_pas_enregistree,
        test_image_ratee_au_milieu_ne_coupe_pas_le_passage,
        test_vote_majoritaire,
    ]
    echecs = 0
    for test in tests:
        try:
            test()
            print(f"OK   {test.__name__}")
        except AssertionError as exc:
            echecs += 1
            print(f"FAUX {test.__name__} : {exc}")
    print(f"\n{len(tests) - echecs}/{len(tests)} tests réussis")
    if echecs:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
