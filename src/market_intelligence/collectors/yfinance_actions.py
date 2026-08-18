"""Collecteur des operations sur titre et du nombre d'actions.

Comme tout collector (doc 02 SS4.1) : recupere et rend le brut, ne valide rien.

Trois flux, de fiabilite tres inegale - c'est le point a retenir avant de leur
faire confiance :

- **splits** : bons. Verifiables par detection de saut sur la serie de cours.
- **dividendes** : bons. Servis dans le meme espace que `Close`, donc deja
  ajustes des splits posterieurs, ce qui les rend directement comparables au
  cours sans retraitement.
- **nombre d'actions** : partiel. `get_shares_full` ne remonte guere avant 2019
  et n'existe pas pour tous les titres. C'est la faiblesse structurelle du
  dispositif gratuit (doc 02 SS2.2) : les augmentations de capital dilutives ne
  sont exposees proprement par aucune source gratuite, et ce sont precisement
  elles qui faussent la regression sur les Atos et les Casino.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import date

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RawActions:
    symbol: str
    splits: object = None       # pandas.Series indexee par ex_date
    dividends: object = None    # pandas.Series indexee par ex_date
    shares: object = None       # pandas.Series indexee par date
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error


def fetch_actions(
    symbol: str,
    shares_start: date | None = None,
    rate_limit_sec: float = 0.0,
) -> RawActions:
    """Recupere splits, dividendes et nombre d'actions. Ne leve pas.

    L'absence de nombre d'actions n'est pas une erreur : la plupart des titres
    n'en ont pas sur toute la periode. L'absence de dividendes non plus - toutes
    les societes n'en versent pas.
    """
    import yfinance as yf

    splits = dividends = shares = None
    error = ""
    try:
        ticker = yf.Ticker(symbol)
        actions = ticker.actions            # un seul appel reseau pour les deux
        if actions is not None and len(actions):
            if "Stock Splits" in actions.columns:
                series = actions["Stock Splits"]
                splits = series[series != 0]
            if "Dividends" in actions.columns:
                series = actions["Dividends"]
                dividends = series[series != 0]

        try:
            shares = ticker.get_shares_full(
                start=(shares_start or date(2015, 1, 1)).isoformat()
            )
        except Exception as exc:  # noqa: BLE001 - flux optionnel, jamais bloquant
            logger.info("nombre d'actions indisponible pour %s : %s", symbol, exc)
    except Exception as exc:  # noqa: BLE001
        error = f"{type(exc).__name__}: {exc}"
        logger.warning("actions %s : %s", symbol, error)

    if rate_limit_sec:
        time.sleep(rate_limit_sec)

    return RawActions(symbol=symbol, splits=splits, dividends=dividends,
                      shares=shares, error=error)
