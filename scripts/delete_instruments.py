"""Suppression definitive d'instruments et de toutes leurs donnees derivees.

Il n'y a pas de corbeille : les FK vers `instruments` sont en NO ACTION, donc
supprimer un instrument impose de supprimer d'abord ses barres, ses fits, ses
fondamentaux. Ce script le fait dans l'ordre topologique, en une transaction.

L'ordre n'est pas negociable :
  - `financial_facts` avant `financial_reports` (facts.report_id -> reports.id) ;
  - `screener_snapshots` et `positions` avant `quality_scores` et
    `regression_fits`, qu'ils referencent par id.

Passe le fichier de sauvegarde en argument obligatoire : reconstruire un
instrument supprime sans son `attributes` d'origine est impossible.

Usage :
    python scripts/delete_instruments.py --codes-fichier cibles.txt --dry-run
    python scripts/delete_instruments.py --codes-fichier cibles.txt --confirmer
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from market_intelligence.db import connect_direct  # noqa: E402

# Ordre topologique : chaque table ne doit plus etre referencee quand on l'atteint.
ORDRE = [
    "financial_facts",
    "financial_reports",
    "screener_snapshots",
    "positions",
    "quality_scores",
    "regression_fits",
    "adjustment_factors",
    "bars",
    "bars_1d",
    "bars_1w",
    "bars_1mo",
    "corporate_actions",
    "data_quality_issues",
    "external_briefs",
    "external_sources",
    "market_analyses",
    "moat_assessments",
    "peer_group_members",
    "shares_outstanding",
    "watchlist",
    "instrument_symbols",
]

CIBLES = "select id from instruments where internal_code = any(%s)"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codes-fichier", type=Path, required=True,
                        help="Fichier texte, un internal_code par ligne")
    parser.add_argument("--dry-run", action="store_true",
                        help="Compte et annule (rollback) sans rien supprimer")
    parser.add_argument("--confirmer", action="store_true",
                        help="Valide la suppression definitive")
    args = parser.parse_args()

    if not args.dry_run and not args.confirmer:
        parser.error("suppression definitive : passer --confirmer (ou --dry-run)")

    codes = [c.strip() for c in args.codes_fichier.read_text(encoding="utf-8").splitlines()
             if c.strip() and not c.startswith("#")]
    print(f"{len(codes)} codes demandes")

    with connect_direct() as conn, conn.cursor() as cur:
        cur.execute("select internal_code, name from instruments "
                    "where internal_code = any(%s) order by internal_code", (codes,))
        trouves = cur.fetchall()
        manquants = set(codes) - {c for c, _ in trouves}
        print(f"{len(trouves)} trouves en base")
        if manquants:
            print(f"  ABSENTS (ignores) : {sorted(manquants)}")

        # Garde-fou : un instrument survivant ne doit pas referencer un
        # quality_score ou un fit appartenant a une cible.
        for table, col, cible in (("positions", "quality_score_id", "quality_scores"),
                                  ("positions", "fit_id", "regression_fits"),
                                  ("screener_snapshots", "quality_score_id", "quality_scores"),
                                  ("screener_snapshots", "fit_id", "regression_fits")):
            cur.execute(
                f"select count(*) from {table} t where t.{col} in "
                f"(select id from {cible} where instrument_id in ({CIBLES})) "
                f"and t.instrument_id not in ({CIBLES})", (codes, codes))
            orphelins = cur.fetchone()[0]
            if orphelins:
                print(f"  ARRET : {orphelins} lignes {table}.{col} d'instruments "
                      f"conserves pointent vers {cible} d'instruments cibles.")
                conn.rollback()
                return 1

        total = 0
        for table in ORDRE:
            cur.execute(f"delete from {table} where instrument_id in ({CIBLES})", (codes,))
            if cur.rowcount:
                print(f"  {table:24} {cur.rowcount:>8}")
                total += cur.rowcount

        cur.execute(f"delete from index_memberships where index_id in ({CIBLES}) "
                    f"or member_id in ({CIBLES})", (codes, codes))
        if cur.rowcount:
            print(f"  {'index_memberships':24} {cur.rowcount:>8}")
            total += cur.rowcount

        cur.execute("delete from instruments where internal_code = any(%s)", (codes,))
        supprimes = cur.rowcount
        print(f"  {'instruments':24} {supprimes:>8}")

        if args.dry_run:
            conn.rollback()
            print(f"\nDRY-RUN : {total} lignes derivees + {supprimes} instruments. "
                  f"Transaction annulee, rien n'a ete supprime.")
        else:
            conn.commit()
            print(f"\nSUPPRIME : {total} lignes derivees + {supprimes} instruments.")

        cur.execute("select count(*) from instruments")
        print(f"Instruments restants en base : {cur.fetchone()[0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
