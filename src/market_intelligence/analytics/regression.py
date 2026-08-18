"""Ajustement log-lineaire et diagnostics de validite (doc 03 SS1 et SS3).

Fonctions pures : elles prennent des tableaux, rendent des dictionnaires, ne
touchent ni la base ni le reseau. Tout y est donc testable sur donnees
synthetiques dont on connait la reponse - ce qui est le seul moyen de savoir si
un moteur statistique dit vrai.

L'erreur a ne pas commettre
---------------------------
Le test de racine unitaire porte sur le **log-prix, avec constante et tendance**,
jamais sur les residus de la regression.

Appliquer un ADF standard aux residus d'une regression aux coefficients estimes
invalide les valeurs critiques et sur-rejette massivement : on obtiendrait une
liste de titres « stationnaires » entierement fictive, sans que rien ne le
signale. Par le theoreme de Frisch-Waugh, le test correct est l'ADF avec
constante et tendance directement sur le log-prix, dont les valeurs critiques
tau_tau valent environ -3,41 a 5%.

C'est l'erreur la plus couteuse et la plus silencieuse du projet, et elle a son
test unitaire dedie.
"""

from __future__ import annotations

import warnings
from datetime import date

import numpy as np

SEMAINES_PAR_AN = 365.25 / 7.0
BOOTSTRAP_TIRAGES = 400
BOOTSTRAP_TAILLE_BLOC = 26          # un semestre de barres hebdomadaires


def fit_log_linear(dates: list[date], prices: np.ndarray) -> dict:
    """Estime log(P_t) = alpha + beta*t + eps_t, t en annees.

    Returns:
        intercept, slope_annual (exp(beta)-1), sigma_resid, z_score, r_squared,
        residuals, n_obs.
    """
    prices = np.asarray(prices, dtype=float)
    origine = dates[0]
    t = np.array([(d - origine).days / 365.25 for d in dates])
    y = np.log(prices)

    X = np.column_stack([np.ones_like(t), t])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    n = len(y)
    sigma = float(np.sqrt((resid ** 2).sum() / (n - 2)))

    variance_totale = float(((y - y.mean()) ** 2).sum())
    return {
        "intercept": float(beta[0]),
        "beta": float(beta[1]),
        "slope_annual": float(np.exp(beta[1]) - 1.0),
        "sigma_resid": sigma,
        "z_score": float(resid[-1] / sigma) if sigma > 0 else 0.0,
        "r_squared": float(1 - (resid ** 2).sum() / variance_totale) if variance_totale > 0 else 0.0,
        "fitted_last": float((X @ beta)[-1]),
        "residual_last": float(resid[-1]),
        "residuals": resid,
        "log_prices": y,
        "n_obs": n,
    }


def _lambda_ou(resid: np.ndarray) -> float:
    """Coefficient lambda de la regression Delta_eps_t = lambda * eps_{t-1} + u_t."""
    d_resid = np.diff(resid)
    lag_resid = resid[:-1]
    denominateur = float((lag_resid ** 2).sum())
    if denominateur == 0:
        return 0.0
    return float((lag_resid * d_resid).sum() / denominateur)


def half_life_days(resid: np.ndarray) -> float | None:
    """Demi-vie du retour a la moyenne, en jours.

    Plus actionnable que le z-score lui-meme : un titre a -2 sigma avec une
    demi-vie de 18 mois et un titre a -2 sigma avec une demi-vie de 9 ans ne sont
    pas la meme proposition, alors qu'ils ont le meme score.

    Le raisonnement porte sur rho = 1 + lambda, la racine autoregressive, et non
    sur lambda directement :

    - `0 < rho < 1` : retour geometrique, demi-vie = -ln(2) / ln(rho).
    - `rho <= 0` : retour plus rapide qu'une periode, avec alternance de signe.
      C'est le cas d'un bruit blanc, ou lambda vaut environ -1 et ou l'expression
      logarithmique n'est pas definie. La demi-vie est alors inferieure au pas
      d'observation : on rend 0, pas None - l'information « ca revient tout de
      suite » n'est pas une absence d'information.
    - `rho >= 1` : le processus ne revient pas. None.

    Le garde precedent, `-2 < lambda < 0`, laissait passer lambda = -1,005 et
    produisait un logarithme de nombre negatif, donc un NaN silencieux.
    """
    rho = 1.0 + _lambda_ou(resid)
    if rho >= 1.0:
        return None
    if rho <= 0.0:
        return 0.0
    demi_vie_semaines = -np.log(2) / np.log(rho)
    return float(demi_vie_semaines * 7.0)


