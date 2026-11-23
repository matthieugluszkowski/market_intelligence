"""Gestion de l'antichambre et du delistage leger des titres surcotes.

1. Delistage quotidien des instruments actifs avec z-score > 2.5 :
   - Sauvegarde des parametres de regression dans `parked_instruments`
   - Desactivation dans `instruments` (`is_active = FALSE`)
   - Purge des barres et tables lourdes pour liberer le stockage Supabase
   - Garde-fou absolu : exclusion des titres detenus en portefeuille

2. Surveillance hebdomadaire live (spot yfinance) :
   - Calcul en direct du z-score sans aucune barre en base
   - Reintegration automatique dans le screener actif des que z_live <= 1.0

3. Ajout de nouveaux candidats en antichambre :
   - Evaluation en memoire et mise en sommeil legere (~300 octets)
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from typing import Any

import numpy as np
import yfinance as yf

from ..analytics.regression import fit_log_linear
from ..db import connect_direct, fetch_all, fetch_one
from ..loaders.journal import ingestion_run
from . import backfill_prices

logger = logging.getLogger(__name__)

SEUIL_DELIST_PAR_DEFAUT = 2.5
SEUIL_REENTRY_PAR_DEFAUT = 1.0


def delist_overvalued(
    z_threshold: float = SEUIL_DELIST_PAR_DEFAUT,
    dry_run: bool = False,
    vacuum: bool = True,
) -> list[dict[str, Any]]:
    """Deliste et purge les instruments dont le z-score depasse le seuil."""
    sql_candidats = """
    SELECT
        i.id,
        i.internal_code,
        i.name,
        i.isin,
        i.currency,
        i.exchange_code,
        i.asset_class,
        i.policy_code,
        i.attributes,
        coalesce(s.symbol, i.internal_code) as symbol_yfinance,
        f.window_start,
        f.intercept,
        f.slope_annual,
        f.sigma_resid,
        f.r_squared,
        f.last_close,
        f.z_score
    FROM regression_fits f
    JOIN instruments i ON i.id = f.instrument_id
    LEFT JOIN instrument_symbols s ON s.instrument_id = i.id AND s.is_primary
    WHERE f.as_of_date = (SELECT max(as_of_date) FROM regression_fits)
      AND f.z_score > %s
      AND i.is_active = TRUE
      AND i.id NOT IN (SELECT instrument_id FROM positions WHERE instrument_id IS NOT NULL)
    ORDER BY f.z_score DESC;
    """

    candidats = fetch_all(sql_candidats, (z_threshold,))
    if not candidats:
        print(f"Aucun instrument actif avec z-score > {z_threshold:+.2f}.")
        return []

    print(f"\n{len(candidats)} instrument(s) detecte(s) avec z-score > {z_threshold:+.2f} :")
    for c in candidats:
        print(f"  - {c[1]:<15} {c[2]:<30} z = {c[16]:+.2f} (cours: {c[15]:.2f} {c[4]})")

    if dry_run:
        print("\n[DRY-RUN] Aucune modification effectuee en base.")
        return [
            {"id": c[0], "code": c[1], "name": c[2], "z_score": c[16]}
            for c in candidats
        ]

    delistes = []
    with connect_direct(autocommit=False) as conn:
        with conn.cursor() as cur:
            for row in candidats:
                inst_id, code, name, isin, currency, exchange, asset_class, policy, attrs, symbol, \
                    w_start, intercept, slope_annual, sigma_resid, r_sq, last_close, z_val = row

                attrs_json = json.dumps(attrs, default=str) if isinstance(attrs, dict) else (attrs or "{}")

                # 1. Sauvegarde dans parked_instruments
                cur.execute(
                    """
                    INSERT INTO parked_instruments (
                        instrument_id, internal_code, symbol_yfinance, name, isin,
                        currency, exchange_code, asset_class, policy_code, attributes,
                        status, parked_reason, window_start, intercept, slope_annual,
                        sigma_resid, r_squared, last_close_at_parking, last_z_at_parking,
                        notes
                    ) VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        'parked', 'z_above_threshold', %s, %s, %s,
                        %s, %s, %s, %s,
                        %s
                    )
                    ON CONFLICT (internal_code) DO UPDATE SET
                        status = 'parked',
                        parked_reason = 'z_above_threshold',
                        parked_at = now(),
                        window_start = EXCLUDED.window_start,
                        intercept = EXCLUDED.intercept,
                        slope_annual = EXCLUDED.slope_annual,
                        sigma_resid = EXCLUDED.sigma_resid,
                        r_squared = EXCLUDED.r_squared,
                        last_close_at_parking = EXCLUDED.last_close_at_parking,
                        last_z_at_parking = EXCLUDED.last_z_at_parking,
                        notes = EXCLUDED.notes;
                    """,
                    (
                        inst_id, code, symbol, name, isin, currency, exchange, asset_class, policy, attrs_json,
                        w_start, intercept, slope_annual, sigma_resid, r_sq, last_close, z_val,
                        f"Deliste automatiquement avec z = {z_val:+.2f} > {z_threshold}",
                    ),
                )

                # 2. Desactivation dans instruments
                cur.execute(
                    """
                    UPDATE instruments
                       SET is_active = FALSE,
                           delisted_at = CURRENT_DATE,
                           delisting_reason = 'z_score_above_threshold'
                     WHERE id = %s;
                    """,
                    (inst_id,),
                )

                # 3. Purge des tables volumineuses pour ce titre
                cur.execute("DELETE FROM bars_1w WHERE instrument_id = %s;", (inst_id,))
                cur.execute("DELETE FROM bars_1d WHERE instrument_id = %s;", (inst_id,))
                cur.execute("DELETE FROM adjustment_factors WHERE instrument_id = %s;", (inst_id,))
                cur.execute("DELETE FROM shares_outstanding WHERE instrument_id = %s;", (inst_id,))
                cur.execute(
                    """
                    DELETE FROM regression_fits
                     WHERE instrument_id = %s
                       AND id NOT IN (SELECT fit_id FROM positions WHERE fit_id IS NOT NULL);
                    """,
                    (inst_id,),
                )
                cur.execute("DELETE FROM external_briefs WHERE instrument_id = %s;", (inst_id,))
                cur.execute("DELETE FROM data_quality_issues WHERE instrument_id = %s;", (inst_id,))

                delistes.append({"id": inst_id, "code": code, "name": name, "z_score": z_val})

        conn.commit()

    print(f"\n{len(delistes)} instrument(s) bascule(s) en parking et purges.")

    if vacuum:
        print("Compaction des tables principales (VACUUM)...")
        with connect_direct(autocommit=True) as conn:
            with conn.cursor() as cur:
                for table in ["bars_1w", "bars_1d", "adjustment_factors", "regression_fits"]:
                    cur.execute(f"VACUUM {table};")

    return delistes


def calculate_live_z(
    window_start: date,
    intercept: float,
    slope_annual: float,
    sigma_resid: float,
    live_price: float,
    as_of: date | None = None,
) -> float:
    """Calcule le z-score spot a partir du cours courant et des parametres stockes."""
    if live_price <= 0 or sigma_resid <= 0:
        return 0.0
    d = as_of or date.today()
    t_years = (d - window_start).days / 365.25
    beta = np.log(1.0 + slope_annual)
    y_hat = intercept + beta * t_years
    y_live = np.log(live_price)
    return float((y_live - y_hat) / sigma_resid)


def check_parked_live(
    z_reentry_threshold: float = SEUIL_REENTRY_PAR_DEFAUT,
    auto_restore: bool = True,
) -> list[dict[str, Any]]:
    """Surveillance hebdomadaire spot des instruments en antichambre."""
    sql_parked = """
    SELECT
        id, instrument_id, internal_code, symbol_yfinance, name,
        window_start, intercept, slope_annual, sigma_resid, last_z_at_parking,
        currency
    FROM parked_instruments
    WHERE status = 'parked'
    ORDER BY internal_code;
    """
    rows = fetch_all(sql_parked)
    if not rows:
        print("Aucun instrument en antichambre actuellement.")
        return []

    print(f"\nSurveillance de {len(rows)} instrument(s) en antichambre...")
    symbols = list({r[3] for r in rows if r[3]})

    # Telechargement spot par lot (1 seule requete yfinance)
    try:
        data = yf.download(symbols, period="5d", interval="1d", progress=False)
    except Exception as exc:
        logger.error(f"Erreur lors de la recuperation spot yfinance : {exc}")
        return []

    aujourdhui = date.today()
    resultats = []
    reintegres = []

    for r in rows:
        p_id, inst_id, code, symbol, name, w_start, intercept, slope_ann, sigma, last_z, cur_code = r
        live_price = None

        if "Close" in data and symbol in data["Close"]:
            serie = data["Close"][symbol].dropna()
            if not serie.empty:
                live_price = float(serie.iloc[-1])

        if live_price is None or live_price <= 0:
            print(f"  ? {code:<15} ({symbol}) : impossible de lire le cours courant")
            continue

        z_live = calculate_live_z(w_start, intercept, slope_ann, sigma, live_price, as_of=aujourdhui)
        eligible = z_live <= z_reentry_threshold

        resultats.append({
            "id": p_id,
            "instrument_id": inst_id,
            "code": code,
            "symbol": symbol,
            "name": name,
            "live_price": live_price,
            "live_z": z_live,
            "last_z": last_z,
            "eligible": eligible,
        })

        statut_str = "ELIGIBLE (RETOUR SCREENER)" if eligible else f"z_live = {z_live:+.2f}"
        print(f"  - {code:<15} cours: {live_price:>7.2f} {cur_code} | z_parc: {last_z:+.2f} -> {statut_str}")

        # Mise a jour dans parked_instruments
        with connect_direct(autocommit=True) as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE parked_instruments
                   SET last_checked_at = now(),
                       live_price = %s,
                       live_z_score = %s
                 WHERE id = %s;
                """,
                (live_price, z_live, p_id),
            )

            if eligible and auto_restore:
                print(f"    ==> Reintegration immediate de {code} dans le screener actif...")
                cur.execute(
                    """
                    UPDATE parked_instruments
                       SET status = 'restored',
                           reentered_at = now(),
                           notes = 'Reintegre automatiquement avec z = ' || round(%s::numeric, 2)
                     WHERE id = %s;
                    """,
                    (z_live, p_id),
                )
                if inst_id:
                    cur.execute(
                        """
                        UPDATE instruments
                           SET is_active = TRUE,
                               delisted_at = NULL,
                               delisting_reason = NULL
                         WHERE id = %s;
                        """,
                        (inst_id,),
                    )
                reintegres.append(code)

    # Re-backfill des titres reintegres
    if reintegres and auto_restore:
        print(f"\nRechargement des cours pour {len(reintegres)} titre(s) reintegre(s)...")
        for code in reintegres:
            try:
                backfill_prices.run(freqs=("1w", "1d"), only=code)
            except Exception as e:
                logger.warning(f"Echec backfill pour {code}: {e}")

    return resultats


