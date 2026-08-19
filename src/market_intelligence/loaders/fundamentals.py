"""Ecriture idempotente des faits financiers.

Meme parti que partout ailleurs : COPY dans une table de transit puis un seul
`insert ... select`. Un titre porte de l ordre de 150 faits, l univers 8 000.
"""

from __future__ import annotations

from dataclasses import dataclass

STAGING = """
create temp table if not exists staging_facts (
  instrument_id bigint, concept_code text, period_end date, period_type text,
  value double precision, currency char(3), published_at date,
  published_at_estimated boolean, source_id smallint, confidence double precision
) on commit drop;
"""

UPSERT = """
insert into financial_facts
  (instrument_id, concept_code, period_end, period_type, value, currency,
   published_at, published_at_estimated, source_id, confidence)
select instrument_id, concept_code, period_end, period_type, value, currency,
       published_at, published_at_estimated, source_id, confidence
  from staging_facts
on conflict (instrument_id, concept_code, period_end, period_type, source_id)
do update set value = excluded.value,
              currency = excluded.currency,
              published_at = excluded.published_at,
              published_at_estimated = excluded.published_at_estimated,
              confidence = excluded.confidence,
              ingested_at = now()
where financial_facts.value is distinct from excluded.value;
"""

COLONNES = ("instrument_id", "concept_code", "period_end", "period_type", "value",
            "currency", "published_at", "published_at_estimated", "source_id",
            "confidence")


@dataclass
class FactsLoadResult:
    nouveaux: int = 0
    total: int = 0
    exercices: int = 0
    concepts: int = 0


def upsert_facts(cur, facts: list[dict], instrument_id: int) -> FactsLoadResult:
    result = FactsLoadResult()
    if not facts:
        return result

    cur.execute("select count(*) from financial_facts where instrument_id = %s",
                (instrument_id,))
    avant = cur.fetchone()[0]

    cur.execute(STAGING)
    cur.execute("truncate staging_facts")
    with cur.copy(f"copy staging_facts ({', '.join(COLONNES)}) from stdin") as copy:
        for fait in facts:
            copy.write_row(tuple(fait[c] for c in COLONNES))
    cur.execute(UPSERT)

    cur.execute(
        "select count(*), count(distinct period_end), count(distinct concept_code) "
        "from financial_facts where instrument_id = %s", (instrument_id,))
    result.total, result.exercices, result.concepts = cur.fetchone()
    result.nouveaux = result.total - avant
    return result
