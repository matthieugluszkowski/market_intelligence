-- =============================================================================
-- Groupes de pairs manuels (doc 08 SS7, limite L1)
--
-- LA limite la plus serieuse du systeme : le groupe de pairs sectoriel
-- automatique est construit a partir des seuls titres europeens de la base, or
-- **les menaces concurrentielles les plus dangereuses viennent presque toujours
-- de l exterieur de cet univers**.
--
--   Shark Ninja, l agresseur de Seb, est americaine.
--   BYD, l agresseur de BMW, est chinoise.
--   Revolut, Lydia et Qonto, les agresseurs des bancaires, ne sont pas cotees.
--
-- Un screener sectoriel automatique sous-estime donc systematiquement la menace,
-- et il le fait de facon d autant plus rassurante que le titre reste leader dans
-- un univers qui ne contient pas son concurrent.
--
-- D ou la regle : **au moins un concurrent hors Europe est obligatoire** dans
-- tout groupe qualifie. Un groupe purement europeen est marque `is_complete`
-- a false, et aucun titre ne peut alors passer en `solid`.
--
-- Sur les donnees des pairs hors univers
-- ---------------------------------------
-- On inscrit ici l identite des concurrents - fait verifiable - et non leurs
-- chiffres d affaires. Saisir de memoire des CA que je ne peux pas sourcer
-- fabriquerait la precision qu on cherche justement a etablir, et fausserait la
-- part de marche relative sans que rien ne le signale. `external_ref` porte donc
-- le pays et la cotation ; la valeur reste a renseigner a la main.
--
-- Perimetre : les titres du podcast et les cas de reference du doc 08. Le doc 05
-- recommande 20 a 30 titres suivis manuellement ; on commence par ceux dont la
-- lecture est deja etablie.
-- =============================================================================

-- --- Groupes ---------------------------------------------------------------
insert into peer_groups (code, label, kind, sector_code, is_complete, notes) values
  ('MAN:PETIT_ELECTRO', 'Petit electromenager mondial', 'manual', '40', true,
   'Cas du podcast : le coeur de Seb est attaque par Shark Ninja, americaine. '
   'Un groupe purement europeen ne verrait pas la menace.'),
  ('MAN:AUTO_PREMIUM', 'Automobile premium mondiale', 'manual', '40', true,
   'BMW perd de la part en Chine face a BYD. Tesla et BYD sont indispensables '
   'au groupe : sans eux, BMW reste leader d un univers qui ne contient pas '
   'ses concurrents.'),
  ('MAN:CHIMIE_SPECIALITE', 'Chimie de specialite mondiale', 'manual', '55', true,
   'Arkema, cas cyclique de reference. Le groupe inclut Dow et LyondellBasell '
   'pour que le cycle se lise sur le secteur mondial et non europeen.'),
  ('MAN:LUXE', 'Luxe mondial', 'manual', '40', true,
   'LVMH, Hermes et Kering face aux maisons suisses et americaines.'),
  ('MAN:SEMICONDUCTEURS', 'Semiconducteurs', 'manual', '10', true,
   'ASML et Infineon dans un secteur ou la concurrence est integralement '
   'extra-europeenne.'),
  ('MAN:LOGICIEL_ENTREPRISE', 'Logiciel d entreprise', 'manual', '10', true,
   'SAP et Dassault Systemes face aux editeurs americains.')
on conflict (code) do update set
  label = excluded.label, is_complete = excluded.is_complete, notes = excluded.notes;

