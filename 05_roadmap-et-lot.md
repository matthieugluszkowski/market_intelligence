# 05 - Roadmap, lots de livraison et critères d'acceptation

**Principe de découpage :** chaque lot produit quelque chose d'observable. Aucun lot ne consiste à « préparer » un lot suivant.

**Estimations :** en jours-homme pour un développeur assisté par LLM. Elles supposent qu'on ne découvre pas de mauvaise surprise sur les sources - hypothèse optimiste, voir §4.

> **État au 19 août 2026 : L0 à L6b faits, L7 à L9 non entamés.** 57 titres, 122 000 barres, 7 044 faits financiers, 169 tests. Effort réel de l'ordre de 20 jours pour L0 à L6b - **la fourchette optimiste a tenu**, contre mon pronostic de 30 à 35 jours. Détail et registre de dette : doc 09.

---

## 1. Les lots

### L0 - Socle · 1 j  ✅

Dépôt Git, environnement Python, projet Supabase, DDL complet appliqué, seeds du référentiel (classes d'actifs, marchés, devises, politiques, sources), variables d'environnement, ping keepalive.

**Acceptation :** le schéma est créé, les tables de référence peuplées, le ping tourne en cron.

---

### L1 - Référentiel de l'univers · 2 à 3 j  ✅

Le lot le plus ingrat et le plus structurant.

Constitution de la liste des titres cibles (~250 visés, **57 réalisés**) : SBF 120 plus les grandes valeurs allemandes, néerlandaises, espagnoles, italiennes et belges. Pour chacun : ISIN, nom, marché, devise, secteur ICB, et **le mapping des symboles vers Stooq et yfinance**.

**Le mapping est la vraie difficulté.** Les symboles diffèrent d'une source à l'autre, sont parfois ambigus - le cas Seb / SEB banque suédoise du podcast - et il n'existe pas de table de correspondance gratuite fiable. Il faut construire et vérifier à la main.

**Acceptation :** 250 instruments en base, chacun avec au moins un symbole vérifié par téléchargement d'une cotation réelle, et zéro doublon d'ISIN. *⚙ Requalifié à 57 - démarrage à 50 comme recommandé au §4.*

> **⚙ Fait, et le piège a été traité par un outil.** `scripts/verify_universe.py` applique trois contrôles indépendants avant tout chargement : clé de Luhn sur l'ISIN, **téléchargement réel d'une cotation** avec mesure de profondeur, et **concordance de la raison sociale** rapportée par le provider. Ce dernier attrape le cas Seb / Skandinaviska Enskilda Banken à 0.19 de similarité. La spec disait que l'étape serait « manuelle et fastidieuse » sans fournir d'outil, alors qu'elle identifiait le risque.
>
> **57 titres chargés sur 59 au CSV.** Banco Santander et Amadeus écartés : 3 barres hebdomadaires chez yfinance, contre 26 ans pour Iberdrola, Inditex et Telefónica sur le même marché.

**Piège à éviter :** ne pas partir directement du site d'un indice. Vérifier chaque symbole en tirant une cotation et en comparant le dernier cours à une source indépendante. Un mapping faux ne se voit jamais - il produit simplement une belle courbe pour la mauvaise société.

---

### L2 - Ingestion des cours · 2 j  ✅

Collecteur Stooq, normalisation, chargement idempotent, backfill hebdomadaire 30 ans, quotidien 3 ans, export Parquet de la couche froide, journal d'ingestion.

**Acceptation :** ≥ 95% des titres ont ≥ 15 ans d'historique hebdomadaire ; le job relancé deux fois de suite produit un état identique ; l'archive Parquet est relisible.

> **⚙ Fait avec yfinance, Stooq étant inaccessible (D-B).** 122 000 barres sur 57 titres, ~6 min, dominé par le débit ménagé. Chargement par `COPY` en table de transit puis un seul `insert … select`, ce qui fait passer le backfill d'heures à secondes par titre.
>
> **Dette T8 : l'archive Parquet est un miroir du chaud, pas une couche plus profonde.** `export_cold.py` relit `bars`, et aucun job ne descend sous 3 ans de quotidien. La stratégie deux températures n'en a qu'une.

---

### L3 - Corporate actions et qualité · 2 à 3 j  ✅

Collecteur yfinance pour splits, dividendes et nombre d'actions. Calcul des facteurs d'ajustement. Les neuf contrôles qualité du doc 02 §5. **Le filtre de dilution.**

**Acceptation :** les cas connus sont correctement détectés. Jeu de test minimal : un split récent sur une grande valeur, une dilution massive sur Atos ou Casino, un titre à trous de cotation, une divergence Stooq/yfinance.

> **⚙ Les 9 contrôles sont livrés, mais deux critères d'acceptation sont devenus inexécutables.** La *dilution massive sur Atos ou Casino* : ces titres sont hors univers, le filtre est donc éprouvé sur données synthétiques - *cela teste la règle, là où un titre réel ne ferait que la constater*. La *divergence Stooq/yfinance* : impossible, et pas seulement faute de seconde source - `source_id` n'est pas dans la clé primaire de `bars` (dette T3).
>
> **Trois contrôles ne couvrent que 3 ans sur 26** (dette T7) : saut de cours, série figée et trou de cotation filtrent `freq='1d'`, donc **aucun ne s'applique à la série hebdomadaire qui porte la régression**.

*C'est le lot où l'on découvre à quel point les données gratuites sont sales. Prévoir de le dépasser.*

---

### L4 - Moteur analytique · 3 à 4 j  ✅

Ajustement log-linéaire, diagnostics complets (ADF `ct`, DF-GLS, KPSS, Durbin-Watson, demi-vie, intervalle de confiance sur la racine AR), verdict de qualité, statistiques de régime, **écriture historisée dans `regression_fits`**.

**Acceptation :**
- sur un jeu synthétique de pente et de σ connus, les paramètres sont retrouvés à 1% près
- sur une marche aléatoire pure simulée, le verdict est majoritairement `weak` ou `rejected` - **c'est le test qui vérifie que le système ne se ment pas à lui-même**
- l'ADF est bien appelé avec `regression="ct"` sur le log-prix et non sur les résidus (test unitaire dédié, c'est l'erreur la plus coûteuse et la plus silencieuse)
- deux exécutions à la même `as_of_date` produisent des paramètres identiques

> **⚙ Le critère « paramètres retrouvés à 1% près » n'est pas atteignable, et ce n'est pas un défaut du code.** L'erreur-type relative de σ̂ vaut `1/√(2(n−2))` = 2.2% sur 1 040 points : il faudrait **45 000 points** pour tenir 1%. Trois tests plus forts ont été substitués - la pente à 1% quand le rapport signal/bruit le permet, l'absence de biais sur 300 tirages (écart 0.11%), et l'écart d'un tirage unique contenu dans 3 erreurs-types. *Expliquer pourquoi un critère ne tient pas vaut mieux que le déclarer atteint.*
>
> **Dette T10 :** `dfgls_pvalue` n'est pas persistée alors que c'est elle qui alimente BHY et détermine `good`. Le verdict n'est pas reconstructible depuis la table - P5 est entamé là où il compte.

**À la fin de ce lot, le système a de la valeur.** Tout ce qui suit est de la restitution.

---

### L5 - Screener et fiche instrument · 3 j  ✅

Application Streamlit, écran screener avec ses filtres, fiche instrument avec le graphe de régression, le bandeau de diagnostics et les statistiques de régime. Thème clair et sombre. Vue tabulaire pour chaque graphe.

**Acceptation :** le graphe d'un titre est superposable à celui de Hiboo pour le même titre, aux conventions d'ajustement près. *C'est le test de non-régression le plus utile du projet, et il justifie à lui seul les 4€ d'abonnement.*

> **⚙ Le critère d'acceptation - superposition au graphe de Hiboo - n'est pas atteint, et c'est déclaré tel quel :** *« Hiboo est un service sur abonnement ; déclarer une superposition sans l'avoir constatée serait exactement la validation fictive que ce projet cherche à éviter. »* Substitut livré : `scripts/export_comparaison.py`, qui exporte la série et **annonce l'écart attendu** - facteur multiplicatif constant sur les titres à splits (L'Oréal ÷20, EssilorLuxottica ÷20.44), superposition directe sur les 26 titres sans split. Règle de lecture : *un écart constant valide la forme, un écart qui dérive signale un vrai problème.*
>
> **C'est le dernier contrôle réellement externe qui reste ouvert.** Coût : 4€ pour un mois d'abonnement DATA.

