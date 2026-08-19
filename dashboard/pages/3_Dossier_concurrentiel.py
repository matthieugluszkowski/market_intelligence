"""Dossier concurrentiel (doc 04, écran 7 · doc 08 §8).

L'écran qui remplace l'agent autonome. Il ne dialogue avec aucune API : il
**compose** les prompts et **importe** le résultat. Entre les deux, le travail se
fait ailleurs — et surtout, il se relit.

Trois principes d'écran, tous issus d'un défaut constaté à l'usage :

- **Le type de fragment est détecté, pas choisi par défaut.** Une liste
  déroulante posée sur « contrôle qualité » fait traiter la sortie du prompt 3
  comme un dossier normalisé complet, sans que rien ne le signale.
- **Ce qui est importé se voit.** Un tableau d'avancement montre ce que chaque
  étape a apporté. Sans lui, l'analyste colle un JSON, lit un message de succès,
  et n'a aucun moyen de vérifier que la donnée est arrivée.
- **Ce que le LLM a établi revient dans le formulaire.** Sinon les prompts
  suivants repartent de zéro et lui redemandent d'établir ce qu'il a déjà
  établi, avec le risque qu'il réponde autrement.
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

from dashboard import data  # noqa: E402
from dashboard.theme import css, palette  # noqa: E402
from market_intelligence.db import connect_direct  # noqa: E402
from market_intelligence.intelligence import importer, prompts, schema  # noqa: E402

st.set_page_config(page_title="Dossier concurrentiel", page_icon="◧", layout="wide")

sombre = st.sidebar.toggle("Mode sombre", value=False)
p = palette(sombre)
st.markdown(css(p), unsafe_allow_html=True)

univers = data.instruments()
choix = st.sidebar.selectbox(
    "Instrument", univers["internal_code"],
    format_func=lambda c: univers.set_index("internal_code").loc[c, "name"],
)
ligne = univers.set_index("internal_code").loc[choix]


def dossier_courant(code: str) -> dict:
    with connect_direct() as conn, conn.cursor() as cur:
        cur.execute(
            """
            select a.dossier from market_analyses a
              join instruments i on i.id = a.instrument_id
             where i.internal_code = %s
             order by a.reference_date desc, a.imported_at desc limit 1
            """, (code,))
        row = cur.fetchone()
    return row[0] if row else {}


dossier = dossier_courant(choix)

st.title("Dossier concurrentiel")
st.caption(f"{ligne['name']} · {choix}")

st.markdown(
    "<div class='avertissement'>Cet outil <b>compose des prompts</b> et "
    "<b>importe du JSON</b>. Il n'appelle aucune API. L'analyse se fait ailleurs — "
    "ChatGPT, Claude, Perplexity — et se relit avant import. La sélection des "
    "concurrents et l'appréciation stratégique restent manuelles : ce sont des "
    "jugements, pas des requêtes.</div>",
    unsafe_allow_html=True,
)

# --------------------------------------------------------------------------- #
# État du dossier — ce qui a été importé, et ce qui manque
# --------------------------------------------------------------------------- #
st.subheader("État du dossier")

if not dossier:
    st.info("Aucun dossier. Commencer par le prompt 1 ci-dessous.")
else:
    etapes = schema.avancement(dossier)
    colonnes = st.columns(len(etapes))
    for colonne, etape in zip(colonnes, etapes):
        with colonne:
            marque = "●" if etape["fait"] else "○"
            couleur = "#0ca30c" if etape["fait"] else "#898781"
            st.markdown(
                f"<span style='color:{couleur}'>{marque}</span> **{etape['etape']}**<br>"
                f"<span style='color:{p.encre_secondaire};font-size:0.85rem'>"
                f"{etape['apporte']}</span>",
                unsafe_allow_html=True,
            )
            if etape["manque"]:
                st.caption(etape["manque"])

    r = schema.resume(dossier)
    st.caption(
        f"Statut **{r['statut']}** · analyste "
        f"**{r['analyste'] or 'non renseigné'}** · {r['n_sources']} source(s) · "
        f"secteur établi : {r['secteur']}"
    )

    with st.expander("Concurrents retenus"):
        concurrents = schema.lire(dossier, "competitors", defaut=[])
        if concurrents:
            st.dataframe(
                pd.DataFrame([{
                    "Concurrent": schema.lire(c, "company_name"),
                    "Pays": schema.lire(c, "country", defaut="—"),
                    "Type": schema.lire(c, "competition_type", defaut="—"),
                    "Fiche": "oui" if schema.lire(c, "profile_available") else "—",
                    "Statut": schema.lire(c, "status", defaut="—"),
                    "Justification": (schema.lire(c, "relevance_explanation",
                                                  defaut="") or "")[:90],
                } for c in concurrents]),
                use_container_width=True, hide_index=True,
            )
            st.caption(
                "**C'est la liste à vérifier avant de lancer le prompt 2.** Un "
                "concurrent mal choisi coûte plus cher analysé que non analysé."
            )
        else:
            st.write("Aucun concurrent.")

    with st.expander("Dossier brut (JSON)"):
        st.json(dossier, expanded=False)

# --------------------------------------------------------------------------- #
# 1 · Les variables
# --------------------------------------------------------------------------- #
st.subheader("1 · Variables du titre")

st.caption(
    "**Rien n'est obligatoire ici** : le titre est déjà choisi dans la barre "
    "latérale. Secteur, sous-secteur, marché, produit et clients cibles sont "
    "**établis par le LLM** au prompt 1 — ils font partie du résultat de "
    "l'analyse, pas de ses données d'entrée. Les champs se remplissent seuls "
    "après l'import du premier JSON."
)

# Le dossier fait autorite sur la saisie : ce que le LLM a etabli revient ici.
etabli = schema.variables_depuis_dossier(dossier) if dossier else {}
memoire = st.session_state.get(f"variables::{choix}", {})


def defaut(nom: str, secours: str = "") -> str:
    return etabli.get(nom) or memoire.get(nom) or secours


A_ETABLIR = "laisser vide : le LLM l'établit"

g, d = st.columns(2)
with g:
    entreprise = st.text_input("Entreprise analysée", defaut("ENTREPRISE_ANALYSEE",
                                                             ligne["name"]))
    secteur = st.text_input("Secteur d'activité", defaut("SECTEUR_ACTIVITE"),
                            placeholder=A_ETABLIR)
    sous_secteur = st.text_input("Sous-secteur", defaut("SOUS_SECTEUR"),
                                 placeholder=A_ETABLIR)
    zone = st.text_input("Pays et zone géographique", defaut(
        "PAYS_ET_ZONE_GEOGRAPHIQUE",
        "Monde, avec priorité à l'Europe et aux États-Unis"))
    marche = st.text_input("Marché cible", defaut("MARCHE_CIBLE"),
                           placeholder=A_ETABLIR)
    produit = st.text_input("Produit ou service", defaut("PRODUIT_OU_SERVICE"),
                            placeholder=A_ETABLIR)
with d:
    clients = st.text_input("Clients cibles", defaut("CLIENTS_CIBLES"),
                            placeholder=A_ETABLIR)
    connus = st.text_area("Concurrents connus", defaut("CONCURRENTS_CONNUS"),
                          height=68,
                          help="Se remplit avec les concurrents du dossier après "
                               "l'import du prompt 1.")
    reference = st.date_input("Date de référence", value=date.today())
    objectif = st.text_input("Objectif de l'analyse", defaut(
        "OBJECTIF_DE_L_ANALYSE",
        "Évaluer la position concurrentielle et sa durabilité pour une décision "
        "d'investissement"))
    internes = st.text_area("Informations internes", defaut("INFORMATIONS_INTERNES"),
                            height=68)

variables = {
    "ENTREPRISE_ANALYSEE": entreprise, "SECTEUR_ACTIVITE": secteur,
    "SOUS_SECTEUR": sous_secteur, "PAYS_ET_ZONE_GEOGRAPHIQUE": zone,
    "MARCHE_CIBLE": marche, "PRODUIT_OU_SERVICE": produit,
    "CLIENTS_CIBLES": clients, "CONCURRENTS_CONNUS": connus,
    "DATE_DE_REFERENCE": reference.isoformat(),
    "OBJECTIF_DE_L_ANALYSE": objectif, "INFORMATIONS_INTERNES": internes,
}
st.session_state[f"variables::{choix}"] = variables

# --------------------------------------------------------------------------- #
# 2 · Les prompts
# --------------------------------------------------------------------------- #
st.subheader("2 · Prompts à copier")

candidats = schema.noms_concurrents(dossier) if dossier else []
if candidats:
    # Le concurrent se choisit dans la liste importee : le retaper a la main
    # ouvre la porte a une variante orthographique, et la fiche ne se rattacherait
    # alors a aucun concurrent connu.
    restants = [n for n in candidats
                if n.lower() not in {
                    (schema.lire(pr, "company_name") or "").lower()
                    for pr in schema.lire(dossier, "company_profiles", defaut=[])}]
    concurrent_courant = st.selectbox(
        "Concurrent à analyser (prompt 2)", candidats,
        index=candidats.index(restants[0]) if restants else 0,
        format_func=lambda n: n + ("" if n in restants else "   (fiche déjà importée)"),
        help="Liste issue du prompt 1. Le prompt 2 s'utilise **un concurrent à "
             "la fois**, jamais en lot.",
    )
    if restants:
        st.caption(f"{len(restants)} concurrent(s) sans fiche : "
                   + ", ".join(restants[:8]))
else:
    concurrent_courant = st.text_input(
        "Concurrent à analyser (prompt 2)", "",
        help="La liste se remplira automatiquement après l'import du prompt 1.")
variables["CONCURRENT"] = concurrent_courant

onglets = st.tabs([prompts.PROMPTS[c][0] for c in prompts.PROMPTS])
for onglet, cle in zip(onglets, prompts.PROMPTS):
    with onglet:
        titre, _texte, explication = prompts.PROMPTS[cle]
        st.caption(explication)

        if cle == "concurrent" and not (concurrent_courant or "").strip():
            st.warning("Aucun concurrent disponible : importer d'abord le prompt 1.")
        if cle == "controle":
            st.caption("Coller les trois analyses précédentes dans le prompt, "
                       "aux emplacements indiqués.")

        manquantes = prompts.variables_manquantes(cle, variables)
        if manquantes:
            st.caption("Variables requises non renseignées : " + ", ".join(manquantes))

        texte = prompts.compose(cle, variables)
        st.code(texte, language="text")
        st.download_button(
            "Télécharger", texte.encode("utf-8"),
            file_name=f"prompt_{cle}_{choix.replace(':', '_')}.txt",
            mime="text/plain", key=f"dl_{cle}",
        )

# --------------------------------------------------------------------------- #
# 3 · Import
# --------------------------------------------------------------------------- #
st.subheader("3 · Import du JSON")

st.caption(
    "Chaque prompt rend un JSON de forme différente : le dossier se construit "
    "**par accumulation**. On repart du dernier dossier connu et on y ajoute — "
    "jamais d'écrasement, sinon l'ordre d'import deviendrait une variable cachée "
    "du résultat."
)

brut = st.text_area("Coller le JSON ici", height=200,
                    placeholder='{"market_definition": {...}, "proposed_competitors": [...]}')

fragment = None
detecte, raison = None, ""
if brut.strip():
    try:
        fragment = json.loads(brut)
        detecte, raison = schema.detecte_fragment(fragment)
    except json.JSONDecodeError as exc:
        st.error(f"JSON invalide : {exc}")

col_type, col_analyste = st.columns([1.3, 1])
with col_type:
    ordre = list(schema.FRAGMENTS)
    type_fragment = st.selectbox(
        "Sortie de quel prompt ?", ordre,
        index=ordre.index(detecte) if detecte else 0,
        format_func=lambda c: schema.FRAGMENTS[c],
        help="Détecté automatiquement d'après les clés du JSON. À corriger "
             "seulement si la détection se trompe.",
    )
with col_analyste:
    analyste = st.text_input(
        "Nom de l'analyste", "",
        disabled=type_fragment != "controle",
        help="Obligatoire pour valider, et actif uniquement sur le dossier "
             "normalisé du prompt 4.",
    )

if detecte:
    if detecte == type_fragment:
        st.caption(f"Détecté : **{schema.FRAGMENTS[detecte]}** — {raison}.")
    else:
        st.warning(
            f"La détection donne **{schema.FRAGMENTS[detecte]}** ({raison}), "
            f"mais **{schema.FRAGMENTS[type_fragment]}** est sélectionné. "
            f"Traiter un fragment partiel comme un dossier normalisé qualifierait "
            f"le titre avant la fin de l'analyse."
        )
elif fragment is not None:
    st.warning("Type non reconnu : aucune clé caractéristique. Vérifier le JSON "
               "ou choisir le type à la main.")

gauche, _ = st.columns([1, 3])
with gauche:
    verifier = st.button("Vérifier", use_container_width=True)
    lancer = st.button("Importer", type="primary", use_container_width=True)

if (verifier or lancer) and fragment is None:
    st.error("Aucun JSON exploitable.")
elif verifier or lancer:
    apercu = schema.fusionne(dossier or {}, fragment, type_fragment)
    validation = schema.valide(apercu)

    v = st.columns(5)
    v[0].metric("Concurrents", validation.concurrents)
    v[1].metric("Hors Europe", validation.concurrents_hors_europe)
    v[2].metric("Fonctions", validation.fonctions)
    v[3].metric("Sources", validation.sources)
    v[4].metric("Bloquants", len(validation.bloquants))

    if validation.problemes:
        st.dataframe(
            pd.DataFrame([{
                "Niveau": pb.niveau, "Élément": pb.element,
                "Problème": pb.explication, "Correction": pb.correction,
            } for pb in validation.problemes]),
            use_container_width=True, hide_index=True,
        )

    if not validation.groupe_complet:
        st.markdown(
            "<div class='avertissement'><b>Aucun concurrent hors Europe.</b> Les "
            "menaces réelles viennent presque toujours de l'extérieur de "
            "l'univers. Le titre restera plafonné à <code>watch</code>. Vérifier "
            "que le code pays sur deux lettres est renseigné pour chaque "
            "concurrent.</div>", unsafe_allow_html=True)

    if verifier:
        if validation.importable:
            st.success("Aucun bloquant : intégrable.")
        elif type_fragment == "controle":
            st.error(f"{len(validation.bloquants)} bloquant(s) : import refusé.")
        else:
            st.info(f"Dossier encore incomplet ({len(validation.bloquants)} "
                    f"manque(s)) — normal tant que les quatre étapes ne sont pas "
                    f"faites. Le fragment reste intégrable.")

    if lancer and (validation.importable or type_fragment != "controle"):
        with connect_direct() as conn, conn.cursor() as cur:
            cur.execute("select id, sector_code from instruments "
                        "where internal_code = %s", (choix,))
            instrument_id, sector_code = cur.fetchone()
            resultat = importer.importe(cur, instrument_id, choix, sector_code,
                                        fragment, analyste, type_fragment)
            conn.commit()

        if resultat.type_fragment != "controle":
            st.success(f"« {schema.FRAGMENTS[resultat.type_fragment]} » intégré. "
                       f"Le dossier compte {resultat.validation.concurrents} "
                       f"concurrent(s) et {resultat.validation.sources} source(s).")
        elif resultat.projete:
            st.success(
                f"Dossier validé par {analyste}. "
                f"{resultat.concurrents_internes} pair(s) de l'univers, "
                f"{resultat.concurrents_externes} hors univers. Relancer "
                f"`python scripts/compute_quality.py --recalculer`.")
        else:
            st.warning("Dossier enregistré, sans projection.")
        for message in resultat.messages:
            st.markdown(f"<div class='avertissement'>{message}</div>",
                        unsafe_allow_html=True)
        st.rerun()
    elif lancer:
        st.error(f"{len(validation.bloquants)} bloquant(s) : import refusé. Le "
                 f"dossier n'est jamais complété automatiquement.")
