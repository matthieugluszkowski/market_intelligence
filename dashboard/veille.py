"""Affichage de la veille externe sur la fiche instrument (doc 04, bloc B).

Trois encarts, une seule règle
-------------------------------
Consensus d'analystes, notations et dépêches sont **des avis de tiers**. Ils sont
affichés à côté du signal du modèle, jamais mélangés à lui, et ils n'entrent dans
aucun calcul : ni le z-score, ni le score de qualité, ni la solidité
concurrentielle ne les regardent.

La raison est simple : le consensus est structurellement optimiste et révisé
après coup. Une méthode qui l'intégrerait à son score achèterait ce que tout le
monde recommande déjà — c'est-à-dire l'inverse exact de ce que cherche un
screener de décote. Sa valeur est ailleurs : quand la régression sort un titre à
−2,4 σ et que vingt-trois analystes le disent à l'achat avec un objectif à +50 %,
on sait que la décote n'est pas un secret. Et quand le consensus dit l'inverse du
modèle, c'est là que la fiche devient intéressante.

Aucune de ces fonctions ne prend la palette : leurs barres vivent dans les
classes CSS de `theme.css`, en encre neutre et jamais en couleur. Ce sont des
rangs et des opinions, pas des verdicts — une barre verte ou rouge
transformerait « mieux noté que 24 % du secteur » en jugement.

Chaque encart porte **sa date de collecte et sa source**. Une dépêche de trois
semaines affichée sans date se lit comme une nouvelle du jour ; un consensus
sans date se lit comme celui d'aujourd'hui.
"""

from __future__ import annotations

from datetime import date, datetime

import streamlit as st


def _horodatage(brut) -> tuple:
    """Rend (date lisible, heure lisible) depuis un ISO. Ne lève jamais."""
    if not brut:
        return "—", ""
    try:
        moment = datetime.fromisoformat(str(brut))
    except ValueError:
        return str(brut), ""
    return moment.strftime("%d/%m/%Y"), moment.strftime("%Hh%M")


def _age(collecte_le) -> str:
    """« collecté aujourd'hui », « il y a 3 jours ». L'âge, pas seulement la date :
    « 25/08/2026 » ne dit rien tant qu'on n'a pas cherché la date du jour."""
    if not collecte_le:
        return ""
    jour = collecte_le if isinstance(collecte_le, date) else None
    if jour is None:
        try:
            jour = datetime.fromisoformat(str(collecte_le)).date()
        except ValueError:
            return str(collecte_le)
    jours = (date.today() - jour).days
    quand = ("aujourd'hui" if jours <= 0 else
             "hier" if jours == 1 else f"il y a {jours} jours")
    return f"collecté {quand} ({jour:%d/%m/%Y})"


def jauge(pourcentage: float | None) -> str:
    """Barre de remplissage. Sans valeur, une barre vide — jamais un zéro."""
    if pourcentage is None:
        return "<div class='jauge'></div>"
    borne = max(0.0, min(100.0, float(pourcentage)))
    return f"<div class='jauge'><span style='width:{borne:.1f}%'></span></div>"


def jauge_a_curseur(pourcentage: float | None) -> str:
    """Barre à curseur : la position sur un axe, pas une quantité.

    Un remplissage dirait « 84 % de quelque chose » ; ici la valeur est un point
    entre deux extrêmes (vendre et acheter), et le curseur le dit sans ambiguïté.
    """
    if pourcentage is None:
        return "<div class='jauge-curseur'></div>"
    borne = max(0.0, min(100.0, float(pourcentage)))
    return (f"<div class='jauge-curseur'>"
            f"<i style='left:calc({borne:.1f}% - 1.5px)'></i></div>")


def ligne_notee(libelle: str, pourcentage: float | None,
                mention: str | None = None) -> str:
    valeur = (mention if pourcentage is None and mention
              else "—" if pourcentage is None else f"{pourcentage:.0f} %")
    return (f"<div class='ligne-jauge'><b>{libelle}</b>{jauge(pourcentage)}"
            f"<span>{valeur}</span></div>")


