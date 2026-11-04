"""Générateur d'instances synthétiques — Projet 3A, semaine 2.

Une instance ne contient QUE des étudiants (effectif 50..100), avec leur choix
de LV2, leur statut et l'indicateur de choix tardif. Ni groupe, ni affectation,
ni capacité : la construction des groupes vit dans `groupes.py`.

Les instances sont figées après création (dataclasses `frozen`) : on ne peut
plus modifier ni l'instance ni ses étudiants. L'historique global `HISTORIQUE`
permet en revanche d'ajouter et de retirer des instances.

Reproductibilité : chaque usage (n, distribution, étudiants, choix tardifs, cas
particuliers) dispose de son propre sous-flux dérivé de la graine maître. Une
instance de taille n n'est donc plus un préfixe d'une instance de taille n+1.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
from dataclasses import asdict, dataclass, replace

DISTRIBUTION_DEFAUT = {"Allemand": 0.45, "Espagnol": 0.20, "Autre": 0.35}
N_MIN, N_MAX = 50, 100
STATUTS = ("normal", "cesure", "redoublant")


# ---------------------------------------------------------------------------
# Sous-flux aléatoires indépendants
# ---------------------------------------------------------------------------
def _derive_seed(graine, *etiquettes):
    """Dérive une graine 64 bits stable (indépendante du hash Python)."""
    h = hashlib.blake2b(digest_size=8)
    h.update(str(graine).encode("utf-8"))
    for etiquette in etiquettes:
        h.update(b"\x1f")
        h.update(str(etiquette).encode("utf-8"))
    return int.from_bytes(h.digest(), "big")


def _rng(graine, *etiquettes):
    """RNG dédié à un usage précis : pas de flux partagé entre deux tirages."""
    return random.Random(_derive_seed(graine, *etiquettes))


def _poids_normale_tronquee(mu, sigma, lo=N_MIN, hi=N_MAX):
    """Poids exacts d'une normale discrète tronquée sur [lo, hi].

    P(k) ∝ Φ((k + 1/2 - μ)/σ) - Φ((k - 1/2 - μ)/σ), puis normalisation.
    Contrairement au clamp, aucun tirage n'est écrasé sur les bornes : on ne
    fabrique donc pas artificiellement un amas de n = 50.
    """
    if not math.isfinite(mu) or not math.isfinite(sigma):
        raise ValueError("mu et sigma doivent être finis")
    if sigma <= 0:
        raise ValueError("sigma doit être strictement positif")
    if hi < lo:
        raise ValueError("intervalle vide")
    racine2 = math.sqrt(2.0)

    def phi(x):
        return 0.5 * (1.0 + math.erf(x / racine2))

    poids = [
        max(0.0, phi((k + 0.5 - mu) / sigma) - phi((k - 0.5 - mu) / sigma))
        for k in range(lo, hi + 1)
    ]
    total = sum(poids)
    if total <= 0.0:
        raise ValueError("mu/sigma rendent la loi dégénérée hors de l'intervalle")
    return [p / total for p in poids]


def generer_n(mu=64.0, sigma=10.0, seed=None, index=0):
    """Effectif tiré dans [50,100] selon une normale tronquée discrète exacte."""
    if seed is None:
        seed = random.SystemRandom().randrange(2**63)
    rng = _rng(seed, "n", index)
    poids = _poids_normale_tronquee(mu, sigma)
    return rng.choices(range(N_MIN, N_MAX + 1), weights=poids, k=1)[0]


# ---------------------------------------------------------------------------
# Structures figées
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class Etudiant:
    id: int
    lv2: str
    choix_tardif: bool
    statut: str = "normal"

    def __post_init__(self):
        if self.statut not in STATUTS:
            raise ValueError(f"statut inconnu: {self.statut!r}")


@dataclass(frozen=True, slots=True, repr=False)
class Instance:
    """Instance figée : les étudiants et leurs attributs ne sont plus modifiables."""

    nom: str
    seed: int
    n: int
    distribution: tuple[tuple[str, float], ...]
    etudiants: tuple[Etudiant, ...]
    meta: tuple[tuple[str, object], ...] = ()

    def __post_init__(self):
        if len(self.etudiants) != self.n:
            raise ValueError(
                f"{self.nom}: n={self.n} mais {len(self.etudiants)} étudiants"
            )
        ids = [e.id for e in self.etudiants]
        if ids != list(range(1, self.n + 1)):
            raise ValueError(f"{self.nom}: ids attendus 1..{self.n}")

    def __repr__(self):
        return (
            f"Instance(nom={self.nom!r}, n={self.n}, seed={self.seed}, "
            f"repartition_lv2={self.repartition_lv2!r})"
        )

    @property
    def effectif(self):
        return len(self.etudiants)

    @property
    def repartition_lv2(self):
        rep = {}
        for e in self.etudiants:
            rep[e.lv2] = rep.get(e.lv2, 0) + 1
        return dict(sorted(rep.items()))

    @property
    def choix_tardifs(self):
        return sum(1 for e in self.etudiants if e.choix_tardif)

    @property
    def cas_particuliers(self):
        return tuple(sorted({e.statut for e in self.etudiants} - {"normal"}))

    def resume(self):
        return {
            "nom": self.nom,
            "seed": self.seed,
            "effectif": self.effectif,
            "repartition_lv2": self.repartition_lv2,
            "choix_tardifs": self.choix_tardifs,
            "cas_particuliers": list(self.cas_particuliers),
            "meta": dict(self.meta),
        }

    def vers_dict(self):
        """Copie mutable de l'instance (l'instance elle-même reste figée)."""
        return {
            "nom": self.nom,
            "seed": self.seed,
            "n": self.n,
            "distribution": dict(self.distribution),
            "etudiants": [asdict(e) for e in self.etudiants],
            "meta": dict(self.meta),
        }

    def checksum(self):
        charge = json.dumps(
            self.vers_dict(), sort_keys=True, ensure_ascii=False, default=str
        )
        return hashlib.blake2b(charge.encode("utf-8"), digest_size=16).hexdigest()


# ---------------------------------------------------------------------------
# Génération d'étudiants (aucun groupe dans l'instance)
# ---------------------------------------------------------------------------
def _normaliser_distribution(distribution):
    if not distribution:
        raise ValueError("distribution vide")
    dist = {}
    for langue, poids in distribution.items():
        if not isinstance(langue, str):
            raise TypeError("les langues doivent être des chaînes")
        poids = float(poids)
        if not math.isfinite(poids) or poids < 0:
            raise ValueError(f"poids invalide pour {langue!r}: {poids!r}")
        dist[langue] = poids
    total = sum(dist.values())
    if total <= 0:
        raise ValueError("la distribution doit avoir une somme > 0")
    return {langue: poids / total for langue, poids in dist.items()}


def _verifier_repartition(repartition, n):
    if not repartition:
        raise ValueError("repartition vide")
    total = 0
    for langue, cnt in repartition.items():
        if not isinstance(langue, str):
            raise TypeError("les langues doivent être des chaînes")
        if not isinstance(cnt, int) or isinstance(cnt, bool) or cnt < 0:
            raise ValueError(f"effectif invalide pour {langue!r}: {cnt!r}")
        total += cnt
    if total != n:
        raise ValueError(f"repartition: total {total} != n {n}")


def generer_instance(
    n=80,
    seed=42,
    distribution=None,
    repartition=None,
    frac_choix_tardif=0.15,
    avec_cas_particuliers=True,
    nom=None,
    index=0,
):
    """Retourne une `Instance` figée ne contenant que des étudiants.

    n                     : effectif, 50 <= n <= 100 (cadrage)
    seed                  : graine maître (None -> graine système, stockée)
    distribution          : probas de LV2 (normalisées), exclusif avec repartition
    repartition           : effectifs exacts par LV2, ex. {"Allemand": 49, "Espagnol": 1}
    frac_choix_tardif     : part de choix de LV2 faits le jour de la rentrée
    avec_cas_particuliers : césure + 4 redoublants à partir de n >= 60
    nom                   : nom de l'instance (défaut dérivé de n et seed)
    index                 : indice d'instance, pour des sous-flux indépendants
    """
    if not (N_MIN <= n <= N_MAX):
        raise ValueError(f"effectif attendu entre {N_MIN} et {N_MAX} (cadrage)")
    if not (0.0 <= frac_choix_tardif <= 1.0):
        raise ValueError("frac_choix_tardif doit être dans [0, 1]")
    if distribution is not None and repartition is not None:
        raise ValueError("distribution et repartition sont exclusifs")
    if seed is None:
        seed = random.SystemRandom().randrange(2**63)

    if repartition is not None:
        _verifier_repartition(repartition, n)
        repartition = dict(repartition)
        dist_effectif = {langue: cnt / n for langue, cnt in repartition.items()}
        choix = [langue for langue, cnt in repartition.items() for _ in range(cnt)]
        rng_etudiants = _rng(seed, "etudiants", index, n)
        rng_etudiants.shuffle(choix)
        lv2_choix = choix
    else:
        source = DISTRIBUTION_DEFAUT if distribution is None else distribution
        dist_effectif = _normaliser_distribution(source)
        langues = list(dist_effectif)
        poids = [dist_effectif[langue] for langue in langues]
        rng_etudiants = _rng(seed, "etudiants", index, n)
        lv2_choix = rng_etudiants.choices(langues, weights=poids, k=n)

    rng_tardif = _rng(seed, "tardif", index, n)
    etudiants = [
        Etudiant(
            id=i,
            lv2=lv2_choix[i - 1],
            choix_tardif=rng_tardif.random() < frac_choix_tardif,
        )
        for i in range(1, n + 1)
    ]

    if avec_cas_particuliers and n >= 60:
        rng_cas = _rng(seed, "cas", index, n)
        etudiants[-1] = replace(etudiants[-1], statut="cesure")
        for j in rng_cas.sample(range(n - 1), 4):
            etudiants[j] = replace(etudiants[j], statut="redoublant")

    if nom is None:
        nom = f"inst_n{n}_seed{seed}"

    return Instance(
        nom=nom,
        seed=seed,
        n=n,
        distribution=tuple(sorted(dist_effectif.items())),
        etudiants=tuple(etudiants),
    )


def generer_lot(nb=10, seed=42, mu=64.0, sigma=10.0):
    """Jeu étendu : n ~ N(mu, sigma) tronquée [50,100], parts LV2 bruitées.

    Chaque instance reçoit une graine maître dérivée de (seed, "lot", i), puis
    ses propres sous-flux. Deux instances du lot sont donc indépendantes, et
    une instance de lot ne coïncide pas avec un appel unitaire de même graine.
    """
    lot = []
    for i in range(nb):
        graine_i = _derive_seed(seed, "lot", i)
        n = generer_n(mu=mu, sigma=sigma, seed=graine_i)
        rng_dist = _rng(graine_i, "distribution")
        dist = {
            langue: max(0.05, valeur + rng_dist.normalvariate(0.0, 0.05))
            for langue, valeur in DISTRIBUTION_DEFAUT.items()
        }
        somme = sum(dist.values())
        dist = {langue: v / somme for langue, v in dist.items()}
        lot.append(
            generer_instance(
                n=n,
                seed=graine_i,
                distribution=dist,
                nom=f"lot_{seed}_{i:03d}",
            )
        )
    return tuple(lot)


# ---------------------------------------------------------------------------
# Instances extrêmes (bornes, distributions dégénérées, saturation capacité)
# ---------------------------------------------------------------------------
def _avec_meta_extreme(instance, categorie, note):
    """Ajoute une catégorie et une note ; aucune capacité dans l'instance."""
    meta = (("categorie", categorie), ("note", note))
    return replace(instance, meta=meta)


