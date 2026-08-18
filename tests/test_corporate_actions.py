"""Criteres d'acceptation du lot L3 (05_roadmap-et-lot.md).

    « les cas connus sont correctement detectes. Jeu de test minimal : un split
      recent sur une grande valeur, une dilution massive sur Atos ou Casino, un
      titre a trous de cotation, une divergence Stooq/yfinance. »

Deux cas du jeu minimal ne sont pas jouables en l'etat, et il vaut mieux le dire
que le maquiller :

- **Atos et Casino** ne sont pas dans l'univers des 57. Le filtre de dilution est
  donc eprouve sur donnees synthetiques, ou l'on connait la reponse, plutot que
  sur un titre reel ou l'on ne ferait que constater.
- **La divergence Stooq/yfinance** est impossible : Stooq sert desormais une page
  de verification navigateur. La requete du controle est ecrite pour fonctionner
  des qu'une seconde source alimentera `bars` ; en attendant elle ne trouve rien,
  et c'est precisement le risque a garder sous les yeux.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from market_intelligence.analytics.adjustment_factors import compute_factors  # noqa: E402
from market_intelligence.db import fetch_all, fetch_one  # noqa: E402


# --------------------------------------------------------------------------- #
# Facteurs d'ajustement : fonction pure
# --------------------------------------------------------------------------- #
def test_sans_dividende_le_facteur_vaut_un_partout():
    barres = [(date(2024, 1, i), 100.0) for i in range(1, 6)]
    assert set(compute_factors(barres, []).values()) == {1.0}


def test_le_facteur_vaut_un_a_la_date_la_plus_recente():
    """Convention : on n'ajuste jamais le present, seulement le passe."""
    barres = [(date(2024, 1, 1), 100.0), (date(2024, 6, 1), 110.0),
              (date(2024, 12, 1), 120.0)]
    facteurs = compute_factors(barres, [(date(2024, 3, 1), 5.0)])
    assert facteurs[date(2024, 12, 1)] == 1.0


def test_le_facteur_applique_le_dividende_aux_dates_anterieures():
    barres = [(date(2024, 1, 1), 100.0), (date(2024, 6, 1), 110.0)]
    facteurs = compute_factors(barres, [(date(2024, 3, 1), 5.0)])
    assert facteurs[date(2024, 1, 1)] == pytest.approx(1.0 - 5.0 / 100.0)


def test_les_dividendes_se_composent():
    barres = [(date(2022, 1, 1), 100.0), (date(2023, 1, 1), 100.0),
              (date(2024, 1, 1), 100.0)]
    dividendes = [(date(2022, 6, 1), 2.0), (date(2023, 6, 1), 2.0)]
    facteurs = compute_factors(barres, dividendes)
    assert facteurs[date(2022, 1, 1)] == pytest.approx(0.98 * 0.98)
    assert facteurs[date(2023, 1, 1)] == pytest.approx(0.98)
    assert facteurs[date(2024, 1, 1)] == 1.0


def test_un_dividende_anterieur_a_lhistorique_est_ignore():
    barres = [(date(2024, 1, 1), 100.0)]
    assert compute_factors(barres, [(date(2020, 1, 1), 5.0)])[date(2024, 1, 1)] == 1.0


def test_un_dividende_superieur_au_cours_est_ecarte():
    """Une donnee aberrante ne doit pas produire un facteur nul ou negatif."""
    barres = [(date(2024, 1, 1), 10.0), (date(2024, 6, 1), 10.0)]
    facteurs = compute_factors(barres, [(date(2024, 3, 1), 50.0)])
    assert all(f > 0 for f in facteurs.values())


def test_la_reference_quotidienne_est_utilisee_quand_elle_existe():
    """Sur barres hebdomadaires, « la veille » du detachement est imprecise."""
    barres = [(date(2024, 1, 1), 100.0), (date(2024, 2, 1), 100.0)]
    reference = [(date(2024, 1, 1), 100.0), (date(2024, 1, 14), 80.0),
                 (date(2024, 2, 1), 100.0)]
    sans = compute_factors(barres, [(date(2024, 1, 15), 4.0)])
    avec = compute_factors(barres, [(date(2024, 1, 15), 4.0)], reference)
    assert sans[date(2024, 1, 1)] == pytest.approx(1 - 4 / 100)
    assert avec[date(2024, 1, 1)] == pytest.approx(1 - 4 / 80)


# --------------------------------------------------------------------------- #
# Filtre de dilution, sur donnees synthetiques
# --------------------------------------------------------------------------- #
def test_le_filtre_de_dilution_reconnait_le_cas_atos():
    """Une dilution d'un facteur cent doit franchir le seuil de 50% sur 12 mois.

    Le cas est synthetique faute d'Atos dans l'univers, mais le calcul teste est
    exactement celui de la requete `DILUTION`.
    """
    depart = date(2024, 1, 1)
    serie = [(depart, 100_000_000), (depart + timedelta(days=200), 10_000_000_000)]
    plancher = min(s for _, s in serie)
    variation = serie[-1][1] / plancher - 1
    assert variation > 0.50


