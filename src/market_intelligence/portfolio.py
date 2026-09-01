"""Portefeuille et paper trading (doc 11).

Ce que ce module fait, et ce qu'il refuse de faire
---------------------------------------------------
Il enregistre des positions, calcule un prix de revient, une valorisation et un
rendement. Il **ne passe aucun ordre**, ne se connecte a aucun courtier, ne
calcule aucune fiscalite et ne recommande rien.

La ligne du doc 00 SS6 ne bouge pas : *le systeme propose, tu decides*. Un outil
qui peut executer change de nature - il devient un endroit ou l'on agit vite,
alors que tout le reste est concu pour ralentir.

Ce qui justifie que ce portefeuille vive ici
---------------------------------------------
**Relier une position au signal qui l'a declenchee.** A l'ouverture, on fige
`fit_id` et `quality_score_id` : les lignes exactes de `regression_fits` et
`quality_scores` en vigueur ce jour-la. Trois ans plus tard on relit ce que le
systeme affirmait, pas une reconstitution.

Sans ces deux colonnes, un tableur ferait le meme travail - et mieux.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

# Prix de revient unitaire : moyenne ponderee des achats, **hors frais**, et
# inchangee par une vente partielle.
#
# Les frais sont portes a part, dans `positions.fees`, et ajoutes au montant
# investi. C'est le choix du doc 11 : a part, ils restent lisibles et leur poids
# se voit. Noyes dans le PRU, ils disparaissent - et sur de petites lignes, ils
# expliquent parfois l'essentiel de l'ecart entre le rendement brut et le reel.
THESE_LONGUEUR_MIN = 30
REVUE_MOIS = 12

# Motif de correction : court, mais jamais vide. Sans lui, le journal ne
# distingue plus une erreur de frappe d'un reajustement apres coup.
MOTIF_LONGUEUR_MIN = 5

# Ce qu'une correction de saisie peut retablir. Tout le reste - `fit_id`,
# `z_at_entry`, la devise, la date de revue - en decoule et se recalcule : ces
# colonnes disent ce que le systeme affirmait, elles ne se saisissent pas.
CHAMPS_CORRIGIBLES = ("instrument_id", "account_id", "opened_at", "quantity",
                      "avg_price", "fees", "thesis")

SUPPORTS = """
select id, code, label, kind, currency, is_paper, eligible_countries,
       contribution_cap, broker, notes
  from accounts order by is_paper, code;
"""

DERNIER_COURS = """
select b.ts, b.close, coalesce(a.factor_total, 1.0) as factor_total
  from bars b
  left join adjustment_factors a
    on a.instrument_id = b.instrument_id and a.ts = b.ts
 where b.instrument_id = %(instrument_id)s and b.freq = '1w'
   and b.ts <= %(as_of)s
 order by b.ts desc limit 1;
"""

SIGNAL_DU_JOUR = """
select f.id as fit_id, f.z_score, f.fit_quality, f.half_life_days,
       f.regime_stats,
       q.id as quality_score_id, q.quality_tier, q.regime, q.roic_vs_threshold
  from instruments i
  left join regression_fits f
    on f.instrument_id = i.id
   and f.as_of_date = (select max(as_of_date) from regression_fits
                        where instrument_id = i.id and as_of_date <= %(as_of)s)
  left join quality_scores q
    on q.instrument_id = i.id
   and q.as_of_date = (select max(as_of_date) from quality_scores
                        where instrument_id = i.id and as_of_date <= %(as_of)s)
 where i.id = %(instrument_id)s;
"""

INSERT_POSITION = """
insert into positions
  (instrument_id, account_id, is_paper, account, opened_at, quantity, avg_price,
   currency, thesis, z_at_entry, fit_id, quality_score_id, watchlist_id,
   fees, price_source, review_at)
values (%(instrument_id)s, %(account_id)s, %(is_paper)s, %(account_code)s,
        %(opened_at)s, %(quantity)s, %(avg_price)s, %(currency)s, %(thesis)s,
        %(z_at_entry)s, %(fit_id)s, %(quality_score_id)s, %(watchlist_id)s,
        %(fees)s, %(price_source)s, %(review_at)s)
returning id;
"""

INSERT_TRANSACTION = """
insert into transactions
  (position_id, kind, executed_at, quantity, price, amount, fees, price_source, note)
