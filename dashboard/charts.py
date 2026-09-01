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

# Debordement tolere a droite du graphe pour la marque d'achat : la serie
# hebdomadaire s'arrete a la derniere barre close, un achat recent lui est
# posterieur de quelques jours. Voir `couches_position`.
MARGE_APRES = pd.Timedelta(days=90)


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


def couches_position(serie: pd.DataFrame, positions: pd.DataFrame,
                     p: Palette, devise: str) -> list:
    """Marque « ma position » sur le graphe : date d'achat et prix de revient.

    Deux traits rouges qui se croisent au point d'entree. La verticale dit
    *quand*, l'horizontale dit *a combien* - et c'est l'horizontale qui porte
    l'information utile : lire la distance entre la courbe et son propre prix de
    revient est immediat, alors qu'un pourcentage dans un tableau demande de
    reconstituer mentalement le graphe.

    **Ce qui sort du cadre n'est pas dessine.** Un achat anterieur a la fenetre
    de regression, ou un prix hors de l'echelle affichee, etirerait les axes et
    ecraserait la courbe : le graphe deviendrait faux a l'oeil pour signaler un
    fait exact. L'appelant l'ecrit alors en toutes lettres sous le graphe.

    La tolerance est asymetrique, et c'est voulu. **A droite**, la serie s'arrete
    a la derniere barre hebdomadaire close : un achat de la semaine en cours lui
    est posterieur de quelques jours, et le refuser masquerait justement la
    position la plus fraiche - pour un etirement de quelques jours sur une
    fenetre de vingt ans. **A gauche**, un achat anterieur a la fenetre
    l'etendrait de plusieurs annees et ecraserait la courbe : on ne le trace pas.
    """
    if positions is None or positions.empty or serie.empty:
        return []

    debut = pd.Timestamp(serie["ts"].min())
    fin = pd.Timestamp(serie["ts"].max())
    bas = float(min(serie["bande_basse_2"].min(), serie["close"].min()))
    haut = float(max(serie["bande_haute_2"].max(), serie["close"].max()))

    marques = positions.copy()
    # `opened_at` arrive en `datetime.date` : sans conversion explicite, la
    # serialisation du graphe depend du transformeur de donnees d'Altair.
    marques["opened_at"] = pd.to_datetime(marques["opened_at"])
    marques["avg_price"] = marques["avg_price"].astype(float)
    marques["mode"] = marques["is_paper"].map({True: "fictive", False: "réelle"})
    marques["etiquette"] = marques.apply(
        lambda l: (f"{l['quantity']:g} × {l['avg_price']:.2f} {devise} "
                   f"({l['mode']})"), axis=1)

    dans_le_cadre = marques[(marques["opened_at"] >= debut)
                            & (marques["opened_at"] <= fin + MARGE_APRES)]
    prix_visibles = marques[(marques["avg_price"] >= bas)
                            & (marques["avg_price"] <= haut)]

    couches = []
    infobulle = [
        alt.Tooltip("opened_at:T", title="Achat"),
        alt.Tooltip("etiquette:N", title="Position"),
    ]

    if not prix_visibles.empty:
        couches.append(
            alt.Chart(prix_visibles).mark_rule(
                size=1.5, color=p.marque_position, opacity=0.75,
            ).encode(y=alt.Y("avg_price:Q", scale=alt.Scale(type="log")),
                     tooltip=infobulle))

    if not dans_le_cadre.empty:
        couches.append(
            alt.Chart(dans_le_cadre).mark_rule(
                size=1.5, color=p.marque_position, opacity=0.75,
            ).encode(x="opened_at:T", tooltip=infobulle))

    croisement = dans_le_cadre[dans_le_cadre["avg_price"].between(bas, haut)]
    if not croisement.empty:
        couches.append(
            alt.Chart(croisement).mark_point(
                size=130, filled=True, color=p.marque_position,
                stroke=p.surface, strokeWidth=2,
            ).encode(x="opened_at:T",
                     y=alt.Y("avg_price:Q", scale=alt.Scale(type="log")),
                     tooltip=infobulle))
    return couches


PERIODES = {
    "Tout": None, "20 ans": 20 * 365, "10 ans": 10 * 365, "5 ans": 5 * 365,
    "3 ans": 3 * 365, "1 an": 365,
}


def fenetre(serie: pd.DataFrame, periode: str) -> pd.DataFrame:
    """Les N dernieres annees de la serie, sans rien recalculer.

    **La tendance et les bandes ne bougent pas** : ce sont des colonnes deja
    calculees sur la fenetre de regression complete. Couper l'affichage ne
    re-estime rien - on regarde de plus pres la meme droite, on n'en trace pas
    une autre. Un graphe qui re-estimerait sur la periode affichee montrerait
    une pente differente a chaque zoom, et ce serait faux.
    """
    jours = PERIODES.get(periode)
    if not jours or serie.empty:
        return serie
    depuis = pd.Timestamp(serie["ts"].max()) - pd.Timedelta(days=jours)
    coupee = serie[pd.to_datetime(serie["ts"]) >= depuis]
    # Moins de deux points ne fait pas un graphe : on rend la serie entiere
    # plutot qu'un ecran vide.
    return coupee if len(coupee) > 2 else serie


