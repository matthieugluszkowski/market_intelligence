# 01 - Modèle de données

**Cible :** PostgreSQL 15+ standard. Aucune extension propriétaire. Compatible Supabase et Postgres nu.
**Convention :** snake_case, clés primaires `id` en `bigint generated always as identity`, horodatages en `timestamptz` UTC.

---

## 1. Vue logique

```
        ┌─────────────── RÉFÉRENTIEL ────────────────┐
        │  asset_classes    exchanges    currencies  │
        │  sectors          data_sources             │
        └──────────────────┬─────────────────────────┘
                           │
                    ┌──────▼───────┐
                    │ instruments  │◀──── instrument_symbols (mapping providers)
                    │  (ISIN = clé)│◀──── index_memberships (historisé)
                    └──────┬───────┘
                           │
        ┌──────────────────┼──────────────────────────┐
        │                  │                          │
   ┌────▼─────┐    ┌───────▼──────────┐      ┌────────▼─────────┐
   │   RAW    │    │   RAW FONDAM.    │      │     DÉRIVÉ       │
   │  bars    │    │ financial_reports│      │ regression_fits  │
   │  corp.   │    │ financial_facts  │      │ screener_snap.   │
   │  shares  │    │ concepts         │      │ quality_issues   │
   │  fx_rates│    └──────────────────┘      └──────────────────┘
   └──────────┘
```

**Règle absolue :** tout ce qui est en DÉRIVÉ est reconstructible en tronquant et relançant. Rien d'irremplaçable n'y vit.

---

## 2. Référentiel

### 2.1 Classes d'actifs

Le champ qui rend le système multi-actifs. Il ne sert pas qu'à étiqueter : il détermine **quelle méthode analytique s'applique**.

```sql
create table asset_classes (
  code            text primary key,          -- 'equity', 'etf', 'index', 'commodity', 'crypto', 'fx', 'bond'
  label           text not null,
  -- comportement analytique
  supports_fundamentals  boolean not null default false,
  default_policy_code    text,               -- politique de régression par défaut
  notes           text
);

insert into asset_classes (code, label, supports_fundamentals, default_policy_code) values
  ('equity',    'Action',            true,  'loglin_20y'),
  ('etf',       'ETF',               false, 'loglin_30y'),
  ('index',     'Indice',            false, 'loglin_30y'),
  ('commodity', 'Matière première',  false, 'real_deflated'),
  ('crypto',    'Crypto-actif',      false, 'excluded'),
  ('fx',        'Devise',            false, 'excluded'),
  ('bond',      'Obligation',        false, 'excluded');
```

*Pourquoi une table et pas un enum :* ajouter une classe d'actif ne doit pas exiger de migration DDL. Et `default_policy_code` matérialise le principe P6 - la crypto est explicitement exclue du modèle log-linéaire, dans la donnée, pas dans un `if` enfoui.

### 2.2 Marchés, devises, secteurs

```sql
create table exchanges (
  code         text primary key,             -- 'XPAR', 'XETR', 'XAMS' (codes MIC)
  name         text not null,
  country_iso2 char(2),
  currency     char(3) not null,
  timezone     text not null default 'Europe/Paris'
);

create table currencies (
  code    char(3) primary key,               -- ISO 4217
  label   text not null
);

create table sectors (
  code        text primary key,              -- classification ICB ou GICS
  scheme      text not null default 'ICB',
  level       smallint not null,             -- 1=industrie ... 4=sous-secteur
  parent_code text references sectors(code),
  label       text not null
);
```

*Le secteur est indispensable à l'analyse concurrentielle de phase 2 : comparer une décote à celle de ses pairs n'a de sens qu'à secteur donné.*

### 2.3 Sources de données

```sql
create table data_sources (
  id            smallint primary key,
  code          text not null unique,        -- 'stooq', 'yfinance', 'esef', 'amf', 'ecb', 'manual'
  label         text not null,
  kind          text not null,               -- 'price', 'fundamental', 'reference', 'fx'
  priority      smallint not null default 100, -- plus bas = plus fiable, arbitre les conflits
  base_url      text,
  license_note  text,
  active        boolean not null default true
);
```

