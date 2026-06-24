# -*- coding: utf-8 -*-
"""Interface principale — Outil prépa crues Plathynes."""

import csv
import os
import sys
import threading
import tkinter as tk
import webbrowser
from datetime import datetime
from tkinter import filedialog, messagebox, scrolledtext, ttk

sys.path.insert(0, os.path.dirname(__file__))

from modules.config_manager import load_config, save_config
from modules.csv_loader import load_episodes
from modules.extractor import run_extraction, ExtractionError
from modules.phyc_client import PhycClient, PhycAuthError
from modules.phyc_diag import run_diagnostics

try:
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    import matplotlib.dates as mdates
    HAS_MPL = True
except ImportError:
    HAS_MPL = False


TITRE = "Outil prépa crues Plathynes"
PDT_PLUIES_OPTIONS = {"15 minutes": 15, "30 minutes": 30, "1 heure": 60}
PDT_DEBITS_OPTIONS = {"15 minutes": 15, "30 minutes": 30, "1 heure": 60}
PDT_HU_OPTIONS = {"1 heure": 60, "Journalier (24h)": 1440}

# Palette couleurs — (fg, bg)
_C = {
    "bleu":   ("#1A5276", "#D6EAF8"),
    "vert":   ("#1D6A39", "#D5F5E3"),
    "violet": ("#4A235A", "#E8DAEF"),
    "ocre":   ("#7D6608", "#FDEBD0"),
    "teal":   ("#0E6655", "#D1F2EB"),
    "rouge":  ("#7B241C", "#FADBD8"),
    "gris":   ("#2C3E50", "#EAECEE"),
}


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(TITRE)
        self.resizable(True, True)
        self.minsize(900, 700)
        _ico = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "logo_lancer_outil.ico")
        if os.path.isfile(_ico):
            try:
                self.iconbitmap(_ico)
            except Exception:
                pass

        self.config_data = {}
        self.episodes = []
        self._extraction_thread = None
        self._visu_episodes = []

        try:
            ttk.Style().theme_use("clam")
        except Exception:
            pass

        self._build_ui()
        self._load_config()

    # ── Helpers paramétrage ─────────────────────────────────────────────────

    @property
    def _pfx_station(self):
        return self.config_data.get("parametrage", {}).get("prefixe_station", "Y")

    @property
    def _nb_digits(self):
        try:
            return int(self.config_data.get("parametrage", {}).get("nb_chiffres_station", 9))
        except (ValueError, TypeError):
            return 9

    @property
    def _pfx_bnbv(self):
        return self.config_data.get("parametrage", {}).get("prefixe_bnbv", "MO")

    # -----------------------------------------------------------------------
    # Construction de l'interface
    # -----------------------------------------------------------------------

    def _build_ui(self):
        self._logo_img = None
        self._notebook = ttk.Notebook(self)
        self._notebook.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        self.tab_config      = ttk.Frame(self._notebook)
        self.tab_episodes    = ttk.Frame(self._notebook)
        self.tab_extraction  = ttk.Frame(self._notebook)
        self.tab_visu        = ttk.Frame(self._notebook)
        self.tab_analyse     = ttk.Frame(self._notebook)
        self.tab_parametrage = tk.Frame(self._notebook, bg="#1B2631")

        self._notebook.add(self.tab_config,      text="  Configuration  ")
        self._notebook.add(self.tab_episodes,    text="  Episodes  ")
        self._notebook.add(self.tab_extraction,  text="  Extraction  ")
        self._notebook.add(self.tab_visu,        text="  Visualisation  ")
        self._notebook.add(self.tab_analyse,     text="  Analyse  ")
        self._notebook.add(self.tab_parametrage, text="  ⚙  Paramétrage  ")

        self._build_tab_config()
        self._build_tab_episodes()
        self._build_tab_extraction()
        self._build_tab_visu()
        self._build_tab_analyse()
        self._build_tab_parametrage()
        self._place_logo()

    def _place_logo(self):
        logo_path = os.path.join(os.path.dirname(__file__), "Doc BDImage", "logo_Plathynes.png")
        if not os.path.exists(logo_path):
            return
        try:
            raw = tk.PhotoImage(file=logo_path)
            self._logo_img = raw.subsample(2, 2)
            logo_lbl = tk.Label(self.tab_config, image=self._logo_img,
                                borderwidth=0, highlightthickness=0)
            logo_lbl.place(relx=1.0, rely=0.0, anchor="ne", x=-6, y=4)
            logo_lbl.lift()
        except Exception:
            pass

    # ── Helpers sections colorées ────────────────────────────────────────────

    def _make_section(self, parent, title, color_key, fill=tk.X, expand=False):
        """Crée un LabelFrame coloré avec un inner tk.Frame assorti."""
        fg, bg = _C[color_key]
        tag = f"Sec{color_key.capitalize()}"
        sty = ttk.Style()
        sty.configure(f"{tag}.TLabelframe",       background=bg, borderwidth=2)
        sty.configure(f"{tag}.TLabelframe.Label", foreground=fg,
                      font=("TkDefaultFont", 9, "bold"), background=bg)
        lf = ttk.LabelFrame(parent, text=f"  {title}", style=f"{tag}.TLabelframe")
        lf.pack(fill=fill, expand=expand, padx=12, pady=(8, 3))
        inner = tk.Frame(lf, bg=bg)
        inner.pack(fill=fill, expand=expand, padx=6, pady=6)
        return inner, bg

    def _row(self, parent, bg):
        f = tk.Frame(parent, bg=bg)
        f.pack(fill=tk.X, pady=3)
        return f

    def _lbl(self, parent, text, bg, w=22):
        tk.Label(parent, text=text, bg=bg, width=w, anchor="w",
                 font=("TkDefaultFont", 9)).pack(side=tk.LEFT)

    # ── Onglet Configuration ─────────────────────────────────────────────────

    def _build_tab_config(self):
        frm = self.tab_config

        # Section 1 — Station
        inn, bg = self._make_section(frm, "Station hydrologique", "rouge")

        r = self._row(inn, bg)
        self._lbl(r, "Code station hydrométrie :", bg)
        self._var_pfx_station_lbl = tk.StringVar(value="Y")
        tk.Label(r, textvariable=self._var_pfx_station_lbl, bg=bg,
                 font=("TkDefaultFont", 10, "bold")).pack(side=tk.LEFT)
        self.var_code_station_suffix = tk.StringVar()
        ttk.Entry(r, textvariable=self.var_code_station_suffix, width=12).pack(side=tk.LEFT, padx=(2, 4))
        self._var_pfx_station_hint = tk.StringVar(value="ex: 027401001  (→ code site Q/H : Y0274010)")
        tk.Label(r, textvariable=self._var_pfx_station_hint, fg="#777777", bg=bg,
                 font=("TkDefaultFont", 8)).pack(side=tk.LEFT)

        r = self._row(inn, bg)
        self._lbl(r, "Identifiant PHyC :", bg)
        self.var_phyc_id = tk.StringVar()
        ttk.Entry(r, textvariable=self.var_phyc_id, width=8).pack(side=tk.LEFT)
        tk.Label(r, text="   Mot de passe :", bg=bg, font=("TkDefaultFont", 9)).pack(side=tk.LEFT)
        self.var_phyc_pwd = tk.StringVar()
        ttk.Entry(r, textvariable=self.var_phyc_pwd, show="*", width=22).pack(side=tk.LEFT, padx=(4, 0))

        r = self._row(inn, bg)
        tk.Button(r, text="  ▼  Récup info PHyC  ",
                  bg="#1A5276", fg="white", activebackground="#154360", activeforeground="white",
                  relief="flat", bd=0, padx=8, pady=5,
                  font=("TkDefaultFont", 9, "bold"), cursor="hand2",
                  command=self._recup_info_phyc).pack(side=tk.LEFT)
        tk.Label(r, text="   Libellé :", bg=bg, font=("TkDefaultFont", 9)).pack(side=tk.LEFT)
        self.var_nom_station = tk.StringVar()
        ttk.Entry(r, textvariable=self.var_nom_station, width=28).pack(side=tk.LEFT, padx=(4, 0))

        self.var_phyc_status = tk.StringVar(value="")
        self.lbl_phyc_status = tk.Label(inn, textvariable=self.var_phyc_status,
                                         wraplength=580, justify=tk.LEFT, bg=bg,
                                         font=("TkDefaultFont", 8))
        self.lbl_phyc_status.pack(anchor=tk.W, padx=2, pady=(0, 2))

        # Section 2 — Bassin versant
        inn, bg = self._make_section(frm, "Bassin versant — pluies et HU", "vert")

        r = self._row(inn, bg)
        self._lbl(r, "Code BNBV :", bg)
        self._var_pfx_bnbv_lbl = tk.StringVar(value="MO")
        tk.Label(r, textvariable=self._var_pfx_bnbv_lbl, bg=bg,
                 font=("TkDefaultFont", 10, "bold")).pack(side=tk.LEFT)
        self.var_code_bnbv_suffix = tk.StringVar()
        self.var_code_bnbv_suffix.trace_add("write", self._on_bnbv_change)
        ttk.Entry(r, textvariable=self.var_code_bnbv_suffix, width=8).pack(side=tk.LEFT, padx=(2, 4))

        r = self._row(inn, bg)
        self._lbl(r, "Coin UL (X,Y L93) :", bg)
        self.var_ul = tk.StringVar()
        ttk.Entry(r, textvariable=self.var_ul, width=26).pack(side=tk.LEFT)

        r = self._row(inn, bg)
        self._lbl(r, "Coin LR (X,Y L93) :", bg)
        self.var_lr = tk.StringVar()
        ttk.Entry(r, textvariable=self.var_lr, width=26).pack(side=tk.LEFT)

        # Section 3 — URLs
        inn, bg = self._make_section(frm, "URLs de service", "violet")

        r = self._row(inn, bg)
        self._lbl(r, "URL PHyC (WSDL) :", bg)
        self.var_phyc_url = tk.StringVar()
        ttk.Entry(r, textvariable=self.var_phyc_url, width=54).pack(side=tk.LEFT, fill=tk.X, expand=True)

        r = self._row(inn, bg)
        self._lbl(r, "URL BDImage :", bg)
        self.var_bdi_url = tk.StringVar()
        ttk.Entry(r, textvariable=self.var_bdi_url, width=54).pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Section 4 — Dossier de sortie
        inn, bg = self._make_section(frm, "Dossier de sortie", "ocre")

        r = self._row(inn, bg)
        self.var_outdir = tk.StringVar()
        ttk.Entry(r, textvariable=self.var_outdir, width=52).pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Button(r, text="  Parcourir...",
                  bg="#7D6608", fg="white", activebackground="#5D4E08", activeforeground="white",
                  relief="flat", bd=0, padx=8, pady=3, cursor="hand2",
                  command=self._browse_outdir).pack(side=tk.LEFT, padx=(8, 0))

        # Section 5 — Seuils de vigilance
        inn, bg = self._make_section(frm, "Seuils de vigilance", "bleu")

        r = self._row(inn, bg)
        self._lbl(r, "Grandeur :", bg)
        self.var_seuils_grandeur = tk.StringVar(value="Q (m³/s)")
        cb_sg = ttk.Combobox(r, textvariable=self.var_seuils_grandeur,
                             values=["Q (m³/s)", "H (m)"], state="readonly", width=10)
        cb_sg.pack(side=tk.LEFT)
        tk.Label(r, text="   (bascule l'unité et le jeu de seuils affiché)", fg="#777777", bg=bg,
                 font=("TkDefaultFont", 8)).pack(side=tk.LEFT, padx=(4, 0))
        cb_sg.bind("<<ComboboxSelected>>", lambda e: self._on_seuils_grandeur_change())

        # 6 seuils : ZT (pointillé, pastel) + seuil principal (plein, prononcé)
        COULEURS_SEUIL = [
            ("zt_jaune",  "ZT Jaune :",  "#F9E79F", "#9A7D0A"),
            ("jaune",     "Jaune    :",  "#F4D03F", "#7D6608"),
            ("zt_orange", "ZT Orange:", "#FAD7A0", "#9A4A0A"),
            ("orange",    "Orange   :", "#E67E22", "#784212"),
            ("zt_rouge",  "ZT Rouge :", "#F5B7B1", "#922B21"),
            ("rouge",     "Rouge    :", "#E74C3C", "#641E16"),
        ]
        self._var_seuils = {}
        self._seuil_unit_labels = []
        # Deux colonnes : ZT à gauche, seuil principal à droite
        grid_frm = tk.Frame(inn, bg=bg)
        grid_frm.pack(anchor=tk.W, padx=4, pady=2)
        for col, (key, lbl_txt, bg_entry, fg_entry) in enumerate(COULEURS_SEUIL):
            row_i = col // 2
            col_i = (col % 2) * 3   # 3 widgets par seuil (label, entry, unit)
            tk.Label(grid_frm, text=lbl_txt, bg=bg,
                     font=("TkDefaultFont", 9, "bold"),
                     fg=fg_entry, width=11, anchor="w").grid(
                         row=row_i, column=col_i, padx=(8, 2), pady=2, sticky="w")
            var = tk.StringVar()
            self._var_seuils[key] = var
            ttk.Entry(grid_frm, textvariable=var, width=9).grid(
                row=row_i, column=col_i+1, padx=(0, 2))
            unit_lbl = tk.Label(grid_frm, text="m³/s", bg=bg,
                                font=("TkDefaultFont", 9))
            unit_lbl.grid(row=row_i, column=col_i+2, padx=(0, 12), sticky="w")
            self._seuil_unit_labels.append(unit_lbl)

        r = self._row(inn, bg)
        tk.Button(r, text="  ▼  Récupérer depuis PHyC  ",
                  bg="#7B241C", fg="white", activebackground="#641E16",
                  relief="flat", bd=0, padx=8, pady=4, cursor="hand2",
                  command=self._recup_seuils_phyc).pack(side=tk.LEFT)
        self.var_seuil_status = tk.StringVar(value="")
        tk.Label(r, textvariable=self.var_seuil_status, bg=bg,
                 fg="#555555", font=("TkDefaultFont", 8)).pack(side=tk.LEFT, padx=(10, 0))

        tk.Button(inn, text="  ✓  Appliquer les seuils à la visualisation  ",
                  bg="#922B21", fg="white", activebackground="#7B241C",
                  relief="flat", bd=0, padx=10, pady=4, cursor="hand2",
                  command=self._appliquer_seuils).pack(anchor=tk.W, padx=4, pady=(4, 6))

        bottom_row = tk.Frame(frm)
        bottom_row.pack(fill=tk.X, pady=(10, 8), padx=4)

        btn_row = tk.Frame(bottom_row)
        btn_row.pack(side=tk.LEFT)
        tk.Button(btn_row, text="  ✓   Enregistrer la configuration  ",
                  bg="#2E86C1", fg="white", activebackground="#1A5276", activeforeground="white",
                  relief="flat", bd=0, padx=16, pady=8,
                  font=("TkDefaultFont", 9, "bold"), cursor="hand2",
                  command=self._save_config).pack(side=tk.LEFT, padx=(0, 12))
        tk.Button(btn_row, text="  ℹ  Aide",
                  bg="#F0F3F4", fg="#1A5276", activebackground="#D6EAF8",
                  relief="groove", bd=1, padx=12, pady=7,
                  font=("TkDefaultFont", 9), cursor="hand2",
                  command=self._ouvrir_aide).pack(side=tk.LEFT)

        lbl_contact = tk.Label(
            bottom_row,
            text="PIOT Charles-Eddy — SPCMO",
            fg="#1A5276", bg=bottom_row.cget("bg"),
            font=("TkDefaultFont", 8, "underline"),
            cursor="hand2",
        )
        lbl_contact.pack(side=tk.RIGHT, padx=(0, 4))
        lbl_contact.bind("<Button-1>", lambda e: webbrowser.open(
            "mailto:charles-eddy.piot@developpement-durable.gouv.fr"
            "?subject=Info%20%2F%20bugg%20outil%20pr%C3%A9pa%20crues%20Plathynes"
        ))

        _ico_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "logo_lancer_outil.ico")
        if os.path.isfile(_ico_path):
            try:
                from PIL import Image, ImageTk
                _img = Image.open(_ico_path).resize((28, 28), Image.LANCZOS)
                self._logo_photo = ImageTk.PhotoImage(_img)
                tk.Label(bottom_row, image=self._logo_photo,
                         bg=bottom_row.cget("bg")).pack(side=tk.RIGHT, padx=(0, 6))
            except Exception:
                pass

    # ── Onglet Episodes ──────────────────────────────────────────────────────

    def _build_tab_episodes(self):
        frm = self.tab_episodes

        # Section — Chargement CSV
        inn, bg = self._make_section(frm, "Chargement d'un catalogue de crues (OCTAVE par ex.)", "bleu")

        r = self._row(inn, bg)
        tk.Button(r, text="  📂  Charger CSV épisodes...",
                  bg="#1A5276", fg="white", activebackground="#154360", activeforeground="white",
                  relief="flat", bd=0, padx=10, pady=5,
                  font=("TkDefaultFont", 9, "bold"), cursor="hand2",
                  command=self._load_csv).pack(side=tk.LEFT)
        self.lbl_csv = tk.Label(r, text="Aucun fichier chargé", fg="#555555", bg=bg,
                                font=("TkDefaultFont", 9, "italic"))
        self.lbl_csv.pack(side=tk.LEFT, padx=12)
        tk.Button(r, text="  ↻  Rafraîchir",
                  bg=bg, fg="#1A5276", relief="groove", cursor="hand2",
                  font=("TkDefaultFont", 9),
                  command=self._refresh_episodes_table).pack(side=tk.RIGHT, padx=4)

        r = self._row(inn, bg)
        tk.Button(r, text="Tout sélectionner", bg=bg, relief="groove",
                  cursor="hand2", command=self._select_all).pack(side=tk.LEFT)
        tk.Button(r, text="Tout désélectionner", bg=bg, relief="groove",
                  cursor="hand2", command=self._deselect_all).pack(side=tk.LEFT, padx=6)

        # Section — Ajout manuel
        inn, bg = self._make_section(frm, "Ajouter un épisode manuellement", "vert")

        r = self._row(inn, bg)
        tk.Label(r, text="Date début (JJ/MM/AAAA HH:MM) :", bg=bg,
                 font=("TkDefaultFont", 9)).pack(side=tk.LEFT)
        self.var_ep_debut = tk.StringVar()
        ttk.Entry(r, textvariable=self.var_ep_debut, width=18).pack(side=tk.LEFT, padx=(4, 16))

        tk.Label(r, text="Date fin :", bg=bg, font=("TkDefaultFont", 9)).pack(side=tk.LEFT)
        self.var_ep_fin = tk.StringVar()
        e_fin = ttk.Entry(r, textvariable=self.var_ep_fin, width=18)
        e_fin.pack(side=tk.LEFT, padx=4)
        e_fin.bind("<FocusOut>", self._calc_duree_manuelle)
        e_fin.bind("<Return>", self._calc_duree_manuelle)

        tk.Label(r, text="Durée :", bg=bg, font=("TkDefaultFont", 9)).pack(side=tk.LEFT, padx=(12, 4))
        self.var_ep_duree = tk.StringVar(value="—")
        tk.Label(r, textvariable=self.var_ep_duree, width=10, bg=bg,
                 fg="#1A5276", font=("TkDefaultFont", 9, "bold")).pack(side=tk.LEFT)

        r = self._row(inn, bg)
        tk.Button(r, text="  + Ajouter  ",
                  bg="#1D6A39", fg="white", activebackground="#154a28", activeforeground="white",
                  relief="flat", bd=0, padx=10, pady=4,
                  font=("TkDefaultFont", 9, "bold"), cursor="hand2",
                  command=self._ajouter_episode_manuel).pack(side=tk.LEFT)
        tk.Button(r, text="  🗑  Supprimer sélection",
                  bg=bg, fg="#7B241C", relief="groove", cursor="hand2",
                  command=self._supprimer_episodes_sel).pack(side=tk.LEFT, padx=(10, 0))

        # ── Tableau avec filtres ─────────────────────────────────────────────
        self._sort_col     = None
        self._sort_rev     = False
        self._filter_debut = tk.StringVar()
        self._filter_fin   = tk.StringVar()
        _VIG_LABELS   = ["Vert", "ZT Jaune", "Jaune", "ZT Orange", "Orange", "ZT Rouge", "Rouge"]
        self._vig_chk = {v: tk.BooleanVar(value=True) for v in _VIG_LABELS}

        # ── Bande de filtres (fixe, toujours visible) ─────────────────────
        fb = tk.Frame(frm, bg="#D6E4F0", pady=5,
                      highlightbackground="#8FAEC8", highlightthickness=1)
        fb.pack(fill=tk.X, padx=12, pady=(6, 0))

        tk.Label(fb, text="Date début :", bg="#D6E4F0",
                 font=("TkDefaultFont", 8)).pack(side=tk.LEFT, padx=(10, 2))
        ttk.Entry(fb, textvariable=self._filter_debut, width=15).pack(side=tk.LEFT)
        self._filter_debut.trace_add("write",
            lambda *_: self.after(150, self._refresh_episodes_table))

        tk.Label(fb, text="  Date fin :", bg="#D6E4F0",
                 font=("TkDefaultFont", 8)).pack(side=tk.LEFT, padx=(10, 2))
        ttk.Entry(fb, textvariable=self._filter_fin, width=15).pack(side=tk.LEFT)
        self._filter_fin.trace_add("write",
            lambda *_: self.after(150, self._refresh_episodes_table))

        tk.Frame(fb, width=1, bg="#8FAEC8").pack(side=tk.LEFT,
                                                  fill=tk.Y, padx=12, pady=2)

        tk.Label(fb, text="Vig. max. :", bg="#D6E4F0",
                 font=("TkDefaultFont", 8, "bold")).pack(side=tk.LEFT, padx=(0, 6))
        for v in _VIG_LABELS:
            tk.Checkbutton(fb, text=v, variable=self._vig_chk[v],
                           bg="#D6E4F0", activebackground="#D6E4F0",
                           font=("TkDefaultFont", 8),
                           command=self._refresh_episodes_table).pack(side=tk.LEFT, padx=3)

        tk.Button(fb, text="✕  Réinitialiser", bg="#D6E4F0", relief="groove",
                  cursor="hand2", font=("TkDefaultFont", 8),
                  command=self._reset_filtres).pack(side=tk.RIGHT, padx=10)

        # ── Treeview ─────────────────────────────────────────────────────────
        tree_outer = tk.Frame(frm)
        tree_outer.pack(fill=tk.BOTH, expand=True, padx=12, pady=(4, 4))
        tree_frame = tk.Frame(tree_outer)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        cols = ("#", "Date début", "Date fin", "Durée", "Vig. max.")
        self.tree = ttk.Treeview(tree_frame, columns=cols,
                                 show="headings", selectmode="extended")
        for c in cols:
            self.tree.heading(c, text=c, command=lambda col=c: self._sort_by(col))
        self.tree.column("#",          width=40,  anchor=tk.CENTER)
        self.tree.column("Date début", width=160)
        self.tree.column("Date fin",   width=160)
        self.tree.column("Durée",      width=90)
        self.tree.column("Vig. max.",  width=90,  anchor=tk.CENTER)

        self.tree.tag_configure("vig_vert",      background="#D5F5E3", foreground="#1D6A39")
        self.tree.tag_configure("vig_zt_jaune",  background="#FFFDE7", foreground="#9E8A00")
        self.tree.tag_configure("vig_jaune",     background="#FEFBC8", foreground="#7D6608")
        self.tree.tag_configure("vig_zt_orange", background="#FEF0D9", foreground="#9A5B1C")
        self.tree.tag_configure("vig_orange",    background="#FCE0B5", foreground="#784212")
        self.tree.tag_configure("vig_zt_rouge",  background="#FDE3DF", foreground="#7B241C")
        self.tree.tag_configure("vig_rouge",     background="#FAC8C3", foreground="#641E16")

        vsb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        self.lbl_count = tk.Label(frm, text="", font=("TkDefaultFont", 9), fg="#555555")
        self.lbl_count.pack(anchor=tk.W, padx=12, pady=(2, 8))

    # ── Onglet Extraction ────────────────────────────────────────────────────

    def _build_tab_extraction(self):
        frm = self.tab_extraction

        # Section Pluies
        inn, bg = self._make_section(frm, "Pluies spatialisées — BDImage", "teal")
        # Ligne Antilope
        r = self._row(inn, bg)
        self.var_pluies = tk.BooleanVar(value=True)
        tk.Checkbutton(r, text="Antilope", variable=self.var_pluies, bg=bg,
                       activebackground=bg).pack(side=tk.LEFT)
        tk.Label(r, text="Pas de temps :", bg=bg, font=("TkDefaultFont", 9)).pack(side=tk.LEFT, padx=(16, 4))
        self.var_pdt_pluies = tk.StringVar(value="1 heure")
        ttk.Combobox(r, textvariable=self.var_pdt_pluies,
                     values=list(PDT_PLUIES_OPTIONS.keys()), state="readonly", width=15).pack(side=tk.LEFT)
        # Ligne Panthère
        r2 = self._row(inn, bg)
        self.var_pluies_panthere = tk.BooleanVar(value=False)
        tk.Checkbutton(r2, text="Panthère", variable=self.var_pluies_panthere, bg=bg,
                       activebackground=bg).pack(side=tk.LEFT)
        tk.Label(r2, text="Pas de temps :", bg=bg, font=("TkDefaultFont", 9)).pack(side=tk.LEFT, padx=(16, 4))
        cb_pant = ttk.Combobox(r2, values=["1 heure"], state="disabled", width=15)
        cb_pant.set("1 heure")
        cb_pant.pack(side=tk.LEFT)
        tk.Label(r2, text="(seul pdt disponible sur BDImage)", bg=bg,
                 fg="#777777", font=("TkDefaultFont", 8, "italic")).pack(side=tk.LEFT, padx=(8, 0))

        # Section HU
        inn, bg = self._make_section(frm, "Humidité des sols HU — BDImage SIM (moyenne BV)", "vert")
        r = self._row(inn, bg)
        self.var_hu = tk.BooleanVar(value=True)
        tk.Checkbutton(r, text="Extraire", variable=self.var_hu, bg=bg,
                       activebackground=bg).pack(side=tk.LEFT)
        tk.Label(r, text="Pas de temps :", bg=bg, font=("TkDefaultFont", 9)).pack(side=tk.LEFT, padx=(16, 4))
        self.var_pdt_hu = tk.StringVar(value="1 heure")
        ttk.Combobox(r, textvariable=self.var_pdt_hu,
                     values=["1 heure", "1 jour à 6:00"], state="readonly", width=16).pack(side=tk.LEFT)
        tk.Label(r, text="Sortie : 1 fichier CSV — HU moyen par BV", bg=bg,
                 font=("TkDefaultFont", 9, "italic"), fg="#1D6A39").pack(side=tk.LEFT, padx=16)

        # Section Débits
        inn, bg = self._make_section(frm, "Débits / Hauteurs — PHyC", "rouge")
        r = self._row(inn, bg)
        self.var_debits = tk.BooleanVar(value=True)
        tk.Checkbutton(r, text="Extraire", variable=self.var_debits, bg=bg,
                       activebackground=bg).pack(side=tk.LEFT)
        tk.Label(r, text="Grandeur :", bg=bg, font=("TkDefaultFont", 9)).pack(side=tk.LEFT, padx=(16, 4))
        self.var_grandeur = tk.StringVar(value="Q")
        ttk.Combobox(r, textvariable=self.var_grandeur,
                     values=["Q", "H"], state="readonly", width=6).pack(side=tk.LEFT)
        tk.Label(r, text="   Pas de temps :", bg=bg, font=("TkDefaultFont", 9)).pack(side=tk.LEFT, padx=(12, 4))
        self.var_pdt_debits = tk.StringVar(value="15 minutes")
        ttk.Combobox(r, textvariable=self.var_pdt_debits,
                     values=list(PDT_DEBITS_OPTIONS.keys()), state="readonly", width=15).pack(side=tk.LEFT)

        # Boutons + progression
        btn_frame = tk.Frame(frm, bg="#F0F0F0")
        btn_frame.pack(fill=tk.X, padx=12, pady=(12, 4))

        self.btn_run = tk.Button(btn_frame, text="  ▶   Lancer l'extraction  ",
                                  bg="#1D6A39", fg="white",
                                  activebackground="#154a28", activeforeground="white",
                                  relief="flat", bd=0, padx=12, pady=8,
                                  font=("TkDefaultFont", 10, "bold"), cursor="hand2",
                                  command=self._run_extraction)
        self.btn_run.pack(side=tk.LEFT)

        self.btn_stop = tk.Button(btn_frame, text="  ■  Arrêter  ",
                                   bg="#922B21", fg="white",
                                   activebackground="#7B241C", activeforeground="white",
                                   relief="flat", bd=0, padx=10, pady=8,
                                   font=("TkDefaultFont", 9), cursor="hand2",
                                   state=tk.DISABLED,
                                   command=self._stop_extraction)
        self.btn_stop.pack(side=tk.LEFT, padx=8)

        self.lbl_status = tk.Label(btn_frame, text="", bg="#F0F0F0",
                                    font=("TkDefaultFont", 9))
        self.lbl_status.pack(side=tk.LEFT, padx=8)

        # Boutons Enregistrer + Aide — centrés à droite
        right_btns = tk.Frame(btn_frame, bg="#F0F0F0")
        right_btns.pack(side=tk.RIGHT)
        tk.Button(right_btns, text="  ✓   Enregistrer la configuration  ",
                  bg="#2E86C1", fg="white",
                  activebackground="#1A5276", activeforeground="white",
                  relief="flat", bd=0, padx=16, pady=8,
                  font=("TkDefaultFont", 9, "bold"), cursor="hand2",
                  command=self._save_config).pack(side=tk.LEFT, padx=(0, 8))
        tk.Button(right_btns, text="  ℹ  Aide",
                  bg="#F0F3F4", fg="#1A5276",
                  activebackground="#D6EAF8", activeforeground="#1A5276",
                  relief="groove", bd=1, padx=12, pady=7,
                  font=("TkDefaultFont", 9), cursor="hand2",
                  command=self._ouvrir_aide).pack(side=tk.LEFT)

        self.progress = ttk.Progressbar(frm, mode="determinate")
        self.progress.pack(fill=tk.X, padx=12, pady=(0, 4))

        # Journal
        inn, bg = self._make_section(frm, "Journal d'extraction", "gris", fill=tk.BOTH, expand=True)
        self.log_text = scrolledtext.ScrolledText(
            inn, height=12, state=tk.DISABLED,
            wrap=tk.WORD, font=("Consolas", 9), bg="#FDFEFE")
        self.log_text.pack(fill=tk.BOTH, expand=True)
        self.log_text.tag_config("erreur", foreground="#C0392B", font=("Consolas", 9, "bold"))
        tk.Button(inn, text="Effacer le journal", bg=bg, relief="groove", cursor="hand2",
                  command=self._clear_log).pack(anchor=tk.E, pady=(4, 0))

    # ── Onglet Visualisation ─────────────────────────────────────────────────

    def _build_tab_visu(self):
        frm = self.tab_visu

        # Panneau gauche — liste des épisodes
        left = tk.Frame(frm, bg="#EBF5FB", width=230)
        left.pack(side=tk.LEFT, fill=tk.Y)
        left.pack_propagate(False)

        tk.Label(left, text="Episodes extraits",
                 bg="#1A5276", fg="white", pady=7,
                 font=("TkDefaultFont", 9, "bold")).pack(fill=tk.X)

        self.visu_listbox = tk.Listbox(
            left, selectmode=tk.SINGLE,
            bg="#EBF5FB", relief="flat",
            font=("TkDefaultFont", 9),
            activestyle="dotbox",
            selectbackground="#1A5276",
            selectforeground="white",
            borderwidth=0, highlightthickness=0)
        self.visu_listbox.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        self.visu_listbox.bind("<<ListboxSelect>>", self._on_visu_select)

        tk.Button(left, text="↻  Rafraîchir la liste",
                  bg="#1A5276", fg="white",
                  activebackground="#154360", activeforeground="white",
                  relief="flat", bd=0, pady=6, cursor="hand2",
                  command=self._refresh_visu_list).pack(fill=tk.X, padx=6, pady=6)

        # Séparateur vertical
        ttk.Separator(frm, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y)

        # Panneau droit — barre de contrôle + graphique
        right = tk.Frame(frm, bg="white")
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Barre seuil hyétogramme
        ctrl = tk.Frame(right, bg="#EEF2F7", pady=4)
        ctrl.pack(fill=tk.X, padx=6, pady=(4, 0))
        tk.Label(ctrl, text="Seuil hyétogramme * :", bg="#EEF2F7",
                 font=("TkDefaultFont", 9)).pack(side=tk.LEFT, padx=(8, 4))
        self._visu_seuil_var = tk.StringVar(value="10")
        seuil_entry = tk.Entry(ctrl, textvariable=self._visu_seuil_var,
                               width=6, font=("TkDefaultFont", 9), justify="center")
        seuil_entry.pack(side=tk.LEFT)
        tk.Label(ctrl, text="mm / pas de temps", bg="#EEF2F7",
                 font=("TkDefaultFont", 9)).pack(side=tk.LEFT, padx=(4, 16))
        tk.Label(ctrl,
                 text="* Reconstitution pluie de BV à partir des pluies spatialisées extraites"
                      " — pour identification des épisodes à fortes intensités",
                 bg="#EEF2F7", fg="#555555",
                 font=("TkDefaultFont", 8, "italic")).pack(side=tk.LEFT)
        self._visu_seuil_var.trace_add("write",
            lambda *_: self.after(200, self._on_seuil_change))

        if HAS_MPL:
            from matplotlib.gridspec import GridSpec
            self._visu_fig = Figure(figsize=(8, 7), dpi=96)
            self._visu_fig.patch.set_facecolor("#F8F9FA")
            gs = GridSpec(2, 1, figure=self._visu_fig,
                          height_ratios=[1, 2],
                          hspace=0.28,
                          left=0.07, right=0.93,
                          top=0.97, bottom=0.06)
            # Graphique haut : hyétogramme (P) + HU
            self._visu_ax_p  = self._visu_fig.add_subplot(gs[0])
            self._visu_ax_hu = self._visu_ax_p.twinx()
            self._visu_ax_p.set_facecolor("#F8F9FA")
            # Graphique bas : débit Q
            self._visu_ax_q  = self._visu_fig.add_subplot(gs[1])
            self._visu_ax_q.set_facecolor("#F8F9FA")
            self._visu_ax_q.text(0.5, 0.5,
                                  "Sélectionnez un épisode dans la liste",
                                  ha="center", va="center",
                                  transform=self._visu_ax_q.transAxes,
                                  fontsize=12, color="#888888")
            self._visu_canvas = FigureCanvasTkAgg(self._visu_fig, master=right)
            self._visu_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
            self._visu_canvas.draw()
            self._synthese_btn_artist = None
            self._visu_canvas.mpl_connect('button_press_event', self._on_synthese_pick)
        else:
            tk.Label(right,
                     text="matplotlib n'est pas installé.\n\npip install matplotlib",
                     bg="white", font=("TkDefaultFont", 12), fg="#888888").pack(expand=True)

    # -----------------------------------------------------------------------
    # Visualisation — logique
    # -----------------------------------------------------------------------

    # Couleurs pastille par niveau (bg, fg) — cohérentes avec les tags Treeview
    _VIG_ITEM_COLORS = {
        "Rouge":     ("#FAC8C3", "#641E16"),
        "ZT Rouge":  ("#FDE3DF", "#7B241C"),
        "Orange":    ("#FCE0B5", "#784212"),
        "ZT Orange": ("#FEF0D9", "#9A5B1C"),
        "Jaune":     ("#FEFBC8", "#7D6608"),
        "ZT Jaune":  ("#FFFDE7", "#9E8A00"),
        "Vert":      ("#D5F5E3", "#1D6A39"),
    }

    def _vig_from_file(self, q_path):
        """Lit le Q max d'un fichier extrait et retourne le label de vigilance."""
        try:
            import csv as _csv
            q_vals = []
            with open(q_path, encoding="utf-8") as fh:
                for row in _csv.reader(fh, delimiter=";"):
                    if row and len(row) >= 2:
                        try:
                            q_vals.append(float(row[1]))
                        except ValueError:
                            pass
            if not q_vals:
                return "Vert"
            return self._vig_label_from_val(max(q_vals))
        except Exception:
            return "Vert"

    # ── Stats Antilope vs Panthère ──────────────────────────────────────────

    @staticmethod
    def _calc_ep_antpan_stats(p_dates, p_vals, pant_dates, pant_vals, seuil=0.0):
        """Calcule les 4 indicateurs de comparaison Ant/Pan pour un épisode.
        Retourne un dict ou None si données insuffisantes."""
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

        # 1. Écart moyen
        ecart_moyen = sum(diffs) / len(diffs)
        pct_pan_over = sum(1 for d in diffs if d > 0) / len(diffs) * 100

        # 2. Écart max 1h (|Pan - Ant| max)
        abs_diffs = [abs(d) for d in diffs]
        idx_max1h = max(range(len(abs_diffs)), key=lambda i: abs_diffs[i])
        ecart_max_1h = diffs[idx_max1h]
        ts_max_1h   = common[idx_max1h]

        # 3. Cumul 1h max Antilope → écart à ce pas de temps
        idx_ant_max = max(range(len(ant_c)), key=lambda i: ant_c[i])
        ecart_at_ant_peak = diffs[idx_ant_max]
        ts_ant_peak       = common[idx_ant_max]

        # 4. 3h consécutives max Antilope → écart sur cette fenêtre
        best_i = 0
        best_sum = -1.0
        for i in range(len(common) - 2):
            s = ant_c[i] + ant_c[i+1] + ant_c[i+2]
            if s > best_sum:
                best_sum = s
                best_i   = i
        ecart_3h      = sum(diffs[best_i:best_i+3])
        ts_3h_start   = common[best_i]
        ts_3h_end     = common[best_i + 2]

        # Cumuls et écart relatif du cumul
        sum_ant = sum(ant_c)
        sum_pan = sum(pan_d[t] for t in common)
        pct_ecart_cumul = ((sum_pan - sum_ant) / sum_ant * 100) if sum_ant > 0 else 0.0
        n_common = len(common)

        # % par rapport à la valeur Antilope au pas de temps concerné
        mean_ant = sum_ant / n_common if n_common > 0 else 1.0
        def _pct(ecart, ref):
            return (ecart / ref * 100) if ref and ref != 0 else None

        pct_em  = _pct(ecart_moyen,       mean_ant)
        pct_e1h = _pct(ecart_max_1h,      ant_c[idx_max1h])
        pct_ep  = _pct(ecart_at_ant_peak, ant_c[idx_ant_max])
        sum_ant_3h = sum(ant_c[best_i:best_i+3])
        pct_e3h = _pct(ecart_3h,          sum_ant_3h) if sum_ant_3h else None

        # Écart moyen sur les pas de forte intensité Antilope (> seuil)
        forte_idx = [i for i, a in enumerate(ant_c) if a > seuil]
        if forte_idx:
            ecart_forte   = sum(diffs[i] for i in forte_idx) / len(forte_idx)
            mean_ant_forte = sum(ant_c[i] for i in forte_idx) / len(forte_idx)
            pct_ef        = _pct(ecart_forte, mean_ant_forte)
        else:
            ecart_forte = None
            pct_ef      = None

        return {
            "ecart_moyen":       ecart_moyen,
            "pct_ecart_moyen":   pct_em,
            "pct_pan_over":      pct_pan_over,
            "n_common":          n_common,
            "pct_ecart_cumul":   pct_ecart_cumul,
            "ecart_forte":        ecart_forte,
            "pct_ecart_forte":    pct_ef,
            "seuil":              seuil,
            "ecart_max_1h":       ecart_max_1h,
            "pct_ecart_max_1h":   pct_e1h,
            "ts_max_1h":          ts_max_1h,
            "ecart_at_ant_peak":  ecart_at_ant_peak,
            "pct_ecart_at_peak":  pct_ep,
            "ts_ant_peak":        ts_ant_peak,
            "ecart_3h":           ecart_3h,
            "pct_ecart_3h":       pct_e3h,
            "ts_3h_start":        ts_3h_start,
            "ts_3h_end":          ts_3h_end,
        }

    def _get_global_antpan_max(self, seuil=0.0):
        """Retourne les maxima globaux (en valeur absolue) sur tous les épisodes.
        Cache invalidé si le seuil change."""
        cache = getattr(self, "_antpan_global_max", None)
        if cache is not None and cache.get("_seuil_key") == round(seuil, 2):
            return cache

        max_em  = 0.0   # |écart moyen|
        max_e1h = 0.0   # |écart max 1h|
        max_ep  = 0.0   # |écart au pic Ant|
        max_e3h = 0.0   # |écart 3h consécutives|
        max_ef  = 0.0   # |écart fortes intensités|

        def _read_bv(path):
            pairs = []
            try:
                with open(path, encoding="utf-8") as f:
                    reader = csv.reader(f, delimiter=";")
                    next(reader, None)
                    for row in reader:
                        if len(row) >= 2:
                            try:
                                pairs.append((
                                    datetime.strptime(row[0].strip(), "%d/%m/%Y %H:%M"),
                                    float(row[1].strip())))
                            except (ValueError, IndexError):
                                pass
            except Exception:
                pass
            pairs.sort(key=lambda x: x[0])
            return [r[0] for r in pairs], [r[1] for r in pairs]

        for ep in self._visu_episodes:
            if not (ep.get("p_path") and ep.get("pant_path")):
                continue
            if not (os.path.exists(ep["p_path"]) and os.path.exists(ep["pant_path"])):
                continue
            try:
                pd_, pv_ = _read_bv(ep["p_path"])
                pp_, ppv = _read_bv(ep["pant_path"])
                s = self._calc_ep_antpan_stats(pd_, pv_, pp_, ppv, seuil)
                if s is None:
                    continue
                max_em  = max(max_em,  abs(s["ecart_moyen"]))
                max_e1h = max(max_e1h, abs(s["ecart_max_1h"]))
                max_ep  = max(max_ep,  abs(s["ecart_at_ant_peak"]))
                max_e3h = max(max_e3h, abs(s["ecart_3h"]))
                if s["ecart_forte"] is not None:
                    max_ef = max(max_ef, abs(s["ecart_forte"]))
            except Exception:
                continue

        self._antpan_global_max = {
            "ecart_moyen":       max_em  or 1.0,
            "ecart_max_1h":      max_e1h or 1.0,
            "ecart_at_ant_peak": max_ep  or 1.0,
            "ecart_3h":          max_e3h or 1.0,
            "ecart_forte":       max_ef  or 1.0,
            "_seuil_key":        round(seuil, 2),
        }
        return self._antpan_global_max

    def _refresh_visu_list(self):
        """Scanne le dossier de sortie et remplit la liste des épisodes extraits."""
        self.visu_listbox.delete(0, tk.END)
        self._visu_episodes.clear()
        self._antpan_global_max = None   # invalide le cache global

        debits_dir, hu_dir, pluies_dir, bv_dir = self._get_out_dirs()

        def _parse_key(key):
            """Extrait (datetime, label) depuis 'DD_MM_YYYY_Station'."""
            parts = key.split("_")
            try:
                dt = datetime.strptime(f"{parts[0]}/{parts[1]}/{parts[2]}", "%d/%m/%Y")
                station = " ".join(parts[3:]) if len(parts) > 3 else ""
                return dt, f"{dt.strftime('%d/%m/%Y')} — {station}"
            except (ValueError, IndexError):
                return datetime.min, key

        # Construire un dict d'épisodes indexé par clé "DD_MM_YYYY_Station"
        eps = {}  # key → ep dict

        def _get_ep(key):
            if key not in eps:
                dt, label = _parse_key(key)
                eps[key] = {"label": label, "_dt": dt,
                            "q_path": None, "hu_path": None,
                            "p_path": None, "pant_path": None}
            return eps[key]

        # Scan Debits/ — fichiers Q-Ep_*.txt (pilotent débit + HU)
        if os.path.isdir(debits_dir):
            for fname in os.listdir(debits_dir):
                if not (fname.startswith("Q-Ep_") and fname.endswith(".txt")):
                    continue
                key = fname[5:-4]  # DD_MM_YYYY_Station
                ep  = _get_ep(key)
                ep["q_path"]  = os.path.join(debits_dir, fname)
                hu_fname = fname.replace("Q-Ep_", "HU-Ep_").replace(".txt", ".csv")
                hu_path  = os.path.join(hu_dir, hu_fname)
                ep["hu_path"] = hu_path if os.path.exists(hu_path) else None

        # Scan Pluies temps moy BV pour graph/ — AntJ1_BV et Pant_BV
        if os.path.isdir(bv_dir):
            for fname in os.listdir(bv_dir):
                if fname.startswith("AntJ1_BV-Ep_") and fname.endswith(".csv"):
                    key = fname[len("AntJ1_BV-Ep_"):-4]
                    _get_ep(key)["p_path"] = os.path.join(bv_dir, fname)
                elif fname.startswith("Pant_BV-Ep_") and fname.endswith(".csv"):
                    key = fname[len("Pant_BV-Ep_"):-4]
                    _get_ep(key)["pant_path"] = os.path.join(bv_dir, fname)

        # Générer AntJ1_BV à la volée si .grd présent mais CSV absent
        for key, ep in eps.items():
            if ep["p_path"] is None:
                p_path = os.path.join(bv_dir, f"AntJ1_BV-Ep_{key}.csv")
                for _pfx in ("AntJ1-Ep_", "Pluie-Ep_"):
                    grd_dir = os.path.join(pluies_dir, f"{_pfx}{key}")
                    if os.path.isdir(grd_dir):
                        try:
                            os.makedirs(bv_dir, exist_ok=True)
                            from modules.bdimage_client import calculer_pluie_bv_csv
                            calculer_pluie_bv_csv(grd_dir, p_path)
                            ep["p_path"] = p_path
                        except Exception:
                            pass
                        break

        # Trier par date décroissante
        sorted_eps = sorted(eps.values(), key=lambda e: e["_dt"], reverse=True)
        for ep in sorted_eps:
            self._visu_episodes.append(ep)
            parts_marker = []
            if ep["q_path"]:    parts_marker.append("Q")
            if ep["hu_path"]:   parts_marker.append("HU")
            if ep["p_path"]:    parts_marker.append("Ant")
            if ep["pant_path"]: parts_marker.append("Pan")
            marker = "+".join(parts_marker) if parts_marker else "?"
            vig    = self._vig_from_file(ep["q_path"]) if ep["q_path"] else "vig_vert"
            bg, fg = self._VIG_ITEM_COLORS.get(vig, ("#EBF5FB", "#1A5276"))
            idx = self.visu_listbox.size()
            self.visu_listbox.insert(tk.END, f"●  [{marker}]  {ep['label']}")
            self.visu_listbox.itemconfig(idx, bg=bg, fg=fg,
                                         selectbackground="#1A5276",
                                         selectforeground="white")

    def _on_visu_select(self, _event=None):
        sel = self.visu_listbox.curselection()
        if not sel or not HAS_MPL:
            return
        idx = sel[0]
        if idx < len(self._visu_episodes):
            self._visu_current_ep = self._visu_episodes[idx]
            self._plot_episode(self._visu_current_ep)

    def _on_seuil_change(self):
        ep = getattr(self, "_visu_current_ep", None)
        if ep and HAS_MPL:
            self._plot_episode(ep)

    def _plot_episode(self, ep):
        self._visu_ax_p.cla()
        self._visu_ax_hu.cla()
        self._visu_ax_q.cla()

        C_Q  = "#1A5276"
        C_HU = "#C0392B"
        C_P  = "#1F618D"   # bleu foncé pluie Antilope
        C_P_EXCESS = "#7D3C98"  # violet dépassement seuil

        def _read_csv(path, has_header=True):
            pairs = []
            try:
                with open(path, encoding="utf-8") as f:
                    reader = csv.reader(f, delimiter=";")
                    if has_header:
                        next(reader, None)
                    for row in reader:
                        if len(row) >= 2:
                            try:
                                pairs.append((
                                    datetime.strptime(row[0].strip(), "%d/%m/%Y %H:%M"),
                                    float(row[1].strip())))
                            except (ValueError, IndexError):
                                pass
            except Exception:
                pass
            pairs.sort(key=lambda x: x[0])
            return [r[0] for r in pairs], [r[1] for r in pairs]

        q_dates,    q_vals    = (_read_csv(ep["q_path"], has_header=False)
                                  if ep.get("q_path") and os.path.exists(ep["q_path"]) else ([], []))
        hu_dates,   hu_vals   = (_read_csv(ep["hu_path"])
                                  if ep.get("hu_path") and os.path.exists(ep["hu_path"]) else ([], []))
        p_dates,    p_vals    = (_read_csv(ep["p_path"])
                                  if ep.get("p_path")  and os.path.exists(ep["p_path"])  else ([], []))
        pant_dates, pant_vals = (_read_csv(ep["pant_path"])
                                  if ep.get("pant_path") and os.path.exists(ep["pant_path"]) else ([], []))

        # Seuil hyétogramme
        try:
            seuil = float(self._visu_seuil_var.get())
        except ValueError:
            seuil = 40.0

        # ── Graphique haut : hyétogramme inversé (barres vers le bas) + HU ────────
        C_PANT = "#CC5500"  # orange foncé Panthère

        from datetime import timedelta as _td

        # Calcul de l'échelle Y globale (max Antilope + Panthère)
        all_p_max = max((max(p_vals) if p_vals else 0),
                        (max(pant_vals) if pant_vals else 0))
        y_bottom = max(all_p_max, 5) * 1.15

        # ── Panthère en premier (arrière-plan, zorder bas)
        pant_handles, pant_labels = [], []
        if pant_dates:
            bar_w_pant = (pant_dates[1] - pant_dates[0]) * 0.85 if len(pant_dates) >= 2 else _td(hours=1)
            bp = self._visu_ax_p.bar(pant_dates, pant_vals, width=bar_w_pant,
                                      color=C_PANT, alpha=0.25, align="center",
                                      edgecolor=C_PANT, linewidth=1.4,
                                      label="Panthère BV (mm)", zorder=1)
            for patch in bp:
                patch.set_linestyle("--")
            pant_handles.append(bp)
            pant_labels.append("Panthère BV (mm)")

        # ── Antilope par-dessus (zorder élevé, alpha légèrement augmenté)
        ant_handles, ant_labels = [], []
        if p_dates:
            bar_w = (p_dates[1] - p_dates[0]) * 0.8 if len(p_dates) >= 2 else _td(hours=1)
            base_vals = [min(v, seuil) for v in p_vals]
            b1 = self._visu_ax_p.bar(p_dates, base_vals, width=bar_w,
                                      color=C_P, alpha=0.70, align="center",
                                      zorder=3, label=f"Antilope BV ≤ {seuil:.0f} mm")
            ant_handles.append(b1)
            ant_labels.append(f"Antilope BV ≤ {seuil:.0f} mm")
            excess_vals = [max(v - seuil, 0) for v in p_vals]
            if any(v > 0 for v in excess_vals):
                b2 = self._visu_ax_p.bar(p_dates, excess_vals, width=bar_w,
                                          bottom=base_vals,
                                          color=C_P_EXCESS, alpha=0.82, align="center",
                                          zorder=3, label=f"Antilope BV > {seuil:.0f} mm")
                ant_handles.append(b2)
                ant_labels.append(f"Antilope BV > {seuil:.0f} mm")
            self._visu_ax_p.axhline(seuil, color=C_P_EXCESS, linewidth=0.9,
                                     linestyle="--", alpha=0.6, zorder=4)

        if p_dates or pant_dates:
            self._visu_ax_p.set_ylim(y_bottom, 0)
        self._visu_ax_p.set_ylabel("Pluie BV (mm)", color=C_P, fontsize=9)
        self._visu_ax_p.tick_params(axis="y", labelcolor=C_P)
        self._visu_ax_p.set_title(f"Episode : {ep['label']}", fontsize=10, pad=6)
        self._visu_ax_p.grid(True, alpha=0.25, linestyle="--", color="#AAAAAA")
        self._visu_ax_p.set_facecolor("#F8F9FA")

        if hu_dates:
            self._visu_ax_hu.plot(hu_dates, hu_vals, color=C_HU, linewidth=1.5,
                                   linestyle="--", label="HU moyen (%)")
            hu_min_v = min(hu_vals)
            hu_max_v = max(hu_vals)
            hu_span  = max(hu_max_v - hu_min_v, 1)
            self._visu_ax_hu.set_ylim(
                max(0, hu_min_v - hu_span * 0.5),
                min(100, hu_max_v + hu_span * 0.5),
            )

            def _annot_hu(ax, dt, val, label_top, above=True):
                """Annotation en deux lignes : étiquette (petite) + valeur (normale).
                above=True  : étiquette au-dessus du point, valeur encore au-dessus
                above=False : étiquette en-dessous du point, valeur encore en-dessous
                """
                ax.plot(dt, val, "o", color=C_HU, markersize=5, zorder=5)
                if above:
                    y_lbl, y_val = 16, 6
                else:
                    y_lbl, y_val = -6, -16
                ax.annotate(label_top,
                            xy=(dt, val), xytext=(6, y_lbl),
                            textcoords="offset points",
                            fontsize=7, color=C_HU, fontstyle="italic",
                            bbox=dict(boxstyle="round,pad=0.15",
                                      fc="white", ec=C_HU, alpha=0.0, lw=0))
                ax.annotate(f"{val:.1f} %",
                            xy=(dt, val), xytext=(6, y_val),
                            textcoords="offset points",
                            fontsize=8.5, color=C_HU, fontweight="bold",
                            bbox=dict(boxstyle="round,pad=0.2",
                                      fc="white", ec=C_HU, alpha=0.85))

            # HU début — annotation au-dessus du point
            _annot_hu(self._visu_ax_hu, hu_dates[0], hu_vals[0], "HU début", above=True)

            # HU 6h — premier pas de temps à 06:00 exact (ou >= 06:00 si pas de 6h pile),
            # sur le même jour ou le lendemain si l'épisode commence après 6h.
            # On cherche le premier index dont l'heure == 6h ; si l'épisode démarre déjà
            # à ou après 6h on cherche le 6h du jour suivant.
            debut_dt = hu_dates[0]
            if debut_dt.hour < 6:
                # 6h est ce jour-là
                hu_6h_idx = next(
                    (i for i, d in enumerate(hu_dates) if d.hour >= 6), None)
            else:
                # Épisode commence >= 6h : chercher le prochain jour à 6h
                from datetime import timedelta as _td2
                lendemain_6h = (debut_dt + _td2(days=1)).replace(
                    hour=6, minute=0, second=0, microsecond=0)
                hu_6h_idx = next(
                    (i for i, d in enumerate(hu_dates) if d >= lendemain_6h), None)
            if hu_6h_idx is not None and hu_6h_idx != 0:
                _annot_hu(self._visu_ax_hu,
                          hu_dates[hu_6h_idx], hu_vals[hu_6h_idx],
                          "HU 6h", above=False)
        self._visu_ax_hu.set_ylabel("HU moyen (%)", color=C_HU, fontsize=9,
                                     labelpad=6)
        self._visu_ax_hu.yaxis.set_label_position("right")
        self._visu_ax_hu.tick_params(axis="y", labelcolor=C_HU)

        # Légende : Antilope inf / sup → Panthère → HU moyen
        # Cumuls intégrés directement dans les labels (pas de phantom entries)
        _sum_ant  = round(sum(p_vals))    if p_vals    else None
        _sum_pant = round(sum(pant_vals)) if pant_vals else None

        h_hu, l_hu = self._visu_ax_hu.get_legend_handles_labels()

        # Label Antilope inf : on y colle le cumul AJ1 directement
        _cum_ant_sfx = (f"      cumul AJ1 : {_sum_ant} mm" if _sum_ant is not None else "")
        # Label Panthère : cumul Pan. sur la même ligne, précédé d'un tiret
        _cum_pan_sfx = (f"  -  cumul Pan. : {_sum_pant} mm" if _sum_pant is not None else "")

        all_h, all_l = [], []
        if ant_handles:
            # 1ère entrée Antilope (inf ≤ seuil) : label + cumul AJ1
            all_h.append(ant_handles[0])
            all_l.append(ant_labels[0] + _cum_ant_sfx)
            # 2ème entrée Antilope (sup > seuil) si présente
            if len(ant_handles) > 1:
                all_h.append(ant_handles[1])
                all_l.append(ant_labels[1])
        for ph, pl in zip(pant_handles, pant_labels):
            all_h.append(ph)
            all_l.append(pl + _cum_pan_sfx)
        all_h += h_hu;  all_l += l_hu

        if all_h:
            self._visu_ax_p.legend(all_h, all_l, loc="upper right", fontsize=8,
                                    handlelength=1.5)

        # ── Encart stats Ant. vs Pan. (bas-droite) ────────────────────────────
        if p_dates and pant_dates:
            try:
                self._draw_antpan_stats_panel(
                    self._visu_ax_p, p_dates, p_vals, pant_dates, pant_vals,
                    C_P, C_PANT, seuil)
            except Exception:
                pass

        # ── Graphique bas : débit Q ou H ─────────────────────────────────────
        grandeur_ep = ep.get("grandeur", self.config_data.get("extraction", {}).get("grandeur", "Q"))
        if grandeur_ep == "H":
            seuils = self.config_data.get("seuils_h", {})
            unite_q = "m"
        else:
            seuils = self.config_data.get("seuils_q",
                     self.config_data.get("seuils", {}))
            unite_q = "m³/s"

        def _s(key):
            try: return float(seuils[key]) if key in seuils else None
            except (ValueError, TypeError): return None

        # Plage Y du graphique Q (pour masquer les labels hors zone)
        y_max = (max(q_vals) * 1.20) if q_vals else None

        # Zones de fond (spans verticaux infinis — l'échelle Y sera calée sur Q max)
        BIG = 1e9   # hauteur "infinie" pour axhspan
        # ZT : pointillé, couleur très pastel + label si dans la plage visible
        for lo_key, hi_key, face, line_c, label_c, lbl in [
            ("zt_jaune",  "jaune",  "#FEFDE7", "#D4AC0D", "#9A7D0A", "ZT Jaune"),
            ("zt_orange", "orange", "#FEF0E7", "#CA6F1E", "#784212", "ZT Orange"),
            ("zt_rouge",  None,     "#FEF0E7", "#C0392B", "#641E16", "ZT Rouge"),
        ]:
            lo = _s(lo_key)
            hi = _s(hi_key) if hi_key else BIG
            if lo is not None:
                self._visu_ax_q.axhspan(lo, hi if hi else BIG,
                    color=face, alpha=0.35, zorder=0)
                self._visu_ax_q.axhline(lo, color=line_c, lw=0.9, ls="--",
                    alpha=0.65, zorder=1)
                if y_max is not None and lo <= y_max:
                    self._visu_ax_q.text(0.002, lo,
                        f" {lbl} {lo:.0f} {unite_q}",
                        va="bottom", fontsize=7, color=label_c,
                        transform=self._visu_ax_q.get_yaxis_transform(),
                        zorder=2)
        # Seuils principaux : trait plein, couleur plus prononcée + label si dans la plage
        for key, face, line_c, label_c, lbl in [
            ("jaune",  "#FEFBC8", "#D4AC0D", "#9A7D0A", "Jaune"),
            ("orange", "#FCE0B5", "#CA6F1E", "#784212", "Orange"),
            ("rouge",  "#FAC8C3", "#C0392B", "#641E16", "Rouge"),
        ]:
            val = _s(key)
            if val is not None:
                self._visu_ax_q.axhspan(val, BIG, color=face, alpha=0.45, zorder=0)
                self._visu_ax_q.axhline(val, color=line_c, lw=1.4, ls="-",
                    alpha=0.9, zorder=1)
                if y_max is not None and val <= y_max:
                    self._visu_ax_q.text(0.002, val,
                        f" {lbl} {val:.0f} {unite_q}",
                        va="bottom", fontsize=7, color=label_c,
                        transform=self._visu_ax_q.get_yaxis_transform(),
                        zorder=2)

        # Courbe Q — tracée après les spans pour rester visible
        if q_dates:
            self._visu_ax_q.plot(q_dates, q_vals, color=C_Q, linewidth=1.8,
                                  label="Q (m³/s)", zorder=4)
            self._visu_ax_q.fill_between(q_dates, q_vals, alpha=0.12, color=C_Q, zorder=3)
            # Échelle Y basée uniquement sur les données Q
            q_max_val = max(q_vals)
            self._visu_ax_q.set_ylim(0, q_max_val * 1.20)
            # Forcer la plage x sur les données Q pour éviter le repli sur epoch
            self._visu_ax_q.set_xlim(q_dates[0], q_dates[-1])
            # Annotation Q début — étiquette au-dessus, valeur en-dessous de l'étiquette
            self._visu_ax_q.plot(q_dates[0], q_vals[0], "o", color=C_Q,
                                  markersize=5, zorder=5)
            self._visu_ax_q.annotate("Q début",
                xy=(q_dates[0], q_vals[0]), xytext=(6, 26),
                textcoords="offset points",
                fontsize=7, color=C_Q, fontstyle="italic",
                bbox=dict(boxstyle="round,pad=0.15", fc="white", ec=C_Q,
                          alpha=0.0, lw=0))
            self._visu_ax_q.annotate(f"{q_vals[0]:.1f} $m^3$/s",
                xy=(q_dates[0], q_vals[0]), xytext=(6, 10),
                textcoords="offset points",
                fontsize=8.5, color=C_Q, fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.2", fc="white",
                          ec=C_Q, alpha=0.85))
            # Annotation Q max
            q_max_val = max(q_vals)
            q_max_idx = q_vals.index(q_max_val)
            q_max_dt  = q_dates[q_max_idx]
            self._visu_ax_q.plot(q_max_dt, q_max_val, "o", color=C_Q,
                                  markersize=5, zorder=5)
            self._visu_ax_q.annotate("Q max",
                xy=(q_max_dt, q_max_val), xytext=(6, 34),
                textcoords="offset points",
                fontsize=7, color=C_Q, fontstyle="italic",
                bbox=dict(boxstyle="round,pad=0.15", fc="white", ec=C_Q,
                          alpha=0.0, lw=0))
            self._visu_ax_q.annotate(
                f"{q_max_val:.1f} $m^3$/s\n{q_max_dt.strftime('%d/%m %H:%M')}",
                xy=(q_max_dt, q_max_val), xytext=(6, 10),
                textcoords="offset points",
                fontsize=8.5, color=C_Q, fontweight="bold",
                linespacing=1.3,
                bbox=dict(boxstyle="round,pad=0.2", fc="white",
                          ec=C_Q, alpha=0.85))

        ylabel_q = f"Hauteur H ({unite_q})" if grandeur_ep == "H" else f"Débit Q ({unite_q})"
        self._visu_ax_q.set_ylabel(ylabel_q, color=C_Q, fontsize=9)
        self._visu_ax_q.tick_params(axis="y", labelcolor=C_Q)
        self._visu_ax_q.grid(True, alpha=0.25, linestyle="--", color="#AAAAAA", zorder=1)
        self._visu_ax_q.set_facecolor("#F8F9FA")

        h3, l3 = self._visu_ax_q.get_legend_handles_labels()
        if h3:
            self._visu_ax_q.legend(h3, l3, loc="upper right", fontsize=8)

        # ── Synchronisation et formatage de l'axe X (identique sur les 2 graphiques) ─
        all_dates = sorted(
            [d for d in q_dates] +
            [d for d in p_dates] +
            [d for d in hu_dates]
        )
        if all_dates:
            from datetime import timedelta as _td_x
            x_min, x_max = all_dates[0], all_dates[-1]
            span_h = (x_max - x_min).total_seconds() / 3600
            # Choisir le pas de graduations selon la durée totale
            if span_h <= 24:
                major_loc = mdates.HourLocator(byhour=range(0, 24, 3))   # toutes les 3h
            elif span_h <= 72:
                major_loc = mdates.HourLocator(byhour=range(0, 24, 6))   # toutes les 6h
            elif span_h <= 168:
                major_loc = mdates.HourLocator(byhour=[0, 12])           # 2×/jour
            else:
                major_loc = mdates.DayLocator()                           # 1×/jour
            fmt = mdates.DateFormatter("%d/%m\n%H:%M")
            marge = _td_x(hours=max(1, span_h * 0.02))
            for ax in (self._visu_ax_p, self._visu_ax_q):
                ax.set_xlim(x_min - marge, x_max + marge)
                ax.xaxis.set_major_locator(major_loc)
                ax.xaxis.set_major_formatter(fmt)
                ax.tick_params(axis="x", labelsize=7)

        self._visu_canvas.draw()

    # ── Encart stats Antilope vs Panthère ───────────────────────────────────

    def _draw_antpan_stats_panel(self, ax, p_dates, p_vals,
                                  pant_dates, pant_vals, c_ant, c_pant, seuil=0.0):
        """Dessine l'encart compact de comparaison Ant/Pan en bas-droite."""
        import matplotlib.patches as mpatches

        s = self._calc_ep_antpan_stats(p_dates, p_vals, pant_dates, pant_vals, seuil)
        if s is None:
            return
        gmax = self._get_global_antpan_max(seuil)

        C_ANT = c_ant
        C_PAN = c_pant

        def color_for(val):
            return C_PAN if val > 0 else C_ANT

        def fmt_val(val, pct=None):
            v = f"{'+'if val>0 else ''}{val:.1f} mm"
            if pct is not None:
                v += f"  / {'+'if pct>0 else ''}{pct:.0f}%"
            return v

        def fmt_ts(ts):
            return ts.strftime("%d/%m %Hh")

        def bar_frac(val, ref_key):
            ref = gmax.get(ref_key, 1.0)
            return min(abs(val) / ref, 1.0) if ref > 0 else 0.0

        # ── Dimensions de l'encart — collé en bas-droite
        w, h = 0.30, 0.32
        x0   = 1.0 - w - 0.005
        y0   = 0.01

        # Fond blanc semi-transparent
        bg = mpatches.FancyBboxPatch(
            (x0, y0), w, h, boxstyle="round,pad=0.006",
            transform=ax.transAxes, clip_on=False,
            facecolor="white", edgecolor="#BBBBBB",
            linewidth=0.7, alpha=0.90, zorder=9)
        ax.add_patch(bg)

        # ── En-tête
        hdr_h = 0.038
        ax.text(x0 + w / 2, y0 + h - hdr_h / 2,
                "Antilope vs Panthère",
                transform=ax.transAxes, fontsize=6.5, fontweight="bold",
                color="#444444", va="center", ha="center", zorder=12)
        synthese_btn = ax.text(x0 + w - 0.005, y0 + h - hdr_h / 2,
                "Synthèse BV ▶",
                transform=ax.transAxes, fontsize=5.5, fontweight="bold",
                color="#1A5276", va="center", ha="right", zorder=13,
                bbox=dict(boxstyle="round,pad=0.15", facecolor="#D6EAF8",
                          edgecolor="#1A5276", linewidth=0.5, alpha=0.85))
        self._synthese_btn_artist = synthese_btn
        ax.plot([x0 + 0.005, x0 + w - 0.005],
                [y0 + h - hdr_h, y0 + h - hdr_h],
                color="#CCCCCC", linewidth=0.5,
                transform=ax.transAxes, zorder=10)

        # ── Pied (tendance)
        ftr_h  = 0.038
        pct_po  = s["pct_pan_over"]
        n_pts   = s["n_common"]
        pct_cum = s["pct_ecart_cumul"]   # (∑Pan−∑Ant)/∑Ant × 100
        cum_sgn = "+" if pct_cum >= 0 else ""
        if pct_po >= 50:
            tend_txt = (f"Pan. sur-estime {pct_po:.0f} % des pas de temps"
                        f" (nb : {n_pts}) soit {cum_sgn}{pct_cum:.0f} % du cumul global")
            tc = C_PAN
        else:
            tend_txt = (f"Pan. sous-estime {100-pct_po:.0f} % des pas de temps"
                        f" (nb : {n_pts}) soit {cum_sgn}{pct_cum:.0f} % du cumul global")
            tc = C_ANT
        ax.text(x0 + w / 2, y0 + ftr_h / 2,
                tend_txt,
                transform=ax.transAxes, fontsize=5.5, fontstyle="italic",
                color=tc, va="center", ha="center", zorder=12)
        ax.plot([x0 + 0.005, x0 + w - 0.005],
                [y0 + ftr_h, y0 + ftr_h],
                color="#CCCCCC", linewidth=0.5,
                transform=ax.transAxes, zorder=10)

        # ── 5 lignes de données
        # Layout : [label] [barre] [valeur  horodatage]
        LBL_W = 0.082   # colonne label (réduite)
        GAP   = 0.004   # espace entre label et barre
        BAR_X = x0 + LBL_W + GAP
        BAR_W = 0.088   # largeur max barre
        VAL_X = BAR_X + BAR_W + 0.005

        seuil_lbl = f"Forte int. (>{seuil:.0f}mm)"
        rows = [
            ("Écart moyen",
             fmt_val(s["ecart_moyen"],       s["pct_ecart_moyen"]),
             None,                                                       "ecart_moyen",      s["ecart_moyen"]),
            ("Écart max 1h",
             fmt_val(s["ecart_max_1h"],      s["pct_ecart_max_1h"]),
             fmt_ts(s["ts_max_1h"]),                                     "ecart_max_1h",     s["ecart_max_1h"]),
            ("Cumul 1h max Ant.",
             fmt_val(s["ecart_at_ant_peak"], s["pct_ecart_at_peak"]),
             fmt_ts(s["ts_ant_peak"]),                                   "ecart_at_ant_peak",s["ecart_at_ant_peak"]),
            ("3h consécutives",
             fmt_val(s["ecart_3h"],          s["pct_ecart_3h"]),
             f"{fmt_ts(s['ts_3h_start'])}–{s['ts_3h_end'].strftime('%Hh')}",
                                                                         "ecart_3h",         s["ecart_3h"]),
            (seuil_lbl,
             fmt_val(s["ecart_forte"], s["pct_ecart_forte"]) if s["ecart_forte"] is not None else None,
             None,                                                       "ecart_forte",      s["ecart_forte"]),
        ]

        data_h  = h - hdr_h - ftr_h
        row_h   = data_h / len(rows)
        bar_th  = row_h * 0.32   # épaisseur barre

        for i, (label, val_txt, ts_txt, ref_key, val_raw) in enumerate(rows):
            # Centre vertical de la ligne (de bas en haut)
            row_cy = y0 + ftr_h + (len(rows) - i - 0.5) * row_h

            if val_txt is None or val_raw is None:
                # Pas de données (ex : aucun pas > seuil)
                ax.text(x0 + 0.006, row_cy, label,
                        transform=ax.transAxes, fontsize=5.8,
                        color="#AAAAAA", va="center", zorder=12)
                ax.text(VAL_X, row_cy, "—",
                        transform=ax.transAxes, fontsize=6,
                        color="#AAAAAA", va="center", zorder=12)
                continue

            c = color_for(val_raw)

            # ── Label (colonne gauche)
            ax.text(x0 + 0.006, row_cy,
                    label,
                    transform=ax.transAxes, fontsize=5.8,
                    color="#555555", va="center", zorder=12)

            # ── Barre fond gris
            ax.add_patch(mpatches.Rectangle(
                (BAR_X, row_cy - bar_th / 2), BAR_W, bar_th,
                transform=ax.transAxes, clip_on=False,
                facecolor="#E8E8E8", alpha=0.85, zorder=10))

            # ── Barre colorée
            frac = bar_frac(val_raw, ref_key)
            if frac > 0:
                ax.add_patch(mpatches.Rectangle(
                    (BAR_X, row_cy - bar_th / 2), BAR_W * frac, bar_th,
                    transform=ax.transAxes, clip_on=False,
                    facecolor=c, alpha=0.60, zorder=11))

            # ── Valeur + % (colonne droite)
            ax.text(VAL_X, row_cy,
                    val_txt,
                    transform=ax.transAxes, fontsize=6, fontweight="bold",
                    color=c, va="center", zorder=12)

            # ── Horodatage (aligné après la valeur)
            if ts_txt:
                ts_offset = len(val_txt) * 0.0048 + 0.003
                ax.text(VAL_X + ts_offset, row_cy,
                        ts_txt,
                        transform=ax.transAxes, fontsize=5.5,
                        color="#888888", va="center", zorder=12)

    # ── Synthèse BV (fenêtre tableau tous épisodes) ──────────────────────────

    def _on_synthese_pick(self, event):
        """Détecte le clic sur le texte 'Synthèse BV ▶' dans l'encart."""
        if self._synthese_btn_artist is None:
            return
        try:
            renderer = self._visu_fig.canvas.get_renderer()
            bbox = self._synthese_btn_artist.get_window_extent(renderer=renderer)
            if bbox.contains(event.x, event.y):
                self._open_synthese_bv_window()
        except Exception:
            pass

    def _open_synthese_bv_window(self):
        """Ouvre la fenêtre tableau synthèse BV de tous les épisodes."""
        win = tk.Toplevel(self)
        win.title("Synthèse BV — Antilope vs Panthère")
        win.geometry("860x520")
        win.resizable(True, True)

        C_ANT = "#1F618D"
        C_PAN = "#CC5500"
        C_NEU = "#888888"

        # Largeurs fixes des colonnes (pixels) — partagées entre header et données
        COL_W = [230, 100, 155, 155, 100]

        # ── Lecture données ──────────────────────────────────────────────────
        def _bv_sum(path):
            if not path or not os.path.exists(path):
                return None
            total, found = 0.0, False
            try:
                with open(path, encoding="utf-8") as f:
                    rdr = csv.reader(f, delimiter=";")
                    next(rdr, None)
                    for row in rdr:
                        if len(row) >= 2:
                            try:
                                total += float(row[1].strip())
                                found = True
                            except ValueError:
                                pass
            except Exception:
                return None
            return total if found else None

        def _q_max(path):
            if not path or not os.path.exists(path):
                return None
            best = None
            try:
                with open(path, encoding="utf-8") as f:
                    for row in csv.reader(f, delimiter=";"):
                        if len(row) >= 2:
                            try:
                                v = float(row[1])
                                if best is None or v > best:
                                    best = v
                            except ValueError:
                                pass
            except Exception:
                return None
            return best

        # ── En-tête figé (hors canvas) ───────────────────────────────────────
        HDR_BG = "#E4E8ED"
        hdr_frame = tk.Frame(win, bg=HDR_BG)
        hdr_frame.pack(fill=tk.X, side=tk.TOP)

        col_defs = [
            ("Date épisode",        "#333333"),
            ("Q max (m³/s)",        "#333333"),
            ("Cumul Antilope (mm)", C_ANT),
            ("Cumul Panthère (mm)", C_PAN),
            ("Écart (%)",           "#333333"),
        ]
        for j, (lbl, fg) in enumerate(col_defs):
            tk.Label(hdr_frame, text=lbl, bg=HDR_BG, fg=fg,
                     font=("TkDefaultFont", 9, "bold"),
                     width=COL_W[j] // 7, anchor="center",
                     padx=6, pady=7, relief="flat"
                     ).grid(row=0, column=j, sticky="nsew", padx=1, pady=0)
            hdr_frame.columnconfigure(j, weight=1, minsize=COL_W[j])

        # ── Canvas scrollable (données uniquement) ───────────────────────────
        container = tk.Frame(win)
        container.pack(fill=tk.BOTH, expand=True)

        canv = tk.Canvas(container, bg="white", highlightthickness=0)
        vsb  = ttk.Scrollbar(container, orient="vertical", command=canv.yview)
        canv.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        canv.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        frame = tk.Frame(canv, bg="white")
        wid   = canv.create_window((0, 0), window=frame, anchor="nw")
        frame.bind("<Configure>",
                   lambda e: canv.configure(scrollregion=canv.bbox("all")))
        canv.bind("<Configure>",
                  lambda e: canv.itemconfig(wid, width=e.width))

        for j, w in enumerate(COL_W):
            frame.columnconfigure(j, weight=1, minsize=w)

        def _scroll(e):
            canv.yview_scroll(int(-1 * (e.delta / 120)), "units")
        canv.bind_all("<MouseWheel>", _scroll)
        win.bind("<Destroy>", lambda e: canv.unbind_all("<MouseWheel>"))

        # ── Lignes de données ────────────────────────────────────────────────
        for i, ep in enumerate(self._visu_episodes):
            ri = i

            date_lbl = ep.get("label", "—")
            vig_lbl  = self._vig_from_file(ep["q_path"]) if ep.get("q_path") else "Vert"
            vig_bg, vig_fg = self._VIG_ITEM_COLORS.get(vig_lbl, ("#EBF5FB", "#1A5276"))

            q_val  = _q_max(ep.get("q_path"))
            s_ant  = _bv_sum(ep.get("p_path"))
            s_pan  = _bv_sum(ep.get("pant_path"))

            q_txt   = f"{q_val:.1f}" if q_val is not None else "—"
            ant_txt = f"{s_ant:.0f}" if s_ant is not None else "—"
            pan_txt = f"{s_pan:.0f}" if s_pan is not None else "—"

            if s_ant is not None and s_pan is not None and s_ant > 0:
                pct     = (s_pan - s_ant) / s_ant * 100
                pct_txt = f"{'+'if pct >= 0 else ''}{pct:.0f} %"
                c_p     = C_PAN if s_pan > s_ant else C_ANT
            else:
                pct_txt = "—"
                c_p     = C_NEU

            row_bg = "#F0F3F4" if ri % 2 == 0 else "white"

            tk.Label(frame, text=date_lbl, bg=vig_bg, fg=vig_fg,
                     font=("TkDefaultFont", 8), anchor="center", padx=8, pady=5
                     ).grid(row=ri, column=0, sticky="nsew", padx=1, pady=0)
            tk.Label(frame, text=q_txt, bg=vig_bg, fg=vig_fg,
                     font=("TkDefaultFont", 8), anchor="center", padx=8, pady=5
                     ).grid(row=ri, column=1, sticky="nsew", padx=1, pady=0)
            for j, (txt, fg) in enumerate(
                    [(ant_txt, C_ANT), (pan_txt, C_PAN), (pct_txt, c_p)], start=2):
                tk.Label(frame, text=txt, bg=row_bg, fg=fg,
                         font=("TkDefaultFont", 8, "bold"), anchor="center", padx=8, pady=5
                         ).grid(row=ri, column=j, sticky="nsew", padx=1, pady=0)

    # ── Onglet Paramétrage ───────────────────────────────────────────────────

    def _build_tab_parametrage(self):
        frm = self.tab_parametrage
        BG  = "#1B2631"
        BG2 = "#212F3D"
        FG  = "#D6EAF8"
        FG2 = "#85C1E9"
        ACC = "#2E86C1"

        # ── En-tête ────────────────────────────────────────────────────────
        hdr = tk.Frame(frm, bg="#154360", pady=14)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text="⚙  Paramétrage territorial",
                 bg="#154360", fg="#FFFFFF",
                 font=("TkDefaultFont", 13, "bold")).pack(side=tk.LEFT, padx=20)
        tk.Label(hdr, text="Préfixes et longueurs des codes identifiants",
                 bg="#154360", fg="#AED6F1",
                 font=("TkDefaultFont", 9, "italic")).pack(side=tk.LEFT, padx=(0, 20))

        body = tk.Frame(frm, bg=BG, padx=30, pady=20)
        body.pack(fill=tk.BOTH, expand=True)

        # ── Note d'avertissement ───────────────────────────────────────────
        note = tk.Frame(body, bg="#1A4971", padx=14, pady=10, relief="flat")
        note.pack(fill=tk.X, pady=(0, 22))
        tk.Label(note, text="ℹ  Ces paramètres s'appliquent à toute la configuration.\n"
                             "Après modification, pensez à re-vérifier les codes station et BNBV\n"
                             "dans l'onglet Configuration.",
                 bg="#1A4971", fg="#D6EAF8", font=("TkDefaultFont", 9),
                 justify=tk.LEFT).pack(anchor=tk.W)

        def _row(label_text):
            r = tk.Frame(body, bg=BG, pady=6)
            r.pack(fill=tk.X)
            tk.Label(r, text=label_text, bg=BG, fg=FG,
                     font=("TkDefaultFont", 10), width=36, anchor=tk.W).pack(side=tk.LEFT)
            return r

        # ── Code station — préfixe ─────────────────────────────────────────
        r = _row("Préfixe du code station hydrométrie :")
        self._var_param_pfx_station = tk.StringVar()
        tk.Entry(r, textvariable=self._var_param_pfx_station, width=6,
                 font=("TkDefaultFont", 10, "bold")).pack(side=tk.LEFT, padx=(0, 12))
        tk.Label(r, text="(ex : Y pour les stations du SPCMO)",
                 bg=BG, fg=FG2, font=("TkDefaultFont", 8, "italic")).pack(side=tk.LEFT)

        # ── Code station — nb chiffres ─────────────────────────────────────
        r = _row("Nombre de chiffres après le préfixe :")
        self._var_param_nb_digits = tk.StringVar()
        tk.Entry(r, textvariable=self._var_param_nb_digits, width=4,
                 font=("TkDefaultFont", 10)).pack(side=tk.LEFT, padx=(0, 12))
        tk.Label(r, text="(9 par défaut — le code site = préfixe + (n-2) premiers chiffres)",
                 bg=BG, fg=FG2, font=("TkDefaultFont", 8, "italic")).pack(side=tk.LEFT)

        # ── Séparateur ─────────────────────────────────────────────────────
        tk.Frame(body, bg="#2E4057", height=1).pack(fill=tk.X, pady=16)

        # ── Code BNBV — préfixe ────────────────────────────────────────────
        r = _row("Préfixe du code BNBV :")
        self._var_param_pfx_bnbv = tk.StringVar()
        tk.Entry(r, textvariable=self._var_param_pfx_bnbv, width=6,
                 font=("TkDefaultFont", 10, "bold")).pack(side=tk.LEFT, padx=(0, 12))
        tk.Label(r, text="(ex : MO pour SPCMO)",
                 bg=BG, fg=FG2, font=("TkDefaultFont", 8, "italic")).pack(side=tk.LEFT)

        # ── Bouton Enregistrer ─────────────────────────────────────────────
        tk.Frame(body, bg="#2E4057", height=1).pack(fill=tk.X, pady=(20, 16))
        btn_row = tk.Frame(body, bg=BG)
        btn_row.pack(anchor=tk.W)
        tk.Button(btn_row, text="  💾  Enregistrer le paramétrage  ",
                  bg=ACC, fg="white",
                  activebackground="#1A5276", activeforeground="white",
                  relief="flat", bd=0, padx=14, pady=8,
                  font=("TkDefaultFont", 10, "bold"), cursor="hand2",
                  command=self._save_parametrage).pack(side=tk.LEFT)
        self._lbl_param_status = tk.Label(btn_row, text="", bg=BG,
                                           font=("TkDefaultFont", 9))
        self._lbl_param_status.pack(side=tk.LEFT, padx=14)

        # ── Barre basse : Aide + contact ───────────────────────────────────
        tk.Frame(body, bg="#2E4057", height=1).pack(fill=tk.X, pady=(20, 12))
        bottom_row = tk.Frame(body, bg=BG)
        bottom_row.pack(fill=tk.X)

        tk.Button(bottom_row, text="  ℹ  Aide",
                  bg="#1A4971", fg="#AED6F1",
                  activebackground="#2E4057", activeforeground="#FFFFFF",
                  relief="groove", bd=1, padx=12, pady=7,
                  font=("TkDefaultFont", 9), cursor="hand2",
                  command=self._ouvrir_aide).pack(side=tk.LEFT)

        _ico_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo_lancer_outil.ico")
        if os.path.isfile(_ico_path):
            try:
                from PIL import Image, ImageTk
                _img = Image.open(_ico_path).resize((28, 28), Image.LANCZOS)
                self._logo_photo_param = ImageTk.PhotoImage(_img)
                tk.Label(bottom_row, image=self._logo_photo_param,
                         bg=BG).pack(side=tk.RIGHT, padx=(0, 6))
            except Exception:
                pass

        lbl_contact = tk.Label(
            bottom_row,
            text="PIOT Charles-Eddy — SPCMO",
            fg="#AED6F1", bg=BG,
            font=("TkDefaultFont", 8, "underline"),
            cursor="hand2",
        )
        lbl_contact.pack(side=tk.RIGHT, padx=(0, 4))
        lbl_contact.bind("<Button-1>", lambda e: webbrowser.open(
            "mailto:charles-eddy.piot@developpement-durable.gouv.fr"
            "?subject=Info%20%2F%20bugg%20outil%20pr%C3%A9pa%20crues%20Plathynes"
        ))

    def _refresh_parametrage_ui(self):
        p = self.config_data.get("parametrage", {})
        if hasattr(self, "_var_param_pfx_station"):
            self._var_param_pfx_station.set(p.get("prefixe_station", "Y"))
            self._var_param_nb_digits.set(str(p.get("nb_chiffres_station", 9)))
            self._var_param_pfx_bnbv.set(p.get("prefixe_bnbv", "MO"))

    def _save_parametrage(self):
        pfx_st = self._var_param_pfx_station.get().strip()
        nb_str = self._var_param_nb_digits.get().strip()
        pfx_bv = self._var_param_pfx_bnbv.get().strip()

        if not pfx_st:
            self._lbl_param_status.config(text="⚠ Le préfixe station ne peut pas être vide.", fg="#E74C3C")
            return
        if not pfx_bv:
            self._lbl_param_status.config(text="⚠ Le préfixe BNBV ne peut pas être vide.", fg="#E74C3C")
            return
        try:
            nb = int(nb_str)
            if nb < 3:
                raise ValueError
        except ValueError:
            self._lbl_param_status.config(text="⚠ Nombre de chiffres invalide (entier ≥ 3 attendu).", fg="#E74C3C")
            return

        self.config_data["parametrage"] = {
            "prefixe_station":     pfx_st,
            "nb_chiffres_station": nb,
            "prefixe_bnbv":        pfx_bv,
        }
        try:
            from modules.config_manager import save_config
            save_config(self.config_data)
        except Exception as e:
            self._lbl_param_status.config(text=f"⚠ Erreur sauvegarde : {e}", fg="#E74C3C")
            return

        # Mettre à jour les labels dynamiques dans Configuration
        self._var_pfx_station_lbl.set(pfx_st)
        self._var_pfx_bnbv_lbl.set(pfx_bv)
        nd = self._nb_digits
        site_digits = nd - 2
        self._var_pfx_station_hint.set(
            f"({nd} chiffres — code site = {pfx_st} + {site_digits} premiers chiffres)")

        self._lbl_param_status.config(
            text="✓ Paramétrage enregistré. Vérifiez les codes en Configuration.", fg="#27AE60")

    # ── Onglet Analyse ───────────────────────────────────────────────────────

    def _build_tab_analyse(self):
        frm = self.tab_analyse

        _VIG_LABELS_A         = ["Vert", "ZT Jaune", "Jaune", "ZT Orange", "Orange", "ZT Rouge", "Rouge"]
        self._analyse_vig_chk = {v: tk.BooleanVar(value=True) for v in _VIG_LABELS_A}

        ctrl = tk.Frame(frm, bg="#EEF2F7", pady=6)
        ctrl.pack(fill=tk.X, padx=6, pady=(4, 0))
        ctrl.columnconfigure(1, weight=1)   # colonne centrale extensible

        tk.Label(ctrl, text="Analyse comparative des épisodes",
                 bg="#EEF2F7", font=("TkDefaultFont", 10, "bold")).grid(
                 row=0, column=0, padx=(8, 0), sticky=tk.W)

        # Cases à cocher Vig. max. — centrées dans la colonne du milieu
        vig_frame = tk.Frame(ctrl, bg="#EEF2F7")
        vig_frame.grid(row=0, column=1)
        tk.Label(vig_frame, text="Vig. max. :", bg="#EEF2F7",
                 font=("TkDefaultFont", 8, "bold")).pack(side=tk.LEFT, padx=(0, 6))
        for v in _VIG_LABELS_A:
            tk.Checkbutton(vig_frame, text=v, variable=self._analyse_vig_chk[v],
                           bg="#EEF2F7", activebackground="#EEF2F7",
                           font=("TkDefaultFont", 8),
                           command=self._refresh_analyse).pack(side=tk.LEFT, padx=3)

        tk.Button(ctrl, text="↻  Calculer / Rafraîchir",
                  bg="#1A5276", fg="white",
                  activebackground="#154360", relief="flat", bd=0,
                  padx=10, pady=5, cursor="hand2",
                  command=self._refresh_analyse).grid(row=0, column=2, padx=8)

        if HAS_MPL:
            self._analyse_fig = Figure(figsize=(9, 6), dpi=96)
            self._analyse_fig.patch.set_facecolor("#F8F9FA")
            self._analyse_ax = self._analyse_fig.add_subplot(111)
            self._analyse_ax.set_facecolor("#F8F9FA")
            self._analyse_ax.text(0.5, 0.5,
                "Cliquez sur « Calculer / Rafraîchir » pour analyser les épisodes",
                ha="center", va="center",
                transform=self._analyse_ax.transAxes,
                fontsize=11, color="#888888")
            self._analyse_canvas = FigureCanvasTkAgg(self._analyse_fig, master=frm)
            self._analyse_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True,
                                                       padx=6, pady=6)
            self._analyse_canvas.draw()

            # Note de lecture
            note = ("Axe X : HU de début (%)   |   Axe Y : Q max (m³/s)   |   "
                    "Taille bulle : cumul pluie (mm)   |   Couleur : intensité max pluie (mm/h)")
            tk.Label(frm, text=note, bg="#EEF2F7", fg="#555555",
                     font=("TkDefaultFont", 8, "italic"),
                     anchor="w").pack(fill=tk.X, padx=10, pady=(0, 4))
        else:
            tk.Label(frm, text="matplotlib requis",
                     bg="white", font=("TkDefaultFont", 12), fg="#888888").pack(expand=True)

    def _refresh_analyse(self):
        if not HAS_MPL:
            return
        debits_dir, hu_dir, pluies_dir, bv_dir = self._get_out_dirs()
        episodes = self._collect_analyse_data(debits_dir, hu_dir, bv_dir)
        vig_on = {v for v, bv in self._analyse_vig_chk.items() if bv.get()}
        if len(vig_on) < len(self._analyse_vig_chk):
            episodes = [ep for ep in episodes
                        if ep.get("vig") in vig_on]
        self._plot_analyse(episodes)

    def _collect_analyse_data(self, debits_dir, hu_dir, bv_dir):
        """Lit les CSV de chaque épisode et retourne la liste des métriques."""
        episodes = []
        if not os.path.isdir(debits_dir):
            return episodes

        for fname in sorted(os.listdir(debits_dir)):
            # Accepte Q-Ep_*.txt et H-Ep_*.txt
            if not (fname.endswith(".txt") and
                    (fname.startswith("Q-Ep_") or fname.startswith("H-Ep_"))):
                continue
            prefix  = "Q-Ep_" if fname.startswith("Q-Ep_") else "H-Ep_"
            base    = fname[len(prefix):-4]   # DD_MM_YYYY_Station
            parts   = base.split("_")
            label   = base
            if len(parts) >= 3:
                try:
                    dt = datetime.strptime(f"{parts[0]}/{parts[1]}/{parts[2]}", "%d/%m/%Y")
                    label = dt.strftime("%d/%m/%Y")
                except ValueError:
                    pass

            q_path  = os.path.join(debits_dir, fname)
            hu_path = os.path.join(hu_dir, fname.replace(prefix, "HU-Ep_").replace(".txt", ".csv"))
            p_path  = os.path.join(bv_dir, fname.replace(prefix, "AntJ1_BV-Ep_").replace(".txt", ".csv"))

            def read_col(path, col=1, has_header=True):
                vals = []
                try:
                    with open(path, encoding="utf-8") as f:
                        r = csv.reader(f, delimiter=";")
                        if has_header:
                            next(r, None)
                        for row in r:
                            if len(row) > col:
                                try:
                                    vals.append(float(row[col].strip()))
                                except ValueError:
                                    pass
                except Exception:
                    pass
                return vals

            q_vals  = read_col(q_path,  col=1, has_header=False)
            hu_vals = read_col(hu_path, col=1, has_header=True)
            p_vals  = read_col(p_path,  col=1, has_header=True)

            if not q_vals:
                continue

            q_max     = max(q_vals)
            hu_debut  = hu_vals[0]  if hu_vals  else None
            p_cumul   = sum(p_vals) if p_vals   else None
            p_max_int = max(p_vals) if p_vals   else None

            episodes.append({
                "label":    label,
                "q_max":    q_max,
                "hu_debut": hu_debut,
                "p_cumul":  p_cumul,
                "p_int":    p_max_int,
                "vig":      self._vig_label_from_val(q_max),
            })
        return episodes

    def _plot_analyse(self, episodes):
        import math
        # Effacer toute la figure (colorbars comprises) et recréer le subplot
        self._analyse_fig.clear()
        ax = self._analyse_fig.add_subplot(111)
        self._analyse_ax = ax
        ax.set_facecolor("#F8F9FA")

        if not episodes:
            ax.text(0.5, 0.5, "Aucun épisode trouvé dans le dossier de sortie",
                    ha="center", va="center", transform=ax.transAxes,
                    fontsize=11, color="#888888")
            self._analyse_fig.tight_layout()
            self._analyse_canvas.draw()
            return

        # Séparer les épisodes complets (4 métriques) des partiels
        complets = [e for e in episodes
                    if e["hu_debut"] is not None and e["p_cumul"] is not None]
        partiels = [e for e in episodes if e not in complets]

        # Valeurs pour couleur et taille
        p_int_vals  = [e["p_int"]  or 0   for e in complets]
        p_cum_vals  = [e["p_cumul"] or 0  for e in complets]
        q_max_vals  = [e["q_max"]         for e in complets]
        hu_vals     = [e["hu_debut"]      for e in complets]

        # Taille de bulle : 100–1200 en surface (sqrt échelle)
        if p_cum_vals and max(p_cum_vals) > 0:
            max_cum = max(p_cum_vals)
            sizes = [100 + 1100 * (v / max_cum) for v in p_cum_vals]
        else:
            sizes = [300] * len(complets)

        # Couleur : intensité max pluie
        try:
            import matplotlib.colors as mcolors
            import matplotlib as mpl
            cmap  = mpl.colormaps["YlOrRd"]
            vmax  = max(p_int_vals) if p_int_vals and max(p_int_vals) > 0 else 1
            norm  = mcolors.Normalize(vmin=0, vmax=vmax)
            colors = [cmap(norm(v)) for v in p_int_vals]
        except Exception:
            colors = ["#1F618D"] * len(complets)
            norm = None

        sc = ax.scatter(hu_vals, q_max_vals, s=sizes, c=colors,
                        alpha=0.75, edgecolors="#333333", linewidths=0.6, zorder=3)

        # Étiquettes : date + Vig. max. — placement greedy anti-superposition

        # 8 directions candidates (offset en points matplotlib)
        # Ordre de préférence : NE, NO, SE, SO, E, O, N, S
        _DIRS = [(6, 6), (-50, 6), (6, -24), (-50, -24),
                 (10, -8), (-54, -8), (-18, 10), (-18, -26)]
        FONT_SZ = 6.5
        # Taille estimée d'une boîte d'étiquette (pts display) : 2 lignes ~10 car
        _BW, _BH = 52, 22

        placed_boxes = []  # (x0, y0, x1, y1) en coords display

        # S'assurer que les limites de l'axe sont posées avant les transforms
        if hu_vals and q_max_vals:
            x_pad = (max(hu_vals) - min(hu_vals)) * 0.05 or 1
            y_pad = (max(q_max_vals) - min(q_max_vals)) * 0.05 or 1
            ax.set_xlim(min(hu_vals) - x_pad, max(hu_vals) + x_pad)
            ax.set_ylim(min(q_max_vals) - y_pad, max(q_max_vals) + y_pad)

        def _overlap(b1, b2):
            ix = max(0, min(b1[2], b2[2]) - max(b1[0], b2[0]))
            iy = max(0, min(b1[3], b2[3]) - max(b1[1], b2[1]))
            return ix * iy

        for e, x, y in zip(complets, hu_vals, q_max_vals):
            lbl_txt = f"{e['label']}\n{e.get('vig', '< Jaune')}"
            try:
                dp = ax.transData.transform((x, y))
            except Exception:
                dp = (0, 0)
            best_dir, best_score = _DIRS[0], float("inf")
            for dx, dy in _DIRS:
                bx0, by0 = dp[0] + dx, dp[1] + dy
                cand = (bx0, by0, bx0 + _BW, by0 + _BH)
                score = sum(_overlap(cand, pb) for pb in placed_boxes)
                if score < best_score:
                    best_score, best_dir = score, (dx, dy)
            ox, oy = best_dir
            dp2 = (dp[0] + ox, dp[1] + oy)
            placed_boxes.append((dp2[0], dp2[1], dp2[0] + _BW, dp2[1] + _BH))
            ax.annotate(lbl_txt, (x, y),
                        textcoords="offset points", xytext=(ox, oy),
                        fontsize=FONT_SZ, color="#222222", linespacing=1.35,
                        bbox=dict(boxstyle="round,pad=0.18", fc="white",
                                  ec="#CCCCCC", alpha=0.80, lw=0.5))

        # Lignes de médiane (quadrants)
        if len(complets) >= 2:
            med_hu = sorted(hu_vals)[len(hu_vals) // 2]
            med_q  = sorted(q_max_vals)[len(q_max_vals) // 2]
            ax.axvline(med_hu, color="#AAAAAA", linewidth=0.8, linestyle="--", zorder=1)
            ax.axhline(med_q,  color="#AAAAAA", linewidth=0.8, linestyle="--", zorder=1)
            # Labels quadrants
            xlim = ax.get_xlim(); ylim = ax.get_ylim()
            kw = dict(fontsize=7.5, color="#999999", style="italic", zorder=2)
            ax.text(xlim[0] + 1, ylim[1] * 0.97, "Sol sec / Q fort",  va="top", **kw)
            ax.text(med_hu  + 1, ylim[1] * 0.97, "Sol humide / Q fort", va="top", **kw)
            ax.text(xlim[0] + 1, ylim[0] + (ylim[1]-ylim[0])*0.03, "Sol sec / Q faible",  **kw)
            ax.text(med_hu  + 1, ylim[0] + (ylim[1]-ylim[0])*0.03, "Sol humide / Q faible", **kw)

        # Épisodes partiels (sans pluie ou sans HU)
        for e in partiels:
            ax.scatter([], [], s=100, c="#CCCCCC", label=f"{e['label']} (données partielles)")

        # Colorbar intensité (réduite, ancrée en haut pour laisser place à la légende taille)
        cb = None
        if norm is not None and p_int_vals and max(p_int_vals) > 0:
            try:
                import matplotlib.colors as mcolors
                import matplotlib as mpl
                sm = mpl.cm.ScalarMappable(cmap=mpl.colormaps["YlOrRd"], norm=norm)
                sm.set_array([])
                cb = self._analyse_fig.colorbar(sm, ax=ax, shrink=0.42, pad=0.02,
                                                anchor=(0.5, 1.0))
                cb.set_label("Intensité max pluie (mm/h)", fontsize=8)
            except Exception:
                pass

        # Préparer les handles de taille avant tight_layout
        _bubble_legend_args = None
        if p_cum_vals and max(p_cum_vals) > 0:
            max_cum = max(p_cum_vals)
            ref_vals = [max_cum * f for f in (0.25, 0.50, 1.0)]
            _bh = [
                ax.scatter([], [], s=100 + 1100 * (v / max_cum),
                           c="#AAAAAA", alpha=0.75,
                           edgecolors="#333333", linewidths=0.6)
                for v in ref_vals
            ]
            _bl = [f"{v:.0f} mm" for v in ref_vals]
            _bubble_legend_args = (_bh, _bl)

        ax.set_xlabel("HU de début (%)", fontsize=9)
        ax.set_ylabel("Q max (m³/s)",    fontsize=9)
        ax.set_title(f"Caractérisation des épisodes ({len(episodes)} épisodes)",
                     fontsize=10, pad=8)
        ax.grid(True, alpha=0.2, linestyle="--")

        self._analyse_fig.tight_layout()

        # 1er draw — stabilise toutes les positions (colorbar comprise)
        self._analyse_canvas.draw()

        # Légende taille des bulles — positionnée en pixels réels après 1er draw
        if _bubble_legend_args is not None:
            _bh, _bl = _bubble_legend_args
            try:
                fig_w_px = self._analyse_fig.get_figwidth()  * self._analyse_fig.dpi
                fig_h_px = self._analyse_fig.get_figheight() * self._analyse_fig.dpi
                cb_bb = cb.ax.get_window_extent()            # bbox colorbar en px
                lx = cb_bb.x0 / fig_w_px - 0.01             # légèrement décalé pour que la note tienne
                cy = cb_bb.y0 / fig_h_px - 0.06             # sous le bas de la colorbar
            except Exception:
                lx, cy = 0.88, 0.38

            self._analyse_fig.legend(
                _bh, _bl, title="Cumul pluie *",
                bbox_to_anchor=(lx, cy), loc="upper left",
                fontsize=7, title_fontsize=7.5,
                framealpha=0.90, edgecolor="#CCCCCC",
                borderaxespad=0)

            # 2e draw — stabilise la légende pour lire son bas réel
            self._analyse_canvas.draw()

            # Note sous la légende, calée sur son bas réel
            try:
                leg = self._analyse_fig.legends[-1]
                leg_bottom_fig = leg.get_window_extent().y0 / fig_h_px
                self._analyse_fig.text(
                    lx - 0.06, leg_bottom_fig - 0.025,
                    "* 25 %, 50 % et 100 % du cumul max des épisodes\n"
                    "  (Antilope — cumul total sur l'ensemble de la BBox)",
                    ha="left", va="top", fontsize=6, color="#777777",
                    linespacing=1.4)
            except Exception:
                pass

        self._analyse_canvas.draw()

    # -----------------------------------------------------------------------
    # Actions — Episodes
    # -----------------------------------------------------------------------

    def _calc_duree_manuelle(self, *_):
        try:
            deb = datetime.strptime(self.var_ep_debut.get().strip(), "%d/%m/%Y %H:%M")
            fin = datetime.strptime(self.var_ep_fin.get().strip(), "%d/%m/%Y %H:%M")
            delta = fin - deb
            if delta.total_seconds() <= 0:
                self.var_ep_duree.set("! fin < début")
                return
            h = int(delta.total_seconds()) // 3600
            m = (int(delta.total_seconds()) % 3600) // 60
            self.var_ep_duree.set(f"{h}h{m:02d}")
        except ValueError:
            self.var_ep_duree.set("—")

    def _ajouter_episode_manuel(self):
        fmt = "%d/%m/%Y %H:%M"
        try:
            deb = datetime.strptime(self.var_ep_debut.get().strip(), fmt)
            fin = datetime.strptime(self.var_ep_fin.get().strip(), fmt)
        except ValueError:
            messagebox.showwarning("Format invalide",
                                   "Utilisez le format JJ/MM/AAAA HH:MM\nExemple : 15/04/2007 19:29")
            return
        if fin <= deb:
            messagebox.showwarning("Dates invalides",
                                   "La date de fin doit être postérieure à la date de début.")
            return
        next_idx = max((ep["index"] for ep in self.episodes), default=0) + 1
        label = f"{deb.strftime('%d/%m/%Y %H:%M')} - {fin.strftime('%d/%m/%Y %H:%M')}"
        self.episodes.append({"index": next_idx, "date_debut": deb, "date_fin": fin, "label": label})
        self._refresh_episodes_table()
        self.var_ep_debut.set("")
        self.var_ep_fin.set("")
        self.var_ep_duree.set("—")

    def _supprimer_episodes_sel(self):
        iids = self.tree.selection()
        if not iids:
            return
        idx_sel = {int(i) for i in iids}
        self.episodes = [ep for ep in self.episodes if ep["index"] not in idx_sel]
        self._refresh_episodes_table()

    def _load_csv(self):
        path = filedialog.askopenfilename(
            title="Charger le fichier CSV épisodes",
            filetypes=[("Fichiers CSV", "*.csv"), ("Tous les fichiers", "*.*")])
        if not path:
            return
        try:
            self.episodes = load_episodes(path)
        except Exception as e:
            messagebox.showerror("Erreur CSV", str(e))
            return
        self.lbl_csv.config(text=os.path.basename(path), fg="black", font=("TkDefaultFont", 9))
        self._refresh_episodes_table()

    # ── Ordre de vigilance pour le tri (du plus faible au plus élevé) ───────
    _VIG_ORDER = {
        "—":         -1,
        "Vert":       0,
        "ZT Jaune":   1,
        "Jaune":       2,
        "ZT Orange":   3,
        "Orange":      4,
        "ZT Rouge":    5,
        "Rouge":       6,
    }

    def _episodes_view(self):
        """Retourne (ep, vig_lbl, vig_tag) après filtres et tri."""
        s_deb   = self._filter_debut.get().strip().lower()
        s_fin   = self._filter_fin.get().strip().lower()
        vig_on  = {v for v, bv in self._vig_chk.items() if bv.get()}
        all_on  = len(vig_on) == len(self._vig_chk)

        rows = [(ep, *self._vig_max_episode(ep)) for ep in self.episodes]

        if s_deb:
            rows = [r for r in rows
                    if s_deb in r[0]["date_debut"].strftime("%d/%m/%Y %H:%M")]
        if s_fin:
            rows = [r for r in rows
                    if s_fin in r[0]["date_fin"].strftime("%d/%m/%Y %H:%M")]
        if not all_on:
            rows = [r for r in rows if r[1] in vig_on]

        col, rev = self._sort_col, self._sort_rev
        if col == "Date début":
            rows.sort(key=lambda r: r[0]["date_debut"], reverse=rev)
        elif col == "Date fin":
            rows.sort(key=lambda r: r[0]["date_fin"], reverse=rev)
        elif col == "Durée":
            rows.sort(key=lambda r: r[0]["date_fin"] - r[0]["date_debut"], reverse=rev)
        elif col == "Vig. max.":
            rows.sort(key=lambda r: self._VIG_ORDER.get(r[1], -1), reverse=rev)
        elif col == "#":
            rows.sort(key=lambda r: r[0]["index"], reverse=rev)
        return rows

    def _sort_by(self, col):
        if self._sort_col == col:
            self._sort_rev = not self._sort_rev
        else:
            self._sort_col = col
            self._sort_rev = False
        for c in ("#", "Date début", "Date fin", "Durée", "Vig. max."):
            arrow = (" ▼" if self._sort_rev else " ▲") if c == col else ""
            self.tree.heading(c, text=c + arrow, command=lambda col=c: self._sort_by(col))
        self._refresh_episodes_table()

    def _reset_filtres(self):
        self._filter_debut.set("")
        self._filter_fin.set("")
        for bv in self._vig_chk.values():
            bv.set(True)
        self._sort_col = None
        self._sort_rev = False
        for c in ("#", "Date début", "Date fin", "Durée", "Vig. max."):
            self.tree.heading(c, text=c, command=lambda col=c: self._sort_by(col))
        self._refresh_episodes_table()

    def _refresh_episodes_table(self):
        for row in self.tree.get_children():
            self.tree.delete(row)
        rows = self._episodes_view()
        for ep, vig_lbl, vig_tag in rows:
            deb, fin = ep["date_debut"], ep["date_fin"]
            d = fin - deb
            h = d.seconds // 3600 + d.days * 24
            m = (d.seconds % 3600) // 60
            item_kw = {"tags": (vig_tag,)} if vig_tag else {}
            self.tree.insert("", tk.END, iid=str(ep["index"]),
                             values=(ep["index"],
                                     deb.strftime("%d/%m/%Y %H:%M"),
                                     fin.strftime("%d/%m/%Y %H:%M"),
                                     f"{h}h{m:02d}",
                                     vig_lbl),
                             **item_kw)
        self.tree.selection_set(self.tree.get_children())
        total = len(self.episodes)
        shown = len(rows)
        if shown < total:
            self.lbl_count.config(
                text=f"{shown} épisode(s) affiché(s) sur {total} — filtre actif")
        else:
            self.lbl_count.config(text=f"{total} épisode(s) chargé(s)")

    def _vig_max_episode(self, ep):
        """Retourne (label, tag) de la vigilance max atteinte pour un épisode.

        Lit le fichier Q CSV de l'épisode, cherche le Q max, compare aux seuils.
        """
        grandeur = self.config_data.get("extraction", {}).get("grandeur", "Q")
        if grandeur == "H":
            seuils = self.config_data.get("seuils_h", {})
        else:
            seuils = self.config_data.get("seuils_q",
                     self.config_data.get("seuils", {}))
        nom_station = self.config_data.get("station", {}).get("nom_station", "") or \
                      self.config_data.get("station", {}).get("code_site", "")
        debits_dir, _, _, _ = self._get_out_dirs()
        date_tag = ep["date_debut"].strftime("%d_%m_%Y")
        q_file = os.path.join(debits_dir, f"{grandeur}-Ep_{date_tag}_{nom_station}.txt")

        if not os.path.isfile(q_file):
            return "—", ""

        try:
            import csv as _csv
            q_vals = []
            with open(q_file, encoding="utf-8") as fh:
                for row in _csv.reader(fh, delimiter=";"):
                    if row and len(row) >= 2:
                        try:
                            q_vals.append(float(row[1]))
                        except ValueError:
                            pass
            if not q_vals:
                return "—", ""
            q_max = max(q_vals)
        except Exception:
            return "—", ""

        def _s(key):
            try:
                return float(seuils[key]) if key in seuils else None
            except (ValueError, TypeError):
                return None

        checks = [
            ("rouge",     "Rouge",     "vig_rouge"),
            ("zt_rouge",  "ZT Rouge",  "vig_zt_rouge"),
            ("orange",    "Orange",    "vig_orange"),
            ("zt_orange", "ZT Orange", "vig_zt_orange"),
            ("jaune",     "Jaune",     "vig_jaune"),
            ("zt_jaune",  "ZT Jaune",  "vig_zt_jaune"),
        ]
        for key, lbl, tag in checks:
            v = _s(key)
            if v is not None and q_max >= v:
                return lbl, tag
        return "Vert", "vig_vert"

    def _vig_label_from_val(self, val):
        """Retourne le label de vigilance à partir d'une valeur brute (Q ou H)."""
        grandeur = self.config_data.get("extraction", {}).get("grandeur", "Q")
        if grandeur == "H":
            seuils = self.config_data.get("seuils_h", {})
        else:
            seuils = self.config_data.get("seuils_q",
                     self.config_data.get("seuils", {}))

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

    def _select_all(self):
        self.tree.selection_set(self.tree.get_children())

    def _deselect_all(self):
        self.tree.selection_set([])

    # -----------------------------------------------------------------------
    # Bbox BNBV
    # -----------------------------------------------------------------------

    def _load_bbox_table(self):
        path = os.path.join(os.path.dirname(__file__), "config", "bbox_bnbv.json")
        try:
            import json
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _on_bnbv_change(self, *_):
        suffix = self.var_code_bnbv_suffix.get().strip()
        code   = self._pfx_bnbv + suffix
        table  = self._load_bbox_table()
        if code in table:
            self.var_ul.set(table[code]["ul"])
            self.var_lr.set(table[code]["lr"])

    # -----------------------------------------------------------------------
    # Configuration
    # -----------------------------------------------------------------------

    def _load_config(self):
        try:
            self.config_data = load_config()
        except Exception:
            self.config_data = {
                "phyc":    {"url": "http://services.schapi.e2.rie.gouv.fr/phycop/bdtr.wsdl",
                             "idcontact": "", "motdepasse": ""},
                "bdimage": {"url": "http://services.schapi.e2.rie.gouv.fr/bdimage/2016/wsbdi",
                             "timeout_async": 300, "epsg": 2154, "resol": 1000, "nodata": -1},
                "station": {"code_station": "", "code_site": "", "code_bnbv": "", "nom_station": "", "ul": "", "lr": ""},
                "output_dir": "./sorties",
            }
        self.config_data.setdefault("parametrage", {
            "prefixe_station":      "Y",
            "nb_chiffres_station":  9,
            "prefixe_bnbv":         "MO",
        })
        self._refresh_parametrage_ui()
        self._refresh_config_ui()
        self._refresh_extraction_ui()

    def _refresh_config_ui(self):
        phyc = self.config_data.get("phyc", {})
        self.var_phyc_url.set(phyc.get("url", ""))
        self.var_phyc_id.set(phyc.get("idcontact", ""))
        self.var_phyc_pwd.set(phyc.get("motdepasse", ""))

        bdi = self.config_data.get("bdimage", {})
        self.var_bdi_url.set(bdi.get("url", ""))
        self.var_outdir.set(self.config_data.get("output_dir", "./sorties"))

        st = self.config_data.get("station", {})
        # Priorité code_station, fallback code_site (compat anciens JSON)
        code_st = st.get("code_station", "") or st.get("code_site", "")
        pfx = self._pfx_station
        self.var_code_station_suffix.set(code_st[len(pfx):] if code_st.startswith(pfx) else code_st)
        code_bnbv = st.get("code_bnbv", "")
        pfx_b = self._pfx_bnbv
        self.var_code_bnbv_suffix.set(code_bnbv[len(pfx_b):] if code_bnbv.startswith(pfx_b) else code_bnbv)
        # Mise à jour des labels préfixe dans l'UI Configuration
        self._var_pfx_station_lbl.set(pfx)
        self._var_pfx_bnbv_lbl.set(pfx_b)
        nd = self._nb_digits
        site_digits = nd - 2
        ex_suffix = "0" * nd
        ex_site   = pfx + ex_suffix[:site_digits] + "…"
        self._var_pfx_station_hint.set(
            f"ex: {'2' + '0'*(nd-1)}  (→ code site Q/H : {pfx}{'0'*site_digits}…  {nd} chiffres)")
        self.var_nom_station.set(st.get("nom_station", ""))
        self.var_ul.set(st.get("ul", ""))
        self.var_lr.set(st.get("lr", ""))

        # Seuils de vigilance — repopuler les champs UI depuis le JSON
        # Compat anciens JSON qui utilisaient "seuils" → traité comme seuils_q
        seuils_grandeur = self.var_seuils_grandeur.get()
        if seuils_grandeur == "H (m)":
            seuils = self.config_data.get("seuils_h", {})
        else:
            seuils = self.config_data.get("seuils_q",
                     self.config_data.get("seuils", {}))
        for key in ("zt_jaune", "jaune", "zt_orange", "orange", "zt_rouge", "rouge"):
            val = seuils.get(key, "")
            self._var_seuils[key].set(str(val) if val != "" else "")

    def _refresh_extraction_ui(self):
        """Restaure les préférences d'extraction depuis config_data."""
        ext = self.config_data.get("extraction", {})
        if not ext:
            return
        self.var_pluies.set(ext.get("pluies", True))
        pdt_p = ext.get("pdt_pluies", 60)
        rev = {v: k for k, v in PDT_PLUIES_OPTIONS.items()}
        self.var_pdt_pluies.set(rev.get(pdt_p, "1 heure"))
        self.var_pluies_panthere.set(ext.get("pluies_panthere", False))
        self.var_hu.set(ext.get("hu", True))
        pdt_hu = ext.get("pdt_hu", 60)
        self.var_pdt_hu.set("1 jour à 6:00" if pdt_hu == "journalier_6h" else "1 heure")
        self.var_debits.set(ext.get("debits", True))
        pdt_q = ext.get("pdt_debits", 15)
        rev_q = {v: k for k, v in PDT_DEBITS_OPTIONS.items()}
        self.var_pdt_debits.set(rev_q.get(pdt_q, "15 minutes"))
        self.var_grandeur.set(ext.get("grandeur", "Q"))

    def _save_config(self):
        if "phyc"    not in self.config_data: self.config_data["phyc"]    = {}
        if "bdimage" not in self.config_data: self.config_data["bdimage"] = {}

        self.config_data["phyc"]["url"]       = self.var_phyc_url.get().strip()
        self.config_data["phyc"]["idcontact"] = self.var_phyc_id.get().strip()
        self.config_data["phyc"]["motdepasse"]= self.var_phyc_pwd.get()
        self.config_data["bdimage"]["url"]    = self.var_bdi_url.get().strip()
        self.config_data["output_dir"]        = self.var_outdir.get().strip()
        suffix9 = self.var_code_station_suffix.get().strip()
        nd = self._nb_digits
        code_station = self._pfx_station + suffix9
        code_site    = self._pfx_station + suffix9[:nd - 2]
        self.config_data["station"] = {
            "code_station": code_station,
            "code_site":    code_site,
            "code_bnbv":   self._pfx_bnbv + self.var_code_bnbv_suffix.get().strip(),
            "nom_station": self.var_nom_station.get().strip(),
            "ul": self.var_ul.get().strip(),
            "lr": self.var_lr.get().strip(),
        }
        # Seuils de vigilance — lire depuis les champs UI, clé dépend de la grandeur
        seuils = {}
        for key in ("zt_jaune", "jaune", "zt_orange", "orange", "zt_rouge", "rouge"):
            txt = self._var_seuils[key].get().strip()
            if txt:
                try:
                    seuils[key] = float(txt)
                except ValueError:
                    pass
        seuils_key = "seuils_h" if self.var_seuils_grandeur.get() == "H (m)" else "seuils_q"
        self.config_data[seuils_key] = seuils
        try:
            save_config(self.config_data)
            messagebox.showinfo("Configuration", "Configuration enregistrée avec succès.")
        except Exception as e:
            messagebox.showerror("Erreur", f"Impossible d'enregistrer la configuration :\n{e}")

    def _ouvrir_aide(self):
        """Ouvre le fichier aide.html dans le navigateur par défaut."""
        html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "aide.html")
        webbrowser.open(f"file:///{html_path.replace(os.sep, '/')}")

    def _get_out_dirs(self):
        """Retourne (debits_dir, hu_dir, pluies_dir, bv_dir) selon la config courante.

        Utilise la nouvelle structure {nom}/Debits|HU|Pluies|Pluies temps moy BV…/ si elle
        existe, sinon replie sur l'ancienne structure plate pour la rétro-compatibilité.
        """
        base = self.config_data.get("output_dir", "./sorties")
        nom  = (self.config_data.get("station", {}).get("nom_station", "")
                or self.config_data.get("station", {}).get("code_site", "")
                or "station")
        new_debits = os.path.join(base, nom, "Debits")
        if os.path.isdir(new_debits):
            root = os.path.join(base, nom)
            return (os.path.join(root, "Debits"),
                    os.path.join(root, "HU"),
                    os.path.join(root, "Pluies"),
                    os.path.join(root, "Pluies temps moy BV pour graph"))
        # Ancienne structure plate (rétro-compatibilité)
        return (base, base, base, os.path.join(base, "Pluie temp pr graphique"))

    def _browse_outdir(self):
        d = filedialog.askdirectory(title="Dossier de sortie")
        if d:
            self.var_outdir.set(d)

    # -----------------------------------------------------------------------
    # Diagnostic PHyC
    # -----------------------------------------------------------------------

    def _ouvrir_diagnostic_phyc(self):
        url = self.var_phyc_url.get().strip()
        idcontact = self.var_phyc_id.get().strip()
        motdepasse = self.var_phyc_pwd.get()

        win = tk.Toplevel(self)
        win.title("Diagnostic connexion PHyC")
        win.geometry("780x520")

        ttk.Label(win, text="Résultats du diagnostic :").pack(anchor=tk.W, padx=10, pady=(8, 2))
        log_box = scrolledtext.ScrolledText(win, font=("Consolas", 9), state=tk.DISABLED, wrap=tk.WORD)
        log_box.pack(fill=tk.BOTH, expand=True, padx=10, pady=4)

        btn_frame = ttk.Frame(win)
        btn_frame.pack(fill=tk.X, padx=10, pady=(0, 8))
        btn_rel = ttk.Button(btn_frame, text="Relancer",
                              command=lambda: self._lancer_diagnostic(url, idcontact, motdepasse, log_box, btn_rel))
        btn_rel.pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="Copier",
                   command=lambda: self._copier_log(log_box)).pack(side=tk.LEFT, padx=6)
        ttk.Button(btn_frame, text="Fermer", command=win.destroy).pack(side=tk.RIGHT)
        self._lancer_diagnostic(url, idcontact, motdepasse, log_box, btn_rel)

    def _lancer_diagnostic(self, url, idcontact, motdepasse, log_box, btn):
        btn.config(state=tk.DISABLED)
        log_box.config(state=tk.NORMAL)
        log_box.delete("1.0", tk.END)
        log_box.config(state=tk.DISABLED)

        def log(msg):
            self.after(0, lambda m=msg: [
                log_box.config(state=tk.NORMAL),
                log_box.insert(tk.END, m + "\n"),
                log_box.see(tk.END),
                log_box.config(state=tk.DISABLED)])

        def worker():
            run_diagnostics(url, idcontact, motdepasse, log)
            self.after(0, lambda: btn.config(state=tk.NORMAL))

        threading.Thread(target=worker, daemon=True).start()

    def _copier_log(self, log_box):
        self.clipboard_clear()
        self.clipboard_append(log_box.get("1.0", tk.END))

    # -----------------------------------------------------------------------
    # Récupération info station PHyC
    # -----------------------------------------------------------------------

    def _recup_info_phyc(self):
        suffix = self.var_code_station_suffix.get().strip()
        nd = self._nb_digits
        if len(suffix) != nd:
            self._set_phyc_status(
                f"Code invalide : saisissez {nd} chiffres après {self._pfx_station} "
                f"(ex: {'027401001'[:nd]}). Actuellement {len(suffix)} caractère(s) saisi(s).", ok=False)
            return

        code_site  = self._pfx_station + suffix[:nd - 2]
        url        = self.var_phyc_url.get().strip()
        idcontact  = self.var_phyc_id.get().strip()
        motdepasse = self.var_phyc_pwd.get()

        manquants = [x for x, v in [("URL WSDL PHyC", url),
                                      ("Identifiant", idcontact),
                                      ("Mot de passe", motdepasse)] if not v]
        if manquants:
            self._set_phyc_status(
                f"Champs manquants : {', '.join(manquants)}.", ok=False)
            return

        self._set_phyc_status("Connexion à PHyC en cours...", ok=None)
        self.update_idletasks()

        def _worker():
            phyc = PhycClient(wsdl_url=url)
            try:
                phyc.login(idcontact, motdepasse)
            except PhycAuthError as e:
                self.after(0, lambda: self._set_phyc_status(f"Échec authentification : {e}", ok=False))
                return
            except Exception as e:
                self.after(0, lambda: self._set_phyc_status(
                    f"Connexion impossible : {e}\nVérifiez le RIE et l'URL.", ok=False))
                return

            libelle = libelle_err = None
            try:
                libelle = phyc.get_libelle_station(code_site)
            except Exception as e:
                libelle_err = str(e)
            finally:
                phyc.logout()

            if libelle:
                self.after(0, lambda: [
                    self.var_nom_station.set(libelle),
                    self._set_phyc_status(f"Connexion PHyC réussie. Libellé : {libelle}", ok=True)])
            else:
                detail = f" ({libelle_err})" if libelle_err else ""
                self.after(0, lambda: self._set_phyc_status(
                    f"Connexion réussie mais libellé non disponible pour '{code_site}'{detail}.\n"
                    f"Saisissez le libellé manuellement.", ok=True))

        threading.Thread(target=_worker, daemon=True).start()

    def _set_phyc_status(self, msg, ok):
        color = "#1D6A39" if ok is True else "#922B21" if ok is False else "#555555"
        self.var_phyc_status.set(msg)
        self.lbl_phyc_status.config(foreground=color)

    def _recup_seuils_phyc(self):
        """Récupère les seuils de vigilance depuis PHyC et pré-remplit les champs."""
        suffix = self.var_code_station_suffix.get().strip()
        nd = self._nb_digits
        if len(suffix) < nd - 2:
            self.var_seuil_status.set(f"Code station manquant ({nd} chiffres attendus).")
            return
        # Pour Q → code site (nd-2 chiffres) ; pour H → code station complet (nd chiffres)
        use_h = self.var_seuils_grandeur.get() == "H (m)"
        code_entite = self._pfx_station + suffix if use_h else self._pfx_station + suffix[:nd - 2]
        phyc_cfg = self.config_data.get("phyc", {})
        unite = "m" if use_h else "m³/s"
        self.var_seuil_status.set(f"Connexion PHyC en cours (seuils {unite})...")

        def _worker():
            try:
                phyc = PhycClient(wsdl_url=phyc_cfg.get("url", ""))
                phyc.login(phyc_cfg.get("idcontact", ""),
                           phyc_cfg.get("motdepasse", ""))
                seuils = phyc.get_seuils_vigilance(code_entite)
                phyc.logout()
                self.after(0, lambda s=seuils: self._fill_seuils(s))
            except Exception as e:
                self.after(0, lambda e=e:
                    self.var_seuil_status.set(f"Erreur : {e}"))

        threading.Thread(target=_worker, daemon=True).start()

    def _fill_seuils(self, seuils):
        """Pré-remplit les champs seuils avec les valeurs PHyC."""
        n = 0
        for key in ("zt_jaune", "jaune", "zt_orange", "orange", "zt_rouge", "rouge"):
            if key in seuils:
                self._var_seuils[key].set(f"{seuils[key]:.1f}")
                n += 1
        if n:
            self.var_seuil_status.set(f"{n} seuil(s) récupéré(s) depuis PHyC.")
        else:
            for key in ("zt_jaune", "jaune", "zt_orange", "orange", "zt_rouge", "rouge"):
                self._var_seuils[key].set("")
            self.var_seuil_status.set("Aucun seuil de vigilance disponible pour ce site — champs vidés.")

    def _on_seuils_grandeur_change(self):
        """Bascule l'affichage entre seuils Q (m³/s) et H (m)."""
        use_h = self.var_seuils_grandeur.get() == "H (m)"
        unit = "m" if use_h else "m³/s"
        for lbl in self._seuil_unit_labels:
            lbl.config(text=unit)
        # Recharger les valeurs depuis le bon jeu JSON
        if use_h:
            seuils = self.config_data.get("seuils_h", {})
        else:
            seuils = self.config_data.get("seuils_q",
                     self.config_data.get("seuils", {}))
        for key in ("zt_jaune", "jaune", "zt_orange", "orange", "zt_rouge", "rouge"):
            val = seuils.get(key, "")
            self._var_seuils[key].set(str(val) if val != "" else "")
        self.var_seuil_status.set("")

    def _appliquer_seuils(self):
        """Sauvegarde les seuils et rafraîchit la visualisation et la table épisodes."""
        seuils = {}
        for key in ("zt_jaune", "jaune", "zt_orange", "orange", "zt_rouge", "rouge"):
            txt = self._var_seuils[key].get().strip()
            if txt:
                try:
                    seuils[key] = float(txt)
                except ValueError:
                    pass
        seuils_key = "seuils_h" if self.var_seuils_grandeur.get() == "H (m)" else "seuils_q"
        self.config_data[seuils_key] = seuils
        # Rafraîchir le graphique courant si disponible
        ep = getattr(self, "_visu_current_ep", None)
        if ep and HAS_MPL:
            self._plot_episode(ep)
        # Rafraîchir la colonne Vig. max. de la table épisodes
        if self.episodes:
            self._refresh_episodes_table()
        self.var_seuil_status.set("Seuils appliqués à la visualisation.")

    # -----------------------------------------------------------------------
    # Extraction
    # -----------------------------------------------------------------------

    def _get_selected_episodes(self):
        idx_sel = {int(i) for i in self.tree.selection()}
        return [ep for ep in self.episodes if ep["index"] in idx_sel]

    def _run_extraction(self):
        episodes_sel = self._get_selected_episodes()
        if not episodes_sel:
            messagebox.showwarning("Aucun épisode",
                                   "Sélectionnez au moins un épisode dans l'onglet Épisodes.")
            return

        suffix_st = self.var_code_station_suffix.get().strip()
        nd = self._nb_digits
        if len(suffix_st) != nd:
            messagebox.showwarning("Code invalide",
                                   f"Saisissez {nd} chiffres pour le code station hydrométrie.")
            return

        suffix_bnbv = self.var_code_bnbv_suffix.get().strip()
        if not suffix_bnbv:
            messagebox.showwarning("Code BNBV manquant",
                                   "Saisissez le code BNBV dans l'onglet Configuration.")
            return

        options = {
            "pluies":           self.var_pluies.get(),
            "pdt_pluies":       PDT_PLUIES_OPTIONS.get(self.var_pdt_pluies.get(), 60),
            "pluies_panthere":  self.var_pluies_panthere.get(),
            "hu":               self.var_hu.get(),
            "pdt_hu":           "journalier_6h" if self.var_pdt_hu.get() == "1 jour à 6:00" else 60,
            "debits":           self.var_debits.get(),
            "pdt_debits":       PDT_DEBITS_OPTIONS.get(self.var_pdt_debits.get(), 15),
            "grandeur":         self.var_grandeur.get(),
        }
        # Sauvegarder les préférences d'extraction dans config
        self.config_data["extraction"] = {
            "pluies":          options["pluies"],
            "pdt_pluies":      options["pdt_pluies"],
            "pluies_panthere": options["pluies_panthere"],
            "hu":              options["hu"],
            "pdt_hu":          options["pdt_hu"],
            "debits":          options["debits"],
            "pdt_debits":      options["pdt_debits"],
            "grandeur":        options["grandeur"],
        }
        try:
            from modules.config_manager import save_config as _save_cfg
            _save_cfg(self.config_data)
        except Exception:
            pass
        if not any([options["pluies"], options["pluies_panthere"], options["hu"], options["debits"]]):
            messagebox.showwarning("Rien à extraire", "Cochez au moins une donnée à extraire.")
            return

        # Sync config from UI
        if "phyc"    not in self.config_data: self.config_data["phyc"]    = {}
        if "bdimage" not in self.config_data: self.config_data["bdimage"] = {}
        self.config_data["phyc"]["url"]        = self.var_phyc_url.get().strip()
        self.config_data["phyc"]["idcontact"]  = self.var_phyc_id.get().strip()
        self.config_data["phyc"]["motdepasse"] = self.var_phyc_pwd.get()
        self.config_data["bdimage"]["url"]     = self.var_bdi_url.get().strip()
        self.config_data["output_dir"]         = self.var_outdir.get().strip() or "./sorties"
        self.config_data["station"] = {
            "code_station": self._pfx_station + suffix_st,
            "code_site":    self._pfx_station + suffix_st[:self._nb_digits - 2],
            "code_bnbv":    self._pfx_bnbv + suffix_bnbv,
            "nom_station": self.var_nom_station.get().strip(),
            "ul": self.var_ul.get().strip(),
            "lr": self.var_lr.get().strip(),
        }

        self._stop_flag = False
        self.btn_run.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self.progress["value"] = 0
        self.progress["maximum"] = len(episodes_sel)
        self.lbl_status.config(text="Extraction en cours...", fg="#555555")
        self._log(f"Demarrage extraction - {len(episodes_sel)} episode(s)")

        def worker():
            errors = []
            synthese_text = ""
            try:
                errors, synthese_text = run_extraction(
                    config=self.config_data,
                    episodes=episodes_sel,
                    options=options,
                    log_fn=self._log,
                    progress_fn=self._update_progress,
                )
            except ExtractionError as e:
                self._log(f"\nErreur fatale : {e}")
                errors = [str(e)]
            except Exception as e:
                self._log(f"\nErreur inattendue : {e}")
                errors = [str(e)]
            finally:
                self.after(0, lambda e=errors, s=synthese_text:
                           self._extraction_done(e, s))

        self._extraction_thread = threading.Thread(target=worker, daemon=True)
        self._extraction_thread.start()

    def _stop_extraction(self):
        self._stop_flag = True
        self._log("\nArrêt demandé...")

    def _extraction_done(self, errors=None, synthese_text=""):
        errors = errors or []
        self.btn_run.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED)
        self.progress["value"] = self.progress["maximum"]

        if errors:
            self.lbl_status.config(
                text=f"Terminé — {len(errors)} erreur(s).", fg="#922B21")
            self._highlight_errors_in_log()
        else:
            self.lbl_status.config(text="Extraction réussie ✓", fg="#1D6A39")
            self._refresh_visu_list()
            self._notebook.select(self.tab_visu)

        if synthese_text:
            self._show_synthese_popup(synthese_text)

    def _show_synthese_popup(self, texte):
        """Fenêtre modale affichant la synthèse post-extraction."""
        pop = tk.Toplevel(self)
        pop.title("Synthèse des téléchargements")
        pop.resizable(True, True)
        pop.grab_set()          # modale
        pop.focus_set()

        tk.Label(pop, text="Synthèse des téléchargements",
                 bg="#1A5276", fg="white",
                 font=("TkDefaultFont", 10, "bold"),
                 pady=8).pack(fill=tk.X)

        txt = scrolledtext.ScrolledText(
            pop, width=62, height=22,
            font=("Courier", 9), wrap=tk.NONE,
            bg="#F8F9FA", relief="flat")
        txt.pack(fill=tk.BOTH, expand=True, padx=10, pady=8)
        txt.insert(tk.END, texte)
        txt.config(state=tk.DISABLED)

        tk.Button(pop, text="   OK   ",
                  bg="#1A5276", fg="white",
                  activebackground="#154360",
                  relief="flat", bd=0, pady=6,
                  font=("TkDefaultFont", 10, "bold"),
                  command=pop.destroy).pack(pady=(0, 10))

        # Centrer sur la fenêtre principale
        self.update_idletasks()
        x = self.winfo_x() + (self.winfo_width()  - pop.winfo_reqwidth())  // 2
        y = self.winfo_y() + (self.winfo_height() - pop.winfo_reqheight()) // 2
        pop.geometry(f"+{x}+{y}")

    def _highlight_errors_in_log(self):
        """Surligne en rouge les lignes contenant une erreur dans le journal."""
        self.log_text.config(state=tk.NORMAL)
        content = self.log_text.get("1.0", tk.END)
        for i, line in enumerate(content.splitlines(), 1):
            low = line.lower()
            if "erreur" in low or "error" in low or "echec" in low:
                self.log_text.tag_add("erreur", f"{i}.0", f"{i}.end")
        self.log_text.config(state=tk.DISABLED)

    def _update_progress(self, done, total):
        self.after(0, lambda: self.progress.config(value=done))

    # -----------------------------------------------------------------------
    # Journal
    # -----------------------------------------------------------------------

    def _log(self, msg):
        def _do():
            self.log_text.config(state=tk.NORMAL)
            self.log_text.insert(tk.END, msg + "\n")
            self.log_text.see(tk.END)
            self.log_text.config(state=tk.DISABLED)
        self.after(0, _do)

    def _clear_log(self):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.config(state=tk.DISABLED)


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Garantit que les chemins relatifs (./sorties, config/) sont résolus
    # depuis le répertoire de main.py, quel que soit le CWD de lancement.
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    app = App()
    app.mainloop()
