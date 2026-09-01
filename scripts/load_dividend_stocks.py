"""Affecte et configure le scope des actions a dividende majeures eligibles au PEA (classe `dividend_stock`).

Pour chaque champion du dividende selectionne (France et Europe) :
- Met a jour l'instrument sous la classe d'actifs `dividend_stock` ('Action à dividende') ;
- Met a jour l'ISIN officiel et enrichit les attributs avec les métadonnées de dividende et d'éligibilité PEA ;
- Conserve l'historique complet existant (cours, dividendes, bilans).

Eligibilite PEA - critere de scope, pas un attribut a part : un titre qui n'est
pas eligible n'entre pas dans cette liste. Les foncieres SIIC (Gecina, Covivio,
Altarea SCA...) beneficient d'une exoneration d'impot sur les societes sur
leurs revenus locatifs et plus-values immobilieres ; cumuler cette exoneration
avec celle du PEA est interdit depuis la loi de finances pour 2012 (art. 8, loi
n°2011-1977 du 28/12/2011, applicable au 21/10/2011). Ce meme regime exclut les
foncieres cotees exonerees equivalentes des autres pays UE (FBI aux Pays-Bas,
SICAFI/GVV en Belgique, UK-REIT, G-REIT en Allemagne, SIIQ en Italie, SOCIMI en
Espagne) : aucune de ces categories ne doit rejoindre `DIVIDEND_STOCKS`, quel
que soit son rendement.

Usage :
    python scripts/load_dividend_stocks.py --dry-run
    python scripts/load_dividend_stocks.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from market_intelligence.db import connect_direct  # noqa: E402

DIVIDEND_STOCKS = (
    {"code": "EQ:FR:TTE", "isin": "FR0000120271", "nom": "TotalEnergies SE", "symbole": "TTE.PA", "profil": "Rendement élevé & Rachat d'actions"},
    {"code": "EQ:FR:SANOFI", "isin": "FR0000120578", "nom": "Sanofi S.A.", "symbole": "SAN.PA", "profil": "Aristocrate du dividende (croissance régulière)"},
    {"code": "EQ:FR:AIRLIQUIDE", "isin": "FR0000120073", "nom": "Air Liquide S.A.", "symbole": "AI.PA", "profil": "Aristocrate du dividende & Actions gratuites"},
    {"code": "EQ:FR:AXA", "isin": "FR0000120628", "nom": "AXA SA", "symbole": "CS.PA", "profil": "Rendement élevé & Distribution solide"},
    {"code": "EQ:FR:BNP", "isin": "FR0000131104", "nom": "BNP Paribas S.A.", "symbole": "BNP.PA", "profil": "Rendement bancaire élevé"},
    {"code": "EQ:FR:VINCI", "isin": "FR0000125486", "nom": "Vinci S.A.", "symbole": "DG.PA", "profil": "Rente autoroutière & Dividende croissant"},
    {"code": "EQ:FR:SCHNEIDER", "isin": "FR0000121972", "nom": "Schneider Electric SE", "symbole": "SU.PA", "profil": "Croissance du dividende & Électrification"},
    {"code": "EQ:FR:DANONE", "isin": "FR0000120644", "nom": "Danone S.A.", "symbole": "BN.PA", "profil": "Défensif grande consommation"},
    {"code": "EQ:FR:OREAL", "isin": "FR0000120321", "nom": "L'Oréal S.A.", "symbole": "OR.PA", "profil": "Aristocrate du dividende & Leader mondial"},
    {"code": "EQ:FR:BOUYGUES", "isin": "FR0000120503", "nom": "Bouygues SA", "symbole": "EN.PA", "profil": "Rendement élevé & Conglomérat résilient"},
    {"code": "EQ:FR:ORANGE", "isin": "FR0000133308", "nom": "Orange S.A.", "symbole": "ORA.PA", "profil": "Rendement télécom élevé"},
    {"code": "EQ:FR:ENGIE", "isin": "FR0010208488", "nom": "Engie SA", "symbole": "ENGI.PA", "profil": "Rendement utility & Transition énergétique"},
    {"code": "EQ:FR:EIFFAGE", "isin": "FR0000130452", "nom": "Eiffage SA", "symbole": "FGR.PA", "profil": "Concessions autoroutières & BTP"},
    {"code": "EQ:FR:RUBIS", "isin": "FR0013269123", "nom": "Rubis SCA", "symbole": "RUI.PA", "profil": "Distribution d'énergie & Rendement très élevé"},
    {"code": "EQ:DE:MERCEDES", "isin": "DE0007100000", "nom": "Mercedes-Benz Group AG", "symbole": "MBG.DE", "profil": "Auto premium & Dividende massif"},
    {"code": "EQ:DE:BMW", "isin": "DE0005190003", "nom": "Bayerische Motoren Werke AG", "symbole": "BMW.DE", "profil": "Auto premium & Bilan ultra-solide"},
    {"code": "EQ:DE:ALLIANZ", "isin": "DE0008404005", "nom": "Allianz SE", "symbole": "ALV.DE", "profil": "Assureur leader européen & Dividende croissant"},
    {"code": "EQ:DE:MUNICHRE", "isin": "DE0008430026", "nom": "Münchener Rück AG (Munich Re)", "symbole": "MUV2.DE", "profil": "Leader mondial réassurance & Dividende jamais baissé"},
    {"code": "EQ:DE:FREENET", "isin": "DE000A0Z2ZZ5", "nom": "freenet AG", "symbole": "FNTN.DE", "profil": "Télécom allemand & Rendement récurrent"},
    {"code": "EQ:ES:IBERDROLA", "isin": "ES0144580Y14", "nom": "Iberdrola, S.A.", "symbole": "IBE.MC", "profil": "Leader mondial éolien/réseaux & Dividende en hausse"},
    {"code": "EQ:IT:ENEL", "isin": "IT0003128367", "nom": "Enel S.p.A.", "symbole": "ENEL.MI", "profil": "Utility intégrée italienne & Haut dividende"},
)

UPDATE_INSTRUMENT = """
update instruments set
  asset_class = 'dividend_stock',
  isin = coalesce(isin, %(isin)s),
  attributes = coalesce(attributes, '{}'::jsonb) || %(attr)s::jsonb,
  updated_at = now()
