"""Deterministic router for Luna procedural Agent Skills."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping

from .skill_loader import SkillDefinition


@dataclass(frozen=True)
class SkillRouteDecision:
    selected_skills: tuple[str, ...]
    reasons: tuple[str, ...]


class SkillRouter:
    """Select a small set of enabled skills from explicit metadata.

    Routing is deliberately deterministic. Skills cannot self-authorize tools or
    host actions; this class only decides which procedural instructions may be
    added to model context.
    """

    def __init__(self, *, max_skills: int = 2, activation_threshold: int = 10) -> None:
        self.max_skills = max(1, int(max_skills))
        self.activation_threshold = max(1, int(activation_threshold))

    @staticmethod
    def _truthy(value: str | None) -> bool:
        return str(value or "").strip().casefold() in {"1", "true", "yes", "on"}

    @staticmethod
    def _split_terms(value: str | None) -> tuple[str, ...]:
        if not value:
            return ()
        return tuple(
            part.strip().casefold()
            for part in re.split(r"[,;\n]+", value)
            if part.strip()
        )

    @staticmethod
    def _priority(skill: SkillDefinition) -> int:
        try:
            return int((skill.metadata or {}).get("luna-priority", "0"))
        except (TypeError, ValueError):
            return 0

    def select(
        self,
        message: str,
        skills: Mapping[str, SkillDefinition],
        *,
        scenario_context: str = "",
    ) -> SkillRouteDecision:
        normalized_message = str(message or "").casefold()
        normalized_context = f"{normalized_message}\n{scenario_context.casefold()}"

        ranked: list[tuple[int, int, str, tuple[str, ...]]] = []
        for name, skill in skills.items():
            metadata = dict(skill.metadata or {})
            if not self._truthy(metadata.get("luna-auto-activate")):
                continue

            score = 0
            reasons: list[str] = []
            explicit_forms = {
                name.casefold(),
                f"/skill {name.casefold()}",
                f"skill:{name.casefold()}",
            }
            if any(form in normalized_message for form in explicit_forms):
                score += 100
                reasons.append("explicit_skill_request")

            trigger_terms = self._split_terms(metadata.get("luna-triggers"))
            for term in trigger_terms:
                if term and term in normalized_context:
                    score += 10
                    reasons.append(f"trigger={term}")

            exclude_terms = self._split_terms(metadata.get("luna-exclude-triggers"))
            excluded = [term for term in exclude_terms if term in normalized_message]
            if excluded:
                score = 0
                reasons.append(f"excluded={excluded[0]}")

            if score >= self.activation_threshold:
                ranked.append((score, self._priority(skill), name, tuple(reasons)))

        ranked.sort(key=lambda item: (-item[0], -item[1], item[2]))
        selected = ranked[: self.max_skills]
        return SkillRouteDecision(
            selected_skills=tuple(item[2] for item in selected),
            reasons=tuple(
                f"{item[2]}:{reason}"
                for item in selected
                for reason in item[3]
            ),
        )
