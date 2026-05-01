#!/usr/bin/env python3
"""
Luna Agent v2.0 - Setup Universal
Script de configuração que funciona em Windows, Linux e macOS
"""

import os
import sys
import subprocess
import platform
from pathlib import Path


class Colors:
    """Cores para terminal"""
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    RESET = '\033[0m'
    
    @staticmethod
    def disable_on_windows():
        if platform.system() == 'Windows':
            Colors.GREEN = ''
            Colors.YELLOW = ''
            Colors.RED = ''
            Colors.RESET = ''


def print_header():
    """Imprimir cabeçalho"""
    print(f"\n{Colors.YELLOW}🌙 Luna Agent v2.0 - Setup Automático{Colors.RESET}")
    print("=" * 50)
    print()


def check_python():
    """Verificar versão do Python"""
    print(f"{Colors.YELLOW}[1/5]{Colors.RESET} Verificando Python...")
    
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 11):
        print(f"{Colors.RED}✗ Python 3.11+ necessário (você tem {version.major}.{version.minor}){Colors.RESET}")
        sys.exit(1)
    
    print(f"{Colors.GREEN}✓ Python {version.major}.{version.minor}.{version.micro} encontrado{Colors.RESET}")
    print()


def create_venv():
    """Criar ambiente virtual"""
    print(f"{Colors.YELLOW}[2/5]{Colors.RESET} Configurando ambiente virtual...")
    
    venv_path = Path('venv')
    if venv_path.exists():
        print(f"{Colors.GREEN}✓ Ambiente virtual já existe{Colors.RESET}")
    else:
        try:
            subprocess.run([sys.executable, '-m', 'venv', 'venv'], check=True)
            print(f"{Colors.GREEN}✓ Ambiente virtual criado{Colors.RESET}")
        except subprocess.CalledProcessError:
            print(f"{Colors.RED}✗ Erro ao criar ambiente virtual{Colors.RESET}")
            sys.exit(1)
    
    print()


def install_dependencies():
    """Instalar dependências"""
    print(f"{Colors.YELLOW}[3/5]{Colors.RESET} Instalando dependências...")
    
    # Determinar pip
    if platform.system() == 'Windows':
        pip_cmd = 'venv\\Scripts\\pip'
    else:
        pip_cmd = 'venv/bin/pip'
    
    try:
        # Atualizar pip
        subprocess.run([pip_cmd, 'install', '--upgrade', 'pip'], 
                      capture_output=True, check=True)
        
        # Instalar requirements
        subprocess.run([pip_cmd, 'install', '-r', 'requirements.txt'], 
                      capture_output=True, check=True)
        
        print(f"{Colors.GREEN}✓ Dependências instaladas{Colors.RESET}")
    except subprocess.CalledProcessError as e:
        print(f"{Colors.RED}✗ Erro ao instalar dependências: {e}{Colors.RESET}")
        sys.exit(1)
    
    print()


def create_directories():
    """Criar diretórios necessários"""
    print(f"{Colors.YELLOW}[4/5]{Colors.RESET} Criando diretórios...")
    
    dirs = ['logs', 'data', 'workspaces']
    for dir_name in dirs:
        Path(dir_name).mkdir(exist_ok=True)
    
    print(f"{Colors.GREEN}✓ Diretórios criados{Colors.RESET}")
    print()


def print_next_steps():
    """Imprimir próximos passos"""
    print("=" * 50)
    print(f"{Colors.GREEN}✓ Setup concluído com sucesso!{Colors.RESET}")
    print()
    print("Para iniciar a Luna Agent, execute:")
    print()
    
    if platform.system() == 'Windows':
        print(f"{Colors.YELLOW}venv\\Scripts\\activate{Colors.RESET}")
    else:
        print(f"{Colors.YELLOW}source venv/bin/activate{Colors.RESET}")
    
    print(f"{Colors.YELLOW}python run_luna.py{Colors.RESET}")
    print()


def main():
    """Executar setup"""
    Colors.disable_on_windows()
    
    print_header()
    check_python()
    create_venv()
    install_dependencies()
    create_directories()
    print_next_steps()


if __name__ == '__main__':
    main()
