"""Analyses — la position concurrentielle d'un titre (doc 04, écran 7 · doc 08 §8).

L'écran ne dialogue avec aucune API : il **compose** un prompt et **importe** le
résultat. Entre les deux, le travail se fait ailleurs — et surtout, il se relit.

Un seul prompt, et c'est le sujet
----------------------------------
La version précédente en enchaînait cinq, pour 34 000 caractères de consignes et
un dossier de vingt-deux blocs. Elle a rendu **30/100 de confiance et un refus
de conclure** sur EssilorLuxottica, dont le résumé disait pourtant « leader
incontesté » : le détail avait mangé la conclusion. Et à cinq copier-coller par
titre, on ne lançait l'analyse presque jamais.

Quatre questions restent, parce qu'elles seules changent la décision :

1. L'entreprise est-elle leader de son marché ?
2. Depuis quand — et si elle l'a perdu, depuis quand ?
3. Qui sont ses concurrents, et **en quoi chacun est une menace** ?
4. Quelles autres menaces pèsent sur elle, et en quoi c'est dangereux ?

**Aucune note n'est demandée au modèle.** Il rend des verdicts ; le score se
calcule dans `intelligence.position`, par un barème affiché à côté du résultat.
Un total dont on ne voit pas la construction ne se discute pas, il se subit.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# Rechargement des modules du projet si leurs sources ont change. **Doit rester
# avant les imports qui suivent** : Streamlit garde les modules importes en cache
# et une purge posterieure laisserait coexister deux versions d une meme classe.
from dashboard.rechargement import recharge_si_modifie  # noqa: E402

recharge_si_modifie()

from dashboard import data, entete  # noqa: E402
from dashboard.theme import css, palette  # noqa: E402
from market_intelligence.db import connect_direct  # noqa: E402
from market_intelligence.intelligence import importer, position, prompts  # noqa: E402

st.set_page_config(page_title="Analyses", page_icon="◧", layout="wide")

sombre = st.sidebar.toggle("Mode sombre", value=False)
p = palette(sombre)
st.markdown(css(p), unsafe_allow_html=True)

univers = data.instruments()
index_univers = univers.set_index("internal_code")
codes = list(univers["internal_code"])

# L'univers est trie par nom : « 2G Energy AG » y arrive en tete et n'a aucune
# raison d'etre le titre qu'on vient analyser. Le defaut va au premier titre
# **deja analyse** - c'est celui qu'on revient relire - et les autres portent la
# mention dans la liste.
analyses = data.codes_analyses()
defaut = next((i for i, c in enumerate(codes) if c in analyses), 0)
choix = st.sidebar.selectbox(
    "Instrument", codes, index=defaut,
    format_func=lambda c: (f"{index_univers.loc[c, 'name']}"
                           + ("" if c in analyses else " · jamais analysé")),
)
ligne = index_univers.loc[choix]

entete.bandeau_portefeuille(data.portefeuille())

st.title("Analyses")
st.caption(f"{ligne['name']} · {choix} — qui est leader, depuis quand, "
           f"qui le menace et en quoi c'est dangereux.")

st.markdown(
    "<div class='avertissement'>Cet outil <b>compose un prompt</b> et "
    "<b>importe</b> sa réponse. Il n'appelle aucune API et ne décide rien : "
    "le texte produit est une analyse à relire, pas un verdict à appliquer.</div>",
    unsafe_allow_html=True)

info = data.dossier_concurrentiel(choix)
dossier_actuel = info.get("dossier") if info else None
if dossier_actuel and not position.est_v2(dossier_actuel):
    st.warning("Le dossier en base est à l'ancien format. Lancer "
               "`python scripts/migre_dossiers_v2.py` avant de continuer.")
    dossier_actuel = None


def entete_dossier(d: dict) -> str:
    """La phrase qu'on lit en premier : position, ancienneté, durabilité, rente."""
    verdict = position.lire(d, "position", "verdict")
    morceaux = [f"position **{position.LIBELLES_POSITION.get(verdict, verdict or '—')}**"]
    annees = position.annees_de_position(d)
    if annees is not None:
        morceaux.append(f"depuis **{position.lire(d, 'position', 'depuis')}** "
                        f"({annees} an{'s' if annees > 1 else ''})")
    perdue = position.annees_depuis_la_perte(d)
    if perdue is not None:
        morceaux.append(f"**perdue en {position.lire(d, 'position', 'perdue_en')}**")
    durabilite = position.lire(d, "durabilite", "verdict")
    if durabilite:
        morceaux.append(
            f"durabilité **{position.LIBELLES_DURABILITE.get(durabilite, durabilite)}**")
    rente = position.lire(d, "durabilite", "sources_de_rente", defaut=[]) or []
    if rente:
        morceaux.append("rente : " + ", ".join(rente))
    return " · ".join(morceaux)


