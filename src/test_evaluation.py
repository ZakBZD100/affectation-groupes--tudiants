import os
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from evaluation import evaluer


def exemple_pdf():
    """10 étudiants, 8 Allemand / 2 Espagnol, 3 groupes de capacité 5."""
    s = {f"A{i}": "Allemand" for i in range(1, 9)}
    s.update({f"E{i}": "Espagnol" for i in range(1, 3)})
    groupes = {"Al1": 5, "Al2": 5, "Es1": 5}
    compat = {e: (["Al1", "Al2"] if s[e] == "Allemand" else ["Es1"]) for e in s}

    aff1 = {
        "A1": "Al1", "A2": "Al1", "A3": "Al1", "A4": "Al1",
        "A5": "Al2", "A6": "Al2", "A7": "Al2", "A8": "Al2",
        "E1": "Es1", "E2": "Es1",
    }
    aff2 = {
        "A1": "Al1", "A2": "Al1", "A3": "Al1", "A4": "Al1", "A5": "Al1",
        "A6": "Al2", "A7": "Al2", "A8": "Al2",
        "E1": "Es1", "E2": "Es1",
    }
    return s, groupes, compat, aff1, aff2


def test_exemple_pdf():
    s, groupes, compat, aff1, aff2 = exemple_pdf()

    r1 = evaluer(s, groupes, aff1, compat=compat)
    assert r1.faisable
    assert r1.criteres["f1"] == 0.0
    assert r1.detail["f1_max"] == 0.5
    assert r1.normalises["f1"] == 0.0
    assert r1.criteres["f2"] == 3.0
    assert r1.normalises["f2"] == 0.0  # f2_min = f2_max = 3 : désactivé
    assert r1.criteres["f3"] == 0.0
    assert r1.score == 1.0

    r2 = evaluer(s, groupes, aff2, compat=compat)
    assert r2.faisable
    assert r2.criteres["f1"] == 0.5
    assert r2.normalises["f1"] == 1.0
    assert r2.score == 0.0
    print("1/7 exemple du PDF OK (f1=0 -> score 1, f1=0.5 -> score 0)")


def test_contraintes_dures():
    s, groupes, compat, aff1, _ = exemple_pdf()

    manquant = dict(aff1)
    del manquant["A1"]
    r = evaluer(s, groupes, manquant, compat=compat)
    assert not r.faisable and r.score is None
    assert any(v.startswith("C1") for v in r.violations)

    inconnu = dict(aff1)
    inconnu["Z"] = "Al1"
    r = evaluer(s, groupes, inconnu, compat=compat)
    assert not r.faisable and any("C1" in v for v in r.violations)

    mauvais_groupe = dict(aff1)
    mauvais_groupe["A1"] = "Es1"
    mauvais_groupe["E1"] = "Al1"
    r = evaluer(s, groupes, mauvais_groupe, compat=compat)
    assert not r.faisable and any("C3" in v for v in r.violations)

    surcharge = dict(aff1)
    surcharge["A5"] = "Al1"
    surcharge["A6"] = "Al1"  # Al1 = 6 > capacité 5
    r = evaluer(s, groupes, surcharge, compat=compat)
    assert not r.faisable and any("C2" in v for v in r.violations)

    inconnu_groupe = dict(aff1)
    inconnu_groupe["A1"] = "AlX"
    r = evaluer(s, groupes, inconnu_groupe, compat=compat)
    assert not r.faisable and any("groupes inconnus" in v for v in r.violations)

    print("2/7 contraintes dures OK (C1 manquant/inconnu, C2, C3)")


def test_f2_et_poids():
    s, _, _, aff1, _ = exemple_pdf()
    groupes4 = {"Al1": 5, "Al2": 5, "Al3": 5, "Es1": 5}
    compat4 = {
        e: (["Al1", "Al2", "Al3"] if s[e] == "Allemand" else ["Es1"])
        for e in s
    }

    r = evaluer(s, groupes4, aff1, compat=compat4)
    assert r.criteres["f2"] == 3.0
    assert r.detail["f2_min"] == 3
    assert r.detail["f2_max"] == 4
    assert r.normalises["f2"] == 0.0
    assert r.poids["f1"] == 0.5 and r.poids["f2"] == 0.5
    assert r.score == 1.0

    aff4 = {
        "A1": "Al1", "A2": "Al1", "A3": "Al1",
        "A4": "Al2", "A5": "Al2", "A6": "Al2",
        "A7": "Al3", "A8": "Al3",
        "E1": "Es1", "E2": "Es1",
    }
    r4 = evaluer(s, groupes4, aff4, compat=compat4)
    assert r4.criteres["f2"] == 4.0
    assert r4.normalises["f2"] == 1.0
    assert r4.criteres["f1"] == 0.5
    assert r4.normalises["f1"] == 1.0
    assert r4.score == 0.0

    groupes5 = {"Al1": 5, "Al2": 5, "Al3": 5, "Es1": 5, "Es2": 5}
    compat5 = {
        e: (["Al1", "Al2", "Al3"] if s[e] == "Allemand" else ["Es1"])
        for e in s
    }
    r5 = evaluer(s, groupes5, aff1, compat=compat5)
    assert r5.criteres["f2"] == 3.0
    assert r5.detail["f2_min"] == 3
    assert r5.detail["f2_max"] == 4  # Es2 n'est compatible avec personne
    assert r5.detail["f2_bornes_blocs"] == {
        "Allemand": {"min": 2, "max": 3},
        "Espagnol": {"min": 1, "max": 1},
    }

    r_poids = evaluer(
        s, groupes4, aff1, compat=compat4,
        poids={"f1": 1.0, "f2": 0.0, "f3": 0.0},
    )
    assert r_poids.poids == {"f1": 1.0, "f2": 0.0, "f3": 0.0}
    assert r_poids.score == 1.0

    for mauvais in (
        {"f4": 1.0},
        {"f1": -1.0},
        {"f1": 0.0, "f2": 0.0, "f3": 0.0},
    ):
        try:
            evaluer(s, groupes4, aff1, compat=compat4, poids=mauvais)
        except ValueError:
            pass
        else:
            raise AssertionError(f"poids accepté: {mauvais}")

    print("3/7 f2 et poids OK (bornes par bloc, renormalisation, poids invalides rejetés)")


