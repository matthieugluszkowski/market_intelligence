"""Consultation et traitement des anomalies qualite (lot L3).

La liste des anomalies n'a de valeur que si on peut y revenir : voir depuis
quand une anomalie traine, ce qu'on en avait conclu la derniere fois, et la
clore avec sa raison.

Usage :
    python scripts/anomalies.py                         # anomalies ouvertes
    python scripts/anomalies.py --severite blocking     # les bloquantes d'abord
    python scripts/anomalies.py --type dilution
    python scripts/anomalies.py --resolues              # ce qui a ete traite
    python scripts/anomalies.py --detail 42             # une anomalie en entier
    python scripts/anomalies.py --resoudre 42 --note "point aberrant du provider"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from market_intelligence.db import connect_direct  # noqa: E402

LISTE = """
select d.id, coalesce(i.internal_code, '-') as titre, d.issue_type, d.severity,
       d.detected_at::date, coalesce(d.last_seen_at, d.detected_at)::date,
       d.run_count, current_date - d.detected_at::date as age_jours,
       d.details, d.resolved_at::date, d.resolution
  from data_quality_issues d
  left join instruments i on i.id = d.instrument_id
 where (%(resolues)s or d.resolved_at is null)
   and (not %(resolues)s or d.resolved_at is not null)
   and (%(severite)s = '' or d.severity = %(severite)s)
   and (%(type)s = '' or d.issue_type = %(type)s)
 order by case d.severity when 'blocking' then 0 when 'warning' then 1 else 2 end,
          d.detected_at
 limit %(limite)s;
"""

DETAIL = """
select d.id, coalesce(i.internal_code, '-'), i.name, d.issue_type, d.severity,
       d.detected_at, d.last_seen_at, d.run_count, d.ts_from, d.ts_to,
       d.details, d.resolved_at, d.resolution, d.fingerprint
  from data_quality_issues d
  left join instruments i on i.id = d.instrument_id
 where d.id = %s;
"""

RESOUDRE = """
update data_quality_issues
   set resolved_at = now(), resolved_kind = 'manual', resolution = %(note)s
 where id = %(id)s and resolved_at is null
returning issue_type, coalesce(instrument_id::text, '-');
"""

# Annule un acquittement : l anomalie sera resignalee au prochain recalcul.
ROUVRIR = """
update data_quality_issues
   set resolved_at = null, resolved_kind = null,
       resolution = 'rouverte : ' || coalesce(resolution, '')
 where id = %s and resolved_kind = 'manual'
   and not exists (
     select 1 from data_quality_issues ouverte
      where ouverte.fingerprint = data_quality_issues.fingerprint
        and ouverte.resolved_at is null
   )
returning issue_type;
"""


def lister(cur, args) -> int:
    cur.execute(LISTE, {"resolues": args.resolues, "severite": args.severite,
                        "type": args.type, "limite": args.limite})
    lignes = cur.fetchall()
    if not lignes:
        print("Aucune anomalie" + (" resolue." if args.resolues else " ouverte."))
        return 0

    entete = "resolues" if args.resolues else "ouvertes"
    print(f"{len(lignes)} anomalie(s) {entete}\n")
    print(f"{'id':>5}  {'titre':<22} {'type':<20} {'sev':<9} "
          f"{'depuis':<11} {'age':>5} {'vue':>4}  resume")
    print("-" * 118)
    for (ident, titre, type_, severite, detecte, vu, runs, age,
         details, resolu, resolution) in lignes:
        marque = "!" if severite == "blocking" else " "
        resume = _resume(type_, details)
        if args.resolues:
            resume = f"[{resolution or 'sans note'}] {resume}"
        print(f"{marque}{ident:>4}  {titre:<22} {type_:<20} {severite:<9} "
              f"{detecte!s:<11} {age:>4}j {runs:>4}  {resume[:44]}")

    if not args.resolues:
        print("\nDetail : python scripts/anomalies.py --detail <id>")
        print("Clore  : python scripts/anomalies.py --resoudre <id> --note \"...\"")
    return 0


def _resume(type_: str, details: dict) -> str:
    """Une ligne qui dit de quoi il s'agit, sans avoir a ouvrir le detail."""
    if not isinstance(details, dict):
        return ""
    if type_ == "dilution":
        return (f"x{1 + details.get('variation_max', 0):.2f} le "
                f"{details.get('date_du_pic')} sur "
                f"{details.get('observations_en_franchissement')} obs")
    if type_ == "short_history":
        return f"{details.get('annees_disponibles')} ans, {details.get('politique')} en exige {details.get('min_years')}"
    if type_ == "outlier_jump":
        return f"{details.get('variation', 0):+.1%} en une seance"
    if type_ == "stale_series":
        return f"{details.get('seances')} seances au meme cours"
    if type_ == "gap":
        return f"{details.get('jours_calendaires', details.get('count'))} jours sans cotation"
    if type_ == "split_unadjusted":
        return f"{details.get('revised')} barres revisees ({details.get('ratio', 0):.0%})"
    if type_ == "source_divergence":
        return f"ecart {details.get('ecart', 0):.2%}"
    if type_ == "currency_mismatch":
        return f"{details.get('devise_instrument')} vs {details.get('devise_marche')}"
    return json.dumps(details, ensure_ascii=False)[:44]