values (%(position_id)s, %(kind)s, %(executed_at)s, %(quantity)s, %(price)s,
        %(amount)s, %(fees)s, %(price_source)s, %(note)s)
returning id;
"""

POSITIONS = """
select p.id, i.internal_code, i.name, i.country_iso2, a.code as support,
       a.kind as support_kind, p.is_paper, p.opened_at, p.quantity, p.avg_price,
       p.currency, p.fees, p.thesis, p.z_at_entry, p.review_at,
       p.closed_at, p.closed_price, p.close_reason, p.thesis_verdict,
       f.z_score as z_a_lentree, q.quality_tier as qualite_a_lentree,
       p.instrument_id, p.account_id, p.price_source,
       (select count(*) from transactions t where t.position_id = p.id) as mouvements
  from positions p
  join instruments i on i.id = p.instrument_id
  left join accounts a on a.id = p.account_id
  left join regression_fits f on f.id = p.fit_id
  left join quality_scores q on q.id = p.quality_score_id
 where (%(ouvertes)s is false or p.closed_at is null)
 order by p.opened_at desc;
"""

SPLITS_DEPUIS = """
select count(*) from corporate_actions
 where instrument_id = %(instrument_id)s
   and action_type in ('split', 'reverse_split')
   and ex_date > %(depuis)s;
"""

VERSEMENTS = """
select coalesce(sum(t.quantity * t.price + t.fees), 0)
  from transactions t
  join positions p on p.id = t.position_id
 where p.account_id = %(account_id)s and t.kind = 'buy';
"""

LIGNE_A_CORRIGER = """
select p.id, p.instrument_id, p.account_id, p.opened_at, p.quantity,
       p.avg_price, p.fees, p.thesis, p.currency, p.price_source, p.is_paper,
       p.account, p.review_at, p.fit_id, p.quality_score_id, p.watchlist_id,
       p.z_at_entry, p.closed_at, i.name, i.internal_code
  from positions p
  join instruments i on i.id = p.instrument_id
 where p.id = %(position_id)s;
"""

INSERT_CORRECTION = """
insert into position_corrections
  (position_id, position_ref, kind, field_name, old_value, new_value, reason, summary)
values (%(position_id)s, %(position_ref)s, %(kind)s, %(field_name)s,
        %(old_value)s, %(new_value)s, %(reason)s, %(summary)s);
"""

CORRECTIONS = """
select c.position_ref, c.corrected_at, c.kind, c.field_name, c.old_value,
       c.new_value, c.reason, c.summary
  from position_corrections c
 order by c.corrected_at desc, c.id desc;
"""


@dataclass
class Eligibilite:
    autorise: bool
    motif: str = ""


@dataclass
class Signal:
    """Ce que le systeme affirmait le jour de l'ouverture."""

    fit_id: int | None = None
    z_score: float | None = None
    fit_quality: str | None = None
    half_life_days: float | None = None
    regime_stats: dict | None = None
    quality_score_id: int | None = None
    quality_tier: str | None = None
    regime: str | None = None
    roic_vs_threshold: float | None = None


@dataclass
class Valorisation:
    quantite: float = 0.0
    prix_de_revient: float = 0.0
    cours: float | None = None
    date_cours: date | None = None
    valeur: float | None = None
    montant_investi: float = 0.0
    plus_value: float | None = None
    plus_value_pct: float | None = None
    rendement_total_pct: float | None = None
    annualise_pct: float | None = None
    jours: int = 0
    frais: float = 0.0
    split_depuis_lentree: bool = False
    avertissements: list = field(default_factory=list)


