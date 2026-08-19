"""Watchlist : les titres qu'on suit reellement (doc 10).

Le screener rend 57 lignes, la watchlist dit lesquelles on suit. C'est une
**selection humaine**, pas un filtre calcule : elle survit au fait qu'un titre
sorte des criteres du jour, et c'est tout son interet. Un titre qu'on suit
depuis huit mois et qui repasse sous -2 sigma ne se decouvre pas, il se
retrouve.

Retrait en douceur
------------------
On n'efface jamais une ligne, on l'horodate. Savoir qu'on a suivi Kering puis
qu'on l'a retire est une information ; l'effacer laisse croire qu'on ne l'a
jamais regarde. C'est le meme raisonnement que pour le journal d'anomalies et
pour `regression_fits`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

AJOUTE = """
insert into watchlist
  (instrument_id, note, z_at_add, fit_at_add, quality_at_add)
select %(instrument_id)s, %(note)s, f.z_score, f.fit_quality,
       coalesce(q.quality_tier, 'unqualified')
  from instruments i
  left join regression_fits f
    on f.instrument_id = i.id
   and f.as_of_date = (select max(as_of_date) from regression_fits
                        where instrument_id = i.id)
  left join quality_scores q
    on q.instrument_id = i.id
   and q.as_of_date = (select max(as_of_date) from quality_scores
                        where instrument_id = i.id)
 where i.id = %(instrument_id)s
on conflict (instrument_id) where removed_at is null do nothing
returning id;
"""

RETIRE = """
update watchlist set removed_at = now(), removal_reason = %(raison)s
 where instrument_id = %(instrument_id)s and removed_at is null
returning id, added_at::date, z_at_add;
"""

EST_SUIVI = """
select id, added_at::date, note, z_at_add, fit_at_add, quality_at_add
  from watchlist where instrument_id = %(instrument_id)s and removed_at is null;
"""

# La liste vivante, avec ce qui a change depuis l'ajout. La colonne `derive`
# est ce qu'on vient regarder : le titre a-t-il baisse depuis qu'on le suit.
LISTE = """
select w.id, i.internal_code, i.name, w.added_at::date, w.note,
       w.z_at_add, f.z_score as z_actuel,
       f.z_score - w.z_at_add as derive,
       f.fit_quality, coalesce(q.quality_tier, 'unqualified') as quality_tier,
       coalesce(q.regime, 'unknown') as regime,
       f.half_life_days, s.label as secteur,
       current_date - w.added_at::date as jours_de_suivi
  from watchlist w
  join instruments i on i.id = w.instrument_id
  left join sectors s on s.code = i.sector_code
  left join regression_fits f
    on f.instrument_id = i.id
   and f.as_of_date = (select max(as_of_date) from regression_fits
                        where instrument_id = i.id)
  left join quality_scores q
    on q.instrument_id = i.id
   and q.as_of_date = (select max(as_of_date) from quality_scores
                        where instrument_id = i.id)
 where w.removed_at is null
 order by f.z_score nulls last;
"""

HISTORIQUE = """
select i.internal_code, i.name, w.added_at::date, w.removed_at::date,
       w.removal_reason, w.note, w.z_at_add,
       w.removed_at::date - w.added_at::date as jours_suivis
  from watchlist w join instruments i on i.id = w.instrument_id
 where w.removed_at is not null
 order by w.removed_at desc;
"""

CODES_SUIVIS = """
select i.internal_code from watchlist w
  join instruments i on i.id = w.instrument_id
 where w.removed_at is null;
"""


@dataclass
class Suivi:
    """Etat de suivi d'un titre, tel qu'il etait au moment de l'ajout."""

    id: int
    depuis: date
    note: str | None
    z_at_add: float | None
    fit_at_add: str | None
    quality_at_add: str | None


def ajoute(cur, instrument_id: int, note: str | None = None) -> int | None:
    """Met un titre sous surveillance. Rend l'identifiant, ou None s'il l'etait deja.

    Le z-score, le verdict de fit et le niveau de qualite du jour sont figes a
    l'ajout : sans eux, on ne peut plus dire trois mois plus tard si le titre a
    baisse depuis qu'on le suit ou s'il etait deja bas - et c'est exactement la
    question qu'on se pose en rouvrant sa liste.
    """
    cur.execute(AJOUTE, {"instrument_id": instrument_id,
                         "note": (note or "").strip() or None})
    ligne = cur.fetchone()
    return ligne[0] if ligne else None


def retire(cur, instrument_id: int, raison: str | None = None) -> bool:
    """Retire un titre. Horodate, n'efface pas."""
    cur.execute(RETIRE, {"instrument_id": instrument_id,
                         "raison": (raison or "").strip() or None})
    return cur.fetchone() is not None


def est_suivi(cur, instrument_id: int) -> Suivi | None:
    cur.execute(EST_SUIVI, {"instrument_id": instrument_id})
    ligne = cur.fetchone()
    return Suivi(*ligne) if ligne else None


def bascule(cur, instrument_id: int, note: str | None = None) -> bool:
    """Ajoute si absent, retire si present. Rend l'etat resultant."""
    if est_suivi(cur, instrument_id):
        retire(cur, instrument_id)
        return False
    ajoute(cur, instrument_id, note)
    return True


def codes_suivis(cur) -> set[str]:
    cur.execute(CODES_SUIVIS)
    return {ligne[0] for ligne in cur.fetchall()}
