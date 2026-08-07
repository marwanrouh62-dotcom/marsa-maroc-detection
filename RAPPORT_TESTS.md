# Rapport de tests — Détection de remplissage des camions (Marsa Maroc)

## 1. Détection camion (YOLOv8n pré-entraîné)

| Test | Source | Résultat |
|---|---|---|
| Détection sur image d'exemple | `bus.jpg` (Ultralytics) | Détecté, confiance 0.87, bbox correcte |
| Détection sur photo réelle 1 | camion bâché bleu (vue arrière) | Détecté (`truck`), confiance 0.93 |
| Détection sur photo réelle 2 | camion bâché bleu (vue 3/4) | Détecté (`truck`), confiance 0.66 |
| Détection sur photo réelle 3 | camion porte-conteneur (sans bâche) | Détecté (`truck`), confiance 0.84 |
| Absence de camion (webcam sans véhicule) | flux webcam local | Correctement "aucun camion détecté", pas de crash |

**Conclusion** : le modèle pré-entraîné COCO détecte correctement les camions réels sans fine-tuning, avec une confiance ≥ 0.66 dans tous les cas testés.

## 2. Analyse HSV de la bâche bleue

### 2.1 Tests unitaires (ROI synthétiques)

| ROI | % bleu attendu | % bleu mesuré | Statut |
|---|---|---|---|
| Bleu pur (BGR 200,120,40) | 100% | 100% | Chargé ✅ |
| Gris uniforme (120,120,120) | 0% | 0% | Vide ✅ |
| Mixte 40% bleu / 60% gris | 40% | 40% | Chargé ✅ (seuil 30%) |

### 2.2 Tests sur photos réelles

| Photo | % bleu mesuré | Statut attendu | Statut obtenu |
|---|---|---|---|
| Camion bâché 1 | 45.9% | Chargé | Chargé ✅ |
| Camion bâché 2 | 54.3% | Chargé | Chargé ✅ |
| Camion porte-conteneur (sans bâche) | 21.6% | Vide | Vide ✅ |

Le résidu de bleu (21.6%) sur la photo sans bâche provient du bras de grue et du châssis de l'engin de manutention embarqué (couleur bleue de l'équipement, pas une bâche) — il reste correctement sous le seuil de décision (30%).

## 3. Tests de robustesse (conditions variables)

Script : `test_conditions.py`. 3 photos réelles × 8 variantes (luminosité, contraste, flou, angle caméra ±12°) = 24 combinaisons.

### 3.1 Premier passage — bug détecté

Un assombrissement additif (`beta=-70`, réduction linéaire de chaque canal BGR) faisait chuter le taux de bleu détecté de 44-54% à 0.9-9%, provoquant un **faux négatif** (camion chargé classé "Vide").

**Diagnostic** : sur les pixels réellement bleus de la bâche, 84.5% sortaient de la plage de teinte (Hue) attendue après cet assombrissement — non pas à cause de la luminosité (V) mais parce qu'une soustraction constante déforme la teinte quand un canal clippe à 0. Ce test n'était pas physiquement réaliste : une caméra réelle en faible lumière atténue *multiplicativement* (moins de photons, teinte préservée), pas de façon additive.

**Correctif appliqué** : seuil V minimum de la plage HSV bleue abaissé de 40 à 15 dans `tarp_analysis.py` (la saturation ≥60 reste le vrai discriminant contre le gris/asphalte — vérifié, pas de faux positif introduit).

### 3.2 Second passage — après correctif, avec simulation réaliste

| Photo | Condition | % bleu | Statut |
|---|---|---|---|
| Camion bâché 1 | original | 45.9% | Chargé ✅ |
| Camion bâché 1 | faible luminosité (×0.35) | 43.7% | Chargé ✅ |
| Camion bâché 1 | forte luminosité (×1.6) | 46.3% | Chargé ✅ |
| Camion bâché 1 | faible/fort contraste | 43.1% / 47.2% | Chargé ✅ |
| Camion bâché 1 | flou | 46.1% | Chargé ✅ |
| Camion bâché 1 | angle ±12° | 44.5% / 41.5% | Chargé ✅ |
| Camion bâché 2 | (mêmes variantes) | 49.6% – 55.0% | Chargé ✅ (8/8) |
| Porte-conteneur sans bâche | (mêmes variantes) | 6.4% – 24.4% | Vide ✅ (8/8) |

