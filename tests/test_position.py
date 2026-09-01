"""Criteres d'acceptation du dossier de position concurrentielle (doc 08 §8).

Ce qui est eprouve ici, dans l'ordre d'importance :

- **le score se calcule, il ne se demande pas** — meme dossier, meme note ;
- le bareme s'affiche terme par terme : un total dont on ne voit pas la
  construction ne se discute pas, il se subit ;
- une menace `faible` ne retire aucun point : compter chaque menace recensee
  punirait le dossier le plus complet ;
- « leader » sans « depuis quand » est signale, jamais comble ;
- un concurrent nomme sans explication du danger est signale ;
- sans nom d'analyste, rien n'est projete.

Remplace `test_dossier.py`, qui eprouvait le dispositif a cinq prompts.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from market_intelligence.db import fetch_all  # noqa: E402
from market_intelligence.intelligence import position as P  # noqa: E402
from market_intelligence.intelligence import prompts, schema  # noqa: E402

AUJOURDHUI = date(2026, 8, 21)


def dossier(**remplace) -> dict:
    """Le dossier de reference : EssilorLuxottica, tel que l'exemple du cadrage."""
    base = {
        "version": 2,
        "entreprise": "EssilorLuxottica",
        "date_reference": "2026-08-21",
        "marche": "verres correcteurs, montures et solaires, retail optique",
        "position": {"verdict": "leader", "depuis": 2018, "perdue_en": None,
                     "preuve": "premier mondial des verres correcteurs",
                     "statut": "FAIT_VERIFIE"},
        "durabilite": {"verdict": "solid",
                       "sources_de_rente": ["brand", "patent", "switching", "scale"],
                       "justification": "integration verticale"},
        "concurrents": [
            {"nom": "Hoya Corporation", "pays": "JP", "type": "directe",
             "danger": "eleve", "pourquoi_dangereux": "MiYOSMART sur la myopie",
             "signal_a_surveiller": "approbation FDA"},
            {"nom": "Kering Eyewear", "pays": "FR", "type": "directe",
             "danger": "moyen", "pourquoi_dangereux": "internalisation des licences"},
            {"nom": "Warby Parker", "pays": "US", "type": "indirecte",
             "danger": "moyen", "pourquoi_dangereux": "disruption DTC"},
        ],
        "autres_menaces": [],
        "resume": "Leader incontesté de l'eyewear.",
        "sources": [{"titre": "Rapport annuel", "url": "https://exemple",
                     "date": "2026-02-12"}],
    }
    base.update(remplace)
    return base


# --------------------------------------------------------------------------- #
# Le score se calcule, il ne se demande pas
# --------------------------------------------------------------------------- #
def test_le_score_est_reproductible():
    """**Le point qui justifie de calculer plutot que de demander.** Un LLM a qui
    l'on demande une note sur 100 en invente une : deux executions du meme prompt
    donnent deux nombres, et aucun n'est reconstituable."""
    d = dossier()
    premier = P.calcule_le_score(d, AUJOURDHUI).total
    second = P.calcule_le_score(d, AUJOURDHUI).total
    assert premier == second


def test_le_bareme_du_cas_de_reference():
    """Le cas pose au cadrage : leader depuis 2018, durabilite solide, une menace
    elevee et deux moyennes."""
    score = P.calcule_le_score(dossier(), AUJOURDHUI)
    assert [(l.libelle, l.points) for l in score.lignes] == [
        ("Position", 50), ("Ancienneté", 16), ("Durabilité", 20), ("Menaces", -20)]
    assert score.total == 66
    assert score.niveau == "position tenue"


def test_chaque_terme_du_bareme_est_affiche():
    """Un total dont on ne voit pas la construction ne se discute pas."""
    score = P.calcule_le_score(dossier(), AUJOURDHUI)
    assert sum(l.points for l in score.lignes) == score.total
    assert all(l.detail for l in score.lignes), "chaque ligne dit sur quoi elle porte"


