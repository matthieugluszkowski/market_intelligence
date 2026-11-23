import sys
sys.path.insert(0, 'src')
from market_intelligence.db import fetch_all

# 100 leaders list
all_100 = [
    # FRANCE (1-50)
    (1, "LVMH", "France", "MC.PA", "EQ:FR:LVMH", "Consommation discrétionnaire", "Leader mondial du luxe"),
    (2, "L'Oréal", "France", "OR.PA", "EQ:FR:OREAL", "Consommation non discrétionnaire", "N°1 mondial des cosmétiques"),
    (3, "Hermès", "France", "RMS.PA", "EQ:FR:HERMES", "Consommation discrétionnaire", "Leader mondial du luxe haut de gamme"),
    (4, "Kering", "France", "KER.PA", "EQ:FR:KERING", "Consommation discrétionnaire", "Leader mondial du luxe (Gucci, Saint Laurent)"),
    (5, "Chanel", "France", None, None, "Consommation discrétionnaire", "Leader mondial du luxe (Privée / Wertheimer)"),
    (6, "Pernod Ricard", "France", "RI.PA", "EQ:FR:PERNOD", "Consommation non discrétionnaire", "N°2 mondial des spiritueux"),
    (7, "Rémy Cointreau", "France", "RCO.PA", "EQ:FR:REMYCOINTREAU", "Consommation non discrétionnaire", "Leader cognac & spiritueux premium"),
    (8, "Danone", "France", "BN.PA", "EQ:FR:DANONE", "Consommation non discrétionnaire", "Leader produits laitiers & nutrition"),
    (9, "Lactalis", "France", None, None, "Consommation non discrétionnaire", "Leader mondial produits laitiers (Privée / Besnier)"),
    (10, "Sodexo", "France", "SW.PA", "EQ:FR:SODEXO", "Consommation discrétionnaire", "Leader restauration collective & services"),
    (11, "Air Liquide", "France", "AI.PA", "EQ:FR:AIRLIQUIDE", "Matériaux de base", "Leader mondial gaz industriels"),
    (12, "Air France-KLM", "France", "AF.PA", "EQ:FR:AIRFRANCEKLM", "Consommation discrétionnaire", "Leader européen transport aérien"),
    (13, "Airbus", "France", "AIR.PA", "EQ:FR:AIRBUS", "Industrie", "Cogrand leader mondial aéronautique"),
    (14, "Safran", "France", "SAF.PA", "EQ:FR:SAFRAN", "Industrie", "Leader mondial propulseurs civils"),
    (15, "Thales", "France", "HO.PA", "EQ:FR:THALES", "Industrie", "Leader défense, aérospatiale, cyber"),
    (16, "Dassault Aviation", "France", "AM.PA", "EQ:FR:DASSAULTAVIATION", "Industrie", "Leader avions d'affaires et Rafale"),
    (17, "Dassault Systèmes", "France", "DSY.PA", "EQ:FR:DASSAULTSYS", "Technologies de l'information", "Leader mondial logiciels 3D / PLM"),
    (18, "Capgemini", "France", "CAP.PA", "EQ:FR:CAPGEMINI", "Technologies de l'information", "Leader européen conseil et services IT"),
    (19, "Atos", "France", "ATO.PA", "EQ:FR:ATOS", "Technologies de l'information", "Acteur majeur transformation numérique"),
    (20, "Schneider Electric", "France", "SU.PA", "EQ:FR:SCHNEIDER", "Industrie", "Leader gestion énergie & automatisation"),
    (21, "Legrand", "France", "LR.PA", "EQ:FR:LEGRAND", "Industrie", "Leader matériel électrique bâtiment"),
    (22, "Nexans", "France", "NEX.PA", "EQ:FR:NEXANS", "Industrie", "Leader câbles et systèmes électriques"),
    (23, "Michelin", "France", "ML.PA", "EQ:FR:MICHELIN", "Consommation discrétionnaire", "Cogrand leader mondial pneumatique"),
    (24, "Valeo", "France", "FR.PA", "EQ:FR:VALEO", "Consommation discrétionnaire", "Leader équipementier auto ADAS/élec"),
    (25, "Forvia", "France", "FRVIA.PA", "EQ:FR:FORVIA", "Consommation discrétionnaire", "Leader mondial équipements automobiles"),
    (26, "Plastic Omnium", "France", "OPM.PA", "EQ:FR:OPMOBILITY", "Consommation discrétionnaire", "Leader réservoirs/extérieurs (OPmobility)"),
    (27, "Saint-Gobain", "France", "SGO.PA", "EQ:FR:SAINTGOBAIN", "Industrie", "Leader matériaux de construction"),
    (28, "Imerys", "France", "NK.PA", "EQ:FR:IMERYS", "Matériaux de base", "Leader minéraux industriels"),
    (29, "Veolia", "France", "VIE.PA", "EQ:FR:VEOLIA", "Services aux collectivités", "Leader mondial eau, déchets, énergie"),
    (30, "Suez", "France", None, None, "Services aux collectivités", "Leader eau et déchets (Privée / Retirée suite OPA)"),
    (31, "EDF", "France", None, None, "Services aux collectivités", "Plus grand exploitant nucléaire (Privée / 100% État)"),
    (32, "Engie", "France", "ENGI.PA", "EQ:FR:ENGIE", "Services aux collectivités", "Leader européen énergie bas carbone"),
    (33, "Orano", "France", None, None, "Services aux collectivités", "Leader combustible nucléaire (Privée / État)"),
    (34, "TotalEnergies", "France", "TTE.PA", "EQ:FR:TTE", "Energie", "Major énergétique mondial"),
    (35, "Sanofi", "France", "SAN.PA", "EQ:FR:SANOFI", "Santé", "Leader mondial vaccination et pharma"),
    (36, "Ipsen", "France", "IPN.PA", "EQ:FR:IPSEN", "Santé", "Leader toxine botulique thérapeutique"),
    (37, "Servier", "France", None, None, "Santé", "Leader cardio/onco (Privée / Fondation FIRS)"),
    (38, "BioMérieux", "France", "BIM.PA", "EQ:FR:BIOMERIEUX", "Santé", "Leader diagnostic in vitro"),
    (39, "Eurofins Scientific", "France", "ERF.PA", "EQ:LU:EUROFINSSCIENTIF", "Santé", "Leader bioanalyse et environnement"),
    (40, "EssilorLuxottica", "France", "EL.PA", "EQ:FR:ESSILOR", "Santé", "Leader mondial optique ophtalmique"),
    (41, "JCDecaux", "France", "DEC.PA", "EQ:FR:JCDECAUX", "Consommation discrétionnaire", "N°1 mondial publicité extérieure"),
    (42, "Publicis Groupe", "France", "PUB.PA", "EQ:FR:PUBLICIS", "Consommation discrétionnaire", "Leader mondial communication"),
    (43, "Edenred", "France", "EDEN.PA", "EQ:FR:EDENRED", "Industrie", "Leader mondial avantages salariés B2B"),
    (44, "Worldline", "France", "WLN.PA", "EQ:FR:WORLDLINE", "Technologies de l'information", "Leader européen paiements transactionnels"),
    (45, "BNP Paribas", "France", "BNP.PA", "EQ:FR:BNP", "Services financiers", "Leader bancaire européen par actifs"),
    (46, "AXA", "France", "CS.PA", "EQ:FR:AXA", "Services financiers", "Leader mondial assurance"),
    (47, "Amundi", "France", "AMUN.PA", "EQ:FR:AMUNDI", "Services financiers", "Premier gestionnaire d'actifs européen"),
    (48, "Natixis", "France", None, None, "Services financiers", "Banque de grande clientèle (Privée / Retirée BPCE)"),
    (49, "Bureau Veritas", "France", "BVI.PA", "EQ:FR:BUREAUVERITAS", "Industrie", "Leader mondial contrôle & certification"),
    (50, "SGS", "Suisse", "SGSN.SW", "EQ:CH:SGS", "Industrie", "Leader mondial inspection & certification"),

    # DACH (51-80)
    (51, "SAP", "Allemagne", "SAP.DE", "EQ:DE:SAP", "Technologies de l'information", "Leader mondial ERP d'entreprise"),
    (52, "Siemens", "Allemagne", "SIE.DE", "EQ:DE:SIEMENS", "Industrie", "Leader automatisation & électrification"),
    (53, "Bosch", "Allemagne", None, None, "Consommation discrétionnaire", "Leader équipement auto (Privée / Fondation)"),
    (54, "Continental", "Allemagne", "CON.DE", "EQ:DE:CONTINENTAL", "Consommation discrétionnaire", "Leader mondial pneumatiques & auto"),
    (55, "ZF Friedrichshafen", "Allemagne", None, None, "Consommation discrétionnaire", "Leader mondial transmissions (Privée / Fondation)"),
    (56, "Schaeffler", "Allemagne", "SHA0.DE", "EQ:DE:SCHAEFFLER", "Industrie", "Leader roulements précision"),
    (57, "Trumpf", "Allemagne", None, None, "Industrie", "Leader machines laser (Privée / Familiale)"),
    (58, "Kärcher", "Allemagne", None, None, "Industrie", "Leader nettoyeurs haute pression (Privée / Familiale)"),
    (59, "Festo", "Allemagne", None, None, "Industrie", "Leader automatisation pneumatique (Privée / Familiale)"),
    (60, "Würth", "Allemagne", None, None, "Industrie", "Leader vente directe fixation (Privée / Familiale)"),
    (61, "Rational", "Allemagne", "RAA.DE", "EQ:DE:RATIONAL", "Industrie", "Leader cuisson professionnelle"),
    (62, "Herrenknecht", "Allemagne", None, None, "Industrie", "Leader mondial tunneliers (Privée / Familiale)"),
    (63, "Krones", "Allemagne", "KRN.DE", "EQ:DE:KRONES", "Industrie", "Leader lignes embouteillage"),
    (64, "KHS", "Allemagne", None, None, "Industrie", "Leader machines emballage (Privée / Salzgitter)"),
    (65, "Carl Zeiss", "Allemagne", "AFX.DE", "EQ:DE:CARLZEISSMEDITEC", "Santé", "Leader optique précision (CZ Meditec)"),
    (66, "Sartorius", "Allemagne", "SRT.DE", "EQ:DE:SARTORIUSAG", "Santé", "Leader équipements labo & bioprocédés"),
    (67, "Eppendorf", "Allemagne", None, None, "Santé", "Leader instruments labo (Privée / Familiale)"),
    (68, "Fresenius Medical Care", "Allemagne", "FME.DE", "EQ:DE:FRESENIUSMEDICAL", "Santé", "Leader mondial dialyse"),
    (69, "Bayer", "Allemagne", "BAYN.DE", "EQ:DE:BAYER", "Santé", "Leader pharma & agrosciences"),
    (70, "BASF", "Allemagne", "BAS.DE", "EQ:DE:BASF", "Matériaux de base", "Plus grand groupe chimique mondial"),
    (71, "Covestro", "Allemagne", "1COV.F", "EQ:DE:COVESTRO", "Matériaux de base", "Leader polymères haute performance"),
    (72, "Clariant", "Suisse", "CLN.SW", "EQ:CH:CLARIANT", "Matériaux de base", "Leader spécialités chimiques"),
    (73, "Sika", "Suisse", "SIKA.SW", "EQ:CH:SIKA", "Matériaux de base", "Leader adhésifs étanchéité construction"),
    (74, "Geberit", "Suisse", "GEBN.SW", "EQ:CH:GEBERIT", "Industrie", "Leader européen systèmes sanitaires"),
    (75, "Schindler", "Suisse", "SCHN.SW", "EQ:CH:SCHINDLER", "Industrie", "Leader ascenseurs & escalators"),
    (76, "ABB", "Suisse", "ABBN.SW", "EQ:CH:ABB", "Industrie", "Leader robotique & électrification"),
    (77, "Stadler Rail", "Suisse", "SRAIL.SW", "EQ:CH:STADLERRAIL", "Industrie", "Leader matériel ferroviaire"),
    (78, "Logitech", "Suisse", "LOGN.SW", "EQ:CH:LOGITECH", "Technologies de l'information", "Leader périphériques informatiques"),
    (79, "Swatch Group", "Suisse", "UHR.SW", "EQ:CH:SWATCHGROUP", "Consommation discrétionnaire", "Leader mondial horlogerie"),
    (80, "Richemont", "Suisse", "CFR.SW", "EQ:CH:RICHEMONT", "Consommation discrétionnaire", "Leader luxe horloger & joaillier"),

    # AUTRES EUROPE (81-100)
    (81, "ASML", "Pays-Bas", "ASML.AS", "EQ:NL:ASML", "Technologies de l'information", "Monopole mondial lithographie EUV"),
    (82, "NXP Semiconductors", "Pays-Bas", "NXPI", "EQ:NL:NXPI", "Technologies de l'information", "Leader semi-conducteurs auto"),
    (83, "Philips", "Pays-Bas", "PHIA.AS", "EQ:NL:KONINKLIJKEPHILI", "Santé", "Leader santé connectée & imagerie"),
    (84, "Heineken", "Pays-Bas", "HEIA.AS", "EQ:NL:HEINEKEN", "Consommation non discrétionnaire", "Leader mondial brasserie"),
    (85, "Randstad", "Pays-Bas", "RAND.AS", "EQ:NL:RANDSTAD", "Industrie", "Leader mondial intérim & RH"),
    (86, "Adyen", "Pays-Bas", "ADYEN.AS", "EQ:NL:ADYEN", "Technologies de l'information", "Leader paiements en ligne"),
    (87, "Booking Holdings", "Pays-Bas/US", "BKNG", "EQ:US:BOOKING", "Consommation discrétionnaire", "Leader mondial voyages en ligne"),
    (88, "Novo Nordisk", "Danemark", "NOVO-B.CO", "EQ:DK:NOVONORDISK", "Santé", "Leader mondial diabète et obésité"),
    (89, "Vestas", "Danemark", "VWSB.DE", "EQ:DK:VESTASWINDSYSTEM", "Industrie", "Leader mondial des éoliennes"),
    (90, "Ørsted", "Danemark", "ORSTED.CO", "EQ:DK:ORSTED", "Services aux collectivités", "Leader éolien offshore"),
    (91, "LEGO", "Danemark", None, None, "Consommation discrétionnaire", "Leader jouets construction (Privée / Kirkbi)"),
    (92, "Maersk", "Danemark", "MAERSK-B.CO", "EQ:DK:MAERSK", "Industrie", "Leader mondial transport conteneurs"),
    (93, "Ericsson", "Suède", "ERIC-B.ST", "EQ:SE:ERICSSON", "Télécommunications", "Leader réseaux télécoms mobiles"),
    (94, "Spotify", "Suède/US", "639.DE", "EQ:SE:SPOTIFYTECHNOLOG", "Technologies de l'information", "Leader streaming audio"),
    (95, "Atlas Copco", "Suède", "ATCO-A.ST", "EQ:SE:ATLASCOPCO", "Industrie", "Leader mondial compresseurs"),
    (96, "Volvo Group", "Suède", "VOLV-B.ST", "EQ:SE:VOLVOB", "Industrie", "Leader mondial poids lourds & bus"),
    (97, "Ferrari", "Italie", "RACE.MI", "EQ:IT:FERRARI", "Consommation discrétionnaire", "Leader voitures de sport d'exception"),
    (98, "Ferrero", "Italie", None, None, "Consommation non discrétionnaire", "Leader confiserie premium (Privée / Familiale)"),
    (99, "Inditex", "Espagne", "ITX.MC", "EQ:ES:INDITEX", "Consommation discrétionnaire", "Leader mondial mode (Zara)"),
    (100, "Arm Holdings", "Royaume-Uni", "ARM", "EQ:GB:ARM", "Technologies de l'information", "Architecture processeurs mobiles")
]

