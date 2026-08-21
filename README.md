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
| **L1** | Référentiel de l'univers — 586 titres vérifiés | **fait** |
| **L2** | Ingestion des cours, archive Parquet, journal | **fait** |
| **L3** | Corporate actions, facteurs, 9 contrôles qualité | **fait** |
| **L4** | Moteur analytique, diagnostics, `regression_fits` | **fait** |
| **L5** | Screener et fiche instrument (Streamlit) | **fait** |
| **L6** | Fondamentaux régime A, ratios, bloc E | **fait** (hors parseur ESEF) |
| **L6b** | Couche qualité, matrice qualité × prix | **fait** |
| **Watchlist** | Suivre des titres — doc 10 | **fait** |
| **L7** | Orchestration — cycle automatique toutes les 8 h | **fait** (rapport hebdomadaire : à faire) |
| **L8** | Portefeuille et paper trading — doc 11 | **fait** |

Détail et critères d'acceptation : `05_roadmap-et-lot.md`.

## Lancer le dashboard

La base est peuplée : il n'y a rien à recalculer pour consulter le système.

```bash
.venv/Scripts/python.exe -m streamlit run dashboard/Screener.py
```

→ **http://localhost:8501**, six écrans dans la barre latérale : screener,
fiche instrument, matrice qualité × prix, dossier concurrentiel, watchlist,
portefeuille.

### Le rechargement du code, et le piège qu'il supprime

Streamlit relance le script à chaque interaction mais **garde les modules
importés en cache**. Une fonction ajoutée à `dashboard/data.py` ou une constante
ajoutée à `intelligence/schema.py` restait donc invisible, et l'écran tombait en
`AttributeError` sur un attribut pourtant présent dans le fichier — le message
désignant le fichier, il oriente le diagnostic vers le code alors que le code est
correct.

Le piège s'est produit deux fois : sur `data.qualite`, puis sur
`schema.FRAGMENTS`.

`runOnSave = true` **ne suffit pas** : le surveillant de Streamlit ne couvre pas
de façon fiable les modules dont le chemin est ajouté à `sys.path` à l'exécution
— c'est le cas de `src/` ici — et le dossier est synchronisé par OneDrive, dont
la virtualisation rend les événements de système de fichiers irréguliers.
Vérifié : avec `runOnSave` seul, une constante modifiée restait invisible.

`dashboard/rechargement.py` calcule donc l'empreinte des sources du projet et
**purge `sys.modules`** quand elle change, avant les imports de chaque page. Deux
précautions : rien n'est purgé quand rien n'a changé — c'est ce qui préserve les
caches `st.cache_data` dans le cas courant — et la purge précède les imports,
sinon deux versions d'une même classe coexisteraient et un `isinstance`
échouerait sans raison visible.

Vérifié de bout en bout : une constante modifiée pendant que le serveur tourne
est prise en compte au rafraîchissement suivant, sans redémarrage.

**Par où commencer pour juger si le système dit vrai :**

| Écran | Ce qu'il faut y regarder |
|---|---|
| Fiche → **Seb** | z = −2,16, sous −2σ depuis 46 semaines — le plus long épisode observé sur ce titre |
| Fiche → **LVMH**, bloc D | le seul value trap, avec ses trois pentes affichées séparément |
| Fiche → **BMW** | titre sans split : c'est le graphe à superposer à Hiboo |
| Matrice | quadrant CIBLE vide, et le bandeau qui dit pourquoi |

