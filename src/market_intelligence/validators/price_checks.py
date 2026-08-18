"""Les neuf controles qualite du doc 02 SS5, par ordre de valeur decroissante.

Chacun rend une liste d'anomalies prete pour `data_quality_issues`. Aucun ne
supprime de donnee : quarantaine plutot que rejet (doc 02 SS4.3) - une ligne
douteuse reste consultable, sinon on ne diagnostique jamais rien apres coup.

Le plus rentable des neuf est le **filtre de dilution**, et il ne figure dans
aucun screener grand public. Atos, Casino, emeis, Solocal sont toujours cotes :
ils ne sortent pas par le filtre 'radiation'. Mais apres une dilution d'un
facteur cent, leur cours ajuste rend la droite de regression absurde - le titre
apparait massivement decote alors que la valeur par action a ete detruite.
"""

from __future__ import annotations

import hashlib
import json

# --------------------------------------------------------------------------- #
# 1. Saut de cours inexplique - bloquant
# --------------------------------------------------------------------------- #
SAUT = """
with variations as (
  select b.instrument_id, b.ts, b.close,
         lag(b.close) over (partition by b.instrument_id order by b.ts) as precedent
    from bars b
   where b.freq = '1d'
)
select v.instrument_id, v.ts, v.precedent, v.close,
       v.close / nullif(v.precedent, 0) - 1 as variation
  from variations v
 where v.precedent is not null
   and abs(v.close / nullif(v.precedent, 0) - 1) > %(seuil)s
   and not exists (
     select 1 from corporate_actions ca
      where ca.instrument_id = v.instrument_id
        and ca.ex_date between v.ts - 4 and v.ts + 1
   )
 order by abs(v.close / nullif(v.precedent, 0) - 1) desc;
"""

# --------------------------------------------------------------------------- #
# 2. Serie figee - avertissement
# --------------------------------------------------------------------------- #
FIGEE = """
with suites as (
  select instrument_id, ts, close,
         row_number() over (partition by instrument_id order by ts)
       - row_number() over (partition by instrument_id, close order by ts) as groupe
    from bars where freq = '1d'
)
select instrument_id, min(ts) as debut, max(ts) as fin, count(*) as seances, close
  from suites
 group by instrument_id, groupe, close
having count(*) > %(seuil)s
 order by count(*) desc;
"""

# --------------------------------------------------------------------------- #
# 3. Trou de cotation - avertissement
# --------------------------------------------------------------------------- #
TROU = """
with ecarts as (
  select instrument_id, ts,
         ts - lag(ts) over (partition by instrument_id order by ts) as jours
    from bars where freq = '1d'
)
select instrument_id, ts - jours as debut, ts as fin, jours
  from ecarts
 where jours > %(seuil_jours)s
 order by jours desc;
"""

