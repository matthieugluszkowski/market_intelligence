"""Tests unitaires et invariants pour le module analytics/dividends."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from market_intelligence.analytics.dividends import (  # noqa: E402
    calcul_cagr,
    evalue_securite_dividende,
)
from market_intelligence.db import connect_direct, fetch_all, fetch_one  # noqa: E402


def test_calcul_cagr():
    # Doublement en 3 ans: (2/1)^(1/3) - 1 ≈ 25.99%
    cagr = calcul_cagr(1.0, 2.0, 3)
    assert cagr == pytest.approx(0.25992, abs=1e-4)

    # Même valeur = 0%
    assert calcul_cagr(2.5, 2.5, 5) == pytest.approx(0.0)

    # Entrées invalides
    assert calcul_cagr(None, 2.0, 3) is None
    assert calcul_cagr(1.0, -2.0, 3) is None
    assert calcul_cagr(0.0, 2.0, 3) is None
    assert calcul_cagr(1.0, 2.0, 0) is None


def test_evalue_securite_dividende():
    # Sans dividende
    v, _ = evalue_securite_dividende(None, None, None, None, 0)
    assert v == "sans_dividende"

    # Dividende exceptionnel (DPA actuel > 1.8x la moyenne 5 ans)
    v, _ = evalue_securite_dividende(dernier_dpa=3.5, dpa_moyen_5a=1.0, payout_fcf=0.5, payout_rn=0.5, nb_baisses_5a=0)
    assert v == "exceptionnel"

    # FCF négatif
    v, _ = evalue_securite_dividende(dernier_dpa=1.0, dpa_moyen_5a=1.0, payout_fcf=None, payout_rn=0.5, nb_baisses_5a=0, fcf_negatif=True)
    assert v == "tendu"

    # Payout FCF > 100%
    v, _ = evalue_securite_dividende(dernier_dpa=1.0, dpa_moyen_5a=1.0, payout_fcf=1.2, payout_rn=0.7, nb_baisses_5a=0)
    assert v == "tendu"

    # Sécurisé : FCF payout <= 65% et aucune baisse sur 5 ans
    v, _ = evalue_securite_dividende(dernier_dpa=1.0, dpa_moyen_5a=0.9, payout_fcf=0.45, payout_rn=0.50, nb_baisses_5a=0)
    assert v == "sécurisé"

    # Soutenable : FCF payout entre 65% et 85%
    v, _ = evalue_securite_dividende(dernier_dpa=1.0, dpa_moyen_5a=0.9, payout_fcf=0.75, payout_rn=0.70, nb_baisses_5a=0)
    assert v == "soutenable"


def test_analyse_dividendes_instrument_sur_un_titre_reel():
    """Vérifie l'analyse de dividende sur un titre de l'univers (ex: TotalEnergies ou Sanofi ou Air Liquide)."""
    from market_intelligence.analytics.dividends import analyse_dividendes_instrument

    row = fetch_one("select id from instruments where internal_code in ('EQ:FR:TTE', 'EQ:FR:AIRLIQUIDE', 'EQ:FR:SANOFI') limit 1")
    if not row:
        pytest.skip("Aucun titre de test trouvé en base")

    instrument_id = row[0]
    with connect_direct() as conn:
        with conn.cursor() as cur:
            prof = analyse_dividendes_instrument(cur, instrument_id)
            assert prof is not None
            assert prof.dernier_dpa is not None
            assert prof.dernier_dpa > 0
            assert prof.rendement_actuel_pct is not None
            assert prof.historique_annuel != []


def test_screener_dividendes_sql_retourne_des_lignes():
    """La requête SQL du screener dividende doit s'exécuter et rendre les colonnes attendues."""
    from market_intelligence.analytics.dividends import SQL_SCREENER_DIVIDENDES

    as_of = fetch_one("select max(as_of_date) from regression_fits")[0]
    assert as_of is not None

    rows = fetch_all(SQL_SCREENER_DIVIDENDES, {"as_of": as_of})
    assert len(rows) > 0, "Le screener dividende ne doit pas être vide sur l'univers calculé"
    first = rows[0]
    # Vérifier que le rendement est calculé
    assert first[16] is not None  # rendement_actuel_pct


