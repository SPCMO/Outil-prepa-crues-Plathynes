# -*- coding: utf-8 -*-
"""Client BDImage Python 3 — pluies spatialisées et humidité des sols (HU).

Réimplémentation Python 3 du cœur de libbdimage/aspimage.
Pas de dépendance à la lib Python 2 existante.
"""

import gzip
import io
import os
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

import requests

BDIMAGE_URL = "http://services.schapi.e2.rie.gouv.fr/bdimage/2016/wsbdi"
NODATA = -1
ENTETE = "NCOLS {ncols}\nNROWS {nrows}\nXLLCORNER {xll}\nYLLCORNER {yll}\nCELLSIZE {cellsize}\nNODATA_VALUE {nodata}\n"

# Première date des produits temps-différé nouvelle nomenclature (12/10/2020)
_ANTILOPE_TD_FIRST = datetime(2020, 10, 12)

# Produit historique disponible depuis 01/07/2006 (60mn uniquement)
_ANTILOPE_J1 = ("antilope", "j1")


def _antilope_product(pdt_minutes, date_debut):
    """Sélectionne le bon produit antilope selon la date et le pas de temps.

    Avant le 12/10/2020, seul j1 (60mn) existe en temps-différé.
    """
    if date_debut >= _ANTILOPE_TD_FIRST:
        if pdt_minutes <= 15:
            return ("antilope", "france-td-15mn"), pdt_minutes
        return ("antilope", "france-td-60mn"), pdt_minutes
    else:
        # Historique : j1 est horaire uniquement — on force pdt=60 si nécessaire
        effective_pdt = max(pdt_minutes, 60)
        return _ANTILOPE_J1, effective_pdt

SIM_HU_PRODUCT = ("sim", "hu")


class BdimageError(Exception):
    pass