def eligibilite(
    pays: str | None,
    eligible_countries: list | None,
    attributes: dict | None = None,
) -> Eligibilite:
    """Le titre est-il admissible sur ce support ?

    On verifie ce qui est verifiable - le pays, et pour les supports qui
    restreignent deja par pays (PEA, PEA-PME) le statut d'un titre au regime
    fiscal exonere d'IS (SIIC et equivalents europeens) que la loi de finances
    2012 exclut explicitement du PEA - et rien d'autre. Les durees de
    detention, conditions de retrait et regles fiscales personnelles dependent
    de la situation de chacun et evoluent : les affirmer serait donner un
    conseil que l'outil n'est pas en position de donner. Le statut SIIC n'est
    pas de cette nature : c'est un fait objectif attache au titre, comme le
    pays de l'emetteur - mais il n'exclut que du PEA, pas d'un CTO ou d'une
    assurance-vie, d'ou la verification uniquement quand le support restreint
    deja par pays.
    """
    if not eligible_countries:
        return Eligibilite(True)
    if not pays:
        return Eligibilite(False, "pays de l'emetteur inconnu")
    if pays.upper() not in {c.upper() for c in eligible_countries}:
        return Eligibilite(
            False,
            f"emetteur {pays} hors des pays declares eligibles pour ce support "
            f"({', '.join(sorted(eligible_countries))})")
    if attributes and attributes.get("pea_eligible") is False:
        motif = attributes.get("pea_motif") or "regime fiscal exonere d'IS incompatible avec le PEA"
        return Eligibilite(False, motif)
    return Eligibilite(True)
    return Eligibilite(
        False,
        f"emetteur {pays} hors des pays declares eligibles pour ce support "
        f"({', '.join(sorted(eligible_countries))})")


def signal_du_jour(cur, instrument_id: int, as_of: date) -> Signal:
    cur.execute(SIGNAL_DU_JOUR, {"instrument_id": instrument_id, "as_of": as_of})
    ligne = cur.fetchone()
    return Signal(*ligne) if ligne else Signal()


def dernier_cours(cur, instrument_id: int, as_of: date) -> tuple:
    """(date, cours ajuste des splits, facteur de rendement total)."""
    cur.execute(DERNIER_COURS, {"instrument_id": instrument_id, "as_of": as_of})
    ligne = cur.fetchone()
    return ligne if ligne else (None, None, None)


def ouvre(cur, instrument_id: int, account_id: int, quantite: float,
          these: str, as_of: date, prix: float | None = None,
          frais: float = 0.0, note: str | None = None) -> tuple[int, str]:
    """Ouvre une position. Rend (id, source de prix).

    Le prix par defaut est la **derniere cloture connue**, et ce choix n'est pas
    de commodite : saisir soi-meme le prix d'entree ouvre la porte au choix d'un
    bon point apres coup, et c'est precisement le biais que tout le projet
    combat sur le prix.
    """
    these = (these or "").strip()
    if len(these) < THESE_LONGUEUR_MIN:
        raise ValueError(
            f"These trop courte ({len(these)} caracteres, {THESE_LONGUEUR_MIN} "
            f"exiges). Une these vide ou en trois mots ne remplit pas sa "
            f"fonction : la relire dans deux ans est le seul antidote fiable au "
            f"biais retrospectif.")
    if quantite <= 0:
        raise ValueError("quantite nulle ou negative")

    cur.execute("select currency from instruments where id = %s", (instrument_id,))
    devise = cur.fetchone()[0]

    cur.execute("select code, is_paper from accounts where id = %s", (account_id,))
    code_support, est_paper = cur.fetchone()

    ts, cours, _facteur = dernier_cours(cur, instrument_id, as_of)
    if prix is None:
        if cours is None:
            raise ValueError("aucun cours disponible : saisir le prix a la main")
        prix, source = float(cours), "close"
    else:
        prix, source = float(prix), "manual"

    cur.execute("select id from watchlist where instrument_id = %s "
                "and removed_at is null", (instrument_id,))
    ligne = cur.fetchone()
    watchlist_id = ligne[0] if ligne else None

    signal = signal_du_jour(cur, instrument_id, as_of)

    cur.execute(INSERT_POSITION, {
        "instrument_id": instrument_id, "account_id": account_id,
        "is_paper": est_paper, "account_code": code_support, "opened_at": as_of,
        "quantity": quantite, "avg_price": prix, "currency": devise,
        "thesis": these, "z_at_entry": signal.z_score, "fit_id": signal.fit_id,
        "quality_score_id": signal.quality_score_id, "watchlist_id": watchlist_id,
        "fees": frais, "price_source": source,
        "review_at": date(as_of.year + 1, as_of.month, min(as_of.day, 28)),
    })
    position_id = cur.fetchone()[0]

    cur.execute(INSERT_TRANSACTION, {
        "position_id": position_id, "kind": "buy", "executed_at": as_of,
        "quantity": quantite, "price": prix, "amount": -(quantite * prix + frais),
        "fees": frais, "price_source": source, "note": note,
    })
    return position_id, source


