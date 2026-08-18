-- =============================================================================
-- 007 - Restitution, qualite de donnee, exploitation, portefeuille
--       (doc 01 SS6.5, SS6.6, SS7)
-- =============================================================================

create table if not exists screener_snapshots (
  id             bigint generated always as identity primary key,
  run_date       date not null,
  instrument_id  bigint not null references instruments(id),
  fit_id         bigint references regression_fits(id),
  quality_score_id bigint references quality_scores(id),
  z_score        double precision not null,
  rank_overall   integer,
  rank_in_sector integer,
  entered_at     date,                        -- premiere apparition sous le seuil
  consecutive_weeks integer default 1,        -- la decote est un regime, pas un evenement
  fundamentals_ok boolean,
  quality_tier   text,
  quadrant       text,                        -- 'target','watchlist','value_trap','avoid','unqualified'
  notes          jsonb,
  constraint snapshot_unique unique (run_date, instrument_id)
);

create table if not exists data_quality_issues (
  id             bigint generated always as identity primary key,
  instrument_id  bigint references instruments(id),
  detected_at    timestamptz not null default now(),
  issue_type     text not null,   -- 'gap','outlier_jump','stale_series','currency_mismatch',
                                  -- 'dilution','split_unadjusted','fx_missing','source_divergence'
  severity       text not null,   -- 'info','warning','blocking'
  ts_from        date,
  ts_to          date,
  details        jsonb,
  resolved_at    timestamptz,
  resolution     text
);

create index if not exists data_quality_issues_open_idx
  on data_quality_issues (instrument_id, detected_at desc) where resolved_at is null;

create table if not exists ingestion_runs (
  id             bigint generated always as identity primary key,
  source_id      smallint not null references data_sources(id),
  job_name       text not null,
  started_at     timestamptz not null default now(),
  finished_at    timestamptz,
  status         text not null default 'running',  -- 'running','success','partial','failed'
  rows_inserted  integer default 0,
  rows_updated   integer default 0,
  rows_rejected  integer default 0,
  error_message  text,
  details        jsonb
);

create index if not exists ingestion_runs_recent_idx on ingestion_runs (started_at desc);

-- thesis ecrite AVANT l achat : seul antidote fiable au biais retrospectif.
create table if not exists positions (
  id             bigint generated always as identity primary key,
  instrument_id  bigint not null references instruments(id),
  account        text not null,               -- 'PEA_CM','CTO','etoro'
  opened_at      date not null,
  closed_at      date,
  quantity       double precision not null,
  avg_price      double precision not null,
  currency       char(3) not null references currencies(code),
  thesis         text,
  z_at_entry     double precision,
  notes          jsonb
);

-- Keepalive : evite la mise en pause Supabase apres 7 jours sans requete
-- (doc 00 SS5, reserve 1). Table triviale, independante du pipeline principal.
create table if not exists keepalive (
  id         smallint primary key default 1,
  pinged_at  timestamptz not null default now(),
  ping_count bigint not null default 0,
  constraint keepalive_singleton check (id = 1)
);

insert into keepalive (id) values (1) on conflict (id) do nothing;
