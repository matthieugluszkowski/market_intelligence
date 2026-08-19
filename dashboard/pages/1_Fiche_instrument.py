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

from dashboard import charts, data  # noqa: E402
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
choix = st.sidebar.selectbox(
    "Instrument", univers["internal_code"],
    format_func=lambda c: univers.set_index("internal_code").loc[c, "name"],
)

f = data.fit(choix, as_of)
if f is None:
    st.error(f"Aucune regression pour {choix} au {as_of}.")
    st.stop()

barres = data.barres(choix, "1w")
serie = charts.serie_de_regression(barres, f)

st.title(f["name"])
st.caption(f"{f['isin']} · {choix} · politique {f['policy_code']} · "
           f"calcul du {as_of} · methode v{f['method_version']}")

# --------------------------------------------------------------------------- #
# Bloc A - Le graphe de regression
# --------------------------------------------------------------------------- #
st.subheader("A · Cours et tendance")

if serie.empty:
    st.warning("Aucune barre dans la fenetre de regression.")
else:
    st.altair_chart(charts.graphe_regression(serie, p, f["currency"]),
                    use_container_width=True)
    st.caption(
        f"Fenetre {f['window_start']} → {f['window_end']}, {f['n_obs']} barres "
        f"hebdomadaires. Echelle logarithmique : le modele est lineaire en log, "
        f"un axe lineaire courberait la droite. Zones bleutees : episodes passes "
        f"sous −2σ — la decote est un regime, pas un instant."
    )

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

# --------------------------------------------------------------------------- #
# Bloc D - Position concurrentielle (L6b)
# --------------------------------------------------------------------------- #
st.subheader("D · Position concurrentielle")
st.markdown(
    "<div class='avertissement'><b>Non evaluee.</b> Leadership, rente et erosion "
    "arrivent avec le lot L6b. Ce titre est donc <code>unqualified</code> — pas "
    "« sans barriere », mais « jamais regarde ». La droite de regression est un "
    "outil statistique, elle a ses limites, et elle doit toujours etre completee "
    "par l'analyse fondamentale.</div>",
    unsafe_allow_html=True,
)

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
