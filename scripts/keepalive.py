"""Ping keepalive Supabase.

Le free tier met le projet en pause apres 7 jours sans requete (doc 00 SS5,
reserve 1). Ce script est deliberement independant du pipeline principal : si
l'ingestion casse, le ping doit continuer a tourner, sinon la base se met en
pause et demande une reactivation manuelle.

Sortie : 0 si le ping a reussi, 1 sinon (pour qu'un cron puisse alerter).

Usage :
    python scripts/keepalive.py
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from market_intelligence.db import connect  # noqa: E402

PING = """
update keepalive
   set pinged_at = now(),
       ping_count = ping_count + 1
 where id = 1
returning pinged_at, ping_count;
"""


def main() -> int:
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        with connect(autocommit=True) as conn, conn.cursor() as cur:
            cur.execute(PING)
            row = cur.fetchone()
        if row is None:
            print(f"{stamp} KEEPALIVE FAILED: ligne keepalive absente")
            return 1
        print(f"{stamp} KEEPALIVE OK pinged_at={row[0].isoformat()} count={row[1]}")
        return 0
    except Exception as exc:  # noqa: BLE001 - un cron veut un code de sortie, pas une trace
        print(f"{stamp} KEEPALIVE FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
