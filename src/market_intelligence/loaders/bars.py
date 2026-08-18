"""Ecriture idempotente des barres, et detection des revisions retroactives.

Idempotence (doc 02 SS4.2) : `insert ... on conflict do update`, jamais d'insert
nu. Un job qui plante a 80% doit pouvoir etre relance sans reflechir.

Le chargement passe par une table de transit alimentee en COPY, puis un seul
`insert ... select`. Ce n'est pas une optimisation gratuite : ligne a ligne, les
~120 000 barres de l'univers coutent autant d'allers-retours reseau vers
Supabase, soit des heures. En deux instructions, quelques secondes par titre.

Detection des revisions - le point qui merite l'attention
---------------------------------------------------------
Le `DO UPDATE` porte un `WHERE` : une barre identique n'est pas reecrite, donc
pas comptee. Ce qui revient est exactement l'insertion nouvelle ou la **valeur
qui a change**, et `xmax = 0` distingue les deux.

Interet concret : la colonne `Close` de Yahoo est retro-ajustee des splits (voir
`collectors/yfinance_prices.py`). Le jour ou une societe de l'univers annonce un
split, toute sa serie se decale d'un coup. Sans ce controle, le rechargement
ecraserait silencieusement dix ans de cotations et la regression changerait sans
que rien ne l'explique. Ici la revision est comptee, et au-dela d'un seuil elle
produit une entree `split_unadjusted` dans `data_quality_issues`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

# Une revision touchant plus que cette fraction des barres deja en base signe un
# reajustement de toute la serie, pas une correction ponctuelle de fin de seance.
REVISION_ALERT_RATIO = 0.05
REVISION_ALERT_MIN_ROWS = 20

STAGING = """
create temp table if not exists staging_bars (
  instrument_id bigint, freq text, ts date,
  open double precision, high double precision, low double precision,
  close double precision, volume bigint, source_id smallint
) on commit drop;
"""

# Compte l'effet a venir avant de l'appliquer. On aurait prefere `returning
# (xmax = 0)` en une passe, mais Postgres refuse de lire une colonne systeme dans
# le RETURNING d'un INSERT sur table partitionnee, et `bars` l'est par frequence.
# La jointure donne le meme resultat, exactement, pour un aller-retour de plus.
DIFF = """
select count(*) filter (where b.ts is null) as a_inserer,
       count(*) filter (
         where b.ts is not null
           and (b.close  is distinct from s.close
             or b.open   is distinct from s.open
             or b.high   is distinct from s.high
             or b.low    is distinct from s.low
             or b.volume is distinct from s.volume)) as a_reviser
  from staging_bars s
  left join bars b
    on b.instrument_id = s.instrument_id and b.freq = s.freq and b.ts = s.ts;
"""

UPSERT = """
insert into bars (instrument_id, freq, ts, open, high, low, close, volume, source_id)
select instrument_id, freq, ts, open, high, low, close, volume, source_id
  from staging_bars
on conflict (instrument_id, freq, ts) do update set
  open = excluded.open, high = excluded.high, low = excluded.low,
  close = excluded.close, volume = excluded.volume,
  source_id = excluded.source_id, ingested_at = now()
where bars.close  is distinct from excluded.close
   or bars.open   is distinct from excluded.open
   or bars.high   is distinct from excluded.high
   or bars.low    is distinct from excluded.low
   or bars.volume is distinct from excluded.volume;
"""

ISSUE = """
insert into data_quality_issues (instrument_id, issue_type, severity, ts_from, ts_to, details)
values (%(instrument_id)s, %(issue_type)s, %(severity)s, %(ts_from)s, %(ts_to)s, %(details)s);
"""

COPY_COLUMNS = ("instrument_id", "freq", "ts", "open", "high", "low",
                "close", "volume", "source_id")


@dataclass
class LoadResult:
    inserted: int = 0
    revised: int = 0
    unchanged: int = 0
    pre_existing: int = 0

    @property
    def revision_ratio(self) -> float:
        return self.revised / self.pre_existing if self.pre_existing else 0.0


def upsert_bars(cur, rows: list[dict], instrument_id: int, freq: str) -> LoadResult:
    """Charge les barres et rend le detail insere / revise / inchange."""
    result = LoadResult()
    if not rows:
        return result

    cur.execute(
        "select count(*) from bars where instrument_id = %s and freq = %s",
        (instrument_id, freq),
    )
    result.pre_existing = cur.fetchone()[0]

    cur.execute(STAGING)
    cur.execute("truncate staging_bars")
    with cur.copy(
        "copy staging_bars (" + ", ".join(COPY_COLUMNS) + ") from stdin"
    ) as copy:
        for row in rows:
            copy.write_row(tuple(row[c] for c in COPY_COLUMNS))

    cur.execute(DIFF)
    result.inserted, result.revised = cur.fetchone()
    result.unchanged = len(rows) - result.inserted - result.revised
    cur.execute(UPSERT)

    if (result.revised >= REVISION_ALERT_MIN_ROWS
            and result.revision_ratio >= REVISION_ALERT_RATIO):
        timestamps = sorted(r["ts"] for r in rows)
        cur.execute(ISSUE, {
            "instrument_id": instrument_id,
            "issue_type": "split_unadjusted",
            "severity": "warning",
            "ts_from": timestamps[0],
            "ts_to": timestamps[-1],
            "details": json.dumps({
                "freq": freq,
                "revised": result.revised,
                "pre_existing": result.pre_existing,
                "ratio": round(result.revision_ratio, 4),
                "diagnostic": "revision retroactive massive : split probable chez le "
                              "provider, la serie entiere s est decalee",
            }, ensure_ascii=False),
        })

    return result


def record_rejections(cur, instrument_id: int, freq: str, rejected: list[dict]) -> None:
    """Quarantaine plutot que rejet : ce qui n'est pas charge doit rester visible."""
    if not rejected:
        return
    timestamps = sorted(r["ts"] for r in rejected if "ts" in r)
    cur.execute(ISSUE, {
        "instrument_id": instrument_id,
        "issue_type": "gap",
        "severity": "info",
        "ts_from": timestamps[0] if timestamps else None,
        "ts_to": timestamps[-1] if timestamps else None,
        "details": json.dumps({"freq": freq, "count": len(rejected),
                               "sample": rejected[:10]}, ensure_ascii=False),
    })
