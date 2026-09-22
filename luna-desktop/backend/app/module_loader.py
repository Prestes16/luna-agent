"""Safe, read-only loader for Luna runtime instruction modules."""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Dict, Iterable, Optional


logger = logging.getLogger(__name__)

DEFAULT_CONFIG_DIR = Path(r"D:\LunaCyber\config")
DEFAULT_MODULES = {
    "mentor_kali_devtools": "module_mentor_kali_devtools.md",
}
_SAFE_MODULE_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


class ModuleLoader:
    """Load Markdown modules without executing or modifying their content."""

    def __init__(
        self,
        config_dir: Optional[str | Path] = None,
        *,
        max_module_bytes: int = 256 * 1024,
    ) -> None:
        configured = config_dir or os.getenv("LUNA_CONFIG_DIR") or DEFAULT_CONFIG_DIR
        self.config_dir = Path(configured).expanduser().resolve()
        self.modules_dir = (self.config_dir / "modules").resolve()
        self.max_module_bytes = max_module_bytes

    def _resolve_module_path(self, module_id: str) -> Optional[Path]:
        if not _SAFE_MODULE_ID.fullmatch(module_id):
            logger.warning("Rejected invalid Luna module id: %r", module_id)
            return None

        filename = DEFAULT_MODULES.get(module_id, f"module_{module_id}.md")
        candidate = (self.modules_dir / filename).resolve()
        try:
            candidate.relative_to(self.modules_dir)
        except ValueError:
            logger.warning("Rejected Luna module path outside modules dir: %s", candidate)
            return None

        if candidate.suffix.lower() != ".md":
            logger.warning("Rejected non-Markdown Luna module: %s", candidate)
            return None
        return candidate

    def list_modules(self) -> list[str]:
        if not self.modules_dir.is_dir():
            return []

        modules: list[str] = []
        for candidate in sorted(self.modules_dir.glob("module_*.md")):
            try:
                resolved = candidate.resolve()
                resolved.relative_to(self.modules_dir)
            except (OSError, ValueError):
                logger.warning("Ignoring unsafe Luna module path: %s", candidate)
                continue
            if resolved.is_file():
                modules.append(resolved.name)
        return modules

    def module_exists(self, module_id: str) -> bool:
        path = self._resolve_module_path(module_id)
        return bool(path and path.is_file())

    def load_module(self, module_id: str) -> Optional[str]:
        path = self._resolve_module_path(module_id)
        if not path or not path.is_file():
            logger.info("Luna module not found: %s", module_id)
            return None

        try:
            size = path.stat().st_size
            if size > self.max_module_bytes:
                logger.warning(
                    "Luna module %s exceeds the %d-byte limit",
                    path.name,
                    self.max_module_bytes,
                )
                return None
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            logger.warning("Could not read Luna module %s: %s", path, exc)
            return None

        logger.info("Loaded Luna module: %s (%d chars)", path.name, len(content))
        return content

    def load_enabled(self, module_ids: Iterable[str]) -> Dict[str, str]:
        loaded: Dict[str, str] = {}
        for module_id in module_ids:
            content = self.load_module(module_id)
            if content:
                loaded[module_id] = content
        return loaded

    @staticmethod
    def extract_section(content: str, heading: str) -> Optional[str]:
        """Return one Markdown section by heading, stopping at the next heading."""
        pattern = re.compile(
            rf"(?ms)^#{{1,6}}\s+{re.escape(heading)}\s*$\n(.*?)(?=^#{{1,6}}\s|\Z)",
            re.IGNORECASE,
        )
        match = pattern.search(content)
        return match.group(1).strip() if match else None

    @staticmethod
    def relevant_excerpt(content: str, query: str, max_chars: int = 4_000) -> str:
        """Select a small, predictable Markdown excerpt for the current request."""
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
            if token not in {"para", "como", "quero", "estou", "uma", "qual"}
        }

        ranked: list[tuple[int, int]] = []
        for index, section in enumerate(sections[2:], start=2):
            heading, _, body = section.partition("\n")
            heading_cf = heading.casefold()
            body_cf = body.casefold()
            score = sum(
                5 if token in heading_cf else 1 if token in body_cf else 0
                for token in query_tokens
            )
            if score:
                ranked.append((score, index))

        ranked_indexes = [
            index for _, index in sorted(ranked, key=lambda item: (-item[0], item[1]))
        ]
        core_headings = ("scenario gate",)
        foundational_indexes = [0]
        foundational_indexes.extend(
            index
            for index, section in enumerate(sections)
            if any(marker in section.partition("\n")[0].casefold() for marker in core_headings)
        )
        selected_indexes = foundational_indexes + ranked_indexes

        excerpt_parts: list[str] = []
        remaining = max_chars
        for index in selected_indexes:
            section = sections[index]
            if section in excerpt_parts:
                continue
            if len(section) + 2 <= remaining:
                excerpt_parts.append(section)
                remaining -= len(section) + 2
            elif remaining > 200:
                excerpt_parts.append(section[:remaining].rstrip())
                remaining = 0
            if remaining <= 0:
                break

        return "\n\n".join(excerpt_parts) or content[:max_chars]
