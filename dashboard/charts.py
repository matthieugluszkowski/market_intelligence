"""Graphe de regression et son jumeau tabulaire (doc 04 SS3, bloc A).

Quatre points de specification qui ne se negocient pas :

- **Axe y logarithmique obligatoire.** Le modele est lineaire en log ; un axe
  lineaire courberait la droite et rendrait le graphe faux a l'oeil.
- **Un seul axe y.** Jamais de second axe pour le volume - c'est l'erreur de
  graphique la plus frequente et elle invente des correlations.
- **Les bandes ne sont pas des series.** Ce sont des zones de reference : gris
  neutres, jamais une teinte de la palette de series.
- **Filets pleins, jamais pointilles**, y compris pour les bornes de bandes.

Et le principe I3 : toute visualisation a un jumeau tabulaire. C'est une exigence
d'accessibilite, et c'est aussi la seule facon de verifier qu'un graphe ne ment
pas - notamment de confronter la courbe a une source externe.
"""

from __future__ import annotations

import altair as alt
import numpy as np
import pandas as pd

from .theme import Palette

SEUIL_EPISODE = -2.0


def serie_de_regression(barres: pd.DataFrame, fit) -> pd.DataFrame:
    """Reconstruit tendance, bandes et z-score depuis les parametres stockes.

    On ne re-estime rien : `intercept` et `slope_annual` sont ceux qu'a ecrits
    le moteur. Recalculer ici ferait diverger le graphe de ce que le screener a
    classe, sans que rien ne le signale.
    """
    fenetre = barres[
        (barres["ts"] >= fit["window_start"]) & (barres["ts"] <= fit["window_end"])
    ].copy()
    if fenetre.empty:
        return fenetre

    origine = fit["window_start"]
    t = np.array([(d - origine).days / 365.25 for d in fenetre["ts"]])
    beta = np.log(1.0 + float(fit["slope_annual"]))
    log_tendance = float(fit["intercept"]) + beta * t
    sigma = float(fit["sigma_resid"])

    fenetre["tendance"] = np.exp(log_tendance)
    fenetre["bande_haute_1"] = np.exp(log_tendance + sigma)
    fenetre["bande_basse_1"] = np.exp(log_tendance - sigma)
    fenetre["bande_haute_2"] = np.exp(log_tendance + 2 * sigma)
    fenetre["bande_basse_2"] = np.exp(log_tendance - 2 * sigma)
    fenetre["z"] = (np.log(fenetre["close"].astype(float)) - log_tendance) / sigma
    return fenetre


def episodes_sous_seuil(serie: pd.DataFrame, seuil: float = SEUIL_EPISODE) -> pd.DataFrame:
    """Intervalles de dates ou z reste sous le seuil.

    Les surligner rend visible que **la decote est un regime, pas un instant** -
    ce que le graphe seul ne montre pas.
    """
    sous = (serie["z"] <= seuil).to_numpy()
    dates = serie["ts"].to_numpy()
    intervalles, debut = [], None
    for i, valeur in enumerate(sous):
        if valeur and debut is None:
            debut = dates[i]
        elif not valeur and debut is not None:
            intervalles.append({"debut": debut, "fin": dates[i - 1]})
            debut = None
    if debut is not None:
        intervalles.append({"debut": debut, "fin": dates[-1]})
    return pd.DataFrame(intervalles)