*`priority` sert à arbitrer quand deux sources donnent des cours différents pour le même jour. On ne choisit pas au hasard et on trace le choix.*

---

## 3. Instruments et identité

### 3.1 Table centrale

```sql
create table instruments (
  id              bigint generated always as identity primary key,
  isin            char(12) unique,           -- clé métier, nullable pour crypto/indices
  internal_code   text not null unique,      -- fallback stable : 'EQ:FR:SEB', 'CX:BTC', 'IX:CAC40'
  asset_class     text not null references asset_classes(code),
  name            text not null,
  exchange_code   text references exchanges(code),
  currency        char(3) not null references currencies(code),
  sector_code     text references sectors(code),
  country_iso2    char(2),

  -- cycle de vie : indispensable pour traiter le survivorship bias
  is_active       boolean not null default true,
  listed_at       date,
  delisted_at     date,
  delisting_reason text,                     -- 'bankruptcy','merger','buyout','transfer','unknown'

  -- politique analytique : null = on applique le défaut de la classe d'actif
  policy_code     text references regression_policies(code),

  attributes      jsonb not null default '{}'::jsonb,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);

create index on instruments (asset_class) where is_active;
create index on instruments (sector_code);
create index on instruments using gin (attributes);
```

**Trois points de conception à noter.**

`delisting_reason` n'est pas cosmétique. Une radiation pour faillite et une radiation pour OPA biaisent un backtest **en sens opposés** - c'est l'erreur que j'avais faite dans l'avis critique avec Hang Seng Bank. Sans ce champ, on ne peut pas corriger.

`attributes` en JSONB absorbe les spécificités de classe sans multiplier les tables : `{"replication":"physical","ter":0.0007}` pour un ETF, `{"consensus_mechanism":"pos"}` pour une crypto, `{"contract_size":100}` pour une matière première. Le prix à payer est l'absence de contrainte typée ; le gain est de pouvoir ajouter une classe d'actif sans DDL.

`internal_code` existe parce que les indices et les cryptos n'ont pas d'ISIN. On a toujours une clé stable.

### 3.2 Le mapping des symboles - la table qui évite le pire bug

```sql
create table instrument_symbols (
  id             bigint generated always as identity primary key,
  instrument_id  bigint not null references instruments(id) on delete cascade,
  source_id      smallint not null references data_sources(id),
  symbol         text not null,              -- 'SK.PA' chez yfinance, 'sk.fr' chez stooq
  valid_from     date not null default '1900-01-01',
  valid_to       date not null default '9999-12-31',
  is_primary     boolean not null default false,
  constraint symbol_period_unique unique (source_id, symbol, valid_from)
);

create index on instrument_symbols (instrument_id, source_id);
```

**Pourquoi cette table est non négociable.** Les tickers changent (Facebook → Meta, FB → META), sont réutilisés par d'autres sociétés après radiation, et diffèrent d'un provider à l'autre pour le même titre. Un modèle qui stocke le ticker dans `instruments` perd de l'historique et fusionne des sociétés distinctes par accident. La validité temporelle permet de rejouer une extraction "comme en 2015".

*Anecdote qui illustre : dans le podcast, Mathieu cherche le code de Seb et hésite entre SK.PA et SEB - qui est une banque suédoise. C'est exactement le bug que cette table prévient.*

### 3.3 Appartenance aux indices, historisée

```sql
create table index_memberships (
  id             bigint generated always as identity primary key,
  index_id       bigint not null references instruments(id),   -- l'indice est lui-même un instrument
  member_id      bigint not null references instruments(id),
  valid_from     date not null,
  valid_to       date not null default '9999-12-31',
  weight         double precision,
  source_id      smallint references data_sources(id),
  constraint membership_unique unique (index_id, member_id, valid_from)
);
```

