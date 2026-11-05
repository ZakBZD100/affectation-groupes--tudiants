"""tests CP-SAT - affectation des groupes, projet 3A"""
from ortools.sat.python import cp_model


def admis_de(s, groupes, compat):
    # C3 : groupes acceptes par chaque etudiant
    tout = set(groupes)
    a = {}
    for e in s:
        g = tout if compat is None or e not in compat else tout & set(compat[e])
        if not g:
            return None
        a[e] = g
    return a


def blocs_de(a, groupes):
    # deux groupes d'un meme etudiant sont comparables -> meme bloc
    par = {g: g for g in groupes}

    def find(g):
        while par[g] != g:
            par[g] = par[par[g]]
            g = par[g]
        return g

    for ens in a.values():
        ens = sorted(ens)
        for g in ens[1:]:
            par[find(g)] = find(ens[0])
    b = {}
    for g in groupes:
        b.setdefault(find(g), []).append(g)
    return list(b.values())


def nb_blocs(a, blocs):
    rac = {g: i for i, bl in enumerate(blocs) for g in bl}
    nb = [0] * len(blocs)
    for ens in a.values():
        nb[rac[next(iter(ens))]] += 1
    return nb


def bati(s, groupes, a, blocs, nb, k=None):
    m = cp_model.CpModel()
    N = len(s)
    x = {(e, g): m.NewBoolVar("x%d_%s" % (e, g)) for e in s for g in groupes}
    for e in s: m.Add(sum(x[e, g] for g in groupes) == 1) # C1
    for g, cap in groupes.items(): m.Add(sum(x[e, g] for e in s) <= cap) # C2
    for e in s:
        for g in set(groupes) - a[e]: m.Add(x[e, g] == 0) # C3
    n = {g: sum(x[e, g] for e in s) for g in groupes}
    y = {g: m.NewBoolVar("y%d" % i) for i, g in enumerate(groupes)}
    for g, cap in groupes.items():
        m.Add(n[g] <= cap * y[g])     # C6 : rien dans un groupe ferme
        m.Add(y[g] <= n[g])           # C5b : pas de groupe ouvert vide
    for i, bl in enumerate(blocs):    # C5a : assez de places ouvertes par bloc
        m.Add(sum(y[g] * groupes[g] for g in bl) >= nb[i])
    if k is not None:
        m.Add(sum(y.values()) == k)
    # f1 intra-bloc : somme de |k_b*n(g) - N_b| sur les groupes ouverts
    ec = []
    for i, bl in enumerate(blocs):
        for g in bl:
            p = m.NewIntVar(0, N * len(groupes), "p%d_%s" % (i, g))
            zs = []
            for h in bl:              # k_b * n(g) reifie : 0 si h ferme
                z = m.NewIntVar(0, N, "z%d_%s_%s" % (i, g, h))
                m.Add(z == 0).OnlyEnforceIf(y[h].Not())
                m.Add(z == n[g]).OnlyEnforceIf(y[h])
                zs.append(z)
            m.Add(p == sum(zs))
            v = m.NewIntVar(0, N * len(groupes), "e%d_%s" % (i, g))
            m.Add(v >= p - nb[i]).OnlyEnforceIf(y[g])
            m.Add(v >= nb[i] - p).OnlyEnforceIf(y[g])
            m.Add(v == 0).OnlyEnforceIf(y[g].Not())
            ec.append(v)
    return m, x, y, n, ec


def resoudre(s, groupes, k=None, compat=None):
    a = admis_de(s, groupes, compat)
    if a is None:
        return cp_model.INFEASIBLE, {}, {}, {}
    blocs = blocs_de(a, groupes)
    nb = nb_blocs(a, blocs)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 10
    if k is None: # phase 1 : le modele choisit le plus petit k (C5a)
        m, x, y, n, ec = bati(s, groupes, a, blocs, nb)
        m.Minimize(sum(y.values()))
        st = solver.Solve(m)
        if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return st, {}, {}, {}
        k = sum(solver.Value(y[g]) for g in y)
    # phase 2 : k fixe, on minimise l'equilibre
    m, x, y, n, ec = bati(s, groupes, a, blocs, nb, k)
    m.Minimize(sum(ec))
    st = solver.Solve(m)
    if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return st, {}, {}, {}
    aff = {e: next(g for g in groupes if solver.Value(x[e, g])) for e in s}
    eff = {g: solver.Value(n[g]) for g in groupes}
    ouv = [g for g in groupes if solver.Value(y[g])]
    kk, N = len(ouv), len(s)
    f1 = sum(abs(kk * eff[g] - N) for g in ouv)
    r = N % kk if kk else 0
    fmin, fmax = 2 * r * (kk - r), 2 * N * (kk - 1)
    norm = 0.0 if fmax == fmin else (f1 - fmin) / (fmax - fmin)
    mm = max(eff[g] for g in ouv) - min(eff[g] for g in ouv) if ouv else 0
    ind = {"k": kk, "f1": f1, "f1_norm": round(norm, 3), "maxmin": mm}
    return st, aff, eff, ind


