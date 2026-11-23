import sys
import yfinance as yf
from datetime import date
sys.path.insert(0, 'src')
from market_intelligence.analytics.regression import fit_log_linear
from market_intelligence.db import fetch_all

candidates = [
    # (name, country, ticker, sector_name, sector_code, currency, exchange)
    ("Roche", "Suisse", "ROG.SW", "Santé", "20", "CHF", "XSWX"),
    ("Novartis", "Suisse", "NOVN.SW", "Santé", "20", "CHF", "XSWX"),
    ("Nestlé", "Suisse", "NESN.SW", "Consommation non discrétionnaire", "45", "CHF", "XSWX"),
    ("Givaudan", "Suisse", "GIVN.SW", "Matériaux de base", "55", "CHF", "XSWX"),
    ("Barry Callebaut", "Suisse", "BARN.SW", "Consommation non discrétionnaire", "45", "CHF", "XSWX"),
    ("Straumann", "Suisse", "STMN.SW", "Santé", "20", "CHF", "XSWX"),
    ("Sonova", "Suisse", "SOON.SW", "Santé", "20", "CHF", "XSWX"),
    ("Kuehne+Nagel", "Suisse", "KGN.SW", "Industrie", "50", "CHF", "XSWX"),
    ("Adecco", "Suisse", "ADEN.SW", "Industrie", "50", "CHF", "XSWX"),
    ("GEA Group", "Allemagne", "GEA.DE", "Industrie", "50", "EUR", "XETR"),
    ("Alstom", "France", "ALO.PA", "Industrie", "50", "EUR", "XPAR"),
    ("STMicroelectronics", "France/Italie", "STM.PA", "Technologies de l'information", "10", "EUR", "XPAR"),
    ("Assa Abloy", "Suède", "ASSA-B.ST", "Industrie", "50", "SEK", "XSTO"),
    ("Axis Communications", "Suède", "AXIS.ST", "Technologies de l'information", "10", "SEK", "XSTO"),
    ("Alfa Laval", "Suède", "ALFA.ST", "Industrie", "50", "SEK", "XSTO"),
    ("Sandvik", "Suède", "SAND.ST", "Industrie", "50", "SEK", "XSTO"),
    ("Epiroc", "Suède", "EPIO-A.ST", "Industrie", "50", "SEK", "XSTO"),
    ("Diageo", "Royaume-Uni", "DGE.L", "Consommation non discrétionnaire", "45", "GBP", "XLON"),
    ("Unilever", "Royaume-Uni", "ULVR.L", "Consommation non discrétionnaire", "45", "GBP", "XLON"),
    ("RELX", "Royaume-Uni", "REL.L", "Industrie", "50", "GBP", "XLON"),
    ("Rolls-Royce", "Royaume-Uni", "RR.L", "Industrie", "50", "GBP", "XLON"),
    ("BAE Systems", "Royaume-Uni", "BA.L", "Industrie", "50", "GBP", "XLON"),
    ("Rockwool", "Danemark", "ROCK-B.CO", "Industrie", "50", "DKK", "XCSE"),
    ("SIG Combibloc", "Suisse", "SIGN.SW", "Industrie", "50", "CHF", "XSWX"),
    ("Zurich Insurance", "Suisse", "ZURN.SW", "Services financiers", "30", "CHF", "XSWX"),
    ("Swiss Re", "Suisse", "SREN.SW", "Services financiers", "30", "CHF", "XSWX"),
    ("UBS", "Suisse", "UBSG.SW", "Services financiers", "30", "CHF", "XSWX"),
]

# Check existing in DB first
print("Checking DB for names or tickers...")
for c in candidates:
    r = fetch_all("SELECT internal_code, name, is_active FROM instruments WHERE name ILIKE %s", (f"%{c[0]}%",))
    if r:
        print(f"  DB match for {c[0]}: {r}")

print(f"\nEvaluating {len(candidates)} priority candidates with yfinance...\n")
results = []

for name, country, ticker, sec_name, sec_code, cur, exch in candidates:
    try:
        t = yf.Ticker(ticker)
        df = t.history(period="max", interval="1wk")
        if df.empty or len(df) < 52:
            print(f"{name:<22} ({ticker:<10}): INSUFFISANT / NON COTÉ ({len(df)} sem)")
            results.append({"name": name, "ticker": ticker, "status": "DELISTED_OR_EMPTY", "error": f"len={len(df)}"})
            continue
        
        closes = df['Close'].dropna().values
        dates = [d.date() if hasattr(d, 'date') else d for d in df.index][-len(closes):]
        fit = fit_log_linear(dates, closes)
        z = fit["z_score"]
        last_price = float(closes[-1])
        r2 = fit["r_squared"]
        slope = fit["slope_annual"]
        
        if z <= 1.0:
            status = "ELIGIBLE (SCREENER)"
        elif z > 2.5:
            status = "SURCOTÉ (PARKED z>2.5)"
        else:
            status = "EN ATTENTE (PARKED 1.0<z<=2.5)"
            
        results.append({
            "name": name,
            "country": country,
            "ticker": ticker,
            "sec_name": sec_name,
            "sec_code": sec_code,
            "cur": cur,
            "exch": exch,
            "price": last_price,
            "z": z,
            "r2": r2,
            "slope": slope,
            "status": status,
            "dates_count": len(dates)
        })
        print(f"{name:<22} ({ticker:<10}) : cours={last_price:>8.2f} {cur:<4} | z={z:>+6.2f} | R²={r2:.2f} | {status}")
    except Exception as e:
        print(f"{name:<22} ({ticker:<10}): ERREUR {e}")
        results.append({"name": name, "ticker": ticker, "status": "ERROR", "error": str(e)})

print("\n--- SYNTHÈSE DES 27 NOUVEAUX TITRES SOUMIS ---")
eligible = [r for r in results if r.get("status") == "ELIGIBLE (SCREENER)"]
parked_over = [r for r in results if r.get("status") == "SURCOTÉ (PARKED z>2.5)"]
parked_wait = [r for r in results if r.get("status") == "EN ATTENTE (PARKED 1.0<z<=2.5)"]
unlisted = [r for r in results if r.get("status") in ("DELISTED_OR_EMPTY", "ERROR")]

print(f"Éligibles au screener actif (z <= 1.0)        : {len(eligible)}")
print(f"En attente en antichambre (1.0 < z <= 2.5)   : {len(parked_wait)}")
print(f"Surcotés en antichambre (z > 2.5)            : {len(parked_over)}")
print(f"Non cotés / retirés de la cote              : {len(unlisted)}")
