"""Le cycle d'actualisation, et les deux silences qu'il faut rendre impossibles
(lot L7, doc 02 SS4.4).

Un orchestrateur ne casse pas bruyamment : il derive. Les deux derives que ces
tests interdisent sont exactement celles qu'on ne verrait pas a l'ecran :

- une etape dont le nom ne correspond plus au `job_name` ecrit dans
  `ingestion_runs`. La lecture de cadence ne trouve alors jamais rien, l'etape
  est relancee a chaque passage, et les 7 minutes de debit menage vers yfinance
  sont payees trois fois par jour pour des comptes qui changent quatre fois par
  an. Rien ne le signale.
- un retour de `compute_fits` a `on conflict do nothing`. Les 2e et 3e passages
  du jour calculeraient alors deux minutes pour n'ecrire rien, et le screener
  afficherait des z-scores du matin en les datant de l'apres-midi.
"""

from __future__ import annotations

import inspect
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from market_intelligence.jobs import cycle  # noqa: E402
from market_intelligence.jobs.compute_fits import INSERT_FIT  # noqa: E402

MAINTENANT = datetime(2026, 8, 21, 8, 0, tzinfo=timezone.utc)


def etape(nom="etape_test", intervalle=cycle.TOUJOURS, depend_de=()):
    return cycle.Etape(nom, lambda: {}, intervalle, "role de test", depend_de)


# --------------------------------------------------------------------------- #
# Cadence
# --------------------------------------------------------------------------- #

def test_une_etape_sans_intervalle_tourne_a_chaque_passage():
    tourne, motif = cycle.doit_tourner(
        etape(), MAINTENANT - timedelta(minutes=1), MAINTENANT)
    assert tourne and motif == ""


def test_une_etape_encore_fraiche_est_sautee():
    tourne, motif = cycle.doit_tourner(
        etape(intervalle=cycle.JOUR), MAINTENANT - timedelta(hours=8), MAINTENANT)
    assert not tourne
    # Le motif finit dans le log du cron : il doit se lire sans ouvrir le code.
    assert "8 h" in motif and "24 h" in motif


def test_une_etape_vieillie_tourne():
    tourne, _ = cycle.doit_tourner(
        etape(intervalle=cycle.JOUR), MAINTENANT - timedelta(hours=25), MAINTENANT)
    assert tourne


def test_une_etape_jamais_lancee_tourne():
    tourne, _ = cycle.doit_tourner(etape(intervalle=30 * cycle.JOUR), None, MAINTENANT)
    assert tourne


def test_force_ignore_la_cadence():
    tourne, _ = cycle.doit_tourner(
        etape(intervalle=30 * cycle.JOUR), MAINTENANT - timedelta(hours=1),
        MAINTENANT, force=True)
    assert tourne


def test_une_dependance_en_echec_saute_l_etape():
    """Ne pas historiser un fit du jour sur des cours qu'on n'a pas pu rafraichir.

    C'est la seule serie que le projet ne rejouera jamais (principe P5) : une
    observation fausse y reste fausse pour toujours.
    """
    tourne, motif = cycle.doit_tourner(
        etape(depend_de=("backfill_prices",)), None, MAINTENANT,
        echouees=frozenset({"backfill_prices"}))
    assert not tourne
    assert "backfill_prices" in motif


def test_la_dependance_ne_bloque_que_si_elle_a_echoue():
    tourne, _ = cycle.doit_tourner(
        etape(depend_de=("backfill_prices",)), None, MAINTENANT,
        echouees=frozenset({"ingest_fundamentals"}))
    assert tourne


@pytest.mark.parametrize("delta,attendu", [
    (timedelta(minutes=12), "12 min"),
    (timedelta(hours=8), "8 h"),
    (timedelta(days=3), "3 j"),
])
def test_age_en_clair(delta, attendu):
    assert cycle.age_en_clair(delta) == attendu


# --------------------------------------------------------------------------- #
# Les deux invariants silencieux
# --------------------------------------------------------------------------- #

def test_chaque_etape_porte_le_job_name_qu_elle_journalise():
    """`Etape.nom` sert de cle de lecture dans `ingestion_runs`.

    Renommer un job sans renommer l'etape ne casse rien visiblement : la cadence
    devient simplement inoperante, et chaque passage relance tout.
    """
    for e in cycle.ETAPES:
        module = sys.modules[cycle.__name__.rsplit(".", 1)[0] + "." + e.nom]
        source = inspect.getsource(module)
        assert f'ingestion_run(conn, source_id, "{e.nom}")' in source, (
            f"l'etape {e.nom} ne correspond a aucun job_name journalise"
        )


def test_l_ecriture_des_fits_remplace_la_ligne_du_jour():
    sql = " ".join(INSERT_FIT.split()).lower()
    assert "on conflict (instrument_id, policy_code, as_of_date, method_version)" in sql
    assert "do update set" in sql, (
        "un retour a `do nothing` rendrait muets les 2e et 3e passages du jour"
    )
    assert "computed_at = now()" in sql


def test_le_cycle_recalcule_les_fits_a_chaque_passage():
    """L'arbitrage retenu : cours et regressions toutes les 8 heures."""
    fits = next(e for e in cycle.ETAPES if e.nom == "compute_fits")
    assert fits.intervalle == cycle.TOUJOURS
    assert "backfill_prices" in fits.depend_de


def test_les_sources_lentes_ne_sont_pas_relancees_a_chaque_passage():
    """7 minutes de debit vers yfinance, pour des comptes publies 4 fois par an."""
    cadences = {e.nom: e.intervalle for e in cycle.ETAPES}
    assert cadences["ingest_fundamentals"] >= 28 * cycle.JOUR
    assert cadences["ingest_corporate_actions"] >= cycle.JOUR


def test_la_jambe_qualite_suit_les_fondamentaux():
    """Ingerer des comptes sans recalculer ce qui en depend classerait les titres
    sur des comptes que la base a deja remplaces."""
    qualite = next(e for e in cycle.ETAPES if e.nom == "compute_quality")
    fondamentaux = next(e for e in cycle.ETAPES if e.nom == "ingest_fundamentals")
    assert "ingest_fundamentals" in qualite.depend_de
    assert qualite.intervalle <= fondamentaux.intervalle
    # L'ordre de declaration vaut ordre d'execution : la qualite se calcule apres.
    noms = [e.nom for e in cycle.ETAPES]
    assert noms.index("compute_quality") > noms.index("ingest_fundamentals")
