"""Critères d'acceptation du portefeuille et du paper trading (doc 11).

Ce qui est éprouvé ici, dans l'ordre d'importance :

- une position sans thèse ne s'enregistre pas ;
- `fit_id` et `quality_score_id` sont figés à l'ouverture — c'est la seule chose
  qui justifie que ce portefeuille vive ici plutôt que dans un tableur ;
- le prix par défaut est la dernière clôture, et une saisie manuelle est marquée ;
- un titre non éligible à un support est refusé avec son motif ;
- le fictif ne se mélange jamais au réel.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from market_intelligence import portfolio as P  # noqa: E402
from market_intelligence.db import connect_direct, fetch_all, fetch_one  # noqa: E402

THESE = ("Sous -2 sigma depuis 46 semaines, le plus long episode observe sur ce "
         "titre. J'attends le retour vers la tendance, pas un rebond rapide.")


@pytest.fixture
def bac():
    """Un bac à sable annulé à la fin : aucun test ne laisse de position en base."""
    with connect_direct() as conn:
        cur = conn.cursor()
        cur.execute("select id from accounts where code = 'PAPER'")
        paper = cur.fetchone()[0]
        cur.execute("select id from instruments where internal_code = 'EQ:FR:SEB'")
        seb = cur.fetchone()[0]
        yield cur, paper, seb
        conn.rollback()


# --------------------------------------------------------------------------- #
# La thèse, seule friction imposée
# --------------------------------------------------------------------------- #
def test_une_position_sans_these_ne_senregistre_pas(bac):
    cur, paper, seb = bac
    with pytest.raises(ValueError, match="These trop courte"):
        P.ouvre(cur, seb, paper, 10, "", date.today())


def test_une_these_en_trois_mots_est_refusee(bac):
    """Une thèse vide ou en trois mots ne remplit pas sa fonction : la relire
    dans deux ans est le seul antidote fiable au biais rétrospectif."""
    cur, paper, seb = bac
    with pytest.raises(ValueError):
        P.ouvre(cur, seb, paper, 10, "elle est decotee", date.today())


def test_la_contrainte_de_these_est_aussi_en_base():
    """En code seulement, elle se contourne par un insert direct."""
    contraintes = fetch_all(
        "select conname from pg_constraint where conrelid = 'positions'::regclass "
        "and conname = 'position_thesis_required'")
    assert contraintes, "la contrainte doit exister en base, pas seulement en Python"


def test_une_quantite_nulle_est_refusee(bac):
    cur, paper, seb = bac
    with pytest.raises(ValueError, match="quantite"):
        P.ouvre(cur, seb, paper, 0, THESE, date.today())


# --------------------------------------------------------------------------- #
# Le signal est figé à l'ouverture
# --------------------------------------------------------------------------- #
def test_le_signal_du_jour_est_fige_a_louverture(bac):
    """**C'est la seule chose qui justifie que ce portefeuille vive ici plutôt
    que dans un tableur.** Trois ans plus tard on relit la ligne d'origine, pas
    une reconstitution."""
    cur, paper, seb = bac
    position_id, _ = P.ouvre(cur, seb, paper, 10, THESE, date.today())

    cur.execute("select fit_id, quality_score_id, z_at_entry from positions "
                "where id = %s", (position_id,))
    fit_id, quality_id, z_entree = cur.fetchone()
    assert fit_id is not None, "aucun fit rattaché : la position perd son signal"
    assert z_entree is not None

    cur.execute("select z_score from regression_fits where id = %s", (fit_id,))
    assert cur.fetchone()[0] == pytest.approx(z_entree)


def test_la_position_reprend_le_suivi_de_watchlist_sil_existe(bac):
    """Depuis combien de temps on regardait ce titre avant d'acheter est une
    information sur la discipline."""
    from market_intelligence import watchlist as W

    cur, paper, seb = bac
    W.ajoute(cur, seb, "je surveille")
    position_id, _ = P.ouvre(cur, seb, paper, 10, THESE, date.today())
    cur.execute("select watchlist_id from positions where id = %s", (position_id,))
    assert cur.fetchone()[0] is not None


# --------------------------------------------------------------------------- #
# Le prix d'exécution
# --------------------------------------------------------------------------- #
def test_le_prix_par_defaut_est_la_derniere_cloture(bac):
    """Saisir soi-même le prix d'entrée ouvre la porte au choix d'un bon point
    après coup — précisément le biais que le projet combat sur le prix."""
    cur, paper, seb = bac
    _ts, cours, _f = P.dernier_cours(cur, seb, date.today())
    position_id, source = P.ouvre(cur, seb, paper, 10, THESE, date.today())

    assert source == "close"
    cur.execute("select avg_price, price_source from positions where id = %s",
                (position_id,))
    prix, marque = cur.fetchone()
    assert float(prix) == pytest.approx(float(cours))
    assert marque == "close"


def test_un_prix_saisi_est_marque_comme_tel(bac):
    """L'agrégat doit pouvoir distinguer les deux."""
    cur, paper, seb = bac
    position_id, source = P.ouvre(cur, seb, paper, 10, THESE, date.today(),
                                  prix=42.0)
    assert source == "manual"
    cur.execute("select price_source from positions where id = %s", (position_id,))
    assert cur.fetchone()[0] == "manual"


