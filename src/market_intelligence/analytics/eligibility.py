"""Filtres d'eligibilite, appliques **avant** tout calcul (doc 03 SS2, etape 2).

L'ordre compte : estimer puis disqualifier laisse trainer des parametres calcules
sur des donnees qu'on vient de declarer inutilisables, et quelqu'un finira par
les lire.

Le filtre de dilution merite d'etre detaille, parce que c'est celui qui n'existe
nulle part ailleurs et qui evite le plus gros piege. Sans lui, Atos, Casino,
Solocal et leurs semblables apparaissent en tete du screener avec un z-score de
-4, parce que la droite historique a ete calculee sur une valeur par action qui
n'existe plus. **C'est invisible sur le graphe** : la courbe est belle, la droite
est propre, et le signal est faux.
"""

from __future__ import annotations

from datetime import date

# Un trou est tolerable, dix pour cent de trous ne le sont plus : la fenetre ne
# couvre alors plus la periode qu'elle pretend couvrir.
PART_TROUS_MAX = 0.10


def eligibilite(
    politique: dict,
    n_obs: int,
    annees_disponibles: float,
    dilution_dans_la_fenetre: bool,
    anomalies_bloquantes: list[str],
    n_obs_attendues: int,
) -> list[str]:
    """Rend la liste des motifs de disqualification. Vide = eligible."""
    motifs: list[str] = []

    if politique["model"] == "none":
        motifs.append("policy_excluded")

    if annees_disponibles < (politique["min_years"] or 0):
        motifs.append("short_history")

    if n_obs < politique["min_observations"]:
        motifs.append("insufficient_data")

    if dilution_dans_la_fenetre:
        motifs.append("dilution_detected")

    if anomalies_bloquantes:
        motifs.append("data_quality")

    if n_obs_attendues > 0 and 1 - n_obs / n_obs_attendues > PART_TROUS_MAX:
        motifs.append("too_many_gaps")

    return motifs


def fenetre(as_of: date, window_years: int | None, premiere_barre: date) -> date:
    """Debut de la fenetre glissante.

    Glissante et non expansive : une fenetre expansive donne un poids croissant
    au passe lointain et ne s'adapte jamais a un changement de regime.
    """
    if window_years is None:
        return premiere_barre
    debut = date(as_of.year - window_years, as_of.month, min(as_of.day, 28))
    return max(debut, premiere_barre)


def verdict(
    motifs: list[str],
    n_obs: int,
    politique: dict,
    r_squared: float | None,
    dfgls_rejette: bool | None,
    dfgls_stat: float | None,
    dfgls_crit_5: float | None,
) -> tuple[str, list[str]]:
    """Rend ('good'|'weak'|'rejected', motifs complets) - doc 03 SS3.3.

    Les motifs sont rendus avec le verdict, et non a cote : un fit rejete sans
    raison enregistree est inexploitable trois mois plus tard, quand personne ne
    se souvient de la regle qui l'a ecarte.

    `weak` doit etre le cas majoritaire, et l'interface doit l'assumer. Si la
    repartition sortait a 80% de `good`, ce serait le signe d'un bug, pas d'un
    univers exceptionnel. Un systeme honnete dit qu'il ne sait pas la plupart du
    temps.
    """
    motifs = list(motifs)
    if motifs:
        return "rejected", motifs

    # « DF-GLS tres loin du rejet » : a moins de la moitie de la valeur critique
    # en distance, le test ne dit pas « on ne sait pas », il dit « non ». La
    # serie se comporte comme une marche aleatoire, la droite n'a pas de sens.
    if dfgls_stat is not None and dfgls_crit_5 is not None and dfgls_stat > dfgls_crit_5 / 2:
        motifs.append("non_stationary")
        return "rejected", motifs

    if (dfgls_rejette
            and n_obs >= politique["min_observations"]
            and r_squared is not None and r_squared >= 0.5):
        return "good", motifs

    # Pourquoi pas `good` : l'information la plus consultee de l'ecran.
    if not dfgls_rejette:
        motifs.append("unit_root_not_rejected")
    if r_squared is not None and r_squared < 0.5:
        motifs.append("low_r_squared")
    if n_obs < politique["min_observations"]:
        motifs.append("few_observations")
    return "weak", motifs
