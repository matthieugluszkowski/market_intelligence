"""Calcul hebdomadaire des regressions et ecriture historisee (doc 03 SS5).

    1. charger les barres hebdo <= as_of_date              <- aucune donnee future
    2. appliquer les filtres d'eligibilite
    3. estimer le modele sur la fenetre de la politique
    4. calculer les diagnostics
    5. INSERER une ligne dans regression_fits (jamais de mise a jour)

Le point 5 est le principe P5. Chaque ligne enregistre ce que le systeme
affirmait a cette date, avec les seules informations dont il disposait, et n'est
jamais reecrite. Au bout d'un an : 52 observations reellement hors echantillon.
Au bout de trois ans : un jeu de donnees que personne ne publie - le comportement
effectif des titres apres un signal, mesure en temps reel, sans look-ahead
possible.

Deux passes, et la seconde n'est pas facultative
------------------------------------------------
Les fits sont d'abord calcules en memoire, puis le verdict `good` est arbitre
apres correction de multiplicite sur l'ensemble de l'univers (doc 03 SS3.3).
Impossible de trancher titre par titre : le seuil depend du nombre de tests menes
et de la distribution des p-values de tous les autres.
"""

from __future__ import annotations

import json
import logging
from datetime import date

import numpy as np

from ..analytics import eligibility as elig
from ..analytics.multiplicity import bhy, facteur_de_penalite
from ..analytics.regime import regime_stats
from ..analytics.regression import analyse
from ..config import get_settings
from ..db import connect_direct
from ..loaders.journal import ingestion_run

logger = logging.getLogger(__name__)

SEMAINES_PAR_AN = 365.25 / 7.0

INSTRUMENTS = """
select i.id, i.internal_code, i.name,
       p.code, p.model, p.window_years, p.min_years, p.bar_freq,
       p.min_observations
  from instruments i
  join asset_classes a on a.code = i.asset_class
  join regression_policies p on p.code = coalesce(i.policy_code, a.default_policy_code)
 where i.is_active
 order by i.internal_code;
"""

# La serie de regression porte sur le cours ajuste des seuls splits
# (doc 03 SS2, etape 1), pour rester comparable a la reference. `factor_total`
# est calcule et stocke, mais sert la mesure de performance, pas la tendance.
BARRES = """
select b.ts, b.close * coalesce(f.factor_price, 1.0) as close_ajuste
  from bars b
  left join adjustment_factors f
    on f.instrument_id = b.instrument_id and f.ts = b.ts
 where b.instrument_id = %(instrument_id)s
   and b.freq = %(freq)s
   and b.ts <= %(as_of)s
 order by b.ts;
"""

ANOMALIES_BLOQUANTES = """
select issue_type from data_quality_issues
 where instrument_id = %(instrument_id)s
   and severity = 'blocking' and resolved_at is null;
"""

DILUTION_DANS_FENETRE = """
select count(*) from data_quality_issues
 where instrument_id = %(instrument_id)s
   and issue_type = 'dilution' and resolved_at is null
   and coalesce(ts_to, ts_from) >= %(debut)s;
"""

INSERT_FIT = """
insert into regression_fits (
  instrument_id, policy_code, as_of_date, window_start, window_end, n_obs,
  slope_annual, intercept, sigma_resid, r_squared,
  last_close, fitted_value, residual, z_score,
  adf_stat, adf_pvalue, dfgls_stat, kpss_stat, durbin_watson,
  half_life_days, ar1_ci_low, ar1_ci_high,
  fit_quality, quality_reasons, regime_stats, method_version
) values (
  %(instrument_id)s, %(policy_code)s, %(as_of_date)s, %(window_start)s,
  %(window_end)s, %(n_obs)s,
  %(slope_annual)s, %(intercept)s, %(sigma_resid)s, %(r_squared)s,
  %(last_close)s, %(fitted_value)s, %(residual)s, %(z_score)s,
  %(adf_stat)s, %(adf_pvalue)s, %(dfgls_stat)s, %(kpss_stat)s, %(durbin_watson)s,
  %(half_life_days)s, %(ar1_ci_low)s, %(ar1_ci_high)s,
  %(fit_quality)s, %(quality_reasons)s, %(regime_stats)s, %(method_version)s
)
on conflict (instrument_id, policy_code, as_of_date, method_version)
do nothing;
"""


