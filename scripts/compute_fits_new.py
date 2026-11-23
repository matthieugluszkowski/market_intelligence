import sys
sys.path.insert(0, 'src')
from market_intelligence.jobs import compute_fits

codes = [
    'EQ:FR:REMYCOINTREAU', 'EQ:FR:ATOS', 'EQ:FR:WORLDLINE', 'EQ:FR:BUREAUVERITAS',
    'EQ:CH:SGS', 'EQ:DE:CONTINENTAL', 'EQ:DE:SARTORIUSAG', 'EQ:DE:COVESTRO',
    'EQ:CH:CLARIANT', 'EQ:CH:SIKA', 'EQ:CH:GEBERIT', 'EQ:CH:SCHINDLER',
    'EQ:CH:LOGITECH', 'EQ:CH:SWATCHGROUP', 'EQ:CH:RICHEMONT', 'EQ:NL:NXPI',
    'EQ:US:BOOKING', 'EQ:DK:NOVONORDISK', 'EQ:DK:ORSTED', 'EQ:SE:ATLASCOPCO',
    'EQ:SE:VOLVOB', 'EQ:GB:ARM', 'EQ:LU:EUROFINSSCIENTIF'
]

print(f"Calcul des fits pour {len(codes)} instruments...")
for code in codes:
    try:
        compute_fits.run(only=code)
    except Exception as e:
        print(f"Erreur pour {code}: {e}")

print("Tous les fits ont été calculés !")