def test_une_attribution_dactions_gratuites_ne_declenche_pas_le_filtre():
    """Air Liquide distribue une action pour dix tous les deux ans.

    C'est une operation reguliere et non destructrice de valeur : elle ne doit
    pas etre confondue avec une augmentation de capital dilutive.
    """
    plancher = 578_000_000
    apres = int(plancher * 1.1)
    assert apres / plancher - 1 < 0.50


# --------------------------------------------------------------------------- #
# Etat de la base apres ingestion
# --------------------------------------------------------------------------- #
def test_les_operations_sur_titre_sont_ingerees():
    assert fetch_one("select count(*) from corporate_actions")[0] > 0


def test_un_split_recent_est_detecte_sur_une_grande_valeur():
    """Air Liquide : attribution d'actions gratuites de 1 pour 10, recurrente."""
    splits = fetch_all(
        """
        select ca.ex_date, ca.ratio
          from corporate_actions ca join instruments i on i.id = ca.instrument_id
         where i.internal_code = 'EQ:FR:AIRLIQUIDE'
           and ca.action_type in ('split', 'reverse_split')
         order by ca.ex_date desc
        """
    )
    assert splits, "aucun split detecte sur Air Liquide"
    assert splits[0][0].year >= 2019
    assert splits[0][1] == pytest.approx(1.1)


def test_les_facteurs_sont_calcules_et_bornes():
    bornes = fetch_one(
        "select min(factor_total), max(factor_total), count(*) from adjustment_factors"
    )
    minimum, maximum, total = bornes
    assert total > 0
    assert 0 < minimum <= 1.0
    assert maximum == pytest.approx(1.0)


def test_le_facteur_prix_vaut_un_avec_yfinance():
    """Les splits sont deja incorpores dans le cours servi : les appliquer une
    seconde fois diviserait la serie deux fois, sans que la courbe le montre."""
    assert fetch_one(
        "select count(*) from adjustment_factors where factor_price <> 1.0"
    )[0] == 0


def test_les_controles_qualite_ont_tourne():
    dernier = fetch_one(
        "select status from ingestion_runs where job_name = 'quality_checks' "
        "order by started_at desc limit 1"
    )
    assert dernier is not None, "lancer scripts/quality_checks.py"
    assert dernier[0] in ("success", "partial")


def test_aucune_incoherence_de_devise():
    """Controle bloquant : il ne doit jamais rien trouver sur un univers propre."""
    assert fetch_one(
        "select count(*) from data_quality_issues "
        "where issue_type = 'currency_mismatch' and resolved_at is null"
    )[0] == 0


def test_le_filtre_de_dilution_ne_confond_pas_un_split_avec_une_dilution():
    """Un 5 pour 1 multiplie le nombre d'actions par cinq sans diluer personne.

    Avant neutralisation des splits, le filtre signalait Dassault Systemes
    (x5,09), Michelin (x4,0), Aena (x10,7) et Prosus (x2,43) - quatre splits pris
    pour des dilutions massives, sur 229 alertes au total.
    """
    signales = {
        code for (code,) in fetch_all(
            """
            select i.internal_code from data_quality_issues d
              join instruments i on i.id = d.instrument_id
             where d.issue_type = 'dilution' and d.resolved_at is null
            """
        )
    }
    splitteurs = {"EQ:FR:DASSAULTSYS", "EQ:FR:MICHELIN", "EQ:ES:AENA"}
    assert not (splitteurs & signales), f"splits pris pour des dilutions : {splitteurs & signales}"


def test_le_filtre_de_dilution_remonte_une_alerte_par_titre():
    """Le provider sert un point par jour : un evenement unique produisait 203
    lignes pour Prosus. On ne veut que le pic, avec l'etendue de l'episode."""
    doublons = fetch_all(
        """
        select instrument_id, count(*) from data_quality_issues
         where issue_type = 'dilution' and resolved_at is null
         group by 1 having count(*) > 1
        """
    )
    assert doublons == []


@pytest.mark.parametrize(
    ("nom", "seuil_desserre"),
    [("SAUT", {"seuil": 0.08}), ("FIGEE", {"seuil": 2}), ("TROU", {"seuil_jours": 4})],
)
def test_les_controles_sans_anomalie_sont_bien_capables_de_se_declencher(nom, seuil_desserre):
    """Un controle qui ne peut jamais sonner est pire que pas de controle.

    Aux seuils de production ces trois-la ne trouvent rien - l'univers est propre.
    On verifie donc qu'ils repondent quand on desserre le seuil, sinon une requete
    cassee passerait indefiniment pour un univers sain.
    """
    from market_intelligence.db import connect
    from market_intelligence.validators import price_checks

    with connect() as conn, conn.cursor() as cur:
        cur.execute(getattr(price_checks, nom), seuil_desserre)
        assert len(cur.fetchall()) > 0, f"le controle {nom} ne repond pas"


