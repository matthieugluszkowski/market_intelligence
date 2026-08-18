"""Execution des neuf controles qualite (lot L3).

Usage :
    python scripts/quality_checks.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from market_intelligence.jobs.quality_checks import run  # noqa: E402

if __name__ == "__main__":
    run()
    raise SystemExit(0)
