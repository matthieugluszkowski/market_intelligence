"""Charge les matieres premieres au referentiel (lot L1, classe `commodity`).

Meme mecanisme que les actions, volontairement : meme collecteur yfinance, memes
barres hebdomadaires, meme regression log-lineaire, meme fiche instrument. Ce qui
distingue une matiere premiere ici tient en trois absences - ni ISIN, ni secteur,
ni fondamentaux - et en une classe d'actif.

Pourquoi `loglin_20y` et non `real_deflated`
--------------------------------------------
`asset_classes.default_policy_code` designe `real_deflated` pour cette classe :
fenetre 50 ans, minimum 30 ans, barres mensuelles, serie deflatee de l'inflation,
fenetre demarrant apres 1971 (doc 03 SS6, doc 07 SS4). Deux faits s'y opposent
aujourd'hui, et ils sont mesures, pas supposes :

- le moteur n'implemente pas ce modele : `compute_fits` applique la regression
  log-lineaire quelle que soit la politique, seul le modele `none` est distingue ;
- aucune source branchee ne remonte a 30 ans. Mesure le 2026-08-24 en
  hebdomadaire : or et cuivre 26,0 ans, Brent 19,1 ans, minerai de fer 15,8 ans.
  Sous `real_deflated`, les douze lignes prendraient le motif `short_history` et
  ne sortiraient jamais du screener.

La politique posee est donc `loglin_20y` - celle des actions - **explicitement**
dans `instruments.policy_code`, champ prevu pour cette derogation (principe P6).

**Consequence a connaitre : la tendance est nominale.** Sur l'or, une pente de
+8 %/an contient l'inflation de la periode et le marche haussier de l'apres-2000.
Le z-score repond « cher ou pas par rapport a la tendance des vingt dernieres
annees », il ne repond pas « cher en termes reels ». La lecture reste valide,
c'est sa portee qui est plus courte que celle du doc 03.

Unites : les cereales du CBOT cotent en **cents** par boisseau, pas en dollars.
yfinance le declare lui-meme (`USX`). La devise suit, sur le modele du `GBX` du
LSE deja au referentiel : sans elle, un ble a 711 s'afficherait « 711 USD » au
lieu de 7,11 dollars le boisseau. Le facteur d'echelle est sans effet sur la
regression - une constante multiplicative ne deplace que l'ordonnee a l'origine -
mais il rend le prix affiche faux, ce qui suffit.

Usage :
    python scripts/load_commodities.py --dry-run
    python scripts/load_commodities.py
    python scripts/backfill_prices.py --freq 1w --only CM:GOLD
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from market_intelligence.collectors.yfinance_prices import fetch_bars  # noqa: E402
from market_intelligence.config import get_settings  # noqa: E402
from market_intelligence.db import connect_direct  # noqa: E402

# Politique posee a la main, contre le defaut de la classe d'actif. Voir le
# docstring : c'est le point de methode de ce fichier, pas un detail.
POLITIQUE = "loglin_20y"

# Dix familles equilibrees - energie, metaux precieux, metaux industriels,
# agricole - puis les metaux que la demande d'infrastructure IA tire :
# le platine et le palladium partent dans les semi-conducteurs, les contacts et
# les capteurs. L'uranium, le lithium et le nickel manquent a l'appel faute de
# serie exploitable chez le collecteur - constate, pas choisi.
MATIERES = (
    {"code": "CM:BRENT", "nom": "Pétrole Brent", "symbole": "BZ=F",
     "devise": "USD", "unite": "USD par baril", "famille": "énergie"},
    {"code": "CM:NATGAS", "nom": "Gaz naturel", "symbole": "NG=F",
     "devise": "USD", "unite": "USD par MMBtu", "famille": "énergie"},
    {"code": "CM:GOLD", "nom": "Or", "symbole": "GC=F",
     "devise": "USD", "unite": "USD par once troy", "famille": "métal précieux"},
    {"code": "CM:SILVER", "nom": "Argent", "symbole": "SI=F",
     "devise": "USD", "unite": "USD par once troy", "famille": "métal précieux"},
    {"code": "CM:PLATINUM", "nom": "Platine", "symbole": "PL=F",
     "devise": "USD", "unite": "USD par once troy", "famille": "métal précieux"},
    {"code": "CM:PALLADIUM", "nom": "Palladium", "symbole": "PA=F",
     "devise": "USD", "unite": "USD par once troy", "famille": "métal précieux"},
    {"code": "CM:COPPER", "nom": "Cuivre", "symbole": "HG=F",
     "devise": "USD", "unite": "USD par livre", "famille": "métal industriel"},
    {"code": "CM:ALUMINIUM", "nom": "Aluminium", "symbole": "ALI=F",
     "devise": "USD", "unite": "USD par tonne", "famille": "métal industriel"},
    {"code": "CM:IRONORE", "nom": "Minerai de fer", "symbole": "TIO=F",
     "devise": "USD", "unite": "USD par tonne", "famille": "métal industriel"},
    {"code": "CM:WHEAT", "nom": "Blé", "symbole": "ZW=F",
     "devise": "USX", "unite": "cents US par boisseau", "famille": "agricole"},
    {"code": "CM:CORN", "nom": "Maïs", "symbole": "ZC=F",
     "devise": "USX", "unite": "cents US par boisseau", "famille": "agricole"},
    {"code": "CM:SOYBEAN", "nom": "Soja", "symbole": "ZS=F",
     "devise": "USX", "unite": "cents US par boisseau", "famille": "agricole"},
)

# Le cent americain manque au referentiel, comme le penny sterling y figure.
DEVISES = (
    ("USX", "Cent americain (cotation CBOT, 1/100 USD)"),
)

UPSERT_DEVISE = """
insert into currencies (code, label) values (%(code)s, %(label)s)
on conflict (code) do nothing;
"""

# Ni ISIN, ni secteur, ni pays : une matiere premiere n'en a pas, et une chaine
# vide en tiendrait lieu a tort - `isin` est unique, `sector_code` porte une
# cle etrangere. Le NULL est la seule valeur juste.
UPSERT_INSTRUMENT = """
insert into instruments
  (internal_code, asset_class, name, currency, policy_code, is_active, attributes)
