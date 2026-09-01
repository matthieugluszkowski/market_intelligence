"""Import d'un dossier de position concurrentielle, et sa projection.

Ce que l'import fait, et ce qu'il refuse de faire
--------------------------------------------------
Il ecrit le dossier dans `market_analyses`, puis - **et seulement si un analyste
est nomme** - il projette deux choses vers le moteur quantitatif :

- le **groupe de pairs** `DOSSIER:<code>`, construit avec les concurrents cites.
  C'est ce qui permet enfin de comparer une entreprise a ses vrais concurrents
  plutot qu'a sa case sectorielle : EssilorLuxottica etait compare a Sanofi et
  UCB parce que son groupe automatique s'appelait « Secteur Health Care ».
- l'**evaluation qualitative** (`moat_assessments`), sans laquelle aucun titre
  ne peut atteindre `solid` : le moat quantitatif mesure le passe, seule la
  jambe qualitative peut ecrire « cette barriere est menacee par X ».

**Sans nom d'analyste, rien n'est projete.** Le dossier est conserve en
brouillon. Ce n'est pas une formalite : rien ne distingue un dossier relu d'un
dossier produit, et projeter le second reviendrait a qualifier un titre sur la
foi d'un texte que personne n'a lu.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date

from . import position as P
from .schema import EUROPE, peremption

UPSERT_ANALYSE = """
insert into market_analyses
  (instrument_id, analysis_id, reference_date, status, analyst, dossier,
   validated_at, expires_at)
values (%(instrument_id)s, %(analysis_id)s, %(reference_date)s, %(status)s,
        %(analyst)s, %(dossier)s, %(validated_at)s, %(expires_at)s)
on conflict (analysis_id) do update set
  status = excluded.status, analyst = excluded.analyst,
  dossier = excluded.dossier, validated_at = excluded.validated_at,
  expires_at = excluded.expires_at, imported_at = now()
returning id;
"""

UPSERT_GROUPE = """
insert into peer_groups (code, label, kind, sector_code, is_complete, notes)
values (%(code)s, %(label)s, 'manual', %(sector_code)s, %(is_complete)s, %(notes)s)
on conflict (code) do update set
  label = excluded.label, is_complete = excluded.is_complete,
  notes = excluded.notes
returning id;
"""

UPSERT_MEMBRE_INTERNE = """
insert into peer_group_members (peer_group_id, instrument_id, is_in_universe)
values (%(groupe_id)s, %(instrument_id)s, true)
on conflict do nothing;
"""

UPSERT_MEMBRE_EXTERNE = """
insert into peer_group_members
  (peer_group_id, external_name, external_ref, is_in_universe)
values (%(groupe_id)s, %(nom)s, %(reference)s, false)
on conflict do nothing;
"""

INSERT_MOAT = """
insert into moat_assessments
  (instrument_id, assessed_at, expires_at, moat_sources, position_verdict,
   durability_verdict, threats, peer_group_id, rationale, sources,
   authored_by, reviewed_by, confidence)
values (%(instrument_id)s, %(assessed_at)s, %(expires_at)s, %(moat_sources)s,
        %(position_verdict)s, %(durability_verdict)s, %(threats)s,
        %(peer_group_id)s, %(rationale)s, %(sources)s, %(authored_by)s,
        %(reviewed_by)s, %(confidence)s)
returning id;
"""

DOSSIER_EXISTANT = """
select id, dossier, status, analyst from market_analyses
 where instrument_id = %(instrument_id)s
 order by reference_date desc, imported_at desc limit 1;
