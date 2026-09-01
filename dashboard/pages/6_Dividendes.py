"""Screener Actions a Dividende sous-cotees & Rendements potentiels moyens.

Cet ecran croise la decote de cours (z-score de regression) et le rendement du dividende,
en mettant en avant la securite du flux de distribution (couverture FCF) et les dividendes
moyens sur 5 ans pour neutraliser les dividendes exceptionnels.
"""

from __future__ import annotations

import sys
from pathlib import Path

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dashboard.rechargement import recharge_si_modifie  # noqa: E402

recharge_si_modifie()

from dashboard import data, definitions, entete, navigation  # noqa: E402
from dashboard.theme import css, palette, statut  # noqa: E402

st.set_page_config(page_title="Screener Dividendes", page_icon="◧", layout="wide")

sombre = st.sidebar.toggle("Mode sombre", value=False)
p = palette(sombre)
st.markdown(css(p), unsafe_allow_html=True)

as_of = data.derniere_date_de_calcul()
if as_of is None:
    st.error("Aucune régression en base. Lancer `python scripts/compute_fits.py`.")
    st.stop()

entete.bandeau_portefeuille(data.portefeuille())

st.title("Screener · Actions à dividende sous-cotées")
st.caption(
    f"Calculs de prix et rendements au {as_of}. "
    f"Ce screener combine décote statistique de cours et flux de dividendes réels."
)

st.markdown(
    "<div class='avertissement'>"
    "<b>Pourquoi croiser décote ($z$-score) et dividende ?</b> "
    "Acheter une entreprise distributrice sous sa tendance de long terme offre un <b>double effet</b> : "
    "un rendement sur coût d'achat gonflé par le creux de marché, et un potentiel de plus-value en capital. "
    "<b>Garde-fou :</b> toujours vérifier le <i>DPA moyen 5 ans</i> et la <i>couverture par le Free Cash Flow</i> "
    "pour éviter les dividendes exceptionnels et les entreprises qui s'endettent pour payer leur dividende."
    "</div>",
    unsafe_allow_html=True,
)

# Charger les données de dividendes
df = data.screener_dividendes(as_of)
if df.empty:
    st.warning("Aucune donnée de dividende disponible.")
    st.stop()

# --------------------------------------------------------------------------- #
# Filtres
# --------------------------------------------------------------------------- #
f1, f2, f3, f4, f5 = st.columns([1.2, 1.2, 1.3, 1.3, 1.2])

with f1:
    seuil_z = st.slider(
        "Décote max (z-score)",
        min_value=-4.0,
        max_value=2.0,
        value=0.0,
        step=0.1,
        help="Garder les actions dont le cours est sous ce seuil en écarts-types (ex: <= 0 = sous la moyenne).",
    )

with f2:
    min_rdt = st.slider(
        "Rendement actuel min (%)",
        min_value=0.0,
        max_value=15.0,
        value=3.5,
        step=0.5,
        help="Filtre sur le rendement actuel (Dernier DPA / Cours).",
    )

with f3:
    options_secu = ["Tous", "sécurisé", "soutenable", "tendu", "exceptionnel"]
    secu_choix = st.multiselect(
        "Sécurité du dividende",
        options_secu,
        default=["sécurisé", "soutenable"],
        help="Basé sur la couverture du dividende par le Free Cash Flow réel.",
    )

with f4:
    secteurs = st.multiselect(
        "Secteur",
        sorted([s for s in df["secteur"].dropna().unique()]),
        help="Filtrer par secteur ICB.",
    )

with f5:
    pays = st.multiselect(
        "Pays",
        sorted([c for c in df["country_iso2"].dropna().unique()]),
        help="Filtrer par pays d'origine.",
    )

# Application des filtres
filtre = df.copy()
filtre = filtre[filtre["z_score"] <= seuil_z]
filtre = filtre[filtre["rendement_actuel_pct"] >= min_rdt]

if "Tous" not in secu_choix and secu_choix:
    filtre = filtre[filtre["securite_dividende"].isin(secu_choix)]

if secteurs:
    filtre = filtre[filtre["secteur"].isin(secteurs)]

if pays:
    filtre = filtre[filtre["country_iso2"].isin(pays)]

# --------------------------------------------------------------------------- #
# Indicateurs clés de synthèse
# --------------------------------------------------------------------------- #
c1, c2, c3, c4 = st.columns(4)
with c1:
    st.metric("Titres qualifiés", len(filtre))
with c2:
    rdt_med = filtre["rendement_actuel_pct"].median() if not filtre.empty else 0
    st.metric("Rendement médian actuel", f"{rdt_med:.2f} %" if rdt_med else "-")
with c3:
    rdt_5a_med = filtre["rendement_moyen_5a_pct"].median() if not filtre.empty else 0
    st.metric("Rendement moyen 5 ans", f"{rdt_5a_med:.2f} %" if rdt_5a_med else "-")
with c4:
    z_med = filtre["z_score"].median() if not filtre.empty else 0
    st.metric("Décote médiane (z-score)", f"{z_med:+.2f} σ" if z_med else "-")

st.markdown("---")

