# Tests CP-SAT - Projet 3A

Tests du modèle du compte-rendu (C1, C2, C3, f1).

```
pip install ortools
python test_cpsat.py
```

4 tests, ça finit par `4/4 tests passent` :

- l'équilibre des effectifs (OPTIMAL, 4/4/4)
- les capacités C(g) sur 24 étudiants
- 9 places pour 12 étudiants → INFEASIBLE
- le respect du choix de LV2 (C3)
