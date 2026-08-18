"""Normalisation des barres : brut du provider -> schema canonique.

Aucune logique metier ici, aucune requete. Un DataFrame yfinance entre, des
lignes pretes pour `bars` sortent, plus le compte de ce qui a ete ecarte.

Les lignes ecartees ne sont pas jetees silencieusement : elles remontent au
job, qui les inscrit dans `data_quality_issues` (doc 02 SS4.3, quarantaine
plutot que rejet).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date


@dataclass
class NormalizedBars:
    rows: list[dict] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.rows)


def _finite(value) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def normalize(frame, instrument_id: int, freq: str, source_id: int) -> NormalizedBars:
    """Convertit un DataFrame yfinance en lignes de `bars`.

    Regles d'ecartement, toutes signalees :
    - `close` absent ou non fini : la barre n'a pas de valeur exploitable ;
    - `close` <= 0 : un cours nul ou negatif n'a pas de sens sur une action, et
      le log-lineaire du lot L4 exploserait dessus ;
    - date non convertible.

    Les extremes incoherents (`high` < `low`) sont conserves mais signales : la
    barre reste utilisable par sa cloture, seule valeur dont depend la regression.
    """
    out = NormalizedBars()
    if frame is None or len(frame) == 0:
        return out

    columns = {c.lower(): c for c in frame.columns}
    col_open = columns.get("open")
    col_high = columns.get("high")
    col_low = columns.get("low")
    col_close = columns.get("close")
    col_volume = columns.get("volume")

    if col_close is None:
        out.rejected.append({"reason": "colonne_close_absente", "columns": list(frame.columns)})
        return out

    for index, row in frame.iterrows():
        try:
            ts: date = index.date()
        except AttributeError:
            out.rejected.append({"reason": "date_illisible", "index": str(index)})
            continue

        close = _finite(row[col_close])
        if close is None:
            out.rejected.append({"reason": "close_absent", "ts": ts.isoformat()})
            continue
        if close <= 0:
            out.rejected.append({"reason": "close_non_positif", "ts": ts.isoformat(), "close": close})
            continue

        high = _finite(row[col_high]) if col_high else None
        low = _finite(row[col_low]) if col_low else None
        if high is not None and low is not None and high < low:
            out.rejected.append({"reason": "extremes_incoherents", "ts": ts.isoformat(),
                                 "high": high, "low": low, "conserve": True})

        volume = _finite(row[col_volume]) if col_volume else None

        out.rows.append({
            "instrument_id": instrument_id,
            "freq": freq,
            "ts": ts,
            "open": _finite(row[col_open]) if col_open else None,
            "high": high,
            "low": low,
            "close": close,
            "volume": int(volume) if volume is not None else None,
            "source_id": source_id,
        })

    return out