*Cette table est le seul remède au survivorship bias. On ne la remplira pas complètement en v1 - les compositions historiques ne sont pas disponibles gratuitement - mais la structure doit exister pour accueillir un backfill manuel ou payant plus tard. Sans elle, tout backtest futur sera irrémédiablement optimiste.*

---

## 4. Données de marché (RAW, append-only)

### 4.1 Barres de cotation

```sql
create table bars (
  instrument_id  bigint not null references instruments(id),
  freq           text   not null,            -- '1d', '1w', '1mo'
  ts             date   not null,            -- date de clôture de la barre
  open           double precision,
  high           double precision,
  low            double precision,
  close          double precision not null,  -- COURS BRUT, jamais ajusté
  volume         bigint,
  source_id      smallint not null references data_sources(id),
  ingested_at    timestamptz not null default now(),
  primary key (instrument_id, freq, ts)
) partition by list (freq);

create table bars_1d  partition of bars for values in ('1d');
create table bars_1w  partition of bars for values in ('1w');
create table bars_1mo partition of bars for values in ('1mo');

create index on bars_1d (ts);
create index on bars_1w (ts);
```

**`close` est le cours brut. C'est le principe P4 et il mérite d'être répété.** L'`adj_close` de Yahoo est recalculé rétroactivement à chaque détachement de dividende : la même requête donne un résultat différent à six mois d'intervalle. Un backtest bâti dessus n'est pas reproductible, et on ne s'en aperçoit jamais. On stocke le brut, on ajuste au calcul via `corporate_actions`.

**Types en `double precision` et non `real`.** Coût : 16 octets de plus par ligne, soit environ 9 Mo sur l'univers v1. Bénéfice : pas de perte de précision sur les rendements composés à 30 ans. Le compromis est évident dans ce sens.

**Chemin de scalabilité.** Le partitionnement par `freq` coûte zéro aujourd'hui. Quand le volume l'exigera - au-delà de ~10 M de lignes - on sous-partitionne `bars_1d` par année en RANGE sur `ts`, ou on bascule la table en hypertable TimescaleDB sur le VPS. Les deux chemins sont ouverts sans réécrire l'application.

### 4.2 Opérations sur titre

```sql
create table corporate_actions (
  id             bigint generated always as identity primary key,
  instrument_id  bigint not null references instruments(id),
  action_type    text not null,              -- 'split','reverse_split','cash_dividend','stock_dividend',
                                             -- 'rights_issue','capital_increase','spinoff','merger'
  ex_date        date not null,
  payment_date   date,
  ratio          double precision,           -- 2.0 pour un split 2:1
  amount         double precision,           -- montant du dividende par action
  currency       char(3) references currencies(code),
  source_id      smallint not null references data_sources(id),
  announced_at   date,                       -- bitemporalité (P2)
  ingested_at    timestamptz not null default now(),
  raw            jsonb,
  constraint ca_unique unique (instrument_id, action_type, ex_date, coalesce(ratio,0), coalesce(amount,0))
);

create index on corporate_actions (instrument_id, ex_date);
```

### 4.3 Nombre d'actions - la table qui détecte les dilutions

```sql
create table shares_outstanding (
  instrument_id  bigint not null references instruments(id),
  as_of          date not null,
  shares         bigint not null,
  source_id      smallint not null references data_sources(id),
  published_at   date,
  primary key (instrument_id, as_of)
);
```

**Cette table traite un problème identifié dans l'avis critique et qui n'a pas de solution ailleurs.** Atos, Casino, emeis, Solocal sont toujours cotés : ils ne sortent pas par le filtre "radiation". Mais après une dilution d'un facteur 100, leur cours ajusté rend la droite de régression historique absurde - le titre apparaîtra massivement "décoté" alors que la valeur par action a été détruite.

**Règle dérivée :** toute variation du nombre d'actions supérieure à un seuil (proposé : +50% sur 12 mois glissants) déclenche une invalidation de la régression sur la fenêtre antérieure. C'est un filtre que ni Hiboo ni les screeners grand public n'appliquent, et c'est probablement le plus rentable de tout le système.

