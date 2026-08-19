"""Collecteur de fondamentaux yfinance - regime A (doc 02 SS3).

Large et superficiel : environ trente concepts sur cinq exercices, pour tout
l'univers, a cout nul. C'est exactement ce qu'il faut pour repondre a la
consigne de Marie de Raismes - *une fois que tu as vu qu'il y avait un signal de
prix, tu verifies que c'est coherent avec les fondamentaux*. Cinq ans suffisent
a voir si les benefices suivent ou si la boite se delite.

Le regime B - etroit et profond, par extraction LLM de PDF sur les seuls titres
qui sortent du screener - est le lot L9.

Ce que ce collecteur ne peut pas fournir
-----------------------------------------
**La date de publication.** yfinance indexe ses tableaux par fin d'exercice et
rien d'autre. Le normaliseur en deduit une borne superieure reglementaire, et
marque le fait comme estime : voir `normalizers/fundamentals.py` et la migration
011. C'est la faiblesse la plus serieuse du regime A, et elle est structurelle,
pas corrigeable par un meilleur code.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

TABLEAUX = ("income_stmt", "balance_sheet", "cashflow")


@dataclass(frozen=True)
class RawFundamentals:
    symbol: str
    tableaux: dict = field(default_factory=dict)   # nom -> pandas.DataFrame
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error and any(
            frame is not None and not frame.empty for frame in self.tableaux.values()
        )

    @property
    def exercices(self) -> list:
        dates = set()
        for frame in self.tableaux.values():
            if frame is not None and not frame.empty:
                dates.update(frame.columns)
        return sorted(dates, reverse=True)


def fetch_fundamentals(symbol: str, rate_limit_sec: float = 0.0,
                       max_retries: int = 3) -> RawFundamentals:
    """Recupere les trois etats financiers annuels. Ne leve pas.

    Comme pour les cours, une reponse vide est traitee comme un echec temporaire
    et non comme une absence de donnee : Yahoo rate-limite en renvoyant du vide.
    """
    import yfinance as yf

    tableaux: dict = {}
    error = ""
    for tentative in range(1, max_retries + 1):
        try:
            ticker = yf.Ticker(symbol)
            tableaux = {nom: getattr(ticker, nom) for nom in TABLEAUX}
            if any(f is not None and not f.empty for f in tableaux.values()):
                error = ""
                break
            error = "aucun etat financier"
        except Exception as exc:  # noqa: BLE001 - remonte au journal, pas en trace
            error = f"{type(exc).__name__}: {exc}"

        if tentative < max_retries:
            attente = (rate_limit_sec or 1.0) * (2 ** tentative)
            logger.warning("fondamentaux %s tentative %d/%d : %s, reprise dans %.1fs",
                           symbol, tentative, max_retries, error, attente)
            time.sleep(attente)

    if rate_limit_sec:
        time.sleep(rate_limit_sec)

    return RawFundamentals(symbol=symbol, tableaux=tableaux, error=error)
