# 02 - Ingestion et sources de données

> **⚙ Écart majeur depuis l'implémentation : Stooq n'est plus utilisable.** L'endpoint `/q/d/l/` renvoie désormais une page de vérification navigateur à **preuve de travail JavaScript**, constaté depuis deux IP indépendantes. L'argument de robustesse qui le plaçait en primaire - *un CSV par URL ne casse pas* - ne tient plus. **yfinance est source primaire et unique.** Voir §2.1 amendé et doc 09 D-B.

---

## 1. Le constat qui structure ce document

**Les cours sur 30 ans sont gratuits et abondants. Les comptes sur 20 ans ne le sont pas.**

C'est l'asymétrie centrale du projet, et elle est plus favorable qu'il n'y paraît : la droite de régression - le cœur de la méthode - ne demande **que des cours**. Les fondamentaux ne servent qu'à valider a posteriori qu'un signal de prix n'est pas un piège. Pour cet usage, 5 ans suffisent largement.

Autrement dit : la partie chère du problème n'est pas nécessaire pour la partie qui a de la valeur.

---

## 2. Cartographie des sources

### 2.1 Cours historiques

| Source | Couverture | Profondeur | Format | Limites | Statut |
|---|---|---|---|---|---|
| **Stooq** | Europe, US, indices, FX, matières | 20-30 ans | CSV direct par URL | **Preuve de travail JavaScript sur `/q/d/l/`** | ✕ **Inaccessible** |
| **yfinance** | Mondiale | Variable, souvent 30 ans+ | Python | Rate limiting agressif, casse à chaque changement Yahoo | ✅ **Primaire et unique** |
| **ABC Bourse** | France | Longue | CSV téléchargeable | Manuel, France seulement | Backfill ponctuel |
| **bnains.org** | France, historiques anciens | Très longue | Archives | Manuel | Backfill CAC 40 ancien |
| **Euronext** | Euronext | Variable | Site officiel | Peu commode en masse | Contrôle qualité |

**~~Choix proposé : Stooq en primaire, yfinance en secondaire.~~** *Caduc.*

> **⚙ Décision réelle : yfinance en primaire et unique.** Stooq est inaccessible (preuve de travail JavaScript sur `/q/d/l/`). Les symboles Stooq sont conservés dans `instruments.attributes.stooq_symbol_unverified` mais **non chargés** dans `instrument_symbols` - *les inscrire non vérifiés reviendrait à fabriquer la confiance qu'on cherche justement à établir*.
>
> **La conséquence contredit frontalement le principe « aucune source ne doit être un point de défaillance unique », et reste à arbitrer.**

**Conséquence de conception :** aucune source ne doit être un point de défaillance unique. D'où la table `data_sources` avec `priority`, et le fait que `bars` porte `source_id` sur chaque ligne.

> **⚙ Dette T3 - et elle est plus grave que l'absence de seconde source.** `bars` a pour clé primaire `(instrument_id, freq, ts)` : **`source_id` n'y figure pas.** Deux sources ne peuvent donc pas porter la même barre. Brancher Stooq demain ne suffirait pas : la seconde source serait comptée comme une *révision* de la première et l'écraserait silencieusement, en déclenchant éventuellement une alerte `split_unadjusted` - un mauvais diagnostic. Le contrôle de divergence inter-sources, que ce document qualifie plus bas de « celui que les gens sautent, et c'est une erreur », est **impossible par schéma**. Correction : ajouter `source_id` à la clé primaire, ou une table de comparaison dédiée.
>
> Par ailleurs `data_sources.priority` est renseignée à l'inverse de l'usage réel (stooq=10, yfinance=20) et **n'est lue par aucun code**.

### 2.2 Corporate actions et nombre d'actions

| Donnée | Source | Fiabilité | Remarque |
|---|---|---|---|
| Splits | yfinance | Bonne | Vérifier par détection de saut |
| Dividendes | yfinance | Bonne | |
| Augmentations de capital | AMF, communiqués | Faible en automatique | **Point faible assumé** |
| Nombre d'actions | yfinance (récent), XBRL (2021+) | Moyenne | Historique long lacunaire |

**C'est la principale faiblesse du dispositif gratuit, et elle est structurelle.** Les augmentations de capital dilutives ne sont exposées proprement par aucune source gratuite. Or c'est précisément ce qui fausse la droite de régression sur les Atos et Casino.

