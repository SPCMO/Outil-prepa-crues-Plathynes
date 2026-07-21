# -*- coding: utf-8 -*-
"""Client SOAP PHyC — authentification et extraction des débits (Q).

PHyC expose un service WSDL/SOAP à l'adresse :
    http://services.schapi.e2.rie.gouv.fr/phycop/bdtrv21.wsdl  (v2.1, recommandée)
    http://services.schapi.e2.rie.gouv.fr/phycop/bdtr.wsdl      (v1.1, obsolète)

Nom du service zeep : WebservicesBdtr
Ports utilisés :
    AuthentificationPort  -> authentifier(cdcontact, motdepasse) -> idsession
    ObservationsHydroPublicationPort -> publierObservationsHydroPasDeTemps(...)
    SiteHydroPublicationPort -> publierSiteHydroListe(...) -> libellé station + CdBNBV
    SeuilHydroPublicationPort -> publierSeuilHydro(...) -> seuils vigilance

Syntaxe zeep pour accéder à un port nommé :
    client.bind('WebservicesBdtr', 'NomPort').methode(...)
"""

import xml.etree.ElementTree as ET
from datetime import datetime

import requests as _requests
from lxml import etree as lxml_etree
from zeep import Client as ZeepClient, Settings as ZeepSettings
from zeep.transports import Transport

WSDL_URL = "http://services.schapi.e2.rie.gouv.fr/phycop/bdtrv21.wsdl"
ZEEP_SERVICE = "WebservicesBdtr"

# Schéma SOAP encoding standard (schemas.xmlsoap.org/soap/encoding/)
# Embarqué localement car inaccessible depuis le RIE (réseau interne SCHAPI).
_SOAP_ENCODING_SCHEMA = b"""<?xml version='1.0' encoding='UTF-8'?>
<xs:schema xmlns:xs='http://www.w3.org/2001/XMLSchema'
           xmlns:tns='http://schemas.xmlsoap.org/soap/encoding/'
           targetNamespace='http://schemas.xmlsoap.org/soap/encoding/'>
  <xs:attributeGroup name='commonAttributes'>
    <xs:attribute name='id' type='xs:ID'/>
    <xs:attribute name='href' type='xs:anyURI'/>
    <xs:anyAttribute namespace='##other'/>
  </xs:attributeGroup>
  <xs:complexType name='Array' abstract='true'>
    <xs:sequence>
      <xs:any namespace='##any' minOccurs='0' maxOccurs='unbounded' processContents='lax'/>
    </xs:sequence>
    <xs:attribute ref='tns:arrayType'/>
    <xs:attribute ref='tns:offset'/>
    <xs:attributeGroup ref='tns:commonAttributes'/>
  </xs:complexType>
  <xs:element name='Array' type='tns:Array'/>
  <xs:attribute name='arrayType' type='xs:string'/>
  <xs:attribute name='offset' type='xs:string'/>
</xs:schema>"""

_LOCAL_SCHEMAS = {
    "http://schemas.xmlsoap.org/soap/encoding/": _SOAP_ENCODING_SCHEMA,
    "https://schemas.xmlsoap.org/soap/encoding/": _SOAP_ENCODING_SCHEMA,
}


class _RieTransport(Transport):
    """Transport zeep qui court-circuite les schémas W3C inaccessibles depuis le RIE."""

    def _load_remote_data(self, url):
        if url in _LOCAL_SCHEMAS:
            return _LOCAL_SCHEMAS[url]
        return super()._load_remote_data(url)


class PhycAuthError(Exception):
    pass


