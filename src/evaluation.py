from __future__ import annotations

import math
from dataclasses import dataclass
from math import ceil

CRITERES = ("f1", "f2", "f3")
POIDS_DEFAUT = {"f1": 1.0 / 3.0, "f2": 1.0 / 3.0, "f3": 1.0 / 3.0}
BLOC_GLOBAL = "__global__"


@dataclass(frozen=True, slots=True)
class Resultat:
    """Résultat figé d'une évaluation.

    faisable    : les contraintes dures C1-C3/C5a sont respectées
    score       : 1 - coût pondéré, dans [0, 1], None si infaisable
    cout        : somme des critères normalisés pondérés, None si infaisable
    criteres    : valeurs brutes f1, f2, f3
    normalises  : valeurs f~ dans [0, 1] (0 pour un critère désactivé)
    poids       : poids effectifs après renormalisation sur les critères actifs
    violations  : messages C1/C2/C3/C5a si infaisable
    detail      : effectifs, blocs, bornes de normalisation, k
    """

    faisable: bool
    score: float | None
    cout: float | None
    criteres: dict[str, float]
    normalises: dict[str, float]
    poids: dict[str, float]
    violations: tuple[str, ...]
    detail: dict[str, object]

    def vers_dict(self):
        """Copie mutable du résultat, pour l'export ou l'affichage."""
        return {
            "faisable": self.faisable,
            "score": self.score,
            "cout": self.cout,
            "criteres": dict(self.criteres),
            "normalises": dict(self.normalises),
            "poids": dict(self.poids),
            "violations": list(self.violations),
            "detail": dict(self.detail),
        }


# ---------------------------------------------------------------------------
# Helpers internes
# ---------------------------------------------------------------------------
def _effectifs(aff):
    """Effectif de chaque groupe à partir de l'affectation."""
    eff = {}
    for g in aff.values():
        eff[g] = eff.get(g, 0) + 1
    return eff


def _autorises(e, groupes, compat):
    """Groupes autorisés pour e. Une clé absente de `compat` = tous compatibles."""
    if compat is None or e not in compat:
        return tuple(groupes)
    return tuple(compat[e])


def _inferer_blocs(s, groupes, compat):
    """Associe chaque groupe utilisable à un bloc comparable.

    Avec `compat`, un groupe est dans le bloc de la langue des étudiants qui
    l'ont dans leurs groupes compatibles. Sans `compat`, un seul bloc global.
    Un groupe sans étudiant compatible n'est jamais ouvert : il est ignoré.
    """
    if compat is None:
        return {g: BLOC_GLOBAL for g in groupes}

    blocs = {}
    for g in groupes:
        langues = {
            s[e]
            for e, autorises in compat.items()
            if e in s and g in autorises
        }
        if len(langues) == 1:
            blocs[g] = next(iter(langues))
        elif len(langues) > 1:
            raise ValueError(
                f"groupe {g!r} compatible avec plusieurs langues "
                f"{sorted(langues)} : fournir `blocs` explicitement"
            )
    return blocs


def _bloc_etudiant(e, s, groupes, blocs, compat):
    """Bloc d'un étudiant, déduit de ses groupes compatibles."""
    if compat is None:
        valeurs = set(blocs.values())
        if len(valeurs) == 1:
            return next(iter(valeurs))
        raise ValueError(
            "compat=None ne permet pas plusieurs blocs : fournir `compat` "
            "(ou un seul bloc global)"
        )

    autorises = [g for g in _autorises(e, groupes, compat) if g in blocs]
    if not autorises:
        return None
    bloc = blocs[autorises[0]]
    if any(blocs[g] != bloc for g in autorises):
        raise ValueError(
            f"étudiant {e!r} a des groupes compatibles dans plusieurs blocs : "
            "fournir un `compat` cohérent"
        )
    return bloc


