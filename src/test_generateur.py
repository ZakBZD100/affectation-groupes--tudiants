"""Tests du générateur d'instances — graines, loi de n, immuabilité, extrêmes.

Exécution :
    python src/test_generateur.py

Les tests 1 à 5 ne dépendent pas d'OR-Tools ; le test 6 vérifie les instances
extrêmes avec le modèle CP-SAT de `test_cpsat.py`. Les groupes et les attendus
(k_min, f1) viennent de `groupes.py`, pas du générateur.
"""
import os
import sys
from dataclasses import FrozenInstanceError

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from generateur_instances import (
    HISTORIQUE,
    Etudiant,
    generer_instance,
    generer_instances_extremes,
    generer_n,
)
from groupes import (
    CAPACITES_DEFAUT,
    construire_groupes,
    construire_groupes_lv2,
    f1_attendu_lv2,
    k_min_lv2,
)


def prep(inst, capacite=24):
    """Instance -> (s, groupes, compat) pour le solveur, étudiants normaux seuls."""
    actifs = [e for e in inst.etudiants if e.statut == "normal"]
    s = {e.id: e.lv2 for e in actifs}
    groupes = {
        g.nom: g.capacite for g in construire_groupes_lv2(inst, capacite)
    }
    compat = {
        e.id: [nom for nom in groupes if nom.startswith(f"LV2_{e.lv2}_")]
        for e in actifs
    }
    return s, groupes, compat


def test_contrat_generateur():
    # 1. L'instance ne contient que des étudiants : ni groupe, ni affectation,
    #    ni capacité. Les groupes sont fournis par un helper séparé.
    inst = generer_instance(n=80, seed=42)
    champs = set(inst.__dataclass_fields__)
    assert "etudiants" in champs
    assert champs.isdisjoint({"groupes", "affectation", "capacite", "capacites"})
    assert all(isinstance(e, Etudiant) for e in inst.etudiants)
    assert all(e.lv2 and e.statut for e in inst.etudiants)

    # 2. Effectif borné à [50, 100].
    for n in (50, 75, 100):
        assert generer_instance(n=n, seed=1).n == n
    for mauvais in (49, 101):
        try:
            generer_instance(n=mauvais)
        except ValueError:
            pass
        else:
            raise AssertionError(f"n={mauvais} accepté")

    # 3. Cas particuliers : aucun à n=50, 1 césure + 4 redoublants dès n>=60.
    sans = generer_instance(n=50, seed=1)
    assert sans.cas_particuliers == ()
    avec = generer_instance(n=80, seed=1)
    statuts = [e.statut for e in avec.etudiants]
    assert statuts.count("cesure") == 1
    assert statuts.count("redoublant") == 4
    assert avec.cas_particuliers == ("cesure", "redoublant")

    # 4. Les groupes vivent dans un module séparé, hors instance.
    import groupes as module_groupes

    assert not hasattr(inst, "groupes")
    assert "construire_groupes" not in vars(__import__("generateur_instances"))
    assert callable(construire_groupes)
    assert construire_groupes(inst)
    assert module_groupes.CAPACITES_DEFAUT == CAPACITES_DEFAUT

    # 5. Aucune capacité dans les métadonnées des instances extrêmes.
    for extreme in generer_instances_extremes(seed=0):
        cles = {cle for cle, _ in extreme.meta}
        assert cles == {"categorie", "note"}, (extreme.nom, cles)

    # 6. Historique : un résumé par instance + une ligne par étudiant.
    HISTORIQUE.vider()
    a = generer_instance(n=50, seed=1, nom="a")
    b = generer_instance(n=60, seed=2, nom="b")
    HISTORIQUE.ajouter(a)
    HISTORIQUE.ajouter(b)
    lignes = HISTORIQUE.tableau()
    assert [ligne["nom"] for ligne in lignes] == ["a", "b"]
    assert all("effectif" in ligne and "repartition_lv2" in ligne for ligne in lignes)

    detail = HISTORIQUE.tableau_etudiants()
    assert len(detail) == a.n + b.n
    assert {ligne["instance"] for ligne in detail} == {"a", "b"}
    assert all(
        set(ligne) == {"instance", "seed", "n", "id", "lv2", "choix_tardif", "statut"}
        for ligne in detail
    )
    assert [ligne["id"] for ligne in detail if ligne["instance"] == "a"] == list(
        range(1, a.n + 1)
    )
    HISTORIQUE.vider()
    print("1/6 contrat du générateur OK (étudiants seuls, bornes, cas, tableaux)")


