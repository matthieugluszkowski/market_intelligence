import sys
import yfinance as yf
sys.path.insert(0, 'src')
from market_intelligence.analytics.regression import fit_log_linear

corrected = [
    ("Roche", "RO.SW", "CHF"),
    ("Kuehne+Nagel", "KNIN.SW", "CHF"),
    ("GEA Group", "G1A.DE", "EUR"),
    ("STMicroelectronics", "STMPA.PA", "EUR"),
    ("Epiroc", "EPI-A.ST", "SEK"),
]

for name, ticker, cur in corrected:
    df = yf.Ticker(ticker).history(period="max", interval="1wk")
    closes = df['Close'].dropna().values
    dates = [d.date() if hasattr(d, 'date') else d for d in df.index][-len(closes):]
    fit = fit_log_linear(dates, closes)
    z = fit["z_score"]
    price = closes[-1]
    status = "ELIGIBLE (SCREENER)" if z <= 1.0 else ("SURCOTE" if z > 2.5 else "EN ATTENTE")
    print(f"{name:<20} ({ticker:<10}) : cours={price:>8.2f} {cur} | z={z:>+6.2f} | R²={fit['r_squared']:.2f} | {status}")
