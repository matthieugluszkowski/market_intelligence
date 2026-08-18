"""Backfill des cours (lot L2).

Usage :
    python scripts/backfill_prices.py                    # hebdo + quotidien, tout l'univers
    python scripts/backfill_prices.py --freq 1w
    python scripts/backfill_prices.py --only EQ:FR:SEB
    python scripts/backfill_prices.py --limit 3
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from market_intelligence.jobs.backfill_prices import run  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freq", action="append", choices=["1w", "1d", "1mo"],
                        help="frequence a charger, repetable (defaut : 1w puis 1d)")
    parser.add_argument("--limit", type=int, default=0, help="n'traiter que les N premiers")
    parser.add_argument("--only", default="", help="un internal_code ou un symbole")
    args = parser.parse_args()

    summary = run(freqs=tuple(args.freq or ("1w", "1d")), limit=args.limit, only=args.only)
    failed = summary["failed_instruments"]
    print(f"\n{len(summary['instruments'])} instruments traites, {len(failed)} echecs")
    for f in failed:
        print(f"  {f['internal_code']} {f['freq']} : {f['reason']}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
