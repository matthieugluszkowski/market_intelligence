-- =============================================================================
-- 016 - Veille externe : consensus, notations, depeches (doc 02 SS2.5, lot L10)
--
-- Ce que ces deux tables stockent n est pas une donnee de marche, c est **ce
-- qu une source tierce affirmait un jour donne**. La distinction commande tout
-- le reste :
--
--   - le contenu est garde en JSONB, tel qu il a ete lu. Un consensus n a pas
--     le meme nombre de champs d une source a l autre, ni d une annee sur
--     l autre, et l eclater en colonnes couterait une migration a chaque
--     evolution de la page source ;
--   - rien de ce qui est ici n alimente un calcul. Ni le z-score, ni le score
--     de qualite, ni la solidite concurrentielle ne lisent ces tables. Un
--     consensus est une opinion agregee et revisee apres coup : l integrer a un
--     score reviendrait a noter un titre sur la popularite dont il jouit deja ;
--   - chaque collecte est **datee et conservee**. Le principe P5 vaut pour les
--     sources externes comme pour le modele : dans un an, savoir que le
--     consensus disait ACHETER a 243 EUR le jour ou le titre cotait 161 vaut
--     bien plus que la derniere valeur en date.
--
-- `external_sources` porte l adresse par titre. Elle existe pour Zonebourse,
-- qui adresse ses fiches par identifiant interne et n a aucun acces par ISIN :
-- l URL se colle une fois depuis le navigateur. Boursier.com, lui, resout par
-- ISIN - l enregistrement y sert seulement de cache de l URL canonique.
-- =============================================================================

create table if not exists external_sources (
  instrument_id  bigint not null references instruments(id) on delete cascade,
  source_code    text not null,
  url            text not null,
  added_at       timestamptz not null default now(),
  primary key (instrument_id, source_code)
);

comment on table external_sources is
  'Adresse de la fiche d un titre chez une source de veille. Saisie a la main '
  'pour Zonebourse (identifiant interne non devinable), deduite de l ISIN pour '
  'Boursier.com.';

create table if not exists external_briefs (
  id             bigint generated always as identity primary key,
  instrument_id  bigint not null references instruments(id) on delete cascade,
  source_code    text not null,               -- 'zonebourse' | 'boursier'
  kind           text not null,               -- 'consensus' | 'notations' | 'depeches'
  collected_on   date not null default current_date,
  collected_at   timestamptz not null default now(),
  source_url     text,
  payload        jsonb not null,
  constraint external_brief_kind_check
    check (kind in ('consensus', 'notations', 'depeches')),
  -- Une collecte par jour et par nature : relancer dans la journee corrige,
  -- le lendemain historise.
  constraint external_brief_unique unique (instrument_id, source_code, kind, collected_on)
);

create index if not exists external_briefs_recent_idx
  on external_briefs (instrument_id, kind, collected_on desc);

comment on table external_briefs is
  'Ce qu une source tierce affirmait un jour donne : consensus d analystes, '
  'notations, depeches. N alimente aucun calcul - affichage seul, avec sa '
  'source et son lien.';
comment on column external_briefs.collected_on is
  'Jour de la collecte, pas de la publication. Une relance le meme jour '
  'ecrase ; le lendemain ajoute une ligne.';