---

### L6 - Fondamentaux régime A · 2 à 3 j  ✅

Collecteur yfinance, parseur XBRL/ESEF, table de correspondance des concepts, calcul des ratios en point-in-time, verdict de cohérence prix/fondamentaux, bloc E de la fiche instrument.

**Acceptation :** ≥ 80% des titres ont ≥ 3 exercices de chiffre d'affaires et de résultat net ; les ratios recoupent une source indépendante sur un échantillon de 10 titres.

> **⚙ Dépassé sur la couverture : 100% des titres, 7 044 faits, 33 concepts.** Recoupement : capitalisation à 0.0% d'écart sur 10 titres, Price/Book 1.8 à 3.7%, marge nette à 0.0% après recomposition du TTM depuis les trimestriels ; concordance globale 85.7% sur 35 comparaisons.
>
> **Deux réserves.** Le parseur XBRL/ESEF, inclus au lot par ce document, **n'a pas été construit** - yfinance couvre le critère et ESEF n'ajouterait de la profondeur que depuis 2021. Et le recoupement n'est pas vraiment indépendant : même fournisseur, chemin de calcul différent.

---

### L6b - Couche qualité et position concurrentielle · 3 à 4 j  ✅

*Doc 08. Dépend de L6. C'est la seconde jambe de la méthode - le lot n'est pas optionnel.*