def tableau_du_bareme(score: position.Score) -> None:
    gauche, droite = st.columns([1, 2])
    with gauche:
        st.metric("Solidité concurrentielle", f"{score.total}/100", score.niveau,
                  delta_color="off")
    with droite:
        st.dataframe(
            pd.DataFrame([{"Critère": l.libelle, "Constat": l.detail,
                           "Points": l.points} for l in score.lignes]),
            use_container_width=True, hide_index=True,
            column_config={"Points": st.column_config.NumberColumn(
                "Points", format="%+d")})
    for reserve in score.reserves:
        st.markdown(f"<div class='avertissement'>{reserve}</div>",
                    unsafe_allow_html=True)


onglet_etat, onglet_prompt, onglet_import = st.tabs(
    ["Ce qui est en base", "Le prompt", "Importer la réponse"])

# --------------------------------------------------------------------------- #
# Ce qui est en base — et ce qu'il y manque
#
# La saisie à la main est réduite à ce qu'aucun prompt ne peut fournir de façon
# fiable : l'année d'accession. Les dossiers migrés de l'ancien format ne la
# portent pas — c'est précisément la question que l'ancien dispositif ne posait
# pas, et elle vaut jusqu'à vingt points du score.
# --------------------------------------------------------------------------- #
with onglet_etat:
    if not dossier_actuel:
        st.info("Aucune analyse pour ce titre. Passer à l'onglet **Le prompt**.")
    else:
        st.markdown(entete_dossier(dossier_actuel))
        resume = position.lire(dossier_actuel, "resume", defaut="")
        if resume:
            st.markdown(resume)
        tableau_du_bareme(position.calcule_le_score(dossier_actuel))

        etat = (f"**validé** par {info['analyst']}"
                if info["status"] == "validated" else "**brouillon**")
        st.caption(f"Dossier {etat} · importé le {info['importe_le']} · "
                   f"expire le {info['expires_at']}")

        toutes = position.menaces(dossier_actuel)
        if toutes:
            st.markdown(f"**Menaces ({len(toutes)})**")
            st.dataframe(
                pd.DataFrame([{
                    "Danger": position.LIBELLES_DANGER.get(m.get("danger"), "—"),
                    "Menace": m.get("nom"),
                    "Nature": m.get("nature") or "—",
                    "Type": m.get("type") or "—",
                    "En quoi c'est dangereux": m.get("pourquoi_dangereux") or "—",
                } for m in toutes]),
                use_container_width=True, hide_index=True)

        # --- Compléter à la main -------------------------------------------
        st.subheader("Compléter à la main")
        st.caption("Seulement ce qu'aucun prompt ne fournit de façon fiable. "
                   "Tout le reste vient du modèle et se corrige en relançant.")

        with st.form("complete"):
            verdict_actuel = position.lire(dossier_actuel, "position", "verdict")
            depuis_actuel = position.lire(dossier_actuel, "position", "depuis")
            perdue_actuel = position.lire(dossier_actuel, "position", "perdue_en")
            durabilite_actuelle = position.lire(dossier_actuel, "durabilite",
                                                "verdict")

            g, m, d = st.columns(3)
            options_position = ["(non posé)", *position.POSITIONS]
            nouveau_verdict = g.selectbox(
                "Position", options_position,
                index=(options_position.index(verdict_actuel)
                       if verdict_actuel in options_position else 0),
                format_func=lambda v: position.LIBELLES_POSITION.get(v, v))
            nouvelle_annee = m.number_input(
                "Depuis (année d'accession)", min_value=1800, max_value=2100,
                value=int(depuis_actuel) if isinstance(depuis_actuel, int) else 2000,
                step=1,
                help="« Leader » sans « depuis quand » ne dit pas si la position "
                     "est établie ou fraîche. Vaut jusqu'à 20 points du score.")
            annee_connue = d.checkbox("Année connue",
                                      value=isinstance(depuis_actuel, int))

            g2, m2, d2 = st.columns(3)
            options_durabilite = ["(non posé)", *position.DURABILITES]
            nouvelle_durabilite = g2.selectbox(
                "Durabilité", options_durabilite,
                index=(options_durabilite.index(durabilite_actuelle)
                       if durabilite_actuelle in options_durabilite else 0),
                format_func=lambda v: position.LIBELLES_DURABILITE.get(v, v))
            annee_perte = m2.number_input(
                "Position perdue en", min_value=1800, max_value=2100,
                value=int(perdue_actuel) if isinstance(perdue_actuel, int) else 2020,
                step=1)
            perte_connue = d2.checkbox("Position perdue",
                                       value=isinstance(perdue_actuel, int))

            analyste_complet = st.text_input(
                "Votre nom", value=info.get("analyst") or "",
                help="Une correction à la main est une décision : elle porte un "
                     "nom, comme la validation.")

            if st.form_submit_button("Enregistrer", type="primary"):
                if not analyste_complet.strip():
                    st.error("Le nom est obligatoire : une saisie à la main est "
                             "une décision, elle ne s'anonymise pas.")
                else:
                    modifie = json.loads(json.dumps(dossier_actuel,
                                                    ensure_ascii=False))
                    modifie.setdefault("position", {})
                    if nouveau_verdict != "(non posé)":
                        modifie["position"]["verdict"] = nouveau_verdict
                    modifie["position"]["depuis"] = (
                        int(nouvelle_annee) if annee_connue else None)
                    modifie["position"]["perdue_en"] = (
                        int(annee_perte) if perte_connue else None)
                    modifie.setdefault("durabilite", {})
                    if nouvelle_durabilite != "(non posé)":
                        modifie["durabilite"]["verdict"] = nouvelle_durabilite
                    try:
                        with connect_direct() as conn, conn.cursor() as cur:
                            resultat = importer.importe(
                                cur, int(ligne["id"]), choix,
                                ligne.get("sector_code"), modifie,
                                analyste_complet.strip())
                            conn.commit()
                        if resultat.validation.importable:
                            st.success(
                                f"Enregistré — score "
                                f"{resultat.score.total}/100.")
                            st.rerun()
                        else:
                            for probleme in resultat.validation.bloquants:
                                st.error(f"{probleme.element} — "
                                         f"{probleme.explication}")
                    except Exception as exc:  # noqa: BLE001
                        st.error(str(exc))

        ancien = position.lire(dossier_actuel, "ancien_dossier")
        if ancien:
            with st.expander("Ancien dossier, avant migration"):
                st.caption(
                    "Conservé tel quel : la migration n'a rien réécrit. Les "
                    "niveaux de danger proviennent d'une conversion prudente — "
                    "relancer le prompt donne un jugement à jour.")
                st.json(ancien, expanded=False)

