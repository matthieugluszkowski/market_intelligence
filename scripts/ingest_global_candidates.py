"""Integrate new global candidates and rebuild the screener dataset.

Eligible candidates become active instruments. Parked candidates are linked to
inactive instruments so the existing monitoring process can restore them later.
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from market_intelligence.db import connect_direct
from market_intelligence.jobs import backfill_prices, compute_fits

COUNTRY_SYMBOLS = {
    "DE": "SAP.DE",
    "TW": "TSM",
    "KR": "005930.KS 000660.KS CPNG 035720.KS 035420.KS",
    "JP": "8035.T 6857.T 4755.T 9984.T 6098.T 4689.T 4502.T 4568.T TM",
    "CN": "0700.HK BABA PDD 3690.HK BIDU NTES JD 1024.HK 2318.HK 1398.HK 0939.HK 1288.HK 3988.HK",
    "ZA": "NPN.JO",
    "SG": "SE GRAB",
    "AR": "MELI",
    "BR": "NU",
    "SA": "2222.SR",
    "US": """NVDA AAPL MSFT GOOGL AMZN META AVGO AMD QCOM TXN ADI MU MRVL AMAT
LRCX KLAC ORCL CRM ADBE NOW PLTR CRWD PANW FTNT JPM BAC WFC C GS MS BRK-B
V MA AXP PYPL FIS FISV BLK BX KKR APO SCHW PGR CB LLY JNJ ABBV MRK PFE BMY
AMGN GILD REGN VRTX MRNA ISRG ABT MDT SYK TMO DHR UNH XOM CVX TSLA""",
}
COUNTRY_BY_SYMBOL = {
    symbol: country for country, symbols in COUNTRY_SYMBOLS.items()
    for symbol in symbols.split()
}
PEA_COUNTRIES = {
    "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "ES", "FI",
    "FR", "GR", "HR", "HU", "IE", "IS", "IT", "LI", "LT", "LU",
    "LV", "MT", "NL", "NO", "PL", "PT", "RO", "SE", "SI", "SK",
}
SECTOR_SYMBOLS = {
    "10": """NVDA AAPL MSFT GOOGL AVGO TSM 005930.KS 000660.KS AMD QCOM TXN ADI MU
MRVL ORCL SAP.DE CRM ADBE NOW PLTR CRWD PANW FTNT FIS FISV""",
    "15": """META 0700.HK BIDU NTES 1024.HK 035720.KS 035420.KS 4689.T""",
    "20": """LLY JNJ ABBV MRK PFE BMY AMGN GILD REGN VRTX MRNA ISRG ABT MDT SYK TMO
DHR 4502.T 4568.T""",
    "30": """JPM BAC WFC C GS MS BRK-B V MA AXP PYPL BLK BX KKR APO SCHW PGR CB
2318.HK 1398.HK 0939.HK 1288.HK 3988.HK NU""",
    "40": """AMZN BABA PDD 3690.HK JD CPNG SE GRAB MELI TM TSLA""",
    "50": """AMAT LRCX KLAC 8035.T 6857.T""",
    "60": """2222.SR XOM CVX""",
}
SECTOR_BY_SYMBOL = {
    symbol: code for code, symbols in SECTOR_SYMBOLS.items()
    for symbol in symbols.split()
}
SECTOR_LABELS = {
    "10": "Technologies de l'information",
    "15": "Telecommunications",
    "20": "Sante",
    "30": "Services financiers",
    "40": "Consommation discretionnaire",
    "50": "Industrie",
    "60": "Energie",
}
CURRENCY_LABELS = {
    "HKD": "Hong Kong dollar",
    "KRW": "South Korean won",
    "SAR": "Saudi riyal",
    "ZAC": "South African rand cents",
}

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    symbols = list(COUNTRY_BY_SYMBOL)
    with connect_direct() as conn, conn.cursor() as cur:
        cur.execute(
            """select id, internal_code, symbol_yfinance, name, currency, status,
                      attributes
                 from parked_instruments
                where symbol_yfinance = any(%s)
                order by symbol_yfinance""",
            (symbols,),
        )
        candidates = cur.fetchall()
        found = {r[2] for r in candidates}
        missing = sorted(set(symbols) - found)
        if missing:
            raise RuntimeError(f"Candidates missing from parked_instruments: {missing}")
        counts = {}
        for row in candidates:
            counts[row[5]] = counts.get(row[5], 0) + 1
        print(f"{len(candidates)} candidates: {counts}")
        active_count = sum(1 for r in candidates if r[5] in ("eligible", "restored"))
        print(f"Will activate and load {active_count} instruments.")
        if args.dry_run:
            return 0
        cur.execute("select id from data_sources where code = 'yfinance'")
        source = cur.fetchone()
        if source is None:
            raise RuntimeError("yfinance source missing from data_sources.")
        source_id = source[0]
        for code, label in CURRENCY_LABELS.items():
            cur.execute(
                """insert into currencies (code, label) values (%s, %s)
                   on conflict (code) do nothing""",
                (code, label),
            )
        instruments = []
        for parked_id, internal_code, symbol, name, currency, status, old_attrs in candidates:
            country = COUNTRY_BY_SYMBOL[symbol]
            active = status in ("eligible", "restored")
            pea = country in PEA_COUNTRIES
            sector_code = SECTOR_BY_SYMBOL.get(symbol)
            attrs = dict(old_attrs or {})
            attrs.update({
                "pea_eligible": pea,
                "pea_motif": None if pea else "issuer outside EU/EEA",
                "sector_label": SECTOR_LABELS.get(sector_code),
            })
            cur.execute(
                """insert into instruments
                     (internal_code, asset_class, name, currency, sector_code,
                      country_iso2, is_active, policy_code, attributes)
                   values (%s, 'equity', %s, %s, %s, %s, %s, 'loglin_20y', %s)
                   on conflict (internal_code) do update set
                     name = excluded.name, currency = excluded.currency,
                     sector_code = excluded.sector_code,
                     country_iso2 = excluded.country_iso2,
                     is_active = excluded.is_active,
                     policy_code = excluded.policy_code,
                     attributes = instruments.attributes || excluded.attributes,
                     updated_at = now()
                   returning id""",
                (internal_code, name, currency, sector_code, country, active,
                 json.dumps(attrs, ensure_ascii=False)),
            )
            instrument_id = cur.fetchone()[0]
            cur.execute(
                """insert into instrument_symbols
                     (instrument_id, source_id, symbol, is_primary)
                   values (%s, %s, %s, true)
                   on conflict (source_id, symbol, valid_from) do update set
                     instrument_id = excluded.instrument_id,
                     is_primary = true""",
                (instrument_id, source_id, symbol),
            )
            cur.execute(
                """update parked_instruments
                      set instrument_id = %s, attributes = %s
                    where id = %s""",
                (instrument_id, json.dumps(attrs, ensure_ascii=False), parked_id),
            )
            if active:
                instruments.append(internal_code)
        conn.commit()

    print(f"{len(instruments)} active instruments; loading prices...")
    failures = []
    for pos, code in enumerate(instruments, 1):
        print(f"\n[{pos}/{len(instruments)}] {code}", flush=True)
        result = backfill_prices.run(freqs=("1w", "1d"), only=code)
        failures.extend(result.get("failed_instruments", []))
    print("\nCalculating regressions on the full active universe...")
    fits = compute_fits.run()
    print(
        f"Done: {len(instruments)} active instruments, "
        f"{len(failures)} price-load failures, {fits.get('fits', 0)} fits calculated."
    )
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
