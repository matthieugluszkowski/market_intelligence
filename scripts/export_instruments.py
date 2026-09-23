"""Export CSV de l'univers d'instruments, avec sa classe d'actif.

Une ligne par instrument, la colonne `type` portant le code de la classe
(`equity`, `dividend_stock`, `etf`, `commodity`, ...) et `type_label` son
libelle francais issu de la table `asset_classes` - pas une chaine recodee ici,
sinon les deux divergeraient au premier ajout de classe.

Les colonnes de detail (`sous_type`, `ter`, `distribution`, ...) sont extraites
de `instruments.attributes`, dont le contenu depend de la classe : profil de
dividende pour les actions a dividende, categorie et frais pour les ETF, famille
pour les matieres premieres. Une cellule vide signifie « non applicable a cette
classe », pas « donnee manquante ».

Usage :
    python scripts/export_instruments.py
    python scripts/export_instruments.py --sortie data/univers.csv
    python scripts/export_instruments.py --inclure-inactifs
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from market_intelligence.db import fetch_all  # noqa: E402

# Le symbole yfinance (source 5) est le seul identifiant de marche utilisable
# tel quel dans une feuille de calcul ; l'ISIN reste la cle metier.
REQUETE = """
select
  i.internal_code,
  i.isin,
  i.name,
  i.asset_class,
  ac.label                       as type_label,
  coalesce(
    i.attributes->>'profil_dividende',
    i.attributes->>'categorie',
    i.attributes->>'famille'
  )                              as sous_type,
  i.exchange_code,
  i.currency,
  i.country_iso2,
  i.sector_code,
  s.label                        as secteur_label,
  i.is_active,
  (i.attributes->>'pea_eligible')::boolean       as pea_eligible,
  coalesce(i.policy_code, ac.default_policy_code) as politique_regression,
  sym.symbol                     as symbole_yfinance,
  i.attributes->>'emetteur'      as emetteur,
  (i.attributes->>'ter')::float  as ter,
  i.attributes->>'distribution'  as distribution,
  i.attributes->>'replication'   as replication,
  i.attributes->>'indice_reference' as indice_reference,
  i.attributes->>'unite'         as unite,
  coalesce(
    i.attributes->'verification'->>'first_bar',
    i.attributes->'verification'->>'premiere_barre'
  )                              as premiere_barre,
  coalesce(
    i.attributes->'verification'->>'last_bar',
    i.attributes->'verification'->>'derniere_barre'
  )                              as derniere_barre,
  (i.attributes->'verification'->>'history_years')::float as annees_historique
from instruments i
join asset_classes ac on ac.code = i.asset_class
left join sectors s on s.code = i.sector_code
left join instrument_symbols sym
  on sym.instrument_id = i.id and sym.source_id = 5
{filtre}
order by ac.code, i.name
"""

COLONNES = [
    "internal_code", "isin", "nom", "type", "type_label", "sous_type",
    "place", "devise", "pays", "secteur_code", "secteur_label", "actif",
    "pea_eligible", "politique_regression", "symbole_yfinance",
    "emetteur", "ter", "distribution", "replication", "indice_reference",
    "unite", "premiere_barre", "derniere_barre", "annees_historique",
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sortie", type=Path, default=Path("data/instruments.csv"),
        help="Fichier CSV a ecrire (defaut : data/instruments.csv)",
    )
    parser.add_argument(
        "--inclure-inactifs", action="store_true",
        help="Inclure les instruments radies (is_active = false)",
    )
    args = parser.parse_args()

    filtre = "" if args.inclure_inactifs else "where i.is_active"
    lignes = fetch_all(REQUETE.format(filtre=filtre))

    args.sortie.parent.mkdir(parents=True, exist_ok=True)
    # utf-8-sig : sans le BOM, Excel sous Windows lit le CSV en cp1252 et casse
    # les accents des libelles ("Matiere premiere" -> "MatiÃ¨re premiÃ¨re").
    with args.sortie.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(COLONNES)
        for ligne in lignes:
            writer.writerow(["" if v is None else v for v in ligne])

    print(f"{len(lignes)} instruments -> {args.sortie}")
    repartition = fetch_all(
        f"select ac.label, count(*) from instruments i "
        f"join asset_classes ac on ac.code = i.asset_class "
        f"{filtre} group by 1 order by 2 desc"
    )
    for label, n in repartition:
        print(f"  {n:>4}  {label}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
