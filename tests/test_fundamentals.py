"""Criteres d'acceptation du lot L6 (05_roadmap-et-lot.md).

    « >= 80% des titres ont >= 3 exercices de chiffre d'affaires et de resultat
      net ; les ratios recoupent une source independante sur un echantillon de
      10 titres. »

Le second critere est joue par `scripts/verify_ratios.py`, qui interroge le
reseau : il n'a pas sa place dans une suite de tests. Ce qui est teste ici, c'est
ce dont depend la validite de ce recoupement - le point-in-time, les conventions
de signe, l'arbitrage entre libelles, et le fait qu'un critere non evaluable ne
soit jamais compte comme reussi.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from market_intelligence.analytics import ratios as R  # noqa: E402
from market_intelligence.db import connect, fetch_all, fetch_one  # noqa: E402
from market_intelligence.normalizers.fundamentals import (  # noqa: E402
    DELAI_ANNUEL_JOURS, date_de_publication_estimee,
)

COUVERTURE_MIN = 0.80


def fondamentaux(**series) -> R.Fondamentaux:
    """Construit un jeu de faits synthetique : {concept: [(annee, valeur), ...]}."""
    f = R.Fondamentaux()
    for concept, valeurs in series.items():
        f.par_concept[concept] = {date(annee, 12, 31): v for annee, v in valeurs}
    f.exercices = sorted({e for v in f.par_concept.values() for e in v})
    return f


# --------------------------------------------------------------------------- #
# Critere 1 : couverture
# --------------------------------------------------------------------------- #
def test_couverture_des_exercices():
    total = fetch_one("select count(*) from instruments where is_active")[0]
    couverts = fetch_one(
        """
        select count(*) from (
          select instrument_id from financial_facts
           where concept_code in ('revenue', 'net_income') and period_type = 'FY'
           group by instrument_id
          having count(*) filter (where concept_code = 'revenue') >= 3
             and count(*) filter (where concept_code = 'net_income') >= 3
        ) t
        """
    )[0]
    assert couverts / total >= COUVERTURE_MIN, f"{couverts}/{total}"


def test_les_faits_portent_tous_une_date_de_publication():
    """Sans elle, le calcul point-in-time les exclut pour toujours."""
    assert fetch_one(
        "select count(*) from financial_facts where published_at is null")[0] == 0


def test_les_dates_estimees_sont_marquees_comme_telles():
    """Le drapeau existe pour que la distinction ne se perde jamais : le jour ou
    une source servira les vraies dates, on saura quels faits reprendre."""
    non_marques = fetch_one(
        """
        select count(*) from financial_facts f
          join data_sources d on d.id = f.source_id
         where d.code = 'yfinance' and not f.published_at_estimated
        """
    )[0]
    assert non_marques == 0


def test_la_date_estimee_est_posterieure_a_la_cloture():
    """Une estimation trop precoce fabriquerait du look-ahead invisible."""
    assert fetch_one(
        "select count(*) from financial_facts where published_at <= period_end")[0] == 0


def test_le_delai_reglementaire_est_de_quatre_mois():
    cloture = date(2024, 12, 31)
    estimee = date_de_publication_estimee(cloture, "FY")
    assert estimee == cloture + timedelta(days=DELAI_ANNUEL_JOURS)
    assert (estimee - cloture).days >= 120, "moins de quatre mois : borne trop serree"


# --------------------------------------------------------------------------- #
# Point-in-time
# --------------------------------------------------------------------------- #
def test_un_fait_non_encore_publie_est_invisible():
    """Les comptes 2024 ne sont connus qu'en mars 2025 ; les utiliser pour juger
    le titre en janvier 2025 est du look-ahead pur."""
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "select instrument_id, min(period_end), min(published_at) "
            "from financial_facts group by instrument_id limit 1"
        )
        instrument_id, period_end, published_at = cur.fetchone()

        veille = R.charge(cur, instrument_id, published_at - timedelta(days=1))
        jour = R.charge(cur, instrument_id, published_at)

    assert period_end not in veille.exercices, "un fait visible avant sa publication"
    assert period_end in jour.exercices


# --------------------------------------------------------------------------- #
# Ratios : fonctions pures
# --------------------------------------------------------------------------- #
def test_les_ratios_de_base_sont_justes():
    f = fondamentaux(
        revenue=[(2024, 1000.0)], ebit=[(2024, 200.0)], net_income=[(2024, 150.0)],
        total_equity=[(2024, 750.0)], ebitda=[(2024, 250.0)], net_debt=[(2024, 500.0)],
    )
    r = R.ratios(f, capitalisation=3000.0)
    assert r["per"] == pytest.approx(20.0)
    assert r["marge_operationnelle"] == pytest.approx(0.20)
    assert r["marge_nette"] == pytest.approx(0.15)
    assert r["roe"] == pytest.approx(0.20)
    assert r["price_to_book"] == pytest.approx(4.0)
    assert r["ev_ebit"] == pytest.approx(3500.0 / 200.0)
    assert r["dette_nette_sur_ebitda"] == pytest.approx(2.0)


def test_un_ratio_sans_capitalisation_sort_a_none():
    """Un ratio faux est pire qu'un ratio absent : il se compare, se trie et se
    decide."""
    f = fondamentaux(revenue=[(2024, 1000.0)], net_income=[(2024, 150.0)])
    r = R.ratios(f, capitalisation=None)
    assert r["per"] is None and r["price_to_book"] is None
    assert r["marge_nette"] == pytest.approx(0.15)


def test_la_croissance_est_annualisee():
    f = fondamentaux(revenue=[(2021, 100.0), (2022, 110.0), (2023, 121.0), (2024, 133.1)])
    assert R.ratios(f)["croissance_ca_3a"] == pytest.approx(0.10)


def test_la_croissance_exige_la_profondeur_complete():
    f = fondamentaux(revenue=[(2023, 100.0), (2024, 200.0)])
    assert R.ratios(f)["croissance_ca_3a"] is None


def test_la_division_par_zero_ne_leve_pas():
    f = fondamentaux(revenue=[(2024, 0.0)], net_income=[(2024, 10.0)])
    assert R.ratios(f, capitalisation=100.0)["marge_nette"] is None


# --------------------------------------------------------------------------- #
# Coherence prix / fondamentaux
# --------------------------------------------------------------------------- #
def test_une_societe_saine_est_confirmee():
    f = fondamentaux(
        revenue=[(2021, 900.0), (2022, 950.0), (2023, 1000.0), (2024, 1100.0)],
        ebit=[(2021, 100.0), (2022, 120.0), (2023, 140.0), (2024, 160.0)],
        ebitda=[(2024, 250.0)], net_debt=[(2024, 300.0)],
        shares_basic=[(2021, 100.0), (2022, 100.0), (2023, 100.0), (2024, 100.0)],
    )
    r = R.ratios(f, capitalisation=3000.0)
    assert R.coherence_prix_fondamentaux(f, r).verdict == "confirme"


def test_un_chiffre_daffaires_en_baisse_rend_le_signal_suspect():
    """C'est la liste des titres qui ont l'air d'opportunites et n'en sont pas,
    et c'est la qu'on perd de l'argent."""
    f = fondamentaux(
        revenue=[(2021, 1200.0), (2022, 1100.0), (2023, 1000.0), (2024, 900.0)],
        ebit=[(2021, 100.0), (2022, 90.0), (2023, 80.0), (2024, 70.0)],
        ebitda=[(2024, 150.0)], net_debt=[(2024, 300.0)],
        shares_basic=[(2021, 100.0), (2022, 100.0), (2023, 100.0), (2024, 100.0)],
    )
    coherence = R.coherence_prix_fondamentaux(f, R.ratios(f, capitalisation=1000.0))
    assert coherence.verdict == "suspect"
    assert "ca_non_decroissant" in coherence.echecs