def _graine(instrument_id: int, as_of: date) -> int:
    """Graine deterministe du bootstrap : meme entree, meme intervalle."""
    return (instrument_id * 1_000_003 + as_of.toordinal()) % (2 ** 31)


def run(as_of: date | None = None, limit: int = 0, only: str = "") -> dict:
    settings = get_settings()
    as_of = as_of or date.today()
    resume: dict = {"as_of": as_of.isoformat(), "fits": 0, "par_verdict": {},
                    "failed_instruments": []}

    with connect_direct() as conn:
        with conn.cursor() as cur:
            cur.execute("select id from data_sources where code = 'manual'")
            source_id = cur.fetchone()[0]
            cur.execute(INSTRUMENTS)
            instruments = cur.fetchall()

        if only:
            instruments = [i for i in instruments if i[1] == only]
        if limit:
            instruments = instruments[:limit]

        print(f"{len(instruments)} instruments, as_of = {as_of}\n")

        with ingestion_run(conn, source_id, "compute_fits") as counters:
            # --- passe 1 : estimation ---------------------------------------
            calcules: list[dict] = []
            for position, (instrument_id, internal_code, nom, politique_code, model,
                           window_years, min_years, bar_freq,
                           min_observations) in enumerate(instruments, 1):
                politique = {"code": politique_code, "model": model,
                             "window_years": window_years, "min_years": min_years,
                             "bar_freq": bar_freq, "min_observations": min_observations}
                try:
                    calcul = _calcule_un(conn, instrument_id, internal_code,
                                         politique, as_of, settings.method_version)
                except Exception as exc:  # noqa: BLE001 - un titre ne doit pas tuer le lot
                    resume["failed_instruments"].append(
                        {"internal_code": internal_code, "reason": f"{type(exc).__name__}: {exc}"}
                    )
                    print(f"X {position:>3}/{len(instruments)} {internal_code:<22} {exc}")
                    continue
                if calcul:
                    calcul["_position"] = f"{position:>3}/{len(instruments)}"
                    calcules.append(calcul)

            # --- passe 2 : verdict apres correction de multiplicite ----------
            pvalues = [c["dfgls_pvalue"] if not c["motifs"] else None for c in calcules]
            rejets = bhy(pvalues, alpha=0.05)
            n_tests = sum(1 for p in pvalues if p is not None)
            penalite = facteur_de_penalite(n_tests)

            for calcul, rejette in zip(calcules, rejets, strict=True):
                calcul["fit_quality"], calcul["motifs"] = elig.verdict(
                    motifs=calcul["motifs"], n_obs=calcul["n_obs"],
                    politique=calcul["politique"], r_squared=calcul["r_squared"],
                    dfgls_rejette=rejette, dfgls_stat=calcul["dfgls_stat"],
                    dfgls_crit_5=calcul["dfgls_crit_5"],
                )

            # --- ecriture ---------------------------------------------------
            with conn.cursor() as cur:
                for calcul in calcules:
                    cur.execute(INSERT_FIT, _ligne(calcul))
                    resume["fits"] += cur.rowcount
            conn.commit()

            for calcul in calcules:
                verdict = calcul["fit_quality"]
                resume["par_verdict"][verdict] = resume["par_verdict"].get(verdict, 0) + 1
                marque = {"good": "*", "weak": " ", "rejected": "X"}[verdict]
                print(
                    f"{marque} {calcul['_position']} {calcul['internal_code']:<22} "
                    f"z={calcul['z_score']:+6.2f} pente={calcul['slope_annual']:+7.2%} "
                    f"r2={calcul['r_squared']:.2f} n={calcul['n_obs']:<5} "
                    f"{verdict:<9} {','.join(calcul['motifs'])}"
                )

            counters.inserted = resume["fits"]
            counters.details = {
                **resume,
                "correction_multiplicite": {
                    "procedure": "Benjamini-Hochberg-Yekutieli",
                    "n_tests": n_tests,
                    "facteur_penalite": round(penalite, 3),
                },
            }

    print(f"\n{resume['fits']} fits ecrits. Repartition : "
          + ", ".join(f"{k}={v}" for k, v in sorted(resume["par_verdict"].items())))
    print(f"Correction de multiplicite BHY sur {n_tests} tests, "
          f"seuil divise par {penalite:.2f}")
    return resume