## Installation depuis zéro

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e ".[dashboard,dev]"   # Windows
cp .env.example .env                                            # puis renseigner
.venv/Scripts/python.exe scripts/migrate.py
.venv/Scripts/python.exe -m pytest tests/ -q
```

## Reconstruire la base, dans l'ordre

Les dépendances entre jobs sont réelles : les facteurs d'ajustement ont besoin
des dividendes, les régressions ont besoin des barres et des anomalies, la
qualité a besoin des fondamentaux. Cet ordre est le seul qui fonctionne.

```bash
python scripts/migrate.py                    # schéma + seeds       instantané
python scripts/verify_universe.py            # vérifie les 57       ~3 min
python scripts/load_universe.py              # charge le vérifié    instantané
python scripts/backfill_prices.py            # 122 000 barres       ~6 min
python scripts/ingest_corporate_actions.py   # + facteurs           ~7 min
python scripts/ingest_fundamentals.py        # 7 000 faits          ~7 min
python scripts/quality_checks.py             # 9 contrôles          ~10 s
python scripts/compute_fits.py               # 57 régressions       ~2 min
python scripts/compute_quality.py            # 57 scores qualité    ~30 s
python scripts/export_cold.py                # archive Parquet      ~20 s
```

Tous sont **idempotents** : les relancer ne produit ni doublon ni écrasement.
Le temps est dominé par le débit ménagé vers yfinance, pas par le calcul.

## Cycle courant

**Il n'y a plus de séquence à lancer à la main.** Le cycle tourne tout seul sur
le VPS toutes les 8 heures (§ *Déploiement sur le VPS*), derrière un point
d'entrée unique :

```bash
python scripts/cycle.py                  # ce que le cron lance
python scripts/cycle.py --plan           # ce qui tournerait maintenant, sans rien lancer
python scripts/cycle.py --force          # ignorer les cadences, après une panne
python scripts/cycle.py --only compute_fits
```

Toutes les étapes ne se paient pas le même prix, donc **chacune porte sa
cadence** ; le cycle relit `ingestion_runs` pour savoir ce qui a vieilli et ne
relance que ça.

| Étape | Cadence | Durée | Pourquoi cette cadence |
|---|---|---|---|
| `backfill_prices` | chaque passage | ~6 min | une séance de plus, des barres de plus |
| `quality_checks` | chaque passage | ~10 s | dix secondes : aucune raison de s'en priver |
| `compute_fits` | chaque passage | ~2 min | c'est lui, et lui seul, qui fait bouger le screener |
| `ingest_corporate_actions` | 1 jour | ~7 min | quelques dividendes par an et par titre |
| `ingest_fundamentals` | 30 jours | ~7 min | des comptes publiés quatre fois par an |
| `compute_quality` | 30 jours | ~30 s | suit les comptes, pas les cours |

Deux règles portent le reste du comportement :

- **Une étape qui échoue n'interrompt pas le cycle.** Les suivantes tournent, et
  le code de sortie vaut 1 pour qu'un cron puisse alerter.
- **Sauf si elles en dépendent.** `compute_fits` dépend de `backfill_prices` :
  si l'ingestion des cours échoue, le calcul est *sauté* plutôt qu'historiser
  une observation du jour sur des cours qu'on sait périmés. `regression_fits` ne
  se rejoue jamais, une observation fausse y reste fausse.

### Ce que P5 devient avec un cycle de 8 heures

`compute_fits` écrit **une ligne par jour et par titre**, et son conflit sur
`as_of_date` se résout désormais en mise à jour : dans la journée, le passage de
16 h remplace celui de 8 h — sans quoi il calculerait deux minutes pour n'écrire
rien, et le screener afficherait les z-scores du matin en les datant de
l'après-midi. **Dès que le jour est passé, la ligne est figée pour toujours.**

L'observation historisée est donc le dernier état connu du jour, jamais un
mélange, et jamais une réécriture rétrospective. La série hebdomadaire du
principe P5 reste extractible telle quelle (`where extract(dow from as_of_date)
= 0`), avec cette différence qu'aucune semaine ne peut plus être manquée.

## Vérifications

```bash
python scripts/verify_ratios.py                    # recoupe les ratios
python scripts/export_comparaison.py EQ:DE:BMW     # série exacte pour Hiboo
python scripts/migrate.py --status                 # volumétrie de toutes les tables
python -m pytest tests/ -q                         # 169 tests
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
scripts/           cycle.py (le cron), migrate.py, keepalive.py, et une enveloppe par job
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

Déployé sur le VPS avec le reste (§ *Déploiement sur le VPS*), et
**volontairement indépendant du cycle** : si l'ingestion casse, le ping doit
continuer, sinon la base se met en pause et il faut la réactiver à la main.

## Déploiement sur le VPS

VPS Lightsail, `/opt/market_intelligence`, clone git de ce dépôt. Déployer une
nouvelle version, c'est un `git pull` :

```bash
cd /opt/market_intelligence && git pull && .venv/bin/python -m pytest tests/ -q
```

Deux crons pour l'utilisateur `ubuntu`, et ils ne se ressemblent pas :

```cron
17 6 * * *   cd /opt/market_intelligence && .venv/bin/python scripts/keepalive.py >> logs/keepalive.log 2>&1
0  */8 * * * cd /opt/market_intelligence && flock -n logs/cycle.lock .venv/bin/python scripts/cycle.py >> logs/cycle-$(date +\%Y\%m).log 2>&1
```

- L'heure du VPS est en **UTC** : les passages tombent à 00 h, 08 h et 16 h UTC,
  soit 02 h, 10 h et 18 h à Paris l'été. Celui de 18 h suit la clôture
  d'Euronext, celui de 02 h suit la clôture américaine.
