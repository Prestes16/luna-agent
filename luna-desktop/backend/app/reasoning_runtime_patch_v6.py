"""Sixth-stage reasoning hardening: canonical parsing and semantic reconciliation.

This layer fixes parser-level false positives exposed by the full backend test
suite.  It deliberately does not weaken the factual or mathematical guards:
paths are canonicalized, executable commands are extracted consistently, and
semantic overclaim reasons are recomputed from canonical evidence before the
final quality gate is accepted.
"""

from __future__ import annotations

import re
import shlex
from typing import Any

from . import reasoning_pipeline as _rp
from .reasoning_quality import score_response_quality
from .reasoning_runtime_patch_v5 import (
    build_replan_instruction as _previous_build_replan,
    validate_model_response as _previous_validate,
)

_COMMAND_LINE_RE = re.compile(
    r"^(?:curl(?:\.exe)?|wget|http|httpie|nmap|python(?:3)?|pwsh|powershell|"
    r"invoke-webrequest|iwr)\b",
    re.IGNORECASE,
)
_FENCE_RE = re.compile(r"```(?P<label>[A-Za-z0-9_+.-]*)[ \t]*(?P<body>.*?)```", re.DOTALL)
_INLINE_CURL_RE = re.compile(
    r"(?im)(?:^\s*(?:[-*]\s*)?|"
    r"\b(?:comando|command)(?:\s+(?:único|unico|sugerido|recomendado))?"
    r"\s*(?:\([^\r\n)]*\))?\s*:?\s*[*_`]*\s*|`)"
    r"(curl(?:\.exe)?\s+[^\r\n`]+)"
)
_METHOD_TARGET_RE = re.compile(
    r"\b(GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD)\s+"
    r"(https?://[^\s`]+|/[A-Za-z0-9._~/%?=&+-]*)",
    re.IGNORECASE,
)
_URL_RE = re.compile(r"https?://[^\s<>\]\)]+", re.IGNORECASE)
_STATUS_TOKEN_RE = re.compile(r"(?<![\d.])([1-5]\d{2})(?![\d.])")
_CRITICAL_QUALITY_THRESHOLD = 0.62

_SEMANTIC_REASONS = {
    "status_claim_for_untested_endpoint",
    "definitive_outcome_for_untested_endpoint",
    "unsupported_client_behavior_claim",
}


def _normalize_command(command: str) -> str:
    compact = command.strip()
    if compact.startswith("$ "):
        compact = compact[2:].lstrip()
    if compact.startswith("PS> "):
        compact = compact[4:].lstrip()
    if compact.casefold().startswith("curl.exe "):
        compact = "curl " + compact[len("curl.exe "):]
    return compact


def extract_commands(response: str) -> list[str]:
    """Extract executable commands from multiline or one-line Markdown fences."""
    commands: list[str] = []

    for match in _FENCE_RE.finditer(response):
        label = match.group("label").casefold()
        body = match.group("body")

        # ```bash curl ...``` and ```bash\ncurl ...``` are both valid enough for
        # the validator.  A fence without a language label is handled the same
        # way.  Non-shell labels are only accepted if the body itself starts with
        # a known executable command.
        if label in {"bash", "sh", "shell", "zsh", "powershell", "pwsh", ""}:
            candidate_text = body
        elif label in {"curl", "wget", "nmap", "python", "python3", "http", "httpie"}:
            candidate_text = f"{label} {body}".strip()
        else:
            candidate_text = body

        compact_block = re.sub(r"\\\s*\r?\n\s*", " ", candidate_text)
        for line in compact_block.splitlines() or [compact_block]:
            compact = _normalize_command(line)
            if compact and not compact.startswith("#") and _COMMAND_LINE_RE.match(compact):
                commands.append(compact)

    if not commands:
        for match in _INLINE_CURL_RE.finditer(response):
            compact = _normalize_command(match.group(1).strip().strip("`"))
            if compact:
                commands.append(compact)

    return list(dict.fromkeys(commands))


