-- =============================================================================
-- 011 - Distinguer une date de publication observee d une date estimee
--
-- Le principe P2 exige que chaque fait porte la date a laquelle il se rapporte
-- ET la date a laquelle on a pu le savoir. Sans elle, « le look-ahead bias est
-- structurel et irrattrapable » (doc 00 SS3).
--
-- Or yfinance ne sert aucune date de publication : ses tableaux financiers sont
-- indexes par fin d exercice, point. Deux facons de reagir, une seule est
-- acceptable :
--
--   1. Stocker period_end comme published_at. INTERDIT : cela ferait croire que
--      les comptes 2024 etaient connus au 31 decembre 2024, alors qu ils ne le
--      sont qu en mars 2025. C est du look-ahead pur, et il serait invisible.
--
--   2. Estimer une borne SUPERIEURE. La directive Transparence impose aux
--      emetteurs europeens de publier leurs comptes annuels dans les quatre
--      mois suivant la cloture. period_end + 4 mois est donc une date a
--      laquelle l information etait certainement disponible.
--
-- L asymetrie est ce qui rend l option 2 sure : une estimation trop TARDIVE ne
-- peut produire qu un exces de prudence - on s interdit d utiliser un fait qu on
-- connaissait deja. Une estimation trop PRECOCE fabrique du look-ahead. On erre
-- donc deliberement du cote tardif.
--
-- Le drapeau existe pour que la distinction ne se perde jamais : le jour ou une
-- source servira les vraies dates - ESEF les porte -, on saura quels faits
-- reprendre.
-- =============================================================================

alter table financial_facts
  add column if not exists published_at_estimated boolean not null default false;

alter table financial_reports
  add column if not exists published_at_estimated boolean not null default false;

comment on column financial_facts.published_at_estimated is
  'true = published_at est une borne superieure calculee (period_end + delai '
  'reglementaire), pas une date observee. Erre volontairement du cote tardif : '
  'une estimation trop precoce fabriquerait du look-ahead.';

create index if not exists financial_facts_point_in_time_idx
  on financial_facts (instrument_id, published_at, concept_code);
