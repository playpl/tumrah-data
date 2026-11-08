@echo off
rem The data admin page: http://127.0.0.1:8770 (close this window to stop it)
cd /d "%~dp0"
start "" http://127.0.0.1:8770
py dm.py page
