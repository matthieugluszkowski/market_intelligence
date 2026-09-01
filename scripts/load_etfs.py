"""Charge les ETF français et européens éligibles au PEA au référentiel (classe etf).

Même mécanique que les actions et les matières premières : même collecteur yfinance,
mêmes barres hebdomadaires, même régression log-linéaire, même fiche instrument.
Ce qui caractérise un ETF ici :
- un ISIN unique au standard UCITS ;
- une cotation sur Euronext Paris (MIC 'XPAR') en EUR ;
- pas de comptes fondamentaux propres (supports_fundamentals = false) ;
- des métadonnées enrichies (émetteur, indice répliqué, frais TER, réplication, éligibilité PEA).

Usage :
    python scripts/load_etfs.py --dry-run
    python scripts/load_etfs.py
    python scripts/backfill_prices.py --freq 1w --only ETF:FR:CW8
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from market_intelligence.collectors.yfinance_prices import fetch_bars  # noqa: E402
from market_intelligence.config import get_settings  # noqa: E402
from market_intelligence.db import connect_direct  # noqa: E402

# Catalogue des ETF français et européens accessibles sur PEA (Crédit Mutuel France)
ETFS = (
    {
        "code": "ETF:FR:CW8",
        "nom": "Amundi MSCI World UCITS ETF EUR (C)",
        "symbole": "CW8.PA",
        "isin": "FR0010315770",
        "exchange": "XPAR",
        "devise": "EUR",
        "politique": "loglin_15y",
        "emetteur": "Amundi",
        "indice": "MSCI World Net Total Return",
        "categorie": "Actions Monde",
        "ter": 0.0038,
        "replication": "Synthétique",
        "distribution": "Capitalisation",
        "pea": True,
    },
    {
        "code": "ETF:IE:WPEA",
        "nom": "iShares MSCI World Swap PEA UCITS ETF (Acc)",
        "symbole": "WPEA.PA",
        "isin": "IE0002XZSHO1",
        "exchange": "XPAR",
        "devise": "EUR",
        "politique": "loglin_10y",
        "emetteur": "iShares (BlackRock)",
        "indice": "MSCI World Net Total Return",
        "categorie": "Actions Monde",
        "ter": 0.0025,
        "replication": "Synthétique",
        "distribution": "Capitalisation",
        "pea": True,
    },
    {
        "code": "ETF:FR:ESE",
        "nom": "BNP Paribas Easy S&P 500 UCITS ETF EUR (C)",
        "symbole": "ESE.PA",
        "isin": "FR0011550185",
        "exchange": "XPAR",
        "devise": "EUR",
        "politique": "loglin_15y",
        "emetteur": "BNP Paribas Easy",
        "indice": "S&P 500 Net Total Return",
        "categorie": "Actions US Large Cap",
        "ter": 0.0015,
        "replication": "Synthétique",
        "distribution": "Capitalisation",
        "pea": True,
    },
    {
        "code": "ETF:FR:PSP5",
        "nom": "Amundi PEA S&P 500 UCITS ETF Acc",
        "symbole": "PSP5.PA",
        "isin": "FR0013412285",
        "exchange": "XPAR",
        "devise": "EUR",
        "politique": "loglin_15y",
        "emetteur": "Amundi",
        "indice": "S&P 500 Net Total Return",
        "categorie": "Actions US Large Cap",
        "ter": 0.0015,
        "replication": "Synthétique",
        "distribution": "Capitalisation",
        "pea": True,
    },
    {
        "code": "ETF:FR:PUST",
        "nom": "Amundi PEA Nasdaq 100 UCITS ETF Acc",
        "symbole": "PUST.PA",
        "isin": "FR0013412269",
        "exchange": "XPAR",
        "devise": "EUR",
        "politique": "loglin_15y",
        "emetteur": "Amundi",
        "indice": "Nasdaq 100 Net Total Return",
        "categorie": "Actions US Tech",
        "ter": 0.0030,
        "replication": "Synthétique",
        "distribution": "Capitalisation",
        "pea": True,
    },
    {
        "code": "ETF:FR:PANX",
        "nom": "Amundi PEA US Tech Screened UCITS ETF Acc",
        "symbole": "PANX.PA",
        "isin": "FR0010713784",
        "exchange": "XPAR",
        "devise": "EUR",
        "politique": "loglin_10y",
        "emetteur": "Amundi",
        "indice": "MSCI USA Tech Screened Net TR",
        "categorie": "Actions US Tech",
        "ter": 0.0030,
        "replication": "Synthétique",
        "distribution": "Capitalisation",
        "pea": True,
    },
    {
        "code": "ETF:FR:C40",
        "nom": "Amundi CAC 40 ESG UCITS ETF EUR (C)",
        "symbole": "C40.PA",
        "isin": "FR0007052782",
        "exchange": "XPAR",
        "devise": "EUR",
        "politique": "loglin_20y",
        "emetteur": "Amundi",
        "indice": "CAC 40 ESG Net Total Return",
        "categorie": "Actions France Large Cap",
        "ter": 0.0025,
        "replication": "Physique",
        "distribution": "Capitalisation",
        "pea": True,
    },
    {
        "code": "ETF:FR:MSE",
        "nom": "Amundi EURO STOXX 50 II UCITS ETF Acc",
        "symbole": "MSE.PA",
        "isin": "FR0013412020",
        "exchange": "XPAR",
        "devise": "EUR",
        "politique": "loglin_20y",
        "emetteur": "Amundi",
        "indice": "Euro Stoxx 50 Net Total Return",
        "categorie": "Actions Zone Euro",
        "ter": 0.0018,
        "replication": "Synthétique",
        "distribution": "Capitalisation",
        "pea": True,
    },
    {
        "code": "ETF:FR:C50",
        "nom": "Amundi Core EURO STOXX 50 UCITS ETF EUR Acc",
        "symbole": "C50.PA",
        "isin": "FR0007054316",
        "exchange": "XPAR",
        "devise": "EUR",
        "politique": "loglin_20y",
        "emetteur": "Amundi",
        "indice": "Euro Stoxx 50 Gross Total Return",
        "categorie": "Actions Zone Euro",
        "ter": 0.0015,
        "replication": "Physique",
        "distribution": "Capitalisation",
        "pea": True,
    },
    {
        "code": "ETF:FR:ETZ",
        "nom": "BNP Paribas Easy Stoxx Europe 600 UCITS ETF EUR (C)",
        "symbole": "ETZ.PA",
        "isin": "FR0011550193",
        "exchange": "XPAR",
        "devise": "EUR",
        "politique": "loglin_15y",
        "emetteur": "BNP Paribas Easy",
        "indice": "Stoxx Europe 600 Net Return",
        "categorie": "Actions Europe Large & Mid",
        "ter": 0.0018,
        "replication": "Synthétique",
        "distribution": "Capitalisation",
        "pea": True,
    },
    {
        "code": "ETF:FR:MEH",
        "nom": "Amundi PEA Stoxx Europe 600 UCITS ETF (C)",
        "symbole": "MEH.PA",
        "isin": "FR0013412038",
        "exchange": "XPAR",
        "devise": "EUR",
        "politique": "loglin_10y",
        "emetteur": "Amundi",
        "indice": "Stoxx Europe 600 Net Return",
        "categorie": "Actions Europe Large & Mid",
        "ter": 0.0020,
        "replication": "Synthétique",
        "distribution": "Capitalisation",
        "pea": True,
    },
    {
        "code": "ETF:FR:PLEM",
        "nom": "Amundi PEA Émergent EMEA ESG UCITS ETF",
        "symbole": "PLEM.PA",
        "isin": "FR0011440478",
        "exchange": "XPAR",
        "devise": "EUR",
        "politique": "loglin_15y",
        "emetteur": "Amundi",
        "indice": "MSCI Emerging EMEA ESG Screened Net TR",
        "categorie": "Actions Marchés Émergents",
        "ter": 0.0030,
        "replication": "Synthétique",
        "distribution": "Capitalisation",
        "pea": True,
    },
    {
        "code": "ETF:FR:PAEEM",
        "nom": "Amundi PEA Émergent (MSCI Emerging) ESG Transition",
        "symbole": "PAEEM.PA",
        "isin": "FR0013412012",
        "exchange": "XPAR",
        "devise": "EUR",
        "politique": "loglin_10y",
        "emetteur": "Amundi",
        "indice": "MSCI Emerging ESG Net Return",
        "categorie": "Actions Marchés Émergents",
        "ter": 0.0030,
        "replication": "Synthétique",
        "distribution": "Capitalisation",
        "pea": True,
    },
    {
        "code": "ETF:FR:RS2K",
        "nom": "Amundi Russell 2000 ETF-C EUR",
        "symbole": "RS2K.PA",
        "isin": "FR0013412277",
        "exchange": "XPAR",
        "devise": "EUR",
        "politique": "loglin_15y",
        "emetteur": "Amundi",
        "indice": "Russell 2000 Net Total Return",
        "categorie": "Actions US Small Cap",
        "ter": 0.0035,
        "replication": "Synthétique",
        "distribution": "Capitalisation",
        "pea": True,
    },
    {
        "code": "ETF:FR:EESM",
        "nom": "BNP Paribas Easy MSCI Europe Small Caps SRI PAB",
        "symbole": "EESM.PA",
        "isin": "FR0011550201",
        "exchange": "XPAR",
        "devise": "EUR",
        "politique": "loglin_20y",
        "emetteur": "BNP Paribas Easy",
        "indice": "MSCI Europe Small Cap SRI Net TR",
        "categorie": "Actions Europe Small Cap",
        "ter": 0.0035,
        "replication": "Physique",
        "distribution": "Capitalisation",
        "pea": True,
    },
    {
        "code": "ETF:FR:WAT",
        "nom": "Amundi MSCI Water UCITS ETF Dist",
        "symbole": "WAT.PA",
        "isin": "FR0014002CH1",
        "exchange": "XPAR",
        "devise": "EUR",
        "politique": "loglin_20y",
        "emetteur": "Amundi",
        "indice": "World Water CW Net Total Return",
        "categorie": "Thématique Eau mondiale",
        "ter": 0.0060,
        "replication": "Synthétique",
        "distribution": "Distribution",
        "pea": True,
    },
    {
        "code": "ETF:FR:PCEU",
        "nom": "Amundi PEA MSCI Europe UCITS ETF Acc",
        "symbole": "PCEU.PA",
        "isin": "FR0013412053",
        "exchange": "XPAR",
        "devise": "EUR",
        "politique": "loglin_10y",
        "emetteur": "Amundi",
        "indice": "MSCI Europe Net Total Return",
        "categorie": "Actions Europe",
        "ter": 0.0020,
        "replication": "Synthétique",
        "distribution": "Capitalisation",
        "pea": True,
    },
    {
        "code": "ETF:FR:PAASI",
        "nom": "Amundi PEA Asie Émergente (MSCI Emerging Asia)",
        "symbole": "PAASI.PA",
        "isin": "FR0013412004",
        "exchange": "XPAR",
        "devise": "EUR",
        "politique": "loglin_10y",
        "emetteur": "Amundi",
        "indice": "MSCI Emerging Asia Net TR",
        "categorie": "Actions Asie Émergente",
        "ter": 0.0030,
        "replication": "Synthétique",
        "distribution": "Capitalisation",
        "pea": True,
    },
    {
        "code": "ETF:FR:CL2",
        "nom": "Amundi MSCI USA Daily (2x) Leveraged UCITS ETF Acc",
        "symbole": "CL2.PA",
        "isin": "FR0010755611",
        "exchange": "XPAR",
        "devise": "EUR",
        "politique": "loglin_20y",
        "emetteur": "Amundi",
        "indice": "MSCI USA Leveraged 2x Net TR",
        "categorie": "Actions US Levier (PEA)",
        "ter": 0.0050,
        "replication": "Synthétique",
        "distribution": "Capitalisation",
        "pea": True,
    },
    {
        "code": "ETF:FR:LQQ",
        "nom": "Amundi Nasdaq-100 Daily (2x) Leveraged UCITS ETF Acc",
        "symbole": "LQQ.PA",
        "isin": "FR0010342592",
        "exchange": "XPAR",
        "devise": "EUR",
        "politique": "loglin_20y",
        "emetteur": "Amundi",
        "indice": "Nasdaq 100 Leveraged 2x Net TR",
        "categorie": "Actions US Tech Levier (PEA)",
        "ter": 0.0060,
        "replication": "Synthétique",
        "distribution": "Capitalisation",
        "pea": True,
    },
)

UPSERT_INSTRUMENT = """
insert into instruments
  (internal_code, isin, asset_class, name, exchange_code, currency,
   policy_code, is_active, attributes)