class BdimageClient:

    def __init__(self, url=BDIMAGE_URL, timeout_async=300, epsg=2154, resol=1000, nodata=NODATA):
        self.url = url
        self.timeout_async = timeout_async
        self.epsg = epsg
        self.resol = resol
        self.nodata = nodata
        self._session = requests.Session()
        self._session.headers.update({
            "user-agent": "PrepacruesPlathynes/1.0 (Python3)"
        })

    # ------------------------------------------------------------------
    # API publique
    # ------------------------------------------------------------------

    def extraire_pluies(self, date_debut, date_fin, ul, lr, pdt_minutes=60,
                        output_dir=".", log_fn=None):
        """Extrait les pluies spatialisées antilope sur une bbox.

        Arguments:
            date_debut, date_fin (datetime) : période de l'épisode
            ul, lr (str) : coins haut-gauche et bas-droite en Lambert 93
                           format 'X,Y' (ex: '594815,6336216')
            pdt_minutes (int) : 15, 30 ou 60
            output_dir (str) : dossier de sortie pour les .grd
            log_fn (callable) : fonction de log(str)

        Retourne:
            list[str] : chemins des fichiers .grd créés
        """
        (type_img, sous_type), effective_pdt = _antilope_product(pdt_minutes, date_debut)
        if effective_pdt != pdt_minutes and log_fn:
            log_fn(f"  ⚠ Pas de produit {pdt_minutes}mn avant le 12/10/2020 — "
                   f"utilisation de {type_img}/{sous_type} (pdt={effective_pdt}mn)")

        return self._extraire_bbox(
            type_img=type_img, sous_type=sous_type,
            date_debut=date_debut, date_fin=date_fin,
            ul=ul, lr=lr,
            pdt=effective_pdt, duree=effective_pdt,
            bandes="rr",
            facteur=0.1,          # 1/10e mm → mm
            force_integer=True,
            output_dir=output_dir,
            log_fn=log_fn,
        )

    def extraire_pluies_panthere(self, date_debut, date_fin, ul, lr,
                                output_dir=".", log_fn=None):
        """Extrait les pluies spatialisées Panthère sur une bbox.

        Seul le produit panthere/france (60 mn) est disponible sur BDImage SCHAPI
        (confirmé par sondage — les sous-types td, j0, j1, france-td, td-5mn
        retournent tous une erreur de type).

        Arguments identiques à extraire_pluies().
        Retourne list[str] : chemins des fichiers .grd créés.
        """
        return self._extraire_bbox(
            type_img="panthere", sous_type="france",
            date_debut=date_debut, date_fin=date_fin,
            ul=ul, lr=lr,
            pdt=60, duree=60,
            bandes="rr",
            facteur=0.1,
            force_integer=True,
            output_dir=output_dir,
            log_fn=log_fn,
        )

    def extraire_hu_bv(self, code_bnbv, date_debut, date_fin,
                       output_file, mode_journalier_6h=False, log_fn=None):
        """Extrait l'HU moyen pour un bassin versant (code BNBV).

        mode_journalier_6h=False : extraction horaire (pdt=60 min), toutes les heures.
        mode_journalier_6h=True  : extraction horaire puis filtrage pour ne conserver
                                   que la valeur de 06:00 de chaque jour (heure de
                                   production et d'actualisation de la donnée SIM HU).

        Utilise getObsStatsByZonesAsync — renvoie directement la moyenne
        spatiale SIM/HU pour la zone BNBV, sans passer par des .grd.

        Écrit un fichier CSV : date;HU_moy
        Retourne le nombre de pas de temps écrits.
        """
        import csv
        log = log_fn or (lambda s: None)
        pdt = 60  # toujours horaire côté BDImage ; filtrage appliqué en post-traitement

        date_debut_snp = _snap_floor(date_debut, pdt)
        date_fin_snp   = _snap_ceil(date_fin, pdt)

        data = {
            "request":       "getObsStatsByZonesAsync",
            "typeImage":     "sim",
            "sousTypeImage": "hu",
            "dateDeb":       _fmt_bdimage(date_debut_snp),
            "dateFin":       _fmt_bdimage(date_fin_snp),
            "duree":         _fmt_duree(0),      # instantané (depth=0)
            "pdt":           _fmt_duree(pdt),
            "bandes":        "brut",
        }
        log(f"  → Requête BDImage zones : sim/hu BV={code_bnbv} "
            f"{_fmt_bdimage(date_debut_snp)}→{_fmt_bdimage(date_fin_snp)}")

        # Mode async uniquement — épisodes toujours dans le passé
        # Les zones doivent être en multipart gzippé (BDImage exige .gz ou .7z)
        zones_raw = code_bnbv.encode("utf-8")
        buf = io.BytesIO()
        # filename="" évite d'inclure un nom de fichier dans l'en-tête gzip
        with gzip.GzipFile(filename="", mode="wb", fileobj=buf) as gz:
            gz.write(zones_raw)
        zones_gz = buf.getvalue()

        # application/octet-stream = même comportement que l'ancienne lib Python 2
        resp = self._session.post(
            self.url, data=data,
            files={"zones": ("zones.gz", zones_gz, "application/octet-stream")},
            timeout=60,
        )
        resp.raise_for_status()
        xml_bytes = _decompress(resp.content)
        uri = _parse_report_uri(xml_bytes)
        log("  → Requête async lancée, polling URI...")
        xml_result = self._poll_async(uri, log)

        # Parser les stats par zone et par image
        root = ET.fromstring(xml_result)
        observations = root.find("observations")
        if observations is None:
            raise BdimageError("Aucune donnée stats zones dans la réponse BDImage.")

        # Collecter et trier par date avant écriture
        rows = []
        for image in observations.findall("image"):
            date_str = image.attrib.get("date", "")
            for bande in image.findall(".//bande"):
                for stats_el in bande.findall("stats"):
                    moy_el = stats_el.find("stat[@parametre='moy']")
                    if moy_el is not None and moy_el.text:
                        try:
                            dt  = datetime.strptime(date_str, "%Y%m%d%H%M")
                            val = round(float(moy_el.text), 1)
                            rows.append((dt, val))
                        except (ValueError, TypeError):
                            pass
        rows.sort(key=lambda x: x[0])

        # Filtrage journalier à 6:00 si demandé
        if mode_journalier_6h:
            rows = [(dt, val) for dt, val in rows if dt.hour == 6 and dt.minute == 0]
            log(f"  → Mode journalier 6h : {len(rows)} valeur(s) à 06:00 retenues")

        os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)
        with open(output_file, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh, delimiter=";")
            writer.writerow(["date", "HU_moy"])
            for dt, val in rows:
                writer.writerow([dt.strftime("%d/%m/%Y %H:%M"), val])

        n = len(rows)
        log(f"  → {n} pas de temps HU écrits dans {output_file}")
        return n

    # ------------------------------------------------------------------
    # Requête BDImage async
    # ------------------------------------------------------------------

    def _extraire_prevision_bbox(self, type_img, sous_type, date_network,
                                date_debut, date_fin, ul, lr, pdt, duree, bandes,
                                facteur=1.0, force_integer=True,
                                output_dir=".", log_fn=None):
        """Extrait un produit de prévision via getPrevByNetworkValuesByBBoxAsync.

        date_network : datetime du réseau/run (ex : 00H du jour J)
        date_debut   : début de la fenêtre de prévision souhaitée (valide time)
        date_fin     : fin   de la fenêtre de prévision souhaitée (valide time)
        """
        os.makedirs(output_dir, exist_ok=True)
        log = log_fn or (lambda s: None)

        data = {
            "request":       "getPrevByNetworkValuesByBBoxAsync",
            "typeImage":     type_img,
            "sousTypeImage": sous_type,
            "dateNetwork":   _fmt_bdimage(date_network),
            "dateDeb":       _fmt_bdimage(date_debut),
            "dateFin":       _fmt_bdimage(date_fin),
            "duree":         _fmt_duree(duree),
            "pdt":           _fmt_duree(pdt),
            "ul":            ul,
            "lr":            lr,
            "resol":         str(self.resol),
            "epsg":          str(self.epsg),
            "bandes":        bandes,
        }

        log(f"  → Requête BDImage prévision : {type_img}/{sous_type} "
            f"réseau={_fmt_bdimage(date_network)} "
            f"{_fmt_bdimage(date_debut)}→{_fmt_bdimage(date_fin)} "
            f"pdt={pdt}mn duree={duree}mn")

        resp = self._session.post(self.url, data=data, timeout=60)
        resp.raise_for_status()
        xml_bytes = _decompress(resp.content)
        uri = _parse_report_uri(xml_bytes)
        log(f"  → Requête lancée, polling URI...")

        xml_result = self._poll_async(uri, log)

        fichiers = _xml_to_grds(
            xml_bytes=xml_result,
            ul=ul, lr=lr,
            resol=self.resol, nodata=self.nodata,
            facteur=facteur, force_integer=force_integer,
            output_dir=output_dir, log_fn=log,
        )
        log(f"  → {len(fichiers)} fichier(s) .grd écrits dans {output_dir}")
        return fichiers

    def _extraire_bbox(self, type_img, sous_type, date_debut, date_fin,
                       ul, lr, pdt, duree, bandes,
                       facteur=1.0, force_integer=True,
                       output_dir=".", log_fn=None, skip_existing=False):
        os.makedirs(output_dir, exist_ok=True)
        log = log_fn or (lambda s: None)

        # Aligner les dates sur la grille du produit
        date_debut = _snap_floor(date_debut, pdt)
        date_fin   = _snap_ceil(date_fin, pdt)

        data = {
            "request": "getObsValuesByBBoxAsync",
            "typeImage": type_img,
            "sousTypeImage": sous_type,
            "dateDeb": _fmt_bdimage(date_debut),
            "dateFin": _fmt_bdimage(date_fin),
            "duree": _fmt_duree(duree),
            "pdt": _fmt_duree(pdt),
            "ul": ul,
            "lr": lr,
            "resol": str(self.resol),
            "epsg": str(self.epsg),
            "bandes": bandes,
        }

        log(f"  → Requête BDImage async : {type_img}/{sous_type} "
            f"{_fmt_bdimage(date_debut)}→{_fmt_bdimage(date_fin)} "
            f"pdt={pdt}mn ({_fmt_duree(pdt)}) duree={duree}mn ({_fmt_duree(duree)})")

        # 1. Lancement de la requête async
        resp = self._session.post(self.url, data=data, timeout=60)
        resp.raise_for_status()
        xml_bytes = _decompress(resp.content)
        uri = _parse_report_uri(xml_bytes)
        log(f"  → Requête lancée, polling URI...")

        # 2. Polling
        xml_result = self._poll_async(uri, log)

        # 3. Parse XML → écriture des .grd
        ul_coords = ul
        lr_coords = lr
        fichiers = _xml_to_grds(
            xml_bytes=xml_result,
            ul=ul_coords, lr=lr_coords,
            resol=self.resol, nodata=self.nodata,
            facteur=facteur, force_integer=force_integer,
            output_dir=output_dir, log_fn=log,
            skip_existing=skip_existing,
        )
        log(f"  → {len(fichiers)} fichier(s) .grd écrits dans {output_dir}")
        return fichiers

    def _poll_async(self, uri, log_fn):
        """Attend le résultat d'une requête BDImage asynchrone."""
        import requests.exceptions
        wait = 2.0
        t0 = time.time()
        consecutive_errors = 0
        while True:
            elapsed = time.time() - t0
            if elapsed > self.timeout_async:
                raise BdimageError(f"Timeout BDImage async après {self.timeout_async}s")
            time.sleep(wait)
            try:
                resp = self._session.post(uri, timeout=60)
                resp.raise_for_status()
            except requests.exceptions.ConnectionError as e:
                consecutive_errors += 1
                if consecutive_errors >= 5:
                    raise BdimageError(f"Connexion BDImage perdue après {consecutive_errors} tentatives : {e}")
                log_fn(f"  → Connexion perdue, nouvelle tentative dans {wait:.0f}s... ({elapsed:.0f}s)")
                wait = min(wait * 2, 30)
                continue
            consecutive_errors = 0
            xml_bytes = _decompress(resp.content)
            status, message = _parse_report_status(xml_bytes)
            if status == 0:
                return xml_bytes
            if status == 404:
                log_fn(f"  → En attente... ({elapsed:.0f}s)")
                wait = min(wait * 2, 30)
            else:
                raise BdimageError(f"Erreur BDImage (statut {status}) : {message}")


