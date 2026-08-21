"""Import d'un dossier concurrentiel et projection vers le moteur quantitatif.

Ce que l'import fait, et dans cet ordre
----------------------------------------
1. valide le dossier contre le contrat ; **s'arrete la si un bloquant subsiste** ;
2. stocke le dossier tel quel dans `market_analyses` ;
3. si et seulement si un analyste est nomme, projette :
   - les concurrents retenus vers `peer_groups` / `peer_group_members` ;
   - les verdicts vers `moat_assessments`, avec `reviewed_by` = l'analyste.

**Le nom de l'analyste est le pivot de tout le dispositif.** Il ne se deduit
d'aucune donnee : il est saisi a l'import, et c'est ce geste - et lui seul - qui
distingue un dossier relu d'un dossier produit. Sans lui, le dossier est
conserve, consultable, mais ne projette rien et ne fait passer aucun titre en
`solid`.

On ne complete jamais une donnee manquante en silence : ce qui manque ressort
dans le rapport, et `null` reste `null`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date

from .schema import (EUROPE, FRAGMENTS, Validation, fusionne, lire,
                     peremption, valide)

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


@dataclass
class ResultatImport:
    validation: Validation
    analyse_id: int | None = None
    groupe_id: int | None = None
    moat_id: int | None = None
    concurrents_internes: int = 0
    concurrents_externes: int = 0
    projete: bool = False
    type_fragment: str = "controle"
    fusionne_avec_precedent: bool = False
    dossier: dict | None = None
    messages: list = field(default_factory=list)


def _resout_concurrents(cur, concurrents: list) -> tuple[list, list]:
    """Separe les concurrents deja dans l'univers de ceux qui n'y sont pas.

    L'appariement se fait sur le nom, en tolerant la casse et les espaces. Un
    concurrent non apparie n'est pas une erreur : c'est le cas le plus frequent
    et le plus utile - SharkNinja, BYD et Revolut ne sont dans aucun univers
    europeen.
    """
    internes, externes = [], []
    for c in concurrents:
        nom = (lire(c, "company_name") or "").strip()
        if not nom:
            continue
        cur.execute(
            "select id, internal_code from instruments "
            "where lower(name) = lower(%s) or upper(internal_code) = upper(%s) "
            "limit 1",
            (nom, nom),
        )
        ligne = cur.fetchone()
        if ligne:
            internes.append((ligne[0], nom, c))
        else:
            externes.append((nom, c))
    return internes, externes


DOSSIER_EXISTANT = """
select dossier, status, analyst, validated_at from market_analyses
 where instrument_id = %(instrument_id)s
 order by reference_date desc, imported_at desc limit 1;
