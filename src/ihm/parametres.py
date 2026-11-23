"""Onglet « Paramètres » : poids, profil de capacités et limites du solveur."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .chemins import SRC  # noqa: F401  (configure sys.path)
from groupes import PROFILS_CAPACITES


class ParametresFrame(ttk.LabelFrame):
    def __init__(self, parent):
        super().__init__(parent, text=" 2. Paramètres du solveur ", padding=8)
        self.f1 = tk.DoubleVar(value=0.30)
        self.f2 = tk.DoubleVar(value=0.70)
        self.f3 = tk.DoubleVar(value=0.15)
        self.profil = tk.StringVar(value="standard")
        self.timeout = tk.DoubleVar(value=30.0)
        self.k_impose = tk.BooleanVar(value=False)
        self.k_valeur = tk.IntVar(value=0)
        self.comparer = tk.BooleanVar(value=True)
        self.marge = tk.IntVar(value=1)
        self._construire()

    def _construire(self):
        poids = ttk.Frame(self)
        poids.pack(fill="x")
        ttk.Label(poids, text="Poids du score :").pack(side="left")
        for titre, variable in (("f1", self.f1), ("f2", self.f2), ("f3", self.f3)):
            ttk.Label(poids, text=titre).pack(side="left", padx=(12, 2))
            ttk.Spinbox(
                poids,
                from_=0.0,
                to=1.0,
                increment=0.05,
                textvariable=variable,
                width=6,
                format="%.2f",
            ).pack(side="left")

        courant = ttk.Frame(self)
        courant.pack(fill="x", pady=(8, 0))
        ttk.Label(courant, text="Profil de capacités :").pack(side="left")
        ttk.Combobox(
            courant,
            textvariable=self.profil,
            values=tuple(PROFILS_CAPACITES),
            state="readonly",
            width=14,
        ).pack(side="left", padx=(4, 16))
        ttk.Label(courant, text="Timeout (s) :").pack(side="left")
        ttk.Spinbox(
            courant, from_=1, to=600, increment=5, textvariable=self.timeout, width=6
        ).pack(side="left", padx=(4, 16))
        ttk.Label(courant, text="Marge de groupes :").pack(side="left")
        ttk.Spinbox(courant, from_=0, to=5, textvariable=self.marge, width=4).pack(side="left", padx=4)

        bas = ttk.Frame(self)
        bas.pack(fill="x", pady=(8, 0))
        ttk.Checkbutton(bas, text="Imposer k =", variable=self.k_impose).pack(side="left")
        ttk.Spinbox(bas, from_=1, to=100, textvariable=self.k_valeur, width=5).pack(side="left", padx=(4, 16))
        ttk.Checkbutton(
            bas, text="Comparer au greedy", variable=self.comparer
        ).pack(side="left")
        ttk.Button(bas, text="Réinitialiser", command=self.reinitialiser).pack(side="right")

    def reinitialiser(self):
        self.f1.set(0.30)
        self.f2.set(0.70)
        self.f3.set(0.15)
        self.profil.set("standard")
        self.timeout.set(30.0)
        self.k_impose.set(False)
        self.k_valeur.set(0)
        self.comparer.set(True)
        self.marge.set(1)

    def get(self):
        """Retourne les paramètres validés, prêts pour `resoudre`."""
        poids = {"f1": self.f1.get(), "f2": self.f2.get(), "f3": self.f3.get()}
        if any(v < 0 for v in poids.values()) or sum(poids.values()) <= 0:
            raise ValueError("les poids doivent être >= 0 et leur somme > 0")
        timeout = self.timeout.get()
        if timeout <= 0:
            raise ValueError("le timeout doit être > 0")
        marge = self.marge.get()
        if marge < 0:
            raise ValueError("la marge doit être >= 0")
        return {
            "poids": poids,
            "profil": self.profil.get(),
            "timeout": timeout,
            "k": self.k_valeur.get() if self.k_impose.get() else None,
            "comparer": self.comparer.get(),
            "marge": marge,
        }
