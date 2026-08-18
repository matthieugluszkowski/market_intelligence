-- =============================================================================
-- 008 - Statistiques de regime sur regression_fits  (doc 03 SS4)
--
-- Ajout au schema du doc 01, requis par le critere d acceptation du lot L4.
-- Le doc 03 SS4 impose d afficher la distribution du temps de premier passage
-- plutot qu une pseudo-probabilite de retournement ; ces statistiques sont
-- calculees en meme temps que le fit, sur la meme fenetre, et doivent donc etre
-- historisees avec lui - sans quoi on ne saurait plus, dans trois ans, sur quelle
-- fenetre elles portaient.
--
-- JSONB plutot que des colonnes : le contenu evoluera (horizons, seuils), et ce
-- sont des donnees d affichage, jamais des criteres de tri.
-- =============================================================================

alter table regression_fits
  add column if not exists regime_stats jsonb;

comment on column regression_fits.regime_stats is
  'Statistiques de regime in-sample : episodes sous seuil, durees, drawdowns, '
  'rendements a horizon. Descriptif du passe du titre, aucune valeur predictive.';
