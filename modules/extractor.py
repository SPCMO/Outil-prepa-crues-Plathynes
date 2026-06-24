# -*- coding: utf-8 -*-
"""Orchestration des extractions par episode."""

import csv
import os
from datetime import datetime, timedelta

from .bdimage_client import BdimageClient, BdimageError, calculer_pluie_bv_csv
from .phyc_client import PhycClient, PhycAuthError


class ExtractionError(Exception):
    pass


def run_extraction(config, episodes, options, log_fn, progress_fn=None):
    """Lance l'extraction complete pour une liste d'episodes.

    Retourne (errors, synthese_text) :
        errors        : liste de messages d'erreur
        synthese_text : résumé formaté par épisode (pour popup)
    """
    st = config.get("station", {})
    code_station = st.get("code_station", "")           # 10 car. Y+9 (pour H)
    code_site    = st.get("code_site", "") or code_station[:8] if code_station else ""  # 8 car. (pour Q/site)
    code_bnbv = st.get("code_bnbv", "")
    nom_station = st.get("nom_station", "") or code_site
    ul = st.get("ul", "")
    lr = st.get("lr", "")
    base_out = config.get("output_dir", "./sorties")
    bdimage_cfg = config.get("bdimage", {})
    phyc_cfg = config.get("phyc", {})

    if not ul or not lr:
        raise ExtractionError(
            "Bounding box non renseignee (UL / LR). "
            "Verifiez l'onglet Configuration."
        )

    bdi = BdimageClient(
        url=bdimage_cfg.get("url", "http://services.schapi.e2.rie.gouv.fr/bdimage/2016/wsbdi"),
        timeout_async=bdimage_cfg.get("timeout_async", 300),
        epsg=bdimage_cfg.get("epsg", 2154),
        resol=bdimage_cfg.get("resol", 1000),
        nodata=bdimage_cfg.get("nodata", -1),
    )

    phyc = None
    if options.get("debits"):
        grandeur_opt = options.get("grandeur", "Q")
        # Pour H on requête sur le code station complet ; pour Q sur le code site
        code_phyc = code_station if grandeur_opt == "H" else code_site
        if not code_phyc:
            raise ExtractionError(
                "Code station non renseigne. "
                "Verifiez l'onglet Configuration."
            )
        phyc = PhycClient(wsdl_url=phyc_cfg.get(
            "url", "http://services.schapi.e2.rie.gouv.fr/phycop/bdtr.wsdl"))
        log_fn("Connexion PHyC...")
        try:
            phyc.login(phyc_cfg.get("idcontact", ""), phyc_cfg.get("motdepasse", ""))
            log_fn(f"Connecte a PHyC. Station : {code_phyc} ({nom_station})")
        except PhycAuthError as e:
            raise ExtractionError(f"Authentification PHyC echouee : {e}")
        except Exception as e:
            raise ExtractionError(
                f"Connexion PHyC impossible : {e}\n"
                f"Verifiez l'URL WSDL et votre acces au RIE."
            )

    errors = []
    syntheses = []   # liste de (label, synthese_dict) par épisode
    total = len(episodes)

    try:
        for idx, episode in enumerate(episodes, 1):
            label = episode["label"]
            log_fn(f"\n{'='*60}")
            log_fn(f"Episode {idx}/{total} : {label}")

            ep_synthese = {}
            try:
                _process_episode(
                    episode=episode,
                    bdi=bdi, phyc=phyc,
                    ul=ul, lr=lr,
                    nom_station=nom_station,
                    code_phyc=code_phyc,
                    code_bnbv=code_bnbv,
                    base_out=base_out,
                    options=options,
                    log_fn=log_fn,
                    synthese_out=ep_synthese,
                )
            except Exception as e:
                log_fn(f"  [ERREUR] Episode {label} : {e}")
                log_fn(f"  --> Relance de l'episode {label} (1 tentative)...")
                ep_synthese_retry = {}
                try:
                    _process_episode(
                        episode=episode,
                        bdi=bdi, phyc=phyc,
                        ul=ul, lr=lr,
                        nom_station=nom_station,
                        code_phyc=code_phyc,
                        code_bnbv=code_bnbv,
                        base_out=base_out,
                        options=options,
                        log_fn=log_fn,
                        synthese_out=ep_synthese_retry,
                    )
                    ep_synthese = ep_synthese_retry
                    log_fn(f"  [OK] Relance reussie pour {label}.")
                except Exception as e2:
                    msg = f"Erreur episode {label} (echec apres relance) : {e2}"
                    log_fn(f"  [ECHEC] Relance echouee : {e2}")
                    errors.append(msg)
                    ep_synthese["_retry_echec"] = str(e2)

            syntheses.append((label, ep_synthese))

            if progress_fn:
                progress_fn(idx, total)

    finally:
        if phyc:
            phyc.logout()

    if errors:
        log_fn(f"\n{len(errors)} episode(s) en erreur :")
        for e in errors:
            log_fn(f"  - {e}")
    else:
        log_fn(f"\nExtraction terminee - {total} episode(s) traite(s).")

    return errors, _build_synthese_text(syntheses)


