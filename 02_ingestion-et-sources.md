# 02 - Ingestion et sources de données

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
| **Stooq** | Europe, US, indices, FX, matières | 20-30 ans | CSV direct par URL | Pas d'API officielle, débit à ménager | Source primaire proposée |
| **yfinance** | Mondiale | Variable, souvent 30 ans+ | Python | Rate limiting agressif, casse à chaque changement Yahoo | Secondaire et complément |
| **ABC Bourse** | France | Longue | CSV téléchargeable | Manuel, France seulement | Backfill ponctuel |
| **bnains.org** | France, historiques anciens | Très longue | Archives | Manuel | Backfill CAC 40 ancien |
| **Euronext** | Euronext | Variable | Site officiel | Peu commode en masse | Contrôle qualité |

**Choix proposé : Stooq en primaire, yfinance en secondaire.**

Justification : Stooq sert des CSV bruts par simple URL, sans dépendance à une bibliothèque qui casse, et couvre les bourses européennes sur une profondeur adaptée. yfinance est plus riche - corporate actions, fondamentaux, métadonnées - mais nettement plus fragile : c'est un scraper non officiel, Yahoo le rate-limite (erreurs 429) et chaque évolution de leur site le casse.

**Conséquence de conception :** aucune source ne doit être un point de défaillance unique. D'où la table `data_sources` avec `priority`, et le fait que `bars` porte `source_id` sur chaque ligne.

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
3. **Revue manuelle** : les cas signalés sont peu nombreux - de l'ordre de quelques titres par an sur 250 - et se traitent à la main.

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

### Régime A - large et superficiel, pour tous les titres

Ingestion automatique de yfinance et du XBRL/ESEF pour l'ensemble de l'univers, sur environ 5 ans. Une trentaine de concepts : chiffre d'affaires, résultat opérationnel, résultat net, capitaux propres, dette nette, flux de trésorerie disponible, nombre d'actions.

**Usage :** répondre à la question de Marie - *"une fois que tu as vu qu'il y avait un signal de prix, tu vérifies que c'est cohérent avec les fondamentaux"*. Cinq ans suffisent parfaitement à voir si les bénéfices suivent ou si la boîte se délite.

**Coût :** nul. **Couverture :** l'univers entier.

### Régime B - étroit et profond, à la demande

Uniquement pour les titres qui **sortent du screener** - une dizaine à une vingtaine par semaine, dont l'essentiel se répète d'une semaine sur l'autre. On récupère les rapports annuels via l'API AMF, on extrait les chiffres par LLM, on stocke dans `financial_facts` avec `extraction_method = 'llm_pdf'` et un score de confiance.

**Pourquoi c'est le bon design.** Le coût d'extraction n'est engagé que là où il produit de la décision. Extraire 20 ans de comptes pour 250 sociétés dont on n'achètera jamais 230 est un gaspillage pur.

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
  stooq.py
  yfinance.py
  esef.py
  amf.py
  ecb_fx.py

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

### 4.4 Ordonnancement

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

**Le contrôle de divergence inter-sources est celui que les gens sautent, et c'est une erreur.** Deux sources indépendantes qui concordent donnent une confiance réelle ; une source unique donne une confiance illusoire. Le coût est de télécharger deux fois - négligeable sur 250 titres.

---

## 6. Backfill initial

Séquence proposée, à exécuter une fois.

1. **Construction du référentiel** - composition actuelle du SBF 120 et des grands indices européens, résolution des ISIN, mapping des tickers par source. *Cette étape est manuelle et fastidieuse. C'est normal, et c'est la fondation.*
2. **Cours hebdomadaires, profondeur maximale**, via Stooq, source primaire.
3. **Cours quotidiens sur 3 ans**, même source.
4. **Contre-vérification** sur yfinance pour un échantillon de 30 titres, mesure du taux de divergence.
5. **Corporate actions** via yfinance.
6. **Archive Parquet** du quotidien complet - la couche froide.
7. **Fondamentaux régime A**.
8. **Premier calcul de régressions**, avec `as_of_date` = date du jour. *Attention : ce premier fit est in-sample, et c'est le seul du système. Il doit être marqué comme tel.*

**Durée estimée du backfill : 2 à 4 heures machine, dont l'essentiel en attente de débit.**

---

## 7. Résilience et débit

- **Débit ménagé** : pas plus d'une requête par seconde par source, avec jitter. On n'est pas pressé, et se faire blacklister coûte plus cher qu'attendre.
- **Reprise avec backoff exponentiel** sur les erreurs réseau, trois tentatives.
- **Cache disque** des réponses brutes pendant 24 h : relancer un job en développement ne doit pas retaper la source.
- **Circuit breaker** : au-delà de 20% d'échecs sur un job, arrêt et alerte plutôt qu'une base à moitié remplie.
- **Aucun secret en dur.** Variables d'environnement, y compris pour Supabase.

---

## 8. Aspects juridiques, dits franchement

**Yahoo Finance.** Les conditions d'utilisation interdisent l'usage commercial des données récupérées par scraping. Un usage strictement personnel se situe dans une zone grise tolérée en pratique, mais ce n'est pas une autorisation. Si le projet devait un jour être exposé à des tiers, il faudrait basculer sur une source licenciée.

**Stooq.** Conditions plus permissives, mais sans licence explicite pour la redistribution.

**ESEF / XBRL et API AMF.** Données publiques réglementées, réutilisation libre. Ce sont les sources les plus sûres juridiquement.

**Recommandation :** faire porter la valeur du système sur le **calcul** - les régressions, les diagnostics, l'historisation - et non sur la donnée brute redistribuée. Le calcul t'appartient sans ambiguïté ; la donnée brute, non.

---

## À challenger en priorité

1. **Stooq en source primaire plutôt que yfinance.** Je privilégie la robustesse - un CSV par URL ne casse pas - au détriment de la richesse. Si tu préfères une source unique plus complète, yfinance en primaire est défendable, avec une fragilité opérationnelle assumée.
2. **Le régime B déclenché uniquement par le screener.** Alternative : extraire les 20 ans de comptes pour une liste blanche de 50 titres que tu suis en permanence, indépendamment du signal. Plus de coût, mais tu ne découvres pas les fondamentaux dans l'urgence d'un signal.
3. **Le seuil de divergence inter-sources à 1%** est probablement trop serré pour les small caps peu liquides. À calibrer.
4. **L'absence de source fiable pour les augmentations de capital** est la faiblesse la plus sérieuse de tout le dispositif gratuit. Si un poste de dépense devait être accepté, c'est celui-là - et non les 20 ans d'historique de comptes.