# --------------------------------------------------------------------------- #
# Le prompt — un seul, à copier tel quel
# --------------------------------------------------------------------------- #
with onglet_prompt:
    titre, _texte, aide = prompts.PROMPTS["position"]
    st.markdown(f"**{titre}** — {aide}")

    with st.expander("Indications facultatives à donner au modèle"):
        st.caption("Le modèle doit établir lui-même le périmètre du marché : "
                   "le fixer d'avance revient à décider où s'arrête la "
                   "concurrence avant d'avoir regardé. Ces champs sont des "
                   "pistes, que le modèle peut contredire en l'expliquant.")
        marche = st.text_input("Marché, si vous avez une idée",
                               key="marche_cible")
        concurrents_connus = st.text_input("Concurrents déjà identifiés",
                                           key="concurrents_connus")
        contexte = st.text_area("Contexte complémentaire", height=80,
                                key="contexte")

    variables = {
        "ENTREPRISE_ANALYSEE": ligne["name"],
        "PAYS_ET_ZONE_GEOGRAPHIQUE": f"{choix.split(':')[1]} / zone euro",
        "DATE_DE_REFERENCE": date.today().isoformat(),
        "MARCHE_CIBLE": st.session_state.get("marche_cible", ""),
        "CONCURRENTS_CONNUS": st.session_state.get("concurrents_connus", ""),
        "INFORMATIONS_INTERNES": st.session_state.get("contexte", ""),
    }
    manquantes = prompts.variables_manquantes("position", variables)
    if manquantes:
        st.error("Variables requises non renseignées : " + ", ".join(manquantes))

    st.code(prompts.compose("position", variables), language="markdown")
    st.caption("Copier ce texte dans ChatGPT, Claude ou Perplexity, puis coller "
               "la réponse JSON dans l'onglet **Importer la réponse**.")

