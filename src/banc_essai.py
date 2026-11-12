"""Banc d'essai S3 : indicateurs calculés + sensibilité au nombre de groupes (k)."""
import os
import sys
import time

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_cpsat import resoudre  # noqa: E402
from generateur_instances import generer_lot  # noqa: E402
from groupes import construire_groupes_lv2, k_min_lv2  # noqa: E402

CAP = 24


def prep(inst):
    """Instance -> (s, groupes LV2, compat, k_min) sur les étudiants normaux.

    Le pool garde deux groupes de réserve par langue pour pouvoir tester
    k_min + 1 et k_min + 2.
    """
    etuds = [e for e in inst.etudiants if e.statut == "normal"]
    s = {e.id: e.lv2 for e in etuds}
    groupes = construire_groupes_lv2(inst, CAP, marge=2)
    compat = {
        e.id: [
            g.nom
            for g in groupes
            if g.nom.startswith(f"LV2_{e.lv2}_")
        ]
        for e in etuds
    }
    return s, groupes, compat, k_min_lv2(inst, CAP)


lot = generer_lot(10, seed=7)
print("banc d'essai S3 - affectation LV2 (C3 active, capacite 24)")
print('10 instances du jeu N(64,10), etudiants "normal" uniquement\n')

print("A) k = minimum necessaire")
print("  %4s %4s %3s %5s %8s %7s %6s" % ("inst", "n", "k", "f1", "f1_norm", "maxmin", "t(s)"))
som = [0.0, 0.0, 0.0]
for i, inst in enumerate(lot, 1):
    s, groupes, compat, kmin = prep(inst)
    t0 = time.perf_counter()
    statut, aff, eff, ind = resoudre(s, groupes, k=kmin, compat=compat)
    dt = time.perf_counter() - t0
    if not aff:
        print("  %4d %4d %3s  INFEASIBLE" % (i, len(s), kmin))
        continue
    print(
        "  %4d %4d %3d %5d %8.3f %7d %6.3f"
        % (i, len(s), ind["k"], ind["f1"], ind["f1_norm"], ind["maxmin"], dt)
    )
    som[0] += ind["f1"]
    som[1] += ind["f1_norm"]
    som[2] += ind["maxmin"]
print(
    "  moyenne : f1=%.1f  f1_norm=%.3f  maxmin=%.1f"
    % (som[0] / len(lot), som[1] / len(lot), som[2] / len(lot))
)

print("\nB) sensibilite au nombre de groupes ouverts (kmin, kmin+1, kmin+2)")
print("  %5s %12s %8s %11s %11s" % ("k", "infaisables", "f1_moy", "norm_moy", "maxmin_moy"))
for dk in (0, 1, 2):
    f1s, norms, mms, inf = [], [], [], 0
    for inst in lot:
        s, groupes, compat, kmin = prep(inst)
        k = kmin + dk
        if k > len(groupes):
            continue
        statut, aff, eff, ind = resoudre(s, groupes, k=k, compat=compat)
        if not aff:
            inf += 1
            continue
        f1s.append(ind["f1"])
        norms.append(ind["f1_norm"])
        mms.append(ind["maxmin"])
    m = len(f1s) or 1
    print(
        "  %+4d %9d/10 %8.1f %11.3f %11.1f"
        % (dk, inf, sum(f1s) / m, sum(norms) / m, sum(mms) / m)
    )
print("\nlecture : le pool offre des groupes de reserve (marge=2 par langue).")
print("f1 brut augmente mecaniquement avec k (facteur k) ; c'est f1_norm qui")
print("mesure l'equilibre relatif, et il baisse quand on ouvre un groupe de plus.")
