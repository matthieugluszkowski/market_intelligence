import sys
sys.path.insert(0, 'src')
from market_intelligence.db import fetch_all

# Candidate listed companies from user prompt
listed_candidates = [
    # (name, country, ticker, segment)
    ("Roche", "Suisse", "ROG.SW", "Leader mondial de la biotech et du diagnostic", "Santé", "20", "CHF", "XSWX"),
    ("Novartis", "Suisse", "NOVN.SW", "Leader mondial de la pharma", "Santé", "20", "CHF", "XSWX"),
    ("Nestlé", "Suisse", "NESN.SW", "N°1 mondial de l’agroalimentaire", "Consommation non discrétionnaire", "45", "CHF", "XSWX"),
    ("Givaudan", "Suisse", "GIVN.SW", "N°1 mondial des arômes et parfums", "Matériaux de base", "55", "CHF", "XSWX"),
    ("Barry Callebaut", "Suisse", "BARN.SW", "N°1 mondial du chocolat B2B", "Consommation non discrétionnaire", "45", "CHF", "XSWX"),
    ("Straumann", "Suisse", "STMN.SW", "N°1 mondial des implants dentaires", "Santé", "20", "CHF", "XSWX"),
    ("Sonova", "Suisse", "SOON.SW", "Leader mondial des aides auditives", "Santé", "20", "CHF", "XSWX"),
    ("Kuehne+Nagel", "Suisse", "KGN.SW", "N°1 mondial du freight forwarding", "Industrie", "50", "CHF", "XSWX"),
    ("Adecco", "Suisse", "ADEN.SW", "Leader mondial du travail temporaire", "Industrie", "50", "CHF", "XSWX"),
    ("Allianz", "Allemagne", "ALV.DE", "L’un des premiers assureurs mondiaux", "Services financiers", "30", "EUR", "XETR"),
    ("Munich Re", "Allemagne", "MUV2.DE", "Cogrand leader mondial de la réassurance", "Services financiers", "30", "EUR", "XETR"),
    ("Siemens Healthineers", "Allemagne", "SHL.DE", "Leader mondial de l’imagerie médicale", "Santé", "20", "EUR", "XETR"),
    ("Merck KGaA", "Allemagne", "MRK.DE", "Leader mondial des solutions life science", "Santé", "20", "EUR", "XETR"),
    ("DHL Group", "Allemagne", "DHL.DE", "Leader mondial de la logistique", "Industrie", "50", "EUR", "XETR"),
    ("Brenntag", "Allemagne", "BN.DE", "N°1 mondial de la distribution chimique", "Industrie", "50", "EUR", "XETR"),
    ("Symrise", "Allemagne", "SY1.DE", "Top 3 mondial des arômes et parfums", "Matériaux de base", "55", "EUR", "XETR"),
    ("GEA Group", "Allemagne", "GEA.DE", "Leader mondial des équipements agroalimentaires", "Industrie", "50", "EUR", "XETR"),
    ("Rheinmetall", "Allemagne", "RHM.DE", "Leader européen de la défense terrestre", "Industrie", "50", "EUR", "XETR"),
    ("MTU Aero Engines", "Allemagne", "MTX.DE", "Leader mondial des moteurs aéronautiques de maintenance", "Industrie", "50", "EUR", "XETR"),
    ("Prysmian", "Italie", "PRY.MI", "N°1 mondial des câbles et systèmes énergétiques", "Industrie", "50", "EUR", "XMIL"),
    ("Nexi", "Italie", "NEXI.MI", "Leader européen des paiements", "Technologies de l'information", "10", "EUR", "XMIL"),
    ("Leonardo", "Italie", "LDO.MI", "Leader européen de la défense aérospatiale", "Industrie", "50", "EUR", "XMIL"),
    ("Alstom", "France", "ALO.PA", "Cogrand leader mondial du ferroviaire", "Industrie", "50", "EUR", "XPAR"),
    ("STMicroelectronics", "France/Italie", "STM.PA", "Leader mondial des semi-conducteurs", "Technologies de l'information", "10", "EUR", "XPAR"),
    ("Soitec", "France", "SOI.PA", "Leader mondial des wafers SOI", "Technologies de l'information", "10", "EUR", "XPAR"),
    ("Kone", "Finlande", "KONE.HE", "Cogrand leader mondial des ascenseurs", "Industrie", "50", "EUR", "XHEL"),
    ("Konecranes", "Finlande", "KCR.HE", "Leader mondial des ponts roulants", "Industrie", "50", "EUR", "XHEL"),
    ("Wärtsilä", "Finlande", "WRT1V.HE", "Leader mondial des moteurs marins", "Industrie", "50", "EUR", "XHEL"),
    ("Neste", "Finlande", "NESTE.HE", "Leader mondial du diesel renouvelable", "Energie", "60", "EUR", "XHEL"),
    ("Assa Abloy", "Suède", "ASSA-B.ST", "N°1 mondial des serrures et contrôle d’accès", "Industrie", "50", "SEK", "XSTO"),
    ("Axis Communications", "Suède", "AXIS.ST", "Leader mondial des caméras IP", "Technologies de l'information", "10", "SEK", "XSTO"),
    ("Hexagon", "Suède", "HEXA-B.ST", "Leader mondial de la métrologie numérique", "Technologies de l'information", "10", "SEK", "XSTO"),
    ("Alfa Laval", "Suède", "ALFA.ST", "Leader mondial des échangeurs thermiques", "Industrie", "50", "SEK", "XSTO"),
    ("Sandvik", "Suède", "SAND.ST", "Leader mondial des outils et équipements miniers", "Industrie", "50", "SEK", "XSTO"),
    ("Epiroc", "Suède", "EPIO-A.ST", "Leader mondial des équipements miniers", "Industrie", "50", "SEK", "XSTO"),
    ("Signify", "Pays-Bas", "LIGHT.AS", "N°1 mondial de l’éclairage", "Industrie", "50", "EUR", "XAMS"),
    ("ASM International", "Pays-Bas", "ASM.AS", "Leader mondial de la déposition ALD", "Technologies de l'information", "10", "EUR", "XAMS"),
    ("Besi", "Pays-Bas", "BESI.AS", "Leader mondial de l’assemblage avancé puces", "Technologies de l'information", "10", "EUR", "XAMS"),
    ("Wolters Kluwer", "Pays-Bas", "WKL.AS", "Leader mondial info pro & logiciels", "Industrie", "50", "EUR", "XAMS"),
    ("AB InBev", "Belgique", "ABI.BR", "N°1 mondial de la bière", "Consommation non discrétionnaire", "45", "EUR", "XBRU"),
    ("Diageo", "Royaume-Uni", "DGE.L", "N°1 mondial des spiritueux", "Consommation non discrétionnaire", "45", "GBP", "XLON"),
    ("Unilever", "Royaume-Uni", "ULVR.L", "Leader mondial des biens de consommation", "Consommation non discrétionnaire", "45", "GBP", "XLON"),
    ("RELX", "Royaume-Uni", "REL.L", "Leader mondial de l’édition scientifique", "Industrie", "50", "GBP", "XLON"),
    ("Amadeus", "Espagne", "AMS.MC", "Leader mondial systèmes réservation aérienne", "Consommation discrétionnaire", "40", "EUR", "XMAD"),
    ("Rolls-Royce", "Royaume-Uni", "RR.L", "Cogrand leader mondial moteurs aéro", "Industrie", "50", "GBP", "XLON"),
    ("BAE Systems", "Royaume-Uni", "BA.L", "Leader mondial de la défense", "Industrie", "50", "GBP", "XLON"),
    ("Rockwool", "Danemark", "ROCK-B.CO", "Leader mondial de la laine de roche", "Industrie", "50", "DKK", "XCSE"),
    ("SIG Combibloc", "Suisse", "SIGN.SW", "Leader mondial emballage carton liquide", "Industrie", "50", "CHF", "XSWX"),
    ("Zurich Insurance", "Suisse", "ZURN.SW", "Leader mondial de l’assurance", "Services financiers", "30", "CHF", "XSWX"),
    ("Swiss Re", "Suisse", "SREN.SW", "Cogrand leader mondial de la réassurance", "Services financiers", "30", "CHF", "XSWX"),
    ("UBS", "Suisse", "UBSG.SW", "Leader mondial de la gestion de fortune", "Services financiers", "30", "CHF", "XSWX"),
]

