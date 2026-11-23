import sys
import json
import logging
from datetime import date, datetime, timezone
import yfinance as yf
import numpy as np

sys.path.insert(0, 'src')
from market_intelligence.db import connect_direct, fetch_all, fetch_one
from market_intelligence.analytics.regression import fit_log_linear
from market_intelligence.jobs import backfill_prices, compute_fits

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ingest_leaders")

# 1. Parked candidates (z > 1.0)
PARKED_CANDIDATES = [
    # (ticker, code, name, country, currency, exchange, sector_code, reason)
    ("MAERSK-B.CO", "EQ:DK:MAERSK", "A.P. Møller - Mærsk", "DK", "DKK", "XCSE", "50", "z_above_threshold (z=+2.58)"),
    ("SRAIL.SW", "EQ:CH:STADLERRAIL", "Stadler Rail AG", "CH", "CHF", "XSWX", "50", "z_above_threshold (z=+3.56)"),
    ("ABBN.SW", "EQ:CH:ABB", "ABB Ltd", "CH", "CHF", "XSWX", "50", "candidate_waiting (z=+1.25)"),
    ("ERIC-B.ST", "EQ:SE:ERICSSON", "Telefonaktiebolaget LM Ericsson", "SE", "SEK", "XSTO", "15", "candidate_waiting (z=+1.20)"),
]

# 2. Eligible candidates (z <= 1.0)
ELIGIBLE_CANDIDATES = [
    # (ticker, code, name, country, currency, exchange, sector_code, sector_name)
    ("RCO.PA", "EQ:FR:REMYCOINTREAU", "Rémy Cointreau", "FR", "EUR", "XPAR", "45", "Consommation non discrétionnaire"),
    ("ATO.PA", "EQ:FR:ATOS", "Atos SE", "FR", "EUR", "XPAR", "10", "Technologies de l'information"),
    ("WLN.PA", "EQ:FR:WORLDLINE", "Worldline SA", "FR", "EUR", "XPAR", "10", "Technologies de l'information"),
    ("BVI.PA", "EQ:FR:BUREAUVERITAS", "Bureau Veritas SA", "FR", "EUR", "XPAR", "50", "Industrie"),
    ("SGSN.SW", "EQ:CH:SGS", "SGS SA", "CH", "CHF", "XSWX", "50", "Industrie"),
    ("CON.DE", "EQ:DE:CONTINENTAL", "Continental AG", "DE", "EUR", "XETR", "40", "Consommation discrétionnaire"),
    ("SRT.DE", "EQ:DE:SARTORIUSAG", "Sartorius AG", "DE", "EUR", "XETR", "20", "Santé"),
    ("1COV.F", "EQ:DE:COVESTRO", "Covestro AG", "DE", "EUR", "XETR", "55", "Matériaux de base"),
    ("CLN.SW", "EQ:CH:CLARIANT", "Clariant AG", "CH", "CHF", "XSWX", "55", "Matériaux de base"),
    ("SIKA.SW", "EQ:CH:SIKA", "Sika AG", "CH", "CHF", "XSWX", "55", "Matériaux de base"),
    ("GEBN.SW", "EQ:CH:GEBERIT", "Geberit AG", "CH", "CHF", "XSWX", "50", "Industrie"),
    ("SCHN.SW", "EQ:CH:SCHINDLER", "Schindler Holding AG", "CH", "CHF", "XSWX", "50", "Industrie"),
    ("LOGN.SW", "EQ:CH:LOGITECH", "Logitech International S.A.", "CH", "CHF", "XSWX", "10", "Technologies de l'information"),
    ("UHR.SW", "EQ:CH:SWATCHGROUP", "The Swatch Group AG", "CH", "CHF", "XSWX", "40", "Consommation discrétionnaire"),
    ("CFR.SW", "EQ:CH:RICHEMONT", "Compagnie Financière Richemont SA", "CH", "CHF", "XSWX", "40", "Consommation discrétionnaire"),
    ("NXPI", "EQ:NL:NXPI", "NXP Semiconductors N.V.", "NL", "USD", None, "10", "Technologies de l'information"),
    ("BKNG", "EQ:US:BOOKING", "Booking Holdings Inc.", "US", "USD", None, "40", "Consommation discrétionnaire"),
    ("NOVO-B.CO", "EQ:DK:NOVONORDISK", "Novo Nordisk A/S", "DK", "DKK", "XCSE", "20", "Santé"),
    ("ORSTED.CO", "EQ:DK:ORSTED", "Ørsted A/S", "DK", "DKK", "XCSE", "65", "Services aux collectivités"),
    ("ATCO-A.ST", "EQ:SE:ATLASCOPCO", "Atlas Copco AB", "SE", "SEK", "XSTO", "50", "Industrie"),
    ("VOLV-B.ST", "EQ:SE:VOLVOB", "Volvo AB", "SE", "SEK", "XSTO", "50", "Industrie"),
    ("ARM", "EQ:GB:ARM", "Arm Holdings plc", "GB", "USD", None, "10", "Technologies de l'information"),
]


