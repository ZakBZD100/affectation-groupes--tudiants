"""Générateur d'instances synthétiques — Projet 3A, semaine 2.

Instance = liste d'étudiants (effectif 50..100) avec choix de LV2,
+ proposition de groupes LV2 / LV1 / TP / TD avec leurs capacités.
Les capacités par défaut sont calées sur les données réelles (septembre).
"""
import random
import json
from math import ceil

CAPACITES_DEFAUT = {"LV2": 24, "LV1": 21, "TP": 16, "TD": 36}
DISTRIBUTION_DEFAUT = {"Allemand": 0.45, "Espagnol": 0.20, "Autre": 0.35}


def generer_instance(n=80, seed=42, distribution=None, capacites=None,
                     frac_choix_tardif=0.15, avec_cas_particuliers=True):
    """Retourne (etudiants, groupes).

    n                    : effectif, contraint à 50 <= n <= 100 (cadrage)
    distribution         : probas de chaque choix de LV2 (somme = 1)
    capacites            : effectif max par type de groupe
    frac_choix_tardif    : part d'étudiants qui choisissent leur LV2 le jour
                           de la rentrée (données « de dernière minute »)
    avec_cas_particuliers: ajoute des cas à traiter séparément (césure,
                           redoublant), comme dans les données réelles
    """
    assert 50 <= n <= 100, "effectif attendu entre 50 et 100 (cadrage)"
    rng = random.Random(seed)
    dist = distribution or DISTRIBUTION_DEFAUT
    cap = dict(CAPACITES_DEFAUT, **(capacites or {}))

    # --- étudiants : choix de LV2 tiré selon la distribution ---
    lv2 = list(dist.keys())
    poids = [dist[k] for k in lv2]
    etudiants = []
    for i in range(1, n + 1):
        choix = rng.choices(lv2, weights=poids, k=1)[0]
        etudiants.append({
            "id": i,
            "lv2": choix,                       # groupe LV2 demandé
            "choix_tardif": rng.random() < frac_choix_tardif,
            "statut": "normal",
        })

    # --- cas particuliers (optionnels, réalistes d'après les données) ---
    if avec_cas_particuliers and n >= 60:
        etudiants[-1]["statut"] = "cesure"       # non affecté à la rentrée
        for e in rng.sample(etudiants[:-1], 4):
            e["statut"] = "redoublant"           # affectation par UE

    # --- proposition de groupes : assez pour loger tout le monde ---
    groupes = []
    for i in range(1, 6):                        # 5 groupes LV2 max. (réel : 5)
        groupes.append({"nom": f"LV2_{i}", "type": "LV2", "cap": cap["LV2"]})
    for i in range(1, ceil(n / cap["LV1"]) + 1):
        groupes.append({"nom": f"Ang{i}", "type": "LV1", "cap": cap["LV1"]})
    for i in range(1, ceil(n / cap["TP"]) + 1):
        groupes.append({"nom": f"TP{i}", "type": "TP", "cap": cap["TP"],
                        "parent": f"TD{1 + (i - 1) // 2}"})
    for i in range(1, ceil(n / cap["TD"]) + 1):
        groupes.append({"nom": f"TD{i}", "type": "TD", "cap": cap["TD"]})
    return etudiants, groupes


def resume(etudiants, groupes):
    """Synthèse d'une instance (sert d'aperçu dans le compte-rendu)."""
    repartition = {}
    for e in etudiants:
        repartition[e["lv2"]] = repartition.get(e["lv2"], 0) + 1
    par_type = {}
    for g in groupes:
        par_type[g["type"]] = par_type.get(g["type"], 0) + 1
    return {
        "effectif": len(etudiants),
        "repartition_lv2": repartition,
        "groupes_proposes": par_type,
        "choix_tardifs": sum(1 for e in etudiants if e["choix_tardif"]),
        "cas_particuliers": sorted({e["statut"] for e in etudiants} - {"normal"}),
    }


def generer_n(mu=64, sigma=10, seed=None):
    """Effectif tire selon une loi normale N(mu, sigma), tronque au cadrage [50,100]."""
    rng = random.Random(seed)
    n = int(round(rng.gauss(mu, sigma)))
    return max(50, min(100, n))


def generer_lot(nb=10, seed=42, mu=64, sigma=10):
    """Jeu etendu d'instances : n ~ N(mu, sigma) tronque, parts LV2 bruitees puis renormalisees."""
    lot = []
    for i in range(nb):
        rng = random.Random(seed + i)
        n = generer_n(mu=mu, sigma=sigma, seed=seed + i)
        dist = {k: max(0.05, v + rng.gauss(0, 0.05)) for k, v in DISTRIBUTION_DEFAUT.items()}
        somme = sum(dist.values())
        dist = {k: v / somme for k, v in dist.items()}
        etudiants, groupes = generer_instance(n=n, seed=seed + i, distribution=dist)
        lot.append({"n": n, "distribution": dist, "etudiants": etudiants, "groupes": groupes})
    return lot


if __name__ == "__main__":
    for n in (50, 75, 100):
        e, g = generer_instance(n=n, seed=42)
        print("n=%3d ->" % n, json.dumps(resume(e, g), ensure_ascii=False))
    e, g = generer_instance()          # instance de référence (n = 80)
    print("\ninstance de référence n=80 :")
    print(json.dumps(resume(e, g), ensure_ascii=False, indent=2))
    lot = generer_lot(20, seed=7)      # jeu étendu : loi normale mu=64, sigma=10
    ns = [inst["n"] for inst in lot]
    print("\njeu etendu (20 instances, N(64,10) tronque [50,100]) :")
    print("n: min=%d max=%d moyenne=%.1f" % (min(ns), max(ns), sum(ns) / len(ns)))
