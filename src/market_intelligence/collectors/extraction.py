"""Outils d extraction de texte depuis du HTML, sans dependance supplementaire.

Pourquoi pas un vrai parseur ? Parce qu on ne lit ici que **quelques encarts
identifies par leur `id`**, dans des pages de 300 ko dont 90 % sont du menu. Un
arbre DOM complet ne rendrait pas la lecture plus sure : ce qui casse, quand une
source change, c est le nom de la classe ou la structure de l encart - et un
selecteur CSS y serait aussi fragile qu une expression reguliere.

La regle qui compte est ailleurs : **une extraction qui ne trouve pas rend
`None`, jamais une valeur inventee**. Un encart absent doit se voir a l ecran
comme absent, pas se confondre avec un zero.
"""

from __future__ import annotations

import html as _html
import re
import unicodedata

_BALISE = re.compile(r"(?s)<[^>]+>")
_ESPACES = re.compile(r"\s+")
_INVISIBLES = re.compile(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>")

# Balises **dans** le fil du texte : les effacer sans rien mettre a la place.
# Les remplacer par une espace, comme les balises de bloc, produit « d'
# EssilorLuxottica . » des que la source met un mot en gras au milieu d une
# phrase - ce qui est le cas de chaque depeche.
_EN_LIGNE = re.compile(r"(?is)</?(b|strong|i|em|u|span|a|sup|sub|small|mark)\b[^>]*>")


def sans_balises(fragment: str) -> str:
    """Le texte visible d un fragment HTML, espaces normalises."""
    if not fragment:
        return ""
    fragment = _INVISIBLES.sub(" ", fragment)
    fragment = _EN_LIGNE.sub("", fragment)
    texte = _html.unescape(_BALISE.sub(" ", fragment))
    # L espace insecable est un espace : « EssilorLuxottica&nbsp;: ... » doit se
    # comparer et se couper comme la meme chaine avec une espace ordinaire.
    return _ESPACES.sub(" ", texte.replace("\xa0", " ")).strip()


def bloc(page: str, marqueur: str, fin: str | None = None,
         taille_max: int = 40_000) -> str:
    """Le fragment qui commence a `marqueur` et s arrete a `fin`.

    Decoupage volontairement grossier : on ne cherche pas la balise fermante
    correspondante, on prend jusqu au repere suivant. C est suffisant pour lire
    un encart et ca ne se casse pas sur un `<div>` non ferme.
    """
    debut = page.find(marqueur)
    if debut < 0:
        return ""
    reste = page[debut:debut + taille_max]
    if fin:
        arret = reste.find(fin, len(marqueur))
        if arret > 0:
            return reste[:arret]
    return reste


def cle(libelle: str) -> str:
    """Cle de comparaison d un libelle : sans accent, sans ponctuation, en bas
    de casse. « Nombre d'Analystes » et « nombre d analystes » sont le meme."""
    plat = unicodedata.normalize("NFKD", libelle or "")
    plat = "".join(c for c in plat if not unicodedata.combining(c))
    return " ".join(re.split(r"[^a-z0-9]+", plat.lower())).strip()


def nombre(texte: str | None) -> float | None:
    """Un nombre ecrit a la francaise : « 243,30 », « 1 234,5 », « +50,47 % ».

    Rend `None` sur l absence de chiffre - y compris sur les tirets cadratins
    dont ces pages se servent pour dire « non publie ».
    """
    if not texte:
        return None
    propre = (texte.replace("\xa0", "").replace("\u202f", "")
              .replace(" ", "").replace("%", ""))
    trouve = re.search(r"[-+]?\d+(?:[.,]\d+)?", propre.replace(",", "."))
    if not trouve:
        return None
    try:
        return float(trouve.group(0))
    except ValueError:
        return None


def entier(texte: str | None) -> int | None:
    valeur = nombre(texte)
    return None if valeur is None else int(round(valeur))


def devise(texte: str | None) -> str | None:
    """Le code devise colle au nombre : « 243,30 EUR » ou « 243,30EUR ».

    Sans espace le plus souvent : la source ferme sa balise entre le montant et
    la devise, et les balises en ligne sont retirees sans rien mettre a la
    place. D ou le chiffre accepte comme separateur - et le refus de reconnaitre
    trois majuscules au milieu d un mot, sans quoi « ACHETER » rendrait « ACH ».
    """
    if not texte:
        return None
    trouve = re.search(r"(?:^|[\s\d])([A-Z]{3})(?![A-Za-z])", texte)
    return trouve.group(1) if trouve else None
