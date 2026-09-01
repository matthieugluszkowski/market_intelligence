"""Collecteur Zonebourse : consensus des analystes et notations (lot L10).

Ce que ce collecteur apporte, et ce qu il ne remplace pas
---------------------------------------------------------
Le consensus est **l avis des autres**, pas un fait sur l entreprise. Il a sa
place sur la fiche pour une raison precise : quand la regression sort un titre a
-2,4 sigma et que vingt-trois analystes le disent a l achat avec un objectif a
+50 %, on sait au moins que la decote n est pas un secret. Et quand le consensus
dit l inverse du modele, c est la que la fiche devient interessante.

Il n entre donc dans **aucun calcul** : ni le z-score, ni le score de qualite, ni
la solidite concurrentielle ne le regardent. Un consensus est une opinion
agregee, revisee apres coup, et structurellement optimiste - l integrer a un
score reviendrait a acheter ce que tout le monde recommande deja.

L URL ne se devine pas
-----------------------
Zonebourse adresse ses fiches par un identifiant interne
(« ESSILORLUXOTTICA-4641 ») et refuse tout slug approchant. Il n existe pas
d acces par ISIN. L URL est donc **enregistree par titre** dans
`external_sources` - collee une fois depuis le navigateur, gardee ensuite.
Deviner serait pire que demander : un mauvais identifiant ne rend pas une
erreur, il rend la fiche d une autre societe.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from .extraction import bloc, cle, devise, entier, nombre, sans_balises
from .web import fetch

logger = logging.getLogger(__name__)

SOURCE = "zonebourse"
COPYRIGHT = ("Copyright Zonebourse (Surperformance SAS) - cotations Factset, "
             "Morningstar et S&P Capital IQ")

# Les deux onglets d une fiche Zonebourse ou vivent les encarts qu on lit.
ONGLET_CONSENSUS = "consensus/"
ONGLET_NOTATIONS = "notations/"

# Recommandation moyenne, telle que la source l ecrit. Conservee **verbatim**
# dans la collecte ; cet ordre ne sert qu a placer le curseur d une barre quand
# la jauge de la page n a pas pu etre lue.
RECOMMANDATIONS = ("VENDRE", "ALLEGER", "CONSERVER", "ACCUMULER", "ACHETER")

_LIBELLES_CONSENSUS = {
    "recommandation moyenne": "recommandation",
    "nombre d analystes": "nombre_d_analystes",
    "dernier cours de cloture": "cours_de_cloture",
    "objectif de cours moyen": "objectif_moyen",
    "ecart objectif moyen": "ecart_moyen_pct",
    "objectif de cours haut": "objectif_haut",
    "ecart objectif haut": "ecart_haut_pct",
    "objectif de cours bas": "objectif_bas",
    "ecart objectif bas": "ecart_bas_pct",
}

_ENTIERS = {"nombre_d_analystes"}
_MONTANTS = {"cours_de_cloture", "objectif_moyen", "objectif_haut", "objectif_bas"}
_POURCENTAGES = {"ecart_moyen_pct", "ecart_haut_pct", "ecart_bas_pct"}

_DEBUT_LIGNE = re.compile(r'<div class="grid[^"]*"')
_GAUCHE = re.compile(r'(?s)<div class="c">(.*?)</div>')
_DROITE = re.compile(r'(?s)<div class="c-auto[^"]*">(.*)')


@dataclass
class Collecte:
    """Le resultat d une collecte : ce qui a ete lu, et ce qui a manque."""

    consensus: dict | None = None
    notations: dict | None = None
    erreurs: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.consensus or self.notations)


def normalise_url(url: str) -> str:
    """Ramene n importe quelle URL de fiche Zonebourse a sa racine.

    L utilisateur colle l adresse de l onglet ou il se trouve - graphiques,
    societe, actualites. On garde `/cours/action/NOM-ID/` et on ajoute l onglet
    voulu ensuite.
    """
    propre = (url or "").strip().split("?")[0].split("#")[0]
    trouve = re.match(r"(https?://[^/]*zonebourse\.com/cours/[a-z-]+/[^/]+/)", propre)
    return trouve.group(1) if trouve else propre


def url_onglet(url_fiche: str, onglet: str) -> str:
    racine = normalise_url(url_fiche)
    if not racine.endswith("/"):
        racine += "/"
    return racine + onglet


def collecte(url_fiche: str, *, delai_sec: float = 1.0) -> Collecte:
    """Les deux onglets, en deux requetes. Un onglet manquant n annule pas l autre."""
    resultat = Collecte()

    page = fetch(url_onglet(url_fiche, ONGLET_CONSENSUS), delai_sec=delai_sec)
    if page.ok:
        resultat.consensus = parse_consensus(page.html, page.url)
        if resultat.consensus is None:
            resultat.erreurs.append(
                "consensus : encart introuvable sur la page. Soit le titre n est "
                "suivi par aucun analyste, soit la structure de la page a change.")
    else:
        resultat.erreurs.append(f"consensus : {page.error}")

    page = fetch(url_onglet(url_fiche, ONGLET_NOTATIONS), delai_sec=delai_sec)
    if page.ok:
        resultat.notations = parse_notations(page.html, page.url)
        if resultat.notations is None:
            resultat.erreurs.append("notations : encart introuvable sur la page.")
    else:
        resultat.erreurs.append(f"notations : {page.error}")

    return resultat


# --------------------------------------------------------------------------- #
# Consensus
# --------------------------------------------------------------------------- #
def parse_consensus(page: str, url: str = "") -> dict | None:
    """L encart « Consensus des Analystes » : recommandation, effectif, objectifs.

    La jauge porte la note dans son attribut `title` (« Note: 8.4 / 10 ») : c est
    elle, et non le libelle, qui permet de dessiner une barre. Un libelle seul
    ne dit pas si « ACHETER » tient a un cheveu de « CONSERVER ».
    """
    encart = bloc(page, 'id="consensus-analysts"', 'id="consensus-detail"')
    if not encart:
        return None

    valeurs: dict = {}
    for libelle, brut in lignes_libelle_valeur(encart):
        nom = _LIBELLES_CONSENSUS.get(cle(libelle))
        if nom is None:
            continue
        if nom in _ENTIERS:
            valeurs[nom] = entier(brut)
        elif nom in _MONTANTS:
            valeurs[nom] = nombre(brut)
            if valeurs.get("devise") is None:
                valeurs["devise"] = devise(brut)
        elif nom in _POURCENTAGES:
            valeurs[nom] = nombre(brut)
        else:
            valeurs[nom] = brut.strip().upper() or None

    if not valeurs.get("recommandation") and not valeurs.get("nombre_d_analystes"):
        return None

    note, note_max = _note_de_la_jauge(encart)
    return {
        "source": SOURCE,
        "url": url,
        "copyright": COPYRIGHT,
        "recommandation": valeurs.get("recommandation"),
        "note": note,
        "note_max": note_max,
        # La barre de l ecran se lit en pourcentage ; la note publiee reste a
        # cote, parce que c est elle qui fait foi.
        "note_pct": _en_pourcentage(note, note_max, valeurs.get("recommandation")),
        "nombre_d_analystes": valeurs.get("nombre_d_analystes"),
        "devise": valeurs.get("devise"),
        "cours_de_cloture": valeurs.get("cours_de_cloture"),
        "objectif_moyen": valeurs.get("objectif_moyen"),
        "objectif_haut": valeurs.get("objectif_haut"),
        "objectif_bas": valeurs.get("objectif_bas"),
        "ecart_moyen_pct": valeurs.get("ecart_moyen_pct"),
        "ecart_haut_pct": valeurs.get("ecart_haut_pct"),
        "ecart_bas_pct": valeurs.get("ecart_bas_pct"),
    }


def _en_pourcentage(note: float | None, note_max: float | None,
                    recommandation: str | None) -> float | None:
    """Position du curseur sur la barre « vendre -> acheter », en pourcentage.

    Depuis la note publiee quand elle a pu etre lue. Sinon depuis le libelle -
    et c est alors un **repere grossier** : « ACHETER » est un intervalle, pas
    un point. L ecran affiche le libelle et l effectif a cote pour cette raison.
    """
    if note is not None and note_max:
        return round(100.0 * note / note_max, 1)
    if recommandation and recommandation.upper() in RECOMMANDATIONS:
        rang = RECOMMANDATIONS.index(recommandation.upper())
        return round(100.0 * (rang + 0.5) / len(RECOMMANDATIONS), 1)
    return None


def _note_de_la_jauge(encart: str) -> tuple:
    trouve = re.search(
        r'consensus-gauge"[^>]*title="[^"]*?([\d.,]+)\s*/\s*([\d.,]+)"', encart)
    if not trouve:
        return None, None
    return nombre(trouve.group(1)), nombre(trouve.group(2))


def lignes_libelle_valeur(encart: str) -> list:
    """Les lignes « libelle / valeur » d un encart Zonebourse.

    Elles sont toutes construites pareil : un conteneur `grid`, un `div.c` a
    gauche, un `div.c-auto` a droite. On decoupe sur le conteneur plutot que de
    faire correspondre les deux d un coup - une expression qui traverse deux
    lignes finit toujours par apparier la gauche de l une avec la droite de la
    suivante.
    """
    lignes = []
    for morceau in _DEBUT_LIGNE.split(encart)[1:]:
        gauche = _GAUCHE.search(morceau)
        droite = _DROITE.search(morceau)
        if gauche and droite:
            lignes.append((sans_balises(gauche.group(1)),
                           sans_balises(droite.group(1))))
    return lignes


# --------------------------------------------------------------------------- #
# Notations
# --------------------------------------------------------------------------- #
def parse_notations(page: str, url: str = "") -> dict | None:
    """Les notations Surperformance, et le constat en une phrase qui va avec.

    Les notes sont des **rangs**, pas des mesures : « 24 % » veut dire que le
    titre est mieux note que 24 % de son univers de comparaison sur ce critere.
    L ecran l ecrit, parce qu une note de 24 % lue comme une probabilite ou une
    performance ne veut rien dire.
    """
    encart = (bloc(page, 'id="surperf-ratings"', 'id="rating-fondamentaux"')
              or bloc(page, 'id="ratings"', 'id="chart_'))
    constats = _constats(page)
    notes = _notes(encart) if encart else []
    if not notes and not constats["constat"]:
        return None
    resultat = {"source": SOURCE, "url": url, "copyright": COPYRIGHT, "notes": notes}
    resultat.update(constats)
    return resultat


def _notes(encart: str) -> list:
    notes = []
    for morceau in _DEBUT_LIGNE.split(encart)[1:]:
        gauche = _GAUCHE.search(morceau)
        if not gauche:
            continue
        libelle = sans_balises(gauche.group(1))
        if not libelle:
            continue
        # La note est dans l attribut `title` de l etoile ; le rang ESG, lui,
        # est une lettre (« AA ») et n a pas de pourcentage.
        pourcent = re.search(r'class="star[^"]*"', morceau)
        valeur = re.search(r'title="(\d+)%"', morceau)
        lettre = re.search(r'esg-rank[^>]*>\s*([A-Z]{1,3})\s*<', morceau)
        if valeur is not None and pourcent is not None:
            notes.append({"libelle": libelle, "note_pct": float(valeur.group(1)),
                          "mention": None})
        elif lettre is not None:
            notes.append({"libelle": libelle, "note_pct": None,
                          "mention": lettre.group(1)})
    return notes


def _constats(page: str) -> dict:
    """Le premier encart de « Forces et Faiblesses » : la phrase de synthese,
    puis les deux listes."""
    vide = {"constat": None, "constats": [], "points_forts": [], "points_faibles": []}
    encart = bloc(page, 'id="sw-card"', 'id="rating-')
    if not encart:
        return vide

    listes = re.findall(r"(?s)<ul[^>]*>(.*?)</ul>", encart)
    puces = [[sans_balises(item)
              for item in re.findall(r"(?s)<li[^>]*>(.*?)</li>", liste)]
             for liste in listes]
    if not puces:
        return vide

    titres = [cle(t) for t in re.findall(r'(?s)txt-bold[^>]*>(.*?)</div>', encart)]
    forts, faibles = [], []
    for titre, liste in zip(titres, puces[1:]):
        if titre.startswith("points forts"):
            forts = liste
        elif titre.startswith("points faibles"):
            faibles = liste

    return {"constat": puces[0][0] if puces[0] else None, "constats": puces[0],
            "points_forts": forts, "points_faibles": faibles}