def action_fingerprint(action: str) -> str | None:
    """Fingerprint a real proposed action without treating factual prose as one."""
    commands = extract_commands(action)
    candidate = commands[0] if commands else ""

    if candidate.casefold().startswith("curl "):
        try:
            tokens = shlex.split(candidate, posix=True)
        except ValueError:
            tokens = candidate.split()

        method = "GET"
        url = ""
        index = 1
        options_with_value = {
            "-h", "--header", "-o", "--output", "-a", "--user-agent", "-u", "--user",
            "-d", "--data", "--data-raw", "--data-binary", "--data-urlencode",
            "-x", "--request", "--proxy", "--connect-timeout", "--max-time",
        }
        while index < len(tokens):
            token = tokens[index]
            lower = token.casefold()
            if lower in {"-x", "--request"} and index + 1 < len(tokens):
                method = tokens[index + 1].upper()
                index += 2
                continue
            if lower in {"-d", "--data", "--data-raw", "--data-binary", "--data-urlencode"}:
                if method == "GET":
                    method = "POST"
                index += 2
                continue
            if lower in options_with_value:
                index += 2
                continue
            if lower.startswith(("http://", "https://")):
                url = token
            index += 1

        if not url:
            return None
        try:
            authority, resource = _rp._normalize_url(url)
        except ValueError:
            return None
        return f"http:{method.casefold()}:{authority}:{resource}"

    nonempty_lines = [line.strip() for line in action.splitlines() if line.strip()]
    if len(nonempty_lines) != 1:
        return None
    match = _METHOD_TARGET_RE.search(nonempty_lines[0])
    if not match:
        return None
    method = match.group(1).casefold()
    target = match.group(2)
    if target.casefold().startswith("http"):
        try:
            authority, resource = _rp._normalize_url(target)
        except ValueError:
            return None
    else:
        authority, resource = "", _canonical_path(target)
    return f"http:{method}:{authority}:{resource}"


def _canonical_path(path: str) -> str:
    value = path.strip().rstrip(".,;:")
    if "?" in value:
        route, query = value.split("?", 1)
        return f"{route.rstrip('.,;:')}?{query.rstrip('.,;:')}"
    return value


def _route_paths(value: str) -> set[str]:
    """Extract canonical route paths while never treating URL authorities as routes."""
    urls = list(_URL_RE.findall(value))
    scrubbed = _URL_RE.sub(" ", value)
    paths = {
        _canonical_path(path).casefold()
        for path in _rp._PATH_RE.findall(scrubbed)
        if _canonical_path(path) not in {"", "/"}
    }
    for raw_url in urls:
        try:
            _, resource = _rp._normalize_url(raw_url.rstrip(".,;:"))
        except (TypeError, ValueError):
            continue
        path = _canonical_path(resource.split("?", 1)[0])
        if path not in {"", "/"}:
            paths.add(path.casefold())
    return paths


def _untested_paths(message: str) -> list[str]:
    found: list[str] = []
    for raw_path in dict.fromkeys(_rp._PATH_RE.findall(message)):
        path = _canonical_path(raw_path)
        if not path or path == "/":
            continue
        if re.search(
            rf"{re.escape(path)}[\s.,;:)]*.{{0,120}}(?:não|nao).{{0,28}}test",
            message,
            re.IGNORECASE | re.DOTALL,
        ):
            found.append(path)
    return list(dict.fromkeys(found))


def _section(response: str, section: str) -> str:
    heading_map = {
        "facts": r"FATOS?",
        "inferences": r"INFER(?:Ê|E)NCIAS?",
        "hypotheses": r"HIP(?:Ó|O)TESES?",
    }
    start_pat = heading_map[section]
    start = re.search(
        rf"(?im)^\s*(?:[#>*-]+\s*)?\**\s*{start_pat}\s*\**\s*:?\s*",
        response,
    )
    if not start:
        return ""
    tail = response[start.end():]
    any_heading = re.search(
        r"(?im)^\s*(?:[#>*-]+\s*)?\**\s*(?:FATOS?|INFER(?:Ê|E)NCIAS?|"
        r"HIP(?:Ó|O)TESES?|PR(?:Ó|O)XIM(?:O|A)(?:\s+TESTE)?|A[CÇ][AÃ]O|COMANDO)\b",
        tail,
    )
    return tail[:any_heading.start()] if any_heading else tail


