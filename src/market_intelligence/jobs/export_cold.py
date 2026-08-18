"""Export de la couche froide en Parquet.

*Le froid n'est pas une sauvegarde, c'est la source de verite* (doc 00 SS5). La
base chaude ne garde que ce dont le screener a besoin ; si l'on veut un jour du
quotidien sur 30 ans, on recharge depuis Parquet sans retoucher au provider - et
sans dependre de ce que Yahoo aura decide de servir ce jour-la.

Un fichier par instrument et par frequence, partitionne par frequence. Le format
se relit sans base et sans reseau, ce qui est exactement ce qu'on demande a une
archive.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from ..config import get_settings
from ..db import connect

QUERY = """
select i.internal_code, i.isin, b.ts, b.open, b.high, b.low, b.close, b.volume,
       b.source_id, b.ingested_at
  from bars b
  join instruments i on i.id = b.instrument_id
 where b.freq = %(freq)s
 order by i.internal_code, b.ts;
"""


def run(freqs: tuple[str, ...] = ("1w", "1d")) -> dict:
    import pandas as pd

    settings = get_settings()
    root = Path(settings.cold_storage_path)
    written = {}

    with connect() as conn:
        for freq in freqs:
            # Lecture par le curseur plutot que pandas.read_sql : pandas ne
            # supporte officiellement que SQLAlchemy et emet un avertissement
            # sur une connexion psycopg brute.
            with conn.cursor() as cur:
                cur.execute(QUERY, {"freq": freq})
                colonnes = [d.name for d in cur.description]
                frame = pd.DataFrame(cur.fetchall(), columns=colonnes)
            if frame.empty:
                print(f"{freq} : aucune barre, rien a exporter")
                continue

            target = root / f"freq={freq}"
            target.mkdir(parents=True, exist_ok=True)
            for internal_code, group in frame.groupby("internal_code"):
                path = target / f"{internal_code.replace(':', '_')}.parquet"
                group.drop(columns=["internal_code"]).to_parquet(
                    path, index=False, compression="snappy"
                )

            total_bytes = sum(p.stat().st_size for p in target.glob("*.parquet"))
            written[freq] = {
                "instruments": int(frame["internal_code"].nunique()),
                "rows": int(len(frame)),
                "bytes": total_bytes,
                "path": str(target),
            }
            print(f"{freq} : {len(frame):>7} barres, "
                  f"{frame['internal_code'].nunique()} fichiers, "
                  f"{total_bytes / 1e6:.1f} Mo -> {target}")

    manifest = root / "MANIFEST.txt"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        f"export {datetime.now(timezone.utc).isoformat(timespec='seconds')}\n"
        + "\n".join(f"{k}: {v}" for k, v in written.items()) + "\n",
        encoding="utf-8",
    )
    return written