"""


@dataclass
class ResultatImport:
    validation: P.Validation
    score: P.Score | None = None
    analyse_id: int | None = None
    groupe_id: int | None = None
    moat_id: int | None = None
    concurrents_internes: int = 0
    concurrents_externes: int = 0
    projete: bool = False
    dossier: dict | None = None
    messages: list = field(default_factory=list)


def _resout_concurrents(cur, concurrents: list) -> tuple[list, list]:
    """Separe les concurrents deja dans l'univers de ceux qui n'y sont pas.

    Un concurrent non apparie n'est pas une erreur : c'est le cas le plus
    frequent **et le plus utile** - SharkNinja, BYD et Revolut ne sont dans
    aucun univers europeen, et ce sont eux qui menacent.
    """
    internes, externes = [], []
    for c in concurrents:
        nom = (P.lire(c, "nom") or "").strip()
        if not nom:
            continue
        cur.execute(
            "select id from instruments "
            "where lower(name) = lower(%s) or upper(internal_code) = upper(%s) "
            "limit 1", (nom, nom))
        ligne = cur.fetchone()
        if ligne:
            internes.append((ligne[0], nom, c))
        else:
            externes.append((nom, c))
    return internes, externes


def _hors_europe(concurrent: dict) -> bool:
    """Le pays arrive tantot en code (« US »), tantot en clair (« Japon »)."""
    pays = (P.lire(concurrent, "pays") or "").strip()
    if not pays:
        return False
    if len(pays) <= 3:
        return pays.upper()[:2] not in EUROPE
    return not _pays_europeen(pays)


_NOMS_EUROPEENS = {
    "france", "allemagne", "italie", "espagne", "pays-bas", "belgique",
    "portugal", "irlande", "autriche", "finlande", "suede", "danemark",
    "norvege", "suisse", "royaume-uni", "pologne", "grece", "luxembourg",
}


def _pays_europeen(nom: str) -> bool:
    """Le LLM ecrit tantot « DE », tantot « Allemagne » : les deux comptent."""
    propre = nom.strip().lower().split("(")[0].strip()
    return propre in _NOMS_EUROPEENS


def importe(cur, instrument_id: int, internal_code: str,
            sector_code: str | None, dossier: dict,
            analyste: str | None) -> ResultatImport:
    """Valide, enregistre, et projette si un analyste est nomme."""
    validation = P.valide(dossier)
    resultat = ResultatImport(validation=validation)
    if not validation.importable:
        return resultat

    resultat.score = P.calcule_le_score(dossier)

    reference = P._date_de_reference(dossier)
    analysis_id = f"{internal_code}@{reference.isoformat()}"
    statut = "validated" if analyste else "draft"

    stocke = json.loads(json.dumps(dossier, ensure_ascii=False, default=str))
    stocke["version"] = P.VERSION
    stocke["date_reference"] = reference.isoformat()
    stocke["analysis_id"] = analysis_id
    stocke["statut"] = statut
    stocke["analyste"] = analyste if analyste else None
    # Le score est fige avec le dossier : il se recalcule a l'identique depuis
    # les verdicts, mais l'ecrire evite de dependre du bareme du jour pour
    # relire une decision de l'an dernier.
    stocke["score"] = {
        "total": resultat.score.total,
        "niveau": resultat.score.niveau,
        "lignes": [{"libelle": l.libelle, "detail": l.detail, "points": l.points}
                   for l in resultat.score.lignes],
        "reserves": resultat.score.reserves,
        "bareme_version": P.VERSION,
    }

    cur.execute(UPSERT_ANALYSE, {
        "instrument_id": instrument_id, "analysis_id": analysis_id,
        "reference_date": reference, "status": statut,
        "analyst": analyste if analyste else None,
        "dossier": json.dumps(stocke, ensure_ascii=False),
        "validated_at": date.today() if analyste else None,
        "expires_at": peremption(reference),
    })
    resultat.analyse_id = cur.fetchone()[0]
    resultat.dossier = stocke

    if not analyste:
        resultat.messages.append(
            "Dossier conserve en brouillon. **Aucune projection** : sans nom "
            "d'analyste, rien ne distingue un dossier relu d'un dossier "
            "produit, et le titre reste non qualifie.")
        return resultat

    projette(cur, instrument_id, internal_code, sector_code, stocke, analyste,
             resultat)
    return resultat


def projette(cur, instrument_id: int, internal_code: str,
             sector_code: str | None, dossier: dict, analyste: str,
             resultat: ResultatImport) -> None:
    """Groupe de pairs et evaluation qualitative, depuis le dossier relu."""
    concurrents = P.lire(dossier, "concurrents", defaut=[]) or []
    internes, externes = _resout_concurrents(cur, concurrents)

    # Un groupe purement europeen est structurellement aveugle : les menaces
    # reelles viennent presque toujours de l'exterieur de l'univers.
    hors_europe = [(nom, c) for nom, c in externes if _hors_europe(c)]
    complet = bool(hors_europe)

    cur.execute(UPSERT_GROUPE, {
        "code": f"DOSSIER:{internal_code}",
        "label": f"Concurrents de {P.lire(dossier, 'entreprise', defaut=internal_code)}",
        "sector_code": sector_code,
        "is_complete": complet,
        "notes": (f"Issu du dossier de position relu par {analyste}. "
                  f"{len(internes)} concurrent(s) dans l'univers, "
                  f"{len(externes)} hors univers, dont {len(hors_europe)} hors "
                  f"Europe."),
    })
    resultat.groupe_id = cur.fetchone()[0]

    cur.execute(UPSERT_MEMBRE_INTERNE,
                {"groupe_id": resultat.groupe_id, "instrument_id": instrument_id})
    for pair_id, _nom, _c in internes:
        cur.execute(UPSERT_MEMBRE_INTERNE,
                    {"groupe_id": resultat.groupe_id, "instrument_id": pair_id})
    resultat.concurrents_internes = len(internes)

    for nom, c in externes:
        cur.execute(UPSERT_MEMBRE_EXTERNE, {
            "groupe_id": resultat.groupe_id, "nom": nom,
            "reference": json.dumps({
                "pays": P.lire(c, "pays"),
                "type": P.lire(c, "type"),
                "danger": P.lire(c, "danger"),
                "pourquoi": P.lire(c, "pourquoi_dangereux"),
            }, ensure_ascii=False),
        })
    resultat.concurrents_externes = len(externes)

    if not complet:
        resultat.messages.append(
            "Groupe marque **incomplet** : aucun concurrent hors Europe avec un "
            "pays renseigne. Le titre restera plafonne a `watch`.")

    verdict = P.lire(dossier, "position", "verdict")
    durabilite = P.lire(dossier, "durabilite", "verdict")
    if verdict and durabilite:
        score = P.lire(dossier, "score", "total")
        cur.execute(INSERT_MOAT, {
            "instrument_id": instrument_id,
            "assessed_at": P._date_de_reference(dossier),
            "expires_at": peremption(P._date_de_reference(dossier)),
            "moat_sources": P.lire(dossier, "durabilite", "sources_de_rente",
                                    defaut=None),
            # `moat_assessments` garde le vocabulaire du doc 08 : la position
            # `suiveur` s'y ecrit `follower`.
            "position_verdict": {"suiveur": "follower"}.get(verdict, verdict),
            "durability_verdict": durabilite,
            "threats": json.dumps(P.menaces(dossier), ensure_ascii=False),
            "peer_group_id": resultat.groupe_id,
            "rationale": P.lire(dossier, "resume", defaut="Voir le dossier."),
            "sources": json.dumps(P.lire(dossier, "sources", defaut=[]),
                                  ensure_ascii=False),
            "authored_by": "llm",
            "reviewed_by": analyste,
            "confidence": (score / 100) if isinstance(score, int) else None,
        })
        resultat.moat_id = cur.fetchone()[0]
    else:
        resultat.messages.append(
            "Aucune evaluation qualitative projetee : il manque le verdict de "
            "position ou de durabilite. Le titre ne pourra pas atteindre "
            "`solid`.")

    resultat.projete = True
