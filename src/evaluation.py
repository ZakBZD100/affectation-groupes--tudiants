"""Évaluation d'une affectation multi-type — fonction objectif (semaine 2).

Note une affectation déjà calculée (CP-SAT, greedy, référence manuelle) selon
les critères souples du PDF `semaine2_formalisation` :

    f1 : équilibre intra-bloc, cible N_b / k_b
    f2 : nombre de groupes ouverts
    f3 : conflits de parallélisation entre types

Chaque critère est normalisé dans [0, 1] entre un minimum et un maximum
réalistes, puis agrégé avec des poids (uniformes par défaut) :

    score = 1 - somme_c w_c * f~_c  dans [0, 1]   (1 = parfait)

Contraintes dures vérifiées : C1 (un groupe par type), C2 (capacité), C3
(choix respecté), C4 (TP -> TD parent), C5a (assez de places ouvertes par
bloc) et C8 (2 TP ouverts par TD ouvert). Une affectation qui les viole est
rejetée : `faisable=False`, `score=None`, violations listées.

Deux formats d'entrée sont acceptés :

- multi-type : `groupes` est une séquence de `groupes.Groupe`, et
  `aff = {e: {"LV2": g, "LV1": g, "TP": g, "TD": g}}` ;
- mono-type (compatibilité) : `groupes` est un dict {nom: capacité} et
  `aff = {e: g}`. Les blocs sont alors inférés depuis `compat` (un bloc par
  langue pour le LV2, un bloc global sinon).

Exemple (PDF) :

    >>> s = {f"A{i}": "Allemand" for i in range(1, 9)}
    >>> s.update({f"E{i}": "Espagnol" for i in range(1, 3)})
    >>> groupes = {"Al1": 5, "Al2": 5, "Es1": 5}
    >>> compat = {e: (["Al1", "Al2"] if s[e] == "Allemand" else ["Es1"])
    ...           for e in s}
    >>> aff = {"A1": "Al1", "A2": "Al1", "A3": "Al1", "A4": "Al1",
    ...        "A5": "Al2", "A6": "Al2", "A7": "Al2", "A8": "Al2",
    ...        "E1": "Es1", "E2": "Es1"}
    >>> evaluer(s, groupes, aff, compat=compat).score
    1.0
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from math import ceil

CRITERES = ("f1", "f2", "f3")
POIDS_DEFAUT = {"f1": 1.0 / 3.0, "f2": 1.0 / 3.0, "f3": 1.0 / 3.0}
BLOC_GLOBAL = "__global__"


@dataclass(frozen=True, slots=True)
class _G:
    """Vue interne d'un groupe (accepte dict ou groupes.Groupe)."""

    nom: str
    type: str
    capacite: int
    parent: str | None = None