def _process_episode(episode, bdi, phyc, ul, lr, nom_station, code_phyc,
                     code_bnbv, base_out, options, log_fn, synthese_out=None):
    date_debut = episode["date_debut"]
    date_fin = episode["date_fin"]
    date_tag = date_debut.strftime("%d_%m_%Y")

    errs = []
    synthese = {}  # {type: {ok, n, lacunes}}

    # ── Pluies ───────────────────────────────────────────────────────────────
    if options.get("pluies"):
        pdt_p = options.get("pdt_pluies", 60)
        out_pluies = os.path.join(base_out, nom_station, "Pluies", f"AntJ1-Ep_{date_tag}_{nom_station}")
        log_fn(f"\n[Pluies] pdt={pdt_p}mn -> {out_pluies}")
        try:
            fichiers = bdi.extraire_pluies(
                date_debut=date_debut, date_fin=date_fin,
                ul=ul, lr=lr,
                pdt_minutes=pdt_p,
                output_dir=out_pluies,
                log_fn=log_fn,
            )
            dates_grd = _dates_from_grd_dir(out_pluies)
            lacunes = _check_lacunes(dates_grd, pdt_p)
            synthese["Pluies"] = {"ok": True, "n": len(dates_grd), "lacunes": lacunes,
                                   "pdt": pdt_p, "unite": "pas de temps (.grd)"}
            # Calcul pluie moyenne BV depuis les .grd déjà téléchargés
            pluie_graphique_dir = os.path.join(base_out, nom_station, "Pluies")
            out_pluie_bv = os.path.join(pluie_graphique_dir, f"PluieBV-Ep_{date_tag}_{nom_station}.csv")
            try:
                calculer_pluie_bv_csv(out_pluies, out_pluie_bv, log_fn=log_fn)
            except Exception as e:
                log_fn(f"  [PluieBV] AVERTISSEMENT : calcul moyenne echoue : {e}")
        except Exception as e:
            log_fn(f"  [Pluies] ERREUR : {e}")
            errs.append(f"Pluies : {e}")
            synthese["Pluies"] = {"ok": False, "erreur": str(e)}

    # ── HU ───────────────────────────────────────────────────────────────────
    if options.get("hu"):
        pdt_hu = options.get("pdt_hu", 60)
        mode_journalier = (pdt_hu == "journalier_6h")
        out_hu_dir = os.path.join(base_out, nom_station, "HU")
        os.makedirs(out_hu_dir, exist_ok=True)
        out_hu_file = os.path.join(out_hu_dir, f"HU-Ep_{date_tag}_{nom_station}.csv")
        mode_lbl = "journalier 6h" if mode_journalier else "horaire"
        log_fn(f"\n[HU] BV={code_bnbv or '?'} mode={mode_lbl} -> {out_hu_file}")
        try:
            if not code_bnbv:
                raise ValueError("Code BNBV non renseigné — impossible d'extraire l'HU moyen par BV.")
            bdi.extraire_hu_bv(
                code_bnbv=code_bnbv,
                date_debut=date_debut, date_fin=date_fin,
                output_file=out_hu_file,
                mode_journalier_6h=mode_journalier,
                log_fn=log_fn,
            )
            dates_hu = _dates_from_csv(out_hu_file, has_header=True)
            pdt_verif = 1440 if mode_journalier else 60
            lacunes = _check_lacunes(dates_hu, pdt_verif)
            synthese["HU"] = {"ok": True, "n": len(dates_hu), "lacunes": lacunes,
                               "pdt": pdt_verif, "unite": "pas de temps"}
        except Exception as e:
            log_fn(f"  [HU] ERREUR : {e}")
            errs.append(f"HU : {e}")
            synthese["HU"] = {"ok": False, "erreur": str(e)}

    # ── Débits / Hauteurs ─────────────────────────────────────────────────────
    if options.get("debits") and phyc and code_phyc:
        pdt_q = options.get("pdt_debits", 15)
        grandeur = options.get("grandeur", "Q")
        debits_dir = os.path.join(base_out, nom_station, "Debits")
        os.makedirs(debits_dir, exist_ok=True)
        filename = os.path.join(debits_dir, f"{grandeur}-Ep_{date_tag}_{nom_station}.txt")
        log_fn(f"\n[PHyC] grandeur={grandeur}, code={code_phyc}, pdt={pdt_q}mn -> {filename}")
        try:
            _extraire_debits(
                phyc=phyc,
                code_site=code_phyc,
                date_debut=date_debut,
                date_fin=date_fin,
                pdt=pdt_q,
                grandeur=grandeur,
                filename=filename,
                log_fn=log_fn,
            )
            dates_q = _dates_from_csv(filename, has_header=False)
            lacunes = _check_lacunes(dates_q, pdt_q)
            synthese[grandeur] = {"ok": True, "n": len(dates_q), "lacunes": lacunes,
                                   "pdt": pdt_q, "unite": "valeurs"}
        except Exception as e:
            log_fn(f"  [Debits] ERREUR : {e}")
            errs.append(f"Debits : {e}")
            synthese[grandeur] = {"ok": False, "erreur": str(e)}

    # ── Synthèse épisode ─────────────────────────────────────────────────────
    _log_synthese(log_fn, synthese)
    if synthese_out is not None:
        synthese_out.update(synthese)

    if errs:
        raise ExtractionError(" | ".join(errs))


