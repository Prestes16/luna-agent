"""
Luna Agent - Serviço de Memória
Memória de curto prazo (STM) + Memória de longo prazo (LTM) com Chroma.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional, Any
from datetime import datetime, timedelta

try:
    import chromadb
    from chromadb.config import Settings
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False


logger = logging.getLogger("luna.memory")


# ─────────────────────────────────────────────────────────────────────────
# Memória de Curto Prazo (STM)
# ─────────────────────────────────────────────────────────────────────────

_STM_STORE: dict[str, list[dict]] = {}


def stm_add(session_id: str, role: str, content: str, metadata: Optional[dict] = None) -> None:
    """Adicionar mensagem à memória de curto prazo."""
    if session_id not in _STM_STORE:
        _STM_STORE[session_id] = []
    
    entry = {
        "role": role,
        "content": content,
        "timestamp": datetime.utcnow().isoformat(),
        "metadata": metadata or {},
    }
    _STM_STORE[session_id].append(entry)
    
    # Manter apenas últimas 50 mensagens
    if len(_STM_STORE[session_id]) > 50:
        _STM_STORE[session_id] = _STM_STORE[session_id][-50:]


def stm_get(session_id: str, limit: int = 10) -> list[dict]:
    """Obter últimas mensagens da memória de curto prazo."""
    if session_id not in _STM_STORE:
        return []
    return _STM_STORE[session_id][-limit:]


def stm_clear(session_id: str) -> None:
    """Limpar memória de curto prazo de uma sessão."""
    if session_id in _STM_STORE:
        del _STM_STORE[session_id]


# ─────────────────────────────────────────────────────────────────────────
# Memória de Longo Prazo (LTM) com Chroma
# ─────────────────────────────────────────────────────────────────────────

class MemoryService:
    """Serviço de memória com Chroma."""
    
    def __init__(self, data_dir: str = "data/memory"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self.client = None
        self.collection = None
        
        if CHROMA_AVAILABLE:
            try:
                settings = Settings(
                    chroma_db_impl="duckdb+parquet",
                    persist_directory=str(self.data_dir),
                    anonymized_telemetry=False,
                )
                self.client = chromadb.Client(settings)
                self.collection = self.client.get_or_create_collection(
                    name="luna_memory",
                    metadata={"hnsw:space": "cosine"},
                )
                logger.info("Chroma inicializado com sucesso")
            except Exception as e:
                logger.warning(f"Erro ao inicializar Chroma: {e}. Usando fallback JSON.")
                self.client = None
        else:
            logger.warning("chromadb não disponível. Usando fallback JSON.")
        
        # Fallback: JSON file
        self.json_file = self.data_dir / "memory.jsonl"
    
    def add_memory(
        self,
        session_id: str,
        content: str,
        metadata: Optional[dict] = None,
        embedding: Optional[list[float]] = None,
    ) -> str:
        """Adicionar entrada à memória de longo prazo."""
        
        entry_id = f"{session_id}_{datetime.utcnow().timestamp()}"
        entry = {
            "id": entry_id,
            "session_id": session_id,
            "content": content,
            "metadata": metadata or {},
            "timestamp": datetime.utcnow().isoformat(),
        }
        
        if self.client and self.collection:
            try:
                self.collection.add(
                    ids=[entry_id],
                    documents=[content],
                    metadatas=[{"session_id": session_id, **(metadata or {})}],
                    embeddings=[embedding] if embedding else None,
                )
                logger.debug(f"Memória adicionada ao Chroma: {entry_id}")
            except Exception as e:
                logger.warning(f"Erro ao adicionar ao Chroma: {e}. Usando fallback.")
                self._save_to_json(entry)
        else:
            self._save_to_json(entry)
        
        return entry_id
    
    def search_memory(
        self,
        query: str,
        session_id: Optional[str] = None,
        limit: int = 5,
    ) -> list[dict]:
        """Buscar na memória de longo prazo."""
        
        if self.client and self.collection:
            try:
                where_filter = {"session_id": session_id} if session_id else None
                results = self.collection.query(
                    query_texts=[query],
                    n_results=limit,
                    where=where_filter,
                )
                
                memories = []
                for i, doc in enumerate(results["documents"][0]):
                    memories.append({
                        "content": doc,
                        "metadata": results["metadatas"][0][i],
                        "distance": results["distances"][0][i] if results["distances"] else 0,
                    })
                return memories
            except Exception as e:
                logger.warning(f"Erro ao buscar no Chroma: {e}. Usando fallback.")
                return self._search_json(query, session_id, limit)
        else:
            return self._search_json(query, session_id, limit)
    
    def get_session_memory(self, session_id: str, limit: int = 20) -> list[dict]:
        """Obter todas as memórias de uma sessão."""
        
        if self.client and self.collection:
            try:
                results = self.collection.get(
                    where={"session_id": session_id},
                    limit=limit,
                )
                
                memories = []
                for i, doc in enumerate(results["documents"]):
                    memories.append({
                        "id": results["ids"][i],
                        "content": doc,
                        "metadata": results["metadatas"][i],
                    })
                return memories
            except Exception as e:
                logger.warning(f"Erro ao obter memória da sessão: {e}")
                return self._get_session_json(session_id, limit)
        else:
            return self._get_session_json(session_id, limit)
    
    def clear_session_memory(self, session_id: str) -> None:
        """Limpar memória de uma sessão."""
        
        if self.client and self.collection:
            try:
                results = self.collection.get(where={"session_id": session_id})
                if results["ids"]:
                    self.collection.delete(ids=results["ids"])
                logger.info(f"Memória da sessão {session_id} limpa")
            except Exception as e:
                logger.warning(f"Erro ao limpar memória: {e}")
    
    # ─── Fallback JSON ───────────────────────────────────────────────────
    
    def _save_to_json(self, entry: dict) -> None:
        """Salvar entrada em arquivo JSON."""
        with open(self.json_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    
    def _search_json(
        self,
        query: str,
        session_id: Optional[str] = None,
        limit: int = 5,
    ) -> list[dict]:
        """Buscar em arquivo JSON (busca simples por substring)."""
        
        if not self.json_file.exists():
            return []
        
        query_lower = query.lower()
        results = []
        
        with open(self.json_file, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    
                    if session_id and entry.get("session_id") != session_id:
                        continue
                    
                    if query_lower in entry.get("content", "").lower():
                        results.append({
                            "content": entry.get("content", ""),
                            "metadata": entry.get("metadata", {}),
                        })
                except json.JSONDecodeError:
                    continue
        
        return results[:limit]
    
    def _get_session_json(self, session_id: str, limit: int = 20) -> list[dict]:
        """Obter memória de sessão do arquivo JSON."""
        
        if not self.json_file.exists():
            return []
        
        results = []
        
        with open(self.json_file, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    if entry.get("session_id") == session_id:
                        results.append(entry)
                except json.JSONDecodeError:
                    continue
        
        return results[-limit:]


# ─────────────────────────────────────────────────────────────────────────
# Instância Global
# ─────────────────────────────────────────────────────────────────────────

_memory_service: Optional[MemoryService] = None


def get_memory_service() -> MemoryService:
    """Obter instância global do serviço de memória."""
    global _memory_service
    if _memory_service is None:
        _memory_service = MemoryService()
    return _memory_service


def ltm_add(
    session_id: str,
    content: str,
    metadata: Optional[dict] = None,
) -> str:
    """Adicionar à memória de longo prazo."""
    service = get_memory_service()
    return service.add_memory(session_id, content, metadata)


def ltm_search(
    query: str,
    session_id: Optional[str] = None,
    limit: int = 5,
) -> list[dict]:
    """Buscar na memória de longo prazo."""
    service = get_memory_service()
    return service.search_memory(query, session_id, limit)


def ltm_get_session(session_id: str, limit: int = 20) -> list[dict]:
    """Obter memória de uma sessão."""
    service = get_memory_service()
    return service.get_session_memory(session_id, limit)


def ltm_clear_session(session_id: str) -> None:
    """Limpar memória de uma sessão."""
    service = get_memory_service()
    service.clear_session_memory(session_id)


# ─────────────────────────────────────────────────────────────────────────
# Facts — Memória de Fatos por Projeto (key-value persistido em JSON)
# ─────────────────────────────────────────────────────────────────────────

_FACTS_DIR = Path("data/facts")


def _facts_file(project: str) -> Path:
    _FACTS_DIR.mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in project)
    return _FACTS_DIR / f"{safe or 'default'}.json"


def _load_facts(project: str) -> dict[str, Any]:
    f = _facts_file(project)
    if not f.exists():
        return {}
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_facts_raw(project: str, data: dict[str, Any]) -> None:
    _facts_file(project).write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def ltm_save_fact(project: str, key: str, value: str) -> None:
    """Salva ou atualiza um fato key-value no projeto."""
    data = _load_facts(project)
    data[key] = {"value": value, "updated_at": datetime.utcnow().isoformat()}
    _save_facts_raw(project, data)
    logger.debug(f"Fact salvo: {project}/{key}")


def ltm_get_facts(project: str) -> list[dict]:
    """Retorna todos os fatos do projeto como lista [{key, value, updated_at}]."""
    data = _load_facts(project)
    return [
        {"key": k, "value": v["value"], "updated_at": v.get("updated_at", "")}
        for k, v in data.items()
    ]


def ltm_get_summaries(project: str, limit: int = 10) -> list[dict]:
    """Retorna as últimas memórias de longo prazo do projeto (por session_id=project)."""
    service = get_memory_service()
    return service.get_session_memory(project, limit)


def ltm_get_stats(project: str) -> dict:
    """Retorna estatísticas de memória do projeto."""
    facts = _load_facts(project)
    return {
        "fact_count": len(facts),
        "project": project,
        "facts_file": str(_facts_file(project)),
    }


def build_memory_context(session_id: str, limit_stm: int = 5, limit_ltm: int = 3) -> str:
    """Construir contexto de memória para o prompt."""
    
    stm = stm_get(session_id, limit_stm)
    ltm = ltm_get_session(session_id, limit_ltm)
    
    parts = []
    
    if stm:
        parts.append("## Memória de Curto Prazo (últimas mensagens)")
        for msg in stm:
            parts.append(f"- {msg['role']}: {msg['content'][:200]}")
    
    if ltm:
        parts.append("\n## Memória de Longo Prazo (fatos importantes)")
        for entry in ltm:
            parts.append(f"- {entry.get('content', '')[:200]}")
    
    return "\n".join(parts) if parts else ""