### 4.4 Taux de change

```sql
create table fx_rates (
  base       char(3) not null,
  quote      char(3) not null,
  ts         date not null,
  rate       double precision not null,
  source_id  smallint not null references data_sources(id),
  primary key (base, quote, ts)
);
```

*Source : BCE, séries de référence quotidiennes, gratuites et stables.*

**Décision analytique associée, à challenger :** la régression se calcule **en devise locale**, pas en euro. Régresser un titre suisse converti en euro mélange la tendance du titre et celle du CHF/EUR - on ne saurait plus ce qu'on mesure. La conversion en euro intervient uniquement au niveau de la performance de portefeuille.

---

## 5. Fondamentaux (RAW)

### 5.1 Documents source

```sql
create table financial_reports (
  id             bigint generated always as identity primary key,
  instrument_id  bigint not null references instruments(id),
  report_type    text not null,              -- 'annual','semi_annual','quarterly','press_release'
  fiscal_year    smallint,
  period_end     date not null,              -- LA PÉRIODE CONCERNÉE
  published_at   date,                       -- QUAND ON A PU LE SAVOIR (P2)
  language       char(2),
  source_id      smallint not null references data_sources(id),
  document_url   text,
  storage_path   text,                       -- copie locale du PDF/XBRL
  extraction_status text not null default 'pending',
      -- 'pending','extracted','failed','not_needed'
  extraction_method text,                    -- 'xbrl','llm_pdf','provider_api','manual'
  extracted_at   timestamptz,
  constraint report_unique unique (instrument_id, report_type, period_end, source_id)
);
```

*`published_at` distinct de `period_end` est ce qui rend une analyse point-in-time possible. Les comptes 2024 d'une société ne sont connus qu'en mars 2025 ; les utiliser pour juger le titre en janvier 2025 est du look-ahead pur.*

### 5.2 Faits financiers - modèle EAV assumé

```sql
create table financial_concepts (
  code         text primary key,             -- canon interne : 'revenue','ebit','net_income',
                                             -- 'total_equity','net_debt','fcf','shares_diluted'
  label        text not null,
  statement    text not null,                -- 'income','balance','cashflow','ratio'
  unit_type    text not null default 'currency',  -- 'currency','count','ratio','percent'
  sign_convention text
);

create table concept_mappings (
  source_id     smallint not null references data_sources(id),
  source_label  text not null,               -- 'totalRevenue' (yfinance),
                                             -- 'ifrs-full:Revenue' (ESEF)
  concept_code  text not null references financial_concepts(code),
  primary key (source_id, source_label)
);

create table financial_facts (
  id             bigint generated always as identity primary key,
  instrument_id  bigint not null references instruments(id),
  concept_code   text not null references financial_concepts(code),
  period_end     date not null,
  period_type    text not null,              -- 'FY','H1','Q1'...,'instant'
  value          double precision not null,
  currency       char(3) references currencies(code),
  published_at   date,                       -- bitemporalité (P2)
  report_id      bigint references financial_reports(id),
  source_id      smallint not null references data_sources(id),
  confidence     double precision,           -- utile pour l'extraction LLM
  ingested_at    timestamptz not null default now(),
  constraint fact_unique unique (instrument_id, concept_code, period_end, period_type, source_id)
);

create index on financial_facts (instrument_id, concept_code, period_end desc);
```

**Pourquoi EAV plutôt qu'une table large.** Trois sources hétérogènes doivent cohabiter : yfinance avec ses libellés propres, le XBRL/ESEF avec la taxonomie IFRS (plusieurs milliers de concepts), et l'extraction LLM de PDF avec ce qu'on lui demande. Une table à colonnes fixes exigerait une migration à chaque nouveau concept. Le volume ne justifie pas l'optimisation inverse : 250 titres × 5 ans × 4 périodes × 50 concepts ≈ 250 k lignes, soit ~25 Mo.

**`confidence` prépare la phase 2.** Une valeur extraite d'un PDF par LLM n'a pas le même statut qu'une valeur XBRL. Le champ existe dès maintenant pour que la distinction soit lisible partout et ne se perde pas dans l'agrégation.

