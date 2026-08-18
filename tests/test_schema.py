"""Verification du socle L0 : le schema est en place et le referentiel peuple.

Ces tests touchent la vraie base (Supabase). Ils sont volontairement peu
nombreux : ils verifient les invariants dont depend tout le reste, pas le detail
du DDL.

    pytest tests/test_schema.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from market_intelligence.db import fetch_all, fetch_one  # noqa: E402

EXPECTED_TABLES = {
    # referentiel
    "regression_policies", "asset_classes", "currencies", "exchanges", "sectors",
    "data_sources", "financial_concepts", "concept_mappings",
    # instruments
    "instruments", "instrument_symbols", "index_memberships",
    # marche (raw)
    "bars", "bars_1d", "bars_1w", "bars_1mo", "corporate_actions",
    "shares_outstanding", "fx_rates", "adjustment_factors",
    # fondamentaux (raw)
    "financial_reports", "financial_facts",
    # derive
    "regression_fits", "peer_groups", "peer_group_members", "quality_scores",
    "moat_assessments", "screener_snapshots",
    # exploitation
    "data_quality_issues", "ingestion_runs", "positions", "keepalive",
    "schema_migrations",
}


def test_toutes_les_tables_existent():
    rows = fetch_all(
        "select table_name from information_schema.tables where table_schema = 'public'"
    )
    existing = {row[0] for row in rows}
    assert EXPECTED_TABLES <= existing, f"tables manquantes : {EXPECTED_TABLES - existing}"


@pytest.mark.parametrize(
    ("table", "minimum"),
    [
        ("regression_policies", 4),
        ("asset_classes", 7),
        ("currencies", 10),
        ("exchanges", 10),
        ("sectors", 11),
        ("data_sources", 6),
        ("financial_concepts", 30),
    ],
)
def test_referentiel_peuple(table, minimum):
    count = fetch_one(f"select count(*) from {table}")[0]  # noqa: S608 - parametres en dur
    assert count >= minimum


def test_bars_est_partitionnee_par_frequence():
    """Le partitionnement par freq est le chemin de scalabilite du doc 00 SS5."""
    rows = fetch_all(
        """
        select c.relname
          from pg_inherits i
          join pg_class c on c.oid = i.inhrelid
          join pg_class p on p.oid = i.inhparent
         where p.relname = 'bars'
        """
    )
    assert {r[0] for r in rows} == {"bars_1d", "bars_1w", "bars_1mo"}


def test_politique_par_defaut_resolue_pour_chaque_classe_dactif():
    """P6 : chaque classe d'actif pointe vers une politique existante."""
    orphans = fetch_all(
        """
        select a.code
          from asset_classes a
     left join regression_policies p on p.code = a.default_policy_code
         where a.default_policy_code is not null and p.code is null
        """
    )
    assert orphans == []


def test_crypto_et_fx_sont_hors_modele():
    """La crypto est exclue dans la donnee, pas dans un if enfoui (doc 01 SS2.1)."""
    rows = dict(
        fetch_all("select code, default_policy_code from asset_classes where code in ('crypto','fx')")
    )
    assert rows == {"crypto": "excluded", "fx": "excluded"}


def test_isin_unique():
    """P3 : l'ISIN est la cle metier, aucun doublon tolere."""
    dupes = fetch_all(
        "select isin, count(*) from instruments where isin is not null group by isin having count(*) > 1"
    )
    assert dupes == []


def test_keepalive_singleton():
    assert fetch_one("select count(*) from keepalive")[0] == 1
