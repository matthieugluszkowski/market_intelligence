"""Portefeuille et paper trading (doc 11, écrans 8 à 10).

Trois principes portés par cet écran, tous issus de la spécification :

- **La thèse avant le montant.** Décider combien avant de dire pourquoi inverse
  le raisonnement. Le formulaire suit donc l'ordre titre → support → thèse →
  quantité, et la thèse s'écrit **en regard** de ce que le système affirme
  aujourd'hui, affiché à côté.
- **Le support est une colonne, jamais un onglet.** Voir en un coup d'œil qu'une
  concentration porte sur un seul support est utile ; le découper en onglets la
  masque.
- **Aucun écran n'agrège du réel et du fictif dans le même chiffre.** Les
  positions fictives sont étiquetées et sorties des totaux.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# Rechargement des modules du projet si leurs sources ont change. **Doit rester
# avant les imports qui suivent.**
from dashboard.rechargement import recharge_si_modifie  # noqa: E402

recharge_si_modifie()

from dashboard import data  # noqa: E402
from dashboard.theme import css, palette  # noqa: E402
from market_intelligence import portfolio as P  # noqa: E402
from market_intelligence.db import connect_direct  # noqa: E402

st.set_page_config(page_title="Portefeuille", page_icon="◧", layout="wide")

sombre = st.sidebar.toggle("Mode sombre", value=False)
p = palette(sombre)
st.markdown(css(p), unsafe_allow_html=True)

AUJOURDHUI = date.today()


def charge(sql: str, params=None) -> pd.DataFrame:
    with connect_direct() as conn, conn.cursor() as cur:
        cur.execute(sql, params or {})
        return pd.DataFrame(cur.fetchall(), columns=[c.name for c in cur.description])


st.title("Portefeuille")
st.caption("Le système propose, vous décidez. Aucun ordre n'est passé, aucun "
           "courtier n'est contacté, aucune fiscalité n'est calculée.")

supports = charge(P.SUPPORTS)
positions = charge(P.POSITIONS, {"ouvertes": False})

onglet_lignes, onglet_ouvrir, onglet_supports = st.tabs(
    ["Positions", "Prendre une position", "Supports"])

# --------------------------------------------------------------------------- #
# Écran 8 - Les positions
# --------------------------------------------------------------------------- #
with onglet_lignes:
    ouvertes = positions[positions["closed_at"].isna()]
    fermees = positions[positions["closed_at"].notna()]

    if ouvertes.empty:
        st.info("Aucune position ouverte. L'onglet **Prendre une position** en "
                "ouvre une, réelle ou fictive.")
    else:
        lignes, totaux_reels = [], {"investi": 0.0, "valeur": 0.0}
        with connect_direct() as conn, conn.cursor() as cur:
            for _, position in ouvertes.iterrows():
                v = P.valorise(cur, position.to_dict(), AUJOURDHUI)
                lignes.append({
                    "": "fictif" if position["is_paper"] else "",
                    "Titre": position["name"],
                    "Support": position["support"] or "—",
                    "Qté": v.quantite,
                    "PRU": round(v.prix_de_revient, 2),
                    "Cours": round(v.cours, 2) if v.cours else None,
                    "Investi": round(v.montant_investi, 2),
                    "Valeur": round(v.valeur, 2) if v.valeur else None,
                    "+/- value": round(v.plus_value, 2) if v.plus_value else None,
                    "%": round(v.plus_value_pct, 4) if v.plus_value_pct else None,
                    "Rdt total": (round(v.rendement_total_pct, 4)
                                  if v.rendement_total_pct is not None else None),
                    "z entrée": (round(float(position["z_at_entry"]), 2)
                                 if pd.notna(position["z_at_entry"]) else None),
                    "z actuel": None,
                    "Jours": v.jours,
                    "Thèse": ("à relire" if position["review_at"]
                              and position["review_at"] <= AUJOURDHUI else ""),
                })
                if not position["is_paper"]:
                    totaux_reels["investi"] += v.montant_investi
                    totaux_reels["valeur"] += v.valeur or 0

        as_of = data.derniere_date_de_calcul()
        courant = data.screener(as_of).set_index("internal_code")["z_score"] \
            if as_of else pd.Series(dtype=float)
        for ligne, (_, position) in zip(lignes, ouvertes.iterrows()):
            code = position["internal_code"]
            if code in courant.index:
                ligne["z actuel"] = round(float(courant.loc[code]), 2)

        # Les totaux ne portent que sur le reel : agreger du fictif dans le meme
        # chiffre fabriquerait un portefeuille fantome dont on mesure la
        # performance sans y avoir engage d argent.
        if totaux_reels["investi"]:
            hauts = st.columns(4)
            plus_value = totaux_reels["valeur"] - totaux_reels["investi"]
            hauts[0].metric("Investi (réel)", f"{totaux_reels['investi']:,.0f} €")
            hauts[1].metric("Valeur (réel)", f"{totaux_reels['valeur']:,.0f} €")
            hauts[2].metric("+/- value", f"{plus_value:+,.0f} €",
                            f"{plus_value / totaux_reels['investi']:+.1%}")
            hauts[3].metric("Lignes", f"{(~ouvertes['is_paper']).sum()} réelles · "
                                      f"{ouvertes['is_paper'].sum()} fictives")

        st.dataframe(
            pd.DataFrame(lignes), use_container_width=True, hide_index=True,
            column_config={
                "%": st.column_config.NumberColumn("%", format="%+.1f%%"),
                "Rdt total": st.column_config.NumberColumn(
                    "Rdt total", format="%+.1f%%",
                    help="Dividendes réinvestis, via `factor_total` — la seule "
                         "mesure économiquement juste."),
                "z entrée": st.column_config.NumberColumn(format="%+.2f"),
                "z actuel": st.column_config.NumberColumn(format="%+.2f"),
            },
        )

        st.markdown(
            "<div class='avertissement'><b>Les totaux ne portent que sur le "
            "réel.</b> Agréger du fictif dans le même chiffre fabriquerait un "
            "portefeuille fantôme dont on mesurerait la performance sans y avoir "
            "engagé d'argent.</div>", unsafe_allow_html=True)

        # --- Fermeture et revue de thèse (écran 10) -------------------------
        st.subheader("Fermer une position")
        st.caption("La revue de thèse se fait ici, à la fermeture, pendant qu'on "
                   "se souvient encore de ce qu'on attendait.")

        choix_id = st.selectbox(
            "Position", ouvertes["id"],
            format_func=lambda i: (
                f"{ouvertes.set_index('id').loc[i, 'name']} · "
                f"{ouvertes.set_index('id').loc[i, 'support'] or '—'}"),
        )
        position = ouvertes.set_index("id").loc[choix_id]
        st.markdown(f"**Thèse d'origine** — {position['thesis']}")

        with st.form("fermeture"):
            gauche, droite = st.columns(2)
            with gauche:
                raison = st.text_input("Raison de la sortie",
                                       placeholder="objectif atteint, thèse invalidée…")
                prix_saisi = st.number_input(
                    "Prix de sortie (0 = dernière clôture)", min_value=0.0,
                    value=0.0, step=0.01)
            with droite:
                # « On ne peut pas savoir » en premier, délibérément : une thèse
                # peut être juste et la position perdante, ou fausse et la
                # position gagnante. Forcer un verdict binaire fabriquerait de
                # l'apprentissage sur du bruit.
                verdict = st.radio(
                    "La thèse s'est-elle vérifiée ?",
                    ["indeterminable", "verifiee", "infirmee"],
                    format_func=lambda v: {
                        "indeterminable": "On ne peut pas savoir",
                        "verifiee": "Oui, elle s'est vérifiée",
                        "infirmee": "Non, elle était fausse"}[v],
                )
            revue = st.text_area("Ce que j'en retiens", height=80)

            if st.form_submit_button("Fermer la position", type="primary"):
                if not raison.strip():
                    st.error("La raison de sortie est obligatoire.")
                else:
                    with connect_direct() as conn, conn.cursor() as cur:
                        P.ferme(cur, int(choix_id), AUJOURDHUI, raison, verdict,
                                revue or None,
                                prix=prix_saisi if prix_saisi > 0 else None)
                        conn.commit()
                    st.rerun()

    # --- Positions fermées ---------------------------------------------------
    if not fermees.empty:
        with st.expander(f"Positions fermées ({len(fermees)})"):
            table = pd.DataFrame({
                "Titre": fermees["name"],
                "Support": fermees["support"],
                "Fictif": fermees["is_paper"],
                "Ouverte": fermees["opened_at"],
                "Fermée": fermees["closed_at"],
                "PRU": fermees["avg_price"].round(2),
                "Sortie": fermees["closed_price"].round(2),
                "z entrée": fermees["z_at_entry"].round(2),
                "Verdict": fermees["thesis_verdict"].map({
                    "indeterminable": "on ne peut pas savoir",
                    "verifiee": "vérifiée", "infirmee": "infirmée"}),
                "Raison": fermees["close_reason"],
            })
            st.dataframe(table, use_container_width=True, hide_index=True)
            st.markdown(
                "<div class='avertissement'><b>Dix positions ne mesurent pas une "
                "méthode.</b> La dispersion des rendements individuels est telle "
                "que la moyenne d'un petit nombre de lignes est dominée par le "
                "hasard. Le vrai jeu de validation reste <code>regression_fits</code>, "
                "qui mesure le comportement de <i>tous</i> les titres après signal — "
                "pas seulement de ceux qu'on a achetés.</div>",
                unsafe_allow_html=True)

# --------------------------------------------------------------------------- #
# Écran 9 - Prendre une position
# --------------------------------------------------------------------------- #
with onglet_ouvrir:
    if supports.empty:
        st.warning("Aucun support. En créer un dans l'onglet **Supports**.")
    else:
        univers = data.instruments()
        gauche, droite = st.columns(2)
        with gauche:
            titre = st.selectbox(
                "Titre", univers["internal_code"],
                format_func=lambda c: univers.set_index("internal_code").loc[c, "name"])
        with droite:
            support_code = st.selectbox(
                "Support", supports["code"],
                format_func=lambda c: (
                    f"{supports.set_index('code').loc[c, 'label']}"
                    f"{'  (fictif)' if supports.set_index('code').loc[c, 'is_paper'] else ''}"))

        support = supports.set_index("code").loc[support_code]
        instrument = univers.set_index("internal_code").loc[titre]

        with connect_direct() as conn, conn.cursor() as cur:
            cur.execute("select id, country_iso2 from instruments "
                        "where internal_code = %s", (titre,))
            instrument_id, pays = cur.fetchone()
            elig = P.eligibilite(pays, support["eligible_countries"])
            signal = P.signal_du_jour(cur, instrument_id, AUJOURDHUI)
            ts, cours, _f = P.dernier_cours(cur, instrument_id, AUJOURDHUI)
            deja_verse = P.versements(cur, int(support["id"]))

        if not elig.autorise:
            st.error(f"**Titre non éligible à ce support** — {elig.motif}")

        # Ce que le système affirme aujourd'hui, affiché À CÔTÉ de la thèse pour
        # qu'elle s'écrive en regard de ces chiffres, et non à leur place.
        st.markdown("**Ce que le système affirme aujourd'hui**")
        vignettes = st.columns(5)
        vignettes[0].metric("z-score", f"{signal.z_score:+.2f}"
                            if signal.z_score is not None else "—")
        vignettes[1].metric("Fit", signal.fit_quality or "—")
        vignettes[2].metric("Qualité", signal.quality_tier or "non qualifié")
        vignettes[3].metric("Régime", signal.regime or "—")
        vignettes[4].metric("Demi-vie",
                            f"{signal.half_life_days / 30.44:.0f} mois"
                            if signal.half_life_days else "—")

        stats = signal.regime_stats or {}
        if stats.get("n_episodes"):
            st.caption(
                f"Sur ce titre : {stats['n_episodes']} épisodes sous −2σ, durée "
                f"médiane {stats['duree_mediane_semaines']:.0f} semaines, maximum "
                f"{stats['duree_max_semaines']}, creux supplémentaire médian "
                f"{stats['drawdown_median_apres_seuil']:+.1%}. "
                f"**In-sample : cela décrit le passé, ce n'est pas une probabilité.**")

        with st.form("ouverture"):
            these = st.text_area(
                f"Thèse — pourquoi j'achète ({P.THESE_LONGUEUR_MIN} caractères minimum)",
                height=120,
                placeholder="Ce que j'attends, à quel horizon, et ce qui me ferait "
                            "changer d'avis…")
            g, m, d = st.columns(3)
            quantite = g.number_input("Quantité", min_value=0.0, value=0.0, step=1.0)
            prix_saisi = m.number_input(
                f"Prix (0 = clôture du {ts})" if ts else "Prix",
                min_value=0.0, value=0.0, step=0.01,
                help="La clôture par défaut évite le biais rétrospectif : on "
                     "choisit toujours un meilleur point d'entrée quand on "
                     "connaît la suite.")
            frais = d.number_input("Frais", min_value=0.0, value=0.0, step=0.01)

            if cours:
                montant = quantite * (prix_saisi or float(cours)) + frais
                st.caption(f"Montant : {montant:,.2f} {instrument['currency']}")

            if st.form_submit_button("Ouvrir la position", type="primary",
                                     disabled=not elig.autorise):
                try:
                    with connect_direct() as conn, conn.cursor() as cur:
                        _id, source = P.ouvre(
                            cur, instrument_id, int(support["id"]), quantite,
                            these, AUJOURDHUI,
                            prix=prix_saisi if prix_saisi > 0 else None,
                            frais=frais)
                        conn.commit()
                    st.success(f"Position ouverte, prix « {source} ».")
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))

        if support["contribution_cap"]:
            plafond = float(support["contribution_cap"])
            st.progress(min(deja_verse / plafond, 1.0))
            st.caption(
                f"Cumul des achats sur ce support : {deja_verse:,.0f} € sur "
                f"{plafond:,.0f} € déclarés. **Indicatif** : le plafond légal "
                f"porte sur les versements d'espèces, pas sur les achats de "
                f"titres — un arbitrage interne ne consomme pas de plafond alors "
                f"qu'il compte ici.")

# --------------------------------------------------------------------------- #
# Supports
# --------------------------------------------------------------------------- #
with onglet_supports:
    st.dataframe(
        supports[["code", "label", "kind", "broker", "currency", "is_paper",
                  "eligible_countries", "contribution_cap"]],
        use_container_width=True, hide_index=True)

    st.markdown(
        "<div class='avertissement'>Les paramètres d'un support — pays éligibles, "
        "plafond — sont <b>déclarés par vous</b> et à vérifier auprès de votre "
        "établissement. Le système les traite comme une configuration, jamais "
        "comme une vérité fiscale : il ne calcule aucun impôt, aucune durée de "
        "détention et aucune condition de retrait.</div>",
        unsafe_allow_html=True)

    with st.form("nouveau_support"):
        st.caption("Ajouter un support")
        g, m, d = st.columns(3)
        code = g.text_input("Code", placeholder="PEA_CM")
        libelle = m.text_input("Libellé", placeholder="PEA Crédit Mutuel")
        genre = d.selectbox("Type", ["PEA", "PEA_PME", "PER", "CTO", "AV", "PAPER"])
        g2, m2, d2 = st.columns(3)
        courtier = g2.text_input("Courtier")
        pays_eligibles = m2.text_input(
            "Pays éligibles (codes ISO séparés par des virgules)",
            placeholder="FR,DE,NL,BE,ES,IT…",
            help="Vide = aucune restriction vérifiée.")
        plafond = d2.number_input("Plafond de versements déclaré", min_value=0.0,
                                  value=0.0, step=1000.0)

        if st.form_submit_button("Créer"):
            if not code.strip() or not libelle.strip():
                st.error("Code et libellé sont obligatoires.")
            else:
                liste = [c.strip().upper() for c in pays_eligibles.split(",")
                         if c.strip()] or None
                with connect_direct() as conn, conn.cursor() as cur:
                    cur.execute(
                        "insert into accounts (code, label, kind, broker, "
                        "eligible_countries, contribution_cap, is_paper) "
                        "values (%s, %s, %s, %s, %s, %s, %s) "
                        "on conflict (code) do nothing",
                        (code.strip().upper(), libelle.strip(), genre,
                         courtier or None, liste,
                         plafond if plafond > 0 else None, genre == "PAPER"))
                    conn.commit()
                st.rerun()
