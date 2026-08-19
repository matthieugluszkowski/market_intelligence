"""Ecran screener (doc 04 SS3, ecran 1).

    streamlit run dashboard/Screener.py

Trois principes portes par cet ecran :

- **I1, le silence est une fonctionnalite.** Aucune notification, aucun
  rafraichissement temps reel, aucun ticker clignotant. Le dashboard se
  consulte, il n'alerte pas. Thaler, Tversky, Kahneman et Schwartz (1997) ont
  montre que plus le feedback est frequent, plus la prise de risque diminue et
  plus le rendement accumule baisse : un outil qui augmente la frequence de
  consultation detruit ce qu'il pretend ameliorer.
- **I2, l'incertitude est affichee.** Un fit `weak` s'affiche `weak`, avec sa
  raison. Le cas majoritaire sera « on ne sait pas trancher », et l'interface
  doit rendre ca normal plutot que honteux.
- **I3, toute visualisation a un jumeau tabulaire.**
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Rechargement des modules du projet si leurs sources ont change. **Doit rester
# avant les imports qui suivent** : Streamlit garde les modules importes en cache
# et une purge posterieure laisserait coexister deux versions d une meme classe.
from dashboard.rechargement import recharge_si_modifie  # noqa: E402

recharge_si_modifie()

from dashboard import data  # noqa: E402
from dashboard.theme import css, motif_en_clair, palette, statut  # noqa: E402

st.set_page_config(page_title="Screener - market intelligence",
                   page_icon="◧", layout="wide")


def barre_laterale() -> bool:
    st.sidebar.title("market intelligence")
    sombre = st.sidebar.toggle("Mode sombre", value=False)
    st.sidebar.caption(
        "Le mode sombre est un jeu de valeurs choisi pour la surface sombre, "
        "pas une inversion du mode clair."
    )
    return sombre


sombre = barre_laterale()
p = palette(sombre)
st.markdown(css(p), unsafe_allow_html=True)

as_of = data.derniere_date_de_calcul()
if as_of is None:
    st.error("Aucune regression en base. Lancer `python scripts/compute_fits.py`.")
    st.stop()

frame = data.screener(as_of)

st.title("Screener")
st.caption(f"Calcul du {as_of}. Le dashboard sert a creuser un titre, "
           f"pas a surveiller : le canal principal est le rapport hebdomadaire.")

# --------------------------------------------------------------------------- #
# Une seule rangee de filtres, au-dessus de tout ce qu'ils cadrent.
# Jamais de filtre a l'interieur d'une carte de graphe.
# --------------------------------------------------------------------------- #
f1, f2, f3, f4, f5 = st.columns([1.1, 1.4, 1.3, 1.3, 1.1])

with f1:
    seuil_z = st.slider("Seuil de z-score", -4.0, 4.0, -1.5, 0.1,
                        help="Ne garder que les titres sous ce seuil.")
with f2:
    qualites = st.multiselect(
        "Qualite du fit", ["good", "weak", "rejected"], default=["good", "weak"],
        format_func=lambda q: f"{statut(q)[1]} {q}",
    )
with f3:
    secteurs = st.multiselect("Secteur", sorted(frame["secteur"].dropna().unique()))
with f4:
    pays = st.multiselect("Pays", sorted(frame["country_iso2"].dropna().unique()))
with f5:
    persistance = st.number_input("Sem. sous seuil ≥", min_value=0, value=0, step=1)

filtre = frame[frame["z_score"] <= seuil_z]
if qualites:
    filtre = filtre[filtre["fit_quality"].isin(qualites)]
if secteurs:
    filtre = filtre[filtre["secteur"].isin(secteurs)]
if pays:
    filtre = filtre[filtre["country_iso2"].isin(pays)]


def semaines_sous_seuil(stats) -> int:
    return int((stats or {}).get("semaines_consecutives_en_cours") or 0)


def n_episodes(stats) -> int:
    return int((stats or {}).get("n_episodes") or 0)


filtre = filtre.copy()
filtre["semaines"] = filtre["regime_stats"].map(semaines_sous_seuil)
filtre["episodes"] = filtre["regime_stats"].map(n_episodes)
if persistance:
    filtre = filtre[filtre["semaines"] >= persistance]

# --------------------------------------------------------------------------- #
# L'ecran matrice qualite x prix arrive avec L6b. En attendant, tous les titres
# sont `unqualified` - c'est leur statut reel et il doit se voir.
# --------------------------------------------------------------------------- #
if (frame["quality_tier"] == "unqualified").all():
    st.markdown(
        "<div class='avertissement'>"
        "<b>Tous les titres sont en statut <code>unqualified</code>.</b> "
        "La jambe qualite - position concurrentielle, rente, erosion - n'est pas "
        "encore calculee (lot L6b). Un signal de prix sans evaluation de la "
        "position concurrentielle est la moitie de la methode, et c'est la moitie "
        "qui produit les value traps. Ces resultats se lisent comme des candidats "
        "a verifier, pas comme des cibles."
        "</div>",
        unsafe_allow_html=True,
    )

if filtre.empty:
    st.info("Aucun titre ne passe ces filtres.")
    st.stop()

# --------------------------------------------------------------------------- #
# Tri par defaut : quadrant d'abord, puis z croissant. Trier par decote seule
# met en tete les pieges ; trier par qualite seule met en tete les titres chers.
# Tant que le quadrant est uniforme, le tri se reduit au z croissant.
# --------------------------------------------------------------------------- #
ordre_qualite = {"good": 0, "weak": 1, "rejected": 2}
filtre["_ordre"] = filtre["fit_quality"].map(ordre_qualite).fillna(3)
filtre = filtre.sort_values(["_ordre", "z_score"])

table = pd.DataFrame({
    "Nom": filtre["name"],
    "Code": filtre["internal_code"],
    "Quadrant": "unqualified",
    "z": filtre["z_score"].round(2),
    "Fit": filtre["fit_quality"].map(lambda q: f"{statut(q)[1]} {q}"),
    "Motif": filtre["quality_reasons"].map(
        lambda motifs: ", ".join(motif_en_clair(m) for m in (motifs or []))
    ),
    "Qualite": filtre["quality_tier"],
    "Erosion": filtre["erosion_flags"].map(lambda n: "-" if pd.isna(n) else f"{int(n)}/3"),
    "Pente an.": (filtre["slope_annual"] * 100).round(1),
    "Demi-vie (j)": filtre["half_life_days"].round(0),
    "Sem. sous seuil": filtre["semaines"],
    "Episodes": filtre["episodes"],
    "Secteur": filtre["secteur"],
    "Pays": filtre["country_iso2"],
})

st.caption(f"{len(table)} titre(s) sur {len(frame)}. "
           f"Tri : qualite du fit, puis z croissant.")

st.dataframe(
    table, use_container_width=True, hide_index=True,
    column_config={
        "z": st.column_config.NumberColumn(
            "z", format="%+.2f",
            help="Position en ecarts-types. Un titre qui passe sous -2σ tous les "
                 "trois ans n'envoie pas le meme signal qu'un titre qui le fait "
                 "pour la deuxieme fois en trente ans : voir la colonne Episodes.",
        ),
        "Pente an.": st.column_config.NumberColumn("Pente an.", format="%.1f%%"),
        "Episodes": st.column_config.NumberColumn(
            "Episodes", help="Nombre d'episodes sous -2σ sur l'historique."),
    },
)

st.markdown(
    "<div class='avertissement'>"
    "Aucune colonne de score composite sur 100 : un z-score et un verdict de "
    "qualite de donnee ne s'agregent pas en une note."
    "</div>",
    unsafe_allow_html=True,
)

with st.expander("Repartition des verdicts sur l'univers"):
    repartition = frame["fit_quality"].value_counts().rename_axis("Verdict")
    resume = pd.DataFrame({
        "Titres": repartition,
        "Libelle": [statut(q)[2] for q in repartition.index],
    })
    st.dataframe(resume, use_container_width=True)
    st.caption(
        "`weak` doit etre le cas majoritaire. Une repartition a 80% de `good` "
        "serait le signe d'un bug, pas d'un univers exceptionnel."
    )

st.page_link("pages/1_Fiche_instrument.py", label="Ouvrir une fiche instrument →")
