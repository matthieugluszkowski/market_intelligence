-- =============================================================================
-- 005 - Couche derivee, jambe PRIX  (doc 01 SS6.3, SS6.5)
-- regression_fits est la table centrale du systeme (principe P5).
-- Tout ici est reconstructible : on tronque, on relance.
-- =============================================================================

create table if not exists regression_fits (
  id              bigint generated always as identity primary key,
  instrument_id   bigint not null references instruments(id),
  policy_code     text not null references regression_policies(code),
  as_of_date      date not null,             -- LA DATE DE CALCUL - coeur du principe P5

  window_start    date not null,
  window_end      date not null,
  n_obs           integer not null,

  slope_annual    double precision not null, -- rendement annualise implicite
  intercept       double precision not null,
  sigma_resid     double precision not null,
  r_squared       double precision,

  last_close      double precision not null,
  fitted_value    double precision not null,
  residual        double precision not null,
  z_score         double precision not null, -- residual / sigma_resid

  -- diagnostics de validite (doc 03)
  adf_stat        double precision,
  adf_pvalue      double precision,
  dfgls_stat      double precision,
  kpss_stat       double precision,
  durbin_watson   double precision,
  half_life_days  double precision,
  ar1_ci_low      double precision,
  ar1_ci_high     double precision,

  fit_quality     text not null,             -- 'good','weak','rejected'
  quality_reasons text[],                    -- ['non_stationary','dilution_detected',...]

  method_version  smallint not null default 1,
  computed_at     timestamptz not null default now(),
  constraint fit_unique unique (instrument_id, policy_code, as_of_date, method_version)
);

create index if not exists regression_fits_screen_idx on regression_fits (as_of_date desc, z_score);
create index if not exists regression_fits_hist_idx   on regression_fits (instrument_id, as_of_date desc);
