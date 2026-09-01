"""Collecte la veille externe : consensus, notations et depeches (lot L10).

Usage :
    python scripts/ingest_veille.py                      # watchlist + portefeuille
    python scripts/ingest_veille.py --code EQ:FR:EL
    python scripts/ingest_veille.py --tout --limit 20
    python scripts/ingest_veille.py --url EQ:FR:EL https://www.zonebourse.com/cours/action/ESSILORLUXOTTICA-4641/

Le dernier appel enregistre l adresse Zonebourse d un titre. Elle ne se devine
pas - la source adresse ses fiches par identifiant interne - et un identifiant
approchant ne rend pas une erreur : il rend la fiche d une autre societe.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from market_intelligence.db import connect_direct  # noqa: E402
from market_intelligence.jobs import ingest_veille  # noqa: E402


def enregistre_une_url(code: str, url: str) -> int:
    with connect_direct() as conn, conn.cursor() as cur:
        cur.execute("select id, name from instruments where internal_code = %s",
                    (code,))
        ligne = cur.fetchone()
        if ligne is None:
            print(f"Titre inconnu : {code}")
            return 1
        ingest_veille.enregistre_url(cur, ligne[0], "zonebourse", url)
        conn.commit()
        print(f"URL Zonebourse enregistree pour {ligne[1]} ({code}) :\n  "
              f"{ingest_veille.url_zonebourse(cur, ligne[0])}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--code", action="append", default=[],
                        help="collecter ce titre (repetable)")
    parser.add_argument("--tout", action="store_true",
                        help="tout l univers actions. Long, et peu utile : "
                             "personne ne lit la veille d un titre qu il ne suit pas")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--delai", type=float, default=1.0,
                        help="secondes entre deux requetes (defaut 1)")
    parser.add_argument("--articles", type=int, default=6,
                        help="nombre de depeches dont le texte complet est lu")
    parser.add_argument("--url", nargs=2, metavar=("CODE", "URL"),
                        help="enregistre l adresse Zonebourse d un titre, puis sort")
    args = parser.parse_args()

    if args.url:
        return enregistre_une_url(*args.url)

    resume = ingest_veille.run(codes=args.code, tout=args.tout, limit=args.limit,
                               delai_sec=args.delai, articles_complets=args.articles)
    rates = resume.get("failed_instruments", [])
    print(f"\n{len(resume.get('titres', {}))} titre(s) traite(s), "
          f"{len(rates)} sans aucune collecte.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
