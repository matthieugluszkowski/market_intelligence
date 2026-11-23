import yfinance as yf

test_tickers = [
    ("Roche", ["ROG.SW", "RO.SW", "RHHBY", "RHO.SW"]),
    ("Kuehne+Nagel", ["KNIN.SW", "KNIN"]),
    ("GEA Group", ["G1A.DE", "GEA.DE"]),
    ("STMicroelectronics", ["STMPA.PA", "STM.PA", "STM.MI", "STM"]),
    ("Epiroc", ["EPI-A.ST", "EPI-B.ST", "EPIRO-A.ST"]),
]

for name, candidates in test_tickers:
    print(f"\nTesting {name}:")
    for t in candidates:
        try:
            df = yf.Ticker(t).history(period="1mo")
            if not df.empty:
                print(f"  [OK] {t}: {len(df)} bars, last close = {df['Close'].iloc[-1]:.2f}")
            else:
                print(f"  [EMPTY] {t}")
        except Exception as e:
            print(f"  [ERR] {t}: {e}")
