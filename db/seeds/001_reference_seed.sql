-- =============================================================================
-- Seeds du referentiel - idempotents (on conflict do update)
-- Ordre : policies -> asset_classes -> currencies -> exchanges -> sectors
--         -> data_sources -> financial_concepts
-- =============================================================================

-- --- Politiques de regression (principe P6 : la methode est une donnee) ------
insert into regression_policies
  (code, label, model, window_years, min_years, bar_freq, min_observations, notes) values
  ('loglin_20y', 'Log-lineaire 20 ans', 'log_linear', 20, 15, '1w', 500,
   'Defaut actions. Marie de Raismes utilise 20 ans pour les societes.'),
  ('loglin_30y', 'Log-lineaire 30 ans', 'log_linear', 30, 20, '1w', 800,
   'Indices et ETF, depuis un regime monetaire homogene.'),
  ('real_deflated', 'Tendance reelle deflatee', 'real_deflated', 50, 30, '1mo', 300,
   'Matieres premieres. La tendance nominale est dominee par l inflation.'),
  ('excluded', 'Hors modele', 'none', null, 0, '1d', 0,
   'Crypto et FX. Regime non stationnaire, pente dependante de la date de depart.')
on conflict (code) do update set
  label = excluded.label, model = excluded.model, window_years = excluded.window_years,
  min_years = excluded.min_years, bar_freq = excluded.bar_freq,
  min_observations = excluded.min_observations, notes = excluded.notes;

-- --- Classes d actifs -------------------------------------------------------
insert into asset_classes (code, label, supports_fundamentals, default_policy_code) values
  ('equity',    'Action',            true,  'loglin_20y'),
  ('etf',       'ETF',               false, 'loglin_30y'),
  ('index',     'Indice',            false, 'loglin_30y'),
  ('commodity', 'Matiere premiere',  false, 'real_deflated'),
  ('crypto',    'Crypto-actif',      false, 'excluded'),
  ('fx',        'Devise',            false, 'excluded'),
  ('bond',      'Obligation',        false, 'excluded')
on conflict (code) do update set
  label = excluded.label,
  supports_fundamentals = excluded.supports_fundamentals,
  default_policy_code = excluded.default_policy_code;

-- --- Devises (ISO 4217, + GBX pence pour le LSE) ----------------------------
insert into currencies (code, label) values
  ('EUR', 'Euro'),
  ('USD', 'Dollar americain'),
  ('GBP', 'Livre sterling'),
  ('GBX', 'Penny sterling (cotation LSE, 1/100 GBP)'),
  ('CHF', 'Franc suisse'),
  ('SEK', 'Couronne suedoise'),
  ('NOK', 'Couronne norvegienne'),
  ('DKK', 'Couronne danoise'),
  ('PLN', 'Zloty polonais'),
  ('JPY', 'Yen japonais'),
  ('CNY', 'Yuan renminbi')
on conflict (code) do update set label = excluded.label;

-- --- Marches (codes MIC) ----------------------------------------------------
-- Perimetre v1 : zone euro eligible PEA. XSWX/XLON/XSTO/XCSE presents pour les
-- groupes de pairs elargis (doc 08) et l elargissement futur.
insert into exchanges (code, name, country_iso2, currency, timezone) values
  ('XPAR', 'Euronext Paris',      'FR', 'EUR', 'Europe/Paris'),
  ('XAMS', 'Euronext Amsterdam',  'NL', 'EUR', 'Europe/Amsterdam'),
  ('XBRU', 'Euronext Bruxelles',  'BE', 'EUR', 'Europe/Brussels'),
  ('XLIS', 'Euronext Lisbonne',   'PT', 'EUR', 'Europe/Lisbon'),
  ('XDUB', 'Euronext Dublin',     'IE', 'EUR', 'Europe/Dublin'),
  ('XETR', 'Xetra (Francfort)',   'DE', 'EUR', 'Europe/Berlin'),
  ('XMAD', 'Bolsa de Madrid',     'ES', 'EUR', 'Europe/Madrid'),
  ('XMIL', 'Borsa Italiana',      'IT', 'EUR', 'Europe/Rome'),
  ('XWBO', 'Wiener Borse',        'AT', 'EUR', 'Europe/Vienna'),
  ('XHEL', 'Nasdaq Helsinki',     'FI', 'EUR', 'Europe/Helsinki'),
  ('XSWX', 'SIX Swiss Exchange',  'CH', 'CHF', 'Europe/Zurich'),
  ('XLON', 'London Stock Exchange','GB', 'GBX', 'Europe/London'),
  ('XSTO', 'Nasdaq Stockholm',    'SE', 'SEK', 'Europe/Stockholm'),
  ('XCSE', 'Nasdaq Copenhague',   'DK', 'DKK', 'Europe/Copenhagen')
on conflict (code) do update set
  name = excluded.name, country_iso2 = excluded.country_iso2,
  currency = excluded.currency, timezone = excluded.timezone;

-- --- Secteurs ICB niveau 1 (industries, taxonomie 2019) ---------------------
insert into sectors (code, scheme, level, parent_code, label) values
  ('10', 'ICB', 1, null, 'Technology'),
  ('15', 'ICB', 1, null, 'Telecommunications'),
  ('20', 'ICB', 1, null, 'Health Care'),
  ('30', 'ICB', 1, null, 'Financials'),
  ('35', 'ICB', 1, null, 'Real Estate'),
  ('40', 'ICB', 1, null, 'Consumer Discretionary'),
  ('45', 'ICB', 1, null, 'Consumer Staples'),
  ('50', 'ICB', 1, null, 'Industrials'),
  ('55', 'ICB', 1, null, 'Basic Materials'),
  ('60', 'ICB', 1, null, 'Energy'),
  ('65', 'ICB', 1, null, 'Utilities')
