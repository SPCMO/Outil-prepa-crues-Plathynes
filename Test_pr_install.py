# -*- coding: utf-8 -*-
"""
Test_pr_install.py — Vérification de l'environnement Python
pour l'outil "Prépa crues Plathynes".

Usage :  python Test_pr_install.py
         (ou double-clic via Test_pr_install.bat)
"""

import sys
import subprocess
import importlib
import os
import io

# Forcer UTF-8 sur stdout (évite les erreurs d'encodage sous Windows cp1252)
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ── Constantes ─────────────────────────────────────────────────────────────
MIN_PYTHON = (3, 9)
MAX_PYTHON = (3, 13, 99)  # 3.14 non validé (trop récent)

# (nom_import, nom_pip, version_minimale_optionnelle)
REQUIRED = [
    ("tkinter",      None,           None),          # stdlib
    ("csv",          None,           None),          # stdlib
    ("xml",          None,           None),          # stdlib
    ("requests",     "requests",     "2.28"),
    ("lxml",         "lxml",         "4.9"),
    ("zeep",         "zeep",         "4.2"),
    ("matplotlib",   "matplotlib",   "3.6"),   # colormaps[] dispo depuis 3.5 ; cm.get_cmap() supprimé en 3.9 (ok, on n'utilise plus)
]

OPTIONAL = [
    ("geopandas",    "geopandas",    "0.13"),  # gen_bbox_bnbv uniquement
]

SEP  = "-" * 60
SEP2 = "=" * 60


def titre(txt):
    print(f"\n{SEP2}")
    print(f"  {txt}")
    print(SEP2)


def ok(msg):    print(f"  [OK]   {msg}")
def warn(msg):  print(f"  [!!]   {msg}")
def err(msg):   print(f"  [ERR]  {msg}")


# ── 1. Version Python ───────────────────────────────────────────────────────
def check_python():
    titre("1 / Vérification Python")
    v = sys.version_info
    vstr = f"{v.major}.{v.minor}.{v.micro}"
    print(f"  Version détectée : Python {vstr}")

    if (v.major, v.minor) < MIN_PYTHON:
        err(f"Python {vstr} trop ancien. Version minimale requise : {MIN_PYTHON[0]}.{MIN_PYTHON[1]}")
        return False
    if (v.major, v.minor) > (MAX_PYTHON[0], MAX_PYTHON[1]):
        warn(f"Python {vstr} est plus récent que la version validée "
             f"({MAX_PYTHON[0]}.{MAX_PYTHON[1]}.x). L'outil devrait fonctionner "
             f"mais n'a pas été testé sur cette version.")
        return True
    ok(f"Python {vstr} — compatible.")
    return True


# ── 2. Packages requis ──────────────────────────────────────────────────────
def check_packages(package_list, label="Requis"):
    titre(f"2 / Vérification des packages {label}")
    manquants = []
    for import_name, pip_name, ver_min in package_list:
        try:
            mod = importlib.import_module(import_name)
            ver = getattr(mod, "__version__", "?")
            ok(f"{import_name:<18} v{ver}")
        except ImportError:
            if pip_name:
                err(f"{import_name:<18} NON INSTALLÉ  (pip install {pip_name})")
                manquants.append((pip_name, ver_min))
            else:
                err(f"{import_name:<18} NON DISPONIBLE (module stdlib manquant — réinstaller Python)")
    return manquants


# ── 3. Fichiers projet ──────────────────────────────────────────────────────
def check_project_files():
    titre("3 / Vérification des fichiers du projet")
    base = os.path.dirname(os.path.abspath(__file__))
    attendus = [
        "main.py",
        os.path.join("modules", "phyc_client.py"),
        os.path.join("modules", "bdimage_client.py"),
        os.path.join("modules", "extractor.py"),
        os.path.join("modules", "config_manager.py"),
        os.path.join("modules", "csv_loader.py"),
        os.path.join("config", "bbox_bnbv.json"),
        "aide.html",
    ]
    manquants = []
    for f in attendus:
        path = os.path.join(base, f)
        if os.path.isfile(path):
            ok(f"{f}")
        else:
            err(f"{f}  — MANQUANT")
            manquants.append(f)

    # Dossier sorties (créé à la volée, juste avertissement)
    sorties = os.path.join(base, "sorties")
    if not os.path.isdir(sorties):
        warn(f"Le dossier 'sorties/' n'existe pas encore — il sera créé automatiquement au premier lancement.")
    else:
        ok("sorties/  (dossier de sortie présent)")

    return manquants


# ── 4. Proposition d'installation ──────────────────────────────────────────
def proposer_installation(manquants_requis, manquants_optionnels):
    if not manquants_requis and not manquants_optionnels:
        return

    titre("4 / Installation des packages manquants")

    tous = []
    if manquants_requis:
        print(f"\n  Packages REQUIS manquants ({len(manquants_requis)}) :")
        for pip_name, ver_min in manquants_requis:
            spec = f"{pip_name}>={ver_min}" if ver_min else pip_name
            print(f"    - {spec}")
            tous.append(spec)

    if manquants_optionnels:
        print(f"\n  Packages OPTIONNELS manquants ({len(manquants_optionnels)}) :")
        for pip_name, ver_min in manquants_optionnels:
            spec = f"{pip_name}>={ver_min}" if ver_min else pip_name
            print(f"    - {spec}  (utilisé uniquement pour gen_bbox_bnbv.py)")

    if not tous:
        print("\n  Seuls des packages optionnels manquent. Rien à installer pour le fonctionnement de base.")
        return

    print()
    reponse = input("  Voulez-vous installer les packages REQUIS manquants maintenant ? [O/n] : ").strip().lower()
    if reponse in ("", "o", "oui", "y", "yes"):
        print()
        for spec in tous:
            print(f"  >> pip install {spec}")
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", spec],
                capture_output=False,
            )
            if result.returncode == 0:
                ok(f"{spec} installé.")
            else:
                err(f"Échec de l'installation de {spec}. Lancez manuellement : pip install {spec}")
    else:
        print("\n  Installation annulée. Lancez manuellement :")
        for spec in tous:
            print(f"    pip install {spec}")


# ── 5. Bilan ────────────────────────────────────────────────────────────────
def bilan(py_ok, manquants_req, manquants_fich):
    titre("BILAN")
    if py_ok and not manquants_req and not manquants_fich:
        print("  [OK] Tout est en ordre - l'outil peut etre lance.")
        print()
        print("  Commande de lancement :")
        print("    python main.py")
        print()
        print("  Ou double-cliquez sur  Lancer_OPALE.bat")
    else:
        print("  [!!] Des problemes ont ete detectes :")
        if not py_ok:
            err("Version Python incompatible.")
        for f in manquants_fich:
            err(f"Fichier manquant : {f}")
        if manquants_req:
            err("Des packages requis ne sont pas installés.")
    print()


# ── Point d'entrée ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    print()
    print(SEP2)
    print("  TEST D'INSTALLATION - Outil prepa crues Plathynes")
    print(SEP2)

    py_ok         = check_python()
    manq_req      = check_packages(REQUIRED,  "requis")
    manq_opt      = check_packages(OPTIONAL,  "optionnels")
    manq_fich     = check_project_files()

    proposer_installation(manq_req, manq_opt)
    # Re-vérifier après installation éventuelle
    manq_req_final = check_packages(REQUIRED, "requis (après install)")
    bilan(py_ok, manq_req_final, manq_fich)

    input("  Appuyez sur Entrée pour fermer...")
