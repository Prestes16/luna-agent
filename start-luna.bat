@echo off
setlocal enabledelayedexpansion
title Luna Agent — Iniciando...

set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"

echo.
echo  ╔══════════════════════════════════════════╗
echo  ║   🌙  Luna Agent — Inicializando...      ║
echo  ╚══════════════════════════════════════════╝
echo.

REM ── Verificar pré-requisitos ──────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERRO] Python não encontrado. Instale Python 3.11+ em https://www.python.org/
    pause & exit /b 1
)

node --version >nul 2>&1
if errorlevel 1 (
    echo  [ERRO] Node.js não encontrado. Instale Node.js 18+ em https://nodejs.org/
    pause & exit /b 1
)

if not exist "%ROOT%\.env" (
    echo  [ERRO] .env não encontrado em %ROOT%
    echo  Configure o arquivo .env antes de iniciar.
    pause & exit /b 1
)

echo  [OK] Python, Node.js e .env encontrados
echo.

REM ── Ativar venv ───────────────────────────────────────────────────────────
if exist "%ROOT%\venv\Scripts\activate.bat" (
    call "%ROOT%\venv\Scripts\activate.bat"
) else (
    echo  [INFO] Criando venv...
    python -m venv "%ROOT%\venv"
    call "%ROOT%\venv\Scripts\activate.bat"
    echo  [INFO] Instalando dependências Python...
    pip install -r "%ROOT%\requirements.txt" -q
    echo  [OK] Dependências instaladas
)

REM ── Criar diretórios ──────────────────────────────────────────────────────
if not exist "%ROOT%\logs"       mkdir "%ROOT%\logs"
if not exist "%ROOT%\data"       mkdir "%ROOT%\data"
if not exist "%ROOT%\workspaces" mkdir "%ROOT%\workspaces"

REM ── Sincronizar token (lê do arquivo compartilhado com o Electron) ──────
set "TOKEN_FILE=%USERPROFILE%\.luna-agent\.api_token"
if exist "%TOKEN_FILE%" (
    set /p _SHARED_TOKEN=<"%TOKEN_FILE%"
    echo  [OK] Token compartilhado lido de %TOKEN_FILE%
) else (
    echo  [INFO] Token nao existe ainda — backend vai criá-lo no startup
)

REM ── Iniciar Backend numa nova janela ──────────────────────────────────────
echo  [1/2] Iniciando backend (FastAPI)...
start "Luna Backend" cmd /k "cd /d %ROOT% && call venv\Scripts\activate.bat && set PYTHONPATH=%ROOT% && set LUNA_API_TOKEN=%_SHARED_TOKEN% && uvicorn app.main:app --host 127.0.0.1 --port 8000"

REM ── Aguardar backend subir (3 segundos) ──────────────────────────────────
echo  [INFO] Aguardando backend inicializar...
timeout /t 3 /nobreak >nul

REM ── Instalar deps frontend se necessário ─────────────────────────────────
if not exist "%ROOT%\luna-desktop\node_modules" (
    echo  [INFO] Instalando dependências do frontend...
    cd /d "%ROOT%\luna-desktop"
    npm install -q
)

REM ── Iniciar Frontend numa nova janela ────────────────────────────────────
echo  [2/2] Iniciando frontend (Electron)...
start "Luna Desktop" cmd /k "cd /d %ROOT%\luna-desktop && npm run dev"

echo.
echo  ╔══════════════════════════════════════════════════════╗
echo  ║  ✅ Luna Agent iniciada!                              ║
echo  ║                                                       ║
echo  ║  Backend:  http://localhost:8000                      ║
echo  ║  API Docs: http://localhost:8000/docs                 ║
echo  ║                                                       ║
echo  ║  Feche as janelas "Luna Backend" e "Luna Desktop"     ║
echo  ║  para encerrar a aplicação.                           ║
echo  ╚══════════════════════════════════════════════════════╝
echo.
pause
endlocal
