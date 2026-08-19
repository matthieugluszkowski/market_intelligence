"""Critères d'acceptation du lot L6b bis (doc 05, doc 08 §8).

    - un dossier importé sans `reviewed_by` ne fait jamais passer un titre en
      `solid`
    - un JSON incomplet est refusé avec le détail des manques, jamais complété
      silencieusement
    - l'interface lit des clés avec valeur par défaut et n'appelle aucun calcul :
      une clé absente affiche « non renseigné », elle ne lève pas

Le troisième critère existe à cause d'une panne réelle : la fiche instrument
appelait une fonction d'agrégation qualité et tombait en `AttributeError`. Le
symptôme était bénin — un module en cache — mais il a révélé le vrai défaut de
conception : **l'écran dépendait d'un calcul, pas d'un contrat de données.**
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from market_intelligence.intelligence import prompts, schema  # noqa: E402


def dossier_complet(**remplace) -> dict:
    """Dossier minimal mais valide : le cas Seb, avec SharkNinja hors Europe."""
    base = {
        "analysis_metadata": {
            "analysis_id": "EQ:FR:SEB@2026-08-19", "company_analyzed": "SEB",
            "sector": "Consumer Discretionary", "reference_date": "2026-08-19",
            "analyst": None, "status": "draft",
        },
        "competitors": [
            {"company_name": "SharkNinja", "country": "US",
             "competition_type": "direct",
             "relevance_explanation": "Attaque le coeur de gamme de Seb.",
             "status": "FAIT_VERIFIE", "sources": []},
        ],
        "functional_analysis": [],
        "quality_control": {"validated": False, "quality_score": None,
                            "blocking_issues": [], "review_date": None},
        "sources": [{"title": "Rapport annuel", "url": "https://x.fr",
                     "date": "2026-03-01"}],
    }
    base.update(remplace)
    return base


# --------------------------------------------------------------------------- #
# Le contrat ne lève jamais
# --------------------------------------------------------------------------- #
def test_une_cle_absente_ne_leve_pas():
    """C'est exactement la panne qui a motivé ce lot."""
    assert schema.lire({}, "quality_control", "validated", defaut=False) is False
    assert schema.lire(None, "a", "b", defaut="non renseigné") == "non renseigné"
    assert schema.lire({"a": {"b": None}}, "a", "b", defaut="défaut") == "défaut"


def test_le_resume_daffichage_est_toujours_complet():
    """L'interface lit ce dictionnaire, jamais le dossier brut. Toutes les clés
    doivent exister, même sur un dossier vide."""
    for entree in ({}, {"analysis_metadata": {}}, dossier_complet()):
        r = schema.resume(entree)
        assert set(r) >= {"entreprise", "secteur", "statut", "valide",
                          "n_concurrents", "n_sources"}
        assert isinstance(r["valide"], bool)


def test_validated_vaut_false_par_defaut():
    """L'absence d'information n'est jamais un feu vert."""
    assert schema.resume({})["valide"] is False
    assert schema.resume({"quality_control": {}})["valide"] is False


def test_le_gabarit_est_conforme_au_contrat():
    g = schema.gabarit("EQ:FR:SEB", "SEB", date(2026, 8, 19))
    assert schema.lire(g, "quality_control", "validated") is False
    assert schema.lire(g, "analysis_metadata", "analyst") is None
    assert schema.resume(g)["statut"] == "draft"


# --------------------------------------------------------------------------- #
# Un JSON incomplet est refusé, jamais complété
# --------------------------------------------------------------------------- #
def test_un_dossier_sans_concurrent_est_refuse():
    v = schema.valide(dossier_complet(competitors=[]))
    assert not v.importable
    assert any("competitors" in p.element for p in v.bloquants)


def test_un_concurrent_sans_justification_est_bloquant():
    """Règle du prompt 4 : aucune entreprise classée concurrente sans
    justification. C'est la porte d'entrée des faux concurrents."""
    v = schema.valide(dossier_complet(competitors=[
        {"company_name": "SharkNinja", "country": "US",
         "competition_type": "direct", "status": "FAIT_VERIFIE"},
    ]))
    assert not v.importable
    assert any("justification" in p.explication for p in v.bloquants)


