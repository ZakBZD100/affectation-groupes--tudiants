"""Greedy constructif — complément au solveur exact CP-SAT.

Le greedy affecte chaque étudiant au groupe ouvert le moins chargé, type par
type, en respectant C3 (choix) et, quand TP et TD coexistent, C4 (le TD est
celui du parent du TP). Il ne garantit pas l'optimum : c'est le CP-SAT qui
fournit l'affectation de référence.
"""
import os
import sqlite3
import sys
import time

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_cpsat import (  # noqa: E402
    _normaliser_groupes,
    admis_de,
    blocs_de,
    resoudre,
)
from evaluation import evaluer  # noqa: E402
from generateur_instances import generer_lot  # noqa: E402
from groupes import construire_groupes_lv2  # noqa: E402

ORDRE_TYPES = {"LV2": 0, "LV1": 1, "TP": 2, "TD": 3}


def greedy(s, groupes, compat=None):
    """Affectation gloutonne multi-type. Retourne (aff, eff) ou ({}, {})."""
    groupes = _normaliser_groupes(groupes)
    if not groupes:
        return {}, {}
    par_nom = {g.nom: g for g in groupes}
    a = admis_de(s, groupes, compat)
    if a is None:
        return {}, {}
    resultat = blocs_de(s, groupes, a, compat)
    if resultat is None:
        return {}, {}
    blocs, _, nb = resultat

    # C5a : ouvrir assez de places par bloc, les plus grosses d'abord.
    ouv = set()
    for i, bloc in enumerate(blocs):
        besoin = nb[i]
        for nom in sorted(bloc["groupes"], key=lambda n: -par_nom[n].capacite):
            if besoin <= 0:
                break
            ouv.add(nom)
            besoin -= par_nom[nom].capacite
        if besoin > 0:
            return {}, {}

    types = sorted({g.type for g in groupes}, key=lambda t: ORDRE_TYPES.get(t, 9))
    for e in s:  # chaque étudiant doit avoir un groupe ouvert par type
        for type_ in types:
            if not any(par_nom[n].type == type_ and n in ouv for n in a[e]):
                candidats = [n for n in a[e] if par_nom[n].type == type_]
                if not candidats:
                    return {}, {}
                ouv.add(max(candidats, key=lambda n: par_nom[n].capacite))

    # Phase 2 : plus contraint d'abord, groupe ouvert le moins chargé.
    aff, eff = {}, {g.nom: 0 for g in groupes}
    for e in sorted(s, key=lambda e: len(a[e])):
        affectation = {}
        for type_ in types:
            if type_ == "TD" and "TP" in affectation:
                parent = par_nom[affectation["TP"]].parent
                if (
                    parent is None
                    or parent not in a[e]
                    or eff[parent] >= par_nom[parent].capacite
                ):
                    return {}, {}
                best = parent
            else:
                candidats = [
                    n
                    for n in a[e]
                    if par_nom[n].type == type_
                    and n in ouv
                    and eff[n] < par_nom[n].capacite
                ]
                if not candidats:
                    return {}, {}
                best = min(candidats, key=lambda n: eff[n])
            affectation[type_] = best
            eff[best] += 1
        aff[e] = affectation if len(types) > 1 else affectation[types[0]]
    return aff, eff


def instance_lv2(inst, cap=24):
    """Instance -> (s, groupes LV2, compat) sur les étudiants normaux."""
    etuds = [e for e in inst.etudiants if e.statut == "normal"]
    s = {e.id: e.lv2 for e in etuds}
    groupes = construire_groupes_lv2(inst, cap, marge=0)
    compat = {
        e.id: [
            g.nom
            for g in groupes
            if g.nom.startswith(f"LV2_{e.lv2}_")
        ]
        for e in etuds
    }
    return s, groupes, compat


def maxmin(resultat):
    """Écart entre le groupe le plus chargé et le moins chargé."""
    ouverts = [n for n in resultat.detail["effectifs"].values() if n > 0]
    return max(ouverts) - min(ouverts) if ouverts else 0


def afficher(nom, r, dt):
    if not r.faisable:
        print("  %-16s INFAISABLE  %s" % (nom, "; ".join(r.violations)))
        return
    print(
        "  %-16s %2d %7.3f %7.3f %3d %7.3f %9.4f"
        % (
            nom,
            r.detail["k"],
            r.criteres["f1"],
            r.normalises["f1"],
            maxmin(r),
            r.score,
            dt,
        )
    )


# ---------- instance réelle (.grist septembre) ----------
GRIST = os.path.join(
    RACINE, "donnees", "CPB1 S1 2026-2027 - septembre - Projet 3A.grist"
)