def renforce(cur, position_id: int, quantite: float, as_of: date,
             prix: float | None = None, frais: float = 0.0) -> None:
    """Ajoute au meme titre. Le prix de revient est recalcule, jamais ecrase."""
    cur.execute("select instrument_id, quantity, avg_price, fees from positions "
                "where id = %s and closed_at is null", (position_id,))
    ligne = cur.fetchone()
    if ligne is None:
        raise ValueError("position inconnue ou deja fermee")
    instrument_id, quantite_actuelle, pru_actuel, frais_actuels = ligne

    _ts, cours, _f = dernier_cours(cur, instrument_id, as_of)
    if prix is None:
        if cours is None:
            raise ValueError("aucun cours disponible")
        prix, source = float(cours), "close"
    else:
        prix, source = float(prix), "manual"

    # Hors frais, comme a l'ouverture : ils sont cumules a part.
    cout_total = float(quantite_actuelle) * float(pru_actuel) + quantite * prix
    nouvelle_quantite = float(quantite_actuelle) + quantite

    cur.execute(
        "update positions set quantity = %s, avg_price = %s, fees = %s where id = %s",
        (nouvelle_quantite, cout_total / nouvelle_quantite,
         float(frais_actuels) + frais, position_id))
    cur.execute(INSERT_TRANSACTION, {
        "position_id": position_id, "kind": "buy", "executed_at": as_of,
        "quantity": quantite, "price": prix, "amount": -(quantite * prix + frais),
        "fees": frais, "price_source": source, "note": "renfort",
    })


def ferme(cur, position_id: int, as_of: date, raison: str,
          verdict: str, revue: str | None = None,
          prix: float | None = None, frais: float = 0.0) -> None:
    """Ferme une position et enregistre la revue de these.

    `verdict` vaut 'indeterminable', 'verifiee' ou 'infirmee'. **La premiere
    valeur est la plus importante** : une these peut etre juste et la position
    perdante, ou fausse et la position gagnante. Forcer un verdict binaire
    fabriquerait de l'apprentissage sur du bruit.
    """
    if verdict not in ("indeterminable", "verifiee", "infirmee"):
        raise ValueError(f"verdict inconnu : {verdict!r}")

    cur.execute("select instrument_id, quantity from positions "
                "where id = %s and closed_at is null", (position_id,))
    ligne = cur.fetchone()
    if ligne is None:
        raise ValueError("position inconnue ou deja fermee")
    instrument_id, quantite = ligne

    _ts, cours, _f = dernier_cours(cur, instrument_id, as_of)
    if prix is None:
        if cours is None:
            raise ValueError("aucun cours disponible")
        prix, source = float(cours), "close"
    else:
        prix, source = float(prix), "manual"

    cur.execute(
        "update positions set closed_at = %s, closed_price = %s, "
        "close_reason = %s, thesis_verdict = %s, thesis_review = %s where id = %s",
        (as_of, prix, raison, verdict, revue, position_id))
    cur.execute(INSERT_TRANSACTION, {
        "position_id": position_id, "kind": "sell", "executed_at": as_of,
        "quantity": float(quantite), "price": prix,
        "amount": float(quantite) * prix - frais, "fees": frais,
        "price_source": source, "note": raison,
    })


# --------------------------------------------------------------------------- #
# Corriger une saisie - ce qui n'est pas fermer une position
# --------------------------------------------------------------------------- #
# Corriger retablit les faits : la position enregistree ne decrivait pas ce qui
# a ete fait. Fermer est une decision, et elle compte dans la mesure de la
# methode. Confondre les deux inscrirait une erreur de frappe au bilan.
#
# Toute correction est journalisee (`position_corrections`). Ce n'est pas une
# precaution decorative : un `update` muet ouvrirait la porte de derriere de
# tout ce projet - reajuster apres coup un prix d'entree ou une these devenue
# genante, sans que rien ne le montre. Le journal ne l'interdit pas, il le rend
# visible.
def _ligne_position(cur, position_id: int) -> dict | None:
    cur.execute(LIGNE_A_CORRIGER, {"position_id": position_id})
    ligne = cur.fetchone()
    if ligne is None:
        return None
    return dict(zip([c.name for c in cur.description], ligne))


