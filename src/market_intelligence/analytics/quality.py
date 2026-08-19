"""Position concurrentielle : leadership, rente, erosion (doc 08).

    « Il faut acheter une action de qualite, et globalement la qualite c'est la
      position concurrentielle. »  - Marie de Raismes

Ce qu'on mesure, et ce qu'on refuse de mesurer
-----------------------------------------------
« Position concurrentielle durable » contient deux mots qui posent deux problemes
de nature differente. La **position** se mesure par proxies. La **durabilite**
est une affirmation sur l'avenir, et aucune donnee historique ne la demontre :
Kodak affichait un ROIC eleve et une marque indepassable en 1998, Nokia detenait
40% du mobile mondial en 2007.

On ne mesure donc pas la durabilite. On mesure la position et on teste
**l'absence d'erosion**. C'est une refutation, pas une confirmation - et c'est
intellectuellement le seul geste disponible.

Les trois questions, dans cet ordre
------------------------------------
Q1 l'entreprise est-elle leader ; Q2 cette position produit-elle de la rente ;
Q3 cette rente s'erode-t-elle. **La troisieme est celle qui decide, et c'est
celle que personne n'affiche** : un leader dont la rente s'erode depuis cinq ans
n'est pas un leader decote, c'est un leader en train de perdre sa position, et le
marche a probablement raison de le vendre.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

# Seuil de cout du capital. Fixe et conventionnel plutot qu'un WACC estime par
# titre : un WACC demande un beta, une prime de risque et un cout de la dette,
# trois parametres bruites qui produisent ensemble une fausse precision
# remarquable. Deux analystes obtiennent 7% et 11% sur la meme societe, et
# l'ecart de rente change de signe.
SEUIL_COUT_DU_CAPITAL = 0.08

# « Significativement negative » : intervalle de confiance a 90% excluant zero.
# Sur cinq points le test est peu puissant et ne detectera que les erosions
# franches. C'est assume : mieux vaut manquer une erosion douteuse que crier au
# loup sur du bruit.
NIVEAU_DE_CONFIANCE = 0.90
T_90 = {1: 6.314, 2: 2.920, 3: 2.353, 4: 2.132, 5: 2.015, 6: 1.943, 7: 1.895,
        8: 1.860, 9: 1.833, 10: 1.812, 11: 1.796, 12: 1.782}

# Au-dela de ce coefficient de variation, le ROIC n'est pas instable : il est
# cyclique. Ce n'est pas une absence de qualite, c'est un autre regime.
VOLATILITE_CYCLIQUE = 0.35

# Mais la volatilite seule ne suffit pas a reconnaitre un cycle, et une premiere
# version s'y est laissee prendre : un ROIC qui s'effondre de 18% a 2% en cinq
# ans a une volatilite tres elevee, et sortait donc en `cyclical` - donc protege
# du verdict d'erosion. C'etait exactement le cas Atos, classe comme un bas de
# cycle a acheter.
#
# Un cycle redescend **et remonte** ; un effondrement ne fait que descendre. Le
# discriminant est la part de variance expliquee par la tendance : au-dela de ce
# seuil, la serie est monotone et il n'y a pas de cycle, seulement une pente.
R2_TENDANCE_MONOTONE = 0.70

PEREMPTION_MOIS = 18


# --------------------------------------------------------------------------- #
# Outillage statistique
# --------------------------------------------------------------------------- #
@dataclass
class Pente:
    valeur: float | None = None
    borne_basse: float | None = None
    borne_haute: float | None = None
    r_squared: float | None = None
    n: int = 0

    @property
    def negative_significative(self) -> bool:
        """Pente negative dont l'intervalle a 90% exclut zero."""
        return (self.valeur is not None and self.borne_haute is not None
                and self.valeur < 0 and self.borne_haute < 0)


