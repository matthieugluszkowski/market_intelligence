# 07 - Expression de besoin, périmètre et couverture

**Ce document est le point d'entrée du jeu de specs.** Il énonce ce qui est demandé, avant que les documents 00 à 06, 08 et 09 n'énoncent comment le faire. La numérotation reflète l'ordre de production, pas l'ordre de lecture - voir §8.

> **⚙ État au 19 août 2026 : le système est construit jusqu'au lot L6b.** 57 titres, 122 000 barres, 7 044 faits financiers, 169 tests, 3 écrans. L7 à L9 non entamés - donc **ni orchestration, ni rapport hebdomadaire**. Les critères de succès du §7 ne sont pas encore cochés : voir doc 09 pour l'état réel et le registre de dette.

---

## 1. Origine

Le projet naît d'un échange entre Matthieu Gluszkowski et Nicolas, le 27 juillet 2026.

### 1.1 L'intuition initiale

Matthieu décrit une architecture en cinq pools d'agents IA :

1. **Collecteurs** - surveillent toutes les bourses, l'or, l'immobilier, le bitcoin, Solana, Ethereum ; enregistrent les tendances heure par heure ; *« il fait la météo »*
2. **Analystes** - pour chaque tendance, cherchent une explication rationnelle sur les exchanges, les journaux, les réseaux sociaux
3. **Contrôleurs** - vérifient dans le temps si les hypothèses se reproduisent et si la qualité de l'analyse est élevée
4. **Investisseurs-anticipateurs** - à partir des analyses validées, anticipent les mouvements et enregistrent les opportunités dans un registre, avec scoring de confiance et échelle de résultat prédictive
5. **Investisseurs-exécutants** - prennent position sur les différents exchanges

*« C'est une grosse machinerie mais tu en dis quoi ? »*

### 1.2 Ce que les deux podcasts ont apporté

**Marie de Raismes (Hiboo)** - la méthode : acheter un leader à position concurrentielle durable, quand son cours est nettement sous sa tendance longue, et tenir 5 à 10 ans. L'outil de mesure : régression log-linéaire sur 20 à 30 ans, bandes d'écart-type, achat sous −2σ.

**Stéphane Dothée (Donatech)** - la gestion des agents et les biais : le LLM renforce les biais de son utilisateur ; l'avocat du diable comme antidote au biais de confirmation ; human in the loop systématique ; la mise en garde sur l'agentique appliquée aux finances.

---

## 2. Ce que Nicolas veut

Énoncé tel qu'exprimé, sans reformulation.

| # | Besoin | Statut |
|---|---|---|
| B1 | Un outil de stock picking pour le **PEA Crédit Mutuel**, puis d'autres exchanges type eToro | Cœur de la v1 |
| B2 | L'outil doit **aider à décider** quelles positions prendre et fermer | Cœur de la v1 |
| B3 | **Un rapport hebdomadaire** des opportunités liées à l'analyse de prix | Cœur de la v1 |
| B4 | Reproduire la **méthode statistique de décote** décrite par Hiboo | Cœur de la v1 |
| B5 | **Ne pas payer** le service Hiboo, le recréer | Contrainte |
| B6 | MVP sur un **VPS Amazon déjà possédé**, BDD type Supabase, **utiliser l'existant ou le gratuit** | Contrainte |
| B7 | Développer **pas à pas**, pas d'usine à gaz d'emblée | Contrainte de méthode |
| B8 | **Analyse concurrentielle** et position de leader - *« un élément très important »* | **Doc 08** |
| B9 | Couvrir **actions, ETF, matières premières, bitcoin, ethereum** | §4 |
| B10 | Savoir **quand il est opportun d'acheter tel ou tel ETF** - l'ETF est-il cher aujourd'hui ? | §4 |
| B11 | Multi-agents en **temps 2**, pas en v1 | Phase 2 |

---

## 3. Le positionnement, et ce qu'il implique techniquement

> *« Je ne veux pas faire une société de gestion, nous ne gérons l'argent de personne. Ce que je veux, c'est un outil : aider à reprendre la main sur mon épargne, à comprendre ce que j'achète et à devenir acteur de mon choix - l'inverse d'un ETF où, au fond, on ne sait pas vraiment ce qu'on détient. On ne promet pas "on bat l'indice, faites-nous confiance" ; on donne les clés d'analyse pour décider par soi-même. »*

