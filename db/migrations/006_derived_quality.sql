-- =============================================================================
-- 006 - Couche derivee, jambe QUALITE  (doc 01 SS6.4, doc 08)
-- La seconde jambe de la methode. Recalculee trimestriellement, pas hebdo.
-- =============================================================================

create table if not exists peer_groups (
  id            bigint generated always as identity primary key,
  code          text not null unique,
  label         text not null,
  kind          text not null,               -- 'sector_auto' | 'manual'
  sector_code   text references sectors(code),
  is_complete   boolean not null default false,  -- au moins un pair hors Europe
  notes         text,
  created_at    timestamptz not null default now()
);

-- external_name / is_in_universe traitent la limite L1 du doc 08 : les menaces
-- concurrentielles reelles viennent presque toujours de hors univers
-- (Shark Ninja vs Seb, BYD vs BMW, Revolut non cotee).
create table if not exists peer_group_members (
  id            bigint generated always as identity primary key,
  peer_group_id bigint not null references peer_groups(id) on delete cascade,
  instrument_id bigint references instruments(id),   -- null si hors univers
  external_name text,
  external_ref  jsonb,
  is_in_universe boolean not null default true,
  valid_from    date not null default current_date,
  valid_to      date not null default '9999-12-31',
  constraint peer_member_identified check (instrument_id is not null or external_name is not null)
);

-- COALESCE est interdit dans une clause UNIQUE de table, autorise en index unique.
create unique index if not exists peer_group_member_unique
  on peer_group_members (peer_group_id, coalesce(instrument_id, 0), coalesce(external_name, ''));

create table if not exists quality_scores (
  id                bigint generated always as identity primary key,
  instrument_id     bigint not null references instruments(id),
  as_of_date        date not null,           -- historise (P5 applique a la qualite)
  peer_group_id     bigint references peer_groups(id),

  -- Q1 : leadership
  relative_share    double precision,        -- CA / CA du plus grand pair
  rank_by_revenue   integer,
  rank_stability_5y double precision,
  foreign_revenue_pct double precision,

  -- Q2 : rente
  roic_latest       double precision,
  roic_mean_5y      double precision,
  roic_volatility   double precision,
  roic_vs_threshold double precision,        -- ecart au seuil absolu (8%)
  roic_vs_peers     double precision,        -- ecart a la mediane du groupe
  persistence_years smallint,
  gross_margin_mean double precision,
  gross_margin_std  double precision,

  -- Q3 : erosion
  roic_slope_5y     double precision,
  gross_margin_slope_5y double precision,
  share_slope_5y    double precision,
  erosion_flags     smallint,                -- 0 a 3 pentes negatives significatives

  regime            text not null,           -- 'rent','cyclical','eroding','no_moat','unknown'
  quality_tier      text not null,           -- 'solid','watch','eroding','unqualified'
  n_years_available smallint not null,
  confidence        text not null,           -- 'high','medium','low'

  method_version    smallint not null default 1,
  computed_at       timestamptz not null default now(),
  constraint quality_unique unique (instrument_id, as_of_date, method_version)
);

create index if not exists quality_scores_screen_idx on quality_scores (as_of_date desc, quality_tier);

-- Le volet qualitatif : ce qui ne se calcule pas.
-- reviewed_by null = non valide : ne fait jamais passer un titre en quadrant cible.
create table if not exists moat_assessments (
  id              bigint generated always as identity primary key,
  instrument_id   bigint not null references instruments(id),
  assessed_at     date not null,
  expires_at      date not null,             -- assessed_at + 18 mois
  moat_sources    text[],                    -- 'brand','patent','switching','network','cost','scale'
  position_verdict text not null,            -- 'leader','challenger','follower','niche'
  durability_verdict text not null,          -- 'solid','watch','eroding','none'
  threats         jsonb,
  peer_group_id   bigint references peer_groups(id),
  rationale       text not null,
  sources         jsonb,
  authored_by     text not null,             -- 'human' | 'llm:<modele>'
  reviewed_by     text,
  confidence      double precision
);

create index if not exists moat_assessments_hist_idx on moat_assessments (instrument_id, assessed_at desc);