def graphe_regression(serie: pd.DataFrame, p: Palette, devise: str,
                      hauteur: int = 620,
                      positions: pd.DataFrame | None = None) -> alt.Chart:
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

    # « Ma position » par-dessus la courbe, sous le point courant : c'est un
    # repere de lecture, pas une serie de donnees.
    couches.extend(couches_position(serie, positions, p, devise))

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

    # Zoom et deplacement : molette pour l'echelle, glisser pour se deplacer,
    # double-clic pour revenir. Lie **aux deux axes** - sur une echelle
    # logarithmique de vingt ans, zoomer sur le temps sans zoomer sur les prix
    # laisse la courbe ecrasee au meme endroit et ne montre rien de plus.
    zoom = alt.selection_interval(bind="scales", encodings=["x", "y"])

    return (
        alt.layer(*couches)
        .add_params(zoom)
        .properties(height=hauteur, background=p.surface)
        .configure_view(stroke=None)
        .configure(font="system-ui")
    )


def panneau_z(serie: pd.DataFrame, p: Palette, hauteur: int = 150) -> alt.Chart:
    """Le z-score sous le graphe des cours, sur toute la fenetre affichee.

    Le meme fait, lu autrement : le graphe du haut montre un cours qui monte, ce
    panneau montre s'il est cher ou non **par rapport a sa propre tendance**.
    Sur vingt ans d'echelle logarithmique, un ecart de deux sigma se voit mal en
    haut et se lit immediatement ici.

    Il ne suit pas le zoom du graphe du dessus, et c'est voulu : il sert de vue
    d'ensemble - savoir ou l'on se trouve quand on est zoome sur six mois.
    """
    if serie.empty:
        return alt.Chart(pd.DataFrame({"ts": [], "z": []})).mark_line()

    axe = alt.Axis(grid=True, gridColor=p.grille, gridDash=[],
                   domainColor=p.encre_attenuee, tickColor=p.encre_attenuee,
                   labelColor=p.encre_secondaire, titleColor=p.encre_secondaire)
    base = alt.Chart(serie).encode(x=alt.X("ts:T", title=None, axis=axe))

    couches = []
    episodes = episodes_sous_seuil(serie)
    if not episodes.empty:
        couches.append(
            alt.Chart(episodes).mark_rect(opacity=0.10, color=p.serie_cours)
            .encode(x="debut:T", x2="fin:T"))

    # Les seuils sont des reperes, pas des series : encre attenuee, filet plein.
    seuils = pd.DataFrame({"seuil": [-2.0, 0.0, 2.0]})
    couches.append(
        alt.Chart(seuils).mark_rule(size=1, color=p.encre_attenuee, opacity=0.55)
        .encode(y=alt.Y("seuil:Q", title="z-score", axis=axe)))
    couches.append(
        base.mark_line(size=1.5, color=p.serie_cours).encode(
            y=alt.Y("z:Q", axis=axe),
            tooltip=[alt.Tooltip("ts:T", title="Date"),
                     alt.Tooltip("z:Q", title="z-score", format="+.2f")]))

    return (alt.layer(*couches)
            .properties(height=hauteur, background=p.surface)
            .configure_view(stroke=None)
            .configure(font="system-ui"))


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


def graphe_dividendes(historique_annuel: pd.DataFrame, p: Palette, devise: str = "EUR") -> alt.Chart:
    """Diagramme en barres de l'historique des dividendes annuels par action."""
    if historique_annuel.empty:
        return alt.Chart(pd.DataFrame()).mark_text().encode(text=alt.value("Aucun dividende"))

    axe_x = alt.Axis(grid=False, labelColor=p.encre_secondaire, titleColor=p.encre_secondaire,
                     domainColor=p.encre_attenuee, tickColor=p.encre_attenuee, format="d")
    axe_y = alt.Axis(grid=True, gridColor=p.grille, gridDash=[],
                     labelColor=p.encre_secondaire, titleColor=p.encre_secondaire,
                     domainColor=p.encre_attenuee, tickColor=p.encre_attenuee)

    return (
        alt.Chart(historique_annuel)
        .mark_bar(color="#0ca30c", cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
        .encode(
            x=alt.X("annee:O", title="Année", axis=axe_x),
            y=alt.Y("montant_total:Q", title=f"DPA ({devise})", axis=axe_y),
            tooltip=[
                alt.Tooltip("annee:O", title="Année"),
                alt.Tooltip("montant_total:Q", title="Dividende par action", format=".2f"),
                alt.Tooltip("nb_versements:Q", title="Versements"),
            ],
        )
        .properties(height=220, background=p.surface)
        .configure_view(stroke=None)
        .configure(font="system-ui")
    )