values (%(internal_code)s, %(isin)s, 'etf', %(name)s, %(exchange_code)s,
        %(currency)s, %(policy_code)s, true, %(attributes)s)
on conflict (internal_code) do update set
  isin = excluded.isin,
  name = excluded.name,
  exchange_code = excluded.exchange_code,
  currency = excluded.currency,
  policy_code = excluded.policy_code,
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


def _identite(symbole: str) -> tuple[str, str]:
    """Nom et devise déclarés par le provider."""
    import yfinance as yf

    try:
        info = yf.Ticker(symbole).get_info()
    except Exception:  # noqa: BLE001
        return "", ""
    return (
        (info.get("longName") or info.get("shortName") or ""),
        (info.get("currency") or "").upper(),
    )


def verifier(etf: dict, rate_limit: float, retries: int) -> dict:
    """Télécharge la série hebdomadaire et valide la cohérence des cotations."""
    brut = fetch_bars(
        etf["symbole"],
        freq="1w",
        rate_limit_sec=rate_limit,
        max_retries=retries,
    )
    if not brut.ok:
        return {"statut": "echec", "motif": brut.error or "aucune cotation"}

    frame = brut.frame
    premiere, derniere = frame.index[0].date(), frame.index[-1].date()
    annees = (derniere - premiere).days / 365.25
    nom_provider, devise_provider = _identite(etf["symbole"])

    if devise_provider and devise_provider != etf["devise"]:
        statut, motif = "devise_divergente", (
            f"{devise_provider} chez le provider, {etf['devise']} déclaré"
        )
    elif len(frame) < 50:
        statut, motif = "historique_trop_court", f"{len(frame)} barres < 50"
    else:
        statut, motif = "retenu", ""

    return {
        "statut": statut,
        "motif": motif,
        "n_obs_weekly": len(frame),
        "history_years": round(annees, 1),
        "first_bar": premiere.isoformat(),
        "last_bar": derniere.isoformat(),
        "last_close": round(float(frame["Close"].iloc[-1]), 4),
        "reported_name": nom_provider or etf["nom"],
        "reported_currency": devise_provider or etf["devise"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", help="vérifie les séries et n'écrit rien"
    )
    args = parser.parse_args()

    settings = get_settings()
    print(f"{len(ETFS)} ETF PEA français et européens\n")
    print(
        f"{'code':<14} {'symbole':<9} {'période':<25} {'obs':>5} {'ans':>5}  statut"
    )

    verifications = {}
    for etf in ETFS:
        v = verifier(
            etf, settings.yfinance_rate_limit_sec, settings.http_max_retries
        )
        verifications[etf["code"]] = v
        periode = (
            f"{v['first_bar']} -> {v['last_bar']}"
            if v["statut"] != "echec"
            else v["motif"][:25]
        )
        print(
            f"{etf['code']:<14} {etf['symbole']:<9} {periode:<25} "
            f"{v.get('n_obs_weekly', 0):>5} {v.get('history_years', 0):>5}  "
            f"{v['statut']}{(' - ' + v['motif']) if v['motif'] and v['statut'] != 'echec' else ''}"
        )

    BLOQUANTS = ("echec", "devise_divergente")
    chargeables = [e for e in ETFS if verifications[e["code"]]["statut"] not in BLOQUANTS]
    ecartees = [e for e in ETFS if verifications[e["code"]]["statut"] in BLOQUANTS]
    print()
    print(f"{len(chargeables)} chargeables, {len(ecartees)} écartée(s)")
    for e in ecartees:
        v = verifications[e["code"]]
        print(f"  écarté {e['code']:<14} {v['statut']} : {v['motif']}")

    if args.dry_run:
        return 0

    with connect_direct() as conn:
        with conn.cursor() as cur:
            cur.execute("select id from data_sources where code = 'yfinance'")
            ligne = cur.fetchone()
            if ligne is None:
                print("Source 'yfinance' absente de data_sources : rejouer les seeds.")
                return 1
            source_id = ligne[0]

            for etf in chargeables:
                verification = verifications[etf["code"]]
                attributs = {
                    "emetteur": etf["emetteur"],
                    "indice_reference": etf["indice"],
                    "categorie": etf["categorie"],
                    "ter": etf["ter"],
                    "replication": etf["replication"],
                    "distribution": etf["distribution"],
                    "pea_eligible": etf["pea"],
                    "notes": "ETF éligible PEA (Crédit Mutuel / Euronext Paris)",
                    "verification": {"source": "yfinance", **verification},
                }
                cur.execute(
                    UPSERT_INSTRUMENT,
                    {
                        "internal_code": etf["code"],
                        "isin": etf["isin"],
                        "name": etf["nom"],
                        "exchange_code": etf["exchange"],
                        "currency": etf["devise"],
                        "policy_code": etf["politique"],
                        "attributes": json.dumps(attributs, ensure_ascii=False),
                    },
                )
                instrument_id = cur.fetchone()[0]
                cur.execute(
                    UPSERT_SYMBOL,
                    {
                        "instrument_id": instrument_id,
                        "source_id": source_id,
                        "symbol": etf["symbole"],
                    },
                )
                print(f"  chargé {etf['code']:<14} id={instrument_id}")
        conn.commit()

    print(
        f"\n{len(chargeables)} ETF écrits au référentiel. Suite :\n"
        f"  python scripts/backfill_prices.py --freq 1w --only ETF:FR:CW8\n"
        f"  python scripts/backfill_prices.py --freq 1w\n"
        f"  python scripts/compute_fits.py"
    )
    return 1 if ecartees else 0


if __name__ == "__main__":
    raise SystemExit(main())