---

## 6. Couche dérivée

### 6.1 Politiques de régression - le principe P6 matérialisé

```sql
create table regression_policies (
  code            text primary key,          -- 'loglin_20y','loglin_30y','real_deflated','excluded'
  label           text not null,
  model           text not null,             -- 'log_linear','log_log','real_deflated','none'
  window_years    smallint,
  min_years       smallint not null default 15,
  bar_freq        text not null default '1w',
  min_observations integer not null default 500,
  requires_stationarity_test boolean not null default true,
  notes           text
);

insert into regression_policies
  (code, label, model, window_years, min_years, bar_freq, notes) values
  ('loglin_20y', 'Log-linéaire 20 ans', 'log_linear', 20, 15, '1w',
   'Défaut actions. Marie de Raismes utilise 20 ans pour les sociétés.'),
  ('loglin_30y', 'Log-linéaire 30 ans', 'log_linear', 30, 20, '1w',
   'Indices et ETF, depuis un régime monétaire homogène.'),
  ('real_deflated', 'Tendance réelle déflatée', 'real_deflated', 50, 30, '1mo',
   'Matières premières. La tendance nominale est dominée par l''inflation.'),
  ('excluded', 'Hors modèle', 'none', null, null, '1d',
   'Crypto et FX. Régime non stationnaire, pente dépendante de la date de départ.');
```

**Résolution de la politique applicable :** `instruments.policy_code` s'il est renseigné, sinon `asset_classes.default_policy_code`. Une exception par titre est ainsi possible sans toucher au code - par exemple passer une banque en 30 ans, comme le recommande Hiboo.

### 6.2 Ajustements de cours

```sql
create table adjustment_factors (
  instrument_id  bigint not null references instruments(id),
  ts             date not null,
  factor_price   double precision not null default 1.0,   -- cumul splits
  factor_total   double precision not null default 1.0,   -- cumul splits + dividendes réinvestis
  computed_at    timestamptz not null default now(),
  method_version smallint not null default 1,
  primary key (instrument_id, ts)
);
```

*Table dérivée, entièrement reconstructible depuis `corporate_actions`. `method_version` permet de changer la convention d'ajustement et de comparer, sans perdre l'ancienne.*

**Décision à challenger :** la régression doit-elle porter sur le cours ajusté des seuls splits, ou sur le rendement total dividendes réinvestis ? Hiboo semble utiliser le cours simple. Le rendement total est plus juste économiquement mais rend la comparaison avec leurs graphes impossible. *Proposition : calculer les deux, afficher le cours simple par défaut, garder le total pour la mesure de performance.*

### 6.3 La table centrale du système : `regression_fits`

```sql
create table regression_fits (
  id              bigint generated always as identity primary key,
  instrument_id   bigint not null references instruments(id),
  policy_code     text not null references regression_policies(code),
  as_of_date      date not null,             -- ⚠ LA DATE DE CALCUL - cœur du principe P5

  -- fenêtre effectivement utilisée
  window_start    date not null,
  window_end      date not null,
  n_obs           integer not null,

  -- paramètres du modèle
  slope_annual    double precision not null, -- rendement annualisé implicite de la tendance
  intercept       double precision not null,
  sigma_resid     double precision not null,
  r_squared       double precision,

  -- position courante
  last_close      double precision not null,
  fitted_value    double precision not null,
  residual        double precision not null,
  z_score         double precision not null, -- residual / sigma_resid

  -- diagnostics de validité
  adf_stat        double precision,
  adf_pvalue      double precision,
  dfgls_stat      double precision,
  kpss_stat       double precision,
  durbin_watson   double precision,
  half_life_days  double precision,          -- vitesse de retour, modèle OU
  ar1_ci_low      double precision,          -- IC sur la racine AR dominante
  ar1_ci_high     double precision,

  -- verdict
  fit_quality     text not null,             -- 'good','weak','rejected'
  quality_reasons text[],                    -- ['non_stationary','dilution_detected','short_history']

  method_version  smallint not null default 1,
  computed_at     timestamptz not null default now(),
  constraint fit_unique unique (instrument_id, policy_code, as_of_date, method_version)
);

create index on regression_fits (as_of_date desc, z_score);
create index on regression_fits (instrument_id, as_of_date desc);
```

