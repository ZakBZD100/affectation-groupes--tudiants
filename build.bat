@echo off
setlocal
cd /d "%~dp0"

python -m PyInstaller --version >nul 2>nul
if errorlevel 1 (
    echo Installation de PyInstaller...
    python -m pip install pyinstaller
    if errorlevel 1 goto :erreur
)

echo Construction de l'application (dossier avec executable + DLL)...
python -m PyInstaller --noconfirm --onedir --clean ^
    --name AffectationGroupes ^
    --add-data "exports;exports" ^
    --paths src ^
    --hidden-import=ihm.app ^
    --collect-submodules ihm ^
    --collect-all ortools ^
    --collect-all google.protobuf ^
    --collect-all absl ^
    --hidden-import=tkinter ^
    app.py
if errorlevel 1 goto :erreur

echo.
echo Termine : dist\AffectationGroupes\AffectationGroupes.exe
echo Le dossier dist\AffectationGroupes est autonome : copiez-le tel quel.
endlocal
exit /b 0

:erreur
echo Echec de la construction.
endlocal
exit /b 1
