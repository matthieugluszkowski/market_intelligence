"""Execution des neuf controles qualite du doc 02 SS5.

Le job repart d'une table propre a chaque passage : les anomalies non resolues
sont purgees avant recalcul, sinon la meme anomalie s'empile a chaque execution
et le tableau de bord devient illisible en trois semaines. Les anomalies
resolues a la main sont conservees - c'est la trace du diagnostic.
"""

from __future__ import annotations

from ..config import get_settings
from ..db import connect_direct
from ..loaders.journal import ingestion_run
from ..validators import price_checks as v

PURGE = """
delete from data_quality_issues
 where resolved_at is null
   and issue_type in ('outlier_jump', 'stale_series', 'gap', 'dilution',
                      'source_divergence', 'currency_mismatch', 'short_history',
                      'fx_missing', 'accounting_identity');
"""

# Seuils du doc 02 SS5. Ceux qui sont arbitraires sont signales comme tels.
SEUIL_SEANCES_FIGEES = 5
SEUIL_TROU_JOURS = 9          # > 5 jours ouvres, exprime en jours calendaires
SEUIL_DIVERGENCE = 0.01       # 1% entre deux sources
TOLERANCE_COMPTABLE = 0.01    # 1% sur actif = passif + capitaux propres


def run() -> dict:
    settings = get_settings()
    resultats: dict = {}

    with connect_direct() as conn:
        with conn.cursor() as cur:
            cur.execute("select id from data_sources where code = 'manual'")
            source_id = cur.fetchone()[0]

        with ingestion_run(conn, source_id, "quality_checks") as counters:
            with conn.cursor() as cur:
                cur.execute(PURGE)
                purgees = cur.rowcount

                resultats["saut_de_cours"] = v.saut_de_cours(
                    cur, settings.jump_alert_threshold)
                resultats["serie_figee"] = v.serie_figee(cur, SEUIL_SEANCES_FIGEES)
                resultats["trou_de_cotation"] = v.trou_de_cotation(cur, SEUIL_TROU_JOURS)
                resultats["dilution"] = v.dilution(cur, settings.dilution_threshold_12m)
                resultats["divergence_inter_sources"] = v.divergence_inter_sources(
                    cur, SEUIL_DIVERGENCE)
                resultats["incoherence_devise"] = v.incoherence_devise(cur)
                resultats["historique_insuffisant"] = v.historique_insuffisant(cur)
                resultats["fx_manquant"] = v.fx_manquant(cur)
                resultats["identite_comptable"] = v.identite_comptable(
                    cur, TOLERANCE_COMPTABLE)
            conn.commit()

            counters.inserted = sum(resultats.values())
            counters.details = {"purgees": purgees, **resultats}

    largeur = max(len(k) for k in resultats)
    print(f"{purgees} anomalies non resolues purgees avant recalcul\n")
    for nom, nombre in resultats.items():
        marque = " " if nombre == 0 else "!"
        print(f"{marque} {nom:<{largeur}} {nombre:>5}")
    print(f"\nTotal : {sum(resultats.values())} anomalies")
    return resultats
