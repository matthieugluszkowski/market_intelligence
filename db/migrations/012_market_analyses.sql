-- =============================================================================
-- 012 - Dossiers d intelligence concurrentielle (doc 01 SS6.4 bis, doc 08 SS8)
--
-- Contrepartie du passage en manuel assiste. Le dossier est stocke tel quel, en
-- JSONB, et n est jamais eclate en colonnes :
--
--   - le schema evoluera - horizons, statuts, familles de criteres - et chaque
--     evolution couterait une migration ;
--   - le dossier est une PIECE, pas un ensemble de champs. Le relire dans deux
--     ans suppose de le retrouver dans la forme ou il a ete valide, y compris
--     ses sources et ses passages incertains.
--
-- Ce qui est eclate, c est ce que le dossier ALIMENTE : peer_group_members pour
-- les concurrents retenus, moat_assessments pour les verdicts. L import fait
-- cette projection ; le dossier reste la source.
--
-- `analyst` est le pivot du garde-fou : il n est renseignable que par un import
-- explicite. Un dossier sans analyste reste en draft, ne projette rien, et ne
-- fait passer aucun titre en solid.
-- =============================================================================

create table if not exists market_analyses (
  id             bigint generated always as identity primary key,
  instrument_id  bigint not null references instruments(id),
  analysis_id    text not null unique,
  reference_date date not null,
  status         text not null default 'draft',
  analyst        text,
  dossier        jsonb not null,
  validated_at   timestamptz,
  expires_at     date,
  imported_at    timestamptz not null default now(),
  constraint analysis_status_check check (status in ('draft', 'review', 'validated')),
  constraint analysis_validated_requires_analyst
    check (status <> 'validated' or analyst is not null)
);

create index if not exists market_analyses_recent_idx
  on market_analyses (instrument_id, reference_date desc);
create index if not exists market_analyses_dossier_gin
  on market_analyses using gin (dossier);

comment on table market_analyses is
  'Dossier concurrentiel produit par assistance LLM et valide a la main. '
  'Alimente peer_group_members et moat_assessments par projection a l import.';
comment on column market_analyses.analyst is
  'Qui a relu. null = non valide : le dossier ne projette rien et ne fait '
  'passer aucun titre en solid.';