**C'est la table qui justifie à elle seule cette architecture.**

`as_of_date` signifie que chaque ligne est un cliché de ce que le modèle affirmait à cette date, avec les seules données disponibles à cette date. On l'écrit chaque semaine et on ne la réécrit jamais.

Conséquence : au bout de 12 mois, 52 observations réellement hors échantillon. Au bout de 36 mois, un jeu de données que ni Hiboo ni personne ne publie - le comportement effectif des titres après un signal à -2σ, mesuré en temps réel, sans possibilité de look-ahead.

Coût aujourd'hui : environ 13 000 lignes par an, soit quelques mégaoctets. Coût si on l'ajoute dans deux ans : l'information n'existera pas, elle n'est pas reconstituable.

`ar1_ci_low`/`ar1_ci_high` plutôt qu'un booléen "stationnaire". Les tests ADF et KPSS n'ont quasi aucune puissance sur 20 ans - c'est l'argument Shiller-Perron. Un verdict binaire donnerait une fausse certitude ; un intervalle de confiance sur la racine autorégressive dit la vérité, à savoir qu'on ne sait souvent pas trancher.

### 6.4 Couche qualité - groupes de pairs, scores et évaluations

*Spécification fonctionnelle complète dans le doc 08. Ici, le schéma.*

```sql
-- Un groupe de pairs peut être automatique (sectoriel) ou manuel (le bon)
create table peer_groups (
  id            bigint generated always as identity primary key,
  code          text not null unique,
  label         text not null,
  kind          text not null,             -- 'sector_auto' | 'manual'
  sector_code   text references sectors(code),
  is_complete   boolean not null default false,  -- au moins un pair hors Europe
  notes         text,
  created_at    timestamptz not null default now()
);

create table peer_group_members (
  peer_group_id bigint not null references peer_groups(id) on delete cascade,
  instrument_id bigint references instruments(id),  -- null si hors univers
  external_name text,                       -- 'Shark Ninja', 'BYD', 'Revolut'
  external_ref  jsonb,                      -- ticker, pays, CA saisi à la main
  is_in_universe boolean not null default true,
  valid_from    date not null default current_date,
  valid_to      date not null default '9999-12-31',
  primary key (peer_group_id, coalesce(instrument_id, 0), coalesce(external_name, ''))
);
```

**`external_name` et `is_in_universe` traitent la limite la plus dangereuse du système** (doc 08 §7, L1) : les menaces concurrentielles réelles viennent presque toujours de l'extérieur de l'univers. Shark Ninja est américaine, BYD est chinoise, Revolut n'est pas cotée. Un groupe de pairs purement européen est structurellement aveugle, et `is_complete` le signale.

```sql
-- Score de qualité, historisé au même titre que regression_fits
create table quality_scores (
  id                bigint generated always as identity primary key,
  instrument_id     bigint not null references instruments(id),
  as_of_date        date not null,          -- ⚠ historisé (principe P5, appliqué à la qualité)
  peer_group_id     bigint references peer_groups(id),

  -- Q1 : leadership
  relative_share    double precision,       -- CA / CA du plus grand pair
  rank_by_revenue   integer,
  rank_stability_5y double precision,
  foreign_revenue_pct double precision,

  -- Q2 : rente
  roic_latest       double precision,
  roic_mean_5y      double precision,
  roic_volatility   double precision,
  roic_vs_threshold double precision,       -- écart au seuil absolu (8%)
  roic_vs_peers     double precision,       -- écart à la médiane du groupe
  persistence_years smallint,               -- exercices avec ROIC > seuil
  gross_margin_mean double precision,
  gross_margin_std  double precision,

  -- Q3 : érosion
  roic_slope_5y     double precision,
  gross_margin_slope_5y double precision,
  share_slope_5y    double precision,
  erosion_flags     smallint,               -- 0 à 3 pentes négatives significatives

  -- verdicts
  regime            text not null,          -- 'rent','cyclical','eroding','no_moat','unknown'
  quality_tier      text not null,          -- 'solid','watch','eroding','unqualified'
  n_years_available smallint not null,
  confidence        text not null,          -- 'high','medium','low' selon la profondeur dispo

  method_version    smallint not null default 1,
  computed_at       timestamptz not null default now(),
  constraint quality_unique unique (instrument_id, as_of_date, method_version)
);

create index on quality_scores (as_of_date desc, quality_tier);
```