def _repartition_blocs(s, groupes, blocs, compat):
    """Répartit étudiants et groupes par bloc comparable."""
    etudiants_par_bloc = {}
    for e in s:
        bloc = _bloc_etudiant(e, s, groupes, blocs, compat)
        if bloc is None:
            raise ValueError(f"étudiant {e!r} sans groupe compatible")
        etudiants_par_bloc.setdefault(bloc, []).append(e)

    groupes_par_bloc = {}
    for g in groupes:
        if g in blocs:
            groupes_par_bloc.setdefault(blocs[g], []).append(g)
    return etudiants_par_bloc, groupes_par_bloc


def _f1_bloc(eff_bloc):
    """f1 d'un bloc : écart relatif à la cible N_b / k_b, groupes ouverts seuls."""
    ouverts = {g: n for g, n in eff_bloc.items() if n > 0}
    k = len(ouverts)
    if k == 0:
        return 0.0, 0
    N = sum(ouverts.values())
    cible = N / k
    return sum(abs(n - cible) / cible for n in ouverts.values()), k


def _baseline_bloc(etudiants, groupes_bloc, capacites, groupes, compat):
    """Remplissage à la volée : groupes triés, saturés à C(g), C3 respectée.

    C'est le pire cas réaliste, utilisé pour normaliser f1.
    """
    eff = {g: 0 for g in groupes_bloc}
    for e in etudiants:
        autorises = set(_autorises(e, groupes, compat))
        for g in groupes_bloc:
            if eff[g] < capacites[g] and g in autorises:
                eff[g] += 1
                break
        else:
            return None
    return eff


def _f1_max(etudiants_par_bloc, groupes_par_bloc, groupes, compat):
    """f1 du remplissage à la volée, somme sur les blocs.

    Si l'affectation ouvre plus de groupes que ce
    remplissage, son f1 peut dépasser la borne : la normalisation le ramène
    alors à 1 (convention de clip).
    """
    total = 0.0
    for bloc, etudiants in etudiants_par_bloc.items():
        groupes_bloc = sorted(groupes_par_bloc.get(bloc, ()))
        if not groupes_bloc:
            return None
        eff = _baseline_bloc(etudiants, groupes_bloc, groupes, groupes, compat)
        if eff is None:
            return None
        total += _f1_bloc(eff)[0]
    return total


def _f2_min(etudiants_par_bloc, groupes_par_bloc, groupes, capacite_max):
    """Minimum couvrant, par bloc : somme_b ceil(N_b / Cmax_b)."""
    total = 0
    for bloc, etudiants in etudiants_par_bloc.items():
        groupes_bloc = groupes_par_bloc.get(bloc, ())
        if not groupes_bloc:
            return None
        cmax = (
            capacite_max
            if capacite_max is not None
            else max(groupes[g] for g in groupes_bloc)
        )
        if cmax <= 0:
            return None
        total += ceil(len(etudiants) / cmax)
    return total


def _verifier(s, groupes, aff, compat, blocs):
    """Vérifie C1, C2, C3 et C5a. Retourne (violations, effectifs)."""
    violations = []

    manquants = set(s) - set(aff)
    inconnus = set(aff) - set(s)
    groupes_inconnus = {g for g in aff.values() if g not in groupes}
    if manquants:
        violations.append(f"C1: étudiants non affectés {sorted(manquants)}")
    if inconnus:
        violations.append(f"C1: étudiants inconnus {sorted(inconnus)}")
    if groupes_inconnus:
        violations.append(f"C1: groupes inconnus {sorted(groupes_inconnus)}")

    eff = _effectifs(aff)
    for g, capacite in groupes.items():
        if eff.get(g, 0) > capacite:
            violations.append(
                f"C2: {g} a {eff[g]} étudiants pour une capacité de {capacite}"
            )

    if compat is not None:
        for e, g in aff.items():
            if e in compat and g not in compat[e]:
                violations.append(
                    f"C3: {e} ({s.get(e)}) affecté à {g}, non compatible"
                )

    if blocs is not None:
        sans_bloc = {g for g in aff.values() if g in groupes and g not in blocs}
        if sans_bloc:
            violations.append(f"C1: groupes sans bloc {sorted(sans_bloc)}")

    # C5a : les groupes ouverts doivent couvrir l'effectif.
    ouverts = [g for g in groupes if eff.get(g, 0) > 0]
    places = sum(groupes[g] for g in ouverts)
    if places < len(s):
        violations.append(f"C5a: {places} places ouvertes pour {len(s)} étudiants")

    return tuple(violations), eff


