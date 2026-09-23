"""Charge les cryptomonnaies majeures au referentiel (classe `crypto`).

Ce script configure et integre les 5 cryptomonnaies de premier plan :
- Bitcoin (BTC-USD) : Reserve de valeur numerique et actif pionnier
- Ethereum (ETH-USD) : Plateforme de contrats intelligents et finance decentralisee
- Solana (SOL-USD) : Blockchain layer 1 ultra-rapide a faible cout
- BNB (BNB-USD) : Jeton de l'ecosysteme BNB Chain
- XRP (XRP-USD) : Protocole de reglement et liquidite interbancaire

Meme mecanisme de suivi que les autres classes d'actifs :
- Collecteur yfinance (symboles BTC-USD, ETH-USD, SOL-USD, BNB-USD, XRP-USD)
- Barres hebdomadaires et quotidiennes
- Regression log-lineaire (politique `loglin_10y`) et z-score
- Statut hors PEA explicite (compte d'actifs numeriques / exchange)
- Pas de fondamentaux d'entreprise (supports_fundamentals = false)

Usage :
    python scripts/load_cryptos.py --dry-run
    python scripts/load_cryptos.py
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from market_intelligence.collectors.yfinance_prices import fetch_bars  # noqa: E402
from market_intelligence.db import connect_direct  # noqa: E402

logger = logging.getLogger(__name__)

POLITIQUE = "loglin_10y"

CRYPTOS = (
    {
        "code": "CRYPTO:BTC",
        "symbole": "BTC-USD",
        "nom": "Bitcoin",
        "devise": "USD",
        "description": "Reserve de valeur decentralisee et actif pionnier",
    },
    {
        "code": "CRYPTO:ETH",
        "symbole": "ETH-USD",
        "nom": "Ethereum",
        "devise": "USD",
        "description": "Plateforme leader de contrats intelligents et finance decentralisee",
    },
    {
        "code": "CRYPTO:SOL",
        "symbole": "SOL-USD",
        "nom": "Solana",
        "devise": "USD",
        "description": "Blockchain layer 1 haute performance a debit eleve",
    },
    {
        "code": "CRYPTO:BNB",
        "symbole": "BNB-USD",
        "nom": "BNB",
        "devise": "USD",
        "description": "Jeton d'infrastructure et d'utilite de l'ecosysteme BNB Chain",
    },
    {
        "code": "CRYPTO:XRP",
        "symbole": "XRP-USD",
        "nom": "XRP",
        "devise": "USD",
        "description": "Protocole de reglement et liquidite pour paiements internationaux",
    },
)

UPSERT_INSTRUMENT = """
insert into instruments (
    internal_code, asset_class, name, exchange_code, currency,
    sector_code, country_iso2, is_active, policy_code, attributes
) values (
    %(internal_code)s, 'crypto', %(name)s, null, %(currency)s,
    null, null, true, %(policy_code)s, %(attributes)s::jsonb
)
on conflict (internal_code) do update set
    asset_class = 'crypto',
    name = excluded.name,
    exchange_code = null,
    currency = excluded.currency,
    is_active = true,
    policy_code = excluded.policy_code,
    attributes = instruments.attributes || excluded.attributes,
    updated_at = now()
returning id;
"""

UPSERT_SYMBOLE = """
insert into instrument_symbols (
    instrument_id, source_id, symbol, is_primary
) values (
    %(instrument_id)s, (select id from data_sources where code = 'yfinance'), %(symbol)s, true
)
on conflict (source_id, symbol, valid_from) do update set
    instrument_id = excluded.instrument_id,
    is_primary = excluded.is_primary;
"""

UPSERT_BARRE = """
insert into bars (
    instrument_id, freq, ts, open, high, low, close, volume, source_id
) values (
    %(instrument_id)s, %(freq)s, %(ts)s, %(open)s, %(high)s, %(low)s,
    %(close)s, %(volume)s, (select id from data_sources where code = 'yfinance')
)
on conflict (instrument_id, freq, ts) do update set
    open = excluded.open,
    high = excluded.high,
    low = excluded.low,
    close = excluded.close,
    volume = excluded.volume;
