# -*- coding: utf-8 -*-
"""
test_phyc_v2.py — Diagnostic PHyC v2.1 (bdtrv21.wsdl)

Objectif : vérifier que bdtrv21.wsdl fonctionne et expose les mêmes
ports/opérations que bdtr.wsdl (v1.1), en particulier :
  - Authentification
  - publierObservationsHydroPasDeTemps  (débits Q)
  - publierSiteHydroListe               (libellé + BNBV ?)
  - publierSeuilHydro                   (seuils de vigilance)

Usage :  python test_phyc_v2.py
"""

import sys
import io
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from lxml import etree

# Forcer UTF-8 sur la console Windows
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, r"D:\charles-eddy.piot\Documents\Perso CEP\Git-Claude IA\Outil prépa crues Plathynes")
from modules.phyc_client import PhycClient, _RieTransport
from zeep import Client as ZeepClient, Settings as ZeepSettings

# ── À RENSEIGNER ────────────────────────────────────────────────────────────
IDCONTACT  = "403"
MOTDEPASSE = "Spcmo11*"
CODE_SITE  = "Y0274010"   # code site hydro (7 ou 8 car.)

WSDL_V1  = "http://services.schapi.e2.rie.gouv.fr/phycop/bdtr.wsdl"
WSDL_V2  = "http://services.schapi.e2.rie.gouv.fr/phycop/bdtrv2.wsdl"
WSDL_V21 = "http://services.schapi.e2.rie.gouv.fr/phycop/bdtrv21.wsdl"

# URL à tester en priorité (modifiez si besoin)
WSDL_CIBLE = WSDL_V21
# ────────────────────────────────────────────────────────────────────────────

SEP  = "-" * 60
SEP2 = "=" * 60

def log(msg=""):  print(msg, flush=True)
def titre(t):     log(f"\n{SEP2}\n  {t}\n{SEP2}")
def ok(m):        log(f"  [OK]  {m}")
def err(m):       log(f"  [ERR] {m}")
def warn(m):      log(f"  [!!]  {m}")

def dump_xml(xml_raw, max_car=4000):
    if not xml_raw:
        log("  (réponse vide)")
        return
    log(f"  XML brut ({len(xml_raw)} car.) :")
    for line in xml_raw[:max_car].splitlines():
        log(f"    {line}")
    if len(xml_raw) > max_car:
        log(f"  ... (tronqué à {max_car} car.)")

def arr_el(code):
    el = etree.Element('ArrayOfStrings')
    etree.SubElement(el, 'string').text = code
    return el


# ── 1. Inventaire des ports — v1.1 vs cible ─────────────────────────────────
def inventaire_ports(wsdl_url, label):
    titre(f"Ports & opérations — {label}")
    log(f"  URL : {wsdl_url}")
    try:
        transport = _RieTransport(timeout=30)
        settings  = ZeepSettings(strict=False, xml_huge_tree=True)
        zc = ZeepClient(wsdl=wsdl_url, transport=transport, settings=settings)
        svc = list(zc.wsdl.services.keys())[0]
        log(f"  Service zeep : {svc}")
        ports = {}
        for port_name, port in zc.wsdl.services[svc].ports.items():
            ops = sorted(port.binding._operations.keys())
            ports[port_name] = ops
            log(f"  {port_name}")
            for op in ops:
                log(f"      → {op}")
        return svc, ports
    except Exception as e:
        err(f"Impossible de charger le WSDL : {e}")
        return None, {}


# ── 2. Connexion / authentification ─────────────────────────────────────────
def test_auth(wsdl_url):
    titre("Authentification")
    phyc = PhycClient(wsdl_url=wsdl_url)
    try:
        phyc.login(IDCONTACT, MOTDEPASSE)
        ok(f"Connecté — idsession = {phyc._idsession}")
        return phyc
    except Exception as e:
        err(f"Échec login : {e}")
        return None


# ── 3. publierSiteHydroListe — libellé + recherche BNBV ─────────────────────
def test_site(phyc):
    titre(f"publierSiteHydroListe — {CODE_SITE}")
    ids = phyc._idsession
    svc = phyc._service_name
    zc  = phyc._client

    for capteurs, roles in [(True, True), (False, False)]:
        log(f"\n  → stations=True, capteurs={capteurs}, roles={roles}")
        try:
            port   = zc.bind(svc, 'SiteHydroPublicationPort')
            result = port.publierSiteHydroListe(
                idsession=ids,
                listecdsitehydro=arr_el(CODE_SITE),
                dtmaj=datetime(2000, 1, 1),
                stations=True, capteurs=capteurs, roles=roles,
            )
            xml_raw = getattr(result, 'xmlprevcrues', None)
            if not xml_raw:
                warn("Réponse vide.")
                continue
            ok(f"{len(xml_raw)} caractères reçus.")

            racine = ET.fromstring(xml_raw)
            tags   = sorted({el.tag for el in racine.iter()})
            log(f"  Tags présents : {tags}")

            # Chercher BNBV / bassin versant
            log("\n  Recherche BNBV / bassin versant :")
            found = False
            for el in racine.iter():
                if any(k in el.tag.lower() for k in ('bnbv', 'bassin', 'bv', 'mn', 'mo')):
                    log(f"  *** {el.tag} = {el.text!r}")
                    found = True
            if not found:
                warn("Aucun tag BNBV/bassin détecté.")

            # Tous les champs courts (codes)
            log("\n  Champs courts (codes potentiels) :")
            for el in racine.iter():
                if el.text and el.text.strip() and len(el.text.strip()) < 40:
                    log(f"    {el.tag} = {el.text.strip()!r}")

        except Exception as e:
            err(f"Erreur : {e}")
            import traceback; traceback.print_exc()

    # Tenter aussi avec capteurs=True sur v2 qui expose parfois un champ BNBV
    log("\n  → Test avec roles=True uniquement (certaines v2 exposent BNBV via roles)")
    try:
        port   = zc.bind(svc, 'SiteHydroPublicationPort')
        result = port.publierSiteHydroListe(
            idsession=ids,
            listecdsitehydro=arr_el(CODE_SITE),
            dtmaj=datetime(2000, 1, 1),
            stations=True, capteurs=False, roles=True,
        )
        xml_raw = getattr(result, 'xmlprevcrues', None)
        if xml_raw:
            dump_xml(xml_raw, max_car=3000)
    except Exception as e:
        err(f"Erreur : {e}")


