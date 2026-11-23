import sys
import logging
from datetime import date
import yfinance as yf

sys.path.insert(0, 'src')
from market_intelligence.db import connect_direct
from market_intelligence.analytics.regression import fit_log_linear
from market_intelligence.jobs import backfill_prices, compute_fits

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ingest_priority")

# 1. Parked candidates (1.0 < z <= 2.5)
PARKED_CANDIDATES = [
    # (ticker, code, name, country, currency, exchange, sector_code, reason)
    ("ZURN.SW", "EQ:CH:ZURICHINS", "Zurich Insurance Group AG", "CH", "CHF", "XSWX", "30", "candidate_waiting (z=+1.18)"),
    ("SAND.ST", "EQ:SE:SANDVIK", "Sandvik AB", "SE", "SEK", "XSTO", "50", "candidate_waiting (z=+1.21)"),
    ("RO.SW", "EQ:CH:ROCHE", "Roche Holding AG", "CH", "CHF", "XSWX", "20", "candidate_waiting (z=+1.41)"),
    ("BA.L", "EQ:GB:BAESYSTEMS", "BAE Systems plc", "GB", "GBP", "XLON", "50", "candidate_waiting (z=+1.59)"),
    ("NOVN.SW", "EQ:CH:NOVARTIS", "Novartis AG", "CH", "CHF", "XSWX", "20", "candidate_waiting (z=+1.78)"),
    ("RR.L", "EQ:GB:ROLLSROYCE", "Rolls-Royce Holdings plc", "GB", "GBP", "XLON", "50", "candidate_waiting (z=+2.04)"),
    ("UBSG.SW", "EQ:CH:UBS", "UBS Group AG", "CH", "CHF", "XSWX", "30", "candidate_waiting (z=+2.12)"),
]

# 2. Eligible candidates (z <= 1.0)
ELIGIBLE_CANDIDATES = [
    # (ticker, code, name, country, currency, exchange, sector_code, sector_name)
    ("NESN.SW", "EQ:CH:NESTLE", "Nestlé S.A.", "CH", "CHF", "XSWX", "45", "Consommation non discrétionnaire"),
    ("DGE.L", "EQ:GB:DIAGEO", "Diageo plc", "GB", "GBP", "XLON", "45", "Consommation non discrétionnaire"),
    ("BARN.SW", "EQ:CH:BARRYCALLEBAUT", "Barry Callebaut AG", "CH", "CHF", "XSWX", "45", "Consommation non discrétionnaire"),
    ("ROCK-B.CO", "EQ:DK:ROCKWOOL", "Rockwool A/S", "DK", "DKK", "XCSE", "50", "Industrie"),
    ("ALO.PA", "EQ:FR:ALSTOM", "Alstom SA", "FR", "EUR", "XPAR", "50", "Industrie"),
    ("KNIN.SW", "EQ:CH:KUEHNENAGEL", "Kühne + Nagel International AG", "CH", "CHF", "XSWX", "50", "Industrie"),
    ("ULVR.L", "EQ:GB:UNILEVER", "Unilever PLC", "GB", "GBP", "XLON", "45", "Consommation non discrétionnaire"),
    ("EPI-A.ST", "EQ:SE:EPIROC", "Epiroc AB", "SE", "SEK", "XSTO", "50", "Industrie"),
    ("STMN.SW", "EQ:CH:STRAUMANN", "Straumann Holding AG", "CH", "CHF", "XSWX", "20", "Santé"),
    ("ADEN.SW", "EQ:CH:ADECCO", "Adecco Group AG", "CH", "CHF", "XSWX", "50", "Industrie"),
    ("SOON.SW", "EQ:CH:SONOVA", "Sonova Holding AG", "CH", "CHF", "XSWX", "20", "Santé"),
    ("GIVN.SW", "EQ:CH:GIVAUDAN", "Givaudan SA", "CH", "CHF", "XSWX", "55", "Matériaux de base"),
    ("SIGN.SW", "EQ:CH:SIGCOMBIBLOC", "SIG Group AG", "CH", "CHF", "XSWX", "50", "Industrie"),
    ("ALFA.ST", "EQ:SE:ALFALAVAL", "Alfa Laval AB", "SE", "SEK", "XSTO", "50", "Industrie"),
    ("ASSA-B.ST", "EQ:SE:ASSAABLOY", "ASSA ABLOY AB", "SE", "SEK", "XSTO", "50", "Industrie"),
    ("REL.L", "EQ:GB:RELX", "RELX PLC", "GB", "GBP", "XLON", "50", "Industrie"),
    ("SREN.SW", "EQ:CH:SWISSRE", "Swiss Re AG", "CH", "CHF", "XSWX", "30", "Services financiers"),
    ("STMPA.PA", "EQ:FR:STMICRO", "STMicroelectronics N.V.", "FR", "EUR", "XPAR", "10", "Technologies de l'information"),
    ("G1A.DE", "EQ:DE:GEAGROUP", "GEA Group Aktiengesellschaft", "DE", "EUR", "XETR", "50", "Industrie"),
]

def process_parked():
    print("\n=======================================================")
    print("1. ENREGISTREMENT DES CANDIDATS EN ANTICHAMBRE (PARKED)")
    print("=======================================================")
    for ticker, code, name, country, cur, exch, sec, reason in PARKED_CANDIDATES:
        print(f"\nTraitement du titre en attente : {ticker} ({name})...")
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
                last_close, z, f"Candidat prioritaire parké sans barres en base ({status_reason}, z={z:+.2f})"
            ))
        print(f"  [OK] {ticker:<12} -> Parké dans parked_instruments (z={z:+.2f}, statut={status_reason})")


def process_eligible():
    print("\n=======================================================")
    print("2. INGESTION DES CANDIDATS ÉLIGIBLES (z <= 1.0)")
    print("=======================================================")
    
    with connect_direct() as conn, conn.cursor() as cur_db:
        cur_db.execute("SELECT id FROM data_sources WHERE code = 'yfinance'")
        source_id = cur_db.fetchone()[0]

    for ticker, code, name, country, cur, exch, sec, sec_name in ELIGIBLE_CANDIDATES:
        print(f"\n--- Ingestion de l'éligible : {name} ({ticker}) ---")
        
        # 0. Évaluation préalable en mémoire
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
                    now(), %s, %s, 'Titre prioritaire directement éligible au screener'
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
                    notes = 'Titre prioritaire directement éligible au screener';
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


if __name__ == "__main__":
    process_parked()
    process_eligible()
    print("\nIngestion des champions prioritaires terminée avec succès !")
