# -*- coding: utf-8 -*-
"""Diagnostic de connexion PHyC — tests progressifs."""

import socket
import traceback
import urllib.parse

import requests


def run_diagnostics(wsdl_url, idcontact, motdepasse, log):
    """Lance une série de tests PHyC et écrit les résultats via log(str).

    Tests effectués :
      1. Résolution DNS du host PHyC
      2. Accès HTTP brut au WSDL (requests)
      3. Contenu WSDL (premières lignes + imports détectés)
      4. Accès aux URL importées dans le WSDL
      5. Connexion SOAP via zeep (avec Settings strict=False)
      6. Authentification PHyC (login)
    """
    log("=" * 60)
    log("DIAGNOSTIC CONNEXION PHyC")
    log("=" * 60)
    log(f"URL WSDL cible : {wsdl_url}")
    log(f"Identifiant    : {idcontact}")
    log(f"Mot de passe   : {'*' * len(motdepasse) if motdepasse else '(vide)'}")
    log("")

    parsed = urllib.parse.urlparse(wsdl_url)
    host = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    # ------------------------------------------------------------------
    # TEST 1 — Résolution DNS
    # ------------------------------------------------------------------
    log("[ TEST 1 ] Resolution DNS du host PHyC...")
    log(f"  Host : {host}")
    try:
        ip = socket.gethostbyname(host)
        log(f"  OK — resolu : {ip}")
    except socket.gaierror as e:
        log(f"  ECHEC — impossible de resoudre {host} : {e}")
        log("  => Verifiez que vous etes connecte au RIE (VPN ou reseau interne).")
        log("  => Arret du diagnostic (les tests suivants echoueront aussi).")
        return

    # ------------------------------------------------------------------
    # TEST 2 — Connexion TCP
    # ------------------------------------------------------------------
    log(f"\n[ TEST 2 ] Connexion TCP {host}:{port}...")
    try:
        sock = socket.create_connection((host, port), timeout=10)
        sock.close()
        log(f"  OK — port {port} accessible.")
    except Exception as e:
        log(f"  ECHEC — {e}")
        log("  => Le port est bloque (firewall, proxy ?). Arret.")
        return

    # ------------------------------------------------------------------
    # TEST 3 — Téléchargement du WSDL
    # ------------------------------------------------------------------
    log(f"\n[ TEST 3 ] Telechargement du WSDL ({wsdl_url})...")
    wsdl_content = None
    try:
        resp = requests.get(wsdl_url, timeout=30)
        resp.raise_for_status()
        wsdl_content = resp.text
        log(f"  OK — {len(wsdl_content)} caracteres recus (HTTP {resp.status_code}).")
        # Premières lignes
        lines = wsdl_content.splitlines()
        log(f"  Premieres lignes du WSDL :")
        for line in lines[:8]:
            log(f"    {line}")
    except Exception as e:
        log(f"  ECHEC — {e}")
        log("  => Le WSDL n'est pas accessible. Arret.")
        return

    # ------------------------------------------------------------------
    # TEST 4 — URLs importées dans le WSDL
    # ------------------------------------------------------------------
    log(f"\n[ TEST 4 ] URLs importees / referencees dans le WSDL...")
    import re
    imports = re.findall(r'(?:schemaLocation|location|namespace)=["\']([^"\']+)["\']',
                         wsdl_content)
    imports_http = [u for u in imports if u.startswith("http")]
    if imports_http:
        for url in sorted(set(imports_http)):
            log(f"  Import detecte : {url}")
            try:
                r = requests.get(url, timeout=10)
                log(f"    -> OK (HTTP {r.status_code})")
            except Exception as e:
                log(f"    -> ECHEC : {e}")
                log(f"    => Cette URL est inaccessible depuis votre poste.")
                log(f"       zeep essaiera de la charger — c'est probablement la cause de l'erreur.")
    else:
        log("  Aucun import HTTP detecte dans le WSDL.")

    # ------------------------------------------------------------------
    # TEST 5 — Chargement WSDL par zeep
    # ------------------------------------------------------------------
    log(f"\n[ TEST 5 ] Chargement WSDL par zeep (transport RIE avec schemas locaux)...")
    zeep_client = None
    try:
        from zeep import Client as ZeepClient, Settings as ZeepSettings
        from .phyc_client import _RieTransport
        transport = _RieTransport(timeout=30)
        settings = ZeepSettings(strict=False, xml_huge_tree=True)
        zeep_client = ZeepClient(wsdl=wsdl_url, transport=transport, settings=settings)
        log("  OK — WSDL charge par zeep.")
        # Lister les services disponibles
        try:
            for svc in zeep_client.wsdl.services.values():
                log(f"  Service : {svc.name}")
                for port in svc.ports.values():
                    log(f"    Port : {port.name}")
        except Exception:
            pass
    except Exception as e:
        log(f"  ECHEC — {e}")
        log(f"  Detail complet :")
        for line in traceback.format_exc().splitlines():
            log(f"    {line}")
        log("  => Le chargement du WSDL par zeep echoue.")
        log("  => Voir TEST 4 pour les URLs bloquees.")
        return

    # ------------------------------------------------------------------
    # TEST 6 — Authentification
    # ------------------------------------------------------------------
    log(f"\n[ TEST 6 ] Authentification PHyC (cdcontact={idcontact})...")
    if not idcontact or not motdepasse:
        log("  IGNORE — identifiant ou mot de passe non renseignes.")
        return

    # Récupère le nom du service depuis le WSDL (ex: WebservicesBdtr)
    service_name = list(zeep_client.wsdl.services.keys())[0]
    log(f"  Nom du service WSDL : {service_name}")

    idsession = None
    auth_port = None
    try:
        auth_port = zeep_client.bind(service_name, 'AuthentificationPort')
        auth = auth_port.authentifier(
            cdcontact=idcontact,
            motdepasse=str(motdepasse),
        )
        idsession = auth.idsession
        log(f"  OK — Authentification reussie !")
        log(f"  idsession = {idsession}")
    except Exception as e:
        log(f"  ECHEC — {e}")
        log(f"  Detail :")
        for line in traceback.format_exc().splitlines():
            log(f"    {line}")
        log("  => Verifiez l'identifiant et le mot de passe PHyC.")

    # ------------------------------------------------------------------
    # TEST 7 — Récupération libellé site hydro via SiteHydroPublicationPort
    # ------------------------------------------------------------------
    if idsession and wsdl_url:
        # On tente avec le code site (Y+7) dérivé de l'URL ou on utilise un exemple connu
        # On dump le XML brut pour analyser la structure de réponse
        code_test = "Y0274010"  # Le Boulou — site de test connu
        log(f"\n[ TEST 7 ] Recuperation libelle site via SiteHydroPublicationPort...")
        log(f"  Code site teste : {code_test}")

        site_port = zeep_client.bind(service_name, 'SiteHydroPublicationPort')

        log(f"  Appel publierSiteHydroListe(listecdsitehydro=['{code_test}'])...")
        try:
            from lxml import etree as lxml_etree
            from datetime import datetime as _dt
            arr_el = lxml_etree.Element('ArrayOfStrings')
            lxml_etree.SubElement(arr_el, 'string').text = code_test
            result = site_port.publierSiteHydroListe(
                idsession=idsession,
                listecdsitehydro=arr_el,
                dtmaj=_dt(2000, 1, 1),
                stations=True,
                capteurs=False,
                roles=False,
            )
            xml_raw = getattr(result, 'xmlprevcrues', None)
            if xml_raw:
                log(f"  OK — XML recu ({len(xml_raw)} car.) :")
                for line in xml_raw[:3000].splitlines():
                    log(f"    {line}")
            else:
                log(f"  Reponse vide : {result!r}")
        except Exception as e:
            log(f"  ECHEC : {e}")

        # Déconnexion propre
        try:
            auth_port.deconnecter(idsession=idsession)
            log("\n  Session PHyC fermee.")
        except Exception:
            pass

    log("\n" + "=" * 60)
    log("FIN DU DIAGNOSTIC")
    log("=" * 60)