**Résultat final : 24/24 combinaisons correctement classées.** Marge confortable de chaque côté du seuil de 30% (jamais plus proche que 6 points de marge).

## 4. Tests fonctionnels backend / interface

| Fonctionnalité | Méthode de test | Résultat |
|---|---|---|
| Flux vidéo temps réel (MJPEG) | requête HTTP sur `/video_feed` | 200, flux continu |
| Enregistrement historique | capture + vérification SQLite | statut, ratio, horodatage, image bien enregistrés |
| Filtrage historique (date/statut) | requêtes avec paramètres GET | résultats correctement filtrés |
| Réglage du seuil en direct | POST `/parametres`, relecture DB | persisté, appliqué sans redémarrage |
| Correction manuelle | POST `/historique/corriger/<id>` | statut mis à jour, `statut_original` conservé pour traçabilité |
| Export CSV | GET `/historique/export.csv` | fichier CSV valide, BOM UTF-8 (compatible Excel FR) |
| Authentification | accès sans session → redirection `/login` ; mauvais mot de passe rejeté ; bon mot de passe → accès accordé | conforme |
| Multi-portails | ajout d'un portail, activation, bascule caméra | activation exclusive confirmée (un seul `actif=1`), pas de crash même avec une source caméra inexistante |
| Analyse par upload (`/analyser`) | POST multipart avec photo réelle | pipeline exécuté, statut correct, image enregistrée et affichée |

## 5. Audit de sécurité et corrections (2026-08-06)

Un audit complet du code (routes, authentification, gestion des fichiers) a été mené sur l'ensemble du projet. Constats et vérifications après correctif :

