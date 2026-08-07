@echo off
cd /d "%~dp0"
python main.py
if errorlevel 1 (
    echo.
    echo   [ERREUR] L'outil n'a pas pu demarrer.
    echo   Lancez d'abord Test_pr_install.bat pour verifier l'environnement.
    pause
)
