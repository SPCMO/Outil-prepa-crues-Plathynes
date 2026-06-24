# -*- coding: utf-8 -*-
"""Test extraction pluies spatialisées Panthère (radar temps-différé).

Sonde les sous-types BDImage possibles pour Panthère car la nomenclature
diffère de celle d'Antilope. Lance le script pour identifier lesquels fonctionnent.

Usage : python test_pluie_panthere.py
"""

import os
import sys
from datetime import datetime

sys.path.insert(0, r"D:\charles-eddy.piot\Documents\Perso CEP\Git-Claude IA\Outil prépa crues Plathynes")
from modules.bdimage_client import BdimageClient

# ── Paramètres ────────────────────────────────────────────────────────────────
DATE_DEBUT = datetime(2022, 11, 5, 0, 0)
DATE_FIN   = datetime(2022, 11, 5, 1, 0)   # 1 h seulement pour la découverte

# Bounding box Cassaignes Lambert 93
UL = "594815,6236216"
LR = "645123,6189500"

OUT_BASE = r"D:\charles-eddy.piot\Documents\Perso CEP\Git-Claude IA\Outil prépa crues Plathynes\sorties"

# Candidats à tester : (sous_type, pdt_minutes)
CANDIDATS = [
    ("td",              5),
    ("td",             60),
    ("j1",             60),
    ("j0",              5),
    ("j0",             60),
    ("france",         60),
    ("france-td",      60),
    ("td-5mn",          5),
    ("td-60mn",        60),
]

# ── Sonde ─────────────────────────────────────────────────────────────────────
def log(msg): print(msg, flush=True)

bdi = BdimageClient()

print("Sonde des sous-types Panthère disponibles sur BDImage")
print("=" * 60)
ok_list = []

for sous_type, pdt in CANDIDATS:
    label = f"panthere/{sous_type} pdt={pdt}mn"
    print(f"\n── Test : {label}")
    out_dir = os.path.join(OUT_BASE, f"test_panthere_{sous_type}_{pdt}mn")
    try:
        fichiers = bdi._extraire_bbox(
            type_img="panthere", sous_type=sous_type,
            date_debut=DATE_DEBUT, date_fin=DATE_FIN,
            ul=UL, lr=LR,
            pdt=pdt, duree=pdt,
            bandes="rr",
            facteur=0.1, force_integer=True,
            output_dir=out_dir,
            log_fn=log,
        )
        print(f"  ✓ OK — {len(fichiers)} fichier(s) .grd")
        ok_list.append(label)
    except Exception as e:
        # Afficher seulement la première ligne de l'erreur pour ne pas noyer la sortie
        msg = str(e).splitlines()[0]
        print(f"  ✗ {msg}")

print()
print("=" * 60)
if ok_list:
    print("Sous-types fonctionnels :")
    for s in ok_list:
        print(f"  ✓ {s}")
else:
    print("Aucun sous-type n'a fonctionné — vérifier la connectivité RIE")
    print("ou consulter la doc BDImage pour les identifiants Panthère exacts.")
