"""Criteres d'acceptation du lot L6b (05_roadmap-et-lot.md, doc 08).

    - les cas du podcast se classent correctement : Nestle en `solid`, Arkema en
      `cyclical`, BMW avec au moins une pente d'erosion, Atos en `eroding`
    - aucun titre ne passe en `solid` sans groupe de pairs contenant un
      concurrent hors Europe
    - une evaluation de plus de 18 mois fait basculer le titre en `unqualified`
    - le calcul est reproductible

Deux cas du jeu de reference ne sont pas jouables sur cet univers, et il vaut
mieux le dire que le maquiller : **Nestle** est suisse, donc hors PEA et hors
perimetre ; **Atos** a ete ecarte en L1. Ils sont donc eprouves sur donnees
synthetiques, ou l'on connait la reponse - ce qui teste la regle, la ou un titre
reel ne ferait que la constater.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from market_intelligence.analytics import quality as Q  # noqa: E402
from market_intelligence.analytics import ratios as R  # noqa: E402
from market_intelligence.db import fetch_all, fetch_one  # noqa: E402


def fondamentaux(**series) -> R.Fondamentaux:
    f = R.Fondamentaux()
    for concept, valeurs in series.items():
        f.par_concept[concept] = {date(annee, 12, 31): v for annee, v in valeurs}
    f.exercices = sorted({e for v in f.par_concept.values() for e in v})
    return f


def titre(roic_cible: list[float], marges: list[float] | None = None,
          annee_depart: int = 2021) -> R.Fondamentaux:
    """Fabrique des comptes dont le ROIC vaut exactement les valeurs voulues.

    ROIC = EBIT x (1 - 25%) / (capitaux propres + dette nette). Avec des capitaux
    de 1 000 et un taux conventionnel de 25%, EBIT = ROIC x 1000 / 0,75.
    """
    capitaux = 1000.0
    ebit = [(annee_depart + i, r * capitaux / 0.75) for i, r in enumerate(roic_cible)]
    series = {
        "ebit": ebit,
        "total_equity": [(a, capitaux) for a, _ in ebit],
        "net_debt": [(a, 0.0) for a, _ in ebit],
        "revenue": [(a, 1000.0) for a, _ in ebit],
    }
    if marges is not None:
        series["gross_profit"] = [(annee_depart + i, m * 1000.0)
                                  for i, m in enumerate(marges)]
    return fondamentaux(**series)


# --------------------------------------------------------------------------- #
# Pentes et significativite
# --------------------------------------------------------------------------- #
def test_une_pente_franchement_negative_est_significative():
    serie = [(date(a, 12, 31), v) for a, v in
             [(2021, 0.30), (2022, 0.25), (2023, 0.20), (2024, 0.15), (2025, 0.10)]]
    pente = Q.pente_avec_intervalle(serie)
    assert pente.negative_significative
    assert pente.valeur == pytest.approx(-0.05, abs=1e-9)


def test_du_bruit_autour_dune_valeur_stable_nest_pas_une_erosion():
    """Sur cinq points le test est peu puissant, et c'est assume : mieux vaut
    manquer une erosion douteuse que crier au loup sur du bruit."""
    serie = [(date(a, 12, 31), v) for a, v in
             [(2021, 0.20), (2022, 0.22), (2023, 0.19), (2024, 0.21), (2025, 0.20)]]
    assert not Q.pente_avec_intervalle(serie).negative_significative


def test_une_pente_positive_nest_jamais_une_erosion():
    serie = [(date(a, 12, 31), v) for a, v in
             [(2021, 0.10), (2022, 0.15), (2023, 0.20), (2024, 0.25)]]
    assert not Q.pente_avec_intervalle(serie).negative_significative


def test_moins_de_trois_points_ne_produit_pas_de_pente():
    assert Q.pente_avec_intervalle([(date(2024, 12, 31), 0.2)]).valeur is None


# --------------------------------------------------------------------------- #
# ROIC
# --------------------------------------------------------------------------- #
def test_le_roic_est_calcule_selon_la_formule_du_doc():
    f = fondamentaux(
        ebit=[(2024, 200.0)], total_equity=[(2024, 600.0)], net_debt=[(2024, 400.0)],
        tax_expense=[(2024, 40.0)], interest_expense=[(2024, 0.0)],
    )
    roic = Q.serie_roic(f)
    # NOPAT = 200 x (1 - 40/200) = 160 ; capitaux = 1000 ; ROIC = 16%
    assert roic[0][1] == pytest.approx(0.16)


def test_un_taux_dimposition_aberrant_est_remplace_par_le_taux_conventionnel():
    """Un taux hors de [0 ; 60%] signale un exercice atypique - report
    deficitaire, produit exceptionnel - et non une fiscalite."""
    f = fondamentaux(
        ebit=[(2024, 200.0)], total_equity=[(2024, 1000.0)], net_debt=[(2024, 0.0)],
        tax_expense=[(2024, 500.0)], interest_expense=[(2024, 0.0)],
    )
    assert Q.serie_roic(f)[0][1] == pytest.approx(200 * 0.75 / 1000)


def test_des_capitaux_employes_negatifs_sont_ecartes():
    f = fondamentaux(ebit=[(2024, 200.0)], total_equity=[(2024, 100.0)],
                     net_debt=[(2024, -300.0)])
    assert Q.serie_roic(f) == []


# --------------------------------------------------------------------------- #
# Regimes
# --------------------------------------------------------------------------- #
def test_une_rente_stable_et_elevee_est_un_regime_de_rente():
    """Le cas Nestle du doc, sur donnees synthetiques faute d'un titre suisse
    dans un univers eligible PEA."""
    f = titre([0.16, 0.155, 0.16, 0.165, 0.16], marges=[0.48] * 5)
    q = Q.evalue(f, roic_median_pairs=0.10, revenus_pairs=[900.0],
                 groupe_complet=True, evaluation_valide=True)
    assert q.regime == "rent"
    assert q.quality_tier == "solid"
    assert q.persistence_years == 5


def test_un_roic_tres_volatil_est_cyclique_et_non_sans_qualite():
    """Arkema, BMW, Beneteau echouent a tous les tests de moat classiques et sont
    pourtant des cibles legitimes."""
    f = titre([0.20, 0.04, 0.18, 0.03, 0.16])
    q = Q.evalue(f, roic_median_pairs=0.10, revenus_pairs=[],
                 groupe_complet=True, evaluation_valide=True)
    assert q.regime == "cyclical"


def test_un_cyclique_nest_jamais_classe_en_erosion():
    """Defaut trouve en observant le resultat brut, pas en relisant.

    Une premiere version testait l'erosion avant le regime et classait Arkema en
    `eroding`, donc en value trap une fois croise avec un z-score bas. Le doc 08
    dit l'inverse : *Arkema - non applicable : regime cyclique - bas de cycle,
    pas erosion*. Une pente de ROIC negative sur un cyclique mesure la descente
    du cycle, pas la perte d'une barriere.
    """
    f = titre([0.25, 0.05, 0.20, 0.04, 0.10], marges=[0.30, 0.22, 0.28, 0.20, 0.18])
    q = Q.evalue(f, roic_median_pairs=0.10, revenus_pairs=[],
                 groupe_complet=True, evaluation_valide=True)
    assert q.regime == "cyclical"
    assert q.quality_tier == "watch", "un cyclique en bas de cycle n'est pas un value trap"
    assert any("cyclique" in m for m in q.motifs)


def test_une_rente_qui_se_contracte_est_une_erosion():
    """Atos, sur donnees synthetiques : le titre a ete ecarte de l'univers en L1."""
    f = titre([0.18, 0.14, 0.10, 0.06, 0.02], marges=[0.40, 0.36, 0.32, 0.28, 0.24])
    q = Q.evalue(f, roic_median_pairs=0.10, revenus_pairs=[],
                 groupe_complet=True, evaluation_valide=True)
    assert q.erosion_flags >= 2
    assert q.quality_tier == "eroding"


