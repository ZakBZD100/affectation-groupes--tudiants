"""Pont entre l'interface et le solveur du projet.

Toute la logique « préparer les données → résoudre → évaluer » est ici afin
d'être testable sans ouvrir de fenêtre Tkinter.
"""
from __future__ import annotations

from .chemins import RACINE, SRC  # noqa: F401  (configure sys.path)
from evaluation import evaluer
from groupes import PROFILS_CAPACITES, construire_groupes
from test_cpsat import resoudre


def resoudre_interface(instance, params):
    """Résout une `Instance` et retourne le contexte complet pour l'UI/export."""
    capacites = (
        PROFILS_CAPACITES[params["profil"]]
        if isinstance(params["profil"], str)
        else dict(params["profil"])
    )
    groupes = construire_groupes(instance, capacites, marge=params["marge"])
    actifs = [e for e in instance.etudiants if e.statut == "normal"]
    s = {e.id: e.lv2 for e in actifs}
    compat = {
        e.id: [
            g.nom
            for g in groupes
            if g.type != "LV2" or g.nom.startswith("LV2_%s_" % e.lv2)
        ]
        for e in actifs
    }
    statut, aff, eff, ind = resoudre(
        s,
        groupes,
        k=params.get("k"),
        compat=compat,
        poids=params["poids"],
        comparer=params.get("comparer", True),
        timeout=params.get("timeout"),
    )
    evaluation = evaluer(s, groupes, aff, compat=compat) if aff else None
    return {
        "instance": instance,
        "statut": statut,
        "aff": aff,
        "eff": eff,
        "ind": ind,
        "groupes": groupes,
        "evaluation": evaluation,
    }
