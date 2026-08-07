@echo off
cd /d "%~dp0"

:: ============================================================
:: PYTHON_EXE : chemin vers python.exe à utiliser.
:: Si vous avez plusieurs installations Python (QGIS, TELEMAC,
:: Python standard...), remplacez "python" par le chemin complet
:: vers le bon interpréteur, par exemple :
::   SET PYTHON_EXE=C:\Python312\python.exe
::   SET PYTHON_EXE=C:\Users\mon_login\AppData\Local\Programs\Python\Python312\python.exe
:: ============================================================
SET PYTHON_EXE=python

"%PYTHON_EXE%" Test_pr_install.py
pause
