"""greedy constructif - complement au solveur exact CP-SAT"""
import os, sys, time, sqlite3
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from test_cpsat import resoudre, admis_de, blocs_de, nb_blocs
from generateur_instances import generer_lot


def greedy(s, groupes, compat=None):
    a = admis_de(s, groupes, compat)
    if a is None:
        return {}, {}
    blocs = blocs_de(a, groupes)
    nb = nb_blocs(a, blocs)
    ouv = set()
    for i, bl in enumerate(blocs): # C5a : ouverture minimale, grosses places d'abord
        bes = nb[i]
        for g in sorted(bl, key=lambda g: -groupes[g]):
            if bes <= 0:
                break
            ouv.add(g)
            bes -= groupes[g]
        if bes > 0:
            return {}, {}
    for e in s: # etudiant sans groupe ouvert compatible -> on en ouvre un
        if not any(g in ouv for g in a[e]):
            ouv.add(max(a[e], key=lambda g: groupes[g]))
    # phase 2 : plus contraint d'abord, dans le groupe ouvert le moins charge
    aff, eff = {}, {g: 0 for g in groupes}
    for e in sorted(s, key=lambda e: len(a[e])):
        cand = [g for g in a[e] if g in ouv and eff[g] < groupes[g]]
        if not cand:
            return {}, {}
        best = min(cand, key=lambda g: eff[g])
        aff[e] = best
        eff[best] += 1
    return aff, eff


def calc_ind(eff, N):
    ouv = [g for g in eff if eff[g] > 0]
    k = len(ouv)
    f1 = sum(abs(k * eff[g] - N) for g in ouv)
    r = N % k if k else 0
    fmin, fmax = 2 * r * (k - r), 2 * N * (k - 1)
    norm = 0.0 if fmax == fmin else (f1 - fmin) / (fmax - fmin)
    mm = max(eff[g] for g in ouv) - min(eff[g] for g in ouv) if ouv else 0
    return k, f1, round(norm, 3), mm


def instance_lv2(inst, cap=24):
    etuds = [e for e in inst.etudiants if e.statut == "normal"]
    s = {e.id: e.lv2 for e in etuds}
    groupes, compat = {}, {}
    for L in sorted(set(s.values())):
        nl = sum(1 for v in s.values() if v == L)
        ngrp = -(-nl // cap)
        noms = [f"{L}_{i}" for i in range(1, ngrp + 1)]
        for nom in noms:
            groupes[nom] = cap
        for e in s:
            if s[e] == L:
                compat[e] = noms
    return s, groupes, compat


# ---------- instance reelle (.grist septembre) ----------
GRIST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "donnees", "CPB1 S1 2026-2027 - septembre - Projet 3A.grist")


def instance_reelle():
    con = sqlite3.connect("file:%s?mode=ro" % GRIST, uri=True)
    rows = con.execute("SELECT id, TypeLV2, GroupeTP FROM Etudiants").fetchall()
    etudiants = {r[0]: {"lv2": r[1], "tp_ref": r[2]} for r in rows}
    grp = con.execute("SELECT id, Nom, Effectif FROM Groupes WHERE Type='TP'").fetchall()
    tp = {r[0]: {"nom": r[1], "eff": r[2]} for r in grp}
    con.close()
    cap = max(g["eff"] for g in tp.values())
    s = {eid: e["lv2"] for eid, e in etudiants.items()
         if e["tp_ref"] is not None and e["tp_ref"] in tp}
    noms = sorted(set(tp[e["tp_ref"]]["nom"] for e in etudiants.values()
                      if e["tp_ref"] in tp))
    groupes = {n: cap for n in noms}
    return s, groupes, None  # reference reelle : pas de compat LV2 sur les TP