**Mitigation en trois temps :**
1. **Détection par saut de cours** : une variation supérieure à 25% en une séance non expliquée par un split ou un dividende connu déclenche une alerte en `data_quality_issues`.
2. **Détection par nombre d'actions** : quand la donnée existe, une hausse de plus de 50% sur 12 mois glissants invalide la régression sur la fenêtre antérieure.
3. **Revue manuelle** : les cas signalés sont peu nombreux - de l'ordre de quelques titres par an sur 57 - et se traitent à la main.

### 2.3 Fondamentaux

| Source | Profondeur | Format | Couverture | Effort |
|---|---|---|---|---|
| **yfinance** | 4-5 ans | JSON structuré | Large | Faible |
| **ESEF / XBRL** (filings.xbrl.org) | 2021+ | XBRL structuré | ~25 700 dépôts, 30 pays européens | Moyen - parsing XBRL |
| **API info-financière (AMF)** | Longue | **PDF, pas de chiffres structurés** | Sociétés cotées françaises | Élevé - extraction |
| **EODHD** | 20 ans+ | JSON | 70 bourses | Nul, mais ~60$/mois |

L'API de l'AMF est en accès libre, sans clé, plafonnée à 10 000 appels par IP et par jour. Elle donne accès aux documents réglementés déposés par les émetteurs - mais **des documents, pas des chiffres**. C'est un dépôt de PDF.

### 2.4 Taux de change et déflateurs

| Donnée | Source | Remarque |
|---|---|---|
| FX quotidien | BCE, séries de référence | Gratuit, stable, officiel |
| Indices de prix (IPCH) | Eurostat | Nécessaire pour la politique `real_deflated` des matières premières |

---

## 3. Stratégie fondamentaux : le double régime

C'est la décision actée, et elle mérite d'être détaillée parce qu'elle est le bon compromis coût/valeur.

> **⚙ État réel : seul le régime A est construit, et sans ESEF.** Aucun collecteur ESEF/XBRL, AMF, BCE ni Eurostat. Le régime B - extraction PDF par LLM - n'est pas amorcé (aucune dépendance LLM au projet). `fx_rates` reste vide, ce qui est sans effet : l'univers est intégralement en euro.

### Régime A - large et superficiel, pour tous les titres

Ingestion automatique de yfinance et du XBRL/ESEF pour l'ensemble de l'univers, sur environ 5 ans. Une trentaine de concepts : chiffre d'affaires, résultat opérationnel, résultat net, capitaux propres, dette nette, flux de trésorerie disponible, nombre d'actions.

**Usage :** répondre à la question de Marie - *"une fois que tu as vu qu'il y avait un signal de prix, tu vérifies que c'est cohérent avec les fondamentaux"*. Cinq ans suffisent parfaitement à voir si les bénéfices suivent ou si la boîte se délite.

**Coût :** nul. **Couverture :** l'univers entier.

> **⚙ Mesuré : 7 044 faits, 33 concepts, 100% des titres avec ≥3 exercices** - le critère d'acceptation était de 80%. **Le parseur ESEF n'a pas été construit** et ne l'a pas empêché : ESEF n'ajouterait de la profondeur que depuis 2021. *Le vrai argument pour le faire un jour n'est pas la couverture, c'est qu'**ESEF porte les vraies dates de dépôt** - voir doc 01 §5.2 et doc 09 D-C.*
>
> **Deux titres écartés :** Banco Santander et Amadeus ne renvoient que 3 barres hebdomadaires chez yfinance, là où Iberdrola, Inditex et Telefónica sur le même marché en renvoient 26 ans. Le seuil de rejet est volontairement dur : *sous un an d'historique, ce n'est pas une jeune société, c'est un flux cassé, et charger la ligne donnerait une régression sur trois points.*

### Régime B - étroit et profond, à la demande

Uniquement pour les titres qui **sortent du screener** - une dizaine à une vingtaine par semaine, dont l'essentiel se répète d'une semaine sur l'autre. On récupère les rapports annuels via l'API AMF, on extrait les chiffres par LLM, on stocke dans `financial_facts` avec `extraction_method = 'llm_pdf'` et un score de confiance.

**Pourquoi c'est le bon design.** Le coût d'extraction n'est engagé que là où il produit de la décision. Extraire 20 ans de comptes pour 57 sociétés dont on n'achètera jamais 50 est un gaspillage pur.

**Et c'est le seul endroit où le LLM est vraiment non substituable.** Lire un PDF de rapport annuel en français et en sortir un tableau structuré est une tâche qu'aucune règle ne fait bien et qu'un LLM fait très correctement. À comparer avec la génération de narratifs explicatifs, qui est le mauvais usage identifié dans l'avis critique.

