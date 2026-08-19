"""Import d'un dossier concurrentiel depuis un fichier JSON (lot L6b bis).

Meme chemin que l'ecran, en ligne de commande - pour importer un dossier relu
hors session, ou pour rejouer un import.

    python scripts/import_dossier.py EQ:FR:SEB dossier.json --analyste "Matthieu"
    python scripts/import_dossier.py EQ:FR:SEB dossier.json --verifier
    python scripts/import_dossier.py --gabarit EQ:FR:SEB > dossier.json

Sans `--analyste`, le dossier est conserve mais **ne projette rien** : c'est le
geste de signature qui distingue un dossier relu d'un dossier produit.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from market_intelligence.db import connect_direct  # noqa: E402
from market_intelligence.intelligence import importer, schema  # noqa: E402


def _instrument(cur, code: str):
    cur.execute(
        "select id, name, sector_code from instruments where internal_code = %s",
        (code,))
    return cur.fetchone()


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("code", help="internal_code, par exemple EQ:FR:SEB")
    parser.add_argument("fichier", nargs="?", help="chemin du JSON")
    parser.add_argument("--analyste", default="",
                        help="qui a relu le dossier ; sans lui, aucune projection")
    parser.add_argument("--verifier", action="store_true",
                        help="valider sans rien ecrire")
    parser.add_argument("--gabarit", action="store_true",
                        help="ecrire un dossier vide conforme au contrat")
    args = parser.parse_args()

    with connect_direct() as conn, conn.cursor() as cur:
        ligne = _instrument(cur, args.code)
        if ligne is None:
            print(f"Instrument inconnu : {args.code}")
            return 1
        instrument_id, nom, sector_code = ligne

        if args.gabarit:
            print(json.dumps(schema.gabarit(args.code, nom, date.today()),
                             ensure_ascii=False, indent=2))
            return 0

        if not args.fichier:
            print("Fichier JSON attendu.")
            return 1

        try:
            dossier = json.loads(Path(args.fichier).read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"JSON invalide : {exc}")
            return 1

        validation = schema.valide(dossier)
        print(f"{nom}  ({args.code})")
        print(f"  concurrents      {validation.concurrents}")
        print(f"  dont hors Europe {validation.concurrents_hors_europe}")
        print(f"  fonctions        {validation.fonctions}")
        print(f"  sources          {validation.sources}")
        if validation.problemes:
            print("\n  problemes :")
            for p in validation.problemes:
                print(f"    [{p.niveau:<9}] {p.element}")
                print(f"                  {p.explication}")
                if p.correction:
                    print(f"                  -> {p.correction}")

        if not validation.importable:
            print(f"\nImport refuse : {len(validation.bloquants)} bloquant(s). "
                  f"Le dossier n'est jamais complete automatiquement.")
            return 1

        if args.verifier:
            print("\nAucun bloquant : le dossier est importable.")
            return 0

        resultat = importer.importe(cur, instrument_id, args.code, sector_code,
                                    dossier, args.analyste)
        conn.commit()

        print()
        if resultat.projete:
            print(f"Importe et valide par {args.analyste}.")
            print(f"  {resultat.concurrents_internes} pair(s) de l'univers, "
                  f"{resultat.concurrents_externes} hors univers")
            print(f"  groupe de pairs #{resultat.groupe_id}"
                  + (f", evaluation #{resultat.moat_id}" if resultat.moat_id else ""))
            print("\nRelancer `python scripts/compute_quality.py` pour que le "
                  "verdict en tienne compte.")
        else:
            print("Dossier enregistre, sans projection.")
        for message in resultat.messages:
            print(f"  {message}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
