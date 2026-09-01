"""Collecteur Boursier.com : les depeches d un titre (lot L10).

Pourquoi des depeches sur une fiche d analyse de long terme
------------------------------------------------------------
Le modele lit vingt ans de cours et n a aucune idee de ce qui s est passe la
semaine derniere. Quand un titre tombe a -2 sigma, la premiere question est
toujours la meme : **qu est-ce qui vient d arriver ?** Une demission, un
avertissement sur resultats, une degradation d analyste - c est ce qui separe
une decote d un effondrement justifie, et aucun test statistique ne le dira.

Les depeches sont donc affichees **a cote** du signal, jamais melangees a lui.
Elles n entrent dans aucun calcul : une actualite est un fait daté, pas une
variable.

L URL se deduit de l ISIN
-------------------------
Contrairement a Zonebourse, Boursier.com resout ses fiches par ISIN et corrige
lui-meme le slug : `.../news/x-FR0000121667,FR.html` redirige vers l adresse
canonique du titre. Aucune table de correspondance a tenir - l ISIN de la base
suffit, et l URL finale revient dans la reponse.

Droits
-------
Le texte des depeches appartient a Boursier.com. Il est conserve pour une
lecture personnelle et **toujours affiche avec son titre, sa date, sa source et
son lien** : la fiche renvoie a l article, elle ne le republie pas.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime

from .extraction import sans_balises
from .web import fetch

logger = logging.getLogger(__name__)

SOURCE = "boursier"
DOMAINE = "https://www.boursier.com"
COPYRIGHT = "Copyright Boursier.com"

# Nombre de depeches dont on va chercher le texte complet. Le reste de la liste
# est conserve en titre + date + lien : une requete par article, et personne ne
# deroule quinze articles sur une fiche.
ARTICLES_COMPLETS = 6
DEPECHES_MAX = 15

_ITEM = re.compile(
    r'(?s)<div class="item">(.*?)</div>\s*</div>')
_DATE = re.compile(r'<time[^>]*datetime="([^"]+)"')
_LIEN = re.compile(r'(?s)<a href="([^"]+)"[^>]*>(.*?)</a>')


@dataclass
class Depeche:
    titre: str
    publie_le: str | None
    url: str
    texte: str = ""
    auteur: str | None = None

    def en_dict(self) -> dict:
        return {"titre": self.titre, "publie_le": self.publie_le, "url": self.url,
                "texte": self.texte, "auteur": self.auteur, "source": SOURCE}


@dataclass
class Collecte:
    depeches: list = field(default_factory=list)
    url: str = ""
    erreurs: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.depeches)


def url_actualites(isin: str, place: str = "FR") -> str:
    """L adresse de la liste d actualites d un titre, depuis son seul ISIN.

    Le slug est ignore par la source, qui redirige vers l adresse canonique -
    on en met donc un neutre plutot que de fabriquer un faux nom de societe.
    """
    return f"{DOMAINE}/actions/actualites/news/x-{isin.strip().upper()},{place}.html"


def collecte(isin: str, *, place: str = "FR", limite: int = DEPECHES_MAX,
             articles_complets: int = ARTICLES_COMPLETS,
             delai_sec: float = 1.0) -> Collecte:
    """La liste des depeches, et le texte des plus recentes."""
    resultat = Collecte()
    liste = fetch(url_actualites(isin, place), delai_sec=delai_sec)
    if not liste.ok:
        resultat.erreurs.append(f"depeches : {liste.error}")
        return resultat

    resultat.url = liste.url
    depeches = parse_depeches(liste.html)[:limite]
    if not depeches:
        resultat.erreurs.append(
            "depeches : aucune actualite sur la page. Titre sans couverture, ou "
            "structure de la page modifiee.")
        return resultat

    for depeche in depeches[:articles_complets]:
        article = fetch(depeche.url, delai_sec=delai_sec)
        if not article.ok:
            resultat.erreurs.append(f"article « {depeche.titre} » : {article.error}")
            continue
        detail = parse_article(article.html)
        depeche.texte = detail.get("texte", "")
        depeche.auteur = detail.get("auteur")
        # La date de l article est plus precise que celle de la liste, qui
        # n affiche que « 10h39 » pour la journee en cours.
        depeche.publie_le = detail.get("publie_le") or depeche.publie_le

    resultat.depeches = depeches
    return resultat


def parse_depeches(page: str) -> list:
    """Les entrees de la liste d actualites : titre, horodatage, lien."""
    debut = page.find('<div class="news-list"')
    if debut < 0:
        return []
    listing = page[debut:]

    depeches = []
    for morceau in _ITEM.findall(listing):
        lien = _LIEN.search(morceau)
        if not lien:
            continue
        titre = sans_balises(lien.group(2))
        # Le compteur de commentaires est colle au titre dans le meme lien.
        titre = re.sub(r"\s*\d+\s*$", "", titre).strip()
        if not titre:
            continue
        date = _DATE.search(morceau)
        depeches.append(Depeche(
            titre=titre,
            publie_le=_horodatage(date.group(1)) if date else None,
            url=_absolue(lien.group(1)),
        ))
    return depeches


def parse_article(page: str) -> dict:
    """Le corps d une depeche : titre, date, auteur, texte en paragraphes."""
    # `find` rend -1 quand le repere manque, et `page[-1:]` est le dernier
    # caractere de la page : sans ce test, une page sans article rend un
    # dictionnaire de champs vides au lieu de rien du tout.
    debut = page.find('id="article-content"')
    if debut < 0:
        return {}
    corps = page[debut:]
    corps = corps[:corps.find("</article>")] if "</article>" in corps else corps

    titre = sans_balises(_premier(r"(?s)<h1[^>]*>(.*?)</h1>", corps))
    publiee = _premier(r'itemprop="datePublished"[^>]*content="([^"]+)"', page) \
        or _premier(r'<time[^>]*datetime="([^"]+)"', corps)
    auteur = sans_balises(_premier(r'(?s)itemprop="author"[^>]*>(.*?)</span>', corps))

    # On retire d abord tout ce qui n est pas du texte d article : partage,
    # illustration, encadres. Sans ca, les paragraphes de la barre de partage
    # arrivent en tete de l article.
    texte = re.sub(r"(?is)<(script|style|figure|header|aside|form|table)[^>]*>.*?</\1>",
                   " ", corps)
    paragraphes = []
    for brut in re.findall(r"(?s)<p[^>]*>(.*?)</p>", texte):
        propre = sans_balises(brut)
        # Le premier paragraphe repete la signature et la date, deja lues.
        if not propre or propre.startswith("Par ") or propre.startswith("Publié le"):
            continue
        paragraphes.append(propre)

    return {
        "titre": titre or None,
        "publie_le": _horodatage(publiee) if publiee else None,
        "auteur": auteur or None,
        "paragraphes": paragraphes,
        "texte": "\n\n".join(paragraphes),
    }


def _premier(motif: str, texte: str) -> str:
    trouve = re.search(motif, texte)
    return trouve.group(1) if trouve else ""


def _absolue(href: str) -> str:
    return href if href.startswith("http") else DOMAINE + href


def _horodatage(brut: str) -> str | None:
    """Normalise en ISO. Un horodatage illisible vaut mieux absent qu invente."""
    try:
        return datetime.fromisoformat(brut.strip()).isoformat()
    except ValueError:
        logger.debug("horodatage illisible : %r", brut)
        return None