def add_candidate(
    symbol: str,
    name: str | None = None,
    z_reentry_threshold: float = SEUIL_REENTRY_PAR_DEFAUT,
) -> dict[str, Any]:
    """Ajoute un nouveau candidat en antichambre (sans alourdir la base)."""
    symbol = symbol.strip().upper()
    print(f"\nAnalyse en memoire du candidat {symbol}...")

    ticker = yf.Ticker(symbol)
    df = ticker.history(period="max", interval="1wk")
    if df.empty or len(df) < 52:
        raise ValueError(f"Historique insuffisant pour {symbol} (au moins 52 semaines requises).")

    closes = df["Close"].dropna().values
    dates = [d.date() if hasattr(d, "date") else d for d in df.index]
    if len(dates) != len(closes):
        dates = dates[-len(closes):]

    fit = fit_log_linear(dates, closes)
    z_actuel = fit["z_score"]
    last_close = float(closes[-1])

    info = ticker.info or {}
    nom = name or info.get("shortName") or info.get("longName") or symbol
    currency = info.get("currency", "EUR")[:3].upper()
    exchange = info.get("exchange", "PAR")
    isin = info.get("isin")

    # Code interne
    code_interne = f"EQ:{currency}:{symbol.split('.')[0]}"

    print(f"  Nom        : {nom}")
    print(f"  Cours      : {last_close:.2f} {currency}")
    print(f"  Pente ann. : {fit['slope_annual']:+.2%}")
    print(f"  z-score    : {z_actuel:+.2f}")

    # Statut selon z-score actuel
    status = "eligible" if z_actuel <= z_reentry_threshold else "parked"
    reason = "candidate_eligible" if z_actuel <= z_reentry_threshold else "candidate_waiting"

    with connect_direct(autocommit=True) as conn, conn.cursor() as cur:
        # Inscription en antichambre
        cur.execute(
            """
            INSERT INTO parked_instruments (
                internal_code, symbol_yfinance, name, isin, currency,
                exchange_code, asset_class, policy_code, attributes,
                status, parked_reason, window_start, intercept, slope_annual,
                sigma_resid, r_squared, last_close_at_parking, last_z_at_parking,
                last_checked_at, live_price, live_z_score, notes
            ) VALUES (
                %s, %s, %s, %s, %s,
                %s, 'equity', 'loglin_20y', '{}'::jsonb,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                now(), %s, %s, %s
            )
            ON CONFLICT (internal_code) DO UPDATE SET
                symbol_yfinance = EXCLUDED.symbol_yfinance,
                name = EXCLUDED.name,
                status = EXCLUDED.status,
                parked_reason = EXCLUDED.parked_reason,
                window_start = EXCLUDED.window_start,
                intercept = EXCLUDED.intercept,
                slope_annual = EXCLUDED.slope_annual,
                sigma_resid = EXCLUDED.sigma_resid,
                r_squared = EXCLUDED.r_squared,
                last_close_at_parking = EXCLUDED.last_close_at_parking,
                last_z_at_parking = EXCLUDED.last_z_at_parking,
                last_checked_at = now(),
                live_price = EXCLUDED.live_price,
                live_z_score = EXCLUDED.live_z_score;
            """,
            (
                code_interne, symbol, nom, isin, currency,
                exchange, status, reason, dates[0], fit["intercept"], fit["slope_annual"],
                fit["sigma_resid"], fit["r_squared"], last_close, z_actuel,
                last_close, z_actuel,
                f"Candidat ajoute (z={z_actuel:+.2f}, statut={status})",
            ),
        )

    print(f"\n[OK] Candidat {symbol} inscrit dans parked_instruments (statut: {status}).")
    if status == "eligible":
        print(f"     => Titre directement eligible (z={z_actuel:+.2f} <= {z_reentry_threshold}) !")
    else:
        print(f"     => En sommeil : sera surveille chaque semaine sans alourdir la base.")
    return {"symbol": symbol, "code": code_interne, "z_score": z_actuel, "price": last_close, "status": status}