# --------------------------------------------------------------------------- #
# 4. Dilution - bloquant sur la regression
# --------------------------------------------------------------------------- #
# Deux precautions, toutes deux apprises en observant le resultat brut.
#
# 1. **Neutraliser les splits.** Un 5 pour 1 multiplie le nombre d'actions par
#    cinq sans diluer personne. Sans correction, le filtre signalait Dassault
#    Systemes (x5,09), Michelin (x4,0), Aena (x10,7) et Prosus (x2,43) - soit
#    quatre splits pris pour des dilutions massives. On compare donc des nombres
#    d'actions ramenes a une base constante, par division du produit cumule des
#    ratios.
#
# 2. **Une alerte par titre, pas par observation.** Le provider sert un point par
#    jour ; un evenement unique produisait 203 lignes pour Prosus. On ne remonte
#    que le pic, avec l'etendue de l'episode et son nombre d'observations.
DILUTION = """
with splits as (
  select instrument_id, ex_date, ratio
    from corporate_actions
   where action_type in ('split', 'reverse_split') and ratio is not null and ratio > 0
),
ajuste as (
  select s.instrument_id, s.as_of, s.shares,
         s.shares / coalesce(
           (select exp(sum(ln(sp.ratio))) from splits sp
             where sp.instrument_id = s.instrument_id and sp.ex_date <= s.as_of), 1
         ) as shares_base
    from shares_outstanding s
),
-- Fenetre glissante plutot que sous-requete correlee : sur ~30 000 points, la
-- correlee est quadratique et depasse le delai maximal d'instruction de Supabase.
fenetre as (
  select a.instrument_id, a.as_of, a.shares, a.shares_base,
         min(a.shares_base) over (
           partition by a.instrument_id order by a.as_of
           range between interval '365 days' preceding and current row
         ) as plancher_12m
    from ajuste a
),
franchissements as (
  select instrument_id, as_of, shares, shares_base, plancher_12m,
         shares_base / nullif(plancher_12m, 0) - 1 as variation
    from fenetre
   where plancher_12m is not null and plancher_12m > 0
     and shares_base / nullif(plancher_12m, 0) - 1 > %(seuil)s
)
select f.instrument_id, min(f.as_of), max(f.as_of), count(*),
       max(f.variation),
       (array_agg(f.as_of order by f.variation desc))[1] as date_du_pic,
       (array_agg(f.plancher_12m order by f.variation desc))[1] as plancher_au_pic,
       (array_agg(f.shares order by f.variation desc))[1] as shares_au_pic
  from franchissements f
 group by f.instrument_id
 order by max(f.variation) desc;
"""

# --------------------------------------------------------------------------- #
# 5. Divergence inter-sources - avertissement
# --------------------------------------------------------------------------- #
# Ecrit pour fonctionner des qu'une seconde source alimentera `bars`. Il ne
# trouvera rien tant que yfinance est seul - ce qui est en soi le constat a
# remonter : *une source unique donne une confiance illusoire* (doc 02 SS5).
DIVERGENCE = """
select a.instrument_id, a.ts, a.source_id, b.source_id, a.close, b.close,
       abs(a.close / nullif(b.close, 0) - 1) as ecart
  from bars a
  join bars b
    on b.instrument_id = a.instrument_id and b.freq = a.freq and b.ts = a.ts
   and b.source_id > a.source_id
 where a.freq = '1d'
   and abs(a.close / nullif(b.close, 0) - 1) > %(seuil)s
 order by 7 desc;
"""

# --------------------------------------------------------------------------- #
# 6. Incoherence de devise - bloquant
# --------------------------------------------------------------------------- #
DEVISE = """
select i.id, i.internal_code, i.currency, e.currency
  from instruments i
  join exchanges e on e.code = i.exchange_code
 where i.currency <> e.currency
   and not (i.currency = 'GBX' and e.currency = 'GBP')
   and not (i.currency = 'GBP' and e.currency = 'GBX');
"""

# --------------------------------------------------------------------------- #
# 7. Historique insuffisant - exclusion du screener
# --------------------------------------------------------------------------- #
HISTORIQUE = """
select i.id, i.internal_code, p.code, p.min_years,
       coalesce((max(b.ts) - min(b.ts)) / 365.25, 0) as annees, count(b.ts) as n_obs
  from instruments i
  join asset_classes a on a.code = i.asset_class
  join regression_policies p on p.code = coalesce(i.policy_code, a.default_policy_code)
  left join bars b on b.instrument_id = i.id and b.freq = p.bar_freq
 where i.is_active and p.model <> 'none'
 group by i.id, i.internal_code, p.code, p.min_years
having coalesce((max(b.ts) - min(b.ts)) / 365.25, 0) < p.min_years;
"""

# --------------------------------------------------------------------------- #
# 8. FX manquant - avertissement
# --------------------------------------------------------------------------- #
# La regression se calcule en devise locale (doc 01 SS4.4), le FX ne sert donc
# qu'a la performance de portefeuille. Le controle reste utile : il dira quand
# l'univers cessera d'etre mono-devise.
FX_MANQUANT = """
select distinct i.currency
  from instruments i
 where i.is_active and i.currency <> 'EUR'
   and not exists (
     select 1 from fx_rates f
      where f.base = i.currency and f.quote = 'EUR'
   );
"""

