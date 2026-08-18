"""Statistiques de regime : ce qu'on affiche a la place d'une fausse probabilite.

Le contresens central de la methode, telle qu'elle est generalement presentee :

    « Ce titre est a -2 sigma, donc il a 95% de chances de remonter. »

C'est faux. Les residus sont fortement autocorreles : les episodes hors bande ne
sont pas des evenements independants de frequence 5%, ce sont des **regimes qui
durent**. « Moins de 5% du temps » est une frequence temporelle, pas une
probabilite de retournement.

On rapporte donc la distribution du temps de premier passage. Decouvrir qu'un
titre reste typiquement quatorze mois sous -2 sigma avec un creux supplementaire
de 20% est une information de gestion ; « 95% de chances » n'en est pas une.

Toutes ces statistiques sont **in-sample** et doivent etre etiquetees comme
telles : elles decrivent le passe de ce titre, elles ne predisent rien.
"""

from __future__ import annotations

from datetime import date

import numpy as np

SEUIL_DEFAUT = -2.0
HORIZONS_ANNEES = (1, 3, 5)
SEMAINES_PAR_AN = 365.25 / 7.0


def _episodes(z: np.ndarray, seuil: float) -> list[tuple[int, int]]:
    """Intervalles [debut, fin] d'indices ou z reste sous le seuil."""
    sous = z <= seuil
    episodes = []
    debut = None
    for i, valeur in enumerate(sous):
        if valeur and debut is None:
            debut = i
        elif not valeur and debut is not None:
            episodes.append((debut, i - 1))
            debut = None
    if debut is not None:
        episodes.append((debut, len(z) - 1))
    return episodes


def regime_stats(
    dates: list[date],
    prices: np.ndarray,
    residuals: np.ndarray,
    sigma: float,
    seuil: float = SEUIL_DEFAUT,
) -> dict:
    """Statistiques de regime sous un seuil de z-score.

    Returns:
        Un dictionnaire serialisable, destine a `regression_fits.regime_stats`.
    """
    if sigma <= 0 or len(residuals) == 0:
        return {"seuil": seuil, "n_episodes": 0, "in_sample": True}

    prices = np.asarray(prices, dtype=float)
    z = residuals / sigma
    episodes = _episodes(z, seuil)

    durees_semaines = [fin - debut + 1 for debut, fin in episodes]

    # Creux supplementaire apres franchissement : de combien le cours baisse-t-il
    # encore, une fois le seuil passe ? C'est la question que pose reellement
    # quelqu'un qui vient d'acheter a -2 sigma.
    drawdowns = []
    for debut, fin in episodes:
        prix_entree = prices[debut]
        creux = prices[debut:fin + 1].min()
        drawdowns.append(creux / prix_entree - 1.0)

    # Rendement a horizon, apres le premier franchissement de chaque episode.
    # Distribution, jamais moyenne seule : c'est la dispersion qui informe.
    rendements: dict = {}
    for annees in HORIZONS_ANNEES:
        pas = int(round(annees * SEMAINES_PAR_AN))
        valeurs = [
            float(prices[debut + pas] / prices[debut] - 1.0)
            for debut, _ in episodes
            if debut + pas < len(prices)
        ]
        if valeurs:
            rendements[f"{annees}a"] = {
                "n": len(valeurs),
                "min": round(min(valeurs), 4),
                "median": round(float(np.median(valeurs)), 4),
                "max": round(max(valeurs), 4),
            }

    # Episode en cours : depuis combien de semaines le titre est-il sous le seuil ?
    semaines_en_cours = 0
    if z[-1] <= seuil:
        for valeur in reversed(z):
            if valeur > seuil:
                break
            semaines_en_cours += 1

    return {
        "seuil": seuil,
        "in_sample": True,
        "n_episodes": len(episodes),
        "part_du_temps_sous_seuil": round(float((z <= seuil).mean()), 4),
        "duree_mediane_semaines": (
            round(float(np.median(durees_semaines)), 1) if durees_semaines else None
        ),
        "duree_max_semaines": max(durees_semaines) if durees_semaines else None,
        "drawdown_median_apres_seuil": (
            round(float(np.median(drawdowns)), 4) if drawdowns else None
        ),
        "drawdown_pire_apres_seuil": round(min(drawdowns), 4) if drawdowns else None,
        "rendements_apres_franchissement": rendements,
        "semaines_consecutives_en_cours": semaines_en_cours,
        "premier_franchissement": (
            dates[episodes[-1][0]].isoformat() if semaines_en_cours and episodes else None
        ),
    }
