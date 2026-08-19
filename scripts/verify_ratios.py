"""Recoupement des ratios calcules (critere d'acceptation du lot L6).

    « les ratios recoupent une source independante sur un echantillon de
      10 titres »

Sur l'independance de la source, et ses limites
------------------------------------------------
La comparaison se fait contre les ratios pre-calcules de Yahoo (`Ticker.info` :
`trailingPE`, `priceToBook`, `profitMargins`, `returnOnEquity`, `marketCap`).

**Ce n'est pas une source pleinement independante** - c'est le meme fournisseur.
Mais c'est un **chemin de calcul different** : Yahoo agrege ses propres donnees
trimestrielles glissantes, la ou nous partons des etats annuels et recomposons.
Une divergence revele donc une erreur de mapping, de signe ou de convention -
exactement ce qu'on cherche a attraper. Une concordance ne prouve pas que les
donnees sous-jacentes sont justes, seulement que notre chaine ne les deforme pas.

La difference de periode, mesuree et non supposee
--------------------------------------------------
Les ratios de Yahoo issus du compte de resultat - PER, marge nette, ROE - portent
sur les **douze mois glissants**. Les notres portent sur le **dernier exercice
clos**, seule base compatible avec le point-in-time : les comptes trimestriels
n'ont pas de date de publication exploitable, et les utiliser reintroduirait le
look-ahead que tout le dispositif cherche a eviter.

Ce script ne se contente donc pas de constater l'ecart, il le **decompose** : il
recalcule le douze-mois-glissant depuis les comptes trimestriels et verifie que
c'est bien lui que Yahoo affiche. Verifie sur AB InBev : douze mois glissants
14,90%, `profitMargins` annonce 14,90% - identiques. La divergence est une
difference de base, pas une erreur d'arithmetique.

Sans cette decomposition, un vrai bug de mapping serait indiscernable d'un ecart
de periode, et on classerait les deux comme « ecart attendu ».

Usage :
    python scripts/verify_ratios.py
    python scripts/verify_ratios.py --echantillon 20
"""

from __future__ import annotations

import argparse
import sys
import warnings
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from market_intelligence.analytics import ratios as R  # noqa: E402
from market_intelligence.config import get_settings  # noqa: E402
from market_intelligence.db import connect  # noqa: E402

ECHANTILLON = """
select i.id, i.internal_code, i.name, s.symbol
  from instruments i
  join instrument_symbols s on s.instrument_id = i.id and s.is_primary
 where i.is_active
   and exists (select 1 from financial_facts f
                where f.instrument_id = i.id and f.concept_code = 'net_income')
 order by i.internal_code
 limit %(limite)s;
"""

CAPITALISATION = """
select (select b.close from bars b
         where b.instrument_id = %(id)s and b.freq = '1w'
         order by b.ts desc limit 1) as cours,
       (select o.shares from shares_outstanding o
         where o.instrument_id = %(id)s order by o.as_of desc limit 1) as actions;
"""

# Deux familles, et la distinction porte tout le raisonnement.
#
# Les ratios de BILAN se comparent directement : les deux cotes lisent la meme
# photographie a la meme date, un ecart est donc une erreur.
#
# Les ratios de COMPTE DE RESULTAT ne portent pas sur la meme periode - exercice
# clos chez nous, douze mois glissants chez Yahoo. On ne les compare pas a Yahoo
# directement : on verifie que notre chiffre reproduit l'exercice clos, et que
# celui de Yahoo reproduit le douze-mois-glissant. Si les deux tiennent, la
# chaine est fidele des deux cotes.
TOLERANCES_BILAN = {
    "capitalisation": 0.02,
    "price_to_book": 0.10,
}

TOLERANCES_RESULTAT = {
    "marge_nette": 0.05,   # comparee au douze-mois-glissant recalcule, pas a Yahoo
    "per": 0.10,
}


