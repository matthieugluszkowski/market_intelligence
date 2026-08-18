"""Correction de multiplicite Benjamini-Hochberg-Yekutieli (doc 03 SS3.3).

*Le verdict de qualite est lui-meme soumis a la multiplicite - 250 tests a 5%
produisent une douzaine de faux `good`.*

Le probleme est reel et souvent ignore : tester 57 titres au seuil de 5% garantit
environ trois rejets a tort, qui ressortiront comme des tendances solidement
etablies alors qu'ils sont du bruit.

BH**Y** plutot que BH simple : la variante Yekutieli reste valide sous
dependance arbitraire entre les tests. C'est necessaire ici - les titres d'un
meme marche partagent leurs chocs, leurs p-values ne sont pas independantes, et
BH simple s'appuie precisement sur cette independance.

Le prix est un seuil plus conservateur d'un facteur ln(m) + gamma, soit environ
4,6 sur 57 tests. Autrement dit : encore moins de `good`. C'est le comportement
recherche.
"""

from __future__ import annotations

import math


def bhy(pvalues: list[float | None], alpha: float = 0.05) -> list[bool]:
    """Rend, pour chaque p-value, si l'hypothese nulle est rejetee sous BHY.

    Les entrees None - test non calculable - ne sont pas rejetees et ne comptent
    pas dans le nombre de tests.
    """
    indexes = [i for i, p in enumerate(pvalues) if p is not None]
    m = len(indexes)
    rejets = [False] * len(pvalues)
    if m == 0:
        return rejets

    # Constante d'harmonie c(m) = somme des 1/i, qui rend la procedure valide
    # sous dependance arbitraire.
    c_m = sum(1.0 / i for i in range(1, m + 1))

    ordonnes = sorted(indexes, key=lambda i: pvalues[i])
    seuil_max = -1
    for rang, i in enumerate(ordonnes, start=1):
        if pvalues[i] <= (rang / m) * alpha / c_m:
            seuil_max = rang

    for rang, i in enumerate(ordonnes, start=1):
        if rang <= seuil_max:
            rejets[i] = True
    return rejets


def facteur_de_penalite(m: int) -> float:
    """Facteur c(m) applique au seuil. Environ ln(m) + 0,577."""
    if m <= 0:
        return 1.0
    return sum(1.0 / i for i in range(1, m + 1))


def approximation_c_m(m: int) -> float:
    """Approximation asymptotique, pour la documentation et les tests."""
    return math.log(m) + 0.5772156649
