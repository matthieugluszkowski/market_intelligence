"""Navigation entre les écrans du dashboard.

Un tableau qui liste des instruments doit mener à leur fiche : chercher le titre
dans la liste déroulante de la fiche après l'avoir repéré au screener est une
rupture de geste — on l'a sous les yeux, on doit pouvoir y aller.

Le mécanisme : la sélection d'une ligne (`on_select`) déclenche
`st.switch_page` vers la fiche, en passant le code de l'instrument par
`st.session_state`. La fiche le consomme une seule fois (`pop`) : le choix
manuel dans sa liste déroulante reprend la main dès l'interaction suivante.
"""

from __future__ import annotations

import streamlit as st

FICHE = "pages/1_Fiche_instrument.py"

# Clé de transmission du titre à ouvrir. Consommée par la fiche via `pop` :
# une cible ne survit jamais à sa navigation.
CLE_CIBLE = "instrument_cible"


def ouvre_fiche(internal_code: str) -> None:
    st.session_state[CLE_CIBLE] = internal_code
    st.switch_page(FICHE)


def tableau_vers_fiche(table, codes: list, cle: str, **kwargs) -> None:
    """Affiche un tableau dont la sélection d'une ligne ouvre la fiche.

    `codes` est la liste des `internal_code` **dans l'ordre des lignes
    affichées** : la sélection est positionnelle, un tableau trié après coup
    enverrait vers le mauvais titre.
    """
    evenement = st.dataframe(
        table, key=cle, on_select="rerun", selection_mode="single-row",
        **kwargs,
    )
    lignes = evenement.selection.rows
    if lignes:
        ouvre_fiche(codes[lignes[0]])


def cible_demandee(codes: list) -> str | None:
    """Côté fiche : le titre demandé par une navigation, s'il y en a une.

    Deux canaux, dans cet ordre : la session (clic depuis un tableau), puis
    l'URL (`?instrument=EQ:DE:ADIDAS`, pour partager un lien direct). Le
    paramètre d'URL est retiré après lecture : sinon il réimposerait le même
    titre à chaque interaction, et la liste déroulante deviendrait inerte.
    """
    cible = st.session_state.pop(CLE_CIBLE, None)
    if cible is None:
        cible = st.query_params.get("instrument")
        if cible is not None:
            del st.query_params["instrument"]
    return cible if cible in set(codes) else None
