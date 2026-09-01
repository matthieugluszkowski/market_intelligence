"""Ecran screener (doc 04 SS3, ecran 1).

    streamlit run dashboard/Screener.py

Trois principes portes par cet ecran :

- **I1, le silence est une fonctionnalite.** Aucune notification, aucun
  rafraichissement temps reel, aucun ticker clignotant. Le dashboard se
  consulte, il n'alerte pas. Thaler, Tversky, Kahneman et Schwartz (1997) ont
  montre que plus le feedback est frequent, plus la prise de risque diminue et
  plus le rendement accumule baisse : un outil qui augmente la frequence de
  consultation detruit ce qu'il pretend ameliorer.
- **I2, l'incertitude est affichee.** Un fit `weak` s'affiche `weak`, avec sa
  raison. Le cas majoritaire sera « on ne sait pas trancher », et l'interface
  doit rendre ca normal plutot que honteux.
- **I3, toute visualisation a un jumeau tabulaire.**
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Rechargement des modules du projet si leurs sources ont change. **Doit rester
# avant les imports qui suivent** : Streamlit garde les modules importes en cache
# et une purge posterieure laisserait coexister deux versions d une meme classe.
from dashboard.rechargement import recharge_si_modifie  # noqa: E402

recharge_si_modifie()

from dashboard import data, entete, navigation  # noqa: E402
from dashboard.theme import css, palette, statut  # noqa: E402

st.set_page_config(page_title="Screener - market intelligence",
                   page_icon="◧", layout="wide")


PARIS = ZoneInfo("Europe/Paris")
CYCLE_HEURES = 8
# Une heure de tolerance au-dela du cycle : un passage dure une dizaine de
# minutes, donc au-dela de 9 h c'est qu'un passage a ete manque, pas qu'il est
# en cours.
SEUIL_RETARD = timedelta(hours=CYCLE_HEURES + 1)

# La demi-vie est stockee en jours ; en mois elle se compare a un horizon
# de detention, ce que 493 jours ne fait pas.
JOURS_PAR_MOIS = 365.25 / 12


def horodate(instant) -> str:
    return instant.astimezone(PARIS).strftime("%d/%m/%Y a %Hh%M")


def age(instant) -> str:
    """Duree ecoulee, nue : « 2 jours », « 8 h », « 12 min »."""
    delta = datetime.now(timezone.utc) - instant
    heures, reste = divmod(int(delta.total_seconds()), 3600)
    if heures >= 48:
        return f"{heures // 24} jours"
    return f"{heures} h" if heures else f"{reste // 60} min"


def dernier_passage(etat: pd.DataFrame, job: str):
    """Ligne du dernier passage d'un job, ou None s'il n'a jamais tourne."""
    lignes = etat[etat["job_name"] == job]
    if lignes.empty:
        return None
    ligne = lignes.iloc[0]
    return ligne if pd.notna(ligne["finished_at"]) else None


def barre_laterale() -> bool:
    st.sidebar.title("market intelligence")
    sombre = st.sidebar.toggle("Mode sombre", value=False)
    st.sidebar.caption(
        "Le mode sombre est un jeu de valeurs choisi pour la surface sombre, "
        "pas une inversion du mode clair."
    )
    return sombre


sombre = barre_laterale()
p = palette(sombre)
st.markdown(css(p), unsafe_allow_html=True)

as_of = data.derniere_date_de_calcul()
if as_of is None:
    st.error("Aucune regression en base. Lancer `python scripts/compute_fits.py`.")
    st.stop()

frame = data.screener(as_of)
portefeuille = data.portefeuille()
detenus = entete.detentions(portefeuille)

entete.bandeau_portefeuille(portefeuille)

st.title("Screener")

# --------------------------------------------------------------------------- #
# Fraicheur des donnees. Deux dates, et elles ne disent pas la meme chose :
# celle des cours ingeres, celle du calcul qui a produit les z-scores affiches.
# Un ecran qui n'afficherait que la seconde laisserait un cron arrete depuis
# trois semaines ressembler a un cron en bonne sante.
# --------------------------------------------------------------------------- #
etat = data.fraicheur()
cours = dernier_passage(etat, "backfill_prices")
calcul = dernier_passage(etat, "compute_fits")

