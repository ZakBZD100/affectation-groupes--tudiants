"""Onglet « Résultats » : métriques, affectations, groupes et exports."""
from __future__ import annotations

import json
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .chemins import SRC  # noqa: F401  (configure sys.path)
from export_csv import (
    COLONNES_ETUDIANTS,
    COLONNES_INSTANCES,
    COLONNES_RESULTATS,
    _ecrire_csv,
    _ligne_instance,
    _lignes_etudiants,
    _lignes_resultats,
)

METRIQUES = (
    ("statut", "Statut"),
    ("temps_s", "Temps (s)"),
    ("gap", "Gap"),
    ("k", "Groupes ouverts"),
    ("f1", "f1"),
    ("f1_norm", "f1 normé"),
    ("f2", "f2"),
    ("f2_norm", "f2 normé"),
    ("f3", "f3"),
    ("f3_norm", "f3 normé"),
    ("score", "Score solveur"),
    ("score_evaluateur", "Score évaluateur"),
    ("taux_occupation", "Occupation"),
    ("delta_score_greedy", "Delta vs greedy"),
)


def exporter_solutions(solutions, dossier):
    """Écrit les trois CSV du projet pour *toutes* les solutions résolues.

    C'est cette fonction qui est utilisée en mode pluriel : les trois fichiers
    contiennent une ligne par instance (et une ligne par étudiant), exactement
    comme les exports historiques de ``exports/``.
    """
    solutions = [s for s in solutions if s.get("aff")]
    if not solutions:
        raise ValueError("aucune solution résolue à exporter")
    os.makedirs(dossier, exist_ok=True)
    chemins = {
        "instances": os.path.join(dossier, "instances.csv"),
        "etudiants": os.path.join(dossier, "etudiants.csv"),
        "resultats": os.path.join(dossier, "resultats_etudiants.csv"),
    }
    lignes_instances = [
        _ligne_instance(s["instance"].resume(), s) for s in solutions
    ]
    lignes_etudiants = []
    lignes_resultats = []
    for solution in solutions:
        instance = solution["instance"]
        lignes_etudiants.extend(_lignes_etudiants(instance, solution))
        lignes_resultats.extend(_lignes_resultats(instance, solution))
    _ecrire_csv(chemins["instances"], COLONNES_INSTANCES, lignes_instances)
    _ecrire_csv(chemins["etudiants"], COLONNES_ETUDIANTS, lignes_etudiants)
    _ecrire_csv(chemins["resultats"], COLONNES_RESULTATS, lignes_resultats)
    return chemins


def exporter_solution(instance, solution, dossier):
    """Écrit les trois CSV du projet pour la solution *affichée* (pas un re-solve)."""
    return exporter_solutions([solution], dossier)