def test_un_dossier_sans_source_est_refuse():
    """Une affirmation sans source n'est pas vérifiable, et un dossier non
    vérifiable ne doit pas entrer en base."""
    v = schema.valide(dossier_complet(sources=[]))
    assert not v.importable
    assert any(p.element == "sources" for p in v.bloquants)


def test_un_dossier_sans_date_de_reference_est_refuse():
    d = dossier_complet()
    d["analysis_metadata"]["reference_date"] = None
    v = schema.valide(d)
    assert not v.importable


def test_les_problemes_bloquants_portent_une_correction():
    """Un refus sans indication de correction oblige à deviner."""
    v = schema.valide({"competitors": [], "sources": []})
    assert v.bloquants
    assert any(p.correction for p in v.bloquants)


def test_le_controle_qualite_du_prompt_4_est_respecte():
    """Si le prompt 4 signale des bloquants non résolus, l'import s'arrête."""
    d = dossier_complet()
    d["quality_control"]["blocking_issues"] = ["chiffre sans devise"]
    assert not schema.valide(d).importable


def test_un_dossier_valide_passe():
    v = schema.valide(dossier_complet())
    assert v.importable
    assert v.concurrents == 1
    assert v.concurrents_hors_europe == 1


# --------------------------------------------------------------------------- #
# La complétude du groupe de pairs
# --------------------------------------------------------------------------- #
def test_un_groupe_purement_europeen_est_incomplet():
    """Limite L1 du doc 08 : les menaces réelles viennent presque toujours de
    l'extérieur de l'univers."""
    v = schema.valide(dossier_complet(competitors=[
        {"company_name": "De'Longhi", "country": "IT", "competition_type": "direct",
         "relevance_explanation": "Concurrent européen direct.",
         "status": "FAIT_VERIFIE"},
    ]))
    assert v.importable, "le dossier reste utile, il n'est pas rejeté"
    assert not v.groupe_complet
    assert any("hors Europe" in p.explication for p in v.problemes)


@pytest.mark.parametrize("pays", ["US", "CN", "JP", "TW", "KR", "IN", "BR"])
def test_un_concurrent_extra_europeen_rend_le_groupe_complet(pays):
    v = schema.valide(dossier_complet(competitors=[
        {"company_name": "Concurrent", "country": pays,
         "competition_type": "direct", "relevance_explanation": "Justifié.",
         "status": "FAIT_VERIFIE"},
    ]))
    assert v.groupe_complet


@pytest.mark.parametrize("pays", ["FR", "DE", "CH", "GB", "SE", "PL"])
def test_un_concurrent_europeen_ne_rend_pas_le_groupe_complet(pays):
    v = schema.valide(dossier_complet(competitors=[
        {"company_name": "Concurrent", "country": pays,
         "competition_type": "direct", "relevance_explanation": "Justifié.",
         "status": "FAIT_VERIFIE"},
    ]))
    assert not v.groupe_complet


# --------------------------------------------------------------------------- #
# Les prompts
# --------------------------------------------------------------------------- #
def test_les_quatre_prompts_existent():
    assert set(prompts.PROMPTS) == {"cadrage", "concurrent", "leaders", "controle"}


@pytest.mark.parametrize("cle", ["cadrage", "concurrent", "leaders", "controle"])
def test_chaque_prompt_se_compose_sans_variable_residuelle(cle):
    variables = {nom: f"valeur_{nom}" for nom in prompts.VARIABLES}
    texte = prompts.compose(cle, variables)
    assert "{{" not in texte, "une variable n'a pas été remplacée"


def test_le_secteur_est_a_etablir_par_le_llm_pas_a_saisir():
    """Correction de conception : secteur, sous-secteur, produit et clients
    cibles ne se saisissent pas.

    Les faire taper serait du travail inutile — un LLM sait dans quel
    sous-secteur opère adidas — mais surtout ce serait **imposer une réponse à
    une question qui fait partie de l'analyse**. Le périmètre d'un marché n'est
    pas une donnée d'entrée, c'est le premier livrable du cadrage : le fixer
    d'avance revient à décider où s'arrête la concurrence avant d'avoir regardé.
    """
    texte = prompts.compose("cadrage", {"ENTREPRISE_ANALYSEE": "SEB"})
    assert "[a determiner par toi]" in texte
    assert "[A RENSEIGNER : SECTEUR_ACTIVITE]" not in texte
    assert "CE QUE TU DOIS ETABLIR TOI-MEME" in texte


