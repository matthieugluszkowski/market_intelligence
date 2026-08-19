"""Ratios fondamentaux en point-in-time, et verdict de coherence prix/fondamentaux.

    « une fois que tu as vu qu'il y avait un signal de prix, tu verifies que
      c'est coherent avec les fondamentaux »  - Marie de Raismes

Le point-in-time n'est pas une precaution decorative
-----------------------------------------------------
On n'utilise que les faits dont `published_at <= as_of_date`. Les comptes 2024
d'une societe ne sont connus qu'en mars 2025 ; les utiliser pour juger le titre
en janvier 2025 est du look-ahead pur, et il ne se voit jamais dans un resultat.

Les dates de publication du regime A sont **estimees** - yfinance ne les sert pas
- et errent volontairement du cote tardif (voir `normalizers/fundamentals.py`).
Consequence a assumer : le systeme s'interdit parfois un fait qu'il connaissait
deja. C'est le bon sens de l'erreur.

Ce que ce module est, et ce qu'il n'est pas
--------------------------------------------
C'est un **filtre de solvabilite**, pas un jugement de qualite. Une entreprise
peut cocher toutes ces cases et perdre sa position concurrentielle - c'est
l'objet du lot L6b, et c'est la moitie de la methode qui manque encore.

Les banques et les assureurs, ou plusieurs ratios n'ont pas de sens
-------------------------------------------------------------------
Constate en recoupant : Allianz ressort a 25% d'ecart sur la marge nette, la ou
les industriels tombent a 0,0%. Ce n'est pas une erreur de calcul, c'est que la
notion de « chiffre d'affaires » n'a pas de definition stable pour un assureur -
primes brutes, primes acquises, produit net bancaire, chaque agregateur choisit
autrement.

Sont donc marques non pertinents pour le secteur financier : marge brute,
operationnelle et nette, EV/CA, EV/EBIT, dette nette sur EBITDA et gearing. Une
banque a structurellement un levier de 15 a 20, ce qui la ferait sortir en
`suspect` a chaque passage pour une raison qui n'en est pas une.

Les ratios qui gardent leur sens - PER, P/B, ROE, croissance, distribution -
restent calcules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

# Seuils du doc 03 SS7.2. Ceux qui sont arbitraires sont signales comme tels.
DETTE_SUR_EBITDA_MAX = 4.0
EXERCICES_RENTABLES_MIN = 3
EXERCICES_EXAMINES = 5
DILUTION_NETTE_MAX = 0.05      # +5% d'actions sur la periode, arbitraire

# Secteur ICB 30 = Financials. Les ratios adosses au chiffre d'affaires ou au
# levier n'y ont pas de sens : voir l'entete du module.
SECTEUR_FINANCIER = "30"
RATIOS_SANS_SENS_EN_FINANCE = (
    "marge_brute", "marge_operationnelle", "marge_nette",
    "ev_revenue", "ev_ebit", "dette_nette_sur_ebitda", "gearing",
    "couverture_interets",
)

FAITS = """
select concept_code, period_end, value, published_at, published_at_estimated
  from financial_facts
 where instrument_id = %(instrument_id)s
   and period_type = 'FY'
   and published_at <= %(as_of)s
 order by period_end;
"""


@dataclass
class Fondamentaux:
    """Serie annuelle d'un instrument, connue a une date donnee."""

    par_concept: dict = field(default_factory=dict)   # concept -> {period_end: valeur}
    exercices: list = field(default_factory=list)
    estimes: bool = False

    def serie(self, concept: str) -> list[tuple]:
        valeurs = self.par_concept.get(concept, {})
        return [(e, valeurs[e]) for e in self.exercices if e in valeurs]

    def dernier(self, concept: str) -> float | None:
        serie = self.serie(concept)
        return serie[-1][1] if serie else None

    def n_exercices(self, concept: str) -> int:
        return len(self.serie(concept))


def charge(cur, instrument_id: int, as_of: date) -> Fondamentaux:
    cur.execute(FAITS, {"instrument_id": instrument_id, "as_of": as_of})
    lignes = cur.fetchall()
    out = Fondamentaux()
    for concept, period_end, valeur, _publie, estime in lignes:
        out.par_concept.setdefault(concept, {})[period_end] = float(valeur)
        out.estimes = out.estimes or estime
    out.exercices = sorted({e for v in out.par_concept.values() for e in v})
    return out


def _div(numerateur, denominateur) -> float | None:
    if numerateur is None or denominateur is None or denominateur == 0:
        return None
    return numerateur / denominateur


def _croissance(serie: list[tuple], annees: int) -> float | None:
    """Taux de croissance annualise sur la fenetre, si elle est disponible."""
    if len(serie) < annees + 1:
        return None
    debut, fin = serie[-(annees + 1)][1], serie[-1][1]
    if debut is None or debut <= 0 or fin is None or fin <= 0:
        return None
    return (fin / debut) ** (1 / annees) - 1