def generer_instances_extremes(seed=0):
    """Instances extrêmes pour tester les limites.

    Couvre les bornes de cadrage, les distributions dégénérées et la saturation
    des capacités. Toutes les instances sont "propres" : aucun cas particulier,
    aucun choix tardif, effectifs exacts par LV2. Chaque instance porte dans
    `meta` sa catégorie et une note ; les attendus (k_min, f1) sont calculés
    par les tests via `groupes.k_min_lv2` / `groupes.f1_attendu_lv2`.
    """
    extremes = []

    for n in (N_MIN, N_MAX):
        inst = generer_instance(
            n=n,
            seed=seed,
            avec_cas_particuliers=False,
            frac_choix_tardif=0.0,
            nom=f"extreme_borne_n{n}",
        )
        extremes.append(_avec_meta_extreme(inst, "borne", f"borne de cadrage n={n}"))

    inst = generer_instance(
        n=80,
        seed=seed,
        repartition={"Allemand": 80},
        avec_cas_particuliers=False,
        frac_choix_tardif=0.0,
        nom="extreme_une_langue_n80",
    )
    extremes.append(_avec_meta_extreme(inst, "distribution", "100 % Allemand"))

    inst = generer_instance(
        n=80,
        seed=seed,
        repartition={"Allemand": 40, "Espagnol": 40},
        avec_cas_particuliers=False,
        frac_choix_tardif=0.0,
        nom="extreme_deux_langues_n80",
    )
    extremes.append(
        _avec_meta_extreme(inst, "distribution", "50/50 Allemand/Espagnol")
    )

    inst = generer_instance(
        n=50,
        seed=seed,
        repartition={"Allemand": 49, "Espagnol": 1},
        avec_cas_particuliers=False,
        frac_choix_tardif=0.0,
        nom="extreme_minorite_n50",
    )
    extremes.append(
        _avec_meta_extreme(
            inst,
            "distribution",
            "49 Allemand + 1 Espagnol : un groupe entier pour un seul étudiant",
        )
    )

    inst = generer_instance(
        n=72,
        seed=seed,
        repartition={"Allemand": 72},
        avec_cas_particuliers=False,
        frac_choix_tardif=0.0,
        nom="extreme_capacite_pile_n72",
    )
    extremes.append(
        _avec_meta_extreme(
            inst, "capacite", "72 = 3 x 24 : trois groupes exactement pleins"
        )
    )

    inst = generer_instance(
        n=73,
        seed=seed,
        repartition={"Allemand": 73},
        avec_cas_particuliers=False,
        frac_choix_tardif=0.0,
        nom="extreme_capacite_depassee_n73",
    )
    extremes.append(
        _avec_meta_extreme(
            inst, "capacite", "73 = 3 x 24 + 1 : k=3 infaisable, k=4 nécessaire"
        )
    )

    return tuple(extremes)


