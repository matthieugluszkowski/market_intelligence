"""Execution des neuf controles qualite du doc 02 SS5.

Journal, pas photographie
-------------------------
Une premiere version purgeait les anomalies non resolues avant chaque recalcul,
pour eviter qu'elles ne s'empilent. Le remede coutait plus cher que le mal : une
anomalie vue en aout et toujours presente en octobre perdait sa date de premiere
detection, et toute note de diagnostic disparaissait au passage suivant. On ne
pouvait donc pas y revenir - ce qui est pourtant tout l'objet d'une liste
d'anomalies.

Chaque anomalie porte desormais une empreinte stable. Un recalcul :

- **revoit** celle qui est toujours la : `last_seen_at` et `run_count` avancent,
  `detected_at` ne bouge pas, c'est l'age de l'anomalie ;
- **cloture** celle qui a disparu, avec la mention, plutot que de la supprimer -
  une anomalie qui s'en va est une information ;
- **respecte** une resolution manuelle et sa note, qui survivent aux recalculs.

Consulter et traiter : `python scripts/anomalies.py`.
"""

from __future__ import annotations

from ..config import get_settings
from ..db import connect_direct
from ..loaders.journal import ingestion_run
from ..validators import price_checks as v

TYPES_RECALCULES = (
    "outlier_jump", "stale_series", "gap", "dilution", "source_divergence",
    "currency_mismatch", "short_history", "fx_missing", "accounting_identity",
)

# Cloture de ce qui n'a pas ete revu par le passage courant. Deux garde-fous :
# on ne touche qu'aux types que ce job recalcule - `split_unadjusted` vient du
# chargeur -, et on ne touche pas a ce qui n'a jamais recu d'empreinte.
CLOTURE_DISPARUES = """
update data_quality_issues
   set resolved_at = now(), resolved_kind = 'auto',
       resolution = 'auto : plus detectee au recalcul du ' || current_date
 where resolved_at is null
   and fingerprint is not null
   and issue_type = any(%(types)s)
   and not (fingerprint = any(%(vues)s))
returning issue_type;
"""

# Les anomalies d'avant la migration 009 n'ont pas d'empreinte : elles seraient
# invisibles au mecanisme de cloture et resteraient ouvertes indefiniment.
CLOTURE_SANS_EMPREINTE = """
update data_quality_issues
   set resolved_at = now(), resolved_kind = 'auto',
       resolution = 'auto : anterieure au suivi par empreinte, remplacee'
 where resolved_at is null and fingerprint is null and issue_type = any(%(types)s);
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
                cur.execute(CLOTURE_SANS_EMPREINTE, {"types": list(TYPES_RECALCULES)})
                sans_empreinte = cur.rowcount

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

                vues = [e for liste in resultats.values() for e in liste]
                cur.execute(CLOTURE_DISPARUES,
                            {"types": list(TYPES_RECALCULES), "vues": vues or [""]})
                cloturees = cur.rowcount

                cur.execute(
                    """
                    select count(*) filter (where run_count = 1),
                           count(*) filter (where run_count > 1)
                      from data_quality_issues
                     where resolved_at is null and fingerprint = any(%s)
                    """,
                    (vues or [""],),
                )
                nouvelles, revues = cur.fetchone()
            conn.commit()

            comptes = {nom: len(liste) for nom, liste in resultats.items()}
            counters.inserted = nouvelles
            counters.updated = revues
            counters.details = {
                "nouvelles": nouvelles, "revues": revues, "cloturees": cloturees,
                "sans_empreinte_remplacees": sans_empreinte, **comptes,
            }

    comptes = {nom: len(liste) for nom, liste in resultats.items()}
    largeur = max(len(k) for k in comptes)
    for nom, nombre in comptes.items():
        marque = " " if nombre == 0 else "!"
        print(f"{marque} {nom:<{largeur}} {nombre:>5}")
    print(f"\n{sum(comptes.values())} anomalies ouvertes : "
          f"{nouvelles} nouvelle(s), {revues} deja connue(s)")
    if cloturees:
        print(f"{cloturees} cloturee(s) automatiquement : plus detectees")
    if sans_empreinte:
        print(f"{sans_empreinte} anterieure(s) au suivi par empreinte, remplacee(s)")
    print("\nConsulter et traiter : python scripts/anomalies.py")
    return comptes