- `flock -n` empêche deux cycles de se chevaucher si un passage déborde ; sans
  lui, deux `backfill_prices` simultanés doubleraient le débit vers yfinance.
- Le log est **mensuel** (`logs/cycle-202608.log`) : pas de rotation à
  installer, pas de fichier qui grossit indéfiniment. Le `%` doit être échappé
  dans une crontab, d'où `\%Y\%m`.

Le `.env` du VPS est une copie locale en `chmod 600`, **hors dépôt** : après une
modification de configuration, le redéployer explicitement, il ne suit pas le
`git pull`.

Vérifier que le cycle vit :

```bash
crontab -l                                   # les deux lignes sont là
tail -50 logs/cycle-$(date +%Y%m).log        # le dernier passage
.venv/bin/python scripts/cycle.py --plan     # ce que ferait le prochain
```

L'écran screener affiche la même information, en clair et sans SSH : date et
heure du dernier passage, et un avertissement si un passage a été manqué.

## Référentiel de l'univers (L1)

**586 titres** de la zone euro éligibles PEA : FR 138, DE 128, IT 78, ES 62,
NL 39, BE 38, FI 36, AT 26, PT 13, LU 12, IE 9, et sept titres de quatre autres
pays de l'EEE cotés sur ces places. Y compris les cas de test cités par la
spec — Seb, Arkema, BMW.

**Deux populations, qui ne se valent pas et ne doivent pas se confondre.**
59 titres saisis et vérifiés à la main, ISIN renseigné, identité recoupée par
trois contrôles indépendants. **527 issus du screener Yahoo** (§ suivant), sans
ISIN et dont l'identité repose sur une source unique. En base,
`instruments.attributes->>'notes'` les distingue.

```bash
python scripts/propose_universe.py   # propose des candidats, n'écrit qu'un CSV
python scripts/verify_universe.py    # vérifie, écrit le rapport
python scripts/load_universe.py      # charge ce qui est vérifié, et rien d'autre
```

### Élargir l'univers, sans le remplir de valeurs américaines

`propose_universe.py` interroge le screener Yahoo place par place et complète
`db/seeds/universe.csv`. **Il ne charge rien** : les trois contrôles restent le
seul passage vers la base. Trois filtres lui évitent le piège de fond — *Yahoo
raisonne en place de cotation, jamais en pays de la société* :

| Filtre | Ce qu'il élimine |
|---|---|
| Place principale | Francfort, Stuttgart, Munich au profit de XETRA seul — et les triplons `NVD.DE` / `NVD.F` / `NVDG.F` |
| Devise de cotation **et** de publication en EUR | Zebra Technologies, qui cote en euros à XETRA et publie en dollars |
| Pays du siège, lu dans `Ticker.info` | tout ce qui n'est pas UE/EEE, donc hors PEA |

Une requête sur la région `de` rend **9 064 lignes**, NVIDIA et Apple en tête.
Après filtrage il reste 115 sociétés allemandes. Les multi-cotations sont
ensuite regroupées par société — 1 350 cotations pour 897 sociétés — et c'est la
cotation du **pays du siège** qui est retenue : une ligne viennoise de valeur
allemande cote peu, cote mal, et donnerait une série trouée là où XETRA en donne
une propre. Si seule une cotation secondaire est trouvée alors que la place du
siège est couverte, la société est écartée plutôt que mal enregistrée.

**L'ISIN de ces lignes reste vide, délibérément.** `Ticker.isin` fait une
recherche par nom et rend le premier homonyme mondial : ISIN canadien pour LVMH,
argentin pour ASML, chilien pour Enel — c'est-à-dire Enel Chile. Un ISIN faux
passe la clé de contrôle Luhn et associerait pour toujours une courbe à la
mauvaise société. `verify_universe` traite donc l'absence d'ISIN en
**avertissement** (`isin_absent`) et un ISIN présent mais faux en **rejet** : un
ISIN absent se voit, un ISIN faux jamais.

Les lignes ainsi proposées portent `notes = "candidat screener yahoo <date>"`,
que `load_universe` recopie dans `instruments.attributes` : les titres vérifiés à
la main et ceux issus du screener restent distinguables en base.