def _semantic_overclaim_reasons(message: str, response: str) -> list[str]:
    reasons: list[str] = []
    untested = _untested_paths(message)
    facts = _section(response, "facts")
    hypotheses = _section(response, "hypotheses")

    for path in untested:
        escaped = re.escape(path)
        status = r"(?<![\d.])[1-5]\d{2}(?![\d.])"
        if re.search(
            rf"(?is)(?:{status}.{{0,90}}{escaped}|{escaped}.{{0,90}}{status})",
            facts,
        ):
            reasons.append("status_claim_for_untested_endpoint")

        if re.search(
            rf"(?is){escaped}.{{0,140}}(?:será|sera|vai\s+retornar|retornará|retornara)"
            rf".{{0,60}}{status}",
            hypotheses,
        ):
            reasons.append("definitive_outcome_for_untested_endpoint")

    normalized_message = message.casefold()
    normalized_response = response.casefold()
    unsupported_negative_markers = (
        "não realiza chamadas api", "nao realiza chamadas api",
        "não faz chamadas api", "nao faz chamadas api",
        "não realiza requisições", "nao realiza requisicoes",
    )
    if any(marker in normalized_response for marker in unsupported_negative_markers) and not any(
        marker in normalized_message for marker in unsupported_negative_markers
    ):
        reasons.append("unsupported_client_behavior_claim")

    return list(dict.fromkeys(reasons))


def validate_model_response(
    *,
    message: str,
    response: str,
    scenario: Any,
    evidence_delta_count: int,
):
    result = _previous_validate(
        message=message,
        response=response,
        scenario=scenario,
        evidence_delta_count=evidence_delta_count,
    )
    reasons = [reason for reason in result.reasons if reason not in _SEMANTIC_REASONS]

    # Reconcile the endpoint guard with canonical route parsing.  The guard stays
    # active for real new routes, but punctuation and URL authorities no longer
    # create phantom endpoints.
    if "unobserved_endpoint_mentioned" in reasons:
        scenario_facts = "\n".join(getattr(scenario, "observed_facts", []) or [])
        observed = _route_paths(f"{message}\n{scenario_facts}")
        response_paths = _route_paths(response)
        if not (response_paths - observed):
            reasons.remove("unobserved_endpoint_mentioned")

    reasons.extend(_semantic_overclaim_reasons(message, response))
    reasons = list(dict.fromkeys(reasons))

    # Stage 4 may have added the soft quality gate because an earlier parser
    # produced a false semantic reason or missed an inline command.  Recompute the
    # final score after canonical reconciliation and keep/remove the gate based on
    # the corrected evidence.
    quality = score_response_quality(message, response, reasons)
    if quality.contract.wants_command:
        if quality.total >= _CRITICAL_QUALITY_THRESHOLD:
            reasons = [reason for reason in reasons if reason != "quality_gate_below_threshold"]
        elif "quality_gate_below_threshold" not in reasons:
            reasons.append("quality_gate_below_threshold")
    else:
        reasons = [reason for reason in reasons if reason != "quality_gate_below_threshold"]

    reasons = list(dict.fromkeys(reasons))
    loop_guard = result.loop_guard
    if not reasons and loop_guard in {"replan_required", "blocked_repeat"}:
        loop_guard = "clear"
    elif reasons and loop_guard in {"clear", "retest_allowed"}:
        loop_guard = "replan_required"

    return _rp.ValidationResult(
        valid=not reasons,
        reasons=tuple(reasons),
        loop_guard=loop_guard,
        proposed_action_fingerprint=action_fingerprint(response),
        command_count=len(extract_commands(response)),
    )


def build_replan_instruction(validation, scenario_prompt: str, current_message: str = "") -> str:
    base = _previous_build_replan(validation, scenario_prompt, current_message)
    additions: list[str] = []
    reasons = set(validation.reasons)
    if "status_claim_for_untested_endpoint" in reasons:
        additions.append("não associe status HTTP a endpoint marcado como não testado")
    if "definitive_outcome_for_untested_endpoint" in reasons:
        additions.append("mantenha resultados futuros como hipótese condicional, nunca como certeza")
    if "unobserved_endpoint_mentioned" in reasons:
        additions.append("use somente paths canônicos realmente presentes na evidência atual")
    if not additions:
        return base
    return base + "\n\nRECONCILIAÇÃO CANÔNICA:\n" + "\n".join(f"- {item}." for item in additions)