def test_f3_inactif():
    s, groupes, compat, aff1, _ = exemple_pdf()
    r = evaluer(s, groupes, aff1, compat=compat)
    assert r.criteres["f3"] == 0.0
    assert r.normalises["f3"] == 0.0
    assert r.poids["f3"] == 0.0
    assert "f3" not in r.detail["criteres_actifs"]
    print("4/7 f3 nul et désactivé en LV2 OK")


def test_blocs():
    s, groupes, compat, aff1, _ = exemple_pdf()

    blocs = {"Al1": "Allemand", "Al2": "Allemand", "Es1": "Espagnol"}
    r = evaluer(s, groupes, aff1, compat=compat, blocs=blocs)
    assert r.faisable and r.score == 1.0
    assert r.detail["blocs"] == blocs

    r_infere = evaluer(s, groupes, aff1, compat=compat)
    assert r_infere.detail["blocs"] == blocs

    compat_ambigu = {e: ["Al1", "Al2", "Es1"] for e in s}
    try:
        evaluer(s, groupes, aff1, compat=compat_ambigu)
    except ValueError:
        pass
    else:
        raise AssertionError("ambiguïté de blocs non détectée")

    print("5/7 blocs OK (explicites, inférés, ambiguïté rejetée)")


def test_instance_generee():
    from generateur_instances import generer_instance
    from groupes import construire_groupes_lv2

    inst = generer_instance(
        n=80, seed=42, avec_cas_particuliers=False, frac_choix_tardif=0.0
    )
    s = {e.id: e.lv2 for e in inst.etudiants}
    groupes = {g.nom: g.capacite for g in construire_groupes_lv2(inst)}
    compat = {
        e.id: [g for g in groupes if g.startswith(f"LV2_{e.lv2}_")]
        for e in inst.etudiants
    }

    # Affectation équilibrée simple : chaque étudiant va au groupe le moins chargé.
    aff, eff = {}, {g: 0 for g in groupes}
    for e in inst.etudiants:
        g = min(compat[e.id], key=lambda nom: eff[nom])
        aff[e.id] = g
        eff[g] += 1

    r = evaluer(s, groupes, aff, compat=compat)
    assert r.faisable
    assert 0.0 < r.score <= 1.0
    assert r.normalises["f1"] < 1.0
    assert r.criteres["f2"] == len(groupes)
    assert r.detail["f2_min"] == len(groupes)
    assert r.detail["f2_max"] == len(groupes)
    assert r.normalises["f2"] == 0.0
    print("6/7 instance générée OK (n=80, score=%.3f)" % r.score)


def test_sans_compat():
    """Sans compat : un seul bloc global, comme pour les TP/TD du PDF."""
    s = {i: ("Allemand" if i <= 6 else "Espagnol") for i in range(1, 11)}
    groupes = {"TP1": 5, "TP2": 5}
    aff = {
        1: "TP1", 2: "TP1", 3: "TP1", 4: "TP1", 5: "TP1",
        6: "TP2", 7: "TP2", 8: "TP2", 9: "TP2", 10: "TP2",
    }
    r = evaluer(s, groupes, aff)
    assert r.faisable
    assert r.detail["blocs"] == {"TP1": "__global__", "TP2": "__global__"}
    assert r.criteres["f1"] == 0.0
    assert r.score == 1.0

    groupes3 = {"TP1": 5, "TP2": 5, "TP3": 5}
    aff3 = {
        1: "TP1", 2: "TP1", 3: "TP1", 4: "TP1",
        5: "TP2", 6: "TP2", 7: "TP2",
        8: "TP3", 9: "TP3", 10: "TP3",
    }
    r3 = evaluer(s, groupes3, aff3)
    assert abs(r3.criteres["f1"] - 0.4) < 1e-9
    # Le remplissage à la volée donne 5/5/0, donc f1_max = 0 : tout écart est
    # ramené à 1 par la convention de normalisation.
    assert r3.detail["f1_max"] == 0.0
    assert r3.normalises["f1"] == 1.0
    print("7/7 sans compat OK (bloc global, f1_max dégénéré)")


if __name__ == "__main__":
    test_exemple_pdf()
    test_contraintes_dures()
    test_f2_et_poids()
    test_f3_inactif()
    test_blocs()
    test_instance_generee()
    test_sans_compat()
    print("7/7 tests de l'évaluation passent")