**Et cette distinction n'est pas cosmétique.** Le troisième contrôle L1 —
concordance entre le nom attendu et le nom rapporté — n'a de valeur que si le
nom attendu vient d'une source *indépendante* du fournisseur. Pour les 59 titres
saisis à la main, c'est le cas, et c'est ce contrôle qui attrape Seb contre
Skandinaviska Enskilda Banken. Pour une ligne issue du screener, le nom attendu
**est** celui de Yahoo : la similarité vaut 1.00 par construction et le contrôle
ne prouve plus rien. Ce qui subsiste pour ces lignes, et qui reste solide : la
cotation existe et sa profondeur est mesurée, la devise est cohérente, le pays du
siège a été lu, et la place est celle du siège. Ce qui disparaît : la
confirmation croisée de l'identité par une seconde source. Ces titres se lisent
donc comme un univers de dépistage, pas comme un référentiel audité.

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
`db/seeds/universe.csv` et dans `instruments.attributes`, mais **non vérifiés
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

### Le journal des anomalies : y revenir plus tard

```bash
python scripts/anomalies.py                        # ce qui est ouvert, le plus grave d'abord
python scripts/anomalies.py --detail 287           # une anomalie en entier
python scripts/anomalies.py --resoudre 287 --note "point aberrant du provider"
python scripts/anomalies.py --rouvrir 287          # annuler un acquittement
```

Une première version purgeait les anomalies non résolues avant chaque recalcul,
pour éviter qu'elles ne s'empilent. Le remède coûtait plus cher que le mal : une
anomalie vue en août et toujours présente en octobre perdait sa date de première
détection, et toute note de diagnostic disparaissait au passage suivant. On ne
pouvait donc pas y revenir — ce qui est pourtant tout l'objet d'une liste
d'anomalies.

Chaque anomalie porte maintenant une **empreinte stable** — instrument, type,
périmètre temporel. Un recalcul :

- **revoit** celle qui est toujours là : `last_seen_at` et `run_count` avancent,
  `detected_at` ne bouge pas — c'est l'âge de l'anomalie, et c'est l'information
  qu'on cherche en retrouvant la liste trois semaines plus tard ;
- **clôture** celle qui a disparu, avec la mention, plutôt que de la supprimer ;
- **respecte** un acquittement humain.

**Clôture automatique et acquittement n'ont pas le même sens**, et la distinction
est venue d'un test qui échouait : une anomalie résolue à la main réapparaissait
au recalcul suivant, puisque la condition sous-jacente était toujours vraie. La
liste ne diminuait jamais et la revue manuelle ne servait à rien.

| `resolved_kind` | Sens | Comportement au recalcul |
|---|---|---|
| `auto` | la condition a disparu | se rouvre en cas de récidive |
| `manual` | un humain a regardé et tranché | n'est plus resignalée à l'identique |

L'acquittement porte sur l'empreinte : un événement différent produit une
empreinte différente, donc une nouvelle anomalie. On n'étouffe que ce qui a été vu.

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

## Moteur analytique (L4)

```bash
python scripts/compute_fits.py                     # calcul du jour
python scripts/compute_fits.py --as-of 2024-06-30  # rejouer une date passée
```

Régression `log(P_t) = α + β·t + ε_t` sur fenêtre glissante de 20 ans, barres
hebdomadaires, MCO sans pondération. Chaque exécution **insère** une ligne dans
`regression_fits` et n'en réécrit jamais aucune — c'est le principe P5, et au
bout d'un an il produit 52 observations réellement hors échantillon.

### L'erreur que ce moteur ne commet pas

Le test de racine unitaire porte sur le **log-prix, avec constante et tendance**,
jamais sur les résidus. Un ADF appliqué aux résidus d'une régression aux
coefficients estimés invalide les valeurs critiques et sur-rejette massivement :
on obtiendrait une liste de titres « stationnaires » entièrement fictive, sans
que rien ne le signale. Un test dédié le vérifie en montrant que la version
fautive rejette à tort sur une marche aléatoire (p < 0,05) là où la bonne ne
rejette pas (p > 0,10).

### Résultat sur l'univers : aucun `good`, et c'est le bon résultat

| Verdict | Titres |
|---|---|
| `weak` | 38 |
| `rejected` | 19 (14 non-stationnaires, 3 historiques courts, 2 dilution) |
| `good` | **0** |

Quatre titres seulement rejettent la racine unitaire au seuil brut de 5 % —
Ahold, Getlink, Michelin, Hermès. Sur 54 tests, un taux de rejet de 7,4 % est
**statistiquement indiscernable du taux de faux positifs de 5 %**. La correction
Benjamini-Hochberg-Yekutieli, qui divise le seuil par 4,56, n'en laisse donc
passer aucun.

Autrement dit : sur vingt ans, l'hypothèse d'une tendance déterministe autour de
laquelle le cours reviendrait n'est établie pour aucune valeur de l'univers. Le
système le dit au lieu de le masquer. Le doc 03 §3.3 prévient : *si la
répartition sortait à 80 % de `good`, ce serait le signe d'un bug, pas d'un
univers exceptionnel*.

