"""Matrice qualite x prix (doc 04 SS3 ecran 3, doc 08 SS6).

L'ecran de synthese du systeme. Quatre decisions d'encodage y sont portees, et
chacune corrige une erreur courante :

- **La forme du marqueur porte le regime, pas la couleur.** La couleur est deja
  prise par le z-score, et surtout un daltonien doit pouvoir distinguer un
  cyclique d'un titre en erosion. Le canal de forme est libre, on l'utilise.
- **Taille constante, pas de bulle par capitalisation.** Un nuage de bulles
  encode mal les magnitudes - l'oeil compare des surfaces - et la capitalisation
  n'entre pas dans la decision ici.
- **Les libelles de quadrant sont ecrits en toutes lettres dans les coins.** Un
  quadrant qui ne se comprend qu'en croisant deux axes mentalement ne se
  comprend pas.
- **Le quadrant value trap est affiche, pas masque.** C'est la liste des titres
  qui ont l'air d'opportunites et n'en sont pas. La voir chaque semaine vaut
  mieux que ne pas la voir : c'est la qu'on perd de l'argent, pas dans le
  quadrant « a eviter » qu'on n'achete jamais.
"""

from __future__ import annotations

import sys
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# Rechargement des modules du projet si leurs sources ont change. **Doit rester
# avant les imports qui suivent** : Streamlit garde les modules importes en cache
# et une purge posterieure laisserait coexister deux versions d une meme classe.
from dashboard.rechargement import recharge_si_modifie  # noqa: E402

recharge_si_modifie()

from dashboard import data, definitions, navigation  # noqa: E402
from dashboard.theme import css, palette  # noqa: E402
from market_intelligence.analytics.quality import quadrant  # noqa: E402

st.set_page_config(page_title="Matrice qualite x prix", page_icon="◧", layout="wide")

sombre = st.sidebar.toggle("Mode sombre", value=False)
p = palette(sombre)
st.markdown(css(p), unsafe_allow_html=True)

QUADRANTS = {
    "target": ("CIBLE", "Leader, rente persistante, aucune erosion, et decote."),
    "watchlist": ("WATCHLIST", "Qualite etablie mais prix non attractif, ou qualite a confirmer."),
    "value_trap": ("VALUE TRAP", "Decote ET position qui se degrade : le marche a probablement raison."),
    "avoid": ("A EVITER", "Cher ET position qui se degrade."),
    "unqualified": ("NON QUALIFIE", "Position concurrentielle jamais evaluee, ou fondamentaux insuffisants."),
}

FORMES = {"rent": "circle", "cyclical": "diamond", "eroding": "triangle",
          "no_moat": "square", "unknown": "cross"}

as_of = data.derniere_date_de_calcul()
if as_of is None:
    st.error("Aucune regression en base.")
    st.stop()

frame = data.screener(as_of)
st.title("Matrice qualite × prix")
st.caption(f"Calcul du prix au {as_of}. La qualite se recalcule au rythme des "
           f"publications de comptes, pas chaque semaine : recalculer la qualite "
           f"chaque semaine creerait une illusion de mouvement la ou il n'y en a pas.")

st.markdown(
    "<div class='avertissement'>La methode a deux jambes : la <b>qualite</b> "
    "(position concurrentielle, rente, erosion — le bloc D de la fiche) et le "
    "<b>prix</b> (z-score, ecart a la tendance). Cet ecran les croise. La grille "
    "de lecture tient en une phrase : <b>une decote n'est une opportunite que "
    "sur une qualite etablie</b> — decote sans qualite = piege probable, "
    "qualite sans decote = deja payee.</div>",
    unsafe_allow_html=True,
)
definitions.glossaire(definitions.MATRICE, "Comment lire cette matrice ?")

frame = frame.copy()
frame["quadrant"] = [
    quadrant(t, z) for t, z in zip(frame["quality_tier"], frame["z_score"])
]
frame["ecart_rente"] = frame["roic_vs_threshold"].astype(float) * 100

f1, f2, f3 = st.columns([2, 1.4, 1.2])
with f1:
    choix = st.multiselect(
        "Quadrant", list(QUADRANTS),
        default=[q for q in QUADRANTS if q != "unqualified"],
        format_func=lambda q: QUADRANTS[q][0],
    )
with f2:
    regimes = st.multiselect("Regime", sorted(frame["regime"].unique()))
with f3:
    seuil_decote = st.slider("Seuil de decote", -4.0, 0.0, -1.5, 0.1)

visible = frame[frame["quadrant"].isin(choix)] if choix else frame
if regimes:
    visible = visible[visible["regime"].isin(regimes)]

# Le filtre par defaut masque les non qualifies - c'est voulu, l'ecran sert a
# regarder ce qui est instruit - mais un graphe presque vide sans explication
# se lit comme une panne. Le compte des masques la remplace.
masques = len(frame) - len(visible)
if masques:
    st.caption(
        f"**{len(visible)} titre(s) affiché(s), {masques} masqué(s) par le "
        f"filtre de quadrant** — en phase de qualification, l'essentiel de "
        f"l'univers est `NON QUALIFIÉ` (aucun dossier concurrentiel validé) : "
        f"cocher ce quadrant pour tout voir.")

traçable = visible.dropna(subset=["ecart_rente"])
if traçable.empty:
    st.info(
        "Aucun titre traçable sur ce filtre : l'axe vertical exige un écart de "
        "rente calculé (ROIC − 8 %), donc des fondamentaux chargés et un score "
        "de qualité (`compute_quality`). Les quadrants restent listés plus bas.")