morceaux = []
if cours is not None:
    morceaux.append(f"**Donnees actualisees le {horodate(cours['finished_at'])}** "
                    f"(il y a {age(cours['finished_at'])})")
if calcul is not None:
    morceaux.append(f"z-scores calcules le {horodate(calcul['finished_at'])}")
morceaux.append(f"cycle automatique toutes les {CYCLE_HEURES} heures")
st.markdown(" &middot; ".join(morceaux) + ".")

alerte = ""
if cours is None:
    alerte = ("<b>Aucune ingestion de cours n'a encore ete journalisee.</b> "
              "Le cycle n'a jamais tourne, ou il n'a jamais abouti.")
elif cours["status"] == "failed":
    alerte = (f"<b>Le dernier passage des cours a echoue</b> "
              f"({horodate(cours['finished_at'])}) : "
              f"{cours['error_message'] or 'motif non journalise'}. "
              f"Les z-scores ci-dessous portent donc sur des cours plus anciens.")
elif datetime.now(timezone.utc) - cours["finished_at"] > SEUIL_RETARD:
    alerte = (f"<b>Les cours n'ont pas ete actualises depuis "
              f"{age(cours['finished_at'])}</b>, "
              f"alors que le cycle passe toutes les {CYCLE_HEURES} heures. "
              f"Au moins un passage a ete manque : verifier le cron du VPS "
              f"(<code>logs/cycle-AAAAMM.log</code>).")
if alerte:
    st.markdown(f"<div class='avertissement'>{alerte}</div>", unsafe_allow_html=True)

st.caption(f"Calcul du {as_of}. Le dashboard sert a creuser un titre, "
           f"pas a surveiller : le canal principal est le rapport hebdomadaire.")

with st.expander("Detail de la derniere actualisation"):
    if etat.empty:
        st.info("Aucun passage journalise dans `ingestion_runs`.")
    else:
        detail = pd.DataFrame({
            "Etape": etat["job_name"].map(
                lambda j: data.JOBS_EN_CLAIR.get(j, j)),
            "Statut": etat["status"],
            "Termine le": etat["finished_at"].map(
                lambda t: "en cours" if pd.isna(t) else horodate(t)),
            "Age": etat["finished_at"].map(
                lambda t: "-" if pd.isna(t) else f"il y a {age(t)}"),
            "Lignes creees": etat["rows_inserted"],
            "Lignes mises a jour": etat["rows_updated"],
            "Erreur": etat["error_message"].fillna(""),
        }).sort_values("Etape")
        st.dataframe(detail, use_container_width=True, hide_index=True)
        st.caption(
            "Heures en Europe/Paris. `partial` signale qu'une etape a abouti en "
            "laissant des titres de cote - le detail est dans `ingestion_runs`."
        )

# --------------------------------------------------------------------------- #
# Une seule rangee de filtres, au-dessus de tout ce qu'ils cadrent.
# Jamais de filtre a l'interieur d'une carte de graphe.
# --------------------------------------------------------------------------- #
f0, f1, f2, f3, f4, f5 = st.columns([1.2, 1.1, 1.4, 1.3, 1.3, 1.1])

with f0:
    # Le type d'actif vient en premier parce que c'est le seul filtre qui change
    # le sens des autres : « secteur » ne veut rien dire pour une matiere
    # premiere, et une qualite de fit ne se compare pas d'une classe a l'autre.
    classes = st.multiselect(
        "Type d'actif", sorted(frame["classe_actif"].dropna().unique()),
        help="Capitalisation boursiere, matiere premiere, indice... "
             "Vide = toutes les classes.",
    )

with f1:
    seuil_z = st.slider("Seuil de z-score", -4.0, 4.0, -1.5, 0.1,
                        help="Ne garder que les titres sous ce seuil.")