# ------------------------------------------------------------------
# Parsing XML BDImage → fichiers .grd
# ------------------------------------------------------------------

def _xml_to_grds(xml_bytes, ul, lr, resol, nodata, facteur, force_integer,
                 output_dir, log_fn, skip_existing=False):
    """Parse la réponse XML BDImage et écrit les fichiers .grd.

    Format XML attendu (simplifié) :
        <bdimage>
          <rapport>...</rapport>
          <observations>
            <image type="..." sousType="..." date="AAAAMMJJhhmm" ...>
              <bandes>
                <bande type="reel" nom="rr">
                  <valeurs zone="bbox">
                    <valeur x="X" y="Y">valeur</valeur>
                    ...
                  </valeurs>
                </bande>
              </bandes>
            </image>
          </observations>
        </bdimage>
    """
    root = ET.fromstring(xml_bytes)
    observations = root.find("observations")
    if observations is None:
        # Format prévision : <previsions><network><image>...</image></network></previsions>
        previsions = root.find("previsions")
        if previsions is not None:
            observations = ET.Element("observations")
            for network in previsions.findall("network"):
                for img in network.findall("image"):
                    observations.append(img)
    if observations is None or len(list(observations)) == 0:
        raise BdimageError("Aucune donnée dans la réponse BDImage.")

    # récupérer ul/lr depuis le rapport si disponible
    rapport = root.find("rapport")
    if rapport is not None:
        ul_req = _get_requete_param(rapport, "ul") or ul
        lr_req = _get_requete_param(rapport, "lr") or lr
    else:
        ul_req, lr_req = ul, lr

    xll = float(ul_req.split(",")[0])
    yll = float(lr_req.split(",")[1])

    fichiers = []
    for image in observations.findall("image"):
        date_str = image.attrib.get("date", "")
        filename = os.path.join(output_dir, f"{date_str}.grd")
        if skip_existing and os.path.isfile(filename):
            log_fn(f"  → {date_str}.grd déjà présent, ignoré.")
            continue

        # première bande disponible
        bandes_el = image.find("bandes")
        if bandes_el is None:
            continue
        bande_el = bandes_el.find("bande")
        if bande_el is None:
            continue
        valeurs_el = bande_el.find("valeurs")
        if valeurs_el is None:
            continue

        # lire les valeurs pixel par pixel
        grid = {}  # {y: [(x, val), ...]}
        for valeur_el in valeurs_el.findall("valeur"):
            x_str = valeur_el.attrib.get("x")
            y_str = valeur_el.attrib.get("y")
            text = valeur_el.text
            if x_str is None or y_str is None:
                continue
            x, y = int(float(x_str)), int(float(y_str))
            val = nodata if text is None else float(text) * facteur
            if y not in grid:
                grid[y] = []
            grid[y].append((x, val))

        if not grid:
            log_fn(f"  ⚠ Image {date_str} : aucune valeur, ignorée.")
            continue

        nrows = len(grid)
        ncols = max(len(row) for row in grid.values())

        with open(filename, "w") as fh:
            fh.write(ENTETE.format(
                ncols=ncols, nrows=nrows,
                xll=int(xll), yll=int(yll),
                cellsize=resol, nodata=nodata,
            ))
            for y in sorted(grid, reverse=True):
                row_vals = sorted(grid[y], key=lambda t: t[0])
                if force_integer:
                    fh.write(" ".join(str(int(round(v))) for _, v in row_vals))
                else:
                    fh.write(" ".join(f"{v:.1f}" for _, v in row_vals))
                fh.write("\n")

        fichiers.append(filename)

    return fichiers