def test_evalue_11_regles_dividende():
    """Vérifie la logique d'attribution des points et verdicts sur les 11 règles d'investissement."""
    from market_intelligence.analytics.dividends import evalue_11_regles_dividende

    # Cas idéal : Entreprise solide cochant toutes les cases
    facts_ideaux = {
        "revenue": [(date(2023, 12, 31), 10_000_000_000.0)],
        "ebit": [(date(2023, 12, 31), 2_000_000_000.0)],
        "interest_expense": [(date(2023, 12, 31), 100_000_000.0)],
        "net_income": [
            (date(2021, 12, 31), 1_000_000_000.0),
            (date(2022, 12, 31), 1_200_000_000.0),
            (date(2023, 12, 31), 1_500_000_000.0),
        ],
        "total_equity": [(date(2023, 12, 31), 8_000_000_000.0)],
        "total_debt": [(date(2023, 12, 31), 4_000_000_000.0)],
        "net_debt": [(date(2023, 12, 31), 2_000_000_000.0)],
        "shares_basic": [(date(2023, 12, 31), 200_000_000.0)],
        "fcf": [(date(2023, 12, 31), 1_200_000_000.0)],
    }

    # Cours = 50.0, DPA = 3.0 (Rdt = 6.0% >= 5%), Cap = 10 Mrd, PER = 6.67x in [3; 14], P/B = 1.25x < 4
    # Marge avant impôts = (2 Mrd - 100M) / 10 Mrd = 19% > 13%
    # Dettes / Equity = 4 / 8 = 50% <= 110%
    # RN croissant sur 3 ans : 1.0 -> 1.2 -> 1.5 Mrd
    # Streak dividende = 8 ans >= 5 ans
    # Slope annual = +8% >= +5%
    score_ideal = evalue_11_regles_dividende(
        cours=50.0,
        slope_annual=0.08,
        dernier_dpa=3.0,
        dpa_moyen_5a=2.8,
        streak_annees=8,
        facts_series=facts_ideaux,
        quality_tier="solid",
        secteur_nom="Industrie",
    )

    assert score_ideal.total_oui == 11
    assert score_ideal.total_capitaux_oui == 6
    assert score_ideal.est_investissable is True
    assert "INVESTISSABLE" in score_ideal.verdict

    # Cas dégradé : faible rendement, endettement lourd, PER cher, baisse du cours
    facts_degrades = {
        "revenue": [(date(2023, 12, 31), 500_000_000.0)],
        "ebit": [(date(2023, 12, 31), 20_000_000.0)],
        "interest_expense": [(date(2023, 12, 31), 15_000_000.0)],
        "net_income": [(date(2023, 12, 31), 5_000_000.0)],
        "total_equity": [(date(2023, 12, 31), 100_000_000.0)],
        "total_debt": [(date(2023, 12, 31), 300_000_000.0)],  # Gearing = 300% > 110%
        "shares_basic": [(date(2023, 12, 31), 10_000_000.0)],
    }
    score_degrade = evalue_11_regles_dividende(
        cours=20.0,  # Cap = 200M < 500M, PER = 200M/5M = 40x > 14x
        slope_annual=-0.03,  # Pente négative
        dernier_dpa=0.20,  # Rdt = 1% < 5%
        dpa_moyen_5a=0.20,
        streak_annees=2,  # < 5 ans
        facts_series=facts_degrades,
        quality_tier="eroded",
        secteur_nom="",
    )

    assert score_degrade.total_oui < 8
    assert score_degrade.est_investissable is False
    assert "RISQUÉ" in score_degrade.verdict

