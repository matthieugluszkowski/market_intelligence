"""Bandeau de portefeuille, en tete d'ecran.

Pourquoi le reel seul, et pas « le portefeuille »
--------------------------------------------------
Un en-tete se lit d'un coup d'oeil, et un coup d'oeil ne tient pas une
distinction. Y afficher un total qui melerait des euros engages et des euros
simules produirait exactement ce que le doc 11 interdit : un chiffre commun. Le
fictif garde donc sa section, avec ses propres totaux, sur l'ecran Portefeuille -
la ou on a le temps de lire l'etiquette.

Quand aucune position reelle n'existe, le bandeau ne montre pas des zeros : des
zeros se lisent comme une performance nulle alors qu'ils signifient « rien
n'est engage ». Il montre une ligne qui le dit, et renvoie au paper trading.

Pourquoi pas de rafraichissement, pas de couleur, pas de fleche
---------------------------------------------------------------
Principe I1 du doc 04 : le dashboard se consulte, il n'alerte pas. Thaler,
Tversky, Kahneman et Schwartz (1997) : plus le feedback est frequent, plus la
prise de risque diminue et plus le rendement accumule baisse. Un bandeau de
performance en haut de chaque ecran est deja a la limite de ce principe - le
garder sobre est ce qui le rend acceptable.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

PAGE_PORTEFEUILLE = "pages/5_Portefeuille.py"


def bandeau_portefeuille(positions: pd.DataFrame, lien: bool = True) -> None:
    """Quelques KPI du portefeuille **reel**, au-dessus du titre de l'ecran."""
    if positions.empty:
        return

    reelles = positions[~positions["is_paper"]]
    if reelles.empty:
        fictives = len(positions)
        st.caption(
            f"Portefeuille : **aucune position reelle** — "
            f"{fictives} position(s) fictive(s) en paper trading. "
            f"[Ouvrir le portefeuille]({PAGE_PORTEFEUILLE})"
            if lien else "Portefeuille : aucune position reelle.")
        return

    investi = float(reelles["investi"].sum())
    valeur = float(reelles["valeur"].fillna(0).sum())
    plus_value = valeur - investi
    a_relire = int((pd.to_datetime(reelles["review_at"])
                    <= pd.Timestamp.today()).sum())

    vignettes = st.columns(5)
    vignettes[0].metric("Portefeuille réel — investi", f"{investi:,.0f} €")
    vignettes[1].metric("Valeur", f"{valeur:,.0f} €")
    vignettes[2].metric("+/- value latente", f"{plus_value:+,.0f} €",
                        f"{plus_value / investi:+.1%}" if investi else None,
                        delta_color="off")
    vignettes[3].metric("Lignes", len(reelles))
    # Le nombre de theses a relire est le seul chiffre du bandeau qui appelle une
    # action. Il vaut mieux qu'il soit la que dans une notification : on le voit
    # en passant, on n'est pas interrompu par lui.
    vignettes[4].metric("Thèses à relire", a_relire)

    st.caption(
        "Latente : rien n'est acquis avant la vente. Le paper trading a ses "
        "propres totaux, jamais melanges a ceux-ci — "
        f"[voir le portefeuille]({PAGE_PORTEFEUILLE})."
        if lien else
        "Latente : rien n'est acquis avant la vente. Le paper trading a ses "
        "propres totaux, jamais melanges a ceux-ci.")


def detentions(positions: pd.DataFrame) -> pd.DataFrame:
    """Une ligne par titre detenu, indexee par `internal_code`.

    Deux positions ouvertes sur le meme titre - un renfort loge a part, un
    support reel et un support fictif - se cumulent en quantite mais **pas** en
    prix : le prix de revient d'un titre est la moyenne ponderee de ses achats,
    et la somme de deux PRU ne veut rien dire.
    """
    if positions.empty:
        return pd.DataFrame(
            columns=["quantite", "prix_de_revient", "investi", "valeur",
                     "plus_value_pct", "reel", "fictif"]).rename_axis("internal_code")

    lignes = positions.copy()
    lignes["cout"] = lignes["quantity"] * lignes["avg_price"]
    groupe = lignes.groupby("internal_code")
    resume = pd.DataFrame({
        "quantite": groupe["quantity"].sum(),
        "investi": groupe["investi"].sum(),
        "valeur": groupe["valeur"].sum(min_count=1),
        "reel": groupe["is_paper"].apply(lambda s: bool((~s).any())),
        "fictif": groupe["is_paper"].apply(lambda s: bool(s.any())),
    })
    resume["prix_de_revient"] = groupe["cout"].sum() / resume["quantite"]
    resume["plus_value_pct"] = (resume["valeur"] - resume["investi"]) / resume["investi"]
    return resume
