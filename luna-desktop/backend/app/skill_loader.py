"""Read-only Agent Skills loader for the Luna Cyber local runtime.

The loader understands the interoperable `SKILL.md` format without granting
any execution authority. `allowed-tools` is parsed as descriptive metadata
only; Luna's harness and supervised executor remain the sole authority gates.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

logger = logging.getLogger(__name__)

DEFAULT_SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"
_SAFE_SKILL_NAME = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
_MAX_SKILL_BYTES = 256 * 1024


class SkillValidationError(ValueError):
    """Raised when a local skill does not satisfy Luna's safe subset."""


@dataclass(frozen=True)
class SkillDefinition:
    name: str
    description: str
    body: str
    path: Path
    license: str | None = None
    compatibility: str | None = None
    metadata: Mapping[str, str] | None = None
    allowed_tools: tuple[str, ...] = ()

    def public_metadata(self) -> dict[str, Any]:
        metadata = dict(self.metadata or {})
        return {
            "name": self.name,
            "description": self.description,
            "license": self.license,
            "compatibility": self.compatibility,
            "metadata": metadata,
            "allowed_tools_declared": list(self.allowed_tools),
            "allowed_tools_authoritative": False,
        }


def _strip_scalar(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Parse Luna's non-executable scalar subset of Agent Skills frontmatter."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise SkillValidationError("SKILL.md must start with YAML frontmatter")

    closing = next(
        (index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---"),
        None,
    )
    if closing is None:
        raise SkillValidationError("SKILL.md frontmatter is not closed")

    frontmatter = lines[1:closing]
    data: dict[str, Any] = {}
    index = 0
    while index < len(frontmatter):
        raw = frontmatter[index]
        if not raw.strip() or raw.lstrip().startswith("#"):
            index += 1
            continue
        if raw[:1].isspace() or ":" not in raw:
            raise SkillValidationError(f"unsupported frontmatter line: {raw!r}")

        key, raw_value = raw.split(":", 1)
        key = key.strip()
        value = raw_value.strip()

        if key == "metadata":
            if value:
                raise SkillValidationError("metadata must be a mapping")
            metadata: dict[str, str] = {}
            index += 1
            while index < len(frontmatter):
                child = frontmatter[index]
                if not child.strip() or child.lstrip().startswith("#"):
                    index += 1
                    continue
                if not child[:1].isspace():
                    break
                child_text = child.strip()
                if ":" not in child_text:
                    raise SkillValidationError(
                        f"unsupported metadata line: {child!r}"
                    )
                child_key, child_value = child_text.split(":", 1)
                metadata[child_key.strip()] = _strip_scalar(child_value)
                index += 1
            data[key] = metadata
            continue

        if value in {">", "|"}:
            style = value
            block: list[str] = []
            index += 1
            while index < len(frontmatter):
                child = frontmatter[index]
                if child.strip() and not child[:1].isspace():
                    break
                block.append(child.strip())
                index += 1
            data[key] = (
                " ".join(part for part in block if part)
                if style == ">"
                else "\n".join(block).strip()
            )
            continue

        data[key] = _strip_scalar(value)
        index += 1

    body = "\n".join(lines[closing + 1 :]).strip()
    return data, body


def _validate_name(name: str) -> None:
    if (
        not name
        or len(name) > 64
        or "--" in name
        or not _SAFE_SKILL_NAME.fullmatch(name)
    ):
        raise SkillValidationError(f"invalid Agent Skill name: {name!r}")


class SkillLoader:
    """Discover and load local skills without executing skill content."""

    def __init__(
        self,
        skills_dir: str | Path | None = None,
        *,
        max_skill_bytes: int = _MAX_SKILL_BYTES,
    ) -> None:
        configured = Path(skills_dir) if skills_dir is not None else DEFAULT_SKILLS_DIR
        self.skills_dir = configured.expanduser().resolve()
        self.max_skill_bytes = max(1024, int(max_skill_bytes))

    def _resolve_skill_dir(self, skill_name: str) -> Path | None:
        try:
            _validate_name(skill_name)
        except SkillValidationError:
            logger.warning("Rejected invalid Luna skill name: %r", skill_name)
            return None
        candidate = (self.skills_dir / skill_name).resolve()
        try:
            candidate.relative_to(self.skills_dir)
        except ValueError:
            logger.warning("Rejected Luna skill path outside skills dir: %s", candidate)
            return None
        return candidate

    def list_skill_names(self) -> list[str]:
        if not self.skills_dir.is_dir():
            return []
        names: list[str] = []
        for candidate in sorted(self.skills_dir.iterdir()):
            if not candidate.is_dir():
                continue
            try:
                _validate_name(candidate.name)
            except SkillValidationError:
                continue
            if (candidate / "SKILL.md").is_file():
                names.append(candidate.name)
        return names

    def skill_exists(self, skill_name: str) -> bool:
        candidate = self._resolve_skill_dir(skill_name)
        return bool(candidate and (candidate / "SKILL.md").is_file())

    def load_skill(self, skill_name: str) -> SkillDefinition | None:
        skill_dir = self._resolve_skill_dir(skill_name)
        if skill_dir is None:
            return None
        skill_path = skill_dir / "SKILL.md"
        if not skill_path.is_file():
            return None

        try:
            size = skill_path.stat().st_size
            if size > self.max_skill_bytes:
                raise SkillValidationError(
                    f"{skill_name} exceeds {self.max_skill_bytes} bytes"
                )
            content = skill_path.read_text(encoding="utf-8")
            frontmatter, body = _parse_frontmatter(content)
        except (OSError, UnicodeError, SkillValidationError) as exc:
            logger.warning("Rejected Luna skill %s: %s", skill_name, exc)
            return None

        name = str(frontmatter.get("name", "")).strip()
        description = str(frontmatter.get("description", "")).strip()
        try:
            _validate_name(name)
            if name != skill_dir.name:
                raise SkillValidationError(
                    f"skill name {name!r} does not match directory {skill_dir.name!r}"
                )
            if not description or len(description) > 1024:
                raise SkillValidationError("description must contain 1-1024 characters")
            compatibility = frontmatter.get("compatibility")
            if compatibility is not None and not (1 <= len(str(compatibility)) <= 500):
                raise SkillValidationError("compatibility must contain 1-500 characters")
            metadata = frontmatter.get("metadata") or {}
            if not isinstance(metadata, dict):
                raise SkillValidationError("metadata must be a mapping")
            if any(
                not isinstance(key, str) or not isinstance(value, str)
                for key, value in metadata.items()
            ):
                raise SkillValidationError("metadata keys and values must be strings")
        except SkillValidationError as exc:
            logger.warning("Rejected Luna skill %s: %s", skill_name, exc)
            return None

        allowed_tools = tuple(
            token
            for token in str(frontmatter.get("allowed-tools", "")).split()
            if token
        )
        return SkillDefinition(
            name=name,
            description=description,
            body=body,
            path=skill_path,
            license=(
                str(frontmatter["license"]).strip()
                if frontmatter.get("license") is not None
                else None
            ),
            compatibility=(
                str(frontmatter["compatibility"]).strip()
                if frontmatter.get("compatibility") is not None
                else None
            ),
            metadata=dict(metadata),
            allowed_tools=allowed_tools,
        )

    def load_all(self) -> dict[str, SkillDefinition]:
        loaded: dict[str, SkillDefinition] = {}
        for skill_name in self.list_skill_names():
            skill = self.load_skill(skill_name)
            if skill is not None:
                loaded[skill.name] = skill
        return loaded

    def load_enabled(self, skill_names: Iterable[str]) -> dict[str, SkillDefinition]:
        loaded: dict[str, SkillDefinition] = {}
        for skill_name in skill_names:
            skill = self.load_skill(str(skill_name))
            if skill is not None:
                loaded[skill.name] = skill
        return loaded

    @staticmethod
    def relevant_excerpt(
        skill: SkillDefinition,
        query: str,
        *,
        max_chars: int = 1_800,
    ) -> str:
        """Return a bounded procedural excerpt; never treat it as authority."""
        content = skill.body.strip()
        if len(content) <= max_chars:
            return content

        sections = [
            section.strip()
            for section in re.split(r"(?m)(?=^#{1,3}\s)", content)
            if section.strip()
        ]
        if not sections:
            return content[:max_chars]

        query_tokens = {
            token
            for token in re.findall(r"[a-z0-9_-]{4,}", query.casefold())
            if token not in {
                "para", "como", "quero", "uma", "qual", "with", "from", "that"
            }
        }
        foundational_markers = (
            "operating contract",
            "contrato operacional",
            "when to use",
            "quando usar",
            "workflow",
            "fluxo",
        )
        ranked: list[tuple[int, int]] = []
        for index, section in enumerate(sections):
            heading, _, body = section.partition("\n")
            heading_cf = heading.casefold()
            body_cf = body.casefold()
            score = sum(
                5 if token in heading_cf else 1 if token in body_cf else 0
                for token in query_tokens
            )
            if any(marker in heading_cf for marker in foundational_markers):
                score += 12
            if index == 0:
                score += 20
            ranked.append((score, index))

        selected = [
            index
            for _, index in sorted(ranked, key=lambda item: (-item[0], item[1]))
        ]
        parts: list[str] = []
        remaining = max(400, int(max_chars))
        seen: set[int] = set()
        for index in selected:
            if index in seen:
                continue
            seen.add(index)
            section = sections[index]
            if len(section) + 2 <= remaining:
                parts.append(section)
                remaining -= len(section) + 2
            elif remaining > 180:
                parts.append(section[:remaining].rstrip())
                remaining = 0
            if remaining <= 0:
                break
        return "\n\n".join(parts) or content[:max_chars]
