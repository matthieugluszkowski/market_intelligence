"""Acces aux donnees pour le dashboard, avec cache.

Le moteur analytique tourne cote VPS et la base ne fait que stocker (doc 00 SS5,
seconde reserve sur Supabase free : 500 Mo de RAM partagee). Ce module ne fait
donc que lire des lignes deja calculees - aucune regression n'est refaite ici.

Consequence directe sur le graphe : la droite affichee est celle qui a ete
**ecrite** dans `regression_fits`, reconstruite depuis `intercept` et
`slope_annual`. Si on la recalculait a l'affichage, le graphe pourrait diverger
silencieusement de ce que le screener a classe.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from market_intelligence.db import connect  # noqa: E402

TTL = 900  # le dashboard se consulte, il ne surveille pas (principe I1)


def _frame(sql: str, params: dict | None = None) -> pd.DataFrame:
    with connect() as conn, conn.cursor() as cur:
        cur.execute(sql, params or {})
        colonnes = [d.name for d in cur.description]
        return pd.DataFrame(cur.fetchall(), columns=colonnes)


@st.cache_data(ttl=TTL)
def derniere_date_de_calcul() -> date | None:
    frame = _frame("select max(as_of_date) as d from regression_fits")
    return None if frame.empty else frame["d"].iloc[0]


@st.cache_data(ttl=TTL)
def screener(as_of: date) -> pd.DataFrame:
    """Une ligne par instrument, telle qu'elle a ete calculee a `as_of`.

    `quality_tier` et `quadrant` sortent en `unqualified` tant que le lot L6b
    n'existe pas. C'est leur statut reel et il doit se voir : afficher un titre
    comme une cible alors que sa position concurrentielle n'a jamais ete evaluee
    serait exactement la moitie manquante de la methode.
    """
    return _frame(
        """
        select i.internal_code, i.name, i.isin, i.country_iso2, i.exchange_code,
               s.label as secteur, f.z_score, f.slope_annual, f.r_squared,
               f.fit_quality, f.quality_reasons, f.half_life_days, f.n_obs,
               f.last_close, f.sigma_resid, f.window_start, f.window_end,
               f.ar1_ci_low, f.ar1_ci_high, f.regime_stats, i.currency,
               coalesce(q.quality_tier, 'unqualified') as quality_tier,
               coalesce(q.regime, 'unknown') as regime,
               q.erosion_flags, q.roic_vs_threshold
          from regression_fits f
          join instruments i on i.id = f.instrument_id
          left join sectors s on s.code = i.sector_code
          left join quality_scores q
            on q.instrument_id = i.id
           and q.as_of_date = (select max(as_of_date) from quality_scores
                                where instrument_id = i.id)
         where f.as_of_date = %(as_of)s
         order by f.z_score
        """,
        {"as_of": as_of},
    )


@st.cache_data(ttl=TTL)
def instruments() -> pd.DataFrame:
    return _frame(
        "select id, internal_code, name, isin, currency, exchange_code "
        "from instruments where is_active order by name"
    )


@st.cache_data(ttl=TTL)
def fit(internal_code: str, as_of: date) -> pd.Series | None:
    frame = _frame(
        """
        select f.*, i.name, i.isin, i.currency, i.internal_code
          from regression_fits f join instruments i on i.id = f.instrument_id
         where i.internal_code = %(code)s and f.as_of_date = %(as_of)s
         order by f.method_version desc limit 1
        """,
        {"code": internal_code, "as_of": as_of},
    )
    return None if frame.empty else frame.iloc[0]


@st.cache_data(ttl=TTL)
def barres(internal_code: str, freq: str = "1w") -> pd.DataFrame:
    """Serie ajustee des seuls splits, celle sur laquelle porte la regression.

    `factor_total` existe en base et sert la mesure de performance, mais la
    tendance se lit sur le cours simple pour rester comparable a la reference.
    """
    return _frame(
        """
        select b.ts, b.close * coalesce(a.factor_price, 1.0) as close,
               b.close as close_brut,
               b.close * coalesce(a.factor_total, 1.0) as close_rendement_total
          from bars b
          join instruments i on i.id = b.instrument_id
          left join adjustment_factors a
            on a.instrument_id = b.instrument_id and a.ts = b.ts
         where i.internal_code = %(code)s and b.freq = %(freq)s
         order by b.ts
        """,
        {"code": internal_code, "freq": freq},
    )


@st.cache_data(ttl=TTL)
def historique_des_fits(internal_code: str) -> pd.DataFrame:
    """Le principe P5 rendu visible : ce que le modele affirmait, semaine apres
    semaine. Une seule ligne aujourd'hui ; 52 dans un an."""
    return _frame(
        """
        select f.as_of_date, f.z_score, f.slope_annual, f.fit_quality, f.n_obs
          from regression_fits f join instruments i on i.id = f.instrument_id
         where i.internal_code = %(code)s
         order by f.as_of_date
        """,
        {"code": internal_code},
    )


