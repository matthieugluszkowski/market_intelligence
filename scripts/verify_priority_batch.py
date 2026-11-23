import sys
sys.path.insert(0, 'src')
from market_intelligence.db import fetch_all

priority_listed = [
    ("Roche", "Suisse", "RO.SW", "EQ:CH:ROCHE", "Santé"),
    ("Novartis", "Suisse", "NOVN.SW", "EQ:CH:NOVARTIS", "Santé"),
    ("Nestlé", "Suisse", "NESN.SW", "EQ:CH:NESTLE", "Consommation non discrétionnaire"),
    ("Givaudan", "Suisse", "GIVN.SW", "EQ:CH:GIVAUDAN", "Matériaux de base"),
    ("Barry Callebaut", "Suisse", "BARN.SW", "EQ:CH:BARRYCALLEBAUT", "Consommation non discrétionnaire"),
    ("Straumann", "Suisse", "STMN.SW", "EQ:CH:STRAUMANN", "Santé"),
    ("Sonova", "Suisse", "SOON.SW", "EQ:CH:SONOVA", "Santé"),
    ("Kuehne+Nagel", "Suisse", "KNIN.SW", "EQ:CH:KUEHNENAGEL", "Industrie"),
    ("Adecco", "Suisse", "ADEN.SW", "EQ:CH:ADECCO", "Industrie"),
    ("Allianz", "Allemagne", "ALV.DE", "EQ:DE:ALLIANZ", "Services financiers"),
    ("Munich Re", "Allemagne", "MUV2.DE", "EQ:DE:MUNICHRE", "Services financiers"),
    ("Siemens Healthineers", "Allemagne", "SHL.DE", "EQ:DE:SIEMENSHEALTHINE", "Santé"),
    ("Merck KGaA", "Allemagne", "MRK.DE", "EQ:DE:MERCK", "Santé"),
    ("DHL Group", "Allemagne", "DHL.DE", "EQ:DE:DEUTSCHEPOST", "Industrie"),
    ("Brenntag", "Allemagne", "BN.DE", "EQ:DE:BRENNTAG", "Industrie"),
    ("Symrise", "Allemagne", "SY1.DE", "EQ:DE:SYMRISE", "Matériaux de base"),
    ("GEA Group", "Allemagne", "G1A.DE", "EQ:DE:GEAGROUP", "Industrie"),
    ("Rheinmetall", "Allemagne", "RHM.DE", "EQ:DE:RHEINMETALL", "Industrie"),
    ("MTU Aero Engines", "Allemagne", "MTX.DE", "EQ:DE:MTUAEROENGINES", "Industrie"),
    ("Prysmian", "Italie", "PRY.MI", "EQ:IT:PRYSMIAN", "Industrie"),
    ("Nexi", "Italie", "NEXI.MI", "EQ:IT:NEXI", "Technologies de l'information"),
    ("Leonardo", "Italie", "LDO.MI", "EQ:IT:LEONARDO", "Industrie"),
    ("Alstom", "France", "ALO.PA", "EQ:FR:ALSTOM", "Industrie"),
    ("STMicroelectronics", "France/Italie", "STMPA.PA", "EQ:FR:STMICRO", "Technologies de l'information"),
    ("Soitec", "France", "SOI.PA", "EQ:FR:SOITEC", "Technologies de l'information"),
    ("Kone", "Finlande", "KONE.HE", "EQ:FI:KONE", "Industrie"),
    ("Konecranes", "Finlande", "KCR.HE", "EQ:FI:KONECRANES", "Industrie"),
    ("Wärtsilä", "Finlande", "WRT1V.HE", "EQ:FI:WARTSILA", "Industrie"),
    ("Neste", "Finlande", "NESTE.HE", "EQ:FI:NESTE", "Energie"),
    ("Assa Abloy", "Suède", "ASSA-B.ST", "EQ:SE:ASSAABLOY", "Industrie"),
    ("Axis Communications", "Suède", "AXIS.ST", None, "Technologies de l'information"),
    ("Hexagon", "Suède", "HEXA-B.ST", "EQ:SE:HEXAGONPUBL", "Technologies de l'information"),
    ("Alfa Laval", "Suède", "ALFA.ST", "EQ:SE:ALFALAVAL", "Industrie"),
    ("Sandvik", "Suède", "SAND.ST", "EQ:SE:SANDVIK", "Industrie"),
    ("Epiroc", "Suède", "EPI-A.ST", "EQ:SE:EPIROC", "Industrie"),
    ("Signify", "Pays-Bas", "LIGHT.AS", "EQ:NL:SIGNIFY", "Industrie"),
    ("ASM International", "Pays-Bas", "ASM.AS", "EQ:NL:ASMINTERNATIONAL", "Technologies de l'information"),
    ("Besi", "Pays-Bas", "BESI.AS", "EQ:NL:SEMICONDUCTORIND", "Technologies de l'information"),
    ("Wolters Kluwer", "Pays-Bas", "WKL.AS", "EQ:NL:WOLTERS", "Industrie"),
    ("AB InBev", "Belgique", "ABI.BR", "EQ:BE:ABINBEV", "Consommation non discrétionnaire"),
    ("Diageo", "Royaume-Uni", "DGE.L", "EQ:GB:DIAGEO", "Consommation non discrétionnaire"),
    ("Unilever", "Royaume-Uni", "ULVR.L", "EQ:GB:UNILEVER", "Consommation non discrétionnaire"),
    ("RELX", "Royaume-Uni", "REL.L", "EQ:GB:RELX", "Industrie"),
    ("Amadeus", "Espagne", "AMS.MC", "EQ:ES:AMADEUS", "Consommation discrétionnaire"),
    ("Rolls-Royce", "Royaume-Uni", "RR.L", "EQ:GB:ROLLSROYCE", "Industrie"),
    ("BAE Systems", "Royaume-Uni", "BA.L", "EQ:GB:BAESYSTEMS", "Industrie"),
    ("Rockwool", "Danemark", "ROCK-B.CO", "EQ:DK:ROCKWOOL", "Industrie"),
    ("SIG Combibloc", "Suisse", "SIGN.SW", "EQ:CH:SIGCOMBIBLOC", "Industrie"),
    ("Zurich Insurance", "Suisse", "ZURN.SW", "EQ:CH:ZURICHINS", "Services financiers"),
    ("Swiss Re", "Suisse", "SREN.SW", "EQ:CH:SWISSRE", "Services financiers"),
    ("UBS", "Suisse", "UBSG.SW", "EQ:CH:UBS", "Services financiers"),
]

