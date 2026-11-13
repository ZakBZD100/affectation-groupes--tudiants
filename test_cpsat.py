"""Tests CP-SAT — affectation multi-type (LV2, LV1, TP, TD), projet 3A.

Le modèle suit la formalisation de la semaine 2 :

    C1  un groupe par type pour chaque étudiant
    C2  n(g) <= C(g)
    C3  x(e, g) = 0 si g incompatible avec s(e)
    C4  x(e, TP) <= x(e, TD parent)
    C5a assez de places ouvertes par bloc
    C5b on n'ouvre que ce qui sert
    C6  rien dans un groupe fermé
    C7  pas de groupe ouvert vide
    C8  exactement 2 TP ouverts par TD ouvert

Le solveur choisit k(t) : aucun nombre de groupes n'est imposé de l'extérieur.
L'objectif agrège f1 (équilibre), f2 (groupes ouverts) et f3 (paires de
groupes de types différents qui partagent un étudiant), avec les mêmes poids
que l'évaluateur (1/3 chacun par défaut) : le modèle minimise exactement ce
que le juge note. Normalisation entière et exacte. Les groupes sont des
`groupes.Groupe` (nom, type, capacité, parent) ; un dict {nom: capacité}
reste accepté pour la compatibilité.
"""
import math
import os
import sys
from fractions import Fraction

from ortools.sat.python import cp_model

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
from groupes import Groupe, TP_PAR_TD, groupes_par_type  # noqa: E402

POIDS_DEFAUT = {"f1": 1.0 / 3.0, "f2": 1.0 / 3.0, "f3": 1.0 / 3.0}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _normaliser_groupes(groupes):
    """Accepte une séquence de Groupe ou un dict {nom: capacité}."""
    if isinstance(groupes, dict):
        resultat = []
        for nom, cap in groupes.items():
            if nom.startswith("LV2_"):
                type_ = "LV2"
            elif nom.startswith("LV1_"):
                type_ = "LV1"
            elif nom.startswith("TD"):
                type_ = "TD"
            else:
                type_ = "TP"
            resultat.append(Groupe(nom, type_, cap))
        return tuple(resultat)
    return tuple(groupes)


def types_restreints(groupes, compat):
    """Types sur lesquels `compat` impose une restriction (C3).

    Un type absent de `compat` est libre : tous ses groupes sont autorisés.
    C'est ce qui permet de ne restreindre que le LV2 sans lister les autres.
    """
    if not compat:
        return set()
    par_nom = {g.nom: g for g in groupes}
    return {
        par_nom[nom].type
        for autorises in compat.values()
        for nom in autorises
        if nom in par_nom
    }


def admis_de(s, groupes, compat):
    """Groupes autorisés par étudiant (C3). None si un étudiant n'a rien."""
    par_nom = {g.nom: g for g in groupes}
    restreints = types_restreints(groupes, compat)
    a = {}
    for e in s:
        if compat is None or e not in compat:
            autorises = set(par_nom)
        else:
            autorises = {
                nom for nom, g in par_nom.items() if g.type not in restreints
            }
            autorises |= {nom for nom in compat[e] if nom in par_nom}
        if not autorises:
            return None
        a[e] = autorises
    return a