def list_parked() -> list[dict[str, Any]]:
    """Affiche la liste des instruments en antichambre."""
    sql = """
    SELECT
        internal_code, symbol_yfinance, name, status,
        last_z_at_parking, live_z_score, live_price, currency,
        last_checked_at, parked_at
    FROM parked_instruments
    ORDER BY status, last_z_at_parking DESC;
    """
    rows = fetch_all(sql)
    return [
        {
            "code": r[0],
            "symbol": r[1],
            "name": r[2],
            "status": r[3],
            "z_parking": r[4],
            "z_live": r[5],
            "live_price": r[6],
            "currency": r[7],
            "last_checked": r[8],
            "parked_at": r[9],
        }
        for r in rows
    ]


def run_delist() -> dict:
    """Point d'entree pour le cycle d'actualisation (delistage quotidien)."""
    with connect_direct() as conn:
        with conn.cursor() as cur:
            cur.execute("select id from data_sources where code = 'manual'")
            source_id = cur.fetchone()[0]
        with ingestion_run(conn, source_id, "delist_overvalued") as counters:
            delistes = delist_overvalued(z_threshold=SEUIL_DELIST_PAR_DEFAUT, dry_run=False, vacuum=False)
            counters.updated = len(delistes)
            counters.details = {"delistes": [d["code"] for d in delistes]}
    return {"delistes": len(delistes)}


def run_check_parked() -> dict:
    """Point d'entree pour le cycle d'actualisation (surveillance hebdo)."""
    with connect_direct() as conn:
        with conn.cursor() as cur:
            cur.execute("select id from data_sources where code = 'yfinance'")
            source_id = cur.fetchone()[0]
        with ingestion_run(conn, source_id, "check_parked_live") as counters:
            res = check_parked_live(z_reentry_threshold=SEUIL_REENTRY_PAR_DEFAUT, auto_restore=True)
            reintegres = [r["code"] for r in res if r.get("eligible")]
            counters.updated = len(res)
            counters.inserted = len(reintegres)
            counters.details = {"controles": len(res), "reintegres": reintegres}
    return {"controles": len(res), "reintegres": len(reintegres)}

