"""Migration des dossiers concurrentiels vers le format « position » (v2).

    python scripts/migre_dossiers_v2.py --essai
    python scripts/migre_dossiers_v2.py

Ce que la migration reprend, et ce qu'elle ne peut pas reprendre
-----------------------------------------------------------------
Elle extrait des anciens dossiers ce qui repond aux quatre questions : verdict
de position, durabilite, sources de rente, concurrents avec leur explication,
menaces, resume. L'ancien dossier complet est conserve sous `ancien_dossier` :
rien n'est perdu, rien n'est reecrit en silence.

**L'annee d'accession a la position n'existe nulle part dans l'ancien format.**
C'est precisement la question que l'ancien dispositif ne posait pas - « leader »
sans « depuis quand » - et elle se saisit a la main dans l'ecran Analyses. Tant
qu'elle manque, le score le dit au lieu de l'inventer.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace")

from market_intelligence.db import connect_direct  # noqa: E402
from market_intelligence.intelligence import position as P  # noqa: E402

A_MIGRER = """
select m.id, i.internal_code, i.name, m.status, m.dossier
  from market_analyses m join instruments i on i.id = m.instrument_id
 order by m.id;
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--essai", action="store_true",
                        help="afficher sans ecrire")
    args = parser.parse_args()

    with connect_direct() as conn, conn.cursor() as cur:
        cur.execute(A_MIGRER)
        lignes = cur.fetchall()
        migres, deja, sans_verdict = 0, 0, 0

        for analyse_id, code, nom, statut, ancien in lignes:
            if P.est_v2(ancien):
                deja += 1
                print(f"  = {code:22} deja au format v2")
                continue

            nouveau = P.migre(ancien, entreprise=nom)
            score = P.calcule_le_score(nouveau)
            validation = P.valide(nouveau)
            verdict = nouveau["position"]["verdict"] or "aucun"
            if verdict == "aucun":
                sans_verdict += 1

            print(f"  > {code:22} {verdict:11} "
                  f"{len(nouveau['concurrents']):2} concurrent(s) "
                  f"{len(nouveau['autres_menaces']):2} menace(s) "
                  f"score {score.total:3d}/100 "
                  f"{'importable' if validation.importable else 'INCOMPLET'}")
            for p in validation.bloquants:
                print(f"      bloquant : {p.element} — {p.explication[:80]}")

            if not args.essai:
                cur.execute(
                    "update market_analyses set dossier = %s where id = %s",
                    (json.dumps(nouveau, ensure_ascii=False, default=str),
                     analyse_id))
                migres += 1

        if not args.essai:
            conn.commit()

    print(f"\n{len(lignes)} dossier(s) : {migres} migre(s), {deja} deja a jour.")
    if sans_verdict:
        print(f"{sans_verdict} sans verdict de position : l'ancien dossier "
              f"n'en portait pas. A completer a la main, ou a relancer avec le "
              f"nouveau prompt.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
