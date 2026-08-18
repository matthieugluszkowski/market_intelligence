"""Backfill des cours : hebdomadaire sur tout l'historique, quotidien sur 3 ans.

Strategie deux temperatures du doc 00 SS5. L'hebdomadaire porte la tendance
longue - Shiller et Perron ont montre que la puissance des tests sur series
temporelles depend de l'etendue temporelle, pas de la frequence d'observation,
donc 1 560 points hebdomadaires sur 30 ans suffisent a estimer deux parametres.
Le quotidien ne sert que la fenetre recente, et ne remonte donc pas.

Le job est relancable sans reflechir : le chargement est idempotent, et une
seconde execution sans nouvelle cotation ne touche aucune ligne.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from ..collectors.yfinance_prices import fetch_bars
from ..config import get_settings
from ..db import connect_direct
from ..loaders.bars import record_rejections, upsert_bars
from ..loaders.journal import ingestion_run
from ..normalizers.bars import normalize

logger = logging.getLogger(__name__)

DAILY_YEARS = 3

INSTRUMENTS = """
select i.id, i.internal_code, i.name, s.symbol
  from instruments i
  join instrument_symbols s
    on s.instrument_id = i.id
   and s.source_id = %(source_id)s
   and s.is_primary
 where i.is_active
 order by i.internal_code;
"""


def run(freqs: tuple[str, ...] = ("1w", "1d"), limit: int = 0, only: str = "") -> dict:
    settings = get_settings()
    summary: dict = {"freqs": list(freqs), "instruments": {}, "failed_instruments": []}

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

        print(f"{len(instruments)} instruments, frequences {', '.join(freqs)}\n")

        with ingestion_run(conn, source_id, "backfill_prices") as counters:
            for position, (instrument_id, internal_code, name, symbol) in enumerate(
                instruments, 1
            ):
                per_instrument = {}
                for freq in freqs:
                    start = (
                        date.today() - timedelta(days=365 * DAILY_YEARS)
                        if freq == "1d" else None
                    )
                    raw = fetch_bars(
                        symbol, freq=freq, start=start,
                        rate_limit_sec=settings.yfinance_rate_limit_sec,
                        max_retries=settings.http_max_retries,
                    )
                    if not raw.ok:
                        reason = raw.error or "aucune cotation"
                        summary["failed_instruments"].append(
                            {"internal_code": internal_code, "freq": freq, "reason": reason}
                        )
                        print(f"X {position:>3}/{len(instruments)} {symbol:<10} {freq} {reason}")
                        continue

                    normalized = normalize(raw.frame, instrument_id, freq, source_id)
                    with conn.cursor() as cur:
                        result = upsert_bars(cur, normalized.rows, instrument_id, freq)
                        record_rejections(cur, instrument_id, freq, normalized.rejected)
                    conn.commit()

                    counters.inserted += result.inserted
                    counters.updated += result.revised
                    counters.rejected += len(normalized.rejected)
                    per_instrument[freq] = {
                        "inserted": result.inserted, "revised": result.revised,
                        "unchanged": result.unchanged, "rejected": len(normalized.rejected),
                    }
                    flag = "!" if result.revised else " "
                    print(
                        f"{flag} {position:>3}/{len(instruments)} {symbol:<10} {freq} "
                        f"+{result.inserted:<6} "
                        f"rev={result.revised:<5} inchange={result.unchanged:<6} "
                        f"rejet={len(normalized.rejected)}"
                    )
                summary["instruments"][internal_code] = per_instrument

            counters.details = summary

    return summary