Groupes de pairs (sectoriels automatiques + manuels pour les titres suivis), calcul du ROIC et de son écart au seuil, persistance, pricing power, volatilité et classification de régime, les trois pentes d'érosion, `quality_tier`, écriture historisée dans `quality_scores`. Table `moat_assessments` avec saisie manuelle.

**Acceptation :**
- les cas du podcast se classent correctement : Nestlé en `solid`, Arkema en `cyclical`, BMW avec au moins une pente d'érosion, Atos en `eroding`
- **aucun titre ne passe en `solid` sans groupe de pairs contenant un concurrent hors Europe** - c'est le garde-fou contre la limite Lim1 du doc 08
- une évaluation de plus de 18 mois fait automatiquement basculer le titre en `unqualified`
- le calcul est reproductible : deux exécutions à la même `as_of_date` donnent le même résultat

> **⚙ Fait. Résultats : 49 `watch`, 7 `unqualified`, 1 `eroding`, 0 `solid`.** Les cas de référence du doc 08 se classent correctement - Arkema `cyclical`, BMW avec une pente d'érosion, Seb `no_moat` avec SharkNinja dans son groupe. Nestlé et Atos sont **hors univers** (suisse non éligible PEA, écarté en L1) et donc éprouvés sur données synthétiques - *cela teste la règle, là où un titre réel ne ferait que la constater*.
>
> **L'absence de `solid` est mécanique** : le garde-fou « évaluation qualitative revue par un humain » est implémenté comme condition bloquante et n'est rempli par aucun titre. **La saisie qualitative est donc le prérequis à tout quadrant cible.**
>
> **Deux critères d'acceptation restent sans verdict :** *Nestlé en `solid`* est impossible - le garde-fou humain bloque `solid` pour tous - et la péremption à 18 mois n'est pas éprouvée puisqu'aucune évaluation n'existe.
>
> **Dette T2, à corriger en priorité :** `serie_part_relative` n'est jamais passée à l'évaluateur. L'érosion ne compte que 2 pentes sur 3 et `erosion_flags = 3` est inatteignable. Correction : une ligne.