**Garde-fous d'extraction :**
- toujours conserver le PDF source et la page d'origine de chaque chiffre
- double extraction sur un échantillon, mesure du taux de divergence
- contrôle d'identité comptable automatique : actif = passif, résultat net cohérent avec la variation de capitaux propres hors dividendes
- tout chiffre sous un seuil de confiance part en revue manuelle, il n'entre pas silencieusement

---

## 4. Architecture du pipeline

### 4.1 Structure

```
collectors/          un module par source, responsabilité unique : récupérer du brut
  stooq.py            ✕ non construit (source inaccessible)
  yfinance.py         ✅ prices · actions · fundamentals
  esef.py             ⬜ non construit
  amf.py              ⬜ non construit
  ecb_fx.py           ⬜ non construit

normalizers/         brut → schéma canonique, aucune logique métier
  bars.py
  corporate_actions.py
  fundamentals.py

validators/          contrôles qualité, produit des data_quality_issues
  price_checks.py
  fundamental_checks.py
  cross_source.py

loaders/             écriture idempotente en base
  upsert.py

jobs/                orchestration
  backfill_initial.py
  daily_prices.py
  weekly_full.py
  on_demand_extraction.py
```

**Règle : un collector ne valide rien et ne transforme rien.** Il récupère et stocke le brut. La séparation permet de rejouer la normalisation sans retélécharger, ce qui est le principe P1 appliqué au pipeline.

### 4.2 Idempotence

Tout job doit pouvoir être relancé sans effet de bord. Concrètement : `insert ... on conflict do update` sur les clés naturelles, jamais de `insert` nu.

*Raison pratique : un job qui plante à 80% doit pouvoir être relancé entièrement sans réfléchir. Sinon on finit par ne plus oser les relancer, et le système pourrit.*

### 4.3 Quarantaine plutôt que rejet

Une ligne qui échoue à la validation n'est pas jetée : elle est écrite avec un marqueur et une entrée dans `data_quality_issues`. On peut ainsi diagnostiquer après coup.

*Les données silencieusement absentes sont bien plus dangereuses que les données visiblement fausses.*

> **⚙ Réel - partiellement, et un bug annule la trace (dette T4).** Les lignes écartées ne sont pas écrites en base avec un marqueur : elles sont jetées, seule une trace est déposée dans `data_quality_issues` avec les 10 premiers exemples. Or `record_rejections` écrit `issue_type = 'gap'` **sans empreinte**, et le job de contrôle clôt automatiquement toute anomalie sans empreinte dont le type est recalculé - `gap` en fait partie. **Les barres écartées deviennent donc invisibles dès le contrôle suivant.** Les rejets d'opérations sur titre et de faits financiers ne produisent, eux, aucune ligne du tout.
>
> **En revanche le cycle de vie des anomalies va bien au-delà de la spec (doc 09 D-H) :** empreinte stable, `run_count`, distinction entre clôture automatique et acquittement humain, réouverture, et un CLI de revue qui **refuse une clôture sans note** - *une résolution sans note ne sert à rien dans six mois*.

### 4.4 Ordonnancement

> **⚙ État : aucun orchestrateur.** Ni Makefile, ni CI, ni fichier crontab, ni point d'entrée CLI. Les modules de `jobs/` sont des fonctions `run()` sans `__main__`. **Un seul cron installé sur le VPS : le keepalive.** Le cycle est aujourd'hui une séquence manuelle. Lot L7, non fait.
>
> **C'est la dette la plus coûteuse du projet, et la seule qui ne se rattrape pas.** Le principe P5 - l'historisation hebdomadaire de `regression_fits` - ne produit sa valeur que par régularité. Chaque semaine sans cron est une observation hors échantillon définitivement perdue.
>
> *Note : six commandes prescrites par le README pointent vers des fichiers `scripts/` inexistants. La logique est dans `jobs/`, les enveloppes CLI manquent (dette T25).*

**Durées réelles mesurées sur 57 titres :** backfill des cours ~6 min (122 000 barres) · corporate actions et facteurs ~7 min · fondamentaux ~7 min (7 044 faits) · contrôles qualité ~10 s · 57 régressions ~2 min · 57 scores qualité ~30 s · archive Parquet ~20 s. *Le temps est dominé par le débit ménagé vers yfinance, pas par le calcul.*

