"""Cycle d'actualisation, lance par le cron toutes les 8 heures (lot L7).

Chaque etape porte son intervalle minimal : les cours a chaque passage, les
operations sur titre une fois par jour, les comptes une fois par mois. Le cycle
ne relance que ce qui a vieilli, en relisant `ingestion_runs`.

Sortie : 0 si tout est passe, 1 des qu'une etape echoue - pour qu'un cron puisse
alerter.

Usage :
    python scripts/cycle.py
    python scripts/cycle.py --force                    # ignore les intervalles
    python scripts/cycle.py --only compute_fits        # une etape, repetable
    python scripts/cycle.py --plan                     # ce qui tournerait, sans rien lancer
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from market_intelligence.jobs.cycle import (  # noqa: E402
    ETAPES, age_en_clair, derniers_succes, doit_tourner, run,
)


def plan() -> int:
    maintenant = datetime.now(timezone.utc)
    derniers = derniers_succes([e.nom for e in ETAPES])
    print(f"{'etape':<26} {'cadence':>14} {'age':>10}   ce passage-ci")
    for etape in ETAPES:
        dernier = derniers.get(etape.nom)
        age = maintenant - dernier if dernier else None
        tourne, motif = doit_tourner(etape, dernier, maintenant)
        cadence = "chaque passage" if not etape.intervalle else age_en_clair(etape.intervalle)
        print(f"{etape.nom:<26} {cadence:>14} "
              f"{'jamais' if age is None else age_en_clair(age):>10}   "
              f"{'oui' if tourne else 'non'}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true",
                        help="ignore les intervalles minimaux")
    parser.add_argument("--only", action="append", default=[],
                        help="n'executer que cette etape, repetable")
    parser.add_argument("--plan", action="store_true",
                        help="afficher ce qui tournerait, sans rien lancer")
    args = parser.parse_args()

    if args.plan:
        return plan()

    resume = run(force=args.force, seulement=tuple(args.only))
    return 1 if resume["echecs"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
