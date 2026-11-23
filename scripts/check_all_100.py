import sys
sys.path.insert(0, 'src')
from market_intelligence.db import fetch_all

# Exact list of 100 leaders
all_100 = [
    # FRANCE
    (1, "LVMH", "France", "MC.PA", "EQ:FR:MC", "Consommation discrétionnaire", "Luxe"),
    (2, "L'Oréal", "France", "OR.PA", "EQ:FR:OR", "Consommation non discrétionnaire", "Cosmétiques"),
    (3, "Hermès", "France", "RMS.PA", "EQ:FR:RMS", "Consommation discrétionnaire", "Luxe"),
    (4, "Kering", "France", "KER.PA", "EQ:FR:KER", "Consommation discrétionnaire", "Luxe"),
    (5, "Chanel", "France", None, None, "Consommation discrétionnaire", "Luxe (Privée)"),
    (6, "Pernod Ricard", "France", "RI.PA", "EQ:FR:RI", "Consommation non discrétionnaire", "Spiritueux"),
    (7, "Rémy Cointreau", "France", "RCO.PA", "EQ:FR:RCO", "Consommation non discrétionnaire", "Spiritueux"),
    (8, "Danone", "France", "BN.PA", "EQ:FR:BN", "Consommation non discrétionnaire", "Agroalimentaire"),
    (9, "Lactalis", "France", None, None, "Consommation non discrétionnaire", "Produits laitiers (Privée)"),
    (10, "Sodexo", "France", "SW.PA", "EQ:FR:SW", "Consommation discrétionnaire", "Restauration / Services"),
    (11, "Air Liquide", "France", "AI.PA", "EQ:FR:AI", "Matériaux de base", "Gaz industriels"),
    (12, "Air France-KLM", "France", "AF.PA", "EQ:FR:AF", "Consommation discrétionnaire", "Transport aérien"),
    (13, "Airbus", "France", "AIR.PA", "EQ:FR:AIR", "Industrie", "Aéronautique"),
    (14, "Safran", "France", "SAF.PA", "EQ:FR:SAF", "Industrie", "Moteurs aéronautiques"),
    (15, "Thales", "France", "HO.PA", "EQ:FR:HO", "Industrie", "Défense / Aérospatiale"),
    (16, "Dassault Aviation", "France", "AM.PA", "EQ:FR:AM", "Industrie", "Aviation civile / militaire"),
    (17, "Dassault Systèmes", "France", "DSY.PA", "EQ:FR:DSY", "Technologies de l'information", "Logiciels 3D / PLM"),
    (18, "Capgemini", "France", "CAP.PA", "EQ:FR:CAP", "Technologies de l'information", "Services IT / Conseil"),
    (19, "Atos", "France", "ATO.PA", "EQ:FR:ATO", "Technologies de l'information", "Services numériques"),
    (20, "Schneider Electric", "France", "SU.PA", "EQ:FR:SU", "Industrie", "Gestion énergie"),
    (21, "Legrand", "France", "LR.PA", "EQ:FR:LR", "Industrie", "Matériel électrique bâtiment"),
    (22, "Nexans", "France", "NEX.PA", "EQ:FR:NEX", "Industrie", "Câbles électriques"),
    (23, "Michelin", "France", "ML.PA", "EQ:FR:ML", "Consommation discrétionnaire", "Pneumatiques"),
    (24, "Valeo", "France", "FR.PA", "EQ:FR:FR", "Consommation discrétionnaire", "Équipements auto"),
    (25, "Forvia", "France", "FRVIA.PA", "EQ:FR:FRVIA", "Consommation discrétionnaire", "Équipements auto"),
    (26, "Plastic Omnium", "France", "OPM.PA", "EQ:FR:OPM", "Consommation discrétionnaire", "Extérieurs auto / OPmobility"),
    (27, "Saint-Gobain", "France", "SGO.PA", "EQ:FR:SGO", "Industrie", "Matériaux construction"),
    (28, "Imerys", "France", "NK.PA", "EQ:FR:NK", "Matériaux de base", "Minéraux industriels"),
    (29, "Veolia", "France", "VIE.PA", "EQ:FR:VIE", "Services aux collectivités", "Eau et déchets"),
    (30, "Suez", "France", None, None, "Services aux collectivités", "Eau et déchets (Privée / OPA)"),
    (31, "EDF", "France", None, None, "Services aux collectivités", "Nucléaire / Énergie (100% État)"),
    (32, "Engie", "France", "ENGI.PA", "EQ:FR:ENGI", "Services aux collectivités", "Énergie bas carbone"),
    (33, "Orano", "France", None, None, "Services aux collectivités", "Cycle nucléaire (90% État)"),
    (34, "TotalEnergies", "France", "TTE.PA", "EQ:FR:TTE", "Energie", "Pétrole et gaz"),
    (35, "Sanofi", "France", "SAN.PA", "EQ:FR:SAN", "Santé", "Pharmacie / Vaccins"),
    (36, "Ipsen", "France", "IPN.PA", "EQ:FR:IPN", "Santé", "Biopharma spécialisée"),
    (37, "Servier", "France", None, None, "Santé", "Pharmacie (Fondation privée)"),
    (38, "BioMérieux", "France", "BIM.PA", "EQ:FR:BIM", "Santé", "Diagnostic in vitro"),
    (39, "Eurofins Scientific", "France", "ERF.PA", "EQ:FR:ERF", "Santé", "Bioanalyse"),
    (40, "EssilorLuxottica", "France", "EL.PA", "EQ:FR:EL", "Santé", "Optique ophtalmique"),
    (41, "JCDecaux", "France", "DEC.PA", "EQ:FR:DEC", "Consommation discrétionnaire", "Publicité extérieure"),
    (42, "Publicis Groupe", "France", "PUB.PA", "EQ:FR:PUB", "Consommation discrétionnaire", "Communication"),
    (43, "Edenred", "France", "EDEN.PA", "EQ:FR:EDEN", "Industrie", "Services B2B"),
    (44, "Worldline", "France", "WLN.PA", "EQ:FR:WLN", "Technologies de l'information", "Paiements"),
    (45, "BNP Paribas", "France", "BNP.PA", "EQ:FR:BNP", "Services financiers", "Banque"),
    (46, "AXA", "France", "CS.PA", "EQ:FR:CS", "Services financiers", "Assurance"),
    (47, "Amundi", "France", "AMUN.PA", "EQ:FR:AMUN", "Services financiers", "Gestion d'actifs"),
    (48, "Natixis", "France", None, None, "Services financiers", "Banque / Gestion (100% BPCE)"),
    (49, "Bureau Veritas", "France", "BVI.PA", "EQ:FR:BVI", "Industrie", "Certification / Contrôle"),
    (50, "SGS", "Suisse", "SGSN.SW", "EQ:CH:SGSN", "Industrie", "Inspection / Certification"),

    # DACH
    (51, "SAP", "Allemagne", "SAP.DE", "EQ:DE:SAP", "Technologies de l'information", "Logiciels ERP"),
    (52, "Siemens", "Allemagne", "SIE.DE", "EQ:DE:SIE", "Industrie", "Automatisation / Électrification"),
    (53, "Bosch", "Allemagne", None, None, "Consommation discrétionnaire", "Équipements auto (Fondation)"),
    (54, "Continental", "Allemagne", "CON.DE", "EQ:DE:CON", "Consommation discrétionnaire", "Pneumatiques"),
    (55, "ZF Friedrichshafen", "Allemagne", None, None, "Consommation discrétionnaire", "Transmissions auto (Fondation)"),
    (56, "Schaeffler", "Allemagne", "SHA.DE", "EQ:DE:SHA", "Industrie", "Roulements de précision"),
    (57, "Trumpf", "Allemagne", None, None, "Industrie", "Machines laser (Privée)"),
    (58, "Kärcher", "Allemagne", None, None, "Industrie", "Nettoyeurs haute pression (Privée)"),
    (59, "Festo", "Allemagne", None, None, "Industrie", "Automatisation pneumatique (Privée)"),
    (60, "Würth", "Allemagne", None, None, "Industrie", "Fixation et assemblage (Privée)"),
    (61, "Rational", "Allemagne", "RAA.DE", "EQ:DE:RAA", "Industrie", "Cuisson professionnelle"),
    (62, "Herrenknecht", "Allemagne", None, None, "Industrie", "Tunneliers (Privée)"),
    (63, "Krones", "Allemagne", "KRN.DE", "EQ:DE:KRN", "Industrie", "Lignes embouteillage"),
    (64, "KHS", "Allemagne", None, None, "Industrie", "Machines emballage (100% Salzgitter)"),
    (65, "Carl Zeiss", "Allemagne", "AFX.DE", "EQ:DE:AFX", "Santé", "Optique médicale / Lithographie"),
    (66, "Sartorius", "Allemagne", "SRT.DE", "EQ:DE:SRT", "Santé", "Équipements de laboratoire"),
    (67, "Eppendorf", "Allemagne", None, None, "Santé", "Instruments laboratoire (Privée)"),
    (68, "Fresenius Medical Care", "Allemagne", "FME.DE", "EQ:DE:FME", "Santé", "Dialyse"),
    (69, "Bayer", "Allemagne", "BAYN.DE", "EQ:DE:BAYN", "Santé", "Pharma et agrochimie"),
    (70, "BASF", "Allemagne", "BAS.DE", "EQ:DE:BAS", "Matériaux de base", "Chimie"),
    (71, "Covestro", "Allemagne", "1COV.DE", "EQ:DE:1COV", "Matériaux de base", "Polymères"),
    (72, "Clariant", "Suisse", "CLN.SW", "EQ:CH:CLN", "Matériaux de base", "Chimie de spécialité"),
    (73, "Sika", "Suisse", "SIKA.SW", "EQ:CH:SIKA", "Matériaux de base", "Chimie construction"),
    (74, "Geberit", "Suisse", "GEBN.SW", "EQ:CH:GEBN", "Industrie", "Systèmes sanitaires"),
    (75, "Schindler", "Suisse", "SCHN.SW", "EQ:CH:SCHN", "Industrie", "Ascenseurs"),
    (76, "ABB", "Suisse", "ABBN.SW", "EQ:CH:ABBN", "Industrie", "Robotique / Électrification"),
    (77, "Stadler Rail", "Suisse", "SRAIL.SW", "EQ:CH:SRAIL", "Industrie", "Matériel ferroviaire"),
    (78, "Logitech", "Suisse", "LOGN.SW", "EQ:CH:LOGN", "Technologies de l'information", "Périphériques"),
    (79, "Swatch Group", "Suisse", "UHR.SW", "EQ:CH:UHR", "Consommation discrétionnaire", "Horlogerie"),
    (80, "Richemont", "Suisse", "CFR.SW", "EQ:CH:CFR", "Consommation discrétionnaire", "Luxe horloger"),

    # AUTRES EUROPE
    (81, "ASML", "Pays-Bas", "ASML.AS", "EQ:NL:ASML", "Technologies de l'information", "Lithographie semi-conducteurs"),
    (82, "NXP Semiconductors", "Pays-Bas", "NXPI", "EQ:US:NXPI", "Technologies de l'information", "Semi-conducteurs auto"),
    (83, "Philips", "Pays-Bas", "PHIA.AS", "EQ:NL:PHIA", "Santé", "Santé et imagerie médicale"),
    (84, "Heineken", "Pays-Bas", "HEIA.AS", "EQ:NL:HEIA", "Consommation non discrétionnaire", "Brasserie"),
    (85, "Randstad", "Pays-Bas", "RAND.AS", "EQ:NL:RAND", "Industrie", "Travail temporaire / RH"),
    (86, "Adyen", "Pays-Bas", "ADYEN.AS", "EQ:NL:ADYEN", "Technologies de l'information", "Paiements"),
    (87, "Booking Holdings", "Pays-Bas/US", "BKNG", "EQ:US:BKNG", "Consommation discrétionnaire", "Voyages en ligne"),
    (88, "Novo Nordisk", "Danemark", "NOVO-B.CO", "EQ:DK:NOVO-B", "Santé", "Diabète et obésité"),
    (89, "Vestas", "Danemark", "VWS.CO", "EQ:DK:VWS", "Industrie", "Éoliennes"),
    (90, "Ørsted", "Danemark", "ORSTED.CO", "EQ:DK:ORSTED", "Services aux collectivités", "Éolien offshore"),
    (91, "LEGO", "Danemark", None, None, "Consommation discrétionnaire", "Jouets (Privée)"),
    (92, "Maersk", "Danemark", "MAERSK-B.CO", "EQ:DK:MAERSK-B", "Industrie", "Transport conteneurs"),
    (93, "Ericsson", "Suède", "ERIC-B.ST", "EQ:SE:ERIC-B", "Télécommunications", "Équipements télécoms"),
    (94, "Spotify", "Suède/US", "SPOT", "EQ:US:SPOT", "Technologies de l'information", "Streaming audio"),
    (95, "Atlas Copco", "Suède", "ATCO-A.ST", "EQ:SE:ATCO-A", "Industrie", "Compresseurs industriels"),
    (96, "Volvo Group", "Suède", "VOLV-B.ST", "EQ:SE:VOLV-B", "Industrie", "Poids lourds"),
    (97, "Ferrari", "Italie", "RACE.MI", "EQ:IT:RACE", "Consommation discrétionnaire", "Voitures de sport"),
    (98, "Ferrero", "Italie", None, None, "Consommation non discrétionnaire", "Confiserie (Privée)"),
    (99, "Inditex", "Espagne", "ITX.MC", "EQ:ES:ITX", "Consommation discrétionnaire", "Mode (Zara)"),
    (100, "Arm", "Royaume-Uni", "ARM", "EQ:US:ARM", "Technologies de l'information", "Architecture puces")
]

