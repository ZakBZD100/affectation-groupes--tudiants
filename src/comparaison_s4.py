"""comparaison S4 : glouton vs CP-SAT vs affectation reelle (juge = evaluation.py)"""
import os, sys, time, sqlite3
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from test_cpsat import resoudre
from evaluation import evaluer
from heuristique import greedy, instance_lv2
from generateur_instances import generer_lot

GRIST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "donnees", "CPB1 S1 2026-2027 - septembre - Projet 3A.grist")


def instance_reelle():
    con = sqlite3.connect("file:%s?mode=ro" % GRIST, uri=True)
    rows = con.execute("SELECT id, TypeLV2, GroupeTP FROM Etudiants").fetchall()
    grp = con.execute("SELECT id, Nom, Effectif FROM Groupes WHERE Type='TP'").fetchall()
    con.close()
    tp = {r[0]: {"nom": r[1], "eff": r[2]} for r in grp}
    cap = max(g["eff"] for g in tp.values())
    s, aff = {}, {}
    for eid, lv2, ref in rows:
        if ref in tp:
            s[eid] = lv2
            aff[eid] = tp[ref]["nom"]
    groupes = {g["nom"]: cap for g in tp.values()}
    return s, groupes, aff


def afficher(nom, r, dt):
    if not r.faisable:
        print("  %-16s INFAISABLE  %s" % (nom, "; ".join(r.violations)))
        return
    print("  %-16s %2d %7.3f %3d %3.1f %7.3f %7.3f %9.4f" % (
        nom, r.detail["k"], r.criteres["f1"], r.criteres["f2"], r.criteres["f3"],
        r.normalises["f1"], r.score, dt))


if __name__ == "__main__":
    print("=" * 78)
    print("COMPARAISON S4 : glouton vs CP-SAT vs affectation reelle")
    print("juge unique : evaluation.py (C1/C2/C3/C5a, f1/f2/f3 -> score)")
    print("=" * 78)

    # --- 1. instance reelle, 3 methodes ---
    s, groupes, aff_ref = instance_reelle()
    N = len(s)
    print("\n[1] Instance reelle (septembre) : n=%d, %d groupes TP, cap=%d"
          % (N, len(groupes), max(groupes.values())))
    print("\n  %-16s %2s %7s %3s %3s %7s %7s %9s" % (
        "Methode", "k", "f1", "f2", "f3", "f1~", "score", "t(s)"))
    print("  " + "-" * 62)

    t0 = time.perf_counter()
    r_ref = evaluer(s, groupes, aff_ref)
    afficher("Reelle (admin)", r_ref, time.perf_counter() - t0)

    t0 = time.perf_counter()
    aff_g, eff_g = greedy(s, groupes)
    t_g = time.perf_counter() - t0
    r_g = evaluer(s, groupes, aff_g)
    afficher("Greedy", r_g, t_g)

    t0 = time.perf_counter()
    st, aff_c, eff_c, ind_c = resoudre(s, groupes)
    t_c = time.perf_counter() - t0
    r_c = evaluer(s, groupes, aff_c)
    afficher("CP-SAT", r_c, t_c)

    print("\n  Effectifs par groupe :")
    print("  %-8s %8s %8s %8s" % ("Groupe", "Reelle", "Greedy", "CP-SAT"))
    for g in sorted(groupes):
        reel = sum(1 for v in aff_ref.values() if v == g)
        print("  %-8s %8d %8d %8d" % (g, reel, eff_g.get(g, 0), eff_c.get(g, 0)))

    # --- 2. lot genere, greedy vs CP-SAT ---
    print("\n[2] 10 instances generees (LV2, cap=24) : greedy vs CP-SAT")
    print("  %4s %4s %4s %4s %7s %7s %8s %8s" % (
        "inst", "n", "k_g", "k_c", "f1_g", "f1_c", "score_g", "score_c"))
    print("  " + "-" * 62)
    lot = generer_lot(10, seed=7)
    sg = sc = 0.0
    wins = 0
    for i, inst in enumerate(lot, 1):
        s, groupes, compat = instance_lv2(inst)
        aff_g, eff_g = greedy(s, groupes, compat)
        st, aff_c, eff_c, ind_c = resoudre(s, groupes, compat=compat)
        r_g = evaluer(s, groupes, aff_g, compat=compat)
        r_c = evaluer(s, groupes, aff_c, compat=compat)
        sg += r_g.score
        sc += r_c.score
        if r_g.score >= r_c.score:
            wins += 1
        print("  %4d %4d %4d %4d %7.3f %7.3f %8.3f %8.3f" % (
            i, len(s), r_g.detail["k"], r_c.detail["k"],
            r_g.criteres["f1"], r_c.criteres["f1"], r_g.score, r_c.score))

    n = len(lot)
    print("  " + "-" * 62)
    print("  Moyenne : greedy score=%.3f | CP-SAT score=%.3f" % (sg / n, sc / n))
    print("  Greedy >= CP-SAT sur le score : %d/%d instances" % (wins, n))

    print("\nLECTURE")
    print("  Sur l'instance reelle, l'affectation de l'admin est exactement le")
    print("  remplissage a la volee : score minimal. Le greedy et le CP-SAT")
    print("  reequilibrent les TP et gagnent du score, sans changer k.")
    print("  Sur les instances generees, le greedy rejoint le CP-SAT partout :")
    print("  la limite n'est pas la qualite mais la garantie (le CP-SAT prouve")
    print("  l'optimum, le greedy non).")
