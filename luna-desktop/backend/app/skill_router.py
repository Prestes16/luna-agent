"""Deterministic relevance router for Luna procedural Agent Skills."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping

from .skill_loader import SkillDefinition


@dataclass(frozen=True)
class SkillCandidate:
    name: str
    score: int
    priority: int
    explicit: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class SkillRouteDecision:
    candidates: tuple[SkillCandidate, ...]

    @property
    def selected_skills(self) -> tuple[str, ...]:
        """Backward-compatible candidate names before admission."""
        return tuple(candidate.name for candidate in self.candidates)

    @property
    def reasons(self) -> tuple[str, ...]:
        return tuple(
            f"{candidate.name}:{reason}"
            for candidate in self.candidates
            for reason in candidate.reasons
        )


class SkillRouter:
    """Discover a bounded candidate set from current-turn intent.

    This class ranks relevance only. A separate SkillAdmissionPolicy decides
    whether a candidate is worth injecting into the model context.
    """

    def __init__(
        self,
        *,
        max_candidates: int = 6,
        activation_threshold: int = 10,
    ) -> None:
        self.max_candidates = max(1, int(max_candidates))
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
    def _hits(text: str, terms: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(term for term in terms if term and term in text)

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
        current = str(message or "").casefold()
        scenario = str(scenario_context or "").casefold()
        combined = f"{current}\n{scenario}"

        ranked: list[SkillCandidate] = []
        for name, skill in skills.items():
            metadata = dict(skill.metadata or {})
            explicit_forms = (
                f"/skill {name.casefold()}",
                f"skill:{name.casefold()}",
            )
            explicit = any(form in current for form in explicit_forms)
            auto_enabled = self._truthy(metadata.get("luna-auto-activate"))

            if not explicit and not auto_enabled:
                continue

            reasons: list[str] = []
            score = 0

            if explicit:
                score = 100
                reasons.append("explicit_skill_request")
            else:
                excluded = self._hits(
                    current,
                    self._split_terms(metadata.get("luna-exclude-triggers")),
                )
                if excluded:
                    continue

                requires_current = self._split_terms(
                    metadata.get("luna-requires-current-any")
                )
                if requires_current and not self._hits(current, requires_current):
                    continue

                requires_any = self._split_terms(metadata.get("luna-requires-any"))
                if requires_any and not self._hits(combined, requires_any):
                    continue

                current_hits = self._hits(
                    current,
                    self._split_terms(metadata.get("luna-triggers")),
                )
                for term in current_hits:
                    score += 10
                    reasons.append(f"current_trigger={term}")

                # Scenario context is continuity only. It may strengthen a
                # current match but can never activate a skill by itself.
                context_hits = self._hits(
                    scenario,
                    self._split_terms(metadata.get("luna-context-triggers")),
                )
                if current_hits and context_hits:
                    bonus = min(6, 2 * len(context_hits))
                    score += bonus
                    reasons.extend(
                        f"context_trigger={term}" for term in context_hits[:3]
                    )

            if score >= self.activation_threshold:
                ranked.append(SkillCandidate(
                    name=name,
                    score=score,
                    priority=self._priority(skill),
                    explicit=explicit,
                    reasons=tuple(reasons),
                ))

        ranked.sort(
            key=lambda item: (
                -int(item.explicit),
                -item.priority,
                -item.score,
                item.name,
            )
        )
        return SkillRouteDecision(
            candidates=tuple(ranked[: self.max_candidates]),
        )
