"""Tests unitaires et invariants pour la classe `dividend_stock` (Actions à dividende)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from market_intelligence.db import fetch_all, fetch_one  # noqa: E402


def test_asset_class_dividend_stock_est_bien_declaree():
    row = fetch_one("select code, label, supports_fundamentals, default_policy_code from asset_classes where code = 'dividend_stock'")
    assert row is not None
    assert row[1] == "Action à dividende"
    assert row[2] is True
    assert row[3] == "loglin_20y"


def test_les_actions_a_dividende_ont_des_cotations_et_fits():
    total = fetch_one("select count(*) from instruments where asset_class = 'dividend_stock' and is_active")[0]
    assert total >= 20, f"Au moins 20 champions du dividende attendus, trouvé {total}"

    fits = fetch_one(
        """
        select count(*)
          from regression_fits f
          join instruments i on i.id = f.instrument_id
         where i.asset_class = 'dividend_stock'
           and f.as_of_date = (select max(as_of_date) from regression_fits)
        """
    )[0]
    assert fits == total, f"{total - fits} action(s) à dividende sans fit"


def test_les_actions_a_dividende_ont_un_historique_de_cash_dividends():
    sans_div = fetch_all(
        """
        select i.internal_code, i.name
          from instruments i
     left join corporate_actions c on c.instrument_id = i.id and c.action_type = 'cash_dividend'
         where i.asset_class = 'dividend_stock'
         group by i.internal_code, i.name
        having count(c.id) = 0
        """
    )
    assert sans_div == [], f"Actions à dividende sans aucun versement en base : {sans_div}"


def test_les_foncieres_siic_sont_exclues_du_scope():
    """Gecina, Covivio et Altarea SCA ne rejoignent pas `dividend_stock` : leur
    statut SIIC (exoneration d'IS sur les revenus locatifs) est incompatible
    avec le PEA depuis la loi de finances 2012 (art. 8, loi n°2011-1977 du
    28/12/2011), et cette classe n'accueille que des titres eligibles - un
    titre non eligible sort du scope, il n'y reste pas avec un simple drapeau.
    Leur `pea_eligible=false` (verifie par ailleurs, cf. test_universe.py) doit
    neanmoins survivre au retour vers `equity` : c'est ce champ que le garde-fou
    d'achat du portefeuille lit pour refuser un ordre PEA.
    """
    hors_scope = fetch_all(
        "select internal_code, asset_class from instruments "
        "where internal_code = any(%s)",
        (["EQ:FR:GECINA", "EQ:FR:COVIVIO", "EQ:FR:ALTAREASCA"],),
    )
    for code, asset_class in hors_scope:
        assert asset_class != "dividend_stock", f"{code} (SIIC) ne devrait plus etre dans dividend_stock"


def test_les_jobs_de_fondamentaux_traitent_les_actions_a_dividende():
    """`supports_fundamentals = true` pour les actions à dividende."""
    from market_intelligence.jobs import compute_quality, ingest_fundamentals

    source_id = fetch_one("select id from data_sources where code = 'yfinance'")[0]

    codes_ingest = [r[1] for r in fetch_all(ingest_fundamentals.INSTRUMENTS, {"source_id": source_id})]
    assert any(c in codes_ingest for c in ["EQ:FR:TTE", "EQ:FR:SAN", "EQ:FR:AI"])

    codes_qual = [r[1] for r in fetch_all(compute_quality.INSTRUMENTS)]
    assert any(c in codes_qual for c in ["EQ:FR:TTE", "EQ:FR:SAN", "EQ:FR:AI"])