BH**Y** et non BH simple : les titres d'un même marché partagent leurs chocs,
leurs p-values ne sont pas indépendantes, et BH simple s'appuie précisément sur
cette indépendance.

### Ce qu'on affiche au lieu d'une probabilité

> « Ce titre est à −2σ, donc il a 95 % de chances de remonter. »

C'est faux, et c'est le contresens central de la méthode telle qu'elle est
vendue. Les résidus sont fortement autocorrélés : les épisodes hors bande ne sont
pas des événements indépendants de fréquence 5 %, ce sont des **régimes qui
durent**.

`regression_fits.regime_stats` porte donc la distribution du temps de premier
passage. Sur Seb, le cas du podcast, au 18 août 2026 :

| | |
|---|---|
| z-score | −2,16 |
| Épisodes sous −2σ depuis 2006 | 4, soit 6,0 % du temps |
| Durée médiane / maximale | 8 semaines / 46 semaines |
| **Épisode en cours** | **46 semaines — le plus long jamais observé** |
| Creux supplémentaire après franchissement | −7,7 % médian, −17,0 % au pire |
| Rendement après franchissement (n=3, in-sample) | +75 % à 1 an, +169 % à 3 ans |
| Demi-vie de retour | 1 256 jours (3,4 ans) |

Ces statistiques sont **in-sample** et décrivent le passé du titre. Elles ne
prédisent rien — mais « il faut typiquement tenir 8 semaines, parfois 46, avec
17 % de baisse supplémentaire » est une information de gestion, là où « 95 % de
chances » n'en est pas une.

### Une limite de l'intervalle AR(1), à ne pas sur-lire

L'intervalle de confiance sur la racine autorégressive est obtenu par bootstrap
par blocs mobiles. Il reste **anti-conservateur près de la racine unitaire** :
les résidus sont ceux d'une tendance estimée, donc déjà détendancés, ce qui biaise
ρ vers le bas, et le bootstrap ne reproduit pas la distribution asymptotique non
standard de ρ quand la vraie valeur vaut 1.

Constaté sur Seb : l'intervalle ressort à [0,943 ; 0,968], qui exclut 1, alors
que le DF-GLS sur le même titre ne rejette pas la racine unitaire. **C'est le
test qui a raison.** L'intervalle sert à comparer des titres entre eux et à
montrer l'ordre de grandeur de la persistance ; l'arbitrage stationnaire ou non
revient au DF-GLS, seul à alimenter `fit_quality`. Une inversion de test à la
Stock (1991) corrigerait ce point ; elle n'est pas prise en v1.

### Sur le critère d'acceptation « paramètres retrouvés à 1 % près »

Atteint pour la pente à rapport signal sur bruit élevé. Il ne l'est **pas** sur
un tirage unique à σ élevé, et ce n'est pas un défaut du code : à σ = 0,25 et
pente = 3 %, l'erreur-type théorique de β vaut déjà 4,6 % de β. Pour σ̂, l'erreur-type
relative vaut 1/√(2(n−2)) = 2,2 % sur 1 040 points, quel que soit σ — il faudrait
45 000 points pour tenir 1 %.

Les tests vérifient donc trois choses plus fortes que le critère littéral :
la pente à 1 % quand c'est possible, l'absence de biais sur 300 tirages (écart
0,11 %), et le fait que l'écart d'un tirage unique reste dans 3 erreurs-types.

## Screener et fiche instrument (L5)

```bash
.venv/Scripts/python.exe -m streamlit run dashboard/Screener.py
```

Deux écrans : le screener avec sa rangée de filtres, et la fiche instrument en
quatre blocs — graphe, diagnostics, statistiques de régime, position
concurrentielle. Thème clair et sombre, chaque graphe doublé de sa vue tabulaire.

Trois principes portés par l'interface :

- **Le silence est une fonctionnalité.** Aucune notification, aucun
  rafraîchissement temps réel. Thaler, Tversky, Kahneman & Schwartz (1997) ont
  montré que plus le feedback est fréquent, plus la prise de risque diminue et
  plus le rendement accumulé baisse : un outil qui augmente la fréquence de
  consultation détruit ce qu'il prétend améliorer. Le dashboard sert à creuser un
  titre, pas à surveiller.
- **L'incertitude est affichée.** Un fit `weak` s'affiche `weak`, avec son motif
  en clair. Le cas majoritaire est « on ne sait pas trancher », et l'interface le
  rend normal plutôt que honteux.
- **Toute visualisation a un jumeau tabulaire.** Exigence d'accessibilité, et
  seule façon de vérifier qu'un graphe ne ment pas.

