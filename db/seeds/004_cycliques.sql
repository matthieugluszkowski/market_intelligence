-- =============================================================================
-- Declaration manuelle des titres cycliques
--
-- Pourquoi une declaration manuelle plutot qu un test statistique
-- ----------------------------------------------------------------
-- Le test statistique - forte volatilite du ROIC et serie non monotone - ne
-- fonctionne que sur un cycle complet. Avec quatre a cinq exercices, la fenetre
-- ne couvre souvent que la DESCENTE d un cycle, et une descente de cycle est
-- statistiquement indiscernable d une erosion : meme pente, meme monotonie.
--
-- Constate sur Arkema. La chimie etait au pic en 2022 et decline depuis ; sur
-- quatre points, la serie est monotone decroissante, donc classee `eroding`.
-- Le doc 08 dit exactement l inverse : *Arkema - non applicable : regime
-- cyclique - bas de cycle, pas erosion*. Le classer en value trap reviendrait a
-- exclure precisement le moment ou il faut regarder.
--
-- C est la limite L2 du doc 08 : *cinq ans de fondamentaux, c est court pour une
-- notion de durabilite*. Aucune amelioration du code ne la leve - il faut soit
-- plus d historique, soit une information exterieure.
--
-- Le doc identifie d ailleurs ces titres par leur METIER, pas par un test :
-- *Arkema, BMW, Beneteau - les valeurs cycliques que Marie recommande
-- explicitement*. On applique donc ici le meme principe que pour les groupes de
-- pairs : la declaration manuelle prime sur la detection automatique.
--
-- A revoir quand huit exercices seront disponibles : le test statistique
-- redeviendra alors capable de trancher seul.
-- =============================================================================

update instruments
   set attributes = jsonb_set(attributes, '{regime_declare}', '"cyclical"'::jsonb),
       updated_at = now()
 where internal_code in (
   'EQ:FR:ARKEMA',        -- chimie de specialite, cas de reference du doc 08
   'EQ:DE:BASF',          -- chimie de base
   'EQ:DE:BMW',           -- automobile premium, cas de reference
   'EQ:DE:MERCEDES',      -- automobile premium
   'EQ:FR:MICHELIN',      -- pneumatique, suit le cycle automobile
   'EQ:DE:INFINEON',      -- semiconducteurs, cycle notoire
   'EQ:FR:SAINTGOBAIN',   -- materiaux de construction
   'EQ:FR:ARCELOR',       -- si present un jour
   'EQ:FR:TTE',           -- petrole, cycle des matieres premieres
   'EQ:IT:ENI',           -- petrole
   'EQ:FR:SAFRAN',        -- aeronautique, cycle long
   'EQ:FR:AIRBUS'         -- aeronautique, cycle long
 );