def process_parked():
    print("\n=======================================================")
    print("1. ENREGISTREMENT DES CANDIDATS EN ANTICHAMBRE (PARKED)")
    print("=======================================================")
    for ticker, code, name, country, cur, exch, sec, reason in PARKED_CANDIDATES:
        print(f"\nTraitement du titre en surcote/attente : {ticker} ({name})...")
        t = yf.Ticker(ticker)
        df = t.history(period="max", interval="1wk")
        if df.empty or len(df) < 52:
            print(f"  [ERREUR] Données insuffisantes pour {ticker}")
            continue
        
        closes = df['Close'].dropna().values
        dates = [d.date() if hasattr(d, 'date') else d for d in df.index][-len(closes):]
        fit = fit_log_linear(dates, closes)
        z = fit["z_score"]
        last_close = float(closes[-1])
        
        status = "parked"
        status_reason = "z_above_threshold" if z > 2.5 else "candidate_waiting"
        
        with connect_direct(autocommit=True) as conn, conn.cursor() as cur_db:
            cur_db.execute("""
                INSERT INTO parked_instruments (
                    internal_code, symbol_yfinance, name, currency,
                    exchange_code, asset_class, policy_code, attributes,
                    status, parked_reason, window_start, intercept, slope_annual,
                    sigma_resid, r_squared, last_close_at_parking, last_z_at_parking,
                    last_checked_at, live_price, live_z_score, notes
                ) VALUES (
                    %s, %s, %s, %s,
                    %s, 'equity', 'loglin_20y', '{}'::jsonb,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    now(), %s, %s, %s
                )
                ON CONFLICT (internal_code) DO UPDATE SET
                    symbol_yfinance = EXCLUDED.symbol_yfinance,
                    name = EXCLUDED.name,
                    status = EXCLUDED.status,
                    parked_reason = EXCLUDED.parked_reason,
                    window_start = EXCLUDED.window_start,
                    intercept = EXCLUDED.intercept,
                    slope_annual = EXCLUDED.slope_annual,
                    sigma_resid = EXCLUDED.sigma_resid,
                    r_squared = EXCLUDED.r_squared,
                    last_close_at_parking = EXCLUDED.last_close_at_parking,
                    last_z_at_parking = EXCLUDED.last_z_at_parking,
                    last_checked_at = now(),
                    live_price = EXCLUDED.live_price,
                    live_z_score = EXCLUDED.live_z_score,
                    notes = EXCLUDED.notes;
            """, (
                code, ticker, name, cur,
                exch, status, status_reason, dates[0], fit["intercept"], fit["slope_annual"],
                fit["sigma_resid"], fit["r_squared"], last_close, z,
                last_close, z, f"Candidat parké sans barres en base ({status_reason}, z={z:+.2f})"
            ))
        print(f"  [OK] {ticker:<12} -> Parké dans parked_instruments (z={z:+.2f}, statut={status_reason})")