def pente_avec_intervalle(serie: list[tuple]) -> Pente:
    """Regression lineaire simple sur (annee, valeur), avec IC a 90% sur la pente.

    On rend l'intervalle et pas seulement le coefficient : sur cinq points, une
    pente ponctuelle negative n'est le plus souvent que du bruit, et la traiter
    comme un signal produirait une alerte d'erosion sur la moitie de l'univers.
    """
    if len(serie) < 3:
        return Pente(n=len(serie))

    xs = [float(annee.year if hasattr(annee, "year") else annee) for annee, _ in serie]
    ys = [float(v) for _, v in serie]
    n = len(xs)
    moyenne_x = sum(xs) / n
    moyenne_y = sum(ys) / n

    variance_x = sum((x - moyenne_x) ** 2 for x in xs)
    if variance_x == 0:
        return Pente(n=n)

    beta = sum((x - moyenne_x) * (y - moyenne_y) for x, y in zip(xs, ys)) / variance_x
    alpha = moyenne_y - beta * moyenne_x
    residus = [y - (alpha + beta * x) for x, y in zip(xs, ys)]

    variance_totale = sum((y - moyenne_y) ** 2 for y in ys)
    r2 = (1 - sum(r ** 2 for r in residus) / variance_totale
          if variance_totale > 0 else None)

    ddl = n - 2
    if ddl <= 0:
        return Pente(valeur=beta, r_squared=r2, n=n)
    variance_residuelle = sum(r ** 2 for r in residus) / ddl
    erreur_type = math.sqrt(variance_residuelle / variance_x) if variance_residuelle > 0 else 0.0
    t = T_90.get(ddl, 1.782)
    return Pente(valeur=beta, borne_basse=beta - t * erreur_type,
                 borne_haute=beta + t * erreur_type, r_squared=r2, n=n)


def _moyenne(valeurs: list[float]) -> float | None:
    return sum(valeurs) / len(valeurs) if valeurs else None


def _ecart_type(valeurs: list[float]) -> float | None:
    if len(valeurs) < 2:
        return None
    moyenne = sum(valeurs) / len(valeurs)
    return math.sqrt(sum((v - moyenne) ** 2 for v in valeurs) / (len(valeurs) - 1))


def _mediane(valeurs: list[float]) -> float | None:
    if not valeurs:
        return None
    ordonnees = sorted(valeurs)
    milieu = len(ordonnees) // 2
    if len(ordonnees) % 2:
        return ordonnees[milieu]
    return (ordonnees[milieu - 1] + ordonnees[milieu]) / 2


# --------------------------------------------------------------------------- #
# Q2 - la rente
# --------------------------------------------------------------------------- #
def serie_roic(f) -> list[tuple]:
    """ROIC par exercice : NOPAT / capitaux employes.

        NOPAT             = EBIT x (1 - taux d'IS effectif)
        Capitaux employes = capitaux propres + dette nette

    Un taux d'imposition hors de [0 ; 60%] est ecarte : il signale un exercice
    atypique - report deficitaire, produit exceptionnel - et non une fiscalite.
    """
    serie = []
    for annee in f.exercices:
        ebit = f.par_concept.get("ebit", {}).get(annee)
        equity = f.par_concept.get("total_equity", {}).get(annee)
        net_debt = f.par_concept.get("net_debt", {}).get(annee)
        if net_debt is None:
            dette = f.par_concept.get("total_debt", {}).get(annee)
            cash = f.par_concept.get("cash_and_equivalents", {}).get(annee)
            net_debt = dette - cash if dette is not None and cash is not None else None
        impots = f.par_concept.get("tax_expense", {}).get(annee)
        interets = f.par_concept.get("interest_expense", {}).get(annee)

        if ebit is None or equity is None or net_debt is None:
            continue
        capitaux = equity + net_debt
        if capitaux <= 0:
            continue

        taux = None
        if impots is not None and interets is not None:
            avant_impot = ebit - interets
            if avant_impot > 0:
                taux = impots / avant_impot
        if taux is None or not (0 <= taux <= 0.6):
            taux = 0.25          # taux conventionnel europeen, faute de mieux
        serie.append((annee, ebit * (1 - taux) / capitaux))
    return serie


def serie_marge_brute(f) -> list[tuple]:
    serie = []
    for annee in f.exercices:
        brut = f.par_concept.get("gross_profit", {}).get(annee)
        revenu = f.par_concept.get("revenue", {}).get(annee)
        if brut is not None and revenu not in (None, 0):
            serie.append((annee, brut / revenu))
    return serie


# --------------------------------------------------------------------------- #
# Synthese
# --------------------------------------------------------------------------- #
@dataclass
class Qualite:
    # Q1 leadership
    relative_share: float | None = None
    rank_by_revenue: int | None = None
    rank_stability_5y: float | None = None
    # Q2 rente
    roic_latest: float | None = None
    roic_mean_5y: float | None = None
    roic_volatility: float | None = None
    roic_vs_threshold: float | None = None
    roic_vs_peers: float | None = None
    persistence_years: int = 0
    gross_margin_mean: float | None = None
    gross_margin_std: float | None = None
    # Q3 erosion
    roic_slope_5y: float | None = None
    gross_margin_slope_5y: float | None = None
    share_slope_5y: float | None = None
    erosion_flags: int = 0
    # verdicts
    regime: str = "unknown"
    quality_tier: str = "unqualified"
    n_years_available: int = 0
    confidence: str = "low"
    motifs: list = field(default_factory=list)


