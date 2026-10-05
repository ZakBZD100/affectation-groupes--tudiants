"""tests CP-SAT - affectation des groupes, projet 3A"""
from ortools.sat.python import cp_model


def resoudre(s, groupes, k=None, compat=None):
    m = cp_model.CpModel()
    k = len(groupes) if k is None else k
    x={(e, g):m.NewBoolVar(f"x{e}_{g}") for e in s for g in groupes}
    for e in s: m.Add(sum(x[e,g] for g in groupes) == 1) # C1 : un seul groupe
    for g,cap in groupes.items(): m.Add(sum(x[e, g] for e in s)<=cap) # C2 : effectif max
    for e, a in (compat or {}).items(): # C3 : groupes compatibles avec s(e)
        for g in set(groupes)-set(a): m.Add(x[e,g]==0)
    n={g:sum(x[e, g] for e in s) for g in groupes}
    y={g:m.NewBoolVar(f"y{g}") for g in groupes}
    m.Add(sum(y.values())==k) # C5 : exactement k groupes ouverts (dur, avant l'equilibre)
    for g,cap in groupes.items():
        m.Add(n[g]<=cap*y[g]) # C6 : rien dans un groupe ferme
        m.Add(y[g]<=n[g])     # C7 : un groupe ouvert a au moins un etudiant
    N=len(s)
    ecarts=[m.NewIntVar(0, k*N, f"e{g}") for g in groupes]
    for g,v in zip(groupes, ecarts): m.AddAbsEquality(v, k*n[g]-N) # f1 : |k*n(g)-N|
    m.Minimize(sum(ecarts))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds=10
    statut=solver.Solve(m)
    if statut not in (cp_model.OPTIMAL,cp_model.FEASIBLE): return statut, {}, {}, {}
    aff={e:next(g for g in groupes if solver.Value(x[e,g])) for e in s}
    eff={g:solver.Value(n[g]) for g in groupes}
    ouverts=[g for g in groupes if solver.Value(y[g])]
    f1=sum(abs(k*eff[g]-N) for g in ouverts)
    r=N%k
    fmin,fmax=2*r*(k-r), 2*N*(k-1)
    norm=0.0 if fmax==fmin else (f1-fmin)/(fmax-fmin)
    ind={"k":len(ouverts), "f1":f1, "f1_norm":round(norm,3),
         "maxmin":max(eff[g] for g in ouverts)-min(eff[g] for g in ouverts)}
    return statut, aff, eff, ind


def test_equilibre():
    # le mini-test de la semaine 1 : 12 etudiants, 3 TP de 5
    s = {**{i: "Allemand" for i in range(7)}, **{i:"Espagnol" for i in range(7,12)}}
    statut, aff, eff, ind = resoudre(s, {"TP1": 5,"TP2":5, "TP3": 5})
    assert statut == cp_model.OPTIMAL and len(aff)==12 and sorted(eff.values()) == [4,4,4], eff
    assert ind["f1"]==0 and ind["f1_norm"]==0.0, ind
    print("1/7 equilibre : OPTIMAL, effectifs 4/4/4, f1=0")


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
    print("4/7 choix LV2 : respecte (C3)")


def test_instance():
    # 75 etudiants repartis en 5 TP de 16 (bornes du cadrage : 50 a 100)
    s = {i: ("Allemand" if i%4 else "Espagnol" if i%3 else "Autre") for i in range(1,76)}
    statut, aff, eff, ind = resoudre(s, {f"TP{i}": 16 for i in range(1,6)})
    assert len(aff)==75 and all(eff[g] <= 16 for g in eff), eff
    print("5/7 instance : 75 etudiants, 5 TP, OK")


def test_k_impose():
    # k est une contrainte dure : k=2 -> au plus 2*5=10 places pour 12 etudiants
    statut,_,_,_ = resoudre({i:"Allemand" for i in range(12)}, {"TP1":5, "TP2":5, "TP3":5}, k=2)
    assert statut == cp_model.INFEASIBLE, statut
    print("6/7 k impose : k=2 pour 12 etudiants -> infaisable")


def test_indicateurs():
    # 10 etudiants, 3 TP de 5 : indivisible -> meilleur repli 4/3/3, f1=4=fmin
    statut, aff, eff, ind = resoudre({i:"Allemand" for i in range(10)}, {"TP1":5, "TP2":5, "TP3":5})
    assert statut == cp_model.OPTIMAL and sorted(eff.values()) == [3,3,4], eff
    assert ind["f1"]==4 and ind["f1_norm"]==0.0 and ind["maxmin"]==1, ind
    print("7/7 indicateurs : 4/3/3, f1=4=fmin, norm=0, max-min=1")


if __name__ == "__main__":
    for t in (test_equilibre, test_capacites, test_infeasible, test_choix_lv2, test_instance, test_k_impose, test_indicateurs): t()
    print("7/7 tests passent")