# --------------------------------------------------------------------------- #
# Graphique interactif : Rendement vs Décote (Z-score)
# --------------------------------------------------------------------------- #
st.subheader("Cartographie Rendement vs Décote")

if not filtre.empty:
    COULEURS_SECU = {
        "sécurisé": "#0ca30c",
        "soutenable": "#fab219",
        "tendu": "#d03b3b",
        "exceptionnel": "#898781",
        "indéterminable": "#898781",
    }

    graphe_df = filtre.copy()
    graphe_df["rendement_plafonne"] = graphe_df["rendement_actuel_pct"].clip(upper=20.0)

    axe_x = alt.Axis(
        grid=True,
        gridColor=p.grille,
        gridDash=[],
        labelColor=p.encre_secondaire,
        titleColor=p.encre_secondaire,
        title="Position du cours (z-score en écarts-types)",
    )
    axe_y = alt.Axis(
        grid=True,
        gridColor=p.grille,
        gridDash=[],
        labelColor=p.encre_secondaire,
        titleColor=p.encre_secondaire,
        title="Rendement actuel du dividende (%)",
    )

    scatter = (
        alt.Chart(graphe_df)
        .mark_circle(size=120, opacity=0.85)
        .encode(
            x=alt.X("z_score:Q", axis=axe_x),
            y=alt.Y("rendement_plafonne:Q", axis=axe_y),
            color=alt.Color(
                "securite_dividende:N",
                scale=alt.Scale(
                    domain=list(COULEURS_SECU.keys()),
                    range=list(COULEURS_SECU.values()),
                ),
                legend=alt.Legend(title="Sécurité dividende"),
            ),
            tooltip=[
                alt.Tooltip("name:N", title="Société"),
                alt.Tooltip("internal_code:N", title="Code"),
                alt.Tooltip("last_close:Q", title="Cours", format=".2f"),
                alt.Tooltip("z_score:Q", title="Z-score", format="+.2f"),
                alt.Tooltip("rendement_actuel_pct:Q", title="Rdt actuel (%)", format=".2f"),
                alt.Tooltip("rendement_moyen_5a_pct:Q", title="Rdt moy 5a (%)", format=".2f"),
                alt.Tooltip("dernier_dpa:Q", title="Dernier DPA", format=".2f"),
                alt.Tooltip("dpa_moyen_5a:Q", title="DPA moyen 5a", format=".2f"),
                alt.Tooltip("payout_fcf_pct:Q", title="Payout FCF (%)", format=".1f"),
                alt.Tooltip("securite_dividende:N", title="Diagnostic"),
            ],
        )
        .properties(height=360, background=p.surface)
        .configure_view(stroke=None)
        .configure(font="system-ui")
    )
    st.altair_chart(scatter, use_container_width=True)

# --------------------------------------------------------------------------- #
# Tableau complet
# --------------------------------------------------------------------------- #
st.subheader("Tableau des opportunités de dividende")

if filtre.empty:
    st.info("Aucune action ne correspond aux critères sélectionnés.")
else:
    suivis = data.codes_suivis()

    table_data = []
    for _, r in filtre.iterrows():
        code = r["internal_code"]
        etoile = "★" if code in suivis else "☆"

        # Badge sécurité
        secu = r["securite_dividende"]
        badge_secu = {
            "sécurisé": "🟢 Sécurisé",
            "soutenable": "🟡 Soutenable",
            "tendu": "🔴 Tendu",
            "exceptionnel": "⚪ Exceptionnel",
            "indéterminable": "⚪ Non évalué",
        }.get(secu, secu)

        # FCF payout format
        fcf_str = f"{r['payout_fcf_pct']:.0f} %" if pd.notna(r.get("payout_fcf_pct")) else "n/d"
        rn_str = f"{r['payout_rn_pct']:.0f} %" if pd.notna(r.get("payout_rn_pct")) else "n/d"

        table_data.append({
            "Suivi": etoile,
            "Code": code,
            "Société": r["name"],
            "Secteur": r["secteur"] or "-",
            "Pays": r["country_iso2"] or "-",
            "Cours": f"{r['last_close']:.2f} {r['currency']}",
            "Z-Score": f"{r['z_score']:+.2f} σ",
            "Rdt Actuel": f"{r['rendement_actuel_pct']:.2f} %",
            "Rdt Moy 5a": f"{r['rendement_moyen_5a_pct']:.2f} %",
            "Dernier DPA": f"{r['dernier_dpa']:.2f} {r['currency']}",
            "DPA Moy 5a": f"{r['dpa_moyen_5a']:.2f} {r['currency']}" if pd.notna(r.get("dpa_moyen_5a")) else "-",
            "Couverture FCF": fcf_str,
            "Payout RN": rn_str,
            "Sécurité": badge_secu,
            "Qualité": r["quality_tier"],
        })

    t_df = pd.DataFrame(table_data)
    st.dataframe(t_df, use_container_width=True, hide_index=True)

    st.caption(
        "Conseil : cliquer sur une ligne dans la *Fiche instrument* pour analyser l'historique complet, "
        "la trajectoire de régression et les flux de trésorerie."
    )
