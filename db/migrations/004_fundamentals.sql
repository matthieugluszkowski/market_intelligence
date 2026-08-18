-- =============================================================================
-- 004 - Fondamentaux (RAW)  (doc 01 SS5)
-- Modele EAV assume : trois sources heterogenes doivent cohabiter
-- (yfinance, XBRL/ESEF, extraction LLM de PDF).
-- =============================================================================

create table if not exists financial_reports (
  id             bigint generated always as identity primary key,
  instrument_id  bigint not null references instruments(id),
  report_type    text not null,              -- 'annual','semi_annual','quarterly','press_release'
  fiscal_year    smallint,
  period_end     date not null,              -- LA PERIODE CONCERNEE
  published_at   date,                       -- QUAND ON A PU LE SAVOIR (P2)
  language       char(2),
  source_id      smallint not null references data_sources(id),
  document_url   text,
  storage_path   text,
  extraction_status text not null default 'pending',   -- 'pending','extracted','failed','not_needed'
  extraction_method text,                    -- 'xbrl','llm_pdf','provider_api','manual'
  extracted_at   timestamptz,
  constraint report_unique unique (instrument_id, report_type, period_end, source_id)
);

create table if not exists financial_concepts (
  code         text primary key,             -- canon interne : 'revenue','ebit','net_income'...
  label        text not null,
  statement    text not null,                -- 'income','balance','cashflow','ratio'
  unit_type    text not null default 'currency',  -- 'currency','count','ratio','percent'
  sign_convention text
);

create table if not exists concept_mappings (
  source_id     smallint not null references data_sources(id),
  source_label  text not null,               -- 'totalRevenue', 'ifrs-full:Revenue'
  concept_code  text not null references financial_concepts(code),
  primary key (source_id, source_label)
);

create table if not exists financial_facts (
  id             bigint generated always as identity primary key,
  instrument_id  bigint not null references instruments(id),
  concept_code   text not null references financial_concepts(code),
  period_end     date not null,
  period_type    text not null,              -- 'FY','H1','Q1'...,'instant'
  value          double precision not null,
  currency       char(3) references currencies(code),
  published_at   date,                       -- bitemporalite (P2)
  report_id      bigint references financial_reports(id),
  source_id      smallint not null references data_sources(id),
  confidence     double precision,           -- < 1 pour l'extraction LLM
  ingested_at    timestamptz not null default now(),
  constraint fact_unique unique (instrument_id, concept_code, period_end, period_type, source_id)
);

create index if not exists financial_facts_lookup_idx
  on financial_facts (instrument_id, concept_code, period_end desc);
