# -*- coding: utf-8 -*-
"""Import automatique de crues dans un projet Plathynes de calage."""

import os
import shutil
from datetime import datetime, timedelta


# ── Correspondance Vig. max. → suffixe NOM_EVT ──────────────────────────────
VIG_SUFFIX = {
    "Rouge":     "R",
    "ZT Rouge":  "ZT_R",
    "Orange":    "Or",
    "ZT Orange": "ZT_Or",
    "Jaune":     "Jn",
    "ZT Jaune":  "ZT_Jn",
    "Vert":      "Vt",
}


def nom_evt_from_date_vig(date_debut, vig_label):
    """Construit le NOM_EVT Plathynes à partir de la date début et la vigilance max."""
    suffix = VIG_SUFFIX.get(vig_label, "Vt")
    return f"{date_debut.strftime('%d_%m_%Y')}_{suffix}"


def lire_info_projet(prj_path):
    """Lit un fichier .prj Plathynes et retourne les infos clés.

    Retourne un dict :
        nom        : str — nom du projet
        bassin     : str — nom du bassin
        station    : str — nom de la station hydro
        station_x  : float
        station_y  : float
        evenements : list of str — noms des évènements existants
    """
    info = {
        "nom": "", "bassin": "", "station": "",
        "station_x": 0.0, "station_y": 0.0,
        "evenements": [],
    }
    try:
        with open(prj_path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if line.startswith("Nom:"):
                    info["nom"] = line.split(":", 1)[1].strip()
                elif line.startswith("Bassin:"):
                    info["bassin"] = line.split(":", 1)[1].strip()
                elif line.lower().startswith("station hydro:"):
                    parts = line.split(":", 1)[1].strip().split()
                    if len(parts) >= 4:
                        info["station"] = parts[0]
                        try:
                            info["station_x"] = float(parts[2])
                            info["station_y"] = float(parts[3])
                        except (ValueError, IndexError):
                            pass
                elif line.startswith("Evenement:"):
                    nom = line.split(":", 1)[1].strip().split()[0]
                    info["evenements"].append(nom)
    except OSError:
        pass
    return info


def lire_plages_evenements(prj_path, prj_info):
    """Retourne la liste des plages (date_deb, date_fin) des évènements existants.

    Lit les fichiers .evt dans <projet_root>/<bassin>/Ev_<NOM>/
    et parse 'Date de debut' / 'Date de fin'.
    """
    plages = []
    projet_root = os.path.dirname(prj_path)
    bassin = prj_info.get("bassin", "")
    if not bassin:
        return plages
    sals_dir = os.path.join(projet_root, bassin)
    for nom_evt in prj_info.get("evenements", []):
        evt_path = os.path.join(sals_dir, f"Ev_{nom_evt}", f"{nom_evt}.evt")
        deb = fin = None
        try:
            with open(evt_path, encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    line = line.strip()
                    if line.startswith("Date de debut:"):
                        try:
                            deb = datetime.strptime(line.split(":", 1)[1].strip(),
                                                    "%Y-%m-%d %H:%M:%S")
                        except ValueError:
                            pass
                    elif line.startswith("Date de fin:"):
                        try:
                            fin = datetime.strptime(line.split(":", 1)[1].strip(),
                                                    "%Y-%m-%d %H:%M:%S")
                        except ValueError:
                            pass
        except OSError:
            continue
        if deb and fin:
            plages.append((deb, fin))
    return plages


def _dates_se_chevauchent(deb1, fin1, plages):
    """Retourne True si [deb1, fin1] chevauche au moins une plage de la liste."""
    if deb1 is None or fin1 is None:
        return False
    for deb2, fin2 in plages:
        if deb1 <= fin2 and fin1 >= deb2:
            return True
    return False


def _detecter_pdt(grd_dir):
    """Détecte le pas de temps à partir des noms de fichiers GRD.

    Retourne une chaîne au format Plathynes "0 HH:MM:SS" (défaut: 1h).
    """
    grds = sorted(f for f in os.listdir(grd_dir) if f.endswith(".grd"))
    if len(grds) < 2:
        return "0 01:00:00"
    try:
        t0 = datetime.strptime(grds[0][:12], "%Y%m%d%H%M")
        t1 = datetime.strptime(grds[1][:12], "%Y%m%d%H%M")
        delta_min = int((t1 - t0).total_seconds() // 60)
        h = delta_min // 60
        m = delta_min % 60
        return f"0 {h:02d}:{m:02d}:00"
    except (ValueError, IndexError):
        return "0 01:00:00"


def _generer_mrr(nom_evt, ep_key, grd_data_dir, mrr_path, log_fn):
    """Génère le fichier .mrr référençant les GRD de pluie."""
    grds = sorted(f for f in os.listdir(grd_data_dir) if f.endswith(".grd"))
    pdt = _detecter_pdt(grd_data_dir)
    repertoire_rel = f"./DATA/P/Pluie-Ep_{ep_key}"

    lines = [
        "################################################################################",
        "# Data settings",
        "################################################################################",
        "Type de donnees: GRD",
        f"Station: {nom_evt}",
        f"Pas de temps: {pdt}",
        "Facteur multiplicatif:  0.10000E+01",
        f"Repertoire des donnees: {repertoire_rel}",
    ]
    for grd in grds:
        lines.append(f".\\{grd}")
    lines.append("")

    with open(mrr_path, "w", encoding="utf-8", newline="\r\n") as fh:
        fh.write("\n".join(lines))
    log_fn(f"  → MRR généré : {len(grds)} fichiers GRD")


def _lire_dates_q(q_src):
    """Retourne (date_debut, date_fin) depuis un fichier Q-Ep_*.txt.

    Format attendu : DD/MM/YYYY HH:MM;valeur
    Retourne (None, None) si le fichier est illisible.
    """
    dates = []
    try:
        with open(q_src, encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    dt = datetime.strptime(raw.split(";")[0].strip(), "%d/%m/%Y %H:%M")
                    dates.append(dt)
                except (ValueError, IndexError):
                    continue
    except OSError:
        pass
    if len(dates) >= 2:
        return min(dates), max(dates)
    return None, None


def _lire_hu_debut(hu_src):
    """Retourne la première valeur HU_moy depuis un fichier HU-Ep_*.csv.

    Format attendu (séparateur ';') :
        date;HU_moy
        DD/MM/YYYY HH:MM;valeur

    Retourne None si le fichier est absent ou illisible.
    """
    if not hu_src or not os.path.isfile(hu_src):
        return None
    try:
        with open(hu_src, encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw or raw.lower().startswith("date"):
                    continue
                parts = raw.split(";")
                if len(parts) >= 2:
                    try:
                        return float(parts[1].strip())
                    except ValueError:
                        continue
    except OSError:
        pass
    return None


def _generer_evt(nom_evt, q_src, hu_src, evt_path, log_fn,
                 pdt_forcage="00:15", pdt_calcul="00:15",
                 pdt_sorties="00:15", pdt_bilans="00:15"):
    """Génère le fichier .evt (descripteur principal de l'évènement Plathynes).

    Les dates sont lues depuis le fichier Q pour être exactes.
    L'HU initial est lu depuis la première ligne de HU-Ep_*.csv.
    Les pas de temps sont paramétrables (en HH:MM).
    """
    date_deb, date_fin = _lire_dates_q(q_src) if (q_src and os.path.isfile(q_src)) else (None, None)
    if date_deb is None:
        deb_str = "0001-01-01 00:00:00"
        fin_str = "0001-01-01 00:00:00"
    else:
        deb_str = date_deb.strftime("%Y-%m-%d %H:%M:%S")
        fin_str = date_fin.strftime("%Y-%m-%d %H:%M:%S")

    hu_debut = _lire_hu_debut(hu_src)

    # Chemins relatifs avec slashes (convention Plathynes _HU)
    mrr_rel = f"Ev_{nom_evt}/{nom_evt}_RRobs.mrr"
    mqo_rel = f"Ev_{nom_evt}/{nom_evt}_1.mqo"

    # Section Parameters (HU initial) — ajoutée seulement si HU disponible
    params_block = ""
    if hu_debut is not None:
        params_block = (
            "#===============================================================================\n"
            "# Parameters\n"
            "#===============================================================================\n"
            "Nombre de parametres evenementiels: 1\n"
            f"Parametre evenementiel: U {hu_debut} HU\n"
            "\n"
        )

    content = (
        "#===============================================================================\n"
        "# event settings\n"
        "#===============================================================================\n"
        f"Nom de l'evenement: {nom_evt}\n"
        f"Description: {nom_evt}\n"
        "\n"
        "#===============================================================================\n"
        "# Temporal settings\n"
        "#===============================================================================\n"
        f"Date de debut: {deb_str}\n"
        f"Date de fin: {fin_str}\n"
        f"Pas de temps de forcage: {pdt_forcage}\n"
        f"Pas de temps de calcul: {pdt_calcul}\n"
        f"Pas de temps des sorties: {pdt_sorties}\n"
        f"Pas de temps des bilans: {pdt_bilans}\n"
        "\n"
        + params_block +
        "#===============================================================================\n"
        "# Forcing settings\n"
        "#===============================================================================\n"
        "Nombre de sources de pluies: 1\n"
        f"Source de pluie: {mrr_rel}\n"
        "\n"
        "#===============================================================================\n"
        "# Observations\n"
        "#===============================================================================\n"
        "Nombre de fichiers d'observations: 1\n"
        f"Fichier d'observation: {mqo_rel}\n"
        "\n"
    )
    with open(evt_path, "w", encoding="utf-8", newline="\r\n") as fh:
        fh.write(content)
    hu_msg = f", HU début = {hu_debut}" if hu_debut is not None else " (HU non disponible)"
    log_fn(f"  → EVT généré : {deb_str} → {fin_str}{hu_msg}")


def _generer_mqo(nom_evt, q_src, mqo_path, nom_station, x, y, log_fn):
    """Génère le fichier .mqo débit observé à partir du CSV Q de l'outil.

    Format source  : DD/MM/YYYY HH:MM;valeur
    Format MQO     : YYYY-MM-DD HH:MM:SS        valeur
    """
    lignes_q = []
    with open(q_src, encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            raw = raw.strip()
            if not raw:
                continue
            try:
                date_str, val_str = raw.split(";", 1)
                dt = datetime.strptime(date_str.strip(), "%d/%m/%Y %H:%M")
                val = float(val_str.strip())
                lignes_q.append((dt, val))
            except (ValueError, IndexError):
                continue

    header = (
        f"MQO file for station {nom_station}, series 1\n"
        "\n"
        " 1\n"
        f"StationID               X            Y Type\n"
        f"{nom_station} {x:.2f} {y:.2f} Qobs 0.000\n"
        "      Date     Time  Qobs [m3/s]\n"
    )

    data_lines = []
    for dt, val in lignes_q:
        data_lines.append(f"{dt.strftime('%Y-%m-%d %H:%M:%S')}        {val:.3f}")

    with open(mqo_path, "w", encoding="utf-8", newline="\r\n") as fh:
        fh.write(header)
        fh.write("\n".join(data_lines))
        fh.write("\n")

    log_fn(f"  → MQO généré : {len(lignes_q)} pas de temps Q")


def _maj_prj(prj_path, nom_evt, log_fn):
    """Met à jour le fichier .prj en ajoutant le nouvel évènement."""
    with open(prj_path, encoding="utf-8", errors="replace") as fh:
        lines = fh.readlines()

    evt_line = f"Evenement: {nom_evt} 0 -1 1.0 0\n"

    # Trouver la ligne "Number of events:" et la dernière ligne "Evenement:"
    idx_nb_evt = None
    idx_last_evt = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.lower().startswith("number of events:"):
            idx_nb_evt = i
        elif stripped.startswith("Evenement:"):
            idx_last_evt = i

    if idx_nb_evt is None:
        raise ValueError(f"Ligne 'Number of events' introuvable dans {prj_path}")

    # Incrémenter le compteur
    parts = lines[idx_nb_evt].split(":", 1)
    try:
        nb = int(parts[1].strip()) + 1
    except ValueError:
        nb = 1
    lines[idx_nb_evt] = f"{parts[0]}: {nb}\n"

    # Insérer le nouvel évènement après le dernier, ou juste après "Number of events"
    insert_after = idx_last_evt if idx_last_evt is not None else idx_nb_evt
    lines.insert(insert_after + 1, evt_line)

    with open(prj_path, "w", encoding="utf-8", newline="\r\n") as fh:
        fh.writelines(lines)

    log_fn(f"  → .prj mis à jour : {nb} évènement(s) total")


def importer_evenement(nom_evt, ep_key, grd_src_dir, q_src, hu_src,
                       projet_root, prj_path, nom_station, x, y, log_fn=None,
                       pdt_forcage="00:15", pdt_calcul="00:15",
                       pdt_sorties="00:15", pdt_bilans="00:15"):
    """Importe un épisode comme évènement de calage Plathynes.

    Paramètres
    ----------
    nom_evt      : NOM_EVT Plathynes (ex: "28_11_2014_ZT_Or")
    ep_key       : clé épisode outil (ex: "28_11_2014_Cassaignes")
    grd_src_dir  : dossier GRD source (Pluies/AntJ1-Ep_<key>/) ou None
    q_src        : fichier Q source (Debits/Q-Ep_<key>.txt)
    hu_src       : fichier HU source ou None
    projet_root  : racine du projet Plathynes (dossier contenant DATA/ et Sals/)
    prj_path     : chemin vers le .prj
    nom_station  : nom de la station (ex: "Cassaignes")
    x, y         : coordonnées Lambert-93 de la station
    log_fn       : callable(str) pour le journal
    """
    log = log_fn or (lambda s: None)

    # ── 1. Copie GRD → DATA/P/Pluie-Ep_<key>/ ──────────────────────────────
    grd_dest_dir = os.path.join(projet_root, "DATA", "P", f"Pluie-Ep_{ep_key}")
    if grd_src_dir and os.path.isdir(grd_src_dir):
        os.makedirs(grd_dest_dir, exist_ok=True)
        n_grd = 0
        for fname in os.listdir(grd_src_dir):
            if fname.endswith(".grd"):
                shutil.copy2(os.path.join(grd_src_dir, fname),
                             os.path.join(grd_dest_dir, fname))
                n_grd += 1
        log(f"  → GRD copiés : {n_grd} fichiers → DATA/P/Pluie-Ep_{ep_key}/")
    else:
        log("  [AVERT] Dossier GRD absent — .mrr créé sans données pluie")

    # ── 2. Copie Q → DATA/Q/ ────────────────────────────────────────────────
    q_dest_dir = os.path.join(projet_root, "DATA", "Q")
    os.makedirs(q_dest_dir, exist_ok=True)
    q_dest = os.path.join(q_dest_dir, f"Q-Ep_{ep_key}.txt")
    if os.path.isfile(q_src):
        shutil.copy2(q_src, q_dest)
        log(f"  → Q copié → DATA/Q/Q-Ep_{ep_key}.txt")
    else:
        log(f"  [AVERT] Fichier Q introuvable : {q_src}")

    # ── 3. Copie HU → DATA/HU/ ──────────────────────────────────────────────
    if hu_src and os.path.isfile(hu_src):
        hu_dest_dir = os.path.join(projet_root, "DATA", "HU")
        os.makedirs(hu_dest_dir, exist_ok=True)
        hu_dest = os.path.join(hu_dest_dir, f"HU-Ep_{ep_key}.csv")
        shutil.copy2(hu_src, hu_dest)
        log(f"  → HU copié → DATA/HU/HU-Ep_{ep_key}.csv")

    # ── 4. Créer dossier Sals/Ev_<NOM_EVT>/ ────────────────────────────────
    sals_dir = os.path.join(projet_root, "Sals", f"Ev_{nom_evt}")
    os.makedirs(sals_dir, exist_ok=True)
    log(f"  → Dossier créé : Sals/Ev_{nom_evt}/")

    # ── 5. Générer .evt (fichier principal lu par Plathynes au chargement) ──
    evt_path = os.path.join(sals_dir, f"{nom_evt}.evt")
    _generer_evt(nom_evt, q_src, hu_src, evt_path, log,
                 pdt_forcage=pdt_forcage, pdt_calcul=pdt_calcul,
                 pdt_sorties=pdt_sorties, pdt_bilans=pdt_bilans)

    # ── 7. Générer .mrr ─────────────────────────────────────────────────────
    mrr_path = os.path.join(sals_dir, f"{nom_evt}_RRobs.mrr")
    if os.path.isdir(grd_dest_dir) and os.listdir(grd_dest_dir):
        _generer_mrr(nom_evt, ep_key, grd_dest_dir, mrr_path, log)
    else:
        _generer_mrr_vide(nom_evt, ep_key, mrr_path, log)

    # ── 8. Générer .mqo ─────────────────────────────────────────────────────
    mqo_path = os.path.join(sals_dir, f"{nom_evt}_1.mqo")
    if os.path.isfile(q_src):
        _generer_mqo(nom_evt, q_src, mqo_path, nom_station, x, y, log)
    else:
        log("  [AVERT] .mqo non généré — fichier Q manquant")

    # ── 9. Mettre à jour le .prj ────────────────────────────────────────────
    _maj_prj(prj_path, nom_evt, log)


def _generer_mrr_vide(nom_evt, ep_key, mrr_path, log_fn):
    """Génère un .mrr sans liste de fichiers (pluie absente)."""
    repertoire_rel = f"./DATA/P/Pluie-Ep_{ep_key}"
    lines = [
        "################################################################################",
        "# Data settings",
        "################################################################################",
        "Type de donnees: GRD",
        f"Station: {nom_evt}",
        "Pas de temps: 0 01:00:00",
        "Facteur multiplicatif:  0.10000E+01",
        f"Repertoire des donnees: {repertoire_rel}",
        "",
    ]
    with open(mrr_path, "w", encoding="utf-8", newline="\r\n") as fh:
        fh.write("\n".join(lines))
    log_fn("  → MRR généré (sans GRD)")