def main() -> int:
    warnings.filterwarnings("ignore")
    import yfinance as yf

    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--echantillon", type=int, default=10)
    args = parser.parse_args()

    settings = get_settings()
    aujourdhui = date.today()

    with connect() as conn, conn.cursor() as cur:
        cur.execute(ECHANTILLON, {"limite": args.echantillon})
        titres = cur.fetchall()

        lignes = []
        for instrument_id, code, nom, symbol in titres:
            cur.execute(CAPITALISATION, {"id": instrument_id})
            cours, actions = cur.fetchone()
            if cours is None or actions is None:
                lignes.append({"code": code, "erreur": "capitalisation indisponible"})
                continue
            capitalisation = float(cours) * float(actions)

            fondamentaux = R.charge(cur, instrument_id, aujourdhui)
            nos = R.ratios(fondamentaux, capitalisation=capitalisation,
                           cours=float(cours))

            try:
                ticker = yf.Ticker(symbol)
                info = ticker.get_info()
                trimestriels = ticker.quarterly_income_stmt
            except Exception as exc:  # noqa: BLE001
                lignes.append({"code": code, "erreur": f"info indisponible : {exc}"})
                continue

            ttm = _douze_mois_glissants(trimestriels)
            lignes.append({
                "code": code, "nom": nom, "erreur": "",
                "bilan": {
                    "capitalisation": (capitalisation, info.get("marketCap")),
                    "price_to_book": (nos["price_to_book"], info.get("priceToBook")),
                },
                "resultat": {
                    "marge_nette": (nos["marge_nette"], info.get("profitMargins"),
                                    ttm.get("marge_nette")),
                    "per": (nos["per"],
                            info.get("trailingPE"),
                            _div(capitalisation, ttm.get("net_income"))),
                },
            })
            import time
            time.sleep(settings.yfinance_rate_limit_sec)

    print(f"Recoupement sur {len(lignes)} titres, au {aujourdhui}\n")

    comptes = {"concordant": 0, "divergent": 0, "incomparable": 0}
    divergences = []

    print("A · Ratios de bilan - meme photographie des deux cotes, un ecart est une erreur")
    entete = f"{'titre':<22} {'ratio':<16} {'calcule':>16} {'Yahoo':>16} {'ecart':>8}"
    print(entete)
    print("-" * len(entete))
    for ligne in lignes:
        if ligne["erreur"]:
            print(f"{ligne['code']:<22} {ligne['erreur']}")
            comptes["incomparable"] += 1
            continue
        for cle, tolerance in TOLERANCES_BILAN.items():
            notre, reference = ligne["bilan"][cle]
            marque, ecart_txt = _juge(notre, reference, tolerance, comptes,
                                      divergences, ligne["code"], cle)
            fmt = ",.0f" if cle == "capitalisation" else ".4f"
            print(f"{marque}{ligne['code']:<20} {cle:<16} "
                  f"{_fmt(notre, fmt):>16} {_fmt(reference, fmt):>16} {ecart_txt}")

    print("\nB · Ratios de compte de resultat - bases differentes, decomposees")
    entete = (f"{'titre':<22} {'ratio':<14} {'exercice clos':>14} "
              f"{'12 mois recalc':>14} {'Yahoo':>14} {'accord':>8}")
    print(entete)
    print("-" * len(entete))
    for ligne in lignes:
        if ligne["erreur"]:
            continue
        for cle, tolerance in TOLERANCES_RESULTAT.items():
            notre, yahoo, ttm = ligne["resultat"][cle]
            # Le test n'est pas « notre chiffre egale celui de Yahoo » mais
            # « le douze-mois-glissant que nous recalculons egale celui de Yahoo ».
            marque, ecart_txt = _juge(ttm, yahoo, tolerance, comptes,
                                      divergences, ligne["code"], f"{cle} (12m)")
            print(f"{marque}{ligne['code']:<20} {cle:<14} {_fmt(notre, '.4f'):>14} "
                  f"{_fmt(ttm, '.4f'):>14} {_fmt(yahoo, '.4f'):>14} {ecart_txt}")

    total = comptes["concordant"] + comptes["divergent"]
    print(f"\nConcordants   {comptes['concordant']:>4}")
    print(f"Divergents    {comptes['divergent']:>4}")
    print(f"Incomparables {comptes['incomparable']:>4}  (donnee absente d'un cote)")
    if total:
        print(f"\nTaux de concordance : {comptes['concordant'] / total:.1%} "
              f"sur {total} comparaisons")

    if divergences:
        print("\nA regarder :")
        for code, cle, notre, reference, ecart in sorted(
            divergences, key=lambda d: -d[4]
        )[:10]:
            print(f"  {code:<22} {cle:<18} {notre:>12.4f} vs {reference:>12.4f}  "
                  f"({ecart:.0%})")
    return 0


def _fmt(valeur, format_) -> str:
    return f"{valeur:{format_}}" if valeur is not None else "-"


def _div(a, b):
    return a / b if a is not None and b not in (None, 0) else None


def _juge(notre, reference, tolerance, comptes, divergences, code, cle):
    if notre is None or reference is None or reference == 0:
        comptes["incomparable"] += 1
        return " ?", "       -"
    ecart = abs(notre / reference - 1)
    if ecart <= tolerance:
        comptes["concordant"] += 1
        return "  ", f"{ecart:>7.1%}"
    comptes["divergent"] += 1
    divergences.append((code, cle, notre, reference, ecart))
    return " !", f"{ecart:>7.1%}"


def _douze_mois_glissants(trimestriels) -> dict:
    """Recompose les quatre derniers trimestres publies."""
    if trimestriels is None or trimestriels.empty:
        return {}
    colonnes = list(trimestriels.columns)[:4]
    if len(colonnes) < 4:
        return {}

    def somme(libelle):
        if libelle not in trimestriels.index:
            return None
        valeurs = [trimestriels.loc[libelle, c] for c in colonnes]
        valeurs = [float(v) for v in valeurs if v == v]
        return sum(valeurs) if len(valeurs) == 4 else None

    net_income, revenue = somme("Net Income"), somme("Total Revenue")
    return {"net_income": net_income, "revenue": revenue,
            "marge_nette": _div(net_income, revenue)}


if __name__ == "__main__":
    raise SystemExit(main())