# ── 4. publierObservationsHydroPasDeTemps — débits Q ────────────────────────
def test_debits(phyc):
    titre(f"Débits Q — {CODE_SITE}")
    dt_fin   = datetime.now().replace(minute=0, second=0, microsecond=0)
    dt_debut = dt_fin - timedelta(hours=6)
    log(f"  Plage : {dt_debut} → {dt_fin}")
    try:
        xml_raw = phyc.get_debits(
            listecdentite=[CODE_SITE],
            date_debut=dt_debut,
            date_fin=dt_fin,
            pasdetemps=15,
            grandeur="Q",
        )
        if xml_raw:
            ok(f"{len(xml_raw)} caractères reçus.")
            dump_xml(xml_raw, max_car=2000)
        else:
            warn("Réponse vide (aucune donnée sur la plage ?).")
    except Exception as e:
        err(f"Erreur : {e}")
        import traceback; traceback.print_exc()


# ── 5. publierSeuilHydro — seuils de vigilance ──────────────────────────────
def test_seuils(phyc):
    titre(f"Seuils de vigilance — {CODE_SITE}")
    try:
        seuils = phyc.get_seuils_vigilance(CODE_SITE)
        if seuils:
            ok(f"Seuils reçus : {seuils}")
        else:
            warn("Aucun seuil retourné.")
    except Exception as e:
        err(f"Erreur : {e}")
        import traceback; traceback.print_exc()


# ── 6. Recherche port BassinsVersants (nouveau en v2 ?) ─────────────────────
def test_bnbv_port(phyc):
    titre("Recherche port dédié BNBV / BassinsVersants")
    svc = phyc._service_name
    zc  = phyc._client
    ids = phyc._idsession

    found = False
    for port_name, port in zc.wsdl.services[svc].ports.items():
        if any(k in port_name.lower() for k in ('bassin', 'bv', 'bnbv')):
            found = True
            log(f"  Port trouvé : {port_name}")
            ops = sorted(port.binding._operations.keys())
            log(f"  Opérations : {ops}")
            p = zc.bind(svc, port_name)
            for op_name in ops:
                log(f"\n  → Tentative {op_name}(idsession=...) :")
                try:
                    fn     = getattr(p, op_name)
                    result = fn(idsession=ids)
                    xml_raw = getattr(result, 'xmlprevcrues', None) or str(result)
                    dump_xml(str(xml_raw)[:2000])
                except Exception as e:
                    log(f"    Erreur : {e}")
    if not found:
        warn("Aucun port BNBV/BassinsVersants détecté dans ce WSDL.")


# ── Point d'entrée ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    log()
    log(SEP2)
    log("  DIAGNOSTIC PHyC — comparaison v1.1 vs v2.1")
    log(SEP2)
    log(f"  Code site testé : {CODE_SITE}")
    log(f"  WSDL cible      : {WSDL_CIBLE}")

    # Inventaire comparatif des ports
    svc_v1, ports_v1   = inventaire_ports(WSDL_V1,    "v1.1 (bdtr.wsdl)")
    svc_cib, ports_cib = inventaire_ports(WSDL_CIBLE, f"cible ({WSDL_CIBLE.split('/')[-1]})")

    # Diff ports
    if ports_v1 and ports_cib:
        titre("Comparaison ports v1.1 vs cible")
        tous_ports = sorted(set(ports_v1) | set(ports_cib))
        for p in tous_ports:
            if p in ports_v1 and p not in ports_cib:
                log(f"  DISPARU  : {p}")
            elif p not in ports_v1 and p in ports_cib:
                log(f"  NOUVEAU  : {p}")
            else:
                ops_v1  = set(ports_v1.get(p, []))
                ops_cib = set(ports_cib.get(p, []))
                if ops_v1 == ops_cib:
                    log(f"  IDENTIQUE: {p}")
                else:
                    log(f"  MODIFIE  : {p}")
                    for op in sorted(ops_v1 - ops_cib):
                        log(f"      - supprimé : {op}")
                    for op in sorted(ops_cib - ops_v1):
                        log(f"      + ajouté   : {op}")

    # Tests fonctionnels sur la version cible
    phyc = test_auth(WSDL_CIBLE)
    if phyc:
        test_site(phyc)
        test_bnbv_port(phyc)
        test_debits(phyc)
        test_seuils(phyc)
        phyc.logout()
        log(f"\n{SEP2}")
        ok("Session fermée.")
        log(SEP2)

    input("\nAppuyez sur Entrée pour fermer...")
