"""Watchlist (doc 10).

Le screener rend 57 lignes ; cet écran dit lesquelles on suit. La différence
n'est pas cosmétique : le screener est une requête, la watchlist est une
**décision**. Elle survit au fait qu'un titre sorte des critères du jour, et
c'est tout son intérêt — un titre suivi depuis huit mois qui repasse sous −2σ
ne se découvre pas, il se retrouve.

La colonne qu'on vient regarder est `dérive` : de combien le z-score a bougé
depuis l'ajout. Sans elle, on ne sait plus si le titre a baissé depuis qu'on le
suit ou s'il était déjà bas — et c'est exactement la question qu'on se pose en
rouvrant sa liste.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# Rechargement des modules du projet si leurs sources ont change. **Doit rester
# avant les imports qui suivent.**
from dashboard.rechargement import recharge_si_modifie  # noqa: E402

recharge_si_modifie()

from dashboard import data, navigation  # noqa: E402
from dashboard.theme import css, palette, statut  # noqa: E402
from market_intelligence import watchlist as W  # noqa: E402
from market_intelligence.db import connect_direct  # noqa: E402

st.set_page_config(page_title="Watchlist", page_icon="★", layout="wide")

sombre = st.sidebar.toggle("Mode sombre", value=False)
p = palette(sombre)
st.markdown(css(p), unsafe_allow_html=True)

st.title("Watchlist")
st.caption("Une sélection humaine, pas un filtre calculé. Le screener est une "
           "requête ; ceci est une décision.")

suivis = data.watchlist()

if suivis.empty:
    st.info(
        "Aucun titre suivi. Depuis une fiche instrument, le bouton **★ Suivre ce "
        "titre** l'ajoute ici avec le z-score du jour et la note du moment."
    )
else:
    haut = st.columns(4)
    haut[0].metric("Titres suivis", len(suivis))
    sous_seuil = int((suivis["z_actuel"] <= -1.5).sum())
    haut[1].metric("Sous −1,5σ", sous_seuil)
    baisse = suivis[suivis["derive"] < 0]
    haut[2].metric("En baisse depuis l'ajout", len(baisse))
    haut[3].metric("Suivi médian",
                   f"{int(suivis['jours_de_suivi'].median())} j")

    table = pd.DataFrame({
        "Nom": suivis["name"],
        "Code": suivis["internal_code"],
        "Depuis": suivis["added_at"],
        "Jours": suivis["jours_de_suivi"],
        "z à l'ajout": suivis["z_at_add"].round(2),
        "z actuel": suivis["z_actuel"].round(2),
        "Dérive": suivis["derive"].round(2),
        "Fit": suivis["fit_quality"].map(
            lambda q: f"{statut(q)[1]} {q}" if pd.notna(q) else "—"),
        "Qualité": suivis["quality_tier"],
        "Régime": suivis["regime"],
        "Demi-vie (j)": suivis["half_life_days"].round(0),
        "Secteur": suivis["secteur"],
    })

    st.caption("**Sélectionner une ligne ouvre la fiche instrument.**")
    navigation.tableau_vers_fiche(
        table, list(suivis["internal_code"]), cle="watchlist_table",
        use_container_width=True, hide_index=True,
        column_config={
            "z à l'ajout": st.column_config.NumberColumn(format="%+.2f"),
            "z actuel": st.column_config.NumberColumn(format="%+.2f"),
            "Dérive": st.column_config.NumberColumn(
                format="%+.2f",
                help="Variation du z-score depuis l'ajout. Négatif = le titre a "
                     "baissé depuis qu'on le suit."),
        },
    )

    st.markdown(
        "<div class='avertissement'>La <b>dérive</b> est la colonne qu'on vient "
        "regarder. Une dérive négative ne dit pas qu'il faut acheter : elle dit "
        "que le régime de décote se prolonge, ce qui est une information "
        "différente — et les statistiques de régime de la fiche disent combien de "
        "temps ces épisodes durent habituellement sur ce titre.</div>",
        unsafe_allow_html=True,
    )

    with st.expander("Notes de suivi — pourquoi ces titres"):
        notes = suivis[["name", "added_at", "note"]].copy()
        notes["note"] = notes["note"].fillna("—")
        st.dataframe(notes.rename(columns={
            "name": "Nom", "added_at": "Depuis", "note": "Note"}),
            use_container_width=True, hide_index=True)
        st.caption(
            "Écrites au moment de l'ajout. Les relire dans un an est le seul "
            "antidote fiable au biais rétrospectif : on reconstruit spontanément "
            "une justification de ce qu'on a fait."
        )

    st.subheader("Retirer un titre")
    gauche, milieu, droite = st.columns([2, 2, 1])
    with gauche:
        a_retirer = st.selectbox(
            "Titre", suivis["internal_code"],
            format_func=lambda c: suivis.set_index("internal_code").loc[c, "name"],
        )
    with milieu:
        raison = st.text_input("Raison du retrait",
                               placeholder="thèse invalidée, position prise…")
    with droite:
        st.write("")
        if st.button("Retirer", use_container_width=True):
            with connect_direct() as conn, conn.cursor() as cur:
                cur.execute("select id from instruments where internal_code = %s",
                            (a_retirer,))
                W.retire(cur, cur.fetchone()[0], raison)
                conn.commit()
            data.watchlist.clear()
            st.rerun()

# --------------------------------------------------------------------------- #
# Historique : ce qu'on a suivi puis retiré
# --------------------------------------------------------------------------- #
historique = data.watchlist_historique()
if not historique.empty:
    with st.expander(f"Titres retirés ({len(historique)})"):
        st.dataframe(
            historique.rename(columns={
                "internal_code": "Code", "name": "Nom", "added_at": "Suivi depuis",
                "removed_at": "Retiré le", "removal_reason": "Raison",
                "note": "Note d'origine", "z_at_add": "z à l'ajout",
                "jours_suivis": "Jours suivis"}),
            use_container_width=True, hide_index=True,
        )
        st.caption(
            "Rien n'est effacé, seulement horodaté. Savoir qu'on a suivi un titre "
            "pendant huit mois puis qu'on l'a retiré est une information ; "
            "l'effacer laisserait croire qu'on ne l'a jamais regardé."
        )
