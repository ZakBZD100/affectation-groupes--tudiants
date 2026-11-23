"""Expériences S5 : greedy vs CP-SAT sur les 27 instances figées.

Pour chaque instance : pool multi-type (profil standard), affectation greedy
et CP-SAT, puis notation par l'évaluateur. Sortie :
  - un tableau à l'écran ;
  - exports/resultats.csv (une ligne par instance, lisible Excel) ;
  - docs/instances_tables.tex (les tableaux du PDF).

Sensibilité aux poids (w1/w2) et comparaison avec l'affectation réelle.
"""
import csv
import os
import sys
import time

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from evaluation import evaluer  # noqa: E402
from generateur_instances import (  # noqa: E402
    generer_instances_extremes,
    generer_lot,
)
from groupes import PROFILS_CAPACITES, construire_groupes  # noqa: E402
from heuristique import greedy  # noqa: E402
from test_cpsat import resoudre  # noqa: E402

CAP = PROFILS_CAPACITES["standard"]
DOCS = os.path.join(RACINE, "docs")
EXPORTS = os.path.join(RACINE, "exports")


def toutes_les_instances():
    """Lot de 20 (seed=7) + 7 instances extrêmes : le jeu figé du PDF."""
    return list(generer_lot(20, seed=7)) + list(
        generer_instances_extremes(seed=0)
    )


def preparer(inst):
    """Instance -> (s, groupes, compat) sur les étudiants affectables."""
    actifs = [e for e in inst.etudiants if e.statut == "normal"]
    s = {e.id: e.lv2 for e in actifs}
    groupes = construire_groupes(inst, CAP)
    compat = {
        e.id: [
            g.nom
            for g in groupes
            if g.type != "LV2" or g.nom.startswith(f"LV2_{e.lv2}_")
        ]
        for e in actifs
    }
    return s, groupes, compat


def ligne_resultats(inst):
    """(greedy, CP-SAT) sur une instance : indicateurs + temps."""
    s, groupes, compat = preparer(inst)

    t0 = time.perf_counter()
    aff_g, _ = greedy(s, groupes, compat)
    tg = time.perf_counter() - t0
    r_g = evaluer(s, groupes, aff_g, compat=compat)

    t0 = time.perf_counter()
    _, aff_c, _, ind_c = resoudre(s, groupes, compat=compat)
    tc = time.perf_counter() - t0
    r_c = evaluer(s, groupes, aff_c, compat=compat)

    if not (r_g.faisable and r_c.faisable):
        return None
    return {
        "nom": inst.nom,
        "n": len(s),
        "k_lv2": r_c.detail["k_par_type"].get("LV2", 0),
        "k_lv1": r_c.detail["k_par_type"].get("LV1", 0),
        "k_td": r_c.detail["k_par_type"].get("TD", 0),
        "k_tp": r_c.detail["k_par_type"].get("TP", 0),
        "f1n_g": round(r_g.normalises["f1"], 3),
        "f1n_c": round(r_c.normalises["f1"], 3),
        "f3n_g": round(r_g.normalises["f3"], 3),
        "f3n_c": round(r_c.normalises["f3"], 3),
        "score_g": round(r_g.score, 3),
        "score_c": round(r_c.score, 3),
        "opt": "oui" if ind_c.get("statut") == "OPTIMAL" else "non",
        "ecart": ind_c.get("gap"),
        "t_g": round(tg, 4),
        "t_c": round(tc, 4),
    }


def sensibilite_poids(lot, nb=5):
    """Sweep w2 de 0 à 1 : compromis équilibre / nombre de groupes (f3 nul)."""
    lignes = []
    preps = [preparer(inst) for inst in lot[:nb]]
    hints = [greedy(s, gr, cp)[0] for s, gr, cp in preps]
    for w2 in (0.0, 0.25, 0.5, 0.75, 1.0):
        f1s, ks = [], []
        for (s, groupes, compat), aff_g in zip(preps, hints):
            _, _, _, ind = resoudre(
                s,
                groupes,
                compat=compat,
                poids={"f1": 1.0 - w2, "f2": w2, "f3": 0.0},
            )
            if ind:
                f1s.append(ind["f1_norm"])
                ks.append(ind["k"])
        lignes.append(
            {
                "w2": w2,
                "f1n": round(sum(f1s) / len(f1s), 3),
                "k": round(sum(ks) / len(ks), 2),
            }
        )
    return lignes