values (%(internal_code)s, 'commodity', %(name)s, %(currency)s, %(policy_code)s,
        true, %(attributes)s)
on conflict (internal_code) do update set
  name = excluded.name,
  currency = excluded.currency,
  policy_code = excluded.policy_code,
  attributes = excluded.attributes,
  updated_at = now()
returning id;
"""

UPSERT_SYMBOL = """
insert into instrument_symbols (instrument_id, source_id, symbol, is_primary)
values (%(instrument_id)s, %(source_id)s, %(symbol)s, true)
on conflict (source_id, symbol, valid_from) do update set
  instrument_id = excluded.instrument_id,
  is_primary = excluded.is_primary;
"""

# Le minimum de la politique `loglin_20y`. En dessous, l'eligibilite posera
# `short_history` - ce n'est pas au chargeur d'ecarter la ligne, mais il doit
# le dire au chargement plutot que de le laisser decouvrir au screener.
MIN_ANNEES = 15


def _identite(symbole: str) -> tuple[str, str]:
    """Nom et devise declares par le provider. Metadonnee : la cotation prime."""
    import yfinance as yf

    try:
        info = yf.Ticker(symbole).get_info()
    except Exception:  # noqa: BLE001
        return "", ""
    return ((info.get("longName") or info.get("shortName") or ""),
            (info.get("currency") or "").upper())


def verifier(matiere: dict, rate_limit: float, retries: int) -> dict:
    """Telecharge la serie hebdomadaire et rend ce qu'elle vaut. Ne leve pas.

    Le garde-fou n'est pas celui d'une action. Sur une action, le mapping se
    controle par la raison sociale - c'est le cas Seb contre SEB banque
    suedoise. Ici le nom du provider est un nom de contrat (« Gold Apr 26 ») et
    le notre une traduction (« Or ») : les confronter ne dirait rien. Le nom est
    donc **enregistre pour l'oeil humain, pas oppose**.

    Ce qui est oppose, c'est la devise, et c'est le controle qui compte pour
    cette classe : les cereales du CBOT cotent en cents. Declarer USD la ou
    yfinance annonce USX afficherait un ble a 711 dollars le boisseau au lieu de
    7,11. La ligne est alors refusee, pas chargee avec un avertissement.
    """
    brut = fetch_bars(matiere["symbole"], freq="1w",
                      rate_limit_sec=rate_limit, max_retries=retries)
    if not brut.ok:
        return {"statut": "echec", "motif": brut.error or "aucune cotation"}

    frame = brut.frame
    premiere, derniere = frame.index[0].date(), frame.index[-1].date()
    annees = (derniere - premiere).days / 365.25
    nom_provider, devise_provider = _identite(matiere["symbole"])

    if devise_provider and devise_provider != matiere["devise"]:
        statut, motif = "devise_divergente", (
            f"{devise_provider} chez le provider, {matiere['devise']} declare")
    elif annees < MIN_ANNEES:
        statut, motif = "historique_court", f"{annees:.1f} ans < {MIN_ANNEES}"
    else:
        statut, motif = "retenu", ""

    return {
        "statut": statut,
        "motif": motif,
        "n_obs_weekly": len(frame),
        "history_years": round(annees, 1),
        "first_bar": premiere.isoformat(),
        "last_bar": derniere.isoformat(),
        "last_close": round(float(frame["Close"].iloc[-1]), 4),
        "reported_name": nom_provider,
        "reported_currency": devise_provider,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="verifie les series et n'ecrit rien")
    args = parser.parse_args()

    settings = get_settings()
    print(f"{len(MATIERES)} matieres premieres, politique {POLITIQUE}\n")
    print(f"{'code':<15} {'symbole':<8} {'periode':<25} {'obs':>5} {'ans':>5}  statut")

    verifications = {}
    for matiere in MATIERES:
        v = verifier(matiere, settings.yfinance_rate_limit_sec, settings.http_max_retries)
        verifications[matiere["code"]] = v
        periode = (f"{v['first_bar']} -> {v['last_bar']}"
                   if v["statut"] != "echec" else v["motif"][:25])
        print(f"{matiere['code']:<15} {matiere['symbole']:<8} {periode:<25} "
              f"{v.get('n_obs_weekly', 0):>5} {v.get('history_years', 0):>5}  "
              f"{v['statut']}{(' - ' + v['motif']) if v['motif'] and v['statut'] != 'echec' else ''}")

    # Une devise divergente est bloquante au meme titre qu'une absence de
    # cotation : elle ne rend pas la ligne imprecise, elle la rend fausse
    # d'un facteur cent.
    BLOQUANTS = ("echec", "devise_divergente")
    chargeables = [m for m in MATIERES
                   if verifications[m["code"]]["statut"] not in BLOQUANTS]
    ecartees = [m for m in MATIERES
                if verifications[m["code"]]["statut"] in BLOQUANTS]
    print()
    print(f"{len(chargeables)} chargeables, {len(ecartees)} ecartee(s)")
    for m in ecartees:
        v = verifications[m["code"]]
        print(f"  ecarte {m['code']:<15} {v['statut']} : {v['motif']}")

    if args.dry_run:
        return 0

    with connect_direct() as conn:
        with conn.cursor() as cur:
            for code, label in DEVISES:
                cur.execute(UPSERT_DEVISE, {"code": code, "label": label})

            cur.execute("select id from data_sources where code = 'yfinance'")
            ligne = cur.fetchone()
            if ligne is None:
                print("Source 'yfinance' absente de data_sources : rejouer les seeds.")
                return 1
            source_id = ligne[0]

            for matiere in chargeables:
                verification = verifications[matiere["code"]]
                attributs = {
                    "unite": matiere["unite"],
                    "famille": matiere["famille"],
                    "politique_forcee": {
                        "code": POLITIQUE,
                        "motif": "real_deflated non implemente et historique < 30 ans ; "
                                 "tendance nominale, portee reduite (voir "
                                 "scripts/load_commodities.py)",
                    },
                    "verification": {"source": "yfinance", **verification},
                }
                cur.execute(UPSERT_INSTRUMENT, {
                    "internal_code": matiere["code"],
                    "name": matiere["nom"],
                    "currency": matiere["devise"],
                    "policy_code": POLITIQUE,
                    "attributes": json.dumps(attributs, ensure_ascii=False),
                })
                instrument_id = cur.fetchone()[0]
                cur.execute(UPSERT_SYMBOL, {
                    "instrument_id": instrument_id,
                    "source_id": source_id,
                    "symbol": matiere["symbole"],
                })
                print(f"  charge {matiere['code']:<15} id={instrument_id}")
        conn.commit()

    print(f"\n{len(chargeables)} instruments ecrits. Suite :\n"
          f"  python scripts/backfill_prices.py --freq 1w --only CM:GOLD   (par ligne)\n"
          f"  python scripts/compute_fits.py                               (univers entier)")
    return 1 if ecartees else 0


if __name__ == "__main__":
    raise SystemExit(main())