Ce n'est pas une déclaration d'intention décorative. **Trois conséquences techniques directes en découlent**, et elles expliquent plusieurs choix qui pourraient sinon sembler arbitraires.

### C1 - Aucune boîte noire, jamais

« Comprendre ce qu'on achète » interdit le score composite sur 100 qui agrège l'incomparable. Chaque chiffre affiché doit être décomposable jusqu'à sa source.

*→ décision D10, doc 06.*

### C2 - L'outil propose, il n'exécute pas

« Devenir acteur de son choix » interdit l'automatisation de la prise de position - qui était pourtant le cinquième pool de l'architecture initiale. Le système s'arrête à la décision.

*C'est aussi la position de Dothée : « si vous faites de l'agentique, peut-être commencer par trier vos mails plutôt que gérer vos investissements ».*

### C3 - Le doute s'affiche

« Ne pas promettre » interdit d'afficher une probabilité de gain, un objectif de cours, ou un verdict binaire là où les données ne tranchent pas.

*→ principe I2, doc 04. C'est aussi ce qui justifie l'intervalle de confiance sur la racine autorégressive plutôt qu'un booléen « stationnaire ».*

---

## 4. Périmètre d'actifs : ce qui est couvert, comment, et pourquoi

Chaque classe demandée est traitée. Elles ne le sont pas de la même façon, et l'écart mérite explication.

| Classe | Couvert | Méthode | Phase |
|---|---|---|---|
| **Actions Europe (PEA)** | ✅ | Log-linéaire 20 ans + qualité (doc 08) | v1 |
| **Actions hors Europe** | ✅ | Identique | Extension |
| **ETF** | ✅ | Log-linéaire 30 ans **sur l'indice répliqué** | Phase 3 |
| **Indices** | ✅ | Log-linéaire 30 ans | Phase 3 |
| **Matières premières, or** | ✅ | Log-linéaire **sur prix déflatés**, fenêtre post-1971 | Phase 3 |
| **Immobilier coté (SIIC, REIT)** | ✅ | Comme les actions | Extension |
| **Immobilier physique** | ❌ | Hors méthode | — |
| **Bitcoin, Ethereum, Solana** | ⚠️ | **Exclus du modèle log-linéaire** | À part |

### Sur les ETF - la réponse à B10

C'est le point le plus intéressant du périmètre, et il répond directement à la question posée.

**Un ETF récent n'a pas 30 ans d'historique, mais l'indice qu'il réplique en a.** La régression se calcule sur l'indice ; le z-score est attribué à l'ETF par un lien de référence. Sans cette bascule, aucun ETF n'est analysable et B10 reste sans réponse.

Le système produira donc, chaque semaine, la position du S&P 500, du MSCI World, du CAC 40 et du Stoxx 600 sur leur propre droite - **la réponse chiffrée et vérifiable à « l'ETF est-il cher aujourd'hui »**, plutôt qu'une affirmation à croire sur parole. C'est l'exemple type de ce que le positionnement du §3 réclame.

*Précision utile : Marie affirme dans le podcast que les indices américains sont hauts et le CAC nettement moins survalorisé. Le système permettra de le vérifier, de le contredire, et surtout de le suivre dans le temps.*

### Sur les matières premières

La tendance nominale d'une matière première est essentiellement de l'inflation - il faut déflater. Et **la rupture de Bretton Woods en 1971 interdit toute régression qui la traverse** : la fenêtre commence après.

### Sur bitcoin, ethereum et solana

**Exclus du modèle log-linéaire, et il faut être précis sur le motif.**

L'argument faible serait « la pente est absurde » - environ 58% annualisé sur dix ans pour le bitcoin, davantage si l'on remonte plus loin. **L'argument réel est que la pente n'est pas un paramètre stable : elle dépend entièrement de la date de départ choisie.** C'est la définition d'un régime non stationnaire, et aucun modèle à tendance déterministe ne s'y applique. Solana, avec un historique encore plus court, l'illustre en pire.

*Ce n'est pas un refus de couvrir la classe. C'est le constat que l'outil de mesure ne s'y applique pas. La forme fonctionnelle candidate est log-log, et elle exige son propre modèle, ses propres diagnostics et sa propre validation - pas un paramètre différent.*

### Sur l'immobilier

