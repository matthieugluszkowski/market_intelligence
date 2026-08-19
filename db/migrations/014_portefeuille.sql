-- =============================================================================
-- 014 - Portefeuille, supports et transactions (doc 11)
--
-- La seule raison valable de mettre le portefeuille ici plutot que dans un
-- tableur : **relier une position au signal qui l a declenchee**. fit_id et
-- quality_score_id pointent la ligne exacte en vigueur a l achat, et trois ans
-- plus tard on relit ce que le systeme affirmait - pas une reconstitution.
--
-- Si on ne devait garder qu une ligne de cette migration, ce serait celle-la.
-- =============================================================================

-- --- Supports ---------------------------------------------------------------
-- Le support est une entite et pas un champ texte, pour trois raisons :
-- les regles d eligibilite sont verifiables, les plafonds sont par support et
-- ne se deduisent d aucune position isolee, et la performance nette n est
-- comparable qu a fiscalite identique.
create table if not exists accounts (
  id                 bigint generated always as identity primary key,
  code               text not null unique,
  label              text not null,
  kind               text not null,
  broker             text,
  currency           char(3) not null default 'EUR' references currencies(code),
  opened_at          date,
  -- Regles en DONNEES, jamais en dur dans le code : elles changent, et une
  -- regle enfouie dans un `if` se decouvre le jour ou elle a deja produit une
  -- erreur. Meme principe que regression_policies.
  eligible_countries text[],              -- null = aucune restriction
  contribution_cap   numeric(14,2),       -- plafond de versements, null = aucun
  is_paper           boolean not null default false,
  notes              text,
  created_at         timestamptz not null default now(),
  constraint account_kind_check
    check (kind in ('PEA', 'PEA_PME', 'PER', 'CTO', 'AV', 'PAPER'))
);

comment on table accounts is
  'Supports de detention. Les parametres fiscaux sont DECLARES par l utilisateur '
  'et a verifier aupres de son etablissement : le systeme ne calcule aucune '
  'fiscalite et ne donne aucun conseil.';

-- --- Positions : reprise de la table du doc 01 SS7 ---------------------------
alter table positions
  add column if not exists account_id       bigint references accounts(id),
  add column if not exists is_paper         boolean not null default false,
  add column if not exists fit_id           bigint references regression_fits(id),
  add column if not exists quality_score_id bigint references quality_scores(id),
  add column if not exists watchlist_id     bigint references watchlist(id),
  add column if not exists fees             double precision not null default 0,
  add column if not exists closed_price     double precision,
  add column if not exists close_reason     text,
  add column if not exists review_at        date,
  add column if not exists thesis_verdict   text,
  add column if not exists thesis_review    text,
  add column if not exists price_source     text not null default 'close',
  add column if not exists created_at       timestamptz not null default now();

-- Une position sans these ne s enregistre pas. C est la seule friction imposee
-- de toute la fonctionnalite, et elle est deliberee : ecrire la these au moment
-- de l achat et la relire deux ans plus tard est le seul antidote fiable au
-- biais retrospectif - on reconstruit spontanement une justification de ce
-- qu on a fait.
alter table positions drop constraint if exists position_thesis_required;
alter table positions add constraint position_thesis_required
  check (thesis is not null and length(btrim(thesis)) >= 30);

-- Trois reponses possibles a « la these s est-elle verifiee ». La troisieme est
-- la plus importante : une these peut etre juste et la position perdante, ou
-- fausse et la position gagnante. Forcer un verdict binaire fabriquerait de
-- l apprentissage sur du bruit.
alter table positions drop constraint if exists position_thesis_verdict_check;
alter table positions add constraint position_thesis_verdict_check
  check (thesis_verdict is null
         or thesis_verdict in ('indeterminable', 'verifiee', 'infirmee'));

alter table positions drop constraint if exists position_price_source_check;
alter table positions add constraint position_price_source_check
  check (price_source in ('close', 'manual', 'statement'));

create index if not exists positions_ouvertes_idx
  on positions (account_id, instrument_id) where closed_at is null;

-- --- Transactions -----------------------------------------------------------
-- `positions` decrit une ligne detenue, `transactions` les mouvements. Les
-- separer permet renforts et cessions partielles sans reecrire le prix de
-- revient a la main.
create table if not exists transactions (
  id           bigint generated always as identity primary key,
  position_id  bigint not null references positions(id) on delete cascade,
  kind         text not null,
  executed_at  date not null,
  quantity     double precision,
  price        double precision,
  amount       double precision,
  fees         double precision not null default 0,
  -- Porte la sincerite de la mesure : une execution au cours de cloture et un
  -- prix saisi a la main ne se lisent pas pareil, et l agregat doit pouvoir
  -- les separer.
  price_source text not null default 'close',
  note         text,
  created_at   timestamptz not null default now(),
  constraint transaction_kind_check
    check (kind in ('buy', 'sell', 'dividend', 'fee', 'split_adj')),
  constraint transaction_price_source_check
    check (price_source in ('close', 'manual', 'statement'))
);

create index if not exists transactions_position_idx
  on transactions (position_id, executed_at);

-- --- Un support de paper trading, pour que la fonctionnalite marche seule ----
-- Les positions fictives vivent dans un support dedie, jamais dans un support
-- reel : aucun ecran n agrege du reel et du fictif dans le meme chiffre.
insert into accounts (code, label, kind, is_paper, notes)
values ('PAPER', 'Paper trading', 'PAPER', true,
        'Positions fictives. Le paper trading mesure la methode, pas '
        'l investisseur : il supprime la peur de la perte et l attente de '
        'dix-huit mois, c est-a-dire ce qui fait reellement echouer les gens.')
on conflict (code) do nothing;
