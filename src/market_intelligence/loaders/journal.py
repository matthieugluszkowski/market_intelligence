"""Journal d'ingestion : chaque job laisse une trace, y compris quand il echoue.

Sans ce journal, un job qui tombe a 3h du matin est invisible jusqu'a ce qu'on
remarque un trou dans les donnees - c'est-a-dire trop tard, apres avoir pris une
decision sur une serie incomplete.
"""

from __future__ import annotations

import json
from contextlib import contextmanager

START = """
insert into ingestion_runs (source_id, job_name, status)
values (%s, %s, 'running') returning id;
"""

FINISH = """
update ingestion_runs
   set finished_at = now(), status = %(status)s,
       rows_inserted = %(rows_inserted)s, rows_updated = %(rows_updated)s,
       rows_rejected = %(rows_rejected)s, error_message = %(error_message)s,
       details = %(details)s
 where id = %(id)s;
"""


class RunCounters:
    def __init__(self) -> None:
        self.inserted = 0
        self.updated = 0
        self.rejected = 0
        self.details: dict = {}


@contextmanager
def ingestion_run(conn, source_id: int, job_name: str):
    """Ouvre une ligne de journal, la cloture quoi qu'il arrive.

    Le statut est deduit : `failed` si une exception remonte, `partial` si le job
    a signale des echecs par instrument, `success` sinon.
    """
    with conn.cursor() as cur:
        cur.execute(START, (source_id, job_name))
        run_id = cur.fetchone()[0]
    conn.commit()

    counters = RunCounters()
    status, error_message = "success", None
    try:
        yield counters
    except BaseException as exc:  # noqa: BLE001 - on journalise puis on relaie
        status, error_message = "failed", f"{type(exc).__name__}: {exc}"[:2000]
        raise
    finally:
        if status != "failed" and counters.details.get("failed_instruments"):
            status = "partial"
        # Une transaction avortee ignore toute commande jusqu'au rollback. Sans
        # ca, l'echec qu'on veut precisement journaliser serait le seul a ne pas
        # l'etre - et masquerait au passage sa propre cause.
        conn.rollback()
        with conn.cursor() as cur:
            cur.execute(FINISH, {
                "id": run_id, "status": status,
                "rows_inserted": counters.inserted, "rows_updated": counters.updated,
                "rows_rejected": counters.rejected, "error_message": error_message,
                "details": json.dumps(counters.details, ensure_ascii=False, default=str),
            })
        conn.commit()
