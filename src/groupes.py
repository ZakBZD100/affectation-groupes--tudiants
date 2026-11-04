"""Construction de groupes à partir d'étudiants — hors générateur.

Le générateur (`generateur_instances.py`) ne produit que des étudiants. Ce
module fournit les helpers opt-in qui proposent des groupes (LV2, LV1, TP, TD)
et leurs capacités, ainsi que les calculs de `k_min` et de `f1` attendu pour
les tests.

Il ne dépend pas de `generateur_instances` : il accepte soit une séquence
d'étudiants, soit un objet exposant un attribut `.etudiants` (une Instance).
"""
from __future__ import annotations

from dataclasses import dataclass
from math import ceil

CAPACITES_DEFAUT = {"LV2": 24, "LV1": 21, "TP": 16, "TD": 36}


@dataclass(frozen=True, slots=True)
class Groupe:
    nom: str
    type: str
    capacite: int
    parent: str | None = None


def _etudiants(objet):
    """Accepte une Instance (attribut .etudiants) ou une séquence d'étudiants."""
    return objet.etudiants if hasattr(objet, "etudiants") else objet


def _actifs(etudiants):
    """Étudiants affectés à la rentrée (les cas particuliers sont exclus)."""
    return [e for e in _etudiants(etudiants) if e.statut == "normal"]


def effectifs_par_langue(etudiants):
    """Effectifs des étudiants normaux, par LV2."""
    effectifs = {}
    for e in _actifs(etudiants):
        effectifs[e.lv2] = effectifs.get(e.lv2, 0) + 1
    return effectifs


def construire_groupes(etudiants, capacites=None, types=("LV2", "LV1", "TP", "TD")):
    """Propose des groupes à partir des étudiants.

    Les étudiants non "normal" sont exclus du calcul des effectifs (ils ne sont
    pas affectés à la rentrée). Retourne des `Groupe` figés.
    """
    cap = dict(CAPACITES_DEFAUT, **(capacites or {}))
    actifs = _actifs(etudiants)
    n = len(actifs)
    groupes = []

    if "LV2" in types:
        for langue in sorted({e.lv2 for e in actifs}):
            cnt = sum(1 for e in actifs if e.lv2 == langue)
            for i in range(1, ceil(cnt / cap["LV2"]) + 1):
                groupes.append(Groupe(f"LV2_{langue}_{i}", "LV2", cap["LV2"]))

    if "LV1" in types:
        for i in range(1, ceil(n / cap["LV1"]) + 1):
            groupes.append(Groupe(f"Ang{i}", "LV1", cap["LV1"]))

    if "TP" in types:
        for i in range(1, ceil(n / cap["TP"]) + 1):
            groupes.append(
                Groupe(f"TP{i}", "TP", cap["TP"], f"TD{1 + (i - 1) // 2}")
            )

    if "TD" in types:
        for i in range(1, ceil(n / cap["TD"]) + 1):
            groupes.append(Groupe(f"TD{i}", "TD", cap["TD"]))

    return tuple(groupes)


def construire_groupes_lv2(etudiants, capacite=None):
    """Raccourci : uniquement les groupes LV2 (un ou plusieurs par langue)."""
    cap = CAPACITES_DEFAUT["LV2"] if capacite is None else capacite
    return construire_groupes(etudiants, {"LV2": cap}, types=("LV2",))


def groupes_vers_dict(groupes):
    """Convertit des `Groupe` en {nom: capacité}, format attendu par le solveur."""
    return {g.nom: g.capacite for g in groupes}


def k_min_lv2(etudiants, capacite=None):
    """Nombre minimal de groupes LV2 compatibles avec les choix de langue."""
    capacite = CAPACITES_DEFAUT["LV2"] if capacite is None else capacite
    return sum(
        ceil(cnt / capacite) for cnt in effectifs_par_langue(etudiants).values()
    )


def f1_attendu_lv2(etudiants, capacite=None):
    """f1 minimal atteignable à k_min, en équilibrant chaque langue.

    Retourne (f1, k_min). f1 est la forme entière du solveur :
    sum_g |k * n(g) - N|.
    """
    capacite = CAPACITES_DEFAUT["LV2"] if capacite is None else capacite
    effectifs = effectifs_par_langue(etudiants)
    N = sum(effectifs.values())
    if N == 0:
        return 0, 0
    k = sum(ceil(cnt / capacite) for cnt in effectifs.values())
    repartition = []
    for cnt in effectifs.values():
        k_l = ceil(cnt / capacite)
        base, reste = divmod(cnt, k_l)
        repartition.extend([base + 1] * reste)
        repartition.extend([base] * (k_l - reste))
    f1 = sum(abs(k * eff - N) for eff in repartition)
    return f1, k