db_fits = {r[0]: (r[1], r[2]) for r in fetch_all('''
    SELECT i.internal_code, f.z_score, f.last_close 
    FROM instruments i 
    JOIN regression_fits f ON f.instrument_id = i.id AND f.as_of_date = (SELECT max(as_of_date) FROM regression_fits WHERE instrument_id = i.id)
''')}

parked_state = {r[0]: (r[1], r[2], r[3]) for r in fetch_all('''
    SELECT internal_code, status, live_z_score, last_z_at_parking FROM parked_instruments
''')}

active = []
parked = []
delisted = []

for name, country, ticker, code, sector in priority_listed:
    if code is None:
        delisted.append((name, country, ticker, sector, "Retirée de la cote suite à OPA (100% Canon)"))
    elif code in parked_state and parked_state[code][0] == 'parked':
        p = parked_state[code]
        z = p[1] if p[1] is not None else p[2]
        parked.append((name, country, ticker, code, z, sector))
    elif code in db_fits:
        z, close = db_fits[code]
        active.append((name, country, ticker, code, z, close, sector))
    else:
        print("Warning not found:", name, code)

print("==================================================================")
print(f"BILAN DU LOT PRIORITAIRE (51 TITRES COTÉS)")
print("==================================================================")
print(f"  - Actifs dans le Screener (z <= 1.0) : {len(active)} (24 déjà présents + 19 nouveaux)")
print(f"  - En Antichambre / Parkés (z > 1.0)  : {len(parked)}")
print(f"  - Retirée de la cote                 : {len(delisted)} (Axis Communications)")
print(f"  TOTAL                                : {len(active) + len(parked) + len(delisted)} / 51")

print("\n--- 19 NOUVEAUX ACTIFS DANS LE SCREENER ---")
new_codes = [
    'EQ:CH:NESTLE', 'EQ:GB:DIAGEO', 'EQ:CH:BARRYCALLEBAUT', 'EQ:DK:ROCKWOOL',
    'EQ:FR:ALSTOM', 'EQ:CH:KUEHNENAGEL', 'EQ:GB:UNILEVER', 'EQ:SE:EPIROC',
    'EQ:CH:STRAUMANN', 'EQ:CH:ADECCO', 'EQ:CH:SONOVA', 'EQ:CH:GIVAUDAN',
    'EQ:CH:SIGCOMBIBLOC', 'EQ:SE:ALFALAVAL', 'EQ:SE:ASSAABLOY', 'EQ:GB:RELX',
    'EQ:CH:SWISSRE', 'EQ:FR:STMICRO', 'EQ:DE:GEAGROUP'
]
new_active = [a for a in active if a[3] in new_codes]
for a in sorted(new_active, key=lambda x: x[4]):
    print(f"  {a[0]:<22} ({a[1]:<10}) | {a[2]:<10} | cours: {a[5]:>8.2f} | z: {a[4]:>+5.2f} | {a[6]}")

print("\n--- 7 EN ANTICHAMBRE / PARKÉS (1.0 < z <= 2.5) ---")
for p in sorted(parked, key=lambda x: x[4], reverse=True):
    print(f"  {p[0]:<22} ({p[1]:<10}) | {p[2]:<10} | z: {p[4]:>+5.2f} | En attente sous 1.0 | {p[5]}")
