"""Admission gate for Luna procedural Agent Skills.

The router discovers relevant candidates. This policy decides whether a candidate
is worth injecting into the current prompt. It does not grant tool or execution
authority; it only controls context admission.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .skill_loader import SkillDefinition
from .skill_router import SkillRouteDecision


_COST_UNITS = {
    "low": 1,
    "medium": 2,
    "high": 3,
}


@dataclass(frozen=True)
class SkillAdmissionRecord:
    name: str
    admitted: bool
    reasons: tuple[str, ...]
    route_score: int
    context_cost: str


@dataclass(frozen=True)
class SkillAdmissionDecision:
    admitted_skills: tuple[str, ...]
    records: tuple[SkillAdmissionRecord, ...]

    @property
    def rejected(self) -> tuple[SkillAdmissionRecord, ...]:
        return tuple(record for record in self.records if not record.admitted)

    def rejection_reasons(self) -> tuple[str, ...]:
        return tuple(
            f"{record.name}:{reason}"
            for record in self.rejected
            for reason in record.reasons
        )


class SkillAdmissionPolicy:
    """Apply bounded, explainable admission after relevance routing.

    Admission optimizes for useful procedural context:
    - explicit operator selection has precedence;
    - automatic use must clear a relevance threshold;
    - high-context skills need stronger intent unless the skill overrides it;
    - mutually exclusive capability groups do not auto-stack;
    - the per-turn skill count and context budget are hard bounds.

    Nothing in this class changes AgentHarness, ExecutionIntent, or executor
    permissions.
    """

    def __init__(
        self,
        *,
        max_active_skills: int = 2,
        max_context_units: int = 5,
    ) -> None:
        self.max_active_skills = max(1, int(max_active_skills))
        self.max_context_units = max(1, int(max_context_units))

    @staticmethod
    def _int_metadata(
        metadata: Mapping[str, str],
        key: str,
        default: int,
    ) -> int:
        try:
            return int(metadata.get(key, str(default)))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _context_cost(metadata: Mapping[str, str]) -> str:
        value = str(metadata.get("luna-context-cost", "medium")).strip().casefold()
        return value if value in _COST_UNITS else "medium"

    @staticmethod
    def _default_min_score(cost: str) -> int:
        return {"low": 10, "medium": 10, "high": 20}[cost]

    def admit(
        self,
        route: SkillRouteDecision,
        skills: Mapping[str, SkillDefinition],
        *,
        evidence_delta_count: int = 0,
    ) -> SkillAdmissionDecision:
        admitted: list[str] = []
        records: list[SkillAdmissionRecord] = []
        used_groups: set[str] = set()
        used_context_units = 0

        for candidate in route.candidates:
            skill = skills.get(candidate.name)
            if skill is None:
                records.append(SkillAdmissionRecord(
                    name=candidate.name,
                    admitted=False,
                    reasons=("skill_not_loaded",),
                    route_score=candidate.score,
                    context_cost="medium",
                ))
                continue

            metadata = dict(skill.metadata or {})
            cost = self._context_cost(metadata)
            cost_units = _COST_UNITS[cost]
            reasons: list[str] = []

            admission_mode = str(
                metadata.get("luna-admission", "on-demand")
            ).strip().casefold()
            if admission_mode not in {"on-demand", "evidence", "explicit-only"}:
                admission_mode = "on-demand"

            if admission_mode == "explicit-only" and not candidate.explicit:
                reasons.append("explicit_selection_required")

            min_score = self._int_metadata(
                metadata,
                "luna-auto-min-score",
                self._default_min_score(cost),
            )
            if not candidate.explicit and candidate.score < min_score:
                reasons.append(
                    f"insufficient_relevance:{candidate.score}<{min_score}"
                )

            min_evidence = self._int_metadata(
                metadata,
                "luna-min-evidence-delta",
                0,
            )
            if (
                admission_mode == "evidence"
                and not candidate.explicit
                and evidence_delta_count <= 0
                and min_evidence <= 0
            ):
                min_evidence = 1
            if (
                min_evidence > 0
                and not candidate.explicit
                and evidence_delta_count < min_evidence
            ):
                reasons.append(
                    f"insufficient_current_evidence:{evidence_delta_count}<{min_evidence}"
                )

            group = str(metadata.get("luna-exclusive-group", "")).strip().casefold()
            if group and group in used_groups and not candidate.explicit:
                reasons.append(f"exclusive_group_already_active:{group}")

            if len(admitted) >= self.max_active_skills:
                reasons.append("max_active_skills_reached")

            # Explicit operator selection may exceed the soft context budget but
            # never the hard max_active_skills bound.
            if (
                not candidate.explicit
                and used_context_units + cost_units > self.max_context_units
            ):
                reasons.append(
                    f"context_budget_exceeded:{used_context_units}+{cost_units}>{self.max_context_units}"
                )

            if reasons:
                records.append(SkillAdmissionRecord(
                    name=candidate.name,
                    admitted=False,
                    reasons=tuple(reasons),
                    route_score=candidate.score,
                    context_cost=cost,
                ))
                continue

            admitted.append(candidate.name)
            used_context_units += cost_units
            if group:
                used_groups.add(group)
            records.append(SkillAdmissionRecord(
                name=candidate.name,
                admitted=True,
                reasons=(
                    "explicit_operator_selection"
                    if candidate.explicit
                    else "relevance_and_policy_passed",
                ),
                route_score=candidate.score,
                context_cost=cost,
            ))

        return SkillAdmissionDecision(
            admitted_skills=tuple(admitted),
            records=tuple(records),
        )

    def public_policy(self) -> dict[str, object]:
        return {
            "max_active_skills": self.max_active_skills,
            "max_context_units": self.max_context_units,
            "cost_units": dict(_COST_UNITS),
            "explicit_selection_overrides_context_budget": True,
            "explicit_selection_overrides_max_active_skills": False,
            "changes_execution_authority": False,
        }
