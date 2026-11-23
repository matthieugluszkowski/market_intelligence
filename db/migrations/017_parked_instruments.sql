-- =============================================================================
-- 017 - Antichambre et instruments delistes (parking z-score > 2.5)
--
-- Stocke les parametres analytiques (alpha, beta, sigma, window_start) des titres
-- surcotes ecartes du screener actif, ou de nouveaux candidats en veille.
-- Permet une surveillance hebdomadaire spot sans conserver de barres historiques.
-- =============================================================================

create table if not exists parked_instruments (
  id                      bigint generated always as identity primary key,
  instrument_id           bigint references instruments(id) on delete set null,
  internal_code           text not null unique,
  symbol_yfinance         text not null,
  name                    text not null,
  isin                    char(12),
  currency                char(3) not null,
  exchange_code           text,
  asset_class             text not null default 'equity',
  policy_code             text references regression_policies(code),
  attributes              jsonb not null default '{}'::jsonb,

  -- Statut et motif de mise en parking
  status                  text not null default 'parked',
  parked_reason           text not null,
  parked_at               timestamptz not null default now(),

  -- Parametres de la droite de regression (pour evaluation spot hors base)
  window_start            date not null,
  intercept               double precision not null,
  slope_annual            double precision not null,
  sigma_resid             double precision not null,
  r_squared               double precision,
  last_close_at_parking   double precision not null,
  last_z_at_parking       double precision not null,

  -- Surveillance hebdomadaire
  last_checked_at         timestamptz,
  live_price              double precision,
  live_z_score            double precision,

  -- Reintegration
  reentered_at            timestamptz,
  notes                   text,

  constraint parked_status_check
    check (status in ('parked', 'candidate', 'eligible', 'restored'))
);

create index if not exists idx_parked_status on parked_instruments(status);
create index if not exists idx_parked_internal_code on parked_instruments(internal_code);

comment on table parked_instruments is
  'Antichambre de titres surcotes (z > 2.5) ou candidats en veille. '
  'Conserve uniquement les parametres de regression pour evaluation spot sans historique lourd.';
