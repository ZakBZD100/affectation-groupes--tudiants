"""Chemins de l'application, en développement et dans l'exécutable gelé."""
from __future__ import annotations

import os
import sys

# src/ihm/chemins.py -> racine du dépôt
RACINE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(RACINE, "src")

for _chemin in (RACINE, SRC):
    if _chemin not in sys.path:
        sys.path.insert(0, _chemin)


def base_donnees():
    """Dossier de l'application (où se trouve ``exports/``).

    En développement c'est la racine du dépôt ; dans l'exécutable PyInstaller
    c'est le dossier qui contient l'.exe (``--onedir``).
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return RACINE


def chemin_exports():
    """Dossier ``exports``, y compris dans le layout PyInstaller 6 (``_internal``)."""
    base = base_donnees()
    candidats = (
        os.path.join(base, "exports"),
        os.path.join(base, "_internal", "exports"),
    )
    for chemin in candidats:
        if os.path.isfile(os.path.join(chemin, "instances.csv")):
            return chemin
    return candidats[0]
