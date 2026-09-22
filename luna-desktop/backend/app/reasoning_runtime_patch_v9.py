"""Ninth-stage hardening: deterministic repair of mechanically fixable commands.

V8 identifies missing privilege elevation and missing scan artifacts.  Those two
properties are deterministic and should not consume another LLM attempt.  V9
therefore accepts only those fixable policy gaps when a target-verified rewrite
can resolve them.  All factual, target, tool and strategy guards remain active.
"""

from __future__ import annotations

from typing import Any

from . import reasoning_pipeline as _rp
from .command_policy import assess_command_policy
from .operational_transform import transform_response_commands
from .reasoning_runtime_patch_v8 import (
    build_replan_instruction as _previous_build_replan,
    extract_commands,
    validate_model_response as _previous_validate,
)

_FIXABLE_POLICY_REASONS = {
    "nmap_privileged_mode_missing_sudo",
    "nmap_scan_artifact_missing",
}


def _can_repair_operationally(message: str, response: str) -> bool:
    commands = extract_commands(response)
    if not commands:
        return False

    # We only auto-repair Nmap commands whose target is already verified by the
    # deterministic operator contract.  A target mismatch is never rewritten.
    for command in commands:
        assessment = assess_command_policy(message, command)
        if assessment.effective_tool != "nmap" or not assessment.target_verified:
            return False

    transformed, mutations = transform_response_commands(message, response)
    if not mutations or transformed == response:
        return False

    # The transformed form must satisfy both privilege and artifact policy.
    for command in extract_commands(transformed):
        assessment = assess_command_policy(message, command)
        if assessment.effective_tool == "nmap":
            if assessment.requires_elevation and not assessment.has_sudo:
                return False
            if assessment.artifact_required and not assessment.artifact_present:
                return False
            if assessment.expected_targets and not assessment.target_verified:
                return False
    return True


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
    reasons = list(result.reasons)

    if reasons and set(reasons).issubset(_FIXABLE_POLICY_REASONS) and _can_repair_operationally(message, response):
        reasons = []

    loop_guard = result.loop_guard
    if not reasons and loop_guard in {"replan_required", "blocked_repeat"}:
        loop_guard = "clear"
    elif reasons and loop_guard in {"clear", "retest_allowed"}:
        loop_guard = "replan_required"

    return _rp.ValidationResult(
        valid=not reasons,
        reasons=tuple(reasons),
        loop_guard=loop_guard,
        proposed_action_fingerprint=result.proposed_action_fingerprint,
        command_count=result.command_count,
    )


def build_replan_instruction(validation, scenario_prompt: str, current_message: str = "") -> str:
    # Non-fixable failures still use the complete V8/V7 replan stack.
    return _previous_build_replan(validation, scenario_prompt, current_message)