def _calcule_un(conn, instrument_id: int, internal_code: str, politique: dict,
                as_of: date, method_version: int) -> dict | None:
    with conn.cursor() as cur:
        cur.execute(BARRES, {"instrument_id": instrument_id,
                             "freq": politique["bar_freq"], "as_of": as_of})
        toutes = cur.fetchall()

    if len(toutes) < 3:
        return None

    debut = elig.fenetre(as_of, politique["window_years"], toutes[0][0])
    barres = [b for b in toutes if b[0] >= debut]
    if len(barres) < 3:
        return None

    dates = [b[0] for b in barres]
    prix = np.array([float(b[1]) for b in barres])

    with conn.cursor() as cur:
        cur.execute(ANOMALIES_BLOQUANTES, {"instrument_id": instrument_id})
        anomalies = [r[0] for r in cur.fetchall()]
        cur.execute(DILUTION_DANS_FENETRE, {"instrument_id": instrument_id, "debut": debut})
        dilution = cur.fetchone()[0] > 0

    annees = (dates[-1] - dates[0]).days / 365.25
    attendues = int(annees * SEMAINES_PAR_AN) if politique["bar_freq"] == "1w" else len(dates)
    motifs = elig.eligibilite(
        politique=politique, n_obs=len(dates), annees_disponibles=annees,
        dilution_dans_la_fenetre=dilution,
        anomalies_bloquantes=[a for a in anomalies if a != "dilution"],
        n_obs_attendues=attendues,
    )

    resultat = analyse(dates, prix, graine=_graine(instrument_id, as_of))
    stats = regime_stats(dates, prix, resultat["residuals"], resultat["sigma_resid"])

    return {
        "instrument_id": instrument_id, "internal_code": internal_code,
        "politique": politique, "as_of": as_of, "method_version": method_version,
        "window_start": dates[0], "window_end": dates[-1],
        "last_close": prix[-1], "motifs": motifs, "regime_stats": stats,
        **{k: v for k, v in resultat.items() if k not in ("residuals", "log_prices")},
    }


def _ligne(c: dict) -> dict:
    return {
        "instrument_id": c["instrument_id"], "policy_code": c["politique"]["code"],
        "as_of_date": c["as_of"], "window_start": c["window_start"],
        "window_end": c["window_end"], "n_obs": c["n_obs"],
        "slope_annual": c["slope_annual"], "intercept": c["intercept"],
        "sigma_resid": c["sigma_resid"], "r_squared": c["r_squared"],
        "last_close": c["last_close"], "fitted_value": c["fitted_last"],
        "residual": c["residual_last"], "z_score": c["z_score"],
        "adf_stat": c["adf_stat"], "adf_pvalue": c["adf_pvalue"],
        "dfgls_stat": c["dfgls_stat"], "kpss_stat": c["kpss_stat"],
        "durbin_watson": c["durbin_watson"], "half_life_days": c["half_life_days"],
        "ar1_ci_low": c["ar1_ci_low"], "ar1_ci_high": c["ar1_ci_high"],
        "fit_quality": c["fit_quality"], "quality_reasons": c["motifs"] or None,
        "regime_stats": json.dumps(c["regime_stats"], ensure_ascii=False, default=str),
        "method_version": c["method_version"],
    }