def _poids(poids):
    """Fusionne les poids fournis avec les poids uniformes par défaut."""
    resultat = dict(POIDS_DEFAUT)
    if poids:
        for critere, valeur in poids.items():
            if critere not in CRITERES:
                raise ValueError(f"critère inconnu: {critere!r}")
            valeur = float(valeur)
            if not math.isfinite(valeur) or valeur < 0.0:
                raise ValueError(f"poids invalide pour {critere!r}: {valeur!r}")
            resultat[critere] = valeur
    if sum(resultat.values()) <= 0.0:
        raise ValueError("la somme des poids doit être > 0")
    return resultat


def _normaliser(valeur, vmin, vmax):
    """Ramène une valeur dans [0, 1]. None = critère dégénéré (inactif)."""
    if vmax > vmin:
        return min(1.0, max(0.0, (valeur - vmin) / (vmax - vmin)))
    if valeur > vmin:
        return 1.0
    return None


def _agreger(criteres, bornes, poids):
    """Normalise, renormalise les poids sur les critères actifs, agrège."""
    normalises = {}
    actifs = []
    for critere in CRITERES:
        vmin, vmax = bornes[critere]
        valeur = _normaliser(criteres[critere], vmin, vmax)
        if valeur is None:
            normalises[critere] = 0.0
        else:
            normalises[critere] = valeur
            if poids[critere] > 0.0:
                actifs.append(critere)

    total = sum(poids[c] for c in actifs)
    if total <= 0.0:
        return 1.0, 0.0, normalises, {c: 0.0 for c in CRITERES}, actifs

    poids_eff = {c: (poids[c] / total if c in actifs else 0.0) for c in CRITERES}
    cout = sum(poids_eff[c] * normalises[c] for c in actifs)
    return 1.0 - cout, cout, normalises, poids_eff, actifs


