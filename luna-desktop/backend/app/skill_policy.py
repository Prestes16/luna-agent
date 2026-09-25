"""Cost-aware exact admission optimizer for Luna procedural Agent Skills.

The router discovers relevant candidates. This module chooses the best bounded
subset for prompt injection. It never grants tool or execution authority.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from itertools import combinations
from typing import Mapping

from .skill_loader import SkillDefinition
from .skill_router import SkillCandidate, SkillRouteDecision


_COST_UNITS = {
    "low": 1,
    "medium": 2,
    "high": 3,
}

_RELEVANCE_WEIGHT = 100
_CONTEXT_COST_WEIGHT = 20
_EXPLICIT_BONUS = 100_000
_COMPLEMENT_BONUS = 200


@dataclass(frozen=True)
class SkillAdmissionRecord:
    name: str
    admitted: bool
    reasons: tuple[str, ...]
    route_score: int
    context_cost: str
    context_units: int
    utility: int


@dataclass(frozen=True)
class SkillAdmissionDecision:
    admitted_skills: tuple[str, ...]
    records: tuple[SkillAdmissionRecord, ...]
    objective_value: int = 0
    context_units: int = 0

    @property
    def rejected(self) -> tuple[SkillAdmissionRecord, ...]:
        return tuple(record for record in self.records if not record.admitted)

    def rejection_reasons(self) -> tuple[str, ...]:
        return tuple(
            f"{record.name}:{reason}"
            for record in self.rejected
            for reason in record.reasons
        )


@dataclass(frozen=True)
class _EligibleCandidate:
    candidate: SkillCandidate
    skill: SkillDefinition
    context_cost: str
    context_units: int
    utility: int


class SkillAdmissionPolicy:
    """Choose the highest-utility feasible subset exactly.

    Candidate count is intentionally small (the router defaults to <= 6) and
    active skills are bounded to <= 2. Therefore exhaustive subset evaluation
    is both cheaper and more predictable than a greedy heuristic.

    Automatic subset objective:

        U(S) = sum(100 * relevance_score
                   + priority
                   - 20 * context_units)
               + 200 * complementary_pairs

    Explicit operator selections receive a large deterministic bonus and
    suppress automatic companions. Hard constraints remain authoritative:
    max active skills, prerequisites, evidence gates, exclusive groups and
    context budget. None of these controls affect execution authority.
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

    @staticmethod
    def _split_names(value: str | None) -> tuple[str, ...]:
        if not value:
            return ()
        return tuple(
            part.strip().casefold()
            for part in re.split(r"[,;\n]+", str(value))
            if part.strip()
        )

    def _utility(
        self,
        candidate: SkillCandidate,
        context_units: int,
    ) -> int:
        return (
            candidate.score * _RELEVANCE_WEIGHT
            + candidate.priority
            - context_units * _CONTEXT_COST_WEIGHT
            + (_EXPLICIT_BONUS if candidate.explicit else 0)
        )

    def _pair_bonus(
        self,
        left: _EligibleCandidate,
        right: _EligibleCandidate,
    ) -> int:
        left_complements = self._split_names(
            (left.skill.metadata or {}).get("luna-complements")
        )
        right_complements = self._split_names(
            (right.skill.metadata or {}).get("luna-complements")
        )
        if (
            right.candidate.name.casefold() in left_complements
            or left.candidate.name.casefold() in right_complements
        ):
            return _COMPLEMENT_BONUS
        return 0

    @staticmethod
    def _exclusive_group(entry: _EligibleCandidate) -> str:
        return str(
            (entry.skill.metadata or {}).get("luna-exclusive-group", "")
        ).strip().casefold()

    def _subset_feasible(
        self,
        subset: tuple[_EligibleCandidate, ...],
        *,
        explicit_mode: bool,
    ) -> bool:
        if len(subset) > self.max_active_skills:
            return False

        if not explicit_mode:
            if sum(item.context_units for item in subset) > self.max_context_units:
                return False
            groups = [
                self._exclusive_group(item)
                for item in subset
                if self._exclusive_group(item)
            ]
            if len(groups) != len(set(groups)):
                return False

        return True

    def _subset_metric(
        self,
        subset: tuple[_EligibleCandidate, ...],
    ) -> tuple[int, int, int, int]:
        pair_bonus = sum(
            self._pair_bonus(left, right)
            for left, right in combinations(subset, 2)
        )
        objective = sum(item.utility for item in subset) + pair_bonus
        relevance = sum(item.candidate.score for item in subset)
        context_units = sum(item.context_units for item in subset)
        # Higher objective/relevance wins. Lower context and fewer skills win
        # exact ties, preventing unnecessary prompt expansion.
        return (
            objective,
            relevance,
            -context_units,
            -len(subset),
        )

    def admit(
        self,
        route: SkillRouteDecision,
        skills: Mapping[str, SkillDefinition],
        *,
        evidence_delta_count: int = 0,
    ) -> SkillAdmissionDecision:
        pre_rejected: dict[str, SkillAdmissionRecord] = {}
        eligible: list[_EligibleCandidate] = []

        for candidate in route.candidates:
            skill = skills.get(candidate.name)
            if skill is None:
                pre_rejected[candidate.name] = SkillAdmissionRecord(
                    name=candidate.name,
                    admitted=False,
                    reasons=("skill_not_loaded",),
                    route_score=candidate.score,
                    context_cost="medium",
                    context_units=_COST_UNITS["medium"],
                    utility=0,
                )
                continue

            metadata = dict(skill.metadata or {})
            cost = self._context_cost(metadata)
            units = _COST_UNITS[cost]
            utility = self._utility(candidate, units)
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

            if reasons:
                pre_rejected[candidate.name] = SkillAdmissionRecord(
                    name=candidate.name,
                    admitted=False,
                    reasons=tuple(reasons),
                    route_score=candidate.score,
                    context_cost=cost,
                    context_units=units,
                    utility=utility,
                )
                continue

            eligible.append(_EligibleCandidate(
                candidate=candidate,
                skill=skill,
                context_cost=cost,
                context_units=units,
                utility=utility,
            ))

        explicit_entries = [item for item in eligible if item.candidate.explicit]
        explicit_mode = bool(explicit_entries)

        if explicit_mode:
            optimization_pool = explicit_entries
            suppressed = {
                item.candidate.name
                for item in eligible
                if not item.candidate.explicit
            }
        else:
            optimization_pool = eligible
            suppressed = set()

        best_subset: tuple[_EligibleCandidate, ...] = ()
        best_metric = self._subset_metric(best_subset)

        upper = min(self.max_active_skills, len(optimization_pool))
        for size in range(1, upper + 1):
            for subset in combinations(optimization_pool, size):
                if not self._subset_feasible(
                    subset,
                    explicit_mode=explicit_mode,
                ):
                    continue
                metric = self._subset_metric(subset)
                if metric > best_metric:
                    best_subset = subset
                    best_metric = metric

        selected_names = {item.candidate.name for item in best_subset}
        selected_groups = {
            self._exclusive_group(item)
            for item in best_subset
            if self._exclusive_group(item)
        }
        selected_context = sum(item.context_units for item in best_subset)

        records: list[SkillAdmissionRecord] = []
        eligible_by_name = {
            item.candidate.name: item
            for item in eligible
        }

        for candidate in route.candidates:
            if candidate.name in pre_rejected:
                records.append(pre_rejected[candidate.name])
                continue

            item = eligible_by_name[candidate.name]
            if candidate.name in selected_names:
                records.append(SkillAdmissionRecord(
                    name=candidate.name,
                    admitted=True,
                    reasons=(
                        "explicit_operator_selection"
                        if candidate.explicit
                        else "exact_optimizer_selected"
                    ,),
                    route_score=candidate.score,
                    context_cost=item.context_cost,
                    context_units=item.context_units,
                    utility=item.utility,
                ))
                continue

            reasons: list[str] = []
            if candidate.name in suppressed:
                reasons.append("manual_selection_suppresses_auto_companion")
            else:
                group = self._exclusive_group(item)
                if group and group in selected_groups and not candidate.explicit:
                    reasons.append(f"exclusive_group_conflict:{group}")

                if (
                    not explicit_mode
                    and selected_context + item.context_units > self.max_context_units
                ):
                    reasons.append("optimizer_context_budget_tradeoff")

                if len(best_subset) >= self.max_active_skills:
                    reasons.append("optimizer_max_active_skills_tradeoff")

                if not reasons:
                    reasons.append("optimizer_higher_utility_subset")

            records.append(SkillAdmissionRecord(
                name=candidate.name,
                admitted=False,
                reasons=tuple(reasons),
                route_score=candidate.score,
                context_cost=item.context_cost,
                context_units=item.context_units,
                utility=item.utility,
            ))

        return SkillAdmissionDecision(
            admitted_skills=tuple(
                item.candidate.name for item in best_subset
            ),
            records=tuple(records),
            objective_value=best_metric[0],
            context_units=selected_context,
        )

    def public_policy(self) -> dict[str, object]:
        return {
            "optimizer": "exact_subset_enumeration",
            "max_active_skills": self.max_active_skills,
            "max_context_units": self.max_context_units,
            "cost_units": dict(_COST_UNITS),
            "objective": (
                "sum(100*relevance + priority - 20*context_units "
                "+ explicit_bonus) + 200*complementary_pairs"
            ),
            "relevance_weight": _RELEVANCE_WEIGHT,
            "context_cost_weight": _CONTEXT_COST_WEIGHT,
            "explicit_bonus": _EXPLICIT_BONUS,
            "complement_bonus": _COMPLEMENT_BONUS,
            "explicit_selection_suppresses_auto_companions": True,
            "explicit_selection_overrides_context_budget": True,
            "explicit_selection_overrides_max_active_skills": False,
            "changes_execution_authority": False,
        }
