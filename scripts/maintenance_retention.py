"""Maintenance et politique de retention du stockage (Option 1).

Permet de respecter la limite des 500 Mo du tier gratuit Supabase en purgeant
les donnees historiques intermediaires non necessaires au screener et a la fiche :

1. `regression_fits` : conserve les 30 derniers jours au pas quotidien, et 1 fit
   par semaine (le vendredi) pour les semaines anterieures. Protege systematiquement
   tous les fits references par le portefeuille (`positions.fit_id`).
2. `data_quality_issues` : purge les anomalies resolues automatiquement depuis plus
   de 7 jours (40 000+ trous 'gap' historises lors du backfill). Conserve toutes
   les anomalies ouvertes et toutes les resolutions manuelles avec leurs notes.
3. `external_briefs` : conserve la depeche / consensus / notation la plus recente
   de chaque type pour chaque instrument, ainsi que les collectes des 7 derniers jours.
4. `VACUUM FULL` : compacte les tables et index pour restituer l'espace disque a l'OS.

Usage :
    python scripts/maintenance_retention.py --dry-run
    python scripts/maintenance_retention.py --apply
    python scripts/maintenance_retention.py --apply --days-fits 14
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from market_intelligence.db import connect_direct, fetch_all, fetch_one  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("maintenance")

QUOTA_MB = 500.0


def db_size_mb() -> float:
    row = fetch_one("SELECT pg_database_size(current_database());")
    return (row[0] / (1024 * 1024)) if row else 0.0


def get_table_sizes(tables: list[str]) -> dict[str, dict]:
    sql = """
    SELECT
        relname,
        n_live_tup,
        pg_total_relation_size(relid) as total_bytes,
        pg_size_pretty(pg_total_relation_size(relid)) as pretty_size
    FROM pg_stat_user_tables
    WHERE relname = any(%s);
    """
    rows = fetch_all(sql, (tables,))
    return {
        r[0]: {
            "rows": r[1],
            "bytes": r[2],
            "mb": r[2] / (1024 * 1024),
            "pretty": r[3],
        }
        for r in rows
    }


def dry_run(days_fits: int, days_issues: int, days_briefs: int) -> None:
    print("=" * 70)
    print("  SIMULATION DE LA MAINTENANCE ET RETENTION (DRY-RUN)")
    print("=" * 70)

    taille_actuelle = db_size_mb()
    print(f"\nTaille actuelle de la base : {taille_actuelle:.1f} Mo / {QUOTA_MB} Mo ({taille_actuelle / QUOTA_MB * 100:.1f}%)")
    print(f"Espace restant            : {QUOTA_MB - taille_actuelle:.1f} Mo\n")

    with connect_direct() as conn, conn.cursor() as cur:
        # 1. regression_fits
        cur.execute(
            """
            SELECT count(*)
              FROM regression_fits f
             WHERE f.as_of_date < current_date - (%s || ' days')::interval
               AND EXTRACT(DOW FROM f.as_of_date) != 5
               AND f.id NOT IN (SELECT fit_id FROM positions WHERE fit_id IS NOT NULL);
            """,
            (days_fits,),
        )
        fits_to_delete = cur.fetchone()[0]

        cur.execute("SELECT count(*) FROM regression_fits;")
        fits_total = cur.fetchone()[0]

        # 2. data_quality_issues
        cur.execute(
            """
            SELECT count(*)
              FROM data_quality_issues
             WHERE resolved_kind = 'auto'
               AND resolved_at < current_date - (%s || ' days')::interval;
            """,
            (days_issues,),
        )
        issues_to_delete = cur.fetchone()[0]

        cur.execute("SELECT count(*) FROM data_quality_issues;")
        issues_total = cur.fetchone()[0]

        # 3. external_briefs
        cur.execute(
            """
            SELECT count(*)
              FROM external_briefs b
             WHERE b.collected_on < current_date - (%s || ' days')::interval
               AND b.id NOT IN (
                   SELECT DISTINCT ON (instrument_id, kind) id
                     FROM external_briefs
                    ORDER BY instrument_id, kind, collected_on DESC, collected_at DESC
               );
            """,
            (days_briefs,),
        )
        briefs_to_delete = cur.fetchone()[0]

        cur.execute("SELECT count(*) FROM external_briefs;")
        briefs_total = cur.fetchone()[0]

    print("Elements a purger :")
    print(f"  - regression_fits      : {fits_to_delete:,} lignes sur {fits_total:,} (conserve {days_fits}j quotidiens + vendredi hebdo)")
    print(f"  - data_quality_issues  : {issues_to_delete:,} lignes sur {issues_total:,} (auto-resolues > {days_issues}j)")
    print(f"  - external_briefs      : {briefs_to_delete:,} lignes sur {briefs_total:,} (historique depeches > {days_briefs}j)")

    cibles = ["regression_fits", "data_quality_issues", "external_briefs", "bars_1w", "adjustment_factors", "shares_outstanding"]
    sizes = get_table_sizes(cibles)
    print("\nTaille actuelle des tables cibles :")
    for t in cibles:
        info = sizes.get(t, {"rows": 0, "pretty": "0 Mo"})
        print(f"  {t:<22} : {info['pretty']:>10} ({info['rows']:,} lignes)")

    est_gain_fits = (fits_to_delete / max(fits_total, 1)) * sizes.get("regression_fits", {}).get("mb", 50)
    est_gain_issues = (issues_to_delete / max(issues_total, 1)) * sizes.get("data_quality_issues", {}).get("mb", 18)
    est_gain_briefs = (briefs_to_delete / max(briefs_total, 1)) * sizes.get("external_briefs", {}).get("mb", 10)
    gain_estime_total = est_gain_fits + est_gain_issues + est_gain_briefs + 5.0  # + bloat

    print(f"\nGain de place estime apres VACUUM FULL : ~{gain_estime_total:.1f} Mo")
    print(f"Taille projetee : ~{taille_actuelle - gain_estime_total:.1f} Mo (soit ~{(taille_actuelle - gain_estime_total) / QUOTA_MB * 100:.1f}% du quota)")
    print(f"Marge projetee  : ~{QUOTA_MB - (taille_actuelle - gain_estime_total):.1f} Mo")
    print("\nPour executer reellement le nettoyage :")
    print("    python scripts/maintenance_retention.py --apply")


def apply_cleanup(days_fits: int, days_issues: int, days_briefs: int, skip_vacuum: bool = False) -> None:
    print("=" * 70)
    print("  EXECUTION DE LA MAINTENANCE ET RETENTION")
    print("=" * 70)

    taille_initiale = db_size_mb()
    print(f"\nTaille initiale : {taille_initiale:.2f} Mo")

    cibles = ["regression_fits", "data_quality_issues", "external_briefs", "bars_1w", "adjustment_factors", "shares_outstanding"]
    sizes_init = get_table_sizes(cibles)

    t0 = time.time()
    with connect_direct(autocommit=False) as conn:
        with conn.cursor() as cur:
            # 1. regression_fits
            print(f"\n[1/3] Purge de regression_fits (> {days_fits} jours, hors vendredis et hors positions)...")
            cur.execute(
                """
                DELETE FROM regression_fits f
                 WHERE f.as_of_date < current_date - (%s || ' days')::interval
                   AND EXTRACT(DOW FROM f.as_of_date) != 5
                   AND f.id NOT IN (SELECT fit_id FROM positions WHERE fit_id IS NOT NULL);
                """,
                (days_fits,),
            )
            del_fits = cur.rowcount
            print(f"      -> {del_fits:,} lignes supprimees dans regression_fits.")

            # 2. data_quality_issues
            print(f"[2/3] Purge de data_quality_issues (auto-resolues > {days_issues} jours)...")
            cur.execute(
                """
                DELETE FROM data_quality_issues
                 WHERE resolved_kind = 'auto'
                   AND resolved_at < current_date - (%s || ' days')::interval;
                """,
                (days_issues,),
            )
            del_issues = cur.rowcount
            print(f"      -> {del_issues:,} lignes supprimees dans data_quality_issues.")

            # 3. external_briefs
            print(f"[3/3] Purge de external_briefs (> {days_briefs} jours, hors dernier etat)...")
            cur.execute(
                """
                DELETE FROM external_briefs b
                 WHERE b.collected_on < current_date - (%s || ' days')::interval
                   AND b.id NOT IN (
                       SELECT DISTINCT ON (instrument_id, kind) id
                         FROM external_briefs
                        ORDER BY instrument_id, kind, collected_on DESC, collected_at DESC
                   );
                """,
                (days_briefs,),
            )
            del_briefs = cur.rowcount
            print(f"      -> {del_briefs:,} lignes supprimees dans external_briefs.")

        conn.commit()
        print(f"\nTransaction validee en {time.time() - t0:.2f} s. Total supprime : {del_fits + del_issues + del_briefs:,} lignes.")

    if not skip_vacuum:
        print("\n" + "-" * 70)
        print("  COMPACTION VACUUM FULL DES TABLES ET INDEX")
        print("-" * 70)
        tables_to_vacuum = [
            "data_quality_issues",
            "external_briefs",
            "regression_fits",
            "shares_outstanding",
            "adjustment_factors",
            "bars_1w",
        ]
        with connect_direct(autocommit=True) as conn:
            with conn.cursor() as cur:
                for table in tables_to_vacuum:
                    t_vac = time.time()
                    print(f"  VACUUM FULL {table}...", end="", flush=True)
                    cur.execute(f"VACUUM FULL {table};")
                    print(f" termine en {time.time() - t_vac:.2f} s.")

    taille_finale = db_size_mb()
    gain_mb = taille_initiale - taille_finale
    sizes_final = get_table_sizes(cibles)

    print("\n" + "=" * 70)
    print("  BILAN APRES MAINTENANCE")
    print("=" * 70)
    print(f"\nTaille initiale : {taille_initiale:.2f} Mo ({taille_initiale / QUOTA_MB * 100:.1f}%)")
    print(f"Taille finale   : {taille_finale:.2f} Mo ({taille_finale / QUOTA_MB * 100:.1f}%)")
    print(f"Espace libere   : {gain_mb:+.2f} Mo")
    print(f"Marge restante  : {QUOTA_MB - taille_finale:.2f} Mo ({(QUOTA_MB - taille_finale) / QUOTA_MB * 100:.1f}%)")

    print("\nEvolution des tables :")
    for t in cibles:
        before = sizes_init.get(t, {"pretty": "-", "rows": 0})
        after = sizes_final.get(t, {"pretty": "-", "rows": 0})
        print(f"  {t:<22} : {before['pretty']:>8} ({before['rows']:>7,} lig) -> {after['pretty']:>8} ({after['rows']:>7,} lig)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="applique reellement les suppressions et VACUUM FULL")
    parser.add_argument("--dry-run", action="store_true", help="simule la purge sans modifier la base (defaut)")
    parser.add_argument("--days-fits", type=int, default=30, help="jours de fits quotidiens a conserver (defaut: 30)")
    parser.add_argument("--days-issues", type=int, default=7, help="jours d'anomalies auto-resolues a conserver (defaut: 7)")
    parser.add_argument("--days-briefs", type=int, default=7, help="jours de depeches a conserver (defaut: 7)")
    parser.add_argument("--skip-vacuum", action="store_true", help="ne pas executer VACUUM FULL apres suppression")

    args = parser.parse_args()

    if args.apply:
        apply_cleanup(args.days_fits, args.days_issues, args.days_briefs, args.skip_vacuum)
    else:
        dry_run(args.days_fits, args.days_issues, args.days_briefs)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
