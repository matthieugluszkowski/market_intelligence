"""Collecteur de cours yfinance.

Regle du doc 02 SS4.1 : *un collector ne valide rien et ne transforme rien*. Il
recupere et rend le brut. La normalisation et les controles vivent ailleurs, pour
qu'on puisse les rejouer sans retelecharger.

Ecart assume au principe P4, a connaitre avant de lire la suite
-----------------------------------------------------------------
P4 veut le cours non ajuste. Yahoo ne le sert pas : sa colonne `Close` est
**retro-ajustee des splits** - verifie sur Dassault Systemes, qui cotait environ
133 EUR en juin 2019 et que l'API renvoie a 26,70 EUR, soit divise par le 5 pour 1
de juillet 2021. Le cours nominal d'epoque n'est disponible chez aucune source
gratuite.

On stocke donc `Close`, et jamais `Adj Close`. Ce n'est pas un detail de
commodite : ce que P4 protege, c'est la reproductibilite, et les deux colonnes ne
s'y comportent pas du tout pareil.

- `Adj Close` est recalcule **a chaque detachement de dividende**, plusieurs fois
  par an. Une regression lancee en janvier et relancee en juin ne donne pas le
  meme resultat, et rien ne le signale.
- `Close` ne bouge **qu'aux splits**, soit deux fois en douze ans sur Dassault.
  Et quand il bouge, le chargeur le detecte et l'inscrit dans
  `data_quality_issues` - voir `loaders/bars.py`.

Le prix a payer est reel et doit rester visible : les splits anterieurs a la
premiere ingestion sont deja incorpores dans la serie, `adjustment_factors` ne
les rejouera pas, et une comparaison au graphe d'un fournisseur qui affiche le
cours nominal sera decalee d'un facteur constant.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import date

logger = logging.getLogger(__name__)

# Correspondance frequence canonique -> intervalle yfinance.
INTERVALS = {"1d": "1d", "1w": "1wk", "1mo": "1mo"}


@dataclass(frozen=True)
class RawBars:
    """Ce que le provider a renvoye, tel quel."""

    symbol: str
    freq: str
    frame: object          # pandas.DataFrame
    fetched_at: float
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error and self.frame is not None and len(self.frame) > 0


def fetch_bars(
    symbol: str,
    freq: str = "1w",
    start: date | None = None,
    rate_limit_sec: float = 0.0,
    max_retries: int = 3,
) -> RawBars:
    """Recupere l'historique brut d'un symbole. Ne leve pas : l'erreur est portee.

    Une reponse vide est traitee comme un echec temporaire, pas comme une absence
    de donnee. Yahoo rate-limite le backfill - risque note comme eleve au doc 05
    SS4 - et le fait en renvoyant un DataFrame vide plutot qu'une erreur franche.
    Sans reprise, on inscrirait un titre comme depourvu d'historique alors qu'il
    a simplement ete refuse, et le lot L4 le classerait `rejected` a tort.

    Args:
        symbol: symbole yfinance, par exemple 'MC.PA'.
        freq: '1d', '1w' ou '1mo' (frequence canonique, pas l'intervalle yfinance).
        start: date de debut ; None pour tout l'historique disponible.
        rate_limit_sec: pause apres l'appel, pour menager le debit.
        max_retries: nombre de tentatives avant d'abandonner.
    """
    import yfinance as yf

    if freq not in INTERVALS:
        raise ValueError(f"frequence inconnue : {freq!r}, attendu {sorted(INTERVALS)}")

    kwargs = {
        "interval": INTERVALS[freq],
        "auto_adjust": False,   # ne pas laisser yfinance appliquer les dividendes
        "back_adjust": False,
        "actions": False,
        "raise_errors": False,
    }
    if start is None:
        kwargs["period"] = "max"
    else:
        kwargs["start"] = start.isoformat()

    error = ""
    frame = None
    for attempt in range(1, max_retries + 1):
        try:
            frame = yf.Ticker(symbol).history(**kwargs)
            if frame is not None and len(frame) > 0:
                error = ""
                break
            error = "reponse vide"
        except Exception as exc:  # noqa: BLE001 - l'erreur remonte au journal, pas en trace
            error = f"{type(exc).__name__}: {exc}"

        if attempt < max_retries:
            backoff = rate_limit_sec * (2 ** attempt) if rate_limit_sec else 2 ** attempt
            logger.warning("yfinance %s %s tentative %d/%d : %s, reprise dans %.1fs",
                           symbol, freq, attempt, max_retries, error, backoff)
            time.sleep(backoff)

    if rate_limit_sec:
        time.sleep(rate_limit_sec)

    return RawBars(symbol=symbol, freq=freq, frame=frame, fetched_at=time.time(), error=error)
