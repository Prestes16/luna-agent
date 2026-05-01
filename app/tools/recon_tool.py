"""
app/tools/recon_tool.py
─────────────────────────────────────────────────────────
Ferramenta de reconhecimento (OSINT & Surface Mapping)
Utiliza subfinder, httpx e gau para mapear o alvo.
"""

import subprocess
import json
import os
from pathlib import Path

def run_recon(target: str, output_dir: str = "recon_results") -> dict:
    """
    Executa um ciclo de reconhecimento no alvo.
    """
    os.makedirs(output_dir, exist_ok=True)
    results = {"target": target, "subdomains": [], "live_hosts": [], "urls": []}
    
    try:
        # 1. Subfinder (Subdomínios)
        sub_file = Path(output_dir) / f"{target}_subs.txt"
        subprocess.run(["subfinder", "-d", target, "-o", str(sub_file)], check=False, capture_output=True)
        if sub_file.exists():
            results["subdomains"] = sub_file.read_text().splitlines()
            
        # 2. Httpx (Hosts Ativos)
        if results["subdomains"]:
            live_file = Path(output_dir) / f"{target}_live.txt"
            subprocess.run(["httpx", "-l", str(sub_file), "-o", str(live_file), "-silent"], check=False, capture_output=True)
            if live_file.exists():
                results["live_hosts"] = live_file.read_text().splitlines()
                
        # 3. Gau (URLs Históricas)
        # Nota:gau pode ser lento, limitamos para fins de exemplo
        url_file = Path(output_dir) / f"{target}_urls.txt"
        subprocess.run(["gau", target, "--limit", "100", "-o", str(url_file)], check=False, capture_output=True)
        if url_file.exists():
            results["urls"] = url_file.read_text().splitlines()
            
        return {"ok": True, "results": results}
        
    except Exception as e:
        return {"ok": False, "error": str(e)}

if __name__ == "__main__":
    # Teste rápido
    import sys
    if len(sys.argv) > 1:
        print(json.dumps(run_recon(sys.argv[1]), indent=2))