@dataclass(frozen=True, slots=True)
class Resultat:
    """Résultat figé d'une évaluation.

    faisable    : les contraintes dures C1-C4/C5a/C8 sont respectées
    score       : 1 - coût pondéré, dans [0, 1], None si infaisable
    cout        : somme des critères normalisés pondérés, None si infaisable
    criteres    : valeurs brutes f1, f2, f3
    normalises  : valeurs f~ dans [0, 1] (0 pour un critère désactivé)
    poids       : poids effectifs après renormalisation sur les critères actifs
    violations  : messages C1-C4/C5a/C8 si infaisable
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
# Normalisation des entrées
# ---------------------------------------------------------------------------
def _type_depuis_nom(nom):
    if nom.startswith("LV2_"):
        return "LV2"
    if nom.startswith("LV1_"):
        return "LV1"
    if nom.startswith("TD"):
        return "TD"
    if nom.startswith("TP"):
        return "TP"
    return "G"


def _normaliser_groupes(groupes):
    """Retourne (par_nom, multi_type)."""
    if isinstance(groupes, dict):
        par_nom = {
            nom: _G(nom, _type_depuis_nom(nom), cap)
            for nom, cap in groupes.items()
        }
        return par_nom, False

    par_nom = {}
    for g in groupes:
        par_nom[g.nom] = _G(
            g.nom, g.type, g.capacite, getattr(g, "parent", None)
        )
    return par_nom, True


def _normaliser_aff(aff, par_nom):
    """Retourne {e: {type: nom_groupe}} ; accepte une affectation plate."""
    types = {g.type for g in par_nom.values()}
    type_unique = next(iter(types)) if len(types) == 1 else BLOC_GLOBAL
    resultat = {}
    for e, valeur in aff.items():
        if isinstance(valeur, str):
            g = par_nom.get(valeur)
            type_ = g.type if g is not None else type_unique
            resultat[e] = {type_: valeur}
        elif isinstance(valeur, dict):
            resultat[e] = dict(valeur)
        else:
            raise TypeError(f"affectation invalide pour {e!r}: {valeur!r}")
    return resultat


def _types_restreints(par_nom, compat):
    """Types sur lesquels `compat` impose une restriction (C3)."""
    if not compat:
        return set()
    return {
        par_nom[nom].type
        for autorises in compat.values()
        for nom in autorises
        if nom in par_nom
    }


def _autorises(e, par_nom, compat, restreints):
    """Groupes autorisés pour e (C3) ; un type non restreint est libre."""
    if compat is None or e not in compat:
        return set(par_nom)
    autorises = {
        nom for nom, g in par_nom.items() if g.type not in restreints
    }
    autorises |= {nom for nom in compat[e] if nom in par_nom}
    return autorises


# ---------------------------------------------------------------------------
# Blocs comparables
# ---------------------------------------------------------------------------
def _blocs_ancien(s, par_nom, compat):
    """Ancien comportement mono-type : blocs inférés depuis `compat`."""
    if compat is None:
        return {nom: BLOC_GLOBAL for nom in par_nom}

    blocs = {}
    for nom in par_nom:
        langues = {
            s[e]
            for e, autorises in compat.items()
            if e in s and nom in autorises
        }
        if len(langues) == 1:
            blocs[nom] = next(iter(langues))
        elif len(langues) > 1:
            raise ValueError(
                f"groupe {nom!r} compatible avec plusieurs langues "
                f"{sorted(langues)} : fournir `blocs` explicitement"
            )
    return blocs


def _blocs_multi(s, par_nom, compat, restreints):
    """Nouveau comportement : un bloc par type, LV2 par langue si restreint."""
    par_type = {}
    for g in par_nom.values():
        par_type.setdefault(g.type, []).append(g)

    blocs = {}
    for type_, gs in par_type.items():
        for g in gs:
            autorises = {
                e for e in s if g.nom in _autorises(e, par_nom, compat, restreints)
            }
            if not autorises:
                continue  # groupe que personne ne peut rejoindre
            if type_ == "LV2" and "LV2" in restreints:
                langues = {s[e] for e in autorises}
                if len(langues) > 1:
                    raise ValueError(
                        f"groupe {g.nom!r} compatible avec plusieurs langues "
                        f"{sorted(langues)}"
                    )
                blocs[g.nom] = f"LV2:{next(iter(langues))}"
            else:
                blocs[g.nom] = type_
    return blocs


def _blocs_de(s, par_nom, multi_type, compat, blocs):
    if blocs is not None:
        return dict(blocs)
    if multi_type:
        restreints = _types_restreints(par_nom, compat)
        return _blocs_multi(s, par_nom, compat, restreints)
    return _blocs_ancien(s, par_nom, compat)


# ---------------------------------------------------------------------------
# Vérification des contraintes dures
# ---------------------------------------------------------------------------
def _effectifs(aff_multi):
    eff = {}
    for affectation in aff_multi.values():
        for nom in affectation.values():
            eff[nom] = eff.get(nom, 0) + 1
    return eff


def _verifier(s, par_nom, aff_multi, compat, restreints, blocs):
    violations = []
    types_presents = sorted({g.type for g in par_nom.values()})

    manquants = set(s) - set(aff_multi)
    inconnus = set(aff_multi) - set(s)
    if manquants:
        violations.append(f"C1: étudiants non affectés {sorted(manquants)}")
    if inconnus:
        violations.append(f"C1: étudiants inconnus {sorted(inconnus)}")

    for e in s:
        affectation = aff_multi.get(e)
        if affectation is None:
            continue
        for type_ in affectation:
            if type_ not in types_presents:
                violations.append(f"C1: {e} a un type inconnu {type_!r}")
        for type_ in types_presents:
            assignes = [
                nom for t, nom in affectation.items() if t == type_
            ]
            if len(assignes) != 1:
                violations.append(
                    f"C1: {e} doit avoir exactement un groupe de type "
                    f"{type_} (a {assignes})"
                )
                continue
            nom = assignes[0]
            if nom not in par_nom:
                violations.append(f"C1: groupe inconnu {nom!r}")
                continue
            if nom not in blocs:
                violations.append(f"C1: groupe sans bloc {nom!r}")
            if nom not in _autorises(e, par_nom, compat, restreints):
                violations.append(
                    f"C3: {e} ({s.get(e)}) affecté à {nom}, non compatible"
                )

    eff = _effectifs(aff_multi)
    for nom, g in par_nom.items():
        if eff.get(nom, 0) > g.capacite:
            violations.append(
                f"C2: {nom} a {eff[nom]} étudiants pour une capacité de "
                f"{g.capacite}"
            )

    # C4 : un étudiant dans un TP est dans son TD parent.
    for e in s:
        affectation = aff_multi.get(e, {})
        tp = affectation.get("TP")
        if tp is None or tp not in par_nom:
            continue
        parent = par_nom[tp].parent
        if parent is None or parent not in par_nom:
            continue
        td = affectation.get("TD")
        if td != parent:
            violations.append(
                f"C4: {e} est dans {tp} mais pas dans son TD parent {parent}"
            )

    # C8 : exactement 2 TP ouverts par TD ouvert (même règle que le solveur).
    enfants = {}
    for nom, g in par_nom.items():
        if g.type == "TP" and g.parent:
            enfants.setdefault(g.parent, []).append(nom)
    if enfants:
        for g in par_nom.values():
            if g.type != "TD":
                continue
            cs = enfants.get(g.nom, ())
            if len(cs) < 2:
                violations.append(
                    f"C8: {g.nom} n'a que {len(cs)} TP enfants (2 attendus)"
                )
                continue
            ouverts = sum(1 for c in cs if eff.get(c, 0) > 0)
            attendu = 2 if eff.get(g.nom, 0) > 0 else 0
            if ouverts != attendu:
                violations.append(
                    f"C8: {g.nom} ouvre {ouverts} TP, {attendu} attendu "
                    "(2 par TD)"
                )

    # C5a : assez de places ouvertes dans chaque bloc.
    groupes_par_bloc = {}
    for nom, bloc in blocs.items():
        groupes_par_bloc.setdefault(bloc, []).append(nom)
    for bloc, noms in groupes_par_bloc.items():
        nb = sum(
            1
            for affectation in aff_multi.values()
            if any(affectation.get(par_nom[n].type) == n for n in noms)
        )
        places = sum(
            par_nom[n].capacite for n in noms if eff.get(n, 0) > 0
        )
        if places < nb:
            violations.append(
                f"C5a: {places} places ouvertes pour {nb} étudiants "
                f"dans le bloc {bloc!r}"
            )

    return tuple(violations), eff


# ---------------------------------------------------------------------------
# Critères
# ---------------------------------------------------------------------------
def _f1_bloc(eff_bloc):
    """f1 d'un bloc : écart relatif à la cible N_b / k_b, groupes ouverts seuls."""
    ouverts = {g: n for g, n in eff_bloc.items() if n > 0}
    k = len(ouverts)
    if k == 0:
        return 0.0, 0
    N = sum(ouverts.values())
    cible = N / k
    return sum(abs(n - cible) / cible for n in ouverts.values()), k