def test_un_levier_excessif_rend_le_signal_suspect():
    f = fondamentaux(
        revenue=[(2021, 900.0), (2022, 950.0), (2023, 1000.0), (2024, 1100.0)],
        ebit=[(2021, 100.0), (2022, 100.0), (2023, 100.0), (2024, 100.0)],
        ebitda=[(2024, 100.0)], net_debt=[(2024, 900.0)],
        shares_basic=[(2021, 100.0), (2022, 100.0), (2023, 100.0), (2024, 100.0)],
    )
    coherence = R.coherence_prix_fondamentaux(f, R.ratios(f, capitalisation=1000.0))
    assert "levier_maitrise" in coherence.echecs


def test_une_dilution_massive_rend_le_signal_suspect():
    f = fondamentaux(
        revenue=[(2021, 900.0), (2022, 950.0), (2023, 1000.0), (2024, 1100.0)],
        ebit=[(2021, 100.0), (2022, 100.0), (2023, 100.0), (2024, 100.0)],
        ebitda=[(2024, 150.0)], net_debt=[(2024, 100.0)],
        shares_basic=[(2021, 100.0), (2022, 200.0), (2023, 400.0), (2024, 800.0)],
    )
    coherence = R.coherence_prix_fondamentaux(f, R.ratios(f, capitalisation=1000.0))
    assert "pas_de_dilution" in coherence.echecs


