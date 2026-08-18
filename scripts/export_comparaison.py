"""Export d'un titre pour confrontation a une source externe (critere L5).

Le critere d'acceptation du lot L5 est le plus utile du projet :

    « le graphe d'un titre est superposable a celui de Hiboo pour le meme titre,
      aux conventions d'ajustement pres. »

Je ne peux pas l'executer moi-meme : Hiboo est un service sur abonnement, et
declarer une superposition sans l'avoir constatee serait exactement le genre de
validation fictive que ce projet cherche a eviter. Ce script produit donc la
piece a conviction - la serie exacte, avec sa tendance et ses bandes - pour que
la comparaison soit faite et tranchee.

Choisir le bon titre pour comparer
-----------------------------------
**Prendre un titre sans split.** 26 des 57 n'en ont aucun : leur serie ajustee
est identique a la serie nominale, et le graphe doit se superposer directement.
BMW, Sanofi, Kering, Heineken, Arkema sont de bons candidats.

Sur un titre avec splits, l'ecart attendu est un **facteur multiplicatif
constant** : Yahoo sert un cours retro-ajuste des splits, Hiboo affiche
vraisemblablement le nominal. L'Oreal ressort divise par 20, EssilorLuxottica par
20,44. Un ecart constant en niveau valide la forme ; un ecart qui derive dans le
temps signale un vrai probleme.

Ce qui doit se superposer, et ce qui peut differer
---------------------------------------------------
Doit coincider : la **forme** de la courbe, la **pente** de la tendance, et
surtout le **z-score courant** - c'est lui qui declenche les decisions.

Peut differer legitimement : le niveau absolu (convention d'ajustement), la
largeur des bandes si Hiboo utilise une fenetre differente de 20 ans, et les
extremites si leur historique commence ailleurs.

Usage :
    python scripts/export_comparaison.py EQ:DE:BMW
    python scripts/export_comparaison.py EQ:FR:SANOFI --sortie /tmp/sanofi.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from dashboard import charts  # noqa: E402
from market_intelligence.db import connect  # noqa: E402

FIT = """
select f.*, i.name, i.isin, i.currency
  from regression_fits f join instruments i on i.id = f.instrument_id
 where i.internal_code = %(code)s
 order by f.as_of_date desc limit 1;
"""

BARRES = """
select b.ts, b.close * coalesce(a.factor_price, 1.0) as close, b.close as close_brut
  from bars b
  join instruments i on i.id = b.instrument_id
  left join adjustment_factors a
    on a.instrument_id = b.instrument_id and a.ts = b.ts
 where i.internal_code = %(code)s and b.freq = '1w'
 order by b.ts;
"""

SPLITS = """
select coalesce(exp(sum(ln(ca.ratio))), 1.0)
  from corporate_actions ca join instruments i on i.id = ca.instrument_id
 where i.internal_code = %(code)s
   and ca.action_type in ('split', 'reverse_split') and ca.ratio > 0;
"""


def _frame(cur, sql: str, code: str) -> pd.DataFrame:
    cur.execute(sql, {"code": code})
    return pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("code", help="internal_code, par exemple EQ:DE:BMW")
    parser.add_argument("--sortie", default="", help="chemin du CSV")
    args = parser.parse_args()

    with connect() as conn, conn.cursor() as cur:
        fits = _frame(cur, FIT, args.code)
        if fits.empty:
            print(f"Aucune regression pour {args.code}.")
            return 1
        fit = fits.iloc[0]
        barres = _frame(cur, BARRES, args.code)
        cur.execute(SPLITS, {"code": args.code})
        facteur_splits = float(cur.fetchone()[0])

    serie = charts.serie_de_regression(barres, fit)
    if serie.empty:
        print("Aucune barre dans la fenetre de regression.")
        return 1

    sortie = Path(args.sortie) if args.sortie else ROOT / "data" / (
        f"comparaison_{args.code.replace(':', '_')}.csv")
    sortie.parent.mkdir(parents=True, exist_ok=True)
    charts.jumeau_tabulaire(serie).to_csv(sortie, index=False, encoding="utf-8")

    print(f"{fit['name']}  ({fit['isin']}, {fit['currency']})")
    print(f"  fenetre        {fit['window_start']} -> {fit['window_end']}  "
          f"({fit['n_obs']} barres hebdomadaires)")
    print(f"  pente annuelle {fit['slope_annual']:+.2%}")
    print(f"  sigma residuel {fit['sigma_resid']:.4f}")
    print(f"  dernier cours  {fit['last_close']:.2f} {fit['currency']}")
    print(f"  tendance       {serie['tendance'].iloc[-1]:.2f} {fit['currency']}")
    print(f"  z-score        {fit['z_score']:+.3f}   <- la valeur a confronter en priorite")
    print(f"  bande -2 sigma {serie['bande_basse_2'].iloc[-1]:.2f}")
    print(f"  bande +2 sigma {serie['bande_haute_2'].iloc[-1]:.2f}")

    print()
    if abs(facteur_splits - 1.0) < 1e-9:
        print("  Aucun split sur ce titre : la serie exportee est le cours nominal.")
        print("  Le graphe doit se superposer DIRECTEMENT, sans mise a l'echelle.")
    else:
        print(f"  Facteur cumule de splits : x{facteur_splits:.4f}")
        print(f"  Yahoo sert un cours retro-ajuste des splits. Si la reference affiche")
        print(f"  le nominal, elle sera environ {facteur_splits:.2f} fois plus haute, "
              f"d'un facteur CONSTANT.")
        print(f"  Un ecart constant valide la forme ; un ecart qui derive dans le temps")
        print(f"  signale un vrai probleme.")

    print(f"\n  Serie complete : {sortie}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