def test_le_cadrage_etabli_est_restitue_dans_le_json():
    """Sans bloc `scoping`, ce que le LLM a établi se perdrait à l'import."""
    assert "scoping" in prompts.PROMPTS["cadrage"][1]


def test_une_indication_de_lanalyste_est_une_piste_pas_une_consigne():
    """Si les sources contredisent l'indication, le LLM doit le dire."""
    assert "Contredis-les si tes sources le justifient" in prompts.PROMPTS["cadrage"][1]


def test_seules_les_variables_vraiment_requises_sont_signalees():
    """Signaler comme manquant ce que le LLM doit établir serait trompeur."""
    manquantes = prompts.variables_manquantes("cadrage", {"ENTREPRISE_ANALYSEE": "SEB"})
    assert "ENTREPRISE_ANALYSEE" not in manquantes
    assert "SECTEUR_ACTIVITE" not in manquantes, "le LLM l'établit, ce n'est pas un manque"
    assert "DATE_DE_REFERENCE" in manquantes


def test_une_variable_facultative_vide_le_dit_explicitement():
    texte = prompts.compose("cadrage", {"ENTREPRISE_ANALYSEE": "SEB"})
    assert "[aucune indication fournie]" in texte


# --------------------------------------------------------------------------- #
# Accumulation des fragments
# --------------------------------------------------------------------------- #
def test_les_quatre_fragments_sont_declares():
    assert set(schema.FRAGMENTS) == {"cadrage", "concurrent", "leaders", "controle"}


# --------------------------------------------------------------------------- #
# Détection du type de fragment
# --------------------------------------------------------------------------- #
def test_la_sortie_du_prompt_1_est_reconnue():
    """Défaut constaté à l'usage : la liste déroulante restait sur « contrôle
    qualité », et la sortie du prompt 1 était traitée comme un dossier normalisé
    complet — sans que rien ne le signale."""
    cle, _ = schema.detecte_fragment({
        "market_definition": {"sector": "Articles de sport"},
        "proposed_competitors": [{"company_name": "Nike"}],
        "functional_matrix": [], "manual_verifications": [],
    })
    assert cle == "cadrage"


def test_la_sortie_du_prompt_3_est_reconnue():
    cle, _ = schema.detecte_fragment({
        "market_leadership_method": {"criteria": []},
        "market_leaders": [{"company_name": "Nike"}],
        "contrarian_conclusion": {"x": "y"}, "disruption_points": [],
    })
    assert cle == "leaders"


def test_la_sortie_du_prompt_2_est_reconnue():
    cle, _ = schema.detecte_fragment({
        "company_identity": {"company_name": "Nike"},
        "competitive_relevance": {}, "trajectory_signals": [],
    })
    assert cle == "concurrent"


def test_le_dossier_normalise_exige_deux_cles():
    """`controle` est le seul type qui projette : une détection permissive y
    ferait tomber des fragments partiels, et un fragment partiel pris pour un
    dossier complet qualifierait un titre avant la fin de l'analyse."""
    cle, _ = schema.detecte_fragment({"quality_control": {"validated": False}})
    assert cle != "controle"
    cle, _ = schema.detecte_fragment({
        "analysis_metadata": {"company_analyzed": "adidas"},
        "quality_control": {"validated": False},
    })
    assert cle == "controle"


def test_un_json_non_reconnu_le_dit():
    """On ne devine pas au hasard."""
    cle, raison = schema.detecte_fragment({"un_champ": 1})
    assert cle is None
    assert "aucune cle" in raison


def test_la_detection_donne_sa_raison():
    _, raison = schema.detecte_fragment({"market_leaders": [{"n": 1}]})
    assert "market_leaders" in raison


# --------------------------------------------------------------------------- #
# Le cadrage remonte dans le formulaire
# --------------------------------------------------------------------------- #
def test_un_cadrage_pose_dans_market_definition_est_accepte():
    """Le prompt demande un bloc `scoping`, mais les LLM posent spontanément ces
    champs dans `market_definition`. Refuser cette forme serait absurde."""
    d = schema.fusionne({}, {
        "market_definition": {"sector": "Articles de sport",
                              "subsector": "Chaussures", "product_analyzed": "Footwear",
                              "geography": "Monde"},
        "proposed_competitors": [{"company_name": "Nike", "country": "US"}],
    }, "cadrage")
    variables = schema.variables_depuis_dossier(d)
    assert variables["SECTEUR_ACTIVITE"] == "Articles de sport"
    assert variables["SOUS_SECTEUR"] == "Chaussures"
    assert variables["PRODUIT_OU_SERVICE"] == "Footwear"