def test_un_critere_non_evaluable_nest_jamais_compte_comme_reussi():
    """Traiter l'absence de donnee comme un succes est la facon la plus courante
    de fabriquer un faux signal."""
    f = fondamentaux(revenue=[(2023, 1000.0), (2024, 1100.0)])
    coherence = R.coherence_prix_fondamentaux(f, R.ratios(f, capitalisation=1000.0))
    assert coherence.verdict == "indeterminable"
    assert coherence.manquants


def test_un_echec_prime_sur_une_donnee_manquante():
    f = fondamentaux(
        revenue=[(2021, 1200.0), (2022, 1100.0), (2023, 1000.0), (2024, 900.0)],
    )
    coherence = R.coherence_prix_fondamentaux(f, R.ratios(f, capitalisation=1000.0))
    assert coherence.verdict == "suspect"


# --------------------------------------------------------------------------- #
# Secteur financier
# --------------------------------------------------------------------------- #
def test_les_ratios_adosses_au_chiffre_daffaires_sont_neutralises_en_finance():
    """Constate en recoupant : Allianz sortait a 25% d'ecart sur la marge nette,
    la ou les industriels tombaient a 0,0%. La notion de chiffre d'affaires n'a
    pas de definition stable pour un assureur."""
    f = fondamentaux(
        revenue=[(2024, 1000.0)], net_income=[(2024, 150.0)],
        total_equity=[(2024, 750.0)], ebitda=[(2024, 200.0)], net_debt=[(2024, 5000.0)],
    )
    r = R.ratios(f, capitalisation=3000.0, sector_code=R.SECTEUR_FINANCIER)
    assert r["marge_nette"] is None
    assert r["dette_nette_sur_ebitda"] is None
    # Ceux qui gardent leur sens restent calcules.
    assert r["per"] == pytest.approx(20.0)
    assert r["roe"] == pytest.approx(0.20)


def test_un_levier_bancaire_ne_rend_pas_le_signal_suspect():
    """Une banque a structurellement un levier de 15 a 20 : la faire sortir en
    `suspect` a chaque passage pour cette raison serait du bruit."""
    f = fondamentaux(
        revenue=[(2021, 900.0), (2022, 950.0), (2023, 1000.0), (2024, 1100.0)],
        ebit=[(2021, 100.0), (2022, 100.0), (2023, 100.0), (2024, 100.0)],
        ebitda=[(2024, 100.0)], net_debt=[(2024, 2000.0)],
        shares_basic=[(2021, 100.0), (2022, 100.0), (2023, 100.0), (2024, 100.0)],
    )
    r = R.ratios(f, capitalisation=1000.0, sector_code=R.SECTEUR_FINANCIER)
    assert "levier_maitrise" not in R.coherence_prix_fondamentaux(f, r).echecs


# --------------------------------------------------------------------------- #
# Conventions de signe et arbitrage entre libelles
# --------------------------------------------------------------------------- #
def test_les_flux_sortants_sont_stockes_en_positif():
    """`capex`, `dividends_paid` et `buybacks` sont servis en negatif par le
    provider et stockes en positif, conformement a `sign_convention`."""
    negatifs = fetch_all(
        "select concept_code, count(*) from financial_facts "
        "where concept_code in ('capex', 'dividends_paid', 'buybacks') and value < 0 "
        "group by 1"
    )
    assert negatifs == []


def test_chaque_fait_pointe_vers_un_concept_declare():
    orphelins = fetch_all(
        """
        select distinct f.concept_code from financial_facts f
          left join financial_concepts c on c.code = f.concept_code
         where c.code is null
        """
    )
    assert orphelins == []


def test_aucun_doublon_de_fait():
    doublons = fetch_all(
        "select instrument_id, concept_code, period_end, period_type, source_id, "
        "count(*) from financial_facts group by 1,2,3,4,5 having count(*) > 1"
    )
    assert doublons == []
