"""Analyse quantitative des dividendes, rendements moyens et pérennité.

Ce module extrait et calcule les indicateurs clés pour les investisseurs de rendement :
1. Le DPA actuel et le DPA potentiel moyen (sur 3 et 5 ans) pour neutraliser les dividendes exceptionnels.
2. Le rendement actuel, le rendement potentiel moyen sur cours actuel et le rendement normalisé sur tendance (Yield on Trend).
3. La dynamique de croissance du dividende (CAGR 3a et 5a).
4. La pérennité / couverture du dividende par le Free Cash Flow (FCF Payout) et le résultat net.
5. La régularité historique (track record, années consécutives, baisses constatées).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass
class DividendeHistorique:
    annee: int
    montant_total: float
    nb_versements: int


@dataclass
class ProfilDividende:
    instrument_id: int
    internal_code: str
    name: str
    currency: str
    cours_actuel: float | None
    z_score: float | None
    fitted_value: float | None
    dernier_dpa: float | None
    dpa_moyen_3a: float | None
    dpa_moyen_5a: float | None
    rendement_actuel_pct: float | None
    rendement_moyen_5a_pct: float | None
    rendement_sur_tendance_pct: float | None
    croissance_dpa_3a_pct: float | None
    croissance_dpa_5a_pct: float | None
    annees_consecutives: int
    nb_baisses_5a: int
    fcf_dernier: float | None
    dividendes_verses_dernier: float | None
    payout_fcf_pct: float | None
    payout_rn_pct: float | None
    securite_verdict: str  # 'sécurisé' | 'soutenable' | 'tendu' | 'exceptionnel' | 'indéterminable'
    securite_motif: str
    historique_annuel: list[DividendeHistorique] = field(default_factory=list)


def calcul_cagr(valeur_debut: float | None, valeur_fin: float | None, annees: int) -> float | None:
    """Calcule le taux de croissance composé annualisé (CAGR)."""
    if (
        valeur_debut is None
        or valeur_fin is None
        or valeur_debut <= 0
        or valeur_fin <= 0
        or annees <= 0
    ):
        return None
    return (valeur_fin / valeur_debut) ** (1.0 / annees) - 1.0


def evalue_securite_dividende(
    dernier_dpa: float | None,
    dpa_moyen_5a: float | None,
    payout_fcf: float | None,
    payout_rn: float | None,
    nb_baisses_5a: int,
    fcf_negatif: bool = False,
) -> tuple[str, str]:
    """Détermine le verdict de sécurité et pérennité du dividende."""
    if dernier_dpa is None or dernier_dpa <= 0:
        return "sans_dividende", "Aucun dividende récent versé"

    # 1. Détection de dividende exceptionnel non reproductible
    if dpa_moyen_5a and dpa_moyen_5a > 0 and (dernier_dpa / dpa_moyen_5a) >= 1.8:
        return (
            "exceptionnel",
            f"Dernier DPA ({dernier_dpa:.2f}) très supérieur à la moyenne 5 ans ({dpa_moyen_5a:.2f}) : probable dividende exceptionnel",
        )

    # 2. FCF négatif : dividende financé par la trésorerie ou la dette
    if fcf_negatif:
        return "tendu", "Free Cash Flow négatif : dividende non autofinancé par l'exploitation"

    # 3. Payout ratios
    if payout_fcf is not None and payout_fcf > 1.0:
        return "tendu", f"Dividende supérieur au Free Cash Flow généré ({payout_fcf:.0%})"

    if payout_rn is not None and payout_rn > 0.95:
        return "tendu", f"Taux de distribution sur résultat net très élevé ({payout_rn:.0%})"

    if payout_fcf is not None and payout_fcf <= 0.65 and (payout_rn is None or payout_rn <= 0.70):
        if nb_baisses_5a == 0:
            return "sécurisé", f"Dividende bien couvert par le FCF ({payout_fcf:.0%}) et historique sans baisse sur 5 ans"
        return "sécurisé", f"Dividende confortablement couvert par le FCF ({payout_fcf:.0%})"

    if (payout_fcf is not None and payout_fcf <= 0.85) or (payout_rn is not None and payout_rn <= 0.85):
        return "soutenable", "Dividende soutenable avec une couverture FCF/RN modérée"

    if payout_fcf is None and payout_rn is None:
        if nb_baisses_5a == 0 and dpa_moyen_5a:
            return "soutenable", "Historique régulier (couverture FCF non calculable)"
        return "indéterminable", "Historique de comptes insuffisant pour évaluer la couverture FCF"

    return "soutenable", "Dividende dans la moyenne des ratios de distribution"


def analyse_dividendes_instrument(cur: Any, instrument_id: int, as_of: date | None = None) -> ProfilDividende | None:
    """Analyse complète du profil de dividende d'un instrument donné."""
    as_of = as_of or date.today()
    annee_courante = as_of.year

    # Récupérer l'instrument et son fit de régression
    cur.execute(
        """
        select i.id, i.internal_code, i.name, i.currency,
               f.last_close, f.z_score, f.fitted_value
          from instruments i
          left join regression_fits f
            on f.instrument_id = i.id
           and f.as_of_date = (select max(as_of_date) from regression_fits where instrument_id = i.id)
         where i.id = %(id)s
        """,
        {"id": instrument_id},
    )
    inst = cur.fetchone()
    if not inst:
        return None

    inst_id, code, nom, devise, cours, z_score, fitted_val = inst

    # Récupérer l'historique des dividendes
    cur.execute(
        """
        select extract(year from ex_date)::int as annee,
               sum(amount)::float as montant_total,
               count(*)::int as nb_versements
          from corporate_actions
         where instrument_id = %(id)s
           and action_type = 'cash_dividend'
           and ex_date <= %(as_of)s
         group by extract(year from ex_date)
         order by annee desc
        """,
        {"id": instrument_id, "as_of": as_of},
    )
    rows = cur.fetchall()
    if not rows:
        return ProfilDividende(
            instrument_id=inst_id,
            internal_code=code,
            name=nom,
            currency=devise,
            cours_actuel=cours,
            z_score=z_score,
            fitted_value=fitted_val,
            dernier_dpa=None,
            dpa_moyen_3a=None,
            dpa_moyen_5a=None,
            rendement_actuel_pct=None,
            rendement_moyen_5a_pct=None,
            rendement_sur_tendance_pct=None,
            croissance_dpa_3a_pct=None,
            croissance_dpa_5a_pct=None,
            annees_consecutives=0,
            nb_baisses_5a=0,
            fcf_dernier=None,
            dividendes_verses_dernier=None,
            payout_fcf_pct=None,
            payout_rn_pct=None,
            securite_verdict="sans_dividende",
            securite_motif="Aucun dividende dans l'historique",
            historique_annuel=[],
        )

    historique = [DividendeHistorique(annee=r[0], montant_total=r[1], nb_versements=r[2]) for r in rows]
    par_annee = {h.annee: h.montant_total for h in historique}

    # Dernier DPA (prendre année courante si déjà versé ou année précédente)
    dernier_dpa = par_annee.get(annee_courante) or par_annee.get(annee_courante - 1)
    if dernier_dpa is None and historique:
        dernier_dpa = historique[0].montant_total

    # DPA moyen sur 3 ans (ex: 2023, 2024, 2025)
    annees_3a = [par_annee[a] for a in range(annee_courante - 3, annee_courante) if a in par_annee]
    dpa_moyen_3a = (sum(annees_3a) / len(annees_3a)) if annees_3a else dernier_dpa

    # DPA moyen sur 5 ans
    annees_5a = [par_annee[a] for a in range(annee_courante - 5, annee_courante) if a in par_annee]
    dpa_moyen_5a = (sum(annees_5a) / len(annees_5a)) if annees_5a else dpa_moyen_3a

    # Croissance DPA (CAGR 3a et 5a)
    dpa_t0 = par_annee.get(annee_courante - 1) or dernier_dpa
    dpa_t_minus_3 = par_annee.get(annee_courante - 4) or par_annee.get(annee_courante - 3)
    dpa_t_minus_5 = par_annee.get(annee_courante - 6) or par_annee.get(annee_courante - 5)

    croissance_3a = calcul_cagr(dpa_t_minus_3, dpa_t0, 3)
    croissance_5a = calcul_cagr(dpa_t_minus_5, dpa_t0, 5)

    # Régularité et historique de versement consécutif
    annees_triees = sorted(par_annee.keys(), reverse=True)
    streak = 0
    annee_attendue = annees_triees[0] if annees_triees else annee_courante
    for a in annees_triees:
        if a == annee_attendue:
            streak += 1
            annee_attendue -= 1
        else:
            break

    # Baisses sur 5 ans
    nb_baisses = 0
    annees_rec = sorted([a for a in par_annee.keys() if a >= annee_courante - 5])
    for i in range(1, len(annees_rec)):
        if par_annee[annees_rec[i]] < par_annee[annees_rec[i - 1]] * 0.98:  # tolérance 2%
            nb_baisses += 1

    # Rendements
    rendement_actuel = ((dernier_dpa / cours) * 100.0) if (cours and dernier_dpa) else None
    rendement_moyen_5a = ((dpa_moyen_5a / cours) * 100.0) if (cours and dpa_moyen_5a) else None
    rendement_sur_tendance = ((dpa_moyen_5a / fitted_val) * 100.0) if (fitted_val and dpa_moyen_5a) else None

    # Données fondamentales : FCF, Résultat Net, Dividendes totaux versés
    cur.execute(
        """
        with faits as (
            select concept_code, value,
                   row_number() over (partition by concept_code order by period_end desc) as rn
              from financial_facts
             where instrument_id = %(id)s
               and period_type = 'FY'
               and published_at <= %(as_of)s
               and concept_code in ('fcf', 'net_income', 'dividends_paid')
        )
        select concept_code, value from faits where rn = 1
        """,
        {"id": instrument_id, "as_of": as_of},
    )
    faits_dict = {r[0]: float(r[1]) for r in cur.fetchall()}
    fcf = faits_dict.get("fcf")
    net_income = faits_dict.get("net_income")
    div_paid = faits_dict.get("dividends_paid")

    payout_fcf = (abs(div_paid) / fcf) if (fcf and div_paid and fcf > 0) else None
    payout_rn = (abs(div_paid) / net_income) if (net_income and div_paid and net_income > 0) else None
    fcf_negatif = (fcf is not None and fcf < 0)

    verdict, motif = evalue_securite_dividende(
        dernier_dpa=dernier_dpa,
        dpa_moyen_5a=dpa_moyen_5a,
        payout_fcf=payout_fcf,
        payout_rn=payout_rn,
        nb_baisses_5a=nb_baisses,
        fcf_negatif=fcf_negatif,
    )

    return ProfilDividende(
        instrument_id=inst_id,
        internal_code=code,
        name=nom,
        currency=devise,
        cours_actuel=cours,
        z_score=z_score,
        fitted_value=fitted_val,
        dernier_dpa=round(dernier_dpa, 4) if dernier_dpa else None,
        dpa_moyen_3a=round(dpa_moyen_3a, 4) if dpa_moyen_3a else None,
        dpa_moyen_5a=round(dpa_moyen_5a, 4) if dpa_moyen_5a else None,
        rendement_actuel_pct=round(rendement_actuel, 2) if rendement_actuel else None,
        rendement_moyen_5a_pct=round(rendement_moyen_5a, 2) if rendement_moyen_5a else None,
        rendement_sur_tendance_pct=round(rendement_sur_tendance, 2) if rendement_sur_tendance else None,
        croissance_dpa_3a_pct=round(croissance_3a * 100.0, 2) if croissance_3a is not None else None,
        croissance_dpa_5a_pct=round(croissance_5a * 100.0, 2) if croissance_5a is not None else None,
        annees_consecutives=streak,
        nb_baisses_5a=nb_baisses,
        fcf_dernier=fcf,
        dividendes_verses_dernier=div_paid,
        payout_fcf_pct=round(payout_fcf * 100.0, 1) if payout_fcf is not None else None,
        payout_rn_pct=round(payout_rn * 100.0, 1) if payout_rn is not None else None,
        securite_verdict=verdict,
        securite_motif=motif,
        historique_annuel=historique,
    )