**Le graphe montre ce que le screener a classé, pas un recalcul.** La droite est
reconstruite depuis l'`intercept` et le `slope_annual` écrits en base — un test
vérifie que le z-score du graphe égale celui stocké à 1e-9 près. Recalculer à
l'affichage laisserait le graphe diverger en silence de la ligne qui a classé le
titre, et c'est le graphe qu'on regarde pour décider.

Tous les titres s'affichent en `unqualified`, avec un bandeau qui l'explique.
C'est leur statut réel tant que L6b n'existe pas : un signal de prix sans
évaluation de la position concurrentielle est la moitié de la méthode, et c'est
la moitié qui produit les value traps.

### Le critère d'acceptation, et ce que je n'ai pas pu faire

> « le graphe d'un titre est superposable à celui de Hiboo pour le même titre,
> aux conventions d'ajustement près. »

**Cette confrontation reste à faire.** Hiboo est un service sur abonnement ;
déclarer une superposition sans l'avoir constatée serait exactement la validation
fictive que ce projet cherche à éviter. Le script produit la pièce à conviction :

```bash
python scripts/export_comparaison.py EQ:DE:BMW
```

**Prendre un titre sans split** — 26 des 57 n'en ont aucun, dont BMW, Sanofi,
Kering, Heineken, Arkema. Leur série ajustée est identique au nominal, le graphe
doit se superposer directement.

Sur un titre avec splits, l'écart attendu est un **facteur multiplicatif
constant** : L'Oréal ressort divisé par 20, EssilorLuxottica par 20,44. Un écart
constant valide la forme ; un écart qui dérive dans le temps signale un vrai
problème.

Ce qui doit coïncider : la forme de la courbe, la pente, et surtout le **z-score
courant** — c'est lui qui déclenche les décisions. Ce qui peut légitimement
différer : le niveau absolu, la largeur des bandes si Hiboo n'utilise pas une
fenêtre de 20 ans, et les extrémités.

Ce qui **est** vérifié automatiquement (18 tests) : que le graphe montre les
paramètres stockés, que l'axe soit logarithmique, qu'il n'y ait qu'un seul axe y,
que les bandes soient des gris neutres et non une teinte de série, qu'aucun filet
ne soit pointillé, que chaque statut porte icône et libellé — la couleur ne
portant jamais seule l'information — et que tout motif produit par le moteur ait
une traduction en clair.

## Fondamentaux régime A (L6)

```bash
python scripts/ingest_fundamentals.py   # ~30 concepts sur 5 exercices, tout l'univers
python scripts/verify_ratios.py         # recoupement des ratios
```

7 044 faits financiers, 33 concepts, **100 % des titres avec ≥ 3 exercices** de
chiffre d'affaires et de résultat net (seuil du doc : 80 %).

### Le principe P2 mis en danger, et comment il est sauvé

**yfinance ne sert aucune date de publication.** Ses tableaux sont indexés par
fin d'exercice, point. C'est un problème direct pour P2 : sans date de
publication, « le look-ahead bias est structurel et irrattrapable ».

Deux réactions possibles, une seule est acceptable :

1. Stocker `period_end` comme `published_at`. **Interdit** — cela ferait croire
   que les comptes 2024 étaient connus au 31 décembre 2024, alors qu'ils ne le
   sont qu'en mars 2025. Du look-ahead pur, et invisible.
2. Estimer une **borne supérieure**. La directive Transparence impose quatre mois
   aux émetteurs européens ; `period_end + 122 jours` est une date à laquelle
   l'information était certainement disponible.

**L'asymétrie est ce qui rend l'option 2 sûre.** Errer tard ne produit qu'un
excès de prudence — on s'interdit un fait qu'on connaissait déjà. Errer tôt
fabrique du look-ahead. On erre donc délibérément du côté tardif, et
`published_at_estimated` garde la trace pour le jour où une source servira les
vraies dates.

### Le recoupement, décomposé plutôt que constaté

Le critère demande de recouper « une source indépendante ». La référence est
Yahoo (`trailingPE`, `priceToBook`, `profitMargins`, `marketCap`) : même
fournisseur, mais **chemin de calcul différent** — il agrège ses trimestriels
glissants, nous partons des états annuels. Une divergence révèle donc une erreur
de mapping, de signe ou de convention.

| | Résultat |
|---|---|
| Capitalisation | **écart 0,0 %** sur les 10 titres |
| Price/Book | 1,8 % à 3,7 % |
| Marge nette (12 mois recalculés) | **0,0 %** sur AB InBev, adidas, BMW, Infineon |
| Concordance globale | 85,7 % sur 35 comparaisons |

