"""Ce que l'arrivee des matieres premieres ne doit pas casser (classe `commodity`).

Elles suivent le mecanisme des actions - meme collecteur, memes barres
hebdomadaires, meme regression log-lineaire, meme fiche. Trois invariants
tiennent cette egalite, et chacun casse en silence : un modele que le moteur
n'implemente pas produit une droite fausse sans le dire, une matiere premiere
qui porterait un secteur entrerait dans un groupe de pairs qui n'a pas de sens,
et un job de fondamentaux qui les ramasserait irait chercher un compte de
resultat pour l'or a chaque passage du cycle.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from market_intelligence.db import fetch_all, fetch_one  # noqa: E402

# Ce que `analytics/regression.py` sait faire aujourd'hui. `none` n'est pas un
# modele : c'est le refus d'estimer, traite par l'eligibilite.
MODELES_IMPLEMENTES = ["log_linear", "none"]


def test_aucune_politique_active_ne_designe_un_modele_non_implemente():
    """La politique par defaut d'une classe peut promettre plus que le moteur.

    `asset_classes.default_policy_code` designe `real_deflated` pour les matieres
    premieres : fenetre de 50 ans, barres mensuelles, serie deflatee. Le moteur
    ne l'implemente pas - `compute_fits` applique la regression log-lineaire quel
    que soit le modele. Un instrument qui tomberait sur cette politique serait
    donc estime par un modele qui n'est pas celui que sa politique annonce, et
    la ligne de `regression_fits` porterait un `policy_code` mensonger.

    D'ou la derogation posee dans `instruments.policy_code` (principe P6). Ce
    test la protege : le jour ou quelqu'un l'enleve, il l'apprend ici et non par
    un z-score qui a change tout seul.
    """
    non_implementees = fetch_all(
        """
        select i.internal_code, p.code, p.model
          from instruments i
          join asset_classes a on a.code = i.asset_class
          join regression_policies p
            on p.code = coalesce(i.policy_code, a.default_policy_code)
         where i.is_active and p.model <> all(%(modeles)s)
         order by i.internal_code
        """,
        {"modeles": MODELES_IMPLEMENTES},
    )
    assert non_implementees == [], (
        f"instruments dont la politique annonce un modele absent du moteur : "
        f"{non_implementees}"
    )


def test_les_matieres_premieres_travaillent_en_hebdomadaire():
    """La dette T12 se declenche a la premiere barre mensuelle.

    `compute_fits` convertit la demi-vie par `x 7.0` et les horizons de regime
    par `SEMAINES_PAR_AN`, tous deux codes en dur. Sous une politique mensuelle,
    une demi-vie de 10 mois s'ecrirait 70 jours au lieu de 304 - un facteur 4,3
    sur la seule colonne qui porte le temps, sans rien qui le signale.
    """
    mensuelles = fetch_all(
        """
        select i.internal_code, p.bar_freq
          from instruments i
          join asset_classes a on a.code = i.asset_class
          join regression_policies p
            on p.code = coalesce(i.policy_code, a.default_policy_code)
         where i.is_active and p.bar_freq <> '1w'
         order by i.internal_code
        """
    )
    assert mensuelles == [], f"politiques non hebdomadaires actives : {mensuelles}"


def test_une_matiere_premiere_n_a_ni_isin_ni_secteur_ni_pays():
    """Les trois absences sur lesquelles la fiche bascule ses blocs D et E.

    Un secteur pose sur une matiere premiere la ferait entrer dans un groupe de
    pairs et publier des indicateurs relatifs a une mediane sectorielle qui ne la
    concerne pas. Un ISIN vide plutot que NULL casserait l'unicite de la colonne.
    """
    bavardes = fetch_all(
        """
        select internal_code, isin, sector_code, country_iso2
          from instruments
         where asset_class = 'commodity'
           and (isin is not null or sector_code is not null
                or country_iso2 is not null)
        """
    )
    assert bavardes == [], f"matieres premieres surqualifiees : {bavardes}"


def test_les_matieres_premieres_sont_calculees_comme_les_actions():
    """Elles entrent dans le cycle, sinon la classe d'actif n'est qu'un libelle."""
    calculees = fetch_one(
        """
        select count(*)
          from regression_fits f
          join instruments i on i.id = f.instrument_id
         where i.asset_class = 'commodity'
           and f.as_of_date = (select max(as_of_date) from regression_fits)
        """
    )[0]
    total = fetch_one(
        "select count(*) from instruments "
        "where asset_class = 'commodity' and is_active"
    )[0]
    assert total > 0, "aucune matiere premiere au referentiel"
    assert calculees == total, f"{total - calculees} matiere(s) premiere(s) sans fit du jour"


def test_les_jobs_de_fondamentaux_ignorent_les_classes_sans_comptes():
    """`supports_fundamentals` existe pour cette question ; il faut s'en servir.

    Sans ce filtre, le cycle de 8 h irait chercher un compte de resultat pour
    l'or et `compute_quality` ecrirait un `unqualified` qui se lirait comme un
    verdict alors que la question ne se pose pas.
    """
    from market_intelligence.jobs import compute_quality, ingest_fundamentals

    source_id = fetch_one("select id from data_sources where code = 'yfinance'")[0]

    for requete, params in (
        (ingest_fundamentals.INSTRUMENTS, {"source_id": source_id}),
        (compute_quality.INSTRUMENTS, None),
    ):
        codes = [r[1] for r in fetch_all(requete, params)]
        intrus = [c for c in codes if c.startswith("CM:")]
        assert intrus == [], f"classe sans comptes ramenee par un job : {intrus}"
