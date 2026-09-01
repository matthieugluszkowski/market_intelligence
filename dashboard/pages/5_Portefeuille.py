"""Portefeuille et paper trading (doc 11, écrans 8 à 10).

Principes portés par cet écran — les deux premiers viennent de la spécification,
le troisième d'un défaut constaté à l'usage :

- **La thèse avant le montant.** Décider combien avant de dire pourquoi inverse
  le raisonnement. Le formulaire suit l'ordre mode → titre → thèse → quantité,
  et la thèse s'écrit **en regard** de ce que le système affirme aujourd'hui.
- **Le réel et le fictif ne partagent jamais un chiffre.** Pas une étiquette
  dans un coin de tableau : deux sections, chacune avec ses totaux. Les colonnes
  sont identiques pour rester comparables — comparer n'est pas agréger.
- **Le support n'existe que pour le réel.** Un support (PEA, CTO…) sert à trois
  choses vérifiables : l'éligibilité géographique, le plafond de versements, la
  comparaison à fiscalité identique. En paper trading, la notion n'a aucun sens :
  l'écran ne la montre pas. Le support reste une colonne du tableau réel, jamais
  un onglet — une concentration sur un seul support doit se voir d'un coup d'œil.
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

from dashboard import data, definitions  # noqa: E402
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
    ["Positions", "Prendre une position", "Supports (réglages)"])

COLONNES_FORMAT = {
    "%": st.column_config.NumberColumn("%", format="%+.1f%%"),
    "Rdt total": st.column_config.NumberColumn(
        "Rdt total", format="%+.1f%%",
        help="Dividendes réinvestis, via `factor_total` — la seule mesure "
             "économiquement juste."),
    "z entrée": st.column_config.NumberColumn(
        format="%+.2f", help="z-score figé le jour de l'ouverture."),
    "z actuel": st.column_config.NumberColumn(
        format="%+.2f", help="z-score du dernier calcul hebdomadaire."),
}


def lignes_valorisees(rows: pd.DataFrame, courant: pd.Series,
                      avec_support: bool) -> tuple[list[dict], dict]:
    """Valorise chaque position et rend (lignes d'affichage, totaux)."""
    lignes, totaux = [], {"investi": 0.0, "valeur": 0.0}
    with connect_direct() as conn, conn.cursor() as cur:
        for _, position in rows.iterrows():
            v = P.valorise(cur, position.to_dict(), AUJOURDHUI)
            code = position["internal_code"]
            ligne = {
                "Titre": position["name"],
                "Qté": v.quantite,
                "PRU": round(v.prix_de_revient, 2),
                "Cours": round(v.cours, 2) if v.cours else None,
                "Investi": round(v.montant_investi, 2),
                "Valeur": round(v.valeur, 2) if v.valeur else None,
                # `is not None` et pas la verite de la valeur : une plus-value
                # exactement nulle est un fait, pas une absence de mesure.
                # Les pourcentages sont portes en points (× 100) : le format
                # `%+.1f%%` de `column_config` ecrit un signe pourcent, il ne
                # convertit pas une fraction - 0,0092 s'affichait « +0,0 % ».
                "+/- value": (round(v.plus_value, 2)
                              if v.plus_value is not None else None),
                "%": (round(v.plus_value_pct * 100, 2)
                      if v.plus_value_pct is not None else None),
                "Rdt total": (round(v.rendement_total_pct * 100, 2)
                              if v.rendement_total_pct is not None else None),
                "z entrée": (round(float(position["z_at_entry"]), 2)
                             if pd.notna(position["z_at_entry"]) else None),
                "z actuel": (round(float(courant.loc[code]), 2)
                             if code in courant.index else None),
                "Jours": v.jours,
                "Thèse": ("à relire" if position["review_at"]
                          and position["review_at"] <= AUJOURDHUI else ""),
            }
            if avec_support:
                # Le support reste une colonne, jamais un onglet : une
                # concentration sur un seul support doit se voir d'un coup d'œil.
                ligne = {"Titre": ligne.pop("Titre"),
                         "Support": position["support"] or "—", **ligne}
            lignes.append(ligne)
            totaux["investi"] += v.montant_investi
            totaux["valeur"] += v.valeur or 0
    return lignes, totaux


def section_positions(titre: str, rows: pd.DataFrame, courant: pd.Series,
                      est_paper: bool) -> None:
    """Une section = un univers (réel ou fictif), ses totaux, son tableau."""
    st.subheader(titre)
    if rows.empty:
        st.caption("Aucune position " + ("fictive." if est_paper else "réelle."))
        return

    lignes, totaux = lignes_valorisees(rows, courant, avec_support=not est_paper)

    etiquette = "fictif" if est_paper else "réel"
    plus_value = totaux["valeur"] - totaux["investi"]
    metriques = st.columns(4)
    metriques[0].metric(f"Investi ({etiquette})", f"{totaux['investi']:,.0f} €")
    metriques[1].metric(f"Valeur ({etiquette})", f"{totaux['valeur']:,.0f} €")
    metriques[2].metric(f"+/- value ({etiquette})", f"{plus_value:+,.0f} €",
                        f"{plus_value / totaux['investi']:+.1%}"
                        if totaux["investi"] else None)
    metriques[3].metric("Lignes", len(rows))

    st.dataframe(pd.DataFrame(lignes), use_container_width=True,
                 hide_index=True, column_config=COLONNES_FORMAT)

    if est_paper:
        st.markdown(
            "<div class='avertissement'>Le paper trading <b>mesure la méthode, "
            "pas l'investisseur</b> : il supprime la peur de la perte, la "
            "tentation de vendre au creux, l'attente sans rien faire. Ses "
            "chiffres qualifient la méthode ; ils ne prédisent pas ce qu'on "
            "obtiendrait réellement.</div>", unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
# Écran 8 - Les positions
# --------------------------------------------------------------------------- #
with onglet_lignes:
    ouvertes = positions[positions["closed_at"].isna()]
    fermees = positions[positions["closed_at"].notna()]

    if ouvertes.empty:
        st.info("Aucune position ouverte. L'onglet **Prendre une position** en "
                "ouvre une — fictive par défaut : en phase de qualification, "
                "c'est le paper trading qui travaille.")
    else:
        as_of = data.derniere_date_de_calcul()
        courant = data.screener(as_of).set_index("internal_code")["z_score"] \
            if as_of else pd.Series(dtype=float)

        reelles = ouvertes[~ouvertes["is_paper"]]
        fictives = ouvertes[ouvertes["is_paper"]]

        # Deux sections, jamais un chiffre commun. L'ordre s'adapte à l'usage :
        # tant qu'aucune position réelle n'existe - toute la phase de
        # qualification - le paper trading passe en premier.
        sections = [("Positions réelles", reelles, False),
                    ("Paper trading — positions fictives", fictives, True)]
        if reelles.empty and not fictives.empty:
            sections.reverse()
        for titre_section, rows, est_paper in sections:
            section_positions(titre_section, rows, courant, est_paper)

        definitions.glossaire(definitions.PORTEFEUILLE,
                              "Que signifient ces colonnes ?")

        # --- Fermeture et revue de thèse (écran 10) -------------------------
        st.subheader("Fermer une position")
        st.caption("La revue de thèse se fait ici, à la fermeture, pendant qu'on "
                   "se souvient encore de ce qu'on attendait.")

        index_ouvertes = ouvertes.set_index("id")
        choix_id = st.selectbox(
            "Position", ouvertes["id"],
            format_func=lambda i: (
                f"{index_ouvertes.loc[i, 'name']}"
                + (" · fictive" if index_ouvertes.loc[i, "is_paper"]
                   else f" · {index_ouvertes.loc[i, 'support'] or '—'}")),
        )
        position = index_ouvertes.loc[choix_id]
        with connect_direct() as conn, conn.cursor() as cur:
            v = P.valorise(cur, position.to_dict(), AUJOURDHUI)
        if v.cours:
            latente = (f" · +/- value latente {v.plus_value:+,.2f}"
                       if v.plus_value is not None else "")
            st.caption(f"PRU {v.prix_de_revient:.2f} · cours {v.cours:.2f}"
                       f"{latente} · détenue {v.jours} jour(s)")
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

    # --- Corriger une saisie (écran 8 bis) -----------------------------------
    # Corriger n'est pas fermer, et l'écran doit le dire : une position fermée
    # est une décision qui compte dans la mesure de la méthode, une position
    # corrigée est une saisie qui ne décrivait pas les faits. Sans cette
    # section, la seule issue à une erreur de saisie était de la fermer — ce qui
    # inscrivait une faute de frappe au bilan comme s'il s'agissait d'un choix.
    if not positions.empty:
        st.subheader("Corriger une saisie")
        st.caption("Corriger rétablit les faits ; fermer enregistre une "
                   "décision. Chaque correction est journalisée avec son motif "
                   "— on ne réajuste pas un prix d'entrée en silence.")

        univers_positions = data.instruments()
        codes = univers_positions["internal_code"].tolist()
        noms = univers_positions.set_index("internal_code")["name"]
        index_positions = positions.set_index("id")

        id_corrige = st.selectbox(
            "Position", positions["id"], key="position_a_corriger",
            format_func=lambda i: (
                f"#{i} · {index_positions.loc[i, 'name']}"
                + (" · fictive" if index_positions.loc[i, "is_paper"]
                   else f" · {index_positions.loc[i, 'support'] or '—'}")
                + (" · fermée" if pd.notna(index_positions.loc[i, "closed_at"])
                   else "")))
        courante = index_positions.loc[id_corrige]
        st.caption(
            f"Actuellement : **{courante['name']}** · "
            f"{float(courante['quantity']):g} × {float(courante['avg_price']):.2f} "
            f"{courante['currency']} · frais {float(courante['fees']):.2f} · "
            f"ouverte le {courante['opened_at']} · prix « {courante['price_source']} »")

        if pd.notna(courante["closed_at"]):
            st.info("**Position fermée.** La rouvrir pour la corriger "
                    "réécrirait une décision déjà prise. Si la ligne était "
                    "fausse depuis le départ, la supprimer ci-dessous.")
        elif int(courante["mouvements"]) > 1:
            st.info("**Position renforcée.** Son prix de revient est la moyenne "
                    "pondérée de plusieurs achats : l'écraser à la main le "
                    "rendrait faux. Reprendre la ligne par une suppression et "
                    "une nouvelle saisie.")
        else:
            with st.form("correction"):
                # Le titre d'abord : c'est l'erreur qui rend tout le reste faux.
                # Une position valorisée contre le cours d'une autre entreprise
                # n'affiche pas un chiffre imprécis, elle affiche un chiffre
                # sans rapport.
                code_actuel = courante["internal_code"]
                options = codes if code_actuel in codes else [code_actuel, *codes]
                nouveau_titre = st.selectbox(
                    "Titre", options, index=options.index(code_actuel),
                    format_func=lambda c: f"{noms.get(c, c)} · {c}")

                index_supports = supports.set_index("id")
                ids_supports = supports["id"].tolist()
                id_actuel = (int(courante["account_id"])
                             if pd.notna(courante["account_id"]) else ids_supports[0])
                nouveau_support = st.selectbox(
                    "Support (mode)", ids_supports,
                    index=ids_supports.index(id_actuel),
                    format_func=lambda i: (
                        f"{index_supports.loc[i, 'label']}"
                        + (" — fictif" if index_supports.loc[i, "is_paper"]
                           else " — réel")),
                    help="Basculer vers le compte PAPER rend la position "
                         "fictive, et l'exclut de tous les totaux réels.")

                g, m, d = st.columns(3)
                nouvelle_date = g.date_input(
                    "Date d'ouverture",
                    value=pd.Timestamp(courante["opened_at"]).date())
                nouvelle_quantite = m.number_input(
                    "Quantité", min_value=0.0, step=1.0,
                    value=float(courante["quantity"]))
                nouveaux_frais = d.number_input(
                    "Frais", min_value=0.0, step=0.01,
                    value=float(courante["fees"]))
                nouveau_prix = st.number_input(
                    "Prix de revient unitaire", min_value=0.0, step=0.01,
                    value=float(courante["avg_price"]),
                    help="Le modifier marque la position `manual`. Inchangé sur "
                         "une position exécutée à la clôture, le prix est repris "
                         "à la source si le titre ou la date changent — sinon il "
                         "resterait celui d'une autre entreprise.")
                nouvelle_these = st.text_area(
                    "Thèse", value=courante["thesis"] or "", height=110)
                motif = st.text_input(
                    "Motif de la correction",
                    placeholder="erreur de titre à la saisie, quantité mal reportée…",
                    help=f"Obligatoire, {P.MOTIF_LONGUEUR_MIN} caractères "
                         f"minimum. Sans motif, le journal ne distingue plus "
                         f"une erreur de frappe d'un réajustement après coup.")

                if st.form_submit_button("Enregistrer la correction",
                                         type="primary"):
                    try:
                        with connect_direct() as conn, conn.cursor() as cur:
                            cur.execute("select id from instruments where "
                                        "internal_code = %s", (nouveau_titre,))
                            modifies = P.corrige(
                                cur, int(id_corrige), motif,
                                instrument_id=cur.fetchone()[0],
                                account_id=int(nouveau_support),
                                opened_at=nouvelle_date,
                                quantity=nouvelle_quantite,
                                avg_price=nouveau_prix,
                                fees=nouveaux_frais,
                                thesis=nouvelle_these)
                            conn.commit()
                        if modifies:
                            st.success("Corrigé : " + ", ".join(
                                champ for champ, _a, _n in modifies))
                            st.rerun()
                        else:
                            st.info("Rien à corriger : aucune valeur ne change.")
                    except ValueError as exc:
                        st.error(str(exc))

        # La suppression reste possible dans tous les cas, mais elle est
        # réservée à une ligne qui n'aurait jamais dû exister : une position
        # réellement détenue puis vendue se **ferme**, sinon on retire de la
        # mesure de la méthode précisément les cas qu'on aurait intérêt à
        # oublier.
        with st.expander("Supprimer cette position"):
            st.markdown(
                "<div class='avertissement'>À réserver à une ligne <b>saisie "
                "par erreur</b>. Une position réellement détenue puis vendue se "
                "<b>ferme</b> : la supprimer retirerait de la mesure de la "
                "méthode les cas qu'on aurait justement intérêt à oublier. La "
                "suppression est définitive — seule une ligne du journal "
                "subsiste.</div>", unsafe_allow_html=True)
            with st.form("suppression"):
                motif_suppression = st.text_input(
                    "Motif de la suppression",
                    placeholder="position jamais prise, doublon de saisie…")
                confirme = st.checkbox(
                    f"Je confirme la suppression définitive de la position "
                    f"#{id_corrige} — {courante['name']}")
                if st.form_submit_button("Supprimer"):
                    if not confirme:
                        st.error("Cocher la confirmation pour supprimer.")
                    else:
                        try:
                            with connect_direct() as conn, conn.cursor() as cur:
                                efface = P.supprime(cur, int(id_corrige),
                                                    motif_suppression)
                                conn.commit()
                            st.success(f"Supprimée : {efface}")
                            st.rerun()
                        except ValueError as exc:
                            st.error(str(exc))

    # --- Journal des corrections ---------------------------------------------
    journal = charge(P.CORRECTIONS)
    if not journal.empty:
        with st.expander(f"Journal des corrections ({len(journal)})"):
            st.caption("Ce que le journal rend possible : relire plus tard "
                       "qu'une ligne a été retouchée, quand, et pourquoi.")
            st.dataframe(
                pd.DataFrame({
                    "Position": journal["position_ref"].map("#{}".format),
                    "Le": pd.to_datetime(journal["corrected_at"])
                            .dt.strftime("%d/%m/%Y %H:%M"),
                    "Action": journal["kind"].map({"update": "correction",
                                                   "delete": "suppression"}),
                    "Champ": journal["field_name"].fillna("—"),
                    "Avant": journal["old_value"].fillna("—"),
                    "Après": journal["new_value"].fillna("—"),
                    "Motif": journal["reason"],
                    "État avant": journal["summary"],
                }), use_container_width=True, hide_index=True)

    # --- Positions fermées ---------------------------------------------------
    if not fermees.empty:
        with st.expander(f"Positions fermées ({len(fermees)})"):
            table = pd.DataFrame({
                "Titre": fermees["name"],
                "Mode": fermees["is_paper"].map({True: "fictive", False: "réelle"}),
                "Support": fermees.apply(
                    lambda l: "—" if l["is_paper"] else (l["support"] or "—"),
                    axis=1),
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
    univers = data.instruments()

    # Le mode d'abord : c'est LA première décision, pas un suffixe dans une
    # liste de supports. Fictif par défaut - en phase de qualification, le
    # paper trading est l'usage normal, et engager du réel doit être un choix
    # explicite, jamais un défaut.
    mode = st.radio(
        "Mode", ["paper", "reel"], horizontal=True,
        format_func=lambda m: ("Fictive — paper trading" if m == "paper"
                               else "Réelle — argent engagé"),
        help="Une position fictive s'exécute à la dernière clôture hebdomadaire "
             "connue et reste à jamais séparée du réel. Une position réelle "
             "enregistre un achat déjà passé chez votre courtier — l'outil ne "
             "passe aucun ordre.")

    support = None
    if mode == "paper":
        paper_supports = supports[supports["is_paper"]]
        if paper_supports.empty:
            st.error("Aucun support de paper trading en base — la migration 014 "
                     "aurait dû le créer. Vérifier la table `accounts`.")
        else:
            # Un seul support paper dans le cas courant : rien a choisir, rien
            # a configurer. La notion de support n'a aucun sens en fictif.
            support = (paper_supports.iloc[0] if len(paper_supports) == 1
                       else paper_supports.set_index("code").loc[st.selectbox(
                           "Compte fictif", paper_supports["code"])])
            st.caption("Exécution à la dernière clôture hebdomadaire, position "
                       "étiquetée fictive, exclue de tout total réel. Aucun "
                       "support à configurer.")
    else:
        reels = supports[~supports["is_paper"]]
        if reels.empty:
            st.info(
                "**Aucun support réel déclaré.** Un support est l'endroit où la "
                "position est réellement détenue — PEA, CTO, PER, assurance-vie. "
                "Le déclarer sert à trois choses : vérifier l'éligibilité "
                "géographique du titre (un PEA n'accepte que des émetteurs "
                "UE/EEE), suivre le plafond de versements, et comparer les "
                "performances à fiscalité identique. À créer dans l'onglet "
                "**Supports (réglages)**.")
        else:
            index_reels = reels.set_index("code")
            code_support = st.selectbox(
                "Support", reels["code"],
                format_func=lambda c: index_reels.loc[c, "label"],
                help="L'éligibilité du titre est vérifiée contre les pays "
                     "déclarés de ce support.")
            support = index_reels.loc[code_support]

    titre = None
    if support is not None:
        # **Aucun titre par défaut, délibérément.** La liste est triée par nom :
        # « 2G Energy AG » y arrive en tête et se retrouvait présélectionnée. Un
        # défaut silencieux sur ce champ ne produit pas une position imprécise,
        # il produit une position sur une autre entreprise — valorisée contre un
        # cours sans rapport. Le titre se choisit, il ne s'hérite pas.
        titre = st.selectbox(
            "Titre", univers["internal_code"], index=None,
            placeholder="Chercher un titre…",
            format_func=lambda c: (
                f"{univers.set_index('internal_code').loc[c, 'name']} · {c}"))
        if titre is None:
            st.caption("Choisir le titre pour continuer.")

    if support is not None and titre is not None:
        instrument = univers.set_index("internal_code").loc[titre]

        with connect_direct() as conn, conn.cursor() as cur:
            cur.execute("select id, country_iso2, attributes from instruments "
                        "where internal_code = %s", (titre,))
            instrument_id, pays, attrs = cur.fetchone()
            elig = P.eligibilite(pays, support["eligible_countries"], attrs)
            signal = P.signal_du_jour(cur, instrument_id, AUJOURDHUI)
            ts, cours, _f = P.dernier_cours(cur, instrument_id, AUJOURDHUI)
            deja_verse = P.versements(cur, int(support["id"]))

        if not elig.autorise:
            st.error(f"**Titre non éligible à ce support** — {elig.motif}")

        # Ce que le système affirme aujourd'hui, affiché À CÔTÉ de la thèse pour
        # qu'elle s'écrive en regard de ces chiffres, et non à leur place.
        st.markdown(f"**Ce que le système affirme aujourd'hui sur "
                    f"{instrument['name']}**")
        vignettes = st.columns(5)
        vignettes[0].metric("z-score", f"{signal.z_score:+.2f}"
                            if signal.z_score is not None else "—",
                            help="Écart à la tendance de long terme, en écarts "
                                 "types. −2 = décote rare historiquement.")
        vignettes[1].metric("Fit", signal.fit_quality or "—",
                            help="Validité statistique de la tendance : good = "
                                 "le retour vers la tendance est démontré.")
        vignettes[2].metric("Qualité", signal.quality_tier or "non qualifié",
                            help="Position concurrentielle : solid, watch, "
                                 "eroding ou unqualified. Voir la fiche "
                                 "instrument, bloc D.")
        vignettes[3].metric("Régime", signal.regime or "—",
                            help="Nature de la rente : rent, cyclical, eroding, "
                                 "no_moat ou unknown.")
        vignettes[4].metric("Demi-vie",
                            f"{signal.half_life_days / 30.44:.0f} mois"
                            if signal.half_life_days else "—",
                            help="Temps de résorption de la moitié d'un écart à "
                                 "la tendance, estimé sur l'historique.")

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
                     "connaît la suite. Un prix saisi est marqué `manual` et "
                     "distingué dans les agrégats.")
            frais = d.number_input(
                "Frais", min_value=0.0, value=0.0, step=0.01,
                help="Suivis à part, jamais noyés dans le PRU. En paper, les "
                     "simuler rapproche la mesure du réel.")

            if cours:
                montant = quantite * (prix_saisi or float(cours)) + frais
                st.caption(f"Montant : {montant:,.2f} {instrument['currency']} "
                           f"sur **{instrument['name']}**"
                           + (" — fictif" if mode == "paper" else ""))

            # Le nom de l'entreprise jusque dans le bouton : c'est la dernière
            # occasion de voir qu'on n'enregistre pas le titre qu'on croit.
            libelle_bouton = (
                f"Ouvrir la position fictive sur {instrument['name']}"
                if mode == "paper"
                else f"Enregistrer la position réelle sur {instrument['name']}")
            if st.form_submit_button(libelle_bouton, type="primary",
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

        # Le plafond n'a de sens que sur un support réel qui en déclare un.
        if mode == "reel" and support["contribution_cap"]:
            plafond = float(support["contribution_cap"])
            st.progress(min(deja_verse / plafond, 1.0))
            st.caption(
                f"Cumul des achats sur ce support : {deja_verse:,.0f} € sur "
                f"{plafond:,.0f} € déclarés. **Indicatif** : le plafond légal "
                f"porte sur les versements d'espèces, pas sur les achats de "
                f"titres — un arbitrage interne ne consomme pas de plafond alors "
                f"qu'il compte ici.")

# --------------------------------------------------------------------------- #
# Supports — des réglages qu'on visite une fois, pas un onglet de travail
# --------------------------------------------------------------------------- #
with onglet_supports:
    st.markdown(
        "**À quoi sert un support ?** C'est l'endroit où une position **réelle** "
        "est détenue — PEA, CTO, PER, assurance-vie. Le déclarer sert à trois "
        "choses, toutes vérifiables :\n"
        "- **l'éligibilité géographique** : un PEA n'accepte que des émetteurs "
        "UE/EEE, et l'outil refuse un achat non éligible avec le motif ;\n"
        "- **le plafond de versements**, suivi par support et jamais déductible "
        "d'une position isolée ;\n"
        "- **la comparaison des performances à fiscalité identique** : PEA et "
        "CTO ne se comparent pas sans le dire.\n\n"
        "Le paper trading a son support intégré (`PAPER`) : **rien à configurer "
        "pour le fictif**."
    )

    st.dataframe(
        supports[["code", "label", "kind", "broker", "currency", "is_paper",
                  "eligible_countries", "contribution_cap"]].rename(columns={
            "code": "Code", "label": "Libellé", "kind": "Type",
            "broker": "Courtier", "currency": "Devise", "is_paper": "Fictif",
            "eligible_countries": "Pays éligibles",
            "contribution_cap": "Plafond déclaré"}),
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