Le script ne se contente pas de constater les écarts, il les **décompose** : il
recalcule le douze-mois-glissant depuis les comptes trimestriels et vérifie que
c'est bien lui que Yahoo affiche. Vérifié sur AB InBev — 14,90 % des deux côtés,
identiques. La divergence est une différence de base, pas une erreur
d'arithmétique. Sans cette décomposition, un vrai bug de mapping serait
indiscernable d'un écart de période.

Nous restons sur le **dernier exercice clos**, seule base compatible avec le
point-in-time : les trimestriels n'ont pas de date de publication exploitable.

### Ce que le recoupement a révélé : les financières

Allianz sortait à 25 % d'écart sur la marge nette, là où les industriels tombaient
à 0,0 %. Ce n'est pas un bug : **la notion de chiffre d'affaires n'a pas de
définition stable pour un assureur** — primes brutes, primes acquises, produit net
bancaire, chaque agrégateur choisit autrement.

Marge brute, opérationnelle et nette, EV/CA, EV/EBIT, dette nette sur EBITDA,
gearing et couverture des intérêts sont donc mis à `None` pour le secteur ICB 30,
et le critère de levier y est neutralisé — une banque a structurellement un levier
de 15 à 20, elle sortirait en `suspect` à chaque passage pour une raison qui n'en
est pas une. PER, P/B, ROE, croissance et distribution gardent leur sens et
restent calculés.

### Verdicts de cohérence, et une réserve sur leur lecture

| Verdict | Titres |
|---|---|
| `confirmé` | 35 |
| `suspect` | 17 |
| `indéterminable` | 5 |

**Un critère qu'on ne peut pas évaluer n'est jamais compté comme réussi** : il
sort en `indéterminable`, pas en `confirmé`. Traiter l'absence de donnée comme un
succès est la façon la plus courante de fabriquer un faux signal.

**La réserve.** Presque tous les `suspect` le sont pour `ca_non_decroissant`, et
la fenêtre de 3 ans démarre en 2022 — l'année du pic d'inflation et des prix de
l'énergie. BASF, Engie, Iberdrola, Arkema, Telefónica affichent mécaniquement une
croissance négative parce que leur base de départ est exceptionnelle, pas parce
qu'elles se délitent. **Ce critère est à relire quand cinq exercices pleins
seront disponibles hors année de base atypique**, ou à calibrer sur une médiane
sectorielle plutôt que sur zéro.

### Ce qui n'est pas fait dans L6

**Le parseur XBRL/ESEF.** Le doc 05 l'inclut dans le lot ; il ne l'est pas ici.
yfinance couvre le critère d'acceptation à 100 %, et ESEF n'ajouterait de la
profondeur que depuis 2021. Le vrai argument pour le faire un jour n'est pas la
couverture : **ESEF porte les vraies dates de dépôt**, ce qui supprimerait
l'estimation décrite plus haut pour tous les exercices postérieurs à 2021.

## Position concurrentielle (L6b)

```bash
python scripts/compute_quality.py      # trimestriel, pas hebdomadaire
```

La seconde jambe de la méthode. Trois questions dans cet ordre — leadership,
rente, érosion — et **c'est la troisième qui décide** : un leader dont la rente
s'érode depuis cinq ans n'est pas un leader décoté, c'est un leader en train de
perdre sa position, et le marché a probablement raison de le vendre.

**Ce qu'on refuse de mesurer.** « Position concurrentielle durable » contient
deux mots de nature différente. La position se mesure par proxies ; la
**durabilité** est une affirmation sur l'avenir qu'aucune donnée historique ne
démontre — Kodak affichait un ROIC élevé et une marque indépassable en 1998. On
ne mesure donc pas la durabilité : on mesure la position et on teste **l'absence
d'érosion**. C'est une réfutation, pas une confirmation.

### Résultat sur l'univers

| Niveau | Titres | | Régime | Titres |
|---|---|---|---|---|
| `watch` | 49 | | `rent` | 25 |
| `unqualified` | 7 | | `cyclical` | 15 |
| `eroding` | 1 | | `no_moat` | 12 |
| `solid` | **0** | | `eroding` / `unknown` | 1 / 4 |

**Aucune cible, et ce n'est pas une anomalie.** Un titre n'accède à `solid`
qu'avec deux conditions cumulatives, et la seconde n'est remplie pour aucun titre
à ce jour :

1. un groupe de pairs contenant **au moins un concurrent hors Europe** ;
2. une **évaluation qualitative revue par un humain**, non périmée.