def resume(ligne: dict) -> str:
    """La position en une ligne, telle qu'elle est a cet instant."""
    return (f"{ligne['name']} ({ligne['internal_code']}) · "
            f"{float(ligne['quantity']):g} × {float(ligne['avg_price']):.2f} "
            f"{ligne['currency']} · frais {float(ligne['fees']):.2f} · "
            f"ouverte le {ligne['opened_at']} · support {ligne['account']}"
            + (" · fermee" if ligne["closed_at"] else ""))


def _texte(valeur) -> str | None:
    if valeur is None:
        return None
    if isinstance(valeur, float):
        return f"{valeur:g}"
    return str(valeur)


def _journalise(cur, ligne: dict, kind: str, motif: str, apercu: str,
                champ: str | None = None, avant=None, apres=None) -> None:
    cur.execute(INSERT_CORRECTION, {
        "position_id": ligne["id"], "position_ref": ligne["id"], "kind": kind,
        "field_name": champ, "old_value": _texte(avant), "new_value": _texte(apres),
        "reason": motif, "summary": apercu,
    })


def corrige(cur, position_id: int, motif: str, **champs) -> list[tuple]:
    """Corrige une saisie erronee. Rend la liste (champ, avant, apres).

    Les champs acceptes sont ceux de `CHAMPS_CORRIGIBLES`. Tout ce qui *decoule*
    d'eux est recalcule et non saisi : changer de titre ou de date rattache la
    position au `fit_id`, au `quality_score_id` et au suivi de watchlist en
    vigueur ce jour-la. Sans ce recalcul, la position garderait le signal d'une
    autre entreprise - exactement l'incoherence qu'on corrige.
    """
    motif = (motif or "").strip()
    if len(motif) < MOTIF_LONGUEUR_MIN:
        raise ValueError(
            f"Motif de correction trop court ({len(motif)} caracteres, "
            f"{MOTIF_LONGUEUR_MIN} exiges). Sans motif, le journal ne distingue "
            f"plus une erreur de frappe d'un reajustement apres coup.")

    inconnus = set(champs) - set(CHAMPS_CORRIGIBLES)
    if inconnus:
        raise ValueError(f"champ non corrigeable : {', '.join(sorted(inconnus))}")

    ligne = _ligne_position(cur, position_id)
    if ligne is None:
        raise ValueError("position inconnue")
    if ligne["closed_at"] is not None:
        raise ValueError(
            "Position fermee : la rouvrir pour la corriger reecrirait une "
            "decision deja prise. Si la saisie etait fausse des le depart, "
            "supprimer la ligne ; sinon elle reste telle quelle.")

    cur.execute("select count(*) from transactions where position_id = %s",
                (position_id,))
    if cur.fetchone()[0] > 1:
        raise ValueError(
            "Position deja renforcee : son prix de revient est la moyenne "
            "ponderee de plusieurs achats, et l'ecraser a la main le rendrait "
            "faux. Corriger le mouvement fautif demande de reprendre la ligne.")

    apercu = resume(ligne)
    voulu = {c: champs.get(c, ligne[c]) for c in CHAMPS_CORRIGIBLES}

    voulu["thesis"] = (voulu["thesis"] or "").strip()
    if len(voulu["thesis"]) < THESE_LONGUEUR_MIN:
        raise ValueError(
            f"These trop courte ({len(voulu['thesis'])} caracteres, "
            f"{THESE_LONGUEUR_MIN} exiges).")
    voulu["quantity"] = float(voulu["quantity"])
    voulu["fees"] = float(voulu["fees"])
    if voulu["quantity"] <= 0:
        raise ValueError("quantite nulle ou negative")
    if voulu["fees"] < 0:
        raise ValueError("frais negatifs")

    cur.execute("select country_iso2, currency, attributes from instruments where id = %s",
                (voulu["instrument_id"],))
    trouve = cur.fetchone()
    if trouve is None:
        raise ValueError("titre inconnu")
    pays, devise, attrs = trouve

    cur.execute("select code, is_paper, eligible_countries from accounts "
                "where id = %s", (voulu["account_id"],))
    trouve = cur.fetchone()
    if trouve is None:
        raise ValueError("support inconnu")
    code_support, est_paper, pays_eligibles = trouve

    # L'eligibilite se reverifie : corriger le titre peut le faire sortir des
    # pays declares du support, et une correction ne doit pas creer une position
    # que l'ouverture aurait refusee.
    elig = eligibilite(pays, pays_eligibles, attrs)
    if not elig.autorise:
        raise ValueError(f"Titre non eligible a ce support — {elig.motif}")

    change_titre = voulu["instrument_id"] != ligne["instrument_id"]
    change_date = voulu["opened_at"] != ligne["opened_at"]

    # Le prix : saisi a la main, il est marque comme tel. Herite d'une cloture,
    # il appartenait a l'ancien titre ou a l'ancienne date et n'a plus de sens -
    # on le reprend a la source plutot que de garder un chiffre orphelin.
    prix = float(voulu["avg_price"])
    source = ligne["price_source"]
    if prix != float(ligne["avg_price"]):
        source = "manual"
    elif source == "close" and (change_titre or change_date):
        _ts, cours, _f = dernier_cours(cur, voulu["instrument_id"], voulu["opened_at"])
        if cours is None:
            raise ValueError(
                "aucun cours connu pour ce titre a cette date : saisir le prix")
        prix = float(cours)

    cible = dict(voulu)
    cible["avg_price"] = prix
    cible["price_source"] = source
    cible["currency"] = devise
    cible["account"] = code_support
    cible["is_paper"] = est_paper
    cible["fit_id"] = ligne["fit_id"]
    cible["quality_score_id"] = ligne["quality_score_id"]
    cible["watchlist_id"] = ligne["watchlist_id"]
    cible["z_at_entry"] = ligne["z_at_entry"]
    cible["review_at"] = ligne["review_at"]

    if change_titre or change_date:
        ouverture = cible["opened_at"]
        signal = signal_du_jour(cur, cible["instrument_id"], ouverture)
        cible["fit_id"] = signal.fit_id
        cible["quality_score_id"] = signal.quality_score_id
        cible["z_at_entry"] = signal.z_score
        cur.execute("select id from watchlist where instrument_id = %s "
                    "and removed_at is null", (cible["instrument_id"],))
        suivi = cur.fetchone()
        cible["watchlist_id"] = suivi[0] if suivi else None
        cible["review_at"] = date(ouverture.year + 1, ouverture.month,
                                  min(ouverture.day, 28))

    modifies = [(champ, ligne[champ], valeur) for champ, valeur in cible.items()
                if _texte(ligne[champ]) != _texte(valeur)]
    if not modifies:
        return []

    cur.execute("""
        update positions set instrument_id = %(instrument_id)s,
               account_id = %(account_id)s, account = %(account)s,
               is_paper = %(is_paper)s, opened_at = %(opened_at)s,
               quantity = %(quantity)s, avg_price = %(avg_price)s,
               fees = %(fees)s, currency = %(currency)s, thesis = %(thesis)s,
               price_source = %(price_source)s, z_at_entry = %(z_at_entry)s,
               fit_id = %(fit_id)s, quality_score_id = %(quality_score_id)s,
               watchlist_id = %(watchlist_id)s, review_at = %(review_at)s
         where id = %(id)s""", {**cible, "id": position_id})

    # Le mouvement d'achat suit la position, sinon le cumul des versements et le
    # prix de revient divergent des la premiere correction.
    cur.execute("""
        update transactions set executed_at = %s, quantity = %s, price = %s,
               amount = %s, fees = %s, price_source = %s
         where position_id = %s and kind = 'buy'""",
                (cible["opened_at"], cible["quantity"], cible["avg_price"],
                 -(cible["quantity"] * cible["avg_price"] + cible["fees"]),
                 cible["fees"], cible["price_source"], position_id))

    for champ, avant, apres in modifies:
        _journalise(cur, ligne, "update", motif, apercu, champ, avant, apres)
    return modifies


