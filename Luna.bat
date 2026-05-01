@echo off
setlocal
set "LUNA_ROOT=%~dp0"
set "PYTHONPATH=%LUNA_ROOT%"
echo [LUNA] Iniciando sistema operacional Luna...
cd /d "%LUNA_ROOT%"
python app/main.py
endlocal
