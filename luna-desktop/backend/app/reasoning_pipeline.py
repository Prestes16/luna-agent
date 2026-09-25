"""Model-first routing, action progression, and response validation helpers."""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from typing import Any, Literal, Mapping, Sequence
from urllib.parse import parse_qsl, urlencode, urlsplit

from .quantitative_reasoning import quantitative_claim_violations


ReasoningRoute = Literal["FAST", "ANALYZE", "DEEP"]
ReasoningEffort = Literal["none", "low", "medium"]

_HTTP_STATUS_RE = re.compile(r"(?im)^\s*HTTP/\d(?:\.\d)?\s+\d{3}\b")
_ENDPOINT_RE = re.compile(
    r"\b(?:GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD)\s+(/[A-Za-z0-9._~/%?=&+-]*)",
    re.IGNORECASE,
)
_PATH_RE = re.compile(r"(?<![\w.])(/[A-Za-z0-9][A-Za-z0-9._~/%?=&+-]*)")
_FENCED_RE = re.compile(
    r"```(?:bash|sh|shell|zsh|powershell|pwsh)?(?:[ \t]*\r?\n|[ \t]+)(.*?)```",
    re.DOTALL | re.IGNORECASE,
)
_CURL_RE = re.compile(
    r"(?im)(?:^\s*(?:[-*]\s*)?|"
    r"\b(?:comando|command)(?:\s+(?:único|unico|sugerido|recomendado))?"
    r"\s*(?:\([^\r\n)]*\))?\s*:?\s*[*_`]*\s*|`)"
    r"(curl\s+[^\r\n`]+)"
)

_ANALYZE_MARKERS = (
    "analise", "análise", "compare", "correlac", "logs", "log ", "devtools",
    "o que isso prova", "não prova", "nao prova", "e agora", "próximo teste",
    "proximo teste", "inferência", "inferencia", "hipótese", "hipotese",
    "evidência", "evidencia", "http/", "authorization", "content-type",
    "otimize", "otimizar", "prioriz", "maior valor", "hydra", "brute force", "credencial",
    "interceptar", "interceptação", "interceptacao", "proxy", "outras ferramentas",
    "outras possibilidades", "mais algum", "mais alguma", "melhor app", "qual ferramenta",
    "proxychains", "torsocks", "wireguard", "openvpn", "vpn", "privacidade",
    "anonim", "rastre", "túnel", "tunel", "dns leak", "vazamento dns",
    "kill switch", "killswitch", "malware", "ransomware", "trojan", "rootkit",
    "bootkit", "loader", "dropper", "stealer", "webshell", "yara", "volatility",
    "ghidra", "rizin", "radare", "reverse engineering", "deobfuscat", "desofusc",
    "packer", "memory dump",
)
_DEEP_MARKERS = (
    "cadeia de vulnerabilidades", "exploit chain", "threat model", "modelo de ameaça",
    "prova matemática", "prova matematica", "demonstre formalmente", "complexidade assintótica",
    "complexidade assintotica", "race condition", "reentrancy", "reentrância",
    "ransomware", "rootkit", "bootkit", "reverse engineering", "malware analysis",
    "análise de malware", "analise de malware", "memory forensics", "forense de memória",
)
_RETEST_MARKERS = (
    "reteste", "retestar", "repita", "repetir", "novamente", "reprodut",
    "instável", "instavel", "variável", "variavel", "timing", "race", "cache",
    "before/after", "antes e depois", "flaky", "intermitente", "mudou o estado",
)

_ONE_COMMAND_MARKERS = (
    "apenas um comando", "somente um comando", "exatamente um comando",
    "um único comando", "um unico comando",
)


def _asks_exactly_one_command(value: str) -> bool:
    normalized = value.casefold()
    return any(marker in normalized for marker in _ONE_COMMAND_MARKERS)