def test_le_cadrage_etabli_par_le_llm_prime_sur_la_saisie():
    """C'est tout l'objet du prompt 1 : établir le périmètre. Une valeur saisie à
    la main ne doit pas l'emporter sur ce qu'il a déterminé."""
    d = schema.fusionne({"analysis_metadata": {"sector": "saisi a la main"}},
                        {"scoping": {"sector": "etabli par le LLM"}}, "cadrage")
    assert d["analysis_metadata"]["sector"] == "etabli par le LLM"


def test_les_concurrents_alimentent_la_liste_deroulante():
    d = {"competitors": [{"company_name": "Nike"}, {"company_name": "PUMA"},
                         {"company_name": ""}]}
    assert schema.noms_concurrents(d) == ["Nike", "PUMA"]


# --------------------------------------------------------------------------- #
# L'avancement rend visible ce qui a été importé
# --------------------------------------------------------------------------- #
def test_lavancement_montre_ce_qui_manque():
    """Sans cet état, l'analyste colle un JSON, lit un succès, et n'a aucun moyen
    de vérifier que la donnée est arrivée."""
    etapes = schema.avancement({})
    assert len(etapes) == 4
    assert not any(e["fait"] for e in etapes)
    assert all(e["manque"] or not e["fait"] for e in etapes)


def test_lavancement_signale_les_concurrents_sans_fiche():
    d = {"competitors": [{"company_name": "Nike"}, {"company_name": "PUMA"}],
         "company_profiles": [{"company_name": "Nike"}]}
    fiches = next(e for e in schema.avancement(d) if e["etape"].startswith("2"))
    assert not fiches["fait"]
    assert "PUMA" in fiches["manque"]


def test_lavancement_marque_le_cadrage_fait_des_quil_y_a_des_concurrents():
    d = {"competitors": [{"company_name": "Nike"}]}
    cadrage = next(e for e in schema.avancement(d) if e["etape"].startswith("1"))
    assert cadrage["fait"]


def test_le_cadrage_alimente_concurrents_fonctions_et_secteur():
    base = schema.gabarit("EQ:DE:ADIDAS", "adidas", date(2026, 8, 19))
    f = schema.fusionne(base, {
        "scoping": {"sector": "Consumer Discretionary",
                    "subsector": "Articles de sport"},
        "proposed_competitors": [
            {"company_name": "Nike", "country": "US", "competition_type": "direct",
             "relevance_explanation": "Premier mondial.", "status": "FAIT_VERIFIE"}],
        "functional_matrix": [{"function_name": "Innovation semelle"}],
        "sources": [{"url": "https://adidas-group.com", "date": "2026-08-01"}],
    }, "cadrage")
    assert len(f["competitors"]) == 1
    assert len(f["functional_analysis"]) == 1
    assert f["analysis_metadata"]["sector"] == "Consumer Discretionary"


def test_une_fiche_concurrent_senrichit_sans_ecraser():
    """On ajoute, on n'écrase pas : sinon l'ordre d'import deviendrait une
    variable cachée du résultat."""
    base = schema.fusionne(
        schema.gabarit("EQ:DE:ADIDAS", "adidas", date(2026, 8, 19)),
        {"proposed_competitors": [
            {"company_name": "Nike", "country": "US", "competition_type": "direct",
             "relevance_explanation": "Premier mondial.", "status": "FAIT_VERIFIE"}]},
        "cadrage")
    apres = schema.fusionne(
        base, {"company_identity": {"company_name": "Nike", "country": "US"}},
        "concurrent")
    assert len(apres["competitors"]) == 1, "le concurrent n'est pas dupliqué"
    assert len(apres["company_profiles"]) == 1
    assert apres["competitors"][0]["relevance_explanation"] == "Premier mondial."


def test_une_source_identique_nest_pas_dupliquee():
    source = [{"url": "https://nike.com", "date": "2026-08-02"}]
    base = schema.fusionne({}, {"sources": source}, "leaders")
    assert len(schema.fusionne(base, {"sources": source}, "leaders")["sources"]) == 1


