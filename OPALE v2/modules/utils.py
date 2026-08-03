# -*- coding: utf-8 -*-
"""Utilitaires communs."""
from datetime import datetime
import csv

_FMT_DT = "%d/%m/%Y %H:%M"


def read_csv_serie(path, has_header=True):
    """Lit un CSV ';'-séparé (col0=date, col1=valeur) → (list[datetime], list[float]).

    Retourne deux listes vides si le fichier est absent ou illisible.
    """
    pairs = []
    try:
        with open(path, encoding="utf-8") as fh:
            reader = csv.reader(fh, delimiter=";")
            if has_header:
                next(reader, None)
            for row in reader:
                if len(row) >= 2:
                    try:
                        pairs.append((
                            datetime.strptime(row[0].strip(), _FMT_DT),
                            float(row[1].strip())
                        ))
                    except (ValueError, IndexError):
                        pass
    except Exception:
        pass
    pairs.sort(key=lambda x: x[0])
    return [p[0] for p in pairs], [p[1] for p in pairs]