@st.cache_data(ttl=TTL)
def qualite(internal_code: str) -> dict:
    """Dernier score de qualite et son groupe de pairs (doc 04, bloc D)."""
    score = _frame(
        """
        select q.*, g.code as groupe_code, g.label as groupe_label,
               g.kind as groupe_kind, g.is_complete as groupe_complet
          from quality_scores q
          join instruments i on i.id = q.instrument_id
          left join peer_groups g on g.id = q.peer_group_id
         where i.internal_code = %(code)s
         order by q.as_of_date desc, q.method_version desc limit 1
        """,
        {"code": internal_code},
    )
    if score.empty:
        return {}

    membres = _frame(
        """
        select coalesce(pi.name, m.external_name) as nom,
               m.is_in_universe,
               coalesce(pi.country_iso2, m.external_ref ->> 'pays') as pays,
               m.external_ref ->> 'menace' as menace
          from peer_group_members m
          left join instruments pi on pi.id = m.instrument_id
         where m.peer_group_id = %(groupe)s
         order by m.is_in_universe desc, nom
        """,
        {"groupe": int(score["peer_group_id"].iloc[0])}
        if score["peer_group_id"].iloc[0] is not None else {"groupe": -1},
    )

    evaluations = _frame(
        """
        select a.assessed_at, a.expires_at, a.position_verdict, a.durability_verdict,
               a.moat_sources, a.threats, a.rationale, a.authored_by, a.reviewed_by,
               a.expires_at < current_date as perimee
          from moat_assessments a join instruments i on i.id = a.instrument_id
         where i.internal_code = %(code)s
         order by a.assessed_at desc limit 1
        """,
        {"code": internal_code},
    )

    return {"score": score.iloc[0], "membres": membres,
            "evaluation": None if evaluations.empty else evaluations.iloc[0]}


@st.cache_data(ttl=TTL)
def fondamentaux(internal_code: str, as_of: date) -> dict:
    """Ratios point-in-time et verdict de coherence (doc 04, bloc E).

    Le point-in-time est applique ici comme ailleurs : seuls les faits dont
    `published_at <= as_of` entrent dans le calcul. Un ecran qui afficherait les
    comptes 2025 sur une fiche datee de janvier 2025 mentirait sur ce que le
    systeme savait a cette date.
    """
    from market_intelligence.analytics import ratios as R

    with connect() as conn, conn.cursor() as cur:
        cur.execute("select id, sector_code from instruments where internal_code = %s",
                    (internal_code,))
        ligne = cur.fetchone()
        if ligne is None:
            return {}
        instrument_id, sector_code = ligne

        cur.execute(
            """
            select (select b.close from bars b
                     where b.instrument_id = %(id)s and b.freq = '1w'
                       and b.ts <= %(as_of)s
                     order by b.ts desc limit 1) as cours,
                   (select o.shares from shares_outstanding o
                     where o.instrument_id = %(id)s and o.as_of <= %(as_of)s
                     order by o.as_of desc limit 1) as actions
            """,
            {"id": instrument_id, "as_of": as_of},
        )
        cours, actions = cur.fetchone()
        capitalisation = (float(cours) * float(actions)
                          if cours is not None and actions is not None else None)

        f = R.charge(cur, instrument_id, as_of)
        if not f.exercices:
            return {}
        r = R.ratios(f, capitalisation=capitalisation,
                     cours=float(cours) if cours else None, sector_code=sector_code)
        coherence = R.coherence_prix_fondamentaux(f, r)

        cur.execute(
            """
            select ff.concept_code, ff.period_end, ff.value, ff.published_at,
                   ff.published_at_estimated, ff.confidence, ds.code as source
              from financial_facts ff
              join data_sources ds on ds.id = ff.source_id
             where ff.instrument_id = %(id)s and ff.published_at <= %(as_of)s
               and ff.concept_code in ('revenue', 'ebit', 'ebitda', 'net_income',
                                       'total_equity', 'net_debt', 'fcf', 'shares_basic')
             order by ff.period_end desc, ff.concept_code
            """,
            {"id": instrument_id, "as_of": as_of},
        )
        colonnes = [d.name for d in cur.description]
        faits = pd.DataFrame(cur.fetchall(), columns=colonnes)

    return {"ratios": r, "coherence": coherence, "faits": faits,
            "capitalisation": capitalisation, "exercices": f.exercices}


@st.cache_data(ttl=TTL)
def anomalies(internal_code: str) -> pd.DataFrame:
    return _frame(
        """
        select d.issue_type, d.severity, d.detected_at::date as depuis,
               d.run_count, d.details, d.resolved_at::date as resolue_le,
               d.resolution
          from data_quality_issues d
          join instruments i on i.id = d.instrument_id
         where i.internal_code = %(code)s and d.resolved_at is null
         order by case d.severity when 'blocking' then 0 else 1 end, d.detected_at
        """,
        {"code": internal_code},
    )
