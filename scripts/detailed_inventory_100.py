import sys
sys.path.insert(0, 'src')
from market_intelligence.db import fetch_all

# List of all 100 companies with metadata
all_100 = [
    # FRANCE (1-50)
    (1, "LVMH", "France", "EQ:FR:MC", "MC.PA", "Consommation discrétionnaire", "40", "Leader mondial du luxe"),
    (2, "L'Oréal", "France", "EQ:FR:OR", "OR.PA", "Consommation non discrétionnaire", "45", "N°1 mondial des cosmétiques"),
    (3, "Hermès", "France", "EQ:FR:RMS", "RMS.PA", "Consommation discrétionnaire", "40", "Leader mondial du luxe haut de gamme"),
    (4, "Kering", "France", "EQ:FR:KER", "KER.PA", "Consommation discrétionnaire", "40", "Leader mondial du luxe (Gucci, Saint Laurent)"),
    (5, "Chanel", "France", None, None, "Consommation discrétionnaire", "40", "Leader mondial du luxe / parfum et mode (Non cotée)"),
    (6, "Pernod Ricard", "France", "EQ:FR:RI", "RI.PA", "Consommation non discrétionnaire", "45", "N°2 mondial des spiritueux"),
    (7, "Rémy Cointreau", "France", "EQ:FR:RCO", "RCO.PA", "Consommation non discrétionnaire", "45", "Leader du cognac et spiritueux premium"),
    (8, "Danone", "France", "EQ:FR:BN", "BN.PA", "Consommation non discrétionnaire", "45", "Leader mondial des produits laitiers frais"),
    (9, "Lactalis", "France", None, None, "Consommation non discrétionnaire", "45", "Leader mondial des produits laitiers (Non cotée)"),
    (10, "Sodexo", "France", "EQ:FR:SW", "SW.PA", "Consommation discrétionnaire", "40", "Leader restauration collective et services"),
    (11, "Air Liquide", "France", "EQ:FR:AI", "AI.PA", "Matériaux de base", "55", "Leader mondial des gaz industriels"),
    (12, "Air France-KLM", "France", "EQ:FR:AF", "AF.PA", "Consommation discrétionnaire", "40", "Leader européen du transport aérien"),
    (13, "Airbus", "France", "EQ:FR:AIR", "AIR.PA", "Industrie", "50", "Cogrand leader mondial de l'aéronautique civile"),
    (14, "Safran", "France", "EQ:FR:SAF", "SAF.PA", "Industrie", "50", "Leader mondial des propulseurs civils"),
    (15, "Thales", "France", "EQ:FR:HO", "HO.PA", "Industrie", "50", "Leader défense, aérospatiale, cyber"),
    (16, "Dassault Aviation", "France", "EQ:FR:AM", "AM.PA", "Industrie", "50", "Leader avions d'affaires et Rafale"),
    (17, "Dassault Systèmes", "France", "EQ:FR:DSY", "DSY.PA", "Technologies de l'information", "10", "Leader mondial logiciels 3D / PLM"),
    (18, "Capgemini", "France", "EQ:FR:CAP", "CAP.PA", "Technologies de l'information", "10", "Leader européen conseil et services IT"),
    (19, "Atos", "France", "EQ:FR:ATO", "ATO.PA", "Technologies de l'information", "10", "Acteur majeur transformation numérique"),
    (20, "Schneider Electric", "France", "EQ:FR:SU", "SU.PA", "Industrie", "50", "Leader gestion énergie et automatisation"),
    (21, "Legrand", "France", "EQ:FR:LR", "LR.PA", "Industrie", "50", "Leader équipements électriques bâtiment"),
    (22, "Nexans", "France", "EQ:FR:NEX", "NEX.PA", "Industrie", "50", "Leader câbles et systèmes électriques"),
    (23, "Michelin", "France", "EQ:FR:ML", "ML.PA", "Consommation discrétionnaire", "40", "Cogrand leader mondial du pneumatique"),
    (24, "Valeo", "France", "EQ:FR:FR", "FR.PA", "Consommation discrétionnaire", "40", "Leader équipementier auto électrification/ADAS"),
    (25, "Forvia", "France", "EQ:FR:FRVIA", "FRVIA.PA", "Consommation discrétionnaire", "40", "Leader mondial équipements automobiles"),
    (26, "Plastic Omnium", "France", "EQ:FR:OPM", "OPM.PA", "Consommation discrétionnaire", "40", "Leader systèmes réservoirs/extérieurs (OPmobility)"),
    (27, "Saint-Gobain", "France", "EQ:FR:SGO", "SGO.PA", "Industrie", "50", "Leader matériaux construction et performance"),
    (28, "Imerys", "France", "EQ:FR:NK", "NK.PA", "Matériaux de base", "55", "Leader minéraux industriels spécialisés"),
    (29, "Veolia", "France", "EQ:FR:VIE", "VIE.PA", "Services aux collectivités", "65", "Leader mondial eau, déchets, énergie"),
    (30, "Suez", "France", None, None, "Services aux collectivités", "65", "Leader eau et déchets (Non cotée / post OPA)"),
    (31, "EDF", "France", None, None, "Services aux collectivités", "65", "Plus grand exploitant nucléaire (Non cotée / 100% État)"),
    (32, "Engie", "France", "EQ:FR:ENGI", "ENGI.PA", "Services aux collectivités", "65", "Leader européen énergie bas carbone"),
    (33, "Orano", "France", None, None, "Services aux collectivités", "65", "Leader cycle combustible nucléaire (Non cotée / État)"),
    (34, "TotalEnergies", "France", "EQ:FR:TTE", "TTE.PA", "Energie", "60", "Major énergétique mondial (Parked z>2.5)"),
    (35, "Sanofi", "France", "EQ:FR:SAN", "SAN.PA", "Santé", "20", "Leader vaccination et pharma spécialité"),
    (36, "Ipsen", "France", "EQ:FR:IPN", "IPN.PA", "Santé", "20", "Leader toxine botulique thérapeutique"),
    (37, "Servier", "France", None, None, "Santé", "20", "Leader cardiologie / oncologie (Non cotée / Fondation)"),
    (38, "BioMérieux", "France", "EQ:FR:BIM", "BIM.PA", "Santé", "20", "Leader diagnostic in vitro microbiologique"),
    (39, "Eurofins Scientific", "France", "EQ:FR:ERF", "ERF.PA", "Santé", "20", "Leader analyses biologiques et environnementales"),
    (40, "EssilorLuxottica", "France", "EQ:FR:EL", "EL.PA", "Santé", "20", "Leader mondial optique ophtalmique"),
    (41, "JCDecaux", "France", "EQ:FR:DEC", "DEC.PA", "Consommation discrétionnaire", "40", "N°1 mondial de la publicité extérieure"),
    (42, "Publicis Groupe", "France", "EQ:FR:PUB", "PUB.PA", "Consommation discrétionnaire", "40", "Leader mondial communication et publicité"),
    (43, "Edenred", "France", "EQ:FR:EDEN", "EDEN.PA", "Industrie", "50", "Leader mondial avantages salariés et B2B"),
    (44, "Worldline", "France", "EQ:FR:WLN", "WLN.PA", "Technologies de l'information", "10", "Leader européen paiements transactionnels"),
    (45, "BNP Paribas", "France", "EQ:FR:BNP", "BNP.PA", "Services financiers", "30", "L'une des 1ères banques mondiales par actifs"),
    (46, "AXA", "France", "EQ:FR:CS", "CS.PA", "Services financiers", "30", "L'un des premiers assureurs mondiaux"),
    (47, "Amundi", "France", "EQ:FR:AMUN", "AMUN.PA", "Services financiers", "30", "Premier gestionnaire d'actifs européen"),
    (48, "Natixis", "France", None, None, "Services financiers", "30", "Banque financement et gestion (Non cotée / 100% BPCE)"),
    (49, "Bureau Veritas", "France", "EQ:FR:BVI", "BVI.PA", "Industrie", "50", "Leader mondial contrôle, inspection, certif"),
    (50, "SGS", "Suisse", "EQ:CH:SGSN", "SGSN.SW", "Industrie", "50", "Leader mondial inspection, vérif, certif"),

    # DACH (51-80)
    (51, "SAP", "Allemagne", "EQ:DE:SAP", "SAP.DE", "Technologies de l'information", "10", "Leader mondial logiciels ERP entreprise"),
    (52, "Siemens", "Allemagne", "EQ:DE:SIE", "SIE.DE", "Industrie", "50", "Leader mondial automatisation et électrification"),
    (53, "Bosch", "Allemagne", None, None, "Consommation discrétionnaire", "40", "Leader mondial équipements auto (Non cotée / Fondation)"),
    (54, "Continental", "Allemagne", "EQ:DE:CON", "CON.DE", "Consommation discrétionnaire", "40", "Leader pneumatiques et technologies auto"),
    (55, "ZF Friedrichshafen", "Allemagne", None, None, "Consommation discrétionnaire", "40", "Leader transmissions mobilité (Non cotée / Fondation)"),
    (56, "Schaeffler", "Allemagne", "EQ:DE:SHA", "SHA0.DE", "Industrie", "50", "Leader roulements et composants précision"),
    (57, "Trumpf", "Allemagne", None, None, "Industrie", "50", "Leader machines-outils laser (Non cotée / Familiale)"),
    (58, "Kärcher", "Allemagne", None, None, "Industrie", "50", "Leader nettoyeurs haute pression (Non cotée / Familiale)"),
    (59, "Festo", "Allemagne", None, None, "Industrie", "50", "Leader automatisation pneumatique (Non cotée / Familiale)"),
    (60, "Würth", "Allemagne", None, None, "Industrie", "50", "Leader vente directe fixation (Non cotée / Familiale)"),
    (61, "Rational", "Allemagne", "EQ:DE:RAA", "RAA.DE", "Industrie", "50", "Leader mondial cuisson professionnelle"),
    (62, "Herrenknecht", "Allemagne", None, None, "Industrie", "50", "Leader mondial des tunneliers (Non cotée / Familiale)"),
    (63, "Krones", "Allemagne", "EQ:DE:KRN", "KRN.DE", "Industrie", "50", "Leader mondial lignes embouteillage"),
    (64, "KHS", "Allemagne", None, None, "Industrie", "50", "Leader machines emballage (Non cotée / Filiale Salzgitter)"),
    (65, "Carl Zeiss", "Allemagne", "EQ:DE:AFX", "AFX.DE", "Santé", "20", "Leader optique précision (Carl Zeiss Meditec cotée)"),
    (66, "Sartorius", "Allemagne", "EQ:DE:SRT", "SRT.DE", "Santé", "20", "Leader équipements labo et bioprocédés"),
    (67, "Eppendorf", "Allemagne", None, None, "Santé", "20", "Leader instruments laboratoire (Non cotée / Familiale)"),
    (68, "Fresenius Medical Care", "Allemagne", "EQ:DE:FME", "FME.DE", "Santé", "20", "Leader mondial de la dialyse"),
    (69, "Bayer", "Allemagne", "EQ:DE:BAYN", "BAYN.DE", "Santé", "20", "Leader pharma, santé animale et agrosciences"),
    (70, "BASF", "Allemagne", "EQ:DE:BAS", "BAS.DE", "Matériaux de base", "55", "Plus grand groupe chimique mondial"),
    (71, "Covestro", "Allemagne", "EQ:DE:1COV", "1COV.F", "Matériaux de base", "55", "Leader polymères haute performance"),
    (72, "Clariant", "Suisse", "EQ:CH:CLN", "CLN.SW", "Matériaux de base", "55", "Leader spécialités chimiques"),
    (73, "Sika", "Suisse", "EQ:CH:SIKA", "SIKA.SW", "Matériaux de base", "55", "Leader adhésifs et étanchéité construction"),
    (74, "Geberit", "Suisse", "EQ:CH:GEBN", "GEBN.SW", "Industrie", "50", "Leader européen systèmes sanitaires"),
    (75, "Schindler", "Suisse", "EQ:CH:SCHN", "SCHN.SW", "Industrie", "50", "Leader ascenseurs et escalators"),
    (76, "ABB", "Suisse", "EQ:CH:ABBN", "ABBN.SW", "Industrie", "50", "Leader électrification et robotique"),
    (77, "Stadler Rail", "Suisse", "EQ:CH:SRAIL", "SRAIL.SW", "Industrie", "50", "Leader matériel roulant ferroviaire"),
    (78, "Logitech", "Suisse", "EQ:CH:LOGN", "LOGN.SW", "Technologies de l'information", "10", "Leader périphériques informatiques"),
    (79, "Swatch Group", "Suisse", "EQ:CH:UHR", "UHR.SW", "Consommation discrétionnaire", "40", "Leader mondial horlogerie"),
    (80, "Richemont", "Suisse", "EQ:CH:CFR", "CFR.SW", "Consommation discrétionnaire", "40", "Leader luxe horloger et joaillier"),

    # AUTRES EUROPE (81-100)
    (81, "ASML", "Pays-Bas", "EQ:NL:ASML", "ASML.AS", "Technologies de l'information", "10", "Monopole mondial lithographie EUV"),
    (82, "NXP Semiconductors", "Pays-Bas", "EQ:US:NXPI", "NXPI", "Technologies de l'information", "10", "Leader semi-conducteurs auto"),
    (83, "Philips", "Pays-Bas", "EQ:NL:PHIA", "PHIA.AS", "Santé", "20", "Leader santé connectée et imagerie"),
    (84, "Heineken", "Pays-Bas", "EQ:NL:HEIA", "HEIA.AS", "Consommation non discrétionnaire", "45", "Un des premiers brasseurs mondiaux"),
    (85, "Randstad", "Pays-Bas", "EQ:NL:RAND", "RAND.AS", "Industrie", "50", "Leader travail temporaire et RH"),
    (86, "Adyen", "Pays-Bas", "EQ:NL:ADYEN", "ADYEN.AS", "Technologies de l'information", "10", "Leader européen paiements en ligne"),
    (87, "Booking Holdings", "Pays-Bas/US", "EQ:US:BKNG", "BKNG", "Consommation discrétionnaire", "40", "Leader réservation voyages en ligne"),
    (88, "Novo Nordisk", "Danemark", "EQ:DK:NOVO-B", "NOVO-B.CO", "Santé", "20", "Leader mondial diabète et obésité"),
    (89, "Vestas", "Danemark", "EQ:DK:VWS", "VWSB.DE", "Industrie", "50", "Leader mondial des éoliennes"),
    (90, "Ørsted", "Danemark", "EQ:DK:ORSTED", "ORSTED.CO", "Services aux collectivités", "65", "Leader mondial éolien offshore"),
    (91, "LEGO", "Danemark", None, None, "Consommation discrétionnaire", "40", "Leader jouets construction (Non cotée / Kirkbi)"),
    (92, "Maersk", "Danemark", "EQ:DK:MAERSK-B", "MAERSK-B.CO", "Industrie", "50", "Leader transport maritime conteneurisé"),
    (93, "Ericsson", "Suède", "EQ:SE:ERIC-B", "ERIC-B.ST", "Télécommunications", "15", "Leader mondial réseaux télécoms mobiles"),
    (94, "Spotify", "Suède/US", "EQ:US:SPOT", "639.DE", "Technologies de l'information", "10", "Leader streaming audio"),
    (95, "Atlas Copco", "Suède", "EQ:SE:ATCO-A", "ATCO-A.ST", "Industrie", "50", "Leader compresseurs et air industriel"),
    (96, "Volvo Group", "Suède", "EQ:SE:VOLV-B", "VOLV-B.ST", "Industrie", "50", "Leader poids lourds, bus et engins"),
    (97, "Ferrari", "Italie", "EQ:IT:RACE", "RACE.MI", "Consommation discrétionnaire", "40", "Leader voitures de sport d'exception"),
    (98, "Ferrero", "Italie", None, None, "Consommation non discrétionnaire", "45", "Leader mondial confiserie premium (Non cotée / Familiale)"),
    (99, "Inditex", "Espagne", "EQ:ES:ITX", "ITX.MC", "Consommation discrétionnaire", "40", "Plus grand distributeur mode (Zara)"),
    (100, "Arm Holdings", "Royaume-Uni", "EQ:US:ARM", "ARM", "Technologies de l'information", "10", "Architecture processeurs mobile/embarqué")
]

