"""Analyses (doc 04, écran 7 · doc 08 §8).

L'écran qui remplace l'agent autonome. Il ne dialogue avec aucune API : il
**compose** les prompts et **importe** le résultat. Entre les deux, le travail se
fait ailleurs — et surtout, il se relit. Cinq prompts : quatre construisent le
dossier concurrentiel, le cinquième produit la synthèse décisionnelle et les
scores — alimenté par les données déjà en base, jamais par une saisie.

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
import math
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

st.set_page_config(page_title="Analyses", page_icon="◧", layout="wide")

sombre = st.sidebar.toggle("Mode sombre", value=False)
p = palette(sombre)
st.markdown(css(p), unsafe_allow_html=True)

univers = data.instruments()
choix = st.sidebar.selectbox(
    "Instrument", univers["internal_code"],
    format_func=lambda c: univers.set_index("internal_code").loc[c, "name"],
)
ligne = univers.set_index("internal_code").loc[choix]


def _nombre(valeur):
    """float propre ou None - jamais de NaN dans un JSON destine au LLM."""
    if isinstance(valeur, bool):
        return valeur
    try:
        nombre = float(valeur)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(nombre) else round(nombre, 6)


def instantane_quantitatif(code: str) -> dict:
    """Ce que l'outil sait de ce titre, assemblé pour le prompt 5.

    C'est le renversement qui rend la synthèse possible : les données ne sont
    pas ressaisies, elles sont **injectées depuis la base** — prix et tendance,
    ratios fondamentaux, qualité quantitative, évaluation qualitative. Un bloc
    absent reste `null` : le prompt a l'obligation de le dire, pas de l'estimer.
    """
    as_of = data.derniere_date_de_calcul()
    fit = data.fit(code, as_of) if as_of else None
    qual = data.qualite(code)
    fonda = data.fondamentaux(code, as_of) if as_of else {}

    prix_et_tendance = None
    if fit is not None:
        prix_et_tendance = {
            "date_du_calcul": str(as_of),
            "dernier_cours": _nombre(fit["last_close"]),
            "devise": str(fit["currency"]),
            "z_score": _nombre(fit["z_score"]),
            "pente_annuelle": _nombre(fit["slope_annual"]),
            "r2": _nombre(fit["r_squared"]),
            "qualite_du_fit": fit["fit_quality"],
            "motifs": list(fit["quality_reasons"] or []),
            "demi_vie_jours": _nombre(fit["half_life_days"]),
            "fenetre": [str(fit["window_start"]), str(fit["window_end"])],
            "statistiques_de_regime": fit["regime_stats"],
        }

    qualite_quantitative, evaluation_qualitative = None, None
    if qual:
        q = qual["score"]
        qualite_quantitative = {
            "date": str(q["as_of_date"]),
            "tier": q["quality_tier"], "regime": q["regime"],
            "roic_moyen_5a": _nombre(q["roic_mean_5y"]),
            "roic_vs_seuil_8pct": _nombre(q["roic_vs_threshold"]),
            "roic_vs_pairs": _nombre(q["roic_vs_peers"]),
            "persistance_rente": f"{q['persistence_years']}/{q['n_years_available']} exercices",
            "marge_brute_moyenne": _nombre(q["gross_margin_mean"]),
            "pentes_5a": {"roic": _nombre(q["roic_slope_5y"]),
                          "marge_brute": _nombre(q["gross_margin_slope_5y"]),
                          "part_relative": _nombre(q["share_slope_5y"])},
            "drapeaux_erosion_sur_3": _nombre(q["erosion_flags"]),
            "groupe_de_pairs": q["groupe_label"],
            "groupe_complet": bool(q["groupe_complet"]),
        }
        evaluation = qual["evaluation"]
        if evaluation is not None:
            evaluation_qualitative = {
                "position": evaluation["position_verdict"],
                "durabilite": evaluation["durability_verdict"],
                "sources_de_rente": list(evaluation["moat_sources"] or []),
                "evaluee_le": str(evaluation["assessed_at"]),
                "expire_le": str(evaluation["expires_at"]),
                "auteur": evaluation["authored_by"],
                "revue_par": evaluation["reviewed_by"],
                "perimee": bool(evaluation["perimee"]),
            }

    fondamentaux = None
    if fonda:
        fondamentaux = {
            "ratios": {cle: _nombre(v) for cle, v in fonda["ratios"].items()
                       if not isinstance(v, (list, dict))},
            "coherence_prix_fondamentaux": {
                "verdict": fonda["coherence"].verdict,
                "criteres": dict(fonda["coherence"].criteres),
                "non_evaluables": list(fonda["coherence"].manquants),
            },
            "capitalisation": _nombre(fonda["capitalisation"]),
            "exercices_connus": [str(e) for e in fonda["exercices"]],
        }

    return {
        "instrument": {"code": code, "nom": str(ligne["name"]),
                       "isin": str(ligne["isin"]),
                       "devise": str(ligne["currency"])},
        "prix_et_tendance": prix_et_tendance,
        "qualite_quantitative": qualite_quantitative,
        "evaluation_qualitative": evaluation_qualitative,
        "fondamentaux": fondamentaux,
        "avertissement": ("Donnees arretees a la derniere date de calcul "
                          "hebdomadaire. null = non disponible : a signaler, "
                          "jamais a estimer."),
    }


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

st.title("Analyses")
st.caption(f"{ligne['name']} · {choix} · du cadrage concurrentiel (prompts 1-4) "
           f"à la synthèse décisionnelle et son scoring (prompt 5)")

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
    noms_fiches = [schema.lire(pr, "company_name")
                   for pr in schema.lire(dossier, "company_profiles", defaut=[])]
    restants = [n for n in candidats
                if not any(schema.meme_societe(n, nf) for nf in noms_fiches)]
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

        variables_du_prompt = variables
        if cle == "concurrent" and not (concurrent_courant or "").strip():
            st.warning("Aucun concurrent disponible : importer d'abord le prompt 1.")
        if cle == "controle":
            st.caption("Coller les trois analyses précédentes dans le prompt, "
                       "aux emplacements indiqués.")
        if cle == "synthese":
            # Les donnees de l'outil sont injectees : rien a coller, rien a
            # ressaisir. C'est aussi ce qui date la synthese - elle juge l'etat
            # de la base a cet instant, pas un souvenir.
            if not dossier:
                st.warning("Aucun dossier : la synthèse jugera sur les seules "
                           "données quantitatives et devra probablement "
                           "conclure « insuffisant ». Lancer d'abord les "
                           "prompts 1 à 4.")
            elif not schema.lire(dossier, "strategic_assessment",
                                 "position_verdict"):
                st.caption("Le dossier n'a pas encore de verdicts (prompt 4 "
                           "non importé ou non signé) : la synthèse devra en "
                           "tenir compte dans son score de confiance.")

            # Tout inline, le prompt depasse les limites de collage des
            # interfaces de chat : elles le convertissent en piece jointe .txt
            # et le modele le traite en document a resumer - plus aucune
            # consigne de format n'est suivie. Le mode « prompt court +
            # fichier de donnees » contourne exactement ce comportement.
            livraison = st.radio(
                "Livraison des données", ["fichier", "inline"], horizontal=True,
                key="livraison_synthese",
                format_func=lambda m: (
                    "Prompt court + fichier de données à joindre (recommandé)"
                    if m == "fichier" else
                    "Tout dans le prompt (long — API ou grandes fenêtres)"),
                help="Collé tel quel, un prompt de ~80 000 caractères est "
                     "converti en fichier .txt par ChatGPT ou Claude, et le "
                     "modèle cesse de suivre le format de sortie. Le mode "
                     "recommandé colle un prompt court et joint les données "
                     "en fichier JSON.")

            donnees = {
                "donnees_quantitatives": instantane_quantitatif(choix),
                "dossier_analyses": dossier or {},
            }
            communes = {
                **variables,
                "TICKER": f"{choix} · ISIN {ligne['isin']}",
                "DEVISE": str(ligne["currency"]),
                "HORIZON_ANALYSE": variables.get("HORIZON_ANALYSE") or "12 à 36 mois",
            }
            if livraison == "fichier":
                nom_donnees = f"donnees_synthese_{choix.replace(':', '_')}.json"
                variables_du_prompt = {
                    **communes,
                    "DONNEES_QUANTITATIVES":
                        f"[Dans le fichier joint « {nom_donnees} », "
                        f"clé `donnees_quantitatives`.]",
                    "DOSSIER_ANALYSES":
                        f"[Dans le fichier joint « {nom_donnees} », "
                        f"clé `dossier_analyses`.]",
                }
                st.download_button(
                    "1 · Télécharger les données (à joindre au message)",
                    json.dumps(donnees, ensure_ascii=False, indent=1,
                               default=str).encode("utf-8"),
                    file_name=nom_donnees, mime="application/json",
                    key="dl_donnees_synthese")
                st.caption("**2 ·** Copier le prompt ci-dessous. **3 ·** Dans "
                           "le chat : joindre le fichier ET coller le prompt "
                           "dans le même message, puis envoyer.")
            else:
                variables_du_prompt = {
                    **communes,
                    "DONNEES_QUANTITATIVES": json.dumps(
                        donnees["donnees_quantitatives"], ensure_ascii=False,
                        indent=1, default=str),
                    "DOSSIER_ANALYSES": json.dumps(
                        donnees["dossier_analyses"], ensure_ascii=False,
                        separators=(",", ":"), default=str),
                }

        manquantes = prompts.variables_manquantes(cle, variables_du_prompt)
        if manquantes:
            st.caption("Variables requises non renseignées : " + ", ".join(manquantes))

        texte = prompts.compose(cle, variables_du_prompt)
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

# Les messages du dernier import sont affichés APRÈS le rerun : les afficher
# avant serait les perdre — st.rerun() interrompt le script et l'analyste ne
# verrait jamais le résultat de son geste.
for genre, texte in st.session_state.pop(f"resultat_import::{choix}", []):
    if genre == "success":
        st.success(texte)
    elif genre == "warning":
        st.warning(texte)
    else:
        st.markdown(f"<div class='avertissement'>{texte}</div>",
                    unsafe_allow_html=True)

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

# --------------------------------------------------------------------------- #
# Ce que seul un humain peut poser : l'acquittement des bloquants du contrôle
# qualité, et les verdicts sur l'entreprise étudiée. Le LLM propose, l'analyste
# dispose — rien de tout cela n'est complété automatiquement.
# --------------------------------------------------------------------------- #
fragment_effectif = fragment
if fragment is not None and type_fragment == "controle":
    fragment_effectif = json.loads(json.dumps(fragment))

    bloquants_qc = list(schema.lire(fragment_effectif, "quality_control",
                                    "blocking_issues", defaut=[]) or [])
    if bloquants_qc:
        st.markdown("**Points bloquants signalés par le contrôle qualité** — ils "
                    "empêchent la validation tant qu'un analyste ne les a pas "
                    "vérifiés :")
        for probleme in bloquants_qc:
            st.markdown(f"- {probleme}")
        acquitte = st.checkbox(
            "J'ai vérifié ces points à la main : les acquitter nominativement.",
            help="L'acquittement est tracé dans le dossier avec le nom de "
                 "l'analyste et la date. Sans lui, le dossier reste en "
                 "brouillon — rien n'est levé en silence.",
        )
        if acquitte and analyste.strip():
            fragment_effectif.setdefault("quality_control", {})[
                "blocking_issues_reviewed"] = {
                "par": analyste.strip(), "le": date.today().isoformat()}
        elif acquitte:
            st.warning("L'acquittement exige le nom de l'analyste, ci-dessus.")

    st.markdown("**Verdicts sur l'entreprise étudiée** — c'est un jugement, pas "
                "une requête : le LLM les propose dans `strategic_assessment`, "
                "l'analyste les confirme ou les corrige ici. Sans eux, aucune "
                "évaluation qualitative n'est projetée et le titre ne peut pas "
                "atteindre `solid`.")
    propose = schema.lire(fragment_effectif, "strategic_assessment", defaut={})
    NON_POSE = "(non posé)"
    POSITIONS = [NON_POSE, "leader", "challenger", "follower", "niche"]
    DURABILITES = [NON_POSE, "solid", "watch", "eroding", "none"]
    MOATS = ["brand", "patent", "switching", "network", "cost", "scale"]
    v1, v2, v3 = st.columns(3)
    with v1:
        prop = schema.lire(propose, "position_verdict")
        position = st.selectbox(
            "Position concurrentielle", POSITIONS,
            index=POSITIONS.index(prop) if prop in POSITIONS else 0,
            help="leader : domine le marché · challenger : conteste le leader · "
                 "follower : suit sans peser · niche : domine un segment étroit",
        )
    with v2:
        prop = schema.lire(propose, "durability_verdict")
        durabilite = st.selectbox(
            "Durabilité de la rente", DURABILITES,
            index=DURABILITES.index(prop) if prop in DURABILITES else 0,
            help="solid : barrière intacte · watch : à surveiller · eroding : "
                 "en érosion · none : aucune barrière",
        )
    with v3:
        moats = st.multiselect(
            "Sources de rente (moat)", MOATS,
            default=[m for m in (schema.lire(propose, "moat_sources",
                                             defaut=[]) or []) if m in MOATS],
            help="brand : marque · patent : brevets · switching : coûts de "
                 "changement · network : effet réseau · cost : avantage de "
                 "coûts · scale : échelle",
        )
    justification = st.text_area(
        "Justification du verdict",
        schema.lire(propose, "rationale", defaut="") or "", height=80,
        placeholder="Ce qui fonde la position et sa durabilité, appuyé sur le "
                    "dossier…",
    )
    if position != NON_POSE or durabilite != NON_POSE:
        strategie = fragment_effectif.setdefault("strategic_assessment", {})
        if position != NON_POSE:
            strategie["position_verdict"] = position
        if durabilite != NON_POSE:
            strategie["durability_verdict"] = durabilite
        if moats:
            strategie["moat_sources"] = moats
        if justification.strip():
            strategie["rationale"] = justification.strip()

gauche, _ = st.columns([1, 3])
with gauche:
    verifier = st.button("Vérifier", use_container_width=True)
    lancer = st.button("Importer", type="primary", use_container_width=True)

if (verifier or lancer) and fragment is None:
    st.error("Aucun JSON exploitable.")
elif verifier or lancer:
    apercu = schema.fusionne(dossier or {}, fragment_effectif, type_fragment)
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
            st.warning(
                f"{len(validation.bloquants)} bloquant(s) : le dossier sera "
                f"conservé en **brouillon**, sans validation ni projection. "
                f"Corriger les points ci-dessus — ou les acquitter "
                f"nominativement s'ils viennent du contrôle qualité — puis "
                f"réimporter.")
        else:
            st.info(f"Dossier encore incomplet ({len(validation.bloquants)} "
                    f"manque(s)) — normal tant que les quatre étapes ne sont pas "
                    f"faites. Le fragment reste intégrable.")

    if lancer:
        with connect_direct() as conn, conn.cursor() as cur:
            cur.execute("select id, sector_code from instruments "
                        "where internal_code = %s", (choix,))
            instrument_id, sector_code = cur.fetchone()
            resultat = importer.importe(cur, instrument_id, choix, sector_code,
                                        fragment_effectif, analyste, type_fragment,
                                        nom_instrument=str(ligne["name"]))
            conn.commit()

        messages = []
        if resultat.type_fragment != "controle":
            messages.append(("success",
                             f"« {schema.FRAGMENTS[resultat.type_fragment]} » intégré. "
                             f"Le dossier compte {resultat.validation.concurrents} "
                             f"concurrent(s) et {resultat.validation.sources} source(s)."))
        elif resultat.projete:
            messages.append(("success",
                             f"Dossier validé par {analyste}. "
                             f"{resultat.concurrents_internes} pair(s) de l'univers, "
                             f"{resultat.concurrents_externes} hors univers. Relancer "
                             f"`python scripts/compute_quality.py --recalculer`."))
        elif not resultat.validation.importable:
            messages.append(("warning",
                             f"{len(resultat.validation.bloquants)} bloquant(s) : "
                             f"dossier conservé en **brouillon**, sans validation "
                             f"ni projection."))
        else:
            messages.append(("warning", "Dossier enregistré, sans projection."))
        messages += [("note", m) for m in resultat.messages]
        st.session_state[f"resultat_import::{choix}"] = messages

        # L'import vient de changer la vérité en base : servir les caches de
        # l'ancienne serait afficher un dossier périmé sur la fiche instrument.
        st.cache_data.clear()
        st.rerun()
