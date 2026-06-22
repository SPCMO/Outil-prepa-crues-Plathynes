# -*- coding: utf-8 -*-
"""Chargement et validation du CSV épisodes."""

import csv
from datetime import datetime

DATE_FORMATS = [
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
]


def _parse_date(s):
    s = s.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    raise ValueError(f"Format de date non reconnu : '{s}'")


def load_episodes(filepath):
    """Charge le CSV épisodes et retourne une liste de dicts.

    Retourne:
        list of dict avec clés 'date_debut', 'date_fin' (datetime),
        'label' (str pour affichage), 'index' (int).

    Lève:
        ValueError si le fichier est invalide.
    """
    episodes = []
    with open(filepath, newline="", encoding="utf-8-sig") as fh:
        # détecter le séparateur
        sample = fh.read(1024)
        fh.seek(0)
        sep = ";" if sample.count(";") >= sample.count(",") else ","
        reader = csv.DictReader(fh, delimiter=sep)

        # normaliser les noms de colonnes (minuscules, sans espaces)
        if reader.fieldnames is None:
            raise ValueError("Fichier CSV vide ou sans en-tête.")
        fields = {f.strip().lower(): f for f in reader.fieldnames}

        col_deb = _find_col(fields, ["date_debut", "datedebut", "debut", "start"])
        col_fin = _find_col(fields, ["date_fin", "datefin", "fin", "end"])

        for i, row in enumerate(reader, start=1):
            raw_deb = row[fields[col_deb]].strip()
            raw_fin = row[fields[col_fin]].strip()
            if not raw_deb or not raw_fin:
                continue
            try:
                dt_deb = _parse_date(raw_deb)
                dt_fin = _parse_date(raw_fin)
            except ValueError as e:
                raise ValueError(f"Ligne {i+1} : {e}")
            if dt_fin <= dt_deb:
                raise ValueError(f"Ligne {i+1} : date_fin doit être postérieure à date_debut.")
            episodes.append({
                "index": i,
                "date_debut": dt_deb,
                "date_fin": dt_fin,
                "label": f"{dt_deb.strftime('%d/%m/%Y %H:%M')} - {dt_fin.strftime('%d/%m/%Y %H:%M')}",
            })

    if not episodes:
        raise ValueError("Aucun épisode trouvé dans le fichier.")
    return episodes


def _find_col(fields, candidates):
    for c in candidates:
        if c in fields:
            return c
    raise ValueError(
        f"Colonne introuvable. Colonnes attendues : {candidates}. "
        f"Colonnes trouvées : {list(fields.keys())}"
    )
