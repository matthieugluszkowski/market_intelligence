"""Calcul trimestriel de la couche qualite (doc 08, lot L6b).

Deux frequences distinctes, et c'est delibere : le prix se recalcule chaque
semaine, la qualite au rythme des publications de comptes. Recalculer la qualite
chaque semaine creerait une illusion de mouvement la ou il n'y en a pas.

Le principe P5 s'applique ici exactement comme au prix : `as_of_date` est
historisee et jamais reecrite. Dans trois ans, on voudra savoir si les titres
classes `solid` en 2026 l'etaient encore en 2029, et cette information ne se
reconstitue pas.

Ordre des operations
--------------------
Les groupes sectoriels automatiques sont d'abord (re)construits, puis les
groupes manuels priment sur eux : *le groupe de pairs manuel prime toujours sur
le groupe sectoriel automatique* (doc 08, limite L4). La classification ICB
range parfois mal - Seb en biens de consommation durables, avec des pairs peu
comparables.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from ..analytics import quality as Q
from ..analytics import ratios as R
from ..config import get_settings
from ..db import connect_direct
from ..loaders.journal import ingestion_run

logger = logging.getLogger(__name__)

INSTRUMENTS = """
select i.id, i.internal_code, i.name, i.sector_code,
       i.attributes ->> 'regime_declare' as regime_declare
  from instruments i where i.is_active order by i.internal_code;
"""

# Groupes sectoriels automatiques : un par secteur ICB represente. Grossiers -
# on ne dispose que du niveau 1 - mais ils donnent une mediane de ROIC de
# reference la ou aucun groupe manuel n'existe.
GROUPES_AUTO = """
insert into peer_groups (code, label, kind, sector_code, is_complete, notes)
select 'AUTO:' || s.code, 'Secteur ' || s.label || ' (automatique)', 'sector_auto',
       s.code, false,
       'Groupe sectoriel automatique, limite a l univers europeen : structurellement '
       'aveugle aux concurrents hors Europe, donc jamais complet.'
  from sectors s
 where exists (select 1 from instruments i where i.sector_code = s.code and i.is_active)
on conflict (code) do update set label = excluded.label
returning id, sector_code;
"""

MEMBRES_AUTO = """
insert into peer_group_members (peer_group_id, instrument_id, is_in_universe)
select g.id, i.id, true
  from peer_groups g
  join instruments i on i.sector_code = g.sector_code and i.is_active
 where g.kind = 'sector_auto'
on conflict do nothing;
"""

# Le groupe manuel prime. A defaut, le sectoriel automatique.
GROUPE_DE = """
select g.id, g.code, g.kind, g.is_complete
  from peer_groups g
  join peer_group_members m on m.peer_group_id = g.id
 where m.instrument_id = %(instrument_id)s
   and %(as_of)s between m.valid_from and m.valid_to
 order by case g.kind when 'manual' then 0 else 1 end
 limit 1;
"""

PAIRS_DU_GROUPE = """
select m.instrument_id
  from peer_group_members m
 where m.peer_group_id = %(groupe_id)s
   and m.instrument_id is not null
   and m.instrument_id <> %(instrument_id)s;
"""

EVALUATION_VALIDE = """
select count(*) from moat_assessments
 where instrument_id = %(instrument_id)s
   and reviewed_by is not null
   and expires_at >= %(as_of)s;