# --------------------------------------------------------------------------- #
# 9. Identite comptable - avertissement sur le fait
# --------------------------------------------------------------------------- #
# Sans effet tant que `financial_facts` est vide : les fondamentaux arrivent en L6.
IDENTITE_COMPTABLE = """
with bilan as (
  select instrument_id, period_end,
         max(value) filter (where concept_code = 'total_assets') as actif,
         max(value) filter (where concept_code = 'total_liabilities') as passif,
         max(value) filter (where concept_code = 'total_equity') as capitaux
    from financial_facts
   where concept_code in ('total_assets', 'total_liabilities', 'total_equity')
   group by instrument_id, period_end
)
select instrument_id, period_end, actif, passif + capitaux,
       abs(actif - (passif + capitaux)) / nullif(actif, 0) as ecart
  from bilan
 where actif is not null and passif is not null and capitaux is not null
   and abs(actif - (passif + capitaux)) / nullif(actif, 0) > %(tolerance)s;
"""

# Upsert sur l'empreinte : une anomalie deja ouverte est revue, pas recreee.
# `detected_at` reste la premiere detection - c'est l'age de l'anomalie, et c'est
# l'information qu'on veut en retrouvant la liste trois semaines plus tard.
UPSERT_ISSUE = """
insert into data_quality_issues
  (instrument_id, issue_type, severity, ts_from, ts_to, details,
   fingerprint, last_seen_at, run_count)
select %(instrument_id)s, %(issue_type)s, %(severity)s, %(ts_from)s, %(ts_to)s,
       %(details)s, %(fingerprint)s, now(), 1
-- Acquittement : une anomalie qu'un humain a regardee et tranchee n'est pas
-- resignalee tant qu'elle est la meme. Sans cette clause, la liste ne diminue
-- jamais - la condition sous-jacente est toujours vraie au recalcul suivant -
-- et la revue manuelle ne sert a rien. Une cloture automatique, elle, se rouvre :
-- une condition qui revient est une recidive.
 where not exists (
   select 1 from data_quality_issues acquittee
    where acquittee.fingerprint = %(fingerprint)s
      and acquittee.resolved_kind = 'manual'
 )
on conflict (fingerprint) where resolved_at is null
do update set details = excluded.details,
              severity = excluded.severity,
              last_seen_at = now(),
              run_count = data_quality_issues.run_count + 1;
"""


def empreinte(instrument_id, issue_type: str, ts_from, ts_to, cle: str = "") -> str:
    """Empreinte stable d'une anomalie : meme probleme, meme empreinte."""
    brut = f"{instrument_id}|{issue_type}|{ts_from}|{ts_to}|{cle}"
    return hashlib.sha256(brut.encode("utf-8")).hexdigest()[:32]


def _issue(cur, instrument_id, issue_type, severity, ts_from, ts_to, details,
           cle: str = "") -> str:
    fingerprint = empreinte(instrument_id, issue_type, ts_from, ts_to, cle)
    cur.execute(UPSERT_ISSUE, {
        "instrument_id": instrument_id, "issue_type": issue_type, "severity": severity,
        "ts_from": ts_from, "ts_to": ts_to,
        "details": json.dumps(details, ensure_ascii=False, default=str),
        "fingerprint": fingerprint,
    })
    return fingerprint


def saut_de_cours(cur, seuil: float) -> list[str]:
    cur.execute(SAUT, {"seuil": seuil})
    lignes = cur.fetchall()
    return [
        _issue(cur, instrument_id, "outlier_jump", "blocking", ts, ts,
               {"precedent": precedent, "close": close, "variation": round(variation, 4),
                "diagnostic": "variation d'une seance non expliquee par une operation "
                              "connue : split non declare ou erreur de cotation"})
        for instrument_id, ts, precedent, close, variation in lignes
    ]


