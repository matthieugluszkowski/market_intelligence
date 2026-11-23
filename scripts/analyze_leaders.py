import sys
sys.path.insert(0, 'src')
from market_intelligence.db import fetch_all

# Leaders definitions
leaders = [
    # France
    (1, 'LVMH', 'MC.PA'), (2, 'L\'Oreal', 'OR.PA'), (3, 'Hermes', 'RMS.PA'), (4, 'Kering', 'KER.PA'),
    (6, 'Pernod Ricard', 'RI.PA'), (8, 'Danone', 'BN.PA'), (10, 'Sodexo', 'SW.PA'), (11, 'Air Liquide', 'AI.PA'),
    (12, 'Air France-KLM', 'AF.PA'), (13, 'Airbus', 'AIR.PA'), (14, 'Safran', 'SAF.PA'), (15, 'Thales', 'HO.PA'),
    (16, 'Dassault Aviation', 'AM.PA'), (17, 'Dassault Systemes', 'DSY.PA'), (18, 'Capgemini', 'CAP.PA'),
    (19, 'Atos', 'ATO.PA'), (20, 'Schneider Electric', 'SU.PA'), (21, 'Legrand', 'LR.PA'), (22, 'Nexans', 'NEX.PA'),
    (23, 'Michelin', 'ML.PA'), (24, 'Valeo', 'FR.PA'), (25, 'Forvia', 'FRVIA.PA'), (26, 'Plastic Omnium', 'OPM.PA'),
    (27, 'Saint-Gobain', 'SGO.PA'), (28, 'Imerys', 'NK.PA'), (29, 'Veolia', 'VIE.PA'), (32, 'Engie', 'ENGI.PA'),
    (34, 'TotalEnergies', 'TTE.PA'), (35, 'Sanofi', 'SAN.PA'), (36, 'Ipsen', 'IPN.PA'), (38, 'BioMerieux', 'BIM.PA'),
    (39, 'Eurofins Scientific', 'ERF.PA'), (40, 'EssilorLuxottica', 'EL.PA'), (41, 'JCDecaux', 'DEC.PA'),
    (42, 'Publicis Groupe', 'PUB.PA'), (43, 'Edenred', 'EDEN.PA'), (45, 'BNP Paribas', 'BNP.PA'),
    (46, 'AXA', 'CS.PA'), (47, 'Amundi', 'AMUN.PA'),
    # DACH
    (51, 'SAP', 'SAP.DE'), (52, 'Siemens', 'SIE.DE'),
    (54, 'Continental', 'CON.DE'), (56, 'Schaeffler', 'SHA.DE'), (61, 'Rational', 'RAA.DE'), (63, 'Krones', 'KRN.DE'),
    (65, 'Carl Zeiss', 'AFX.DE'), (66, 'Sartorius', 'SRT.DE'), (68, 'Fresenius Medical Care', 'FME.DE'),
    (69, 'Bayer', 'BAYN.DE'), (70, 'BASF', 'BAS.DE'),
    # Other Europe
    (81, 'ASML', 'ASML.AS'), (83, 'Philips', 'PHIA.AS'),
    (84, 'Heineken', 'HEIA.AS'), (85, 'Randstad', 'RAND.AS'), (86, 'Adyen', 'ADYEN.AS'), (89, 'Vestas', 'VWS.CO'),
    (94, 'Spotify', 'SPOT'), (97, 'Ferrari', 'RACE.MI'), (99, 'Inditex', 'ITX.MC'), (100, 'Arm', 'ARM')
]

print("=== CHECKING MATCHES IN DATABASE ===")
for num, name, sym in leaders:
    ticker_base = sym.split('.')[0]
    rows = fetch_all('''
        SELECT i.internal_code, i.name, s.symbol, i.is_active, f.z_score, p.status
        FROM instruments i
        LEFT JOIN instrument_symbols s ON s.instrument_id = i.id
        LEFT JOIN regression_fits f ON f.instrument_id = i.id AND f.as_of_date = (SELECT max(as_of_date) FROM regression_fits WHERE instrument_id = i.id)
        LEFT JOIN parked_instruments p ON p.internal_code = i.internal_code
        WHERE s.symbol = %s OR i.name ILIKE %s
    ''', (sym, f'%{name}%'))
    if rows:
        r = rows[0]
        z_str = f"{r[4]:+.2f}" if r[4] is not None else "N/A"
        print(f"#{num:02d} {name:<22} -> code:{r[0]:<20} sym:{str(r[2]):<10} act:{r[3]} z:{z_str} park:{r[5]}")
    else:
        print(f"#{num:02d} {name:<22} -> [NOT FOUND] sym:{sym}")
