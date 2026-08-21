"""Criteres d'acceptation du lot L5 (05_roadmap-et-lot.md, doc 04).

    « le graphe d'un titre est superposable a celui de Hiboo pour le meme titre,
      aux conventions d'ajustement pres. »

Ce critere-la ne peut pas etre automatise ici : Hiboo est un service sur
abonnement, et declarer une superposition sans l'avoir constatee serait
exactement la validation fictive que ce projet cherche a eviter.
`scripts/export_comparaison.py` produit la piece a conviction ; la confrontation
reste a faire.

Ce qui **est** verifiable automatiquement, et qui conditionne la validite de
cette comparaison, l'est ici : que le graphe montre exactement ce que le screener
a classe, que l'axe soit logarithmique, que les bandes soient des zones de
reference et non des series, et que chaque graphe ait son jumeau tabulaire.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from dashboard import charts  # noqa: E402
from dashboard.theme import (  # noqa: E402
    CLAIR, MOTIFS, SOMBRE, motif_en_clair, palette, statut,
)
from market_intelligence.db import connect  # noqa: E402


def _frame(sql: str, params: dict | None = None) -> pd.DataFrame:
    with connect() as conn, conn.cursor() as cur:
        cur.execute(sql, params or {})
        return pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])


@pytest.fixture(scope="module")
def fit_et_barres():
    fit = _frame(
        """
        select f.*, i.name, i.currency from regression_fits f
          join instruments i on i.id = f.instrument_id
         where i.internal_code = 'EQ:FR:SEB'
         order by f.as_of_date desc limit 1
        """
    )
    if fit.empty:
        pytest.skip("aucun fit en base")
    barres = _frame(
        """
        select b.ts, b.close * coalesce(a.factor_price, 1.0) as close,
               b.close as close_brut
          from bars b join instruments i on i.id = b.instrument_id
          left join adjustment_factors a
            on a.instrument_id = b.instrument_id and a.ts = b.ts
         where i.internal_code = 'EQ:FR:SEB' and b.freq = '1w'
         order by b.ts
        """
    )
    return fit.iloc[0], barres


# --------------------------------------------------------------------------- #
# Le graphe montre ce que le screener a classe
# --------------------------------------------------------------------------- #
def test_le_z_du_graphe_est_celui_qui_a_ete_stocke(fit_et_barres):
    """Le point le plus important de cet ecran.

    La droite affichee est reconstruite depuis `intercept` et `slope_annual`
    tels qu'ecrits en base, jamais re-estimee. Si on la recalculait a
    l'affichage, le graphe pourrait diverger de ce que le screener a classe sans
    que rien ne le signale - et c'est le graphe qu'on regarde pour decider.
    """
    fit, barres = fit_et_barres
    serie = charts.serie_de_regression(barres, fit)
    assert serie["z"].iloc[-1] == pytest.approx(float(fit["z_score"]), abs=1e-9)


def test_la_fenetre_du_graphe_est_celle_du_fit(fit_et_barres):
    fit, barres = fit_et_barres
    serie = charts.serie_de_regression(barres, fit)
    assert serie["ts"].min() >= fit["window_start"]
    assert serie["ts"].max() <= fit["window_end"]
    assert len(serie) == fit["n_obs"]


def test_les_bandes_encadrent_la_tendance(fit_et_barres):
    fit, barres = fit_et_barres
    serie = charts.serie_de_regression(barres, fit)
    assert (serie["bande_basse_2"] < serie["bande_basse_1"]).all()
    assert (serie["bande_basse_1"] < serie["tendance"]).all()
    assert (serie["tendance"] < serie["bande_haute_1"]).all()
    assert (serie["bande_haute_1"] < serie["bande_haute_2"]).all()


def test_les_episodes_du_graphe_concordent_avec_les_statistiques_stockees(fit_et_barres):
    """Deux calculs independants du meme fait doivent tomber d'accord."""
    fit, barres = fit_et_barres
    serie = charts.serie_de_regression(barres, fit)
    episodes = charts.episodes_sous_seuil(serie)
    assert len(episodes) == fit["regime_stats"]["n_episodes"]