on conflict (code) do update set
  scheme = excluded.scheme, level = excluded.level, label = excluded.label;

-- --- Sources de donnees (priority : plus bas = plus fiable) -----------------
insert into data_sources (id, code, label, kind, priority, base_url, license_note) values
  (1, 'manual',   'Saisie manuelle',            'reference',   1,  null,
      'Verite de reference : arbitre tous les conflits.'),
  (2, 'stooq',    'Stooq (CSV historiques)',    'price',       10, 'https://stooq.com/q/d/l/',
      'Source primaire cours. Pas d API officielle, debit a menager.'),
  (3, 'ecb',      'BCE - taux de reference',    'fx',          10, 'https://data-api.ecb.europa.eu/service/data',
      'Officiel, gratuit, stable.'),
  (4, 'esef',     'ESEF / XBRL (filings.xbrl.org)', 'fundamental', 15, 'https://filings.xbrl.org',
      'Structure, 2021+, ~30 pays europeens.'),
  (5, 'yfinance', 'Yahoo Finance (yfinance)',   'price',       20, 'https://finance.yahoo.com',
      'Secondaire cours + corporate actions + fondamentaux 5 ans. Scraper non officiel, rate-limite.'),
  (6, 'amf',      'AMF - info-financiere',      'fundamental', 30, 'https://api.info-financiere.fr/api/v1',
      'Documents PDF, pas de chiffres structures. 10 000 appels/IP/jour.'),
  (7, 'eurostat', 'Eurostat - IPCH',            'reference',   20, 'https://ec.europa.eu/eurostat/api/dissemination',
      'Deflateurs pour la politique real_deflated.')
on conflict (id) do update set
  code = excluded.code, label = excluded.label, kind = excluded.kind,
  priority = excluded.priority, base_url = excluded.base_url,
  license_note = excluded.license_note;

-- --- Concepts financiers canoniques (regime A, doc 02 SS3) ------------------
insert into financial_concepts (code, label, statement, unit_type, sign_convention) values
  ('revenue',            'Chiffre d affaires',              'income',   'currency', 'positive'),
  ('cost_of_revenue',    'Cout des ventes',                 'income',   'currency', 'positive'),
  ('gross_profit',       'Marge brute',                     'income',   'currency', 'signed'),
  ('operating_expenses', 'Charges operationnelles',         'income',   'currency', 'positive'),
  ('rd_expense',         'Recherche et developpement',      'income',   'currency', 'positive'),
  ('ebitda',             'EBITDA',                          'income',   'currency', 'signed'),
  ('ebit',               'Resultat operationnel (EBIT)',    'income',   'currency', 'signed'),
  ('interest_expense',   'Charges financieres',             'income',   'currency', 'positive'),
  ('tax_expense',        'Impot sur les societes',          'income',   'currency', 'positive'),
  ('net_income',         'Resultat net part du groupe',     'income',   'currency', 'signed'),
  ('minority_interest',  'Interets minoritaires',           'income',   'currency', 'signed'),
  ('eps_basic',          'BPA de base',                     'income',   'currency', 'signed'),
  ('eps_diluted',        'BPA dilue',                       'income',   'currency', 'signed'),

  ('total_assets',       'Total actif',                     'balance',  'currency', 'positive'),
  ('total_liabilities',  'Total passif exigible',           'balance',  'currency', 'positive'),
  ('total_equity',       'Capitaux propres',                'balance',  'currency', 'signed'),
  ('cash_and_equivalents','Tresorerie et equivalents',      'balance',  'currency', 'positive'),
  ('total_debt',         'Dette financiere brute',          'balance',  'currency', 'positive'),
  ('net_debt',           'Dette financiere nette',          'balance',  'currency', 'signed'),
  ('inventory',          'Stocks',                          'balance',  'currency', 'positive'),
  ('receivables',        'Creances clients',                'balance',  'currency', 'positive'),
  ('payables',           'Dettes fournisseurs',             'balance',  'currency', 'positive'),
  ('working_capital',    'Besoin en fonds de roulement',    'balance',  'currency', 'signed'),
  ('goodwill',           'Ecarts d acquisition',            'balance',  'currency', 'positive'),
  ('intangibles',        'Immobilisations incorporelles',   'balance',  'currency', 'positive'),
  ('invested_capital',   'Capitaux employes',               'balance',  'currency', 'signed'),

  ('cfo',                'Flux de tresorerie operationnels','cashflow', 'currency', 'signed'),
  ('capex',              'Investissements corporels',       'cashflow', 'currency', 'positive'),
  ('fcf',                'Flux de tresorerie disponible',   'cashflow', 'currency', 'signed'),
  ('dividends_paid',     'Dividendes verses',               'cashflow', 'currency', 'positive'),
  ('buybacks',           'Rachats d actions',               'cashflow', 'currency', 'positive'),

  ('shares_basic',       'Nombre d actions de base',        'balance',  'count',    'positive'),
  ('shares_diluted',     'Nombre d actions dilue',          'balance',  'count',    'positive'),

  ('nopat',              'Resultat operationnel apres impot','ratio',   'currency', 'signed'),
  ('roic',               'ROIC',                            'ratio',    'ratio',    'signed'),
  ('gross_margin',       'Taux de marge brute',             'ratio',    'ratio',    'signed'),
  ('foreign_revenue_pct','Part du CA hors marche domestique','ratio',   'percent',  'positive')
on conflict (code) do update set
  label = excluded.label, statement = excluded.statement,
  unit_type = excluded.unit_type, sign_convention = excluded.sign_convention;
