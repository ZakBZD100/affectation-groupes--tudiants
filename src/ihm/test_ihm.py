"""Tests des briques non-graphiques de l'interface (aucune fenêtre requise)."""
import csv
import os
import sys
import tempfile

RACINE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _chemin in (RACINE, os.path.join(RACINE, "src")):
    if _chemin not in sys.path:
        sys.path.insert(0, _chemin)

from export_csv import COLONNES_ETUDIANTS, COLONNES_INSTANCES, COLONNES_RESULTATS  # noqa: E402
from generateur_instances import generer_instance  # noqa: E402
from ihm.donnees import instance_depuis_lignes, lire_csv_etudiants  # noqa: E402
from ihm.explorateur import lire_csv  # noqa: E402
from ihm.resultats import exporter_solution  # noqa: E402
from ihm.solution import resoudre_interface  # noqa: E402


def test_saisie_manuelle():
    lignes = [
        {"lv2": "Allemand", "statut": "normal", "choix_tardif": False},
        {"lv2": "Espagnol", "statut": "redoublant", "choix_tardif": "oui"},
        {"lv2": "Autre", "statut": "normal"},
    ]
    inst = instance_depuis_lignes(lignes, nom="test")
    assert inst.n == 3 and [e.id for e in inst.etudiants] == [1, 2, 3]
    assert inst.etudiants[1].choix_tardif is True
    assert abs(sum(p for _l, p in inst.distribution) - 1.0) < 1e-12
    try:
        instance_depuis_lignes([{"lv2": "Klingon"}])
    except ValueError:
        pass
    else:
        raise AssertionError("LV2 inconnue acceptée")
    print("1/5 saisie manuelle OK (ids 1..n, statuts, distribution)")


def test_import_csv():
    with tempfile.TemporaryDirectory() as dossier:
        chemin = os.path.join(dossier, "etudiants.csv")
        with open(chemin, "w", encoding="utf-8-sig", newline="") as f:
            f.write("id,Langue,Statut,choix tardif\n")
            f.write("10,Allemand,normal,0\n")
            f.write("11,Espagnol,cesure,1\n")
        lignes = lire_csv_etudiants(chemin)
        assert len(lignes) == 2
        assert lignes[0]["lv2"] == "Allemand" and lignes[1]["statut"] == "cesure"
        inst = instance_depuis_lignes(lignes, nom="import")
        assert [e.id for e in inst.etudiants] == [1, 2]
        assert inst.etudiants[1].choix_tardif is True
    print("2/5 import CSV OK (BOM, alias de colonnes, renommage des ids)")


def test_generation_reproductible():
    a = generer_instance(n=50, seed=7)
    b = generer_instance(n=50, seed=7)
    assert a == b
    assert generer_instance(n=50, seed=8) != a
    print("3/5 génération blake2b reproductible OK")


def test_resolution_et_exports():
    lignes = [
        {"lv2": "Allemand" if i % 2 else "Espagnol", "statut": "normal"}
        for i in range(12)
    ]
    inst = instance_depuis_lignes(lignes, nom="test_export", seed=1)
    params = {
        "poids": {"f1": 0.3, "f2": 0.7, "f3": 0.15},
        "profil": "standard",
        "timeout": 10,
        "k": None,
        "comparer": True,
        "marge": 1,
    }
    solution = resoudre_interface(inst, params)
    assert solution["aff"] and solution["ind"].get("statut") in ("OPTIMAL", "FEASIBLE")
    with tempfile.TemporaryDirectory() as dossier:
        chemins = exporter_solution(inst, solution, dossier)
        assert sorted(os.path.basename(p) for p in chemins.values()) == sorted(
            ("instances.csv", "etudiants.csv", "resultats_etudiants.csv")
        )
        with open(chemins["instances"], encoding="utf-8-sig", newline="") as f:
            lecture = csv.DictReader(f)
            assert tuple(lecture.fieldnames) == COLONNES_INSTANCES
            assert len(list(lecture)) == 1
        with open(chemins["etudiants"], encoding="utf-8-sig", newline="") as f:
            lecture = csv.DictReader(f)
            assert tuple(lecture.fieldnames) == COLONNES_ETUDIANTS
            assert len(list(lecture)) == 12
        with open(chemins["resultats"], encoding="utf-8-sig", newline="") as f:
            lecture = csv.DictReader(f)
            assert tuple(lecture.fieldnames) == COLONNES_RESULTATS
            lignes_r = list(lecture)
            assert len(lignes_r) == 12
            assert all(r["respecte_choix"] == "True" for r in lignes_r)
            assert all(r["td_parent"] == r["groupe_td"] for r in lignes_r)
    print("4/5 résolution + 3 CSV OK (en-têtes, 12 lignes, C3/C4)")


def test_explorateur():
    chemin = os.path.join(RACINE, "exports", "instances.csv")
    lignes = lire_csv(chemin)
    assert len(lignes) == 27
    assert all(ligne["nom"] for ligne in lignes)
    print("5/5 explorateur OK (27 instances lues)")


if __name__ == "__main__":
    test_saisie_manuelle()
    test_import_csv()
    test_generation_reproductible()
    test_resolution_et_exports()
    test_explorateur()
    print("5/5 tests de l'interface passent")
