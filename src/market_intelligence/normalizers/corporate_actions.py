"""Normalisation des operations sur titre et du nombre d'actions."""

from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class NormalizedActions:
    actions: list[dict] = field(default_factory=list)
    shares: list[dict] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)


def _valid(value) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def normalize(raw, instrument_id: int, source_id: int, currency: str) -> NormalizedActions:
    """Convertit les series yfinance en lignes de `corporate_actions` et
    `shares_outstanding`.

    Les ratios de split sont conserves tels quels, y compris les 1.1 des
    attributions d'actions gratuites - Air Liquide en distribue une tous les deux
    ans. Ce ne sont pas des splits au sens strict, mais l'effet sur le cours est
    identique et le provider les sert dans le meme flux.
    """
    out = NormalizedActions()

    if raw.splits is not None and len(raw.splits):
        for index, value in raw.splits.items():
            ratio = _valid(value)
            if ratio is None or ratio <= 0:
                out.rejected.append({"kind": "split", "reason": "ratio_invalide",
                                     "value": str(value)})
                continue
            out.actions.append({
                "instrument_id": instrument_id,
                "action_type": "reverse_split" if ratio < 1 else "split",
                "ex_date": index.date(),
                "ratio": ratio,
                "amount": None,
                "currency": None,
                "source_id": source_id,
            })

    if raw.dividends is not None and len(raw.dividends):
        for index, value in raw.dividends.items():
            amount = _valid(value)
            if amount is None or amount <= 0:
                out.rejected.append({"kind": "dividend", "reason": "montant_invalide",
                                     "value": str(value)})
                continue
            out.actions.append({
                "instrument_id": instrument_id,
                "action_type": "cash_dividend",
                "ex_date": index.date(),
                "ratio": None,
                "amount": amount,
                "currency": currency,
                "source_id": source_id,
            })

    if raw.shares is not None and len(raw.shares):
        # Deux passes, et l'ordre compte.
        #
        # 1. Le provider horodate a la seconde et peut rendre plusieurs valeurs
        #    le meme jour. `shares_outstanding` a pour cle (instrument, date) :
        #    on retient la derniere de la journee, tant que l'heure est encore
        #    la pour en decider. Deduplique plus tard, en base, il faudrait
        #    choisir au hasard.
        par_jour: dict = {}
        for index, value in raw.shares.items():
            count = _valid(value)
            if count is None or count <= 0:
                out.rejected.append({"kind": "shares", "reason": "nombre_invalide",
                                     "value": str(value)})
                continue
            par_jour[index.date()] = int(count)

        # 2. Le provider repete ensuite la meme valeur des dizaines de fois. Seuls
        #    les changements portent l'information de dilution, et n'en garder que
        #    ceux-la divise le volume par un facteur dix.
        precedent = None
        for as_of in sorted(par_jour):
            count = par_jour[as_of]
            if count == precedent:
                continue
            precedent = count
            out.shares.append({
                "instrument_id": instrument_id,
                "as_of": as_of,
                "shares": count,
                "source_id": source_id,
            })

    # Meme precaution sur les operations : deux lignes identiques dans un meme
    # COPY feraient echouer le ON CONFLICT (une commande ne peut pas toucher la
    # meme ligne deux fois).
    vues = set()
    uniques = []
    for action in out.actions:
        cle = (action["action_type"], action["ex_date"],
               action["ratio"] or 0, action["amount"] or 0)
        if cle in vues:
            out.rejected.append({"kind": "action", "reason": "doublon", "cle": str(cle)})
            continue
        vues.add(cle)
        uniques.append(action)
    out.actions = uniques

    return out
