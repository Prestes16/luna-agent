"""Second-stage validator hardening for URL-aware endpoint detection.

The base validator intentionally rejects endpoints that were never observed. In
real model output, however, the generic path regex can misread the authority part
of a full URL (for example the second slash in ``http://127.0.0.1:8080``) as an
endpoint. This wrapper recomputes only that one guard with URL-aware semantics.
All executable-action guards remain intact.
"""

from __future__ import annotations

import re
from typing import Any

from . import reasoning_pipeline as _rp
from .reasoning_runtime_patch import validate_model_response as _previous_validate

_URL_RE = re.compile(r"https?://[^\s<>\]\)]+", re.IGNORECASE)


def _route_paths(value: str) -> set[str]:
    """Return actual route paths without treating URL authorities as paths."""
    urls = list(_URL_RE.findall(value))
    scrubbed = _URL_RE.sub(" ", value)
    paths = {
        path.casefold()
        for path in _rp._PATH_RE.findall(scrubbed)
        if path and path != "/"
    }

    # Preserve the real path component of full URLs while ignoring the host.
    for url in urls:
        try:
            _, resource = _rp._normalize_url(url)
        except (TypeError, ValueError):
            continue
        path = resource.split("?", 1)[0]
        if path and path != "/":
            paths.add(path.casefold())

    return paths


def validate_model_response(
    *,
    message: str,
    response: str,
    scenario: Any,
    evidence_delta_count: int,
):
    """Remove only URL-parser false positives from endpoint validation."""
    result = _previous_validate(
        message=message,
        response=response,
        scenario=scenario,
        evidence_delta_count=evidence_delta_count,
    )
    reasons = list(result.reasons)

    if "unobserved_endpoint_mentioned" in reasons:
        scenario_facts = "\n".join(getattr(scenario, "observed_facts", []) or [])
        factual_context = f"{message}\n{scenario_facts}"
        observed = _route_paths(factual_context)
        response_paths = _route_paths(response)
        truly_unobserved = response_paths - observed

        # If the only mismatch came from parsing a URL authority as a route, the
        # guard is a false positive. Real invented route paths remain blocked.
        if not truly_unobserved:
            reasons.remove("unobserved_endpoint_mentioned")

    reasons = list(dict.fromkeys(reasons))
    loop_guard = result.loop_guard
    if not reasons and loop_guard == "replan_required":
        loop_guard = "clear"
    elif reasons and loop_guard == "clear":
        loop_guard = "replan_required"

    return _rp.ValidationResult(
        valid=not reasons,
        reasons=tuple(reasons),
        loop_guard=loop_guard,
        proposed_action_fingerprint=result.proposed_action_fingerprint,
        command_count=result.command_count,
    )