def instance_reelle():
    """Affectation réelle de septembre (fichier local, jamais poussé)."""
    import sqlite3

    chemin = os.path.join(
        RACINE, "donnees", "CPB1 S1 2026-2027 - septembre - Projet 3A.grist"
    )
    con = sqlite3.connect("file:%s?mode=ro" % chemin, uri=True)
    rows = con.execute(
        "SELECT id, TypeLV2, GroupeTP FROM Etudiants"
    ).fetchall()
    grp = con.execute(
        "SELECT id, Nom, Effectif FROM Groupes WHERE Type='TP'"
    ).fetchall()
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


def lignes_reelles():
    """Admin vs greedy vs CP-SAT sur la même instance réelle."""
    s, groupes, aff_ref = instance_reelle()
    resultats = []
    for nom, aff, appel in (
        ("Reference (admin)", aff_ref, None),
        ("Greedy", None, "greedy"),
        ("CP-SAT", None, "cpsat"),
    ):
        t0 = time.perf_counter()
        if appel == "greedy":
            aff, _ = greedy(s, groupes)
        elif appel == "cpsat":
            _, aff, _, _ = resoudre(s, groupes)
        dt = time.perf_counter() - t0
        r = evaluer(s, groupes, aff)
        resultats.append(
            {
                "methode": nom,
                "k": r.detail["k"],
                "f1": round(r.criteres["f1"], 3),
                "f1n": round(r.normalises["f1"], 3),
                "maxmin": max(
                    v for v in r.detail["effectifs"].values() if v > 0
                )
                - min(v for v in r.detail["effectifs"].values() if v > 0),
                "score": round(r.score, 3),
                "t": round(dt, 4),
            }
        )
    return resultats


# ---------------------------------------------------------------------------
# Tableaux LaTeX
# ---------------------------------------------------------------------------
def _tableau(titre, entetes, largeurs, lignes):
    def echapper(c):
        # noms d'instances (lot_7_000) : les _ du texte brut sont protégés,
        # pas ceux des mathématiques des en-têtes ($k_{LV2}$). Décimales
        # à la française : 0.852 -> 0{,}852.
        return str(c).replace("_", "\\_").replace(".", "{,}")

    # adjustbox : reduit le tableau s'il depasse la page, jamais agrandi ;
    # tabcolsep serre pour garder le texte lisible une fois reduit.
    corps = (
        "\\begin{adjustbox}{max width=\\textwidth}\n"
        "\\begin{tabular}{%s}\n\\toprule\n%s\\\\\n\\midrule\n"
        % (
            "".join(largeurs),
            " & ".join(entetes) + " \\\\",
        )
    )
    corps += "\n".join(
        " & ".join(echapper(c) for c in l) + " \\\\" for l in lignes
    )
    corps += "\n\\bottomrule\n\\end{tabular}\n\\end{adjustbox}"
    return (
        "\\textbf{%s}\\par\n\\vspace{1mm}\n"
        "\\noindent{\\scriptsize\\setlength{\\tabcolsep}{3pt}\n%s}\n"
        % (titre, corps)
    )