*C'est le lot le moins automatisable du projet. La constitution des groupes de pairs élargis - avec Shark Ninja face à Seb, BYD face à BMW - est un travail manuel de jugement, pas de code. Prévoir d'y passer du temps sur les 20 à 30 titres réellement suivis, et de laisser les autres en sectoriel automatique.*

---

### L7 - Orchestration et rapport hebdomadaire · 2 j  ⬜ **priorité 1**

Crons, génération du rapport HTML, envoi, archivage, écran de qualité des données, alerte en cas d'échec de job.

**Acceptation :** le cycle complet du dimanche tourne sans intervention et produit un rapport lisible. Un échec de job déclenche une alerte.

**À ce stade le système est complet et autonome, sur ses deux jambes.** Total : **20 à 25 jours-homme.**

> **⚙ Non fait, et c'est la priorité absolue.** Aucun cron d'ingestion, de régression ni de rapport ; un seul cron installé sur le VPS Lightsail, le keepalive. Le cycle est aujourd'hui une séquence manuelle, et six commandes prescrites par le README pointent vers des fichiers `scripts/` inexistants (la logique est dans `jobs/`, les enveloppes CLI manquent).
>
> **Le principe P5 - l'historisation hebdomadaire - ne produit sa valeur que par régularité.** Un pipeline lancé quand on y pense ne bâtit pas un jeu hors échantillon. **Chaque semaine sans orchestrateur est une observation définitivement perdue** : c'est le seul élément de dette du projet qui ne se rattrape jamais.

---

### L8 - Vue sectorielle et portefeuille · 2 à 3 j  ⬜

Métriques relatives au secteur, écran sectoriel, saisie et suivi des positions avec thèse écrite, analyse de concentration et de corrélation.

---

### L9 - Extraction PDF à la demande · 3 à 4 j  ⬜

Collecteur API AMF, stockage des documents, chaîne d'extraction LLM, contrôles de cohérence comptable, score de confiance, revue manuelle, traçabilité jusqu'à la page source.

*Premier lot où un LLM intervient - et sur la seule tâche où il est vraiment non substituable.*

---

## 2. Séquencement

```
L0 ──▶ L1 ──▶ L2 ──▶ L3 ──▶ L4 ──▶ L5 ─────────▶ L7
                       │              │           ▲
                       └──▶ L6 ──▶ L6b ──▶ L8 ────┤
                                    │             │
                                    └──▶ L9 ──────┘
```

L6 peut démarrer en parallèle de L4 dès que L3 est fini. **L6b est le prérequis de la matrice qualité × prix**, donc du rapport hebdomadaire complet.

## 3. Chemin de scalabilité, sans réécriture

| Déclencheur | Action | Effort |
|---|---|---|
| > 1 000 titres | Migration Supabase → Postgres sur VPS (`pg_dump \| psql`) | 0.5 j |
| > 10 M lignes dans `bars` | Sous-partition RANGE par année, ou hypertable TimescaleDB | 1 j |
| Ajout d'une classe d'actif | Ligne dans `asset_classes` + politique + collecteur | 1 à 2 j |
| Ajout d'un pays | Entrées dans `exchanges` + mapping de symboles | 0.5 j |
| Changement de méthode | Incrément de `method_version`, recalcul, comparaison | 0.5 j |

**Aucune de ces évolutions n'exige de retoucher au modèle de données.** C'est le résultat des choix du doc 01, et c'est ce qu'on achète en acceptant un schéma plus riche que nécessaire au départ.

## 4. Où ça va déraper - pronostic honnête