def evalue(f, roic_median_pairs: float | None, revenus_pairs: list[float],
           groupe_complet: bool, evaluation_valide: bool,
           serie_part_relative: list[tuple] | None = None,
           regime_declare: str | None = None) -> Qualite:
    """Calcule les trois questions et rend le verdict.

    Args:
        f: fondamentaux point-in-time de l'instrument.
        roic_median_pairs: ROIC median du groupe, pour le seuil relatif. Plus
            robuste que le seuil absolu : l'essentiel des biais d'estimation est
            commun au secteur et s'annule dans la difference.
        revenus_pairs: chiffres d'affaires des pairs, pour la part relative.
        groupe_complet: le groupe contient-il un concurrent hors Europe.
        evaluation_valide: existe-t-il une evaluation qualitative non perimee.
        regime_declare: regime declare a la main, qui prime sur la detection
            automatique. Le test statistique ne sait pas distinguer la descente
            d un cycle d une erosion tant que la fenetre ne couvre pas un cycle
            complet ; sur quatre exercices, elle ne le couvre jamais.
    """
    q = Qualite()
    roic = serie_roic(f)
    marges = serie_marge_brute(f)
    q.n_years_available = len(f.exercices)

    # --- Q1 leadership ----------------------------------------------------
    revenu = f.dernier("revenue")
    if revenu is not None and revenus_pairs:
        plus_grand = max(revenus_pairs + [revenu])
        q.relative_share = revenu / plus_grand if plus_grand else None
        q.rank_by_revenue = 1 + sum(1 for r in revenus_pairs if r > revenu)

    # --- Q2 rente ----------------------------------------------------------
    if roic:
        valeurs = [v for _, v in roic]
        q.roic_latest = valeurs[-1]
        q.roic_mean_5y = _moyenne(valeurs)
        ecart_type = _ecart_type(valeurs)
        q.roic_volatility = (ecart_type / abs(q.roic_mean_5y)
                             if ecart_type is not None and q.roic_mean_5y else None)
        q.persistence_years = sum(1 for v in valeurs if v > SEUIL_COUT_DU_CAPITAL)
        q.roic_vs_threshold = q.roic_mean_5y - SEUIL_COUT_DU_CAPITAL
        if roic_median_pairs is not None:
            q.roic_vs_peers = q.roic_mean_5y - roic_median_pairs

    if marges:
        valeurs = [v for _, v in marges]
        q.gross_margin_mean = _moyenne(valeurs)
        q.gross_margin_std = _ecart_type(valeurs)

    # --- Q3 erosion --------------------------------------------------------
    pente_roic = pente_avec_intervalle(roic)
    pente_marge = pente_avec_intervalle(marges)
    pente_part = pente_avec_intervalle(serie_part_relative or [])
    q.roic_slope_5y = pente_roic.valeur
    q.gross_margin_slope_5y = pente_marge.valeur
    q.share_slope_5y = pente_part.valeur
    q.erosion_flags = sum(p.negative_significative
                          for p in (pente_roic, pente_marge, pente_part))

    q.regime = _regime(q, pente_roic, regime_declare)
    q.quality_tier, q.motifs = _tier(q, groupe_complet, evaluation_valide)
    q.confidence = ("high" if q.n_years_available >= 8
                    else "medium" if q.n_years_available >= 5 else "low")
    return q


def _regime(q: Qualite, pente_roic: Pente, declare: str | None = None) -> str:
    """rent / cyclical / eroding / no_moat / unknown (doc 08 SS4.4).

    L'ordre des tests compte. **Le cyclique est teste avant l'erosion** : Arkema,
    BMW et Beneteau echouent a tous les tests de moat classiques et sont pourtant
    des cibles legitimes. Les juger sur un ROIC ponctuel est un contresens - toute
    la question d'une boite cyclique est d'acheter en bas de cycle.
    """
    if declare:
        # La declaration manuelle prime, comme le groupe de pairs manuel prime
        # sur le sectoriel automatique (doc 08, limite L4).
        return declare
    if q.roic_mean_5y is None:
        # Cas structurel des banques et assureurs : ni EBIT ni capitaux employes
        # au sens industriel. Ce n'est pas une donnee manquante qu'un meilleur
        # provider comblerait, c'est un modele qui ne s'applique pas.
        return "unknown"
    monotone = (pente_roic.r_squared is not None
                and pente_roic.r_squared >= R2_TENDANCE_MONOTONE)
    if (q.roic_volatility is not None and q.roic_volatility > VOLATILITE_CYCLIQUE
            and not monotone):
        return "cyclical"
    if q.erosion_flags >= 2:
        return "eroding"
    if q.roic_mean_5y > SEUIL_COUT_DU_CAPITAL and q.persistence_years >= 3:
        return "rent"
    return "no_moat"


