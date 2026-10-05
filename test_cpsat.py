"""tests CP-SAT - affectation des groupes, projet 3A"""
from ortools.sat.python import cp_model


def resoudre(s, groupes, compat=None):
    m = cp_model.CpModel()
    x={(e, g):m.NewBoolVar(f"x{e}_{g}") for e in s for g in groupes}
    for e in s: m.Add(sum(x[e,g] for g in groupes) == 1) # C1 : un seul groupe
    for g,cap in groupes.items(): m.Add(sum(x[e, g] for e in s)<=cap) # C2 : effectif max
    for e, a in (compat or {}).items(): # C3 : groupes compatibles avec s(e)
        for g in set(groupes)-set(a): m.Add(x[e,g]==0)
    n={g:sum(x[e, g] for e in s) for g in groupes}
    cible = int(len(s)/len(groupes)) # f1 : équilibre |n(g) - N/k|
    ecarts=[m.NewIntVar(0, len(s), f"e{g}") for g in groupes]
    for g,v in zip(groupes, ecarts): m.AddAbsEquality(v, n[g]-cible)
    m.Minimize(sum(ecarts))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds=10
    statut=solver.Solve(m)
    if statut not in (cp_model.OPTIMAL,cp_model.FEASIBLE): return statut, {}, {}
    return statut, {e:next(g for g in groupes if solver.Value(x[e,g])) for e in s}, {g:solver.Value(n[g]) for g in groupes}


def test_equilibre():
    # le mini-test de la semaine 1 : 12 étudiants, 3 TP de 5
    s={**{i: "Allemand" for i in range(7)}, **{i:"Espagnol" for i in range(7,12)}}
    statut, aff, eff = resoudre(s, {"TP1": 5,"TP2":5, "TP3": 5})
    assert statut == cp_model.OPTIMAL and len(aff)==12 and sorted(eff.values()) == [4,4,4], eff
    print("1/4 equilibre : OPTIMAL, effectifs 4/4/4")


def test_capacites():
    s={i: "Espagnol" if i%3 else "Allemand" for i in range(1,25)}
    statut, aff, eff = resoudre(s, {"TP1":8, "TP2": 8,"TP3":8})
    assert len(aff)==24 and all(eff[g] <= 8 for g in eff), eff
    print("2/4 capacites : 24 etudiants, 3 TP de 8, rien ne depasse")


def test_infeasible():
    statut,_,_ = resoudre({i:"Allemand" for i in range(12)}, {"TP1":3, "TP2": 3,"TP3":3})
    assert statut == cp_model.INFEASIBLE, statut
    print("3/4 infaisable : detecte")


def test_choix_lv2():
    s = {**{i:"Allemand" for i in range(6)}, **{i: "Espagnol" for i in range(6,12)}}
    compat = {e: (["TP1","TP2"] if s[e]=="Allemand" else ["TP3"]) for e in s}
    statut, aff, eff = resoudre(s, {"TP1":4, "TP2": 4, "TP3":6}, compat)
    assert statut==cp_model.OPTIMAL and all(g in compat[e] for e,g in aff.items()) and eff["TP3"]==6, aff
    print("4/4 choix LV2 : respecte (C3)")


def test_instance():
    # 75 etudiants repartis en 5 TP de 16 (bornes du cadrage : 50 a 100)
    s = {i: ("Allemand" if i%4 else "Espagnol" if i%3 else "Autre") for i in range(1,76)}
    statut, aff, eff = resoudre(s, {f"TP{i}": 16 for i in range(1,6)})
    assert len(aff)==75 and all(eff[g] <= 16 for g in eff), eff
    print("5/5 instance : 75 etudiants, 5 TP, OK")


if __name__ == "__main__":
    for t in (test_equilibre, test_capacites, test_infeasible, test_choix_lv2, test_instance): t()
    print("5/5 tests passent")
