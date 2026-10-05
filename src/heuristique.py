"""Heuristique gloutonne (greedy constructif) - complement au solveur exact CP-SAT.

Principe : on place les etudiants un par un, chacun dans le groupe compatible
le moins charge qui a encore de la place. On traite d'abord les etudiants les
plus contraints (ceux qui ont le moins de groupes compatibles) pour eviter les
blocages en fin de parcours (heuristique "most constrained first" classique
en satisfaction de contraintes).

Complexite : O(n * k) - tres rapide, contrairement au CP-SAT qui peut etre
exponentiel en pire cas. Sur les instances du projet (n <= 100), le gain en
temps est net ; en qualite, le greedy est proche de l'optimum mais ne le
garantit pas (d'ou l'interet du solveur exact).
"""
import os, sys, time, sqlite3
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from test_cpsat import resoudre
from generateur_instances import generer_lot


def greedy(s, groupes, compat=None):
    """Remplissage constructif. Retourne (aff, eff) ou ({}, {}) si infaisable.

    s       : {etudiant: lv2}
    groupes : {nom: capacite}
    compat  : {etudiant: [groupes compatibles]} ou None (tous compatibles)
    """
    aff = {}
    eff = {g: 0 for g in groupes}

    def nb_compat(e):
        if compat and e in compat:
            return len([g for g in compat[e] if g in groupes])
        return len(groupes)

    # most constrained first : les etudiants avec le moins de choix d'abord
    etuds = sorted(s.keys(), key=nb_compat)

    for e in etuds:
        cand = [g for g in groupes if eff[g] < groupes[g]]
        if compat and e in compat:
            cand = [g for g in cand if g in compat[e]]
        if not cand:
            return {}, {}  # infaisable
        # choisir le groupe le moins charge (equilibre)
        best = min(cand, key=lambda g: eff[g])
        aff[e] = best
        eff[best] += 1
    return aff, eff


def calc_ind(eff, k, N):
    ouverts = [g for g in eff if eff[g] > 0]
    f1 = sum(abs(k * eff[g] - N) for g in ouverts)
    r = N % k
    fmin, fmax = 2 * r * (k - r), 2 * N * (k - 1)
    norm = 0.0 if fmax == fmin else (f1 - fmin) / (fmax - fmin)
    mm = max(eff[g] for g in ouverts) - min(eff[g] for g in ouverts)
    return f1, round(norm, 3), mm


def instance_lv2(inst, cap=24):
    """Instance generee -> (s, groupes LV2, compat) etudiants "normal"."""
    etuds = [e for e in inst["etudiants"] if e["statut"] == "normal"]
    s = {e["id"]: e["lv2"] for e in etuds}
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
    N, k = len(s), len(groupes)
    print("\n[1] Instance reelle (septembre) : n=%d, k=%d groupes TP" % (N, k))

    t0 = time.perf_counter()
    aff_g, eff_g = greedy(s, groupes, compat)
    t_g = time.perf_counter() - t0
    f1_g, norm_g, mm_g = calc_ind(eff_g, k, N)

    t0 = time.perf_counter()
    statut, aff_c, eff_c, ind_c = resoudre(s, groupes, compat=compat)
    t_c = time.perf_counter() - t0

    print("  %-14s %6s %9s %8s %10s" % ("Methode", "f1", "f1_norm", "maxmin", "t(s)"))
    print("  " + "-" * 52)
    print("  %-14s %6d %9.3f %8d %10.5f" % ("Greedy", f1_g, norm_g, mm_g, t_g))
    print("  %-14s %6d %9.3f %8d %10.5f" % ("CP-SAT", ind_c["f1"], ind_c["f1_norm"], ind_c["maxmin"], t_c))

    # --- 2. Instances generees (lot de 10) ---
    print("\n[2] Lot de 10 instances generees (N(64,10), LV2, cap=24)")
    lot = generer_lot(10, seed=7)
    print("  %-5s %4s %3s | %-28s | %-28s" % ("inst", "n", "k", "Greedy (f1/norm/mm/t)", "CP-SAT (f1/norm/mm/t)"))
    print("  " + "-" * 70)
    sg, sc, tg, tc = [0.0] * 4
    wins_g = 0
    for i, inst in enumerate(lot, 1):
        s, groupes, compat = instance_lv2(inst)
        N, k = len(s), len(groupes)
        t0 = time.perf_counter()
        aff_g, eff_g = greedy(s, groupes, compat)
        dtg = time.perf_counter() - t0
        f1_g, norm_g, mm_g = calc_ind(eff_g, k, N)
        t0 = time.perf_counter()
        statut, aff_c, eff_c, ind_c = resoudre(s, groupes, compat=compat)
        dtc = time.perf_counter() - t0
        f1_c, norm_c, mm_c = ind_c["f1"], ind_c["f1_norm"], ind_c["maxmin"]
        if f1_g <= f1_c:
            wins_g += 1
        sg += f1_g; sc += f1_c; tg += dtg; tc += dtc
        print("  %-5d %4d %3d | %6d %6.3f %3d %8.4f | %6d %6.3f %3d %8.4f" % (
            i, N, k, f1_g, norm_g, mm_g, dtg, f1_c, norm_c, mm_c, dtc))

    n = len(lot)
    print("  " + "-" * 70)
    print("  Moyenne : greedy f1=%.1f t=%.5fs | CP-SAT f1=%.1f t=%.5fs" % (sg/n, tg/n, sc/n, tc/n))
    print("  Greedy >= CP-SAT sur f1 : %d/%d instances" % (wins_g, n))
    print("  Gain de temps moyen : x%.0f" % ((tc/n) / (tg/n) if tg/n > 0 else float('inf')))

    print("\n" + "=" * 72)
    print("LECTURE")
    print("=" * 72)
    print("Le greedy est ~%.0f fois plus rapide que CP-SAT." % ((tc/n) / (tg/n) if tg/n > 0 else 0))
    print("En qualite, il est souvent proche mais pas toujours optimal :")
    print("le solveur exact garantit f1 = f_min (optimum), le greedy l'approche.")
    print("Usage : greedy pour un premier resultats immediat ; CP-SAT pour")
    print("l'affectation officielle (qualite garantie, temps encore acceptable).")
