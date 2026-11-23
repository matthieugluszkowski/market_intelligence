"""Gestion de l'antichambre et du delistage des titres surcotes.

Usage :
    python scripts/manage_parking.py list
    python scripts/manage_parking.py delist                      # deliste z > 2.5
    python scripts/manage_parking.py delist --dry-run            # simulation sans modif
    python scripts/manage_parking.py check                       # verification live hebdo (seuil reentry: 1.0)
    python scripts/manage_parking.py add --symbol KER.PA         # ajout d'un candidat leger
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from market_intelligence.jobs.parking import (  # noqa: E402
    SEUIL_DELIST_PAR_DEFAUT,
    SEUIL_REENTRY_PAR_DEFAUT,
    add_candidate,
    check_parked_live,
    delist_overvalued,
    list_parked,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", help="Commande a executer")

    # list
    subparsers.add_parser("list", help="Affiche les titres en antichambre")

    # delist
    p_delist = subparsers.add_parser("delist", help="Deliste les titres avec z-score > seuil")
    p_delist.add_argument("--threshold", type=float, default=SEUIL_DELIST_PAR_DEFAUT, help="Seuil de delistage (defaut: 2.5)")
    p_delist.add_argument("--dry-run", action="store_true", help="Simule sans modifier la base")

    # check
    p_check = subparsers.add_parser("check", help="Surveillance live spot et reintegration des titres qualifies")
    p_check.add_argument("--threshold", type=float, default=SEUIL_REENTRY_PAR_DEFAUT, help="Seuil de retour au screener (defaut: 1.0)")
    p_check.add_argument("--no-auto-restore", action="store_true", help="Ne pas reintegrer automatiquement les titres qualifies")

    # add
    p_add = subparsers.add_parser("add", help="Ajoute un candidat en antichambre sans alourdir la base")
    p_add.add_argument("--symbol", type=str, required=True, help="Symbole yfinance (ex: KER.PA, MC.PA)")
    p_add.add_argument("--name", type=str, default=None, help="Nom de l'entreprise (optionnel)")
    p_add.add_argument("--threshold", type=float, default=SEUIL_REENTRY_PAR_DEFAUT, help="Seuil d'eligibilite")

    args = parser.parse_args()

    if args.command == "list":
        parked = list_parked()
        if not parked:
            print("Aucun titre en antichambre.")
            return 0
        print(f"\n{'CODE':<16} {'SYMBOLE':<10} {'NOM':<30} {'STATUT':<10} {'Z_PARC':>7} {'Z_LIVE':>7} {'COURS':>8}   {'DERNIER CONTROLE'}")
        print("-" * 105)
        for p in parked:
            z_p = f"{p['z_parking']:+.2f}" if p['z_parking'] is not None else "-"
            z_l = f"{p['z_live']:+.2f}" if p['z_live'] is not None else "-"
            prix = f"{p['live_price']:.2f} {p['currency']}" if p['live_price'] is not None else "-"
            dt_ctrl = p['last_checked'].strftime("%Y-%m-%d %H:%M") if p['last_checked'] else "jamais"
            print(f"{p['code']:<16} {p['symbol']:<10} {p['name'][:28]:<30} {p['status']:<10} {z_p:>7} {z_l:>7} {prix:>8}   {dt_ctrl}")
        return 0

    elif args.command == "delist":
        delist_overvalued(z_threshold=args.threshold, dry_run=args.dry_run)
        return 0

    elif args.command == "check":
        check_parked_live(z_reentry_threshold=args.threshold, auto_restore=not args.no_auto_restore)
        return 0

    elif args.command == "add":
        add_candidate(symbol=args.symbol, name=args.name, z_reentry_threshold=args.threshold)
        return 0

    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