SQL_SCREENER_DIVIDENDES = """
-- Exclut les foncieres au regime fiscal exonere d'IS (SIIC et equivalents
-- europeens : SOCIMI, SIR/GVV, FBI, G-REIT, SIIQ), incompatible avec le PEA
-- depuis la loi de finances 2012 - meme logique que dashboard/data.py::screener.
with div_annuels as (
    select c.instrument_id,
           extract(year from c.ex_date)::int as annee,
           sum(c.amount)::float as dpa_an
      from corporate_actions c
     where c.action_type = 'cash_dividend'
       and c.ex_date <= %(as_of)s
     group by c.instrument_id, extract(year from c.ex_date)
),
div_stats as (
    select instrument_id,
           count(distinct annee)::int as total_annees_div,
           avg(dpa_an) filter (where annee >= extract(year from %(as_of)s)::int - 5 and annee < extract(year from %(as_of)s)::int) as dpa_moyen_5a,
           avg(dpa_an) filter (where annee >= extract(year from %(as_of)s)::int - 3 and annee < extract(year from %(as_of)s)::int) as dpa_moyen_3a,
           coalesce(
               max(dpa_an) filter (where annee = extract(year from %(as_of)s)::int),
               max(dpa_an) filter (where annee = extract(year from %(as_of)s)::int - 1)
           ) as dernier_dpa
      from div_annuels
     group by instrument_id
),
derniers_faits as (
    select instrument_id,
           max(value) filter (where concept_code = 'fcf') as fcf,
           max(value) filter (where concept_code = 'net_income') as net_income,
           abs(max(value) filter (where concept_code = 'dividends_paid')) as dividends_paid
      from (
          select instrument_id, concept_code, value,
                 row_number() over (partition by instrument_id, concept_code order by period_end desc) as rn
            from financial_facts
           where period_type = 'FY'
             and published_at <= %(as_of)s
             and concept_code in ('fcf', 'net_income', 'dividends_paid')
      ) f
     where rn = 1
     group by instrument_id
)
select i.internal_code,
       i.name,
       i.isin,
       i.country_iso2,
       s.label as secteur,
       i.currency,
       f.last_close,
       f.z_score,
       f.slope_annual,
       f.r_squared,
       f.fitted_value,
       f.half_life_days,
       coalesce(q.quality_tier, 'unqualified') as quality_tier,
       st.dernier_dpa,
       st.dpa_moyen_3a,
       st.dpa_moyen_5a,
       (st.dernier_dpa / nullif(f.last_close, 0)) * 100.0 as rendement_actuel_pct,
       (coalesce(st.dpa_moyen_5a, st.dernier_dpa) / nullif(f.last_close, 0)) * 100.0 as rendement_moyen_5a_pct,
       (coalesce(st.dpa_moyen_5a, st.dernier_dpa) / nullif(f.fitted_value, 0)) * 100.0 as rendement_sur_tendance_pct,
       st.total_annees_div,
       df.fcf,
       df.net_income,
       df.dividends_paid,
       (df.dividends_paid / nullif(df.fcf, 0)) * 100.0 as payout_fcf_pct,
       (df.dividends_paid / nullif(df.net_income, 0)) * 100.0 as payout_rn_pct
  from div_stats st
  join instruments i on i.id = st.instrument_id
  join regression_fits f
    on f.instrument_id = i.id
   and f.as_of_date = %(as_of)s
  left join sectors s on s.code = i.sector_code
  left join quality_scores q
    on q.instrument_id = i.id
   and q.as_of_date = (select max(as_of_date) from quality_scores where instrument_id = i.id)
  left join derniers_faits df on df.instrument_id = i.id
 where i.is_active
   and i.asset_class in ('equity', 'dividend_stock')
   and (i.attributes ->> 'pea_eligible') is distinct from 'false'
   and st.dernier_dpa is not null
   and st.dernier_dpa > 0
 order by rendement_actuel_pct desc nulls last;
"""
