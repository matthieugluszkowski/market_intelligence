# market_intelligence

Couche data pour un screener de décote multi-actifs : régression log-linéaire sur
30 ans (la « droite de Hiboo ») **et** évaluation de position concurrentielle. Les
deux jambes sont d'égale importance — un système qui ne traiterait que le prix
produirait des value traps avec une belle courbe.

Spécification complète dans les documents à la racine. **Ordre de lecture :**
`07` (expression de besoin) → `00` (vue d'ensemble) → `08` (jambe qualité) →
`03` (jambe prix) → `01` (modèle de données) → `02` (ingestion) → `04` (screener)
→ `05` (roadmap) → `06` (points ouverts).

## État d'avancement

| Lot | Contenu | Statut |
|---|---|---|
| **L0** | Socle : dépôt, env Python, DDL, seeds, keepalive | **fait** |
| **L1** | Référentiel de l'univers — 57 titres vérifiés | **fait** |
| **L2** | Ingestion des cours, archive Parquet, journal | **fait** |
| **L3** | Corporate actions, facteurs, 9 contrôles qualité | **fait** |
| L4 | Moteur analytique (régression, diagnostics) | à faire |
| L5 | Screener et fiche instrument (Streamlit) | à faire |
| L6 / L6b | Fondamentaux régime A / couche qualité | à faire |
| L7 | Orchestration et rapport hebdomadaire | à faire |

Détail et critères d'acceptation : `05_roadmap-et-lot.md`.

## Démarrage

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e ".[dev]"   # Windows
cp .env.example .env                                   # puis renseigner
.venv/Scripts/python.exe scripts/migrate.py
.venv/Scripts/python.exe -m pytest tests/ -q
```

## Structure

```
db/migrations/     DDL versionné, appliqué une seule fois (table schema_migrations)
db/seeds/          référentiel, rejouable (on conflict do update)
src/market_intelligence/
  config.py        configuration lue depuis .env
  db.py            connexions pooler transaction / session
  collectors/      un module par source, récupère du brut et rien d'autre
  normalizers/     brut -> schéma canonique, aucune logique métier
  validators/      contrôles qualité, produit des data_quality_issues
  loaders/         écriture idempotente
  jobs/            orchestration
  analytics/       régression, diagnostics, scores de qualité
scripts/           migrate.py, keepalive.py
data/parquet/      couche froide (non versionnée)
```

## Base de données

Supabase free tier, **Postgres strictement standard** — aucune fonctionnalité
propriétaire dans le schéma, pour que la migration vers un VPS reste un
`pg_dump | psql` et pas un chantier.

Deux connexions, et la distinction compte :

| Variable | Port | Usage |
|---|---|---|
| `DATABASE_URL` | 6543 | pooler transaction (pgbouncer) — requêtes applicatives |
| `DIRECT_URL` | 5432 | pooler session — DDL, migrations, transactions longues |

`db.py` retire de l'URL les paramètres que Supabase destine à Prisma
(`pgbouncer=true`…) et que libpq rejette : le `.env` reste copiable tel quel
depuis le dashboard.

### Migrations

Un fichier de `db/migrations/` n'est joué qu'une fois ; son empreinte est
enregistrée. **Modifier une migration déjà appliquée ne la rejoue pas** — le
script signale la divergence et il faut créer une nouvelle migration.

```bash
python scripts/migrate.py             # migrations + seeds
python scripts/migrate.py --status    # état et volumétrie
```

### Keepalive

Le free tier met le projet en pause après 7 jours sans requête. `scripts/keepalive.py`
touche une table triviale, **indépendamment du pipeline principal** : si
l'ingestion casse, le ping doit continuer. Code de sortie 1 en cas d'échec, pour
qu'un cron puisse alerter.

Déployé sur le VPS Lightsail (`ubuntu@3.249.92.28`), dans
`/opt/market_intelligence`, crontab de l'utilisateur `ubuntu` :

```cron
17 6 * * * cd /opt/market_intelligence && .venv/bin/python scripts/keepalive.py >> logs/keepalive.log 2>&1
```

Le `.env` du VPS est une copie locale en `chmod 600`, hors dépôt. Après une
modification de configuration, le redéployer explicitement — il ne suit pas le
`git pull`.

## Référentiel de l'univers (L1)

57 titres de la zone euro éligibles PEA : FR 29, DE 10, NL 8, ES 4, BE 3, IT 3.
Y compris les cas de test cités par la spec — Seb, Arkema, BMW.

```bash
python scripts/verify_universe.py    # vérifie, écrit le rapport
python scripts/load_universe.py      # charge ce qui est vérifié, et rien d'autre
```

Trois contrôles indépendants, parce qu'**un mapping faux ne se voit jamais
ensuite** — il produit une belle courbe pour la mauvaise société :

1. clé de contrôle ISIN (Luhn mod 10) ;
2. téléchargement d'une cotation réelle, avec profondeur d'historique ;
3. concordance de la devise et de la raison sociale rapportées par le provider.

Le contrôle 3 est celui qui attrape le cas du podcast : la similarité entre
« SEB » et « Skandinaviska Enskilda Banken » est de 0.19, très en dessous du
seuil. Un symbole qui échoue n'entre pas en base — il est écarté avec son motif.

### Deux constats sur les sources, qui contredisent le doc 02

**Stooq n'est plus utilisable en primaire.** Le doc 02 §2.1 le retient parce
qu'il « sert des CSV bruts par simple URL, sans dépendance à une bibliothèque
qui casse ». Ce n'est plus vrai : l'endpoint `/q/d/l/` renvoie désormais une page
de vérification navigateur à preuve de travail JavaScript — constaté depuis le
poste de travail comme depuis le VPS. Les symboles Stooq sont conservés dans
`db/seeds/universe_50.csv` et dans `instruments.attributes`, mais **non vérifiés
et non chargés dans `instrument_symbols`**. yfinance assure seul la vérification
L1, et doit être considéré comme source primaire de cours pour L2 tant que
l'accès Stooq n'est pas rétabli — ce qui contredit le principe « aucune source ne
doit être un point de défaillance unique » et reste à arbitrer.

**Deux valeurs de Madrid ont un historique tronqué chez yfinance.** Banco
Santander et Amadeus ne renvoient que 3 barres hebdomadaires, alors qu'Iberdrola,
Inditex et Telefónica sur le même marché en renvoient 26 ans. Elles sont dans le
CSV, écartées du chargement, en attente d'une seconde source. Le seuil est
volontairement dur : sous un an d'historique, ce n'est pas une jeune société,
c'est un flux cassé, et charger la ligne donnerait une régression sur trois
points.

## Ingestion des cours (L2)

```bash
python scripts/backfill_prices.py     # hebdo sur tout l'historique + quotidien 3 ans
python scripts/export_cold.py         # archive Parquet de la couche froide
```

Pipeline en quatre étages étanches (doc 02 §4.1) : le collecteur ne valide ni ne
transforme rien, le normaliseur ne parle pas à la base, le chargeur ne fait
qu'écrire, le job orchestre et journalise. On peut ainsi rejouer la normalisation
sans retélécharger.

Le chargement passe par une table de transit alimentée en `COPY` puis un seul
`insert … select`. Ligne à ligne, les ~120 000 barres de l'univers coûteraient
autant d'allers-retours vers Supabase, soit des heures.

### L'écart au principe P4, et pourquoi il est acceptable

P4 exige le cours **non ajusté**. Yahoo ne le sert pas : sa colonne `Close` est
rétro-ajustée des splits — Dassault Systèmes cotait ~133 € en juin 2019, l'API
renvoie 26,70 €, soit divisé par le 5:1 de juillet 2021. Le cours nominal
d'époque n'est disponible chez aucune source gratuite.

On stocke donc `Close`, jamais `Adj Close`. Ce n'est pas une commodité : ce que
P4 protège, c'est la reproductibilité, et les deux colonnes s'y comportent de
façon opposée.

| | change quand | fréquence |
|---|---|---|
| `Adj Close` | à chaque détachement de dividende | plusieurs fois par an |
| `Close` | aux splits seulement | 2 fois en 12 ans sur Dassault |

Le prix à payer reste réel et doit rester visible : les splits antérieurs à la
première ingestion sont déjà incorporés, `adjustment_factors` ne les rejouera
pas, et la comparaison au graphe d'un fournisseur affichant le nominal sera
décalée d'un facteur constant.

**Le garde-fou.** Le `DO UPDATE` porte un `WHERE` : une barre identique n'est pas
réécrite. Ce qui est compté comme *révision* est donc exactement une valeur qui a
changé. Le jour où une société annonce un split, toute sa série se décale d'un
coup ; au-delà de 5 % des barres révisées, le chargeur inscrit un
`split_unadjusted` dans `data_quality_issues`. Sans ce contrôle, un rechargement
écraserait dix ans de cotations en silence et la régression changerait sans
explication.

*Note d'implémentation :* on aurait préféré `returning (xmax = 0)` en une passe,
mais Postgres refuse de lire une colonne système dans le `RETURNING` d'un
`INSERT` sur table partitionnée — et `bars` l'est par fréquence. Le comptage se
fait donc par jointure avant écriture, pour un aller-retour de plus.

### Débit et reprise

Yahoo rate-limite le backfill — risque noté comme élevé au doc 05 §4 — et le fait
en renvoyant un DataFrame **vide** plutôt qu'une erreur franche. Une réponse vide
est donc traitée comme un échec temporaire, avec reprise à attente croissante.
Sans cela, un titre refusé serait enregistré comme dépourvu d'historique, et L4
le classerait `rejected` à tort.

## Corporate actions et qualité (L3)

```bash
python scripts/ingest_corporate_actions.py   # splits, dividendes, nb d'actions, facteurs
python scripts/quality_checks.py             # les 9 contrôles du doc 02 §5
```

### Les deux facteurs d'ajustement, et pourquoi ils diffèrent

`factor_price` vaut **1.0 partout**, et ce n'est pas un oubli. Le cours servi par
Yahoo est déjà rétro-ajusté des splits ; appliquer en plus les ratios de
`corporate_actions` diviserait la série une seconde fois. Air Liquide, qui
distribue une action gratuite pour dix tous les deux ans, verrait son historique
divisé par 1,1 à chaque opération, deux fois. **C'est le type d'erreur qui ne se
voit pas** — la courbe reste lisse, seule la pente est fausse.

`factor_total` est calculé, lui, puisque les dividendes ne sont pas incorporés :

```
factor_total(t) = ∏ sur les dividendes d'ex-date > t de (1 − D / C_veille)
```

**La convention est vérifiée, pas supposée.** Appliqué au `Close` de Yahoo, le
facteur doit redonner son `Adj Close`. Mesuré sur Air Liquide, 1 390 barres :
écart médian **0,036 %**, exact sur les dates récentes, maximum 3,9 % sur une
semaine de détachement de 2009. Ce résidu vient de la granularité : sur barre
hebdomadaire, « la veille » du détachement est la clôture de la semaine
précédente. Le quotidien sert donc de référence là où il existe.

On aurait pu supprimer le résidu en téléchargeant 30 ans de quotidien à chaque
calcul, mais les facteurs cesseraient d'être reconstructibles depuis les seules
tables `raw` — ce qui viole P1. L'approximation est le prix de ce principe, et
elle est mesurée.

### Les neuf contrôles

Par ordre de valeur décroissante (doc 02 §5). Aucun ne supprime de donnée :
quarantaine plutôt que rejet.

| Contrôle | Détection | Sévérité |
|---|---|---|
| Saut de cours inexpliqué | > 25 % en une séance sans opération connue | bloquant |
| Série figée | cours identique > 5 séances | avertissement |
| Trou de cotation | > 5 jours ouvrés sans donnée | avertissement |
| **Dilution** | nombre d'actions +50 % sur 12 mois glissants | bloquant |
| Divergence inter-sources | écart > 1 % entre deux sources | avertissement |
| Incohérence de devise | devise du titre ≠ devise du marché | bloquant |
| Historique insuffisant | < `min_years` de la politique applicable | exclusion |
| FX manquant | pas de taux pour une devise à une date | avertissement |
| Identité comptable | actif ≠ passif + capitaux propres | avertissement |

Le job **purge les anomalies non résolues avant recalcul**. Sans cela la même
anomalie s'empile à chaque exécution et le tableau de bord devient illisible en
trois semaines. Les anomalies résolues à la main sont conservées : c'est la trace
du diagnostic.

**Le filtre de dilution est le plus rentable des neuf, et il ne figure dans aucun
screener grand public.** Atos, Casino, emeis, Solocal sont toujours cotés : ils ne
sortent pas par le filtre « radiation ». Mais après une dilution d'un facteur
cent, leur cours ajusté rend la droite de régression absurde — le titre apparaît
massivement décoté alors que la valeur par action a été détruite.

### Deux contrôles que l'univers actuel ne peut pas éprouver

- **Divergence inter-sources.** Impossible : Stooq est inaccessible, yfinance est
  seul. La requête est écrite pour fonctionner dès qu'une seconde source
  alimentera `bars` ; en attendant elle ne trouve rien, et c'est exactement le
  risque à garder sous les yeux — *une source unique donne une confiance
  illusoire*.
- **Dilution sur un cas réel.** Atos et Casino ne sont pas dans les 57. Le calcul
  est donc éprouvé sur données synthétiques, où la réponse est connue, plutôt que
  sur un titre réel où l'on ne ferait que constater.

## Principes non négociables

Détaillés dans `00_vue-densemble.md §3`. Les trois qui se paient le plus cher si
on les oublie :

- **P4 — `bars.close` est le cours brut.** Jamais l'`adj_close` d'un provider :
  Yahoo le recalcule rétroactivement à chaque dividende, et un backtest lancé en
  janvier ne donne plus le même résultat en juin. On ajuste au calcul, via
  `corporate_actions`.
- **P5 — `regression_fits.as_of_date`.** Les paramètres de chaque régression sont
  historisés chaque semaine et jamais réécrits. Au bout de 12 mois : 52
  observations réellement hors échantillon. Cette information ne se reconstitue
  pas rétroactivement.
- **P2 — bitemporalité.** Chaque fait porte la date à laquelle il se rapporte et
  la date à laquelle on l'a su. Sans ça le look-ahead bias est structurel.

## Sécurité

`.env` et `*.pem` sont dans `.gitignore`. Aucun secret ne doit apparaître dans un
commit, un log ou un message d'erreur.