def test_un_fragment_ne_perd_jamais_le_travail_precedent():
    base = schema.fusionne(
        schema.gabarit("EQ:DE:ADIDAS", "adidas", date(2026, 8, 19)),
        {"proposed_competitors": [
            {"company_name": "Nike", "country": "US", "competition_type": "direct",
             "relevance_explanation": "Justifié.", "status": "FAIT_VERIFIE"}],
         "sources": [{"url": "https://a.fr", "date": "2026-08-01"}]},
        "cadrage")
    apres = schema.fusionne(base, {"market_leaders": [{"name": "Nike"}]}, "leaders")
    assert len(apres["competitors"]) == 1
    assert len(apres["sources"]) == 1
    assert len(apres["market_leaders"]) == 1


@pytest.mark.parametrize("cle", ["cadrage", "concurrent", "leaders"])
def test_chaque_prompt_impose_la_hierarchie_des_sources(cle):
    texte = prompts.PROMPTS[cle][1]
    assert "HIERARCHIE DES SOURCES" in texte
    assert "sites officiels" in texte


@pytest.mark.parametrize("cle", ["cadrage", "concurrent", "leaders"])
def test_chaque_prompt_impose_les_statuts(cle):
    """Une phrase sans statut est inexploitable trois mois plus tard."""
    texte = prompts.PROMPTS[cle][1]
    for statut in ("FAIT_VERIFIE", "DECLARATION_ENTREPRISE", "ESTIMATION",
                   "INTERPRETATION", "HYPOTHESE"):
        assert statut in texte


def test_le_prompt_de_controle_interdit_de_completer_en_silence():
    texte = prompts.PROMPTS["controle"][1]
    assert "Ne complete jamais silencieusement" in texte
    assert "null" in texte


def test_le_prompt_concurrent_interdit_de_fabriquer_des_chiffres():
    texte = prompts.PROMPTS["concurrent"][1]
    assert "Ne fabrique aucun chiffre" in texte


def test_le_prompt_cadrage_annonce_la_relecture_humaine():
    """L'étape 3 du flux — vérification manuelle de la liste — doit être annoncée
    au LLM : c'est ce qui l'incite à signaler ses incertitudes."""
    texte = prompts.PROMPTS["cadrage"][1]
    assert "relue et corrigee par un humain" in texte


def test_un_prompt_inconnu_leve_clairement():
    with pytest.raises(KeyError, match="prompt inconnu"):
        prompts.compose("inexistant", {})


# --------------------------------------------------------------------------- #
# Péremption
# --------------------------------------------------------------------------- #
def test_la_peremption_est_a_dix_huit_mois():
    reference = date(2026, 8, 19)
    expiration = schema.peremption(reference)
    assert 540 <= (expiration - reference).days <= 552


# --------------------------------------------------------------------------- #
# État de la base
# --------------------------------------------------------------------------- #
def test_un_dossier_valide_alimente_le_groupe_de_pairs():
    from market_intelligence.db import fetch_all, fetch_one

    if fetch_one("select count(*) from market_analyses")[0] == 0:
        pytest.skip("aucun dossier importé")

    orphelins = fetch_all(
        """
        select a.analysis_id from market_analyses a
         where a.status = 'validated'
           and not exists (
             select 1 from peer_groups g
              where g.code = 'DOSSIER:' || (
                select i.internal_code from instruments i where i.id = a.instrument_id))
        """
    )
    assert orphelins == [], f"dossiers validés sans groupe de pairs : {orphelins}"


def test_un_dossier_validated_porte_toujours_un_analyste():
    """Contrainte de base, pas seulement de code : c'est le pivot du garde-fou."""
    from market_intelligence.db import fetch_all

    fautifs = fetch_all(
        "select analysis_id from market_analyses "
        "where status = 'validated' and analyst is null")
    assert fautifs == []


def test_le_dossier_stocke_reste_du_json_relisible():
    """Le dossier est une pièce, pas un ensemble de champs : le relire dans deux
    ans suppose de le retrouver dans la forme où il a été validé."""
    from market_intelligence.db import fetch_one

    ligne = fetch_one("select dossier from market_analyses limit 1")
    if ligne is None:
        pytest.skip("aucun dossier importé")
    assert isinstance(ligne[0], dict)
    assert json.dumps(ligne[0])
