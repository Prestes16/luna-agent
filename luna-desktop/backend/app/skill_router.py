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
    """Select a bounded set of enabled procedural skills.

    Current-turn intent dominates routing. Scenario context can satisfy a
    prerequisite (for example an already-confirmed finding) but cannot
    auto-activate an otherwise unrelated skill by itself.
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

        ranked: list[tuple[int, int, int, str, tuple[str, ...]]] = []
        for name, skill in skills.items():
            metadata = dict(skill.metadata or {})
            explicit_forms = (
                f"/skill {name.casefold()}",
                f"skill:{name.casefold()}",
                name.casefold(),
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

                # Weak continuity signal only. It may rank a skill that already
                # matched the current message, never activate one on its own.
                context_hits = self._hits(
                    scenario,
                    self._split_terms(metadata.get("luna-context-triggers")),
                )
                if current_hits and context_hits:
                    score += min(6, 2 * len(context_hits))
                    reasons.extend(
                        f"context_trigger={term}" for term in context_hits[:3]
                    )

            if score >= self.activation_threshold:
                ranked.append((
                    1 if explicit else 0,
                    self._priority(skill),
                    score,
                    name,
                    tuple(reasons),
                ))

        # Manual selection always wins. Otherwise a narrow specialist with a
        # higher Luna priority stays ahead of a generic skill that matched more
        # words in the same request.
        ranked.sort(key=lambda item: (-item[0], -item[1], -item[2], item[3]))
        selected = ranked[: self.max_skills]
        return SkillRouteDecision(
            selected_skills=tuple(item[3] for item in selected),
            reasons=tuple(
                f"{item[3]}:{reason}"
                for item in selected
                for reason in item[4]
            ),
        )