def process_eligible():
    print("\n=======================================================")
    print("2. INGESTION DES CANDIDATS ÉLIGIBLES (z <= 1.0)")
    print("=======================================================")
    
    # Check data source id for yfinance
    with connect_direct() as conn, conn.cursor() as cur_db:
        cur_db.execute("SELECT id FROM data_sources WHERE code = 'yfinance'")
        source_id = cur_db.fetchone()[0]

    for ticker, code, name, country, cur, exch, sec, sec_name in ELIGIBLE_CANDIDATES:
        print(f"\n--- Ingestion de l'éligible : {name} ({ticker}) ---")
        
        # 0. Évaluation préalable en mémoire pour récupérer les métriques initiales
        t = yf.Ticker(ticker)
        df = t.history(period="max", interval="1wk")
        if df.empty or len(df) < 52:
            print(f"  [ERREUR] Données insuffisantes pour {ticker}")
            continue
        closes = df['Close'].dropna().values
        dates = [d.date() if hasattr(d, 'date') else d for d in df.index][-len(closes):]
        fit = fit_log_linear(dates, closes)
        z = fit["z_score"]
        last_close = float(closes[-1])
        w_start = dates[0]

        # 1. Création ou mise à jour dans instruments
        with connect_direct(autocommit=True) as conn, conn.cursor() as cur_db:
            cur_db.execute("""
                INSERT INTO instruments (
                    internal_code, asset_class, name, exchange_code,
                    currency, sector_code, country_iso2, is_active, policy_code
                ) VALUES (
                    %s, 'equity', %s, %s,
                    %s, %s, %s, TRUE, 'loglin_20y'
                )
                ON CONFLICT (internal_code) DO UPDATE SET
                    name = EXCLUDED.name,
                    exchange_code = EXCLUDED.exchange_code,
                    currency = EXCLUDED.currency,
                    sector_code = EXCLUDED.sector_code,
                    country_iso2 = EXCLUDED.country_iso2,
                    is_active = TRUE,
                    policy_code = 'loglin_20y'
                RETURNING id;
            """, (code, name, exch, cur, sec, country))
            instrument_id = cur_db.fetchone()[0]
            
            # 2. Symbole principal
            cur_db.execute("""
                SELECT id FROM instrument_symbols 
                WHERE source_id = %s AND symbol = %s
            """, (source_id, ticker))
            existing_sym = cur_db.fetchone()
            if existing_sym:
                cur_db.execute("""
                    UPDATE instrument_symbols
                       SET instrument_id = %s, is_primary = TRUE
                     WHERE id = %s;
                """, (instrument_id, existing_sym[0]))
            else:
                cur_db.execute("""
                    INSERT INTO instrument_symbols (
                        instrument_id, source_id, symbol, is_primary
                    ) VALUES (
                        %s, %s, %s, TRUE
                    );
                """, (instrument_id, source_id, ticker))
            
            # 3. Enregistrement dans parked_instruments comme 'eligible'
            cur_db.execute("""
                INSERT INTO parked_instruments (
                    instrument_id, internal_code, symbol_yfinance, name, currency,
                    exchange_code, asset_class, policy_code, attributes,
                    status, parked_reason, window_start, intercept, slope_annual,
                    sigma_resid, r_squared, last_close_at_parking, last_z_at_parking,
                    last_checked_at, live_price, live_z_score, notes
                ) VALUES (
                    %s, %s, %s, %s, %s,
                    %s, 'equity', 'loglin_20y', '{}'::jsonb,
                    'eligible', 'candidate_eligible', %s, %s, %s,
                    %s, %s, %s, %s,
                    now(), %s, %s, 'Titre directement éligible au screener'
                )
                ON CONFLICT (internal_code) DO UPDATE SET
                    instrument_id = EXCLUDED.instrument_id,
                    symbol_yfinance = EXCLUDED.symbol_yfinance,
                    name = EXCLUDED.name,
                    status = 'eligible',
                    parked_reason = 'candidate_eligible',
                    window_start = EXCLUDED.window_start,
                    intercept = EXCLUDED.intercept,
                    slope_annual = EXCLUDED.slope_annual,
                    sigma_resid = EXCLUDED.sigma_resid,
                    r_squared = EXCLUDED.r_squared,
                    last_close_at_parking = EXCLUDED.last_close_at_parking,
                    last_z_at_parking = EXCLUDED.last_z_at_parking,
                    last_checked_at = now(),
                    live_price = EXCLUDED.live_price,
                    live_z_score = EXCLUDED.live_z_score,
                    notes = 'Titre directement éligible au screener';
            """, (
                instrument_id, code, ticker, name, cur,
                exch, w_start, fit["intercept"], fit["slope_annual"],
                fit["sigma_resid"], fit["r_squared"], last_close, z,
                last_close, z
            ))

        print(f"  [OK] Instrument créé / actif : ID={instrument_id}, code={code}")
        
        # 4. Backfill des cours (hebdo 1w + quotidien 1d)
        print(f"  Chargement des cours pour {code}...")
        try:
            backfill_prices.run(freqs=("1w", "1d"), only=code)
        except Exception as e:
            logger.warning(f"  Erreur backfill pour {code}: {e}")
            
        # 5. Calcul de la régression loglin_20y
        print(f"  Calcul régression pour {code}...")
        try:
            compute_fits.run(only=code)
        except Exception as e:
            logger.warning(f"  Erreur compute_fits pour {code}: {e}")

    # Fix Eurofins Scientific symbol to ERF.PA
    print("\n--- Mise à jour symbole Eurofins Scientific -> ERF.PA ---")
    with connect_direct(autocommit=True) as conn, conn.cursor() as cur_db:
        cur_db.execute("""
            UPDATE instrument_symbols
               SET symbol = 'ERF.PA'
             WHERE instrument_id = (SELECT id FROM instruments WHERE internal_code = 'EQ:LU:EUROFINSSCIENTIF')
               AND source_id = 5;
        """)
        cur_db.execute("""
            UPDATE instruments
               SET sector_code = '20'
             WHERE internal_code = 'EQ:LU:EUROFINSSCIENTIF';
        """)
    print("  Rechargement et calcul Eurofins...")
    try:
        backfill_prices.run(freqs=("1w", "1d"), only="EQ:LU:EUROFINSSCIENTIF")
        compute_fits.run(only="EQ:LU:EUROFINSSCIENTIF")
    except Exception as e:
        logger.warning(f"  Erreur Eurofins: {e}")


if __name__ == "__main__":
    process_parked()
    process_eligible()
    print("\nIngestion terminée avec succès !")