def instance_reelle():
    con = sqlite3.connect("file:%s?mode=ro" % GRIST, uri=True)
    rows = con.execute("SELECT id, TypeLV2, GroupeTP FROM Etudiants").fetchall()
    etudiants = {r[0]: {"lv2": r[1], "tp_ref": r[2]} for r in rows}
    grp = con.execute(
        "SELECT id, Nom, Effectif FROM Groupes WHERE Type='TP'"
    ).fetchall()
    tp = {r[0]: {"nom": r[1], "eff": r[2]} for r in grp}
    con.close()
    cap = max(g["eff"] for g in tp.values())
    s = {
        eid: e["lv2"]
        for eid, e in etudiants.items()
        if e["tp_ref"] is not None and e["tp_ref"] in tp
    }
    from groupes import Groupe

    groupes = tuple(
        Groupe(nom, "TP", cap)
        for nom in sorted(
            {tp[e["tp_ref"]]["nom"] for e in etudiants.values() if e["tp_ref"] in tp}
        )
    )
    return s, groupes, None  # référence réelle : pas de compat LV2 sur les TP


if __name__ == "__main__":
    print("=" * 78)
    print("HEURISTIQUE GREEDY vs CP-SAT EXACT (juge : evaluation.py)")
    print("=" * 78)

    # --- 1. instance réelle ---
    try:
        s, groupes, compat = instance_reelle()
    except (sqlite3.Error, FileNotFoundError) as exc:
        print("\n[1] Instance réelle indisponible : %s" % exc)
    else:
        print(
            "\n[1] Instance réelle (septembre) : n=%d, %d groupes TP"
            % (len(s), len(groupes))
        )
        print(
            "\n  %-16s %2s %7s %7s %3s %7s %9s"
            % ("Methode", "k", "f1", "f1~", "mm", "score", "t(s)")
        )
        print("  " + "-" * 62)

        t0 = time.perf_counter()
        aff_g, eff_g = greedy(s, groupes, compat)
        t_g = time.perf_counter() - t0
        afficher("Greedy", evaluer(s, groupes, aff_g, compat=compat), t_g)

        t0 = time.perf_counter()
        statut, aff_c, eff_c, ind_c = resoudre(s, groupes, compat=compat)
        t_c = time.perf_counter() - t0
        afficher("CP-SAT", evaluer(s, groupes, aff_c, compat=compat), t_c)

    # --- 2. instances générées (lot de 10) ---
    print("\n[2] Lot de 10 instances générées (LV2, cap=24)")
    print(
        "  %-5s %4s | %-31s | %-31s"
        % ("inst", "n", "Greedy (k/f1~/score/t)", "CP-SAT (k/f1~/score/t)")
    )
    print("  " + "-" * 78)
    lot = generer_lot(10, seed=7)
    sg = sc = tg = tc = 0.0
    wins_g = 0
    for i, inst in enumerate(lot, 1):
        s, groupes, compat = instance_lv2(inst)
        t0 = time.perf_counter()
        aff_g, eff_g = greedy(s, groupes, compat)
        dtg = time.perf_counter() - t0
        r_g = evaluer(s, groupes, aff_g, compat=compat)

        t0 = time.perf_counter()
        statut, aff_c, eff_c, ind_c = resoudre(s, groupes, compat=compat)
        dtc = time.perf_counter() - t0
        r_c = evaluer(s, groupes, aff_c, compat=compat)

        if r_g.score <= r_c.score:
            wins_g += 1
        sg += r_g.score
        sc += r_c.score
        tg += dtg
        tc += dtc
        print(
            "  %-5d %4d | %2d %6.3f %6.3f %7.4f | %2d %6.3f %6.3f %7.4f"
            % (
                i,
                len(s),
                r_g.detail["k"],
                r_g.normalises["f1"],
                r_g.score,
                dtg,
                r_c.detail["k"],
                r_c.normalises["f1"],
                r_c.score,
                dtc,
            )
        )

    n = len(lot)
    print("  " + "-" * 78)
    print(
        "  Moyenne : greedy score=%.3f t=%.5fs | CP-SAT score=%.3f t=%.5fs"
        % (sg / n, tg / n, sc / n, tc / n)
    )
    print("  CP-SAT >= greedy sur le score : %d/%d instances" % (n - wins_g, n))
    print("  Gain de temps moyen : x%.0f" % ((tc / n) / (tg / n) if tg / n > 0 else 0))

    print("\n" + "=" * 78)
    print("LECTURE")
    print("=" * 78)
    print("Le greedy approche l'optimum mais ne le garantit pas ; le CP-SAT")
    print("fournit l'affectation de référence et prouve l'optimum atteint.")
