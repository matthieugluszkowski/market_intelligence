"""Cycle d'actualisation : le point d'entree unique du cron (lot L7).

Le principe P5 - l'historisation de `regression_fits` - ne produit sa valeur que
par regularite. Chaque passage manque est une observation hors echantillon
definitivement perdue, et c'est le seul cout du projet qui ne se rattrape
jamais. Ce module existe pour qu'aucun passage ne depende de quelqu'un qui y
pense.

**Toutes les etapes ne se paient pas le meme prix.** Les cours changent a chaque
seance ; les operations sur titre quelques fois par an ; les comptes quatre fois
par an - or leur ingestion coute 7 minutes de debit menage vers yfinance. Chaque
etape porte donc son intervalle minimal, et le cycle relit `ingestion_runs` pour
savoir ce qui a vieilli : un passage de 8 h ne relance que ce qui le merite.

**Une etape qui echoue n'interrompt pas le cycle.** Les suivantes tournent, et le
code de sortie vaut 1 pour qu'un cron puisse alerter. Seules les etapes qui en
dependent sont sautees : historiser un fit du jour sur des cours dont on sait que
le rafraichissement vient d'echouer, ce serait ecrire une observation fausse dans
la seule serie que ce projet ne rejouera jamais.
"""

from __future__ import annotations

import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from ..db import connect_direct
from . import (
    backfill_prices,
    compute_fits,
    compute_quality,
    ingest_corporate_actions,
    ingest_fundamentals,
    quality_checks,
)

JOUR = timedelta(days=1)
TOUJOURS = timedelta(0)


@dataclass(frozen=True)
class Etape:
    """Une etape du cycle.

    `nom` doit valoir exactement le `job_name` que le job ecrit dans
    `ingestion_runs` : c'est cette egalite qui permet de lire son age sans
    tenir un second registre qui divergerait du premier.
    """

    nom: str
    lance: Callable[[], dict]
    intervalle: timedelta
    role: str
    depend_de: tuple[str, ...] = ()


ETAPES: tuple[Etape, ...] = (
    Etape("backfill_prices", lambda: backfill_prices.run(freqs=("1w", "1d")),
          TOUJOURS, "cours hebdomadaires et quotidiens"),
    Etape("ingest_corporate_actions", ingest_corporate_actions.run,
          JOUR, "dividendes, splits, facteurs d'ajustement"),
    Etape("ingest_fundamentals", ingest_fundamentals.run,
          30 * JOUR, "comptes annuels et trimestriels"),
    Etape("quality_checks", quality_checks.run,
          TOUJOURS, "les neuf controles"),
    Etape("compute_fits", compute_fits.run,
          TOUJOURS, "regressions, z-scores du screener",
          depend_de=("backfill_prices",)),
    # La jambe qualite suit les comptes, pas les cours : la recalculer a chaque
    # passage ne changerait rien. Mais ne pas la recalculer du tout apres une
    # ingestion de fondamentaux laisserait le screener classer les titres sur
    # des comptes que la base a deja remplaces.
    Etape("compute_quality", compute_quality.run,
          30 * JOUR, "scores de qualite, jambe concurrentielle",
          depend_de=("ingest_fundamentals",)),
)

DERNIERS_SUCCES = """
select job_name, max(finished_at) as fin
  from ingestion_runs
 where status in ('success', 'partial')
   and job_name = any(%(noms)s)
 group by job_name;
"""


def derniers_succes(noms: list[str]) -> dict[str, datetime]:
    """Date du dernier passage utile de chaque job, `partial` compris.

    Un passage `partial` a fait le travail pour la grande majorite des titres :
    le compter comme un echec relancerait 57 telechargements pour 2 titres.
    """
    with connect_direct() as conn, conn.cursor() as cur:
        cur.execute(DERNIERS_SUCCES, {"noms": noms})
        return {nom: fin for nom, fin in cur.fetchall() if fin is not None}