def ratios(f: Fondamentaux, capitalisation: float | None = None,
           cours: float | None = None, sector_code: str | None = None) -> dict:
    """Les cinq familles du doc 03 SS7.1.

    Les ratios de valorisation exigent la capitalisation ; sans elle ils sortent
    a None plutot qu'a une valeur approchee. Un ratio faux est pire qu'un ratio
    absent - il se compare, se trie et se decide.
    """
    revenue = f.dernier("revenue")
    ebit = f.dernier("ebit")
    ebitda = f.dernier("ebitda")
    net_income = f.dernier("net_income")
    equity = f.dernier("total_equity")
    net_debt = f.dernier("net_debt")
    total_debt = f.dernier("total_debt")
    cash = f.dernier("cash_and_equivalents")
    fcf = f.dernier("fcf")
    interets = f.dernier("interest_expense")
    dividendes = f.dernier("dividends_paid")
    invested = f.dernier("invested_capital")
    impots = f.dernier("tax_expense")
    resultat_avant_impot = None
    if ebit is not None and interets is not None:
        resultat_avant_impot = ebit - interets

    if net_debt is None and total_debt is not None and cash is not None:
        net_debt = total_debt - cash

    valeur_entreprise = None
    if capitalisation is not None and net_debt is not None:
        valeur_entreprise = capitalisation + net_debt

    taux_impot = _div(impots, resultat_avant_impot)
    nopat = ebit * (1 - taux_impot) if (ebit is not None and taux_impot is not None
                                        and 0 <= taux_impot <= 0.6) else None

    calcules = {
        # --- valorisation ---
        "per": _div(capitalisation, net_income),
        "ev_ebit": _div(valeur_entreprise, ebit),
        "ev_revenue": _div(valeur_entreprise, revenue),
        "price_to_book": _div(capitalisation, equity),
        "fcf_yield": _div(fcf, capitalisation),
        "dividend_yield": _div(dividendes, capitalisation),
        # --- rentabilite ---
        "marge_operationnelle": _div(ebit, revenue),
        "marge_nette": _div(net_income, revenue),
        "marge_brute": _div(f.dernier("gross_profit"), revenue),
        "roe": _div(net_income, equity),
        "roce": _div(ebit, invested),
        "roic": _div(nopat, invested),
        # --- solidite ---
        "dette_nette_sur_ebitda": _div(net_debt, ebitda),
        "couverture_interets": _div(ebit, interets),
        "gearing": _div(net_debt, equity),
        # --- dynamique ---
        "croissance_ca_3a": _croissance(f.serie("revenue"), 3),
        "croissance_ca_5a": _croissance(f.serie("revenue"), 5),
        "croissance_rn_3a": _croissance(f.serie("net_income"), 3),
        # --- distribution ---
        "taux_de_distribution": _div(dividendes, net_income),
        "dilution_nette": _croissance(f.serie("shares_basic"), 3),
        # --- tracabilite ---
        "n_exercices": len(f.exercices),
        "dates_estimees": f.estimes,
    }

    # Un ratio sans signification est mis a None, pas laisse a sa valeur : une
    # valeur affichee se compare, se trie et se decide, meme accompagnee d'une
    # note en petits caracteres.
    if sector_code == SECTEUR_FINANCIER:
        for cle in RATIOS_SANS_SENS_EN_FINANCE:
            calcules[cle] = None
        calcules["secteur_financier"] = True

    return calcules


@dataclass
class Coherence:
    verdict: str                       # 'confirme' | 'suspect' | 'indeterminable'
    criteres: dict = field(default_factory=dict)
    echecs: list = field(default_factory=list)
    manquants: list = field(default_factory=list)


def coherence_prix_fondamentaux(f: Fondamentaux, r: dict) -> Coherence:
    """Doc 03 SS7.2.

    **Sortir les signaux suspects est aussi utile que sortir les bons.** C'est la
    liste des titres qui ont l'air decotes et ne le sont pas - et c'est la qu'on
    perd de l'argent.

    Un critere qu'on ne peut pas evaluer n'est pas un critere reussi : il sort en
    `manquants` et, s'il y en a, le verdict est `indeterminable` plutot que
    `confirme`. Traiter l'absence de donnee comme un succes est la facon la plus
    courante de fabriquer un faux signal.
    """
    criteres: dict = {}
    manquants: list = []

    # 1. Chiffre d'affaires non decroissant sur 3 ans
    croissance = r.get("croissance_ca_3a")
    if croissance is None:
        manquants.append("croissance_ca_3a")
    else:
        criteres["ca_non_decroissant"] = croissance >= 0

    # 2. Resultat operationnel positif sur au moins 3 des 5 derniers exercices
    serie_ebit = f.serie("ebit")[-EXERCICES_EXAMINES:]
    if len(serie_ebit) < EXERCICES_RENTABLES_MIN:
        manquants.append("ebit_positif_3_sur_5")
    else:
        positifs = sum(1 for _, v in serie_ebit if v > 0)
        criteres["ebit_positif_3_sur_5"] = positifs >= EXERCICES_RENTABLES_MIN

    # 3. Dette nette / EBITDA < 4. Sans objet pour une banque ou un assureur :
    # un levier de 15 a 20 y est structurel et ne dit rien de la solvabilite.
    levier = r.get("dette_nette_sur_ebitda")
    if r.get("secteur_financier"):
        criteres["levier_maitrise"] = True
    elif levier is None:
        manquants.append("levier")
    else:
        # Une dette nette negative est une tresorerie nette : le critere est tenu.
        criteres["levier_maitrise"] = levier < DETTE_SUR_EBITDA_MAX

    # 4. Aucune dilution nette significative
    dilution = r.get("dilution_nette")
    if dilution is None:
        manquants.append("dilution_nette")
    else:
        criteres["pas_de_dilution"] = dilution <= DILUTION_NETTE_MAX

    echecs = [nom for nom, ok in criteres.items() if not ok]
    if echecs:
        verdict = "suspect"
    elif manquants:
        verdict = "indeterminable"
    else:
        verdict = "confirme"

    return Coherence(verdict=verdict, criteres=criteres, echecs=echecs,
                     manquants=manquants)
