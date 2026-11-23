"""Onglet « Données » : saisie manuelle, import CSV et génération reproductible.

Toutes les instances produites ici sont des ``generateur_instances.Instance``
figées : l'appelant peut donc les passer directement au solveur et à l'export.
"""
from __future__ import annotations

import csv
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .chemins import RACINE  # noqa: F401  (configure sys.path)
from generateur_instances import (
    Etudiant,
    Instance,
    generer_instance,
    generer_instances_extremes,
    generer_lot,
)

LANGUES = ("Allemand", "Espagnol", "Autre")
STATUTS = ("normal", "cesure", "redoublant")
VRAI = ("1", "true", "vrai", "oui", "yes", "t")


def _booleen(valeur):
    if isinstance(valeur, bool):
        return valeur
    if isinstance(valeur, (int, float)):
        return bool(valeur)
    return str(valeur).strip().lower() in VRAI


def instance_depuis_lignes(lignes, nom="saisie_manuelle", seed=0):
    """Construit une `Instance` figée à partir de lignes d'étudiants.

    Les ids sont assignés de 1 à n (contrat de `Instance`). `lignes` est une
    séquence de dictionnaires avec au minimum ``lv2`` ; ``statut`` et
    ``choix_tardif`` sont optionnels.
    """
    lignes = list(lignes)
    if not lignes:
        raise ValueError("au moins un étudiant est nécessaire")
    etudiants = []
    for index, ligne in enumerate(lignes, 1):
        lv2 = str(ligne.get("lv2", "")).strip()
        if lv2 not in LANGUES:
            raise ValueError(f"LV2 inconnue à la ligne {index}: {lv2!r}")
        statut = str(ligne.get("statut", "normal") or "normal").strip()
        if statut not in STATUTS:
            raise ValueError(f"statut inconnu à la ligne {index}: {statut!r}")
        etudiants.append(Etudiant(index, lv2, _booleen(ligne.get("choix_tardif")), statut))
    comptes = {}
    for e in etudiants:
        comptes[e.lv2] = comptes.get(e.lv2, 0) + 1
    distribution = tuple(
        (langue, count / len(etudiants)) for langue, count in comptes.items()
    )
    return Instance(
        nom=nom,
        seed=int(seed),
        n=len(etudiants),
        distribution=distribution,
        etudiants=tuple(etudiants),
    )


def _cle_nettoyee(texte):
    return (
        str(texte)
        .strip()
        .lower()
        .replace("é", "e")
        .replace("è", "e")
        .replace(" ", "_")
        .replace("-", "_")
    )


ALIAS = {
    "id": "id",
    "lv2": "lv2",
    "langue": "lv2",
    "choix": "lv2",
    "statut": "statut",
    "status": "statut",
    "choix_tardif": "choix_tardif",
    "choixtardif": "choix_tardif",
    "tardif": "choix_tardif",
}


def lire_csv_etudiants(chemin):
    """Lit unCSV d'étudiants (BOM UTF-8 accepté) et retourne des lignes propres."""
    with open(chemin, "r", encoding="utf-8-sig", newline="") as fichier:
        lecteur = csv.DictReader(fichier)
        if not lecteur.fieldnames:
            raise ValueError("fichier CSV vide ou sans en-tête")
        colonnes = {}
        for brut in lecteur.fieldnames:
            nettoye = _cle_nettoyee(brut)
            if nettoye in ALIAS:
                colonnes[brut] = ALIAS[nettoye]
        if "lv2" not in colonnes.values():
            raise ValueError(
                "colonne LV2 introuvable (attendu: id, lv2, statut, choix_tardif)"
            )
        lignes = []
        for numero, brute in enumerate(lecteur, 2):
            ligne = {colonnes[c]: v for c, v in brute.items() if c in colonnes}
            ligne.setdefault("statut", "normal")
            ligne.setdefault("choix_tardif", False)
            ligne["_ligne"] = numero
            lignes.append(ligne)
    return lignes