def test_chaque_mouvement_porte_sa_source_de_prix(bac):
    cur, paper, seb = bac
    position_id, _ = P.ouvre(cur, seb, paper, 10, THESE, date.today())
    P.renforce(cur, position_id, 5, date.today(), prix=50.0)
    cur.execute("select price_source from transactions where position_id = %s "
                "order by id", (position_id,))
    assert [r[0] for r in cur.fetchall()] == ["close", "manual"]


# --------------------------------------------------------------------------- #
# Prix de revient
# --------------------------------------------------------------------------- #
def test_le_prix_de_revient_est_une_moyenne_ponderee_hors_frais(bac):
    """Les frais sont portes a part, pas noyes dans le PRU.

    Choix du doc 11 : a part, ils restent lisibles et leur poids se voit. Noyes
    dans le PRU ils disparaissent — et sur de petites lignes ils expliquent
    parfois l'essentiel de l'ecart entre le rendement brut et le reel.

    Defaut trouve en testant : les frais d'ouverture etaient hors PRU mais ceux
    du renfort y entraient, ce qui rendait le PRU dependant de l'ordre des
    operations.
    """
    cur, paper, seb = bac
    position_id, _ = P.ouvre(cur, seb, paper, 10, THESE, date.today(),
                             prix=100.0, frais=5.0)
    P.renforce(cur, position_id, 10, date.today(), prix=50.0, frais=5.0)

    cur.execute("select quantity, avg_price, fees from positions where id = %s",
                (position_id,))
    quantite, pru, frais = cur.fetchone()
    assert float(quantite) == 20
    assert float(pru) == pytest.approx(75.0), "(10*100 + 10*50) / 20, hors frais"
    assert float(frais) == pytest.approx(10.0), "les frais sont cumules a part"


def test_les_frais_entrent_dans_le_montant_investi(bac):
    """Hors du PRU, mais bien payes : ils doivent peser sur la performance."""
    cur, paper, seb = bac
    position_id, _ = P.ouvre(cur, seb, paper, 10, THESE, date.today(),
                             prix=100.0, frais=5.0)
    cur.execute("""
        select id, instrument_id, quantity, avg_price, fees, opened_at,
               closed_at, closed_price, price_source
          from positions where id = %s""", (position_id,))
    position = dict(zip([c.name for c in cur.description], cur.fetchone()))
    v = P.valorise(cur, position, date.today())
    assert v.montant_investi == pytest.approx(1005.0)


def test_renforcer_une_position_fermee_est_refuse(bac):
    cur, paper, seb = bac
    position_id, _ = P.ouvre(cur, seb, paper, 10, THESE, date.today())
    P.ferme(cur, position_id, date.today(), "sortie", "indeterminable")
    with pytest.raises(ValueError):
        P.renforce(cur, position_id, 5, date.today())


# --------------------------------------------------------------------------- #
# Valorisation
# --------------------------------------------------------------------------- #
def test_le_rendement_total_differe_de_la_plus_value_simple(bac):
    """Le rendement total réinvestit les dividendes, via `factor_total` — déjà
    vérifié contre l'`Adj Close` de Yahoo, écart médian 0,036 %."""
    cur, paper, seb = bac
    jadis = date.today() - timedelta(days=730)
    position_id, _ = P.ouvre(cur, seb, paper, 10, THESE, jadis)

    cur.execute("""
        select id, instrument_id, quantity, avg_price, fees, opened_at,
               closed_at, closed_price, price_source
          from positions where id = %s""", (position_id,))
    position = dict(zip([c.name for c in cur.description], cur.fetchone()))
    v = P.valorise(cur, position, date.today())

    assert v.rendement_total_pct is not None
    assert v.rendement_total_pct > v.plus_value_pct, (
        "sur un titre qui verse un dividende, le rendement total doit dépasser "
        "la plus-value simple")
    assert v.annualise_pct is not None


