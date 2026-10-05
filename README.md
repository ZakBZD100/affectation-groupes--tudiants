# Tests CP-SAT - Projet 3A

Tests du modèle du compte-rendu (C1 à C7, f1).

```
pip install ortools
python test_cpsat.py
```

7 tests, ça finit par `7/7 tests passent` :

- l'équilibre des effectifs (OPTIMAL, 4/4/4, f1=0)
- les capacités C(g) sur 24 étudiants
- 9 places pour 12 étudiants → INFEASIBLE
- le respect du choix de LV2 (C3)
- 75 étudiants sur 5 TP (bornes du cadrage)
- k ouvertures imposées en dur (C5) → infaisable si trop juste
- indicateurs : 4/3/3, f1=fmin, normalisation à 0