class DonneesFrame(ttk.LabelFrame):
    """Sélection de la source de données et aperçu."""

    def __init__(self, parent, on_change=None):
        super().__init__(parent, text=" 1. Données étudiants ", padding=8)
        self.on_change = on_change
        self.source = tk.StringVar(value="manuel")
        self.lignes = []
        self._chemin_csv = None
        self._instances_generees = []
        self._construire()

    # ---------- construction ----------
    def _construire(self):
        barre = ttk.Frame(self)
        barre.pack(fill="x", pady=(0, 8))
        for texte, valeur in (
            ("Saisie manuelle", "manuel"),
            ("Import CSV", "csv"),
            ("Génération aléatoire", "genere"),
        ):
            ttk.Radiobutton(
                barre,
                text=texte,
                variable=self.source,
                value=valeur,
                command=self._changer_source,
            ).pack(side="left", padx=(0, 14))

        self.stack = ttk.Frame(self)
        self.stack.pack(fill="both", expand=True)
        self.manuel = ttk.Frame(self.stack)
        self.csv = ttk.Frame(self.stack)
        self.genere = ttk.Frame(self.stack)
        for cadre in (self.manuel, self.csv, self.genere):
            cadre.grid(row=0, column=0, sticky="nsew")
        self.stack.rowconfigure(0, weight=1)
        self.stack.columnconfigure(0, weight=1)

        self._construire_manuel()
        self._construire_csv()
        self._construire_genere()
        self._changer_source()

    def _construire_manuel(self):
        haut = ttk.Frame(self.manuel)
        haut.pack(fill="x", pady=(0, 6))
        ttk.Label(haut, text="LV2 :").pack(side="left")
        self.lv2_var = tk.StringVar(value=LANGUES[0])
        ttk.Combobox(
            haut, textvariable=self.lv2_var, values=LANGUES, state="readonly", width=12
        ).pack(side="left", padx=(4, 12))
        ttk.Label(haut, text="Statut :").pack(side="left")
        self.statut_var = tk.StringVar(value=STATUTS[0])
        ttk.Combobox(
            haut, textvariable=self.statut_var, values=STATUTS, state="readonly", width=12
        ).pack(side="left", padx=(4, 12))
        self.tardif_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(haut, text="Choix tardif", variable=self.tardif_var).pack(side="left")

        actions = ttk.Frame(self.manuel)
        actions.pack(fill="x", pady=(0, 6))
        for texte, commande in (
            ("Ajouter", self.ajouter_ligne),
            ("Modifier la sélection", self.modifier_ligne),
            ("Supprimer", self.supprimer_ligne),
            ("Vider", self.vider_lignes),
            ("Coller un tableau…", self.coller_tableau),
        ):
            ttk.Button(actions, text=texte, command=commande).pack(side="left", padx=(0, 6))

        colonnes = ("id", "lv2", "statut", "choix_tardif")
        self.arbre = self._arbre(self.manuel, colonnes, {"id": 50, "lv2": 110, "statut": 100, "choix_tardif": 100})
        self.arbre.bind("<Double-1>", self._charger_selection)
        self.info_manuel = ttk.Label(self.manuel, text="0 étudiant")
        self.info_manuel.pack(anchor="w", pady=(4, 0))

    def _construire_csv(self):
        haut = ttk.Frame(self.csv)
        haut.pack(fill="x", pady=(0, 6))
        ttk.Button(haut, text="Choisir un CSV…", command=self.choisir_csv).pack(side="left")
        self.chemin_csv = tk.StringVar(value="Aucun fichier")
        ttk.Label(haut, textvariable=self.chemin_csv).pack(side="left", padx=(8, 0))
        self.info_csv = ttk.Label(self.csv, text="Colonnes attendues : id, lv2, statut, choix_tardif")
        self.info_csv.pack(anchor="w", pady=(0, 6))
        self.arbre_csv = self._arbre(
            self.csv,
            ("ligne", "id", "lv2", "statut", "choix_tardif"),
            {"ligne": 60, "id": 60, "lv2": 110, "statut": 100, "choix_tardif": 100},
        )

    def _construire_genere(self):
        haut = ttk.Frame(self.genere)
        haut.pack(fill="x", pady=(0, 6))
        ttk.Label(haut, text="Mode :").pack(side="left")
        self.mode_genre = tk.StringVar(value="Unitaire")
        ttk.Combobox(
            haut,
            textvariable=self.mode_genre,
            values=("Unitaire", "Lot", "Extrêmes"),
            state="readonly",
            width=12,
        ).pack(side="left", padx=(4, 16))
        ttk.Label(haut, text="Graine :").pack(side="left")
        self.graine_gen = tk.StringVar(value="7")
        ttk.Entry(haut, textvariable=self.graine_gen, width=12).pack(side="left", padx=(4, 16))
        ttk.Label(haut, text="n :").pack(side="left")
        self.n_gen = tk.StringVar(value="80")
        ttk.Spinbox(haut, from_=50, to=100, textvariable=self.n_gen, width=6).pack(side="left", padx=4)
        ttk.Button(haut, text="Générer", command=self.generer).pack(side="left", padx=(16, 0))

        options = ttk.Frame(self.genere)
        options.pack(fill="x", pady=(0, 6))
        self.cas_gen = tk.BooleanVar(value=True)
        ttk.Checkbutton(options, text="Cas particuliers", variable=self.cas_gen).pack(side="left")
        ttk.Label(options, text="Part de choix tardifs :").pack(side="left", padx=(16, 4))
        self.tardif_gen = tk.DoubleVar(value=0.15)
        ttk.Scale(
            options,
            from_=0.0,
            to=1.0,
            variable=self.tardif_gen,
            orient="horizontal",
            length=140,
        ).pack(side="left")

        bas = ttk.Frame(self.genere)
        bas.pack(fill="x")
        ttk.Label(bas, text="Instances générées :").pack(side="left")
        self.liste_gen = ttk.Combobox(bas, state="readonly", width=42)
        self.liste_gen.pack(side="left", padx=(6, 0))
        self.liste_gen.bind("<<ComboboxSelected>>", lambda _e: self._notifier())
        self.info_gen = ttk.Label(self.genere, text="")
        self.info_gen.pack(anchor="w", pady=(6, 0))

    @staticmethod
    def _arbre(parent, colonnes, largeurs):
        cadre = ttk.Frame(parent)
        cadre.pack(fill="both", expand=True)
        arbre = ttk.Treeview(cadre, columns=colonnes, show="headings", height=10)
        for col in colonnes:
            arbre.heading(col, text=col)
            arbre.column(col, width=largeurs.get(col, 90), anchor="w")
        barre = ttk.Scrollbar(cadre, orient="vertical", command=arbre.yview)
        arbre.configure(yscrollcommand=barre.set)
        arbre.pack(side="left", fill="both", expand=True)
        barre.pack(side="right", fill="y")
        return arbre

    # ---------- actions ----------
    def _notifier(self):
        if self.on_change:
            self.on_change()

    def _changer_source(self):
        cadre = {"manuel": self.manuel, "csv": self.csv, "genere": self.genere}[
            self.source.get()
        ]
        cadre.tkraise()
        self._notifier()

    def _ligne_courante(self):
        return {
            "lv2": self.lv2_var.get(),
            "statut": self.statut_var.get(),
            "choix_tardif": self.tardif_var.get(),
        }

    def _rafraichir_manuel(self):
        self.arbre.delete(*self.arbre.get_children())
        for index, ligne in enumerate(self.lignes, 1):
            self.arbre.insert(
                "",
                "end",
                iid=str(index),
                values=(
                    index,
                    ligne["lv2"],
                    ligne["statut"],
                    "oui" if ligne["choix_tardif"] else "non",
                ),
            )
        self.info_manuel.config(
            text="%d étudiant(s) — double-cliquez une ligne pour la modifier"
            % len(self.lignes)
        )
        self._notifier()

    def ajouter_ligne(self):
        self.lignes.append(self._ligne_courante())
        self._rafraichir_manuel()

    def _charger_selection(self, _evenement=None):
        selection = self.arbre.selection()
        if not selection:
            return
        ligne = self.lignes[int(selection[0]) - 1]
        self.lv2_var.set(ligne["lv2"])
        self.statut_var.set(ligne["statut"])
        self.tardif_var.set(ligne["choix_tardif"])

    def modifier_ligne(self):
        selection = self.arbre.selection()
        if not selection:
            messagebox.showinfo("Modifier", "Sélectionnez d'abord une ligne.", parent=self)
            return
        self.lignes[int(selection[0]) - 1] = self._ligne_courante()
        self._rafraichir_manuel()

    def supprimer_ligne(self):
        selection = self.arbre.selection()
        if not selection:
            return
        for iid in sorted(selection, reverse=True):
            del self.lignes[int(iid) - 1]
        self._rafraichir_manuel()

    def vider_lignes(self):
        self.lignes.clear()
        self._rafraichir_manuel()

    def coller_tableau(self):
        fenetre = tk.Toplevel(self)
        fenetre.title("Coller un tableau")
        fenetre.transient(self.winfo_toplevel())
        ttk.Label(
            fenetre,
            text="Une ligne par étudiant : lv2, statut, choix_tardif\nséparateurs : virgule, point-virgule ou tabulation",
        ).pack(anchor="w", padx=10, pady=(10, 4))
        texte = tk.Text(fenetre, width=52, height=12)
        texte.pack(padx=10, pady=4)

        def valider():
            ajoutes = 0
            for ligne in texte.get("1.0", "end").splitlines():
                if not ligne.strip():
                    continue
                morceaux = [m.strip() for m in ligne.replace("\t", ",").replace(";", ",").split(",")]
                if not morceaux or morceaux[0] not in LANGUES:
                    continue
                self.lignes.append(
                    {
                        "lv2": morceaux[0],
                        "statut": morceaux[1] if len(morceaux) > 1 and morceaux[1] in STATUTS else "normal",
                        "choix_tardif": _booleen(morceaux[2]) if len(morceaux) > 2 else False,
                    }
                )
                ajoutes += 1
            fenetre.destroy()
            self.source.set("manuel")
            self._changer_source()
            self._rafraichir_manuel()
            messagebox.showinfo("Collage", "%d étudiant(s) ajouté(s)." % ajoutes, parent=self)

        ttk.Button(fenetre, text="Ajouter", command=valider).pack(pady=(0, 10))

    def choisir_csv(self):
        chemin = filedialog.askopenfilename(
            parent=self,
            title="Importer un CSV d'étudiants",
            filetypes=(("CSV", "*.csv"), ("Tous", "*.*")),
        )
        if not chemin:
            return
        try:
            lignes = lire_csv_etudiants(chemin)
        except Exception as erreur:
            messagebox.showerror("Import CSV", str(erreur), parent=self)
            return
        self._chemin_csv = chemin
        self.arbre_csv.delete(*self.arbre_csv.get_children())
        for ligne in lignes[:200]:
            self.arbre_csv.insert(
                "",
                "end",
                values=(
                    ligne["_ligne"],
                    ligne.get("id", ""),
                    ligne["lv2"],
                    ligne["statut"],
                    "oui" if _booleen(ligne["choix_tardif"]) else "non",
                ),
            )
        self.chemin_csv.set(os.path.basename(chemin))
        self.info_csv.config(text="%d étudiant(s) importé(s)" % len(lignes))
        self._notifier()

    def generer(self):
        try:
            graine = int(self.graine_gen.get())
            n = int(self.n_gen.get())
            mode = self.mode_genre.get()
            if mode == "Unitaire":
                self._instances_generees = [
                    generer_instance(
                        n=n,
                        seed=graine,
                        avec_cas_particuliers=self.cas_gen.get(),
                        frac_choix_tardif=self.tardif_gen.get(),
                    )
                ]
            elif mode == "Lot":
                self._instances_generees = list(generer_lot(nb=max(1, min(50, n)), seed=graine))
            else:
                self._instances_generees = list(generer_instances_extremes(seed=0))
        except Exception as erreur:
            messagebox.showerror("Génération", str(erreur), parent=self)
            return
        self.liste_gen.config(values=[i.nom for i in self._instances_generees])
        if self._instances_generees:
            self.liste_gen.current(0)
        self.info_gen.config(
            text="%d instance(s) — graine blake2b, identique au générateur du projet"
            % len(self._instances_generees)
        )
        self._notifier()

    # ---------- API ----------
    def get_instance(self):
        """Retourne l'`Instance` sélectionnée, ou lève `ValueError`."""
        source = self.source.get()
        if source == "manuel":
            return instance_depuis_lignes(self.lignes)
        if source == "csv":
            if not self._chemin_csv:
                raise ValueError("choisissez un fichier CSV")
            lignes = lire_csv_etudiants(self._chemin_csv)
            return instance_depuis_lignes(lignes, nom="import_csv", seed=0)
        if not self._instances_generees or not self.liste_gen.get():
            raise ValueError("générez d'abord une instance")
        return self._instances_generees[self.liste_gen.current()]

    def get_chemin_csv(self):
        return self.chemin_csv.get()

    def get_instances_generees(self):
        """Retourne les instances générées, pour la liste du mode pluriel."""
        return list(self._instances_generees)
