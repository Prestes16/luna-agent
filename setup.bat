@echo off
REM Luna Agent v2.0 - Setup Script (Windows)
REM Este script configura e executa a Luna Agent automaticamente

setlocal enabledelayedexpansion

echo.
echo 🌙 Luna Agent v2.0 - Setup Automático
echo ======================================
echo.

REM Verificar Python
echo [1/5] Verificando Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo ✗ Python não encontrado!
    echo Por favor, instale Python 3.11 ou superior
    echo Baixe em: https://www.python.org/downloads/
    pause
    exit /b 1
)

for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
echo ✓ Python %PYTHON_VERSION% encontrado
echo.

REM Criar venv se não existir
echo [2/5] Configurando ambiente virtual...
if not exist "venv" (
    python -m venv venv
    echo ✓ Ambiente virtual criado
) else (
    echo ✓ Ambiente virtual já existe
)
echo.

REM Ativar venv
echo [3/5] Ativando ambiente virtual...
call venv\Scripts\activate.bat
echo ✓ Ambiente virtual ativado
echo.

REM Instalar dependências
echo [4/5] Instalando dependências...
python -m pip install --upgrade pip >nul 2>&1
pip install -r requirements.txt >nul 2>&1
if errorlevel 1 (
    echo ✗ Erro ao instalar dependências
    pause
    exit /b 1
)
echo ✓ Dependências instaladas
echo.

REM Criar diretórios necessários
echo [5/5] Criando diretórios...
if not exist "logs" mkdir logs
if not exist "data" mkdir data
if not exist "workspaces" mkdir workspaces
echo ✓ Diretórios criados
echo.

echo ======================================
echo ✓ Setup concluído com sucesso!
echo.
echo Para iniciar a Luna Agent, execute:
echo venv\Scripts\activate
echo python run_luna.py
echo.
pause