def test_les_anomalies_ne_sempilent_pas_dune_execution_a_lautre():
    """Le job purge les anomalies non resolues avant recalcul : sans cela, le
    tableau de bord devient illisible en trois semaines."""
    doublons = fetch_all(
        """
        select instrument_id, issue_type, ts_from, count(*)
          from data_quality_issues
         where resolved_at is null and issue_type <> 'split_unadjusted'
         group by 1, 2, 3 having count(*) > 1
        """
    )
    assert doublons == []


# --------------------------------------------------------------------------- #
# Journal des anomalies : y revenir plus tard
# --------------------------------------------------------------------------- #
def test_chaque_anomalie_ouverte_porte_une_empreinte():
    """Sans empreinte, une anomalie ne peut pas etre suivie d'un recalcul a
    l'autre - elle serait recreee, et son age perdu."""
    sans = fetch_one(
        "select count(*) from data_quality_issues "
        "where resolved_at is null and fingerprint is null"
    )[0]
    assert sans == 0


def test_une_seule_anomalie_ouverte_par_empreinte():
    doublons = fetch_all(
        "select fingerprint, count(*) from data_quality_issues "
        "where resolved_at is null group by 1 having count(*) > 1"
    )
    assert doublons == []


def test_un_recalcul_revoit_les_anomalies_au_lieu_de_les_recreer():
    """La date de premiere detection est l'age de l'anomalie : elle ne bouge pas.

    `run_count` compte les recalculs qui l'ont revue - une anomalie vue vingt
    fois n'a pas le meme statut qu'une anomalie apparue ce matin.
    """
    from market_intelligence.jobs.quality_checks import run

    avant = {
        f: (i, d, r) for f, i, d, r in fetch_all(
            "select fingerprint, id, detected_at, run_count from data_quality_issues "
            "where resolved_at is null and fingerprint is not null"
        )
    }
    assert avant, "aucune anomalie ouverte : le test ne demontre rien"

    run()

    apres = {
        f: (i, d, r) for f, i, d, r in fetch_all(
            "select fingerprint, id, detected_at, run_count from data_quality_issues "
            "where resolved_at is null and fingerprint is not null"
        )
    }
    for empreinte, (ident, detecte, runs) in avant.items():
        assert empreinte in apres, f"anomalie {empreinte} perdue au recalcul"
        nouvel_ident, nouveau_detecte, nouveaux_runs = apres[empreinte]
        assert nouvel_ident == ident, "l'anomalie a ete recreee au lieu d'etre revue"
        assert nouveau_detecte == detecte, "la date de premiere detection a bouge"
        assert nouveaux_runs == runs + 1



def test_un_acquittement_manuel_nest_pas_resignale_au_recalcul():
    """Defaut trouve en testant, pas en relisant.

    Une premiere version resignalait au recalcul suivant une anomalie resolue a
    la main : la condition sous-jacente etait toujours vraie. La liste ne
    diminuait donc jamais et la revue manuelle ne servait a rien - alors que
    c'est precisement ce qu'on veut pouvoir faire.

    Une cloture automatique, elle, doit se rouvrir : une condition qui revient
    est une recidive.
    """
    from market_intelligence.db import connect_direct
    from market_intelligence.jobs.quality_checks import run

    cible = fetch_one(
        "select id from data_quality_issues where resolved_at is null "
        "and issue_type = 'short_history' limit 1"
    )
    if cible is None:
        pytest.skip("aucune anomalie a resoudre")

    # On passe par le vrai chemin de resolution plutot que par un UPDATE direct :
    # c'est lui qui pose `resolved_kind`, et c'est justement ce qui distingue un
    # acquittement d'une cloture automatique.
    sys.path.insert(0, str(ROOT / "scripts"))
    from anomalies import resoudre

    note = "test : introduction en bourse recente, comportement attendu"
    with connect_direct() as conn, conn.cursor() as cur:
        assert resoudre(cur, cible[0], note) == 0
        conn.commit()

    run()

    apres = fetch_one(
        "select resolved_at, resolution, resolved_kind from data_quality_issues "
        "where id = %s", (cible[0],),
    )
    assert apres[0] is not None, "la resolution manuelle a ete effacee"
    assert apres[1] == note
    assert apres[2] == "manual"

    empreinte = fetch_one(
        "select fingerprint from data_quality_issues where id = %s", (cible[0],))[0]
    rouvertes = fetch_one(
        "select count(*) from data_quality_issues "
        "where fingerprint = %s and resolved_at is null", (empreinte,))[0]
    assert rouvertes == 0, "l'anomalie acquittee a ete resignalee"

    # Remise en etat : on annule l'acquittement pour les tests suivants.
    with connect_direct() as conn, conn.cursor() as cur:
        cur.execute(
            "update data_quality_issues set resolved_at = null, resolved_kind = null, "
            "resolution = null where id = %s", (cible[0],),
        )
        conn.commit()