def _log_synthese(log_fn, synthese):
    """Affiche un résumé structuré par type de donnée."""
    log_fn(f"\n{'─'*60}")
    log_fn("SYNTHESE :")
    for dtype, info in synthese.items():
        if not info.get("ok"):
            log_fn(f"  ✗ {dtype:<10} ERREUR : {info.get('erreur', '?')}")
            continue
        n       = info["n"]
        lacunes = info["lacunes"]
        pdt     = info["pdt"]
        unite   = info["unite"]
        if lacunes:
            log_fn(f"  ✗ {dtype:<10} {n} {unite} — {len(lacunes)} lacune(s) détectée(s) :")
            # Afficher max 5 lacunes pour ne pas noyer le journal
            for lac in lacunes[:5]:
                log_fn(f"             • {lac.strftime('%d/%m/%Y %H:%M')} (manquant)")
            if len(lacunes) > 5:
                log_fn(f"             ... et {len(lacunes) - 5} autre(s)")
        else:
            log_fn(f"  ✓ {dtype:<10} {n} {unite} — série continue (pdt={pdt}mn), aucune lacune")


# ---------------------------------------------------------------------------
# Extraction des débits PHyC
# ---------------------------------------------------------------------------

def _extraire_debits(phyc, code_site, date_debut, date_fin, pdt, grandeur, filename, log_fn):
    os.makedirs(os.path.dirname(os.path.abspath(filename)), exist_ok=True)

    xml_str = phyc.get_debits(
        listecdentite=[code_site],
        date_debut=date_debut,
        date_fin=date_fin,
        pasdetemps=pdt,
        grandeur=grandeur,
    )

    series = PhycClient.parse_series_xml(xml_str, grandeur=grandeur)
    points = series.get(code_site, [])

    if not points:
        log_fn(f"  Aucune donnee PHyC pour la station {code_site} sur la periode demandee.")
        return

    # Arrondir les timestamps au pas de temps grille
    points_snap = [(_snap_to_grid(dt, pdt), val) for dt, val in points]
    # Trier après arrondi
    points_snap.sort(key=lambda x: x[0])

    with open(filename, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh, delimiter=";")
        for dt, val in points_snap:
            writer.writerow([dt.strftime("%d/%m/%Y %H:%M"), val])

    log_fn(f"  {code_site} -> {len(points_snap)} valeurs -> {filename}")


