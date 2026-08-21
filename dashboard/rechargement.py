"""Rechargement des modules du projet quand leurs sources changent.

Le probleme, constate trois fois
---------------------------------
Streamlit relance le script a chaque interaction mais **garde les modules
importes en cache**. Une fonction ajoutee a `dashboard/data.py` ou une constante
ajoutee a `intelligence/schema.py` reste donc invisible, et la page tombe en
`AttributeError` - ou en `ImportError` sur un `from ... import` - pour un nom
pourtant present dans le fichier. Le message designe le fichier, ce qui oriente
le diagnostic vers le code alors que le code est correct.

Constate sur `data.qualite`, puis sur `schema.FRAGMENTS`, puis sur
`quality.groupe_comparable`.

Pourquoi `runOnSave` ne suffit pas
-----------------------------------
Le surveillant de Streamlit ne couvre pas de facon fiable les modules dont le
chemin est ajoute a `sys.path` a l'execution - c'est le cas de `src/` ici - et le
dossier du projet est synchronise par OneDrive, dont la virtualisation rend les
evenements de systeme de fichiers irreguliers.

Pourquoi l'empreinte globale ne suffisait pas non plus
-------------------------------------------------------
La version precedente comparait **un seul nombre** : l'horodatage de
modification le plus recent de tout le projet. Deux failles, la seconde
constatee en production le 2026-08-21 :

1. *« Premier passage du processus : les modules viennent d'etre importes, ils
   sont donc a jour par construction. »* C'est faux des qu'un module a ete
   importe avant le premier appel.
2. **Un seul nombre ne dit rien d'un module en particulier.** Le maximum
   progresse des qu'un fichier - n'importe lequel - est touche. Un run qui
   observe cette progression met l'empreinte a jour **meme s'il ne reimporte pas
   le module concerne** : le compteur est consomme par une page, la peremption
   est portee par une autre. `analytics/quality.py` est reste charge sans
   `groupe_comparable` pendant que l'empreinte, elle, etait a jour - purge
   jamais declenchee, page morte jusqu'au redemarrage du serveur.

Ce que fait cette version
--------------------------
Elle ne compare plus un compteur global mais **chaque module a sa propre
source**. Un module est perime si l'horodatage de son fichier ne correspond plus
a celui note quand on l'a vu frais. La comparaison est une **inegalite**, pas un
« plus recent que » : OneDrive peut ramener un horodatage en arriere, et un
fichier revenu en arriere est aussi un fichier different.

Deux precautions conservees :

- **Rien n'est purge quand rien n'a bouge.** C'est ce qui rend le mecanisme
  gratuit : les caches `st.cache_data` survivent au cas courant.
- La purge est faite **avant** les imports de la page, jamais apres : purger un
  module deja importe dans le meme run laisserait coexister deux versions d'une
  meme classe, et un `isinstance` echouerait sans raison visible.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import streamlit as st

RACINE = Path(__file__).resolve().parents[1]

# Prefixes surveilles et purges. `dashboard.rechargement` s'exclut lui-meme : se
# purger en cours d'execution n'aurait pas de sens - et c'est pour cela qu'une
# modification de CE fichier n'est prise en compte qu'au redemarrage du serveur.
PREFIXES = ("market_intelligence", "dashboard")
JAMAIS_PURGE = ("dashboard.rechargement",)

# Horodatage de source note pour chaque module au moment ou on l'a vu frais.
_horodatages: dict[str, float] = {}

# Debut du processus. Un module vu pour la premiere fois dont la source n'a pas
# bouge depuis ce moment a forcement ete importe dans son etat actuel : inutile
# de purger. Si elle a bouge depuis, on ne peut rien affirmer - on purge.
_DEBUT = time.time()


def _source(module) -> Path | None:
    fichier = getattr(module, "__file__", None)
    if not fichier:
        return None
    chemin = Path(fichier)
    try:
        # Un module hors du projet porterait un prefixe homonyme : on ne le
        # purge pas sur la foi de son nom.
        chemin.relative_to(RACINE)
    except ValueError:
        return None
    return chemin


def _modules_du_projet() -> dict:
    return {nom: module for nom, module in list(sys.modules.items())
            if nom.startswith(PREFIXES) and nom not in JAMAIS_PURGE
            and module is not None}


def recharge_si_modifie() -> bool:
    """Purge les modules du projet dont la source a change. Rend True si purge.

    A appeler **en tete de page, avant les imports du projet**.
    """
    charges = _modules_du_projet()

    mesures: dict[str, float] = {}
    perimes: list[str] = []
    for nom, module in charges.items():
        source = _source(module)
        if source is None:
            continue
        try:
            mtime = source.stat().st_mtime
        except OSError:
            continue
        mesures[nom] = mtime
        reference = _horodatages.get(nom)
        if reference is None:
            # Jamais observe. Sa source n'a pas bouge depuis le demarrage du
            # processus -> ce qui est charge est forcement a jour.
            if mtime > _DEBUT:
                perimes.append(nom)
        elif mtime != reference:
            perimes.append(nom)

    if not perimes:
        # On enregistre ce qu'on vient de constater frais : sans cela, un module
        # jamais observe le resterait et serait reteste a chaque run.
        _horodatages.update(mesures)
        return False

    for nom in charges:
        sys.modules.pop(nom, None)

    # Les modules purges seront reimportes plus bas dans CE run, depuis les
    # sources telles qu'elles sont maintenant : leur horodatage de reference est
    # donc celui qu'on vient de mesurer.
    _horodatages.clear()
    _horodatages.update(mesures)

    # Les caches de donnees portent sur des fonctions qui viennent d'etre
    # remplacees : les vider evite de servir un resultat calcule par l'ancienne.
    try:
        st.cache_data.clear()
    except Exception:  # noqa: BLE001 - hors runtime Streamlit, sans objet
        pass
    return True
