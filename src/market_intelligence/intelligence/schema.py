"""Aides partagees du dossier concurrentiel.

Ce module portait le dispositif a cinq prompts : detection de fragment, fusion
additive, controle qualite, acquittement nominatif, avancement, resume. Ce
dispositif a ete remplace le 2026-08-21 par `intelligence.position` - quatre
questions, un prompt, un score calcule - apres avoir rendu **30/100 de confiance
et un refus de conclure** sur EssilorLuxottica, dont le resume disait pourtant
« leader incontesté ».

Il ne reste ici que ce qui sert encore, et qui n'appartient a aucun format en
particulier : l'appariement de noms de societes, la peremption des evaluations,
la liste des statuts epistemiques, et la geographie du groupe de pairs.
"""

from __future__ import annotations

import re
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


def json_copie(valeur):
    import json as _json
    return _json.loads(_json.dumps(valeur, ensure_ascii=False, default=str))


def peremption(reference_date: date) -> date:
    """Une evaluation de 2026 inspire la meme confiance qu'une de 2029, et c'est
    le probleme. La peremption force la revue."""
    return reference_date + timedelta(days=int(PEREMPTION_MOIS * 30.44))