else:
    axe = alt.Axis(grid=True, gridColor=p.grille, gridDash=[],
                   labelColor=p.encre_secondaire, titleColor=p.encre_secondaire,
                   domainColor=p.encre_attenuee, tickColor=p.encre_attenuee)

    nuage = (
        alt.Chart(traçable)
        .mark_point(size=110, filled=True, opacity=0.85,
                    stroke=p.surface, strokeWidth=1)
        .encode(
            # La decote (z negatif) est A GAUCHE, comme le titre de l'axe
            # l'annonce. La premiere version posait domain=[4, -4], ce qui
            # mettait la decote a droite : l'axe contredisait son libelle.
            x=alt.X("z_score:Q", title="z-score  ←  decote        surcote  →",
                    scale=alt.Scale(domain=[-4, 4]), axis=axe),
            y=alt.Y("ecart_rente:Q", title="Ecart de rente : ROIC − 8 % (points)",
                    axis=axe),
            color=alt.Color(
                "z_score:Q", title="z-score",
                scale=alt.Scale(domain=[-4, 0, 4],
                                range=[p.z_decote, p.z_neutre, p.z_surcote]),
            ),
            shape=alt.Shape("regime:N", title="Regime",
                            scale=alt.Scale(domain=list(FORMES),
                                            range=list(FORMES.values()))),
            tooltip=["name:N", "quadrant:N", "regime:N", "quality_tier:N",
                     alt.Tooltip("z_score:Q", format="+.2f"),
                     alt.Tooltip("ecart_rente:Q", format="+.1f")],
        )
    )
    filets = (
        alt.Chart(pd.DataFrame({"x": [seuil_decote]}))
        .mark_rule(color=p.encre_attenuee, size=1).encode(x="x:Q")
        + alt.Chart(pd.DataFrame({"y": [0]}))
        .mark_rule(color=p.encre_attenuee, size=1).encode(y="y:Q")
    )

    # Les libelles de quadrant, ecrits en toutes lettres dans les coins : un
    # quadrant qui ne se comprend qu'en croisant deux axes mentalement ne se
    # comprend pas. Ce sont des reperes de lecture - le classement officiel
    # est la colonne Quadrant, calculee sur le niveau de qualite.
    HAUT, BAS = 12, 448
    coins = [
        (-3.9, "left", HAUT, "CIBLE — décote sur qualité établie"),
        (3.9, "right", HAUT, "WATCHLIST — qualité chère ou à confirmer"),
        (-3.9, "left", BAS, "VALUE TRAP — décote sur position qui se dégrade"),
        (3.9, "right", BAS, "À ÉVITER — cher et en dégradation"),
    ]
    libelles = None
    for x, alignement, y_px, texte in coins:
        calque = (
            alt.Chart(pd.DataFrame({"x": [x], "texte": [texte]}))
            .mark_text(align=alignement, fontSize=11, fontWeight="bold",
                       color=p.encre_attenuee)
            .encode(x="x:Q", y=alt.value(y_px), text="texte:N")
        )
        libelles = calque if libelles is None else libelles + calque

    st.altair_chart(
        (filets + nuage + libelles).properties(height=460, background=p.surface)
        .configure_view(stroke=None),
        use_container_width=True,
    )
    st.caption("Forme = regime · Couleur = z-score · Taille constante : la "
               "capitalisation n'entre pas dans la decision ici. Les libelles "
               "de coins sont des reperes : le classement officiel est celui "
               "des listes ci-dessous, calcule sur le niveau de qualite.")

# --------------------------------------------------------------------------- #
# Quatre listes, une par quadrant, avec le motif de classement.
# --------------------------------------------------------------------------- #
st.subheader("Listes par quadrant")
st.caption("**Sélectionner une ligne ouvre la fiche instrument.**")
for code, (titre, explication) in QUADRANTS.items():
    lot = frame[frame["quadrant"] == code].sort_values("z_score")
    with st.expander(f"{titre} — {len(lot)} titre(s)", expanded=code in ("target", "value_trap")):
        st.caption(explication)
        if lot.empty:
            st.write("Aucun titre.")
            continue
        navigation.tableau_vers_fiche(
            pd.DataFrame({
                "Nom": lot["name"],
                "z": lot["z_score"].round(2),
                "Qualite": lot["quality_tier"],
                "Regime": lot["regime"],
                "Erosion": lot["erosion_flags"].map(
                    lambda n: "—" if pd.isna(n) else f"{int(n)}/3"),
                "ROIC − 8 %": lot["ecart_rente"].round(1),
                "Fit": lot["fit_quality"],
                "Secteur": lot["secteur"],
            }),
            list(lot["internal_code"]), cle=f"matrice_{code}",
            use_container_width=True, hide_index=True,
        )

if (frame["quadrant"] == "target").sum() == 0:
    st.markdown(
        "<div class='avertissement'><b>Aucune cible, et ce n'est pas une "
        "anomalie.</b> Un titre n'atteint le quadrant CIBLE que si trois "
        "conditions convergent : un dossier concurrentiel <b>validé par un "
        "analyste</b> avec un concurrent hors Europe dans le groupe de pairs "
        "(écran Dossier concurrentiel), une <b>rente quantitative</b> établie "
        "dans les comptes (ROIC durablement au-dessus de 8 %), et une "
        "<b>décote</b> sous le seuil. Un dossier validé ne suffit donc pas : "
        "tant que la rente ne se lit pas dans les comptes, le titre reste en "
        "WATCHLIST — et c'est le verdict honnête.</div>",
        unsafe_allow_html=True,
    )