# --------------------------------------------------------------------------- #
# Specifications de forme (doc 04 SS3, bloc A)
# --------------------------------------------------------------------------- #
def test_laxe_des_ordonnees_est_logarithmique(fit_et_barres):
    """Le modele est lineaire en log ; un axe lineaire courberait la droite et
    rendrait le graphe faux a l'oeil."""
    fit, barres = fit_et_barres
    serie = charts.serie_de_regression(barres, fit)
    spec = charts.graphe_regression(serie, palette(False), "EUR").to_dict()
    echelles = [
        couche["encoding"]["y"].get("scale", {}).get("type")
        for couche in spec["layer"] if "y" in couche.get("encoding", {})
    ]
    assert echelles, "aucun encodage y trouve"
    assert all(t == "log" for t in echelles), f"echelles non logarithmiques : {echelles}"


def test_il_ny_a_quun_seul_axe_des_ordonnees(fit_et_barres):
    """Jamais de second axe pour le volume : c'est l'erreur de graphique la plus
    frequente et elle invente des correlations."""
    fit, barres = fit_et_barres
    serie = charts.serie_de_regression(barres, fit)
    spec = charts.graphe_regression(serie, palette(False), "EUR").to_dict()
    titres = {
        couche["encoding"]["y"].get("title")
        for couche in spec["layer"] if "y" in couche.get("encoding", {})
    }
    nommes = [t for t in titres if isinstance(t, str)]
    assert len(nommes) <= 1, f"plusieurs axes y nommes : {nommes}"


def test_les_bandes_ne_sont_pas_une_teinte_de_la_palette_de_series(fit_et_barres):
    """Les bandes sont des zones de reference : gris neutres. Une teinte de serie
    les ferait lire comme une quatrieme donnee."""
    fit, barres = fit_et_barres
    serie = charts.serie_de_regression(barres, fit)
    p = palette(False)
    spec = charts.graphe_regression(serie, p, "EUR").to_dict()
    aires = [c for c in spec["layer"] if c.get("mark", {}).get("type") == "area"]
    assert aires, "aucune bande tracee"
    couleurs_de_series = {p.serie_cours, p.serie_pair, p.serie_secteur}
    for aire in aires:
        assert aire["mark"]["color"] not in couleurs_de_series


def test_aucun_filet_nest_pointille(fit_et_barres):
    """Filets pleins, jamais pointilles - y compris pour les bornes de bandes."""
    fit, barres = fit_et_barres
    serie = charts.serie_de_regression(barres, fit)
    spec = charts.graphe_regression(serie, palette(False), "EUR").to_dict()
    for couche in spec["layer"]:
        for axe in ("x", "y"):
            dash = couche.get("encoding", {}).get(axe, {}).get("axis", {})
            if isinstance(dash, dict):
                assert not dash.get("gridDash"), "grille en pointilles"


def test_le_graphe_a_son_jumeau_tabulaire(fit_et_barres):
    """Principe I3 : exigence d'accessibilite, et seule facon de verifier qu'un
    graphe ne ment pas."""
    fit, barres = fit_et_barres
    serie = charts.serie_de_regression(barres, fit)
    table = charts.jumeau_tabulaire(serie)
    assert len(table) == len(serie)
    assert "z-score" in table.columns
    assert "Cours brut" in table.columns, "le cours non ajuste doit rester consultable"


# --------------------------------------------------------------------------- #
# Systeme visuel
# --------------------------------------------------------------------------- #
def test_le_mode_sombre_nest_pas_une_inversion_du_mode_clair():
    """C'est un jeu de valeurs choisi pour la surface sombre : une inversion
    produit des bleus qui vibrent et des gris qui disparaissent."""
    assert SOMBRE.serie_cours != CLAIR.serie_cours
    assert SOMBRE.serie_pair != CLAIR.serie_pair
    assert SOMBRE.grille != CLAIR.grille


@pytest.mark.parametrize("qualite", ["good", "weak", "rejected"])
def test_chaque_statut_porte_une_icone_et_un_libelle(qualite):
    """La couleur ne porte jamais seule l'information : deux des trois statuts
    passent sous 3:1 sur surface claire, et un daltonien doit pouvoir lire le
    tableau."""
    couleur, icone, libelle = statut(qualite)
    assert couleur.startswith("#")
    assert icone and icone not in ("", " ")
    assert len(libelle) > 5


