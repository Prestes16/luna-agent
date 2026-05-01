"""
app/tools/solana_tool.py
─────────────────────────────────────────────────────────
Ferramenta de desenvolvimento e auditoria Solana/Anchor.
Executa comandos anchor, solana-verify e análise de segurança.
"""

import subprocess
import json
import os
from pathlib import Path

def run_solana_check(program_dir: str = ".") -> dict:
    """
    Executa um ciclo de verificação e auditoria no programa Solana.
    """
    results = {"program_dir": program_dir, "build": {}, "test": {}, "security": {}}
    
    try:
        # 1. Anchor Build (Compilação)
        build_proc = subprocess.run(["anchor", "build"], cwd=program_dir, capture_output=True, text=True, encoding="utf-8", errors="replace")
        results["build"] = {
            "ok": build_proc.returncode == 0,
            "stdout": build_proc.stdout[:500],
            "stderr": build_proc.stderr[:500]
        }
        
        # 2. Anchor Test (Testes)
        if results["build"]["ok"]:
            test_proc = subprocess.run(["anchor", "test"], cwd=program_dir, capture_output=True, text=True, encoding="utf-8", errors="replace")
            results["test"] = {
                "ok": test_proc.returncode == 0,
                "stdout": test_proc.stdout[:500],
                "stderr": test_proc.stderr[:500]
            }
            
        # 3. Solana Verify (Verificação de Deploy)
        verify_proc = subprocess.run(["solana-verify", "get-executable-hash", "target/deploy/program.so"], cwd=program_dir, capture_output=True, text=True, encoding="utf-8", errors="replace")
        results["security"]["hash"] = verify_proc.stdout.strip() if verify_proc.returncode == 0 else "N/A"
        
        # 4. Verificação de Constraints (Análise Estática Básica)
        # Procura por vulnerabilidades comuns em arquivos Rust
        rust_files = list(Path(program_dir).rglob("*.rs"))
        vulns = []
        for rf in rust_files:
            content = rf.read_text()
            if "is_signer" not in content and "Signer" not in content:
                vulns.append(f"Possível falta de verificação de assinatura em {rf.name}")
            if "checked_add" not in content and "checked_mul" not in content:
                vulns.append(f"Possível falta de matemática segura em {rf.name}")
        results["security"]["vulnerabilities"] = vulns
        
        return {"ok": True, "results": results}
        
    except Exception as e:
        return {"ok": False, "error": str(e)}

if __name__ == "__main__":
    # Teste rápido
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "."
    print(json.dumps(run_solana_check(path), indent=2))