# Fetch DB state
db_fits = {r[0]: (r[1], r[2]) for r in fetch_all('''
    SELECT i.internal_code, f.z_score, f.last_close 
    FROM instruments i 
    JOIN regression_fits f ON f.instrument_id = i.id AND f.as_of_date = (SELECT max(as_of_date) FROM regression_fits WHERE instrument_id = i.id)
''')}

parked_state = {r[0]: (r[1], r[2], r[3]) for r in fetch_all('''
    SELECT internal_code, status, live_z_score, last_z_at_parking FROM parked_instruments
''')}

active_in_screener = []
parked_list = []
unlisted_list = []

for item in all_100:
    num, name, country, ticker, code, sector, desc = item
    if ticker is None:
        unlisted_list.append((num, name, country, sector, desc))
    elif code in parked_state and parked_state[code][0] == 'parked':
        p = parked_state[code]
        z = p[1] if p[1] is not None else p[2]
        parked_list.append((num, name, country, ticker, code, z, sector, desc))
    elif code in db_fits:
        z, close = db_fits[code]
        active_in_screener.append((num, name, country, ticker, code, z, close, sector, desc))
    else:
        print(f"Warning: {name} ({code}) not categorized!")

print("==================================================================")
print(f"BILAN GLOBAL DES 100 CHAMPIONS MONDIAUX EUROPÉENS")
print("==================================================================")
print(f"  1. Actifs & suivis dans le Screener (z <= 1.0) : {len(active_in_screener)}")
print(f"  2. En Antichambre / Parkés (z > 1.0 ou > 2.5)  : {len(parked_list)}")
print(f"  3. Entreprises non cotées (Privées/Fondations): {len(unlisted_list)}")
print(f"  TOTAL                                         : {len(active_in_screener) + len(parked_list) + len(unlisted_list)} / 100")

print("\n--- 1. ÉLIGIBLES & ACTIFS DANS LE SCREENER (77 titres) ---")
for r in sorted(active_in_screener, key=lambda x: x[5]):
    print(f"  #{r[0]:02d} {r[1]:<24} ({r[2]:<10}) | {r[3]:<11} | cours: {r[6]:>8.2f} | z: {r[5]:>+5.2f} | {r[7]}")

print("\n--- 2. EN ANTICHAMBRE / PARKÉS (5 titres) ---")
for r in sorted(parked_list, key=lambda x: x[5], reverse=True):
    print(f"  #{r[0]:02d} {r[1]:<24} ({r[2]:<10}) | {r[3]:<11} | z: {r[5]:>+5.2f} | Statut: {'SURCOTÉ (z > 2.5)' if r[5] > 2.5 else 'EN ATTENTE (1.0 < z <= 2.5)'} | {r[6]}")

print("\n--- 3. NON COTÉES (18 entreprises) ---")
for r in unlisted_list:
    print(f"  #{r[0]:02d} {r[1]:<24} ({r[2]:<10}) | {r[3]:<30} | {r[4]}")
