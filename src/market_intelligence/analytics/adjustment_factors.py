"""Calcul des facteurs d'ajustement, reconstructibles depuis `corporate_actions`.

Deux facteurs, et la difference entre eux n'est pas cosmetique.

`factor_price` - splits
-----------------------
Vaut **1.0 partout** avec la source yfinance, et ce n'est pas un oubli.

Le cours servi par Yahoo est deja retro-ajuste des splits (voir
`collectors/yfinance_prices.py`). Appliquer en plus les ratios de
`corporate_actions` diviserait une seconde fois la serie : Air Liquide, qui
distribue une action gratuite pour dix tous les deux ans, se retrouverait avec
un historique divise par 1.1 a chaque operation, deux fois. C'est le genre
d'erreur qui ne se voit pas - la courbe reste lisse, la pente est simplement
fausse.

Le champ est donc renseigne a 1.0, explicitement, avec la raison. Le jour ou une
source servant le cours nominal est branchee, le calcul se fait au meme endroit
et `method_version` s'incremente.

`factor_total` - dividendes reinvestis
--------------------------------------
Celui-la, il faut le calculer : les dividendes ne sont pas incorpores dans
`Close`.

Convention retenue, celle de Yahoo pour son `Adj Close` :

    factor_total(t) = produit sur les dividendes d'ex-date > t de (1 - D / C_veille)

d'ou une serie en rendement total obtenue par `close(t) * factor_total(t)`. Le
facteur vaut 1.0 a la date la plus recente et decroit en remontant le temps.

Le calcul est verifiable : applique au `Close` de Yahoo, il doit redonner son
`Adj Close`. C'est l'objet d'un test dedie - sans lui, une erreur de convention
sur cette formule passerait inapercue et decalerait toutes les performances.
"""

from __future__ import annotations

from dataclasses import dataclass

DIVIDENDES = """
select ca.ex_date, ca.amount
  from corporate_actions ca
 where ca.instrument_id = %(instrument_id)s
   and ca.action_type = 'cash_dividend'
   and ca.amount is not null
 order by ca.ex_date;
"""

BARRES = """
select ts, close from bars
 where instrument_id = %(instrument_id)s and freq = %(freq)s
 order by ts;
"""

# Reference pour lire le cours de veille de detachement : le quotidien la ou il
# existe - trois ans, strategie deux temperatures du doc 00 SS5 - et
# l'hebdomadaire au-dela. `distinct on` garde une seule ligne par date, en
# privilegiant '1d' par l'ordre de tri.
REFERENCE = """
select distinct on (ts) ts, close
  from bars
 where instrument_id = %(instrument_id)s and freq in ('1d', '1w')
 order by ts, freq;
"""

STAGING = """
create temp table if not exists staging_factors (
  instrument_id bigint, ts date,
  factor_price double precision, factor_total double precision,
  method_version smallint
) on commit drop;
"""

# Comme partout ailleurs : COPY puis un seul insert. Un titre porte de l'ordre de
# 1 400 facteurs, l'univers en porte 80 000.
UPSERT = """
insert into adjustment_factors
  (instrument_id, ts, factor_price, factor_total, method_version)
select instrument_id, ts, factor_price, factor_total, method_version
  from staging_factors
on conflict (instrument_id, ts) do update set
  factor_price = excluded.factor_price,
  factor_total = excluded.factor_total,
  method_version = excluded.method_version,
  computed_at = now()
where adjustment_factors.factor_total is distinct from excluded.factor_total
   or adjustment_factors.factor_price is distinct from excluded.factor_price;
"""

# Les splits sont deja incorpores dans le cours servi par yfinance.
FACTOR_PRICE_YFINANCE = 1.0


@dataclass
class FactorsResult:
    n_barres: int = 0
    n_dividendes: int = 0
    facteur_le_plus_ancien: float = 1.0


def compute_factors(
    barres: list[tuple],
    dividendes: list[tuple],
    reference: list[tuple] | None = None,
) -> dict:
    """Calcule factor_total pour chaque date de barre. Fonction pure, testable.

    Args:
        barres: (ts, close) de la frequence cible, triees par date croissante.
        dividendes: (ex_date, amount) triees par date croissante.
        reference: (ts, close) servant a lire le cours de veille de detachement.
            On y passe le quotidien la ou il existe : sur une barre hebdomadaire,
            « la veille » est en realite la cloture de la semaine precedente, et
            si le cours a bouge de 4% dans l'intervalle, le ratio l'est d'autant.
            A defaut, les barres cibles font office de reference.

    Returns:
        {ts: factor_total}
    """
    if not barres:
        return {}

    dates = [b[0] for b in barres]
    reference = reference or barres
    dates_ref = [r[0] for r in reference]
    closes = {r[0]: r[1] for r in reference}

    ratios: list[tuple] = []
    for ex_date, amount in dividendes:
        precedente = None
        for ts in dates_ref:
            if ts < ex_date:
                precedente = ts
            else:
                break
        if precedente is None:
            continue                       # dividende anterieur a l'historique
        close_veille = closes[precedente]
        if close_veille <= 0 or amount >= close_veille:
            continue                       # incoherent : on n'applique pas
        ratios.append((ex_date, 1.0 - amount / close_veille))

    # Remontee du temps : le facteur d'une date est le produit des ratios de tous
    # les dividendes qui la suivent. Vaut donc 1.0 sur la barre la plus recente.
    facteurs: dict = {}
    cumul = 1.0
    index_ratio = len(ratios) - 1
    for ts in reversed(dates):
        while index_ratio >= 0 and ratios[index_ratio][0] > ts:
            cumul *= ratios[index_ratio][1]
            index_ratio -= 1
        facteurs[ts] = cumul
    return facteurs


def run_for_instrument(cur, instrument_id: int, freq: str, method_version: int) -> FactorsResult:
    cur.execute(DIVIDENDES, {"instrument_id": instrument_id})
    dividendes = cur.fetchall()
    cur.execute(BARRES, {"instrument_id": instrument_id, "freq": freq})
    barres = cur.fetchall()
    cur.execute(REFERENCE, {"instrument_id": instrument_id})
    reference = cur.fetchall()

    facteurs = compute_factors(barres, dividendes, reference)
    if facteurs:
        cur.execute(STAGING)
        cur.execute("truncate staging_factors")
        with cur.copy(
            "copy staging_factors (instrument_id, ts, factor_price, factor_total, "
            "method_version) from stdin"
        ) as copy:
            for ts, factor_total in facteurs.items():
                copy.write_row((instrument_id, ts, FACTOR_PRICE_YFINANCE,
                                factor_total, method_version))
        cur.execute(UPSERT)

    return FactorsResult(
        n_barres=len(barres),
        n_dividendes=len(dividendes),
        facteur_le_plus_ancien=facteurs[barres[0][0]] if barres else 1.0,
    )
