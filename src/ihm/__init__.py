"""Interface graphique Tkinter de l'application d'affectation de groupes.

L'application est lancée par ``python app.py`` à la racine du projet, ou par
l'exécutable généré par ``build.bat`` (PyInstaller --onedir).

Les modules de ce paquet réutilisent le code existant :

* ``generateur_instances`` pour les données (saisie, import, génération) ;
* ``test_cpsat.resoudre`` pour le solveur CP-SAT ;
* ``export_csv`` pour l'écriture des trois CSV.
"""