"""


def charge_crypto(conn, crypto: dict, dry_run: bool = False) -> int:
    """Charge une cryptomonnaie et son historique de cours."""
    symbole = crypto["symbole"]
    nom = crypto["nom"]
    code = crypto["code"]
    devise = crypto["devise"]

    print(f"\nTraitement {code} ({nom} - {symbole}) :")

    # 1. Telecharger l'historique hebdomadaire
    print(f"  telechargement 1w depuis yfinance ({symbole})...", flush=True)
    res_1w = fetch_bars(symbole, "1w")
    if not res_1w.ok or res_1w.frame is None or len(res_1w.frame) == 0:
        print(f"  ERREUR : aucune barre 1w recuperee pour {symbole} : {res_1w.error}")
        return 0

    frame_1w = res_1w.frame
    premier_1w = frame_1w.index[0].date()
    dernier_1w = frame_1w.index[-1].date()
    annees = round((dernier_1w - premier_1w).days / 365.25, 1)
    print(f"  -> {len(frame_1w)} barres 1w du {premier_1w} au {dernier_1w} ({annees} ans)")

    # 2. Telecharger l'historique quotidien (1d)
    print(f"  telechargement 1d depuis yfinance ({symbole})...", flush=True)
    res_1d = fetch_bars(symbole, "1d")
    frame_1d = res_1d.frame if res_1d.ok else None
    print(f"  -> {len(frame_1d) if frame_1d is not None else 0} barres 1d")

    if dry_run:
        print("  mode dry-run : aucune ecriture en base.")
        return len(frame_1w)

    # 3. Inserer dans instruments
    attrs = {
        "notes": crypto["description"],
        "pea_eligible": False,
        "pea_motif": "Actif numérique hors PEA (compte de détention numérique / exchange)",
        "verification": {
            "source": "yfinance",
            "status": "verifie",
            "history_years": annees,
            "n_obs_weekly": len(frame_1w),
            "first_bar": str(premier_1w),
            "last_bar": str(dernier_1w),
            "last_close": float(frame_1w["Close"].iloc[-1]),
            "reported_name": nom,
        },
    }

    with conn.cursor() as cur:
        # S'assurer que asset_classes possede bien crypto
        cur.execute("""
            insert into asset_classes (code, label, supports_fundamentals, default_policy_code)
            values ('crypto', 'Cryptomonnaie', false, 'loglin_10y')
            on conflict (code) do update set
              label = excluded.label,
              supports_fundamentals = excluded.supports_fundamentals,
              default_policy_code = excluded.default_policy_code;
        """)

        cur.execute(
            UPSERT_INSTRUMENT,
            {
                "internal_code": code,
                "name": nom,
                "currency": devise,
                "policy_code": POLITIQUE,
                "attributes": json.dumps(attrs),
            },
        )
        instrument_id = cur.fetchone()[0]

        # 4. Inserer symbole
        cur.execute(
            UPSERT_SYMBOLE,
            {"instrument_id": instrument_id, "symbol": symbole},
        )

        # 5. Inserer barres 1w par lot
        barres_1w = [
            {
                "instrument_id": instrument_id,
                "freq": "1w",
                "ts": idx.date() if hasattr(idx, "date") else idx,
                "open": float(row["Open"]),
                "high": float(row["High"]),
                "low": float(row["Low"]),
                "close": float(row["Close"]),
                "volume": float(row.get("Volume") or 0),
            }
            for idx, row in frame_1w.iterrows()
        ]
        cur.executemany(UPSERT_BARRE, barres_1w)

        # 6. Inserer barres 1d par lot
        nb_1d = 0
        if frame_1d is not None and not frame_1d.empty:
            barres_1d = [
                {
                    "instrument_id": instrument_id,
                    "freq": "1d",
                    "ts": idx.date() if hasattr(idx, "date") else idx,
                    "open": float(row["Open"]),
                    "high": float(row["High"]),
                    "low": float(row["Low"]),
                    "close": float(row["Close"]),
                    "volume": float(row.get("Volume") or 0),
                }
                for idx, row in frame_1d.iterrows()
            ]
            cur.executemany(UPSERT_BARRE, barres_1d)
            nb_1d = len(barres_1d)

        conn.commit()

    print(f"  enregistre instrument_id={instrument_id} ({len(frame_1w)} barres 1w, {nb_1d} barres 1d)", flush=True)
    return len(frame_1w)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="teste les telechargements sans ecrire en base")
    parser.add_argument("--only", help="codes internes separes par des virgules (ex: CRYPTO:BTC,CRYPTO:ETH)")
    args = parser.parse_args()

    cibles = CRYPTOS
    if args.only:
        codes = {c.strip() for c in args.only.split(",")}
        cibles = tuple(c for c in CRYPTOS if c["code"] in codes)

    print(f"Chargement de {len(cibles)} cryptomonnaie(s) majeure(s)...")

    with connect_direct() as conn:
        for c in cibles:
            charge_crypto(conn, c, dry_run=args.dry_run)

    if not args.dry_run:
        print("\nCalcul des regressions log-lineaires et z-scores...")
        import subprocess

        codes_str = ",".join(c["code"] for c in cibles)
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "compute_fits.py"), "--only", codes_str],
            check=False,
        )

    print("\nTermine avec succes !")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
