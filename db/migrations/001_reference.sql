-- =============================================================================
-- 001 - Referentiel  (doc 01 SS2, SS6.1)
-- Postgres 15+ standard. Aucune extension propriétaire (cf. doc 00 SS5).
-- =============================================================================

-- Politiques de regression : creees en premier car referencees par
-- asset_classes.default_policy_code et instruments.policy_code (principe P6).
create table if not exists regression_policies (
  code            text primary key,
  label           text not null,
  model           text not null,             -- 'log_linear','log_log','real_deflated','none'
  window_years    smallint,
  min_years       smallint not null default 15,
  bar_freq        text not null default '1w',
  min_observations integer not null default 500,
  requires_stationarity_test boolean not null default true,
  notes           text
);

create table if not exists asset_classes (
  code            text primary key,          -- 'equity','etf','index','commodity','crypto','fx','bond'
  label           text not null,
  supports_fundamentals  boolean not null default false,
  default_policy_code    text references regression_policies(code),
  notes           text
);

create table if not exists currencies (
  code    char(3) primary key,               -- ISO 4217
  label   text not null
);

create table if not exists exchanges (
  code         text primary key,             -- code MIC : 'XPAR','XETR','XAMS'
  name         text not null,
  country_iso2 char(2),
  currency     char(3) not null references currencies(code),
  timezone     text not null default 'Europe/Paris'
);

create table if not exists sectors (
  code        text primary key,              -- ICB (ou GICS)
  scheme      text not null default 'ICB',
  level       smallint not null,             -- 1=industrie ... 4=sous-secteur
  parent_code text references sectors(code),
  label       text not null
);

create table if not exists data_sources (
  id            smallint primary key,
  code          text not null unique,        -- 'stooq','yfinance','esef','amf','ecb','manual'
  label         text not null,
  kind          text not null,               -- 'price','fundamental','reference','fx'
  priority      smallint not null default 100,  -- plus bas = plus fiable
  base_url      text,
  license_note  text,
  active        boolean not null default true
);
