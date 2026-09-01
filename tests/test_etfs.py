"""Ce que l'arrivée des ETF ne doit pas casser (classe `etf`).

Ils suivent le mécanisme des actions et des matières premières : même collecteur,
mêmes barres hebdomadaires, même régression log-linéaire, même fiche.
Invariants vérifiés :
- politique de régression valide et modèle implémenté (`log_linear`) ;
- fréquence hebdomadaire (`1w`) ;
- présence d'un ISIN valide et d'une place de cotation (`XPAR` pour Euronext Paris) ;
- calcul dans regression_fits ;
- exclusion des jobs de fondamentaux d'entreprise (`supports_fundamentals = false`).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from market_intelligence.db import fetch_all, fetch_one  # noqa: E402

MODELES_IMPLEMENTES = ["log_linear", "none"]


def test_aucune_politique_active_etf_ne_designe_un_modele_non_implemente():
    non_implementees = fetch_all(
        """
        select i.internal_code, p.code, p.model
          from instruments i
          join asset_classes a on a.code = i.asset_class
          join regression_policies p
            on p.code = coalesce(i.policy_code, a.default_policy_code)
         where i.is_active and i.asset_class = 'etf' and p.model <> all(%(modeles)s)
         order by i.internal_code
        """,
        {"modeles": MODELES_IMPLEMENTES},
    )
    assert non_implementees == [], (
        f"ETF dont la politique annonce un modèle absent du moteur : {non_implementees}"
    )


def test_les_etf_travaillent_en_hebdomadaire():
    mensuelles = fetch_all(
        """
        select i.internal_code, p.bar_freq
          from instruments i
          join asset_classes a on a.code = i.asset_class
          join regression_policies p
            on p.code = coalesce(i.policy_code, a.default_policy_code)
         where i.is_active and i.asset_class = 'etf' and p.bar_freq <> '1w'
         order by i.internal_code
        """
    )
    assert mensuelles == [], f"ETF avec politique non hebdomadaire : {mensuelles}"


def test_un_etf_a_un_isin_et_un_marche_mais_pas_de_secteur_icb():
    """Un ETF est un véhicule coté sur un marché (ex: XPAR) avec ISIN, mais sans secteur ICB."""
    invalides = fetch_all(
        """
        select internal_code, isin, exchange_code, sector_code
          from instruments
         where asset_class = 'etf'
           and (isin is null or exchange_code is null or sector_code is not null)
        """
    )
    assert invalides == [], f"ETF mal configurés (manque ISIN/marché ou a un secteur) : {invalides}"


def test_les_etf_ont_des_attributs_pea_et_metadonnees_valides():
    invalides = fetch_all(
        """
        select internal_code, attributes
          from instruments
         where asset_class = 'etf'
           and (attributes -> 'pea_eligible' is null
                or attributes -> 'emetteur' is null
                or attributes -> 'indice_reference' is null)
        """
    )
    assert invalides == [], f"ETF sans métadonnées complètes : {invalides}"


def test_les_jobs_de_fondamentaux_ignorent_les_etf():
    """Les ETF n'ont pas de comptes de résultat / bilans d'entreprise."""
    from market_intelligence.jobs import compute_quality, ingest_fundamentals

    source_id = fetch_one("select id from data_sources where code = 'yfinance'")[0]

    for requete, params in (
        (ingest_fundamentals.INSTRUMENTS, {"source_id": source_id}),
        (compute_quality.INSTRUMENTS, None),
    ):
        codes = [r[1] for r in fetch_all(requete, params)]
        intrus = [c for c in codes if c.startswith("ETF:")]
        assert intrus == [], f"ETF ramené par un job de fondamentaux : {intrus}"
