-- =============================================================================
-- 003 - Donnees de marche  (doc 01 SS4, SS6.2)
-- RAW append-only. P4 : `close` est le cours BRUT, jamais l'adj_close provider.
-- =============================================================================

create table if not exists bars (
  instrument_id  bigint not null references instruments(id),
  freq           text   not null,            -- '1d','1w','1mo'
  ts             date   not null,            -- date de cloture de la barre
  open           double precision,
  high           double precision,
  low            double precision,
  close          double precision not null,  -- COURS BRUT (P4)
  volume         bigint,
  source_id      smallint not null references data_sources(id),
  ingested_at    timestamptz not null default now(),
  primary key (instrument_id, freq, ts)
) partition by list (freq);

create table if not exists bars_1d  partition of bars for values in ('1d');
create table if not exists bars_1w  partition of bars for values in ('1w');
create table if not exists bars_1mo partition of bars for values in ('1mo');

create index if not exists bars_1d_ts_idx  on bars_1d (ts);
create index if not exists bars_1w_ts_idx  on bars_1w (ts);
create index if not exists bars_1mo_ts_idx on bars_1mo (ts);

create table if not exists corporate_actions (
  id             bigint generated always as identity primary key,
  instrument_id  bigint not null references instruments(id),
  action_type    text not null,              -- 'split','reverse_split','cash_dividend',
                                             -- 'stock_dividend','rights_issue',
                                             -- 'capital_increase','spinoff','merger'
  ex_date        date not null,
  payment_date   date,
  ratio          double precision,           -- 2.0 pour un split 2:1
  amount         double precision,           -- dividende par action
  currency       char(3) references currencies(code),
  source_id      smallint not null references data_sources(id),
  announced_at   date,                       -- bitemporalite (P2)
  ingested_at    timestamptz not null default now(),
  raw            jsonb
);

-- Contrainte d'unicite via index expressionnel : COALESCE est interdit dans une
-- clause UNIQUE de table, autorise dans un index unique.
create unique index if not exists ca_unique
  on corporate_actions (instrument_id, action_type, ex_date,
                        coalesce(ratio, 0), coalesce(amount, 0));
create index if not exists corporate_actions_lookup_idx
  on corporate_actions (instrument_id, ex_date);

-- Detection des dilutions (Atos, Casino, Solocal) : le filtre le plus rentable.
create table if not exists shares_outstanding (
  instrument_id  bigint not null references instruments(id),
  as_of          date not null,
  shares         bigint not null,
  source_id      smallint not null references data_sources(id),
  published_at   date,
  primary key (instrument_id, as_of)
);

create table if not exists fx_rates (
  base       char(3) not null references currencies(code),
  quote      char(3) not null references currencies(code),
  ts         date not null,
  rate       double precision not null,
  source_id  smallint not null references data_sources(id),
  primary key (base, quote, ts)
);

-- Derive, entierement reconstructible depuis corporate_actions.
create table if not exists adjustment_factors (
  instrument_id  bigint not null references instruments(id),
  ts             date not null,
  factor_price   double precision not null default 1.0,  -- cumul splits
  factor_total   double precision not null default 1.0,  -- splits + dividendes reinvestis
  computed_at    timestamptz not null default now(),
  method_version smallint not null default 1,
  primary key (instrument_id, ts)
);
