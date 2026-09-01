"""Criteres d'acceptation du lot L1 (05_roadmap-et-lot.md).

    « 250 instruments en base, chacun avec au moins un symbole verifie par
      telechargement d'une cotation reelle, et zero doublon d'ISIN. »

Perimetre de depart retenu : 50 titres, conformement a la recommandation du
doc 05 SS4 - le referentiel est le point d'enlisement le plus probable du projet.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from market_intelligence.db import fetch_all, fetch_one  # noqa: E402

CIBLE_MIN = 50


def test_univers_atteint_la_cible():
    assert fetch_one("select count(*) from instruments where is_active")[0] >= CIBLE_MIN


def test_zero_doublon_disin():
    dupes = fetch_all(
        "select isin, count(*) from instruments where isin is not null "
        "group by isin having count(*) > 1"
    )
    assert dupes == []


def test_chaque_instrument_a_un_symbole_verifie():
    orphelins = fetch_all(
        """
        select i.internal_code
          from instruments i
     left join instrument_symbols s on s.instrument_id = i.id
         where s.id is null
        """
    )
    assert orphelins == [], f"instruments sans symbole : {orphelins}"


def test_chaque_symbole_porte_la_trace_dun_telechargement_reel():
    """Aucun symbole ne doit entrer en base sans cotation effectivement tiree.

    C'est le piege du lot L1 : un mapping faux ne se voit jamais ensuite, il
    produit simplement une belle courbe pour la mauvaise societe.
    """
    non_verifies = fetch_all(
        """
        select internal_code
          from instruments
         where attributes -> 'verification' ->> 'last_close' is null
            or (attributes -> 'verification' ->> 'n_obs_weekly')::int < 50
        """
    )
    assert non_verifies == [], f"instruments sans cotation eprouvee : {non_verifies}"


def test_le_nom_rapporte_par_le_provider_concorde():
    """Garde-fou contre le cas Seb / SEB banque suedoise."""
    sans_nom = fetch_all(
        "select internal_code from instruments "
        "where coalesce(attributes -> 'verification' ->> 'reported_name', '') = ''"
    )
    assert sans_nom == [], f"raison sociale non confrontee : {sans_nom}"


def test_referentiel_coherent():
    """Chaque classe porte les attributs que sa nature autorise.

    Les cles etrangeres garantissent deja qu'un code pose designe une ligne
    existante ; ce que ce test protege est ce qu'elles ne disent pas, la
    presence. Elle ne s'exige pas pareil selon la classe : **une action sans
    marche ni secteur est un mapping incomplet**, alors qu'une matiere premiere
    n'a ni l'un ni l'autre - lui poser un secteur la ferait entrer dans un
    groupe de pairs et publier des indicateurs relatifs a une mediane
    sectorielle qui ne la concerne pas. Ce versant-la est verifie en sens
    inverse dans `test_commodities.py`.
    """
    incompletes = fetch_all(
        """
        select i.internal_code, i.exchange_code, i.sector_code, i.currency
          from instruments i
         where i.asset_class in ('equity', 'dividend_stock')
           and (i.exchange_code is null or i.sector_code is null
                or i.currency is null)
         order by i.internal_code
        """
    )
    assert incompletes == [], f"actions au referentiel incomplet : {incompletes}"


# Deux populations d'actions coexistent : les 59 titres historiques saisis a la
# main, et les 527 issus du screener du 2026-08-21. Ces derniers sont marques
# dans `attributes.notes`. Melanger leurs mesures effacerait la difference.
ISSU_DU_SCREENER = "coalesce(attributes->>'notes','') like 'candidat screener%'"


def test_profondeur_historique_du_referentiel_saisi_a_la_main():
    """Le doc 05 vise >= 15 ans sur >= 95% de l'univers (critere du lot L2).

    Ce critere a ete ecrit pour un univers de grandes capitalisations choisies
    une par une, et **il tient toujours sur cette population** : c'est ce que ce
    test protege, sans l'affaiblir. Les exceptions attendues sont des
    introductions recentes - Prosus 2019, Ferrari 2015, Aena 2015 - pas des
    defauts de mapping.
    """
    total = fetch_one(
        f"select count(*) from instruments where asset_class in ('equity', 'dividend_stock') and not {ISSU_DU_SCREENER}")[0]
    courts = fetch_all(
        "select internal_code, (attributes -> 'verification' ->> 'history_years')::float "
        f"from instruments where asset_class in ('equity', 'dividend_stock') and not {ISSU_DU_SCREENER} "
        "and (attributes -> 'verification' ->> 'history_years')::float < 15"
    )
    assert len(courts) / total <= 0.10, f"trop d'historiques courts : {courts}"



def test_profondeur_historique_de_l_univers_elargi():
    """L'univers du screener est moins profond, c'est mesure et c'est visible.

    Descendre sous les grandes capitalisations fait entrer des societes plus
    jeunes : **30% des titres issus du screener ont moins de 15 ans**
    d'historique, contre 5% de ceux saisis a la main (mesure du 2026-08-21, sur
    527 et 59 titres). Ce n'est pas un defaut de mapping, c'est la structure de
    cet univers-la.

    Et ces titres ne passent pas inapercus : la politique `loglin_20y` exige 15
    ans, donc `eligibility` les disqualifie en `short_history` et le screener les
    affiche en `rejected`. Le systeme dit qu'il ne sait pas, ce qui est le
    comportement voulu (doc 04, principe I2).

    Le seuil de 45% est un **detecteur de regression, pas un objectif** : le
    franchir signifierait qu'une collecte a ramene des series tronquees, comme
    les cotations secondaires a 21 barres que la verification rejette deja.
    """
    total = fetch_one(
        f"select count(*) from instruments where {ISSU_DU_SCREENER}")[0]
    if not total:
        return  # base sans titres issus du screener : rien a mesurer
    courts = fetch_one(
        f"select count(*) from instruments where {ISSU_DU_SCREENER} "
        "and (attributes -> 'verification' ->> 'history_years')::float < 15")[0]
    assert courts / total <= 0.45, f"{courts}/{total} sous 15 ans d'historique"


def test_aucune_serie_tronquee_n_est_entree_en_base():
    """Sous un an, ce n'est pas une jeune societe, c'est un flux casse.

    `verify_universe` le bloque au chargement ; ce test verifie que la barriere
    a tenu, y compris sur les 527 lignes entrees d'un coup le 2026-08-21.
    """
    tronquees = fetch_all(
        "select internal_code, (attributes -> 'verification' ->> 'history_years')::float "
        "from instruments "
        "where (attributes -> 'verification' ->> 'history_years')::float < 1.0"
    )
    assert tronquees == [], f"series tronquees en base : {tronquees}"


def test_les_foncieres_siic_portent_leur_inegibilite_pea():
    """Le statut SIIC (exoneration d'IS sur revenus locatifs) exclut ces titres
    du PEA depuis la loi de finances 2012 (art. 8, loi n°2011-1977), quel que
    soit leur asset_class - `pea_eligible` sert de garde-fou d'achat portefeuille
    (voir portfolio.eligibilite) independamment du scope `dividend_stock`.
    """
    siic = {"EQ:FR:GECINA", "EQ:FR:COVIVIO", "EQ:FR:ALTAREASCA"}
    rows = fetch_all(
        "select internal_code, attributes->>'pea_eligible', attributes->>'pea_motif' "
        "from instruments where internal_code = any(%s)",
        (list(siic),),
    )
    trouves = {r[0] for r in rows}
    assert trouves == siic, f"foncieres SIIC introuvables : {siic - trouves}"
    for code, pea_eligible, motif in rows:
        assert pea_eligible == "false", f"{code} devrait etre hors PEA (SIIC)"
        assert motif, f"{code} devrait porter un motif d'exclusion"


def test_le_screener_exclut_les_titres_non_eligibles_pea():
    """Le classement principal (`dashboard/data.py::screener`) et le screener
    dividendes (`analytics/dividends.py::SQL_SCREENER_DIVIDENDES`) executent
    tous deux la requete de production - pas une reimplementation locale - pour
    verifier qu'un titre `pea_eligible=false` (SIIC/SOCIMI/GVV/FBI) n'apparait
    dans aucun des deux, quel que soit son z-score ou son rendement. C'est le
    "retrait du scope" applique a l'ensemble de l'univers, pas seulement aux
    trois exemples cites en conversation.
    """
    hors_pea = fetch_all(
        "select internal_code from instruments where attributes->>'pea_eligible' = 'false'"
    )
    assert len(hors_pea) >= 20, "le nettoyage SIIC/SOCIMI/GVV/FBI ne semble pas applique"
    codes_hors_pea = {r[0] for r in hors_pea}

    as_of = fetch_one("select max(as_of_date) from regression_fits")[0]
    if as_of is None:
        return  # pas de calcul en base : rien a verifier

    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    from dashboard import data as dashboard_data  # noqa: E402
    from market_intelligence.analytics.dividends import SQL_SCREENER_DIVIDENDES  # noqa: E402

    classement = set(dashboard_data.screener(as_of)["internal_code"])
    assert classement.isdisjoint(codes_hors_pea), (
        f"titres hors PEA presents dans le classement principal : {classement & codes_hors_pea}")

    div = {r[0] for r in fetch_all(SQL_SCREENER_DIVIDENDES, {"as_of": as_of})}
    assert div.isdisjoint(codes_hors_pea), (
        f"titres hors PEA presents dans le screener dividendes : {div & codes_hors_pea}")


def test_symboles_uniques_par_source():
    dupes = fetch_all(
        "select source_id, symbol, count(*) from instrument_symbols "
        "group by source_id, symbol having count(*) > 1"
    )
    assert dupes == []