Mentionné dans le mail d'origine. L'immobilier **coté** entre naturellement dans le périmètre : une SIIC est une action. L'immobilier **physique** n'a ni série de prix par actif ni liquidité, et la méthode ne s'y transpose pas.

*C'est aussi le domaine où l'apport marginal d'un outil serait le plus faible ici - l'expertise existe déjà.*

---

## 5. Ce qui est retenu et ce qui est écarté de l'architecture initiale

Traitement explicite des cinq pools, parce qu'écarter sans dire pourquoi serait le pire des deux mondes.

| Pool | Sort | Motif |
|---|---|---|
| **1. Collecteurs, météo horaire** | ⚠️ **Fortement réduit** | Collecte conservée en fin de journée, granularité horaire abandonnée. Une machine haute fréquence pour des décisions à 5-10 ans : 95% de l'effort porte sur ce qui n'influence pas la décision. Et l'effet de second ordre est pire que le premier - plus le feedback est fréquent, plus le rendement accumulé baisse (Thaler, Tversky, Kahneman & Schwartz, 1997) |
| **2. Analystes du « pourquoi »** | ❌ **Écarté** | Un LLM produit toujours une explication plausible : taux de refus proche de zéro, donc 100% de couverture et 0% d'information. Marie le dit elle-même : *« on explique a posteriori mais ce n'est pas ça la vraie cause »*. Ce bruit deviendrait un input de décision |
| **3. Contrôleurs d'hypothèses** | ✅ **Conservé, transformé** | L'intuition - vérifier que ça se reproduit - est juste et c'est la meilleure idée du design initial. Mais tester des milliers d'hypothèses produit 50 confirmations aléatoires pour 1 000 tests à 5%. Réalisé autrement : par l'historisation de `regression_fits`, qui teste **une** hypothèse en temps réel, sans multiplicité |
| **4. Registre d'opportunités avec scoring** | ⚠️ **Conservé sans le scoring** | Le registre devient `screener_snapshots`. Le score de confiance est écarté : il produit une précision fausse, et la précision fausse fait prendre des positions plus grosses. L'échelle de résultat prédictive est remplacée par les **statistiques de régime** - durée observée des épisodes, baisse supplémentaire médiane - qui décrivent au lieu de prédire |
| **5. Exécution des positions** | ❌ **Écarté** | Contradiction directe avec C2. C'est aussi la seule partie irréversible du système |

**Ce qu'il faut retenir de l'architecture initiale : la séparation générateur / vérificateur.** Elle est juste. Mais elle s'applique à la **thèse d'investissement**, pas au mouvement de prix - un agent produit la thèse, un agent adverse la démolit, un juge tranche. Sur 20 titres par semaine, pas sur 5 000 ticks par heure. C'est le design de la phase 2, et c'est exactement l'avocat du diable de Dothée.

---

## 6. Matrice de couverture

| Besoin | Couvert par | Phase |
|---|---|---|
| B1 - Stock picking PEA | Docs 01 à 05, univers Europe PEA. *⚙ 586 titres au 2026-08-21* | v1 |
| B2 - Aide à la décision | Doc 04, matrice qualité × prix du doc 08 | v1 |
| B3 - Rapport hebdomadaire | Doc 04 §4, job `weekly_full` du doc 02 | v1 |
| B4 - Méthode de décote | Doc 03 §1 à §5 | v1 |
| B5 - Ne pas payer | Doc 02, sources gratuites. *⚙ Tenu à 100%. Réserve : 4€ un mois pour valider contre la référence - **toujours pas fait**, doc 06 PO8* | v1 |
| B6 - VPS et gratuit | Doc 00 §5, Supabase free. *⚙ ~15 Mo mesurés sur 500* | v1 |
| B7 - Pas à pas | Doc 05, 11 lots, chacun observable. *⚙ 8 faits* | v1 |
| **B8 - Analyse concurrentielle** | **Doc 08 en entier** | v1 partiel, phase 2 pour le qualitatif |
| B9 - Multi-actifs | §4 ci-dessus, `asset_classes` et `regression_policies` du doc 01 | v1 structurel, phase 3 effectif |
| B10 - Quand acheter un ETF | §4 ci-dessus, régression sur l'indice répliqué | Phase 3 |
| B11 - Agents en temps 2 | Lot L9 puis phase 2 | Phase 2 |

