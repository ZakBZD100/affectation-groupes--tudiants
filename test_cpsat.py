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
L'objectif est pondéré (f1 + f2 + f3, 0.3/0.7/0.15 par défaut : f2 est
prioritaire), avec une normalisation entière exacte. f3 est modélisé par des
variables booléennes « paire de groupes de types différents partageant un
étudiant », ce qui aligne le solveur sur le juge `evaluation.evaluer`. Les
groupes sont des `groupes.Groupe` (nom, type, capacité, parent) ; un dict
{nom: capacité} reste accepté pour la compatibilité.
"""
import math
import os
import sys
import time
from fractions import Fraction

from ortools.sat.python import cp_model

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
from groupes import Groupe, groupes_par_type  # noqa: E402

POIDS_DEFAUT = {"f1": 0.3, "f2": 0.7, "f3": 0.15}


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


def _f3_multi(s, aff, par_nom, types):
    """Paires de groupes de types différents partageant un étudiant."""
    paires = set()
    for e in s:
        affectation = aff.get(e, {})
        if not isinstance(affectation, dict):
            continue
        items = sorted(affectation.items())
        for i in range(len(items)):
            t1, g1 = items[i]
            for j in range(i + 1, len(items)):
                t2, g2 = items[j]
                if t1 != t2:
                    paires.add(tuple(sorted(((t1, g1), (t2, g2)))))
    f3 = float(len(paires))
    par_type = {
        t: sum(1 for g in par_nom.values() if g.type == t) for t in types
    }
    f3_max = 0
    for i, t1 in enumerate(types):
        for t2 in types[i + 1:]:
            f3_max += par_type[t1] * par_type[t2]
    return f3, f3_max


def _remplissage(eff, ouv, par_nom):
    """Statistiques sur les groupes ouverts."""
    tailles = [eff[nom] for nom in ouv]
    capacites = [par_nom[nom].capacite for nom in ouv]
    if not tailles:
        return {
            "effectif_min": 0,
            "effectif_max": 0,
            "effectif_moyen": 0.0,
            "ecart_type": 0.0,
            "taux_occupation": 0.0,
        }
    moyenne = sum(tailles) / len(tailles)
    ecart_type = (sum((v - moyenne) ** 2 for v in tailles) / len(tailles)) ** 0.5
    return {
        "effectif_min": min(tailles),
        "effectif_max": max(tailles),
        "effectif_moyen": round(moyenne, 3),
        "ecart_type": round(ecart_type, 3),
        "taux_occupation": round(sum(tailles) / sum(capacites), 4),
    }


def _coefficients(poids, f1_max_int, f2_min, f2_max, f3_max_int):
    """Coefficients entiers de l'objectif pondéré f1 + f2 + f3.

    Retourne (A, B, C) tels que minimiser A*F1_INT + B*sum(y) + C*sum(z) soit
    équivalent à minimiser w1*f1~ + w2*f2~ + w3*f3~. (0, 0, 0) = aucun critère
    actif (par exemple en mono-type LV2, où f3 est dégénéré).
    """
    w = {
        c: Fraction(str(poids.get(c, 0.0))).limit_denominator(10000)
        for c in ("f1", "f2", "f3")
    }
    if any(valeur < 0 for valeur in w.values()):
        raise ValueError("les poids doivent être >= 0")
    if sum(w.values()) == 0:
        raise ValueError("la somme des poids doit être > 0")

    actif = {
        "f1": f1_max_int > 0 and w["f1"] > 0,
        "f2": f2_max > f2_min and w["f2"] > 0,
        "f3": f3_max_int > 0 and w["f3"] > 0,
    }
    if not any(actif.values()):
        return 0, 0, 0

    denom = math.lcm(*(valeur.denominator for valeur in w.values()))
    p = {c: valeur.numerator * (denom // valeur.denominator) for c, valeur in w.items()}
    # Un critère dégénéré ne doit pas annuler l'échelle des autres.
    d1 = f1_max_int if f1_max_int > 0 else 1
    d2 = f2_max - f2_min if f2_max > f2_min else 1
    d3 = f3_max_int if f3_max_int > 0 else 1
    A = p["f1"] * d2 * d3 if actif["f1"] else 0
    B = p["f2"] * d1 * d3 if actif["f2"] else 0
    C = p["f3"] * d1 * d2 if actif["f3"] else 0
    return A, B, C


# ---------------------------------------------------------------------------
# Modèle
# ---------------------------------------------------------------------------
def bati(s, groupes, a, blocs, nb, k=None, avec_f3=True):
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

    # f3 : paires de groupes de types différents partageant un étudiant.
    # Clause SAT (¬x(e,g1) ∨ ¬x(e,g2) ∨ z) : z minimiseur prend exactement
    # la valeur de l'OR sur les étudiants admis dans les deux groupes.
    z = {}
    if avec_f3:
        for i, g1 in enumerate(groupes):
            for g2 in groupes[i + 1:]:
                if g1.type == g2.type:
                    continue
                cle = (g1.nom, g2.nom)
                zz = m.NewBoolVar("f3_%s_%s" % cle)
                z[cle] = zz
                for e in s:
                    if g1.nom in a[e] and g2.nom in a[e]:
                        # clause SAT : z ou non x(e,g1) ou non x(e,g2)
                        m.AddBoolOr([x[e, g1.nom].Not(), x[e, g2.nom].Not(), zz])

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
                zh = m.NewIntVar(0, N, "z%d_%s_%s" % (idx, nom, h))
                m.Add(zh == 0).OnlyEnforceIf(y[h].Not())
                m.Add(zh == n[nom]).OnlyEnforceIf(y[h])
                zs.append(zh)
            m.Add(p == sum(zs))
            v = m.NewIntVar(0, N * len(bloc["groupes"]), "v%d_%s" % (idx, nom))
            m.Add(v >= p - nb[idx]).OnlyEnforceIf(y[nom])
            m.Add(v >= nb[idx] - p).OnlyEnforceIf(y[nom])
            m.Add(v == 0).OnlyEnforceIf(y[nom].Not())
            ecs.append(v)
        ec_par_bloc.append(ecs)

    return m, x, y, n, ec_par_bloc, z


def resoudre(s, groupes, k=None, compat=None, poids=None, comparer=False,
             timeout=None):
    """Résout l'affectation multi-type et renvoie (statut, aff, eff, ind).

    s        : {étudiant: LV2}
    groupes  : séquence de `Groupe` (ou dict {nom: capacité})
    k        : nombre total de groupes ouverts imposé (None = choisi)
    compat   : {étudiant: [groupes autorisés]} (C3)
    poids    : {"f1": w1, "f2": w2, "f3": w3}, 0.3/0.7/0.15 par défaut
    comparer : si True, calcule aussi l'écart de score avec le greedy
    timeout  : limite de temps en secondes (10 par défaut)
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
    f3_max_int = sum(
        1
        for i, g1 in enumerate(groupes)
        for g2 in groupes[i + 1:]
        if g1.type != g2.type
    )
    avec_f3 = poids.get("f3", 0) > 0
    A, B, C = _coefficients(poids, f1_max_int, f2_min, f2_max, f3_max_int)

    m, x, y, n, ec_par_bloc, z = bati(
        s, groupes, a, blocs, nb, k, avec_f3=avec_f3
    )

    if A or B or C:
        f1_int = sum(
            (L // nb[idx]) * v
            for idx, ecs in enumerate(ec_par_bloc)
            if nb[idx] > 0
            for v in ecs
        )
        m.Minimize(A * f1_int + B * sum(y.values()) + C * sum(z.values()))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 10 if timeout is None else timeout
    solver.parameters.random_seed = 7
    t_solve = time.perf_counter()
    statut = solver.Solve(m)
    temps_s = time.perf_counter() - t_solve
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

    aff = {}
    for e in s:
        affectation = {}
        for type_ in types:
            for g in groupes:
                if g.type == type_ and solver.Value(x[e, g.nom]):
                    affectation[type_] = g.nom
                    break
        aff[e] = affectation

    noms_ouverts = [nom for nom in noms if ouv[nom]]
    ouverts = [eff[nom] for nom in noms_ouverts]
    remplissage = _remplissage(eff, noms_ouverts, par_nom)
    f3, f3_max = _f3_multi(s, aff, par_nom, types)
    f3_norm = f3 / f3_max if f3_max > 0 else 0.0

    # Score sur les trois critères, avec les mêmes poids que l'objectif.
    w = {c: float(poids.get(c, 0.0)) for c in ("f1", "f2", "f3")}
    normes = {"f1": f1_norm, "f2": f2_norm, "f3": f3_norm}
    actifs = [
        c
        for c, disponible in (
            ("f1", f1_max_int > 0),
            ("f2", f2_max > f2_min),
            ("f3", f3_max > 0),
        )
        if disponible and w[c] > 0
    ]
    total_poids = sum(w[c] for c in actifs)
    score = (
        1.0 - sum(w[c] * normes[c] for c in actifs) / total_poids
        if total_poids
        else 1.0
    )

    objectif = solver.ObjectiveValue() if A or B or C else 0
    borne = solver.BestObjectiveBound() if A or B or C else 0
    ecart = 0.0 if objectif == 0 else abs(objectif - borne) / abs(objectif)

    ind = {
        "statut": solver.StatusName(statut),
        "temps_s": round(temps_s, 4),
        "objectif": objectif,
        "best_bound": borne,
        "gap": round(ecart, 6),
        "variables": len(m.Proto().variables),
        "contraintes": len(m.Proto().constraints),
        "k": k_total,
        "k_par_type": k_par_type,
        "f1": f1_raw,
        "f1_norm": round(f1_norm, 6),
        "f1_max": f1_max_int / L if L else 0.0,
        "f2": k_total,
        "f2_norm": round(f2_norm, 6),
        "f2_min": f2_min,
        "f2_max": f2_max,
        "f3": f3,
        "f3_max": f3_max,
        "f3_norm": round(f3_norm, 6),
        "maxmin": max(ouverts) - min(ouverts) if ouverts else 0,
        "score": round(score, 6),
        "ecart_f2_min": k_total - f2_min,
        "marge_f2": f2_max - f2_min,
        **remplissage,
        "blocs": [
            {"type": b["type"], "cle": b["cle"], "groupes": list(b["groupes"]),
             "N": nb[i]}
            for i, b in enumerate(blocs)
        ],
    }

    if comparer:
        from heuristique import greedy
        from evaluation import evaluer

        aff_g, _ = greedy(s, groupes, compat=compat)
        r_g = evaluer(s, groupes, aff_g, compat=compat)
        r_c = evaluer(s, groupes, aff, compat=compat)
        ind["greedy"] = {
            "faisable": r_g.faisable,
            "k": r_g.detail["k"] if r_g.faisable else None,
            "f1": r_g.criteres["f1"] if r_g.faisable else None,
            "f3": r_g.criteres["f3"] if r_g.faisable else None,
            "score": r_g.score,
        }
        if r_g.faisable and r_c.faisable:
            ind["delta_score_greedy"] = round(r_c.score - r_g.score, 6)
            ind["delta_k_greedy"] = r_c.detail["k"] - r_g.detail["k"]
        else:
            ind["delta_score_greedy"] = None
            ind["delta_k_greedy"] = None

    return statut, aff, eff, ind


def afficher_metriques(ind):
    """Affiche un bloc compact de métriques après résolution."""
    print("  Resolution : %s en %.4fs, objectif=%s, borne=%s, gap=%.3f"
          % (ind["statut"], ind["temps_s"], ind["objectif"],
             ind["best_bound"], ind["gap"]))
    print("  Qualite    : k=%s, f1=%.3f (norm %.3f), f2=%.3f (norm %.3f), "
          "f3=%.1f (norm %.3f), score=%.3f"
          % (ind["k"], ind["f1"], ind["f1_norm"], ind["f2"], ind["f2_norm"],
             ind["f3"], ind["f3_norm"], ind["score"]))
    print("  Remplissage: min=%d max=%d moy=%.2f ecart-type=%.2f occupation=%.1f%%"
          % (ind["effectif_min"], ind["effectif_max"], ind["effectif_moyen"],
             ind["ecart_type"], 100 * ind["taux_occupation"]))
    print("  Bornes     : f2- f2_min=%+d (marge %d), maxmin=%d"
          % (ind["ecart_f2_min"], ind["marge_f2"], ind["maxmin"]))
    if "delta_score_greedy" in ind:
        print("  vs greedy  : delta score=%s, delta k=%s"
              % (ind["delta_score_greedy"], ind["delta_k_greedy"]))


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
    statut, aff, eff, ind = resoudre(s, groupes, compat=compat, comparer=True)
    assert statut in (cp_model.OPTIMAL, cp_model.FEASIBLE), statut
    assert 0 <= ind["f3"] <= ind["f3_max"]
    assert 0.0 <= ind["f3_norm"] <= 1.0
    assert ind["greedy"]["f3"] is not None
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
    avec, sans = (
        _coefficients({"f1": 0.3, "f2": 0.7, "f3": 0.15}, 100, 10, 20, 150),
        _coefficients({"f1": 0.3, "f2": 0.7, "f3": 0.0}, 100, 10, 20, 150),
    )
    assert len(avec) == len(sans) == 3 and avec[2] > 0 and sans[2] == 0
    print("7/8 indicateurs : 3/4/4, f1=4, f1_norm=0.25, max-min=1, f3 dans l'objectif")


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
