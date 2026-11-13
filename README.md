# Affectation des groupes — Projet 3A

Générateur d'instances, solveur CP-SAT multi-type (LV2, LV1, TP, TD),
évaluation de la fonction objectif et export des instances figées.

Le générateur ne produit **que des étudiants** : les groupes, leurs capacités
et la hiérarchie TP → TD vivent dans `src/groupes.py`, et le solveur choisit
lui-même le nombre de groupes ouverts `k(t)`.

## Prérequis

- Python 3.11+
- `ortools` pour le solveur et les scripts de comparaison :

```bash
pip install ortools
```

L'export ne demande aucune dépendance : ce sont des CSV UTF-8 avec BOM,
lisibles directement par Excel. `pandas`, `openpyxl` et `xlsxwriter` ne sont
pas nécessaires.

## Commandes et résultats attendus

### Tests

```bash
python test_cpsat.py
```

Modèle multi-type : C1 par type, C2, C3, C4 (TP → TD parent), C5a/C5b,
C6/C7, C8 (exactement 2 TP ouverts par TD ouvert), objectif pondéré
f1 + f2 + f3 avec les mêmes poids que l'évaluateur (1/3 chacun). Un test
dédié rejoue le solveur sur les quatre profils de capacités et deux variantes
aléatoires. Résultat attendu :

```
8/8 tests passent
```

```bash
python src/test_generateur.py
```

Contrat du générateur (étudiants seuls), reproductibilité, loi de `n`,
immuabilité, historique et instances extrêmes. Résultat attendu :

```
6/6 tests du générateur passent
```

```bash
python src/test_evaluation.py
```

Évaluation post-hoc (C1 à C4/C5a/C8, f1/f2/f3, normalisation, poids). Résultat
attendu :

```
7/7 tests de l'évaluation passent
```

```bash
python src/test_export.py
```

Contenu et en-têtes des CSV, BOM UTF-8, reproductibilité du lot. Résultat
attendu :

```
tests de l'export passent
```

### Export Excel (CSV)

```bash
python src/export_csv.py
```

Fige un lot reproductible de 20 instances (`seed=7`) plus les 7 instances
extrêmes dans l'historique global, puis écrit :

- `exports/instances.csv` — une ligne par instance (effectif, répartition
  LV2, choix tardifs, cas particuliers, catégorie) ;
- `exports/etudiants.csv` — une ligne par étudiant, toutes instances
  confondues.

Résultat attendu :

```
27 instance(s) figée(s), 1845 étudiant(s)
  -> .../exports/instances.csv
  -> .../exports/etudiants.csv
```

Options :

```bash
python src/export_csv.py --lot 30 --seed 11
python src/export_csv.py --sans-extremes
python src/export_csv.py --sortie C:\chemin\vers\sortie
```

### Expériences (27 instances)

```bash
python src/experiences.py
```

Rejoue greedy et CP-SAT sur les 27 instances figées, notés par le même juge,
puis écrit :

- `exports/resultats.csv` — une ligne par instance (`k` par type, f1 normalisé
  et score des deux méthodes, temps) ;
- `docs/instances_tables.tex` — les tableaux inclus dans `docs/instances.pdf`.

Le script calcule aussi la sensibilité aux poids (`w1`/`w2`) et compare avec
l'affectation réelle de septembre, lue dans le fichier local `donnees/`
(absent du dépôt).

### Banc d'essai

```bash
python src/banc_essai.py
```

Sensibilité au nombre de groupes ouverts : `k_min`, `k_min+1`, `k_min+2`,
avec un pool de deux groupes de réserve par langue. Résultat attendu : un
tableau A (k minimal) et un tableau B (sensibilité), par exemple :

```
moyenne : f1=1.0  f1_norm=0.060  maxmin=6.1

      k  infaisables   f1_moy    norm_moy  maxmin_moy
    +0         0/10      1.0       0.060         6.1
    +1         0/10      4.4       0.020         9.1
    +2         0/10      6.2       0.024        10.5
```

### Heuristique et comparaisons

```bash
python src/heuristique.py
python src/comparaison_s4.py
```