with f2:
    qualites = st.multiselect(
        "Qualite du fit", ["good", "weak", "rejected"], default=["good", "weak"],
        format_func=lambda q: f"{statut(q)[1]} {q}",
    )
with f3:
    secteurs = st.multiselect("Secteur", sorted(frame["secteur"].dropna().unique()))
with f4:
    pays = st.multiselect("Pays", sorted(frame["country_iso2"].dropna().unique()))
with f5:
    persistance = st.number_input("Sem. sous seuil ≥", min_value=0, value=0, step=1)

suivis = data.codes_suivis()
c1, c2 = st.columns(2)
favoris_seuls = c1.checkbox(
    f"Watchlist seulement ({len(suivis)})", value=False,
    help="La watchlist est une selection humaine, pas un filtre calcule : elle "
         "survit au fait qu'un titre sorte des criteres du jour.",
)
# Meme raisonnement que la watchlist, en plus fort : un titre detenu doit rester
# consultable quoi qu'il arrive a son z-score. C'est meme l'inverse - un titre
# qu'on possede et qui sort des criteres du jour est precisement celui qu'on a
# le plus besoin de revoir.
detenus_seuls = c2.checkbox(
    f"Portefeuille seulement ({len(detenus)})", value=False,
    disabled=detenus.empty,
    help="Les titres detenus, meme repasses au-dessus du seuil de z-score.",
)

filtre = frame[frame["z_score"] <= seuil_z]
if favoris_seuls:
    # Le filtre de watchlist s'applique AVANT le seuil de z-score dans l'esprit,
    # mais apres dans le code : on veut voir un titre suivi meme s'il est repasse
    # au-dessus du seuil, d'ou le contournement ci-dessous.
    filtre = frame[frame["internal_code"].isin(suivis)]
if detenus_seuls:
    filtre = frame[frame["internal_code"].isin(detenus.index)]
if classes:
    filtre = filtre[filtre["classe_actif"].isin(classes)]
if qualites:
    filtre = filtre[filtre["fit_quality"].isin(qualites)]
if secteurs:
    filtre = filtre[filtre["secteur"].isin(secteurs)]
if pays:
    filtre = filtre[filtre["country_iso2"].isin(pays)]


def semaines_sous_seuil(stats) -> int:
    return int((stats or {}).get("semaines_consecutives_en_cours") or 0)


filtre = filtre.copy()
filtre["semaines"] = filtre["regime_stats"].map(semaines_sous_seuil)
if persistance:
    filtre = filtre[filtre["semaines"] >= persistance]

# --------------------------------------------------------------------------- #
# L'ecran matrice qualite x prix arrive avec L6b. En attendant, tous les titres
# sont `unqualified` - c'est leur statut reel et il doit se voir.
# --------------------------------------------------------------------------- #
if (frame["quality_tier"] == "unqualified").all():
    st.markdown(
        "<div class='avertissement'>"
        "<b>Tous les titres sont en statut <code>unqualified</code>.</b> "
        "La jambe qualite - position concurrentielle, rente, erosion - n'est pas "
        "encore calculee (lot L6b). Un signal de prix sans evaluation de la "
        "position concurrentielle est la moitie de la methode, et c'est la moitie "
        "qui produit les value traps. Ces resultats se lisent comme des candidats "
        "a verifier, pas comme des cibles."
        "</div>",
        unsafe_allow_html=True,
    )

if filtre.empty:
    st.info("Aucun titre ne passe ces filtres.")
    st.stop()

# --------------------------------------------------------------------------- #
# Tri par defaut : quadrant d'abord, puis z croissant. Trier par decote seule
# met en tete les pieges ; trier par qualite seule met en tete les titres chers.
# Tant que le quadrant est uniforme, le tri se reduit au z croissant.
# --------------------------------------------------------------------------- #
ordre_qualite = {"good": 0, "weak": 1, "rejected": 2}
filtre["_ordre"] = filtre["fit_quality"].map(ordre_qualite).fillna(3)
filtre = filtre.sort_values(["_ordre", "z_score"])

