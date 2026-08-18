"""Criteres d'acceptation du lot L4 (05_roadmap-et-lot.md).

    - sur un jeu synthetique de pente et de sigma connus, les parametres sont
      retrouves a 1% pres
    - sur une marche aleatoire pure simulee, le verdict est majoritairement
      `weak` ou `rejected` - **c'est le test qui verifie que le systeme ne se
      ment pas a lui-meme**
    - l'ADF est bien appele avec regression="ct" sur le log-prix et non sur les
      residus (test unitaire dedie, c'est l'erreur la plus couteuse et la plus
      silencieuse)
    - deux executions a la meme as_of_date produisent des parametres identiques
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from market_intelligence.analytics.eligibility import eligibilite, fenetre, verdict  # noqa: E402
from market_intelligence.analytics.multiplicity import approximation_c_m, bhy  # noqa: E402
from market_intelligence.analytics.regime import regime_stats  # noqa: E402
from market_intelligence.analytics.regression import (  # noqa: E402
    analyse, ar1_confidence_interval, fit_log_linear, half_life_days, unit_root_tests,
)
from market_intelligence.db import fetch_all, fetch_one  # noqa: E402

POLITIQUE = {"code": "loglin_20y", "model": "log_linear", "window_years": 20,
             "min_years": 15, "bar_freq": "1w", "min_observations": 500}


def serie_synthetique(pente_annuelle: float, sigma: float, n: int = 1040,
                      graine: int = 12345) -> tuple[list[date], np.ndarray]:
    """Serie a tendance deterministe et bruit gaussien i.i.d. de parametres connus."""
    rng = np.random.default_rng(graine)
    depart = date(2006, 1, 2)
    dates = [depart + timedelta(weeks=i) for i in range(n)]
    t = np.array([(d - depart).days / 365.25 for d in dates])
    beta = np.log(1 + pente_annuelle)
    log_prix = np.log(50.0) + beta * t + rng.normal(0, sigma, n)
    return dates, np.exp(log_prix)


def marche_aleatoire(n: int = 1040, graine: int = 7) -> tuple[list[date], np.ndarray]:
    """Marche aleatoire pure : aucune tendance deterministe a retrouver."""
    rng = np.random.default_rng(graine)
    depart = date(2006, 1, 2)
    dates = [depart + timedelta(weeks=i) for i in range(n)]
    return dates, np.exp(np.log(50.0) + np.cumsum(rng.normal(0, 0.03, n)))


# --------------------------------------------------------------------------- #
# 1. Les parametres sont retrouves a 1% pres
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("pente", [0.03, 0.08, 0.15])
@pytest.mark.parametrize("sigma", [0.02, 0.05])
def test_les_parametres_connus_sont_retrouves(pente, sigma):
    """Critere du doc 05 : pente et sigma retrouves a 1% pres.

    A rapport signal sur bruit eleve, ou l'erreur d'echantillonnage est
    negligeable devant le seuil. Le critere litteral n'est **pas** atteignable
    sur un tirage unique a sigma eleve, et ce n'est pas un defaut du code : a
    sigma = 0,25 et pente = 3%, l'erreur-type theorique de beta vaut deja 4,6% de
    beta. Exiger 1% reviendrait a exiger de l'estimateur qu'il soit plus precis
    que ce que l'information contenue dans les donnees permet. Les deux tests
    suivants verifient ce qui est reellement verifiable.
    """
    dates, prix = serie_synthetique(pente, sigma)
    r = fit_log_linear(dates, prix)
    assert r["slope_annual"] == pytest.approx(pente, rel=0.01)

    # sigma a sa propre limite, et elle ne depend pas du rapport signal sur bruit :
    # l'erreur-type relative de l'ecart-type estime vaut 1/sqrt(2(n-2)), soit 2,2%
    # sur 1 040 points, quel que soit sigma. Aucun choix de parametres ne rend le
    # seuil de 1% atteignable sur un tirage unique - il faudrait 45 000 points.
    erreur_type_relative = 1 / np.sqrt(2 * (r["n_obs"] - 2))
    assert r["sigma_resid"] == pytest.approx(sigma, rel=3 * erreur_type_relative)


@pytest.mark.parametrize(("pente", "sigma"), [(0.03, 0.25), (0.08, 0.10)])
def test_lestimateur_est_sans_biais(pente, sigma):
    """Ce que le critere du doc cherche vraiment : un estimateur juste.

    Sur 300 tirages a sigma = 0,25, la moyenne des pentes estimees tombe a 0,11%
    de la vraie valeur - la dispersion d'un tirage unique est du bruit, pas un
    biais. Pente **et** sigma sont verifies a 1% ici, ce que le tirage unique ne
    permet pas.
    """
    ajustements = [
        fit_log_linear(*serie_synthetique(pente, sigma, graine=g))
        for g in range(300)
    ]
    assert float(np.mean([a["slope_annual"] for a in ajustements])) == pytest.approx(
        pente, rel=0.01)
    assert float(np.mean([a["sigma_resid"] for a in ajustements])) == pytest.approx(
        sigma, rel=0.01)


@pytest.mark.parametrize(("pente", "sigma"), [(0.03, 0.25), (0.03, 0.10), (0.15, 0.25)])
def test_lerreur_dun_tirage_reste_dans_lerreur_type_theorique(pente, sigma):
    """Exigence plus forte que celle du doc : l'ecart constate doit s'expliquer
    entierement par l'erreur-type des moindres carres. Un estimateur mal code
    derive au-dela, meme quand la moyenne semble correcte."""
    dates, prix = serie_synthetique(pente, sigma)
    r = fit_log_linear(dates, prix)
    t = np.array([(d - dates[0]).days / 365.25 for d in dates])
    erreur_type = sigma / np.sqrt(((t - t.mean()) ** 2).sum())
    beta_estime, beta_vrai = np.log(1 + r["slope_annual"]), np.log(1 + pente)
    assert abs(beta_estime - beta_vrai) < 3 * erreur_type


def test_lintercept_est_retrouve():
    dates, prix = serie_synthetique(0.08, 0.15)
    assert fit_log_linear(dates, prix)["intercept"] == pytest.approx(np.log(50.0), abs=0.02)


def test_le_z_score_est_le_residu_normalise():
    dates, prix = serie_synthetique(0.06, 0.20)
    r = fit_log_linear(dates, prix)
    assert r["z_score"] == pytest.approx(r["residual_last"] / r["sigma_resid"])


def test_un_titre_sur_sa_tendance_a_un_z_proche_de_zero():
    dates, prix = serie_synthetique(0.07, 0.0001)
    assert abs(fit_log_linear(dates, prix)["z_score"]) < 3


# --------------------------------------------------------------------------- #
# 2. Le systeme ne se ment pas a lui-meme sur une marche aleatoire
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("graine", [1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
def test_une_marche_aleatoire_nest_jamais_declaree_good(graine):
    """Le test le plus important du lot.

    Une marche aleatoire n'a pas de tendance deterministe. Un moteur qui la
    declare `good` produit une liste de titres « solidement en tendance » qui
    n'est que du bruit - et rien ne le signale jamais.
    """
    dates, prix = marche_aleatoire(graine=graine)
    r = analyse(dates, prix, graine=graine)
    rejette = r["dfgls_pvalue"] is not None and r["dfgls_pvalue"] < 0.05
    qualite, _ = verdict(
        motifs=[], n_obs=r["n_obs"], politique=POLITIQUE, r_squared=r["r_squared"],
        dfgls_rejette=rejette, dfgls_stat=r["dfgls_stat"], dfgls_crit_5=r["dfgls_crit_5"],
    )
    assert qualite in ("weak", "rejected"), f"marche aleatoire declaree {qualite}"


def test_une_serie_a_tendance_nette_est_reconnue_comme_stationnaire_en_tendance():
    """Symetrique du precedent : le moteur doit savoir dire oui, sinon il ne dit rien."""
    dates, prix = serie_synthetique(0.08, 0.12)
    r = analyse(dates, prix, graine=1)
    assert r["dfgls_pvalue"] < 0.05
    assert r["adf_pvalue"] < 0.05


# --------------------------------------------------------------------------- #
# 3. L'ADF porte sur le log-prix avec constante et tendance, jamais sur les residus
# --------------------------------------------------------------------------- #
def test_ladf_est_calcule_sur_le_log_prix_et_non_sur_les_residus():
    """L'erreur la plus couteuse et la plus silencieuse du projet.

    Un ADF applique aux residus d'une regression aux coefficients estimes
    sur-rejette massivement : sur une marche aleatoire, ou il ne devrait rien
    trouver, il rejette la racine unitaire avec une p-value ecrasante. On
    verifie que notre statistique est bien celle du log-prix, et qu'elle differe
    de la version fautive.
    """
    from statsmodels.tsa.stattools import adfuller

    dates, prix = marche_aleatoire(graine=42)
    ajustement = fit_log_linear(dates, prix)
    notre = unit_root_tests(ajustement["log_prices"])

    attendu = adfuller(np.log(prix), regression="ct", autolag="AIC")
    assert notre["adf_stat"] == pytest.approx(attendu[0])

    # La version fautive : ADF sur les residus. Elle rejette a tort.
    fautif = adfuller(ajustement["residuals"], regression="c", autolag="AIC")
    assert fautif[1] < 0.05, "le contre-exemple ne demontre plus rien"
    assert notre["adf_pvalue"] > 0.10
    assert notre["adf_stat"] != pytest.approx(fautif[0])


def test_ladf_utilise_bien_constante_et_tendance():
    """Avec 'c' au lieu de 'ct', les valeurs critiques ne sont pas les bonnes."""
    from statsmodels.tsa.stattools import adfuller

    dates, prix = serie_synthetique(0.10, 0.15)
    notre = unit_root_tests(np.log(prix))["adf_stat"]
    assert notre == pytest.approx(adfuller(np.log(prix), regression="ct", autolag="AIC")[0])
    assert notre != pytest.approx(adfuller(np.log(prix), regression="c", autolag="AIC")[0])


# --------------------------------------------------------------------------- #
# 4. Reproductibilite
# --------------------------------------------------------------------------- #
def test_deux_executions_donnent_des_parametres_identiques():
    dates, prix = serie_synthetique(0.07, 0.18)
    a = analyse(dates, prix, graine=999)
    b = analyse(dates, prix, graine=999)
    for cle in ("slope_annual", "sigma_resid", "z_score", "r_squared",
                "adf_stat", "dfgls_stat", "ar1_ci_low", "ar1_ci_high", "half_life_days"):
        assert a[cle] == b[cle], f"{cle} non reproductible"


def test_le_bootstrap_est_deterministe_par_sa_graine():
    resid = np.random.default_rng(5).normal(0, 1, 1040)
    assert ar1_confidence_interval(resid, 77) == ar1_confidence_interval(resid, 77)
    assert ar1_confidence_interval(resid, 77) != ar1_confidence_interval(resid, 78)


# --------------------------------------------------------------------------- #
# Diagnostics
# --------------------------------------------------------------------------- #
def test_la_demi_vie_dun_bruit_blanc_est_courte():
    """Un bruit i.i.d. revient immediatement : rho proche de 0, demi-vie < 1 pas.

    Cas limite reel : lambda vaut environ -1,005, donc rho est legerement negatif
    et l'expression logarithmique n'est pas definie. Le garde initial laissait
    passer et produisait un NaN silencieux, qui serait parti tel quel en base.
    """
    resid = np.random.default_rng(3).normal(0, 1, 1040)
    dv = half_life_days(resid)
    assert dv is not None and not np.isnan(dv)
    assert 0 <= dv < 30


def test_la_demi_vie_dune_serie_persistante_est_longue():
    rng = np.random.default_rng(3)
    resid = np.zeros(1040)
    for i in range(1, 1040):
        resid[i] = 0.99 * resid[i - 1] + rng.normal(0, 0.1)
    dv = half_life_days(resid)
    assert dv is None or dv > 200


def test_lintervalle_ar1_encadre_lunite_pour_une_marche_aleatoire():
    """Sur vingt ans aucun test ne distingue rho = 1 de rho = 0,99 : l'intervalle
    doit le dire, plutot que de trancher."""
    dates, prix = marche_aleatoire(graine=11)
    r = analyse(dates, prix, graine=11)
    assert r["ar1_ci_low"] is not None
    assert r["ar1_ci_low"] < r["ar1_ci_high"]


# --------------------------------------------------------------------------- #
# Eligibilite et fenetre
# --------------------------------------------------------------------------- #
def test_la_dilution_disqualifie_le_fit():
    motifs = eligibilite(POLITIQUE, n_obs=1040, annees_disponibles=20,
                         dilution_dans_la_fenetre=True, anomalies_bloquantes=[],
                         n_obs_attendues=1043)
    assert "dilution_detected" in motifs


def test_une_politique_excluded_disqualifie():
    exclue = {**POLITIQUE, "model": "none", "min_years": 0, "min_observations": 0}
    assert "policy_excluded" in eligibilite(exclue, 1040, 20, False, [], 1043)


def test_trop_de_trous_disqualifie():
    motifs = eligibilite(POLITIQUE, n_obs=900, annees_disponibles=20,
                         dilution_dans_la_fenetre=False, anomalies_bloquantes=[],
                         n_obs_attendues=1043)
    assert "too_many_gaps" in motifs


def test_un_fit_rejete_porte_toujours_son_motif():
    qualite, motifs = verdict([], 1040, POLITIQUE, 0.9, False, -0.5, -2.87)
    assert qualite == "rejected"
    assert motifs, "un rejet sans motif est inexploitable trois mois plus tard"


def test_la_fenetre_est_glissante_et_bornee_par_lhistorique():
    assert fenetre(date(2026, 8, 18), 20, date(2000, 1, 1)) == date(2006, 8, 18)
    assert fenetre(date(2026, 8, 18), 20, date(2015, 1, 1)) == date(2015, 1, 1)


# --------------------------------------------------------------------------- #
# Correction de multiplicite
# --------------------------------------------------------------------------- #
def test_bhy_est_plus_conservateur_que_le_seuil_brut():
    """57 tests a 5% produisent environ trois rejets a tort."""
    pvalues = [0.001, 0.02, 0.04, 0.045] + [0.5] * 53
    rejets = bhy(pvalues, alpha=0.05)
    bruts = sum(1 for p in pvalues if p < 0.05)
    assert sum(rejets) < bruts


def test_bhy_ignore_les_tests_non_calculables():
    assert bhy([None, None, 0.0001]) == [False, False, True]


def test_le_facteur_de_penalite_croit_avec_le_nombre_de_tests():
    from market_intelligence.analytics.multiplicity import facteur_de_penalite

    assert facteur_de_penalite(57) > facteur_de_penalite(10) > 1
    assert facteur_de_penalite(1000) == pytest.approx(approximation_c_m(1000), rel=0.01)


# --------------------------------------------------------------------------- #
# Statistiques de regime
# --------------------------------------------------------------------------- #
def test_les_statistiques_de_regime_comptent_les_episodes():
    dates = [date(2020, 1, 6) + timedelta(weeks=i) for i in range(10)]
    prix = np.array([100.0] * 10)
    resid = np.array([0, 0, -3, -3, -3, 0, 0, -3, 0, 0], dtype=float)
    stats = regime_stats(dates, prix, resid, sigma=1.0, seuil=-2.0)
    assert stats["n_episodes"] == 2
    assert stats["duree_max_semaines"] == 3


def test_les_statistiques_de_regime_sont_etiquetees_in_sample():
    """Elles decrivent le passe du titre, elles ne predisent rien."""
    dates = [date(2020, 1, 6) + timedelta(weeks=i) for i in range(10)]
    stats = regime_stats(dates, np.array([100.0] * 10), np.zeros(10), sigma=1.0)
    assert stats["in_sample"] is True


def test_lepisode_en_cours_est_compte():
    dates = [date(2020, 1, 6) + timedelta(weeks=i) for i in range(6)]
    resid = np.array([0, 0, 0, -3, -3, -3], dtype=float)
    stats = regime_stats(dates, np.array([100.0] * 6), resid, sigma=1.0, seuil=-2.0)
    assert stats["semaines_consecutives_en_cours"] == 3


# --------------------------------------------------------------------------- #
# Etat de la base
# --------------------------------------------------------------------------- #
def test_des_fits_ont_ete_ecrits():
    assert fetch_one("select count(*) from regression_fits")[0] > 0


def test_weak_est_le_cas_majoritaire():
    """Si la repartition sortait a 80% de `good`, ce serait le signe d'un bug,
    pas d'un univers exceptionnel."""
    repartition = dict(
        fetch_all(
            "select fit_quality, count(*) from regression_fits "
            "where as_of_date = (select max(as_of_date) from regression_fits) "
            "group by 1"
        )
    )
    total = sum(repartition.values())
    assert repartition.get("good", 0) / total < 0.5, repartition


def test_aucun_fit_nutilise_de_donnee_posterieure_a_sa_date_de_calcul():
    """Sans cela le look-ahead bias est structurel et irrattrapable."""
    assert fetch_one(
        "select count(*) from regression_fits where window_end > as_of_date"
    )[0] == 0


def test_les_fits_ne_sont_jamais_reecrits():
    """Principe P5 : chaque ligne enregistre ce que le systeme affirmait a cette
    date. Une reecriture detruirait l'observation hors echantillon."""
    doublons = fetch_all(
        "select instrument_id, policy_code, as_of_date, method_version, count(*) "
        "from regression_fits group by 1,2,3,4 having count(*) > 1"
    )
    assert doublons == []