_MENTOR_MARKERS = (
    "kali", "linux", "devtools", "network", "initiator", "header", "payload",
    "response", "curl", "nmap", "hydra", "ffuf", "gobuster", "sqlmap", "nuclei",
    "burp", "burpsuite", "mitmproxy", "zaproxy", "wireshark", "proxy",
    "chrome", "firefox", "proxychains", "tor", "torsocks", "wireguard",
    "openvpn", "vpn", "ctf", "autoriz", "malware", "ransomware", "trojan",
    "rootkit", "bootkit", "loader", "dropper", "stealer", "yara", "volatility",
    "ghidra", "rizin", "radare", "capa", "floss", "reverse engineering",
    "evidência", "evidencia", "http/", "json", "endpoint", "api/", "fato:",
)


@dataclass(frozen=True)
class RouteDecision:
    route: ReasoningRoute
    reasoning_effort: ReasoningEffort
    reasons: tuple[str, ...]
    selected_modules: tuple[str, ...]
    llm_required: bool = True


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    reasons: tuple[str, ...]
    loop_guard: str
    proposed_action_fingerprint: str | None
    command_count: int


def redact_sensitive_text(value: str) -> str:
    """Redact only non-evidentiary telemetry/fingerprint copies.

    Exact authorized artifacts remain available in local project/scenario memory.
    """
    redacted = re.sub(
        r"(?im)(Authorization\s*:\s*Bearer\s+)([^\s\r\n]+)",
        r"\1[REDACTED]",
        value,
    )
    redacted = re.sub(
        r'(?i)("(?:token|access_token|refresh_token)"\s*:\s*")[^"]+("?)',
        r"\1[REDACTED]\2",
        redacted,
    )
    redacted = re.sub(
        r"(?im)(Set-Cookie\s*:\s*[^=;\s]+)=([^;\r\n]+)",
        r"\1=[REDACTED]",
        redacted,
    )
    return redacted


def extract_commands(response: str) -> list[str]:
    commands: list[str] = []
    for block in _FENCED_RE.findall(response):
        for line in block.splitlines():
            compact = line.strip()
            if compact and not compact.startswith("#"):
                commands.append(compact)
    if not commands:
        commands.extend(match.group(1).strip().strip("`") for match in _CURL_RE.finditer(response))
    return commands


def _normalize_url(url: str) -> tuple[str, str]:
    parsed = urlsplit(url.strip("`'\".,;"))
    host = (parsed.hostname or "").casefold()
    port = parsed.port
    default_port = 443 if parsed.scheme.casefold() == "https" else 80
    authority = f"{host}:{port or default_port}" if host else ""
    path = parsed.path or "/"
    query = urlencode(sorted(parse_qsl(parsed.query, keep_blank_values=True)))
    resource = f"{path}?{query}" if query else path
    return authority, resource


def _canonical_observed_path(path: str) -> str:
    """Strip prose punctuation while preserving meaningful route/query syntax."""
    value = path.strip().rstrip(".,;:")
    if "?" in value:
        route, query = value.split("?", 1)
        return f"{route.rstrip('.,;:')}?{query.rstrip('.,;:')}"
    return value


def _observed_route_paths(value: str) -> set[str]:
    """Extract canonical route paths without misreading URL authorities as /paths."""
    urls = re.findall(r"https?://[^\s<>\]\)]+", value, re.IGNORECASE)
    scrubbed = re.sub(r"https?://[^\s<>\]\)]+", " ", value, flags=re.IGNORECASE)
    paths = {
        canonical.casefold()
        for path in _PATH_RE.findall(scrubbed)
        if (canonical := _canonical_observed_path(path)) not in {"", "/"}
    }
    for raw_url in urls:
        try:
            _, resource = _normalize_url(raw_url.rstrip(".,;:"))
        except (TypeError, ValueError):
            continue
        path = _canonical_observed_path(resource.split("?", 1)[0])
        if path not in {"", "/"}:
            paths.add(path.casefold())
    return paths


_ROLE_MUTATION_RE = re.compile(
    r"(?is)\b(?:mutar|alterar|forçar|forcar|injetar|mudar)\b.{0,100}\brole\b"
)