def test_le_point_neutre_du_z_score_est_gris():
    """Il doit se lire comme « rien ». Une teinte lui donnerait un sens."""
    for p in (CLAIR, SOMBRE):
        r, v, b = (int(p.z_neutre[i:i + 2], 16) for i in (1, 3, 5))
        assert max(r, v, b) - min(r, v, b) < 20, "le point neutre porte une teinte"


def test_les_poles_du_z_score_sont_chaud_et_froid():
    """Ils doivent se lire comme opposes."""
    for p in (CLAIR, SOMBRE):
        bleu_decote = int(p.z_decote[5:7], 16)
        rouge_surcote = int(p.z_surcote[1:3], 16)
        assert bleu_decote > 150 and rouge_surcote > 150


def test_tous_les_motifs_produits_par_le_moteur_ont_une_traduction():
    """Un code technique dans une interface est une dette qu'on paie a chaque
    lecture."""
    produits = _frame(
        "select distinct unnest(quality_reasons) as motif from regression_fits "
        "where quality_reasons is not null"
    )
    for motif in produits["motif"]:
        assert motif in MOTIFS, f"motif sans traduction : {motif}"
        assert motif_en_clair(motif) != motif


# --------------------------------------------------------------------------- #
# Episodes
# --------------------------------------------------------------------------- #
def test_les_episodes_sont_des_intervalles_contigus():
    serie = pd.DataFrame({
        "ts": [date(2024, 1, 1) + timedelta(weeks=i) for i in range(8)],
        "z": np.array([0, -3, -3, 0, 0, -3, -3, -3], dtype=float),
    })
    episodes = charts.episodes_sous_seuil(serie)
    assert len(episodes) == 2
    assert episodes.iloc[0]["debut"] == date(2024, 1, 8)
    assert episodes.iloc[1]["fin"] == date(2024, 2, 19)


def test_un_episode_en_cours_va_jusqua_la_derniere_barre():
    serie = pd.DataFrame({
        "ts": [date(2024, 1, 1) + timedelta(weeks=i) for i in range(4)],
        "z": np.array([0, 0, -3, -3], dtype=float),
    })
    episodes = charts.episodes_sous_seuil(serie)
    assert len(episodes) == 1
    assert episodes.iloc[0]["fin"] == date(2024, 1, 22)


# --------------------------------------------------------------------------- #
# « Ma position » sur le graphe
#
# Un repere personnel au milieu de donnees de marche : il doit se voir, et il ne
# doit jamais deformer ce qu'il annote.
# --------------------------------------------------------------------------- #
def _position(ouverture: date, prix: float, fictive: bool = False) -> pd.DataFrame:
    return pd.DataFrame([{
        "opened_at": ouverture, "avg_price": prix, "quantity": 3.0,
        "is_paper": fictive,
    }])


def _marques(serie: pd.DataFrame, positions: pd.DataFrame) -> list[str]:
    couches = charts.couches_position(serie, positions, CLAIR, "EUR")
    return [c.to_dict()["mark"]["type"] for c in couches]


