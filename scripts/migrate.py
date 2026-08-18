"""Applique les migrations DDL puis les seeds du referentiel.

Idempotent : chaque fichier de db/migrations/ n'est joue qu'une fois (suivi dans
`schema_migrations`) ; les seeds sont ecrits en `on conflict do update` et sont
donc rejouables a volonte.

Usage :
    python scripts/migrate.py            # migrations + seeds
    python scripts/migrate.py --no-seeds
    python scripts/migrate.py --status
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from market_intelligence.db import connect_direct  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = ROOT / "db" / "migrations"
SEEDS_DIR = ROOT / "db" / "seeds"

BOOTSTRAP = """
create table if not exists schema_migrations (
  filename    text primary key,
  checksum    text not null,
  applied_at  timestamptz not null default now()
);
"""


def _checksum(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _applied(conn) -> dict[str, str]:
    with conn.cursor() as cur:
        cur.execute("select filename, checksum from schema_migrations")
        return dict(cur.fetchall())


def run_migrations(conn) -> int:
    applied = _applied(conn)
    count = 0
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        sql = path.read_text(encoding="utf-8")
        checksum = _checksum(sql)
        if path.name in applied:
            if applied[path.name] != checksum:
                print(
                    f"  ! {path.name} : deja appliquee mais le fichier a change "
                    f"({applied[path.name]} -> {checksum}). "
                    f"Creer une nouvelle migration plutot que de modifier celle-ci."
                )
            else:
                print(f"  = {path.name}")
            continue
        with conn.cursor() as cur:
            cur.execute(sql)
            cur.execute(
                "insert into schema_migrations (filename, checksum) values (%s, %s)",
                (path.name, checksum),
            )
        conn.commit()
        print(f"  + {path.name}")
        count += 1
    return count


def run_seeds(conn) -> int:
    count = 0
    for path in sorted(SEEDS_DIR.glob("*.sql")):
        with conn.cursor() as cur:
            cur.execute(path.read_text(encoding="utf-8"))
        conn.commit()
        print(f"  ~ {path.name}")
        count += 1
    return count


def show_status(conn) -> None:
    tables = [
        "regression_policies", "asset_classes", "currencies", "exchanges", "sectors",
        "data_sources", "financial_concepts", "instruments", "instrument_symbols",
        "bars_1w", "bars_1d", "corporate_actions", "shares_outstanding", "fx_rates",
        "financial_facts", "regression_fits", "quality_scores", "peer_groups",
        "moat_assessments", "screener_snapshots", "data_quality_issues", "ingestion_runs",
    ]
    print("\nEtat des tables :")
    with conn.cursor() as cur:
        cur.execute(
            "select table_name from information_schema.tables where table_schema = 'public'"
        )
        existing = {row[0] for row in cur.fetchall()}
        for table in tables:
            if table not in existing:
                print(f"  {table:<24} ABSENTE")
                continue
            cur.execute(f"select count(*) from {table}")  # noqa: S608 - liste en dur
            print(f"  {table:<24} {cur.fetchone()[0]:>8} lignes")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-seeds", action="store_true", help="ne pas rejouer les seeds")
    parser.add_argument("--status", action="store_true", help="afficher l'etat et sortir")
    args = parser.parse_args()

    with connect_direct() as conn:
        if args.status:
            show_status(conn)
            return 0

        with conn.cursor() as cur:
            cur.execute(BOOTSTRAP)
        conn.commit()

        print("Migrations :")
        n_mig = run_migrations(conn)

        n_seed = 0
        if not args.no_seeds:
            print("Seeds :")
            n_seed = run_seeds(conn)

        print(f"\n{n_mig} migration(s) appliquee(s), {n_seed} seed(s) rejoue(s).")
        show_status(conn)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