| Job | Fréquence | Durée estimée | Rôle |
|---|---|---|---|
| `daily_prices` | quotidien, 19h CET | ~2 min | Cours du jour, univers actif |
| `weekly_full` | dimanche 6h | ~15 min | Consolidation hebdo, corporate actions, **calcul et historisation des fits**, screener, rapport |
| `monthly_fundamentals` | 1er du mois | ~20 min | Rafraîchissement du régime A |
| `on_demand_extraction` | déclenché | variable | Régime B sur les titres du screener |
| `keepalive_ping` | quotidien | 1 s | Empêche la mise en pause Supabase |

*Le `keepalive_ping` doit être un job séparé et trivial. S'il dépend du pipeline principal, une panne de pipeline entraîne une mise en pause de la base, donc une panne aggravée.*

---

## 5. Contrôles qualité

Liste des vérifications à implémenter, par ordre de valeur décroissante.

| Contrôle | Détection | Sévérité |
|---|---|---|
| **Saut de cours inexpliqué** | Variation > 25% en une séance sans corporate action connue | bloquant |
| **Série figée** | Cours identique > 5 séances consécutives | avertissement |
| **Trou de cotation** | > 5 jours ouvrés sans donnée sur un titre actif | avertissement |
| **Dilution** | Nombre d'actions +50% sur 12 mois glissants | bloquant sur la régression |
| **Divergence inter-sources** | Écart > 1% sur une clôture entre Stooq et yfinance | avertissement |
| **Incohérence de devise** | Cours dans une devise ≠ devise du marché | bloquant |
| **Historique insuffisant** | < `min_years` de la politique applicable | exclusion du screener |
| **FX manquant** | Pas de taux pour une devise à une date | avertissement |
| **Identité comptable** | Actif ≠ passif au-delà d'une tolérance | avertissement sur le fait |

**Le contrôle de divergence inter-sources est celui que les gens sautent, et c'est une erreur.** Deux sources indépendantes qui concordent donnent une confiance réelle ; une source unique donne une confiance illusoire.

> **⚙ Réel : les 9 contrôles sont écrits et appelés. Trois réserves.**
>
> **(a) Deux ne sont pas éprouvables** sur l'univers actuel : la divergence inter-sources (source unique, et impossible par schéma - voir §2.1) et le FX manquant (univers mono-devise). Le filtre de dilution est éprouvé sur **données synthétiques**, Atos et Casino n'étant pas dans les 57 - *cela teste la règle, là où un titre réel ne ferait que la constater*.
>
> **(b) Dette T7 : les trois contrôles de série ne voient que 3 ans sur 26.** Saut de cours, série figée et trou de cotation filtrent tous `freq = '1d'`, et le quotidien s'arrête à 3 ans. **Aucun ne s'applique à la série hebdomadaire de 20 ans qui porte la régression.** Un point aberrant en 2009 passe sans être vu.
>
> **(c) Deux contrôles se sont affaiblis à l'écriture.** L'incohérence de devise compare deux colonnes de référentiel (`instruments.currency` vs `exchanges.currency`) et non les cotations : elle attrape une erreur de saisie, pas une bascule GBX/GBP chez le provider. Le FX manquant teste l'existence d'un taux, pas sa présence à une date donnée.

**Contrôle ajouté, absent de la spec et indispensable : `split_unadjusted`.** Détecte la réécriture rétroactive massive de la série par Yahoo - seuil : plus de 5% des barres révisées sur au moins 20 lignes. Sans lui, le choix de stocker `Close` (doc 00 P4) serait aveugle à ses propres effets.

