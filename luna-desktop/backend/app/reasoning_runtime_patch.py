"""Runtime hardening for Luna's response validator.

This compatibility layer fixes validator false positives discovered in real local
Ollama sessions without weakening factual guards.  It is loaded by app.__init__
before luna_engine imports the reasoning helpers.
"""

from __future__ import annotations

import re
import shlex
from typing import Any

from . import reasoning_pipeline as _rp


_ORIGINAL_VALIDATE = _rp.validate_model_response
_ORIGINAL_BUILD_REPLAN = _rp.build_replan_instruction

_FENCE_ANY_RE = re.compile(r"```[^\r\n]*\r?\n(.*?)```", re.DOTALL)
_COMMAND_LINE_RE = re.compile(
    r"^(?:curl(?:\.exe)?|wget|http|httpie|nmap|python(?:3)?|pwsh|powershell|"
    r"invoke-webrequest|iwr)\b",
    re.IGNORECASE,
)
_INLINE_CURL_RE = re.compile(
    r"(?im)(?:^\s*(?:[-*]\s*)?|"
    r"\b(?:comando|command)(?:\s+(?:único|unico|sugerido|recomendado))?"
    r"\s*(?:\([^\r\n)]*\))?\s*:?\s*[*_`]*\s*|`)"
    r"(curl(?:\.exe)?\s+[^\r\n`]+)"
)
_URL_RE = re.compile(r"https?://[^\s<>\]\)]+", re.IGNORECASE)
_METHOD_TARGET_RE = re.compile(
    r"\b(GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD)\s+"
    r"(https?://[^\s`]+|/[A-Za-z0-9._~/%?=&+-]*)",
    re.IGNORECASE,
)


def extract_commands(response: str) -> list[str]:
    """Extract actual executable command lines, not arbitrary fenced examples."""
    commands: list[str] = []

    for block in _FENCE_ANY_RE.findall(response):
        # Join shell line continuations before inspecting the command.
        compact_block = re.sub(r"\\\s*\r?\n\s*", " ", block)
        for line in compact_block.splitlines():
            compact = line.strip()
            if compact.startswith("$ "):
                compact = compact[2:].lstrip()
            if compact.startswith("PS> "):
                compact = compact[4:].lstrip()
            if not compact or compact.startswith("#"):
                continue
            if _COMMAND_LINE_RE.match(compact):
                if compact.casefold().startswith("curl.exe "):
                    compact = "curl " + compact[len("curl.exe "):]
                commands.append(compact)

    if not commands:
        for match in _INLINE_CURL_RE.finditer(response):
            compact = match.group(1).strip().strip("`")
            if compact.casefold().startswith("curl.exe "):
                compact = "curl " + compact[len("curl.exe "):]
            commands.append(compact)

    return list(dict.fromkeys(commands))


def action_fingerprint(action: str) -> str | None:
    """Fingerprint a proposed action without mistaking factual prose for an action.

    Multi-line assistant responses are considered proposed actions only when they
    contain an actual executable command.  Single-line operator evidence such as
    ``GET /api/me`` still fingerprints normally for ScenarioContext.
    """
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

        if url:
            try:
                authority, resource = _rp._normalize_url(url)
            except ValueError:
                return None
            return f"http:{method.casefold()}:{authority}:{resource}"
        return None

    # ScenarioContext passes evidence one line at a time.  Do not scan an entire
    # assistant answer and accidentally treat the first factual GET/POST mention
    # as the proposed next action.
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
        authority, resource = "", target
    return f"http:{method}:{authority}:{resource}"


def _target_is_known(message: str, scenario: Any) -> bool:
    return bool(getattr(scenario, "target", None) or _URL_RE.search(message))