# ---------------------------------------------------------------------------
# Utilitaires
# ---------------------------------------------------------------------------

def _snap_to_grid(dt, pdt_minutes):
    """Arrondit un datetime au multiple de pdt_minutes le plus proche (depuis minuit)."""
    midnight = dt.replace(hour=0, minute=0, second=0, microsecond=0)
    total_min = int((dt - midnight).total_seconds()) // 60
    snapped_min = round(total_min / pdt_minutes) * pdt_minutes
    return midnight + timedelta(minutes=snapped_min)


def _check_lacunes(datetimes_sorted, pdt_minutes):
    """Retourne la liste des pas de temps manquants dans une série ordonnée."""
    if len(datetimes_sorted) < 2:
        return []
    step = timedelta(minutes=pdt_minutes)
    lacunes = []
    for i in range(len(datetimes_sorted) - 1):
        expected = datetimes_sorted[i] + step
        while expected < datetimes_sorted[i + 1]:
            lacunes.append(expected)
            expected += step
    return lacunes


def _dates_from_csv(filepath, fmt="%d/%m/%Y %H:%M", has_header=True):
    """Lit les dates (colonne 0) d'un CSV et les retourne triées."""
    dates = []
    try:
        with open(filepath, encoding="utf-8") as f:
            reader = csv.reader(f, delimiter=";")
            if has_header:
                next(reader, None)
            for row in reader:
                if row:
                    try:
                        dates.append(datetime.strptime(row[0].strip(), fmt))
                    except ValueError:
                        pass
    except Exception:
        pass
    return sorted(dates)


def _build_synthese_text(syntheses):
    """Formate le texte de synthèse globale pour la popup post-extraction."""
    lines = []
    lines.append("=" * 58)
    lines.append(f"  SYNTHESE DES TELECHARGEMENTS — {len(syntheses)} episode(s)")
    lines.append("=" * 58)
    for label, syn in syntheses:
        lines.append(f"\nEpisode : {label}")
        lines.append("-" * 50)
        if not syn:
            lines.append("  Aucune donnee (extraction echouee ou non lancee)")
            continue
        if "_retry_echec" in syn:
            lines.append(f"  ✗  Echec apres relance : {syn['_retry_echec']}")
            syn = {k: v for k, v in syn.items() if k != "_retry_echec"}
            if not syn:
                continue
        for dtype, info in syn.items():
            if not info.get("ok"):
                lines.append(f"  ✗  {dtype:<12} ERREUR : {info.get('erreur', '?')}")
                continue
            n       = info["n"]
            lacunes = info["lacunes"]
            pdt     = info["pdt"]
            if lacunes:
                lines.append(f"  ✗  {dtype:<12} {n} pts (pdt={pdt}mn) — "
                             f"{len(lacunes)} lacune(s)")
                for lac in lacunes[:3]:
                    lines.append(f"       • {lac.strftime('%d/%m/%Y %H:%M')}")
                if len(lacunes) > 3:
                    lines.append(f"       ... +{len(lacunes)-3} autre(s)")
            else:
                lines.append(f"  ✓  {dtype:<12} {n} pts (pdt={pdt}mn) — serie complete")
    lines.append("")
    return "\n".join(lines)


def _dates_from_grd_dir(output_dir):
    """Extrait les datetimes des noms de fichiers .grd (format AAAAMMJJhhmm.grd)."""
    dates = []
    if not os.path.isdir(output_dir):
        return dates
    for fname in sorted(os.listdir(output_dir)):
        if fname.endswith(".grd") and len(fname) == 16:  # 12 + ".grd"
            try:
                dates.append(datetime.strptime(fname[:12], "%Y%m%d%H%M"))
            except ValueError:
                pass
    return dates
