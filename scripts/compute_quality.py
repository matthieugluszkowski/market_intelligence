"""Calcul de la couche qualite et ecriture historisee (lot L6b).

Usage :
    python scripts/compute_quality.py
    python scripts/compute_quality.py --as-of 2026-06-30
    python scripts/compute_quality.py --only EQ:FR:SEB
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from market_intelligence.jobs.compute_quality import run  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", default="")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--only", default="")
    args = parser.parse_args()
    as_of = date.fromisoformat(args.as_of) if args.as_of else None
    resume = run(as_of=as_of, limit=args.limit, only=args.only)
    return 1 if resume["failed_instruments"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