def test_un_roic_au_niveau_du_cout_du_capital_est_sans_barriere():
    f = titre([0.078, 0.079, 0.080, 0.078, 0.079])
    q = Q.evalue(f, roic_median_pairs=0.08, revenus_pairs=[],
                 groupe_complet=True, evaluation_valide=True)
    assert q.regime == "no_moat"
    assert q.quality_tier == "watch"


def test_une_banque_sans_roic_calculable_reste_non_qualifiee():
    """Ni EBIT ni capitaux employes au sens industriel : ce n'est pas une donnee
    manquante, c'est un modele qui ne s'applique pas."""
    f = fondamentaux(revenue=[(2024, 1000.0)], net_income=[(2024, 200.0)])
    q = Q.evalue(f, roic_median_pairs=None, revenus_pairs=[],
                 groupe_complet=True, evaluation_valide=True)
    assert q.regime == "unknown"
    assert q.quality_tier == "unqualified"


# --------------------------------------------------------------------------- #
# Les deux garde-fous
# --------------------------------------------------------------------------- #
def test_aucun_solid_sans_concurrent_hors_europe():
    """Limite L1 du doc 08, la plus serieuse du systeme. Un groupe purement
    europeen est structurellement aveugle : SharkNinja est americaine, BYD est
    chinoise, Revolut n'est pas cotee."""
    f = titre([0.16] * 5, marges=[0.48] * 5)
    q = Q.evalue(f, roic_median_pairs=0.10, revenus_pairs=[900.0],
                 groupe_complet=False, evaluation_valide=True)
    assert q.quality_tier == "watch"
    assert "groupe_de_pairs_sans_concurrent_hors_europe" in q.motifs


