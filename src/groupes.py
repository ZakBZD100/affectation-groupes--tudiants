"""Construction de groupes à partir d'étudiants — hors générateur.

Le générateur (`generateur_instances.py`) ne produit que des étudiants. Ce
module propose des groupes (LV2, LV1, TP, TD) à partir d'un profil de
capacités **explicite** : il n'existe plus de capacité par défaut cachée.

Pour tester le solveur sur des cas variés, `PROFILS_CAPACITES` fournit quatre
profils nommés et `variantes_capacites` en génère des perturbations entières.

Structure hiérarchique : un TP a exactement un TD parent, et un TD ouvert
porte exactement `tp_par_td` TP ouverts (contrainte C8, valeur de règle de
l'établissement transmise en paramètre — défaut `TP_PAR_TD = 2`).
Le pool propose `tp_par_td` enfants par TD : c'est le modèle qui décide quels
TD ouvrir, jamais le générateur.

Il ne dépend pas de `generateur_instances` : il accepte soit une séquence
d'étudiants, soit un objet exposant un attribut `.etudiants` (une Instance).
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from math import ceil

TYPES = ("LV2", "LV1", "TP", "TD")

# Règle de l'établissement (C8) : un TD ouvert porte exactement 2 TP ouverts.
# Valeur par défaut, transmise partout en paramètre `tp_par_td` — ce n'est
# pas une constante codée en dur dans le modèle.
TP_PAR_TD = 2

# Profils de capacités maximales C(g), en places par groupe.
# Aucun n'est appliqué implicitement : l'appelant doit en choisir un.
PROFILS_CAPACITES = {
    "standard": {"LV2": 24, "LV1": 24, "TP": 16, "TD": 40},
    "serre": {"LV2": 18, "LV1": 18, "TP": 10, "TD": 30},
    "large": {"LV2": 30, "LV1": 30, "TP": 20, "TD": 50},
    "heterogene": {"LV2": 24, "LV1": 16, "TP": 12, "TD": 40},
}


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


def valider_capacites(capacites, types=TYPES):
    """Vérifie qu'un profil est complet et strictement positif.

    `capacites` est obligatoire : plus de valeurs par défaut implicites.
    """
    if capacites is None:
        raise TypeError("capacites obligatoires (plus de valeurs par défaut)")
    manquants = [t for t in types if t not in capacites]
    if manquants:
        raise ValueError(f"capacités manquantes pour {manquants}")
    resultat = {}
    for t in types:
        cap = capacites[t]
        if not isinstance(cap, int) or isinstance(cap, bool) or cap <= 0:
            raise ValueError(f"capacité invalide pour {t}: {cap!r}")
        resultat[t] = cap
    return resultat


def variantes_capacites(profil="standard", n_variantes=3, amplitude=0.2, seed=0):
    """Génère des variantes entières d'un profil de capacités.

    Chaque capacité est perturbée indépendamment de ±amplitude, puis bornée à
    au moins 1. Le profil de base n'est pas inclus dans le résultat.
    """
    base = PROFILS_CAPACITES[profil] if isinstance(profil, str) else dict(profil)
    base = valider_capacites(base)
    if n_variantes < 0:
        raise ValueError("n_variantes doit être >= 0")
    if not 0.0 <= amplitude <= 1.0:
        raise ValueError("amplitude doit être dans [0, 1]")
    rng = random.Random(seed)
    variantes = []
    for _ in range(n_variantes):
        variante = {}
        for t in TYPES:
            facteur = 1.0 + rng.uniform(-amplitude, amplitude)
            variante[t] = max(1, int(round(base[t] * facteur)))
        variantes.append(variante)
    return tuple(variantes)


def construire_groupes(
    etudiants, capacites, types=TYPES, marge=1, tp_par_td=TP_PAR_TD
):
    """Propose un pool de groupes à partir des étudiants.

    Les étudiants non "normal" sont exclus du calcul des effectifs (ils ne sont
    pas affectés à la rentrée). Retourne des `Groupe` figés.

    Le pool contient `ceil(N/C) + marge` groupes par bloc, ce qui laisse au
    solveur la liberté d'en ouvrir un de plus que le minimum. `capacites` doit
    contenir une capacité pour chaque type demandé.

    TP/TD : les TD sont créés en premier, en nombre suffisant pour que
    `tp_par_td` TP par TD tiennent l'effectif (au plus min(C_TD,
    tp_par_td*C_TP) étudiants par TD), puis chaque TD reçoit exactement
    `tp_par_td` enfants. Le solveur choisit ensuite quels TD ouvrir (C8).
    """
    if marge < 0:
        raise ValueError("marge doit être >= 0")
    types = tuple(types)
    inconnus = [t for t in types if t not in TYPES]
    if inconnus:
        raise ValueError(f"types inconnus: {inconnus}")
    if "TP" in types and "TD" not in types:
        raise ValueError("les TP ont besoin des TD parents : ajouter 'TD' aux types")
    cap = valider_capacites(capacites, types)

    actifs = _actifs(etudiants)
    n = len(actifs)
    groupes = []

    if "LV2" in types:
        for langue in sorted({e.lv2 for e in actifs}):
            cnt = sum(1 for e in actifs if e.lv2 == langue)
            for i in range(1, ceil(cnt / cap["LV2"]) + marge + 1):
                groupes.append(Groupe(f"LV2_{langue}_{i}", "LV2", cap["LV2"]))

    if "LV1" in types:
        for i in range(1, ceil(n / cap["LV1"]) + marge + 1):
            groupes.append(Groupe(f"LV1_{i}", "LV1", cap["LV1"]))

    noms_td = []
    if "TD" in types:
        # Un TD porte tp_par_td TP : il ne peut héberger que
        # min(C_TD, tp_par_td * C_TP) étudiants (C2 et C8).
        par_td = cap["TD"]
        if "TP" in types:
            par_td = min(cap["TD"], tp_par_td * cap["TP"])
        for i in range(1, ceil(n / par_td) + marge + 1):
            nom = f"TD{i}"
            noms_td.append(nom)
            groupes.append(Groupe(nom, "TD", cap["TD"]))

    if "TP" in types:
        # tp_par_td TP consécutifs par TD : chaque TD du pool a ses enfants.
        for i in range(1, tp_par_td * len(noms_td) + 1):
            parent = noms_td[(i - 1) // tp_par_td]
            groupes.append(Groupe(f"TP{i}", "TP", cap["TP"], parent))

    return tuple(groupes)


def construire_groupes_lv2(etudiants, capacite, marge=1):
    """Raccourci : uniquement les groupes LV2. La capacité est obligatoire."""
    return construire_groupes(
        etudiants, {"LV2": capacite}, types=("LV2",), marge=marge
    )


def groupes_vers_dict(groupes):
    """Convertit des `Groupe` en {nom: capacité}, format simple pour l'affichage."""
    return {g.nom: g.capacite for g in groupes}


