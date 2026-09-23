"""Deterministic factual context for the supervised, model-first chat pipeline."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from .reasoning_pipeline import action_fingerprint, redact_sensitive_text


_URL_RE = re.compile(r"https?://[^\s<>\]\)]+", re.IGNORECASE)
_STATUS_RE = re.compile(r"\bHTTP/(\d(?:\.\d)?)\s+(\d{3})(?:\s+([^\r\n]+))?", re.IGNORECASE)
_CONTENT_TYPE_RE = re.compile(r"(?im)^\s*Content-Type\s*:\s*([^\r\n]+)")
_WWW_AUTH_RE = re.compile(r"(?im)^\s*WWW-Authenticate\s*:\s*([^\r\n]+)")
_AUTHORIZATION_RE = re.compile(r"(?im)^\s*Authorization\s*:\s*Bearer\s+([^\s\r\n]+)")
_EXPLICIT_FACT_RE = re.compile(r"(?im)\bFATO\s*:\s*([^\r\n]+)")
_METHOD_PATH_RE = re.compile(
    r"\b(GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD)\s+(/[A-Za-z0-9._~/%?=&+-]*)",
    re.IGNORECASE,
)
_PATH_RE = re.compile(r"(?<![\w.])(/[A-Za-z0-9][A-Za-z0-9._~/%?=&+-]*)")
_NO_EVIDENCE_MARKERS = (
    "ainda não coletei nenhuma evidência", "ainda nao coletei nenhuma evidencia",
    "nenhuma evidência", "nenhuma evidencia", "sem evidência", "sem evidencia",
)
_ADVANCED_MARKERS = (
    "já sei usar", "ja sei usar", "pode ir direto", "vá direto", "va direto",
    "sou avançado", "sou avancado",
)
_BEGINNER_MARKERS = (
    "estou aprendendo", "ainda estou aprendendo", "sou iniciante", "não conheço",
    "nao conheco", "não sei", "nao sei",
)


def _clean_url(value: str) -> str:
    return value.rstrip(".,;:'\"")


def _compact(value: str, limit: int = 360) -> str:
    return " ".join(value.split()).strip()[:limit]


def _fingerprint(value: str) -> str:
    normalized = _compact(redact_sensitive_text(value)).casefold()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:20]


def _append_unique(values: list[str], value: str, *, limit: int = 24) -> bool:
    compact = _compact(value)
    if not compact or compact.casefold() in {item.casefold() for item in values}:
        return False
    values.append(compact)
    if len(values) > limit:
        del values[:-limit]
    return True


def _extract_json_values(message: str) -> list[Any]:
    decoder = json.JSONDecoder()
    values: list[Any] = []
    consumed_until = -1
    for index, char in enumerate(message):
        if index < consumed_until or char not in "[{":
            continue
        try:
            value, consumed = decoder.raw_decode(message[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, (dict, list)):
            values.append(value)
            consumed_until = index + consumed
    return values


def _extract_goal(message: str) -> Optional[str]:
    candidates = re.split(r"(?<=[.!?])\s+|[\r\n]+", message)
    markers = (
        "quero ", "objetivo", "preciso ", "qual deve ser", "como ",
        "separe ", "escolha ", "explique ", "forneça ", "forneca ",
    )
    selected = [
        _compact(candidate, 240)
        for candidate in candidates
        if any(marker in candidate.casefold().strip() for marker in markers)
    ]
    return " | ".join(selected[-3:])[:500] if selected else None


@dataclass(frozen=True)
class EvidenceDelta:
    facts: tuple[str, ...] = ()
    fingerprints: tuple[str, ...] = ()

    @property
    def count(self) -> int:
        return len(self.facts)

    def to_prompt_block(self, max_chars: int = 1_400) -> str:
        if not self.facts:
            return "CURRENT TURN EVIDENCE DELTA: none"
        lines = [f"CURRENT TURN EVIDENCE DELTA ({self.count} new facts):"]
        selected = self.facts
        if len(selected) > 12:
            selected = (*selected[:4], *selected[-8:])
        lines.extend(f"- {fact}" for fact in selected)
        lines.append("Rule: current-turn evidence overrides stale assistant conclusions.")
        return "\n".join(lines)[:max_chars]


@dataclass
class ScenarioContext:
    """Facts explicitly declared or observed in one local conversation."""

    environment: Optional[str] = None
    operator_level: Optional[str] = None
    scope: Optional[str] = None
    target: Optional[str] = None
    current_goal: Optional[str] = None
    observed_facts: list[str] = field(default_factory=list)
    current_unknowns: list[str] = field(default_factory=list)
    last_question: Optional[str] = None
    last_action: Optional[str] = None
    last_action_fingerprint: Optional[str] = None
    last_result: Optional[str] = None
    last_result_fingerprint: Optional[str] = None
    resolved_questions: list[str] = field(default_factory=list)
    pending_question: Optional[str] = None
    action_history: list[str] = field(default_factory=list)
    explained_concepts: set[str] = field(default_factory=set)
    no_evidence_declared: bool = False

    def _add_environment(self, value: str) -> None:
        if not self.environment:
            self.environment = value
            return
        parts = [part.strip() for part in self.environment.split(";")]
        if value.casefold() not in {part.casefold() for part in parts}:
            self.environment = f"{self.environment}; {value}"[:160]

    def _add_fact(self, value: str, delta: list[str]) -> None:
        if _append_unique(self.observed_facts, value):
            delta.append(self.observed_facts[-1])

    def update(self, message: str, *, project_context: Optional[str] = None) -> EvidenceDelta:
        normalized = message.casefold()
        delta: list[str] = []

        if "kali linux" in normalized or re.search(r"\bno kali\b|\bestou no kali\b", normalized):
            self._add_environment("Kali Linux")
        for marker, label in (("chrome", "Chrome"), ("firefox", "Firefox"), (" edge", "Edge")):
            if marker in normalized:
                self._add_environment(label)

        if any(marker in normalized for marker in _ADVANCED_MARKERS):
            self.operator_level = "avançado"
        elif "intermediário" in normalized or "intermediario" in normalized:
            self.operator_level = "intermediário"
        elif any(marker in normalized for marker in _BEGINNER_MARKERS):
            self.operator_level = "iniciante"

        if re.search(r"\bctf\b.{0,40}\bautorizad[oa]\b", normalized):
            self.scope = "CTF autorizado"
        elif re.search(r"\b(?:alvo|ambiente|laborat[oó]rio)\b.{0,50}\bautorizad[oa]\b", normalized):
            self.scope = "ambiente autorizado"

        url_match = _URL_RE.search(message)
        if url_match:
            self.target = _clean_url(url_match.group(0))[:500]

        goal = _extract_goal(message)
        if goal:
            self.current_goal = goal

        questions = [
            _compact(candidate, 280)
            for candidate in re.split(r"[\r\n]+|(?<=\?)\s+", message)
            if "?" in candidate
        ]
        if questions:
            self.last_question = questions[-1]

        if any(marker in normalized for marker in _NO_EVIDENCE_MARKERS) and not self.observed_facts:
            self.no_evidence_declared = True

        for match in _EXPLICIT_FACT_RE.finditer(message):
            self._add_fact(f"Fato declarado: {match.group(1)}", delta)

        current_action: Optional[str] = None
        current_action_fp: Optional[str] = None
        for line in message.splitlines():
            compact_line = line.strip()
            line_action_fp = action_fingerprint(compact_line)
            if line_action_fp:
                current_action = compact_line
                current_action_fp = line_action_fp
                self._add_fact(f"Ação observada no relato: {line_action_fp}", delta)
            method_match = _METHOD_PATH_RE.search(compact_line)
            if method_match:
                method = method_match.group(1).upper()
                path = method_match.group(2)
                current_action = f"{method} {path}"
                current_action_fp = action_fingerprint(current_action)
                self._add_fact(f"Endpoint/ação observado no relato: {current_action}", delta)
                if "sem authorization" in compact_line.casefold():
                    self._add_fact(f"{current_action} foi executado sem Authorization", delta)

            status_match = _STATUS_RE.search(compact_line)
            if status_match:
                reason = _compact(status_match.group(3) or "", 100)
                status_line = f"HTTP/{status_match.group(1)} {status_match.group(2)}"
                if reason:
                    status_line = f"{status_line} {reason}"
                prefix = current_action or "Resposta HTTP"
                self._add_fact(f"{prefix} retornou {status_line}", delta)
                self.last_result = status_line
                self.no_evidence_declared = False
                if current_action_fp:
                    self.last_action = current_action
                    self.last_action_fingerprint = current_action_fp
                    _append_unique(self.action_history, current_action_fp, limit=12)

        for match in _WWW_AUTH_RE.finditer(message):
            self._add_fact(f"WWW-Authenticate observado: {_compact(match.group(1), 120)}", delta)
        for match in _CONTENT_TYPE_RE.finditer(message):
            self._add_fact(f"Content-Type observado: {_compact(match.group(1), 120)}", delta)
        for auth_match in _AUTHORIZATION_RE.finditer(message):
            self._add_fact(
                f"Authorization Bearer observado: {auth_match.group(1)}",
                delta,
            )

        for json_value in _extract_json_values(message):
            compact_json = json.dumps(json_value, ensure_ascii=False, separators=(",", ":"))
            self._add_fact(f"Corpo JSON observado: {compact_json}", delta)
            self.last_result = "Resposta HTTP com corpo JSON observado"
            self.no_evidence_declared = False

        if re.search(r"user\.role\s*===?\s*[\"']admin[\"']", message, re.IGNORECASE):
            self._add_fact("Frontend contém verificação visual user.role === admin", delta)
        if "showadminpanel" in normalized:
            self._add_fact("Frontend chama showAdminPanel() quando o check local de role passa", delta)

        for path in dict.fromkeys(_PATH_RE.findall(message)):
            if re.search(
                rf"{re.escape(path)}.{{0,100}}(?:não|nao).{{0,24}}test",
                message,
                re.IGNORECASE | re.DOTALL,
            ):
                self._add_fact(f"Endpoint observado e ainda não testado: {path}", delta)
                self.pending_question = f"o backend autoriza o operador atual em {path}?"

        if "rodei curl" in normalized or "executei curl" in normalized:
            self.last_action = "curl executado pelo operador"
        elif "vi uma requisição" in normalized and "network" in normalized:
            self.last_action = "requisição observada no painel Network"

        if "no such file or directory" in normalized:
            self.last_result = "erro local: No such file or directory"
            delta = [fact for fact in delta if "No such file" not in fact]

        delta.extend(self._update_from_project_context(project_context))
        unique_delta = list(dict.fromkeys(delta))
        if unique_delta:
            self.last_result_fingerprint = _fingerprint(" | ".join(unique_delta))
        self._recompute_unknowns()
        return EvidenceDelta(
            facts=tuple(unique_delta),
            fingerprints=tuple(_fingerprint(fact) for fact in unique_delta),
        )

    def _update_from_project_context(self, project_context: Optional[str]) -> list[str]:
        if not project_context or "Fatos conhecidos:" not in project_context:
            return []
        delta: list[str] = []
        _, facts_block = project_context.split("Fatos conhecidos:", 1)
        facts_block = facts_block.split("\n\n", 1)[0]
        for line in facts_block.splitlines():
            fact = line.strip()
            if fact.startswith("- "):
                self._add_fact(f"Projeto: {fact[2:]}", delta)
        return delta

    def _recompute_unknowns(self) -> None:
        unknowns: list[str] = []
        if self.pending_question:
            unknowns.append(self.pending_question)
        has_status = any(" retornou HTTP/" in fact for fact in self.observed_facts)
        if self.target and not has_status:
            unknowns.extend(("como o alvo responde ao baseline", "tipo de aplicação ou serviço"))
        if not unknowns and has_status:
            unknowns.append("qual pergunta técnica ainda não respondida traz maior ganho de informação")
        self.current_unknowns = unknowns[:6]

    def mark_explained(self, concept: str) -> None:
        self.explained_concepts.add(concept)

    def record_model_response(self, response: str) -> None:
        proposed = action_fingerprint(response)
        if proposed:
            self.last_action_fingerprint = proposed
            self.last_action = proposed
        pending_match = re.search(
            r"(?is)(?:PRÓXIMA PERGUNTA|OBJETIVO(?: DESTE PASSO)?):\s*([^\r\n]+)",
            response,
        )
        if pending_match:
            self.pending_question = _compact(pending_match.group(1), 280)
        if "curl -i" in response.casefold():
            self.mark_explained("curl -i")

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key in (
            "environment", "operator_level", "scope", "target", "current_goal",
            "last_question", "last_action", "last_action_fingerprint", "last_result",
            "last_result_fingerprint", "pending_question",
        ):
            value = getattr(self, key)
            if value:
                result[key] = value
        if self.observed_facts:
            result["observed_facts"] = list(self.observed_facts)
        if self.current_unknowns:
            result["current_unknowns"] = list(self.current_unknowns)
        if self.resolved_questions:
            result["resolved_questions"] = list(self.resolved_questions)
        if self.action_history:
            result["action_history"] = list(self.action_history)
        if self.explained_concepts:
            result["explained_concepts"] = sorted(self.explained_concepts)
        return result

    def to_prompt_block(self, max_chars: int = 2_200) -> str:
        data = self.to_dict()
        if not data:
            return ""
        lines = ["SCENARIO CONTEXT — only explicit/observed facts"]
        observed_paths = set(_PATH_RE.findall("\n".join(self.observed_facts)))
        for fingerprint in self.action_history:
            if ":/" in fingerprint:
                observed_paths.add(fingerprint[fingerprint.index(":/") + 1:].split("?", 1)[0])
        if observed_paths:
            lines.append(f"observed_endpoint_allowlist: {', '.join(sorted(observed_paths))}")
        observed_headers: list[str] = []
        facts_text = "\n".join(self.observed_facts).casefold()
        for header in ("Authorization", "WWW-Authenticate", "Content-Type", "Set-Cookie"):
            if header.casefold() in facts_text:
                observed_headers.append(header)
        if observed_headers:
            lines.append(f"observed_header_allowlist: {', '.join(observed_headers)}")
        for key in (
            "environment", "operator_level", "scope", "target", "current_goal",
            "last_question", "last_action", "last_action_fingerprint", "last_result",
            "last_result_fingerprint", "pending_question",
        ):
            if key in data:
                lines.append(f"{key}: {data[key]}")
        if self.observed_facts:
            lines.append("observed_facts:")
            lines.extend(f"- {fact}" for fact in self.observed_facts[-12:])
        if self.current_unknowns:
            lines.append("current_unknowns:")
            lines.extend(f"- {item}" for item in self.current_unknowns)
        if self.resolved_questions:
            lines.append("resolved_questions:")
            lines.extend(f"- {item}" for item in self.resolved_questions[-6:])
        if self.action_history:
            lines.append("action_history_fingerprints:")
            lines.extend(f"- {item}" for item in self.action_history[-8:])
        if self.explained_concepts:
            lines.append(f"already_explained: {', '.join(sorted(self.explained_concepts))}")
        lines.append("Rules: unknown is not fact; do not repeat resolved actions without a new reason.")
        return "\n".join(lines)[:max_chars]