class ResultatsFrame(ttk.LabelFrame):
    def __init__(self, parent, on_resoudre=None):
        super().__init__(parent, text=" 3. Résultats ", padding=8)
        self.on_resoudre = on_resoudre
        self.solution = None
        self.labels = {}
        self.bouton_resoudre = None
        self._construire()

    def _construire(self):
        barre = ttk.Frame(self)
        barre.pack(fill="x", pady=(0, 8))
        self.bouton_resoudre = ttk.Button(
            barre, text="Résoudre avec CP-SAT", command=self._demander_resolution
        )
        self.bouton_resoudre.pack(side="left")
        ttk.Button(barre, text="Exporter les 3 CSV…", command=self.exporter_csv).pack(
            side="left", padx=(8, 0)
        )
        ttk.Button(barre, text="Exporter le rapport JSON…", command=self.exporter_json).pack(
            side="left", padx=(8, 0)
        )
        self.etat = ttk.Label(barre, text="Prêt.")
        self.etat.pack(side="left", padx=(12, 0))

        grille = ttk.LabelFrame(self, text="Métriques", padding=6)
        grille.pack(fill="x")
        for index, (cle, titre) in enumerate(METRIQUES):
            ligne, colonne = divmod(index, 4)
            ttk.Label(grille, text=titre + " :", font=("TkDefaultFont", 9, "bold")).grid(
                row=ligne, column=colonne * 2, sticky="w", padx=(4, 2), pady=2
            )
            valeur = ttk.Label(grille, text="—", width=16, anchor="w")
            valeur.grid(row=ligne, column=colonne * 2 + 1, sticky="w", pady=2)
            self.labels[cle] = valeur

        vue = ttk.Notebook(self)
        vue.pack(fill="both", expand=True, pady=(8, 0))
        self.etudiants = ttk.Frame(vue)
        self.groupes = ttk.Frame(vue)
        self.comparaison = ttk.Frame(vue)
        vue.add(self.etudiants, text="Affectations")
        vue.add(self.groupes, text="Groupes")
        vue.add(self.comparaison, text="Greedy vs CP-SAT")

        self.arbre_etudiants = self._arbre(
            self.etudiants,
            ("id", "lv2", "statut", "LV2", "LV1", "TP", "TD"),
            {"id": 50, "lv2": 90, "statut": 90, "LV2": 150, "LV1": 150, "TP": 130, "TD": 130},
        )
        self.arbre_groupes = self._arbre(
            self.groupes,
            ("nom", "type", "capacite", "effectif", "occupation", "parent"),
            {"nom": 170, "type": 70, "capacite": 80, "effectif": 80, "occupation": 90, "parent": 100},
        )
        self.texte_comparaison = tk.Text(self.comparaison, height=8, wrap="word")
        self.texte_comparaison.pack(fill="both", expand=True, padx=6, pady=6)
        self.texte_comparaison.config(state="disabled")

    @staticmethod
    def _arbre(parent, colonnes, largeurs):
        cadre = ttk.Frame(parent)
        cadre.pack(fill="both", expand=True)
        arbre = ttk.Treeview(cadre, columns=colonnes, show="headings", height=9)
        for col in colonnes:
            arbre.heading(col, text=col)
            arbre.column(col, width=largeurs.get(col, 90), anchor="w")
        barre = ttk.Scrollbar(cadre, orient="vertical", command=arbre.yview)
        arbre.configure(yscrollcommand=barre.set)
        arbre.pack(side="left", fill="both", expand=True)
        barre.pack(side="right", fill="y")
        return arbre

    def _demander_resolution(self):
        if self.on_resoudre:
            self.on_resoudre()

    def set_occupation(self, texte):
        self.etat.config(text=texte)

    def set_solve_state(self, actif):
        self.bouton_resoudre.config(state="normal" if actif else "disabled")

    def effacer(self):
        self.solution = None
        for valeur in self.labels.values():
            valeur.config(text="—")
        for arbre in (self.arbre_etudiants, self.arbre_groupes):
            arbre.delete(*arbre.get_children())
        self.texte_comparaison.config(state="normal")
        self.texte_comparaison.delete("1.0", "end")
        self.texte_comparaison.config(state="disabled")

    def afficher(self, solution):
        self.solution = solution
        ind = solution["ind"]
        evaluation = solution.get("evaluation")
        valeurs = dict(ind)
        if evaluation is not None and evaluation.score is not None:
            valeurs["score_evaluateur"] = round(evaluation.score, 6)
        for cle, _titre in METRIQUES:
            valeur = valeurs.get(cle, "—")
            if isinstance(valeur, float):
                valeur = round(valeur, 6)
            self.labels[cle].config(text=str(valeur))

        self.arbre_etudiants.delete(*self.arbre_etudiants.get_children())
        for e in solution["instance"].etudiants:
            groupes = solution["aff"].get(e.id, {}) if solution["aff"] else {}
            self.arbre_etudiants.insert(
                "",
                "end",
                values=(
                    e.id,
                    e.lv2,
                    e.statut,
                    groupes.get("LV2", ""),
                    groupes.get("LV1", ""),
                    groupes.get("TP", ""),
                    groupes.get("TD", ""),
                ),
            )

        parents = {g.nom: g.parent for g in solution["groupes"]}
        effectifs = solution["eff"]
        self.arbre_groupes.delete(*self.arbre_groupes.get_children())
        for g in solution["groupes"]:
            effet = effectifs.get(g.nom, 0)
            self.arbre_groupes.insert(
                "",
                "end",
                values=(
                    g.nom,
                    g.type,
                    g.capacite,
                    effet,
                    "%.0f%%" % (100.0 * effet / g.capacite),
                    parents.get(g.nom) or "",
                ),
            )

        greedy = ind.get("greedy", {})
        lignes = [
            "Méthode        Score       k     f1      f3",
            "------------------------------------------------",
        ]
        if greedy.get("faisable"):
            lignes.append(
                "Greedy         %.6f   %s   %.3f   %s"
                % (
                    greedy.get("score", 0),
                    greedy.get("k"),
                    greedy.get("f1", 0),
                    greedy.get("f3"),
                )
            )
        lignes.append(
            "CP-SAT         %.6f   %s   %.3f   %s"
            % (ind.get("score", 0), ind.get("k"), ind.get("f1", 0), ind.get("f3"))
        )
        if ind.get("delta_score_greedy") is not None:
            lignes.append("")
            lignes.append("Delta (évaluateur) : %+.6f" % ind["delta_score_greedy"])
            lignes.append("Delta k            : %s" % ind.get("delta_k_greedy"))
        self.texte_comparaison.config(state="normal")
        self.texte_comparaison.delete("1.0", "end")
        self.texte_comparaison.insert("1.0", "\n".join(lignes))
        self.texte_comparaison.config(state="disabled")
        self.set_occupation("Résolution terminée : %s" % ind.get("statut", "?"))

    def _verifier_solution(self):
        if self.solution is None:
            messagebox.showinfo("Export", "Résolvez d'abord une instance.", parent=self)
            return None
        return self.solution

    def exporter_csv(self):
        solution = self._verifier_solution()
        if solution is None:
            return
        dossier = filedialog.askdirectory(parent=self, title="Dossier de destination des CSV")
        if not dossier:
            return
        try:
            chemins = exporter_solution(solution["instance"], solution, dossier)
        except Exception as erreur:
            messagebox.showerror("Export CSV", str(erreur), parent=self)
            return
        messagebox.showinfo(
            "Export CSV",
            "Trois fichiers écrits :\n" + "\n".join(os.path.basename(p) for p in chemins.values()),
            parent=self,
        )

    def exporter_json(self):
        solution = self._verifier_solution()
        if solution is None:
            return
        chemin = filedialog.asksaveasfilename(
            parent=self,
            title="Rapport JSON",
            defaultextension=".json",
            filetypes=(("JSON", "*.json"), ("Tous", "*.*")),
        )
        if not chemin:
            return
        rapport = {
            "instance": solution["instance"].nom,
            "indicateurs": solution["ind"],
            "affectations": solution["aff"],
        }
        try:
            with open(chemin, "w", encoding="utf-8") as fichier:
                json.dump(rapport, fichier, indent=2, ensure_ascii=False, default=str)
        except Exception as erreur:
            messagebox.showerror("Export JSON", str(erreur), parent=self)
            return
        messagebox.showinfo("Export JSON", "Rapport enregistré.", parent=self)
