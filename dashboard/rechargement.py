"""Rechargement des modules du projet quand leurs sources changent.

Le probleme, constate deux fois
--------------------------------
Streamlit relance le script a chaque interaction mais **garde les modules
importes en cache**. Une fonction ajoutee a `dashboard/data.py` ou une constante
ajoutee a `intelligence/schema.py` reste donc invisible, et la page tombe en
`AttributeError` sur un attribut pourtant present dans le fichier. Le message
d'erreur designe le fichier, ce qui oriente le diagnostic vers le code alors que
le code est correct.

Constate sur `data.qualite`, puis sur `schema.FRAGMENTS`.

Pourquoi `runOnSave` ne suffit pas
-----------------------------------
Le surveillant de Streamlit ne couvre pas de facon fiable les modules dont le
chemin est ajoute a `sys.path` a l'execution - c'est le cas de `src/` ici - et le
dossier du projet est synchronise par OneDrive, dont la virtualisation rend les
evenements de systeme de fichiers irreguliers. Verifie : avec `runOnSave = true`,
une constante modifiee restait invisible.

La solution retenue
--------------------
On calcule l'empreinte des sources du projet - le plus recent horodatage de
modification - et on **purge `sys.modules`** quand elle change. Le module est
alors reimporte a l'instruction `import` suivante.

Deux precautions :

- **Rien n'est purge quand rien n'a change.** C'est ce qui rend le mecanisme
  gratuit : les caches `st.cache_data` survivent au cas courant, et une purge
  systematique ferait retourner en base a chaque clic.
- La purge est faite **avant** les imports de la page, jamais apres : purger un
  module deja importe dans le meme run laisserait coexister deux versions d'une
  meme classe, et un `isinstance` echouerait sans raison visible.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

RACINE = Path(__file__).resolve().parents[1]

# Ce qui est surveille : le code du projet, et rien d'autre. Surveiller les
# dependances couterait cher pour un benefice nul.
SOURCES = (RACINE / "src" / "market_intelligence", RACINE / "dashboard")

# Prefixes purges quand une source change. `dashboard.rechargement` s'exclut
# lui-meme : se purger en cours d'execution n'aurait pas de sens.
PREFIXES = ("market_intelligence", "dashboard")
JAMAIS_PURGE = ("dashboard.rechargement",)

# L'empreinte est portee par le **processus**, pas par la session Streamlit.
# Avec `st.session_state`, un onglet fraichement ouvert la trouvait a None et ne
# purgeait rien : les modules du serveur, importes avant la modification,
# restaient servis tels quels, et la page tombait en AttributeError sur une
# fonction pourtant presente dans le fichier - le symptome meme que ce module
# existe pour supprimer. Constate sur `data.fraicheur` le 2026-08-21.
_empreinte_connue: float | None = None


def _empreinte() -> float:
    """Horodatage de modification le plus recent parmi les sources du projet."""
    recent = 0.0
    for racine in SOURCES:
        if not racine.exists():
            continue
        for fichier in racine.rglob("*.py"):
            if "__pycache__" in fichier.parts:
                continue
            try:
                recent = max(recent, fichier.stat().st_mtime)
            except OSError:
                continue
    return recent


def recharge_si_modifie() -> bool:
    """Purge les modules du projet si une source a change. Rend True si purge.

    A appeler **en tete de page, avant les imports du projet**.
    """
    global _empreinte_connue

    courante = _empreinte()
    precedente = _empreinte_connue
    _empreinte_connue = courante

    # Premier passage du processus : les modules viennent d'etre importes, ils
    # sont donc a jour par construction. Rien a purger.
    if precedente is None or courante <= precedente:
        return False

    for nom in [n for n in list(sys.modules)
                if n.startswith(PREFIXES) and n not in JAMAIS_PURGE]:
        sys.modules.pop(nom, None)

    # Les caches de donnees portent sur des fonctions qui viennent d'etre
    # remplacees : les vider evite de servir un resultat calcule par l'ancienne.
    try:
        st.cache_data.clear()
    except Exception:  # noqa: BLE001 - hors runtime Streamlit, sans objet
        pass
    return True
