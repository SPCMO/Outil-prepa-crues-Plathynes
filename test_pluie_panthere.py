# -*- coding: utf-8 -*-
"""Test rapide extraction pluies spatialisées Panthère (radar temps-différé).

Usage : python test_pluie_panthere.py
Produits testés :
  panthere/france-td-5mn  (pdt=5mn)
  panthere/france-td-60mn (pdt=60mn)

Modifier CODE_BNBV, DATE_DEBUT/FIN et les bounding boxes UL/LR selon l'épisode souhaité.
"""

import os
import sys
from datetime import datetime

sys.path.insert(0, r"D:\charles-eddy.piot\Documents\Perso CEP\Git-Claude IA\Outil prépa crues Plathynes")
from modules.bdimage_client import BdimageClient

# ── Paramètres à adapter ──────────────────────────────────────────────────────
# Épisode Cassaignes — à ajuster selon l'épisode souhaité
DATE_DEBUT = datetime(2022, 11, 5, 0, 0)
DATE_FIN   = datetime(2022, 11, 5, 6, 0)   # 6 h pour limiter le volume du test

# Bounding box Cassaignes en Lambert 93 (UL=haut-gauche, LR=bas-droite)
UL = "594815,6236216"
LR = "645123,6189500"

# Dossier de sortie des .grd
OUT_DIR_5MN  = r"D:\charles-eddy.piot\Documents\Perso CEP\Git-Claude IA\Outil prépa crues Plathynes\sorties\test_panthere_5mn"
OUT_DIR_60MN = r"D:\charles-eddy.piot\Documents\Perso CEP\Git-Claude IA\Outil prépa crues Plathynes\sorties\test_panthere_60mn"

# ── Test ─────────────────────────────────────────────────────────────────────
def log(msg): print(msg, flush=True)

bdi = BdimageClient()

print("=" * 60)
print("TEST Panthère 5mn")
print("=" * 60)
try:
    fichiers = bdi.extraire_pluies_panthere(
        date_debut=DATE_DEBUT, date_fin=DATE_FIN,
        ul=UL, lr=LR,
        pdt_minutes=5,
        output_dir=OUT_DIR_5MN,
        log_fn=log,
    )
    print(f"\n✓ {len(fichiers)} fichier(s) .grd écrits dans {OUT_DIR_5MN}")
    for f in fichiers[:5]:
        print(f"  {os.path.basename(f)}")
    if len(fichiers) > 5:
        print(f"  ... ({len(fichiers) - 5} autres)")
except Exception as e:
    print(f"\n✗ ERREUR 5mn : {e}")

print()
print("=" * 60)
print("TEST Panthère 60mn")
print("=" * 60)
try:
    fichiers = bdi.extraire_pluies_panthere(
        date_debut=DATE_DEBUT, date_fin=DATE_FIN,
        ul=UL, lr=LR,
        pdt_minutes=60,
        output_dir=OUT_DIR_60MN,
        log_fn=log,
    )
    print(f"\n✓ {len(fichiers)} fichier(s) .grd écrits dans {OUT_DIR_60MN}")
    for f in fichiers[:5]:
        print(f"  {os.path.basename(f)}")
except Exception as e:
    print(f"\n✗ ERREUR 60mn : {e}")