def age_en_clair(delta: timedelta) -> str:
    heures, reste = divmod(int(delta.total_seconds()), 3600)
    if heures >= 48:
        return f"{heures // 24} j"
    return f"{heures} h" if heures else f"{reste // 60} min"


def doit_tourner(etape: Etape, dernier: datetime | None, maintenant: datetime,
                 force: bool = False, echouees: frozenset[str] = frozenset(),
                 ) -> tuple[bool, str]:
    """Faut-il lancer cette etape maintenant ? Retourne (oui, motif du refus).

    Fonction pure : c'est elle qui porte toute la regle de cadence, et c'est
    elle que les tests eprouvent - `run` ne fait que l'appliquer.
    """
    bloquantes = [d for d in etape.depend_de if d in echouees]
    if bloquantes:
        return False, f"depend de {', '.join(bloquantes)}, en echec"
    if force or dernier is None:
        return True, ""
    age = maintenant - dernier
    if age < etape.intervalle:
        return False, (f"actualise il y a {age_en_clair(age)}, "
                       f"intervalle {age_en_clair(etape.intervalle)}")
    return True, ""


def run(force: bool = False, seulement: tuple[str, ...] = ()) -> dict:
    """Enchaine les etapes, retourne le compte rendu de chacune.

    `force` ignore les intervalles - utile pour une reprise a la main apres une
    panne, jamais pour le cron.
    """
    debut = datetime.now(timezone.utc)
    etapes = [e for e in ETAPES if not seulement or e.nom in seulement]
    if seulement:
        inconnues = set(seulement) - {e.nom for e in ETAPES}
        if inconnues:
            raise ValueError(f"etape inconnue : {', '.join(sorted(inconnues))}")

    derniers = derniers_succes([e.nom for e in etapes])
    resume: dict = {"debut": debut.isoformat(timespec="seconds"), "etapes": []}
    echouees: set[str] = set()

    print(f"=== cycle {debut.isoformat(timespec='seconds')} "
          f"({len(etapes)} etapes){' [force]' if force else ''} ===\n")

    for etape in etapes:
        tourne, motif = doit_tourner(etape, derniers.get(etape.nom), debut,
                                     force=force, echouees=frozenset(echouees))
        if not tourne:
            ligne = {"etape": etape.nom, "statut": "saute", "raison": motif}
        else:
            ligne = _execute(etape)
            if ligne["statut"] == "echec":
                echouees.add(etape.nom)

        resume["etapes"].append(ligne)
        marque = {"ok": "  ", "saute": "- ", "echec": "X "}[ligne["statut"]]
        detail = ligne.get("raison") or f"{ligne.get('duree_sec', 0):.0f} s"
        print(f"{marque}{etape.nom:<26} {detail}")

    duree = (datetime.now(timezone.utc) - debut).total_seconds()
    resume["duree_sec"] = round(duree, 1)
    resume["echecs"] = sorted(echouees)
    print(f"\n=== cycle termine en {duree / 60:.1f} min, "
          f"{len(echouees)} echec(s) ===\n")
    return resume


def _execute(etape: Etape) -> dict:
    print(f"\n--- {etape.nom} : {etape.role} ---")
    depart = time.monotonic()
    try:
        detail = etape.lance()
    except Exception as exc:  # noqa: BLE001 - un cron veut un compte rendu, pas une trace perdue
        traceback.print_exc()
        return {"etape": etape.nom, "statut": "echec",
                "duree_sec": round(time.monotonic() - depart, 1),
                "raison": f"{type(exc).__name__}: {exc}"[:500]}
    ligne = {"etape": etape.nom, "statut": "ok",
             "duree_sec": round(time.monotonic() - depart, 1)}
    # Un echec par instrument ne fait pas echouer l'etape - le job l'a deja
    # journalise en `partial` - mais il doit rester lisible dans le log du cron.
    rates = (detail or {}).get("failed_instruments") or []
    if rates:
        ligne["partiels"] = len(rates)
    return ligne
