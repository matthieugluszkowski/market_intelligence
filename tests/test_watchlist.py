"""Critères d'acceptation de la watchlist (doc 10 §5).

    - un titre ajouté deux fois ne crée pas de doublon ;
    - un titre retiré puis repris crée une seconde ligne, et l'historique montre
      les deux périodes ;
    - `z_at_add` reflète le z-score du dernier calcul disponible à l'ajout, et ne
      bouge plus ;
    - le retrait n'efface aucune ligne.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from market_intelligence import watchlist as W  # noqa: E402
from market_intelligence.db import connect_direct, fetch_all, fetch_one  # noqa: E402

CODE_TEST = "EQ:FR:CARREFOUR"


@pytest.fixture
def instrument():
    """Un titre neutre, nettoyé avant et après pour ne rien laisser traîner."""
    identifiant = fetch_one(
        "select id from instruments where internal_code = %s", (CODE_TEST,))[0]
    with connect_direct() as conn, conn.cursor() as cur:
        cur.execute("delete from watchlist where instrument_id = %s", (identifiant,))
        conn.commit()
    yield identifiant
    with connect_direct() as conn, conn.cursor() as cur:
        cur.execute("delete from watchlist where instrument_id = %s", (identifiant,))
        conn.commit()


def test_ajouter_puis_lire(instrument):
    with connect_direct() as conn, conn.cursor() as cur:
        assert W.ajoute(cur, instrument, "je surveille le retournement") is not None
        conn.commit()
        suivi = W.est_suivi(cur, instrument)
    assert suivi is not None
    assert suivi.note == "je surveille le retournement"


def test_un_titre_ajoute_deux_fois_ne_cree_pas_de_doublon(instrument):
    with connect_direct() as conn, conn.cursor() as cur:
        W.ajoute(cur, instrument, "premier")
        second = W.ajoute(cur, instrument, "second")
        conn.commit()
    assert second is None, "le second ajout doit être sans effet"
    assert fetch_one(
        "select count(*) from watchlist where instrument_id = %s and removed_at is null",
        (instrument,))[0] == 1


def test_letat_du_titre_est_fige_a_lajout(instrument):
    """Sans `z_at_add`, on ne peut plus dire trois mois plus tard si le titre a
    baissé depuis qu'on le suit ou s'il était déjà bas — et c'est exactement la
    question qu'on se pose en rouvrant sa liste."""
    attendu = fetch_one(
        """
        select f.z_score, f.fit_quality from regression_fits f
          join instruments i on i.id = f.instrument_id
         where i.internal_code = %s order by f.as_of_date desc limit 1
        """, (CODE_TEST,))

    with connect_direct() as conn, conn.cursor() as cur:
        W.ajoute(cur, instrument, "note")
        conn.commit()
        suivi = W.est_suivi(cur, instrument)

    assert suivi.z_at_add == pytest.approx(attendu[0])
    assert suivi.fit_at_add == attendu[1]


def test_le_retrait_nefface_pas_la_ligne(instrument):
    """Savoir qu'on a suivi un titre puis qu'on l'a retiré est une information ;
    l'effacer laisserait croire qu'on ne l'a jamais regardé."""
    with connect_direct() as conn, conn.cursor() as cur:
        W.ajoute(cur, instrument, "note d'origine")
        conn.commit()
        assert W.retire(cur, instrument, "thèse invalidée") is True
        conn.commit()
        assert W.est_suivi(cur, instrument) is None

    ligne = fetch_one(
        "select note, removal_reason, removed_at is not null from watchlist "
        "where instrument_id = %s", (instrument,))
    assert ligne is not None, "la ligne a été supprimée au lieu d'être horodatée"
    assert ligne[0] == "note d'origine"
    assert ligne[1] == "thèse invalidée"
    assert ligne[2] is True


def test_un_titre_repris_apres_retrait_cree_une_seconde_ligne(instrument):
    """C'est une reprise, et elle doit se voir."""
    with connect_direct() as conn, conn.cursor() as cur:
        W.ajoute(cur, instrument, "première période")
        conn.commit()
        W.retire(cur, instrument, "sorti des critères")
        conn.commit()
        assert W.ajoute(cur, instrument, "seconde période") is not None
        conn.commit()

    lignes = fetch_all(
        "select note, removed_at from watchlist where instrument_id = %s "
        "order by added_at", (instrument,))
    assert len(lignes) == 2
    assert lignes[0][1] is not None, "la première période est close"
    assert lignes[1][1] is None, "la seconde est ouverte"


def test_retirer_un_titre_non_suivi_est_sans_effet(instrument):
    with connect_direct() as conn, conn.cursor() as cur:
        assert W.retire(cur, instrument, "raison") is False


def test_la_bascule_alterne(instrument):
    with connect_direct() as conn, conn.cursor() as cur:
        assert W.bascule(cur, instrument, "note") is True
        conn.commit()
        assert W.bascule(cur, instrument) is False
        conn.commit()
        assert W.est_suivi(cur, instrument) is None


def test_une_note_vide_est_stockee_a_null(instrument):
    with connect_direct() as conn, conn.cursor() as cur:
        W.ajoute(cur, instrument, "   ")
        conn.commit()
        assert W.est_suivi(cur, instrument).note is None


def test_les_codes_suivis_ne_contiennent_que_les_actifs(instrument):
    with connect_direct() as conn, conn.cursor() as cur:
        W.ajoute(cur, instrument, "note")
        conn.commit()
        assert CODE_TEST in W.codes_suivis(cur)
        W.retire(cur, instrument)
        conn.commit()
        assert CODE_TEST not in W.codes_suivis(cur)


def test_la_liste_expose_la_derive(instrument):
    """La colonne qu'on vient regarder."""
    with connect_direct() as conn, conn.cursor() as cur:
        W.ajoute(cur, instrument, "note")
        conn.commit()

    lignes = fetch_all(W.LISTE)
    notre = [r for r in lignes if r[1] == CODE_TEST]
    assert notre, "le titre suivi n'apparaît pas dans la liste"
    _, _, _, _, _, z_ajout, z_actuel, derive, *_ = notre[0]
    assert derive == pytest.approx(z_actuel - z_ajout)


def test_un_titre_supprime_emporte_son_suivi():
    """`on delete cascade` : une watchlist qui pointerait un instrument disparu
    afficherait une ligne vide sans qu'on sache pourquoi."""
    contrainte = fetch_one(
        """
        select rc.delete_rule
          from information_schema.referential_constraints rc
          join information_schema.table_constraints tc
            on tc.constraint_name = rc.constraint_name
         where tc.table_name = 'watchlist'
        """
    )
    assert contrainte is not None
    assert contrainte[0] == "CASCADE"


def test_lindex_unique_ne_porte_que_sur_les_lignes_actives():
    """Sinon un titre retiré ne pourrait jamais être repris."""
    definition = fetch_one(
        "select indexdef from pg_indexes where indexname = 'watchlist_active_unique'")
    assert definition is not None
    assert "removed_at IS NULL" in definition[0]
