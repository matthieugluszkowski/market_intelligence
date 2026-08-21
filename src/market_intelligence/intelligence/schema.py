"""Contrat de donnees du dossier concurrentiel (doc 08 SS8.5).

Pourquoi un contrat plutot qu'un calcul
----------------------------------------
La fiche instrument appelait une fonction d'agregation qualite et tombait en
`AttributeError`. Le symptome etait benin - un module en cache - mais il a revele
le vrai defaut : **l'ecran dependait d'un calcul, pas d'un contrat de donnees.**

Un calcul peut manquer, changer de signature, lever. Un contrat, non : on lit des
cles avec valeur par defaut, et une cle absente s'affiche « non renseigne ».

Trois regles, appliquees partout dans ce module :

- toute lecture passe par `lire()`, jamais par `dossier["cle"]` ;
- une cle absente rend une valeur neutre, elle ne leve pas ;
- `validated` vaut **false** par defaut. L'absence d'information n'est jamais un
  feu vert.

La regle qui compte le plus a l'import
---------------------------------------
**On ne complete jamais silencieusement une donnee manquante.** Une valeur
absente reste `null` et ressort dans le rapport de validation. Transformer une
absence en valeur plausible est la facon la plus efficace de fabriquer un dossier
qui a l'air complet et ne l'est pas.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta

# Statuts autorises pour toute affirmation du dossier (doc 08 SS8.3).
# Une phrase sans statut est inexploitable trois mois plus tard : on ne sait plus
# si elle a ete verifiee ou deduite.
STATUTS = (
    "FAIT_VERIFIE",            # etabli par une source primaire citee
    "DECLARATION_ENTREPRISE",  # l'entreprise l'affirme ; pas un fait independant
    "DONNEE_SECONDAIRE",       # reprise d'un agregateur, non remontee a la source
    "SIGNAL",                  # indice de trajectoire
    "ESTIMATION",              # chiffre calcule ou approche, avec sa methode
    "INTERPRETATION",          # lecture de l'analyste
    "HYPOTHESE",               # affirmation prospective, non demontrable
)

TYPES_DE_CONCURRENCE = ("direct", "indirect", "reference", "emerging")
NIVEAUX = ("low", "medium", "high")
COUVERTURES = ("unknown", "weak", "partial", "strong")
STATUTS_DOSSIER = ("draft", "review", "validated")

PEREMPTION_MOIS = 18

# Pays d'Europe geographique, pour le test de completude du groupe de pairs.
# Un concurrent hors de cette liste rend le groupe complet (doc 08, limite L1).
EUROPE = {
    "FR", "DE", "NL", "BE", "ES", "IT", "PT", "IE", "AT", "FI", "SE", "DK", "NO",
    "CH", "GB", "UK", "PL", "CZ", "GR", "LU", "HU", "RO", "SK", "SI", "HR", "BG",
    "EE", "LV", "LT", "IS", "MT", "CY",
}


# Suffixes juridiques ignores pour apparier deux noms de societe. « NIKE, Inc. »,
# « Nike Inc. » et « Nike » designent la meme entreprise ; sans cette tolerance,
# la fiche du prompt 2 ne se rattache a aucun concurrent du prompt 1 et le
# dossier compte deux fois la meme societe.
_SUFFIXES_JURIDIQUES = {
    "inc", "incorporated", "corp", "corporation", "co", "company", "ag", "se",
    "sa", "sas", "sarl", "plc", "ltd", "limited", "llc", "gmbh", "nv", "bv",
    "spa", "ab", "asa", "oyj", "kk", "kgaa", "holding", "holdings", "group",
    "groupe", "brands",
}


def normalise_nom(nom: str | None) -> str:
    """Cle d'appariement d'un nom de societe : casse, ponctuation et suffixes
    juridiques ignores."""
    if not nom:
        return ""
    mots = [m for m in re.split(r"[^a-z0-9]+", nom.lower()) if m]
    utiles = [m for m in mots if m not in _SUFFIXES_JURIDIQUES]
    return " ".join(utiles or mots)


def meme_societe(a: str | None, b: str | None) -> bool:
    """Vrai si deux noms designent selon toute vraisemblance la meme societe.

    Egalite des noms normalises, ou inclusion des mots de l'un dans l'autre :
    « HOKA (Deckers Brands) » et « HOKA ONE ONE (Deckers Brands) » doivent se
    reconnaitre sans qu'on maintienne une table d'alias.
    """
    na, nb = normalise_nom(a), normalise_nom(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    ma, mb = set(na.split()), set(nb.split())
    return ma <= mb or mb <= ma


def lire(dossier: dict | None, *chemin, defaut=None):
    """Acces defensif : `lire(d, 'quality_control', 'validated')`.

    C'est la seule facon de lire un dossier dans tout le projet. Un chemin
    absent rend `defaut` ; il ne leve jamais.
    """
    courant = dossier
    for cle in chemin:
        if not isinstance(courant, dict) or cle not in courant:
            return defaut
        courant = courant[cle]
    return defaut if courant is None else courant


def gabarit(internal_code: str, nom: str, reference_date: date) -> dict:
    """Dossier vide conforme au contrat. Sert de reference et de point de depart."""
    return {
        "analysis_metadata": {
            "analysis_id": f"{internal_code}@{reference_date.isoformat()}",
            "company_analyzed": nom,
            "sector": None,
            "subsector": None,
            "geography": None,
            "reference_date": reference_date.isoformat(),
            "analyst": None,
            "status": "draft",
        },
        "market_definition": {
            "description": None, "included_scope": [], "excluded_scope": [],
            "confidence": "low",
        },
        "customer_needs": [],
        "competitors": [],
        "functional_analysis": [],
        "company_profiles": [],
        "market_leaders": [],
        "market_trends": [],
        "future_scenarios": [],
        "strategic_assessment": {
            "position_verdict": None, "durability_verdict": None,
            "moat_sources": [], "threats": [], "main_strengths": [],
            "main_weaknesses": [], "rationale": None,
            "status": "INTERPRETATION",
        },
        "manual_review": [],
        "quality_control": {
            "validated": False, "quality_score": None,
            "blocking_issues": [], "review_date": None,
        },
        "sources": [],
    }


@dataclass
class Probleme:
    niveau: str      # 'BLOQUANT' | 'IMPORTANT' | 'MINEUR'
    element: str
    explication: str
    correction: str = ""


@dataclass
class Validation:
    problemes: list = field(default_factory=list)
    concurrents: int = 0
    concurrents_hors_europe: int = 0
    fonctions: int = 0
    sources: int = 0
    statuts_manquants: int = 0

    @property
    def bloquants(self) -> list:
        return [p for p in self.problemes if p.niveau == "BLOQUANT"]

    @property
    def importable(self) -> bool:
        return not self.bloquants

    @property
    def groupe_complet(self) -> bool:
        """Au moins un concurrent hors Europe (doc 08, limite L1)."""
        return self.concurrents_hors_europe > 0


def _ajoute(v: Validation, niveau: str, element: str, explication: str,
            correction: str = "") -> None:
    v.problemes.append(Probleme(niveau, element, explication, correction))


def valide(dossier: dict) -> Validation:
    """Controle le dossier avant import. N'ecrit rien, ne corrige rien.

    Ce qui est BLOQUANT empeche l'import : un dossier incomplet est refuse avec
    le detail des manques, jamais complete silencieusement.
    """
    v = Validation()

    if not isinstance(dossier, dict):
        _ajoute(v, "BLOQUANT", "racine", "le JSON n'est pas un objet")
        return v

    # --- metadonnees -------------------------------------------------------
    meta = lire(dossier, "analysis_metadata", defaut={})
    if not lire(meta, "company_analyzed"):
        _ajoute(v, "BLOQUANT", "analysis_metadata.company_analyzed",
                "entreprise analysee absente",
                "renseigner le nom exact de la societe")
    if not lire(meta, "reference_date"):
        _ajoute(v, "BLOQUANT", "analysis_metadata.reference_date",
                "date de reference absente : sans elle, on ne peut ni dater le "
                "dossier ni calculer sa peremption",
                "format AAAA-MM-JJ")
    statut = lire(meta, "status", defaut="draft")
    if statut not in STATUTS_DOSSIER:
        _ajoute(v, "IMPORTANT", "analysis_metadata.status",
                f"statut inconnu : {statut!r}",
                f"un de {', '.join(STATUTS_DOSSIER)}")

    # --- concurrents : le coeur du dossier ---------------------------------
    concurrents = lire(dossier, "competitors", defaut=[])
    if not isinstance(concurrents, list) or not concurrents:
        _ajoute(v, "BLOQUANT", "competitors",
                "aucun concurrent : c'est la donnee que ce dossier existe pour "
                "produire",
                "lancer le prompt 1, puis verifier la liste a la main")
        concurrents = []
    v.concurrents = len(concurrents)

    for i, c in enumerate(concurrents):
        prefixe = f"competitors[{i}]"
        nom = lire(c, "company_name")
        if not nom:
            _ajoute(v, "BLOQUANT", prefixe, "concurrent sans nom")
            continue
        type_ = lire(c, "competition_type")
        if type_ not in TYPES_DE_CONCURRENCE:
            _ajoute(v, "IMPORTANT", f"{prefixe} ({nom})",
                    f"type de concurrence invalide : {type_!r}",
                    f"un de {', '.join(TYPES_DE_CONCURRENCE)}")
        if not lire(c, "relevance_explanation"):
            # Regle du prompt 4 : aucune entreprise classee concurrente sans
            # justification. C'est la porte d'entree des faux concurrents.
            _ajoute(v, "BLOQUANT", f"{prefixe} ({nom})",
                    "aucune justification de pertinence concurrentielle",
                    "expliquer en quoi cette societe est reellement concurrente")
        if lire(c, "status") not in STATUTS:
            v.statuts_manquants += 1
        pays = (lire(c, "country", defaut="") or "").upper()[:2]
        if pays and pays not in EUROPE:
            v.concurrents_hors_europe += 1

    if v.concurrents and not v.concurrents_hors_europe:
        # Non bloquant : le dossier reste utile. Mais le titre ne pourra pas
        # atteindre `solid`, et il vaut mieux le savoir a l'import.
        _ajoute(v, "IMPORTANT", "competitors",
                "aucun concurrent hors Europe. Les menaces reelles viennent "
                "presque toujours de l'exterieur de l'univers - SharkNinja est "
                "americaine, BYD est chinoise. Le titre restera plafonne a "
                "`watch`.",
                "ajouter au moins un concurrent extra-europeen, avec son "
                "code pays sur deux lettres")

    # --- analyse fonctionnelle --------------------------------------------
    fonctions = lire(dossier, "functional_analysis", defaut=[])
    v.fonctions = len(fonctions) if isinstance(fonctions, list) else 0
    for i, f in enumerate(fonctions or []):
        if not lire(f, "function_name"):
            _ajoute(v, "MINEUR", f"functional_analysis[{i}]", "fonction sans nom")
        if lire(f, "company_coverage") not in COUVERTURES:
            _ajoute(v, "MINEUR", f"functional_analysis[{i}]",
                    "couverture non renseignee",
                    f"un de {', '.join(COUVERTURES)}")

    # --- sources -----------------------------------------------------------
    sources = lire(dossier, "sources", defaut=[])
    v.sources = len(sources) if isinstance(sources, list) else 0
    if v.sources == 0:
        _ajoute(v, "BLOQUANT", "sources",
                "aucune source. Une affirmation sans source n'est pas verifiable, "
                "et un dossier non verifiable ne doit pas entrer en base.",
                "citer au minimum les sites officiels consultes, avec leur date")
    for i, s in enumerate(sources or []):
        if not lire(s, "url"):
            _ajoute(v, "MINEUR", f"sources[{i}]", "source sans URL")
        if not lire(s, "date"):
            _ajoute(v, "MINEUR", f"sources[{i}]", "source sans date de consultation")

    if v.statuts_manquants:
        _ajoute(v, "IMPORTANT", "statuts",
                f"{v.statuts_manquants} affirmation(s) sans statut. Une phrase "
                f"sans statut est inexploitable trois mois plus tard : on ne sait "
                f"plus si elle a ete verifiee ou deduite.",
                f"un de {', '.join(STATUTS)}")

    # --- controle qualite ---------------------------------------------------
    # Le prompt 4 signale presque toujours des points a verifier a la main :
    # c'est son travail, pas un accident. Ils bloquent la validation tant qu'un
    # analyste ne les a pas acquittes **nominativement** - l'acquittement est
    # trace dans le dossier, rien n'est complete ni leve en silence.
    bloquants_controle = lire(dossier, "quality_control", "blocking_issues",
                              defaut=[])
    if bloquants_controle:
        acquittement = lire(dossier, "quality_control",
                            "blocking_issues_reviewed", defaut=None)
        acquitte_par = (lire(acquittement, "par") or "").strip() \
            if isinstance(acquittement, dict) else ""
        if acquitte_par:
            _ajoute(v, "IMPORTANT", "quality_control.blocking_issues",
                    f"{len(bloquants_controle)} point(s) bloquant(s) du controle "
                    f"qualite, acquitte(s) par {acquitte_par} le "
                    f"{lire(acquittement, 'le', defaut='?')}",
                    "verifier que l'acquittement couvre bien chaque point")
        else:
            _ajoute(v, "BLOQUANT", "quality_control.blocking_issues",
                    "le controle qualite du prompt 4 signale des problemes "
                    "bloquants non resolus",
                    "les traiter, ou les verifier a la main et les acquitter "
                    "nominativement a l'import")

    return v


# Chaque prompt rend un JSON de forme differente. Le dossier se construit donc
# par accumulation, fragment par fragment, et non en un seul import.
#
# Seul le fragment `controle` - la sortie du prompt 4 - est un dossier complet
# normalise : c'est le seul qui autorise la projection vers le moteur
# quantitatif. Les trois autres enrichissent un brouillon.
FRAGMENTS = {
    "cadrage": "1 · Cadrage et analyse fonctionnelle",
    "concurrent": "2 · Fiche d'un concurrent",
    "leaders": "3 · Leaders et perspectives",
    "controle": "4 · Contrôle qualité — dossier normalisé",
    "synthese": "5 · Synthèse décisionnelle et scoring",
}

# Verdicts possibles du prompt 5, avec leur libellé d'affichage. La sixième
# valeur est la plus importante : s'abstenir est une conclusion valide, et un
# outil qui ne la propose pas force une opinion là où il n'y a pas de dossier.
VERDICTS_SYNTHESE = {
    "study_buy": "Achat à étudier",
    "study_hold": "Conservation à étudier",
    "monitor": "Surveillance",
    "wait_for_better_valuation": "Attendre une meilleure valorisation",
    "avoid_or_wait": "Éviter ou attendre",
    "insufficient_to_conclude": "Insuffisant pour conclure",
}


# Cles distinctives de chaque sortie de prompt. La detection evite l'erreur la
# plus couteuse de cet ecran : coller la sortie du prompt 3 alors que la liste
# deroulante est restee sur son defaut, et voir le fragment traite comme un
# dossier normalise complet.
SIGNATURES = {
    "controle": ("quality_control", "analysis_metadata"),
    "cadrage": ("proposed_competitors", "functional_matrix", "actor_mapping",
                "manual_verifications", "customer_needs", "market_definition"),
    "concurrent": ("company_identity", "competitive_relevance", "trajectory_signals",
                   "products_and_features", "strategic_assessment"),
    "leaders": ("market_leadership_method", "market_leaders", "contrarian_conclusion",
                "disruption_points", "market_scenarios", "defensible_advantages"),
    # La synthese porte `analysis_metadata` mais PAS `quality_control` (elle a
    # son propre `quality_gate`) : elle ne peut donc pas etre prise pour un
    # dossier normalise par la detection du controle.
    "synthese": ("scores", "category_scores", "recommendation_status",
                 "quality_gate", "valuation_assessment", "market_assessment"),
}


def detecte_fragment(fragment: dict) -> tuple[str | None, str]:
    """Devine de quel prompt vient ce JSON, d'apres ses cles.

    Rend (cle, explication). `None` quand rien ne tranche - on ne devine pas au
    hasard, on le dit.

    `controle` exige **deux** cles simultanement, parce que c'est le seul type
    qui projette : une detection trop permissive y ferait tomber des fragments
    partiels, et un fragment partiel pris pour un dossier complet qualifierait un
    titre avant qu'on ait fini de le regarder.
    """
    if not isinstance(fragment, dict):
        return None, "le JSON n'est pas un objet"

    presentes = {c for c in fragment if fragment.get(c)}

    if all(c in presentes for c in SIGNATURES["controle"]):
        return "controle", "porte `analysis_metadata` et `quality_control`"

    scores = {
        cle: presentes & set(signature)
        for cle, signature in SIGNATURES.items() if cle != "controle"
    }
    meilleur = max(scores, key=lambda c: len(scores[c]))
    if not scores[meilleur]:
        return None, "aucune cle reconnue"
    return meilleur, "cles reconnues : " + ", ".join(sorted(scores[meilleur]))


def fusionne(dossier: dict, fragment: dict, type_fragment: str) -> dict:
    """Integre un fragment dans le dossier en construction.

    Regle de fusion, unique et volontairement simple : **on ajoute, on
    n'ecrase pas**. Un fragment qui arriverait a ecraser le travail precedent
    ferait perdre en silence une analyse deja relue - et l'ordre d'import
    deviendrait une variable cachee du resultat.

    Les listes sont concatenees en dedoublonnant sur la cle naturelle ; les
    dictionnaires ne remplacent que les cles absentes ou nulles.
    """
    resultat = json_copie(dossier or {})

    # Les metadonnees se propagent quel que soit le fragment, sans ecraser :
    # sans cela la date de reference, posee au premier fragment, se perdait aux
    # suivants et le dossier final etait declare incomplet a tort.
    _ajoute_dict(resultat, "analysis_metadata",
                 lire(fragment, "analysis_metadata", defaut={}))

    if type_fragment == "controle":
        # Le prompt 4 rend le dossier normalise complet : il fait autorite sur
        # la structure, mais ses profils de societes sont des **resumes**. Un
        # simple ecrasement perdrait les fiches detaillees du prompt 2 - forces,
        # faiblesses, signaux de trajectoire - deja relues. On fusionne donc les
        # profils societe par societe, sans rien perdre.
        profils_detailles = lire(resultat, "company_profiles", defaut=[])
        fusionne_dict(resultat, fragment, ecrase=True)
        resultat["company_profiles"] = _fusionne_profils(
            profils_detailles, lire(fragment, "company_profiles", defaut=[]))
        _rattache_fiches(resultat)
        return resultat

    if type_fragment == "cadrage":
        # Le cadrage peut arriver sous deux formes : le bloc `scoping` que le
        # prompt demande, ou les memes champs poses dans `market_definition` -
        # ce que les LLM font spontanement, et qu'il serait absurde de refuser.
        cadrage = lire(fragment, "scoping", defaut={})
        definition = lire(fragment, "market_definition", defaut={})
        if not cadrage and definition:
            cadrage = {
                "sector": lire(definition, "sector"),
                "subsector": lire(definition, "subsector"),
                "product_or_service": lire(definition, "product_or_service",
                                           defaut=lire(definition, "product_analyzed")),
                "target_market": lire(definition, "target_market"),
                "target_customers": lire(definition, "target_customers"),
                "geography": lire(definition, "geography"),
                "status": lire(definition, "status", defaut="INTERPRETATION"),
                "sources": lire(definition, "sources", defaut=[]),
            }
            cadrage = {k: v for k, v in cadrage.items() if v not in (None, [], "")}

        if cadrage:
            meta = resultat.setdefault("analysis_metadata", {})
            for cle in ("sector", "subsector", "geography"):
                # Le cadrage etabli par le LLM fait autorite sur une valeur
                # posee a la main : c'est tout l'objet du prompt 1.
                if lire(cadrage, cle):
                    meta[cle] = lire(cadrage, cle)
            resultat["scoping"] = {**lire(resultat, "scoping", defaut={}), **cadrage}
        _ajoute_dict(resultat, "market_definition",
                     lire(fragment, "market_definition", defaut={}))
        _concatene(resultat, "customer_needs",
                   lire(fragment, "customer_needs", defaut=[]))
        _concatene(resultat, "functional_analysis",
                   lire(fragment, "functional_matrix",
                        defaut=lire(fragment, "functional_analysis", defaut=[])),
                   cle="function_name")
        _concatene(resultat, "competitors",
                   lire(fragment, "proposed_competitors",
                        defaut=lire(fragment, "competitors", defaut=[])),
                   cle="company_name")
        _concatene(resultat, "manual_review",
                   lire(fragment, "manual_verifications", defaut=[]))

    elif type_fragment == "concurrent":
        # Une fiche par concurrent : elle s'ajoute aux profils et enrichit
        # l'entree correspondante de la liste des concurrents. Les LLM nomment
        # la societe tantot `company_name`, tantot `name`, tantot `legal_name`
        # (« NIKE, Inc. ») : refuser ces variantes laisserait une fiche
        # orpheline, rattachee a aucun concurrent.
        identite = lire(fragment, "company_identity", defaut={})
        nom = (lire(identite, "company_name") or lire(identite, "name")
               or lire(identite, "legal_name"))
        # Le nom canonique est celui de la liste des concurrents - c'est elle
        # que l'analyste a relue. « NIKE, Inc. » redevient « Nike Inc. ».
        for concurrent in resultat.get("competitors", []):
            if meme_societe(concurrent.get("company_name"), nom):
                nom = concurrent.get("company_name") or nom
                break
        profil = json_copie(fragment)
        if nom:
            profil["company_name"] = nom
        _concatene(resultat, "company_profiles", [profil], cle="company_name")
        _rattache_fiches(resultat)

    elif type_fragment == "leaders":
        for cle in ("market_leaders", "market_trends", "structural_trends",
                    "disruption_points", "market_scenarios", "recommendations",
                    "implications_for_company", "defensible_advantages"):
            valeurs = lire(fragment, cle, defaut=[])
            if valeurs:
                cible = "market_trends" if cle == "structural_trends" else cle
                cible = "future_scenarios" if cle == "market_scenarios" else cible
                _concatene(resultat, cible, valeurs)
        _ajoute_dict(resultat, "contrarian_conclusion",
                     lire(fragment, "contrarian_conclusion", defaut={}))

    elif type_fragment == "synthese":
        # La synthese est un avis DATE sur l'etat du dossier : la nouvelle
        # remplace l'ancienne - deux avis contradictoires qui coexistent sans
        # date de peremption ne s'additionnent pas, ils se neutralisent.
        # C'est l'exception assumee a la regle « on ajoute, on n'ecrase pas ».
        resultat["synthese"] = json_copie(fragment)
        scores = lire(fragment, "scores", defaut={})
        porte = lire(fragment, "quality_gate", defaut={})
        # Raccourcis d'affichage (modele de donnees du doc 08 §8.5) : l'ecran
        # lit ces deux blocs, jamais le JSON complet de la synthese.
        resultat["scoring"] = {
            "attractiveness_score": lire(scores, "attractiveness_score"),
            "confidence_score": lire(scores, "confidence_score"),
            "alignment_score": lire(scores, "alignment_score"),
            "score_version": lire(scores, "score_version", defaut="1.0"),
            "scored_at": lire(fragment, "analysis_metadata", "reference_date"),
            "scored_by": lire(scores, "scored_by", defaut="llm"),
            # Toujours non relu a l'import : un humain peut relire une
            # synthese, jamais la produire retroactivement.
            "human_review_status": "not_reviewed",
        }
        resultat["decision_gate"] = {
            "quality_control_passed": bool(lire(porte, "passed", defaut=False)),
            "blocking_issues_count": len(lire(porte, "blocking_issues",
                                              defaut=[]) or []),
            "manual_review_required": bool(lire(porte, "manual_review_required",
                                                defaut=True)),
            "conclusion_allowed": bool(lire(porte, "conclusion_allowed",
                                            defaut=False)),
        }

    _concatene(resultat, "sources", lire(fragment, "sources", defaut=[]), cle="url")
    return resultat


def json_copie(valeur):
    import json as _json
    return _json.loads(_json.dumps(valeur, ensure_ascii=False, default=str))


def fusionne_dict(cible: dict, source: dict, ecrase: bool = False) -> None:
    for cle, valeur in (source or {}).items():
        if ecrase or cle not in cible or cible[cle] in (None, [], {}):
            cible[cle] = valeur


def _ajoute_dict(dossier: dict, cle: str, valeurs: dict) -> None:
    if not valeurs:
        return
    fusionne_dict(dossier.setdefault(cle, {}), valeurs)


def _concatene(dossier: dict, champ: str, valeurs: list, cle: str = "") -> None:
    """Ajoute sans doublon. `cle` designe le champ d'identite des elements.

    Sans cle d'identite, on concatene simplement : c'est le cas des listes de
    texte libre, ou un doublon apparent peut etre deux observations distinctes.
    """
    if not valeurs:
        return
    existants = dossier.setdefault(champ, [])
    if not isinstance(existants, list):
        return
    if cle:
        deja = {(lire(e, cle) or "").lower() for e in existants
                if isinstance(e, dict)}
        for valeur in valeurs:
            identite = (lire(valeur, cle) or "").lower()
            if identite and identite in deja:
                continue
            deja.add(identite)
            existants.append(valeur)
    else:
        existants.extend(valeurs)


def _fusionne_profils(detailles: list, resumes: list) -> list:
    """Fusionne les profils du prompt 4 (resumes) dans ceux du prompt 2
    (detailles), societe par societe. Aucune fiche detaillee n'est perdue :
    le resume ne fait que completer les cles absentes.
    """
    resultat = [json_copie(p) for p in (detailles or []) if isinstance(p, dict)]
    for resume_ in resumes or []:
        if not isinstance(resume_, dict):
            continue
        nom = lire(resume_, "company_name", defaut=lire(resume_, "normalized_name"))
        for profil in resultat:
            if meme_societe(profil.get("company_name"), nom):
                fusionne_dict(profil, resume_)  # complete, n'ecrase pas
                break
        else:
            resultat.append(json_copie(resume_))
    return resultat


def _rattache_fiches(dossier: dict) -> None:
    """Marque `profile_available` sur chaque concurrent dont une fiche existe,
    et complete son pays depuis la fiche s'il manque. C'est ce marquage qui
    raye le concurrent de la liste « sans fiche » du prompt 2."""
    profils = [p for p in lire(dossier, "company_profiles", defaut=[])
               if isinstance(p, dict)]
    for concurrent in lire(dossier, "competitors", defaut=[]):
        if not isinstance(concurrent, dict):
            continue
        for profil in profils:
            if meme_societe(concurrent.get("company_name"),
                            profil.get("company_name")):
                concurrent["profile_available"] = True
                pays = lire(profil, "company_identity", "country")
                if pays and not concurrent.get("country"):
                    concurrent["country"] = pays
                break


def peremption(reference_date: date) -> date:
    """Une evaluation de 2026 inspire la meme confiance qu'une de 2029, et c'est
    le probleme. La peremption force la revue."""
    return reference_date + timedelta(days=int(PEREMPTION_MOIS * 30.44))


def avancement(dossier: dict) -> list[dict]:
    """Ce que chaque etape a apporte au dossier, et ce qui manque encore.

    Sans cet etat, l'ecran ne montre rien de ce qui a ete importe : l'analyste
    colle un JSON, voit un message de succes, et n'a aucun moyen de verifier que
    la donnee est arrivee ni ou elle en est. C'est exactement le doute qui rend
    un outil inutilisable - on finit par tout reimporter dans le doute.
    """
    concurrents = lire(dossier, "competitors", defaut=[])
    profils = lire(dossier, "company_profiles", defaut=[])
    noms_profiles = [lire(p, "company_name") for p in profils]
    sans_fiche = [lire(c, "company_name") for c in concurrents
                  if not any(meme_societe(lire(c, "company_name"), n)
                             for n in noms_profiles)]

    strategie = lire(dossier, "strategic_assessment", defaut={})
    synthese = lire(dossier, "synthese", defaut={})
    verdict_synthese = lire(synthese, "recommendation_status", "classification")
    scoring = lire(dossier, "scoring", defaut={})
    return [
        {
            "etape": "1 · Cadrage",
            "apporte": (f"{len(concurrents)} concurrent(s), "
                        f"{len(lire(dossier, 'functional_analysis', defaut=[]))} fonction(s)"),
            "fait": bool(concurrents),
            "manque": "" if concurrents else "lancer le prompt 1",
        },
        {
            "etape": "2 · Fiches concurrents",
            "apporte": f"{len(profils)} fiche(s) sur {len(concurrents)}",
            "fait": bool(profils) and not sans_fiche,
            "manque": ("sans fiche : " + ", ".join(n for n in sans_fiche[:6] if n)
                       if sans_fiche else ""),
        },
        {
            "etape": "3 · Leaders",
            "apporte": (f"{len(lire(dossier, 'market_leaders', defaut=[]))} leader(s), "
                        f"{len(lire(dossier, 'market_trends', defaut=[]))} tendance(s)"),
            "fait": bool(lire(dossier, "market_leaders", defaut=[])),
            "manque": "" if lire(dossier, "market_leaders", defaut=[]) else "lancer le prompt 3",
        },
        {
            "etape": "4 · Contrôle qualité",
            "apporte": ("verdicts posés"
                        if lire(strategie, "position_verdict") else "aucun verdict"),
            "fait": bool(lire(strategie, "position_verdict")
                         and lire(strategie, "durability_verdict")),
            "manque": ("`strategic_assessment` doit porter `position_verdict` et "
                       "`durability_verdict`"
                       if not lire(strategie, "position_verdict") else ""),
        },
        {
            "etape": "5 · Synthèse & scoring",
            "apporte": ((f"{VERDICTS_SYNTHESE.get(verdict_synthese, verdict_synthese)} · "
                         f"attractivité {lire(scoring, 'attractiveness_score', defaut='—')}/100 · "
                         f"confiance {lire(scoring, 'confidence_score', defaut='—')}/100")
                        if verdict_synthese else "aucune synthèse"),
            "fait": bool(verdict_synthese),
            "manque": "" if verdict_synthese else "lancer le prompt 5, après le prompt 4",
        },
    ]


def noms_concurrents(dossier: dict) -> list[str]:
    """Concurrents retenus, pour la liste deroulante du prompt 2."""
    return [n for n in ((lire(c, "company_name") or "").strip()
                        for c in lire(dossier, "competitors", defaut=[])) if n]


def variables_depuis_dossier(dossier: dict) -> dict:
    """Prefill du formulaire depuis ce qui a deja ete etabli.

    Ce que le LLM a determine au prompt 1 doit revenir dans le formulaire :
    sinon les prompts suivants repartent de zero et redemandent au modele
    d'etablir ce qu'il a deja etabli, avec le risque qu'il reponde autrement.
    """
    cadrage = lire(dossier, "scoping", defaut={})
    definition = lire(dossier, "market_definition", defaut={})
    meta = lire(dossier, "analysis_metadata", defaut={})

    def premier(*valeurs):
        for v in valeurs:
            if v:
                return v if isinstance(v, str) else str(v)
        return ""

    return {
        "SECTEUR_ACTIVITE": premier(lire(cadrage, "sector"), lire(definition, "sector"),
                                    lire(meta, "sector")),
        "SOUS_SECTEUR": premier(lire(cadrage, "subsector"), lire(definition, "subsector"),
                                lire(meta, "subsector")),
        "PRODUIT_OU_SERVICE": premier(lire(cadrage, "product_or_service"),
                                      lire(definition, "product_analyzed"),
                                      lire(definition, "product_or_service")),
        "MARCHE_CIBLE": premier(lire(cadrage, "target_market"),
                                lire(definition, "target_market")),
        "CLIENTS_CIBLES": premier(lire(cadrage, "target_customers"),
                                  lire(definition, "target_customers")),
        "PAYS_ET_ZONE_GEOGRAPHIQUE": premier(lire(cadrage, "geography"),
                                             lire(definition, "geography"),
                                             lire(meta, "geography")),
        "CONCURRENTS_CONNUS": ", ".join(noms_concurrents(dossier)),
    }


def resume(dossier: dict) -> dict:
    """Lecture d'affichage. Toutes les cles ont une valeur par defaut.

    C'est cette fonction que l'interface appelle - jamais le dossier brut.
    """
    meta = lire(dossier, "analysis_metadata", defaut={})
    controle = lire(dossier, "quality_control", defaut={})
    concurrents = lire(dossier, "competitors", defaut=[])
    return {
        "entreprise": lire(meta, "company_analyzed", defaut="non renseigne"),
        "secteur": lire(meta, "sector", defaut="non renseigne"),
        "sous_secteur": lire(meta, "subsector", defaut="non renseigne"),
        "zone": lire(meta, "geography", defaut="non renseigne"),
        "date_reference": lire(meta, "reference_date", defaut="non renseigne"),
        "analyste": lire(meta, "analyst", defaut=None),
        "statut": lire(meta, "status", defaut="draft"),
        # false par defaut : l'absence d'information n'est jamais un feu vert.
        "valide": bool(lire(controle, "validated", defaut=False)),
        "score_qualite": lire(controle, "quality_score", defaut=None),
        "n_concurrents": len(concurrents) if isinstance(concurrents, list) else 0,
        "n_fonctions": len(lire(dossier, "functional_analysis", defaut=[])),
        "n_sources": len(lire(dossier, "sources", defaut=[])),
        "a_revoir": lire(dossier, "manual_review", defaut=[]),
    }
