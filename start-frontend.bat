@echo off
setlocal enabledelayedexpansion
title Luna Agent — Desktop (Electron)

set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"
set "FRONT=%ROOT%\luna-desktop"

echo.
echo  ==========================================
echo   🌙  Luna Agent — Desktop (Electron)
echo  ==========================================
echo.

REM ── Verificar Node.js ────────────────────────────────────────────────────
node --version >nul 2>&1
if errorlevel 1 (
    echo  [ERRO] Node.js não encontrado.
    echo  Instale Node.js 18+ em https://nodejs.org/
    pause & exit /b 1
)

REM ── Entrar na pasta do frontend ───────────────────────────────────────────
cd /d "%FRONT%"

REM ── Instalar dependências se necessário ───────────────────────────────────
if not exist "node_modules" (
    echo  [INFO] Instalando dependências do frontend (pode demorar)...
    npm install
    if errorlevel 1 (
        echo  [ERRO] Falha ao instalar dependências
        pause & exit /b 1
    )
)

REM ── Modo de execução ──────────────────────────────────────────────────────
REM   - dev:   hot reload (React + Electron ao mesmo tempo)  ← padrão
REM   - start: build estático e abre Electron (mais rápido para testar)
set "MODE=dev"
if "%1"=="prod"  set "MODE=start"
if "%1"=="start" set "MODE=start"

echo  [INFO] Modo: %MODE%
echo  [INFO] Backend esperado em http://localhost:8000
echo  [INFO] Pressione Ctrl+C para parar
echo.

if "%MODE%"=="dev" (
    npm run dev
) else (
    npm run start
)

endlocal
pause
