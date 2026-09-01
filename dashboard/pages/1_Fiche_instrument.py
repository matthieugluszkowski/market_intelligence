"""Fiche instrument (doc 04 SS3, ecran 2).

L'ecran central. Les blocs sont dans cet ordre parce que **le prix declenche
l'attention et la qualite decide** : bloc A le graphe, bloc B les diagnostics,
bloc C les statistiques de regime, bloc D la position concurrentielle - qui
arrive avec L6b et s'affiche vide, pas masquee.

Deux ajouts du 2026-08-25, et ils vont ensemble
------------------------------------------------
La cinquieme vignette du bloc B portait la **qualite du fit**. Elle y disait
quelque chose sur la methode, jamais sur l'entreprise, et laissait la question
qui decide - *qui est leader ?* - a six ecrans de la. Elle porte desormais la
**solidite concurrentielle** ; la qualite du fit est descendue dans le
depliable technique, a cote des tests qui la produisent.

Le bloc B bis - *ce que disent les autres* - repond a la seule question que la
regression ne peut pas traiter : **qu'est-ce qui vient d'arriver ?** Un modele
qui lit vingt ans de cours n'en a aucune idee, et c'est pourtant la premiere
chose qu'on se demande devant un titre a -2,4 sigma. Consensus, notations et
depeches y sont affiches **a cote** du signal, jamais melanges a lui : ils
n'entrent dans aucun calcul (doc 02 SS2.5).

Ce que la fiche ne montre plus - bloc E, anomalies, historique des fits - est
explique en fin de fichier, avec ce qu'il faut savoir de ce qui part avec.
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

from dashboard import (  # noqa: E402
    charts, data, definitions, entete, navigation, veille,
)
from market_intelligence import watchlist  # noqa: E402
from market_intelligence.analytics.quality import (  # noqa: E402
    groupe_comparable, quadrant,
)
from market_intelligence.db import connect_direct  # noqa: E402
from market_intelligence.intelligence import position  # noqa: E402
from market_intelligence.jobs import ingest_veille  # noqa: E402
from dashboard.theme import (  # noqa: E402
    css, motif_en_clair, palette, pastille_statut, statut, vignette,
)

st.set_page_config(page_title="Fiche instrument", page_icon="◧", layout="wide")

sombre = st.sidebar.toggle("Mode sombre", value=False)
p = palette(sombre)
st.markdown(css(p), unsafe_allow_html=True)

# Libelle de l'option qui ne filtre rien. Il vaut mieux qu'il ne puisse pas
# collisionner avec un libelle de classe d'actif.
TOUT = "Tout"

as_of = data.derniere_date_de_calcul()
if as_of is None:
    st.error("Aucune regression en base. Lancer `python scripts/compute_fits.py`.")
    st.stop()

univers = data.instruments()
noms = univers.set_index("internal_code")["name"]

# Une navigation depuis le screener, la watchlist ou la matrice arrive ici avec
# son titre : il preselectionne la liste, puis la main revient a l'utilisateur.
cible = navigation.cible_demandee(list(univers["internal_code"]))
if cible is not None:
    st.session_state["fiche_instrument_choix"] = cible
    # La cible peut appartenir a une autre classe que celle filtree. C'est elle
    # qui gagne - arriver du screener sur une liste qui ne contient pas le titre
    # demande casserait la navigation. L'ecrire n'est possible qu'**ici**, avant
    # que le widget n'existe : apres, Streamlit refuse qu'on touche a sa cle.
    classe_de_la_cible = univers.set_index("internal_code").loc[cible, "classe_actif"]
    if st.session_state.get("fiche_classe", TOUT) not in (TOUT, classe_de_la_cible):
        st.session_state["fiche_classe"] = TOUT

# Le meme decoupage qu'au screener, et pour la meme raison : chercher « Or »
# dans une liste de 598 lignes ou 586 sont des actions demande de savoir a
# l'avance ce qu'on cherche. Le choix n'apparait qu'a partir de deux classes.
classes = sorted(univers["classe_actif"].dropna().unique())
classe = TOUT
if len(classes) > 1:
    classe = st.sidebar.radio("Type d'actif", [TOUT, *classes], horizontal=True,
                              key="fiche_classe")

retenus = univers if classe == TOUT else univers[univers["classe_actif"] == classe]
codes = list(retenus["internal_code"])

# Le filtre a pu retirer de la liste le titre choisi au passage precedent, et
# Streamlit refuse une valeur de session absente des options. On la lache, le
# defaut ci-dessous reprend la main.
if st.session_state.get("fiche_instrument_choix") not in codes:
    st.session_state.pop("fiche_instrument_choix", None)

# L'univers compte 586 titres, la regression n'en couvre qu'une partie : le
# premier code par ordre alphabetique n'a aucune raison d'etre calcule, et la
# fiche s'ouvrait donc sur « Aucune regression pour EQ:DE:ENERGY ». Un ecran qui
# accueille par une erreur se lit comme un ecran casse. Le defaut va au premier
# titre calcule, et les autres portent la mention dans la liste plutot que de la
# reveler une fois choisis.
calcules = set(data.screener(as_of)["internal_code"])
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
        f"applicable. {len(calcules & set(codes))} titres sur {len(codes)} "
        f"sont calcules dans cette selection.")
    st.stop()

barres = data.barres(choix, "1w")
serie = charts.serie_de_regression(barres, f)

# Une matiere premiere n'a ni bilan, ni concurrent, ni position a defendre. Les
# blocs D, « position analysee » et E n'y sont donc pas *en attente de calcul*,
# ils sont **sans objet** - et les deux se ressemblent trop pour etre confondus :
# « lancer compute_quality.py » enverrait relancer un job qui ne produira jamais
# rien pour cette ligne. Les blocs A, B et C, eux, sont identiques a ceux d'une
# action : meme serie hebdomadaire, meme droite log-lineaire, meme z-score.
sans_fondamentaux = f["asset_class"] not in ("equity", "dividend_stock")
if f["asset_class"] == "etf":
    SANS_OBJET = (
        "Sans objet pour un ETF : panier indiciel diversifié sans bilan d'entreprise "
        "unique ni position concurrentielle individuelle. L'aide à la décision se lit "
        "sur les blocs A à C (canal de régression, z-score de décote/surévaluation, "
        "statistiques de régime)."
    )
elif f["asset_class"] == "commodity":
    SANS_OBJET = (
        "Sans objet pour une matière première : ni bilan, ni concurrent, "
        "ni position à défendre. Le signal se lit sur les blocs A à C."
    )
else:
    SANS_OBJET = (
        "Sans objet pour cette classe d'actif : le signal se lit sur les blocs A à C."
    )



def solidite_concurrentielle(info: dict | None, sans_objet: bool) -> tuple:
    """Le contenu de la cinquieme vignette : **le constat, pas la note**.

    « leader » en gros, « 78/100 · position forte » en petit. L'ordre n'est pas
    cosmetique : un score de 78 ne dit rien tant qu'on ne sait pas s'il note un
    leader ou un suiveur, alors que « leader » se lit sans son bareme. Le score
    reste sous les yeux parce qu'il porte la nuance — leader depuis dix-huit
    mois et leader depuis vingt ans ne valent pas pareil.
    """
    titre = "Solidité concurrentielle"
    if sans_objet:
        return titre, "sans objet", "ni concurrent, ni position à défendre"
    if not info:
        return titre, "non analysée", "écran Analyses : un prompt, une réponse"

    dossier = info["dossier"]
    if not position.est_v2(dossier):
        return titre, "à migrer", "dossier à l'ancien format"

    verdict = position.lire(dossier, "position", "verdict")
    constat = position.LIBELLES_POSITION.get(verdict, verdict or "non posée")
    score = position.calcule_le_score(dossier)

    detail = [f"{score.total}/100 · {score.niveau}"]
    annees = position.annees_de_position(dossier)
    if annees is not None:
        detail.append(f"depuis {annees} an{'s' if annees > 1 else ''}")
    durabilite = position.lire(dossier, "durabilite", "verdict")
    if durabilite:
        detail.append(position.LIBELLES_DURABILITE.get(durabilite, durabilite))
    # Un dossier non relu ne vaut pas un dossier relu, et la vignette est
    # justement l'endroit ou l'on ne prendra pas le temps d'aller verifier.
    if info.get("status") != "validated":
        detail.append("<b>brouillon</b>")
    return titre, constat, " · ".join(detail)

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
st.caption(f"{f['isin'] or (f['attributes'] or {}).get('unite') or f['classe_actif']}"
           f" · {choix} · politique {f['policy_code']} · "
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
    # Deux facons de regarder de plus pres, et elles ne font pas la meme chose.
    # La **periode** coupe la serie : l'echelle des ordonnees se recalcule sur
    # ce qui reste, et un episode de six mois cesse d'etre un pli dans une
    # courbe de vingt ans. Le **zoom** garde toute la serie et grossit une zone.
    # Ni l'un ni l'autre ne re-estime la regression : la droite et les bandes
    # sont celles qui ont ete calculees sur la fenetre complete.
    gauche, droite = st.columns([3, 2])
    with gauche:
        periode = st.radio("Periode affichee", list(charts.PERIODES),
                           horizontal=True, label_visibility="collapsed",
                           key="fiche_periode")
    with droite:
        # Un curseur plutot qu'une hauteur fixe : sur un portable, 900 px de
        # graphe font disparaitre les diagnostics sous la ligne de flottaison ;
        # sur un ecran large, 420 px ecrasent vingt ans en une bande.
        hauteur = st.select_slider("Hauteur du graphe (pixels)",
                                   [420, 520, 620, 760, 900], value=620)

    vue = charts.fenetre(serie, periode)
    st.altair_chart(
        charts.graphe_regression(vue, p, f["currency"], hauteur=hauteur,
                                 positions=mes_lignes),
        use_container_width=True)
    st.caption(
        f"**Molette pour zoomer, glisser pour se deplacer, double-clic pour "
        f"revenir.** Fenetre de regression {f['window_start']} → "
        f"{f['window_end']}, {f['n_obs']} barres hebdomadaires — "
        f"{len(vue)} affichees. Echelle logarithmique : le modele est lineaire "
        f"en log, un axe lineaire courberait la droite. Zones bleutees : "
        f"episodes passes sous −2σ — la decote est un regime, pas un instant."
    )

    # Le meme fait, lu autrement. Sur vingt ans d'echelle logarithmique, un
    # ecart de deux sigma se voit mal en haut et se lit immediatement ici.
    st.altair_chart(charts.panneau_z(vue, p), use_container_width=True)
    st.caption(
        "Ecart a la tendance, en ecarts types. Les trois filets sont −2σ, 0 et "
        "+2σ. Ce panneau ne suit pas le zoom du graphe du dessus : il sert de "
        "vue d'ensemble quand on est zoome sur quelques mois."
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
            # Sur `vue`, pas sur `serie` : ce qui compte est ce qui est trace, et
            # ce qui est trace est la periode affichee. Restreindre a cinq ans
            # peut sortir un achat du cadre — il faut alors le dire.
            if achat < pd.Timestamp(vue["ts"].min()):
                hors_cadre.append("achat anterieur a la periode affichee")
            elif achat > pd.Timestamp(vue["ts"].max()) + charts.MARGE_APRES:
                hors_cadre.append("achat trop posterieur a la derniere barre "
                                  "connue — les cours ne sont plus a jour")
            if not (float(vue["bande_basse_2"].min()) <= ligne["avg_price"]
                    <= float(vue["bande_haute_2"].max())):
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
        table = charts.jumeau_tabulaire(vue)
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

# Le dossier de position est lu ici, avant les vignettes : c'est lui qui remplit
# la cinquieme, et le bloc D bis le relit plus bas sans le recharger.
info_dossier = None if sans_fondamentaux else data.dossier_concurrentiel(choix)

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
    # Cinquieme vignette : **la conclusion du dossier, pas la qualite du fit**.
    # Le verdict statistique de la regression a longtemps occupe cette place ;
    # il y disait quelque chose sur la methode, jamais sur l'entreprise, et
    # laissait la question qui decide - qui est leader ? - a six ecrans de la.
    # La qualite du fit n'a pas disparu : elle est dans « Detail technique des
    # tests », a cote des tests qui la produisent, et ses motifs restent
    # affiches en clair sous le bandeau.
    st.markdown(vignette(*solidite_concurrentielle(
        info_dossier, sans_fondamentaux)), unsafe_allow_html=True)

if f["asset_class"] == "dividend_stock":
    prof_b = data.profil_dividende(choix, as_of)
    if prof_b and prof_b.dernier_dpa:
        cours_val = float(f["last_close"])
        tendance_val = float(f["fitted_value"]) if f["fitted_value"] else cours_val
        pot_cours = ((tendance_val - cours_val) / cours_val) * 100.0 if cours_val > 0 else 0.0
        rdt_div_moy = prof_b.rendement_moyen_5a_pct or 0.0
        gain_total = rdt_div_moy + pot_cours
        st.markdown(
            f"<div class='avertissement' style='border-left: 4px solid #0ca30c;'>"
            f"<b>Action à dividende (éligible PEA)</b> · "
            f"<b>DPA moyen 5 ans :</b> {prof_b.dpa_moyen_5a:.2f} {f['currency']} "
            f"(<b>Rendement moyen :</b> {rdt_div_moy:.2f} %) · "
            f"<b>Rattrapage de cours vers la tendance :</b> {pot_cours:+.1f} % · "
            f"<b>Plus-value totale moyenne espérée :</b> <span style='color:#0ca30c; font-weight:bold;'>{gain_total:+.1f} %</span>"
            f"</div>",
            unsafe_allow_html=True,
        )

motifs = list(f["quality_reasons"] or [])
if motifs:
    st.markdown(
        "<div class='avertissement'><b>Reserves sur la regression</b> "
        + f"({statut(f['fit_quality'])[2].lower()}) : "
        + " · ".join(motif_en_clair(m) for m in motifs)
        + "</div>", unsafe_allow_html=True,
    )

definitions.glossaire(definitions.DIAGNOSTICS)

with st.expander("Detail technique des tests"):
    st.markdown(f"**Qualite du fit** — {pastille_statut(f['fit_quality'])}",
                unsafe_allow_html=True)
    st.caption("Verdict des trois tests ci-dessous sur la validite de la "
               "regression, donc sur le sens du z-score. C'est une propriete de "
               "la **methode appliquee a ce titre**, pas un jugement sur "
               "l'entreprise — d'ou sa place ici, a cote des tests qui le "
               "produisent.")
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
# Bloc B bis - Ce que disent les autres (lot L10)
#
# Consensus d'analystes, notations et depeches, collectes chez Zonebourse et
# Boursier.com. Ils sont **ici**, dans le bloc des diagnostics, parce que c'est
# au moment ou l'on regarde un z-score qu'on se demande ce qui vient d'arriver -
# et le modele, qui lit vingt ans de cours, n'en a aucune idee.
#
# Ils n'entrent dans aucun calcul. Le consensus est structurellement optimiste
# et revise apres coup : l'integrer au score reviendrait a acheter ce que tout
# le monde recommande deja, c'est-a-dire l'inverse exact d'un screener de
# decote. Sa valeur est ailleurs - savoir si la decote est un secret ou non, et
# lire ou le consensus contredit le modele.
#
# Le sous-bloc disparait entierement sur une matiere premiere : aucune des deux
# sources ne suit l'or ou le cuivre par ISIN, et un encart vide en permanence se
# lit comme une collecte en panne.
# --------------------------------------------------------------------------- #
if not sans_fondamentaux:
    st.markdown("#### Ce que disent les autres")

    collectes = data.veille(choix)
    url_zb = data.url_de_veille(choix, "zonebourse")

    if not any(collectes.values()):
        st.markdown(
            "<div class='avertissement'>Aucune collecte pour ce titre. Les trois "
            "encarts ci-dessous sont vides tant que la veille n'a pas tourne — pas "
            "parce que les analystes se taisent, mais parce que personne n'est allé "
            "leur demander.</div>", unsafe_allow_html=True)

    trois = st.columns([2, 2, 3])
    with trois[0]:
        veille.bloc_consensus(collectes.get("consensus"))
    with trois[1]:
        veille.bloc_notations(collectes.get("notations"))
    with trois[2]:
        veille.bloc_depeches(collectes.get("depeches"))

    with st.expander("Collecter, ou changer l'adresse des sources"):
        st.caption(
            "Boursier.com se resout depuis l'ISIN : rien a saisir. Zonebourse "
            "adresse ses fiches par identifiant interne, qui ne se devine pas — et "
            "un identifiant approchant ne rend pas une erreur, **il rend la fiche "
            "d'une autre societe**. L'adresse se colle donc une fois, depuis le "
            "navigateur ; n'importe quel onglet de la fiche fait l'affaire."
        )
        saisie = st.text_input(
            "Adresse Zonebourse de ce titre", value=url_zb or "",
            placeholder="https://www.zonebourse.com/cours/action/NOM-1234/",
            key=f"url_zb_{choix}")
        gauche, droite = st.columns(2)
        if gauche.button("Enregistrer l'adresse", use_container_width=True,
                         disabled=not saisie.strip()):
            with connect_direct() as conn, conn.cursor() as cur:
                ingest_veille.enregistre_url(cur, int(f["instrument_id"]),
                                             "zonebourse", saisie.strip())
                conn.commit()
            st.rerun()

        if droite.button("Collecter maintenant", type="primary",
                         use_container_width=True):
            # Une dizaine de requetes, avec un delai entre chacune : c'est long, et
            # un ecran qui parait fige pendant vingt secondes parait casse.
            with st.spinner("Collecte en cours — une requete par page, espacees."):
                with connect_direct() as conn, conn.cursor() as cur:
                    resultat = ingest_veille.collecte_un(
                        cur, int(f["instrument_id"]), choix, f["isin"])
                    conn.commit()
            # Ce cache-la seulement : purger tout le cache du dashboard
            # rechargerait les 586 lignes du screener et les 1 044 barres du
            # graphe pour une depeche.
            data.veille.clear()
            if resultat.ok:
                st.success(f"Collecte : {resultat.resume()}.")
            for erreur in resultat.erreurs:
                st.warning(erreur)
            if resultat.ok:
                st.rerun()

        st.caption(
            "La collecte se lance titre par titre, a la demande. En lot : "
            "`python scripts/ingest_veille.py` — watchlist et portefeuille par "
            "defaut. Passer les 586 titres martelerait deux serveurs pour des pages "
            "que personne n'ira lire."
        )

    definitions.glossaire(definitions.VEILLE,
                          "Comment lire les avis de tiers ?")

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
if sans_fondamentaux:
    st.info(SANS_OBJET)
elif not qual:
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
# Bloc D bis - Position concurrentielle telle qu'analysee
#
# La jambe qualitative du bloc D, reduite a ce qui decide : qui est leader,
# depuis quand, qui le menace et en quoi c'est dangereux.
#
# La version precedente affichait vingt-deux blocs - besoins clients, analyse
# fonctionnelle, scenarios prospectifs, sept notes par categorie, trois scores -
# et rendait 30/100 de confiance sur un dossier dont le resume disait « leader
# incontesté ». **Le detail avait mange la conclusion.** La premiere ligne dit
# maintenant la conclusion ; tout le reste la justifie.
# --------------------------------------------------------------------------- #
# Ce sous-bloc prolonge le bloc D, qui vient de dire « sans objet » deux lignes
# plus haut. Le repeter mot pour mot ferait lire au lecteur la meme phrase deux
# fois d'affilee, ce qui la vide de son sens : sur une matiere premiere, le
# sous-bloc disparait entierement, son titre compris.
# `info_dossier` a ete charge plus haut, pour la vignette de solidite du bloc B.
if not sans_fondamentaux:
    st.markdown("#### Position concurrentielle analysée")

if sans_fondamentaux:
    pass  # le bloc D vient de le dire, quelques lignes plus haut
elif not info_dossier:
    st.info("Aucune analyse. La lancer sur l'écran « Analyses » : un prompt, "
            "une réponse, un import.")
elif not position.est_v2(info_dossier["dossier"]):
    st.warning("Dossier à l'ancien format. Lancer "
               "`python scripts/migre_dossiers_v2.py`.")
else:
    d = info_dossier["dossier"]
    score = position.calcule_le_score(d)

    verdict = position.lire(d, "position", "verdict")
    durabilite = position.lire(d, "durabilite", "verdict")
    rente = position.lire(d, "durabilite", "sources_de_rente", defaut=[]) or []
    annees = position.annees_de_position(d)
    perdue = position.annees_depuis_la_perte(d)

    # --- La phrase qu'on lit en premier -------------------------------------
    tete = [f"position **{position.LIBELLES_POSITION.get(verdict, verdict)}**"]
    if annees is not None:
        tete.append(f"depuis **{position.lire(d, 'position', 'depuis')}** "
                    f"({annees} an{'s' if annees > 1 else ''})")
    if perdue is not None:
        tete.append(f"**perdue en {position.lire(d, 'position', 'perdue_en')}** "
                    f"(il y a {perdue} an{'s' if perdue > 1 else ''})")
    if durabilite:
        tete.append(f"durabilité **{position.LIBELLES_DURABILITE.get(durabilite, durabilite)}**")
    if rente:
        tete.append("rente : " + ", ".join(rente))
    st.markdown(" · ".join(tete))

    resume_texte = position.lire(d, "resume", defaut="")
    if resume_texte:
        st.markdown(resume_texte)

    # --- Le score, avec son bareme ------------------------------------------
    # Un total dont on ne voit pas la construction ne se discute pas, il se
    # subit. Les lignes sont donc affichees a cote, toujours.
    gauche, droite = st.columns([1, 2])
    with gauche:
        st.metric("Solidité concurrentielle", f"{score.total}/100",
                  score.niveau, delta_color="off",
                  help="Calculé ici à partir des verdicts, jamais demandé au "
                       "modèle : deux exécutions du même prompt donneraient "
                       "deux notes différentes.")
    with droite:
        st.dataframe(
            pd.DataFrame([{"Critère": ligne.libelle, "Constat": ligne.detail,
                           "Points": ligne.points} for ligne in score.lignes]),
            use_container_width=True, hide_index=True,
            column_config={"Points": st.column_config.NumberColumn(
                "Points", format="%+d")})
    for reserve in score.reserves:
        st.markdown(f"<div class='avertissement'>{reserve}</div>",
                    unsafe_allow_html=True)

    preuve = position.lire(d, "position", "preuve")
    marche = position.lire(d, "marche")
    if marche or preuve:
        st.caption(
            ((f"**Marché retenu** — {marche} " if marche else "")
             + (f"· **Preuve du rang** — {preuve}" if preuve else "")).strip(" ·"))

    # --- Les menaces, la partie la plus utile du dossier ---------------------
    toutes = position.menaces(d)
    if toutes:
        st.markdown(f"**Menaces ({len(toutes)})** — concurrents et autres, "
                    "classées par danger")
        st.dataframe(
            pd.DataFrame([{
                "Danger": position.LIBELLES_DANGER.get(m.get("danger"), "—"),
                "Menace": m.get("nom"),
                "Nature": m.get("nature") or "—",
                "Type": m.get("type") or "—",
                "Pays": m.get("pays") or "—",
                "En quoi c'est dangereux": m.get("pourquoi_dangereux") or "—",
                "Signal à surveiller": m.get("signal_a_surveiller") or "—",
            } for m in toutes]),
            use_container_width=True, hide_index=True)
        st.markdown(
            "<div class='avertissement'>Une menace <b>faible</b> ne retire aucun "
            "point : compter chaque menace recensée punirait le dossier le plus "
            "complet, alors qu'un concurrent identifié puis jugé peu dangereux "
            "est une information rassurante, pas un risque.</div>",
            unsafe_allow_html=True)

    etat_dossier = (f"**validé** par {info_dossier['analyst']}"
                    if info_dossier["status"] == "validated"
                    else "**brouillon** — non validé, aucun verdict projeté")
    sources_dossier = position.lire(d, "sources", defaut=[]) or []
    st.caption(
        f"Dossier {etat_dossier} · référence "
        f"{position.lire(d, 'date_reference', defaut='—')} · importé le "
        f"{info_dossier['importe_le']} · expire le {info_dossier['expires_at']} · "
        f"{len(sources_dossier)} source(s)")

    if sources_dossier:
        with st.expander(f"Sources ({len(sources_dossier)})"):
            for s in sources_dossier:
                if isinstance(s, dict):
                    titre_source = s.get("titre") or s.get("title") or s.get("url") or "—"
                    url = s.get("url")
                    st.markdown(f"- [{titre_source}]({url})" if url
                                else f"- {titre_source}")
                else:
                    st.markdown(f"- {s}")

    definitions.glossaire(definitions.DOSSIER,
                          "Comment lire la position concurrentielle ?")

    ancien = position.lire(d, "ancien_dossier")
    if ancien:
        with st.expander("Ancien dossier, avant migration"):
            st.caption(
                "Conservé tel quel : la migration n'a rien réécrit. Les niveaux "
                "de danger et les types de menace en proviennent par conversion "
                "— à revoir en relançant le prompt.")
            st.json(ancien, expanded=False)

# --------------------------------------------------------------------------- #
# Bloc E - Dividendes & Rendements potentiels
# --------------------------------------------------------------------------- #
if f["asset_class"] in ("equity", "dividend_stock"):
    st.subheader("E · Dividendes & Rendements potentiels")
    prof = data.profil_dividende(choix, as_of)
    if not prof or not prof.dernier_dpa:
        st.info("Aucun dividende versé par cette société sur la période analysée.")
    else:
        COULEURS_SECU = {
            "sécurisé": "#0ca30c",
            "soutenable": "#fab219",
            "tendu": "#d03b3b",
            "exceptionnel": "#898781",
            "indéterminable": "#898781",
        }
        c_secu = COULEURS_SECU.get(prof.securite_verdict, "#898781")
        st.markdown(
            f"<span class='pastille' style='color:{c_secu}; border-color:{c_secu}'>"
            f"<b>Sécurité du dividende : {prof.securite_verdict.upper()}</b></span> — {prof.securite_motif}",
            unsafe_allow_html=True,
        )

        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.metric(
                "Rendement actuel",
                f"{prof.rendement_actuel_pct:.2f} %" if prof.rendement_actuel_pct else "—",
                help="Dernier dividende annuel rapporté au cours de clôture actuel.",
            )
        with m2:
            st.metric(
                "Rendement moyen 5 ans",
                f"{prof.rendement_moyen_5a_pct:.2f} %" if prof.rendement_moyen_5a_pct else "—",
                help="Moyenne des dividendes des 5 dernières années rapportée au cours actuel (dividende potentiel lissé).",
            )
        with m3:
            st.metric(
                "Rendement sur tendance",
                f"{prof.rendement_sur_tendance_pct:.2f} %" if prof.rendement_sur_tendance_pct else "—",
                help="DPA moyen 5 ans rapporté à la valeur théorique de la droite de régression (rendement hors anomalie de prix).",
            )
        with m4:
            fcf_payout_str = f"{prof.payout_fcf_pct:.0f} %" if prof.payout_fcf_pct is not None else "n/d"
            st.metric(
                "Couverture FCF",
                fcf_payout_str,
                help="Part du Free Cash Flow absorbée par les dividendes. < 65 % = sécurisé, > 100 % = non autofinancé.",
            )

        col_graphe, col_details = st.columns([1.2, 1.0])
        with col_graphe:
            st.caption("Historique des dividendes annuels par action (DPA)")
            if prof.historique_annuel:
                h_df = pd.DataFrame([
                    {"annee": h.annee, "montant_total": h.montant_total, "nb_versements": h.nb_versements}
                    for h in prof.historique_annuel
                ])
                st.altair_chart(charts.graphe_dividendes(h_df, p, f["currency"]), use_container_width=True)

        with col_details:
            st.caption("Indicateurs de distribution & Dynamique")
            lignes_div = [
                {"Métrique": "Dernier DPA annuel", "Valeur": f"{prof.dernier_dpa:.2f} {f['currency']}" if prof.dernier_dpa else "—"},
                {"Métrique": "DPA moyen (3 ans)", "Valeur": f"{prof.dpa_moyen_3a:.2f} {f['currency']}" if prof.dpa_moyen_3a else "—"},
                {"Métrique": "DPA moyen (5 ans)", "Valeur": f"{prof.dpa_moyen_5a:.2f} {f['currency']}" if prof.dpa_moyen_5a else "—"},
                {"Métrique": "Croissance DPA (CAGR 3a)", "Valeur": f"{prof.croissance_dpa_3a_pct:+.1f} %" if prof.croissance_dpa_3a_pct is not None else "—"},
                {"Métrique": "Croissance DPA (CAGR 5a)", "Valeur": f"{prof.croissance_dpa_5a_pct:+.1f} %" if prof.croissance_dpa_5a_pct is not None else "—"},
                {"Métrique": "Années consécutives de versement", "Valeur": f"{prof.annees_consecutives} an(s)"},
                {"Métrique": "Baisses sur les 5 derniers exercices", "Valeur": f"{prof.nb_baisses_5a} fois"},
            ]
            st.dataframe(pd.DataFrame(lignes_div), use_container_width=True, hide_index=True)


# --------------------------------------------------------------------------- #
# Ce que la fiche ne montre plus, et pourquoi
#
# Trois blocs ont ete retires le 2026-08-25, tous pour la meme raison : ils
# repondaient a des questions qu'on ne se pose pas devant un titre.
#
# - **E · Fondamentaux** — vingt ratios en cinq familles, tires du regime A. Un
#   filtre de solvabilite, jamais un jugement de qualite : une entreprise peut
#   cocher les vingt cases et perdre sa position concurrentielle, et c'est cette
#   seconde question que la fiche traite desormais en entier.
#   **Ce qui part avec lui, et qu'il faut savoir :** le verdict de coherence
#   prix/fondamentaux - `confirme` / `suspect` / `indeterminable`, celui qui
#   ecrit « value trap potentiel » - n'est plus affiche nulle part dans le
#   dashboard. Il reste **calcule** (`analytics/ratios.coherence_prix_fondamentaux`)
#   et `data.fondamentaux()` n'a pas bouge : une pastille d'une ligne dans le
#   bandeau de diagnostics le remettrait sous les yeux sans ramener le bloc.
# - **Anomalies qualite ouvertes** — un tableau d'exploitation dans un ecran de
#   decision. Les anomalies bloquantes disqualifient deja la regression, et le
#   motif s'affiche sous le bandeau de diagnostics ; les autres se traitent avec
#   `scripts/anomalies.py`, pas en regardant un cours.
# - **Ce que le modele affirmait, semaine apres semaine** — le principe P5 rendu
#   visible, sur un historique qui compte aujourd'hui un point par titre. Un
#   graphe a un point ne montre rien, et la promesse (« 52 dans un an ») se
#   tenait toute seule dans une legende que personne ne relisait. L'historique
#   continue de s'ecrire dans `regression_fits` — c'est lui qui compte — et
#   `data.historique_des_fits()` avec `charts.graphe_historique_fits()` sont
#   restes en place pour le jour ou il y aura de quoi tracer.
# --------------------------------------------------------------------------- #