| Problème trouvé | Test de vérification | Résultat après correctif |
|---|---|---|
| Photos servies sans authentification via `/static/captures/` | GET `/captures/<fichier>` sans session ; GET `/static/captures/<fichier>` | `/captures/...` → 302 (redirigé vers login) sans session, 200 avec session ; `/static/captures/...` → 404 (le dossier n'existe plus à cet emplacement) |
| Thread caméra sans gestion d'erreur (crash silencieux possible) | Revue de code | `try/except` ajouté autour de la boucle ; erreur loguée, thread continue |
| Paramètres non validés côté serveur | POST `/parametres` avec `seuil_bleu=5.0` (hors bornes) et `seuil_bleu=abc` (non numérique) | Les deux rejetés avec message d'erreur explicite, valeur non persistée |
| Pas de limite de taille d'upload | Revue de code | `MAX_CONTENT_LENGTH` = 10 Mo ajouté |
| Open redirect sur `/historique/corriger` | Revue de code | Redirection fixe vers `/historique` |
| Absence de protection CSRF | POST `/login` sans cookie ni token ; POST `/login` avec cookie mais sans token ; POST `/login` avec cookie + bon token | Les deux premiers → 403 ; le troisième → 302 (succès) |
| Premier correctif CSRF incomplet (`None != None` contournable) | Même test que ci-dessus, avant le second correctif | Le premier cas (aucun cookie) renvoyait 200 (faille) au lieu de 403 — corrigé en exigeant un token de session non vide |
| `db.set_mot_de_passe()` inaccessible depuis l'interface | POST `/compte` avec mauvais mot de passe actuel | Rejeté avec message d'erreur, mot de passe réel inchangé (vérifié en base) |

## 7. Recalibrage de la ROI et du seuil (2026-08-07)

Deux signalements sur des photos réelles supplémentaires ont conduit à revoir l'heuristique de ROI.

### 7.1 Faux négatif : bâche non couverte par la ROI

Sur une photo réelle de camion benne bâché (bâche bombée au-dessus de la caisse, parois métalliques et roues en dessous), l'ancienne ROI (partie **basse** de la bbox, `top_ratio=0.35` excluant le haut supposé "cabine") ne couvrait presque pas la bâche :

| Avant correctif | Après correctif |
|---|---|
| ROI basse de la bbox, 14.2% bleu → **Vide** ❌ (faux négatif, camion réellement chargé) | ROI haute de la bbox, 47.2% bleu → **Chargé** ✅ |

**Cause** : sur ce type de camion (benne + bâche bombée), la bâche occupe le **haut** de la caisse, pas le bas — l'inverse de l'hypothèse initiale (qui supposait la cabine en haut, la benne en bas). Corrigé dans `tarp_analysis.extract_benne_roi()` : la ROI cible désormais le haut de la bbox (`top_margin=0.05` exclut une fine bande tout en haut, `top_ratio=0.45` définit la hauteur analysée à partir de là), au lieu du bas.

### 7.2 Faux positif potentiel : cabine peinte en bleu

Question soulevée : un camion à cabine bleue mais **sans bâche** (semi-remorque bâchée sombre, pas de bleu) risque-t-il d'être classé "Chargé" à cause de la couleur de la cabine ?

Testé sur une photo réelle (tracteur à cabine bleu métallisé + remorque rideaux coulissants sombre, aucune bâche bleue) : **confirmé, faux positif réel** — 34.6% de bleu avec l'ancienne ROI (basse), au-dessus du seuil de 30% → classé "Chargé" à tort.

**Tentative de correction par marge latérale** : augmenter `side_margin` pour exclure davantage les bords (où se trouve la cabine) a été testée — **effet inverse à celui attendu** : le % de bleu augmente avec la marge (28.1% à 0.05, jusqu'à 45.9% à 0.25), car rogner les bords concentre la ROI restante sur la cabine plutôt que de l'exclure. `side_margin` reste donc à sa valeur par défaut (0.05).

**Correction retenue : relever le seuil de décision.** Avec la nouvelle ROI haute, sur les 5 photos réelles disponibles :

| Photo | % bleu (ROI haute, side_margin=0.05) | Statut réel |
|---|---|---|
| Cabine bleue, sans bâche | 28.1% | Vide (attendu) |
| Camion benne bâché (haut) | 47.2% | Chargé (attendu) |
| Camion bâché 1 | 91.0% | Chargé (attendu) |
| Camion bâché 2 | 75.2% | Chargé (attendu) |
| Porte-conteneur sans bâche | 24.1% | Vide (attendu) |

Écart net entre le cas "Vide" le plus haut (28.1%, cabine bleue) et le cas "Chargé" le plus bas (47.2%) → seuil par défaut relevé de **0.30 à 0.35**, au milieu de cet écart avec marge des deux côtés. Valeur mise à jour dans `tarp_analysis.py`, `pipeline.py`, `db.py` (paramètre par défaut) et sur la base de données de l'instance en cours.

### 7.3 Re-validation de la robustesse (test_conditions.py, 5 photos × 8 conditions = 40 combinaisons)

**39/40 correctement classées.** Seule exception : *camion benne bâché, angle -12°* → 34.8% (juste sous le nouveau seuil de 35%) → classé "Vide" à tort.

**Diagnostic** : à forte rotation, la bounding box (toujours axis-aligned) s'agrandit pour englober le camion incliné, ce qui déplace la position relative de la bâche à l'intérieur de la bbox — la tranche "haut" fixe (`top_ratio`) capture alors proportionnellement plus de cabine/arrière-plan et moins de bâche. C'est une limite géométrique de l'heuristique (ROI rectangulaire non adaptative à la rotation), pas un problème de couleur/seuil. Non corrigé volontairement : baisser le seuil pour rattraper ce cas isolé réduirait la marge de sécurité contre le faux positif de cabine bleue (§7.2), qui est un risque plus réaliste en usage normal (caméra de portail fixe, angle stable) qu'une rotation de ±12°.

## 8. Limites connues (non-bugs, limites d'approche)

- La règle de décision ne détecte que la couleur bleue — un camion chargé sans bâche bleue (ex. conteneur) est classé "Vide". Comportement volontaire du cahier des charges (approche sans dataset).
- La ROI "bâche" est une heuristique géométrique (haut de la bounding box, rectangle axis-aligned), non calibrée sur le portail réel — à ajuster via les paramètres une fois la caméra installée sur site. Elle perd en précision sur les rotations extrêmes (voir §7.3) et ne distingue pas la cabine de la caisse par position (seule la couleur mesurée en résulte, compensée par le seuil — voir §7.2).
- Une cabine peinte en bleu reste un facteur de risque de faux positif si elle occupe une grande partie du haut de la bbox (camions courts, cabine large) — atténué mais pas éliminé par le seuil à 0.35.
- Tests de robustesse basés sur 5 photos réelles + variantes simulées, pas sur un flux vidéo réel du portail Marsa Maroc (caméra non encore installée à ce stade du projet).