def blocs_de(s, groupes, a, compat):
    """Découpe en blocs comparables et associe chaque étudiant à un bloc/type.

    LV2 restreint par `compat` : un bloc par langue. Sinon (LV1, TP, TD, ou
    LV2 non restreint) : un bloc unique par type.
    """
    par_type = groupes_par_type(groupes)
    restreints = types_restreints(groupes, compat)
    blocs = []
    bloc_etudiant = {}

    for type_, gs in sorted(par_type.items()):
        if type_ == "LV2" and "LV2" in restreints:
            langue_g = {}
            for g in gs:
                langues = {s[e] for e in s if g.nom in a[e]}
                if not langues:
                    continue
                if len(langues) > 1:
                    raise ValueError(
                        f"groupe {g.nom!r} compatible avec plusieurs langues "
                        f"{sorted(langues)}"
                    )
                langue_g[g.nom] = next(iter(langues))
            par_langue = {}
            for g in gs:
                if g.nom in langue_g:
                    par_langue.setdefault(langue_g[g.nom], []).append(g.nom)
            for langue in sorted(par_langue):
                idx = len(blocs)
                blocs.append(
                    {"type": type_, "cle": langue, "groupes": par_langue[langue]}
                )
                for e in s:
                    if s[e] == langue:
                        bloc_etudiant[(e, type_)] = idx
        else:
            noms = [g.nom for g in gs if any(g.nom in a[e] for e in s)]
            if not noms:
                return None
            idx = len(blocs)
            blocs.append({"type": type_, "cle": type_, "groupes": noms})
            for e in s:
                bloc_etudiant[(e, type_)] = idx

    for e in s:
        for type_ in par_type:
            if (e, type_) not in bloc_etudiant:
                return None

    nb = [0] * len(blocs)
    for idx in bloc_etudiant.values():
        nb[idx] += 1
    return blocs, bloc_etudiant, nb


def _baseline_bloc(etudiants, bloc, par_nom, a):
    """Remplissage à la volée : groupes triés, saturés à C(g), C3 respectée."""
    eff = {nom: 0 for nom in bloc}
    for e in etudiants:
        for nom in bloc:
            if eff[nom] < par_nom[nom].capacite and nom in a[e]:
                eff[nom] += 1
                break
        else:
            return None
    return eff


