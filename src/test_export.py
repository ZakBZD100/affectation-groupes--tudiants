"""Tests de l'export CSV — contenu, en-têtes et BOM Excel.

Exécution :
    python src/test_export.py
"""
import csv
import os
import sys
import tempfile

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from export_csv import (  # noqa: E402
    COLONNES_ETUDIANTS,
    COLONNES_INSTANCES,
    construire_historique,
    exporter,
)


def test_export():
    historique = construire_historique(nb_lot=2, seed=3, avec_extremes=True)
    assert len(historique) == 9, len(historique)
    assert len(historique.tableau_etudiants()) == sum(
        i.n for i in historique.lister()
    )

    with tempfile.TemporaryDirectory() as dossier:
        chemin_instances, chemin_etudiants = exporter(historique, dossier)

        for chemin in (chemin_instances, chemin_etudiants):
            with open(chemin, "rb") as fichier:
                assert fichier.read(3) == b"\xef\xbb\xbf", "BOM UTF-8 absent"

        with open(chemin_instances, encoding="utf-8-sig", newline="") as fichier:
            lignes = list(csv.DictReader(fichier))
        assert list(lignes[0]) == list(COLONNES_INSTANCES)
        assert len(lignes) == len(historique)
        assert sum(int(ligne["effectif"]) for ligne in lignes) == len(
            historique.tableau_etudiants()
        )

        with open(chemin_etudiants, encoding="utf-8-sig", newline="") as fichier:
            detail = list(csv.DictReader(fichier))
        assert list(detail[0]) == list(COLONNES_ETUDIANTS)
        assert len(detail) == len(historique.tableau_etudiants())
        assert {ligne["instance"] for ligne in detail} == {
            i.nom for i in historique.lister()
        }

    # Même graine -> même lot (reproductibilité de l'export).
    a = [i.nom for i in construire_historique(3, seed=5, avec_extremes=False)]
    b = [i.nom for i in construire_historique(3, seed=5, avec_extremes=False)]
    assert a == b, (a, b)

    print("export CSV OK (en-tetes, BOM UTF-8, lot reproductible)")


if __name__ == "__main__":
    test_export()
    print("tests de l'export passent")