"""

INSERT_SCORE = """
insert into quality_scores (
  instrument_id, as_of_date, peer_group_id,
  relative_share, rank_by_revenue, rank_stability_5y, foreign_revenue_pct,
  roic_latest, roic_mean_5y, roic_volatility, roic_vs_threshold, roic_vs_peers,
  persistence_years, gross_margin_mean, gross_margin_std,
  roic_slope_5y, gross_margin_slope_5y, share_slope_5y, erosion_flags,
  regime, quality_tier, n_years_available, confidence, method_version
) values (
  %(instrument_id)s, %(as_of_date)s, %(peer_group_id)s,
  %(relative_share)s, %(rank_by_revenue)s, %(rank_stability_5y)s, %(foreign_revenue_pct)s,
  %(roic_latest)s, %(roic_mean_5y)s, %(roic_volatility)s, %(roic_vs_threshold)s,
  %(roic_vs_peers)s, %(persistence_years)s, %(gross_margin_mean)s, %(gross_margin_std)s,
  %(roic_slope_5y)s, %(gross_margin_slope_5y)s, %(share_slope_5y)s, %(erosion_flags)s,
  %(regime)s, %(quality_tier)s, %(n_years_available)s, %(confidence)s, %(method_version)s
)
on conflict (instrument_id, as_of_date, method_version) do nothing;
"""


def run(as_of: date | None = None, limit: int = 0, only: str = "") -> dict:
    settings = get_settings()
    as_of = as_of or date.today()
    resume: dict = {"as_of": as_of.isoformat(), "scores": 0, "par_tier": {},
                    "par_regime": {}, "failed_instruments": []}

    with connect_direct() as conn:
        with conn.cursor() as cur:
            cur.execute("select id from data_sources where code = 'manual'")
            source_id = cur.fetchone()[0]

        with ingestion_run(conn, source_id, "compute_quality") as counters:
            with conn.cursor() as cur:
                cur.execute(GROUPES_AUTO)
                cur.fetchall()
                cur.execute(MEMBRES_AUTO)
            conn.commit()

            with conn.cursor() as cur:
                cur.execute(INSTRUMENTS)
                instruments = cur.fetchall()
            if only:
                instruments = [i for i in instruments if i[1] == only]
            if limit:
                instruments = instruments[:limit]

            print(f"{len(instruments)} instruments, as_of = {as_of}\n")

            # Passe 1 : fondamentaux et ROIC de tous, pour disposer des medianes.
            contexte: dict = {}
            with conn.cursor() as cur:
                for instrument_id, code, nom, secteur, declare in instruments:
                    f = R.charge(cur, instrument_id, as_of)
                    roic = Q.serie_roic(f)
                    contexte[instrument_id] = {
                        "code": code, "nom": nom, "secteur": secteur, "f": f,
                        "declare": declare,
                        "roic_moyen": (sum(v for _, v in roic) / len(roic)
                                       if roic else None),
                        "revenu": f.dernier("revenue"),
                    }

            # Passe 2 : verdicts, avec le groupe de pairs de chacun.
            with conn.cursor() as cur:
                for instrument_id, code, nom, secteur, declare in instruments:
                    ctx = contexte[instrument_id]
                    cur.execute(GROUPE_DE, {"instrument_id": instrument_id,
                                            "as_of": as_of})
                    groupe = cur.fetchone()
                    groupe_id, groupe_code, groupe_kind, complet = (
                        groupe if groupe else (None, None, None, False))

                    pairs_roic, pairs_revenus = [], []
                    if groupe_id:
                        cur.execute(PAIRS_DU_GROUPE, {"groupe_id": groupe_id,
                                                      "instrument_id": instrument_id})
                        for (pair_id,) in cur.fetchall():
                            pair = contexte.get(pair_id)
                            if pair is None:
                                continue
                            if pair["roic_moyen"] is not None:
                                pairs_roic.append(pair["roic_moyen"])
                            if pair["revenu"] is not None:
                                pairs_revenus.append(pair["revenu"])

                    cur.execute(EVALUATION_VALIDE, {"instrument_id": instrument_id,
                                                    "as_of": as_of})
                    evaluation_valide = cur.fetchone()[0] > 0

                    q = Q.evalue(
                        ctx["f"],
                        roic_median_pairs=Q._mediane(pairs_roic) if pairs_roic else None,
                        revenus_pairs=pairs_revenus,
                        groupe_complet=bool(complet),
                        evaluation_valide=evaluation_valide,
                        regime_declare=declare,
                    )

                    cur.execute(INSERT_SCORE, {
                        "instrument_id": instrument_id, "as_of_date": as_of,
                        "peer_group_id": groupe_id,
                        "relative_share": q.relative_share,
                        "rank_by_revenue": q.rank_by_revenue,
                        "rank_stability_5y": q.rank_stability_5y,
                        "foreign_revenue_pct": None,
                        "roic_latest": q.roic_latest, "roic_mean_5y": q.roic_mean_5y,
                        "roic_volatility": q.roic_volatility,
                        "roic_vs_threshold": q.roic_vs_threshold,
                        "roic_vs_peers": q.roic_vs_peers,
                        "persistence_years": q.persistence_years,
                        "gross_margin_mean": q.gross_margin_mean,
                        "gross_margin_std": q.gross_margin_std,
                        "roic_slope_5y": q.roic_slope_5y,
                        "gross_margin_slope_5y": q.gross_margin_slope_5y,
                        "share_slope_5y": q.share_slope_5y,
                        "erosion_flags": q.erosion_flags,
                        "regime": q.regime, "quality_tier": q.quality_tier,
                        "n_years_available": q.n_years_available,
                        "confidence": q.confidence,
                        "method_version": settings.method_version,
                    })
                    resume["scores"] += cur.rowcount
                    resume["par_tier"][q.quality_tier] = (
                        resume["par_tier"].get(q.quality_tier, 0) + 1)
                    resume["par_regime"][q.regime] = (
                        resume["par_regime"].get(q.regime, 0) + 1)

                    marque = {"solid": "*", "watch": " ", "eroding": "!",
                              "unqualified": "?"}[q.quality_tier]
                    roic_txt = ("    -" if q.roic_mean_5y is None
                                else f"{q.roic_mean_5y:+6.1%}")
                    print(f"{marque} {code:<22} ROIC {roic_txt} "
                          f"pers={q.persistence_years}/{q.n_years_available} "
                          f"erosion={q.erosion_flags}/3 "
                          f"{q.regime:<9} {q.quality_tier:<12} "
                          f"{(groupe_code or '-'):<24} {','.join(q.motifs)}")
            conn.commit()

            counters.inserted = resume["scores"]
            counters.details = resume

    print(f"\n{resume['scores']} scores ecrits.")
    print("Par niveau  : " + ", ".join(f"{k}={v}" for k, v in
                                       sorted(resume["par_tier"].items())))
    print("Par regime  : " + ", ".join(f"{k}={v}" for k, v in
                                       sorted(resume["par_regime"].items())))
    return resume


def expire_les_evaluations(cur, as_of: date) -> int:
    """Les evaluations de plus de 18 mois cessent de qualifier.

    Une evaluation de 2026 inspire exactement la meme confiance qu'une de 2029,
    et c'est precisement le probleme. La peremption force la revue.
    """
    cur.execute(
        "update moat_assessments set expires_at = assessed_at + interval '18 months' "
        "where expires_at is null returning id"
    )
    return len(cur.fetchall())
