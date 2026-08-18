-- =============================================================================
-- 002 - Instruments et identite  (doc 01 SS3)
-- P3 : l'identite d'un instrument est son ISIN, pas son ticker.
-- =============================================================================

create table if not exists instruments (
  id              bigint generated always as identity primary key,
  isin            char(12) unique,           -- cle metier, nullable (crypto, indices)
  internal_code   text not null unique,      -- fallback stable : 'EQ:FR:SEB','IX:CAC40'
  asset_class     text not null references asset_classes(code),
  name            text not null,
  exchange_code   text references exchanges(code),
  currency        char(3) not null references currencies(code),
  sector_code     text references sectors(code),
  country_iso2    char(2),

  -- cycle de vie : traitement du survivorship bias
  is_active       boolean not null default true,
  listed_at       date,
  delisted_at     date,
  delisting_reason text,                     -- 'bankruptcy','merger','buyout','transfer','unknown'

  -- null = on applique asset_classes.default_policy_code (P6)
  policy_code     text references regression_policies(code),

  attributes      jsonb not null default '{}'::jsonb,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);

create index if not exists instruments_asset_class_active_idx
  on instruments (asset_class) where is_active;
create index if not exists instruments_sector_idx on instruments (sector_code);
create index if not exists instruments_attributes_gin on instruments using gin (attributes);

-- Mapping des symboles par provider, avec validite temporelle.
-- C'est la table qui evite de confondre Seb (SK.PA) et SEB (banque suedoise).
create table if not exists instrument_symbols (
  id             bigint generated always as identity primary key,
  instrument_id  bigint not null references instruments(id) on delete cascade,
  source_id      smallint not null references data_sources(id),
  symbol         text not null,              -- 'SK.PA' (yfinance), 'sk.fr' (stooq)
  valid_from     date not null default '1900-01-01',
  valid_to       date not null default '9999-12-31',
  is_primary     boolean not null default false,
  constraint symbol_period_unique unique (source_id, symbol, valid_from)
);

create index if not exists instrument_symbols_lookup_idx
  on instrument_symbols (instrument_id, source_id);

-- Appartenance aux indices, historisee : seul remede au survivorship bias.
create table if not exists index_memberships (
  id             bigint generated always as identity primary key,
  index_id       bigint not null references instruments(id),
  member_id      bigint not null references instruments(id),
  valid_from     date not null,
  valid_to       date not null default '9999-12-31',
  weight         double precision,
  source_id      smallint references data_sources(id),
  constraint membership_unique unique (index_id, member_id, valid_from)
);