class PhycClient:
    """Client SOAP PHyC."""

    DT_FMT = "%Y-%m-%dT%H:%M:%S"

    def __init__(self, wsdl_url=WSDL_URL, timeout=60):
        self.wsdl_url = wsdl_url
        self.timeout = timeout
        self._idsession = None
        self._client = None
        self._service_name = None

    def _make_client(self):
        """Crée le client zeep avec le transport RIE."""
        transport = _RieTransport(timeout=self.timeout)
        settings = ZeepSettings(strict=False, xml_huge_tree=True)
        return ZeepClient(wsdl=self.wsdl_url, transport=transport, settings=settings)

    def _port(self, port_name):
        """Retourne un proxy zeep pour le port donné."""
        return self._client.bind(self._service_name, port_name)

    # ------------------------------------------------------------------
    # Authentification
    # ------------------------------------------------------------------

    def login(self, cdcontact, motdepasse):
        """Ouvre une session PHyC."""
        self._client = self._make_client()
        # Récupère le nom du service depuis le WSDL (évite de le hardcoder)
        self._service_name = list(self._client.wsdl.services.keys())[0]
        try:
            auth = self._port('AuthentificationPort').authentifier(
                cdcontact=cdcontact,
                motdepasse=str(motdepasse),
            )
            self._idsession = auth.idsession
        except Exception as e:
            raise PhycAuthError(f"Authentification PHyC échouée : {e}")

    def logout(self):
        """Ferme la session PHyC."""
        self._idsession = None
        self._client = None
        self._service_name = None

    # ------------------------------------------------------------------
    # Libellé station via SiteHydroPublicationPort
    # ------------------------------------------------------------------

    def get_libelle_station(self, code_site):
        """Tente de récupérer le libellé du site hydro via PHyC.

        Retourne:
            str : libellé, ou None si non disponible.
        """
        libelle, _ = self.get_libelle_et_bnbv(code_site)
        return libelle

    def get_libelle_et_bnbv(self, code_site):
        """Récupère le libellé et le code BNBV du site hydro via PHyC v2.1.

        Retourne:
            (libelle, code_bnbv) — l'un ou l'autre peut être None si absent.
        """
        if self._client is None or self._idsession is None:
            raise PhycAuthError("Client PHyC non connecté. Appelez login() d'abord.")

        try:
            port = self._port('SiteHydroPublicationPort')
            arr_el = lxml_etree.Element('ArrayOfStrings')
            lxml_etree.SubElement(arr_el, 'string').text = code_site
            result = port.publierSiteHydroListe(
                idsession=self._idsession,
                listecdsitehydro=arr_el,
                dtmaj=datetime(2000, 1, 1),
                stations=True,
                capteurs=False,
                roles=False,
            )
            if result and result.xmlprevcrues:
                racine = ET.fromstring(result.xmlprevcrues)
                libelle = None
                for tag in ("LbUsuelSiteHydro", "LbSiteHydro", "LbStationHydro"):
                    val = racine.findtext(f".//{tag}")
                    if val and val.strip():
                        libelle = val.strip()
                        break
                code_bnbv = racine.findtext(".//CdBNBV")
                if code_bnbv:
                    code_bnbv = code_bnbv.strip() or None
                return libelle, code_bnbv
        except Exception:
            pass

        return None, None

    # ------------------------------------------------------------------
    # Extraction des débits Q
    # ------------------------------------------------------------------

    def get_debits(self, listecdentite, date_debut, date_fin,
                   pasdetemps=15, grandeur="Q"):
        """Récupère les observations hydro au pas de temps donné.

        Appel SOAP brut (bypass zeep) car le WSDL déclare idasynchrone:xsd:int
        mais le serveur PHP attend ?array ($tabStatut). On envoie un élément
        xsi:nil='true' pour passer null au PHP sans passer par la validation zeep.

        Retourne:
            str : XML brut de la réponse (xmlprevcrues) ou None si vide.
        """
        if self._client is None or self._idsession is None:
            raise PhycAuthError("Client PHyC non connecté. Appelez login() d'abord.")

        # Construire l'enveloppe SOAP manuellement
        SOAP_ENV = "http://schemas.xmlsoap.org/soap/envelope/"
        WS_NS    = "urn:webservice"
        XSI_NS   = "http://www.w3.org/2001/XMLSchema-instance"

        env = lxml_etree.Element(
            f"{{{SOAP_ENV}}}Envelope",
            nsmap={"soapenv": SOAP_ENV, "ws": WS_NS, "xsi": XSI_NS},
        )
        body = lxml_etree.SubElement(env, f"{{{SOAP_ENV}}}Body")
        call = lxml_etree.SubElement(body, f"{{{WS_NS}}}publierObservationsHydroPasDeTemps")

        def _add(tag, text=None, **attrib):
            el = lxml_etree.SubElement(call, tag, **attrib)
            if text is not None:
                el.text = str(text)
            return el

        _add("idsession", self._idsession)

        ent_el = _add("listecdentite")
        for code in listecdentite:
            lxml_etree.SubElement(ent_el, "string").text = code

        _add("grandeur", grandeur)
        _add("pasdetemps", str(pasdetemps))
        _add("dtmesuredebut", date_debut.strftime(self.DT_FMT))
        _add("dtmesurefin",   date_fin.strftime(self.DT_FMT))
        # tabStatut côté PHP (?array) — on envoie xsi:nil pour null
        _add("idasynchrone", **{f"{{{XSI_NS}}}nil": "true"})

        soap_bytes = lxml_etree.tostring(env, xml_declaration=True, encoding="UTF-8")

        # Récupérer l'URL du endpoint depuis le WSDL zeep
        svc = self._client.wsdl.services[self._service_name]
        port = svc.ports.get("ObservationsHydroPublicationPort")
        if port:
            endpoint = port.binding_options["address"]
        else:
            # Fallback : déduire l'endpoint depuis l'URL du WSDL
            endpoint = self.wsdl_url.rsplit("/", 1)[0] + "/"

        resp = _requests.post(
            endpoint,
            data=soap_bytes,
            headers={
                "Content-Type": "text/xml; charset=utf-8",
                "SOAPAction": '"publierObservationsHydroPasDeTemps"',
            },
            timeout=120,
        )
        resp.raise_for_status()

        # Parser la réponse SOAP
        root = lxml_etree.fromstring(resp.content)
        # Chercher xmlprevcrues dans la réponse
        ns = {"s": SOAP_ENV}
        body_el = root.find("s:Body", ns)
        if body_el is None:
            body_el = root
        # Chercher le texte de xmlprevcrues n'importe où dans le Body
        for el in body_el.iter():
            if el.tag.endswith("xmlprevcrues") and el.text:
                return el.text
        return None

    # ------------------------------------------------------------------
    # Seuils de vigilance
    # ------------------------------------------------------------------

    def get_seuils_vigilance(self, code_site):
        """Récupère les seuils de vigilance actifs (NatureSeuil=22) pour un site.

        Retourne dict : {"jaune": Q_m3s, "orange": Q_m3s, "rouge": Q_m3s}
        Valeurs absentes si non disponibles pour la couleur.
        """
        if self._client is None or self._idsession is None:
            raise PhycAuthError("Client PHyC non connecte.")

        SOAP_ENV = "http://schemas.xmlsoap.org/soap/envelope/"
        WS_NS    = "urn:webservice"

        env  = lxml_etree.Element(f"{{{SOAP_ENV}}}Envelope",
                                   nsmap={"soapenv": SOAP_ENV, "ws": WS_NS})
        body = lxml_etree.SubElement(env, f"{{{SOAP_ENV}}}Body")
        call = lxml_etree.SubElement(body, f"{{{WS_NS}}}publierSeuilHydro")
        lxml_etree.SubElement(call, "idsession").text = self._idsession
        arr = lxml_etree.SubElement(call, "listecdentite")
        lxml_etree.SubElement(arr, "string").text = code_site

        soap_bytes = lxml_etree.tostring(env, xml_declaration=True, encoding="UTF-8")
        svc  = self._client.wsdl.services[self._service_name]
        port = svc.ports.get("SeuilHydroPublicationPort")
        if not port:
            raise Exception("Port SeuilHydroPublicationPort introuvable dans le WSDL.")
        endpoint = port.binding_options["address"]

        resp = _requests.post(endpoint, data=soap_bytes,
                              headers={"Content-Type": "text/xml; charset=utf-8",
                                       "SOAPAction": '"publierSeuilHydro"'},
                              timeout=60)
        resp.raise_for_status()

        root_soap = lxml_etree.fromstring(resp.content)
        xmlprev = None
        for el in root_soap.iter():
            if el.tag.endswith("xmlprevcrues") and el.text:
                xmlprev = el.text
                break
        if not xmlprev:
            return {}
        return self._parse_seuils_vigilance(xmlprev)

    # Mapping indice de gravité → clé seuil
    # 24=ZT jaune, 26=Jaune, 49=ZT orange, 51=Orange, 74=ZT rouge, 76=Rouge
    _INDICE_TO_KEY = {24: "zt_jaune", 26: "jaune",
                      49: "zt_orange", 51: "orange",
                      74: "zt_rouge",  76: "rouge"}

    @staticmethod
    def _parse_seuils_vigilance(xml_str):
        """Parse le XML publierSeuilHydro — retourne seuils actifs en m3/s.

        Clés retournées : zt_jaune, jaune, zt_orange, orange, zt_rouge, rouge
        """
        root = ET.fromstring(xml_str)
        candidats = {}  # {indice_gravite: val_m3s}  — garde la valeur active la plus basse
        for val_el in root.iter("ValeursSeuilSiteHydro"):
            if val_el.findtext("NatureSeuilSiteHydro") != "22":
                continue
            if val_el.findtext("DtDesactivationSeuilSiteHydro"):
                continue
            val_str    = val_el.findtext("ValDebitSeuilSiteHydro")
            indice_str = val_el.findtext("IndiceGraviteSeuilSiteHydro")
            if not val_str or not indice_str:
                continue
            indice  = int(indice_str)
            if indice not in PhycClient._INDICE_TO_KEY:
                continue
            val_m3s = float(val_str) / 1000.0
            if indice not in candidats or val_m3s < candidats[indice]:
                candidats[indice] = val_m3s
        return {PhycClient._INDICE_TO_KEY[i]: v for i, v in candidats.items()}

    # ------------------------------------------------------------------
    # Parsing XML réponse PHyC
    # ------------------------------------------------------------------

    @staticmethod
    def parse_series_xml(xml_str, grandeur="Q"):
        """Parse le XML PHyC et retourne les séries temporelles.

        Retourne:
            dict { code_entite (str): [(datetime, float_m3s), ...] }
        """
        if not xml_str:
            return {}

        racine = ET.fromstring(xml_str)
        donnees = racine.find("Donnees")
        if donnees is None:
            return {}
        series_el = donnees.find("Series")
        if series_el is None:
            return {}

        tag_code = "CdSiteHydro" if grandeur == "Q" else "CdStationHydro"

        result = {}
        for serie in series_el:
            grd = serie.findtext("GrdSerie", "")
            if grd != grandeur:
                continue
            code = serie.findtext(tag_code)
            if code is None:
                continue

            observations = serie.find("ObssHydro")
            if observations is None:
                continue

            points = []
            for obs in observations:
                dt_str = obs.findtext("DtObsHydro")
                res_str = obs.findtext("ResObsHydro")
                if dt_str and res_str:
                    try:
                        dt = datetime.strptime(dt_str, "%Y-%m-%dT%H:%M:%S")
                        # PHyC retourne les valeurs en L/s x 1000 -> diviser par 1000 pour m3/s
                        val = round(float(res_str) / 1000, 3)
                        points.append((dt, val))
                    except (ValueError, TypeError):
                        continue

            points.sort(key=lambda p: p[0])
            result[code] = points

        return result
