"""Calcul des regressions et ecriture historisee dans regression_fits (lot L4).

Usage :
    python scripts/compute_fits.py
    python scripts/compute_fits.py --as-of 2024-06-30    # rejouer une date passee
    python scripts/compute_fits.py --only EQ:FR:SEB
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from market_intelligence.jobs.compute_fits import run  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", default="", help="date de calcul (AAAA-MM-JJ)")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--only", default="")
    args = parser.parse_args()

    as_of = date.fromisoformat(args.as_of) if args.as_of else None
    resume = run(as_of=as_of, limit=args.limit, only=args.only)
    for f in resume["failed_instruments"]:
        print(f"  echec {f['internal_code']} : {f['reason']}")
    return 1 if resume["failed_instruments"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