**`as_of_date` ici aussi.** Le principe P5 s'applique à la qualité exactement comme au prix : dans trois ans, on voudra savoir si les titres classés `solid` en 2026 l'étaient encore en 2029. Cette information ne se reconstitue pas.

**`regime` sépare le cyclique du reste, et c'est indispensable.** Arkema, BMW, Benetteau échouent à tous les tests de moat classiques et sont pourtant des cibles légitimes - Marie les recommande explicitement. Un cyclique se juge sur son ROIC **moyen de cycle**, jamais sur le dernier exercice.

```sql
-- Le volet qualitatif : ce qui ne se calcule pas
create table moat_assessments (
  id              bigint generated always as identity primary key,
  instrument_id   bigint not null references instruments(id),
  assessed_at     date not null,
  expires_at      date not null,            -- assessed_at + 18 mois
  moat_sources    text[],                   -- 'brand','patent','switching','network','cost','scale'
  position_verdict text not null,           -- 'leader','challenger','follower','niche'
  durability_verdict text not null,         -- 'solid','watch','eroding','none'
  threats         jsonb,                    -- [{"threat":"...", "horizon":"3-5y", "source":"..."}]
  peer_group_id   bigint references peer_groups(id),
  rationale       text not null,
  sources         jsonb,                    -- traçabilité : documents cités
  authored_by     text not null,            -- 'human' | 'llm:<modèle>'
  reviewed_by     text,                     -- ⚠ null = non validé
  confidence      double precision
);

create index on moat_assessments (instrument_id, assessed_at desc);
```

**`expires_at` force la revue.** Les positions concurrentielles bougent lentement mais elles bougent, et une évaluation de 2026 inspire exactement la même confiance qu'une de 2029 - c'est le problème. Au-delà de 18 mois, le titre repasse en `unqualified`.

**`reviewed_by` distinct de `authored_by` est le human in the loop de Dothée, matérialisé.** Une évaluation produite par un LLM et non revue par un humain ne fait jamais passer un titre dans le quadrant cible.

### 6.5 Clichés de screener et qualité de données

```sql
create table screener_snapshots (
  id             bigint generated always as identity primary key,
  run_date       date not null,
  instrument_id  bigint not null references instruments(id),
  fit_id         bigint references regression_fits(id),
  quality_score_id bigint references quality_scores(id),
  z_score        double precision not null,
  rank_overall   integer,
  rank_in_sector integer,
  entered_at     date,                       -- première apparition sous le seuil
  consecutive_weeks integer default 1,       -- persistance du signal
  fundamentals_ok boolean,
  quality_tier   text,                       -- repris de quality_scores
  quadrant       text,                       -- 'target','watchlist','value_trap','avoid','unqualified'
  notes          jsonb,
  constraint snapshot_unique unique (run_date, instrument_id)
);

create table data_quality_issues (
  id             bigint generated always as identity primary key,
  instrument_id  bigint references instruments(id),
  detected_at    timestamptz not null default now(),
  issue_type     text not null,   -- 'gap','outlier_jump','stale_series','currency_mismatch',
                                  -- 'dilution','split_unadjusted','fx_missing','source_divergence'
  severity       text not null,   -- 'info','warning','blocking'
  ts_from        date,
  ts_to          date,
  details        jsonb,
  resolved_at    timestamptz,
  resolution     text
);
```

