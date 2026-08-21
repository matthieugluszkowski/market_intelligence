"""Fiche instrument (doc 04 SS3, ecran 2).

L'ecran central. Les blocs sont dans cet ordre parce que **le prix declenche
l'attention et la qualite decide** : bloc A le graphe, bloc B les diagnostics,
bloc C les statistiques de regime, bloc D la position concurrentielle - qui
arrive avec L6b et s'affiche vide, pas masquee.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# Rechargement des modules du projet si leurs sources ont change. **Doit rester
# avant les imports qui suivent** : Streamlit garde les modules importes en cache
# et une purge posterieure laisserait coexister deux versions d une meme classe.
from dashboard.rechargement import recharge_si_modifie  # noqa: E402

recharge_si_modifie()

from dashboard import charts, data, definitions, entete, navigation  # noqa: E402
from market_intelligence import watchlist  # noqa: E402
from market_intelligence.analytics.quality import (  # noqa: E402
    groupe_comparable, quadrant,
)
from market_intelligence.db import connect_direct  # noqa: E402
from market_intelligence.intelligence import schema  # noqa: E402
from dashboard.theme import (  # noqa: E402
    css, motif_en_clair, palette, pastille_statut, vignette,
)

st.set_page_config(page_title="Fiche instrument", page_icon="◧", layout="wide")

sombre = st.sidebar.toggle("Mode sombre", value=False)
p = palette(sombre)
st.markdown(css(p), unsafe_allow_html=True)

as_of = data.derniere_date_de_calcul()
if as_of is None:
    st.error("Aucune regression en base. Lancer `python scripts/compute_fits.py`.")
    st.stop()

univers = data.instruments()
codes = list(univers["internal_code"])

# Une navigation depuis le screener, la watchlist ou la matrice arrive ici avec
# son titre : il preselectionne la liste, puis la main revient a l'utilisateur.
cible = navigation.cible_demandee(codes)
if cible is not None:
    st.session_state["fiche_instrument_choix"] = cible

# L'univers compte 586 titres, la regression n'en couvre qu'une partie : le
# premier code par ordre alphabetique n'a aucune raison d'etre calcule, et la
# fiche s'ouvrait donc sur « Aucune regression pour EQ:DE:ENERGY ». Un ecran qui
# accueille par une erreur se lit comme un ecran casse. Le defaut va au premier
# titre calcule, et les autres portent la mention dans la liste plutot que de la
# reveler une fois choisis.
calcules = set(data.screener(as_of)["internal_code"])
noms = univers.set_index("internal_code")["name"]
defaut = next((i for i, c in enumerate(codes) if c in calcules), 0)

choix = st.sidebar.selectbox(
    "Instrument", codes, index=defaut, key="fiche_instrument_choix",
    format_func=lambda c: (noms.loc[c] if c in calcules
                           else f"{noms.loc[c]} · non calculé"),
)

f = data.fit(choix, as_of)
if f is None:
    st.error(
        f"**{noms.loc[choix]} n'a pas de regression au {as_of}.** Le titre est "
        f"dans l'univers mais la regression ne l'a pas retenu — historique trop "
        f"court, serie trop lacunaire, ou politique de regression non "
        f"applicable. {len(calcules)} titres sur {len(codes)} sont calcules.")
    st.stop()

barres = data.barres(choix, "1w")
serie = charts.serie_de_regression(barres, f)

# --------------------------------------------------------------------------- #
# Watchlist — dans la barre laterale, sous le selecteur d'instrument
#
# Une premiere version placait le bouton dans une colonne etroite a droite du
# titre. Il y etait, mais personne ne le voyait : sur un ecran large, un bouton
# au cinquieme droit de la page n'est pas dans le champ de lecture. Ici, il est
# a cote du selecteur - c'est-a-dire la ou l'on agit deja sur le titre courant.
# --------------------------------------------------------------------------- #
with connect_direct() as conn, conn.cursor() as cur:
    suivi = watchlist.est_suivi(cur, int(f["instrument_id"]))

st.sidebar.divider()
if suivi:
    st.sidebar.markdown(f"★ **Suivi depuis le {suivi.depuis}**")
    if suivi.z_at_add is not None:
        derive = float(f["z_score"]) - suivi.z_at_add
        st.sidebar.caption(f"z à l'ajout {suivi.z_at_add:+.2f} → "
                           f"{f['z_score']:+.2f} ({derive:+.2f})")
    if suivi.note:
        st.sidebar.caption(f"« {suivi.note} »")
    if st.sidebar.button("Retirer de la watchlist", use_container_width=True):
        with connect_direct() as conn, conn.cursor() as cur:
            watchlist.retire(cur, int(f["instrument_id"]))
            conn.commit()
        st.rerun()
else:
    if st.sidebar.button("★ Ajouter à la watchlist", use_container_width=True,
                         type="primary"):
        st.session_state["_ajout_watchlist"] = True

    if st.session_state.get("_ajout_watchlist"):
        with st.sidebar.form("ajout_watchlist"):
            st.caption(
                "**Pourquoi suivre ce titre ?** À écrire maintenant, pas plus "
                "tard : relire dans un an ce qu'on avait en tête est le seul "
                "antidote fiable au biais rétrospectif."
            )
            note = st.text_area("Note", height=90,
                                placeholder="Ce que j'attends, ce que je surveille…")
            if st.form_submit_button("Ajouter", type="primary",
                                     use_container_width=True):
                with connect_direct() as conn, conn.cursor() as cur:
                    watchlist.ajoute(cur, int(f["instrument_id"]), note)
                    conn.commit()
                st.session_state.pop("_ajout_watchlist", None)
                st.rerun()
            if st.form_submit_button("Annuler", use_container_width=True):
                st.session_state.pop("_ajout_watchlist", None)
                st.rerun()

portefeuille = data.portefeuille()
entete.bandeau_portefeuille(portefeuille)

st.title(("★ " if suivi else "") + f["name"])
st.caption(f"{f['isin']} · {choix} · politique {f['policy_code']} · "
           f"calcul du {as_of} · methode v{f['method_version']}")

# Les positions ouvertes sur CE titre : elles marquent le graphe du bloc A et
# se resument juste en dessous.
mes_lignes = (portefeuille[portefeuille["internal_code"] == choix]
              if not portefeuille.empty else portefeuille)

# --------------------------------------------------------------------------- #
# Bloc A - Le graphe de regression
# --------------------------------------------------------------------------- #
st.subheader("A · Cours et tendance")

if serie.empty:
    st.warning("Aucune barre dans la fenetre de regression.")
else:
    st.altair_chart(
        charts.graphe_regression(serie, p, f["currency"], positions=mes_lignes),
        use_container_width=True)
    st.caption(
        f"Fenetre {f['window_start']} → {f['window_end']}, {f['n_obs']} barres "
        f"hebdomadaires. Echelle logarithmique : le modele est lineaire en log, "
        f"un axe lineaire courberait la droite. Zones bleutees : episodes passes "
        f"sous −2σ — la decote est un regime, pas un instant."
    )

    # --- Ma position sur ce titre ------------------------------------------
    # Le graphe porte les deux traits rouges ; cette ligne porte les nombres.
    # Sans elle, l'ecart entre la courbe et le prix de revient se lit « a peu
    # pres » — ce qui suffit pour regarder, pas pour decider.
    if not mes_lignes.empty:
        for _, ligne in mes_lignes.iterrows():
            mode = "fictive" if ligne["is_paper"] else "réelle"
            hors_cadre = []
            achat = pd.Timestamp(ligne["opened_at"])
            if achat < pd.Timestamp(serie["ts"].min()):
                hors_cadre.append("achat anterieur a la fenetre de regression")
            elif achat > pd.Timestamp(serie["ts"].max()) + charts.MARGE_APRES:
                hors_cadre.append("achat trop posterieur a la derniere barre "
                                  "connue — les cours ne sont plus a jour")
            if not (float(serie["bande_basse_2"].min()) <= ligne["avg_price"]
                    <= float(serie["bande_haute_2"].max())):
                hors_cadre.append("prix de revient hors de l'echelle affichee")
            variation = (f" · {ligne['plus_value']:+,.2f} {ligne['currency']} "
                         f"({ligne['plus_value_pct']:+.1%})"
                         if pd.notna(ligne["plus_value"]) else "")
            st.markdown(
                f"<div class='avertissement'>"
                f"<b>Ma position ({mode})</b> — {ligne['quantity']:g} titre(s) "
                f"a {ligne['avg_price']:.2f} {ligne['currency']} depuis le "
                f"{ligne['opened_at']:%d/%m/%Y} ({ligne['jours']} jour(s)) · "
                f"cours {ligne['cours']:.2f}{variation}. "
                f"Les traits rouges du graphe marquent la date d'achat et le "
                f"prix de revient."
                + (f" <b>Non tracé :</b> {', '.join(hors_cadre)}."
                   if hors_cadre else "")
                + "</div>", unsafe_allow_html=True)
    elif not portefeuille.empty:
        st.caption("Aucune position ouverte sur ce titre.")

    with st.expander("Vue tabulaire du graphe (valeurs exactes)"):
        st.caption(
            "Toute visualisation a son jumeau tabulaire : c'est une exigence "
            "d'accessibilite, et la seule facon de verifier qu'un graphe ne ment "
            "pas — notamment de le confronter a une source externe."
        )
        table = charts.jumeau_tabulaire(serie)
        st.dataframe(table, use_container_width=True, hide_index=True, height=320)
        st.download_button(
            "Telecharger la serie (CSV)",
            table.to_csv(index=False).encode("utf-8"),
            file_name=f"{choix.replace(':', '_')}_serie.csv",
            mime="text/csv",
        )

# --------------------------------------------------------------------------- #
# Bloc B - Bandeau de diagnostics
# --------------------------------------------------------------------------- #
st.subheader("B · Diagnostics")

stats = f["regime_stats"] or {}
demi_vie = f["half_life_days"]
semaines = int(stats.get("semaines_consecutives_en_cours") or 0)

colonnes = st.columns(5)
with colonnes[0]:
    st.markdown(vignette("z actuel", f"{f['z_score']:+.2f}",
                         f"cours {f['last_close']:.2f} {f['currency']}"),
                unsafe_allow_html=True)
with colonnes[1]:
    valeur = "non etablie" if pd.isna(demi_vie) or demi_vie is None else (
        f"{demi_vie / 30.44:.0f} mois" if demi_vie else "< 1 semaine")
    st.markdown(vignette("Demi-vie", valeur, "vitesse de rappel vers la tendance"),
                unsafe_allow_html=True)
with colonnes[2]:
    st.markdown(vignette("Sous −2σ depuis",
                         f"{semaines} sem." if semaines else "—",
                         stats.get("premier_franchissement") or "hors episode"),
                unsafe_allow_html=True)
with colonnes[3]:
    st.markdown(vignette("Pente annuelle", f"{f['slope_annual']:+.2%}",
                         f"r² = {f['r_squared']:.2f}"),
                unsafe_allow_html=True)
with colonnes[4]:
    st.markdown(vignette("Qualite du fit", pastille_statut(f["fit_quality"]), ""),
                unsafe_allow_html=True)

motifs = list(f["quality_reasons"] or [])
if motifs:
    st.markdown(
        "<div class='avertissement'>Motif : "
        + " · ".join(motif_en_clair(m) for m in motifs)
        + "</div>", unsafe_allow_html=True,
    )

definitions.glossaire(definitions.DIAGNOSTICS)

with st.expander("Detail technique des tests"):
    ar_bas, ar_haut = f["ar1_ci_low"], f["ar1_ci_high"]
    diagnostics = pd.DataFrame([
        {"Test": "ADF (log-prix, constante + tendance)",
         "Statistique": f["adf_stat"], "p-value": f["adf_pvalue"],
         "Lecture": "valeur critique ~ −3.41 a 5%"},
        {"Test": "DF-GLS (log-prix, constante + tendance)",
         "Statistique": f["dfgls_stat"], "p-value": None,
         "Lecture": "arbitre le verdict : plus puissant que l'ADF pres de la racine unitaire"},
        {"Test": "KPSS", "Statistique": f["kpss_stat"], "p-value": None,
         "Lecture": "hypothese nulle inversee : stationnarite"},
        {"Test": "Durbin-Watson", "Statistique": f["durbin_watson"], "p-value": None,
         "Lecture": "2 = pas d'autocorrelation residuelle"},
    ])
    st.dataframe(diagnostics, use_container_width=True, hide_index=True)

    if ar_bas is not None and ar_haut is not None:
        inclut_un = ar_bas <= 1.0 <= ar_haut
        st.markdown(f"**Racine autoregressive dominante** : `[{ar_bas:.3f} ; {ar_haut:.3f}]`")
        if inclut_un:
            st.markdown(
                "<div class='avertissement'>Intervalle incluant 1 : le retour a la "
                "tendance n'est pas etabli. Sur vingt ans, aucun test ne distingue "
                "de facon fiable ρ = 1 de ρ = 0,99 — l'intervalle dit la verite, "
                "a savoir qu'on ne sait pas trancher.</div>",
                unsafe_allow_html=True)
        else:
            st.markdown(
                "<div class='avertissement'>Intervalle excluant 1, mais obtenu par "
                "bootstrap par blocs, <b>anti-conservateur pres de la racine "
                "unitaire</b> : les residus sont ceux d'une tendance estimee, donc "
                "deja detendances. En cas de desaccord avec le DF-GLS, c'est le "
                "test qui fait foi — lui seul alimente le verdict.</div>",
                unsafe_allow_html=True)

# --------------------------------------------------------------------------- #
# Bloc C - Statistiques de regime
# --------------------------------------------------------------------------- #
st.subheader("C · Statistiques de regime")
st.markdown(
    "<div class='avertissement'><b>Ces statistiques sont calculees sur "
    "l'historique complet, donc in-sample.</b> Elles decrivent le passe de ce "
    "titre, elles ne sont pas une probabilite. « Sous −2σ moins de 5% du temps » "
    "est une frequence temporelle, pas une chance de retournement : les residus "
    "sont autocorreles, les episodes hors bande sont des regimes qui durent.</div>",
    unsafe_allow_html=True,
)

if stats.get("n_episodes"):
    gauche, droite = st.columns(2)
    with gauche:
        lignes = [
            ("Episodes sous −2σ sur l'historique", stats["n_episodes"]),
            ("Part du temps sous le seuil", f"{stats['part_du_temps_sous_seuil']:.1%}"),
            ("Duree mediane d'un episode", f"{stats['duree_mediane_semaines']:.0f} semaines"),
            ("Duree maximale observee", f"{stats['duree_max_semaines']} semaines"),
            ("Baisse supplementaire mediane", f"{stats['drawdown_median_apres_seuil']:+.1%}"),
            ("Pire baisse supplementaire", f"{stats['drawdown_pire_apres_seuil']:+.1%}"),
        ]
        st.dataframe(pd.DataFrame(lignes, columns=["Metrique", "Valeur"]),
                     use_container_width=True, hide_index=True)
    with droite:
        rendements = stats.get("rendements_apres_franchissement") or {}
        if rendements:
            table = pd.DataFrame([
                {"Horizon": horizon, "Episodes": v["n"],
                 "Median": f"{v['median']:+.1%}",
                 "Etendue": f"{v['min']:+.1%} a {v['max']:+.1%}"}
                for horizon, v in rendements.items()
            ])
            st.dataframe(table, use_container_width=True, hide_index=True)
            st.caption("Distribution, jamais moyenne seule : c'est la dispersion "
                       "qui informe. Nombre d'episodes tres faible — a lire comme "
                       "un ordre de grandeur, pas comme une esperance.")
else:
    st.info("Ce titre n'est jamais passe sous −2σ sur la fenetre analysee.")

definitions.glossaire(definitions.REGIME)

# --------------------------------------------------------------------------- #
# Bloc D - Position concurrentielle (L6b)
# --------------------------------------------------------------------------- #
st.subheader("D · Position concurrentielle")

qual = data.qualite(choix)
if not qual:
    st.info("Aucun score de qualite. Lancer `python scripts/compute_quality.py`.")
else:
    q = qual["score"]
    couleurs_tier = {"solid": "#0ca30c", "watch": "#fab219",
                     "eroding": "#d03b3b", "unqualified": "#898781"}
    icones_tier = {"solid": "●", "watch": "▲", "eroding": "■", "unqualified": "○"}
    libelles_tier = {
        "solid": "Position etablie, rente persistante, aucune erosion detectee",
        "watch": "A surveiller",
        "eroding": "Rente en erosion",
        "unqualified": "Position non qualifiee",
    }
    tier = q["quality_tier"]
    st.markdown(
        f"<span class='pastille' style='color:{couleurs_tier[tier]};"
        f"border-color:{couleurs_tier[tier]}'>{icones_tier[tier]} "
        f"{libelles_tier[tier]}</span>  ·  regime <b>{q['regime']}</b>  ·  "
        f"quadrant <b>{quadrant(tier, float(f['z_score']))}</b>",
        unsafe_allow_html=True,
    )

    # Un decoupage sectoriel a onze cases n'est pas un groupe de pairs : les
    # indicateurs relatifs ne sont alors pas publies, et l'ecran doit dire que
    # c'est un refus de publier — pas une donnee manquante.
    comparable = groupe_comparable(q["groupe_code"], q["groupe_kind"],
                                   q["groupe_complet"])
    if not comparable:
        st.markdown(
            f"<div class='avertissement'><b>Indicateurs relatifs non publiés</b> — "
            f"le groupe « {q['groupe_label'] or '—'} » est un découpage sectoriel "
            f"automatique, pas un groupe de pairs. Comparer le ROIC d'une "
            f"entreprise à la médiane de sa case sectorielle produit un nombre "
            f"lisible et faux ; les trois mesures relatives (part relative, rang "
            f"par chiffre d'affaires, écart à la médiane des pairs) affichent donc "
            f"« — ». Les mesures <b>absolues</b> ci-dessous restent valables, et "
            f"ce sont elles qui décident du régime et du verdict. Pour obtenir des "
            f"comparaisons, constituer un groupe depuis un dossier concurrentiel "
            f"(onglet Analyses).</div>", unsafe_allow_html=True)

    trois = st.columns(3)
    with trois[0]:
        st.caption("Q1 · Leadership")
        st.dataframe(pd.DataFrame([
            {"Mesure": "Part relative au plus grand pair",
             "Valeur": "—" if pd.isna(q["relative_share"]) else f"{q['relative_share']:.2f}"},
            {"Mesure": "Rang par chiffre d'affaires",
             "Valeur": "—" if pd.isna(q["rank_by_revenue"]) else int(q["rank_by_revenue"])},
        ]), use_container_width=True, hide_index=True)
    with trois[1]:
        st.caption("Q2 · Rente")
        st.dataframe(pd.DataFrame([
            {"Mesure": "ROIC moyen", "Valeur": "—" if pd.isna(q["roic_mean_5y"])
             else f"{q['roic_mean_5y']:.1%}"},
            {"Mesure": "Ecart au seuil de 8 %", "Valeur": "—" if pd.isna(q["roic_vs_threshold"])
             else f"{q['roic_vs_threshold']:+.1%}"},
            {"Mesure": "Ecart a la mediane des pairs", "Valeur": "—" if pd.isna(q["roic_vs_peers"])
             else f"{q['roic_vs_peers']:+.1%}"},
            {"Mesure": "Persistance", "Valeur": f"{q['persistence_years']}/{q['n_years_available']} exercices"},
            {"Mesure": "Marge brute moyenne", "Valeur": "—" if pd.isna(q["gross_margin_mean"])
             else f"{q['gross_margin_mean']:.1%}"},
        ]), use_container_width=True, hide_index=True)
    with trois[2]:
        st.caption("Q3 · Erosion — les trois pentes, separement")
        st.dataframe(pd.DataFrame([
            {"Pente": "ROIC", "Par an": "—" if pd.isna(q["roic_slope_5y"])
             else f"{q['roic_slope_5y']:+.2%}"},
            {"Pente": "Marge brute", "Par an": "—" if pd.isna(q["gross_margin_slope_5y"])
             else f"{q['gross_margin_slope_5y']:+.2%}"},
            {"Pente": "Part relative", "Par an": "—" if pd.isna(q["share_slope_5y"])
             else f"{q['share_slope_5y']:+.2%}"},
            {"Pente": "Drapeaux d'erosion", "Par an": f"{int(q['erosion_flags'])}/3"},
        ]), use_container_width=True, hide_index=True)
        st.caption("Le decompte, pas un verdict : trois pentes negatives se lisent "
                   "3/3. Plus honnete qu'un feu tricolore.")

    membres = qual["membres"]
    complet = bool(q["groupe_complet"])
    st.markdown(f"**Groupe de pairs** : {q['groupe_label'] or '—'} "
                f"(`{q['groupe_kind'] or '—'}`)")
    if not membres.empty:
        st.dataframe(
            membres.rename(columns={"nom": "Concurrent", "is_in_universe": "Dans l'univers",
                                    "pays": "Pays", "menace": "Menace identifiee"}),
            use_container_width=True, hide_index=True,
        )
    if not complet:
        st.markdown(
            "<div class='avertissement'><b>Groupe incomplet : aucun concurrent hors "
            "Europe.</b> C'est la limite la plus serieuse du systeme. Les menaces "
            "reelles viennent presque toujours de l'exterieur de l'univers — "
            "SharkNinja est americaine, BYD est chinoise, Revolut n'est pas cotee. "
            "Un groupe purement europeen est d'autant plus rassurant qu'il ne "
            "contient pas le concurrent. Aucun titre ne peut passer "
            "<code>solid</code> dans cet etat.</div>",
            unsafe_allow_html=True)

    evaluation = qual["evaluation"]
    st.markdown("**Evaluation qualitative**")
    if evaluation is None:
        st.markdown(
            "<div class='avertissement'>Aucune evaluation. Le moat quantitatif "
            "mesure le <b>passe</b> : un ROIC eleve est la trace d'une barriere qui "
            "a existe, il ne dit rien de sa resistance a une rupture technologique. "
            "Seule la jambe qualitative peut ecrire « cette barriere est menacee "
            "par X », et X n'est jamais dans les comptes. Un LLM peut la rediger ; "
            "il ne la valide jamais — <code>reviewed_by</code> reste humain.</div>",
            unsafe_allow_html=True)
    else:
        st.dataframe(pd.DataFrame([{
            "Evaluee le": evaluation["assessed_at"],
            "Expire le": evaluation["expires_at"],
            "Position": evaluation["position_verdict"],
            "Durabilite": evaluation["durability_verdict"],
            "Auteur": evaluation["authored_by"],
            "Revue par": evaluation["reviewed_by"] or "NON VALIDEE",
        }]), use_container_width=True, hide_index=True)
        if bool(evaluation["perimee"]):
            st.markdown(
                "<div class='avertissement'><b>Evaluation perimee.</b> Une "
                "evaluation de plus de 18 mois inspire exactement la meme confiance "
                "qu'une recente, et c'est le probleme. Le titre reste dans le "
                "screener mais son quadrant s'affiche non qualifie.</div>",
                unsafe_allow_html=True)

    if tier == "eroding":
        st.markdown(
            "<div class='avertissement'>Croise avec une decote, ce titre tombe en "
            "<b>value trap</b> : la decote sur une position qui s'erode n'est pas "
            "une decote, c'est un ajustement de prix correct.</div>",
            unsafe_allow_html=True)

    definitions.glossaire(definitions.QUALITE)

# --------------------------------------------------------------------------- #
# Bloc D bis - Le dossier concurrentiel, tel qu'importe
#
# La jambe qualitative du bloc D : ce que les prompts 1 a 4 ont etabli, relu ou
# non. Il s'affiche des le premier fragment - un dossier en cours de
# constitution se montre comme tel, il ne se cache pas derriere un ecran vide.
# --------------------------------------------------------------------------- #
st.markdown("#### Dossier concurrentiel")

info_dossier = data.dossier_concurrentiel(choix)
if not info_dossier:
    st.info("Aucun dossier. Le constituer sur l'écran « Analyses » : "
            "cinq prompts, cinq imports.")
else:
    d = info_dossier["dossier"]
    r = schema.resume(d)

    if info_dossier["status"] == "validated":
        etat_dossier = f"**validé** par {info_dossier['analyst']}"
    else:
        etat_dossier = "**brouillon** — non validé, aucun verdict projeté"
    st.caption(
        f"Dossier {etat_dossier} · référence {r['date_reference']} · importé le "
        f"{info_dossier['importe_le']} · expire le {info_dossier['expires_at']} · "
        f"{r['n_concurrents']} concurrent(s) · {r['n_fonctions']} fonction(s) · "
        f"{r['n_sources']} source(s)"
    )

    etapes = schema.avancement(d)
    st.markdown(" · ".join(
        ("<span style='color:#0ca30c'>●</span> " if e["fait"]
         else "<span style='color:#898781'>○</span> ") + e["etape"]
        for e in etapes), unsafe_allow_html=True)
    manques = [e["manque"] for e in etapes if e["manque"]]
    if manques:
        st.caption("Reste à faire : " + " · ".join(manques))

    # --- Synthèse décisionnelle et scoring (prompt 5) -----------------------
    scoring = schema.lire(d, "scoring", defaut={})
    synthese5 = schema.lire(d, "synthese", defaut={})
    if scoring or synthese5:
        verdict5 = schema.lire(synthese5, "recommendation_status",
                               "classification")
        def note(cle: str) -> str:
            valeur = schema.lire(scoring, cle)
            try:
                return f"{float(valeur):.0f}/100"
            except (TypeError, ValueError):
                return "—"
        quatre = st.columns(4)
        quatre[0].metric("Attractivité", note("attractiveness_score"),
                         help="Qualité et intérêt potentiel du dossier. Ne "
                              "prédit pas le cours futur.")
        quatre[1].metric("Confiance", note("confidence_score"),
                         help="Robustesse, fraîcheur, cohérence et "
                              "vérifiabilité de l'analyse. Sous 50, aucune "
                              "conclusion forte n'est permise.")
        quatre[2].metric("Alignement", note("alignment_score"),
                         help="Cohérence entre qualité, risque, perspectives "
                              "et prix actuel.")
        quatre[3].metric("Avis",
                         schema.VERDICTS_SYNTHESE.get(verdict5, verdict5 or "—"),
                         help="Conclusion prudente du prompt 5 — un avis "
                              "d'analyse, jamais un conseil d'investissement. "
                              "« Insuffisant pour conclure » est une réponse "
                              "valide.")
        porte = schema.lire(d, "decision_gate", defaut={})
        etat_revue = {"not_reviewed": "non relue", "reviewed": "relue",
                      "approved": "approuvée", "rejected": "rejetée"}.get(
            schema.lire(scoring, "human_review_status"), "non relue")
        st.caption(
            f"Synthèse du {schema.lire(scoring, 'scored_at', defaut='—')} · "
            f"produite par {schema.lire(scoring, 'scored_by', defaut='llm')} · "
            f"**{etat_revue}** · conclusion "
            f"{'autorisée' if schema.lire(porte, 'conclusion_allowed') else 'non autorisée'} "
            f"par le contrôle préalable · "
            f"{schema.lire(porte, 'blocking_issues_count', defaut=0)} point(s) "
            f"bloquant(s) signalé(s)")

        with st.expander("Synthèse décisionnelle — détail"):
            if schema.lire(synthese5, "recommendation_status", "rationale"):
                st.markdown(f"**Thèse.** "
                            f"{schema.lire(synthese5, 'recommendation_status', 'rationale')}")
            for titre_bloc, cle_bloc in (
                    ("Points favorables", "key_strengths"),
                    ("Risques principaux", "key_risks"),
                    ("Hypothèses critiques", "critical_hypotheses"),
                    ("Données manquantes ou à actualiser", "missing_or_stale_data"),
                    ("Indicateurs à surveiller", "monitoring_indicators"),
                    ("Déclencheurs de révision", "review_triggers")):
                valeurs = schema.lire(synthese5, cle_bloc, defaut=[])
                if valeurs:
                    st.markdown(f"**{titre_bloc}**")
                    for v in valeurs:
                        st.markdown(f"- {v}")
            revision = schema.lire(synthese5, "review_recommended_at")
            if revision:
                st.caption(f"Révision recommandée : {revision}")
            st.json(synthese5, expanded=False)

    synthese = schema.lire(d, "strategic_assessment", defaut={})
    if any(schema.lire(synthese, cle) for cle in
           ("position_verdict", "durability_verdict", "rationale",
            "main_strengths", "main_weaknesses", "threats")):
        with st.expander("Synthèse stratégique sur le titre", expanded=True):
            elements = []
            if schema.lire(synthese, "position_verdict"):
                elements.append(f"position **{schema.lire(synthese, 'position_verdict')}**")
            if schema.lire(synthese, "durability_verdict"):
                elements.append(f"durabilité **{schema.lire(synthese, 'durability_verdict')}**")
            moats = schema.lire(synthese, "moat_sources", defaut=[])
            if moats:
                elements.append("rente : " + ", ".join(moats))
            if elements:
                st.markdown(" · ".join(elements))
            if schema.lire(synthese, "rationale"):
                st.markdown(f"*{schema.lire(synthese, 'rationale')}*")
            forces = schema.lire(synthese, "main_strengths", defaut=[])
            faiblesses = schema.lire(synthese, "main_weaknesses", defaut=[])
            menaces = schema.lire(synthese, "threats", defaut=[])
            for titre_liste, valeurs in (("Forces", forces),
                                         ("Faiblesses", faiblesses),
                                         ("Menaces", menaces)):
                if valeurs:
                    st.markdown(f"**{titre_liste}** : "
                                + " · ".join(str(x) for x in valeurs))
            if info_dossier["status"] != "validated":
                st.caption("Proposition non validée : ces verdicts ne sont "
                           "projetés qu'à l'import signé du prompt 4.")

    concurrents = schema.lire(d, "competitors", defaut=[])
    if concurrents:
        with st.expander(f"Concurrents retenus ({len(concurrents)})"):
            st.dataframe(pd.DataFrame([{
                "Concurrent": schema.lire(c, "company_name"),
                "Pays": schema.lire(c, "country", defaut="—"),
                "Type": schema.lire(c, "competition_type", defaut="—"),
                "Fiche": "oui" if schema.lire(c, "profile_available") else "—",
                "Statut": schema.lire(c, "status", defaut="—"),
                "Justification": (schema.lire(c, "relevance_explanation",
                                              defaut="") or "")[:120],
            } for c in concurrents]), use_container_width=True, hide_index=True)

    profils = [p for p in schema.lire(d, "company_profiles", defaut=[])
               if isinstance(p, dict)]
    if profils:
        with st.expander(f"Fiches concurrents ({len(profils)})"):
            st.dataframe(pd.DataFrame([{
                "Concurrent": schema.lire(p, "company_name", defaut="sans nom"),
                "Menace globale": schema.lire(p, "competitive_relevance",
                                              "overall_threat_level", defaut="—"),
                "Menace principale": (schema.lire(p, "strategic_assessment",
                                                  "main_threat", defaut="") or "")[:110],
                "Vulnérabilité": (schema.lire(p, "strategic_assessment",
                                              "main_vulnerability", defaut="") or "")[:110],
                "Forces": len(schema.lire(p, "strengths", defaut=[])),
                "Faiblesses": len(schema.lire(p, "weaknesses", defaut=[])),
                "Signaux": len(schema.lire(p, "trajectory_signals", defaut=[])),
            } for p in profils]), use_container_width=True, hide_index=True)
            nom_fiche = st.selectbox(
                "Fiche détaillée", [schema.lire(p, "company_name",
                                                defaut="sans nom") for p in profils])
            profil = next(p for p in profils
                          if schema.lire(p, "company_name", defaut="sans nom") == nom_fiche)
            st.json(profil, expanded=False)

    leaders = schema.lire(d, "market_leaders", defaut=[])
    if leaders:
        with st.expander(f"Leaders du marché ({len(leaders)})"):
            st.dataframe(pd.DataFrame([{
                "Rang": schema.lire(le, "rank", defaut="—"),
                "Acteur": schema.lire(le, "company", defaut=schema.lire(le, "name")),
                "Critère de leadership": (schema.lire(le, "leadership_criteria",
                                                      defaut="") or "")[:120],
                "Segments dominés": ", ".join(s) if isinstance(
                    (s := schema.lire(le, "dominated_segments", defaut="—")), list)
                    else str(s)[:120],
            } for le in leaders]), use_container_width=True, hide_index=True)

    tendances = schema.lire(d, "market_trends", defaut=[])
    if tendances:
        with st.expander(f"Tendances structurantes ({len(tendances)})"):
            st.dataframe(pd.DataFrame([{
                "Tendance": schema.lire(t, "trend", defaut="—"),
                "Horizon": schema.lire(t, "horizon", defaut="—"),
                "Preuves": (schema.lire(t, "description",
                                        defaut=schema.lire(t, "evidence", defaut="")) or "")[:130],
                "Impact sur le titre": (schema.lire(t, "impact",
                                                    defaut=schema.lire(t, "impact_on_adidas",
                                                                       defaut="")) or "")[:130],
            } for t in tendances]), use_container_width=True, hide_index=True)

    ruptures = schema.lire(d, "disruption_points", defaut=[])
    if ruptures:
        with st.expander(f"Points de rupture possibles ({len(ruptures)})"):
            st.dataframe(pd.DataFrame([{
                "Rupture": schema.lire(x, "point", defaut="—"),
                "Nature": schema.lire(x, "nature", defaut="—"),
                "Probabilité": schema.lire(x, "probability", defaut="—"),
                "Scénario": (schema.lire(x, "rupture_scenario", defaut="") or "")[:130],
            } for x in ruptures]), use_container_width=True, hide_index=True)

    scenarios = schema.lire(d, "future_scenarios", defaut=[])
    if scenarios:
        with st.expander(f"Scénarios à 12-36 mois ({len(scenarios)})"):
            st.dataframe(pd.DataFrame([{
                "Scénario": schema.lire(s, "scenario_name", defaut="—"),
                "Probabilité": schema.lire(s, "probability",
                                           defaut=schema.lire(s, "qualitative_probability",
                                                              defaut="—")),
                "Hypothèses": (schema.lire(s, "hypotheses", defaut="") or "")[:160],
            } for s in scenarios]), use_container_width=True, hide_index=True)

    contradictoire = schema.lire(d, "contrarian_conclusion", defaut={})
    if contradictoire:
        with st.expander("Conclusion contradictoire"):
            st.caption("Le meilleur argument dans chaque sens, l'hypothèse la plus "
                       "fragile, et ce qui ferait changer d'avis : c'est la partie "
                       "du dossier qui protège contre la lecture complaisante.")
            # Les clés varient avec l'entreprise analysée
            # (`best_argument_for_adidas`) : on les lit par motif, pas par nom.
            for cle, valeur in contradictoire.items():
                if cle == "status" or not isinstance(valeur, str) or not valeur:
                    continue
                if cle.startswith("best_argument_for"):
                    libelle = "Pour le titre"
                elif cle.startswith("best_argument_against"):
                    libelle = "Contre le titre"
                elif cle == "most_fragile_hypothesis":
                    libelle = "Hypothèse la plus fragile"
                elif cle == "information_that_would_change_conclusion":
                    libelle = "Ce qui ferait changer d'avis"
                else:
                    libelle = cle.replace("_", " ").capitalize()
                st.markdown(f"**{libelle}.** {valeur}")

    recommandations = schema.lire(d, "recommendations", defaut=[])
    implications = schema.lire(d, "implications_for_company", defaut=[])
    if recommandations or implications:
        with st.expander("Recommandations et implications pour le titre"):
            for imp in implications:
                st.markdown(f"- {imp}")
            for rec in recommandations:
                if isinstance(rec, dict):
                    st.markdown(f"**{schema.lire(rec, 'category', defaut='—')}**")
                    for action in schema.lire(rec, "actions", defaut=[]):
                        st.markdown(f"- {action}")
                else:
                    st.markdown(f"- {rec}")

    a_revoir = schema.lire(d, "manual_review", defaut=[])
    bloquants_qc = schema.lire(d, "quality_control", "blocking_issues", defaut=[])
    # Un bloquant requalifié laisse sa trace : sans elle, on ne saurait plus
    # trois mois plus tard si le point a été traité, mesuré faux, ou oublié.
    requalifies = schema.lire(d, "quality_control",
                              "blocking_issues_requalifies", defaut=[])
    if a_revoir or bloquants_qc or requalifies:
        with st.expander(f"À vérifier à la main ({len(a_revoir)}) · "
                         f"bloquants restants ({len(bloquants_qc)})"):
            for probleme in bloquants_qc:
                st.markdown(f"- **BLOQUANT** : {probleme}")
            if requalifies:
                LIBELLES = {
                    "leve_par_mesure": "levé par mesure",
                    "defaut_de_generation": "défaut de génération, pas de dossier",
                    "corrige": "corrigé",
                    "maintenu": "maintenu",
                }
                st.markdown(f"**Bloquants requalifiés ({len(requalifies)})** — "
                            "chacun confronté au dossier tel qu'il est en base :")
                for r in requalifies:
                    verdict = schema.lire(r, "verdict", defaut="—")
                    st.markdown(
                        f"- `{schema.lire(r, 'code', defaut='—')}` "
                        f"**{LIBELLES.get(verdict, verdict)}** — "
                        f"{schema.lire(r, 'constat', defaut='')} "
                        f"*Preuve : {schema.lire(r, 'preuve', defaut='—')}* "
                        f"({schema.lire(r, 'par', defaut='—')}, "
                        f"{schema.lire(r, 'le', defaut='—')})")
            for element in a_revoir:
                if isinstance(element, dict):
                    st.markdown(
                        f"- **{schema.lire(element, 'item', defaut='—')}** — "
                        f"{schema.lire(element, 'issue', defaut='')} "
                        f"*(priorité {schema.lire(element, 'priority', defaut='—')})*")
                else:
                    st.markdown(f"- {element}")

    definitions.glossaire(definitions.DOSSIER,
                          "Comment lire le dossier concurrentiel ?")

# --------------------------------------------------------------------------- #
# Bloc E - Fondamentaux (regime A)
# --------------------------------------------------------------------------- #
st.subheader("E · Fondamentaux")

fonda = data.fondamentaux(choix, as_of)
if not fonda:
    st.info("Aucun fondamental connu a cette date. "
            "Lancer `python scripts/ingest_fundamentals.py`.")
else:
    r, coherence = fonda["ratios"], fonda["coherence"]

    couleurs = {"confirme": "#0ca30c", "suspect": "#d03b3b", "indeterminable": "#fab219"}
    icones = {"confirme": "●", "suspect": "■", "indeterminable": "▲"}
    libelles = {
        "confirme": "Signal coherent avec les fondamentaux",
        "suspect": "Signal suspect : value trap potentiel",
        "indeterminable": "Coherence non evaluable : donnees incompletes",
    }
    verdict = coherence.verdict
    st.markdown(
        f"<span class='pastille' style='color:{couleurs[verdict]};"
        f"border-color:{couleurs[verdict]}'>{icones[verdict]} {libelles[verdict]}"
        f"</span>", unsafe_allow_html=True,
    )

    detail = [{"Critere": nom, "Resultat": "tenu" if ok else "EN ECHEC"}
              for nom, ok in coherence.criteres.items()]
    detail += [{"Critere": nom, "Resultat": "non evaluable"}
               for nom in coherence.manquants]
    st.dataframe(pd.DataFrame(detail), use_container_width=True, hide_index=True)

    if verdict == "suspect":
        st.markdown(
            "<div class='avertissement'>Ce titre a l'air decote et un critere "
            "fondamental est en echec. <b>Sortir les signaux suspects est aussi "
            "utile que sortir les bons</b> : c'est la liste des titres qui ont "
            "l'air d'opportunites et n'en sont pas, et c'est la qu'on perd de "
            "l'argent.</div>", unsafe_allow_html=True)
    elif verdict == "indeterminable":
        st.markdown(
            "<div class='avertissement'>Un critere qu'on ne peut pas evaluer n'est "
            "pas un critere reussi. Traiter l'absence de donnee comme un succes est "
            "la facon la plus courante de fabriquer un faux signal.</div>",
            unsafe_allow_html=True)

    familles = {
        "Valorisation": [("PER", "per", "x"), ("EV/EBIT", "ev_ebit", "x"),
                         ("EV/CA", "ev_revenue", "x"), ("P/B", "price_to_book", "x"),
                         ("Rendement du FCF", "fcf_yield", "%"),
                         ("Rendement du dividende", "dividend_yield", "%")],
        "Rentabilite": [("Marge brute", "marge_brute", "%"),
                        ("Marge operationnelle", "marge_operationnelle", "%"),
                        ("Marge nette", "marge_nette", "%"),
                        ("ROE", "roe", "%"), ("ROCE", "roce", "%"),
                        ("ROIC", "roic", "%")],
        "Solidite": [("Dette nette / EBITDA", "dette_nette_sur_ebitda", "x"),
                     ("Couverture des interets", "couverture_interets", "x"),
                     ("Gearing", "gearing", "%")],
        "Dynamique": [("Croissance CA 3 ans", "croissance_ca_3a", "%"),
                      ("Croissance CA 5 ans", "croissance_ca_5a", "%"),
                      ("Croissance RN 3 ans", "croissance_rn_3a", "%")],
        "Distribution": [("Taux de distribution", "taux_de_distribution", "%"),
                         ("Dilution nette 3 ans", "dilution_nette", "%")],
    }
    for colonne, (famille, lignes) in zip(st.columns(len(familles)), familles.items()):
        with colonne:
            st.caption(famille)
            st.dataframe(
                pd.DataFrame([
                    {"Ratio": libelle,
                     "Valeur": ("—" if r.get(cle) is None
                                else f"{r[cle]:.1%}" if unite == "%"
                                else f"{r[cle]:.2f}x")}
                    for libelle, cle, unite in lignes
                ]),
                use_container_width=True, hide_index=True,
            )

    definitions.glossaire(definitions.FONDAMENTAUX)

    st.markdown(
        "<div class='avertissement'><b>Ce bloc est un filtre de solvabilite, pas un "
        "jugement de qualite.</b> Une entreprise peut cocher toutes ces cases et "
        "perdre sa position concurrentielle — c'est l'objet du lot L6b, et c'est la "
        "moitie de la methode qui manque encore.</div>",
        unsafe_allow_html=True)

    with st.expander(f"Faits sources ({len(fonda['exercices'])} exercices)"):
        if not fonda["faits"].empty:
            st.dataframe(fonda["faits"], use_container_width=True, hide_index=True)
        if bool(r.get("dates_estimees")):
            st.markdown(
                "<div class='avertissement'><b>Dates de publication estimees.</b> "
                "yfinance n'en sert aucune : on applique le delai reglementaire de "
                "la directive Transparence, soit quatre mois apres la cloture. C'est "
                "une borne <i>superieure</i> — l'erreur va deliberement dans le sens "
                "tardif, parce qu'une estimation trop precoce fabriquerait du "
                "look-ahead invisible, tandis qu'une estimation trop tardive ne "
                "produit qu'un exces de prudence.</div>",
                unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
# Anomalies et historique des calculs
# --------------------------------------------------------------------------- #
anomalies = data.anomalies(choix)
if not anomalies.empty:
    st.subheader("Anomalies qualite ouvertes")
    st.dataframe(
        anomalies[["issue_type", "severity", "depuis", "run_count", "details"]],
        use_container_width=True, hide_index=True,
    )
    st.caption("Traiter avec `python scripts/anomalies.py --resoudre <id> --note \"...\"`.")

historique = data.historique_des_fits(choix)
if len(historique) > 1:
    st.subheader("Ce que le modele affirmait, semaine apres semaine")
    st.altair_chart(charts.graphe_historique_fits(historique, p),
                    use_container_width=True)
    with st.expander("Vue tabulaire"):
        st.dataframe(historique, use_container_width=True, hide_index=True)
else:
    st.caption(
        f"Un seul calcul historise a ce jour ({as_of}). Chaque semaine ajoute une "
        f"observation reellement hors echantillon : 52 dans un an, et au bout de "
        f"trois ans un jeu de donnees que personne ne publie — le comportement "
        f"effectif des titres apres un signal, mesure en temps reel. C'est la "
        f"validation de la methode obtenue par simple ecoulement du temps."
    )