def test_une_menace_faible_ne_retire_aucun_point():
    """Compter chaque menace recensee punirait le dossier le plus complet : un
    concurrent identifie puis juge peu dangereux est une information rassurante."""
    avec = dossier()
    avec["concurrents"] = avec["concurrents"] + [
        {"nom": "Safilo", "pays": "IT", "type": "directe", "danger": "faible",
         "pourquoi_dangereux": "montures de mode, part limitee"}]
    assert (P.calcule_le_score(avec, AUJOURDHUI).total
            == P.calcule_le_score(dossier(), AUJOURDHUI).total)


def test_les_menaces_ne_font_pas_couler_le_score_indefiniment():
    """Au-dela du plancher, on empile sans rien apprendre."""
    d = dossier()
    d["concurrents"] = [
        {"nom": f"Menace {i}", "type": "directe", "danger": "eleve",
         "pourquoi_dangereux": "x"} for i in range(12)]
    lignes = {l.libelle: l.points for l in P.calcule_le_score(d, AUJOURDHUI).lignes}
    assert lignes["Menaces"] == P.PLANCHER_MENACES


def test_lanciennete_plafonne_a_dix_ans():
    court = P.calcule_le_score(dossier(position={"verdict": "leader",
                                                 "depuis": 2022}), AUJOURDHUI)
    ancien = P.calcule_le_score(dossier(position={"verdict": "leader",
                                                  "depuis": 1950}), AUJOURDHUI)
    points = {l.libelle: l.points for l in ancien.lignes}
    assert points["Ancienneté"] == P.POINTS_PAR_ANNEE * P.ANNEES_PLAFOND
    assert court.total < ancien.total


def test_une_anciennete_inconnue_est_dite_au_lieu_detre_inventee():
    """« Leader » sans « depuis quand » ne dit pas si la position est etablie ou
    fraiche. Le score le signale au lieu de combler."""
    d = dossier(position={"verdict": "leader", "depuis": None})
    score = P.calcule_le_score(d, AUJOURDHUI)
    assert {l.libelle: l.points for l in score.lignes}["Ancienneté"] == 0
    assert any("accession" in r for r in score.reserves)


def test_une_position_perdue_recemment_pese_plus_quune_perte_ancienne():
    """La premiere est une trajectoire, la seconde un etat de fait que le marche
    a deja digere."""
    recente = P.calcule_le_score(
        dossier(position={"verdict": "challenger", "depuis": 2024,
                          "perdue_en": 2025}), AUJOURDHUI)
    ancienne = P.calcule_le_score(
        dossier(position={"verdict": "challenger", "depuis": 2010,
                          "perdue_en": 2010}), AUJOURDHUI)
    malus_recent = {l.libelle: l.points for l in recente.lignes}["Position perdue"]
    malus_ancien = {l.libelle: l.points for l in ancienne.lignes}["Position perdue"]
    assert malus_recent < malus_ancien
    assert malus_ancien == 0, "au-dela de cinq ans, le malus est efface"


def test_le_score_reste_dans_les_bornes():
    parfait = dossier(position={"verdict": "leader", "depuis": 1900},
                      autres_menaces=[], concurrents=[
                          {"nom": "x", "type": "directe", "danger": "faible",
                           "pourquoi_dangereux": "y"}])
    assert P.calcule_le_score(parfait, AUJOURDHUI).total <= 100
    desastre = dossier(
        position={"verdict": "suiveur", "depuis": 2026, "perdue_en": 2026},
        durabilite={"verdict": "none", "sources_de_rente": []},
        concurrents=[{"nom": f"m{i}", "type": "directe", "danger": "eleve",
                      "pourquoi_dangereux": "x"} for i in range(8)])
    assert P.calcule_le_score(desastre, AUJOURDHUI).total >= 0


def test_une_position_absente_ne_produit_aucun_score():
    """Mieux vaut aucun chiffre qu'un chiffre dont la base manque."""
    score = P.calcule_le_score(dossier(position={"verdict": None}), AUJOURDHUI)
    assert score.total == 0
    assert score.reserves


# --------------------------------------------------------------------------- #
# Les concurrents et leurs menaces
# --------------------------------------------------------------------------- #
def test_les_menaces_sortent_classees_par_danger():
    ordre = [m["danger"] for m in P.menaces(dossier())]
    assert ordre == sorted(ordre, key=lambda d: ["eleve", "moyen", "faible"].index(d))