def _proposes_role_mutation(value: str) -> bool:
    """Detect role-mutation proposals while ignoring explicit negations/prohibitions."""
    for match in _ROLE_MUTATION_RE.finditer(value):
        start = max(
            value.rfind("\n", 0, match.start()),
            value.rfind(".", 0, match.start()),
            value.rfind(";", 0, match.start()),
            value.rfind(":", 0, match.start()),
        )
        prefix = value[start + 1:match.start()].casefold()
        if re.search(
            r"\b(?:não|nao|nunca|jamais|sem|evite|evitar|proibido|proibida)\b",
            prefix,
        ):
            continue
        return True
    return False


def action_fingerprint(action: str) -> str | None:
    """Normalize functionally equivalent HTTP actions without retaining secrets."""
    candidates = extract_commands(action)
    if not candidates:
        curl_match = _CURL_RE.search(action)
        if curl_match:
            candidates = [curl_match.group(1)]

    if candidates and candidates[0].casefold().startswith("curl "):
        try:
            tokens = shlex.split(candidates[0], posix=True)
        except ValueError:
            tokens = candidates[0].split()
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
            if lower.startswith("http://") or lower.startswith("https://"):
                url = token
            index += 1
        if url:
            try:
                authority, resource = _normalize_url(url)
            except ValueError:
                return None
            return f"http:{method.casefold()}:{authority}:{resource}"

    method_match = re.search(
        r"\b(GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD)\s+(https?://[^\s`]+|/[A-Za-z0-9._~/%?=&+-]*)",
        action,
        re.IGNORECASE,
    )
    if method_match:
        method = method_match.group(1).casefold()
        target = method_match.group(2)
        if target.startswith("http"):
            authority, resource = _normalize_url(target)
        else:
            authority, resource = "", target
        return f"http:{method}:{authority}:{resource}"
    return None


def classify_complexity(
    message: str,
    *,
    evidence_delta_count: int,
    scenario: Mapping[str, Any] | None = None,
    history: Sequence[Mapping[str, Any]] = (),
    mentor_enabled: bool = True,
) -> RouteDecision:
    normalized = message.casefold()
    lines = [line for line in message.splitlines() if line.strip()]
    # Count only canonicalized observed routes. Combining raw method matches with
    # canonical paths double-counted prose punctuation variants such as /api/me.
    endpoints = _observed_route_paths(message)
    status_count = len(_HTTP_STATUS_RE.findall(message))
    has_code = bool(re.search(r"```|\bif\s*\(|\bdef\s+|\bclass\s+|=>|\{\s*$", message, re.MULTILINE))
    has_http = status_count > 0 or bool(endpoints)
    has_analysis_request = any(marker in normalized for marker in _ANALYZE_MARKERS)
    has_deep_request = any(marker in normalized for marker in _DEEP_MARKERS)
    history_relevant = bool(history) and (has_http or has_analysis_request)

    reasons: list[str] = []
    if evidence_delta_count:
        reasons.append(f"evidence_delta={evidence_delta_count}")
    if len(endpoints) > 1:
        reasons.append(f"multiple_endpoints={len(endpoints)}")
    if status_count > 1:
        reasons.append(f"multiple_http_results={status_count}")
    if has_code and has_http:
        reasons.append("code_plus_http")
    if history_relevant:
        reasons.append("relevant_history")
    if has_analysis_request:
        reasons.append("correlation_or_investigation")

    deep = (
        has_deep_request
        or len(message) >= 3_000
        or len(lines) >= 50
        or (len(endpoints) >= 5 and status_count >= 4)
    )
    analyze = (
        evidence_delta_count >= 2
        or len(endpoints) >= 2
        or status_count >= 2
        or (has_code and has_http)
        or len(lines) >= 7
        or has_analysis_request
        or history_relevant
    )

    if deep:
        route: ReasoningRoute = "DEEP"
        effort: ReasoningEffort = "medium"
        reasons.append("deep_artifact_or_reasoning_load")
    elif analyze:
        route = "ANALYZE"
        effort = "low"
    else:
        route = "FAST"
        effort = "none"
        reasons.append("single_step_or_low_correlation")

    selected_modules: tuple[str, ...] = ()
    scenario_active = bool(
        scenario
        and (
            scenario.get("scope")
            or scenario.get("target")
            or scenario.get("observed_facts")
        )
    )
    if mentor_enabled and (
        any(marker in normalized for marker in _MENTOR_MARKERS)
        or (scenario_active and (has_http or has_analysis_request))
    ):
        selected_modules = ("mentor_kali_devtools",)

    return RouteDecision(
        route=route,
        reasoning_effort=effort,
        reasons=tuple(dict.fromkeys(reasons)),
        selected_modules=selected_modules,
    )