def _f1_max_int(blocs, nb, bloc_etudiant, par_nom, a):
    """f1_max (pire remplissage à la volée) en entier, et L = lcm des N_b.

    f1_b = sum_g |k_b n(g) - N_b| / N_b. En multipliant par L (multiple de
    tous les N_b), on garde des entiers exacts.
    """
    positifs = [n for n in nb if n > 0]
    if not positifs:
        return 0, 1
    L = 1
    for n in positifs:
        L = math.lcm(L, n)

    total = 0
    for idx, bloc in enumerate(blocs):
        if nb[idx] == 0:
            continue
        etudiants = [
            e for (e, type_), i in bloc_etudiant.items() if i == idx
        ]
        eff = _baseline_bloc(etudiants, bloc["groupes"], par_nom, a)
        if eff is None:
            return None, L
        ouverts = [n for n in eff.values() if n > 0]
        k_b = len(ouverts)
        f1_b = sum(abs(k_b * n - nb[idx]) for n in ouverts)
        total += f1_b * (L // nb[idx])
    return total, L


def _f2_min(blocs, nb, par_nom):
    total = 0
    for idx, bloc in enumerate(blocs):
        if nb[idx] == 0:
            continue
        cmax = max(par_nom[nom].capacite for nom in bloc["groupes"])
        total += -(-nb[idx] // cmax)
    return total


def _peuvent_partager(g1, g2):
    """Faux pour une paire TP/TD non parente : C1 + C4 l'interdisent."""
    if g1.type == "TP" and g2.type == "TD" and g1.parent is not None:
        return g1.parent == g2.nom
    if g2.type == "TP" and g1.type == "TD" and g2.parent is not None:
        return g2.parent == g1.nom
    return True


def _coefficients(poids, bornes):
    """Coefficients entiers de l'objectif pondéré f1 + f2 + f3.

    bornes = {"f1": (0, f1_max_int), "f2": (f2_min, f2_max), "f3": (0, f3_max)}.
    Minimiser somme_c coef_c * valeur_c revient à minimiser
    somme_c w_c * (valeur_c - lo_c)/(hi_c - lo_c), exactement (entiers).
    Poids nul ou critère dégénéré (hi == lo) : coefficient 0, critère inactif
    (l'évaluateur fait pareil).
    """
    inconnus = set(poids) - {"f1", "f2", "f3"}
    if inconnus:
        raise ValueError(f"critère inconnu: {sorted(inconnus)}")
    w = {}
    for critere in ("f1", "f2", "f3"):
        valeur = Fraction(str(poids.get(critere, 0.0))).limit_denominator(10000)
        if valeur < 0:
            raise ValueError("les poids doivent être >= 0")
        w[critere] = valeur
    if sum(w.values()) == 0:
        raise ValueError("la somme des poids doit être > 0")

    denom = 1
    for valeur in w.values():
        denom = math.lcm(denom, valeur.denominator)
    a = {c: w[c].numerator * (denom // w[c].denominator) for c in w}

    # écart de chaque critère ; 0 = inactif
    ecarts = {}
    for critere, (lo, hi) in bornes.items():
        delta = hi - lo
        ecarts[critere] = delta if (delta > 0 and a[critere] > 0) else 0
    D = 1
    for delta in ecarts.values():
        if delta:
            D = math.lcm(D, delta)

    return {
        c: (a[c] * D // delta if delta else 0)
        for c, delta in ecarts.items()
    }


# ---------------------------------------------------------------------------
# Modèle
# ---------------------------------------------------------------------------
def bati(s, groupes, a, blocs, nb, k=None, poids=None):
    m = cp_model.CpModel()
    N = len(s)
    par_nom = {g.nom: g for g in groupes}
    noms = [g.nom for g in groupes]
    types = sorted({g.type for g in groupes})

    x = {(e, nom): m.NewBoolVar("x%d_%s" % (e, nom)) for e in s for nom in noms}
    for e in s:  # C1 : un groupe par type
        for type_ in types:
            m.Add(
                sum(x[e, g.nom] for g in groupes if g.type == type_) == 1
            )
    for g in groupes:  # C2 : capacité maximale
        m.Add(sum(x[e, g.nom] for e in s) <= g.capacite)
    for e in s:  # C3 : respect du choix
        for nom in noms:
            if nom not in a[e]:
                m.Add(x[e, nom] == 0)

    n = {nom: sum(x[e, nom] for e in s) for nom in noms}
    y = {nom: m.NewBoolVar("y_%s" % nom) for nom in noms}
    for g in groupes:
        m.Add(n[g.nom] <= g.capacite * y[g.nom])  # C6
        m.Add(y[g.nom] <= n[g.nom])  # C5b / C7

    for g in groupes:  # C4 : cohérence hiérarchique TP -> TD
        if g.type == "TP" and g.parent is not None:
            if g.parent not in par_nom:
                raise ValueError(f"parent inconnu pour {g.nom}: {g.parent!r}")
            for e in s:
                m.Add(x[e, g.nom] <= x[e, g.parent])

    # C8 : exactement TP_PAR_TD TP ouverts par TD ouvert.
    enfants = {}
    for g in groupes:
        if g.type == "TP" and g.parent is not None:
            enfants.setdefault(g.parent, []).append(g.nom)
    if enfants:
        for g in groupes:
            if g.type != "TD":
                continue
            cs = enfants.get(g.nom, ())
            if len(cs) < TP_PAR_TD:
                raise ValueError(
                    f"{g.nom} n'a que {len(cs)} TP enfants "
                    f"(il en faut {TP_PAR_TD} pour C8)"
                )
            m.Add(sum(y[c] for c in cs) == TP_PAR_TD * y[g.nom])

    for idx, bloc in enumerate(blocs):  # C5a : assez de places par bloc
        if nb[idx] == 0:
            continue
        m.Add(
            sum(par_nom[nom].capacite * y[nom] for nom in bloc["groupes"])
            >= nb[idx]
        )

    if k is not None:
        m.Add(sum(y.values()) == k)

    # f1 intra-bloc : sum_g |k_b n(g) - N_b|, groupes ouverts seulement
    ec_par_bloc = []
    for idx, bloc in enumerate(blocs):
        ecs = []
        if nb[idx] == 0:
            ec_par_bloc.append(ecs)
            continue
        for nom in bloc["groupes"]:
            p = m.NewIntVar(0, N * len(bloc["groupes"]), "p%d_%s" % (idx, nom))
            zs = []
            for h in bloc["groupes"]:
                z = m.NewIntVar(0, N, "z%d_%s_%s" % (idx, nom, h))
                m.Add(z == 0).OnlyEnforceIf(y[h].Not())
                m.Add(z == n[nom]).OnlyEnforceIf(y[h])
                zs.append(z)
            m.Add(p == sum(zs))
            v = m.NewIntVar(0, N * len(bloc["groupes"]), "v%d_%s" % (idx, nom))
            m.Add(v >= p - nb[idx]).OnlyEnforceIf(y[nom])
            m.Add(v >= nb[idx] - p).OnlyEnforceIf(y[nom])
            m.Add(v == 0).OnlyEnforceIf(y[nom].Not())
            ecs.append(v)
        ec_par_bloc.append(ecs)

    # f3 : q(g1, g2) = 1 si un étudiant est affecté aux 2 groupes (types
    # différents). Paires TP/TD non parentes exclues : impossible de coexister.
    q = {}
    for i, g1 in enumerate(groupes):
        for g2 in groupes[i + 1:]:
            if g1.type == g2.type or not _peuvent_partager(g1, g2):
                continue
            var = m.NewBoolVar("q_%s_%s" % (g1.nom, g2.nom))
            for e in s:
                m.Add(x[e, g1.nom] + x[e, g2.nom] <= 1 + var)
            q[(g1.nom, g2.nom)] = var

    return m, x, y, n, ec_par_bloc, q


def _poser_indice(m, x, hint):
    """Pose l'affectation greedy comme point de départ (hint du solveur).

    Ce ne sont que des indices : s'ils sont incohérents, le solveur les
    répare, la faisabilité du modèle ne dépend pas d'eux.
    """
    for e, affectation in (hint or {}).items():
        # mono-type : {e: "TP1"} ; multi-type : {e: {"TP": "TP1", ...}}
        noms_hint = (
            [affectation] if isinstance(affectation, str)
            else affectation.values()
        )
        for nom in noms_hint:
            if (e, nom) in x:
                m.AddHint(x[e, nom], 1)


def resoudre(s, groupes, k=None, compat=None, poids=None, hint=None):
    """Résout l'affectation multi-type et renvoie (statut, aff, eff, ind).

    s       : {étudiant: LV2}
    groupes : séquence de `Groupe` (ou dict {nom: capacité})
    k       : nombre total de groupes ouverts imposé (None = choisi)
    compat  : {étudiant: [groupes autorisés]} (C3)
    poids   : {"f1": w1, "f2": w2, "f3": w3}, 1/3 chacun par défaut
    hint    : affectation greedy donnée comme point de départ
    """
    poids = dict(POIDS_DEFAUT, **(poids or {}))
    groupes = _normaliser_groupes(groupes)
    if not groupes:
        return cp_model.INFEASIBLE, {}, {}, {}
    noms = [g.nom for g in groupes]
    if len(set(noms)) != len(noms):
        raise ValueError("noms de groupes en double")
    par_nom = {g.nom: g for g in groupes}

    a = admis_de(s, groupes, compat)
    if a is None:
        return cp_model.INFEASIBLE, {}, {}, {}
    resultat_blocs = blocs_de(s, groupes, a, compat)
    if resultat_blocs is None:
        return cp_model.INFEASIBLE, {}, {}, {}
    blocs, bloc_etudiant, nb = resultat_blocs

    f1_max_int, L = _f1_max_int(blocs, nb, bloc_etudiant, par_nom, a)
    if f1_max_int is None:
        return cp_model.INFEASIBLE, {}, {}, {}
    f2_min = _f2_min(blocs, nb, par_nom)
    f2_max = sum(len(bloc["groupes"]) for bloc in blocs)
    # f3_max : toutes les paires de groupes de types différents, y compris
    # les paires impossibles (la même échelle que l'évaluateur).
    par_type_bloc = {}
    for bloc in blocs:
        for nom in bloc["groupes"]:
            par_type_bloc.setdefault(par_nom[nom].type, []).append(nom)
    types_b = sorted(par_type_bloc)
    f3_max = sum(
        len(par_type_bloc[t1]) * len(par_type_bloc[t2])
        for i, t1 in enumerate(types_b)
        for t2 in types_b[i + 1:]
    )
    bornes = {
        "f1": (0, f1_max_int),
        "f2": (f2_min, f2_max),
        "f3": (0, f3_max),
    }
    coefs = _coefficients(poids, bornes)

    m, x, y, n, ec_par_bloc, q = bati(s, groupes, a, blocs, nb, k, poids)
    _poser_indice(m, x, hint)

    if any(coefs.values()):
        f1_int = sum(
            (L // nb[idx]) * v
            for idx, ecs in enumerate(ec_par_bloc)
            if nb[idx] > 0
            for v in ecs
        )
        m.Minimize(
            coefs["f1"] * f1_int
            + coefs["f2"] * sum(y.values())
            + coefs["f3"] * sum(q.values())
        )

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 10
    statut = solver.Solve(m)
    if statut not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return statut, {}, {}, {}
    ecart = None
    if any(coefs.values()):
        obj = solver.ObjectiveValue()
        ecart = round(
            (obj - solver.BestObjectiveBound()) / max(abs(obj), 1.0), 6
        )

    eff = {nom: solver.Value(n[nom]) for nom in noms}
    ouv = {nom: bool(solver.Value(y[nom])) for nom in noms}
    types = sorted({g.type for g in groupes})
    k_par_type = {
        t: sum(1 for g in groupes if g.type == t and ouv[g.nom]) for t in types
    }
    k_total = sum(k_par_type.values())

    f1_int_bloc = []
    for idx, bloc in enumerate(blocs):
        if nb[idx] == 0:
            f1_int_bloc.append(0)
            continue
        ouverts = [nom for nom in bloc["groupes"] if ouv[nom]]
        k_b = len(ouverts)
        f1_int_bloc.append(
            sum(abs(k_b * eff[nom] - nb[idx]) for nom in ouverts)
        )
    f1_raw = sum(f1_int_bloc)
    if f1_max_int > 0:
        f1_norm = sum(
            (L // nb[idx]) * f1_int_bloc[idx]
            for idx in range(len(blocs))
            if nb[idx] > 0
        ) / f1_max_int
    else:
        f1_norm = 0.0
    f2_norm = (
        (k_total - f2_min) / (f2_max - f2_min) if f2_max > f2_min else 0.0
    )

    aff = {}
    for e in s:
        affectation = {}
        for type_ in types:
            for g in groupes:
                if g.type == type_ and solver.Value(x[e, g.nom]):
                    affectation[type_] = g.nom
                    break
        aff[e] = affectation

    # f3 : paires de groupes de types différents partageant un étudiant,
    # calculé sur l'affectation (règle exacte de l'évaluateur).
    paires = set()
    for e in s:
        items = sorted(aff[e].items())
        for i in range(len(items)):
            t1, g1 = items[i]
            for j in range(i + 1, len(items)):
                t2, g2 = items[j]
                if t1 != t2:
                    paires.add(tuple(sorted(((t1, g1), (t2, g2)))))
    f3 = len(paires)
    f3_norm = f3 / f3_max if f3_max > 0 else 0.0

    # score : même règle que l'évaluateur (poids renormalisés sur les
    # critères actifs, critère dégénéré ignoré).
    w = {c: float(poids.get(c, 0.0)) for c in ("f1", "f2", "f3")}
    norms = {"f1": f1_norm, "f2": f2_norm, "f3": f3_norm}
    actifs = [
        c
        for c, ok in (
            ("f1", f1_max_int > 0),
            ("f2", f2_max > f2_min),
            ("f3", f3_max > 0),
        )
        if ok and w[c] > 0.0
    ]
    total = sum(w[c] for c in actifs)
    if total > 0.0:
        cout = sum(
            w[c] / total * min(1.0, max(0.0, norms[c])) for c in actifs
        )
        score = 1.0 - cout
    else:
        score = 1.0

    ouverts = [eff[nom] for nom in noms if ouv[nom]]
    ind = {
        "k": k_total,
        "k_par_type": k_par_type,
        "f1": f1_raw,
        "f1_norm": round(min(1.0, max(0.0, f1_norm)), 6),
        "f1_max": f1_max_int / L if L else 0.0,
        "f2": k_total,
        "f2_norm": round(min(1.0, max(0.0, f2_norm)), 6),
        "f2_min": f2_min,
        "f2_max": f2_max,
        "f3": f3,
        "f3_norm": round(min(1.0, max(0.0, f3_norm)), 6),
        "f3_max": f3_max,
        "maxmin": max(ouverts) - min(ouverts) if ouverts else 0,
        "score": round(score, 6),
        "optimal": statut == cp_model.OPTIMAL,
        "ecart": ecart,
        "blocs": [
            {"type": b["type"], "cle": b["cle"], "groupes": list(b["groupes"]),
             "N": nb[i]}
            for i, b in enumerate(blocs)
        ],
    }
    return statut, aff, eff, ind


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
def test_equilibre():
    # 12 étudiants, 3 TP de 5 : même bloc, tout le monde est interchangeable
    s = {**{i: "Allemand" for i in range(7)}, **{i: "Espagnol" for i in range(7, 12)}}
    groupes = [Groupe(f"TP{i}", "TP", 5) for i in range(1, 4)]
    statut, aff, eff, ind = resoudre(s, groupes)
    assert statut == cp_model.OPTIMAL and len(aff) == 12
    assert sorted(eff.values()) == [4, 4, 4], eff
    assert ind["f1"] == 0 and ind["f1_norm"] == 0.0 and ind["k"] == 3, ind
    print("1/8 equilibre : OPTIMAL, effectifs 4/4/4, k=3, f1=0")


def test_capacites():
    s = {i: "Espagnol" if i % 3 else "Allemand" for i in range(1, 25)}
    groupes = [Groupe(f"TP{i}", "TP", 8) for i in range(1, 4)]
    statut, aff, eff, ind = resoudre(s, groupes)
    assert len(aff) == 24 and all(eff[g] <= 8 for g in eff), eff
    assert ind["k"] == 3 and ind["f1"] == 0, ind
    print("2/8 capacites : 24 etudiants, 3 TP de 8, rien ne depasse")


def test_infeasible():
    s = {i: "Allemand" for i in range(12)}
    groupes = [Groupe(f"TP{i}", "TP", 3) for i in range(1, 4)]
    statut, _, _, _ = resoudre(s, groupes)
    assert statut == cp_model.INFEASIBLE, statut
    print("3/8 infaisable : detecte (9 places pour 12 etudiants)")


def test_choix_lv2():
    s = {**{i: "Allemand" for i in range(6)}, **{i: "Espagnol" for i in range(6, 12)}}
    groupes = [
        Groupe("TP1", "TP", 4), Groupe("TP2", "TP", 4), Groupe("TP3", "TP", 6)
    ]
    compat = {e: (["TP1", "TP2"] if s[e] == "Allemand" else ["TP3"]) for e in s}
    statut, aff, eff, ind = resoudre(s, groupes, compat=compat)
    assert statut == cp_model.OPTIMAL
    assert all(aff[e]["TP"] in compat[e] for e in s), aff
    assert eff["TP3"] == 6 and ind["k"] == 3, (eff, ind)
    print("4/8 choix LV2 : respecte (C3), k=3")


def test_instance_multi_type():
    from generateur_instances import generer_instance
    from groupes import PROFILS_CAPACITES, construire_groupes

    inst = generer_instance(
        n=75, seed=42, avec_cas_particuliers=False, frac_choix_tardif=0.0
    )
    etudiants = list(inst.etudiants)
    s = {e.id: e.lv2 for e in etudiants}
    groupes = construire_groupes(inst, PROFILS_CAPACITES["standard"])
    compat = {
        e.id: [
            g.nom
            for g in groupes
            if g.type != "LV2" or g.nom.startswith(f"LV2_{e.lv2}_")
        ]
        for e in etudiants
    }
    statut, aff, eff, ind = resoudre(s, groupes, compat=compat)
    assert statut in (cp_model.OPTIMAL, cp_model.FEASIBLE), statut
    assert len(aff) == 75
    for e in s:
        assert set(aff[e]) == {"LV2", "LV1", "TP", "TD"}, aff[e]
    parent = {g.nom: g.parent for g in groupes}
    for e in s:
        assert aff[e]["TD"] == parent[aff[e]["TP"]], aff[e]
    for g in groupes:
        assert eff[g.nom] <= g.capacite, (g.nom, eff[g.nom])

    # C8 : le pool propose 2 TP par TD, le solveur n'en ouvre que 2 par TD.
    tps = [g for g in groupes if g.type == "TP"]
    tds = [g for g in groupes if g.type == "TD"]
    assert len(tps) == TP_PAR_TD * len(tds), (len(tps), len(tds))
    for td in tds:
        ouverts = sum(1 for g in tps if g.parent == td.nom and eff[g.nom] > 0)
        assert ouverts == TP_PAR_TD * (eff[td.nom] > 0), (td.nom, ouverts)
    assert ind["k_par_type"]["TP"] == TP_PAR_TD * ind["k_par_type"]["TD"], ind

    # L'évaluateur (juge) valide la même affectation : C8 respectée.
    from evaluation import evaluer

    r = evaluer(s, groupes, aff, compat=compat)
    assert r.faisable, r.violations
    print(
        "5/8 instance multi-type : 75 etudiants, C1/C2/C4/C8 OK, "
        "k=%s, score=%.3f" % (ind["k_par_type"], ind["score"])
    )


def test_k_impose():
    s = {i: "Allemand" for i in range(12)}
    groupes = [Groupe(f"TP{i}", "TP", 5) for i in range(1, 4)]
    statut, _, _, _ = resoudre(s, groupes, k=2)
    assert statut == cp_model.INFEASIBLE, statut
    print("6/8 k impose : k=2 pour 12 etudiants -> infaisable")


def test_indicateurs():
    s = {i: "Allemand" for i in range(11)}
    groupes = [Groupe(f"TP{i}", "TP", 5) for i in range(1, 4)]
    statut, aff, eff, ind = resoudre(s, groupes)
    assert statut == cp_model.OPTIMAL and sorted(eff.values()) == [3, 4, 4], eff
    assert ind["f1"] == 4 and ind["f1_norm"] == 0.25 and ind["maxmin"] == 1, ind
    print("7/8 indicateurs : 3/4/4, f1=4, f1_norm=0.25, max-min=1")


def test_profils_capacites():
    """Le solveur reste faisable et cohérent sur des profils variés."""
    from generateur_instances import generer_instance
    from groupes import PROFILS_CAPACITES, construire_groupes, variantes_capacites

    inst = generer_instance(
        n=75, seed=42, avec_cas_particuliers=False, frac_choix_tardif=0.0
    )
    etudiants = list(inst.etudiants)
    s = {e.id: e.lv2 for e in etudiants}

    cas = [(nom, cap) for nom, cap in PROFILS_CAPACITES.items()]
    cas += [
        ("variante_%d" % i, cap)
        for i, cap in enumerate(variantes_capacites("standard", 2, seed=1), 1)
    ]

    for nom, capacites in cas:
        groupes = construire_groupes(inst, capacites)
        par_nom = {g.nom: g for g in groupes}
        compat = {
            e.id: [
                g.nom
                for g in groupes
                if g.type != "LV2" or g.nom.startswith(f"LV2_{e.lv2}_")
            ]
            for e in etudiants
        }
        statut, aff, eff, ind = resoudre(s, groupes, compat=compat)
        assert statut in (cp_model.OPTIMAL, cp_model.FEASIBLE), (nom, statut)
        assert len(aff) == 75, nom
        for g in groupes:
            assert eff[g.nom] <= g.capacite, (nom, g.nom, eff[g.nom])
        for e in s:
            assert set(aff[e]) == {"LV2", "LV1", "TP", "TD"}, (nom, aff[e])
            assert aff[e]["TD"] == par_nom[aff[e]["TP"]].parent, (nom, aff[e])
        assert 0.0 <= ind["score"] <= 1.0, (nom, ind["score"])
        print(
            "8/8 %-14s %s score=%.3f"
            % (nom, ind["k_par_type"], ind["score"])
        )


if __name__ == "__main__":
    for t in (
        test_equilibre,
        test_capacites,
        test_infeasible,
        test_choix_lv2,
        test_instance_multi_type,
        test_k_impose,
        test_indicateurs,
        test_profils_capacites,
    ):
        t()
    print("8/8 tests passent")
