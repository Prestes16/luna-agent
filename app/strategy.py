from __future__ import annotations

import json
import logging
import re
import sqlite3
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("luna.strategy")

TASK_TYPES = {
    "code_analysis": {
        "keywords": ["analise", "analisa", "analiz", "entend", "o que faz", "como funciona", "revise", "revisa", "verifique", "verifica", "inspecione"],
        "description": "Análise de código existente",
        "strategy": "scan_first",
    },
    "bug_fix": {
        "keywords": ["corrija", "corrige", "conserte", "fix", "erro", "bug", "falha", "não funciona", "nao funciona", "quebrando", "crash", "exception"],
        "description": "Correção de bug ou erro",
        "strategy": "read_error_first",
    },
    "code_generation": {
        "keywords": ["crie", "cria", "escreva", "escreve", "implemente", "implementa", "construa", "constroi", "adicione", "adiciona", "faça", "faz"],
        "description": "Geração de código novo",
        "strategy": "understand_context_first",
    },
    "security_audit": {
        "keywords": ["vulnerabilidade", "segurança", "seguranca", "hack", "exploit", "ataque", "bounty", "audit", "pentest", "poc", "reentrancy", "overflow", "bypass", "injection", "solana", "smart contract"],
        "description": "Auditoria de segurança / bug bounty",
        "strategy": "deep_read_then_search",
    },
    "project_setup": {
        "keywords": ["configure", "configura", "setup", "instale", "instala", "inicializ", "crie projeto", "boilerplate", "estrutura", "scaffold"],
        "description": "Setup e configuração de projeto",
        "strategy": "check_existing_first",
    },
    "refactoring": {
        "keywords": ["refatore", "refatora", "refactor", "otimize", "otimiza", "melhore", "melhora", "limpe", "limpa", "organize", "organiza", "reescreva"],
        "description": "Refatoração e otimização",
        "strategy": "scan_then_propose",
    },
    "research": {
        "keywords": ["pesquise", "pesquisa", "busque", "busca", "procure", "procura", "encontre", "encontra", "documentação", "documentacao", "como", "qual é", "qual e", "o que é", "o que e"],
        "description": "Pesquisa e busca de informação",
        "strategy": "search_first",
    },
    "shell_task": {
        "keywords": ["execute", "executa", "rode", "roda", "run", "compile", "compila", "build", "teste", "testa", "deploy", "instale dependências"],
        "description": "Execução de comandos shell",
        "strategy": "check_dir_then_run",
    },
}

COMPLEXITY_INDICATORS = {
    "high": ["tudo", "completo", "completa", "inteiro", "inteira", "do zero", "da scratch", "do início", "do inicio", "múltiplos", "multiplos", "vários", "varios", "toda a", "todo o", "todos os", "todas as", "e também", "e tambem", "além disso", "alem disso"],
    "medium": ["e depois", "então", "entao", "também", "tambem", "mais", "adicione também", "corrija e", "analise e"],
}

@dataclass
class TaskClassification:
    task_type: str
    confidence: float
    complexity: str
    strategy: str
    description: str
    needs_planning: bool
    detected_keywords: list[str] = field(default_factory=list)

@dataclass
class ExecutionPlan:
    task_type: str
    goal: str
    steps: list[str]
    tools_needed: list[str]
    potential_issues: list[str]
    success_criteria: str
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

@dataclass
class Lesson:
    task_type: str
    task_summary: str
    what_worked: str
    what_failed: str
    tools_used: list[str]
    outcome: str
    notes: str
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

