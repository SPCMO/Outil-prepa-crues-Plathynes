# -*- coding: utf-8 -*-
"""Fonctions de visualisation et calculs hydrologiques — sans dépendance tkinter."""
import os
from datetime import datetime

from .utils import read_csv_serie

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False


# ─────────────────────────────────────────────────────────────────────────────
# Vigilance
# ─────────────────────────────────────────────────────────────────────────────

def vig_label_from_val(val, seuils):
    """Retourne le label de vigilance à partir d'une valeur brute (Q ou H).

    Paramètres
    ----------
    val    : float — valeur à comparer
    seuils : dict  — clés 'rouge', 'zt_rouge', 'orange', 'zt_orange', 'jaune', 'zt_jaune'
    """
    def _s(key):
        try:
            return float(seuils[key]) if key in seuils else None
        except (ValueError, TypeError):
            return None

    for key, lbl in [("rouge",    "Rouge"),    ("zt_rouge",  "ZT Rouge"),
                     ("orange",   "Orange"),   ("zt_orange", "ZT Orange"),
                     ("jaune",    "Jaune"),    ("zt_jaune",  "ZT Jaune")]:
        v = _s(key)
        if v is not None and val >= v:
            return lbl
    return "Vert"


def vig_from_file(q_path, seuils=None):
    """Lit le Q max d'un fichier extrait et retourne le label de vigilance.

    Paramètres
    ----------
    q_path : str  — chemin vers le fichier CSV de débits
    seuils : dict — seuils de vigilance (optionnel ; si None ou vide → toujours "Vert")
    """
    if seuils is None:
        seuils = {}
    try:
        q_vals = []
        with open(q_path, encoding="utf-8") as fh:
            import csv as _csv
            for row in _csv.reader(fh, delimiter=";"):
                if row and len(row) >= 2:
                    try:
                        q_vals.append(float(row[1]))
                    except ValueError:
                        pass
        if not q_vals:
            return "Vert"
        return vig_label_from_val(max(q_vals), seuils)
    except Exception:
        return "Vert"


# ─────────────────────────────────────────────────────────────────────────────
# Construction de la liste des épisodes
# ─────────────────────────────────────────────────────────────────────────────