def supprime(cur, position_id: int, motif: str) -> str:
    """Efface une position saisie par erreur. Rend son resume.

    **Reservee a une ligne qui n'aurait jamais du exister.** Une position
    reellement detenue puis vendue se *ferme* : elle a produit un resultat, et
    l'effacer retirerait de la mesure de la methode precisement les cas qu'on
    aurait interet a oublier.

    La ligne du journal survit a la suppression : `position_id` passe a null,
    `position_ref` et `summary` gardent de quoi la relire.
    """
    motif = (motif or "").strip()
    if len(motif) < MOTIF_LONGUEUR_MIN:
        raise ValueError(
            f"Motif de suppression trop court ({len(motif)} caracteres, "
            f"{MOTIF_LONGUEUR_MIN} exiges).")

    ligne = _ligne_position(cur, position_id)
    if ligne is None:
        raise ValueError("position inconnue")

    apercu = resume(ligne)
    _journalise(cur, ligne, "delete", motif, apercu)
    cur.execute("delete from positions where id = %s", (position_id,))
    return apercu


def valorise(cur, position: dict, as_of: date) -> Valorisation:
    """Valorisation d'une ligne, avec le rendement total dividendes reinvestis.

    Le rendement total s'appuie sur `factor_total`, deja calcule et verifie
    contre l'`Adj Close` de Yahoo - ecart median 0,036%.
    """
    v = Valorisation(
        quantite=float(position["quantity"]),
        prix_de_revient=float(position["avg_price"]),
        frais=float(position.get("fees") or 0),
    )
    v.montant_investi = v.quantite * v.prix_de_revient + v.frais

    instrument_id = position["instrument_id"]
    ouverture = position["opened_at"]
    fermeture = position.get("closed_at")

    if fermeture:
        v.cours, v.date_cours = float(position["closed_price"]), fermeture
    else:
        ts, cours, _facteur = dernier_cours(cur, instrument_id, as_of)
        if cours is None:
            v.avertissements.append("aucun cours disponible")
            return v
        v.cours, v.date_cours = float(cours), ts

    v.valeur = v.quantite * v.cours
    v.plus_value = v.valeur - v.montant_investi
    if v.montant_investi:
        v.plus_value_pct = v.plus_value / v.montant_investi

    # Rendement total : le facteur a l'entree ramene le cours d'alors en termes
    # de rendement reinvesti. Le facteur d'aujourd'hui vaut 1 par construction.
    cur.execute(
        "select factor_total from adjustment_factors where instrument_id = %s "
        "and ts <= %s order by ts desc limit 1", (instrument_id, ouverture))
    ligne = cur.fetchone()
    if ligne and ligne[0]:
        facteur_entree = float(ligne[0])
        if facteur_entree > 0 and v.prix_de_revient > 0:
            v.rendement_total_pct = (
                v.cours / (v.prix_de_revient * facteur_entree) - 1)

    fin = fermeture or as_of
    v.jours = (fin - ouverture).days
    base = v.rendement_total_pct if v.rendement_total_pct is not None else v.plus_value_pct
    if base is not None and v.jours >= 30 and base > -1:
        v.annualise_pct = (1 + base) ** (365.25 / v.jours) - 1

    # Un split posterieur a l'entree decale le cours servi par le provider par
    # rapport au prix saisi. Sur une execution a la cloture les deux sont dans
    # le meme espace, mais un prix saisi a la main ne l'est pas.
    cur.execute(SPLITS_DEPUIS, {"instrument_id": instrument_id, "depuis": ouverture})
    if cur.fetchone()[0] and position.get("price_source") == "manual":
        v.split_depuis_lentree = True
        v.avertissements.append(
            "un split est intervenu depuis l'entree et le prix a ete saisi a la "
            "main : la plus-value affichee est fausse tant que le prix n'est pas "
            "ramene a la base actuelle")
    return v


def versements(cur, account_id: int) -> float:
    """Cumul indicatif des achats sur un support.

    **Indicatif, et l'ecran doit le dire.** Le plafond legal porte sur les
    versements d'especes, pas sur les achats de titres : un arbitrage interne ne
    consomme pas de plafond alors qu'il compte ici. Suivre le vrai cumul
    exigerait de saisir les mouvements d'especes, ce qui doublerait la saisie.
    """
    cur.execute(VERSEMENTS, {"account_id": account_id})
    return float(cur.fetchone()[0] or 0)
