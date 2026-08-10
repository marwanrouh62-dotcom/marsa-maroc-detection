"""
Suivi d'un passage de camion à travers plusieurs détections successives,
pour déclencher l'enregistrement automatique d'un seul résultat final par
camion (au lieu d'un enregistrement manuel par clic, ou d'un enregistrement
à chaque inférence qui dupliquerait la même détection plusieurs fois).
"""


class SuiviPassage:
    """
    `observer()` est appelé à chaque nouvelle inférence du pipeline.

    - Tant qu'un camion est détecté en continu, les lectures (Chargé/Vide,
      % bleu, confiance) sont accumulées.
    - `duree_min_presence` : un camion doit être détecté depuis au moins
      cette durée avant qu'un passage ne soit considéré valide (filtre le
      bruit d'une détection isolée sur une seule image).
    - `duree_grace_absence` : après la disparition du camion, on attend
      cette durée avant de considérer qu'il est vraiment reparti (tolère
      une image ratée au milieu d'un passage réel, sans le couper en deux).
    - Quand le camion est confirmé reparti, `observer()` renvoie le
      résultat agrégé du passage (statut majoritaire, moyennes) à
      enregistrer — une seule fois par passage.
    """

    def __init__(self, duree_min_presence=1.5, duree_grace_absence=1.0):
        self.duree_min_presence = duree_min_presence
        self.duree_grace_absence = duree_grace_absence
        self._en_cours = False
        self._debut = 0.0
        self._derniere_detection = 0.0
        self._compte_charge = 0
        self._compte_vide = 0
        self._somme_ratio = 0.0
        self._somme_confiance = 0.0
        self._n = 0

    def observer(self, result, maintenant):
        """Renvoie un dict {statut, ratio_bleu, confiance} si un passage
        vient de se terminer et doit être enregistré, sinon None."""
        if result.get("camion_detecte"):
            self._derniere_detection = maintenant
            if not self._en_cours:
                self._en_cours = True
                self._debut = maintenant
                self._compte_charge = 0
                self._compte_vide = 0
                self._somme_ratio = 0.0
                self._somme_confiance = 0.0
                self._n = 0
            if result["statut"] == "Chargé":
                self._compte_charge += 1
            else:
                self._compte_vide += 1
            self._somme_ratio += result["ratio_bleu"]
            self._somme_confiance += result.get("confiance") or 0.0
            self._n += 1
            return None

        if self._en_cours and (maintenant - self._derniere_detection) >= self.duree_grace_absence:
            duree_presence = self._derniere_detection - self._debut
            self._en_cours = False
            if duree_presence >= self.duree_min_presence and self._n > 0:
                return {
                    "statut": "Chargé" if self._compte_charge >= self._compte_vide else "Vide",
                    "ratio_bleu": self._somme_ratio / self._n,
                    "confiance": self._somme_confiance / self._n,
                }
        return None

    @property
    def en_cours(self):
        return self._en_cours
