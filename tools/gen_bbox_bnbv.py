# -*- coding: utf-8 -*-
"""Génère config/bbox_bnbv.json depuis le shapefile BNBV_Bassins_SPCMO.shp.

Lecture native .shp + .dbf sans dépendance externe.
Coordonnées en Lambert 93 (EPSG:2154), mêmes que BDImage.
Chaque bbox est étendue d'une marge de 5 km pour inclure les pixels de bordure.

Résultat JSON :
  { "MO12345": {"ul": "X,Y", "lr": "X,Y"}, ... }
  UL = coin haut-gauche (min_x, max_y)
  LR = coin bas-droite  (max_x, min_y)
"""

import json
import os
import struct

SHP = os.path.join(os.path.dirname(__file__), "..", "BNBV_SPCMO", "BNBV_Bassins_SPCMO.shp")
DBF = os.path.join(os.path.dirname(__file__), "..", "BNBV_SPCMO", "BNBV_Bassins_SPCMO.dbf")
OUT = os.path.join(os.path.dirname(__file__), "..", "config", "bbox_bnbv.json")

MARGE_M = 5000  # 5 km de marge autour de chaque BV


# ---------------------------------------------------------------------------
# Lecture .dbf — récupère les valeurs du champ IDENTIF dans l'ordre
# ---------------------------------------------------------------------------

def _lire_identif_dbf(dbf_path):
    with open(dbf_path, "rb") as f:
        header = f.read(32)
        num_records = struct.unpack("<I", header[4:8])[0]
        header_size = struct.unpack("<H", header[8:10])[0]
        record_size = struct.unpack("<H", header[10:12])[0]

        # Champs
        fields = []
        while True:
            rec = f.read(32)
            if rec[0] == 0x0D:
                break
            name = rec[:11].replace(b"\x00", b"").decode("latin-1")
            length = rec[16]
            fields.append((name, length))

        # Index et longueur du champ IDENTIF
        identif_offset = 1  # le premier octet de chaque record est le flag de suppression
        identif_len = None
        for name, length in fields:
            if name == "IDENTIF":
                identif_len = length
                break
            identif_offset += length

        if identif_len is None:
            raise ValueError("Champ IDENTIF introuvable dans le DBF.")

        f.seek(header_size)
        codes = []
        for _ in range(num_records):
            rec = f.read(record_size)
            val = rec[identif_offset: identif_offset + identif_len].decode("latin-1").strip()
            codes.append(val)

    return codes


# ---------------------------------------------------------------------------
# Lecture .shp — récupère la bbox de chaque entité (offset 4 dans chaque record)
# Le format shapefile stocke [Xmin, Ymin, Xmax, Ymax] en little-endian double
# pour les types polygone (type 5).
# ---------------------------------------------------------------------------

def _lire_bboxes_shp(shp_path):
    bboxes = []
    with open(shp_path, "rb") as f:
        f.seek(100)  # sauter le header global (100 octets)
        while True:
            rec_header = f.read(8)
            if len(rec_header) < 8:
                break
            content_length = struct.unpack(">I", rec_header[4:8])[0] * 2  # en octets

            content = f.read(content_length)
            if len(content) < 4:
                break

            shape_type = struct.unpack("<I", content[:4])[0]
            if shape_type == 0:
                # Null shape
                bboxes.append(None)
            else:
                # Bytes 4-36 : Xmin, Ymin, Xmax, Ymax (4 doubles LE)
                xmin, ymin, xmax, ymax = struct.unpack("<4d", content[4:36])
                bboxes.append((xmin, ymin, xmax, ymax))

    return bboxes


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("Lecture DBF...")
    codes = _lire_identif_dbf(DBF)
    print(f"  {len(codes)} enregistrements lus.")

    print("Lecture SHP...")
    bboxes = _lire_bboxes_shp(SHP)
    print(f"  {len(bboxes)} bboxes lues.")

    if len(codes) != len(bboxes):
        raise ValueError(f"Désaccord DBF ({len(codes)}) / SHP ({len(bboxes)})")

    result = {}
    skipped = 0
    for code, bbox in zip(codes, bboxes):
        if not code or bbox is None:
            skipped += 1
            continue
        xmin, ymin, xmax, ymax = bbox
        # Appliquer la marge
        xmin -= MARGE_M
        ymin -= MARGE_M
        xmax += MARGE_M
        ymax += MARGE_M
        # UL = haut-gauche, LR = bas-droite
        result[code] = {
            "ul": f"{xmin:.0f},{ymax:.0f}",
            "lr": f"{xmax:.0f},{ymin:.0f}",
        }

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, sort_keys=True)

    print(f"\n{len(result)} BV exportes ({skipped} ignores).")
    print(f"Fichier genere : {os.path.abspath(OUT)}")

    # Apercu des 5 premiers
    print("\nApercu :")
    for k, v in list(result.items())[:5]:
        print(f"  {k:15s}  UL={v['ul']}  LR={v['lr']}")


if __name__ == "__main__":
    main()
