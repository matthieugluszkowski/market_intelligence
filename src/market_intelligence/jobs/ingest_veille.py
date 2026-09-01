"""Collecte de la veille externe : consensus, notations, depeches (lot L10).

Ce job est le seul du projet qui **n alimente aucun calcul**. Il remplit
`external_briefs`, que la fiche instrument affiche a cote du signal - jamais
dedans. La raison tient en une phrase : le consensus des analystes est
structurellement optimiste et revise apres coup, et une methode qui l integre a
son score achete ce que tout le monde recommande deja.

Perimetre par defaut : les titres suivis
-----------------------------------------
L univers compte 586 titres et chaque titre coute une dizaine de requetes, avec
un delai entre chacune. Passer l univers entier prendrait des heures et
martelerait deux serveurs qui nous rendent service pour des pages que personne
n ira lire. Le defaut est donc **watchlist + portefeuille** : ce qu on suit
vraiment. `--tout` existe, il faut le demander.

La fraicheur compte, et elle est visible
-----------------------------------------
Une depeche de trois semaines affichee sans sa date se lit comme une nouvelle du
jour. Chaque collecte est datee, conservee, et l ecran affiche l age de ce qu il
montre.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from ..collectors import boursier, zonebourse
from ..db import connect_direct
from ..loaders.journal import ingestion_run

logger = logging.getLogger(__name__)

SOURCES = {"zonebourse": 8, "boursier": 9}

CIBLES_SUIVIES = """
select distinct i.id, i.internal_code, i.name, i.isin
  from instruments i
 where i.is_active
   and (exists (select 1 from watchlist w
                 where w.instrument_id = i.id and w.removed_at is null)
     or exists (select 1 from positions p
                 where p.instrument_id = i.id and p.closed_at is null)
     -- Une adresse Zonebourse est **saisie a la main** : l'avoir collee est
     -- une declaration d'interet aussi nette qu'une etoile de watchlist. Celle
     -- de Boursier.com ne compte pas - elle s'enregistre toute seule au premier
     -- passage, et suffirait a faire entrer dans le cycle nocturne n'importe
     -- quel titre regarde une fois.
     or exists (select 1 from external_sources s
                 where s.instrument_id = i.id
                   and s.source_code = 'zonebourse'))
 order by i.internal_code;
"""

CIBLES_TOUTES = """
select i.id, i.internal_code, i.name, i.isin
  from instruments i
 where i.is_active and i.asset_class = 'equity' and i.isin is not null
 order by i.internal_code;
"""

CIBLES_NOMMEES = """
select i.id, i.internal_code, i.name, i.isin
  from instruments i
 where i.internal_code = any(%(codes)s)
 order by i.internal_code;
"""

LIT_URL = """
select url from external_sources
 where instrument_id = %(instrument_id)s and source_code = %(source)s;
"""

ECRIT_URL = """
insert into external_sources (instrument_id, source_code, url)
values (%(instrument_id)s, %(source)s, %(url)s)
on conflict (instrument_id, source_code) do update set
  url = excluded.url, added_at = now();
"""

ECRIT_BRIEF = """
insert into external_briefs
  (instrument_id, source_code, kind, source_url, payload)
values (%(instrument_id)s, %(source)s, %(kind)s, %(url)s, %(payload)s)
on conflict (instrument_id, source_code, kind, collected_on) do update set
  payload = excluded.payload, source_url = excluded.source_url,
  collected_at = now()
