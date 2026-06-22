# Outil préparation crues Plathynes — Stand-alone

Interface graphique Python/tkinter pour la préparation et l'analyse d'épisodes de crue, développée au **SPCMO (Service de Prévision des Crues Méditerranée Ouest)**.

## Fonctionnalités

- **Configuration** : saisie des codes station hydrométrie / BNBV, seuils de vigilance (Q ou H), connexion PHyC
- **Épisodes** : chargement d'un catalogue (OCTAVE…) ou saisie manuelle, filtres et tri par vigilance max
- **Extraction** : téléchargement automatique des pluies spatialisées (AntilopeJ1), HU SIM et débits/hauteurs PHyC
- **Visualisation** : hyétogramme + HU + courbe de débit avec zones de vigilance et seuils étiquetés
- **Analyse** : bubble chart comparatif (HU début × Q max × cumul pluie × intensité)
- **Paramétrage** : adaptation des préfixes de codes identifiants pour un autre territoire SPC

## Prérequis

- Python 3.9 à 3.13
- Packages : `requests`, `lxml`, `zeep`, `matplotlib` (voir `Test_pr_install.bat`)
- Accès réseau **RIE** (services PHyC et BDImage SCHAPI)

## Installation

```bash
# 1. Cloner le dépôt
git clone https://github.com/<votre-compte>/stand-alone-prepa-crues-plathynes.git
cd stand-alone-prepa-crues-plathynes

# 2. Vérifier / installer les dépendances
Test_pr_install.bat

# 3. Créer votre configuration
copy config\config.exemple.json config\config.json
# Puis renseigner vos identifiants PHyC et votre code station dans config\config.json
# (ou directement via l'interface graphique)

# 4. Lancer l'outil
Lancer_outil.bat
```

## Configuration

Le fichier `config/config.json` est **exclu du dépôt** (`.gitignore`) car il contient vos identifiants PHyC.  
Utilisez `config/config.exemple.json` comme point de départ.

## Bounding box (autre territoire)

Le fichier `config/bbox_bnbv.json` contient les bounding boxes précalculées pour les bassins versants du **SPCMO** (Lambert 93, marge 5 km).  
Pour un autre territoire, voir `tools/gen_bbox_bnbv.py` et l'onglet **"Bounding box pour un autre territoire"** de l'aide intégrée.

## Documentation

Ouvrir `aide.html` dans un navigateur ou utiliser le bouton **ℹ Aide** de l'application.

## Contact

PIOT Charles-Eddy — SPCMO  
[charles-eddy.piot@developpement-durable.gouv.fr](mailto:charles-eddy.piot@developpement-durable.gouv.fr?subject=Info%20%2F%20bug%20outil%20prépa%20crues%20Plathynes)
