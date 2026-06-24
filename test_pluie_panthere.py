# -*- coding: utf-8 -*-
"""Test extraction pluies spatialisées Panthère (radar temps-différé).

Produit BDImage confirmé : panthere/france, pdt=60mn.
(sondage réalisé le 24/06/2026 — seul sous-type valide sur BDImage SCHAPI)

Usage : python test_pluie_panthere.py
"""

import os
import sys
from datetime import datetime

sys.path.insert(0, r"D:\charles-eddy.piot\Documents\Perso CEP\Git-Claude IA\Outil prépa crues Plathynes")
from modules.bdimage_client import BdimageClient

# ── Paramètres à adapter ──────────────────────────────────────────────────────
DATE_DEBUT = datetime(2022, 11, 5, 0, 0)
DATE_FIN   = datetime(2022, 11, 5, 6, 0)

# Bounding box Cassaignes Lambert 93
UL = "594815,6236216"
LR = "645123,6189500"

OUT_DIR = r"D:\charles-eddy.piot\Documents\Perso CEP\Git-Claude IA\Outil prépa crues Plathynes\sorties\test_panthere_france_60mn"

# ── Test ─────────────────────────────────────────────────────────────────────
def log(msg): print(msg, flush=True)

bdi = BdimageClient()

print("=" * 60)
print("TEST Panthère — panthere/france pdt=60mn")
print("=" * 60)
try:
    fichiers = bdi.extraire_pluies_panthere(
        date_debut=DATE_DEBUT, date_fin=DATE_FIN,
        ul=UL, lr=LR,
        output_dir=OUT_DIR,
        log_fn=log,
    )
    print(f"\n✓ {len(fichiers)} fichier(s) .grd écrits dans {OUT_DIR}")
    for f in fichiers[:5]:
        print(f"  {os.path.basename(f)}")
    if len(fichiers) > 5:
        print(f"  ... ({len(fichiers) - 5} autres)")
except Exception as e:
    print(f"\n✗ ERREUR : {e}")
