"""Position concurrentielle : le dossier reduit a ce qui decide.

Ce que ce module remplace, et pourquoi
---------------------------------------
La version precedente demandait cinq prompts et 34 000 caracteres de consignes
pour produire un dossier de vingt-deux blocs : definition de marche, besoins
clients, analyse fonctionnelle, tendances, scenarios prospectifs, controle
qualite, synthese decisionnelle, sept notes par categorie, trois scores. Sur
EssilorLuxottica, ce dispositif a rendu **30/100 de confiance et un refus de
conclure** pour un dossier dont le paragraphe de synthese disait « leader
incontesté ». Le detail avait mange la conclusion.

Quatre questions, et rien d'autre
----------------------------------
1. L'entreprise est-elle **leader** de son marche ?
2. **Depuis quand** - et si elle l'a perdu, depuis quand ?
3. Qui sont ses **concurrents**, et en quoi chacun est une menace ?
4. Quelles autres menaces pesent sur elle, et **en quoi c'est dangereux** ?

Tout le reste - part de marche au dixieme, scenarios a cinq ans, notation de la
gouvernance - est du detail qui ne change pas la decision d'acheter ou non.

Le score est calcule ici, jamais demande au modele
---------------------------------------------------
Un LLM a qui l'on demande une note sur 100 en invente une : deux executions du
meme prompt donnent deux nombres, et aucun n'est reconstituable. Le modele rend
donc des **verdicts** - leader ou non, depuis quelle annee, quel danger pour
chaque menace - et le score se calcule ici, par une formule qui s'affiche a
cote du resultat. Reproductible, verifiable, et surtout : **aucune porte de
qualite ne peut plus le plafonner**.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

VERSION = 2

POSITIONS = ("leader", "challenger", "suiveur", "niche")
DURABILITES = ("solid", "watch", "eroding", "none")
DANGERS = ("eleve", "moyen", "faible")
TYPES_DE_MENACE = ("directe", "indirecte")
NATURES = ("concurrent", "reglementaire", "technologique", "commerciale",
           "financiere", "autre")

# Sources de rente : ce qui protege une position, pas ce qui l'a produite. La
# liste est fermee - un moat qui ne rentre dans aucune de ces cases est en
# general une qualite operationnelle, pas une barriere.
SOURCES_DE_RENTE = ("brand", "patent", "switching", "network", "cost", "scale",
                    "regulatory", "distribution")

LIBELLES_POSITION = {
    "leader": "leader",
    "challenger": "challenger",
    "suiveur": "suiveur",
    "niche": "acteur de niche",
}
LIBELLES_DURABILITE = {
    "solid": "solide",
    "watch": "à surveiller",
    "eroding": "en érosion",
    "none": "aucune",
}
LIBELLES_DANGER = {"eleve": "élevé", "moyen": "moyen", "faible": "faible"}

# --------------------------------------------------------------------------- #
# Le bareme
#
# Chaque terme repond a une des quatre questions, et un seul. Les poids sont
# arbitraires - tout bareme l'est - mais ils sont **affiches**, ce qui permet de
# les discuter. Un score dont on ne voit pas la construction ne se discute pas,
# il se subit.
# --------------------------------------------------------------------------- #
BASE_POSITION = {"leader": 50, "challenger": 35, "niche": 30, "suiveur": 20}

POINTS_PAR_ANNEE = 2
ANNEES_PLAFOND = 10          # au-dela de dix ans, une position est etablie

POINTS_DURABILITE = {"solid": 20, "watch": 10, "eroding": -10, "none": -20}

# Une menace `faible` ne retire rien. C'est deliberé : compter chaque menace
# identifiee punirait le dossier le plus complet, alors qu'un concurrent
# recense et juge peu dangereux est une information rassurante, pas un risque.
POINTS_DANGER = {"eleve": -10, "moyen": -5, "faible": 0}
PLANCHER_MENACES = -30       # au-dela, on empile sans rien apprendre

# Une position perdue recemment est un fait different d'une position perdue il y
# a quinze ans : la premiere est une trajectoire, la seconde un etat de fait que
# le marche a deja digere. Le malus s'efface donc en cinq ans.
MALUS_PERTE = -15
EFFACEMENT_PAR_ANNEE = 3


@dataclass
class Ligne:
    """Une ligne du bareme, telle qu'elle s'affiche."""
    libelle: str
    detail: str
    points: int


@dataclass
class Score:
    total: int
    lignes: list = field(default_factory=list)
    reserves: list = field(default_factory=list)

    @property
    def niveau(self) -> str:
        if self.total >= 75:
            return "position forte"
        if self.total >= 55:
            return "position tenue"
        if self.total >= 35:
            return "position contestee"
        return "position fragile"


@dataclass
class Probleme:
    niveau: str      # 'BLOQUANT' | 'IMPORTANT'
    element: str
    explication: str


@dataclass
class Validation:
    problemes: list = field(default_factory=list)
    concurrents: int = 0
    autres_menaces: int = 0

    @property
    def bloquants(self) -> list:
        return [p for p in self.problemes if p.niveau == "BLOQUANT"]

    @property
    def importable(self) -> bool:
        return not self.bloquants


def _ajoute(v: Validation, niveau: str, element: str, explication: str) -> None:
    v.problemes.append(Probleme(niveau, element, explication))


def lire(source, *chemin, defaut=None):
    """Acces defensif : `lire(d, 'position', 'verdict')`.

    Un dossier vient d'un LLM : n'importe quelle cle peut manquer ou porter
    `null`. Un acces direct ferait tomber l'ecran sur une cle absente, ce qui
    transforme un dossier incomplet - le cas normal - en page cassee.
    """
    courant = source
    for cle in chemin:
        if not isinstance(courant, dict):
            return defaut
        courant = courant.get(cle)
    return defaut if courant is None else courant


def menaces(dossier: dict) -> list:
    """Concurrents et autres menaces, dans une seule liste ordonnee.

    Les concurrents sont des menaces qui portent un nom d'entreprise ; une
    contrainte reglementaire ou une rupture technologique n'en porte pas. Les
    separer a la saisie evite de faire passer un risque de licence pour une
    societe ; les reunir a la lecture evite d'avoir a regarder deux tableaux
    pour savoir ce qui menace l'entreprise.
    """
    rang = {"eleve": 0, "moyen": 1, "faible": 2}
    ensemble = []
    for c in lire(dossier, "concurrents", defaut=[]) or []:
        ensemble.append({**c, "nature": lire(c, "nature", defaut="concurrent")})
    for m in lire(dossier, "autres_menaces", defaut=[]) or []:
        ensemble.append({**m, "nature": lire(m, "nature", defaut="autre")})
    return sorted(ensemble, key=lambda m: rang.get(m.get("danger"), 3))


def annees_de_position(dossier: dict, aujourdhui: date | None = None) -> int | None:
    """Depuis combien d'annees l'entreprise occupe sa position actuelle."""
    depuis = lire(dossier, "position", "depuis")
    if not isinstance(depuis, int):
        return None
    reference = aujourdhui or _date_de_reference(dossier)
    return max(0, reference.year - depuis)


def annees_depuis_la_perte(dossier: dict, aujourdhui: date | None = None) -> int | None:
    perdue = lire(dossier, "position", "perdue_en")
    if not isinstance(perdue, int):
        return None
    reference = aujourdhui or _date_de_reference(dossier)
    return max(0, reference.year - perdue)


def _date_de_reference(dossier: dict) -> date:
    brut = lire(dossier, "date_reference")
    if isinstance(brut, date):
        return brut
    if isinstance(brut, str):
        try:
            return date.fromisoformat(brut[:10])
        except ValueError:
            pass
    return date.today()


def calcule_le_score(dossier: dict, aujourdhui: date | None = None) -> Score:
    """Le score de solidite concurrentielle, terme par terme.

    Rend les lignes du bareme en plus du total : l'ecran les affiche, et un
    total dont on ne voit pas la construction ne se discute pas.
    """
    lignes, reserves = [], []

    verdict = lire(dossier, "position", "verdict")
    base = BASE_POSITION.get(verdict)
    if base is None:
        return Score(0, [], ["position non renseignée : aucun score calculable"])
    lignes.append(Ligne("Position", LIBELLES_POSITION.get(verdict, verdict), base))

    annees = annees_de_position(dossier, aujourdhui)
    if annees is None:
        reserves.append(
            f"année d'accession non renseignée : jusqu'à "
            f"{POINTS_PAR_ANNEE * ANNEES_PLAFOND} points d'ancienneté non comptés")
        lignes.append(Ligne("Ancienneté", "non renseignée", 0))
    else:
        points = min(annees, ANNEES_PLAFOND) * POINTS_PAR_ANNEE
        lignes.append(Ligne("Ancienneté", f"{annees} an(s)", points))

    durabilite = lire(dossier, "durabilite", "verdict")
    if durabilite in POINTS_DURABILITE:
        lignes.append(Ligne("Durabilité",
                            LIBELLES_DURABILITE.get(durabilite, durabilite),
                            POINTS_DURABILITE[durabilite]))
    else:
        reserves.append("durabilité non renseignée : aucun point attribué")
        lignes.append(Ligne("Durabilité", "non renseignée", 0))

    tous = menaces(dossier)
    compte = {niveau: sum(1 for m in tous if m.get("danger") == niveau)
              for niveau in DANGERS}
    brut = sum(POINTS_DANGER.get(m.get("danger"), 0) for m in tous)
    points_menaces = max(brut, PLANCHER_MENACES)
    detail = " · ".join(f"{compte[n]} {LIBELLES_DANGER[n]}" for n in DANGERS
                        if compte[n]) or "aucune recensée"
    if brut < PLANCHER_MENACES:
        detail += f" (plafonné à {PLANCHER_MENACES})"
    lignes.append(Ligne("Menaces", detail, points_menaces))
    if not tous:
        reserves.append("aucune menace recensée : un dossier sans menace est "
                        "un dossier incomplet, pas une entreprise sans risque")

    depuis_la_perte = annees_depuis_la_perte(dossier, aujourdhui)
    if depuis_la_perte is not None:
        malus = min(0, MALUS_PERTE + EFFACEMENT_PAR_ANNEE * depuis_la_perte)
        lignes.append(Ligne(
            "Position perdue",
            f"il y a {depuis_la_perte} an(s)" if depuis_la_perte else "cette année",
            malus))

    total = max(0, min(100, sum(ligne.points for ligne in lignes)))
    return Score(total, lignes, reserves)


def valide(dossier: dict) -> Validation:
    """Controle avant import. N'ecrit rien, ne corrige rien.

    Est BLOQUANT ce qui rend le dossier **inexploitable** : sans entreprise,
    sans verdict de position, ou sans aucune menace, il n'y a rien a lire. Tout
    le reste est signale et laisse passer - le dossier reste utile.
    """
    v = Validation()

    if not isinstance(dossier, dict):
        _ajoute(v, "BLOQUANT", "racine", "le JSON n'est pas un objet")
        return v

    if not (lire(dossier, "entreprise") or "").strip():
        _ajoute(v, "BLOQUANT", "entreprise",
                "aucune entreprise analysee : le dossier ne se rattache a rien")

    verdict = lire(dossier, "position", "verdict")
    if verdict not in POSITIONS:
        _ajoute(v, "BLOQUANT", "position.verdict",
                f"verdict de position absent ou inconnu ({verdict!r}), "
                f"attendu un de {', '.join(POSITIONS)}")

    depuis = lire(dossier, "position", "depuis")
    if depuis is None:
        _ajoute(v, "IMPORTANT", "position.depuis",
                "annee d'accession non renseignee : « leader » sans « depuis "
                "quand » ne dit pas si la position est etablie ou fraiche")
    elif not isinstance(depuis, int) or not 1800 <= depuis <= 2100:
        _ajoute(v, "IMPORTANT", "position.depuis",
                f"annee d'accession invalide ({depuis!r})")

    perdue = lire(dossier, "position", "perdue_en")
    if perdue is not None and verdict == "leader":
        _ajoute(v, "IMPORTANT", "position.perdue_en",
                "une position perdue et un verdict `leader` se contredisent")

    durabilite = lire(dossier, "durabilite", "verdict")
    if durabilite not in DURABILITES:
        _ajoute(v, "IMPORTANT", "durabilite.verdict",
                f"durabilite absente ou inconnue ({durabilite!r})")

    for source in lire(dossier, "durabilite", "sources_de_rente", defaut=[]) or []:
        if source not in SOURCES_DE_RENTE:
            _ajoute(v, "IMPORTANT", "durabilite.sources_de_rente",
                    f"source de rente inconnue : {source!r}")

    concurrents = lire(dossier, "concurrents", defaut=[]) or []
    autres = lire(dossier, "autres_menaces", defaut=[]) or []
    v.concurrents, v.autres_menaces = len(concurrents), len(autres)

    if not concurrents and not autres:
        _ajoute(v, "BLOQUANT", "concurrents",
                "aucun concurrent ni menace. Une entreprise sans concurrent "
                "identifie n'existe pas : c'est l'analyse qui manque, pas le "
                "concurrent")

    for prefixe, liste in (("concurrents", concurrents), ("autres_menaces", autres)):
        for i, m in enumerate(liste):
            ou = f"{prefixe}[{i}]"
            nom = (lire(m, "nom") or "").strip()
            if not nom:
                _ajoute(v, "BLOQUANT", ou, "menace sans nom")
                continue
            if lire(m, "danger") not in DANGERS:
                _ajoute(v, "IMPORTANT", f"{ou} ({nom})",
                        f"niveau de danger absent ou inconnu, attendu un de "
                        f"{', '.join(DANGERS)}")
            if lire(m, "type") not in TYPES_DE_MENACE:
                _ajoute(v, "IMPORTANT", f"{ou} ({nom})",
                        "menace ni directe ni indirecte")
            if not (lire(m, "pourquoi_dangereux") or "").strip():
                _ajoute(v, "IMPORTANT", f"{ou} ({nom})",
                        "aucune explication du danger. Un concurrent nomme sans "
                        "raison ne se relit pas : dans six mois on ne saura plus "
                        "pourquoi il figurait la")

    if not (lire(dossier, "resume") or "").strip():
        _ajoute(v, "IMPORTANT", "resume",
                "aucun resume : c'est la phrase qu'on relit en premier")

    if not (lire(dossier, "sources", defaut=[]) or []):
        _ajoute(v, "IMPORTANT", "sources",
                "aucune source citee : rien n'est verifiable")

    return v


# --------------------------------------------------------------------------- #
# Migration depuis l'ancien dossier
#
# Les dossiers deja importes ne sont pas rejoues : on en extrait ce qui repond
# aux quatre questions, on marque ce qui vient d'une conversion, et on laisse
# vide ce qui n'existait pas. **L'annee d'accession n'existe nulle part dans
# l'ancien format** - c'est precisement la question que l'ancien dispositif ne
# posait pas, et elle se saisit a la main.
# --------------------------------------------------------------------------- #
TYPE_MIGRE = {"direct": "directe", "emerging": "directe",
              "indirect": "indirecte", "reference": "indirecte"}


def _danger_migre(score) -> str:
    """Convertit un `relevance_score` de l'ancien format en niveau de danger.

    L'echelle etait utilisee de facon incoherente d'un dossier a l'autre - Nike
    a 10 chez adidas, le concurrent le plus dangereux d'Essilor a 4 - donc la
    conversion est prudente et le resultat est marque comme a revoir.
    """
    if not isinstance(score, (int, float)):
        return "faible"
    if score >= 8:
        return "eleve"
    if score >= 5:
        return "moyen"
    return "faible"


def migre(ancien: dict, entreprise: str | None = None) -> dict:
    """Convertit un dossier de l'ancien format vers celui-ci."""
    strategique = lire(ancien, "strategic_assessment", defaut={})

    concurrents = []
    for c in lire(ancien, "competitors", defaut=[]) or []:
        nom = (lire(c, "company_name") or lire(c, "legal_name") or "").strip()
        if not nom:
            continue
        concurrents.append({
            "nom": nom,
            "nature": "concurrent",
            "type": TYPE_MIGRE.get(lire(c, "competition_type"), "directe"),
            "danger": _danger_migre(lire(c, "relevance_score")),
            "pourquoi_dangereux": lire(c, "relevance_explanation") or "",
            "pays": lire(c, "country"),
            "signal_a_surveiller": None,
            "statut": "MIGRE",
        })

    autres = []
    for m in lire(strategique, "threats", defaut=[]) or []:
        if isinstance(m, dict):
            nom = (lire(m, "threat") or lire(m, "nom") or "").strip()
            explication = lire(m, "explication") or lire(m, "horizon") or ""
        else:
            nom, explication = str(m).strip(), ""
        if not nom:
            continue
        autres.append({
            "nom": nom,
            "nature": "autre",
            "type": "indirecte",
            # Conversion prudente : l'ancien format ne portait aucun niveau de
            # danger, et en inventer un fausserait le score sans le dire.
            "danger": "moyen",
            "pourquoi_dangereux": explication,
            "signal_a_surveiller": None,
            "statut": "MIGRE",
        })

    return {
        "version": VERSION,
        "entreprise": entreprise or lire(ancien, "analysis_metadata",
                                          "company_analyzed") or "",
        "date_reference": lire(ancien, "analysis_metadata", "reference_date"),
        "marche": lire(ancien, "market_definition", "description"),
        "position": {
            "verdict": lire(strategique, "position_verdict"),
            # L'ancien format ne posait pas la question : elle se saisit a la main.
            "depuis": None,
            "perdue_en": None,
            "preuve": None,
            "statut": "MIGRE",
        },
        "durabilite": {
            "verdict": lire(strategique, "durability_verdict"),
            "sources_de_rente": lire(strategique, "moat_sources", defaut=[]) or [],
            "justification": None,
        },
        "concurrents": concurrents,
        "autres_menaces": autres,
        "resume": lire(strategique, "rationale") or "",
        "sources": lire(ancien, "sources", defaut=[]) or [],
        "migre_le": date.today().isoformat(),
        "ancien_dossier": ancien,
    }


def est_v2(dossier: dict) -> bool:
    return isinstance(dossier, dict) and lire(dossier, "version") == VERSION