def test_aucun_solid_sans_evaluation_qualitative_valide():
    """Le moat quantitatif mesure le passe : un ROIC eleve est la trace d'une
    barriere qui a existe, il ne dit rien de sa resistance a une rupture."""
    f = titre([0.16] * 5, marges=[0.48] * 5)
    q = Q.evalue(f, roic_median_pairs=0.10, revenus_pairs=[900.0],
                 groupe_complet=True, evaluation_valide=False)
    assert q.quality_tier == "unqualified"
    assert "evaluation_qualitative_absente_ou_perimee" in q.motifs


def test_une_evaluation_perimee_equivaut_a_une_absence():
    """Une evaluation de 2026 inspire exactement la meme confiance qu'une de
    2029, et c'est le probleme. La peremption force la revue."""
    f = titre([0.16] * 5, marges=[0.48] * 5)
    perimee = Q.evalue(f, roic_median_pairs=0.10, revenus_pairs=[900.0],
                       groupe_complet=True, evaluation_valide=False)
    valide = Q.evalue(f, roic_median_pairs=0.10, revenus_pairs=[900.0],
                      groupe_complet=True, evaluation_valide=True)
    assert perimee.quality_tier == "unqualified"
    assert valide.quality_tier == "solid"


def test_la_peremption_est_de_dix_huit_mois():
    assert Q.PEREMPTION_MOIS == 18


# --------------------------------------------------------------------------- #
# Matrice qualite x prix
# --------------------------------------------------------------------------- #
def test_une_decote_sur_une_position_qui_serode_est_un_value_trap():
    """*La decote sur une position qui s'erode n'est pas une decote, c'est un
    ajustement de prix correct.* C'est la definition du value trap, et c'est la
    qu'un investisseur value perd son argent."""
    assert Q.quadrant("eroding", -2.5) == "value_trap"
    assert Q.quadrant("eroding", 2.0) == "avoid"


def test_une_decote_sur_une_position_solide_est_une_cible():
    assert Q.quadrant("solid", -2.0) == "target"
    assert Q.quadrant("solid", 1.5) == "watchlist"


def test_un_titre_non_qualifie_ne_devient_jamais_une_cible():
    assert Q.quadrant("unqualified", -3.0) == "unqualified"


# --------------------------------------------------------------------------- #
# Etat de la base
# --------------------------------------------------------------------------- #
def test_des_scores_ont_ete_ecrits():
    assert fetch_one("select count(*) from quality_scores")[0] > 0


def test_aucun_solid_en_base_sans_groupe_complet():
    violations = fetch_all(
        """
        select i.internal_code from quality_scores q
          join instruments i on i.id = q.instrument_id
          left join peer_groups g on g.id = q.peer_group_id
         where q.quality_tier = 'solid' and coalesce(g.is_complete, false) = false
        """
    )
    assert violations == []


def test_arkema_est_cyclique_et_non_en_erosion():
    """Cas de reference du doc 08 : *bas de cycle, pas erosion*."""
    ligne = fetch_one(
        "select q.regime, q.quality_tier from quality_scores q "
        "join instruments i on i.id = q.instrument_id "
        "where i.internal_code = 'EQ:FR:ARKEMA'"
    )
    assert ligne is not None, "lancer scripts/compute_quality.py"
    assert ligne[0] == "cyclical"
    assert ligne[1] != "eroding"


def test_bmw_porte_au_moins_une_pente_derosion():
    """Cas de reference : perte de part en Chine face a BYD, profit warning."""
    flags = fetch_one(
        "select q.erosion_flags from quality_scores q "
        "join instruments i on i.id = q.instrument_id "
        "where i.internal_code = 'EQ:DE:BMW'"
    )
    assert flags is not None and flags[0] >= 1


def test_les_groupes_manuels_contiennent_des_concurrents_hors_univers():
    incomplets = fetch_all(
        """
        select g.code from peer_groups g
         where g.kind = 'manual'
           and not exists (select 1 from peer_group_members m
                            where m.peer_group_id = g.id and not m.is_in_universe)
        """
    )
    assert incomplets == []