# ------------------------------------------------------------------
# Helpers XML / HTTP
# ------------------------------------------------------------------

def _parse_report_status(xml_bytes):
    root = ET.fromstring(xml_bytes)
    rapport = root.find("rapport")
    if rapport is None:
        raise BdimageError("Réponse BDImage sans élément <rapport>")
    statut_el = rapport.find("statut")
    message_el = rapport.find("message")
    status = int(statut_el.text) if statut_el is not None else -1
    message = message_el.text if message_el is not None else ""
    return status, message


def _parse_report_uri(xml_bytes):
    root = ET.fromstring(xml_bytes)
    rapport = root.find("rapport")
    if rapport is None:
        raise BdimageError("Réponse BDImage sans élément <rapport>")
    statut_el = rapport.find("statut")
    status = int(statut_el.text) if statut_el is not None else -1
    message_el = rapport.find("message")
    message = message_el.text if message_el is not None else ""
    if status != 0:
        raise BdimageError(f"BDImage erreur statut {status} : {message}")
    uri_el = rapport.find("uri")
    if uri_el is None or not uri_el.text:
        raise BdimageError("Pas d'URI dans la réponse BDImage async")
    return uri_el.text


def _get_requete_param(rapport, nom):
    for p in rapport.findall("requete/parametre"):
        if p.attrib.get("nom") == nom:
            return p.text
    return None


