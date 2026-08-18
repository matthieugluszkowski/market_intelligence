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
| L1 | Référentiel de l'univers (~50 titres puis 250) | à faire |
| L2 | Ingestion des cours (Stooq) | à faire |
| L3 | Corporate actions et contrôles qualité | à faire |
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