# --------------------------------------------------------------------------- #
# Ce que je possede, dans le tableau lui-meme.
#
# Trois colonnes seulement, et jamais un total : le screener classe des titres,
# il ne totalise pas un portefeuille - ce travail a son ecran. « Detenu »
# distingue le reel du fictif parce qu'une quantite nue ne dit pas si l'argent
# est engage, et c'est la seule chose qu'on veut savoir en balayant une liste.
# --------------------------------------------------------------------------- #
def mode_detention(code: str) -> str:
    if code not in detenus.index:
        return ""
    ligne = detenus.loc[code]
    if ligne["reel"] and ligne["fictif"]:
        return "◧ reel + ◌ fictif"
    return "◧ reel" if ligne["reel"] else "◌ fictif"


def colonne_detenue(code: str, champ: str):
    return detenus.loc[code, champ] if code in detenus.index else None


# --------------------------------------------------------------------------- #
# Le cours, sa tendance, l'ecart entre les deux, le temps que met cet ecart a se
# resorber : lues ensemble, ces colonnes disent combien, et sous combien de temps.
#
# La tendance est `exp(fitted_value)` - la valeur **ecrite en base** par le
# moteur. La reconstruire ici depuis l'intercept et la pente donnerait le meme
# nombre aujourd'hui et pourrait diverger en silence demain : c'est exactement la
# raison pour laquelle le graphe de la fiche ne recalcule pas sa droite non plus.
#
# Le potentiel est un ecart mesure, pas un objectif de cours. Il suppose un
# retour exact sur la droite et ne dit rien de la date de ce retour - le temps
# est porte par la demi-vie, et elle ne porte que la moitie du chemin.
# --------------------------------------------------------------------------- #
# Une colonne qui ne prend qu'une valeur sur tout l'univers n'apprend rien et
# coute une colonne. « Devise » et « Type » n'apparaissent donc qu'a partir du
# moment ou l'univers en compte plusieurs - tant qu'il est 100 % actions en
# euros, le tableau reste celui d'avant. La devise, elle, ne peut pas rester
# implicite : un prix de matiere premiere en dollars affiche « 12,34 EUR »
# serait faux, pas imprecis.
devises = frame["currency"].dropna().unique()
devise_unique = devises[0] if len(devises) == 1 else None
format_prix = f"%.2f {devise_unique}" if devise_unique is not None else "%.2f"
plusieurs_classes = frame["classe_actif"].nunique() > 1

tendance = np.exp(filtre["fitted_value"])
potentiel = (tendance / filtre["last_close"] - 1.0) * 100

table = pd.DataFrame({
    "★": filtre["internal_code"].map(lambda c: "★" if c in suivis else ""),
    "Nom": filtre["name"],
    "Code": filtre["internal_code"],
    **({"Type": filtre["classe_actif"]} if plusieurs_classes else {}),
    "Detenu": filtre["internal_code"].map(mode_detention),
    "Qte": filtre["internal_code"].map(lambda c: colonne_detenue(c, "quantite")),
    "PRU": filtre["internal_code"].map(
        lambda c: colonne_detenue(c, "prix_de_revient")),
    # En points, pas en fraction : `%+.1f%%` ecrit un signe pourcent, il ne
    # convertit pas — meme convention que « Potentiel » plus bas.
    "+/- %": filtre["internal_code"].map(
        lambda c: colonne_detenue(c, "plus_value_pct")) * 100,
    "Prix": filtre["last_close"].round(2),
    **({"Devise": filtre["currency"]} if devise_unique is None else {}),
    "z": filtre["z_score"].round(2),
    # Zero semaine sous le seuil, ce n'est pas « depuis zero semaine » : c'est
    # que le titre n'est pas sous le seuil. La case reste vide.
    "Sous -2σ depuis": filtre["semaines"].replace(0, float("nan")),
    "Tendance": tendance.round(2),
    "Potentiel": potentiel.round(1),
    "Demi-vie": (filtre["half_life_days"] / JOURS_PAR_MOIS).round(0),
    "Secteur": filtre["secteur"],
    "Pays": filtre["country_iso2"],
})