"""


def importe(cur, instrument_id: int, internal_code: str, sector_code: str | None,
            fragment: dict, analyste: str | None,
            type_fragment: str = "controle",
            nom_instrument: str | None = None) -> ResultatImport:
    """Integre un fragment, puis projette si le dossier est complet et signe.

    Chaque prompt rend un JSON de forme differente : le dossier se construit par
    **accumulation**, fragment par fragment. On repart du dernier dossier connu
    pour ce titre et on y ajoute - on n'ecrase jamais, sinon l'ordre d'import
    deviendrait une variable cachee du resultat.

    Seul le fragment `controle`, sortie du prompt 4, est un dossier normalise
    complet. Les trois autres enrichissent un brouillon et ne projettent rien,
    meme signes : projeter sur un dossier partiel reviendrait a qualifier un
    titre avant d'avoir fini de le regarder.
    """
    cur.execute(DOSSIER_EXISTANT, {"instrument_id": instrument_id})
    ligne = cur.fetchone()
    precedent = ligne[0] if ligne else None
    statut_precedent = ligne[1] if ligne else None
    analyste_precedent = ligne[2] if ligne else None
    valide_le_precedent = ligne[3] if ligne else None

    dossier = fusionne(precedent or {}, fragment, type_fragment)

    # Le nom de l'entreprise analysee vient de l'instrument choisi a l'ecran :
    # aucun fragment intermediaire ne le porte, et sans lui le dossier final
    # serait refuse pour « entreprise analysee absente ».
    if nom_instrument:
        meta_fusion = dossier.setdefault("analysis_metadata", {})
        if not meta_fusion.get("company_analyzed"):
            meta_fusion["company_analyzed"] = nom_instrument

    resultat = ResultatImport(validation=valide(dossier))
    resultat.type_fragment = type_fragment
    resultat.fusionne_avec_precedent = precedent is not None

    if type_fragment != "controle":
        # Un fragment intermediaire est conserve tel quel, sans exiger la
        # completude. **Il n'annule pas une validation existante** : ajouter la
        # synthese du prompt 5 a un dossier signe ne retire pas la signature -
        # le bloc ajoute porte son propre etat de relecture (`not_reviewed`).
        resultat.dossier = dossier
        conserve_validation = (statut_precedent == "validated"
                               and analyste_precedent)
        _enregistre(cur, instrument_id, internal_code, dossier,
                    analyste=analyste_precedent if conserve_validation else None,
                    force_draft=not conserve_validation, resultat=resultat,
                    valide_le=valide_le_precedent if conserve_validation else None)
        if type_fragment == "synthese":
            resultat.messages.append(
                "Synthèse et scores intégrés. **Les scores mesurent la solidité "
                "du dossier et la confiance dans l'analyse, jamais le cours "
                "futur.** Produits par LLM, non relus : la relecture se fait "
                "sur la fiche instrument."
            )
        else:
            resultat.messages.append(
                f"Fragment « {FRAGMENTS.get(type_fragment, type_fragment)} » integre "
                f"au brouillon. Aucune projection : seul le dossier normalise du "
                f"prompt 4 qualifie un titre."
            )
        if conserve_validation:
            resultat.messages.append(
                f"Le dossier reste validé par {analyste_precedent} : un ajout "
                f"n'efface pas une relecture."
            )
        return resultat

    if not resultat.validation.importable:
        # Refuser tout enregistrement ferait perdre le travail accumule : le
        # prompt 4 signale presque toujours des points a verifier, c'est son
        # role. Le dossier est donc **conserve en brouillon**, sans validation
        # ni projection - rien n'est complete automatiquement, et le titre
        # reste non qualifie tant que les bloquants ne sont pas traites ou
        # acquittes nominativement.
        _enregistre(cur, instrument_id, internal_code, dossier, analyste=None,
                    force_draft=True, resultat=resultat)
        details = "; ".join(p.element for p in resultat.validation.bloquants)
        resultat.messages.append(
            f"{len(resultat.validation.bloquants)} probleme(s) bloquant(s) "
            f"({details}) : dossier conserve en `draft`, sans validation ni "
            f"projection. Corriger les points signales - ou verifier a la main "
            f"et acquitter nominativement ceux du controle qualite - puis "
            f"reimporter."
        )
        return resultat

    resultat.dossier = dossier
    meta = lire(dossier, "analysis_metadata", defaut={})
    reference = lire(meta, "reference_date")
    reference_date = (date.fromisoformat(reference)
                      if isinstance(reference, str) else date.today())
    analysis_id = (lire(meta, "analysis_id")
                   or f"{internal_code}@{reference_date.isoformat()}")

    analyste = (analyste or "").strip() or None
    statut = "validated" if analyste else "draft"

    # Le dossier stocke porte la trace de sa validation : on ne laisse pas
    # `analyst` a null cote JSON si un humain vient de le signer.
    dossier_stocke = json.loads(json.dumps(dossier))
    dossier_stocke.setdefault("analysis_metadata", {})
    dossier_stocke["analysis_metadata"]["analyst"] = analyste
    dossier_stocke["analysis_metadata"]["status"] = statut
    dossier_stocke.setdefault("quality_control", {})
    dossier_stocke["quality_control"]["validated"] = bool(analyste)
    if analyste:
        dossier_stocke["quality_control"]["review_date"] = date.today().isoformat()

    cur.execute(UPSERT_ANALYSE, {
        "instrument_id": instrument_id, "analysis_id": analysis_id,
        "reference_date": reference_date, "status": statut, "analyst": analyste,
        "dossier": json.dumps(dossier_stocke, ensure_ascii=False),
        "validated_at": date.today() if analyste else None,
        "expires_at": peremption(reference_date),
    })
    resultat.analyse_id = cur.fetchone()[0]
    resultat.dossier = dossier_stocke

    if not analyste:
        resultat.messages.append(
            "Dossier conserve en `draft`. **Aucune projection** : sans nom "
            "d'analyste, rien ne distingue un dossier relu d'un dossier produit, "
            "et le titre reste non qualifie."
        )
        return resultat

    # --- projection vers le groupe de pairs --------------------------------
    concurrents = lire(dossier, "competitors", defaut=[])
    internes, externes = _resout_concurrents(cur, concurrents)

    hors_europe = [
        (nom, c) for nom, c in externes
        if (lire(c, "country", defaut="") or "").upper()[:2] not in EUROPE
        and lire(c, "country")
    ]
    complet = bool(hors_europe)

    cur.execute(UPSERT_GROUPE, {
        "code": f"DOSSIER:{internal_code}",
        "label": f"Dossier concurrentiel - {lire(meta, 'company_analyzed', defaut=internal_code)}",
        "sector_code": sector_code,
        "is_complete": complet,
        "notes": (f"Issu du dossier {analysis_id}, relu par {analyste}. "
                  f"{len(internes)} pair(s) dans l'univers, {len(externes)} hors "
                  f"univers, dont {len(hors_europe)} hors Europe."),
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
                "pays": lire(c, "country"),
                "type": lire(c, "competition_type"),
                "justification": lire(c, "relevance_explanation"),
                "statut": lire(c, "status"),
                "ca_musd": lire(c, "revenue_musd"),   # null tant que non saisi
            }, ensure_ascii=False),
        })
    resultat.concurrents_externes = len(externes)

    if not complet:
        resultat.messages.append(
            "Groupe marque **incomplet** : aucun concurrent hors Europe avec un "
            "code pays renseigne. Le titre restera plafonne a `watch`."
        )

    # --- projection vers l'evaluation qualitative ---------------------------
    strategie = lire(dossier, "strategic_assessment", defaut={})
    position = lire(strategie, "position_verdict", defaut=None)
    durabilite = lire(strategie, "durability_verdict", defaut=None)
    if position and durabilite:
        cur.execute(INSERT_MOAT, {
            "instrument_id": instrument_id,
            "assessed_at": reference_date,
            "expires_at": peremption(reference_date),
            "moat_sources": lire(strategie, "moat_sources", defaut=None),
            "position_verdict": position,
            "durability_verdict": durabilite,
            "threats": json.dumps(lire(strategie, "threats", defaut=[]),
                                  ensure_ascii=False),
            "peer_group_id": resultat.groupe_id,
            "rationale": lire(strategie, "rationale",
                              defaut="Voir le dossier complet."),
            "sources": json.dumps(lire(dossier, "sources", defaut=[]),
                                  ensure_ascii=False),
            "authored_by": lire(meta, "authored_by", defaut="llm:non precise"),
            "reviewed_by": analyste,
            "confidence": lire(dossier, "quality_control", "quality_score",
                               defaut=None),
        })
        resultat.moat_id = cur.fetchone()[0]
    else:
        resultat.messages.append(
            "Aucune evaluation qualitative projetee : `strategic_assessment` doit "
            "porter `position_verdict` et `durability_verdict`. Le groupe de "
            "pairs est enregistre, mais le titre ne pourra pas atteindre `solid`."
        )

    resultat.projete = True
    return resultat


def _enregistre(cur, instrument_id: int, internal_code: str, dossier: dict,
                analyste: str | None, force_draft: bool,
                resultat: ResultatImport, valide_le=None) -> None:
    """Ecrit le dossier sans projeter. Utilise par les fragments 1, 2, 3 et 5.

    `force_draft=False` avec un analyste conserve une validation existante :
    un fragment additif n'efface pas une relecture deja faite.
    """
    meta = lire(dossier, "analysis_metadata", defaut={})
    reference = lire(meta, "reference_date")
    reference_date = (date.fromisoformat(reference)
                      if isinstance(reference, str) else date.today())
    analysis_id = (lire(meta, "analysis_id")
                   or f"{internal_code}@{reference_date.isoformat()}")

    statut = "draft" if force_draft or not analyste else "validated"

    stocke = json.loads(json.dumps(dossier, ensure_ascii=False, default=str))
    stocke.setdefault("analysis_metadata", {})
    stocke["analysis_metadata"]["analysis_id"] = analysis_id
    stocke["analysis_metadata"]["status"] = statut
    # La date de reference est persistee dans le dossier lui-meme : sinon elle
    # se perd d'un fragment a l'autre, et le dossier final ressort incomplet.
    stocke["analysis_metadata"]["reference_date"] = reference_date.isoformat()
    stocke["analysis_metadata"].setdefault("analyst", None)
    if statut == "validated":
        stocke["analysis_metadata"]["analyst"] = analyste
    stocke.setdefault("quality_control", {})
    stocke["quality_control"].setdefault("validated", False)
    if statut != "validated":
        stocke["quality_control"]["validated"] = False

    cur.execute(UPSERT_ANALYSE, {
        "instrument_id": instrument_id, "analysis_id": analysis_id,
        "reference_date": reference_date, "status": statut,
        "analyst": analyste if statut == "validated" else None,
        "dossier": json.dumps(stocke, ensure_ascii=False),
        "validated_at": (valide_le or date.today()) if statut == "validated" else None,
        "expires_at": peremption(reference_date),
    })
    resultat.analyse_id = cur.fetchone()[0]
    resultat.dossier = stocke
