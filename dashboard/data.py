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