# --------------------------------------------------------------------------- #
# Importer la réponse
# --------------------------------------------------------------------------- #
with onglet_import:
    brut = st.text_area("Réponse JSON du modèle", height=280,
                        placeholder='{"version": 2, "entreprise": "…", …}')

    fragment = None
    if brut.strip():
        try:
            fragment = json.loads(brut)
        except json.JSONDecodeError as exc:
            st.error(f"JSON invalide : {exc}")

    if fragment is not None:
        validation = position.valide(fragment)
        score = position.calcule_le_score(fragment)

        st.markdown("**Ce qui serait importé**")
        st.markdown(entete_dossier(fragment))
        tableau_du_bareme(score)

        toutes = position.menaces(fragment)
        if toutes:
            st.dataframe(
                pd.DataFrame([{
                    "Danger": position.LIBELLES_DANGER.get(m.get("danger"), "—"),
                    "Menace": m.get("nom"),
                    "Nature": m.get("nature") or "—",
                    "Type": m.get("type") or "—",
                    "En quoi c'est dangereux": m.get("pourquoi_dangereux") or "—",
                } for m in toutes]),
                use_container_width=True, hide_index=True)

        for probleme in validation.problemes:
            afficher = st.error if probleme.niveau == "BLOQUANT" else st.warning
            afficher(f"**{probleme.niveau}** · {probleme.element} — "
                     f"{probleme.explication}")

        # Le nom de l'analyste commande la projection, et c'est le seul verrou
        # de l'écran : sans lui, rien ne distingue un dossier relu d'un dossier
        # produit, et le titre ne doit pas être qualifié sur cette base.
        analyste = st.text_input(
            "Votre nom — pour valider et projeter",
            help="Sans nom, le dossier est conservé en brouillon : ni groupe de "
                 "pairs, ni évaluation qualitative, et le titre reste non "
                 "qualifié.")

        if st.button("Importer", type="primary",
                     disabled=not validation.importable):
            try:
                with connect_direct() as conn, conn.cursor() as cur:
                    resultat = importer.importe(
                        cur, int(ligne["id"]), choix, ligne.get("sector_code"),
                        fragment, analyste.strip() or None)
                    conn.commit()
                st.success(
                    f"Importé — score {resultat.score.total}/100, "
                    f"{resultat.concurrents_internes} concurrent(s) dans "
                    f"l'univers, {resultat.concurrents_externes} hors univers."
                    + (" Groupe de pairs et évaluation qualitative projetés."
                       if resultat.projete else ""))
                for message in resultat.messages:
                    st.info(message)
            except Exception as exc:  # noqa: BLE001
                st.error(str(exc))
