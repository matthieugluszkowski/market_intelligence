"""Criteres d'acceptation du lot L2 (05_roadmap-et-lot.md).

    « >= 95% des titres ont >= 15 ans d'historique hebdomadaire ; le job relance
      deux fois de suite produit un etat identique ; l'archive Parquet est
      relisible. »
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from market_intelligence.config import get_settings  # noqa: E402
from market_intelligence.db import fetch_all, fetch_one  # noqa: E402
from market_intelligence.normalizers.bars import normalize  # noqa: E402

COUVERTURE_MIN = 0.95
ANNEES_MIN = 15


# --------------------------------------------------------------------------- #
# Normalisation : hors reseau, hors base
# --------------------------------------------------------------------------- #
@pytest.fixture
def frame():
    import pandas as pd

    return pd.DataFrame(
        {
            "Open": [10.0, 11.0, float("nan"), 13.0, 14.0],
            "High": [10.5, 11.5, 12.5, 12.0, 14.5],   # ligne 4 : high < low
            "Low": [9.5, 10.5, 11.5, 13.5, 13.5],
            "Close": [10.2, float("nan"), 12.2, 13.2, -1.0],
            "Volume": [1000, 2000, 3000, 4000, 5000],
        },
        index=pd.to_datetime(["2024-01-01", "2024-01-08", "2024-01-15",
                              "2024-01-22", "2024-01-29"]),
    )


def test_normalisation_ecarte_les_clotures_inexploitables(frame):
    out = normalize(frame, instrument_id=1, freq="1w", source_id=5)
    assert len(out.rows) == 3
    motifs = {r["reason"] for r in out.rejected}
    assert "close_absent" in motifs
    assert "close_non_positif" in motifs


def test_normalisation_conserve_la_barre_aux_extremes_incoherents(frame):
    """La cloture reste exploitable : c'est la seule valeur dont depend la regression."""
    out = normalize(frame, instrument_id=1, freq="1w", source_id=5)
    incoherentes = [r for r in out.rejected if r["reason"] == "extremes_incoherents"]
    assert len(incoherentes) == 1
    assert incoherentes[0]["conserve"] is True
    assert date(2024, 1, 22) in [r["ts"] for r in out.rows]


def test_normalisation_ne_leve_pas_sur_entree_vide():
    assert len(normalize(None, 1, "1w", 5).rows) == 0


# --------------------------------------------------------------------------- #
# Etat de la base apres backfill
# --------------------------------------------------------------------------- #
# Introductions en bourse posterieures a 2010, dont l'historique est court parce
# que la societe est jeune et non parce que l'ingestion a echoue. Liste close et
# nominative : un quatrieme titre a historique court fait echouer le test, ce qui
# est exactement le comportement recherche.
COTATIONS_RECENTES = {
    "EQ:NL:PROSUS": 2019,   # scission de Naspers
    "EQ:IT:FERRARI": 2015,  # scission de FCA
    "EQ:ES:AENA": 2015,     # privatisation partielle
}


def test_couverture_historique_hebdomadaire():
    """Le critere du doc 05 vise >= 95% de l'univers a >= 15 ans d'hebdomadaire.

    Il existe pour attraper une ingestion defaillante ou un mapping faux, pas
    pour constater qu'une societe est jeune : aucun provider ne fabriquera vingt
    ans de cotations a Ferrari, introduite en 2015. L'assertion porte donc sur
    l'univers dont l'historique long est *possible*, et la liste des exceptions
    est nominative pour qu'un nouveau titre court ne passe pas inapercu.
    """
    courts = fetch_all(
        """
        select i.internal_code, round((max(b.ts) - min(b.ts)) / 365.25, 1)
          from bars b join instruments i on i.id = b.instrument_id
         where b.freq = '1w'
         group by i.internal_code
        having (max(b.ts) - min(b.ts)) / 365.25 < %s
         order by 1
        """,
        (ANNEES_MIN,),
    )
    inattendus = [c for c, _ in courts if c not in COTATIONS_RECENTES]
    assert inattendus == [], (
        f"historique court sans introduction recente connue : {inattendus}. "
        f"Soit le mapping est faux, soit l'ingestion a echoue."
    )

    total = fetch_one("select count(*) from instruments where is_active")[0]
    eligibles = total - len(COTATIONS_RECENTES)
    couverts = eligibles - len(inattendus)
    ratio = couverts / eligibles
    assert ratio >= COUVERTURE_MIN, f"couverture {ratio:.1%} ({couverts}/{eligibles})"


def test_toutes_les_barres_ont_une_cloture_positive():
    assert fetch_one("select count(*) from bars where close <= 0")[0] == 0


def test_aucune_barre_dans_le_futur():
    assert fetch_one("select count(*) from bars where ts > current_date")[0] == 0


def test_les_barres_hebdomadaires_sont_bien_hebdomadaires():
    """Un pas median trop eloigne de 7 jours signale une confusion de frequence."""
    ecarts = fetch_all(
        """
        select instrument_id, percentile_cont(0.5) within group (order by d) as pas_median
          from (
            select instrument_id, ts - lag(ts) over (partition by instrument_id order by ts) as d
              from bars where freq = '1w'
          ) t
         where d is not null
         group by instrument_id
        having percentile_cont(0.5) within group (order by d) not between 6 and 8
        """
    )
    assert ecarts == [], f"pas median anormal : {ecarts}"


def test_le_journal_dingestion_est_alimente():
    dernier = fetch_one(
        "select status, rows_inserted from ingestion_runs "
        "where job_name = 'backfill_prices' order by started_at desc limit 1"
    )
    assert dernier is not None, "aucun run journalise"
    assert dernier[0] in ("success", "partial")


# --------------------------------------------------------------------------- #
# Archive froide
# --------------------------------------------------------------------------- #
def test_larchive_parquet_est_relisible():
    import pandas as pd

    racine = Path(get_settings().cold_storage_path) / "freq=1w"
    if not racine.exists():
        pytest.skip("archive non exportee : lancer scripts/export_cold.py")

    fichiers = sorted(racine.glob("*.parquet"))
    assert fichiers, "aucun fichier Parquet"

    frame = pd.read_parquet(fichiers[0])
    assert {"ts", "close"} <= set(frame.columns)
    assert len(frame) > 0
    assert (frame["close"] > 0).all()