| Risque | Probabilité | Impact | Mitigation |
|---|---|---|---|
| Mapping de symboles plus long que prévu | **Élevée** | +2 à 3 j sur L1 | ✅ traité par `verify_universe.py` - triple contrôle automatisé |
| ~~Historiques Stooq plus courts qu'annoncé~~ · **Stooq inaccessible** | ✅ **survenu** | Source unique | Aucune - à arbitrer (D-B) |
| Rate limiting yfinance sur le backfill | ✅ **survenu** | Lenteur | Débit ménagé 2 s, backoff. *Cache disque non construit - T23* |
| Corporate actions incomplètes | **Élevée** | Régressions faussées | Détection par saut + revue manuelle |
| Parsing XBRL plus pénible que prévu | Moyenne | +2 j sur L6 | Se limiter à 30 concepts, yfinance en repli |
| **Groupes de pairs élargis longs à constituer** | **Élevée** | +2 j sur L6b | Manuel sur 20-30 titres seulement, sectoriel auto ailleurs |
| **5 ans de fondamentaux trop courts pour la persistance** | **Certaine** | Qualité en confiance `low` | Assumé et affiché ; régime B sur les titres suivis |
| Volume Supabase dépassé | Faible | Migration anticipée | Le chemin est prévu, 0.5 j |
| Extraction LLM peu fiable sur les vieux PDF | Moyenne | L9 dégradé | Revue manuelle, périmètre restreint |

**Le risque dominant n'est pas technique, c'est le référentiel.** Constituer et vérifier des centaines de mappings de symboles est fastidieux, sans intérêt intellectuel, et c'est ce sur quoi le projet peut s'enliser. *⚙ Le risque s'est matérialisé mais a été traité par l'outillage : `verify_universe.py` automatise les trois contrôles, et l'univers s'est stabilisé à 57 titres plutôt que 250.* **Recommandation : faire L1 sur 50 titres, aller jusqu'à L5 avec ces 50, voir le système fonctionner, puis élargir. *⚙ Suivie : 57 titres, et le système est allé jusqu'à L6b sans élargir.*** Un système qui marche sur 50 titres motive l'élargissement ; un référentiel de 250 lignes à saisir avant de rien voir, non.

## 5. Ce qui suit, et n'est pas dans cette spec

**Phase 2 - couche agentique.** Agent producteur de thèse, agent adverse, juge, sur les 10 à 20 titres du screener. Conditionné à un système de données stable.

**Phase 2bis - qualité assistée.** Agent de synthèse documentaire produisant les `moat_assessments` : lecture des rapports annuels et de la presse sectorielle, extraction des menaces citées et des parts de marché mentionnées, avec traçabilité vers les sources. Revue humaine obligatoire avant validation.

**Phase 3 - élargissement.** ETF et indices d'abord - c'est la réponse à « quand acheter tel ETF » -, matières premières ensuite. La crypto reste hors modèle.

**Phase 4 - exploitation de `regression_fits`.** Au bout de 12 à 24 mois d'historisation, analyse du comportement effectif des titres après signal. **C'est le seul backtest sans hypothèse contestable que le projet produira**, et il ne coûtera qu'une requête.

---

## À challenger en priorité

1. **Démarrer à 50 titres plutôt que 250.** Je le recommande fortement. Le référentiel est le point d'enlisement le plus probable et le moins gratifiant.
2. **L4 avant L5.** Tentation inverse : faire l'interface tôt pour voir quelque chose. Mais une belle interface sur des régressions fausses est pire que pas d'interface.
3. **L9 en dernier.** L'extraction PDF est la partie la plus amusante et la moins urgente.
4. **Les 20 à 25 jours sont optimistes** et supposent qu'on ne découvre pas de mauvaise surprise sur les sources. Une fourchette réaliste est 30 à 35 jours, l'écart tenant presque entièrement à L1, L3 et L6b.
5. **L6b n'est pas un lot optionnel malgré sa position tardive.** Sans lui, le système produit des signaux de prix non qualifiés - c'est-à-dire la moitié de la méthode, et la moitié qui produit les value traps. Si le budget se réduit, couper L8 et L9, jamais L6b.