def test_une_position_fermee_se_valorise_au_prix_de_sortie(bac):
    cur, paper, seb = bac
    position_id, _ = P.ouvre(cur, seb, paper, 10, THESE, date.today(), prix=100.0)
    P.ferme(cur, position_id, date.today(), "sortie", "verifiee", prix=120.0)

    cur.execute("""
        select id, instrument_id, quantity, avg_price, fees, opened_at,
               closed_at, closed_price, price_source
          from positions where id = %s""", (position_id,))
    position = dict(zip([c.name for c in cur.description], cur.fetchone()))
    v = P.valorise(cur, position, date.today())
    assert v.cours == pytest.approx(120.0)
    assert v.plus_value == pytest.approx(200.0)


# --------------------------------------------------------------------------- #
# Éligibilité par support
# --------------------------------------------------------------------------- #
def test_un_titre_hors_pays_eligibles_est_refuse():
    resultat = P.eligibilite("CH", ["FR", "DE", "NL"])
    assert not resultat.autorise
    assert "CH" in resultat.motif


def test_un_titre_eligible_passe():
    assert P.eligibilite("FR", ["FR", "DE", "NL"]).autorise


def test_un_support_sans_restriction_accepte_tout():
    assert P.eligibilite("US", None).autorise
    assert P.eligibilite("US", []).autorise


def test_un_pays_inconnu_est_refuse_quand_une_restriction_existe():
    """Ne pas savoir n'est pas une autorisation."""
    assert not P.eligibilite(None, ["FR"]).autorise


def test_la_casse_du_code_pays_est_indifferente():
    assert P.eligibilite("fr", ["FR", "DE"]).autorise


# --------------------------------------------------------------------------- #
# Fermeture et revue de thèse
# --------------------------------------------------------------------------- #
def test_les_trois_verdicts_sont_acceptes(bac):
    cur, paper, seb = bac
    for verdict in ("indeterminable", "verifiee", "infirmee"):
        position_id, _ = P.ouvre(cur, seb, paper, 1, THESE, date.today())
        P.ferme(cur, position_id, date.today(), "test", verdict)
        cur.execute("select thesis_verdict from positions where id = %s",
                    (position_id,))
        assert cur.fetchone()[0] == verdict


def test_un_verdict_inconnu_est_refuse(bac):
    cur, paper, seb = bac
    position_id, _ = P.ouvre(cur, seb, paper, 1, THESE, date.today())
    with pytest.raises(ValueError, match="verdict inconnu"):
        P.ferme(cur, position_id, date.today(), "test", "peut-etre")


def test_la_fermeture_enregistre_un_mouvement_de_vente(bac):
    cur, paper, seb = bac
    position_id, _ = P.ouvre(cur, seb, paper, 10, THESE, date.today(), prix=100.0)
    P.ferme(cur, position_id, date.today(), "sortie", "verifiee", prix=120.0)
    cur.execute("select kind, quantity, price, amount from transactions "
                "where position_id = %s and kind = 'sell'", (position_id,))
    kind, quantite, prix, montant = cur.fetchone()
    assert (kind, float(quantite), float(prix)) == ("sell", 10.0, 120.0)
    assert float(montant) == pytest.approx(1200.0)


# --------------------------------------------------------------------------- #
# Le fictif ne se mélange pas au réel
# --------------------------------------------------------------------------- #
def test_une_position_sur_un_support_paper_est_marquee_fictive(bac):
    cur, paper, seb = bac
    position_id, _ = P.ouvre(cur, seb, paper, 10, THESE, date.today())
    cur.execute("select is_paper from positions where id = %s", (position_id,))
    assert cur.fetchone()[0] is True


def test_le_support_paper_existe_et_est_marque():
    ligne = fetch_one("select kind, is_paper from accounts where code = 'PAPER'")
    assert ligne == ("PAPER", True)


def test_aucun_support_reel_nest_marque_fictif():
    """Les positions fictives vivent dans un support dédié, jamais dans un
    support réel."""
    fautifs = fetch_all(
        "select code from accounts where is_paper and kind <> 'PAPER'")
    assert fautifs == []


# --------------------------------------------------------------------------- #
# Versements
# --------------------------------------------------------------------------- #
def test_les_versements_cumulent_les_achats(bac):
    cur, paper, seb = bac
    avant = P.versements(cur, paper)
    P.ouvre(cur, seb, paper, 10, THESE, date.today(), prix=100.0, frais=5.0)
    assert P.versements(cur, paper) == pytest.approx(avant + 1005.0)