affiches = set(filtre["internal_code"]) & set(detenus.index)
manquants = len(detenus) - len(affiches)
st.caption(
    f"{len(table)} titre(s) sur {len(frame)}. "
    f"Tri : qualite du fit, puis z croissant. "
    f"**Selectionner une ligne ouvre la fiche instrument.**"
    + (f" {len(affiches)} titre(s) detenu(s) dans cette vue"
       + (f", {manquants} hors filtres — cocher « Portefeuille seulement » "
          f"pour les voir." if manquants else ".")
       if len(detenus) else ""))

navigation.tableau_vers_fiche(
    table, list(filtre["internal_code"]), cle="screener_table",
    use_container_width=True, hide_index=True,
    column_config={
        "Qte": st.column_config.NumberColumn(
            "Qte", format="%g", help="Quantite detenue, tous supports confondus."),
        "PRU": st.column_config.NumberColumn(
            "PRU", format="%.2f",
            help="Prix de revient unitaire, moyenne ponderee des achats, hors "
                 "frais."),
        "+/- %": st.column_config.NumberColumn(
            "+/- %", format="%+.1f%%",
            help="Ecart entre la valeur au dernier cours et le montant investi, "
                 "frais compris. Latente : rien n'est acquis avant la vente."),
        "Prix": st.column_config.NumberColumn(
            "Prix", format=format_prix,
            help="Dernier cours de la fenetre de calcul, ajuste des splits. "
                 "Ce n'est pas un cours temps reel : il date du dernier passage "
                 "du moteur, indique en tete de page."),
        "z": st.column_config.NumberColumn(
            "z", format="%+.2f",
            help="Ecart du cours a sa tendance, en ecarts-types des residus."),
        "Sous -2σ depuis": st.column_config.NumberColumn(
            "Sous -2σ depuis", format="%d sem.",
            help="Semaines consecutives sous -2σ dans l'episode en cours. "
                 "Vide = le titre est au-dessus du seuil aujourd'hui. Un titre qui "
                 "passe sous -2σ tous les trois ans n'envoie pas le meme signal "
                 "qu'un titre qui y reste depuis deux ans."),
        "Tendance": st.column_config.NumberColumn(
            "Tendance", format=format_prix,
            help="Valeur de la droite de regression a la date de calcul. "
                 "C'est un repere statistique, pas un objectif de cours."),
        "Potentiel": st.column_config.NumberColumn(
            "Potentiel", format="%+.1f%%",
            help="Ce que rapporterait un retour exact du cours sur sa tendance, "
                 "hors derive de la droite elle-meme. Mesure d'un ecart, pas une "
                 "prevision : rien ne garantit ce retour, ni qu'il ait lieu."),
        "Demi-vie": st.column_config.NumberColumn(
            "Demi-vie", format="%.0f mois",
            help="Temps moyen pour combler la **moitie** de cet ecart, estime sur "
                 "l'autocorrelation des residus et in-sample. En combler 90 % "
                 "demande environ 3,3 fois cette duree. Vide : estimation non "
                 "exploitable."),
    },
)

st.markdown(
    "<div class='avertissement'>"
    "Aucune colonne de score composite sur 100 : un z-score et un verdict de "
    "qualite de donnee ne s'agregent pas en une note."
    "</div>",
    unsafe_allow_html=True,
)

with st.expander("Repartition des verdicts sur l'univers"):
    repartition = frame["fit_quality"].value_counts().rename_axis("Verdict")
    resume = pd.DataFrame({
        "Titres": repartition,
        "Libelle": [statut(q)[2] for q in repartition.index],
    })
    st.dataframe(resume, use_container_width=True)
    st.caption(
        "`weak` doit etre le cas majoritaire. Une repartition a 80% de `good` "
        "serait le signe d'un bug, pas d'un univers exceptionnel."
    )

st.page_link("pages/1_Fiche_instrument.py", label="Ouvrir une fiche instrument →")
st.page_link("pages/4_Watchlist.py", label="Voir la watchlist →")
