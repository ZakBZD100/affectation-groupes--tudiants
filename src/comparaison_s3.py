"""S3 : extraction des donnees reelles (.grist) + comparaison 3 methodes.

Methodes comparees sur la meme instance reelle (septembre) :
  1. Reference manuelle  : l'affectation reelle de l'admin (extraite du .grist)
  2. Baseline naive      : remplissage a la volee (greedy, premier groupe avec de la place)
  3. Modele CP-SAT       : notre optimiseur (f1 relative, C5-C7)
"""
import sqlite3, sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from test_cpsat import resoudre

GRIST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "donnees", "CPB1 S1 2026-2027 - septembre - Projet 3A.grist")

# ---------- 1. Extraction depuis le .grist ----------
con = sqlite3.connect("file:%s?mode=ro" % GRIST, uri=True)

# Etudiants : id, TypeLV2, GroupeTP (reference manuelle)
rows = con.execute("SELECT id, TypeLV2, GroupeTP FROM Etudiants").fetchall()
etudiants = {r[0]: {"lv2": r[1], "tp_ref": r[2]} for r in rows}

# Groupes TP : id -> nom, effectif
grp_rows = con.execute("SELECT id, Nom, Effectif FROM Groupes WHERE Type='TP'").fetchall()
tp_groups = {r[0]: {"nom": r[1], "eff": r[2]} for r in grp_rows}
# Capacite max observee sur les TP
tp_cap = max(g["eff"] for g in tp_groups.values()) if tp_groups else 16
con.close()

# Filtrer : etudiants avec un TP assigne (reference non vide)
s_ref = {eid: e["lv2"] for eid, e in etudiants.items() if e["tp_ref"] is not None and e["tp_ref"] in tp_groups}
tp_ids = sorted(set(etudiants[eid]["tp_ref"] for eid in s_ref))
groupes = {tp_groups[tid]["nom"]: tp_cap for tid in tp_ids}

print("=" * 70)
print("INSTANCE REELLE (septembre, .grist)")
print("=" * 70)
print("Etudiants avec TP de reference :", len(s_ref))
print("Groupes TP utilises :", {tp_groups[t]["nom"]: tp_groups[t]["eff"] for t in tp_ids})
print("Capacite retenue pour le modele :", tp_cap)
print()

# ---------- 2. Reference manuelle ----------
eff_ref = {}
for eid, tp in ((eid, etudiants[eid]["tp_ref"]) for eid in s_ref):
    nom = tp_groups[tp]["nom"]
    eff_ref[nom] = eff_ref.get(nom, 0) + 1

# ---------- 3. Baseline naive (greedy) ----------
def baseline_naive(s, groupes):
    """Remplissage a la volee : chaque etudiant va dans le premier groupe avec de la place."""
    aff, eff = {}, {g: 0 for g in groupes}
    for e, lv in s.items():
        place = False
        for g in groupes:
            if eff[g] < groupes[g]:
                aff[e] = g
                eff[g] += 1
                place = True
                break
        if not place:
            return {}, {}  # infaisable
    return aff, eff

t0 = time.perf_counter()
aff_base, eff_base = baseline_naive(s_ref, groupes)
t_base = time.perf_counter() - t0

# ---------- 4. Modele CP-SAT ----------
t0 = time.perf_counter()
statut, aff_sat, eff_sat, ind_sat = resoudre(s_ref, groupes, k=len(groupes))
t_sat = time.perf_counter() - t0

# ---------- 5. Calcul des indicateurs pour chaque methode ----------
def calc_ind(eff, k, N):
    ouverts = [g for g in eff if eff[g] > 0]
    f1 = sum(abs(k * eff[g] - N) for g in ouverts)
    r = N % k
    fmin, fmax = 2 * r * (k - r), 2 * N * (k - 1)
    norm = 0.0 if fmax == fmin else (f1 - fmin) / (fmax - fmin)
    mm = max(eff[g] for g in ouverts) - min(eff[g] for g in ouverts)
    return f1, round(norm, 3), mm

N = len(s_ref)
k = len(groupes)

f1_ref, norm_ref, mm_ref = calc_ind(eff_ref, k, N)
f1_base, norm_base, mm_base = calc_ind(eff_base, k, N)
f1_sat,  norm_sat,  mm_sat  = ind_sat["f1"], ind_sat["f1_norm"], ind_sat["maxmin"]

print("=" * 70)
print("COMPARAISON 3 METHODES (meme instance, meme k=%d, meme N=%d)" % (k, N))
print("=" * 70)
print("%-22s %6s %9s %8s %10s" % ("Methode", "f1", "f1_norm", "maxmin", "t(s)"))
print("-" * 70)
print("%-22s %6d %9.3f %8d %10s" % ("Reference manuelle", f1_ref, norm_ref, mm_ref, "(fixe)"))
print("%-22s %6d %9.3f %8d %10.4f" % ("Baseline naive", f1_base, norm_base, mm_base, t_base))
print("%-22s %6d %9.3f %8d %10.4f" % ("Modele CP-SAT", f1_sat, norm_sat, mm_sat, t_sat))
print("-" * 70)

# Effectifs detailles
print("\nEffectifs par groupe :")
print("%-12s %8s %8s %8s" % ("Groupe", "Ref", "Base", "CP-SAT"))
for g in sorted(groupes.keys()):
    print("%-12s %8d %8d %8d" % (g, eff_ref.get(g, 0), eff_base.get(g, 0), eff_sat.get(g, 0)))

# Verdict
print("\nVERDICT :")
if f1_sat <= f1_ref and f1_sat <= f1_base:
    print("  CP-SAT <= reference manuelle ET <= baseline naive sur f1.")
    print("  L'optimisation ameliore l'equilibre par rapport au remplissage a la volee")
    print("  et par rapport a l'affectation reelle de l'admin.")
else:
    print("  (voir tableau ci-dessus)")
