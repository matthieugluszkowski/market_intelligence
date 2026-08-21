-- =============================================================================
-- 015 - Corriger une saisie de position, sans reecrire l historique en silence
--
-- Constat a l usage : une position ouverte sur le mauvais titre - la liste est
-- triee par nom, le premier element etait preselectionne - ne pouvait plus etre
-- rattrapee. La seule issue offerte par l ecran etait de la *fermer*, ce qui
-- inscrivait une erreur de saisie dans le bilan de la methode comme s il
-- s agissait d une decision.
--
-- Deux choses different et l outil doit les separer :
--
--   corriger  la position enregistree ne decrit pas ce qui a ete fait. On
--             retablit les faits : titre, quantite, prix, date, support.
--   fermer    la position decrivait bien ce qui a ete fait, et on en sort.
--             C est une decision, elle compte dans la mesure de la methode.
--
-- Pourquoi un journal plutot qu un simple update
-- -----------------------------------------------
-- Tout ce projet est construit contre le biais retrospectif : `thesis` s ecrit
-- avant, `fit_id` fige ce que le systeme affirmait, la watchlist s horodate au
-- lieu de s effacer. Un `update` muet sur une position ouvrirait la porte de
-- derriere - reajuster apres coup un prix d entree ou une these devenue genante,
-- sans que rien ne le montre.
--
-- Le journal ne l interdit pas : il le rend visible. C est le meme arbitrage
-- que l acquittement de la migration 010 - on n empeche pas l humain de
-- trancher, on garde la trace qu il a tranche.
-- =============================================================================

create table if not exists position_corrections (
  id            bigint generated always as identity primary key,
  -- Passe a null si la position est supprimee ; `position_ref` garde le
  -- numero, pour qu une suppression laisse quand meme une ligne lisible.
  position_id   bigint references positions(id) on delete set null,
  position_ref  bigint not null,
  corrected_at  timestamptz not null default now(),
  kind          text not null,
  field_name    text,                  -- null pour une suppression
  old_value     text,
  new_value     text,
  reason        text not null,
  -- La position telle qu elle etait AVANT : relire le journal ne doit pas
  -- exiger de reconstituer l etat d alors a partir des lignes voisines.
  summary       text not null,
  constraint position_correction_kind_check
    check (kind in ('update', 'delete')),
  constraint position_correction_reason_check
    check (length(btrim(reason)) >= 5),
  constraint position_correction_field_check
    check (kind = 'delete' or field_name is not null)
);

create index if not exists position_corrections_idx
  on position_corrections (position_ref, corrected_at desc);

comment on table position_corrections is
  'Journal des corrections de saisie sur les positions. Corriger n est pas '
  'fermer : une position fermee est une decision et compte dans la mesure de '
  'la methode, une position corrigee est une saisie qui ne decrivait pas les '
  'faits.';
comment on column position_corrections.reason is
  'Pourquoi la correction. Obligatoire : sans motif, le journal ne distingue '
  'plus une erreur de frappe d un reajustement apres coup.';
comment on column position_corrections.summary is
  'La position telle qu elle etait avant la correction, en une ligne.';
