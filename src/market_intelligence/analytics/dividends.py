"""Analyse quantitative des dividendes, rendements moyens et pérennité.

Ce module extrait et calcule les indicateurs clés pour les investisseurs de rendement :
1. La grille d'évaluation des 11 règles d'investissement en actions à dividende (Investing.com & Morningstar).
2. Le DPA actuel et le DPA potentiel moyen (sur 3 et 5 ans) pour neutraliser les dividendes exceptionnels.
3. Le rendement actuel, le rendement potentiel moyen sur cours actuel et le rendement normalisé sur tendance.
4. La dynamique de croissance du dividende (CAGR 3a et 5a).
5. La pérennité / couverture du dividende par le Free Cash Flow (FCF Payout) et le résultat net.
6. La régularité historique (track record, années consécutives, baisses constatées).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass
class RegleDividende:
    numero: int
    nom: str
    est_capitale: bool
    seuil_requis: str
    valeur_observee: str
    passe: bool
    explication: str
    source_info: str


@dataclass
class ScoreDividende11Regles:
    total_oui: int
    total_non: int
    total_capitaux_oui: int
    total_capitaux: int
    est_investissable: bool
    verdict: str
    synthese_explication: str
    regles: list[RegleDividende] = field(default_factory=list)


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
    score_11_regles: ScoreDividende11Regles | None = None


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


def evalue_11_regles_dividende(
    cours: float | None,
    slope_annual: float | None,
    dernier_dpa: float | None,
    dpa_moyen_5a: float | None,
    streak_annees: int,
    facts_series: dict[str, list[tuple[date, float]]],
    quality_tier: str = "unqualified",
    secteur_nom: str = "",
) -> ScoreDividende11Regles:
    """Évalue les 11 règles d'investissement de la stratégie action à dividende."""
    regles: list[RegleDividende] = []

    # Extraire les derniers faits comptables
    def dernier_fait(code: str) -> float | None:
        serie = facts_series.get(code, [])
        return serie[-1][1] if serie else None

    revenue = dernier_fait("revenue")
    ebit = dernier_fait("ebit")
    interets = dernier_fait("interest_expense") or 0.0
    net_income = dernier_fait("net_income")
    equity = dernier_fait("total_equity")
    total_debt = dernier_fait("total_debt")
    net_debt = dernier_fait("net_debt")
    shares = dernier_fait("shares_basic") or dernier_fait("shares_diluted")

    # Capitalisation estimée
    capitalisation = (cours * shares) if (cours and shares and shares > 0) else None

    # 1. Règle 1 (CAPITALE) : +5% de dividendes versés chaque année
    rdt_actuel = ((dernier_dpa / cours) * 100.0) if (cours and dernier_dpa and cours > 0) else None
    passe_1 = (rdt_actuel is not None and rdt_actuel >= 5.0)
    regles.append(
        RegleDividende(
            numero=1,
            nom="Rendement du dividende ≥ 5 %",
            est_capitale=True,
            seuil_requis="≥ 5.0 %",
            valeur_observee=f"{rdt_actuel:.2f} %" if rdt_actuel is not None else "n/d",
            passe=passe_1,
            explication=(
                f"Le rendement actuel ressort à {rdt_actuel:.2f} % (≥ 5.0 % requis)."
                if passe_1
                else f"Le rendement actuel ({rdt_actuel:.2f} % si disponible) est inférieur au seuil de 5.0 %."
                if rdt_actuel is not None
                else "Rendement non calculable (aucun dividende récent ou cours manquant)."
            ),
            source_info="Investing.com > Principaux > Rendement de dividendes (%)",
        )
    )

    # 2. Règle 2 : PER compris entre 3 et 14
    per = (capitalisation / net_income) if (capitalisation and net_income and net_income > 0) else None
    passe_2 = (per is not None and 3.0 <= per <= 14.0)
    regles.append(
        RegleDividende(
            numero=2,
            nom="PER compris entre 3 et 14",
            est_capitale=False,
            seuil_requis="3.0 ≤ PER ≤ 14.0",
            valeur_observee=f"{per:.1f}x" if per is not None else "n/d",
            passe=passe_2,
            explication=(
                f"PER attractif et modéré à {per:.1f}x (compris dans l'intervalle [3 ; 14])."
                if passe_2
                else f"PER de {per:.1f}x hors fourchette (valorisation trop chère > 14x ou sous 3x)."
                if per is not None
                else "PER non calculable (résultat net négatif ou capitalisation indisponible)."
            ),
            source_info="Investing.com > PER",
        )
    )

    # 3. Règle 3 (CAPITALE) : Capitalisation boursière > 500 millions $ / €
    seuil_cap = 500_000_000.0
    passe_3 = (capitalisation is not None and capitalisation >= seuil_cap)
    val_cap_str = f"{capitalisation / 1e6:.0f} M€" if capitalisation else "> 500 M€ (Large Cap)" if shares is None else "n/d"
    # Si le nombre d'actions manque mais qu'il s'agit d'un grand titre établi du CAC40/DAX
    if capitalisation is None and equity and equity >= seuil_cap:
        passe_3 = True
        val_cap_str = f"Fonds propres > {equity / 1e6:.0f} M€"

    regles.append(
        RegleDividende(
            numero=3,
            nom="Capitalisation > 500 millions",
            est_capitale=True,
            seuil_requis="> 500 M€ / M$",
            valeur_observee=val_cap_str,
            passe=passe_3,
            explication=(
                f"Société de taille significative avec capitalisation estimée à {val_cap_str}."
                if passe_3
                else "Capitalisation inférieure à 500 millions ou données insuffisantes."
            ),
            source_info="Investing.com > Cap.Bours.",
        )
    )

    # 4. Règle 4 : Price to Book (P/B) < 4
    pb = (capitalisation / equity) if (capitalisation and equity and equity > 0) else None
    passe_4 = (pb is not None and 0 < pb < 4.0)
    regles.append(
        RegleDividende(
            numero=4,
            nom="Price to Book (P/B) < 4",
            est_capitale=False,
            seuil_requis="P/B < 4.0",
            valeur_observee=f"{pb:.2f}x" if pb is not None else "n/d",
            passe=passe_4,
            explication=(
                f"Multiple de valeur comptable sain à {pb:.2f}x (< 4.0)."
                if passe_4
                else f"Price to Book élevé à {pb:.2f}x (≥ 4.0) ou capitaux propres négatifs."
                if pb is not None
                else "Price to Book non calculable."
            ),
            source_info="Investing.com > Ratios > Cours / Valeur Comptable (MRQ)",
        )
    )

    # 5. Règle 5 (CAPITALE) : Marge avant impôts > 13%
    resultat_ebt = (ebit - interets) if (ebit is not None) else None
    marge_ebt = (resultat_ebt / revenue) if (resultat_ebt is not None and revenue and revenue > 0) else (ebit / revenue if (ebit is not None and revenue and revenue > 0) else None)
    passe_5 = (marge_ebt is not None and marge_ebt >= 0.13)
    regles.append(
        RegleDividende(
            numero=5,
            nom="Taux de marge avant impôts > 13 %",
            est_capitale=True,
            seuil_requis="> 13.0 %",
            valeur_observee=f"{marge_ebt * 100:.1f} %" if marge_ebt is not None else "n/d",
            passe=passe_5,
            explication=(
                f"Forte rentabilité opérationnelle avec une marge avant impôts de {marge_ebt * 100:.1f} % (> 13 %)."
                if passe_5
                else f"Marge avant impôts de {marge_ebt * 100:.1f} % (≤ 13.0 % requis)."
                if marge_ebt is not None
                else "Marge avant impôts non calculable."
            ),
            source_info="Investing.com > Fondamentaux > Marge bénéficiaire avant impôts (TTM)",
        )
    )

    # 6. Règle 6 (CAPITALE) : Dettes / Capitaux Propres ≤ 110%
    dette_ref = total_debt if total_debt is not None else net_debt
    ratio_dette_equity = (dette_ref / equity) if (dette_ref is not None and equity and equity > 0) else None
    passe_6 = (ratio_dette_equity is not None and ratio_dette_equity <= 1.10)
    # Si dette nette négative (trésorerie nette), le critère est tenu à 100%
    if net_debt is not None and net_debt <= 0:
        passe_6 = True
        ratio_dette_equity = min(ratio_dette_equity or 0.0, 0.0)

    regles.append(
        RegleDividende(
            numero=6,
            nom="Dettes / Capitaux Propres ≤ 110 %",
            est_capitale=True,
            seuil_requis="≤ 110 % (1.10x)",
            valeur_observee=f"{ratio_dette_equity * 100:.0f} %" if ratio_dette_equity is not None else "n/d",
            passe=passe_6,
            explication=(
                f"Endettement maîtrisé à {ratio_dette_equity * 100:.0f} % des fonds propres (≤ 110 %)."
                if passe_6
                else f"Endettement excessif représentant {ratio_dette_equity * 100:.0f} % des fonds propres (> 110 %)."
                if ratio_dette_equity is not None
                else "Ratio d'endettement non calculable."
            ),
            source_info="Investing.com > Fondamentaux > Dettes / Capitaux Propres",
        )
    )

    # 7. Règle 7 : Résultat net en hausse depuis 3 années consécutives
    serie_rn = facts_series.get("net_income", [])
    passe_7 = False
    if len(serie_rn) >= 3:
        rn_recents = [v for _, v in serie_rn[-3:]]
        if rn_recents[2] > rn_recents[1] > rn_recents[0] and rn_recents[0] > 0:
            passe_7 = True
    elif len(serie_rn) == 2 and serie_rn[-1][1] > serie_rn[-2][1] > 0:
        passe_7 = True

    val_rn_str = "Croissance 3 ans ✅" if passe_7 else "Irrégulier / Baisse ❌" if serie_rn else "n/d"
    regles.append(
        RegleDividende(
            numero=7,
            nom="Résultat net en hausse sur 3 ans",
            est_capitale=False,
            seuil_requis="RN(t) > RN(t-1) > RN(t-2)",
            valeur_observee=val_rn_str,
            passe=passe_7,
            explication=(
                "Bénéfice net en progression ininterrompue sur les 3 derniers exercices."
                if passe_7
                else "Le résultat net a marqué au moins une baisse ou stagnation sur les 3 dernières années."
            ),
            source_info="Investing.com > Profil financier > Compte de résultat > Annuel > Résultat net",
        )
    )

    # 8. Règle 8 (CAPITALE) : Verse des dividendes depuis ≥ 5 années consécutives
    passe_8 = (streak_annees >= 5)
    regles.append(
        RegleDividende(
            numero=8,
            nom="Dividendes versés depuis ≥ 5 ans",
            est_capitale=True,
            seuil_requis="≥ 5 années consécutives",
            valeur_observee=f"{streak_annees} an(s)",
            passe=passe_8,
            explication=(
                f"Historique de distribution robuste et continu sur {streak_annees} années consécutives (≥ 5 ans)."
                if passe_8
                else f"Historique de distribution récent insuffisant ({streak_annees} an(s) consécutif(s) < 5 ans requis)."
            ),
            source_info="Morningstar.fr > Finance > Dividendes",
        )
    )

    # 9. Règle 9 (CAPITALE) : Croissance des actions / tendance > 5% sur 5 ans
    passe_9 = (slope_annual is not None and slope_annual >= 0.05)
    regles.append(
        RegleDividende(
            numero=9,
            nom="Croissance de l'action > 5 % / an",
            est_capitale=True,
            seuil_requis="≥ +5.0 % / an",
            valeur_observee=f"{slope_annual * 100:+.1f} % / an" if slope_annual is not None else "n/d",
            passe=passe_9,
            explication=(
                f"Tendance haussière structurelle de fond à {slope_annual * 100:+.1f} % / an (≥ +5 % requis)."
                if passe_9
                else f"Tendance de long terme insuffisante à {slope_annual * 100:+.1f} % / an (< +5 %)."
                if slope_annual is not None
                else "Pente de régression non calculable."
            ),
            source_info="Morningstar.fr > Ratios Clés > Taux de croissance > Moyenne sur 5 ans",
        )
    )

    # 10. Règle 10 (Qualitative) : Compréhension de l'activité de l'entreprise
    passe_10 = bool(secteur_nom and secteur_nom != "-")
    regles.append(
        RegleDividende(
            numero=10,
            nom="Compréhension de l'activité",
            est_capitale=False,
            seuil_requis="Modèle économique clair",
            valeur_observee="Compris ✅" if passe_10 else "À vérifier",
            passe=passe_10,
            explication=(
                f"Activité et positionnement sectoriel identifiés ({secteur_nom})."
                if passe_10
                else "Modèle économique et activités à valider par l'investisseur."
            ),
            source_info="Analyse fondamentale & Positionnement métier",
        )
    )

    # 11. Règle 11 (Qualitative) : L'entreprise sera-t-elle toujours là dans 10 ans ?
    passe_11 = (quality_tier in ("solid", "watch") or (streak_annees >= 5 and (marge_ebt or 0) > 0.10))
    regles.append(
        RegleDividende(
            numero=11,
            nom="Pérennité de l'entreprise à 10 ans",
            est_capitale=False,
            seuil_requis="Barrières & Rente pérennes",
            valeur_observee="Pérenne ✅" if passe_11 else "Risque d'érosion",
            passe=passe_11,
            explication=(
                f"Solidité concurrentielle et pérennité établies (Statut qualité : {quality_tier})."
                if passe_11
                else "Visibilité à 10 ans incertaine (position en érosion ou non qualifiée)."
            ),
            source_info="Bloc D · Position concurrentielle & Moat durable",
        )
    )

    # Calculs du score
    total_oui = sum(1 for r in regles if r.passe)
    total_non = len(regles) - total_oui
    capitaux_oui = sum(1 for r in regles if r.est_capitale and r.passe)
    total_capitaux = sum(1 for r in regles if r.est_capitale)

    est_investissable = (total_oui >= 8)
    if est_investissable:
        verdict = f"INVESTISSABLE ({total_oui}/11 OUI)"
        synthese = (
            f"Cette action valide {total_oui} critères sur 11 (dont {capitaux_oui}/{total_capitaux} règles capitales). "
            f"Le profil de dividende et la solidité financière justifient une décision d'investissement."
        )
    else:
        verdict = f"RISQUÉ ({total_oui}/11 OUI)"
        echecs_capitaux = [r.nom for r in regles if r.est_capitale and not r.passe]
        if echecs_capitaux:
            synthese = (
                f"L'action n'obtient que {total_oui}/11 OUI (< 8 requis). "
                f"Attention : {len(echecs_capitaux)} règle(s) capitale(s) non validée(s) : {', '.join(echecs_capitaux)}."
            )
        else:
            synthese = (
                f"L'action obtient {total_oui}/11 OUI (< 8 requis pour être investissable selon la stratégie)."
            )

    return ScoreDividende11Regles(
        total_oui=total_oui,
        total_non=total_non,
        total_capitaux_oui=capitaux_oui,
        total_capitaux=total_capitaux,
        est_investissable=est_investissable,
        verdict=verdict,
        synthese_explication=synthese,
        regles=regles,
    )


