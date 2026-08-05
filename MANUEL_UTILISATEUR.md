# Manuel utilisateur — Détection de remplissage des camions (Marsa Maroc)

## 1. Démarrage

1. Ouvrir un terminal dans le dossier du projet.
2. Lancer le serveur :
   ```
   .venv\Scripts\python.exe app.py
   ```
3. Ouvrir un navigateur sur **http://127.0.0.1:5000**

L'application se connecte automatiquement à la caméra du portail actif (par défaut **Terminal Polyvalent**).

## 2. Connexion

L'accès à l'application nécessite une authentification.

- Identifiant par défaut : `admin`
- Mot de passe par défaut : `admin123`

⚠️ À changer après le premier déploiement (pas d'interface de changement de mot de passe dans cette version — le modifier directement en base ou redemander au support technique).

## 3. Page d'accueil

- **Flux en direct** : image de la caméra du portail, rafraîchie en continu. Le statut détecté (Chargé / Vide) et le % de pixels bleus sont incrustés directement sur l'image, avec la zone du camion (cadre bleu) et la zone d'analyse de la benne (cadre vert).
- **Bouton "Enregistrer la détection actuelle dans l'historique"** : sauvegarde l'état affiché à l'instant (image + statut + horodatage) dans la base de données.

## 4. Historique

Accessible via le menu **Historique**.

- Liste de toutes les détections enregistrées : date/heure, statut, % de bleu, confiance, image.
- **Filtres** : par date et/ou par statut (Chargé / Vide / Aucun camion).
- **Correction manuelle** : si un agent constate qu'un statut a été mal détecté, il peut le corriger directement depuis la liste déroulante en face de la ligne concernée et cliquer sur "Corriger". La valeur détectée automatiquement reste visible (mention "corrigé (détecté : ...)") pour garder une trace.
- **Export CSV** : bouton "Exporter CSV" en haut de la page, respecte les filtres actifs (date/statut).

## 5. Portails

Accessible via le menu **Portails**.

- Liste des portails enregistrés (nom, source caméra, statut actif/inactif).
- **Ajouter un portail** : renseigner un nom et une source caméra (index webcam local comme `0`, `1`… ou URL RTSP pour une caméra IP).
- **Activer un portail** : bascule le flux caméra de l'application sur ce portail (prend effet en quelques secondes). Un seul portail peut être actif à la fois, car l'application ne pilote qu'un seul flux vidéo à l'instant T.

## 6. Paramètres

Accessible via le menu **Paramètres**.

- **Seuil de décision** : pourcentage de pixels bleus au-delà duquel un camion est considéré "Chargé" (par défaut 30%). À augmenter si le système déclare "Chargé" trop souvent à tort ; à diminuer s'il déclare "Vide" trop souvent à tort.
- **Fraction haute exclue (cabine)** et **marge latérale** : ajustent la zone de l'image analysée (la "benne") par rapport à la cabine et aux bords du camion. À recalibrer si la caméra du portail est positionnée différemment du cas de test (angle, distance).

Les changements sont appliqués immédiatement au flux en direct, sans redémarrage.

## 7. Cas particuliers

- **Aucun camion détecté** : s'affiche quand aucun véhicule n'est dans le champ de la caméra, ou si le modèle ne le reconnaît pas (mauvais angle, trop loin).
- **Camion sans bâche bleue** (ex. porte-conteneur) : sera classé "Vide" par la règle de décision actuelle, qui se base uniquement sur la présence de bleu — voir le manuel technique pour cette limite connue.