def test_reproductibilite_et_non_emboitement():
    a = generer_instance(n=50, seed=42)
    b = generer_instance(n=50, seed=42)
    assert [e.lv2 for e in a.etudiants] == [e.lv2 for e in b.etudiants]

    grand = generer_instance(n=100, seed=42)
    prefixe = [e.lv2 for e in grand.etudiants[:50]]
    assert [e.lv2 for e in a.etudiants] != prefixe, "instances encore emboîtées"
    print("2/6 reproductibilité OK, n=50 n'est plus un préfixe de n=100")


def test_loi_n_tronquee():
    tirages = [generer_n(seed=s) for s in range(20000)]
    assert min(tirages) == 50 and max(tirages) == 100
    part_50 = tirages.count(50) / len(tirages)
    assert part_50 < 0.03, f"trop de n=50: {part_50:.3f}"
    moyenne = sum(tirages) / len(tirages)
    assert 62 <= moyenne <= 66, moyenne
    print("3/6 loi de n OK : P(n=50)=%.3f, moyenne=%.2f" % (part_50, moyenne))


def test_instances_figees():
    inst = generer_instance(n=50, seed=1)
    try:
        inst.n = 51
    except FrozenInstanceError:
        pass
    else:
        raise AssertionError("Instance modifiable")

    try:
        inst.etudiants[0].lv2 = "Autre"
    except FrozenInstanceError:
        pass
    else:
        raise AssertionError("Etudiant modifiable")
    print("4/6 instances figées OK")


def test_historique():
    HISTORIQUE.vider()
    a = generer_instance(n=50, seed=1, nom="a")
    b = generer_instance(n=51, seed=2, nom="b")
    HISTORIQUE.ajouter(a)
    HISTORIQUE.ajouter(b)
    assert len(HISTORIQUE) == 2
    assert HISTORIQUE.obtenir("a") is a
    assert [i.nom for i in HISTORIQUE.lister()] == ["a", "b"]

    try:
        HISTORIQUE.ajouter(a)
    except ValueError:
        pass
    else:
        raise AssertionError("doublon accepté")

    HISTORIQUE.retirer("a")
    assert "a" not in HISTORIQUE and len(HISTORIQUE) == 1
    HISTORIQUE.vider()
    print("5/6 historique OK (ajout, retrait, doublon refusé)")


def test_extremes():
    from ortools.sat.python import cp_model
    from test_cpsat import resoudre

    for inst in generer_instances_extremes(seed=0):
        meta = dict(inst.meta)
        assert set(meta) == {"categorie", "note"}, (inst.nom, set(meta))
        s, groupes, compat = prep(inst)
        k_min = k_min_lv2(inst)
        f1_attendu, k_calcule = f1_attendu_lv2(inst)
        assert k_calcule == k_min, (inst.nom, k_calcule, k_min)

        statut, aff, eff, ind = resoudre(s, groupes, k=k_min, compat=compat)
        assert statut in (cp_model.OPTIMAL, cp_model.FEASIBLE), (inst.nom, statut)
        assert len(aff) == len(s), inst.nom
        assert ind["f1"] == f1_attendu, (inst.nom, ind["f1"], f1_attendu)
        assert ind["k"] == k_min, (inst.nom, ind["k"], k_min)

        statut, _, _, _ = resoudre(s, groupes, k=k_min - 1, compat=compat)
        assert statut == cp_model.INFEASIBLE, (inst.nom, k_min - 1, statut)
        print(
            "6/6 %-32s n=%3d k_min=%d f1=%d OK"
            % (inst.nom, inst.n, k_min, f1_attendu)
        )


if __name__ == "__main__":
    test_contrat_generateur()
    test_reproductibilite_et_non_emboitement()
    test_loi_n_tronquee()
    test_instances_figees()
    test_historique()
    test_extremes()
    print("6/6 tests du générateur passent")