returning id;
"""


@dataclass
class Resultat:
    """Ce qui a ete collecte pour un titre, et ce qui a manque."""

    internal_code: str
    consensus: bool = False
    notations: bool = False
    depeches: int = 0
    erreurs: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.consensus or self.notations or bool(self.depeches)

    def resume(self) -> str:
        morceaux = []
        morceaux.append("consensus" if self.consensus else "consensus —")
        morceaux.append("notations" if self.notations else "notations —")
        morceaux.append(f"{self.depeches} depeche(s)")
        return " · ".join(morceaux)


def url_zonebourse(cur, instrument_id: int) -> str | None:
    cur.execute(LIT_URL, {"instrument_id": instrument_id, "source": "zonebourse"})
    ligne = cur.fetchone()
    return ligne[0] if ligne else None


def enregistre_url(cur, instrument_id: int, source: str, url: str) -> None:
    """Associe une adresse de fiche a un titre. Normalisee pour Zonebourse :
    l utilisateur colle l onglet ou il se trouve, pas la racine."""
    propre = (zonebourse.normalise_url(url) if source == "zonebourse"
              else (url or "").strip())
    cur.execute(ECRIT_URL, {"instrument_id": instrument_id, "source": source,
                            "url": propre})


def _ecrit(cur, instrument_id: int, source: str, kind: str, payload,
           url: str | None) -> None:
    cur.execute(ECRIT_BRIEF, {
        "instrument_id": instrument_id, "source": source, "kind": kind,
        "url": url,
        "payload": json.dumps(payload, ensure_ascii=False, default=str),
    })


def collecte_un(cur, instrument_id: int, internal_code: str, isin: str | None,
                *, delai_sec: float = 1.0,
                articles_complets: int = boursier.ARTICLES_COMPLETS) -> Resultat:
    """Collecte les trois natures pour un titre. N ecrit que ce qui a ete lu.

    Ne leve pas : une source qui refuse la requete est un fait a journaliser,
    pas une raison de faire tomber la collecte des autres titres.
    """
    resultat = Resultat(internal_code=internal_code)

    url_fiche = url_zonebourse(cur, instrument_id)
    if url_fiche:
        lu = zonebourse.collecte(url_fiche, delai_sec=delai_sec)
        if lu.consensus:
            _ecrit(cur, instrument_id, "zonebourse", "consensus", lu.consensus,
                   lu.consensus.get("url"))
            resultat.consensus = True
        if lu.notations:
            _ecrit(cur, instrument_id, "zonebourse", "notations", lu.notations,
                   lu.notations.get("url"))
            resultat.notations = True
        resultat.erreurs.extend(lu.erreurs)
    else:
        resultat.erreurs.append(
            "zonebourse : aucune URL enregistree pour ce titre. La coller depuis "
            "la fiche instrument — l identifiant interne de la source ne se "
            "devine pas et un mauvais identifiant rend la fiche d une autre "
            "societe.")

    if isin:
        lu = boursier.collecte(isin, delai_sec=delai_sec,
                               articles_complets=articles_complets)
        if lu.depeches:
            _ecrit(cur, instrument_id, "boursier", "depeches",
                   {"source": boursier.SOURCE, "url": lu.url,
                    "copyright": boursier.COPYRIGHT,
                    "depeches": [d.en_dict() for d in lu.depeches]},
                   lu.url)
            enregistre_url(cur, instrument_id, "boursier", lu.url)
            resultat.depeches = len(lu.depeches)
        resultat.erreurs.extend(lu.erreurs)
    else:
        resultat.erreurs.append(
            "boursier : ce titre n a pas d ISIN en base, et l adresse de la "
            "source s en deduit. Le cas est **majoritaire** - 59 titres sur 586 "
            "portent un ISIN depuis l elargissement de l univers. yfinance sait "
            "le donner (`Ticker.isin`) ; le backfill reste a ecrire.")

    return resultat


def run(codes: list | None = None, tout: bool = False, limit: int = 0,
        delai_sec: float = 1.0,
        articles_complets: int = boursier.ARTICLES_COMPLETS) -> dict:
    resume: dict = {"titres": {}, "failed_instruments": []}

    with connect_direct() as conn:
        with conn.cursor() as cur:
            if codes:
                cur.execute(CIBLES_NOMMEES, {"codes": list(codes)})
            elif tout:
                cur.execute(CIBLES_TOUTES)
            else:
                cur.execute(CIBLES_SUIVIES)
            cibles = cur.fetchall()

        if limit:
            cibles = cibles[:limit]
        if not cibles:
            print("Aucun titre a collecter. Suivre un titre, ou enregistrer une "
                  "URL Zonebourse depuis la fiche instrument.")
            return resume

        print(f"{len(cibles)} titre(s) a collecter\n")

        # Le journal se tient sous Zonebourse : une ligne par cycle, pas deux.
        # Les deux sources sont collectees ensemble et echouent separement -
        # c'est `details` qui porte le decompte source par source.
        source_id = SOURCES["zonebourse"]
        with ingestion_run(conn, source_id, "ingest_veille") as compteurs:
            for rang, (instrument_id, code, nom, isin) in enumerate(cibles, 1):
                with conn.cursor() as cur:
                    resultat = collecte_un(
                        cur, instrument_id, code, isin, delai_sec=delai_sec,
                        articles_complets=articles_complets)
                conn.commit()

                compteurs.inserted += (int(resultat.consensus)
                                       + int(resultat.notations)
                                       + int(bool(resultat.depeches)))
                resume["titres"][code] = {
                    "consensus": resultat.consensus,
                    "notations": resultat.notations,
                    "depeches": resultat.depeches,
                    "erreurs": resultat.erreurs,
                }
                if not resultat.ok:
                    resume["failed_instruments"].append(
                        {"internal_code": code,
                         "reason": "; ".join(resultat.erreurs)[:500]})

                marque = " " if resultat.ok else "X"
                print(f"{marque} {rang:>3}/{len(cibles)} {code:<16} "
                      f"{resultat.resume()}")
                for erreur in resultat.erreurs:
                    print(f"      · {erreur}")

            compteurs.details = resume

    return resume
