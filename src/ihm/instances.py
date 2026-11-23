"""Reconstruction des instances figées à partir des CSV livrés.

Le mode pluriel doit pouvoir résoudre les 27 instances du dépôt sans deviner
les graines du générateur : les étudiants sont lus directement dans
``exports/etudiants.csv`` et les métriques affichées viennent de
``exports/instances.csv``.
"""
from __future__ import annotations

import csv
import os

from .chemins import chemin_exports  # noqa: F401  (configure sys.path)
from .donnees import instance_depuis_lignes
from .explorateur import lire_csv


def lire_instances_precalculees():
    """Retourne les instances de ``exports/`` sous forme de ``Instance`` figées.

    Chaque élément est un dictionnaire ``{"instance", "meta", "source"}`` où
    ``meta`` contient les colonnes de ``instances.csv`` (score, catégorie, ...).
    """
    dossier = chemin_exports()
    chemin_etudiants = os.path.join(dossier, "etudiants.csv")
    if not os.path.isfile(chemin_etudiants):
        return []

    meta = {}
    chemin_instances = os.path.join(dossier, "instances.csv")
    if os.path.isfile(chemin_instances):
        for ligne in lire_csv(chemin_instances):
            meta[ligne.get("nom", "")] = ligne

    groupes = {}
    graines = {}
    with open(chemin_etudiants, "r", encoding="utf-8-sig", newline="") as fichier:
        for ligne in csv.DictReader(fichier):
            nom = ligne.get("instance", "")
            if not nom:
                continue
            groupes.setdefault(nom, []).append(ligne)
            try:
                graines.setdefault(nom, int(ligne.get("seed", 0)))
            except (TypeError, ValueError):
                graines.setdefault(nom, 0)

    resultats = []
    for nom, lignes in groupes.items():
        try:
            instance = instance_depuis_lignes(lignes, nom=nom, seed=graines[nom])
        except ValueError:
            continue
        resultats.append(
            {"instance": instance, "meta": meta.get(nom, {}), "source": "pré-calculée"}
        )
    return resultats
