"""Ingestion des operations sur titre, du nombre d'actions, et calcul des facteurs.

Trois etapes enchainees, parce que la troisieme depend strictement des deux
premieres : sans dividendes en base, `factor_total` vaudrait 1.0 partout et
personne ne s'en apercevrait.
"""

from __future__ import annotations

import logging

from ..analytics.adjustment_factors import run_for_instrument
from ..collectors.yfinance_actions import fetch_actions
from ..config import get_settings
from ..db import connect_direct
from ..loaders.corporate_actions import upsert_actions
from ..loaders.journal import ingestion_run
from ..normalizers.corporate_actions import normalize

logger = logging.getLogger(__name__)

INSTRUMENTS = """
select i.id, i.internal_code, i.currency, s.symbol
  from instruments i
  join instrument_symbols s
    on s.instrument_id = i.id and s.source_id = %(source_id)s and s.is_primary
 where i.is_active
 order by i.internal_code;
"""


def run(limit: int = 0, only: str = "", freq: str = "1w") -> dict:
    settings = get_settings()
    summary: dict = {"instruments": {}, "failed_instruments": []}

    with connect_direct() as conn:
        with conn.cursor() as cur:
            cur.execute("select id from data_sources where code = 'yfinance'")
            source_id = cur.fetchone()[0]
            cur.execute(INSTRUMENTS, {"source_id": source_id})
            instruments = cur.fetchall()

        if only:
            instruments = [i for i in instruments if only in (i[1], i[3])]
        if limit:
            instruments = instruments[:limit]

        print(f"{len(instruments)} instruments\n")

        with ingestion_run(conn, source_id, "ingest_corporate_actions") as counters:
            for position, (instrument_id, internal_code, currency, symbol) in enumerate(
                instruments, 1
            ):
                raw = fetch_actions(
                    symbol, rate_limit_sec=settings.yfinance_rate_limit_sec
                )
                if not raw.ok:
                    summary["failed_instruments"].append(
                        {"internal_code": internal_code, "reason": raw.error}
                    )
                    print(f"X {position:>3}/{len(instruments)} {symbol:<10} {raw.error}")
                    continue

                normalized = normalize(raw, instrument_id, source_id, currency)
                with conn.cursor() as cur:
                    charge = upsert_actions(cur, normalized, instrument_id)
                    facteurs = run_for_instrument(
                        cur, instrument_id, freq, settings.method_version
                    )
                conn.commit()

                counters.inserted += charge.actions_nouvelles + charge.shares_nouvelles
                counters.rejected += len(normalized.rejected)
                summary["instruments"][internal_code] = {
                    "actions": charge.actions_totales,
                    "shares": charge.shares_totales,
                    "dividendes": facteurs.n_dividendes,
                    "facteur_le_plus_ancien": round(facteurs.facteur_le_plus_ancien, 4),
                }
                print(
                    f"  {position:>3}/{len(instruments)} {symbol:<10} "
                    f"ops={charge.actions_totales:<4} (+{charge.actions_nouvelles}) "
                    f"actions={charge.shares_totales:<4} (+{charge.shares_nouvelles}) "
                    f"facteur_1998={facteurs.facteur_le_plus_ancien:.4f}"
                )

            counters.details = summary

    return summary