def analyse_dividendes_instrument(cur: Any, instrument_id: int, as_of: date | None = None) -> ProfilDividende | None:
    """Analyse complète du profil de dividende d'un instrument donné avec le score des 11 règles."""
    as_of = as_of or date.today()
    annee_courante = as_of.year

    # Récupérer l'instrument et son fit de régression
    cur.execute(
        """
        select i.id, i.internal_code, i.name, i.currency, s.label as secteur,
               f.last_close, f.z_score, f.fitted_value, f.slope_annual,
               coalesce(q.quality_tier, 'unqualified') as quality_tier
          from instruments i
          left join sectors s on s.code = i.sector_code
          left join regression_fits f
            on f.instrument_id = i.id
           and f.as_of_date = (select max(as_of_date) from regression_fits where instrument_id = i.id)
          left join quality_scores q
            on q.instrument_id = i.id
           and q.as_of_date = (select max(as_of_date) from quality_scores where instrument_id = i.id)
         where i.id = %(id)s
        """,
        {"id": instrument_id},
    )
    inst = cur.fetchone()
    if not inst:
        return None

    inst_id, code, nom, devise, secteur_label, cours, z_score, fitted_val, slope_ann, qual_tier = inst

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

    # Récupérer toute la série des faits financiers pour les 11 règles
    cur.execute(
        """
        select concept_code, period_end, value
          from financial_facts
         where instrument_id = %(id)s
           and period_type = 'FY'
           and published_at <= %(as_of)s
         order by period_end asc
        """,
        {"id": instrument_id, "as_of": as_of},
    )
    facts_series: dict[str, list[tuple[date, float]]] = {}
    for c_code, p_end, val in cur.fetchall():
        facts_series.setdefault(c_code, []).append((p_end, float(val)))

    fcf = facts_series.get("fcf", [(None, None)])[-1][1]
    net_income = facts_series.get("net_income", [(None, None)])[-1][1]
    div_paid = facts_series.get("dividends_paid", [(None, None)])[-1][1]

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

    # Évaluer les 11 règles de la stratégie
    score_11 = evalue_11_regles_dividende(
        cours=cours,
        slope_annual=slope_ann,
        dernier_dpa=dernier_dpa,
        dpa_moyen_5a=dpa_moyen_5a,
        streak_annees=streak,
        facts_series=facts_series,
        quality_tier=qual_tier,
        secteur_nom=secteur_label or "",
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
        score_11_regles=score_11,
    )


SQL_SCREENER_DIVIDENDES = """
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
           max(value) filter (where concept_code = 'revenue') as revenue,
           max(value) filter (where concept_code = 'ebit') as ebit,
           max(value) filter (where concept_code = 'total_equity') as total_equity,
           max(value) filter (where concept_code = 'total_debt') as total_debt,
           max(value) filter (where concept_code = 'net_debt') as net_debt,
           max(value) filter (where concept_code = 'shares_basic') as shares_basic,
           abs(max(value) filter (where concept_code = 'dividends_paid')) as dividends_paid
      from (
          select instrument_id, concept_code, value,
                 row_number() over (partition by instrument_id, concept_code order by period_end desc) as rn
            from financial_facts
           where period_type = 'FY'
             and published_at <= %(as_of)s
             and concept_code in ('fcf', 'net_income', 'revenue', 'ebit', 'total_equity', 'total_debt', 'net_debt', 'shares_basic', 'dividends_paid')
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
       df.revenue,
       df.ebit,
       df.total_equity,
       df.total_debt,
       df.net_debt,
       df.shares_basic,
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
   and st.dernier_dpa is not null
   and st.dernier_dpa > 0
 order by rendement_actuel_pct desc nulls last;
"""