def test_equilibre():
    # le mini-test de la semaine 1 : 12 etudiants, 3 TP de 5
    s = {**{i: "Allemand" for i in range(7)}, **{i:"Espagnol" for i in range(7,12)}}
    statut, aff, eff, ind = resoudre(s, {"TP1": 5,"TP2":5, "TP3": 5})
    assert statut == cp_model.OPTIMAL and len(aff)==12 and sorted(eff.values()) == [4,4,4], eff
    assert ind["f1"]==0 and ind["f1_norm"]==0.0 and ind["k"]==3, ind
    print("1/7 equilibre : OPTIMAL, effectifs 4/4/4, k=3, f1=0")


def test_capacites():
    s={i: "Espagnol" if i%3 else "Allemand" for i in range(1,25)}
    statut, aff, eff, ind = resoudre(s, {"TP1":8, "TP2": 8,"TP3":8})
    assert len(aff)==24 and all(eff[g] <= 8 for g in eff), eff
    assert ind["k"]==3 and ind["f1"]==0, ind
    print("2/7 capacites : 24 etudiants, 3 TP de 8, rien ne depasse")


def test_infeasible():
    statut,_,_,_ = resoudre({i:"Allemand" for i in range(12)}, {"TP1":3, "TP2": 3,"TP3":3})
    assert statut == cp_model.INFEASIBLE, statut
    print("3/7 infaisable : detecte")


def test_choix_lv2():
    s = {**{i:"Allemand" for i in range(6)}, **{i: "Espagnol" for i in range(6,12)}}
    compat = {e: (["TP1","TP2"] if s[e]=="Allemand" else ["TP3"]) for e in s}
    statut, aff, eff, ind = resoudre(s, {"TP1":4, "TP2": 4, "TP3":6}, compat=compat)
    assert statut==cp_model.OPTIMAL and all(g in compat[e] for e,g in aff.items()) and eff["TP3"]==6, aff
    assert ind["k"]==3, ind
    print("4/7 choix LV2 : respecte (C3), 2 blocs, k=3")


def test_instance():
    # 75 etudiants repartis en 5 TP de 16 (bornes du cadrage : 50 a 100)
    s = {i: ("Allemand" if i%4 else "Espagnol" if i%3 else "Autre") for i in range(1,76)}
    statut, aff, eff, ind = resoudre(s, {f"TP{i}": 16 for i in range(1,6)})
    assert len(aff)==75 and all(eff[g] <= 16 for g in eff), eff
    print("5/7 instance : 75 etudiants, 5 TP, OK")


def test_k_impose():
    # k impose : k=2 -> 2*5=10 places pour 12 etudiants, C5a refuse
    statut,_,_,_ = resoudre({i:"Allemand" for i in range(12)}, {"TP1":5, "TP2":5, "TP3":5}, k=2)
    assert statut == cp_model.INFEASIBLE, statut
    print("6/7 k impose : k=2 pour 12 etudiants -> infaisable")


def test_indicateurs():
    # 11 etudiants, 3 TP de 5 : k=3 minimal, indivisible -> repli 4/4/3, f1=4=fmin
    statut, aff, eff, ind = resoudre({i:"Allemand" for i in range(11)}, {"TP1":5, "TP2":5, "TP3":5})
    assert statut == cp_model.OPTIMAL and sorted(eff.values()) == [3,4,4], eff
    assert ind["f1"]==4 and ind["f1_norm"]==0.0 and ind["maxmin"]==1, ind
    print("7/7 indicateurs : 3/4/4, f1=4=fmin, norm=0, max-min=1")


if __name__ == "__main__":
    for t in (test_equilibre, test_capacites, test_infeasible, test_choix_lv2, test_instance, test_k_impose, test_indicateurs): t()
    print("7/7 tests passent")