def graphe_regression(serie: pd.DataFrame, p: Palette, devise: str,
                      hauteur: int = 460) -> alt.Chart:
    axe_x = alt.Axis(grid=True, gridColor=p.grille, gridDash=[], domainColor=p.encre_attenuee,
                     tickColor=p.encre_attenuee, labelColor=p.encre_secondaire,
                     titleColor=p.encre_secondaire)
    axe_y = alt.Axis(grid=True, gridColor=p.grille, gridDash=[], domainColor=p.encre_attenuee,
                     tickColor=p.encre_attenuee, labelColor=p.encre_secondaire,
                     titleColor=p.encre_secondaire, format="~s")

    base = alt.Chart(serie).encode(
        x=alt.X("ts:T", title=None, axis=axe_x)
    )

    couches = []

    # Episodes sous seuil, en fond tres leger : ils passent sous tout le reste.
    episodes = episodes_sous_seuil(serie)
    if not episodes.empty:
        couches.append(
            alt.Chart(episodes).mark_rect(opacity=0.10, color=p.serie_cours).encode(
                x="debut:T", x2="fin:T"
            )
        )

    # Bandes : zones de reference en gris neutre, jamais une teinte de serie.
    couches.append(base.mark_area(opacity=0.04, color=p.encre_attenuee).encode(
        y=alt.Y("bande_basse_2:Q", scale=alt.Scale(type="log"),
                title=f"Cours ({devise}), echelle logarithmique", axis=axe_y),
        y2="bande_haute_2:Q",
    ))
    couches.append(base.mark_area(opacity=0.08, color=p.encre_attenuee).encode(
        y=alt.Y("bande_basse_1:Q", scale=alt.Scale(type="log")), y2="bande_haute_1:Q",
    ))

    # Bornes de bandes : filets pleins de 1px, encre attenuee.
    for colonne in ("bande_basse_2", "bande_basse_1", "bande_haute_1", "bande_haute_2"):
        couches.append(base.mark_line(size=1, color=p.encre_attenuee, opacity=0.55).encode(
            y=alt.Y(f"{colonne}:Q", scale=alt.Scale(type="log"))
        ))

    couches.append(base.mark_line(size=2, color=p.encre_secondaire).encode(
        y=alt.Y("tendance:Q", scale=alt.Scale(type="log"))
    ))
    couches.append(base.mark_line(size=2, color=p.serie_cours).encode(
        y=alt.Y("close:Q", scale=alt.Scale(type="log"))
    ))

    # Point courant : marqueur 8px minimum, anneau de la couleur de surface.
    dernier = serie.tail(1)
    couches.append(
        alt.Chart(dernier).mark_point(
            size=110, filled=True, color=p.serie_cours,
            stroke=p.surface, strokeWidth=2,
        ).encode(x="ts:T", y=alt.Y("close:Q", scale=alt.Scale(type="log")))
    )

    # Reticule et infobulle au survol : aucune valeur ecrite sur les points.
    selection = alt.selection_point(nearest=True, on="pointerover",
                                    fields=["ts"], empty=False)
    couches.append(
        base.mark_rule(color=p.encre_attenuee).encode(
            opacity=alt.condition(selection, alt.value(0.5), alt.value(0)),
            tooltip=[
                alt.Tooltip("ts:T", title="Date"),
                alt.Tooltip("close:Q", title=f"Cours ({devise})", format=".2f"),
                alt.Tooltip("tendance:Q", title="Tendance", format=".2f"),
                alt.Tooltip("z:Q", title="z-score", format="+.2f"),
            ],
        ).add_params(selection)
    )

    return (
        alt.layer(*couches)
        .properties(height=hauteur, background=p.surface)
        .configure_view(stroke=None)
        .configure(font="system-ui")
    )


def jumeau_tabulaire(serie: pd.DataFrame) -> pd.DataFrame:
    """Valeurs exactes du graphe (principe I3).

    Sert aussi de piece a conviction pour confronter la courbe a une source
    externe : sans les nombres, une superposition « a l'oeil » ne prouve rien.
    """
    table = serie[["ts", "close", "close_brut", "tendance",
                   "bande_basse_2", "bande_basse_1",
                   "bande_haute_1", "bande_haute_2", "z"]].copy()
    table.columns = ["Date", "Cours ajuste", "Cours brut", "Tendance",
                     "-2σ", "-1σ", "+1σ", "+2σ", "z-score"]
    return table.sort_values("Date", ascending=False).round(4)


def graphe_historique_fits(historique: pd.DataFrame, p: Palette) -> alt.Chart:
    """Le principe P5 rendu visible : le z-score tel qu'affirme chaque semaine."""
    axe = alt.Axis(grid=True, gridColor=p.grille, gridDash=[],
                   labelColor=p.encre_secondaire, titleColor=p.encre_secondaire,
                   domainColor=p.encre_attenuee, tickColor=p.encre_attenuee)
    return (
        alt.Chart(historique)
        .mark_line(size=2, point=True, color=p.serie_cours)
        .encode(
            x=alt.X("as_of_date:T", title="Date de calcul", axis=axe),
            y=alt.Y("z_score:Q", title="z-score affirme ce jour-la", axis=axe),
            tooltip=["as_of_date:T", alt.Tooltip("z_score:Q", format="+.2f"),
                     "fit_quality:N"],
        )
        .properties(height=200, background=p.surface)
        .configure_view(stroke=None)
    )
