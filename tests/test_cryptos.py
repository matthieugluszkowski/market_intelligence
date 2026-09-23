"""Tests d'integrite pour la classe d'actifs crypto et les 5 cryptomonnaies majeures."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from market_intelligence.db import fetch_all, fetch_one  # noqa: E402

CODES_CRYPTOS = {"CRYPTO:BTC", "CRYPTO:ETH", "CRYPTO:SOL", "CRYPTO:BNB", "CRYPTO:XRP"}


def test_asset_class_crypto_est_declaree():
    """La classe 'crypto' doit exister avec label, sans fondamentaux et avec politique 10 ans."""
    row = fetch_one(
        "select code, label, supports_fundamentals, default_policy_code from asset_classes where code = 'crypto'"
    )
    assert row is not None, "classe d'actifs 'crypto' introuvable dans asset_classes"
    code, label, supports_fund, default_policy = row
    assert code == "crypto"
    assert "crypto" in label.lower()
    assert supports_fund is False
    assert default_policy == "loglin_10y"


def test_les_5_cryptomonnaies_sont_presentes_et_actives():
    """Les 5 cryptomonnaies majeures doivent etre declarees et actives."""
    rows = fetch_all(
        "select internal_code, name, currency, asset_class from instruments where internal_code = any(%s) and is_active",
        (list(CODES_CRYPTOS),),
    )
    trouves = {r[0] for r in rows}
    assert trouves == CODES_CRYPTOS, f"cryptos manquantes : {CODES_CRYPTOS - trouves}"
    for _, _, currency, asset_class in rows:
        assert currency == "USD"
        assert asset_class == "crypto"


def test_les_cryptos_ont_des_barres_de_cours_hebdo_et_quotidiennes():
    """Chaque crypto doit posseder un historique significatif de barres 1w et 1d."""
    for code in CODES_CRYPTOS:
        inst_id = fetch_one("select id from instruments where internal_code = %s", (code,))[0]
        nb_1w = fetch_one("select count(*) from bars where instrument_id = %s and freq = '1w'", (inst_id,))[0]
        nb_1d = fetch_one("select count(*) from bars where instrument_id = %s and freq = '1d'", (inst_id,))[0]

        assert nb_1w >= 200, f"{code} n'a que {nb_1w} barres 1w (< 200 attendues)"
        assert nb_1d >= 1000, f"{code} n'a que {nb_1d} barres 1d (< 1000 attendues)"


def test_les_cryptos_ont_des_fits_et_z_scores():
    """Chaque crypto doit posseder une droite de regression log-lineaire et un z-score valide."""
    as_of = fetch_one("select max(as_of_date) from regression_fits")[0]
    assert as_of is not None, "aucune regression en base"

    fits = fetch_all(
        """
        select i.internal_code, f.z_score, f.slope_annual, f.r_squared, f.fit_quality
          from regression_fits f
          join instruments i on i.id = f.instrument_id
         where i.internal_code = any(%s)
           and f.as_of_date = %s
        """,
        (list(CODES_CRYPTOS), as_of),
    )
    trouves = {r[0] for r in fits}
    assert trouves == CODES_CRYPTOS, f"fits manquants pour {CODES_CRYPTOS - trouves}"

    for code, z_score, slope_ann, r2, _quality in fits:
        assert z_score is not None, f"z_score None pour {code}"
        assert -10.0 <= z_score <= 10.0, f"z_score aberrant ({z_score}) pour {code}"
        assert slope_ann is not None, f"slope_annual None pour {code}"
        assert 0.0 <= r2 <= 1.0, f"r_squared aberrant ({r2}) pour {code}"


def test_les_cryptos_portent_leur_statut_hors_pea():
    """Les cryptomonnaies doivent explicitement declarer leur statut hors PEA."""
    rows = fetch_all(
        "select internal_code, attributes->>'pea_eligible', attributes->>'pea_motif' "
        "from instruments where internal_code = any(%s)",
        (list(CODES_CRYPTOS),),
    )
    for code, pea_eligible, motif in rows:
        assert pea_eligible == "false", f"{code} devrait etre hors PEA"
        assert motif and "pea" in motif.lower(), f"{code} devrait porter un motif explicite"
