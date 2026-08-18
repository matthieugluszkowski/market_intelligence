"""Export Parquet de la couche froide (lot L2).

Usage :
    python scripts/export_cold.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from market_intelligence.jobs.export_cold import run  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(0 if run() else 1)
