-- =============================================================================
-- 013 - Watchlist : les titres qu on suit reellement (doc 10)
--
-- Le screener rend 57 lignes ; la watchlist dit lesquelles on suit. C est une
-- selection humaine, pas un filtre calcule : elle survit au fait qu un titre
-- sorte des criteres du jour.
--
-- Trois choix de conception
-- --------------------------
-- 1. **Retrait en douceur.** On ne supprime pas une ligne, on l horodate. Savoir
--    qu on a suivi Kering pendant huit mois puis qu on l a retire est une
--    information ; l effacer laisse croire qu on ne l a jamais regarde. Meme
--    raisonnement que pour le journal d anomalies et pour regression_fits.
--
-- 2. **Le z-score au moment de l ajout.** Fige ce que le systeme affirmait ce
--    jour-la. Sans lui, on ne peut plus dire trois mois plus tard si le titre a
--    baisse depuis qu on le suit ou s il etait deja bas - et c est precisement
--    la question qu on se pose en rouvrant sa liste.
--
-- 3. **Une note libre, ecrite en ajoutant.** Meme role que `positions.thesis` :
--    relire dans un an pourquoi on avait mis un titre sous surveillance est le
--    seul antidote fiable au biais retrospectif. On reconstruit spontanement une
--    justification de ce qu on a fait.
-- =============================================================================

create table if not exists watchlist (
  id             bigint generated always as identity primary key,
  instrument_id  bigint not null references instruments(id) on delete cascade,
  added_at       timestamptz not null default now(),
  note           text,
  z_at_add       double precision,
  fit_at_add     text,
  quality_at_add text,
  removed_at     timestamptz,
  removal_reason text
);

-- Un titre n est suivi qu une fois a la fois. Rien n empeche de le reprendre
-- apres retrait : c est une reprise, et elle doit se voir.
create unique index if not exists watchlist_active_unique
  on watchlist (instrument_id) where removed_at is null;

create index if not exists watchlist_recent_idx
  on watchlist (added_at desc) where removed_at is null;

comment on column watchlist.z_at_add is
  'z-score au moment de l ajout. Fige ce que le systeme affirmait ce jour-la : '
  'sans lui on ne sait plus si le titre a baisse depuis, ou s il etait deja bas.';
comment on column watchlist.note is
  'Pourquoi on suit ce titre, ecrit EN AJOUTANT. Relire dans un an est le seul '
  'antidote fiable au biais retrospectif.';