def _retest_is_justified(message: str) -> bool:
    normalized = message.casefold()
    return any(marker in normalized for marker in _RETEST_MARKERS)


def validate_model_response(
    *,
    message: str,
    response: str,
    scenario: Any,
    evidence_delta_count: int,
) -> ValidationResult:
    """Reject loops or evidence regressions; never synthesize the replacement answer."""
    reasons: list[str] = []
    commands = extract_commands(response)
    proposed = action_fingerprint(response)
    repeat_allowed = _retest_is_justified(message)
    action_history = set(getattr(scenario, "action_history", []) or [])
    last_result_fingerprint = getattr(scenario, "last_result_fingerprint", None)
    scenario_facts = "\n".join(getattr(scenario, "observed_facts", []) or [])
    factual_context = f"{message}\n{scenario_facts}".casefold()
    normalized_message = message.casefold()
    normalized_response = response.casefold()
    asks_next_test = any(
        marker in normalized_message
        for marker in ("próximo teste", "proximo teste", "next test")
    )

    observed_paths_in_context = _observed_route_paths(factual_context)
    response_paths = _observed_route_paths(response)
    if any(path not in observed_paths_in_context for path in response_paths):
        reasons.append("unobserved_endpoint_mentioned")

    if not response.strip():
        reasons.append("empty_model_response")

    continuation_without_pending_evidence = (
        any(marker in message.casefold() for marker in ("e agora", "qual o próximo", "qual o proximo"))
        and bool(action_history)
        and not getattr(scenario, "pending_question", None)
        and evidence_delta_count == 0
    )
    if continuation_without_pending_evidence and (not response.strip() or proposed or commands):
        reasons.append("continuation_has_no_observed_pending_action")
    if (
        asks_next_test
        and action_history
        and not getattr(scenario, "pending_question", None)
        and evidence_delta_count == 0
        and (not response.strip() or proposed or commands)
    ):
        reasons.append("no_observed_pending_action")

    loop_guard = "clear"
    if proposed and proposed in action_history and last_result_fingerprint:
        if repeat_allowed:
            loop_guard = "retest_allowed"
        else:
            reasons.append("proposed_action_already_resolved")
            loop_guard = "blocked_repeat"

    if proposed and action_history and ":/" in proposed:
        proposed_path = proposed[proposed.index(":/") + 1:].split("?", 1)[0].casefold()
        observed_paths = _observed_route_paths(factual_context)
        if proposed_path != "/" and proposed_path not in observed_paths:
            reasons.append("proposed_unobserved_endpoint")

    if proposed and proposed.startswith("http:"):
        authority_match = re.match(r"^http:[^:]+:(.*):(/.*)$", proposed)
        proposed_authority = authority_match.group(1) if authority_match else ""
        observed_authorities: set[str] = set()
        target = getattr(scenario, "target", None)
        factual_urls = re.findall(r"https?://[^\s<>\]\)]+", f"{message}\n{target or ''}")
        for factual_url in factual_urls:
            try:
                authority, _ = _normalize_url(factual_url)
            except ValueError:
                continue
            if authority:
                observed_authorities.add(authority)
        if proposed_authority and proposed_authority not in observed_authorities:
            reasons.append("proposed_unobserved_authority")

    if commands and commands[0].casefold().startswith("curl ") and not proposed:
        reasons.append("invalid_curl_target")

    observed_admin_role = bool(
        re.search(
            r"\brole\s*(?:===?|:)\s*[\"']?admin\b",
            factual_context,
            re.IGNORECASE,
        )
    )
    invented_markers = [
        "x-original-url", "x-rewrite-url", "x-forwarded-host", "jwt",
    ]
    if not observed_admin_role:
        invented_markers.extend(("role=admin", '"role":"admin"', "role: admin"))
    command_text = "\n".join(commands).casefold()
    for invented_marker in invented_markers:
        marker_used_as_input = invented_marker in command_text or bool(
            re.search(
                rf"(?is)(?:\buse\b|\busar\b|\badicione\b|\benvie\b|\bteste\b|"
                rf"\bmut(?:e|ar)\b|\binjete\b).{{0,100}}{re.escape(invented_marker)}",
                response,
            )
        )
        if marker_used_as_input and invented_marker not in factual_context:
            reasons.append("invented_input_not_observed")
            break
    proposes_unobserved_cookie = "cookie" not in factual_context and (
        any("cookie" in command.casefold() for command in commands)
        or bool(
            re.search(
                r"(?is)(?:\bcom\b|\binclu(?:a|indo)\b|\buse\b|\busar\b|"
                r"\badicione\b|\benvie\b).{0,80}\bcookie\b",
                response,
            )
        )
    )
    if proposes_unobserved_cookie:
        reasons.append("invented_input_not_observed")
    if _proposes_role_mutation(response) and not _proposes_role_mutation(message):
        reasons.append("invented_role_mutation")

    if _asks_exactly_one_command(message) and len(commands) != 1:
        reasons.append(f"expected_one_command_got_{len(commands)}")

    if commands and commands[0].casefold().startswith("curl "):
        try:
            command_tokens = shlex.split(commands[0], posix=True)
        except ValueError:
            command_tokens = commands[0].split()
        allowed_long_options = {
            "--include", "--header", "--request", "--data", "--data-raw",
            "--data-binary", "--silent", "--show-error", "--location", "--output",
            "--user", "--connect-timeout", "--max-time", "--fail", "--fail-with-body",
            "--insecure", "--cookie", "--cookie-jar", "--url", "--get", "--head",
        }
        if any(
            token.startswith("--") and token.split("=", 1)[0] not in allowed_long_options
            for token in command_tokens[1:]
        ):
            reasons.append("unknown_curl_option")
        data_options = {"-d", "--data", "--data-raw", "--data-binary"}
        if any(token.casefold() in data_options for token in command_tokens[1:]) and not re.search(
            r"(?i)(?:request body|corpo da requisição|corpo da requisicao|payload|--data|\s-d\s)",
            message,
        ):
            reasons.append("invented_request_body")

    observed_untested_paths = [
        path
        for path in sorted(_observed_route_paths(message))
        if re.search(
            rf"{re.escape(path)}[\s.,;:)]*.{{0,80}}(?:não|nao).{{0,20}}test",
            message,
            re.IGNORECASE | re.DOTALL,
        )
    ]
    if asks_next_test and observed_untested_paths and proposed:
        proposed_match = re.match(r"^http:([^:]+):.*:(/.*)$", proposed)
        if proposed_match:
            proposed_method = proposed_match.group(1).upper()
            proposed_resource = proposed_match.group(2).split("?", 1)[0].casefold()
            for pending_path in observed_untested_paths:
                if proposed_resource != pending_path.casefold():
                    continue
                explicit_methods = {
                    match.group(1).upper()
                    for match in re.finditer(
                        r"\b(GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD)\s+"
                        r"(/[A-Za-z0-9._~/%?=&+-]*)",
                        message,
                        re.IGNORECASE,
                    )
                    if match.group(2).casefold() == pending_path.casefold()
                }
                allowed_methods = explicit_methods or {"GET"}
                if proposed_method not in allowed_methods:
                    reasons.append("unobserved_method_for_pending_endpoint")
                break
    if asks_next_test and observed_untested_paths:
        if not any(path.casefold() in normalized_response for path in observed_untested_paths):
            reasons.append("ignored_observed_untested_endpoint")
        observed_token_match = re.search(
            r"(?i)Authorization\s*:\s*Bearer\s+([^\s\r\n]+)",
            message,
        )
        observed_token = (
            observed_token_match.group(1).rstrip("`'\".,;:)")
            if observed_token_match
            else None
        )
        if (
            observed_token
            and not any(
                "authorization" in command.casefold()
                and "bearer" in command.casefold()
                and observed_token in command
                for command in commands
            )
        ):
            reasons.append("observed_user_credential_missing_from_test")

    asks_client_proof = "client-side" in normalized_message or "client side" in normalized_message
    if asks_client_proof:
        server_side_named = any(
            marker in normalized_response
            for marker in ("backend", "servidor", "server-side", "server side")
        )
        limitation_named = any(
            marker in normalized_response
            for marker in (
                "não prova", "nao prova", "não confirma", "nao confirma",
                "não garante", "nao garante", "apenas visual", "somente visual",
                "puramente local", "só na interface", "so na interface",
            )
        )
        limitation_named = limitation_named or (
            any(
                marker in normalized_response
                for marker in ("client-side", "client side", "frontend", "navegador", "interface")
            )
            and server_side_named
        )
        if not server_side_named or not limitation_named:
            reasons.append("client_side_limit_not_explained")
        if re.search(
            r"(?is)client-side.{0,100}(?:prova|demonstra|confirma).{0,120}"
            r"(?:backend|servidor|api).{0,80}(?:não valida|nao valida|falha)",
            response,
        ):
            reasons.append("client_side_overclaimed_backend_failure")

    asks_fact_split = all(
        marker in normalized_message
        for marker in ("fatos", "inferências", "hipóteses")
    )
    if asks_fact_split and not all(
        marker in normalized_response
        for marker in ("fato", "infer", "hip")
    ):
        reasons.append("missing_fact_inference_hypothesis_split")
    if asks_fact_split:
        evidence_concepts = [
            marker in normalized_response
            for marker in ("401", "200", "/api/me", "/api/admin/users", "role")
            if marker in normalized_message
        ]
        if "/api/login" in normalized_message:
            evidence_concepts.append(
                "/api/login" in normalized_response or "login" in normalized_response
            )
        if evidence_concepts and sum(evidence_concepts) < min(3, len(evidence_concepts)):
            reasons.append("multi_evidence_fact_coverage_missing")

    if evidence_delta_count >= 4:
        current_paths = _observed_route_paths(message)
        response_path_hits = sum(path in normalized_response for path in current_paths)
        evidence_concept_hits = sum(
            marker in normalized_response
            for marker in ("401", "403", "role", "token", "frontend", "visual", "backend")
        )
        if current_paths and response_path_hits == 0 and evidence_concept_hits < 3:
            reasons.append("large_evidence_delta_ignored_current_endpoints")
        if proposed and proposed.endswith(":/") and any(path != "/" for path in current_paths):
            reasons.append("regressed_to_root_baseline_after_large_delta")

    # V17/V18 are executable output validators, not merely prompt guidance.
    # Strong numerical/physical claims must agree with deterministic facts/bounds.
    reasons.extend(
        quantitative_claim_violations(
            f"{message}\n{scenario_facts}",
            response,
        )
    )

    if reasons and loop_guard == "clear":
        loop_guard = "replan_required"
    return ValidationResult(
        valid=not reasons,
        reasons=tuple(dict.fromkeys(reasons)),
        loop_guard=loop_guard,
        proposed_action_fingerprint=proposed,
        command_count=len(commands),
    )


