"""Ecriture idempotente des operations sur titre et du nombre d'actions.

Meme parti que pour les barres (`loaders/bars.py`) : table de transit alimentee
en COPY, puis un `insert ... select`. Ligne a ligne, les 600 a 800 points de
nombre d'actions par titre coutent autant d'allers-retours vers Supabase - de
l'ordre d'une heure et demie sur l'univers, mesure avant correction.
"""

from __future__ import annotations

from dataclasses import dataclass

STAGING_ACTIONS = """
create temp table if not exists staging_actions (
  instrument_id bigint, action_type text, ex_date date,
  ratio double precision, amount double precision,
  currency char(3), source_id smallint
) on commit drop;
"""

STAGING_SHARES = """
create temp table if not exists staging_shares (
  instrument_id bigint, as_of date, shares bigint, source_id smallint
) on commit drop;
"""

# `ca_unique` est un index expressionnel sur COALESCE(ratio,0) et COALESCE(amount,0)
# (migration 003). Un ON CONFLICT doit en repeter l'expression a l'identique.
UPSERT_ACTIONS = """
insert into corporate_actions
  (instrument_id, action_type, ex_date, ratio, amount, currency, source_id)
select instrument_id, action_type, ex_date, ratio, amount, currency, source_id
  from staging_actions
on conflict (instrument_id, action_type, ex_date,
             coalesce(ratio, 0), coalesce(amount, 0))
do update set currency = excluded.currency, source_id = excluded.source_id;
"""

UPSERT_SHARES = """
insert into shares_outstanding (instrument_id, as_of, shares, source_id)
select instrument_id, as_of, shares, source_id from staging_shares
on conflict (instrument_id, as_of) do update set
  shares = excluded.shares, source_id = excluded.source_id
where shares_outstanding.shares is distinct from excluded.shares;
"""

COLONNES_ACTIONS = ("instrument_id", "action_type", "ex_date", "ratio",
                    "amount", "currency", "source_id")
COLONNES_SHARES = ("instrument_id", "as_of", "shares", "source_id")


@dataclass
class ActionsLoadResult:
    actions_nouvelles: int = 0
    actions_totales: int = 0
    shares_nouvelles: int = 0
    shares_totales: int = 0


def _compte(cur, table: str, instrument_id: int) -> int:
    cur.execute(f"select count(*) from {table} where instrument_id = %s",  # noqa: S608
                (instrument_id,))
    return cur.fetchone()[0]


def _charge(cur, table_transit: str, ddl: str, upsert: str,
            colonnes: tuple, lignes: list[dict]) -> None:
    if not lignes:
        return
    cur.execute(ddl)
    cur.execute(f"truncate {table_transit}")  # noqa: S608 - nom en dur
    with cur.copy(f"copy {table_transit} ({', '.join(colonnes)}) from stdin") as copy:
        for ligne in lignes:
            copy.write_row(tuple(ligne[c] for c in colonnes))
    cur.execute(upsert)


def upsert_actions(cur, normalized, instrument_id: int) -> ActionsLoadResult:
    result = ActionsLoadResult()
    avant_actions = _compte(cur, "corporate_actions", instrument_id)
    avant_shares = _compte(cur, "shares_outstanding", instrument_id)

    _charge(cur, "staging_actions", STAGING_ACTIONS, UPSERT_ACTIONS,
            COLONNES_ACTIONS, normalized.actions)
    _charge(cur, "staging_shares", STAGING_SHARES, UPSERT_SHARES,
            COLONNES_SHARES, normalized.shares)

    result.actions_totales = _compte(cur, "corporate_actions", instrument_id)
    result.shares_totales = _compte(cur, "shares_outstanding", instrument_id)
    result.actions_nouvelles = result.actions_totales - avant_actions
    result.shares_nouvelles = result.shares_totales - avant_shares
    return result