# ---------------------------------------------------------------------------
# API publique
# ---------------------------------------------------------------------------
def evaluer(s, groupes, aff, compat=None, blocs=None, poids=None, capacite_max=None):
    """Évalue une affectation et renvoie un `Resultat` avec un score dans [0, 1].

    s             : {étudiant: LV2}
    groupes       : {nom_groupe: capacité}
    aff           : {étudiant: nom_groupe} — l'affectation à noter
    compat        : {étudiant: [groupes autorisés]} (C3) ; None = tous
    blocs         : {nom_groupe: bloc} ; None = inféré depuis `compat`
    poids         : {"f1": w1, "f2": w2, "f3": w3}, uniformes par défaut
    capacite_max  : Cmax imposé pour f2_min ; None = max des capacités du bloc

    Une affectation invalide (C1, C2, C3, C5a) renvoie `faisable=False`,
    `score=None` et la liste des violations.
    """
    s = dict(s)
    groupes = dict(groupes)
    aff = dict(aff)
    compat = None if compat is None else {e: tuple(gs) for e, gs in compat.items()}
    poids = _poids(poids)

    if capacite_max is not None:
        capacite_max = float(capacite_max)
        if not math.isfinite(capacite_max) or capacite_max <= 0.0:
            raise ValueError("capacite_max doit être > 0")

    blocs = _inferer_blocs(s, groupes, compat) if blocs is None else dict(blocs)

    violations, eff = _verifier(s, groupes, aff, compat, blocs)
    if violations:
        return Resultat(
            faisable=False,
            score=None,
            cout=None,
            criteres={c: float("nan") for c in CRITERES},
            normalises={c: float("nan") for c in CRITERES},
            poids=poids,
            violations=violations,
            detail={"effectifs": eff},
        )

    etudiants_par_bloc, groupes_par_bloc = _repartition_blocs(
        s, groupes, blocs, compat
    )
    eff_par_bloc = {
        bloc: {g: eff.get(g, 0) for g in groupes_bloc}
        for bloc, groupes_bloc in groupes_par_bloc.items()
    }

    f1 = sum(_f1_bloc(eb)[0] for eb in eff_par_bloc.values())
    f1_max = _f1_max(etudiants_par_bloc, groupes_par_bloc, groupes, compat)
    f2 = sum(1 for g in groupes if eff.get(g, 0) > 0)
    f2_min = _f2_min(etudiants_par_bloc, groupes_par_bloc, groupes, capacite_max)
    f2_max = len(groupes)
    f3 = 0.0  # LV2 seul : un seul type, donc aucune paire de types différents.
    f3_max = 0

    if f1_max is None or f2_min is None:
        return Resultat(
            faisable=False,
            score=None,
            cout=None,
            criteres={c: float("nan") for c in CRITERES},
            normalises={c: float("nan") for c in CRITERES},
            poids=poids,
            violations=("C5a: places insuffisantes pour couvrir un bloc",),
            detail={"effectifs": eff, "blocs": blocs},
        )

    criteres = {"f1": f1, "f2": float(f2), "f3": f3}
    bornes = {
        "f1": (0.0, f1_max),
        "f2": (float(f2_min), float(f2_max)),
        "f3": (0.0, float(f3_max)),
    }
    score, cout, normalises, poids_eff, actifs = _agreger(criteres, bornes, poids)

    detail = {
        "effectifs": {g: eff.get(g, 0) for g in groupes},
        "blocs": dict(blocs),
        "blocs_effectifs": {
            bloc: {g: eff.get(g, 0) for g in groupes_bloc}
            for bloc, groupes_bloc in groupes_par_bloc.items()
        },
        "effectifs_blocs": {
            bloc: len(etudiants) for bloc, etudiants in etudiants_par_bloc.items()
        },
        "f1_max": f1_max,
        "f2_min": f2_min,
        "f2_max": f2_max,
        "f3_max": f3_max,
        "k": f2,
        "criteres_actifs": list(actifs),
    }

    return Resultat(
        faisable=True,
        score=score,
        cout=cout,
        criteres=criteres,
        normalises=normalises,
        poids=poids_eff,
        violations=(),
        detail=detail,
    )


if __name__ == "__main__":
    import json

    s = {f"A{i}": "Allemand" for i in range(1, 9)}
    s.update({f"E{i}": "Espagnol" for i in range(1, 3)})
    groupes = {"Al1": 5, "Al2": 5, "Es1": 5}
    compat = {e: (["Al1", "Al2"] if s[e] == "Allemand" else ["Es1"]) for e in s}

    aff1 = {
        "A1": "Al1", "A2": "Al1", "A3": "Al1", "A4": "Al1",
        "A5": "Al2", "A6": "Al2", "A7": "Al2", "A8": "Al2",
        "E1": "Es1", "E2": "Es1",
    }
    aff2 = {
        "A1": "Al1", "A2": "Al1", "A3": "Al1", "A4": "Al1", "A5": "Al1",
        "A6": "Al2", "A7": "Al2", "A8": "Al2",
        "E1": "Es1", "E2": "Es1",
    }

    for nom, aff in (("Aff. 1 (4/4/2)", aff1), ("Aff. 2 (5/3/2)", aff2)):
        resultat = evaluer(s, groupes, aff, compat=compat)
        print(nom)
        print(json.dumps(resultat.vers_dict(), ensure_ascii=False, indent=2))