def build_replan_instruction(
    validation: ValidationResult,
    scenario_prompt: str,
    current_message: str = "",
) -> str:
    corrections: list[str] = []
    reason_set = set(validation.reasons)
    normalized_current = current_message.casefold()
    if "generation_truncated" in reason_set:
        corrections.append(
            "a geração anterior atingiu o limite de saída; preserve todas as seções explicitamente "
            "pedidas, mas use tabelas/bullets compactos, não repita o prompt e não exponha raciocínio interno"
        )
    if reason_set & {"proposed_unobserved_authority", "invalid_curl_target"}:
        corrections.append(
            "não invente hostname, porta nem placeholder de URL; se só há um path observado "
            "e nenhum target factual, descreva o teste pelo path e não forneça curl"
        )
    pending_paths = [
        path
        for path in sorted(_observed_route_paths(current_message))
        if re.search(
            rf"{re.escape(path)}[\s.,;:)]*.{{0,80}}(?:não|nao).{{0,20}}test",
            current_message,
            re.IGNORECASE | re.DOTALL,
        )
    ]
    if pending_paths:
        corrections.append(
            "use somente GET no path pendente " + ", ".join(pending_paths)
            + "; não use POST, -X, -d, body, role mutada ou input novo"
        )
    if all(marker in normalized_current for marker in ("fatos", "inferências", "hipóteses")):
        corrections.append(
            "mantenha seções explicitamente intituladas FATOS, INFERÊNCIAS e HIPÓTESES"
        )
    if "client-side" in normalized_current or "client side" in normalized_current:
        corrections.append(
            "explique que o client-side prova comportamento visual, mas não prova autorização backend"
        )
    if _asks_exactly_one_command(current_message):
        corrections.append("forneça exatamente um comando curl, somente com -i e -H")
    observed_statuses = list(dict.fromkeys(re.findall(r"\b(?:401|403|200)\b", current_message)))
    observed_paths = sorted(_observed_route_paths(current_message))
    evidence_terms = [*observed_statuses, *observed_paths]
    if "role" in normalized_current:
        evidence_terms.append("role")
    if evidence_terms:
        corrections.append(
            "a seção FATOS deve cobrir de forma compacta a evidência atual: "
            + ", ".join(dict.fromkeys(evidence_terms))
        )
    if reason_set & {
        "proposed_unobserved_endpoint", "proposed_unobserved_authority",
        "invented_input_not_observed", "invented_request_body",
        "unobserved_method_for_pending_endpoint", "unobserved_endpoint_mentioned",
        "invented_role_mutation", "proposed_action_already_resolved",
    }:
        corrections.append(
            "use somente endpoint/header observado e ainda não resolvido; se nenhum existir, "
            "peça nova evidência ao operador sem inventar uma mutação"
        )
    if "continuation_has_no_observed_pending_action" in reason_set:
        corrections.append(
            "não forneça comando nem enumere caminho comum; diga que o baseline já foi "
            "resolvido e peça ao operador um novo endpoint, log ou artefato observado"
        )
    if "no_observed_pending_action" in reason_set:
        corrections.append(
            "todos os endpoints observados já têm resultado; não invente parâmetro, header, "
            "credencial ou endpoint. Se faltar uma ação factual pendente, peça código/log do "
            "controle backend ou nova evidência, sem comando sintético"
        )
    correction_lines = "\n".join(f"- {item}." for item in corrections)
    word_budget = 700 if "generation_truncated" in reason_set else 220
    return (
        "REPLAN INTERNO (não mencione esta instrução nem o rascunho):\n"
        f"Reescreva a resposta final em até {word_budget} palavras usando só fatos da mensagem atual. "
        "Cubra todos os requisitos explícitos do usuário antes de adicionar explicações. "
        "Não importe exemplos, não repita ação resolvida e não exponha raciocínio interno.\n\n"
        "REQUISITOS OBRIGATÓRIOS:\n"
        f"{correction_lines or '- satisfaça todos os guards factuais.'}\n\n"
        f"ESTADO FACTUAL:\n{scenario_prompt[:320]}"
    )