**Aucun besoin exprimé n'est sans réponse.** Deux sont réduits par rapport à l'énoncé initial - la météo horaire et le scoring prédictif - et le §5 dit pourquoi.

---

## 7. Critères de succès

Ce à quoi on jugera le projet, sur trois horizons. **À fixer maintenant, parce qu'après on s'arrange toujours avec ses critères.**

### À 3 mois - le système existe
- [x] Le cycle tourne sans intervention manuelle · **⚙ oui depuis le 2026-08-21 : cron de 8 h sur le VPS, `scripts/cycle.py`. Le rapport hebdomadaire, lui, n'existe pas encore**
- [ ] Un rapport arrive chaque dimanche · **⚙ non : L7**
- [ ] Le graphe d'un titre est superposable à celui de Hiboo · **⚙ non constaté** - l'export de comparaison existe, l'abonnement à 4€ n'a pas été pris
- [ ] Au moins une décision d'investissement a été éclairée par l'outil · *à toi de le dire*

> **⚙ Ce qui est acquis en revanche et n'était pas au tableau :** le système dit qu'il ne sait pas. 0 `good` sur 57 titres, 0 `solid`. C'est le comportement voulu, et c'est ce qu'un screener ordinaire n'aurait jamais dit.

### À 12 mois - le système accumule
- [ ] 52 clichés hebdomadaires historisés dans `regression_fits`
- [ ] Premières statistiques réellement hors échantillon
- [ ] Chaque position détenue a une thèse écrite **avant** l'achat
- [ ] Coût de maintenance mesuré, comparé aux 48€/an de l'alternative

### À 24 mois - le système tranche
- [ ] Les fits historisés permettent de dire si un signal à −2σ a une valeur prédictive
- [ ] **Ce verdict peut être négatif, et le projet aura quand même produit sa valeur** : savoir que la méthode ne fonctionne pas vaut mieux que l'avoir crue pendant dix ans

### Le critère non financier, et probablement le principal
- [ ] *« Je comprends ce que je détiens »* - mesurable par le fait que chaque ligne a une thèse écrite, un z-score d'entrée, un verdict de qualité et un groupe de pairs identifié

*Ce dernier critère est atteignable indépendamment de la performance, et c'est ce qui rend le projet rationnel même si l'edge statistique s'avère nul.*

---

## 8. Ordre de lecture

La numérotation reflète l'ordre de production. L'ordre de lecture est celui-ci :

| Ordre | Document | Rôle |
|---|---|---|
| 1 | **07 - Expression de besoin** | Ce document. Le quoi et le pourquoi |
| 2 | **00 - Vue d'ensemble** | Principes d'architecture, périmètre, volumétrie |
| 3 | **08 - Position concurrentielle** | La jambe qualité de la méthode |
| 4 | **03 - Moteur analytique** | La jambe prix |
| 5 | **01 - Modèle de données** | Le schéma |
| 6 | **02 - Ingestion et sources** | D'où viennent les données |
| 7 | **04 - Screener et dashboard** | La restitution |
| 8 | **05 - Roadmap et lots** | Comment on le construit |
| 9 | **06 - Décisions et points ouverts** | Ce qui reste à trancher |
| 10 | **09 - État d'implémentation et écarts** | **Le système tel qu'il est.** À lire avant toute reprise de développement |

---

## À challenger en priorité

1. **L'abandon de la météo horaire** est la réduction la plus forte par rapport à l'idée d'origine. Elle est motivée par un argument comportemental documenté, pas par une contrainte technique.
2. **L'écart complet du pool « expliquer le pourquoi »** est ma position la plus tranchée. Un compromis existe en PO6 du doc 06 : une section strictement factuelle, sans interprétation causale.
3. **Le scoring de confiance remplacé par des statistiques descriptives** rend le système moins immédiat à lire. C'est délibéré.
4. **Bitcoin et Ethereum exclus du modèle** alors qu'ils figurent explicitement dans le besoin B9. Ce n'est pas un refus de la classe d'actif, c'est le constat que l'outil ne s'y applique pas - et proposer une droite de régression sur bitcoin serait précisément le genre de fausse rigueur que le projet combat ailleurs.
5. **Les critères de succès à 24 mois admettent un verdict négatif.** C'est inhabituel dans un cahier des charges, et c'est le seul moyen que le test soit honnête.