### Les deux garde-fous, et pourquoi ils ne sont pas négociables

**Le groupe de pairs incomplet.** C'est la limite la plus sérieuse du système :
les menaces réelles viennent presque toujours de l'extérieur de l'univers.
SharkNinja, l'agresseur de Seb, est américaine ; BYD, celui de BMW, est chinoise ;
Revolut n'est pas cotée. Un screener sectoriel européen sous-estime donc la
menace, **et d'autant plus qu'il rassure** — le titre reste leader d'un univers
qui ne contient pas son concurrent. Six groupes manuels sont seedés avec 14
concurrents hors univers ; les 10 groupes sectoriels automatiques sont marqués
incomplets par construction.

**L'évaluation qualitative.** Le moat quantitatif mesure le passé : un ROIC élevé
est la trace d'une barrière **qui a existé**, il ne dit rien de sa résistance à
une rupture. Seule la jambe qualitative peut écrire « cette barrière est menacée
par X », et X n'est jamais dans les comptes. Un LLM pourra la rédiger en phase 2 ;
il ne la valide jamais — `reviewed_by` reste humain.

### Deux défauts trouvés en observant les résultats

**1. Un cyclique classé en value trap.** La première version testait l'érosion
avant le régime : Arkema sortait `eroding`, donc value trap une fois croisé avec
un z-score bas. Le doc 08 dit l'inverse — *Arkema : non applicable, régime
cyclique, bas de cycle, pas érosion*. Une pente de ROIC négative sur un cyclique
mesure la descente du cycle, pas la perte d'une barrière. Classer cela en value
trap revenait à **exclure précisément le moment où il faut regarder**.

**2. Un effondrement classé en cyclique.** La correction a d'abord basculé trop
loin : un ROIC qui s'effondre de 18 % à 2 % a une volatilité très élevée et
sortait donc `cyclical`, donc protégé du verdict d'érosion. C'était exactement le
cas Atos, présenté comme un bas de cycle à acheter. Un cycle redescend **et
remonte** ; un effondrement ne fait que descendre — d'où un discriminant sur la
part de variance expliquée par la tendance.

**Mais ce discriminant ne suffit pas non plus, et c'est une limite de fond.** Avec
quatre exercices, la fenêtre ne couvre souvent que la *descente* d'un cycle, et
une descente de cycle est statistiquement indiscernable d'une érosion : même
pente, même monotonie. C'est la limite L2 du doc 08 — *cinq ans, c'est court pour
une notion de durabilité* — et aucune amélioration du code ne la lève.

La sortie retenue est celle que le doc emploie lui-même : il identifie Arkema et
BMW **par leur métier**, pas par un test. `db/seeds/004_cycliques.sql` déclare
donc les cycliques à la main, sur le même principe que les groupes de pairs
manuels — la déclaration prime sur la détection. À revoir quand huit exercices
seront disponibles : le test statistique redeviendra capable de trancher seul.

### Le seul value trap, et la réserve qui l'accompagne

**LVMH.** ROIC 22,3 % → 15,2 % et marge brute 68,4 % → 66,2 % entre 2022 et 2025,
les deux pentes significativement négatives à 90 %. La donnée est réelle et le
verdict conforme à la spécification.

**Mais trois choses doivent être lues avec.** Le ROIC reste à 15,2 %, soit près
du double du seuil de 8 % — l'érosion porte sur la *tendance*, pas sur le niveau.
La fenêtre ne compte que 4 points et démarre en 2022, le pic post-Covid du luxe :
une descente depuis un sommet exceptionnel n'est pas l'érosion d'une barrière. Et
la borne haute de l'intervalle sur la marge brute est à −0,0000, soit une
significativité tout juste atteinte.

C'est précisément le genre de cas où le système doit afficher son raisonnement
plutôt que son verdict — ce que fait le bloc D, en montrant les trois pentes
séparément et l'écart au seuil à côté du niveau.

### Cas de référence du doc 08

| Titre | Attendu | Obtenu |
|---|---|---|
| Arkema | `cyclical`, bas de cycle | `cyclical` / `watch` ✓ |
| BMW | ≥ 1 pente d'érosion | 1/3, `cyclical` / `watch` ✓ |
| Seb | à qualifier, pas à trancher | `no_moat` / `watch`, groupe manuel avec SharkNinja ✓ |
| Nestlé | `solid` | **hors univers** — suisse, non éligible PEA |
| Atos | `eroding` | **hors univers** — écarté en L1 |

Les deux derniers sont éprouvés sur données synthétiques, où la réponse est
connue : cela teste la règle, là où un titre réel ne ferait que la constater.

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
