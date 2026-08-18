-- =============================================================================
-- 009 - Journal traçable des anomalies qualite
--
-- Le job de controles purgeait les anomalies non resolues avant chaque
-- recalcul, pour eviter qu elles ne s empilent. Effet de bord : une anomalie
-- vue en aout et toujours presente en octobre perdait sa date de premiere
-- detection, et toute note de diagnostic disparaissait au passage suivant.
-- On ne pouvait donc pas y revenir.
--
-- On identifie desormais chaque anomalie par une empreinte stable. Un
-- recalcul met a jour `last_seen_at` au lieu de detruire et recreer :
--   - `detected_at` devient la date de PREMIERE detection et ne bouge plus ;
--   - une anomalie qui cesse d etre detectee est cloturee automatiquement,
--     avec la mention, plutot que supprimee ;
--   - une resolution manuelle et sa note survivent aux recalculs.
-- =============================================================================

alter table data_quality_issues
  add column if not exists fingerprint  text,
  add column if not exists last_seen_at timestamptz,
  add column if not exists run_count    integer not null default 1;

-- Une seule anomalie ouverte par empreinte. Rien n empeche la meme empreinte de
-- reapparaitre apres cloture : c est une recidive, et elle doit se voir.
create unique index if not exists data_quality_issues_ouverte_unique
  on data_quality_issues (fingerprint) where resolved_at is null;

create index if not exists data_quality_issues_triage_idx
  on data_quality_issues (severity, detected_at) where resolved_at is null;

comment on column data_quality_issues.fingerprint is
  'Empreinte stable de l anomalie : instrument, type et perimetre temporel. '
  'Permet de la suivre d un recalcul a l autre au lieu de la recreer.';
comment on column data_quality_issues.detected_at is
  'Premiere detection. Ne bouge jamais - c est l age de l anomalie.';
comment on column data_quality_issues.last_seen_at is
  'Dernier recalcul ou l anomalie etait encore presente.';