def groupes_par_type(groupes):
    """Regroupe des `Groupe` par type : {type: [Groupe, ...]}."""
    resultat = {}
    for g in groupes:
        resultat.setdefault(g.type, []).append(g)
    return resultat


def k_min_lv2(etudiants, capacite):
    """Nombre minimal de groupes LV2 compatibles avec les choix de langue."""
    if capacite is None:
        raise TypeError("capacite obligatoire (plus de valeur par défaut)")
    if capacite <= 0:
        raise ValueError("capacite doit être > 0")
    return sum(
        ceil(cnt / capacite) for cnt in effectifs_par_langue(etudiants).values()
    )


def f1_attendu_lv2(etudiants, capacite):
    """f1 minimal atteignable à k_min, en équilibrant chaque bloc de langue.

    Retourne (f1, k_min). f1 est la forme entière du solveur, calculée bloc
    par bloc : sum_b sum_g |k_b * n(g) - N_b|.
    """
    if capacite is None:
        raise TypeError("capacite obligatoire (plus de valeur par défaut)")
    if capacite <= 0:
        raise ValueError("capacite doit être > 0")
    effectifs = effectifs_par_langue(etudiants)
    if not effectifs:
        return 0, 0
    total = 0
    k = 0
    for cnt in effectifs.values():
        k_l = ceil(cnt / capacite)
        k += k_l
        base, reste = divmod(cnt, k_l)
        repartition = [base + 1] * reste + [base] * (k_l - reste)
        total += sum(abs(k_l * eff - cnt) for eff in repartition)
    return total, k