# ---------------------------------------------------------------------------
# Historique global
# ---------------------------------------------------------------------------
class Historique:
    """Registre global d'instances figées.

    Les instances ne peuvent pas être modifiées, mais on peut les ajouter et
    les retirer : c'est un historique, pas un ensemble immuable.
    """

    def __init__(self):
        self._instances = {}

    def ajouter(self, instance, remplacer=False):
        if not isinstance(instance, Instance):
            raise TypeError("attendu: Instance")
        if instance.nom in self._instances and not remplacer:
            raise ValueError(f"instance déjà présente: {instance.nom}")
        self._instances[instance.nom] = instance
        return instance

    def retirer(self, nom_ou_instance):
        nom = (
            nom_ou_instance.nom
            if isinstance(nom_ou_instance, Instance)
            else nom_ou_instance
        )
        if nom not in self._instances:
            raise KeyError(nom)
        return self._instances.pop(nom)

    def obtenir(self, nom):
        return self._instances[nom]

    def lister(self):
        return tuple(self._instances.values())

    def vider(self):
        self._instances.clear()

    def tableau(self):
        """Vue synthétique de l'historique (une ligne par instance)."""
        return [instance.resume() for instance in self._instances.values()]

    def tableau_etudiants(self):
        """Vue détaillée : une ligne par étudiant, toutes instances confondues."""
        lignes = []
        for instance in self._instances.values():
            for e in instance.etudiants:
                lignes.append(
                    {
                        "instance": instance.nom,
                        "seed": instance.seed,
                        "n": instance.n,
                        "id": e.id,
                        "lv2": e.lv2,
                        "choix_tardif": e.choix_tardif,
                        "statut": e.statut,
                    }
                )
        return lignes

    def __len__(self):
        return len(self._instances)

    def __iter__(self):
        return iter(self._instances.values())

    def __contains__(self, nom):
        return nom in self._instances

    def __getitem__(self, nom):
        return self._instances[nom]