def test_concurrents_et_autres_menaces_se_lisent_ensemble():
    """Les separer a la saisie evite de faire passer un risque de licence pour
    une societe ; les reunir a la lecture evite deux tableaux."""
    d = dossier(autres_menaces=[
        {"nom": "Regulation du prix des verres", "nature": "reglementaire",
         "type": "indirecte", "danger": "moyen", "pourquoi_dangereux": "x"}])
    toutes = P.menaces(d)
    assert len(toutes) == 4
    assert {m["nature"] for m in toutes} == {"concurrent", "reglementaire"}


def test_un_concurrent_sans_explication_du_danger_est_signale():
    """Un concurrent nomme sans raison ne se relit pas : dans six mois on ne
    saura plus pourquoi il figurait la."""
    d = dossier()
    d["concurrents"][0]["pourquoi_dangereux"] = ""
    problemes = P.valide(d).problemes
    assert any("explication du danger" in p.explication for p in problemes)


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #
def test_un_dossier_de_reference_passe():
    assert P.valide(dossier()).importable


def test_un_dossier_sans_verdict_de_position_est_refuse():
    assert not P.valide(dossier(position={"verdict": None})).importable


def test_un_dossier_sans_aucun_concurrent_est_refuse():
    """Une entreprise sans concurrent identifie n'existe pas : c'est l'analyse
    qui manque, pas le concurrent."""
    assert not P.valide(dossier(concurrents=[], autres_menaces=[])).importable


def test_une_anciennete_manquante_ne_bloque_pas_limport():
    """Elle est signalee et le score le dit, mais un dossier utile ne se refuse
    pas pour une annee inconnue."""
    validation = P.valide(dossier(position={"verdict": "leader", "depuis": None}))
    assert validation.importable
    assert any(p.element == "position.depuis" for p in validation.problemes)


def test_une_source_de_rente_hors_liste_est_signalee():
    d = dossier(durabilite={"verdict": "solid", "sources_de_rente": ["magie"]})
    assert any("source de rente inconnue" in p.explication
               for p in P.valide(d).problemes)


def test_un_leader_qui_a_perdu_sa_position_se_contredit():
    d = dossier(position={"verdict": "leader", "depuis": 2018, "perdue_en": 2024})
    assert any(p.element == "position.perdue_en" for p in P.valide(d).problemes)


# --------------------------------------------------------------------------- #
# Le prompt
# --------------------------------------------------------------------------- #
def test_il_ny_a_quun_seul_prompt():
    """Cinq copier-coller par titre faisaient qu'on ne lancait l'analyse
    presque jamais."""
    assert list(prompts.PROMPTS) == ["position"]


def test_le_prompt_se_compose_sans_variable_residuelle():
    import re

    texte = prompts.compose("position", {
        "ENTREPRISE_ANALYSEE": "EssilorLuxottica",
        "DATE_DE_REFERENCE": "2026-08-21",
        "PAYS_ET_ZONE_GEOGRAPHIQUE": "France",
    })
    assert not re.findall(r"\{\{[A-Z_]+\}\}", texte)


def test_le_squelette_du_prompt_est_un_json_valide():
    """Un squelette mal echappe produit un JSON que le modele recopie tel quel."""
    import json

    texte = prompts.compose("position", {
        "ENTREPRISE_ANALYSEE": "X", "DATE_DE_REFERENCE": "2026-08-21",
        "PAYS_ET_ZONE_GEOGRAPHIQUE": "FR"})
    squelette = texte[texte.index('{\n  "version"'):]
    assert json.loads(squelette)["version"] == 2


def test_le_prompt_interdit_explicitement_de_noter():
    """Sinon le modele produit une note, elle s'affiche, et personne ne sait
    plus si elle vient d'un bareme ou d'une intuition."""
    texte = prompts.PROMPTS["position"][1]
    assert "Pas de note, pas de score" in texte


def test_le_prompt_demande_de_chercher_hors_de_la_zone():
    """Les menaces reelles viennent presque toujours de l'exterieur de
    l'univers : SharkNinja est americaine, BYD est chinoise."""
    assert "hors de la zone geographique" in prompts.PROMPTS["position"][1]


def test_le_prompt_exige_une_reponse_en_francais():
    assert "francais" in prompts.PROMPTS["position"][1]


