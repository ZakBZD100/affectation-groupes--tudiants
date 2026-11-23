"""Onglet « Explorateur » : consulter les 27 instances déjà résolues."""
from __future__ import annotations

import csv
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .chemins import chemin_exports

COLONNES_VUES = (
    ("nom", "Instance", 190),
    ("effectif", "n", 55),
    ("categorie", "Catégorie", 90),
    ("statut", "Statut", 100),
    ("k_total", "k", 45),
    ("score", "Score", 90),
    ("score_evaluateur", "Score éval.", 95),
    ("f3_norm", "f3 normé", 85),
    ("gap", "Gap", 80),
    ("delta_score_greedy", "Δ greedy", 90),
)


def lire_csv(chemin):
    with open(chemin, "r", encoding="utf-8-sig", newline="") as fichier:
        return list(csv.DictReader(fichier))


class ExplorateurFrame(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent, padding=8)
        self.lignes = []
        self.etudiants = []
        self.chemin_instances = None
        self._construire()
        self.charger(chemin_exports())

    def _construire(self):
        haut = ttk.Frame(self)
        haut.pack(fill="x", pady=(0, 6))
        ttk.Label(haut, text="Fichier :").pack(side="left")
        self.chemin_var = tk.StringVar(value="")
        ttk.Label(haut, textvariable=self.chemin_var).pack(side="left", padx=(6, 10))
        ttk.Button(haut, text="Choisir un autre CSV…", command=self.choisir).pack(side="left")
        self.info = ttk.Label(haut, text="")
        self.info.pack(side="right")

        haut_table = ttk.Frame(self)
        haut_table.pack(fill="both", expand=True)
        colonnes = tuple(c[0] for c in COLONNES_VUES)
        self.arbre = ttk.Treeview(haut_table, columns=colonnes, show="headings", height=11)
        for cle, titre, largeur in COLONNES_VUES:
            self.arbre.heading(cle, text=titre)
            self.arbre.column(cle, width=largeur, anchor="w")
        barre = ttk.Scrollbar(haut_table, orient="vertical", command=self.arbre.yview)
        self.arbre.configure(yscrollcommand=barre.set)
        self.arbre.pack(side="left", fill="both", expand=True)
        barre.pack(side="right", fill="y")
        self.arbre.bind("<<TreeviewSelect>>", self._selection)

        bas = ttk.PanedWindow(self, orient="horizontal")
        bas.pack(fill="both", expand=True, pady=(8, 0))
        detail = ttk.LabelFrame(bas, text="Détail de l'instance", padding=4)
        liste = ttk.LabelFrame(bas, text="Étudiants de l'instance", padding=4)
        bas.add(detail, weight=1)
        bas.add(liste, weight=1)
        self.texte = tk.Text(detail, wrap="word", height=11)
        self.texte.pack(fill="both", expand=True)
        self.texte.config(state="disabled")

        cadre = ttk.Frame(liste)
        cadre.pack(fill="both", expand=True)
        self.arbre_etudiants = ttk.Treeview(
            cadre,
            columns=("id", "lv2", "statut", "groupe_lv2", "groupe_tp", "groupe_td"),
            show="headings",
            height=11,
        )
        for cle, titre, largeur in (
            ("id", "id", 45),
            ("lv2", "LV2", 95),
            ("statut", "Statut", 85),
            ("groupe_lv2", "Groupe LV2", 130),
            ("groupe_tp", "Groupe TP", 120),
            ("groupe_td", "Groupe TD", 120),
        ):
            self.arbre_etudiants.heading(cle, text=titre)
            self.arbre_etudiants.column(cle, width=largeur, anchor="w")
        barre_e = ttk.Scrollbar(cadre, orient="vertical", command=self.arbre_etudiants.yview)
        self.arbre_etudiants.configure(yscrollcommand=barre_e.set)
        self.arbre_etudiants.pack(side="left", fill="both", expand=True)
        barre_e.pack(side="right", fill="y")

    def charger(self, dossier):
        chemin = os.path.join(dossier, "instances.csv")
        if not os.path.isfile(chemin):
            self.info.config(text="exports/instances.csv introuvable")
            return
        try:
            self.lignes = lire_csv(chemin)
            chemin_e = os.path.join(dossier, "etudiants.csv")
            self.etudiants = lire_csv(chemin_e) if os.path.isfile(chemin_e) else []
        except Exception as erreur:
            messagebox.showerror("Explorateur", str(erreur), parent=self)
            return
        self.chemin_instances = chemin
        self.chemin_var.set(chemin)
        self.info.config(text="%d instance(s)" % len(self.lignes))
        self.arbre.delete(*self.arbre.get_children())
        for index, ligne in enumerate(self.lignes):
            self.arbre.insert(
                "",
                "end",
                iid=str(index),
                values=tuple(ligne.get(cle, "") for cle, *_ in COLONNES_VUES),
            )

    def choisir(self):
        chemin = filedialog.askopenfilename(
            parent=self,
            title="Fichier instances.csv",
            filetypes=(("CSV", "*.csv"), ("Tous", "*.*")),
        )
        if chemin:
            self.charger(os.path.dirname(chemin))

    def _selection(self, _evenement=None):
        selection = self.arbre.selection()
        if not selection:
            return
        ligne = self.lignes[int(selection[0])]
        self.texte.config(state="normal")
        self.texte.delete("1.0", "end")
        self.texte.insert(
            "1.0",
            "\n".join("%-24s %s" % (cle + " :", valeur) for cle, valeur in ligne.items()),
        )
        self.texte.config(state="disabled")

        nom = ligne.get("nom", "")
        self.arbre_etudiants.delete(*self.arbre_etudiants.get_children())
        for e in self.etudiants:
            if e.get("instance") != nom:
                continue
            self.arbre_etudiants.insert(
                "",
                "end",
                values=(
                    e.get("id", ""),
                    e.get("lv2", ""),
                    e.get("statut", ""),
                    e.get("groupe_lv2", ""),
                    e.get("groupe_tp", ""),
                    e.get("groupe_td", ""),
                ),
            )