def serie_figee(cur, seuil_seances: int) -> list[str]:
    cur.execute(FIGEE, {"seuil": seuil_seances})
    lignes = cur.fetchall()
    return [
        _issue(cur, instrument_id, "stale_series", "warning", debut, fin,
               {"seances": seances, "close": close})
        for instrument_id, debut, fin, seances, close in lignes
    ]


def trou_de_cotation(cur, seuil_jours: int) -> list[str]:
    cur.execute(TROU, {"seuil_jours": seuil_jours})
    lignes = cur.fetchall()
    return [
        _issue(cur, instrument_id, "gap", "warning", debut, fin,
               {"jours_calendaires": jours})
        for instrument_id, debut, fin, jours in lignes
    ]


def dilution(cur, seuil: float) -> list[str]:
    cur.execute(DILUTION, {"seuil": seuil})
    lignes = cur.fetchall()
    empreintes = []
    for (instrument_id, debut, fin, observations, variation_max,
         date_du_pic, plancher_au_pic, shares_au_pic) in lignes:
        empreintes.append(_issue(cur, instrument_id, "dilution", "blocking", debut, fin,
               {"variation_max": round(variation_max, 4),
                "date_du_pic": date_du_pic,
                "plancher_12m_base_constante": plancher_au_pic,
                "shares_au_pic": shares_au_pic,
                "observations_en_franchissement": observations,
                "diagnostic": "le nombre d'actions a bondi hors effet de split : la "
                              "regression sur la fenetre anterieure ne mesure plus la "
                              "meme chose"}))
    return empreintes


def divergence_inter_sources(cur, seuil: float) -> list[str]:
    cur.execute(DIVERGENCE, {"seuil": seuil})
    lignes = cur.fetchall()
    return [
        _issue(cur, instrument_id, "source_divergence", "warning", ts, ts,
               {"source_a": source_a, "source_b": source_b,
                "close_a": close_a, "close_b": close_b, "ecart": round(ecart, 4)})
        for instrument_id, ts, source_a, source_b, close_a, close_b, ecart in lignes
    ]


def incoherence_devise(cur) -> list[str]:
    cur.execute(DEVISE)
    lignes = cur.fetchall()
    return [
        _issue(cur, instrument_id, "currency_mismatch", "blocking", None, None,
               {"internal_code": internal_code, "devise_instrument": devise_titre,
                "devise_marche": devise_marche}, cle=internal_code)
        for instrument_id, internal_code, devise_titre, devise_marche in lignes
    ]


def historique_insuffisant(cur) -> list[str]:
    cur.execute(HISTORIQUE)
    lignes = cur.fetchall()
    empreintes = []
    for instrument_id, internal_code, politique, min_years, annees, n_obs in lignes:
        empreintes.append(_issue(cur, instrument_id, "short_history", "warning", None, None,
               {"internal_code": internal_code, "politique": politique,
                "min_years": min_years, "annees_disponibles": round(float(annees), 1),
                "n_obs": n_obs,
                "diagnostic": "exclu du screener tant que la profondeur exigee par la "
                              "politique n'est pas atteinte"}, cle=politique))
    return empreintes


def fx_manquant(cur) -> list[str]:
    cur.execute(FX_MANQUANT)
    lignes = cur.fetchall()
    return [
        _issue(cur, None, "fx_missing", "warning", None, None,
               {"devise": devise, "diagnostic": "aucun taux vers EUR ; sans effet sur la "
                                                "regression, qui se calcule en devise locale"},
               cle=devise)
        for (devise,) in lignes
    ]


def identite_comptable(cur, tolerance: float) -> list[str]:
    cur.execute(IDENTITE_COMPTABLE, {"tolerance": tolerance})
    lignes = cur.fetchall()
    return [
        _issue(cur, instrument_id, "accounting_identity", "warning", period_end, period_end,
               {"actif": actif, "passif_plus_capitaux": passif_et_capitaux,
                "ecart_relatif": round(ecart, 4)})
        for instrument_id, period_end, actif, passif_et_capitaux, ecart in lignes
    ]