def ecrire_latex(instances, resultats, poids, reelles, chemin):
    blocs = []

    lignes = []
    for inst in instances:
        r = inst.resume()
        rep = r["repartition_lv2"]
        meta = dict(r["meta"])
        # C = césure, R = redoublant (legende dans le titre) ; langues
        # fusionnees "A/E/Aut" pour tenir dans la page.
        cas = "+".join(p[0].upper() for p in r["cas_particuliers"]) or "-"
        lignes.append(
            (
                r["nom"],
                r["effectif"],
                "%d/%d/%d" % (
                    rep.get("Allemand", 0), rep.get("Espagnol", 0),
                    rep.get("Autre", 0),
                ),
                r["choix_tardifs"],
                cas,
            )
        )
    blocs.append(
        _tableau(
            "Les 27 instances figées (lot seed=7 + extrêmes ; "
            "C = césure, R = redoublant)",
            ("Instance", "$n$", "LV2 A/E/Aut", "Choix tard.", "Cas part."),
            ("l", "r", "r", "r", "l"),
            lignes,
        )
    )

    blocs.append(
        _tableau(
            "Résultats : groupes ouverts par type "
            "(C8 : $k_{TP} = 2\\,k_{TD}$)",
            ("Instance", "$n$", "$k_{LV2}$", "$k_{LV1}$", "$k_{TD}$",
             "$k_{TP}$"),
            ("l", "r", "r", "r", "r", "r"),
            [
                (r["nom"], r["n"], r["k_lv2"], r["k_lv1"], r["k_td"],
                 r["k_tp"])
                for r in resultats
            ],
        )
    )

    blocs.append(
        _tableau(
            "Résultats : note du juge (greedy vs CP-SAT, profil standard)",
            ("Instance", "$\\tilde f_1$ g", "$\\tilde f_1$ c",
             "score g", "score c", "$t_g$", "$t_c$"),
            ("l", "r", "r", "r", "r", "r", "r"),
            [
                (r["nom"], r["f1n_g"], r["f1n_c"], r["score_g"],
                 r["score_c"], r["t_g"], r["t_c"])
                for r in resultats
            ],
        )
    )

    blocs.append(
        _tableau(
            "Sensibilité aux poids : $w_1 + w_2 = 1$ sur $f_1, f_2$ "
            "($w_3 = 0$, moyenne de 5 instances)",
            ("$w_2$ (poids de $f_2$)", "$\\tilde f_1$", "$k$ total"),
            ("l", "r", "r"),
            [(str(p["w2"]).replace(".", "{,}"), p["f1n"], p["k"]) for p in poids],
        )
    )

    blocs.append(
        _tableau(
            "Instance réelle de septembre : 62 étudiants, 4 TP de capacité 16",
            ("Méthode", "$k$", "$f_1$", "$\\tilde f_1$", "max$-$min",
             "score", "$t$ (s)"),
            ("l", "r", "r", "r", "r", "r", "r"),
            [
                (r["methode"], r["k"], r["f1"], str(r["f1n"]).replace(".", "{,}"),
                 r["maxmin"], str(r["score"]).replace(".", "{,}"), r["t"])
                for r in reelles
            ],
        )
    )

    with open(chemin, "w", encoding="utf-8") as f:
        f.write(
            "% Généré par src/experiences.py — ne pas éditer à la main.\n"
            + "\n\n".join(blocs)
            + "\n"
        )


def main():
    instances = toutes_les_instances()
    print("%d instances" % len(instances))

    resultats = []
    for i, inst in enumerate(instances, 1):
        ligne = ligne_resultats(inst)
        if ligne is None:
            print("  %-24s INFAISABLE" % inst.nom)
            continue
        resultats.append(ligne)
        print(
            "  %-24s n=%3d k=%d/%d/%d/%d  score %.3f vs %.3f%s (%.3fs / %.3fs)"
            % (
                ligne["nom"], ligne["n"], ligne["k_lv2"], ligne["k_lv1"],
                ligne["k_td"], ligne["k_tp"], ligne["score_g"],
                ligne["score_c"], " opt" if ligne["opt"] == "oui" else "",
                ligne["t_g"], ligne["t_c"],
            )
        )

    if resultats:
        g = [r["score_g"] for r in resultats]
        c = [r["score_c"] for r in resultats]
        bons = sum(1 for r in resultats if r["score_c"] >= r["score_g"])
        opt = sum(1 for r in resultats if r["opt"] == "oui")
        print(
            "moyennes : greedy %.3f, CP-SAT %.3f ; CP-SAT >= greedy sur %d/%d"
            % (sum(g) / len(g), sum(c) / len(c), bons, len(resultats))
        )
        print("optimalite prouvee : %d/%d" % (opt, len(resultats)))

    os.makedirs(EXPORTS, exist_ok=True)
    chemin_csv = os.path.join(EXPORTS, "resultats.csv")
    with open(chemin_csv, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(resultats[0]))
        writer.writeheader()
        writer.writerows(resultats)
    print("-> %s (%d lignes)" % (chemin_csv, len(resultats)))

    lot = generer_lot(20, seed=7)
    poids = sensibilite_poids(lot)
    print("poids :", [(p["w2"], p["f1n"], p["k"]) for p in poids])

    try:
        reelles = lignes_reelles()
    except Exception as exc:  # fichier .grist absent : table vide
        print("instance réelle indisponible :", exc)
        reelles = []
    else:
        for r in reelles:
            print("  %-20s score=%.3f" % (r["methode"], r["score"]))

    os.makedirs(DOCS, exist_ok=True)
    chemin_tex = os.path.join(DOCS, "instances_tables.tex")
    ecrire_latex(instances, resultats, poids, reelles, chemin_tex)
    print("-> %s" % chemin_tex)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
