"""Onglet « Résolution lots » : mode unitaire ou pluriel.

* **Unitaire** : résout l'instance définie dans l'onglet Données (une seule).
* **Pluriel** : coche les 27 instances du dépôt et/ou les instances générées,
  puis résout la sélection et affiche un tableau synthétique. Un clic sur une
  ligne ouvre le détail dans l'onglet Résultats.
"""
from __future__ import annotations

import os
import queue
import threading
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .instances import lire_instances_precalculees
from .resultats import exporter_solutions
from .solution import resoudre_lots

COLONNES_LOT = (
    ("nom", "Instance", 210),
    ("source", "Source", 110),
    ("n", "n", 50),
    ("statut", "Statut", 100),
    ("score", "Score", 85),
    ("f1_norm", "f1 normé", 85),
    ("f2_norm", "f2 normé", 85),
    ("f3_norm", "f3 normé", 85),
    ("k", "k", 45),
    ("gap", "Gap", 80),
    ("temps_s", "Temps (s)", 85),
    ("delta", "Δ greedy", 90),
)


class ResolutionLotsFrame(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=8)
        self.app = app
        self.mode = tk.StringVar(value="unitaire")
        self.info_liste = tk.StringVar(value="")
        self.candidats = []
        self.vars = []
        self.selection_etat = {}
        self.solutions = []
        self.file = queue.Queue()
        self._en_cours = False
        self._annuler = threading.Event()
        self._construire()
        self.actualiser()
        self.actualiser_unitaire()

    # ------------------------------------------------------------------ UI
    def _construire(self):
        haut = ttk.Frame(self)
        haut.pack(fill="x", pady=(0, 8))
        ttk.Label(
            haut, text="Mode de résolution :", font=("TkDefaultFont", 10, "bold")
        ).pack(side="left")
        for texte, valeur in (
            ("Unitaire — 1 instance", "unitaire"),
            ("Pluriel — plusieurs instances", "pluriel"),
        ):
            ttk.Radiobutton(
                haut,
                text=texte,
                variable=self.mode,
                value=valeur,
                command=self._changer_mode,
            ).pack(side="left", padx=(14, 0))

        # --- mode unitaire ------------------------------------------------
        self.cadre_unitaire = ttk.LabelFrame(self, text="Instance courante", padding=8)
        self.cadre_unitaire.pack(fill="x")
        self.resume_unitaire = ttk.Label(
            self.cadre_unitaire, text="…", wraplength=950, justify="left"
        )
        self.resume_unitaire.pack(anchor="w")
        actions_u = ttk.Frame(self.cadre_unitaire)
        actions_u.pack(fill="x", pady=(8, 0))
        ttk.Button(
            actions_u,
            text="Voir / modifier les données",
            command=lambda: self.app.notebook.select(self.app.donnees),
        ).pack(side="left")
        ttk.Button(
            actions_u, text="Résoudre cette instance", command=self.app.resoudre
        ).pack(side="left", padx=(8, 0))

        # --- mode pluriel --------------------------------------------------
        self.cadre_pluriel = ttk.LabelFrame(self, text="Instances à résoudre", padding=8)
        outils = ttk.Frame(self.cadre_pluriel)
        outils.pack(fill="x", pady=(0, 6))
        ttk.Button(outils, text="Actualiser la liste", command=self.actualiser).pack(
            side="left"
        )
        ttk.Button(
            outils, text="Tout cocher", command=lambda: self._cocher(True)
        ).pack(side="left", padx=(6, 0))
        ttk.Button(
            outils, text="Tout décocher", command=lambda: self._cocher(False)
        ).pack(side="left", padx=(6, 0))
        ttk.Label(outils, textvariable=self.info_liste).pack(side="right")

        zone = ttk.Frame(self.cadre_pluriel)
        zone.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(zone, height=180, highlightthickness=0)
        barre = ttk.Scrollbar(zone, orient="vertical", command=self.canvas.yview)
        self.liste_frame = ttk.Frame(self.canvas)
        self.liste_frame.bind(
            "<Configure>",
            lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )
        self.canvas.create_window((0, 0), window=self.liste_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=barre.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        barre.pack(side="right", fill="y")
        for widget in (self.canvas, self.liste_frame):
            widget.bind("<MouseWheel>", self._molette)
        self.source_par_nom = {}

        actions = ttk.Frame(self.cadre_pluriel)
        actions.pack(fill="x", pady=(8, 4))
        self.bouton_resoudre = ttk.Button(
            actions, text="Résoudre la sélection", command=self.resoudre_selection
        )
        self.bouton_resoudre.pack(side="left")
        self.bouton_annuler = ttk.Button(
            actions, text="Annuler", command=self.annuler, state="disabled"
        )
        self.bouton_annuler.pack(side="left", padx=(6, 0))
        ttk.Button(
            actions,
            text="Exporter les 3 CSV (résolus)…",
            command=self.exporter,
        ).pack(side="left", padx=(6, 0))
        self.progression = ttk.Progressbar(
            actions, orient="horizontal", length=180, mode="determinate"
        )
        self.progression.pack(side="right")
        self.info_progression = ttk.Label(self.cadre_pluriel, text="Prêt.")
        self.info_progression.pack(anchor="w")

        # --- tableau synthétique ------------------------------------------
        self.tableau_frame = ttk.LabelFrame(self, text="Résultats du lot", padding=6)
        cadre_arbre = ttk.Frame(self.tableau_frame)
        cadre_arbre.pack(fill="both", expand=True)
        colonnes = tuple(c[0] for c in COLONNES_LOT)
        self.arbre = ttk.Treeview(
            cadre_arbre, columns=colonnes, show="headings", height=9
        )
        for cle, titre, largeur in COLONNES_LOT:
            self.arbre.heading(cle, text=titre)
            self.arbre.column(cle, width=largeur, anchor="w")
        barre_arbre = ttk.Scrollbar(
            cadre_arbre, orient="vertical", command=self.arbre.yview
        )
        self.arbre.configure(yscrollcommand=barre_arbre.set)
        self.arbre.pack(side="left", fill="both", expand=True)
        barre_arbre.pack(side="right", fill="y")
        self.arbre.bind("<<TreeviewSelect>>", self._afficher_detail)
        ttk.Label(
            self.tableau_frame,
            text="Double-cliquez ou sélectionnez une ligne pour voir le détail des affectations.",
        ).pack(anchor="w", pady=(4, 0))

    def _molette(self, evenement):
        self.canvas.yview_scroll(int(-1 * (evenement.delta / 120)), "units")

    def _changer_mode(self):
        if self.mode.get() == "unitaire":
            self.cadre_pluriel.pack_forget()
            self.tableau_frame.pack_forget()
            self.cadre_unitaire.pack(fill="x")
            self.actualiser_unitaire()
        else:
            self.cadre_unitaire.pack_forget()
            self.cadre_pluriel.pack(fill="both", expand=True)
            self.tableau_frame.pack(fill="both", expand=True, pady=(8, 0))
            self.actualiser()

    # -------------------------------------------------------------- données
    def actualiser_unitaire(self):
        """Met à jour le récapitulatif de l'instance du mode unitaire."""
        if self._en_cours or self.app.donnees is None:
            return
        try:
            instance = self.app.donnees.get_instance()
            profil = self.app.parametres.profil.get()
            self.resume_unitaire.config(
                text=(
                    "Source : %s   |   Nom : %s   |   Effectif : %d étudiants"
                    "   |   Graine : %s   |   Profil : %s"
                )
                % (
                    self.app.donnees.source.get(),
                    instance.nom,
                    instance.n,
                    instance.seed,
                    profil,
                )
            )
        except Exception as erreur:
            self.resume_unitaire.config(text="Aucune instance prête : %s" % erreur)

    def actualiser(self):
        """Reconstruit la liste à cocher (27 instances + instances générées)."""
        if self._en_cours or self.app.donnees is None:
            return
        candidats = list(lire_instances_precalculees())
        for instance in self.app.donnees.get_instances_generees():
            candidats.append(
                {"instance": instance, "meta": {}, "source": "générée"}
            )
        vus = set()
        self.candidats = []
        for candidat in candidats:
            nom = candidat["instance"].nom
            if nom in vus:
                continue
            vus.add(nom)
            self.candidats.append(candidat)

        for enfant in self.liste_frame.winfo_children():
            enfant.destroy()
        ttk.Style(self).configure("Lot.TCheckbutton", font=("Consolas", 9))
        self.vars = []
        for candidat in self.candidats:
            instance = candidat["instance"]
            nom = instance.nom
            var = tk.BooleanVar(
                value=self.selection_etat.get(nom, True)
            )
            var.trace_add(
                "write", lambda *_e, n=nom, v=var: self._selection_changee(n, v)
            )
            score = candidat["meta"].get("score", "—")
            libelle = "%-38s  n=%-4s  %-12s  score %s" % (
                nom[:38],
                instance.n,
                candidat["source"][:12],
                score,
            )
            case = ttk.Checkbutton(
                self.liste_frame,
                text=libelle,
                variable=var,
                style="Lot.TCheckbutton",
            )
            case.pack(fill="x", anchor="w")
            case.bind("<MouseWheel>", self._molette)
            self.vars.append(var)
        self.source_par_nom = {
            c["instance"].nom: c["source"] for c in self.candidats
        }
        self._maj_compteur()

    def _selection_changee(self, nom, var):
        self.selection_etat[nom] = bool(var.get())
        self._maj_compteur()

    def _maj_compteur(self):
        nb = sum(1 for v in self.vars if v.get())
        self.info_liste.set("%d / %d sélectionnée(s)" % (nb, len(self.vars)))

    def _cocher(self, valeur):
        for var in self.vars:
            var.set(valeur)

    # ------------------------------------------------------------ résolution
    def resoudre_selection(self):
        if self._en_cours:
            return
        selection = [
            c["instance"] for c, v in zip(self.candidats, self.vars) if v.get()
        ]
        if not selection:
            messagebox.showinfo(
                "Résolution lots", "Cochez au moins une instance.", parent=self
            )
            return
        try:
            params = self.app.parametres.get()
        except Exception as erreur:
            messagebox.showerror("Paramètres", str(erreur), parent=self)
            return

        self._en_cours = True
        self._annuler.clear()
        self.solutions = []
        self.arbre.delete(*self.arbre.get_children())
        self.bouton_resoudre.config(state="disabled")
        self.bouton_annuler.config(state="normal")
        self.progression.config(maximum=len(selection), value=0)
        self.info_progression.config(text="0 / %d…" % len(selection))
        self.update_idletasks()
        threading.Thread(
            target=self._travail, args=(selection, params), daemon=True
        ).start()
        self.after(120, self._verifier_file)

    def _travail(self, instances, params):
        """Thread : ne touche jamais aux widgets Tkinter."""

        def progression(index, total, instance, solution):
            self.file.put(("progression", (index, total, instance, solution)))

        try:
            solutions = resoudre_lots(
                instances,
                params,
                progression=progression,
                annuler=self._annuler.is_set,
            )
            self.file.put(("ok", solutions))
        except Exception:
            self.file.put(("erreur", traceback.format_exc()))

    def annuler(self):
        if self._en_cours:
            self._annuler.set()
            self.info_progression.config(text="Annulation après l'instance en cours…")

    def _verifier_file(self):
        try:
            genre, contenu = self.file.get_nowait()
        except queue.Empty:
            self.after(120, self._verifier_file)
            return

        if genre == "progression":
            index, total, instance, solution = contenu
            self.solutions.append(solution)
            self.progression.config(value=index)
            statut = solution.get("ind", {}).get("statut", "?")
            self.info_progression.config(
                text="%d / %d — %s : %s" % (index, total, instance.nom, statut)
            )
            self._inserer_ligne(solution)
            self.after(120, self._verifier_file)
            return

        self._en_cours = False
        self.bouton_resoudre.config(state="normal")
        self.bouton_annuler.config(state="disabled")
        if genre == "erreur":
            messagebox.showerror("Résolution lots", contenu, parent=self)
            return
        self.solutions = contenu
        self.info_progression.config(
            text="Terminé : %d instance(s) résolue(s)." % len(self.solutions)
        )

    @staticmethod
    def _formater(valeur):
        if isinstance(valeur, float):
            return "%.4f" % valeur
        return "" if valeur is None else str(valeur)

    def _inserer_ligne(self, solution):
        ind = solution.get("ind", {})
        valeurs = (
            solution["instance"].nom,
            self.source_par_nom.get(solution["instance"].nom, ""),
            solution["instance"].n,
            ind.get("statut", "?"),
            self._formater(ind.get("score")),
            self._formater(ind.get("f1_norm")),
            self._formater(ind.get("f2_norm")),
            self._formater(ind.get("f3_norm")),
            self._formater(ind.get("k")),
            self._formater(ind.get("gap")),
            self._formater(ind.get("temps_s")),
            self._formater(ind.get("delta_score_greedy")),
        )
        self.arbre.insert("", "end", iid=str(len(self.arbre.get_children())), values=valeurs)

    def _afficher_detail(self, _evenement=None):
        selection = self.arbre.selection()
        if not selection:
            return
        index = int(selection[0])
        if index >= len(self.solutions):
            return
        solution = self.solutions[index]
        if not solution.get("aff"):
            messagebox.showinfo(
                "Détail",
                "Pas de solution pour cette instance.\n%s"
                % solution.get("ind", {}).get("erreur", ""),
                parent=self,
            )
            return
        self.app.resultats.afficher(solution)
        self.app.notebook.select(self.app.resultats)

    def exporter(self):
        if not self.solutions:
            messagebox.showinfo(
                "Export", "Résolvez d'abord une sélection.", parent=self
            )
            return
        dossier = filedialog.askdirectory(
            parent=self, title="Dossier de destination des 3 CSV groupés"
        )
        if not dossier:
            return
        try:
            chemins = exporter_solutions(self.solutions, dossier)
        except Exception as erreur:
            messagebox.showerror("Export CSV", str(erreur), parent=self)
            return
        messagebox.showinfo(
            "Export CSV",
            "Trois fichiers écrits pour %d instance(s) :\n%s"
            % (
                sum(1 for s in self.solutions if s.get("aff")),
                "\n".join(os.path.basename(p) for p in chemins.values()),
            ),
            parent=self,
        )
