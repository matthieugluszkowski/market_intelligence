-- =============================================================================
-- 010 - Distinguer une cloture automatique d un acquittement humain
--
-- Constat en testant la migration 009 : une anomalie resolue a la main
-- reapparaissait au recalcul suivant, puisque la condition sous-jacente etait
-- toujours vraie. La liste ne diminuait donc jamais et la revue manuelle ne
-- servait a rien - or c est precisement ce qu on veut pouvoir faire.
--
-- Les deux clotures n ont pas le meme sens et ne doivent pas avoir le meme effet :
--
--   'auto'   la condition a disparu. Si elle revient, c est une recidive et
--            l anomalie doit se rouvrir.
--   'manual' un humain a regarde et tranche - « point aberrant du provider »,
--            « introduction recente, comportement attendu ». C est un
--            acquittement : tant que l anomalie est la meme, on ne redemande pas.
--
-- L acquittement porte sur l empreinte, qui encode l instrument, le type et le
-- perimetre temporel. Un evenement different produit une empreinte differente,
-- donc une nouvelle anomalie : on n etouffe que ce qui a ete vu.
-- =============================================================================

alter table data_quality_issues
  add column if not exists resolved_kind text;

update data_quality_issues
   set resolved_kind = case when resolution like 'auto %' then 'auto' else 'manual' end
 where resolved_at is not null and resolved_kind is null;

alter table data_quality_issues
  add constraint data_quality_issues_resolved_kind_check
  check (resolved_kind is null or resolved_kind in ('auto', 'manual'));

create index if not exists data_quality_issues_acquittees_idx
  on data_quality_issues (fingerprint) where resolved_kind = 'manual';

comment on column data_quality_issues.resolved_kind is
  '''auto'' = condition disparue, se rouvre en cas de recidive. '
  '''manual'' = acquittement humain, l anomalie identique n est pas resignalee.';