if __name__ == "__main__":
    print("=" * 72)
    print("HEURISTIQUE GREEDY vs CP-SAT EXACT")
    print("=" * 72)

    # --- 1. Instance reelle ---
    s, groupes, compat = instance_reelle()
    N = len(s)
    print("\n[1] Instance reelle (septembre) : n=%d, %d groupes TP proposes" % (N, len(groupes)))

    t0 = time.perf_counter()
    aff_g, eff_g = greedy(s, groupes, compat)
    t_g = time.perf_counter() - t0
    kg, f1_g, norm_g, mm_g = calc_ind(eff_g, N)

    t0 = time.perf_counter()
    statut, aff_c, eff_c, ind_c = resoudre(s, groupes, compat=compat)
    t_c = time.perf_counter() - t0

    print("  %-14s %3s %6s %9s %8s %10s" % ("Methode", "k", "f1", "f1_norm", "maxmin", "t(s)"))
    print("  " + "-" * 56)
    print("  %-14s %3d %6d %9.3f %8d %10.5f" % ("Greedy", kg, f1_g, norm_g, mm_g, t_g))
    print("  %-14s %3d %6d %9.3f %8d %10.5f" % ("CP-SAT", ind_c["k"], ind_c["f1"],
                                                ind_c["f1_norm"], ind_c["maxmin"], t_c))

    # --- 2. Instances generees (lot de 10) ---
    print("\n[2] Lot de 10 instances generees (N(64,10), LV2, cap=24)")
    lot = generer_lot(10, seed=7)
    print("  %-5s %4s | %-31s | %-31s" % ("inst", "n", "Greedy (k/f1/norm/mm/t)",
                                          "CP-SAT (k/f1/norm/mm/t)"))
    print("  " + "-" * 78)
    sg, sc, tg, tc = [0.0] * 4
    wins_g, meme_k = 0, 0
    for i, inst in enumerate(lot, 1):
        s, groupes, compat = instance_lv2(inst)
        N = len(s)
        t0 = time.perf_counter()
        aff_g, eff_g = greedy(s, groupes, compat)
        dtg = time.perf_counter() - t0
        kg, f1_g, norm_g, mm_g = calc_ind(eff_g, N)
        t0 = time.perf_counter()
        statut, aff_c, eff_c, ind_c = resoudre(s, groupes, compat=compat)
        dtc = time.perf_counter() - t0
        f1_c, norm_c, mm_c = ind_c["f1"], ind_c["f1_norm"], ind_c["maxmin"]
        if f1_g <= f1_c:
            wins_g += 1
        if kg == ind_c["k"]:
            meme_k += 1
        sg += f1_g; sc += f1_c; tg += dtg; tc += dtc
        print("  %-5d %4d | %2d %5d %6.3f %3d %7.4f | %2d %5d %6.3f %3d %7.4f" % (
            i, N, kg, f1_g, norm_g, mm_g, dtg,
            ind_c["k"], f1_c, norm_c, mm_c, dtc))

    n = len(lot)
    print("  " + "-" * 78)
    print("  Moyenne : greedy f1=%.1f t=%.5fs | CP-SAT f1=%.1f t=%.5fs" % (sg/n, tg/n, sc/n, tc/n))
    print("  Greedy <= CP-SAT sur f1 : %d/%d instances" % (wins_g, n))
    print("  Meme k minimal ouvert : %d/%d instances" % (meme_k, n))
    print("  Gain de temps moyen : x%.0f" % ((tc/n) / (tg/n) if tg/n > 0 else float('inf')))

    print("\n" + "=" * 72)
    print("LECTURE")
    print("=" * 72)
    print("Les deux ouvrent le minimum de groupes (C5a) : meme k dans %d/%d cas." % (meme_k, n))
    print("Le greedy reste ~%.0f fois plus rapide que CP-SAT." % ((tc/n) / (tg/n) if tg/n > 0 else 0))
    print("Sur f1 il approche l'optimum mais ne le garantit pas : le solveur")
    print("exact donne l'affectation officielle, le greedy un premier resultat immediat.")
