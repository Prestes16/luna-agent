"""Fourth-stage reasoning hardening: quantitative quality gate.

The earlier stages catch concrete parser and semantic failures.  This stage adds
an instruction-fidelity score so several individually small mistakes cannot pass
just because no single regex guard fired.
"""

from __future__ import annotations

from typing import Any

from . import reasoning_pipeline as _rp
from .reasoning_quality import build_operator_contract, score_response_quality
from .reasoning_runtime_patch_v3 import (
    build_replan_instruction as _previous_build_replan,
    validate_model_response as _previous_validate,
)

_COMMAND_QUALITY_THRESHOLD = 0.62


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
    quality = score_response_quality(message, response, reasons)

    # Apply the quantitative gate only when the operator explicitly asked for an
    # executable command.  Normal teaching/conversation should not be forced into
    # command-shaped responses.
    if (
        quality.contract.wants_command
        and quality.total < _COMMAND_QUALITY_THRESHOLD
        and "quality_gate_below_threshold" not in reasons
    ):
        reasons.append("quality_gate_below_threshold")

    reasons = list(dict.fromkeys(reasons))
    loop_guard = result.loop_guard
    if not reasons and loop_guard == "replan_required":
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
    base = _previous_build_replan(validation, scenario_prompt, current_message)
    contract = build_operator_contract(current_message)
    if not contract.active:
        return base

    requirements: list[str] = []
    if contract.requested_tool:
        requirements.append(
            f"ferramenta solicitada={contract.requested_tool}; use exatamente essa ferramenta e o nome canônico"
        )
    if contract.target_hosts:
        requirements.append(
            "target(s) factual(is)=" + ", ".join(contract.target_hosts) + "; não altere o host"
        )
    if contract.requested_tool == "nmap" and contract.target_hosts:
        requirements.append(
            "para Nmap, passe hostname/IP/CIDR como alvo; não passe http://, https:// ou path"
        )
    if contract.wants_command:
        requirements.append("a entrega pedida é um comando executável, não uma ferramenta diferente ou pseudocomando")
    if contract.one_command:
        requirements.append("forneça exatamente um comando")
    if contract.wants_bash:
        requirements.append("use bloco ```bash``` para o comando")
    if contract.operator_executes:
        requirements.append("o operador executará o comando; não alegue execução ou resultado ainda não observado")

    if "quality_gate_below_threshold" in set(validation.reasons):
        requirements.append(
            "a resposta anterior falhou no gate quantitativo de fidelidade; priorize ferramenta, target, executabilidade e fatos acima de floreio"
        )

    return base + "\n\nCONTRATO OPERACIONAL:\n" + "\n".join(
        f"- {item}." for item in requirements
    )
