"""Ingestion des fondamentaux, regime A (lot L6)."""

from __future__ import annotations

import logging

from ..collectors.yfinance_fundamentals import fetch_fundamentals
from ..config import get_settings
from ..db import connect_direct
from ..loaders.fundamentals import upsert_facts
from ..loaders.journal import ingestion_run
from ..normalizers.fundamentals import normalize

logger = logging.getLogger(__name__)

INSTRUMENTS = """
select i.id, i.internal_code, i.currency, s.symbol
  from instruments i
  join instrument_symbols s
    on s.instrument_id = i.id and s.source_id = %(source_id)s and s.is_primary
 where i.is_active
   and (select supports_fundamentals from asset_classes
         where code = i.asset_class)
 order by i.internal_code;
"""

MAPPINGS = """
select source_label, concept_code from concept_mappings where source_id = %(source_id)s;
"""


def run(limit: int = 0, only: str = "") -> dict:
    settings = get_settings()
    resume: dict = {"instruments": {}, "failed_instruments": []}

    with connect_direct() as conn:
        with conn.cursor() as cur:
            cur.execute("select id from data_sources where code = 'yfinance'")
            source_id = cur.fetchone()[0]
            cur.execute(MAPPINGS, {"source_id": source_id})
            mappings = dict(cur.fetchall())
            cur.execute(INSTRUMENTS, {"source_id": source_id})
            instruments = cur.fetchall()

        if not mappings:
            print("Aucune correspondance de concepts : rejouer les seeds.")
            return resume

        if only:
            instruments = [i for i in instruments if only in (i[1], i[3])]
        if limit:
            instruments = instruments[:limit]

        print(f"{len(instruments)} instruments, {len(mappings)} libelles mappes\n")

        with ingestion_run(conn, source_id, "ingest_fundamentals") as counters:
            for position, (instrument_id, code, currency, symbol) in enumerate(
                instruments, 1
            ):
                raw = fetch_fundamentals(
                    symbol, rate_limit_sec=settings.yfinance_rate_limit_sec,
                    max_retries=settings.http_max_retries)
                if not raw.ok:
                    resume["failed_instruments"].append(
                        {"internal_code": code, "reason": raw.error})
                    print(f"X {position:>3}/{len(instruments)} {symbol:<10} {raw.error}")
                    continue

                normalized = normalize(raw, instrument_id, source_id, currency, mappings)
                with conn.cursor() as cur:
                    charge = upsert_facts(cur, normalized.facts, instrument_id)
                conn.commit()

                counters.inserted += charge.nouveaux
                counters.rejected += len(normalized.rejected)
                resume["instruments"][code] = {
                    "faits": charge.total, "exercices": charge.exercices,
                    "concepts": charge.concepts,
                }
                print(f"  {position:>3}/{len(instruments)} {symbol:<10} "
                      f"faits={charge.total:<4} (+{charge.nouveaux:<3}) "
                      f"exercices={charge.exercices} concepts={charge.concepts}")

            counters.details = resume

    return resume
