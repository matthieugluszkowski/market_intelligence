"""Dossier concurrentiel (doc 04, écran 7 · doc 08 §8).

L'écran qui remplace l'agent autonome. Il ne dialogue avec aucune API : il
**compose** les prompts et **importe** le résultat. Entre les deux, le travail se
fait ailleurs — et surtout, il se relit.

L'étape 3 du flux, la vérification manuelle de la liste des concurrents, est
présentée comme une étape à part entière et non comme un champ à corriger au
passage : c'est la décision la plus lourde de toute la jambe qualité.
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

with st.expander("Le flux en sept étapes", expanded=False):
    st.markdown("""
| # | Étape | Qui |
|---|---|---|
| 1 | Choisir le titre — secteur, sous-secteur, produit et clients sont **établis par le LLM** | outil |
| 2 | Prompt 1 — cadrage et analyse fonctionnelle | LLM |
| 3 | **Vérifier ou corriger la liste des concurrents** | **vous** ← l'étape qui décide |
| 4 | Prompt 2 — analyse détaillée, un concurrent à la fois | LLM |
| 5 | Prompt 3 — leaders et perspectives | LLM |
| 6 | Prompt 4 — contrôle qualité, sortie JSON | LLM |
| 7 | Relire, puis importer le JSON | **vous** |

