"""Export des instances figées et des résultats en CSV lisible par Excel.

Pour chaque instance figée du lot et des cas extrêmes, le solveur CP-SAT
multi-type est lancé avec le profil de capacités ``standard``. Trois tables
sont écrites :

- ``instances.csv`` : une ligne par instance, avec les métriques du solveur ;
- ``etudiants.csv`` : une ligne par étudiant, données d'entrée + groupes
  assignés ;
- ``resultats_etudiants.csv`` : état de chaque étudiant après analyse
  (affectation multi-type, conformité au choix, score de l'instance).

Les fichiers sont écrits en UTF-8 avec BOM (``utf-8-sig``) pour qu'Excel
affiche correctement les accents sans réglage supplémentaire.

Exécution :
    python src/export_csv.py
    python src/export_csv.py --lot 30 --seed 11 --sans-extremes
    python src/export_csv.py --timeout 60      # plus de temps par instance
    python src/export_csv.py --sans-solution   # export des entrées seulement

Les instances sont reproductibles (graines dérivées par blake2b), mais les
affectations peuvent varier d'une exécution à l'autre : CP-SAT utilise ses
workers automatiques pour rester rapide.
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
from groupes import PROFILS_CAPACITES, construire_groupes  # noqa: E402
from test_cpsat import resoudre  # noqa: E402
from evaluation import evaluer  # noqa: E402

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
    "statut",
    "temps_s",
    "objectif",
    "best_bound",
    "gap",
    "variables",
    "contraintes",
    "k_total",
    "k_lv2",
    "k_lv1",
    "k_tp",
    "k_td",
    "f1",
    "f1_norm",
    "f1_max",
    "f2",
    "f2_norm",
    "f2_min",
    "f2_max",
    "f3",
    "f3_max",
    "f3_norm",
    "score",
    "score_evaluateur",
    "ecart_f2_min",
    "marge_f2",
    "effectif_min",
    "effectif_max",
    "effectif_moyen",
    "ecart_type",
    "taux_occupation",
    "maxmin",
    "delta_score_greedy",
    "delta_k_greedy",
)
COLONNES_ETUDIANTS = (
    "instance",
    "seed",
    "n",
    "id",
    "lv2",
    "choix_tardif",
    "statut",
    "groupe_lv2",
    "groupe_lv1",
    "groupe_tp",
    "groupe_td",
)
COLONNES_RESULTATS = (
    "instance",
    "id",
    "lv2_choisie",
    "choix_tardif",
    "statut",
    "statut_affectation",
    "groupe_lv2",
    "groupe_lv1",
    "groupe_tp",
    "groupe_td",
    "td_parent",
    "respecte_choix",
    "faisable",
    "score_instance",
    "score_evaluateur",
    "methode",
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


def resoudre_instance(instance, timeout=None):
    """Résout une instance figée et retourne le contexte complet."""
    actifs = [e for e in instance.etudiants if e.statut == "normal"]
    s = {e.id: e.lv2 for e in actifs}
    groupes = construire_groupes(instance, PROFILS_CAPACITES["standard"])
    compat = {
        e.id: [
            g.nom
            for g in groupes
            if g.type != "LV2" or g.nom.startswith(f"LV2_{e.lv2}_")
        ]
        for e in actifs
    }
    statut, aff, eff, ind = resoudre(
        s, groupes, compat=compat, comparer=True, timeout=timeout
    )
    r_eval = evaluer(s, groupes, aff, compat=compat) if aff else None
    return {
        "instance": instance,
        "s": s,
        "groupes": groupes,
        "compat": compat,
        "statut": ind.get("statut", "INFEASIBLE"),
        "aff": aff,
        "eff": eff,
        "ind": ind,
        "evaluation": r_eval,
    }


def _v(ind, cle, defaut=""):
    return ind.get(cle, defaut)


def _ligne_instance(resume, solution):
    repartition = resume["repartition_lv2"]
    meta = resume["meta"]
    ind = solution["ind"] if solution else {}
    k = ind.get("k_par_type", {})
    r = solution["evaluation"] if solution else None
    score_eval = (
        round(r.score, 6)
        if r is not None and r.faisable and r.score is not None
        else ""
    )
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
        "statut": ind.get("statut", "NON_RESOLU"),
        "temps_s": _v(ind, "temps_s"),
        "objectif": _v(ind, "objectif"),
        "best_bound": _v(ind, "best_bound"),
        "gap": _v(ind, "gap"),
        "variables": _v(ind, "variables"),
        "contraintes": _v(ind, "contraintes"),
        "k_total": _v(ind, "k"),
        "k_lv2": k.get("LV2", 0),
        "k_lv1": k.get("LV1", 0),
        "k_tp": k.get("TP", 0),
        "k_td": k.get("TD", 0),
        "f1": _v(ind, "f1"),
        "f1_norm": _v(ind, "f1_norm"),
        "f1_max": _v(ind, "f1_max"),
        "f2": _v(ind, "f2"),
        "f2_norm": _v(ind, "f2_norm"),
        "f2_min": _v(ind, "f2_min"),
        "f2_max": _v(ind, "f2_max"),
        "f3": _v(ind, "f3"),
        "f3_max": _v(ind, "f3_max"),
        "f3_norm": _v(ind, "f3_norm"),
        "score": _v(ind, "score"),
        "score_evaluateur": score_eval,
        "ecart_f2_min": _v(ind, "ecart_f2_min"),
        "marge_f2": _v(ind, "marge_f2"),
        "effectif_min": _v(ind, "effectif_min"),
        "effectif_max": _v(ind, "effectif_max"),
        "effectif_moyen": _v(ind, "effectif_moyen"),
        "ecart_type": _v(ind, "ecart_type"),
        "taux_occupation": _v(ind, "taux_occupation"),
        "maxmin": _v(ind, "maxmin"),
        "delta_score_greedy": _v(ind, "delta_score_greedy"),
        "delta_k_greedy": _v(ind, "delta_k_greedy"),
    }


def _lignes_etudiants(instance, solution):
    aff = solution["aff"] if solution else {}
    for e in instance.etudiants:
        groups = aff.get(e.id, {}) if isinstance(aff, dict) else {}
        yield {
            "instance": instance.nom,
            "seed": instance.seed,
            "n": instance.n,
            "id": e.id,
            "lv2": e.lv2,
            "choix_tardif": e.choix_tardif,
            "statut": e.statut,
            "groupe_lv2": groups.get("LV2", ""),
            "groupe_lv1": groups.get("LV1", ""),
            "groupe_tp": groups.get("TP", ""),
            "groupe_td": groups.get("TD", ""),
        }


def _lignes_resultats(instance, solution):
    aff = solution["aff"] if solution else {}
    ind = solution["ind"] if solution else {}
    r = solution["evaluation"] if solution else None
    parents = (
        {g.nom: g.parent for g in solution["groupes"]} if solution else {}
    )
    score_eval = (
        round(r.score, 6)
        if r is not None and r.faisable and r.score is not None
        else ""
    )
    for e in instance.etudiants:
        groups = aff.get(e.id, {}) if isinstance(aff, dict) else {}
        affecte = bool(groups)
        tp = groups.get("TP", "")
        lv2_groupe = groups.get("LV2", "")
        yield {
            "instance": instance.nom,
            "id": e.id,
            "lv2_choisie": e.lv2,
            "choix_tardif": e.choix_tardif,
            "statut": e.statut,
            "statut_affectation": (
                "affecte"
                if affecte
                else (
                    "non_affecte_cas_particulier"
                    if e.statut != "normal"
                    else "non_resolu"
                )
            ),
            "groupe_lv2": lv2_groupe,
            "groupe_lv1": groups.get("LV1", ""),
            "groupe_tp": tp,
            "groupe_td": groups.get("TD", ""),
            "td_parent": parents.get(tp, "") or "",
            "respecte_choix": (
                lv2_groupe.startswith(f"LV2_{e.lv2}_") if affecte else ""
            ),
            "faisable": bool(r.faisable) if r is not None else False,
            "score_instance": _v(ind, "score"),
            "score_evaluateur": score_eval,
            "methode": "CP-SAT" if affecte else "",
        }


def _ecrire_csv(chemin, colonnes, lignes):
    with open(chemin, "w", newline="", encoding="utf-8-sig") as fichier:
        writer = csv.DictWriter(fichier, fieldnames=colonnes)
        writer.writeheader()
        writer.writerows(lignes)


def exporter(historique=None, sortie=None, avec_solution=True, timeout=None):
    """Écrit les trois CSV et retourne leurs chemins."""
    historique = HISTORIQUE if historique is None else historique
    sortie = os.path.join(RACINE, "exports") if sortie is None else sortie
    os.makedirs(sortie, exist_ok=True)

    solutions = {}
    for instance in historique.lister():
        solutions[instance.nom] = (
            resoudre_instance(instance, timeout) if avec_solution else None
        )

    resume_par_nom = {r["nom"]: r for r in historique.tableau()}
    chemin_instances = os.path.join(sortie, "instances.csv")
    chemin_etudiants = os.path.join(sortie, "etudiants.csv")
    chemin_resultats = os.path.join(sortie, "resultats_etudiants.csv")

    _ecrire_csv(
        chemin_instances,
        COLONNES_INSTANCES,
        [
            _ligne_instance(resume_par_nom[i.nom], solutions[i.nom])
            for i in historique.lister()
        ],
    )

    lignes_etudiants = []
    lignes_resultats = []
    for instance in historique.lister():
        solution = solutions[instance.nom]
        lignes_etudiants.extend(_lignes_etudiants(instance, solution))
        lignes_resultats.extend(_lignes_resultats(instance, solution))

    _ecrire_csv(chemin_etudiants, COLONNES_ETUDIANTS, lignes_etudiants)
    _ecrire_csv(chemin_resultats, COLONNES_RESULTATS, lignes_resultats)
    return chemin_instances, chemin_etudiants, chemin_resultats


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Exporte instances, étudiants et résultats en CSV (Excel)."
    )
    parser.add_argument("--lot", type=int, default=20, help="nombre d'instances du lot")
    parser.add_argument("--seed", type=int, default=7, help="graine du lot")
    parser.add_argument(
        "--timeout",
        type=float,
        default=30,
        help="temps maximal en secondes par instance (défaut : 30)",
    )
    parser.add_argument(
        "--sans-extremes",
        action="store_true",
        help="ne pas inclure les instances extrêmes",
    )
    parser.add_argument(
        "--sans-solution",
        action="store_true",
        help="exporter seulement les données d'entrée (sans lancer le solveur)",
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
    chemins = exporter(
        historique,
        args.sortie,
        avec_solution=not args.sans_solution,
        timeout=args.timeout,
    )

    print(
        "%d instance(s) figée(s), %d étudiant(s)"
        % (len(historique), len(historique.tableau_etudiants()))
    )
    for chemin in chemins:
        print("  ->", chemin)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