def test_le_perimetre_du_marche_reste_a_etablir_par_le_modele():
    """Le fixer d'avance revient a decider ou s'arrete la concurrence avant
    d'avoir regarde."""
    assert "MARCHE_CIBLE" in prompts.VARIABLES_A_ETABLIR
    texte = prompts.compose("position", {"ENTREPRISE_ANALYSEE": "X"})
    assert "[a determiner par toi]" in texte


def test_un_prompt_inconnu_leve_clairement():
    with pytest.raises(KeyError, match="prompt inconnu"):
        prompts.compose("synthese", {})


# --------------------------------------------------------------------------- #
# Migration depuis l'ancien format
# --------------------------------------------------------------------------- #
ANCIEN = {
    "analysis_metadata": {"company_analyzed": "EssilorLuxottica",
                          "reference_date": "2026-08-21"},
    "market_definition": {"description": "eyewear"},
    "strategic_assessment": {
        "position_verdict": "leader", "durability_verdict": "solid",
        "moat_sources": ["brand", "scale"],
        "threats": ["Perte de licences de luxe"],
        "rationale": "Leader incontesté.",
    },
    "competitors": [
        {"company_name": "Hoya Corporation", "country": "Japon",
         "competition_type": "direct", "relevance_score": 8,
         "relevance_explanation": "verres premium"},
        {"company_name": "Warby Parker", "country": "US",
         "competition_type": "indirect", "relevance_score": 3,
         "relevance_explanation": "DTC"},
    ],
    "sources": [{"url": "https://exemple"}],
}


def test_la_migration_reprend_les_verdicts_et_les_concurrents():
    converti = P.migre(ANCIEN)
    assert converti["position"]["verdict"] == "leader"
    assert converti["durabilite"]["verdict"] == "solid"
    assert [c["nom"] for c in converti["concurrents"]] == ["Hoya Corporation",
                                                           "Warby Parker"]
    assert converti["concurrents"][0]["type"] == "directe"
    assert converti["concurrents"][1]["type"] == "indirecte"


def test_la_migration_ne_fabrique_pas_lannee_daccession():
    """C'est precisement la question que l'ancien dispositif ne posait pas :
    l'inventer serait pire que la laisser vide."""
    assert P.migre(ANCIEN)["position"]["depuis"] is None


def test_la_migration_conserve_lancien_dossier():
    """Rien n'est perdu, rien n'est reecrit en silence."""
    assert P.migre(ANCIEN)["ancien_dossier"] == ANCIEN


def test_la_migration_marque_ce_qui_vient_dune_conversion():
    converti = P.migre(ANCIEN)
    assert converti["position"]["statut"] == "MIGRE"
    assert all(c["statut"] == "MIGRE" for c in converti["concurrents"])


def test_un_dossier_migre_reste_lisible_et_notable():
    converti = P.migre(ANCIEN)
    assert P.est_v2(converti)
    assert P.valide(converti).importable
    assert P.calcule_le_score(converti, AUJOURDHUI).total > 0


# --------------------------------------------------------------------------- #
# Ce qui reste vrai en base
# --------------------------------------------------------------------------- #
def test_la_peremption_est_a_dix_huit_mois():
    """Une evaluation de 2026 inspire la meme confiance qu'une de 2029, et c'est
    le probleme."""
    assert schema.PEREMPTION_MOIS == 18
    assert (schema.peremption(date(2026, 1, 1)) - date(2026, 1, 1)).days > 540


def test_tous_les_dossiers_en_base_sont_au_format_courant():
    """Une page qui rencontre un ancien dossier ne sait pas quoi en faire."""
    anciens = fetch_all(
        "select i.internal_code from market_analyses m "
        "join instruments i on i.id = m.instrument_id "
        "where coalesce((m.dossier->>'version')::int, 1) <> %s", (P.VERSION,))
    assert anciens == [], "lancer scripts/migre_dossiers_v2.py"


def test_un_dossier_validated_porte_toujours_un_analyste():
    """Sans nom, rien ne distingue un dossier relu d'un dossier produit."""
    fautifs = fetch_all(
        "select analysis_id from market_analyses "
        "where status = 'validated' and (analyst is null or btrim(analyst) = '')")
    assert fautifs == []