def build_episode_list(debits_dir, hu_dir, pluies_dir, bv_dir):
    """Scanne les dossiers de sortie et retourne la liste des épisodes détectés.

    Retourne une list[dict] triée par date décroissante.
    Chaque dict : {label, _dt, _key, q_path, hu_path, p_path, pant_path}
    """
    def _parse_key(key):
        parts = key.split("_")
        try:
            dt = datetime.strptime(f"{parts[0]}/{parts[1]}/{parts[2]}", "%d/%m/%Y")
            station = " ".join(parts[3:]) if len(parts) > 3 else ""
            return dt, f"{dt.strftime('%d/%m/%Y')} — {station}"
        except (ValueError, IndexError):
            return datetime.min, key

    eps = {}

    def _get_ep(key):
        if key not in eps:
            dt, label = _parse_key(key)
            eps[key] = {"label": label, "_dt": dt, "_key": key,
                        "q_path": None, "hu_path": None,
                        "p_path": None, "p_liq_path": None, "pant_path": None}
        return eps[key]

    # Scan Debits/
    if os.path.isdir(debits_dir):
        for fname in os.listdir(debits_dir):
            if not (fname.startswith("Q-Ep_") and fname.endswith(".txt")):
                continue
            key = fname[5:-4]
            ep  = _get_ep(key)
            ep["q_path"] = os.path.join(debits_dir, fname)
            hu_fname = fname.replace("Q-Ep_", "HU-Ep_").replace(".txt", ".csv")
            hu_path  = os.path.join(hu_dir, hu_fname)
            ep["hu_path"] = hu_path if os.path.exists(hu_path) else None

    # Scan Pluies temps moy BV/
    if os.path.isdir(bv_dir):
        for fname in os.listdir(bv_dir):
            if fname.startswith("AntJ1_BV-Ep_") and fname.endswith(".csv"):
                key = fname[len("AntJ1_BV-Ep_"):-4]
                _get_ep(key)["p_path"] = os.path.join(bv_dir, fname)
            elif fname.startswith("AntJ1-Liq_BV-Ep_") and fname.endswith(".csv"):
                key = fname[len("AntJ1-Liq_BV-Ep_"):-4]
                _get_ep(key)["p_liq_path"] = os.path.join(bv_dir, fname)
            elif fname.startswith("Pant_BV-Ep_") and fname.endswith(".csv"):
                key = fname[len("Pant_BV-Ep_"):-4]
                _get_ep(key)["pant_path"] = os.path.join(bv_dir, fname)

    # Scan Pluies/ (dossiers .grd sans débits)
    if os.path.isdir(pluies_dir):
        for dname in os.listdir(pluies_dir):
            for pfx in ("AntJ1-Ep_", "Pluie-Ep_", "Pant-Ep_"):
                if dname.startswith(pfx):
                    key = dname[len(pfx):]
                    _get_ep(key)
                    break

    # Générer AntJ1_BV, AntJ1-Liq_BV et Pant_BV à la volée si .grd présent mais CSV absent
    from .bdimage_client import calculer_pluie_bv_csv
    for key, ep in list(eps.items()):
        if ep.get("p_liq_path") is None:
            liq_csv = os.path.join(bv_dir, f"AntJ1-Liq_BV-Ep_{key}.csv")
            grd_liq = os.path.join(pluies_dir, f"AntJ1-Liq-Ep_{key}")
            if os.path.isdir(grd_liq):
                try:
                    os.makedirs(bv_dir, exist_ok=True)
                    calculer_pluie_bv_csv(grd_liq, liq_csv)
                    ep["p_liq_path"] = liq_csv
                except Exception as _e:
                    print(f"[WARN] build_episode_list : calcul Ant-Liq BV échoué "
                          f"pour {key} — {type(_e).__name__}: {_e}")
        if ep["p_path"] is None:
            p_path = os.path.join(bv_dir, f"AntJ1_BV-Ep_{key}.csv")
            for _pfx in ("AntJ1-Ep_", "Pluie-Ep_"):
                grd_dir = os.path.join(pluies_dir, f"{_pfx}{key}")
                if os.path.isdir(grd_dir):
                    try:
                        os.makedirs(bv_dir, exist_ok=True)
                        calculer_pluie_bv_csv(grd_dir, p_path)
                        ep["p_path"] = p_path
                    except Exception as _e:
                        print(f"[WARN] build_episode_list : calcul Ant BV échoué "
                              f"pour {key} ({grd_dir}) — {type(_e).__name__}: {_e}")
                    break
        if ep["pant_path"] is None:
            pant_path = os.path.join(bv_dir, f"Pant_BV-Ep_{key}.csv")
            grd_dir   = os.path.join(pluies_dir, f"Pant-Ep_{key}")
            if os.path.isdir(grd_dir):
                try:
                    os.makedirs(bv_dir, exist_ok=True)
                    calculer_pluie_bv_csv(grd_dir, pant_path)
                    ep["pant_path"] = pant_path
                except Exception as _e:
                    print(f"[WARN] build_episode_list : calcul Pant BV échoué "
                          f"pour {key} ({grd_dir}) — {type(_e).__name__}: {_e}")

    return sorted(eps.values(), key=lambda e: e["_dt"], reverse=True)


# ─────────────────────────────────────────────────────────────────────────────
# Stats Antilope vs Panthère
# ─────────────────────────────────────────────────────────────────────────────