**Le filtre de dilution est allé plus loin que la spec, et il le fallait.** Il compare au **minimum glissant sur 365 jours** (attrape une dilution suivie d'un rachat partiel), sur un nombre d'actions **préalablement neutralisé des splits**. Sans cette neutralisation : quatre faux positifs - Dassault ×5.09, Michelin ×4.0, Aena ×10.7, Prosus ×2.43. Et une seule alerte par titre, contre 203 lignes pour Prosus autrement.

---

## 6. Backfill initial

Séquence proposée, à exécuter une fois.

1. **Construction du référentiel** - composition actuelle du SBF 120 et des grands indices européens, résolution des ISIN, mapping des tickers par source. *Cette étape est manuelle et fastidieuse. C'est normal, et c'est la fondation.*
2. **Cours hebdomadaires, profondeur maximale**, via yfinance. *⚙ Stooq inaccessible - voir §2.1.*
3. **Cours quotidiens sur 3 ans**, même source.
4. ~~**Contre-vérification** sur une seconde source.~~ *⚙ Caduc : source unique, et impossible par schéma - `source_id` n'est pas dans la clé primaire de `bars` (dette T3). Substitut partiel : `scripts/verify_ratios.py` recoupe les ratios contre un chemin de calcul différent du même fournisseur.*
5. **Corporate actions** via yfinance.
6. **Archive Parquet** du quotidien complet - la couche froide. *⚙ **Dette T8 : l'archive est un miroir du chaud, pas une couche plus profonde.** `export_cold.py` relit `bars`, or aucun job ne télécharge de quotidien au-delà de 3 ans. Les deux températures ont la même profondeur : la stratégie du doc 00 §5 n'a qu'une température. Le docstring du fichier cite pourtant la règle qu'il ne tient pas.*
7. **Fondamentaux régime A**.
8. **Premier calcul de régressions**, avec `as_of_date` = date du jour. *Attention : ce premier fit est in-sample, et c'est le seul du système. Il doit être marqué comme tel.*

**Durée estimée du backfill : 2 à 4 heures machine, dont l'essentiel en attente de débit.**

---

## 7. Résilience et débit

- **Débit ménagé** : pas plus d'une requête par seconde par source, avec jitter. On n'est pas pressé, et se faire blacklister coûte plus cher qu'attendre. *⚙ Réel : 2 s, deux fois plus prudent. **Mais aucun jitter** - la cadence est parfaitement régulière, ce qui est exactement le motif que le jitter devait casser (dette T23).*
- **Reprise avec backoff exponentiel** sur les erreurs réseau, trois tentatives. *⚙ Fait sur les prix et les fondamentaux ; **absent de `fetch_actions`**, un seul essai (dette T24). Ajout notable : **une réponse vide est traitée comme un échec temporaire** - Yahoo rate-limite en renvoyant un DataFrame vide plutôt qu'une erreur franche, sans quoi un titre refusé serait enregistré comme dépourvu d'historique et classé `rejected` à tort.*
- **Cache disque** des réponses brutes pendant 24 h : relancer un job en développement ne doit pas retaper la source. *⚙ **Non construit.** Le brut n'est jamais persisté : le collecteur rend un DataFrame consommé immédiatement. Le principe P1 - « rejouer la normalisation sans retélécharger » - est affirmé dans les docstrings et impraticable (dette T23).*
- **Circuit breaker** : au-delà de 20% d'échecs sur un job, arrêt et alerte plutôt qu'une base à moitié remplie. *⚙ **Non construit.** Les jobs empilent les échecs et poursuivent ; le seul effet est un statut `partial` en fin de course - exactement le scénario que ce point voulait interdire (dette T23).*
- **Aucun secret en dur.** Variables d'environnement, y compris pour Supabase.

---

## 8. Aspects juridiques, dits franchement

**Yahoo Finance.** Les conditions d'utilisation interdisent l'usage commercial des données récupérées par scraping. Un usage strictement personnel se situe dans une zone grise tolérée en pratique, mais ce n'est pas une autorisation. Si le projet devait un jour être exposé à des tiers, il faudrait basculer sur une source licenciée.

**Stooq.** Conditions plus permissives, mais sans licence explicite pour la redistribution.

**ESEF / XBRL et API AMF.** Données publiques réglementées, réutilisation libre. Ce sont les sources les plus sûres juridiquement.

**Recommandation :** faire porter la valeur du système sur le **calcul** - les régressions, les diagnostics, l'historisation - et non sur la donnée brute redistribuée. Le calcul t'appartient sans ambiguïté ; la donnée brute, non.

---

## À challenger en priorité

1. ~~**Stooq en source primaire plutôt que yfinance.**~~ **Tranché par les faits - doc 09 D-B.** Stooq est inaccessible. Ce qui reste à arbitrer n'est plus le choix de la source mais **l'acceptation d'une source unique**, et la correction de la clé primaire de `bars` (T3) qui la rend aujourd'hui non réparable par simple ajout d'un provider.
2. **Le régime B déclenché uniquement par le screener.** Alternative : extraire les 20 ans de comptes pour une liste blanche de 50 titres que tu suis en permanence, indépendamment du signal. Plus de coût, mais tu ne découvres pas les fondamentaux dans l'urgence d'un signal.
3. **Le seuil de divergence inter-sources à 1%** est probablement trop serré pour les small caps peu liquides. À calibrer.
4. **L'absence de source fiable pour les augmentations de capital** est la faiblesse la plus sérieuse de tout le dispositif gratuit. Si un poste de dépense devait être accepté, c'est celui-là - et non les 20 ans d'historique de comptes.
