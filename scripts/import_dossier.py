"""Import en ligne de commande d'un dossier de position concurrentielle.

    python scripts/import_dossier.py --code EQ:FR:ESSILOR --fichier reponse.json
    python scripts/import_dossier.py --code EQ:FR:ESSILOR --fichier r.json --analyste "Prenom Nom"
    python scripts/import_dossier.py --prompt --code EQ:FR:ESSILOR

Meme regle que l'ecran Analyses : **sans nom d'analyste, rien n'est projete**.
Le dossier est conserve en brouillon - ni groupe de pairs, ni evaluation
qualitative - parce que rien ne distingue un dossier relu d'un dossier produit.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace")

from market_intelligence.db import connect_direct  # noqa: E402
from market_intelligence.intelligence import importer, position, prompts  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--code", required=True, help="internal_code du titre")
    parser.add_argument("--fichier", help="JSON de reponse du modele")
    parser.add_argument("--analyste", default="",
                        help="nom de l'analyste ; sans lui, aucune projection")
    parser.add_argument("--prompt", action="store_true",
                        help="afficher le prompt compose et sortir")
    args = parser.parse_args()

    with connect_direct() as conn, conn.cursor() as cur:
        cur.execute("select id, name, sector_code, country_iso2 from instruments "
                    "where internal_code = %s", (args.code,))
        ligne = cur.fetchone()
        if ligne is None:
            print(f"Titre inconnu : {args.code}")
            return 1
        instrument_id, nom, secteur, pays = ligne

        if args.prompt:
            print(prompts.compose("position", {
                "ENTREPRISE_ANALYSEE": nom,
                "PAYS_ET_ZONE_GEOGRAPHIQUE": f"{pays} / zone euro",
                "DATE_DE_REFERENCE": date.today().isoformat(),
            }))
            return 0

        if not args.fichier:
            print("--fichier est requis, ou --prompt pour composer le prompt.")
            return 2

        dossier = json.loads(Path(args.fichier).read_text(encoding="utf-8"))
        validation = position.valide(dossier)
        for probleme in validation.problemes:
            print(f"  [{probleme.niveau:9}] {probleme.element} — "
                  f"{probleme.explication}")
        if not validation.importable:
            print("\nImport refuse : le dossier est inexploitable en l'etat.")
            return 1

        resultat = importer.importe(cur, instrument_id, args.code, secteur,
                                    dossier, args.analyste.strip() or None)
        conn.commit()

    score = resultat.score
    print(f"\n{nom} — {score.total}/100 ({score.niveau})")
    for l in score.lignes:
        print(f"  {l.libelle:16} {l.detail:28} {l.points:+4d}")
    for reserve in score.reserves:
        print(f"  reserve : {reserve}")
    print(f"\nDossier #{resultat.analyse_id}, "
          f"{resultat.concurrents_internes} concurrent(s) dans l'univers, "
          f"{resultat.concurrents_externes} hors univers.")
    for message in resultat.messages:
        print(f"  {message}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
