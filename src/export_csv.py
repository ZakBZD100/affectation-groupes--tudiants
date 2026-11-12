"""Export des instances figées en CSV lisible par Excel.

Le générateur ne produit que des étudiants : l'export fige donc un lot
reproductible et les instances extrêmes, puis écrit deux tables :

- ``exports/instances.csv`` : une ligne par instance (effectif, répartition
  LV2, choix tardifs, cas particuliers, catégorie) ;
- ``exports/etudiants.csv`` : une ligne par étudiant, toutes instances
  confondues.

Les fichiers sont écrits en UTF-8 avec BOM (``utf-8-sig``) pour qu'Excel
affiche correctement les accents sans réglage supplémentaire.

Exécution :
    python src/export_csv.py
    python src/export_csv.py --lot 30 --seed 11 --sans-extremes
"""
from __future__ import annotations

import argparse
import csv
import os
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from generateur_instances import (  # noqa: E402
    HISTORIQUE,
    generer_instances_extremes,
    generer_lot,
)

COLONNES_INSTANCES = (
    "nom",
    "seed",
    "effectif",
    "allemand",
    "espagnol",
    "autre",
    "choix_tardifs",
    "cas_particuliers",
    "categorie",
    "note",
)
COLONNES_ETUDIANTS = (
    "instance",
    "seed",
    "n",
    "id",
    "lv2",
    "choix_tardif",
    "statut",
)


def construire_historique(nb_lot=20, seed=7, avec_extremes=True):
    """Vide l'historique global puis y fige le lot et les extrêmes demandés."""
    HISTORIQUE.vider()
    for instance in generer_lot(nb_lot, seed=seed):
        HISTORIQUE.ajouter(instance)
    if avec_extremes:
        for instance in generer_instances_extremes(seed=0):
            HISTORIQUE.ajouter(instance)
    return HISTORIQUE


def _ligne_instance(resume):
    repartition = resume["repartition_lv2"]
    meta = resume["meta"]
    return {
        "nom": resume["nom"],
        "seed": resume["seed"],
        "effectif": resume["effectif"],
        "allemand": repartition.get("Allemand", 0),
        "espagnol": repartition.get("Espagnol", 0),
        "autre": repartition.get("Autre", 0),
        "choix_tardifs": resume["choix_tardifs"],
        "cas_particuliers": ";".join(resume["cas_particuliers"]),
        "categorie": meta.get("categorie", ""),
        "note": meta.get("note", ""),
    }


def _ecrire_csv(chemin, colonnes, lignes):
    with open(chemin, "w", newline="", encoding="utf-8-sig") as fichier:
        writer = csv.DictWriter(fichier, fieldnames=colonnes)
        writer.writeheader()
        writer.writerows(lignes)


def exporter(historique=None, sortie=None):
    """Écrit les deux CSV et retourne leurs chemins."""
    historique = HISTORIQUE if historique is None else historique
    sortie = os.path.join(RACINE, "exports") if sortie is None else sortie
    os.makedirs(sortie, exist_ok=True)

    chemin_instances = os.path.join(sortie, "instances.csv")
    chemin_etudiants = os.path.join(sortie, "etudiants.csv")

    _ecrire_csv(
        chemin_instances,
        COLONNES_INSTANCES,
        [_ligne_instance(r) for r in historique.tableau()],
    )
    _ecrire_csv(
        chemin_etudiants,
        COLONNES_ETUDIANTS,
        historique.tableau_etudiants(),
    )
    return chemin_instances, chemin_etudiants


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Exporte les instances figées en CSV (Excel)."
    )
    parser.add_argument("--lot", type=int, default=20, help="nombre d'instances du lot")
    parser.add_argument("--seed", type=int, default=7, help="graine du lot")
    parser.add_argument(
        "--sans-extremes",
        action="store_true",
        help="ne pas inclure les instances extrêmes",
    )
    parser.add_argument(
        "--sortie",
        default=None,
        help="dossier de sortie (défaut : exports/)",
    )
    args = parser.parse_args(argv)

    historique = construire_historique(
        nb_lot=args.lot, seed=args.seed, avec_extremes=not args.sans_extremes
    )
    chemin_instances, chemin_etudiants = exporter(historique, args.sortie)

    print(
        "%d instance(s) figée(s), %d étudiant(s)"
        % (len(historique), len(historique.tableau_etudiants()))
    )
    print("  ->", chemin_instances)
    print("  ->", chemin_etudiants)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