# --------------------------------------------------------------------------- #
# Consensus des analystes
# --------------------------------------------------------------------------- #
def bloc_consensus(collecte: dict | None) -> None:
    st.markdown("**Consensus des analystes**")
    if not collecte:
        st.caption("Aucune collecte. Enregistrer l'adresse Zonebourse du titre "
                   "ci-dessous, puis lancer la collecte.")
        return

    c = collecte["payload"]
    recommandation = c.get("recommandation") or "—"
    analystes = c.get("nombre_d_analystes")
    devise = c.get("devise") or ""

    entete = [f"<span class='pastille'>{recommandation}</span>"]
    if analystes:
        entete.append(f"<b>{analystes}</b> analyste(s)")
    if c.get("note") is not None and c.get("note_max"):
        entete.append(f"note {c['note']:.1f}/{c['note_max']:.0f}".replace(".", ","))
    st.markdown("&nbsp;·&nbsp;".join(entete), unsafe_allow_html=True)

    st.markdown(
        f"<div class='ligne-jauge'><b>Vendre</b>"
        f"{jauge_a_curseur(c.get('note_pct'))}<span>Acheter</span></div>",
        unsafe_allow_html=True)

    objectifs = [
        ("Objectif moyen", c.get("objectif_moyen"), c.get("ecart_moyen_pct")),
        ("Objectif bas", c.get("objectif_bas"), c.get("ecart_bas_pct")),
        ("Objectif haut", c.get("objectif_haut"), c.get("ecart_haut_pct")),
    ]
    lignes = []
    for libelle, cible, ecart in objectifs:
        if cible is None:
            continue
        montant = f"{cible:,.2f}".replace(",", " ").replace(".", ",")
        variation = "" if ecart is None else f" ({ecart:+.2f} %)".replace(".", ",")
        lignes.append(f"{libelle} <b>{montant} {devise}</b>{variation}")
    if lignes:
        st.markdown(" · ".join(lignes), unsafe_allow_html=True)
    if c.get("cours_de_cloture") is not None:
        st.caption(f"Dernier cours retenu par la source : "
                   f"{c['cours_de_cloture']:.2f} {devise}".replace(".", ","))

    _pied(collecte, c)


# --------------------------------------------------------------------------- #
# Notations
# --------------------------------------------------------------------------- #
def bloc_notations(collecte: dict | None) -> None:
    st.markdown("**Notations**")
    if not collecte:
        st.caption("Aucune collecte.")
        return

    n = collecte["payload"]
    constat = n.get("constat")
    if constat:
        st.markdown(f"<div class='avertissement'>« {constat} »</div>",
                    unsafe_allow_html=True)

    notes = n.get("notes") or []
    if notes:
        st.markdown("".join(ligne_notee(x.get("libelle") or "—", x.get("note_pct"),
                                        x.get("mention"))
                            for x in notes), unsafe_allow_html=True)
        st.caption("Ces notes sont des **rangs**, pas des mesures : « 24 % » veut "
                   "dire mieux noté que 24 % de l'univers de comparaison de la "
                   "source sur ce critère. Lu comme une probabilité ou une "
                   "performance, le chiffre ne veut rien dire.")

    forts, faibles = n.get("points_forts") or [], n.get("points_faibles") or []
    if forts or faibles:
        with st.expander(f"Points forts et points faibles selon la source "
                         f"({len(forts)} + {len(faibles)})"):
            if forts:
                st.markdown("**Points forts**")
                for ligne in forts:
                    st.markdown(f"- {ligne}")
            if faibles:
                st.markdown("**Points faibles**")
                for ligne in faibles:
                    st.markdown(f"- {ligne}")
            st.caption("Reproduits tels que la source les publie. Ce sont des "
                       "phrases générées à partir de ses propres notations — pas "
                       "une analyse relue, et pas la nôtre.")

    _pied(collecte, n)


# --------------------------------------------------------------------------- #
# Dépêches
# --------------------------------------------------------------------------- #
def bloc_depeches(collecte: dict | None, limite: int = 12) -> None:
    st.markdown("**Dépêches**")
    if not collecte:
        st.caption("Aucune collecte.")
        return

    d = collecte["payload"]
    depeches = (d.get("depeches") or [])[:limite]
    if not depeches:
        st.caption("Aucune dépêche pour ce titre.")
        return

    for depeche in depeches:
        jour, heure = _horodatage(depeche.get("publie_le"))
        titre = depeche.get("titre") or "—"
        with st.expander(f"{jour} {heure} · {titre}"):
            texte = (depeche.get("texte") or "").strip()
            if texte:
                for paragraphe in texte.split("\n\n"):
                    st.markdown(paragraphe)
            else:
                st.caption("Texte non collecté — seules les dépêches les plus "
                           "récentes sont lues en entier, une requête chacune.")
            url = depeche.get("url")
            if url:
                st.markdown(f"[Lire sur {d.get('source') or 'la source'}]({url})")
            auteur = depeche.get("auteur")
            if auteur:
                st.caption(f"Par {auteur}")

    _pied(collecte, d)


def _pied(collecte: dict, payload: dict) -> None:
    """Source, lien, droits, âge de la collecte. Jamais optionnel : un chiffre
    sans sa source est une autorité, avec sa source c'est un argument."""
    morceaux = [_age(collecte.get("collecte_le"))]
    url = payload.get("url") or collecte.get("url")
    if url:
        # Une balise, pas un lien markdown : le pied est rendu en HTML brut, et
        # markdown n'y est pas interprété.
        morceaux.append(f"<a href='{url}' target='_blank'>voir la page source</a>")
    droits = payload.get("copyright")
    if droits:
        morceaux.append(droits)
    st.markdown(f"<div class='source-note'>{' · '.join(m for m in morceaux if m)}"
                f"</div>", unsafe_allow_html=True)