def detailler(cur, ident: int) -> int:
    cur.execute(DETAIL, (ident,))
    ligne = cur.fetchone()
    if ligne is None:
        print(f"Anomalie {ident} introuvable.")
        return 1
    (i, code, nom, type_, severite, detecte, vu, runs, ts_from, ts_to,
     details, resolu, resolution, empreinte) = ligne

    print(f"Anomalie {i} - {type_} ({severite})")
    print(f"  titre              {code} {nom or ''}")
    print(f"  premiere detection {detecte}")
    print(f"  derniere vue       {vu}  ({runs} recalcul(s) l'ont revue)")
    print(f"  perimetre          {ts_from} -> {ts_to}")
    print(f"  empreinte          {empreinte}")
    print(f"  statut             {'resolue le ' + str(resolu) if resolu else 'OUVERTE'}")
    if resolution:
        print(f"  resolution         {resolution}")
    print("  details")
    for cle, valeur in (details or {}).items():
        print(f"    {cle:<34} {valeur}")
    return 0


def resoudre(cur, ident: int, note: str) -> int:
    if not note:
        print("Une resolution sans note ne sert a rien dans six mois. "
              "Utiliser --note \"...\".")
        return 1
    cur.execute(RESOUDRE, {"id": ident, "note": note})
    ligne = cur.fetchone()
    if ligne is None:
        print(f"Anomalie {ident} introuvable ou deja resolue.")
        return 1
    print(f"Anomalie {ident} ({ligne[0]}) acquittee : {note}")
    print("Elle ne sera plus resignalee tant qu'elle reste identique. "
          "Un evenement different produit une nouvelle anomalie.")
    print(f"Revenir dessus : python scripts/anomalies.py --rouvrir {ident}")
    return 0


def rouvrir(cur, ident: int) -> int:
    cur.execute(ROUVRIR, (ident,))
    ligne = cur.fetchone()
    if ligne is None:
        print(f"Anomalie {ident} : pas un acquittement manuel, ou deja rouverte.")
        return 1
    print(f"Anomalie {ident} ({ligne[0]}) rouverte : elle sera resignalee au "
          f"prochain recalcul si la condition tient toujours.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--severite", default="", choices=["", "blocking", "warning", "info"])
    parser.add_argument("--type", default="", help="issue_type exact")
    parser.add_argument("--resolues", action="store_true", help="lister ce qui a ete traite")
    parser.add_argument("--limite", type=int, default=50)
    parser.add_argument("--detail", type=int, default=0, help="id d'une anomalie")
    parser.add_argument("--resoudre", type=int, default=0, help="id a clore")
    parser.add_argument("--note", default="", help="raison de la cloture")
    parser.add_argument("--rouvrir", type=int, default=0, help="id a rouvrir")
    args = parser.parse_args()

    with connect_direct() as conn:
        with conn.cursor() as cur:
            if args.detail:
                return detailler(cur, args.detail)
            if args.rouvrir:
                code = rouvrir(cur, args.rouvrir)
                conn.commit()
                return code
            if args.resoudre:
                code = resoudre(cur, args.resoudre, args.note)
                conn.commit()
                return code
            return lister(cur, args)


if __name__ == "__main__":
    raise SystemExit(main())