where internal_code = %(code)s or isin = %(isin)s
returning id, internal_code, name;
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", help="vérifie la liste et n'écrit rien"
    )
    args = parser.parse_args()

    print(f"{len(DIVIDEND_STOCKS)} actions à dividende majeures éligibles PEA\n")
    print(f"{'code':<18} {'isin':<14} {'symbole':<9} {'nom':<30}  profil")
    for s in DIVIDEND_STOCKS:
        print(f"{s['code']:<18} {s['isin']:<14} {s['symbole']:<9} {s['nom']:<30}  {s['profil']}")

    if args.dry_run:
        return 0

    with connect_direct() as conn:
        with conn.cursor() as cur:
            modifies = 0
            for s in DIVIDEND_STOCKS:
                attr = {
                    "pea_eligible": True,
                    "profil_dividende": s["profil"],
                    "scope_dividende": "champion_pea_credit_mutuel",
                }
                cur.execute(
                    UPDATE_INSTRUMENT,
                    {
                        "code": s["code"],
                        "isin": s["isin"],
                        "attr": json.dumps(attr, ensure_ascii=False),
                    },
                )
                row = cur.fetchone()
                if row:
                    print(f"  configuré {row[1]:<20} ({row[2]}) -> asset_class='dividend_stock'")
                    modifies += 1
                else:
                    print(f"  ATTENTION : {s['code']} / {s['isin']} non trouvé en base")
        conn.commit()

    print(f"\n{modifies}/{len(DIVIDEND_STOCKS)} actions configurées en 'dividend_stock'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
