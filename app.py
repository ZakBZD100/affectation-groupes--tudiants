"""Lanceur de l'application graphique d'affectation de groupes.

    python app.py

L'interface utilise le solveur CP-SAT du projet (``test_cpsat.resoudre``) :
aucun portage ni approximation n'est nécessaire, contrairement à une version
web statique où OR-Tools ne peut pas tourner dans le navigateur.
"""
import os
import sys

RACINE = os.path.dirname(os.path.abspath(__file__))
for _chemin in (RACINE, os.path.join(RACINE, "src")):
    if _chemin not in sys.path:
        sys.path.insert(0, _chemin)

from ihm.app import main  # noqa: E402


def selftest():
    """Vérifie, sans ouvrir de fenêtre, que l'exe gelé sait résoudre et lire les exports."""
    import csv
    import os

    from ihm.chemins import chemin_exports
    from ihm.donnees import instance_depuis_lignes
    from ihm.solution import resoudre_interface

    dossier = chemin_exports()
    chemin_csv = os.path.join(dossier, "instances.csv")
    assert os.path.isfile(chemin_csv), chemin_csv
    with open(chemin_csv, encoding="utf-8-sig", newline="") as fichier:
        nb_instances = len(list(csv.DictReader(fichier)))
    assert nb_instances == 27, nb_instances
    print("selftest exports OK : %s (%d instances)" % (dossier, nb_instances))

    instance = instance_depuis_lignes(
        [
            {"lv2": "Allemand" if i % 2 else "Espagnol", "statut": "normal"}
            for i in range(12)
        ],
        nom="selftest",
    )
    solution = resoudre_interface(
        instance,
        {
            "poids": {"f1": 0.3, "f2": 0.7, "f3": 0.15},
            "profil": "standard",
            "timeout": 10,
            "k": None,
            "comparer": False,
            "marge": 1,
        },
    )
    statut = solution["ind"].get("statut")
    assert statut in ("OPTIMAL", "FEASIBLE"), statut
    assert len(solution["aff"]) == 12
    print("selftest OK : statut=%s, score=%.4f, k=%s" % (
        statut, solution["ind"]["score"], solution["ind"]["k"]
    ))


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        main()
