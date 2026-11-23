"""Tests de l'export CSV — contenu, en-têtes, BOM Excel et résolution.

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
    COLONNES_RESULTATS,
    construire_historique,
    exporter,
)


def _lire(chemin):
    with open(chemin, "rb") as fichier:
        assert fichier.read(3) == b"\xef\xbb\xbf", "BOM UTF-8 absent"
    with open(chemin, encoding="utf-8-sig", newline="") as fichier:
        return list(csv.DictReader(fichier))


def test_export():
    historique = construire_historique(nb_lot=2, seed=3, avec_extremes=True)
    assert len(historique) == 9, len(historique)
    assert len(historique.tableau_etudiants()) == sum(
        i.n for i in historique.lister()
    )

    with tempfile.TemporaryDirectory() as dossier:
        chemins = exporter(historique, dossier, avec_solution=False)
        assert len(chemins) == 3
        chemin_instances, chemin_etudiants, chemin_resultats = chemins

        instances = _lire(chemin_instances)
        assert list(instances[0]) == list(COLONNES_INSTANCES)
        assert len(instances) == len(historique)
        assert sum(int(ligne["effectif"]) for ligne in instances) == len(
            historique.tableau_etudiants()
        )
        assert {ligne["statut"] for ligne in instances} == {"NON_RESOLU"}

        etudiants = _lire(chemin_etudiants)
        assert list(etudiants[0]) == list(COLONNES_ETUDIANTS)
        assert len(etudiants) == len(historique.tableau_etudiants())
        assert {ligne["instance"] for ligne in etudiants} == {
            i.nom for i in historique.lister()
        }
        assert all(ligne["groupe_lv2"] == "" for ligne in etudiants)

        resultats = _lire(chemin_resultats)
        assert list(resultats[0]) == list(COLONNES_RESULTATS)
        assert len(resultats) == len(historique.tableau_etudiants())
        assert {ligne["statut_affectation"] for ligne in resultats} <= {
            "non_resolu",
            "non_affecte_cas_particulier",
        }

    # Même graine -> même lot (reproductibilité de l'export).
    a = [i.nom for i in construire_historique(3, seed=5, avec_extremes=False)]
    b = [i.nom for i in construire_historique(3, seed=5, avec_extremes=False)]
    assert a == b, (a, b)


def test_export_avec_solution():
    """Une instance résolue remplit les groupes et les métriques."""
    historique = construire_historique(nb_lot=1, seed=11, avec_extremes=False)

    with tempfile.TemporaryDirectory() as dossier:
        chemin_instances, chemin_etudiants, chemin_resultats = exporter(
            historique, dossier
        )

        instances = _lire(chemin_instances)
        assert len(instances) == 1
        ligne = instances[0]
        assert ligne["statut"] in ("OPTIMAL", "FEASIBLE")
        assert int(ligne["k_total"]) > 0
        assert int(ligne["f2_min"]) > 0
        assert ligne["score"] != ""
        assert ligne["delta_score_greedy"] != ""

        etudiants = _lire(chemin_etudiants)
        assert len(etudiants) == len(historique.tableau_etudiants())
        normalux = [e for e in etudiants if e["statut"] == "normal"]
        assert normalux
        assert all(e["groupe_lv2"] for e in normalux)
        assert all(e["groupe_lv1"] for e in normalux)
        assert all(e["groupe_tp"] for e in normalux)
        assert all(e["groupe_td"] for e in normalux)
        assert all(
            e["groupe_lv2"].startswith(f"LV2_{e['lv2']}_") for e in normalux
        )

        resultats = _lire(chemin_resultats)
        assert len(resultats) == len(etudiants)
        affectes = [r for r in resultats if r["statut_affectation"] == "affecte"]
        assert len(affectes) == len(normalux)
        assert all(r["faisable"] == "True" for r in resultats)
        assert all(r["respecte_choix"] == "True" for r in affectes)
        assert all(r["td_parent"] for r in affectes)
        assert all(r["methode"] == "CP-SAT" for r in affectes)


if __name__ == "__main__":
    test_export()
    test_export_avec_solution()
    print("tests de l'export passent")