# Query current DB status
db_map = {}
rows = fetch_all('''
    SELECT i.id, i.internal_code, i.name, i.is_active, s.symbol, f.z_score, p.status, p.live_z_score
    FROM instruments i
    LEFT JOIN instrument_symbols s ON s.instrument_id = i.id AND s.is_primary = TRUE
    LEFT JOIN regression_fits f ON f.instrument_id = i.id AND f.as_of_date = (SELECT max(as_of_date) FROM regression_fits WHERE instrument_id = i.id)
    LEFT JOIN parked_instruments p ON p.internal_code = i.internal_code
''')
for r in rows:
    # Key by symbol and code
    if r[4]:
        db_map[r[4].upper()] = r
    if r[1]:
        db_map[r[1].upper()] = r

# Also check parked_instruments table
parked_all = fetch_all('SELECT internal_code, symbol_yfinance, name, status, live_z_score, last_z_at_parking FROM parked_instruments')
parked_map = {p[0].upper(): p for p in parked_all}

print(f"Loaded {len(db_map)} mappings from DB.")

stats = {"unlisted": 0, "active_screener": 0, "parked_overvalued": 0, "parked_waiting": 0, "new_eligible": 0, "new_parked": 0}

classified = []
for item in all_100:
    num, name, country, code, ticker, sector_name, sector_code, desc = item
    if ticker is None:
        stats["unlisted"] += 1
        classified.append((num, name, country, "NON COTÉE", "—", "—", sector_name, desc))
        continue
    
    # Check if in DB
    db_match = db_map.get(ticker.upper()) or (code and db_map.get(code.upper()))
    park_match = (code and parked_map.get(code.upper()))
    
    if db_match and db_match[3] is True: # active in DB
        z = db_match[5]
        z_str = f"{z:+.2f}" if z is not None else "N/A"
        stats["active_screener"] += 1
        classified.append((num, name, country, "DÉJÀ ACTIF", ticker, z_str, sector_name, desc))
    elif park_match or (db_match and db_match[3] is False):
        p_row = park_match
        z_val = p_row[4] if p_row and p_row[4] is not None else (p_row[5] if p_row else None)
        z_str = f"{z_val:+.2f}" if z_val is not None else "N/A"
        stats["parked_overvalued"] += 1
        classified.append((num, name, country, "DÉJÀ PARKÉ", ticker, z_str, sector_name, desc))
    else:
        classified.append((num, name, country, "NOUVEAU", ticker, "—", sector_name, desc))

print(f"\nInventory of 100 Leaders:")
for c in classified:
    print(f"#{c[0]:02d} {c[1]:<22} ({c[2]:<11}) [{c[3]:<11}] Ticker: {c[4]:<12} z: {c[5]:<6} Secteur: {c[6]}")

print(f"\nStats:")
for k, v in stats.items():
    print(f"  {k}: {v}")
