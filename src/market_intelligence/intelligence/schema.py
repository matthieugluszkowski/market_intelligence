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
    if lire(dossier, "quality_control", "blocking_issues", defaut=[]):
        _ajoute(v, "BLOQUANT", "quality_control.blocking_issues",
                "le controle qualite du prompt 4 signale des problemes bloquants "
                "non resolus",
                "les traiter avant import")

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
}


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
        # Le prompt 4 rend le dossier normalise complet : il fait autorite, mais
        # on conserve ce qu'il aurait perdu.
        fusionne_dict(resultat, fragment, ecrase=True)
        return resultat

    if type_fragment == "cadrage":
        cadrage = lire(fragment, "scoping", defaut={})
        if cadrage:
            meta = resultat.setdefault("analysis_metadata", {})
            for cle_source, cle_cible in (("sector", "sector"),
                                          ("subsector", "subsector")):
                if not meta.get(cle_cible):
                    meta[cle_cible] = lire(cadrage, cle_source)
            resultat["scoping"] = cadrage
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
        # l'entree correspondante de la liste des concurrents.
        nom = lire(fragment, "company_identity", "company_name",
                   defaut=lire(fragment, "company_identity", "name"))
        profil = json_copie(fragment)
        if nom:
            profil["company_name"] = nom
        _concatene(resultat, "company_profiles", [profil], cle="company_name")
        if nom:
            for concurrent in resultat.get("competitors", []):
                if (concurrent.get("company_name") or "").lower() == nom.lower():
                    concurrent.setdefault(
                        "country", lire(fragment, "company_identity", "country"))
                    concurrent["profile_available"] = True

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


def peremption(reference_date: date) -> date:
    """Une evaluation de 2026 inspire la meme confiance qu'une de 2029, et c'est
    le probleme. La peremption force la revue."""
    return reference_date + timedelta(days=int(PEREMPTION_MOIS * 30.44))


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