Comparent le greedy constructif au CP-SAT avec le même juge (`evaluer`). Le
CP-SAT reçoit l'affectation greedy comme point de départ (`hint`) et minimise
les trois critères : sur le jeu figé de 27 instances, il atteint ou dépasse le
greedy sur le score du juge (voir `exports/resultats.csv`). Le greedy apporte
la vitesse (≈ 2 ms), le CP-SAT l'optimisation (plafond de 10 s).

```bash
python src/comparaison_s3.py
```

Comparaison avec l'affectation réelle de septembre. Ce script exige le fichier
`donnees/CPB1 S1 2026-2027 - septembre - Projet 3A.grist`, absent du dépôt :
il échoue explicitement tant que la base n'est pas fournie.

### Démonstration du générateur

```bash
python src/generateur_instances.py
```

Affiche trois instances (n=50, 75, 100), le lot de 20 instances, les 7 cas
extrêmes et un extrait d'historique.

## Capacités et liberté du solveur

`src/groupes.py` ne contient plus de capacité par défaut cachée. Un profil est
toujours passé explicitement :

```python
from groupes import PROFILS_CAPACITES, construire_groupes

groupes = construire_groupes(instance, PROFILS_CAPACITES["standard"])
```

Profils fournis :

| Profil | LV2 | LV1 | TP | TD |
|---|---:|---:|---:|---:|
| `standard` | 24 | 24 | 16 | 40 |
| `serre` | 18 | 18 | 10 | 30 |
| `large` | 30 | 30 | 20 | 50 |
| `heterogene` | 24 | 16 | 12 | 40 |

`variantes_capacites(profil, n_variantes, amplitude, seed)` génère des
perturbations entières de ces profils pour tester le solveur sur des cas
variés.

Pour chaque bloc, le pool contient `ceil(N/C) + 1` groupes : le solveur peut
en ouvrir un de plus que le minimum si l'équilibre y gagne. Pour TP/TD, les
TD sont créés en nombre suffisant pour que deux TP par TD tiennent l'effectif,
puis chaque TD reçoit exactement deux enfants consécutifs. `k(t)` reste donc
une décision du modèle, pas une donnée.

## TP et TD

- Un TP a exactement un TD parent (C4 : `x(e, TP) ≤ x(e, TD parent)`).
- **C8 : un TD ouvert porte exactement 2 TP ouverts** (`TP_PAR_TD = 2`,
  constante dans `src/groupes.py`). Le pool propose `2 × #TD` TP, deux enfants
  consécutifs par TD ; c'est le solveur qui choisit quels TD ouvrir, jamais
  le générateur. L'évaluateur vérifie la même règle.
- `TD = 40` et `TP = 16` sont des capacités maximales `C(g)` (contrainte C2),
  pas des effectifs cibles.

## Structure du dépôt

```
test_cpsat.py                  solveur CP-SAT multi-type + 8 tests
src/generateur_instances.py    générateur (étudiants seuls) + historique
src/groupes.py                 profils de capacités, pool de groupes, TP/TD
src/evaluation.py              évaluation post-hoc f1/f2/f3 et contraintes
src/export_csv.py              export des instances figées en CSV
src/experiences.py             campagne greedy vs CP-SAT (CSV + tableaux)
src/test_generateur.py         tests du générateur
src/test_evaluation.py         tests de l'évaluation
src/test_export.py             tests de l'export
src/banc_essai.py              sensibilité au nombre de groupes
src/heuristique.py             greedy + comparaison CP-SAT
src/comparaison_s3.py          comparaison sur données réelles (.grist)
src/comparaison_s4.py          comparaison greedy / CP-SAT / réel
exports/resultats.csv          résultats des 27 instances (greedy vs CP-SAT)
docs/semaine2_formalisation.pdf  formalisation (C1–C8, f1–f3)
docs/instances.pdf             instances figées + analyse des expériences
docs/soutenance.pdf            diaporama de la soutenance mi-projet
```

Les sources LaTeX restent locales (`.gitignore`) : seuls les PDF sont poussés.
