"""Ingestion des operations sur titre et calcul des facteurs d ajustement (lot L3).

Usage :
    python scripts/ingest_corporate_actions.py
    python scripts/ingest_corporate_actions.py --only EQ:FR:AIRLIQUIDE
    python scripts/ingest_corporate_actions.py --limit 5
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from market_intelligence.jobs.ingest_corporate_actions import run  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--only", default="")
    args = parser.parse_args()

    summary = run(limit=args.limit, only=args.only)
    failed = summary["failed_instruments"]
    print(f"\n{len(summary['instruments'])} instruments traites, {len(failed)} echecs")
    for f in failed:
        print(f"  {f['internal_code']} : {f['reason']}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
