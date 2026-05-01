"""
app/tools/fuzz_tool.py
─────────────────────────────────────────────────────────
Ferramenta de fuzzing e busca de endpoints/parâmetros.
Utiliza ffuf e feroxbuster para descoberta de diretórios e arquivos.
"""

import subprocess
import json
import os
from pathlib import Path

def run_fuzz(target_url: str, wordlist: str = "common.txt", output_dir: str = "fuzz_results") -> dict:
    """
    Executa um ciclo de fuzzing no alvo.
    """
    os.makedirs(output_dir, exist_ok=True)
    results = {"target": target_url, "endpoints": [], "files": []}
    
    try:
        # 1. Ffuf (Fuzzing de Diretórios)
        # Nota: ffuf exige wordlist, usamos uma padrão se existir
        fuzz_file = Path(output_dir) / f"{target_url.replace('://', '_').replace('/', '_')}_fuzz.json"
        
        # Simulação de comando (requer ffuf instalado e wordlist configurada)
        cmd = ["ffuf", "-u", f"{target_url}/FUZZ", "-w", wordlist, "-o", str(fuzz_file), "-of", "json", "-silent"]
        
        # Executa com timeout curto para fins de exemplo
        try:
            subprocess.run(cmd, timeout=30, capture_output=True)
        except subprocess.TimeoutExpired:
            pass
            
        if fuzz_file.exists():
            with open(fuzz_file, "r") as f:
                data = json.load(f)
                results["endpoints"] = [r["url"] for r in data.get("results", []) if r.get("status", 0) == 200]
                
        # 2. Feroxbuster (Recursivo)
        # Feroxbuster é ótimo para descobrir estrutura de arquivos
        ferox_file = Path(output_dir) / f"{target_url.replace('://', '_').replace('/', '_')}_ferox.txt"
        cmd_ferox = ["feroxbuster", "-u", target_url, "-o", str(ferox_file), "-silent", "-n"]
        
        try:
            subprocess.run(cmd_ferox, timeout=30, capture_output=True)
        except subprocess.TimeoutExpired:
            pass
            
        if ferox_file.exists():
            results["files"] = ferox_file.read_text().splitlines()
            
        return {"ok": True, "results": results}
        
    except Exception as e:
        return {"ok": False, "error": str(e)}

if __name__ == "__main__":
    # Teste rápido
    import sys
    if len(sys.argv) > 1:
        print(json.dumps(run_fuzz(sys.argv[1]), indent=2))