def _tier(q: Qualite, groupe_complet: bool, evaluation_valide: bool) -> tuple:
    """solid / watch / eroding / unqualified, avec les motifs du classement.

    Deux garde-fous non negociables, tous deux issus des limites du doc 08 :

    - **Aucun titre ne passe `solid` sans groupe de pairs contenant un concurrent
      hors Europe** (limite L1). Un groupe purement europeen est structurellement
      aveugle : Shark Ninja est americaine, BYD est chinoise, Revolut n'est pas
      cotee. Le screener serait d'autant plus rassurant que le titre reste leader
      dans un univers qui ne contient pas son concurrent.
    - **Aucun titre ne passe `solid` sans evaluation qualitative valide.** Le
      moat quantitatif mesure le passe : un ROIC eleve est la trace d'une
      barriere qui a existe, il ne dit rien de sa resistance a une rupture. Seule
      la jambe qualitative peut ecrire « cette barriere est menacee par X », et X
      n'est jamais dans les comptes.
    """
    motifs: list[str] = []

    if q.roic_mean_5y is None:
        return "unqualified", ["fondamentaux_insuffisants"]

    # Le cyclique est teste AVANT l'erosion, et l'ordre n'est pas indifferent.
    #
    # Une premiere version testait l'erosion d'abord et classait Arkema en
    # `eroding`, donc en value trap une fois croise avec un z-score bas. Le doc 08
    # dit exactement l'inverse : *Arkema - non applicable : regime cyclique - bas
    # de cycle, pas erosion*. Une pente de ROIC negative sur un cyclique mesure la
    # descente du cycle, pas la perte d'une barriere, et *toute la question d'une
    # boite cyclique, c'est d'acheter en bas de cycle*. Classer cela en value trap
    # revient a exclure precisement le moment ou il faut regarder.
    #
    # L'erosion d'un cyclique se mesure de pic a pic (doc 08 SS4.4). Sur quatre a
    # cinq exercices, aucun pic a pic n'est identifiable : on ne la mesure donc
    # pas, et on ne pretend pas le contraire.
    if q.regime == "cyclical":
        motifs.append("regime_cyclique_juge_sur_moyenne_de_cycle")
        if q.erosion_flags:
            motifs.append("erosion_non_mesuree_sur_cyclique_historique_trop_court")
        return "watch", motifs

    if q.erosion_flags >= 2:
        motifs.append(f"erosion_{q.erosion_flags}_pentes_sur_3")
        return "eroding", motifs

    if q.roic_mean_5y <= SEUIL_COUT_DU_CAPITAL:
        motifs.append("roic_sous_le_cout_du_capital")
        return "watch", motifs

    if q.persistence_years < 3:
        motifs.append(f"rente_peu_persistante_{q.persistence_years}_exercices")
        return "watch", motifs

    if q.erosion_flags == 1:
        motifs.append("une_pente_d_erosion")
        return "watch", motifs

    if not groupe_complet:
        motifs.append("groupe_de_pairs_sans_concurrent_hors_europe")
        return "watch", motifs

    if not evaluation_valide:
        motifs.append("evaluation_qualitative_absente_ou_perimee")
        return "unqualified", motifs

    return "solid", motifs


def quadrant(quality_tier: str, z_score: float | None,
             seuil_decote: float = -1.5, seuil_cher: float = 1.0) -> str:
    """Croisement qualite x prix (doc 08 SS6).

    Le quadrant `value_trap` est **affiche, pas masque** : c'est la liste des
    titres qui ont l'air d'opportunites et n'en sont pas, et c'est la qu'on perd
    de l'argent - pas dans le quadrant « a eviter », qu'on n'achete jamais.
    """
    if z_score is None or quality_tier == "unqualified":
        return "unqualified"
    decote = z_score <= seuil_decote
    cher = z_score >= seuil_cher
    if quality_tier in ("solid", "watch"):
        if decote:
            return "target" if quality_tier == "solid" else "watchlist"
        if cher:
            return "watchlist"
        return "watchlist"
    if quality_tier == "eroding":
        return "value_trap" if decote else "avoid"
    return "unqualified"