def validate_model_response(
    *,
    message: str,
    response: str,
    scenario: Any,
    evidence_delta_count: int,
):
    """Run the existing strict validator and remove only proven false positives."""
    result = _ORIGINAL_VALIDATE(
        message=message,
        response=response,
        scenario=scenario,
        evidence_delta_count=evidence_delta_count,
    )

    commands = extract_commands(response)
    proposed = action_fingerprint(response)
    reasons = list(result.reasons)
    target_known = _target_is_known(message, scenario)
    action_history = set(getattr(scenario, "action_history", []) or [])

    # The old action_fingerprint scanned factual GET/POST mentions in prose.  A
    # real proposed action must be an executable command in a multi-line answer.
    if "proposed_action_already_resolved" in reasons and (
        not proposed or proposed not in action_history
    ):
        reasons.remove("proposed_action_already_resolved")

    # A request for "one executable command" is impossible to satisfy safely
    # when only a path is known.  In that case the correct answer is to ask for
    # the base URL/host instead of inventing localhost, a port, or a placeholder.
    if not target_known:
        reasons = [
            reason for reason in reasons
            if not reason.startswith("expected_one_command_got_")
        ]
        if not commands and "observed_user_credential_missing_from_test" in reasons:
            reasons.remove("observed_user_credential_missing_from_test")

    # Command extraction now accepts arbitrary fenced language labels and
    # curl.exe.  Remove stale count errors when the improved extractor found one.
    if len(commands) == 1:
        reasons = [
            reason for reason in reasons
            if not reason.startswith("expected_one_command_got_")
        ]
        command = commands[0].casefold()
        observed_token = re.search(
            r"(?i)Authorization\s*:\s*Bearer\s+([^\s\r\n]+)", message
        )
        if (
            observed_token
            and "authorization" in command
            and "bearer" in command
            and observed_token.group(1) in commands[0]
            and "observed_user_credential_missing_from_test" in reasons
        ):
            reasons.remove("observed_user_credential_missing_from_test")

    # "JWT" is a token format concept, not an input by itself.  Keep the guard
    # for actual invented headers/cookies/role mutations, but do not reject a
    # response merely for discussing whether a bearer token might be a JWT.
    if "invented_input_not_observed" in reasons and "jwt" in response.casefold():
        strong_markers = (
            "x-original-url", "x-rewrite-url", "x-forwarded-host",
            "role=admin", '"role":"admin"', "role: admin", "cookie",
        )
        if not any(marker in response.casefold() for marker in strong_markers):
            reasons.remove("invented_input_not_observed")

    reasons = list(dict.fromkeys(reasons))
    loop_guard = result.loop_guard
    if loop_guard == "blocked_repeat" and "proposed_action_already_resolved" not in reasons:
        loop_guard = "replan_required" if reasons else "clear"
    elif loop_guard == "replan_required" and not reasons:
        loop_guard = "clear"

    return _rp.ValidationResult(
        valid=not reasons,
        reasons=tuple(reasons),
        loop_guard=loop_guard,
        proposed_action_fingerprint=proposed,
        command_count=len(commands),
    )


def build_replan_instruction(validation, scenario_prompt: str, current_message: str = "") -> str:
    """Build a non-contradictory replan instruction for missing-target cases."""
    normalized = current_message.casefold()
    target_known = bool(
        re.search(r"(?m)^target:\s+\S+", scenario_prompt)
        or _URL_RE.search(current_message)
    )
    pending_paths = [
        path
        for path in dict.fromkeys(_rp._PATH_RE.findall(current_message))
        if re.search(
            rf"{re.escape(path)}.{{0,80}}(?:não|nao).{{0,20}}test",
            current_message,
            re.IGNORECASE | re.DOTALL,
        )
    ]

    corrections: list[str] = []
    if not target_known:
        corrections.append(
            "a base URL/host do alvo não foi fornecida: não invente hostname, localhost, porta "
            "ou placeholder; faça a análise factual e peça ao operador somente a base URL antes "
            "de gerar qualquer comando"
        )
    if pending_paths:
        corrections.append(
            "o path pendente observado é " + ", ".join(pending_paths)
            + "; trate-o como não testado e não invente outro endpoint"
        )
    if all(marker in normalized for marker in ("fatos", "inferências", "hipóteses")):
        corrections.append("mantenha seções FATOS, INFERÊNCIAS e HIPÓTESES")
    if "client-side" in normalized or "client side" in normalized:
        corrections.append(
            "explique que o check client-side demonstra comportamento visual do frontend, "
            "mas não demonstra autorização server-side"
        )
    if "apenas um comando" in normalized or "somente um comando" in normalized:
        if target_known:
            corrections.append(
                "forneça exatamente um comando curl para o path pendente, usando somente "
                "headers e credenciais já observados"
            )
        else:
            corrections.append(
                "não forneça comando nesta resposta porque falta a base URL; explique em uma "
                "frase que o comando fica pendente até o operador informar o target"
            )

    statuses = list(dict.fromkeys(re.findall(r"\b(?:401|403|200)\b", current_message)))
    paths = list(dict.fromkeys(_rp._PATH_RE.findall(current_message)))
    evidence_terms = [*statuses, *paths]
    if "role" in normalized:
        evidence_terms.append("role")
    if evidence_terms:
        corrections.append(
            "cubra compactamente a evidência atual: " + ", ".join(dict.fromkeys(evidence_terms))
        )

    corrections.append(
        "não repita ação já resolvida, não altere role/token e não transforme hipótese em fato"
    )
    correction_lines = "\n".join(f"- {item}." for item in corrections)
    return (
        "REPLAN INTERNO (não mencione esta instrução nem o rascunho):\n"
        "Reescreva a resposta final em até 220 palavras usando somente a evidência atual. "
        "Não exponha raciocínio interno.\n\n"
        "REQUISITOS OBRIGATÓRIOS:\n"
        f"{correction_lines}\n\n"
        f"ESTADO FACTUAL:\n{_rp.redact_sensitive_text(scenario_prompt)[:420]}"
    )