def _baseline_bloc(etudiants, groupes_bloc, par_nom, autorises):
    """Remplissage à la volée : groupes triés, saturés à C(g), C3 respectée."""
    eff = {nom: 0 for nom in groupes_bloc}
    for e in etudiants:
        for nom in groupes_bloc:
            if (
                eff[nom] < par_nom[nom].capacite
                and nom in autorises[e]
            ):
                eff[nom] += 1
                break
        else:
            return None
    return eff


def _f1_max(etudiants_par_bloc, groupes_par_bloc, par_nom, autorises):
    """f1 du remplissage à la volée, somme sur les blocs."""
    total = 0.0
    for bloc, etudiants in etudiants_par_bloc.items():
        groupes_bloc = sorted(groupes_par_bloc.get(bloc, ()))
        if not groupes_bloc:
            return None
        eff = _baseline_bloc(etudiants, groupes_bloc, par_nom, autorises)
        if eff is None:
            return None
        total += _f1_bloc(eff)[0]
    return total


def _f2_bornes_bloc(
    etudiants_par_bloc, groupes_par_bloc, par_nom, capacite_max
):
    """Bornes de f2, bloc par bloc : (ceil(N_b/Cmax_b), |G(b)|)."""
    bornes = {}
    for bloc, etudiants in etudiants_par_bloc.items():
        groupes_bloc = groupes_par_bloc.get(bloc, ())
        if not groupes_bloc:
            return None
        cmax = (
            capacite_max
            if capacite_max is not None
            else max(par_nom[nom].capacite for nom in groupes_bloc)
        )
        if cmax <= 0:
            return None
        bornes[bloc] = (ceil(len(etudiants) / cmax), len(groupes_bloc))
    return bornes


