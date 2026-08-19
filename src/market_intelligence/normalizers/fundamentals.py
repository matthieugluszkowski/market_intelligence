"""Normalisation des fondamentaux : libelles provider -> concepts canoniques.

Deux decisions portees ici, et la seconde est la plus importante du lot.

Ordre de preference entre libelles
-----------------------------------
Plusieurs libelles peuvent pointer vers un meme concept - `EBIT` et
`Operating Income` valent tous deux `ebit`. On retient le premier trouve dans un
ordre explicite, pour qu'un libelle de repli n'ecrase jamais une valeur plus
fiable. Sans cet ordre, le resultat dependrait de l'ordre des lignes du
DataFrame, c'est-a-dire du hasard.

Date de publication : une borne superieure, jamais period_end
--------------------------------------------------------------
yfinance ne sert aucune date de publication. On ne peut pas pour autant laisser
`published_at` vide - le calcul point-in-time du doc 03 SS7.1 n'utilise que les
faits dont `published_at <= as_of_date`, et un fait sans date en serait exclu
pour toujours.

On estime donc une borne superieure a partir du delai reglementaire : la
directive Transparence impose aux emetteurs europeens quatre mois pour les
comptes annuels, trois pour les semestriels.

**L'asymetrie est ce qui rend l'estimation acceptable.** Errer TARD ne produit
qu'un exces de prudence : on s'interdit d'utiliser un fait qu'on connaissait
deja, et le screener est simplement en retard d'un trimestre. Errer TOT fabrique
du look-ahead, et il est invisible. On erre donc deliberement du cote tardif, et
`published_at_estimated` garde la trace pour le jour ou une source servira les
vraies dates.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta

# Directive Transparence 2004/109/CE, article 4 : quatre mois pour le rapport
# financier annuel. On prend la borne pleine, pas une moyenne observee.
DELAI_ANNUEL_JOURS = 122
DELAI_SEMESTRIEL_JOURS = 92

# Ordre de preference quand plusieurs libelles pointent vers le meme concept.
# Le premier present gagne.
PREFERENCE = {
    "revenue": ["Total Revenue", "Operating Revenue"],
    "cost_of_revenue": ["Cost Of Revenue", "Reconciled Cost Of Revenue"],
    "ebit": ["EBIT", "Operating Income"],
    "ebitda": ["EBITDA", "Normalized EBITDA"],
    "net_income": ["Net Income", "Net Income Common Stockholders"],
    "total_equity": ["Stockholders Equity", "Total Equity Gross Minority Interest"],
    "cash_and_equivalents": ["Cash And Cash Equivalents",
                             "Cash Cash Equivalents And Short Term Investments"],
    "shares_basic": ["Ordinary Shares Number", "Share Issued"],
    "cfo": ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities"],
    "dividends_paid": ["Cash Dividends Paid", "Common Stock Dividend Paid"],
}

# Concepts servis en valeur negative par le provider et stockes en positif,
# conformement a `financial_concepts.sign_convention`.
A_INVERSER = {"capex", "dividends_paid", "buybacks"}


@dataclass
class NormalizedFundamentals:
    facts: list[dict] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)
    exercices: set = field(default_factory=set)


def date_de_publication_estimee(period_end: date, period_type: str = "FY") -> date:
    """Borne superieure : la date a laquelle l'information etait certainement la."""
    delai = DELAI_ANNUEL_JOURS if period_type == "FY" else DELAI_SEMESTRIEL_JOURS
    return period_end + timedelta(days=delai)


def _valide(valeur) -> float | None:
    try:
        f = float(valeur)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def normalize(raw, instrument_id: int, source_id: int, currency: str,
              mappings: dict[str, str]) -> NormalizedFundamentals:
    """Convertit les tableaux yfinance en lignes de `financial_facts`.

    Args:
        mappings: libelle provider -> code de concept, lu depuis `concept_mappings`.
    """
    out = NormalizedFundamentals()
    if not raw.ok:
        return out

    # Un concept peut apparaitre dans plusieurs tableaux avec des libelles
    # differents : on collecte tout, puis on arbitre par l'ordre de preference.
    candidats: dict = {}
    for frame in raw.tableaux.values():
        if frame is None or frame.empty:
            continue
        for libelle in frame.index:
            concept = mappings.get(str(libelle))
            if concept is None:
                continue
            for colonne in frame.columns:
                try:
                    period_end = colonne.date()
                except AttributeError:
                    out.rejected.append({"reason": "exercice_illisible",
                                         "colonne": str(colonne)})
                    continue
                valeur = _valide(frame.loc[libelle, colonne])
                if valeur is None:
                    continue
                candidats.setdefault((concept, period_end), []).append(
                    (str(libelle), valeur)
                )

    for (concept, period_end), propositions in candidats.items():
        ordre = PREFERENCE.get(concept, [])
        propositions.sort(
            key=lambda p: ordre.index(p[0]) if p[0] in ordre else len(ordre)
        )
        libelle, valeur = propositions[0]

        if concept in A_INVERSER:
            valeur = abs(valeur)

        out.exercices.add(period_end)
        out.facts.append({
            "instrument_id": instrument_id,
            "concept_code": concept,
            "period_end": period_end,
            "period_type": "FY",
            "value": valeur,
            "currency": currency,
            "published_at": date_de_publication_estimee(period_end, "FY"),
            "published_at_estimated": True,
            "source_id": source_id,
            "confidence": 1.0,   # valeur structuree du provider, pas une extraction
        })

    return out
