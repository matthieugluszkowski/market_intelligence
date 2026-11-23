import sys
import yfinance as yf
import numpy as np
from datetime import date
sys.path.insert(0, 'src')
from market_intelligence.analytics.regression import fit_log_linear

candidates = [
    # (num, name, ticker, country, sector)
    (7, "Rémy Cointreau", "RCO.PA", "France", "Consommation non discrétionnaire"),
    (19, "Atos", "ATO.PA", "France", "Technologies de l'information"),
    (44, "Worldline", "WLN.PA", "France", "Technologies de l'information"),
    (49, "Bureau Veritas", "BVI.PA", "France", "Industrie"),
    (50, "SGS", "SGSN.SW", "Suisse", "Industrie"),
    (54, "Continental AG", "CON.DE", "Allemagne", "Consommation discrétionnaire"),
    (66, "Sartorius AG", "SRT.DE", "Allemagne", "Santé"),
    (71, "Covestro", "1COV.DE", "Allemagne", "Matériaux de base"),
    (72, "Clariant", "CLN.SW", "Suisse", "Matériaux de base"),
    (73, "Sika", "SIKA.SW", "Suisse", "Matériaux de base"),
    (74, "Geberit", "GEBN.SW", "Suisse", "Industrie"),
    (75, "Schindler", "SCHN.SW", "Suisse", "Industrie"),
    (76, "ABB", "ABBN.SW", "Suisse", "Industrie"),
    (77, "Stadler Rail", "SRAIL.SW", "Suisse", "Industrie"),
    (78, "Logitech", "LOGN.SW", "Suisse", "Technologies de l'information"),
    (79, "Swatch Group", "UHR.SW", "Suisse", "Consommation discrétionnaire"),
    (80, "Richemont", "CFR.SW", "Suisse", "Consommation discrétionnaire"),
    (82, "NXP Semiconductors", "NXPI", "Pays-Bas", "Technologies de l'information"),
    (87, "Booking Holdings", "BKNG", "Pays-Bas/US", "Consommation discrétionnaire"),
    (88, "Novo Nordisk", "NOVO-B.CO", "Danemark", "Santé"),
    (90, "Ørsted", "ORSTED.CO", "Danemark", "Services aux collectivités"),
    (92, "Maersk", "MAERSK-B.CO", "Danemark", "Industrie"),
    (93, "Ericsson", "ERIC-B.ST", "Suède", "Télécommunications"),
    (95, "Atlas Copco", "ATCO-A.ST", "Suède", "Industrie"),
    (96, "Volvo Group", "VOLV-B.ST", "Suède", "Industrie"),
    (100, "Arm Holdings", "ARM", "Royaume-Uni", "Technologies de l'information")
]

print(f"Evaluating {len(candidates)} new candidates in memory...\n")
results = []

for num, name, ticker, country, sector in candidates:
    try:
        t = yf.Ticker(ticker)
        df = t.history(period="max", interval="1wk")
        if df.empty or len(df) < 52:
            print(f"#{num:02d} {name:<20} ({ticker}): ERROR - insufficient data ({len(df)} wks)")
            continue
        
        closes = df['Close'].dropna().values
        dates = [d.date() if hasattr(d, 'date') else d for d in df.index]
        if len(dates) != len(closes):
            dates = dates[-len(closes):]
        
        fit = fit_log_linear(dates, closes)
        z = fit["z_score"]
        last_price = float(closes[-1])
        r2 = fit["r_squared"]
        slope = fit["slope_annual"]
        
        # Determine status according to rules:
        # z <= 1.0 => ELIGIBLE (active screener)
        # z > 1.0 => WAITING / PARKED (in antichambre, no heavy bars)
        # z > 2.5 => OVERVALUED / PARKED
        if z <= 1.0:
            status = "ELIGIBLE (SCREENER)"
        elif z > 2.5:
            status = "SURCOTE (PARKED z>2.5)"
        else:
            status = "EN ATTENTE (PARKED 1.0<z<=2.5)"
            
        results.append({
            "num": num,
            "name": name,
            "ticker": ticker,
            "country": country,
            "sector": sector,
            "price": last_price,
            "z": z,
            "r2": r2,
            "slope": slope,
            "status": status,
            "dates_count": len(dates)
        })
        print(f"#{num:02d} {name:<20} ({ticker:<11}) : cours={last_price:>8.2f} | z={z:>+6.2f} | R²={r2:.2f} | {status}")
    except Exception as e:
        print(f"#{num:02d} {name:<20} ({ticker}): EXCEPTION - {e}")

print("\n--- SUMMARY ---")
eligible = [r for r in results if "ELIGIBLE" in r["status"]]
parked = [r for r in results if "PARKED" in r["status"]]
print(f"Eligibles pour le screener actif (z <= 1.0) : {len(eligible)}")
print(f"En antichambre / surveillés (z > 1.0)       : {len(parked)}")