class StrategyEngine:
    def __init__(self, data_dir: str | Path = "data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.lessons_file = self.data_dir / "luna_lessons.jsonl"
        self.lessons_db = self.data_dir / "strategy_lessons.db"
        self._lesson_cache: list[Lesson] = []
        self._cache_loaded = False
        self._init_lessons_db()

    def _init_lessons_db(self) -> None:
        try:
            with sqlite3.connect(str(self.lessons_db)) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS lessons (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        task_type TEXT,
                        task_summary TEXT,
                        what_worked TEXT,
                        what_failed TEXT,
                        tools_used TEXT,
                        outcome TEXT,
                        notes TEXT,
                        timestamp TEXT,
                        workspace_path TEXT DEFAULT ''
                    )
                """)
                try:
                    conn.execute("ALTER TABLE lessons ADD COLUMN workspace_path TEXT DEFAULT ''")
                except Exception:
                    pass
                conn.commit()
        except Exception:
            pass

    def classify(self, message: str) -> TaskClassification:
        msg_lower = message.lower()
        best_type = "general"
        best_score = 0
        best_keywords: list[str] = []
        for task_type, info in TASK_TYPES.items():
            found = [kw for kw in info["keywords"] if kw in msg_lower]
            score = len(found)
            if score > best_score:
                best_score = score
                best_type = task_type
                best_keywords = found
        if best_score == 0:
            best_type = "general"
            strategy = "understand_context_first"
            description = "Tarefa geral"
        else:
            strategy = TASK_TYPES[best_type]["strategy"]
            description = TASK_TYPES[best_type]["description"]
        confidence = min(1.0, best_score / 3.0)
        high_count = sum(1 for kw in COMPLEXITY_INDICATORS["high"] if kw in msg_lower)
        med_count = sum(1 for kw in COMPLEXITY_INDICATORS["medium"] if kw in msg_lower)
        msg_len = len(message)
        if high_count >= 2 or msg_len > 200:
            complexity = "high"
        elif high_count >= 1 or med_count >= 1 or msg_len > 80:
            complexity = "medium"
        else:
            complexity = "low"
        always_plan = {"code_analysis", "security_audit", "refactoring", "code_generation"}
        needs_planning = best_type in always_plan or complexity in ("medium", "high") or msg_len > 100
        return TaskClassification(best_type, confidence, complexity, strategy, description, needs_planning, best_keywords)

    def build_thinking_prompt(self, classification: TaskClassification, message: str) -> str:
        strategy_pipelines = {
            "scan_first": "PIPELINE: 1. scan_project 2. read_many 3. save_context 4. learn_lesson",
            "read_error_first": "PIPELINE: 1. read_file 2. grep/search 3. corrigir 4. run_command 5. learn_lesson",
            "understand_context_first": "PIPELINE: 1. scan_project 2. read_many 3. implementar 4. validar",
            "deep_read_then_search": "PIPELINE: 1. read_many 2. search_files 3. validar hipótese 4. learn_lesson",
            "check_existing_first": "PIPELINE: 1. scan_project 2. validar stack existente 3. setup mínimo",
            "scan_then_propose": "PIPELINE: 1. scan_project 2. read_many 3. propor e aplicar refactor",
            "search_first": "PIPELINE: 1. web_search ou search_files 2. validar 3. responder com evidência",
            "check_dir_then_run": "PIPELINE: 1. list_dir 2. validar cwd 3. run_command 4. confirmar saída",
        }
        pipeline = strategy_pipelines.get(classification.strategy, "PIPELINE: coletar contexto → agir → learn_lesson")
        return (
            "━━━ MODO ESTRATÉGICO ATIVADO ━━━\n"
            f"Tipo detectado: {classification.description}\n"
            f"Complexidade: {classification.complexity}\n\n"
            f"{pipeline}\n\n"
            "REGRAS: mostre achados reais, cite arquivos reais, não finalize sem evidência."
        )

    def save_lesson(self, task_type: str, task_summary: str, what_worked: str, what_failed: str, tools_used: list[str], outcome: str, notes: str = "") -> None:
        lesson = Lesson(task_type, task_summary[:200], what_worked[:500], what_failed[:300], tools_used, outcome, notes[:300])
        try:
            with open(self.lessons_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(lesson), ensure_ascii=False) + "\n")
        except Exception:
            pass
        try:
            with sqlite3.connect(str(self.lessons_db)) as conn:
                conn.execute(
                    "INSERT INTO lessons (task_type, task_summary, what_worked, what_failed, tools_used, outcome, notes, timestamp, workspace_path) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (lesson.task_type, lesson.task_summary, lesson.what_worked, lesson.what_failed, json.dumps(lesson.tools_used, ensure_ascii=False), lesson.outcome, lesson.notes, lesson.timestamp, "")
                )
                conn.commit()
        except Exception:
            pass
        self._lesson_cache.append(lesson)
        if len(self._lesson_cache) > 100:
            self._lesson_cache = self._lesson_cache[-100:]

    def load_lessons(self, task_type: Optional[str] = None, limit: int = 5) -> list[Lesson]:
        if not self.lessons_file.exists():
            return []
        lessons = []
        try:
            with open(self.lessons_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        lesson = Lesson(**data)
                        if task_type is None or lesson.task_type == task_type or lesson.task_type == "general":
                            lessons.append(lesson)
                    except Exception:
                        continue
        except Exception:
            return []
        same_type = [l for l in lessons if l.task_type == task_type]
        other = [l for l in lessons if l.task_type != task_type]
        combined = same_type[-limit:] + other[-(limit // 2):]
        return combined[-limit:]

    def format_lessons_for_prompt(self, task_type: Optional[str] = None) -> str:
        lessons = self.load_lessons(task_type, limit=4)
        if not lessons:
            return ""
        lines = ["📚 LIÇÕES APRENDIDAS DE TAREFAS ANTERIORES:"]
        for l in lessons:
            lines.append(f"- [{l.outcome}] {l.task_summary[:80]}")
        return "\n".join(lines)

    def get_stats(self) -> dict:
        lessons = self.load_lessons(limit=1000)
        if not lessons:
            return {"total_lessons": 0, "by_type": {}}
        by_type: dict[str, dict] = {}
        for l in lessons:
            if l.task_type not in by_type:
                by_type[l.task_type] = {"total": 0, "success": 0, "partial": 0, "failed": 0}
            by_type[l.task_type]["total"] += 1
            by_type[l.task_type][l.outcome] = by_type[l.task_type].get(l.outcome, 0) + 1
        return {"total_lessons": len(lessons), "by_type": by_type, "last_lesson": lessons[-1].task_summary if lessons else None}

    def recall_lessons_for_project(self, workspace_path: str, task_type: str, limit: int = 5) -> list[dict]:
        try:
            with sqlite3.connect(str(self.lessons_db)) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT task_type, task_summary, what_worked, what_failed, tools_used, outcome, notes, timestamp, workspace_path FROM lessons WHERE workspace_path = ? AND task_type = ? ORDER BY timestamp DESC, id DESC LIMIT ?",
                    (workspace_path or "", task_type or "general", limit),
                ).fetchall()
            output = []
            for row in rows:
                try:
                    tools = json.loads(row["tools_used"]) if row["tools_used"] else []
                except Exception:
                    tools = []
                output.append({
                    "task_type": row["task_type"],
                    "task_summary": row["task_summary"],
                    "what_worked": row["what_worked"],
                    "what_failed": row["what_failed"],
                    "tools_used": tools,
                    "outcome": row["outcome"],
                    "notes": row["notes"],
                    "timestamp": row["timestamp"],
                    "workspace_path": row["workspace_path"],
                })
            return output
        except Exception:
            return []

    def format_project_lessons(self, workspace_path: str, task_type: str) -> str:
        lessons = self.recall_lessons_for_project(workspace_path, task_type, limit=5)
        if not lessons:
            return ""
        lines = ["## Lições relevantes do projeto"]
        for item in lessons:
            lines.append(f"- [{item['outcome']}] {item['task_summary']}")
            if item["what_worked"]:
                lines.append(f"  Funcionou: {item['what_worked'][:140]}")
            if item["what_failed"]:
                lines.append(f"  Falhou: {item['what_failed'][:120]}")
        return "\n".join(lines)

_strategy_engine: Optional[StrategyEngine] = None

def get_strategy_engine(data_dir: str = "data") -> StrategyEngine:
    global _strategy_engine
    if _strategy_engine is None:
        _strategy_engine = StrategyEngine(data_dir)
    return _strategy_engine