HISTORIQUE = Historique()


def resume(instance):
    """Synthèse d'une instance (compatibilité avec l'ancien nom)."""
    if not isinstance(instance, Instance):
        raise TypeError("attendu: Instance")
    return instance.resume()


# ---------------------------------------------------------------------------
# Démonstration
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    for n in (N_MIN, 75, N_MAX):
        inst = generer_instance(n=n, seed=42)
        print("n=%3d ->" % n, json.dumps(inst.resume(), ensure_ascii=False))

    inst = generer_instance()  # instance de référence (n = 80)
    print("\ninstance de référence n=80 :")
    print(json.dumps(inst.resume(), ensure_ascii=False, indent=2))

    lot = generer_lot(20, seed=7)  # jeu étendu : loi normale mu=64, sigma=10
    ns = [i.n for i in lot]
    print("\njeu étendu (20 instances, N(64,10) tronquée [50,100]) :")
    print("n: min=%d max=%d moyenne=%.1f" % (min(ns), max(ns), sum(ns) / len(ns)))

    print("\ninstances extrêmes :")
    for inst in generer_instances_extremes(seed=0):
        meta = dict(inst.meta)
        print(
            "  %-32s n=%3d categorie=%s"
            % (inst.nom, inst.n, meta["categorie"])
        )

    print("\nhistorique (3 premières instances du lot) :")
    for inst in lot[:3]:
        HISTORIQUE.ajouter(inst)
    print("  %d instance(s)" % len(HISTORIQUE))
    for ligne in HISTORIQUE.tableau():
        print("   ", json.dumps(ligne, ensure_ascii=False))
    print("  %d ligne(s) étudiant" % len(HISTORIQUE.tableau_etudiants()))