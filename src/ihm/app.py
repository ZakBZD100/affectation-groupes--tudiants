"""Fenêtre principale de l'application d'affectation de groupes."""
from __future__ import annotations

import queue
import threading
import tkinter as tk
import traceback
from tkinter import messagebox, ttk

from .donnees import DonneesFrame
from .explorateur import ExplorateurFrame
from .lots import ResolutionLotsFrame
from .parametres import ParametresFrame
from .resultats import ResultatsFrame
from .solution import resoudre_interface


class Application(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Affectation de groupes — CP-SAT")
        self.geometry("1180x800")
        self.minsize(1000, 700)
        self.file = queue.Queue()
        self._resolution_en_cours = False
        self.donnees = None  # assigné après construction (callback pendant l'init)

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=8, pady=8)

        self.donnees = DonneesFrame(self.notebook, on_change=self._changement_donnees)
        self.parametres = ParametresFrame(self.notebook)
        self.resultats = ResultatsFrame(self.notebook, on_resoudre=self.resoudre)
        self.lots = ResolutionLotsFrame(self.notebook, app=self)
        self.explorateur = ExplorateurFrame(self.notebook)
        self.notebook.add(self.donnees, text="Données")
        self.notebook.add(self.parametres, text="Paramètres")
        self.notebook.add(self.lots, text="Résolution lots")
        self.notebook.add(self.resultats, text="Résultats")
        self.notebook.add(self.explorateur, text="Instances pré-calculées")
        self.notebook.bind("<<NotebookTabChanged>>", self._onglet_change)

        self.etat = ttk.Label(
            self,
            text="Prêt — choisissez des données puis cliquez sur « Résoudre avec CP-SAT ».",
            anchor="w",
        )
        self.etat.pack(fill="x", side="bottom", padx=10, pady=(0, 6))

    def _changement_donnees(self):
        if self._resolution_en_cours or self.donnees is None:
            return
        try:
            instance = self.donnees.get_instance()
            self.etat.config(text="Instance prête : %s (%d étudiants)" % (instance.nom, instance.n))
        except ValueError:
            self.etat.config(text="En attente de données…")
        if hasattr(self, "lots"):
            self.lots.actualiser_unitaire()

    def _onglet_change(self, _evenement=None):
        """Rafraîchit la liste plurielle quand on entre dans l'onglet dédié."""
        if hasattr(self, "lots") and self.notebook.select() == str(self.lots):
            self.lots.actualiser()
            self.lots.actualiser_unitaire()

    def resoudre(self):
        if self._resolution_en_cours:
            return
        try:
            instance = self.donnees.get_instance()
            params = self.parametres.get()
        except Exception as erreur:
            messagebox.showerror("Données invalides", str(erreur), parent=self)
            return

        self._resolution_en_cours = True
        self.resultats.set_solve_state(False)
        self.resultats.set_occupation("Résolution en cours… (le solveur peut prendre le timeout)")
        self.etat.config(text="Résolution de %s…" % instance.nom)
        self.update_idletasks()
        fil = threading.Thread(
            target=self._travail, args=(instance, params), daemon=True
        )
        fil.start()
        self.after(120, self._verifier_file)

    def _travail(self, instance, params):
        """Exécuté dans un thread : ne touche jamais aux widgets Tkinter."""
        try:
            self.file.put(("ok", resoudre_interface(instance, params)))
        except Exception:
            self.file.put(("erreur", traceback.format_exc()))

    def _verifier_file(self):
        try:
            genre, contenu = self.file.get_nowait()
        except queue.Empty:
            self.after(120, self._verifier_file)
            return

        self._resolution_en_cours = False
        self.resultats.set_solve_state(True)
        if genre == "erreur":
            self.etat.config(text="Erreur pendant la résolution.")
            messagebox.showerror("Résolution", contenu, parent=self)
            return
        self.resultats.afficher(contenu)
        self.notebook.select(self.resultats)
        self.etat.config(
            text="Terminé : %s — %s" % (contenu["instance"].nom, contenu["ind"].get("statut", "?"))
        )


def main():
    application = Application()
    application.mainloop()


if __name__ == "__main__":
    main()