*`consecutive_weeks` répond à un point de l'avis critique : la décote n'est pas un événement mais un régime qui dure. Savoir qu'un titre est sous -2σ depuis 14 semaines est une information différente de sa première semaine, et c'est la brique de la distribution des temps de premier passage.*

### 6.5 Journal d'ingestion

```sql
create table ingestion_runs (
  id             bigint generated always as identity primary key,
  source_id      smallint not null references data_sources(id),
  job_name       text not null,
  started_at     timestamptz not null default now(),
  finished_at    timestamptz,
  status         text not null default 'running',  -- 'running','success','partial','failed'
  rows_inserted  integer default 0,
  rows_updated   integer default 0,
  rows_rejected  integer default 0,
  error_message  text,
  details        jsonb
);
```

---

## 7. Portefeuille personnel (optionnel, mais recommandé dès la v1)

```sql
create table positions (
  id             bigint generated always as identity primary key,
  instrument_id  bigint not null references instruments(id),
  account        text not null,              -- 'PEA_CM', 'CTO', 'etoro'
  opened_at      date not null,
  closed_at      date,
  quantity       double precision not null,
  avg_price      double precision not null,
  currency       char(3) not null,
  thesis         text,                       -- pourquoi tu l'as acheté, écrit AVANT
  z_at_entry     double precision,
  notes          jsonb
);
```

**`thesis` et `z_at_entry` sont plus importants qu'ils n'en ont l'air.** Écrire la thèse au moment de l'achat et la relire deux ans plus tard est le seul antidote fiable au biais rétrospectif - on reconstruit spontanément une justification de ce qu'on a fait. C'est exactement l'usage que Dothée décrit dans le second podcast, et c'est aussi la matière première de l'agent avocat du diable en phase 2.

---

## 8. Volumétrie récapitulative - univers v1

| Table | Lignes estimées | Volume |
|---|---:|---:|
| `bars_1w` (30 ans) | 390 000 | ~45 Mo |
| `bars_1d` (3 ans) | 189 000 | ~22 Mo |
| `financial_facts` | 250 000 | ~25 Mo |
| `corporate_actions` | 15 000 | ~2 Mo |
| `regression_fits` (an 1) | 13 000 | ~3 Mo |
| `quality_scores` (an 1, trimestriel) | 1 000 | < 1 Mo |
| `peer_groups` + membres | 2 000 | < 1 Mo |
| `moat_assessments` | 300 | < 1 Mo |
| `fx_rates` | 60 000 | ~5 Mo |
| Référentiel et divers | — | ~5 Mo |
| **Total** | | **~110 Mo** |

*La couche qualité ne pèse quasiment rien : elle est trimestrielle et porte sur 250 lignes. C'est le prix le plus bas du système pour la moitié de sa valeur.*

Sur 500 Mo disponibles en Supabase free. Marge confortable, y compris pour trois ans d'historisation des fits.

---

## À challenger en priorité

1. **Le modèle EAV pour les fondamentaux.** Il est flexible mais les requêtes sont plus lourdes à écrire qu'avec une table large. Alternative : table large avec 40 colonnes fixes + JSONB pour le reste. Plus simple à requêter, moins souple. Je penche pour l'EAV parce que trois sources hétérogènes doivent cohabiter, mais l'argument inverse est recevable.
2. **Cours brut plutôt qu'ajusté.** C'est plus de travail au calcul. Je considère ce point comme non négociable, mais autant que ce soit explicite.
3. **`regression_fits` historisée dès le jour 1.** C'est ma recommandation la plus forte de tout le document. Si tu ne devais retenir qu'une chose du modèle, ce serait ce champ `as_of_date`.
4. **Le seuil de détection de dilution à +50% sur 12 mois** est arbitraire. À calibrer sur des cas réels - Atos, Casino, Solocal fournissent des exemples propres.
5. **Régression en devise locale.** Défendable, mais ça complique la comparaison entre titres de zones différentes.
