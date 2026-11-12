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

Le solveur choisit k(t) : aucun nombre de groupes n'est imposé de l'extérieur.
L'objectif est pondéré (f1 + f2, 50/50 par défaut), avec une normalisation
entière exacte. Les groupes sont des `groupes.Groupe` (nom, type, capacité,
parent) ; un dict {nom: capacité} reste accepté pour la compatibilité.
"""
import math
import os
import sys
from fractions import Fraction

from ortools.sat.python import cp_model

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
from groupes import Groupe, groupes_par_type  # noqa: E402

POIDS_DEFAUT = {"f1": 0.5, "f2": 0.5}


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


def _coefficients(poids, f1_max_int, f2_min, f2_max):
    """Coefficients entiers de l'objectif pondéré f1 + f2.

    Retourne (A, B) tels que minimiser A*F1_INT + B*sum(y) soit équivalent à
    minimiser w1*f1~ + w2*f2~. (0, 0) = aucun critère actif.
    """
    w1 = Fraction(str(poids.get("f1", 0.0))).limit_denominator(10000)
    w2 = Fraction(str(poids.get("f2", 0.0))).limit_denominator(10000)
    if w1 < 0 or w2 < 0:
        raise ValueError("les poids doivent être >= 0")
    if w1 == 0 and w2 == 0:
        raise ValueError("la somme des poids doit être > 0")

    f1_actif = f1_max_int > 0 and w1 > 0
    f2_actif = f2_max > f2_min and w2 > 0
    if not f1_actif and not f2_actif:
        return 0, 0

    denom = math.lcm(w1.denominator, w2.denominator)
    a = w1.numerator * (denom // w1.denominator)
    b = w2.numerator * (denom // w2.denominator)
    # Un critère dégénéré ne doit pas annuler l'échelle de l'autre.
    delta_f1 = f1_max_int if f1_max_int > 0 else 1
    delta_f2 = f2_max - f2_min if f2_max > f2_min else 1
    A = a * delta_f2 if f1_actif else 0
    B = b * delta_f1 if f2_actif else 0
    return A, B


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

    return m, x, y, n, ec_par_bloc


def resoudre(s, groupes, k=None, compat=None, poids=None):
    """Résout l'affectation multi-type et renvoie (statut, aff, eff, ind).

    s       : {étudiant: LV2}
    groupes : séquence de `Groupe` (ou dict {nom: capacité})
    k       : nombre total de groupes ouverts imposé (None = choisi)
    compat  : {étudiant: [groupes autorisés]} (C3)
    poids   : {"f1": w1, "f2": w2}, 50/50 par défaut
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
    A, B = _coefficients(poids, f1_max_int, f2_min, f2_max)

    m, x, y, n, ec_par_bloc = bati(s, groupes, a, blocs, nb, k, poids)

    if A or B:
        f1_int = sum(
            (L // nb[idx]) * v
            for idx, ecs in enumerate(ec_par_bloc)
            if nb[idx] > 0
            for v in ecs
        )
        m.Minimize(A * f1_int + B * sum(y.values()))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 10
    statut = solver.Solve(m)
    if statut not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return statut, {}, {}, {}

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

    w1 = float(poids.get("f1", 0.0))
    w2 = float(poids.get("f2", 0.0))
    if f1_max_int > 0 and f2_max > f2_min:
        score = 1.0 - (w1 * f1_norm + w2 * f2_norm) / (w1 + w2)
    elif f1_max_int > 0:
        score = 1.0 - f1_norm
    elif f2_max > f2_min:
        score = 1.0 - f2_norm
    else:
        score = 1.0

    aff = {}
    for e in s:
        affectation = {}
        for type_ in types:
            for g in groupes:
                if g.type == type_ and solver.Value(x[e, g.nom]):
                    affectation[type_] = g.nom
                    break
        aff[e] = affectation

    ouverts = [eff[nom] for nom in noms if ouv[nom]]
    ind = {
        "k": k_total,
        "k_par_type": k_par_type,
        "f1": f1_raw,
        "f1_norm": round(f1_norm, 6),
        "f1_max": f1_max_int / L if L else 0.0,
        "f2": k_total,
        "f2_norm": round(f2_norm, 6),
        "f2_min": f2_min,
        "f2_max": f2_max,
        "maxmin": max(ouverts) - min(ouverts) if ouverts else 0,
        "score": round(score, 6),
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
    print(
        "5/8 instance multi-type : 75 etudiants, C1/C2/C4 OK, "
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