-- --- Membres de l univers --------------------------------------------------
insert into peer_group_members (peer_group_id, instrument_id, is_in_universe)
select g.id, i.id, true
  from peer_groups g
  join (values
    ('MAN:PETIT_ELECTRO',      'EQ:FR:SEB'),
    ('MAN:AUTO_PREMIUM',       'EQ:DE:BMW'),
    ('MAN:AUTO_PREMIUM',       'EQ:DE:MERCEDES'),
    ('MAN:AUTO_PREMIUM',       'EQ:IT:FERRARI'),
    ('MAN:CHIMIE_SPECIALITE',  'EQ:FR:ARKEMA'),
    ('MAN:CHIMIE_SPECIALITE',  'EQ:DE:BASF'),
    ('MAN:LUXE',               'EQ:FR:LVMH'),
    ('MAN:LUXE',               'EQ:FR:HERMES'),
    ('MAN:LUXE',               'EQ:FR:KERING'),
    ('MAN:SEMICONDUCTEURS',    'EQ:NL:ASML'),
    ('MAN:SEMICONDUCTEURS',    'EQ:DE:INFINEON'),
    ('MAN:LOGICIEL_ENTREPRISE','EQ:DE:SAP'),
    ('MAN:LOGICIEL_ENTREPRISE','EQ:FR:DASSAULTSYS')
  ) as m(groupe, titre) on m.groupe = g.code
  join instruments i on i.internal_code = m.titre
on conflict do nothing;

-- --- Concurrents hors univers ----------------------------------------------
-- C est cette table qui rend le groupe complet. `external_ref` ne porte que des
-- faits verifiables : pays et cotation. Le chiffre d affaires reste a saisir.
insert into peer_group_members
  (peer_group_id, external_name, external_ref, is_in_universe)
select g.id, m.nom, m.reference::jsonb, false
  from peer_groups g
  join (values
    ('MAN:PETIT_ELECTRO', 'SharkNinja',
     '{"pays":"US","cotation":"SN (NYSE)","menace":"coeur de gamme de Seb","ca_musd":null}'),
    ('MAN:PETIT_ELECTRO', 'Midea',
     '{"pays":"CN","cotation":"000333 (Shenzhen)","ca_musd":null}'),
    ('MAN:AUTO_PREMIUM', 'BYD',
     '{"pays":"CN","cotation":"1211 (HKEX)","menace":"part de marche en Chine","ca_musd":null}'),
    ('MAN:AUTO_PREMIUM', 'Tesla',
     '{"pays":"US","cotation":"TSLA (Nasdaq)","ca_musd":null}'),
    ('MAN:CHIMIE_SPECIALITE', 'Dow',
     '{"pays":"US","cotation":"DOW (NYSE)","ca_musd":null}'),
    ('MAN:CHIMIE_SPECIALITE', 'LyondellBasell',
     '{"pays":"US","cotation":"LYB (NYSE)","ca_musd":null}'),
    ('MAN:LUXE', 'Richemont',
     '{"pays":"CH","cotation":"CFR (SIX)","note":"hors PEA","ca_musd":null}'),
    ('MAN:LUXE', 'Tapestry',
     '{"pays":"US","cotation":"TPR (NYSE)","ca_musd":null}'),
    ('MAN:SEMICONDUCTEURS', 'TSMC',
     '{"pays":"TW","cotation":"2330 (TWSE)","ca_musd":null}'),
    ('MAN:SEMICONDUCTEURS', 'Applied Materials',
     '{"pays":"US","cotation":"AMAT (Nasdaq)","ca_musd":null}'),
    ('MAN:SEMICONDUCTEURS', 'Texas Instruments',
     '{"pays":"US","cotation":"TXN (Nasdaq)","ca_musd":null}'),
    ('MAN:LOGICIEL_ENTREPRISE', 'Oracle',
     '{"pays":"US","cotation":"ORCL (NYSE)","ca_musd":null}'),
    ('MAN:LOGICIEL_ENTREPRISE', 'Salesforce',
     '{"pays":"US","cotation":"CRM (NYSE)","ca_musd":null}'),
    ('MAN:LOGICIEL_ENTREPRISE', 'Autodesk',
     '{"pays":"US","cotation":"ADSK (Nasdaq)","ca_musd":null}')
  ) as m(groupe, nom, reference) on m.groupe = g.code
on conflict do nothing;