def test_la_position_marque_la_date_dachat_et_le_prix_de_revient(fit_et_barres):
    """Deux traits qui se croisent : la verticale dit quand, l'horizontale dit a
    combien — et c'est l'horizontale qui porte l'information utile."""
    fit, barres = fit_et_barres
    serie = charts.serie_de_regression(barres, fit)
    milieu = serie.iloc[len(serie) // 2]
    marques = _marques(serie, _position(milieu["ts"], float(milieu["close"])))
    assert marques.count("rule") == 2, "une verticale (date) et une horizontale (PRU)"
    assert "point" in marques, "le croisement des deux est marque"


def test_la_marque_de_position_utilise_sa_couleur_reservee(fit_et_barres):
    """`marque_position` ne code pas un jugement mais un fait personnel : la
    reutiliser ailleurs la viderait de son sens."""
    fit, barres = fit_et_barres
    serie = charts.serie_de_regression(barres, fit)
    milieu = serie.iloc[len(serie) // 2]
    couches = charts.couches_position(
        serie, _position(milieu["ts"], float(milieu["close"])), CLAIR, "EUR")
    couleurs = {c.to_dict()["mark"]["color"] for c in couches}
    assert couleurs == {CLAIR.marque_position}
    assert CLAIR.marque_position not in {CLAIR.serie_cours, CLAIR.serie_pair,
                                        CLAIR.serie_secteur, CLAIR.encre_attenuee}


def test_un_achat_anterieur_a_la_fenetre_ne_trace_pas_de_verticale(fit_et_barres):
    """Il etendrait l'axe de plusieurs annees et ecraserait la courbe : le graphe
    deviendrait faux a l'oeil pour signaler un fait exact."""
    fit, barres = fit_et_barres
    serie = charts.serie_de_regression(barres, fit)
    vieux = serie["ts"].min() - timedelta(days=4000)
    marques = _marques(serie, _position(vieux, float(serie["close"].median())))
    assert marques.count("rule") == 1, "le prix de revient reste, la date non"
    assert "point" not in marques


def test_un_achat_de_la_semaine_en_cours_est_trace(fit_et_barres):
    """La serie hebdomadaire s'arrete a la derniere barre close : refuser un
    achat posterieur de quelques jours masquerait la position la plus fraiche —
    c'est le cas le plus courant, pas un cas limite."""
    fit, barres = fit_et_barres
    serie = charts.serie_de_regression(barres, fit)
    recent = serie["ts"].max() + timedelta(days=4)
    marques = _marques(serie, _position(recent, float(serie["close"].iloc[-1])))
    assert marques.count("rule") == 2
    assert "point" in marques


def test_un_prix_hors_echelle_ne_trace_pas_dhorizontale(fit_et_barres):
    fit, barres = fit_et_barres
    serie = charts.serie_de_regression(barres, fit)
    milieu = serie.iloc[len(serie) // 2]
    marques = _marques(serie, _position(milieu["ts"], 1e9))
    assert marques.count("rule") == 1, "la date reste, le prix absurde non"


def test_sans_position_le_graphe_est_inchange(fit_et_barres):
    fit, barres = fit_et_barres
    serie = charts.serie_de_regression(barres, fit)
    nu = charts.graphe_regression(serie, CLAIR, "EUR").to_dict()
    vide = charts.graphe_regression(
        serie, CLAIR, "EUR", positions=_position(date(2024, 1, 1), 10.0).iloc[0:0]
    ).to_dict()
    assert len(nu["layer"]) == len(vide["layer"])


# --------------------------------------------------------------------------- #
# Detentions : ce que le screener et l'en-tete lisent
# --------------------------------------------------------------------------- #
def test_deux_lignes_sur_un_meme_titre_cumulent_la_quantite_pas_le_prix():
    """La somme de deux prix de revient ne veut rien dire ; leur moyenne
    ponderee, si."""
    from dashboard import entete

    positions = pd.DataFrame([
        {"internal_code": "EQ:FR:X", "quantity": 10.0, "avg_price": 100.0,
         "investi": 1000.0, "valeur": 1200.0, "is_paper": False},
        {"internal_code": "EQ:FR:X", "quantity": 30.0, "avg_price": 50.0,
         "investi": 1500.0, "valeur": 3600.0, "is_paper": True},
    ])
    resume = entete.detentions(positions)
    ligne = resume.loc["EQ:FR:X"]
    assert ligne["quantite"] == 40.0
    assert ligne["prix_de_revient"] == pytest.approx(62.5), "(10×100 + 30×50) / 40"
    assert ligne["reel"] and ligne["fictif"], "les deux modes sont signales"


def test_un_portefeuille_vide_rend_une_table_vide_mais_utilisable():
    """Les ecrans testent `.empty` et lisent des colonnes : une table sans
    colonnes les casserait tous."""
    from dashboard import entete

    resume = entete.detentions(pd.DataFrame())
    assert resume.empty
    assert "quantite" in resume.columns and "reel" in resume.columns
