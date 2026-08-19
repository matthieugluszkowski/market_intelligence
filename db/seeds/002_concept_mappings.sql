-- =============================================================================
-- Correspondance des libelles provider vers les concepts canoniques
--
-- C'est la table qui permet a trois sources heterogenes de cohabiter sans
-- migration DDL a chaque nouveau concept (doc 01 SS5.2). Ajouter une source
-- revient a inserer des lignes ici, jamais a toucher au schema.
--
-- Regle de lecture : plusieurs libelles peuvent pointer vers un meme concept.
-- Le normaliseur retient le premier trouve dans un ordre de preference explicite,
-- ce qui evite qu'un libelle de repli ecrase une valeur plus fiable.
-- =============================================================================

insert into concept_mappings (source_id, source_label, concept_code)
select 5, libelle, concept from (values
  -- --- compte de resultat -------------------------------------------------
  ('Total Revenue',                             'revenue'),
  ('Operating Revenue',                         'revenue'),
  ('Cost Of Revenue',                           'cost_of_revenue'),
  ('Reconciled Cost Of Revenue',                'cost_of_revenue'),
  ('Gross Profit',                              'gross_profit'),
  ('Operating Expense',                         'operating_expenses'),
  ('Research And Development',                  'rd_expense'),
  ('EBITDA',                                    'ebitda'),
  ('Normalized EBITDA',                         'ebitda'),
  ('EBIT',                                      'ebit'),
  ('Operating Income',                          'ebit'),
  ('Interest Expense',                          'interest_expense'),
  ('Tax Provision',                             'tax_expense'),
  ('Net Income',                                'net_income'),
  ('Net Income Common Stockholders',            'net_income'),
  ('Minority Interests',                        'minority_interest'),
  ('Basic EPS',                                 'eps_basic'),
  ('Diluted EPS',                               'eps_diluted'),

  -- --- bilan ---------------------------------------------------------------
  ('Total Assets',                              'total_assets'),
  ('Total Liabilities Net Minority Interest',   'total_liabilities'),
  ('Stockholders Equity',                       'total_equity'),
  ('Total Equity Gross Minority Interest',      'total_equity'),
  ('Cash And Cash Equivalents',                 'cash_and_equivalents'),
  ('Cash Cash Equivalents And Short Term Investments', 'cash_and_equivalents'),
  ('Total Debt',                                'total_debt'),
  ('Net Debt',                                  'net_debt'),
  ('Inventory',                                 'inventory'),
  ('Accounts Receivable',                       'receivables'),
  ('Accounts Payable',                          'payables'),
  ('Working Capital',                           'working_capital'),
  ('Goodwill',                                  'goodwill'),
  ('Goodwill And Other Intangible Assets',      'intangibles'),
  ('Invested Capital',                          'invested_capital'),
  ('Ordinary Shares Number',                    'shares_basic'),
  ('Share Issued',                              'shares_basic'),
  ('Diluted Average Shares',                    'shares_diluted'),

  -- --- flux de tresorerie --------------------------------------------------
  ('Operating Cash Flow',                       'cfo'),
  ('Cash Flow From Continuing Operating Activities', 'cfo'),
  ('Capital Expenditure',                       'capex'),
  ('Free Cash Flow',                            'fcf'),
  ('Cash Dividends Paid',                       'dividends_paid'),
  ('Common Stock Dividend Paid',                'dividends_paid'),
  ('Repurchase Of Capital Stock',               'buybacks')
) as m(libelle, concept)
on conflict (source_id, source_label) do update set concept_code = excluded.concept_code;