def ar1_confidence_interval(resid: np.ndarray, graine: int) -> tuple[float | None, float | None]:
    """Intervalle de confiance a 95% sur la racine autoregressive dominante.

    Un intervalle plutot qu'un booleen « stationnaire », et c'est le point
    methodologique le plus important du moteur. Sur vingt ans, aucun test ne
    distingue de facon fiable rho = 1 de rho = 0,99 : rendre un verdict binaire
    fabriquerait une certitude qui n'existe pas. Un intervalle [0,94 ; 1,02] dit
    la verite, a savoir qu'on ne sait pas trancher.

    Methode : bootstrap par blocs mobiles sur les residus, qui preserve leur
    autocorrelation - un bootstrap i.i.d. la detruirait et rendrait un intervalle
    faussement etroit.

    Limite a connaitre avant de lire l'intervalle
    ---------------------------------------------
    Cet intervalle reste **anti-conservateur pres de la racine unitaire**, et il
    ne faut pas lui faire dire plus qu'il ne peut.

    Deux raisons se cumulent. Les residus sont ceux d'une tendance estimee, donc
    deja detendances : rho y est biaise vers le bas, d'un ordre de 1/n (biais de
    Dickey-Fuller). Et le bootstrap par blocs ne reproduit pas la distribution
    asymptotique non standard de rho quand la vraie valeur vaut 1.

    Consequence observee sur l'univers : Seb ressort a [0,943 ; 0,968], qui
    exclut 1, alors que le DF-GLS sur le meme titre ne rejette pas la racine
    unitaire. **C'est le test qui a raison, pas l'intervalle.** L'intervalle sert
    a comparer des titres entre eux et a montrer l'ordre de grandeur de la
    persistance ; l'arbitrage stationnaire ou non revient au DF-GLS, et c'est lui
    seul qui alimente `fit_quality`.

    Une inversion de test a la Stock (1991) donnerait un intervalle correct pres
    de l'unite. C'est la piste d'amelioration, elle n'est pas prise en v1.

    La graine est derivee de l'instrument et de la date de calcul : le resultat
    doit etre identique d'une execution a l'autre, sinon `regression_fits`
    cesserait d'etre reproductible.
    """
    n = len(resid)
    if n < 3 * BOOTSTRAP_TAILLE_BLOC:
        return None, None

    rng = np.random.default_rng(graine)
    n_blocs = int(np.ceil(n / BOOTSTRAP_TAILLE_BLOC))
    depart_max = n - BOOTSTRAP_TAILLE_BLOC

    rhos = np.empty(BOOTSTRAP_TIRAGES)
    for tirage in range(BOOTSTRAP_TIRAGES):
        departs = rng.integers(0, depart_max + 1, size=n_blocs)
        echantillon = np.concatenate(
            [resid[d:d + BOOTSTRAP_TAILLE_BLOC] for d in departs]
        )[:n]
        rhos[tirage] = 1.0 + _lambda_ou(echantillon)

    return float(np.percentile(rhos, 2.5)), float(np.percentile(rhos, 97.5))


def durbin_watson(resid: np.ndarray) -> float:
    return float((np.diff(resid) ** 2).sum() / (resid ** 2).sum())


def unit_root_tests(log_prices: np.ndarray) -> dict:
    """ADF, KPSS et DF-GLS, tous sur le log-prix avec constante et tendance.

    DF-GLS (Elliott-Rothenberg-Stock, 1996) est nettement plus puissant que l'ADF
    sur les alternatives proches de la racine unitaire - exactement notre cas.
    C'est lui qui arbitre le verdict de qualite ; l'ADF et le KPSS sont rapportes
    pour que le desaccord entre tests reste visible.
    """
    from arch.unitroot import DFGLS
    from statsmodels.tsa.stattools import adfuller, kpss

    resultats: dict = {
        "adf_stat": None, "adf_pvalue": None,
        "kpss_stat": None, "dfgls_stat": None, "dfgls_pvalue": None,
        "dfgls_crit_5": None,
    }

    try:
        adf = adfuller(log_prices, regression="ct", autolag="AIC")
        resultats["adf_stat"] = float(adf[0])
        resultats["adf_pvalue"] = float(adf[1])
    except Exception:  # noqa: BLE001 - un diagnostic absent ne doit pas tuer le fit
        pass

    try:
        with warnings.catch_warnings():
            # p-value hors table : statsmodels previent, l'information reste utile.
            warnings.simplefilter("ignore")
            resultats["kpss_stat"] = float(kpss(log_prices, regression="ct", nlags="auto")[0])
    except Exception:  # noqa: BLE001
        pass

    try:
        dfgls = DFGLS(log_prices, trend="ct")
        resultats["dfgls_stat"] = float(dfgls.stat)
        resultats["dfgls_pvalue"] = float(dfgls.pvalue)
        resultats["dfgls_crit_5"] = float(dfgls.critical_values["5%"])
    except Exception:  # noqa: BLE001
        pass

    return resultats


def analyse(dates: list[date], prices: np.ndarray, graine: int) -> dict:
    """Enchaine ajustement, tests de racine unitaire et diagnostics residuels."""
    ajustement = fit_log_linear(dates, prices)
    resid = ajustement["residuals"]

    diagnostics = unit_root_tests(ajustement["log_prices"])
    ar1_bas, ar1_haut = ar1_confidence_interval(resid, graine)
    diagnostics.update({
        "durbin_watson": durbin_watson(resid),
        "half_life_days": half_life_days(resid),
        "ar1_ci_low": ar1_bas,
        "ar1_ci_high": ar1_haut,
    })
    return {**ajustement, **diagnostics}