L'étape 3 s'intercale délibérément entre le cadrage et l'analyse détaillée :
analyser en profondeur un concurrent mal choisi coûte plus cher que de ne pas
l'analyser.
""")

# --------------------------------------------------------------------------- #
# 1 · Les variables
# --------------------------------------------------------------------------- #
st.subheader("1 · Variables du titre")

st.caption(
    "**Rien n'est obligatoire ici** : le titre est déjà choisi dans la barre "
    "latérale. Secteur, sous-secteur, marché, produit et clients cibles sont "
    "**établis par le LLM** au prompt 1 — ils font partie du résultat de "
    "l'analyse, pas de ses données d'entrée. Les remplir revient à imposer une "
    "réponse à une question qui fait partie du travail ; à n'utiliser que pour "
    "orienter, le prompt demandant alors au LLM de contredire l'indication si "
    "ses sources le justifient."
)

cle_etat = f"variables::{choix}"
defauts = st.session_state.get(cle_etat, {})
A_ETABLIR = "laisser vide : le LLM l'établit"

g, d = st.columns(2)
with g:
    entreprise = st.text_input("Entreprise analysée", defauts.get(
        "ENTREPRISE_ANALYSEE", ligne["name"]))
    secteur = st.text_input("Secteur d'activité", defauts.get("SECTEUR_ACTIVITE", ""),
                            placeholder=A_ETABLIR)
    sous_secteur = st.text_input("Sous-secteur", defauts.get("SOUS_SECTEUR", ""),
                                 placeholder=A_ETABLIR)
    zone = st.text_input("Pays et zone géographique", defauts.get(
        "PAYS_ET_ZONE_GEOGRAPHIQUE", "Monde, avec priorité à l'Europe et aux États-Unis"))
    marche = st.text_input("Marché cible", defauts.get("MARCHE_CIBLE", ""),
                           placeholder=A_ETABLIR)
    produit = st.text_input("Produit ou service", defauts.get("PRODUIT_OU_SERVICE", ""),
                            placeholder=A_ETABLIR)
with d:
    clients = st.text_input("Clients cibles", defauts.get("CLIENTS_CIBLES", ""),
                            placeholder=A_ETABLIR)
    connus = st.text_area("Concurrents connus", defauts.get("CONCURRENTS_CONNUS", ""),
                          height=68,
                          help="Séparés par des virgules. Sert d'amorce au prompt 1 ; "
                               "la liste définitive se décide à l'étape 3.")
    reference = st.date_input("Date de référence", value=date.today())
    objectif = st.text_input("Objectif de l'analyse", defauts.get(
        "OBJECTIF_DE_L_ANALYSE",
        "Évaluer la position concurrentielle et sa durabilité pour une décision d'investissement"))
    internes = st.text_area("Informations internes", defauts.get(
        "INFORMATIONS_INTERNES", ""), height=68)

variables = {
    "ENTREPRISE_ANALYSEE": entreprise, "SECTEUR_ACTIVITE": secteur,
    "SOUS_SECTEUR": sous_secteur, "PAYS_ET_ZONE_GEOGRAPHIQUE": zone,
    "MARCHE_CIBLE": marche, "PRODUIT_OU_SERVICE": produit,
    "CLIENTS_CIBLES": clients, "CONCURRENTS_CONNUS": connus,
    "DATE_DE_REFERENCE": reference.isoformat(),
    "OBJECTIF_DE_L_ANALYSE": objectif, "INFORMATIONS_INTERNES": internes,
}
st.session_state[cle_etat] = variables

# --------------------------------------------------------------------------- #
# 2 · Les prompts
# --------------------------------------------------------------------------- #
st.subheader("2 · Prompts à copier")

concurrent_courant = st.text_input(
    "Concurrent à analyser (prompt 2)", "",
    help="Le prompt 2 s'utilise **un concurrent à la fois**, jamais en lot : "
         "une fiche par concurrent, homogène et relue.",
)
variables["CONCURRENT"] = concurrent_courant

onglets = st.tabs([prompts.PROMPTS[c][0] for c in prompts.PROMPTS])
for onglet, cle in zip(onglets, prompts.PROMPTS):
    with onglet:
        titre, _texte, explication = prompts.PROMPTS[cle]
        st.caption(explication)

        if cle == "concurrent" and not concurrent_courant.strip():
            st.warning("Renseigner le concurrent à analyser ci-dessus.")
        if cle == "controle":
            st.caption("Coller les trois analyses précédentes dans le prompt, "
                       "aux emplacements indiqués.")

        manquantes = prompts.variables_manquantes(cle, variables)
        if manquantes:
            st.caption("Variables non renseignées, visibles en clair dans le "
                       "prompt : " + ", ".join(manquantes))

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
    "**par accumulation**. On repart du dernier dossier connu pour ce titre et on "
    "y ajoute — jamais d'écrasement, sinon l'ordre d'import deviendrait une "
    "variable cachée du résultat."
)

col_type, col_analyste = st.columns([1.2, 1])
with col_type:
    type_fragment = st.selectbox(
        "Sortie de quel prompt ?", list(schema.FRAGMENTS),
        index=len(schema.FRAGMENTS) - 1,
        format_func=lambda c: schema.FRAGMENTS[c],
        help="Seule la sortie du prompt 4 est un dossier normalisé complet : "
             "c'est la seule qui qualifie un titre. Les trois autres "
             "enrichissent un brouillon.",
    )
with col_analyste:
    analyste = st.text_input(
        "Nom de l'analyste", "",
        disabled=type_fragment != "controle",
        help="Obligatoire pour valider, et actif uniquement sur le dossier "
             "normalisé du prompt 4. C'est ce geste — et lui seul — qui "
             "distingue un dossier relu d'un dossier produit.",
    )

if type_fragment != "controle":
    st.caption(
        f"« {schema.FRAGMENTS[type_fragment]} » sera intégré au brouillon. "
        f"Aucune projection : qualifier un titre sur un dossier partiel "
        f"reviendrait à conclure avant d'avoir fini de regarder."
    )

brut = st.text_area(f"JSON — {schema.FRAGMENTS[type_fragment]}", height=220,
                    placeholder='{"scoping": {...}, "proposed_competitors": [...]}')

colonne_g, colonne_d = st.columns([1, 3])
with colonne_g:
    verifier = st.button("Vérifier", use_container_width=True)
    importer_ = st.button("Importer", type="primary", use_container_width=True)

if (verifier or importer_) and not brut.strip():
    st.error("Aucun JSON fourni.")
elif verifier or importer_:
    try:
        dossier = json.loads(brut)
    except json.JSONDecodeError as exc:
        st.error(f"JSON invalide : {exc}")
        dossier = None

    if dossier is not None:
        # Un fragment intermediaire est valide apres fusion avec le brouillon
        # existant : le juger seul le declarerait incomplet a tort.
        apercu = dossier
        if type_fragment != "controle":
            with connect_direct() as conn, conn.cursor() as cur:
                cur.execute(
                    """
                    select a.dossier from market_analyses a
                      join instruments i on i.id = a.instrument_id
                     where i.internal_code = %s
                     order by a.reference_date desc, a.imported_at desc limit 1
                    """, (choix,))
                ligne = cur.fetchone()
            apercu = schema.fusionne(ligne[0] if ligne else {}, dossier,
                                     type_fragment)
        validation = schema.valide(apercu)
        resume = schema.resume(apercu)

        v = st.columns(5)
        v[0].metric("Concurrents", validation.concurrents)
        v[1].metric("Hors Europe", validation.concurrents_hors_europe)
        v[2].metric("Fonctions", validation.fonctions)
        v[3].metric("Sources", validation.sources)
        v[4].metric("Bloquants", len(validation.bloquants))

        if validation.problemes:
            st.dataframe(
                pd.DataFrame([{
                    "Niveau": p.niveau, "Élément": p.element,
                    "Problème": p.explication, "Correction": p.correction,
                } for p in validation.problemes]),
                use_container_width=True, hide_index=True,
            )

        if not validation.groupe_complet:
            st.markdown(
                "<div class='avertissement'><b>Aucun concurrent hors Europe.</b> "
                "Les menaces réelles viennent presque toujours de l'extérieur de "
                "l'univers — SharkNinja est américaine, BYD est chinoise, Revolut "
                "n'est pas cotée. Le titre restera plafonné à <code>watch</code>. "
                "Vérifier que le code pays sur deux lettres est bien renseigné "
                "pour chaque concurrent.</div>",
                unsafe_allow_html=True,
            )

        if not validation.importable and type_fragment == "controle":
            st.error(
                f"{len(validation.bloquants)} problème(s) bloquant(s) : import "
                f"refusé. Le dossier n'est jamais complété automatiquement — "
                f"corriger et relancer le prompt 4."
            )
        elif not validation.importable:
            st.info(
                f"Le dossier reste incomplet après ce fragment "
                f"({len(validation.bloquants)} manque(s)) — c'est normal tant "
                f"que les quatre étapes ne sont pas faites. Le fragment est "
                f"intégrable au brouillon."
            )
            if verifier:
                st.json(resume)
        elif verifier:
            st.success("Aucun bloquant. Le dossier est importable.")
            st.json(resume)
        if importer_ and (validation.importable or type_fragment != "controle"):
            with connect_direct() as conn, conn.cursor() as cur:
                cur.execute(
                    "select id, sector_code from instruments where internal_code = %s",
                    (choix,))
                instrument_id, sector_code = cur.fetchone()
                resultat = importer.importe(cur, instrument_id, choix, sector_code,
                                            dossier, analyste, type_fragment)
                conn.commit()

            if resultat.type_fragment != "controle":
                st.success(
                    f"Fragment intégré au brouillon. "
                    f"{resultat.validation.concurrents} concurrent(s), "
                    f"{resultat.validation.sources} source(s) au total."
                )
            elif resultat.projete:
                st.success(
                    f"Dossier importé et validé par {analyste}. "
                    f"{resultat.concurrents_internes} pair(s) de l'univers, "
                    f"{resultat.concurrents_externes} hors univers. "
                    f"Relancer `python scripts/compute_quality.py` pour que le "
                    f"verdict en tienne compte."
                )
            else:
                st.warning("Dossier enregistré, sans projection.")
            for message in resultat.messages:
                st.markdown(f"<div class='avertissement'>{message}</div>",
                            unsafe_allow_html=True)

# --------------------------------------------------------------------------- #
# Dossiers existants
# --------------------------------------------------------------------------- #
st.subheader("Dossiers enregistrés pour ce titre")
with connect_direct() as conn, conn.cursor() as cur:
    cur.execute(
        """
        select a.analysis_id, a.reference_date, a.status, a.analyst, a.expires_at,
               a.expires_at < current_date as perimee,
               jsonb_array_length(coalesce(a.dossier -> 'competitors', '[]'::jsonb)) as n
          from market_analyses a join instruments i on i.id = a.instrument_id
         where i.internal_code = %s order by a.reference_date desc
        """,
        (choix,),
    )
    colonnes = [c.name for c in cur.description]
    existants = pd.DataFrame(cur.fetchall(), columns=colonnes)

if existants.empty:
    st.info("Aucun dossier. Le titre reste `unqualified` — ce qui est son statut "
            "réel : pas « sans barrière », mais « jamais regardé ».")
else:
    st.dataframe(existants, use_container_width=True, hide_index=True)
    if bool(existants["perimee"].iloc[0]):
        st.markdown(
            "<div class='avertissement'><b>Dossier périmé.</b> Une évaluation de "
            "plus de 18 mois inspire exactement la même confiance qu'une récente, "
            "et c'est le problème. Le titre repasse en non qualifié.</div>",
            unsafe_allow_html=True,
        )