# Fetch DB symbols & fits
db_rows = fetch_all('''
    SELECT i.id, i.internal_code, i.name, i.is_active, s.symbol, f.z_score, p.status as parked_status
    FROM instruments i
    LEFT JOIN instrument_symbols s ON s.instrument_id = i.id
    LEFT JOIN regression_fits f ON f.instrument_id = i.id AND f.as_of_date = (SELECT max(as_of_date) FROM regression_fits WHERE instrument_id = i.id)
    LEFT JOIN parked_instruments p ON p.internal_code = i.internal_code
''')

db_sym_map = {r[4].upper(): r for r in db_rows if r[4]}
db_name_map = {r[2].lower(): r for r in db_rows if r[2]}

already_active = []
already_parked = []
to_test = []

for item in listed_candidates:
    name, country, ticker, desc, sec_name, sec_code, cur, exch = item
    match = db_sym_map.get(ticker.upper())
    if not match:
        # Search by exact name
        for k, v in db_name_map.items():
            if name.lower() in k:
                match = v
                break
    
    if match:
        if match[3] is True:
            already_active.append((name, ticker, match[1], match[5]))
        else:
            already_parked.append((name, ticker, match[1], match[6]))
    else:
        to_test.append(item)

print(f"Total listés soumis      : {len(listed_candidates)}")
print(f"Déjà actifs dans screener : {len(already_active)}")
print(f"Déjà parkés               : {len(already_parked)}")
print(f"Nouveaux à évaluer        : {len(to_test)}")

print("\n--- Déjà actifs ---")
for a in already_active:
    print(f"  {a[0]:<20} ({a[1]}) -> code:{a[2]} z:{a[3]}")

print("\n--- Nouveaux à tester ---")
for t in to_test:
    print(f"  {t[0]:<22} ({t[2]:<10}) [{t[1]}] Secteur: {t[4]}")
