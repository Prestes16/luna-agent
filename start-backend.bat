@echo off
setlocal enabledelayedexpansion
title Luna Agent — Backend

set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"

echo.
echo  ==========================================
echo   🌙  Luna Agent — Backend (FastAPI)
echo  ==========================================
echo.

REM ── Verificar Python ──────────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERRO] Python não encontrado.
    echo  Instale Python 3.11+ em https://www.python.org/downloads/
    pause & exit /b 1
)

REM ── Ativar venv ───────────────────────────────────────────────────────────
if exist "%ROOT%\venv\Scripts\activate.bat" (
    call "%ROOT%\venv\Scripts\activate.bat"
    echo  [OK] venv ativada
) else (
    echo  [AVISO] venv não encontrada. Criando...
    python -m venv "%ROOT%\venv"
    call "%ROOT%\venv\Scripts\activate.bat"
    echo  [OK] venv criada e ativada
    echo  [INFO] Instalando dependências...
    pip install -r "%ROOT%\requirements.txt"
)

REM ── Verificar .env ────────────────────────────────────────────────────────
if not exist "%ROOT%\.env" (
    echo.
    echo  [AVISO] Arquivo .env não encontrado em: %ROOT%\.env
    echo  Copie o .env.example e configure suas chaves antes de continuar.
    echo.
    pause & exit /b 1
)

REM ── Criar diretórios necessários ──────────────────────────────────────────
if not exist "%ROOT%\logs"       mkdir "%ROOT%\logs"
if not exist "%ROOT%\data"       mkdir "%ROOT%\data"
if not exist "%ROOT%\workspaces" mkdir "%ROOT%\workspaces"

REM ── Sincronizar token com Electron ───────────────────────────────────────
REM Lê o token do mesmo arquivo que main.ts usa: %USERPROFILE%\.luna-agent\.api_token
REM Se não existir ainda, o backend vai criá-lo no startup — o Electron lerá na
REM próxima abertura. Para dev sem Electron basta rodar só o backend primeiro.
set "TOKEN_FILE=%USERPROFILE%\.luna-agent\.api_token"
if exist "%TOKEN_FILE%" (
    set /p _TOKEN=<"%TOKEN_FILE%"
    echo  [OK] Token lido de %TOKEN_FILE%
    set "LUNA_API_TOKEN=%_TOKEN%"
) else (
    echo  [INFO] Token ainda nao existe — backend vai gerar e persistir
)

REM ── Iniciar uvicorn ───────────────────────────────────────────────────────
echo.
echo  [INFO] Backend iniciando em http://localhost:8000
echo  [INFO] Docs em        http://localhost:8000/docs
echo  [INFO] Pressione Ctrl+C para parar
echo.

cd /d "%ROOT%"
set "PYTHONPATH=%ROOT%"
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

endlocal
pause