def calc_ep_antpan_stats(p_dates, p_vals, pant_dates, pant_vals, seuil=0.0):
    """Calcule les 4 indicateurs de comparaison Antilope vs Panthère pour un épisode.

    Les deux séries sont alignées sur leurs timestamps COMMUNS (intersection).
    Conventions : écart = Pan − Ant → positif si Pan > Ant (sur-estimation Panthère).
    Le % relatif est calculé par rapport à la valeur Antilope au même pas de temps.

    Paramètres
    ----------
    p_dates / p_vals       : liste de datetime / float pour Antilope (BV moyen, mm/pdt)
    pant_dates / pant_vals : idem pour Panthère
    seuil                  : seuil hyétogramme (mm/pdt) pour l'indicateur "forte intensité"

    Retourne dict ou None si < 2 timestamps communs.
    """
    if not p_dates or not pant_dates:
        return None
    ant_d = dict(zip(p_dates, p_vals))
    pan_d = dict(zip(pant_dates, pant_vals))
    common = sorted(set(ant_d) & set(pan_d))
    if len(common) < 2:
        return None
    ant_c = [ant_d[t] for t in common]
    pan_c = [pan_d[t] for t in common]
    diffs = [p - a for p, a in zip(pan_c, ant_c)]

    ecart_moyen = sum(diffs) / len(diffs)
    pct_pan_over = sum(1 for d in diffs if d > 0) / len(diffs) * 100

    abs_diffs = [abs(d) for d in diffs]
    idx_max1h = max(range(len(abs_diffs)), key=lambda i: abs_diffs[i])
    ecart_max_1h = diffs[idx_max1h]
    ts_max_1h    = common[idx_max1h]

    idx_ant_max = max(range(len(ant_c)), key=lambda i: ant_c[i])
    ecart_at_ant_peak = diffs[idx_ant_max]
    ts_ant_peak       = common[idx_ant_max]

    best_i = 0
    best_sum = -1.0
    for i in range(len(common) - 2):
        s = ant_c[i] + ant_c[i+1] + ant_c[i+2]
        if s > best_sum:
            best_sum = s
            best_i   = i
    ecart_3h    = sum(diffs[best_i:best_i+3])
    ts_3h_start = common[best_i]
    ts_3h_end   = common[best_i + 2]

    sum_ant = sum(ant_c)
    sum_pan = sum(pan_d[t] for t in common)
    pct_ecart_cumul = ((sum_pan - sum_ant) / sum_ant * 100) if sum_ant > 0 else 0.0
    n_common = len(common)

    mean_ant = sum_ant / n_common if n_common > 0 else 1.0

    def _pct(ecart, ref):
        return (ecart / ref * 100) if ref and ref != 0 else None

    pct_em  = _pct(ecart_moyen,       mean_ant)
    pct_e1h = _pct(ecart_max_1h,      ant_c[idx_max1h])
    pct_ep  = _pct(ecart_at_ant_peak, ant_c[idx_ant_max])
    sum_ant_3h = sum(ant_c[best_i:best_i+3])
    pct_e3h = _pct(ecart_3h, sum_ant_3h) if sum_ant_3h else None

    forte_idx = [i for i, a in enumerate(ant_c) if a > seuil]
    if forte_idx:
        ecart_forte    = sum(diffs[i] for i in forte_idx) / len(forte_idx)
        mean_ant_forte = sum(ant_c[i] for i in forte_idx) / len(forte_idx)
        pct_ef         = _pct(ecart_forte, mean_ant_forte)
    else:
        ecart_forte = None
        pct_ef      = None

    return {
        "ecart_moyen":       ecart_moyen,
        "pct_ecart_moyen":   pct_em,
        "pct_pan_over":      pct_pan_over,
        "n_common":          n_common,
        "pct_ecart_cumul":   pct_ecart_cumul,
        "ecart_forte":       ecart_forte,
        "pct_ecart_forte":   pct_ef,
        "seuil":             seuil,
        "ecart_max_1h":      ecart_max_1h,
        "pct_ecart_max_1h":  pct_e1h,
        "ts_max_1h":         ts_max_1h,
        "ecart_at_ant_peak": ecart_at_ant_peak,
        "pct_ecart_at_peak": pct_ep,
        "ts_ant_peak":       ts_ant_peak,
        "ecart_3h":          ecart_3h,
        "pct_ecart_3h":      pct_e3h,
        "ts_3h_start":       ts_3h_start,
        "ts_3h_end":         ts_3h_end,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Lecture / écriture GRD
# ─────────────────────────────────────────────────────────────────────────────

def lire_grd(filepath):
    """Lit un fichier GRD/ASC (format ESRI ASCII) → (np.array float32, header dict)."""
    if not HAS_NUMPY:
        raise ImportError("numpy requis pour lire_grd")
    header = {}
    header_keys = {"ncols", "nrows", "xllcorner", "yllcorner",
                   "xllcenter", "yllcenter", "cellsize",
                   "nodata_value", "nodata"}
    rows = []
    with open(filepath, "r") as fh:
        for line in fh:
            parts = line.strip().split()
            if not parts:
                continue
            if parts[0].lower() in header_keys:
                header[parts[0].lower()] = float(parts[1])
            else:
                rows.append([float(v) for v in parts])
    arr = np.array(rows, dtype=np.float32)
    h = {
        "ncols":     int(header.get("ncols", arr.shape[1])),
        "nrows":     int(header.get("nrows", arr.shape[0])),
        "xllcorner": header.get("xllcorner", header.get("xllcenter", 0)),
        "yllcorner": header.get("yllcorner", header.get("yllcenter", 0)),
        "cellsize":  header.get("cellsize", 1000),
        "nodata":    header.get("nodata_value", header.get("nodata", -1)),
    }
    return arr, h


def lire_asc_numpy(filepath):
    """Lecture rapide d'un fichier ESRI ASCII (.asc/.grd) via numpy.loadtxt."""
    if not HAS_NUMPY:
        raise ImportError("numpy requis pour lire_asc_numpy")
    header = {}
    header_keys = {"ncols", "nrows", "xllcorner", "yllcorner",
                   "xllcenter", "yllcenter", "cellsize",
                   "nodata_value", "nodata"}
    skip = 0
    with open(filepath, "r") as fh:
        for line in fh:
            parts = line.strip().split()
            if not parts:
                skip += 1
                continue
            if parts[0].lower() in header_keys:
                header[parts[0].lower()] = float(parts[1])
                skip += 1
            else:
                break
    ncols_hdr = int(header.get("ncols", 0))
    uc  = range(ncols_hdr) if ncols_hdr else None
    arr = np.loadtxt(filepath, skiprows=skip, dtype=np.float32, usecols=uc)
    h = {
        "ncols":     int(header.get("ncols",     arr.shape[1])),
        "nrows":     int(header.get("nrows",     arr.shape[0])),
        "xllcorner": header.get("xllcorner", header.get("xllcenter", 0)),
        "yllcorner": header.get("yllcorner", header.get("yllcenter", 0)),
        "cellsize":  header.get("cellsize", 1000),
        "nodata":    header.get("nodata_value", header.get("nodata", -1)),
    }
    return arr, h


def calculer_cumul_grd(grd_dir):
    """Somme tous les .grd du dossier (1/10 mm → mm via ×0.1) → (cumul mm, header)."""
    if not HAS_NUMPY:
        raise ImportError("numpy requis pour calculer_cumul_grd")
    fichiers = sorted(
        f for f in os.listdir(grd_dir)
        if f.lower().endswith(".grd") or f.lower().endswith(".asc"))
    if not fichiers:
        raise ValueError(f"Aucun fichier GRD dans {grd_dir}")
    cumul  = None
    header = None
    for fname in fichiers:
        arr, h = lire_grd(os.path.join(grd_dir, fname))
        valid = arr != h["nodata"]
        vals  = np.where(valid, arr * 0.1, 0.0)
        if cumul is None:
            cumul  = vals
            header = h
        else:
            cumul += vals
    return cumul, header


def ecrire_grd(filepath, array, header):
    """Écrit un tableau numpy en format ESRI ASCII GRD."""
    with open(filepath, "w") as fh:
        fh.write(f"ncols         {header['ncols']}\n")
        fh.write(f"nrows         {header['nrows']}\n")
        fh.write(f"xllcorner     {header['xllcorner']:.2f}\n")
        fh.write(f"yllcorner     {header['yllcorner']:.2f}\n")
        fh.write(f"cellsize      {header['cellsize']:.2f}\n")
        fh.write("NODATA_VALUE  -1\n")
        for row in array:
            fh.write(" ".join(f"{v:.4f}" for v in row) + "\n")


# ─────────────────────────────────────────────────────────────────────────────
# Indices spatiaux d'un épisode
# ─────────────────────────────────────────────────────────────────────────────

def indices_ep_calcul(ep, produit, pluies_dir, bv_dir, masque_path=None):
    """Charge le GRD cumul et calcule CV, Gini, Max/Moy sur les pixels BV.

    Retourne dict {cv, gini, max_moy} ou None si données manquantes.
    Pas de cache — le cache est géré par l'appelant (App._indices_ep).

    Paramètres
    ----------
    ep         : dict épisode {_key, ...}
    produit    : "antilope" ou "panthere"
    pluies_dir : dossier Pluies/
    bv_dir     : dossier "Pluies temps moy BV pour graph"/
    masque_path: chemin vers le fichier .asc du masque BV (optionnel)
    """
    if not HAS_NUMPY:
        return None
    key = ep.get("_key", ep.get("label", ""))
    try:
        cumul_dir = os.path.join(bv_dir, "GRD cumuls")
        if produit == "antilope":
            candidates = [f"AntJ1-Ep_{key}", f"Pluie-Ep_{key}"]
            pfx = "AntJ1_CumulGRD-Ep_"
        else:
            candidates = [f"Pant-Ep_{key}"]
            pfx = "Pant_CumulGRD-Ep_"
        cumul_path = os.path.join(cumul_dir, f"{pfx}{key}.grd")
        if os.path.isfile(cumul_path):
            arr, hdr = lire_grd(cumul_path)
        else:
            grd_dir = next(
                (os.path.join(pluies_dir, c) for c in candidates
                 if os.path.isdir(os.path.join(pluies_dir, c))), None)
            if grd_dir is None:
                return None
            arr, hdr = calculer_cumul_grd(grd_dir)
            os.makedirs(cumul_dir, exist_ok=True)
            ecrire_grd(cumul_path, arr, hdr)

        data = np.where(arr == hdr["nodata"], np.nan, arr)

        masque_array = None
        mask_header  = None
        if masque_path and os.path.isfile(masque_path):
            masque_array, mask_header = lire_asc_numpy(masque_path)

        if masque_array is not None and mask_header is not None:
            mx   = mask_header["xllcorner"]; my  = mask_header["yllcorner"]
            mcs  = mask_header["cellsize"];  mnr = mask_header["nrows"]
            mnc  = mask_header["ncols"]
            nc_g = hdr["ncols"]; nr_g = hdr["nrows"]
            cs_g = hdr["cellsize"]
            xll_g = hdr["xllcorner"]; yll_g = hdr["yllcorner"]
            cols_g = np.arange(nc_g)
            rows_g = np.arange(nr_g)
            gx = xll_g + (cols_g + 0.5) * cs_g
            gy = yll_g + (nr_g - rows_g - 0.5) * cs_g
            mj = ((gx - mx) / mcs).astype(int)
            mi = ((my + mnr * mcs - gy) / mcs).astype(int)
            valid_col = (mj >= 0) & (mj < mnc)
            valid_row = (mi >= 0) & (mi < mnr)
            vals = []
            for ri in range(nr_g):
                if not valid_row[ri]:
                    continue
                for ci in range(nc_g):
                    if not valid_col[ci]:
                        continue
                    v = data[ri, ci]
                    if not np.isnan(v) and masque_array[mi[ri], mj[ci]] == 1:
                        vals.append(v)
            pixels_bv = np.array(vals, dtype=np.float32)
        else:
            pixels_bv = data[~np.isnan(data)]

        if pixels_bv.size <= 1:
            return None
        mu = float(np.mean(pixels_bv))
        if mu <= 0:
            return None
        cv      = float(np.std(pixels_bv)) / mu
        max_moy = float(np.max(pixels_bv)) / mu
        px_s    = np.sort(pixels_bv)
        n_s     = len(px_s)
        gini    = float(
            (2 * np.dot(np.arange(1, n_s + 1, dtype=np.float64), px_s)
             / (n_s * float(np.sum(px_s)))) - (n_s + 1) / n_s)
        return {"cv": max(0.0, cv), "gini": max(0.0, gini), "max_moy": max_moy}

    except Exception as exc:
        print(f"[WARN] indices_ep_calcul {produit} ep={key} : {exc}")
        return None
