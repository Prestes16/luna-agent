"""Compatibility entry point for the real V3 Golden Test runner."""

from __future__ import annotations

import asyncio
import sys

from tests.run_reasoning_pipeline_v3 import main


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(asyncio.run(main()))