def _f3(s, aff_multi, par_nom, blocs):
    """Paires de groupes de types différents partageant un étudiant."""
    paires = set()
    for e in s:
        items = sorted(aff_multi.get(e, {}).items())
        for i in range(len(items)):
            t1, g1 = items[i]
            for j in range(i + 1, len(items)):
                t2, g2 = items[j]
                if t1 != t2:
                    paires.add(tuple(sorted(((t1, g1), (t2, g2)))))
    f3 = float(len(paires))

    par_type = {}
    for nom in blocs:
        par_type.setdefault(par_nom[nom].type, []).append(nom)
    types = sorted(par_type)
    f3_max = 0
    for i, t1 in enumerate(types):
        for t2 in types[i + 1:]:
            f3_max += len(par_type[t1]) * len(par_type[t2])
    return f3, f3_max


# ---------------------------------------------------------------------------
# Agrégation
# ---------------------------------------------------------------------------
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
    groupes       : séquence de `Groupe` (multi-type) ou dict {nom: capacité}
    aff           : {e: {type: groupe}} (multi-type) ou {e: groupe} (mono-type)
    compat        : {étudiant: [groupes autorisés]} (C3) ; None = tous
    blocs         : {nom_groupe: bloc} ; None = inféré depuis les types/compat
    poids         : {"f1": w1, "f2": w2, "f3": w3}, uniformes par défaut
    capacite_max  : Cmax imposé pour f2_min ; None = max des capacités du bloc

    Une affectation invalide (C1, C2, C3, C4, C5a, C8) renvoie `faisable=False`,
    `score=None` et la liste des violations.
    """
    s = dict(s)
    par_nom, multi_type = _normaliser_groupes(groupes)
    aff_multi = _normaliser_aff(dict(aff), par_nom)
    compat = None if compat is None else {e: tuple(gs) for e, gs in compat.items()}
    poids = _poids(poids)

    if capacite_max is not None:
        capacite_max = float(capacite_max)
        if not math.isfinite(capacite_max) or capacite_max <= 0.0:
            raise ValueError("capacite_max doit être > 0")

    restreints = _types_restreints(par_nom, compat)
    blocs = _blocs_de(s, par_nom, multi_type, compat, blocs)
    autorises = {
        e: _autorises(e, par_nom, compat, restreints) for e in s
    }

    violations, eff = _verifier(
        s, par_nom, aff_multi, compat, restreints, blocs
    )
    if violations:
        return Resultat(
            faisable=False,
            score=None,
            cout=None,
            criteres={c: float("nan") for c in CRITERES},
            normalises={c: float("nan") for c in CRITERES},
            poids=poids,
            violations=violations,
            detail={"effectifs": eff, "blocs": dict(blocs)},
        )

    groupes_par_bloc = {}
    for nom, bloc in blocs.items():
        groupes_par_bloc.setdefault(bloc, []).append(nom)

    etudiants_par_bloc = {bloc: [] for bloc in groupes_par_bloc}
    for e in s:
        for type_, nom in aff_multi.get(e, {}).items():
            if nom in blocs:
                etudiants_par_bloc[blocs[nom]].append(e)

    eff_par_bloc = {
        bloc: {nom: eff.get(nom, 0) for nom in noms}
        for bloc, noms in groupes_par_bloc.items()
    }

    f1 = sum(_f1_bloc(eb)[0] for eb in eff_par_bloc.values())
    f1_max = _f1_max(etudiants_par_bloc, groupes_par_bloc, par_nom, autorises)
    f2 = float(sum(1 for nom in par_nom if eff.get(nom, 0) > 0))
    f2_bornes = _f2_bornes_bloc(
        etudiants_par_bloc, groupes_par_bloc, par_nom, capacite_max
    )
    f2_min = None if f2_bornes is None else sum(lo for lo, _ in f2_bornes.values())
    f2_max = None if f2_bornes is None else sum(hi for _, hi in f2_bornes.values())
    f3, f3_max = _f3(s, aff_multi, par_nom, blocs)

    if f1_max is None or f2_bornes is None:
        return Resultat(
            faisable=False,
            score=None,
            cout=None,
            criteres={c: float("nan") for c in CRITERES},
            normalises={c: float("nan") for c in CRITERES},
            poids=poids,
            violations=("C5a: places insuffisantes pour couvrir un bloc",),
            detail={"effectifs": eff, "blocs": dict(blocs)},
        )

    criteres = {"f1": f1, "f2": f2, "f3": f3}
    bornes = {
        "f1": (0.0, f1_max),
        "f2": (float(f2_min), float(f2_max)),
        "f3": (0.0, float(f3_max)),
    }
    score, cout, normalises, poids_eff, actifs = _agreger(criteres, bornes, poids)

    k_par_type = {}
    for nom in par_nom:
        if eff.get(nom, 0) > 0:
            type_ = par_nom[nom].type
            k_par_type[type_] = k_par_type.get(type_, 0) + 1

    detail = {
        "effectifs": {nom: eff.get(nom, 0) for nom in par_nom},
        "blocs": dict(blocs),
        "blocs_effectifs": {
            bloc: {nom: eff.get(nom, 0) for nom in noms}
            for bloc, noms in groupes_par_bloc.items()
        },
        "effectifs_blocs": {
            bloc: len(etudiants) for bloc, etudiants in etudiants_par_bloc.items()
        },
        "f1_max": f1_max,
        "f2_min": f2_min,
        "f2_max": f2_max,
        "f2_bornes_blocs": {
            bloc: {"min": lo, "max": hi}
            for bloc, (lo, hi) in f2_bornes.items()
        },
        "f3_max": f3_max,
        "k": int(f2),
        "k_par_type": k_par_type,
        "types": sorted({g.type for g in par_nom.values()}),
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