def test_les_groupes_sectoriels_automatiques_sont_marques_incomplets():
    """Ils sont limites a l'univers europeen, donc structurellement aveugles."""
    fautifs = fetch_all(
        "select code from peer_groups where kind = 'sector_auto' and is_complete")
    assert fautifs == []


def test_les_scores_ne_sont_jamais_reecrits():
    """Principe P5 applique a la qualite : dans trois ans on voudra savoir si les
    titres classes `solid` en 2026 l'etaient encore en 2029."""
    doublons = fetch_all(
        "select instrument_id, as_of_date, method_version, count(*) "
        "from quality_scores group by 1,2,3 having count(*) > 1"
    )
    assert doublons == []


# --------------------------------------------------------------------------- #
# Un casier sectoriel n'est pas un groupe de pairs
#
# Constat sur EssilorLuxottica (2026-08-21) : son groupe etait `AUTO:20 —
# Secteur Health Care`, dont les membres sont Sanofi et UCB. Le systeme
# comparait le ROIC d'un lunetier a celui de deux laboratoires
# pharmaceutiques, et l'ecart de -2,56 points a servi de preuve dans la
# synthese. Meme regle que l'indice de reference du doc 11 SS8.1 : afficher un
# chiffre dont la reference est arbitraire vaut moins que ne rien afficher.
# --------------------------------------------------------------------------- #
def test_un_groupe_sectoriel_automatique_nest_pas_comparable():
    assert not Q.groupe_comparable("AUTO:20", "sector_auto", False)


def test_un_groupe_issu_dun_dossier_est_comparable():
    """Il vient d'une analyse concurrentielle : ses membres sont les concurrents
    reels, pas les voisins de case."""
    assert Q.groupe_comparable("DOSSIER:EQ:DE:ADIDAS", "manual", True)
    assert Q.groupe_comparable("DOSSIER:EQ:FR:X", "sector_auto", False)


def test_un_groupe_manuel_ou_marque_complet_est_comparable():
    assert Q.groupe_comparable("MAN:LUXE", "manual", False)
    assert Q.groupe_comparable("AUTO:20", "sector_auto", True)


def test_labsence_de_groupe_nest_pas_comparable():
    assert not Q.groupe_comparable(None, None, None)


def _entreprise_rentable():
    return fondamentaux(
        ebit=[(a, 300) for a in range(2020, 2026)],
        total_equity=[(a, 1000) for a in range(2020, 2026)],
        net_debt=[(a, 0) for a in range(2020, 2026)],
        revenue=[(a, 2000) for a in range(2020, 2026)],
    )


def test_sans_groupe_comparable_aucun_indicateur_relatif_nest_publie():
    q = Q.evalue(_entreprise_rentable(), roic_median_pairs=0.05,
                 revenus_pairs=[5000.0], groupe_complet=False,
                 evaluation_valide=False, groupe_est_comparable=False)
    assert q.roic_vs_peers is None
    assert q.relative_share is None
    assert q.rank_by_revenue is None
    assert "indicateurs_relatifs_non_publies_groupe_non_comparable" in q.motifs, \
        "trois cases vides sans motif se lisent comme une donnee manquante"


def test_les_mesures_absolues_et_les_verdicts_ne_bougent_pas():
    """Le regime et le niveau reposent sur des mesures absolues : retirer les
    comparaisons ne doit rien changer au jugement porte sur le titre."""
    f = _entreprise_rentable()
    avec = Q.evalue(f, roic_median_pairs=0.05, revenus_pairs=[5000.0],
                    groupe_complet=False, evaluation_valide=False,
                    groupe_est_comparable=True)
    sans = Q.evalue(f, roic_median_pairs=0.05, revenus_pairs=[5000.0],
                    groupe_complet=False, evaluation_valide=False,
                    groupe_est_comparable=False)
    assert (sans.regime, sans.quality_tier) == (avec.regime, avec.quality_tier)
    assert sans.roic_mean_5y == avec.roic_mean_5y
    assert sans.roic_vs_threshold == avec.roic_vs_threshold


def test_aucun_indicateur_relatif_en_base_sur_un_groupe_non_comparable():
    """La regle doit tenir sur les donnees reelles, pas seulement en unitaire."""
    fautifs = fetch_all(
        """
        select i.internal_code, g.code
          from quality_scores q
          join instruments i on i.id = q.instrument_id
          left join peer_groups g on g.id = q.peer_group_id
         where q.as_of_date = (select max(as_of_date) from quality_scores)
           and (q.roic_vs_peers is not null or q.relative_share is not null
                or q.rank_by_revenue is not null)
           and not (coalesce(g.is_complete, false)
                    or g.code like 'DOSSIER:%%' or g.kind = 'manual')
        """
    )
    assert fautifs == []
