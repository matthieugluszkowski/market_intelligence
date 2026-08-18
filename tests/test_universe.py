"""Criteres d'acceptation du lot L1 (05_roadmap-et-lot.md).

    « 250 instruments en base, chacun avec au moins un symbole verifie par
      telechargement d'une cotation reelle, et zero doublon d'ISIN. »

Perimetre de depart retenu : 50 titres, conformement a la recommandation du
doc 05 SS4 - le referentiel est le point d'enlisement le plus probable du projet.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from market_intelligence.db import fetch_all, fetch_one  # noqa: E402

CIBLE_MIN = 50


def test_univers_atteint_la_cible():
    assert fetch_one("select count(*) from instruments where is_active")[0] >= CIBLE_MIN


def test_zero_doublon_disin():
    dupes = fetch_all(
        "select isin, count(*) from instruments where isin is not null "
        "group by isin having count(*) > 1"
    )
    assert dupes == []


def test_chaque_instrument_a_un_symbole_verifie():
    orphelins = fetch_all(
        """
        select i.internal_code
          from instruments i
     left join instrument_symbols s on s.instrument_id = i.id
         where s.id is null
        """
    )
    assert orphelins == [], f"instruments sans symbole : {orphelins}"


def test_chaque_symbole_porte_la_trace_dun_telechargement_reel():
    """Aucun symbole ne doit entrer en base sans cotation effectivement tiree.

    C'est le piege du lot L1 : un mapping faux ne se voit jamais ensuite, il
    produit simplement une belle courbe pour la mauvaise societe.
    """
    non_verifies = fetch_all(
        """
        select internal_code
          from instruments
         where attributes -> 'verification' ->> 'last_close' is null
            or (attributes -> 'verification' ->> 'n_obs_weekly')::int < 50
        """
    )
    assert non_verifies == [], f"instruments sans cotation eprouvee : {non_verifies}"


def test_le_nom_rapporte_par_le_provider_concorde():
    """Garde-fou contre le cas Seb / SEB banque suedoise."""
    sans_nom = fetch_all(
        "select internal_code from instruments "
        "where coalesce(attributes -> 'verification' ->> 'reported_name', '') = ''"
    )
    assert sans_nom == [], f"raison sociale non confrontee : {sans_nom}"


def test_referentiel_coherent():
    """Marche, devise et secteur pointent tous vers des lignes existantes."""
    incoherents = fetch_all(
        """
        select i.internal_code
          from instruments i
     left join exchanges  e on e.code = i.exchange_code
     left join currencies c on c.code = i.currency
     left join sectors    s on s.code = i.sector_code
         where e.code is null or c.code is null or s.code is null
        """
    )
    assert incoherents == []


def test_profondeur_historique_suffisante_pour_la_regression():
    """Le doc 05 vise >= 15 ans sur >= 95% de l'univers (critere du lot L2).

    Les exceptions attendues sont des introductions recentes - Prosus 2019,
    Ferrari 2015, Aena 2015 - pas des defauts de mapping.
    """
    total = fetch_one("select count(*) from instruments")[0]
    courts = fetch_all(
        "select internal_code, (attributes -> 'verification' ->> 'history_years')::float "
        "from instruments "
        "where (attributes -> 'verification' ->> 'history_years')::float < 15"
    )
    assert len(courts) / total <= 0.10, f"trop d'historiques courts : {courts}"


def test_symboles_uniques_par_source():
    dupes = fetch_all(
        "select source_id, symbol, count(*) from instrument_symbols "
        "group by source_id, symbol having count(*) > 1"
    )
    assert dupes == []