# Load all instruments and symbols from DB
db_instruments = fetch_all('''
    SELECT i.id, i.internal_code, i.name, i.is_active, s.symbol, f.z_score, p.status, p.live_z_score
    FROM instruments i
    LEFT JOIN instrument_symbols s ON s.instrument_id = i.id
    LEFT JOIN regression_fits f ON f.instrument_id = i.id AND f.as_of_date = (SELECT max(as_of_date) FROM regression_fits WHERE instrument_id = i.id)
    LEFT JOIN parked_instruments p ON p.internal_code = i.internal_code
''')

# Map symbol -> list of rows
sym_map = {}
for r in db_instruments:
    if r[4]:
        sym_map[r[4].upper()] = r

unlisted = []
already_in_db = []
to_evaluate = []

for num, name, country, ticker, code, sector, desc in all_100:
    if ticker is None:
        unlisted.append((num, name, country, sector, desc))
        continue
    
    # Check if symbol exists in DB
    match = sym_map.get(ticker.upper())
    if match:
        already_in_db.append((num, name, country, ticker, match, sector, desc))
    else:
        to_evaluate.append((num, name, country, ticker, code, sector, desc))

print(f"Total 100 Leaders breakdown:")
print(f"  - Non cotées (Unlisted) : {len(unlisted)}")
print(f"  - Déjà en base (DB)     : {len(already_in_db)}")
print(f"  - Nouveaux à évaluer    : {len(to_evaluate)}")

print("\n--- NOUVEAUX CANDIDATS A EVALUER ---")
for num, name, country, ticker, code, sector, desc in to_evaluate:
    print(f"#{num:02d} {name:<22} ({country:<11}) Ticker: {ticker:<12} Secteur: {sector}")