def _decompress(content):
    """Décompresse gzip si nécessaire."""
    if content[:2] == b"\x1f\x8b":
        with gzip.open(io.BytesIO(content)) as gz:
            return gz.read()
    return content


def _snap_floor(dt, pdt_minutes):
    """Arrondit une datetime vers le bas sur la grille du produit (pdt en minutes)."""
    total = dt.hour * 60 + dt.minute
    snapped = (total // pdt_minutes) * pdt_minutes
    return dt.replace(hour=snapped // 60, minute=snapped % 60, second=0, microsecond=0)


def _snap_ceil(dt, pdt_minutes):
    """Arrondit une datetime vers le haut sur la grille du produit (pdt en minutes)."""
    total = dt.hour * 60 + dt.minute
    remainder = total % pdt_minutes
    if remainder == 0 and dt.second == 0 and dt.microsecond == 0:
        return dt.replace(second=0, microsecond=0)
    snapped = ((total // pdt_minutes) + 1) * pdt_minutes
    base = dt.replace(hour=0, minute=0, second=0, microsecond=0)
    return base + timedelta(minutes=snapped)


def _fmt_bdimage(dt):
    """Formate une datetime au format BDImage : AAAAMMJJhhmm."""
    return dt.strftime("%Y%m%d%H%M")


def calculer_pluie_bv_csv(grd_dir, output_csv, nodata=NODATA, log_fn=None):
    """Calcule la pluie moyenne de bassin versant à partir des fichiers .grd.

    Lit chaque fichier ESRI ASCII Grid du dossier, fait la moyenne des pixels
    non-nodata, et écrit un CSV datetime;pluie_mm.

    Retourne le nombre de pas de temps écrits.
    """
    import csv as _csv
    log = log_fn or (lambda s: None)

    grd_files = sorted(
        f for f in os.listdir(grd_dir) if f.endswith(".grd") and len(f) == 16
    )
    if not grd_files:
        raise BdimageError(f"Aucun fichier .grd trouvé dans {grd_dir}")

    rows = []
    for fname in grd_files:
        try:
            dt = datetime.strptime(fname[:12], "%Y%m%d%H%M")
        except ValueError:
            continue
        val = _grd_mean(os.path.join(grd_dir, fname), nodata)
        if val is not None:
            rows.append((dt, round(val, 2)))

    os.makedirs(os.path.dirname(os.path.abspath(output_csv)), exist_ok=True)
    with open(output_csv, "w", newline="", encoding="utf-8") as fh:
        w = _csv.writer(fh, delimiter=";")
        w.writerow(["date", "pluie_mm"])
        for dt, val in rows:
            w.writerow([dt.strftime("%d/%m/%Y %H:%M"), val])

    log(f"  {len(rows)} pas de temps pluie BV ecrits dans {output_csv}")
    return len(rows)


def _grd_mean(filepath, nodata):
    """Retourne la moyenne des pixels non-nodata d'un fichier ESRI ASCII Grid."""
    total = 0.0
    count = 0
    try:
        with open(filepath, "r") as fh:
            # Sauter les 6 lignes d'en-tête
            for _ in range(6):
                next(fh)
            for line in fh:
                for tok in line.split():
                    v = float(tok)
                    if v != nodata:
                        total += v
                        count += 1
    except Exception:
        return None
    return (total / count) * 0.1 if count > 0 else 0.0


def _fmt_duree(minutes):
    """Convertit une durée en minutes au format BDImage ddHHMM (6 chiffres min).

    Format attendu : [d*]ddHHMM — jours (2+ chiffres) + heures (2) + minutes (2).
    Exemples : 15 -> '000015', 60 -> '000100', 90 -> '000130', 1440 -> '010000'
    """
    jours = minutes // 1440
    reste = minutes % 1440
    heures = reste // 60
    mins = reste % 60
    return f"{jours:02d}{heures:02d}{mins:02d}"
