"""Charge le referentiel de l'univers en base (lot L1).

Ne charge que ce qui a ete verifie : la source est le rapport produit par
`verify_universe.py`, et toute ligne en statut `rejete` est ecartee. C'est la
regle qui donne son sens au lot L1 - un mapping faux ne se voit jamais ensuite.

Seuls les symboles effectivement eprouves par un telechargement entrent dans
`instrument_symbols`. Les symboles Stooq restent dans le CSV de l'univers tant
qu'ils ne sont pas verifiables : les inscrire non verifies reviendrait a fabriquer
la confiance qu'on cherche justement a etablir.

Usage :
    python scripts/verify_universe.py && python scripts/load_universe.py
    python scripts/load_universe.py --dry-run
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from market_intelligence.db import connect_direct  # noqa: E402

REPORT_CSV = ROOT / "db" / "seeds" / "universe_50_verification.csv"

UPSERT_INSTRUMENT = """
insert into instruments
  (isin, internal_code, asset_class, name, exchange_code, currency,
   sector_code, country_iso2, is_active, attributes)
values (%(isin)s, %(internal_code)s, 'equity', %(name)s, %(exchange_code)s,
        %(currency)s, %(sector_code)s, %(country_iso2)s, true, %(attributes)s)
on conflict (internal_code) do update set
  isin = excluded.isin,
  name = excluded.name,
  exchange_code = excluded.exchange_code,
  currency = excluded.currency,
  sector_code = excluded.sector_code,
  country_iso2 = excluded.country_iso2,
  attributes = excluded.attributes,
  updated_at = now()
returning id;
"""

UPSERT_SYMBOL = """
insert into instrument_symbols (instrument_id, source_id, symbol, is_primary)
values (%(instrument_id)s, %(source_id)s, %(symbol)s, true)
on conflict (source_id, symbol, valid_from) do update set
  instrument_id = excluded.instrument_id,
  is_primary = excluded.is_primary;
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="n'ecrit rien")
    args = parser.parse_args()

    if not REPORT_CSV.exists():
        print(f"Rapport de verification absent : {REPORT_CSV}\n"
              f"Lancer d'abord : python scripts/verify_universe.py")
        return 1

    rows = list(csv.DictReader(REPORT_CSV.open(encoding="utf-8")))
    loadable = [r for r in rows if r["status"] != "rejete"]
    rejected = [r for r in rows if r["status"] == "rejete"]

    print(f"{len(rows)} lignes verifiees : {len(loadable)} chargeables, {len(rejected)} ecartees")
    for r in rejected:
        print(f"  ecarte {r['internal_code']:<20} {r['yfinance_symbol']:<10} {r['reasons']}")
    if args.dry_run:
        return 0

    with connect_direct() as conn:
        with conn.cursor() as cur:
            cur.execute("select id from data_sources where code = 'yfinance'")
            row = cur.fetchone()
            if row is None:
                print("Source 'yfinance' absente de data_sources : rejouer les seeds.")
                return 1
            yfinance_source_id = row[0]

            for r in loadable:
                attributes = {
                    "verification": {
                        "source": "yfinance",
                        "status": r["status"],
                        "reasons": r["reasons"],
                        "n_obs_weekly": int(r["n_obs"]),
                        "history_years": float(r["years"]),
                        "first_bar": r["first"],
                        "last_bar": r["last"],
                        "last_close": float(r["last_close"]) if r["last_close"] else None,
                        "reported_name": r["reported_name"],
                    },
                    "stooq_symbol_unverified": r["stooq_symbol"] or None,
                }
                if r["notes"]:
                    attributes["notes"] = r["notes"]

                cur.execute(UPSERT_INSTRUMENT, {
                    "isin": r["isin"], "internal_code": r["internal_code"], "name": r["name"],
                    "exchange_code": r["exchange_code"], "currency": r["currency"],
                    "sector_code": r["sector_code"], "country_iso2": r["country_iso2"],
                    "attributes": json.dumps(attributes, ensure_ascii=False),
                })
                instrument_id = cur.fetchone()[0]
                cur.execute(UPSERT_SYMBOL, {
                    "instrument_id": instrument_id,
                    "source_id": yfinance_source_id,
                    "symbol": r["yfinance_symbol"],
                })
        conn.commit()

        with conn.cursor() as cur:
            cur.execute("select count(*) from instruments")
            n_instruments = cur.fetchone()[0]
            cur.execute("select count(*) from instrument_symbols")
            n_symbols = cur.fetchone()[0]
            cur.execute(
                "select isin, count(*) from instruments where isin is not null "
                "group by isin having count(*) > 1"
            )
            dupes = cur.fetchall()
            cur.execute(
                """
                select i.country_iso2, count(*)
                  from instruments i group by i.country_iso2 order by 2 desc
                """
            )
            by_country = cur.fetchall()

    print(f"\n{n_instruments} instruments, {n_symbols} symboles verifies en base.")
    print("Repartition par pays : " + ", ".join(f"{c}={n}" for c, n in by_country))
    if dupes:
        print(f"!!! DOUBLONS D'ISIN : {dupes}")
        return 1
    print("Zero doublon d'ISIN.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
