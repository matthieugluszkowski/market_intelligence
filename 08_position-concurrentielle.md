# 08 - Position concurrentielle, leadership et qualité

> **État : implémenté (lot L6b).** 57 scores, 6 groupes de pairs manuels avec 14 concurrents hors univers. Résultats : 49 `watch`, 7 `unqualified`, 1 `eroding`, **0 `solid`**. Écarts signalés en ligne par des blocs `⚙ Réel` ; registre complet doc 09.

> *« Il faut acheter une action de qualité, et globalement la qualité c'est la position concurrentielle. »*
> *« Choisis un leader et regarde si sa position concurrentielle est durable. »*
> — Marie de Raismes

---

## 1. Pourquoi ce document existe, et pourquoi il est le plus difficile

Les documents 01 à 06 traitent bien le **prix**. Ils traitent mal la **qualité**. Or la méthode repose sur deux jambes, et le prix n'en est qu'une : Marie répète que la droite de régression est *« un outil statistique, donc il a ses limites, il faut toujours le compléter par l'analyse fondamentale »*, et son critère de qualité n'est ni la croissance ni la marge - c'est **la position concurrentielle durable**.

**La difficulté est d'une autre nature que celle du prix.** Le prix se calcule : on a la série, on ajuste, on obtient un z-score. La position concurrentielle durable contient deux mots qui posent deux problèmes distincts :

| | Nature | Mesurable ? |
|---|---|---|
| **Position** | Où en est l'entreprise aujourd'hui | Oui, par proxies |
| **Durable** | Y sera-t-elle dans dix ans | **Non. Jamais.** |

Le second mot est une affirmation sur l'avenir. Aucune donnée historique ne le démontre. Kodak affichait un ROIC élevé et une marque mondialement indépassable en 1998 ; Nokia détenait 40% du marché mondial du mobile en 2007.

**Position retenue :** on ne mesure pas la durabilité. On mesure la **position** et on teste l'**absence d'érosion**. C'est une réfutation, pas une confirmation - et c'est intellectuellement le seul geste disponible.

---

## 2. Le cadre : trois questions, dans cet ordre

### Q1 - L'entreprise est-elle leader ?
Position relative à ses concurrents. Mesurable par proxies.

### Q2 - Cette position produit-elle de la rente ?
Être gros ne suffit pas. Un leader qui ne dégage pas de rendement supérieur au coût du capital n'a pas de barrière, il a de la taille. Mesurable.

### Q3 - Cette rente s'érode-t-elle ?
**C'est la question qui décide, et c'est celle que personne n'affiche.** Un leader dont la rente s'érode depuis cinq ans n'est pas un leader décoté - c'est un leader en train de perdre sa position, et le marché a probablement raison de le vendre.

---

## 3. Q1 - Mesurer le leadership

### 3.1 Part de marché relative

```
part_relative = CA(titre) / CA(plus grand pair du groupe)
```

| Valeur | Lecture |
|---|---|
| ≥ 1.0 | Leader du groupe |
| 0.5 à 1.0 | Challenger crédible |
| < 0.5 | Suiveur |

*Métrique classique du BCG, et le proxy le plus proche du « leader » de Marie. Elle a un défaut majeur, traité en §7.*

### 3.2 Échelle absolue et couverture géographique

CA total, nombre de pays d'implantation, part du CA réalisée hors marché domestique.

*Marie insiste sur ce point à propos du CAC 40 : « un L'Oréal, un Air Liquide, un Saint-Gobain, ce sont des leaders mondiaux, ils font 75% de leur chiffre d'affaires hors de France ». Un leader national et un leader mondial ne sont pas la même chose face à un entrant.*

### 3.3 Stabilité du rang

Rang du titre par CA dans son groupe de pairs, sur cinq ans. **Un rang stable vaut mieux qu'un bon rang instable.**

---

## 4. Q2 - Mesurer la rente

### 4.1 L'indicateur central : ROIC et son écart au coût du capital

C'est le test quantitatif du moat, et il repose sur un raisonnement économique simple : **en concurrence libre, le rendement du capital converge vers son coût.** Un rendement durablement supérieur signale qu'une barrière empêche cette convergence.

```
NOPAT              = EBIT × (1 − taux d'IS effectif)
Capitaux employés  = capitaux propres + dette nette
ROIC               = NOPAT / capitaux employés moyens
Écart de rente     = ROIC − seuil de coût du capital
```

**Choix méthodologique : un seuil fixe plutôt qu'un WACC estimé par titre.**

Estimer un WACC titre par titre demande un bêta, une prime de risque marché et un coût de la dette - trois paramètres bruités qui, combinés, produisent un chiffre d'une fausse précision remarquable. Deux analystes obtiennent 7% et 11% sur la même société, et l'écart de rente change de signe.

**Alternative retenue, en deux lectures complémentaires :**
- **seuil absolu** à 8%, valeur conventionnelle et transparente
- **seuil relatif** : ROIC du titre − ROIC médian de son groupe de pairs

La seconde est plus robuste, parce que l'essentiel des biais d'estimation est commun au secteur et s'annule dans la différence.

### 4.2 Persistance de la rente

**Plus informatif que le niveau.**

```
persistance = nombre d'exercices où ROIC > seuil, sur les N disponibles
```

Un ROIC à 25% une année sur cinq est un accident cyclique. Un ROIC à 14% cinq années sur cinq est une barrière.

*Contrainte à assumer : avec 5 ans de fondamentaux gratuits, on mesure la persistance sur 5 points - **⚙ 4 exercices en pratique**. C'est court. C'est le meilleur argument en faveur du régime B - l'extraction PDF sur 15 ans pour les titres réellement suivis - ou d'un abonnement données.*

### 4.3 Pricing power par la stabilité de la marge brute

La capacité à répercuter l'inflation sur ses prix sans perdre de volume est la signature la plus directe d'une marque forte.

```
pricing_power = f(niveau moyen de la marge brute,
                  écart-type de la marge brute sur 5 ans,
                  tendance de la marge brute)
```

Une marge brute stable **à travers un cycle** est plus révélatrice qu'une marge brute élevée. Les années 2021-2023, avec leur choc inflationniste, constituent un test naturel d'une qualité rare : les entreprises qui ont maintenu leur marge brute ont démontré leur pricing power en conditions réelles.

*Exploiter ce test naturel est un des rares avantages que procure la fenêtre courte de 5 ans.*

### 4.4 Volatilité du ROIC et distinction cyclique

Un ROIC très volatil ne signifie pas absence de qualité - il signifie **cyclicité**, ce qui est un autre régime d'investissement.

| Profil | ROIC | Volatilité | Traitement |
|---|---|---|---|
| Rente | élevé | faible | Moat classique - Nestlé, L'Oréal |
| Cyclique | moyen sur cycle | forte | **Régime distinct**, jugé sur le ROIC moyen de cycle |
| Érosion | déclinant | variable | Signal d'alerte |
| Sans barrière | ≈ seuil | faible | Ni moat ni cycle |

**La distinction cyclique est indispensable et manquait complètement aux specs.** Arkema, BMW, Benetteau - les valeurs cycliques que Marie recommande explicitement - échouent à tous les tests de moat classiques et sont pourtant des cibles légitimes. Les juger sur un ROIC ponctuel est un contresens : *« toute la question d'une boîte cyclique, c'est d'acheter en bas de cycle »*.

**Règle dérivée :** un titre marqué `cyclical` est évalué sur le ROIC **moyen sur cycle complet**, jamais sur le dernier exercice, et son érosion se mesure de pic à pic.

> **⚙ Réel : le régime est déclaré à la main, et c'est le bon choix.** La détection automatique a produit deux erreurs symétriques. D'abord Arkema classé `eroding` donc value trap, alors que ce document dit *bas de cycle, pas érosion*. Puis, après correction par la volatilité, l'inverse : un ROIC qui s'effondre de 18% à 2% a une volatilité très élevée et sortait `cyclical`, donc protégé du verdict d'érosion - **c'était exactement le cas Atos.**
>
> Un discriminant a été ajouté et il est juste : **un cycle redescend et remonte, un effondrement est monotone** (`R2_TENDANCE_MONOTONE = 0.70`). **Mais il ne suffit pas.** Avec quatre exercices, la fenêtre ne couvre souvent que la *descente* d'un cycle, et une descente de cycle est **statistiquement indiscernable d'une érosion** : même pente, même monotonie. C'est la limite Lim2 de ce document, et aucune amélioration du code ne la lève.
>
> D'où 12 cycliques déclarés à la main - *ce document les identifie lui-même par leur métier, pas par un test*. À revoir à huit exercices.
>
> **Ni le ROIC moyen de cycle ni l'érosion pic-à-pic ne sont implémentés** : un cyclique renvoie `watch` sans condition, avec le motif `erosion_non_mesuree_sur_cyclique_historique_trop_court`.

### 4.5 Proxies d'actifs incorporels

| Source du moat | Proxy |
|---|---|
| Marques | Intensité publicitaire et marketing / CA |
| Brevets et technologie | Intensité de R&D / CA, tendance |
| Coûts de transfert | Récurrence du CA, taux de rétention si publié |
| Effet de réseau | Non mesurable en automatique - qualitatif |
| Avantage de coût | Marge opérationnelle relative à celle des pairs |
| Échelle efficiente | Part de marché relative + intensité capitalistique |

*Les deux premières lignes sont calculables quand la ligne comptable est publiée, ce qui est irrégulier en Europe. Les autres relèvent de la jambe qualitative.*

---

## 5. Q3 - L'indicateur d'érosion : le vrai apport de ce document

### 5.1 Définition

L'érosion est la **tendance**, pas le niveau. Trois pentes, calculées par régression sur les 5 dernières années :

| Composante | Ce qu'elle capte |
|---|---|
| Pente du ROIC | La rente se contracte-t-elle ? |
| Pente de la marge brute | Le pricing power se dégrade-t-il ? |
| Pente de la part de marché relative | Le leader perd-il du terrain ? |

> **⚙ Dette T2, la plus coûteuse du système : l'érosion ne compte que deux pentes sur trois.** `compute_quality.py` ne passe jamais la série de part de marché relative à l'évaluateur. `share_slope_5y` est toujours `null`, **`erosion_flags` est borné à 2, et le niveau 3 - « érosion confirmée » - n'existe pas dans les données.** Aggravant : la deuxième pente exige la marge brute, que la limite Lim4 signale comme irrégulièrement publiée en Europe. **Le quadrant value trap n'a qu'un seul titre.** Correction : une ligne d'appel.

```
erosion_flags = nombre de pentes significativement négatives (0 à 3)

0    → pas d'érosion détectée
1    → surveiller
2    → érosion probable
3    → érosion confirmée : la décote n'est pas une opportunité
```

*« Significativement négative » : pente négative dont l'intervalle de confiance à 90% exclut zéro. Sur 4 à 5 points, ce test est peu puissant - il ne détectera que les érosions franches. C'est assumé : mieux vaut manquer une érosion douteuse que crier au loup sur du bruit.*

### 5.2 Pourquoi c'est le croisement qui décide

**La décote sur une position qui s'érode n'est pas une décote, c'est un ajustement de prix correct.** C'est la définition même du value trap, et c'est là qu'un investisseur value perd son argent - pas sur les titres chers, qu'il n'achète pas.

Le cadre se valide sur les cas mêmes du podcast :

| Titre | Position | Rente | Érosion | Lecture |
|---|---|---|---|---|
| **Nestlé** | Leader mondial | ROIC stable, marques fortes | Aucune sur la rente ; problèmes de direction et de réputation | Décote sur difficultés conjoncturelles - cible |
| **Seb** | Leader du petit électroménager | Marge sous pression | Partielle : cœur attaqué par Shark Ninja, mais Supor et café pro en croissance | À qualifier, pas à trancher automatiquement |
| **BMW** | Leader premium | Rente historiquement forte | **Réelle** : perte de part en Chine face à BYD, profit warning | Décote justifiée sur au moins un segment |
| **Arkema** | Leader de la chimie de spécialité | ROIC volatil, cyclique | Non applicable : régime cyclique | Bas de cycle, pas érosion |
| **Atos** | Ex-leader | Rente détruite | **Totale**, plus dilution massive | Doit sortir de l'univers |

*Marie fait ce raisonnement intuitivement - « est-ce que la question se pose de la même manière pour Stellantis que pour BMW ? Pour moi, ce n'est pas la même qualité de dossier du tout ». Ce document ne fait que le rendre explicite et reproductible.*

---

## 6. Synthèse : la matrice qualité × prix

L'écran qui manquait au dashboard.

```
                        PRIX
              décoté  (z ≤ −1.5)          cher  (z ≥ +1)
            ┌───────────────────────┬───────────────────────┐
   solide   │      ◆ LA CIBLE       │     ○ WATCHLIST       │
            │  Leader, rente        │  Leader, rente,       │
 Q          │  persistante,         │  mais payé cher.      │
 U          │  aucune érosion.      │  Attendre.            │
 A          │  → dossier à creuser  │  → suivre le prix     │
 L          ├───────────────────────┼───────────────────────┤
 I          │    ⚠ VALUE TRAP       │    ✕ À ÉVITER         │
 T  érosion │  Décoté ET position   │  Cher ET position     │
 É          │  qui se dégrade.      │  qui se dégrade.      │
            │  → le marché a        │  → sans intérêt       │
            │    probablement raison│                       │
            └───────────────────────┴───────────────────────┘
```

> **⚙ Le seul value trap détecté est LVMH** - ROIC 22.3% → 15.2% et marge brute 68.4% → 66.2% entre 2022 et 2025, les deux pentes significatives à 90%. **À lire avec trois réserves** : le ROIC reste à 15.2%, soit près du double du seuil de 8% ; la fenêtre ne compte que 4 points et démarre en 2022, année de base post-Covid atypique ; la borne haute de l'intervalle sur la marge brute est à −0.0000, soit une significativité tout juste atteinte.

**Le quadrant en bas à gauche est le plus important du système.** Il ne se contente pas d'être exclu : il est **affiché**, avec le motif. C'est la liste des titres qui ont l'air d'opportunités et n'en sont pas, et la voir chaque semaine vaut mieux que ne pas la voir.

Deux quadrants supplémentaires implicites, à traiter à part : les **cycliques en bas de cycle** (Arkema) et les **cycliques en haut de cycle**, où la lecture s'inverse - un ROIC au plus haut sur un cyclique est un signal de vente, pas de qualité.

---

## 7. Les limites, dites franchement

### Lim1 - L'univers n'est pas le marché *(la limite la plus sérieuse)*

Le groupe de pairs est construit à partir des **57 titres européens** de la base. **Or les menaces concurrentielles les plus dangereuses viennent presque toujours de l'extérieur de cet univers.**

Les cas du podcast le démontrent tous :
- **Shark Ninja**, l'agresseur de Seb, est une société américaine
- **BYD**, l'agresseur de BMW, est chinoise
- **Revolut, Lydia, Qonto**, les agresseurs des bancaires, ne sont pas cotées du tout

**Un screener sectoriel automatique va donc systématiquement sous-estimer la menace concurrentielle**, et il le fera de façon d'autant plus rassurante que le titre reste leader dans un univers qui ne contient pas son concurrent.

**Mitigation, en trois niveaux :**
1. `peer_groups` définis **manuellement** pour les titres réellement suivis *(⚙ réel : 6 groupes, 13 titres sur 57 ; **46 n'ont aucun groupe manuel**)*, incluant des concurrents hors univers, y compris non cotés
2. les pairs hors univers portent leurs données en saisie manuelle ou par extraction, sans série de prix
3. **au moins un concurrent hors Europe est obligatoire** dans tout groupe de pairs qualifié - un groupe purement européen est marqué comme incomplet

> **Révision du 2026-08-21 — un casier sectoriel n'est pas un groupe de pairs, et il ne publie plus rien.** La mitigation ci-dessus marquait le groupe automatique comme *incomplet*, ce qui l'empêchait de produire un `solid` — mais **les indicateurs relatifs continuaient d'être calculés, écrits en base et affichés**. Constaté sur EssilorLuxottica : son groupe était `AUTO:20 — Secteur Health Care`, dont les membres sont **Sanofi et UCB**. Le système comparait le ROIC d'un lunetier à celui de deux laboratoires pharmaceutiques, et l'écart de −2,56 points a servi de preuve dans la synthèse du prompt 5. Sur 57 titres calculés, **43 publiaient ainsi un écart aux pairs mesuré contre une case sectorielle**.
>
> Règle posée : `quality.groupe_comparable` — seuls un groupe issu d'un dossier concurrentiel (`DOSSIER:`), un groupe constitué à la main, ou un groupe automatique explicitement marqué complet autorisent la publication de `roic_vs_peers`, `relative_share` et `rank_by_revenue`. Sinon les trois sortent à `null`, avec le motif `indicateurs_relatifs_non_publies_groupe_non_comparable` et une explication à l'écran — jamais une case vide muette.
>
> **C'est la règle de l'indice de référence du doc 11 §8.1, appliquée ici :** afficher un chiffre dont la référence est arbitraire vaut moins que ne rien afficher, parce qu'un chiffre affiché est lu, cité, et finit dans une conclusion. Les mesures **absolues** — ROIC, écart au seuil de rente, marges, pentes d'érosion — ne changent pas, et ce sont elles qui décident du `regime` et du `quality_tier` : aucun verdict n'a bougé.

### Lim2 - Cinq ans de fondamentaux, c'est court pour une notion de durabilité

La persistance mesurée sur 4 à 5 points est faible. La contradiction est réelle : on prétend juger de la durabilité avec une fenêtre courte.

*C'est le meilleur argument pour le régime B, et c'est aussi le seul endroit du projet où j'estime qu'une dépense de données serait justifiée. Pas pour les cours - ils sont gratuits - mais pour 15 à 20 ans de ROIC.*

### Lim3 - Le moat quantitatif mesure le passé

Un ROIC élevé et persistant est la trace d'une barrière **qui a existé**. Il ne dit rien de sa résistance à une rupture technologique. C'est précisément le biais rétrospectif que le projet combat sur le prix, et il faut reconnaître qu'on l'accepte partiellement ici.

*C'est ce qui rend la jambe qualitative non optionnelle : elle est le seul endroit où l'on peut écrire « cette barrière est menacée par X », et X n'est jamais dans les comptes.*

### Lim4 - Les données sectorielles européennes sont irrégulières

La marge brute n'est pas toujours publiée sous une forme comparable. Les segments opérationnels varient. La classification ICB range parfois mal - Seb en biens de consommation durables, avec des pairs peu comparables.

*Mitigation : le groupe de pairs manuel prime toujours sur le groupe sectoriel automatique.*

---

## 8. La jambe qualitative

Ce qui ne se calcule pas mais se structure.

### 8.1 Contenu d'une évaluation

| Champ | Contenu |
|---|---|
| Sources du moat | Typologie multi-valuée : marques, brevets, coûts de transfert, effet de réseau, avantage de coût, échelle |
| Verdict de position | leader / challenger / suiveur / niche |
| Verdict de durabilité | solide / sous surveillance / en érosion / absente |
| Menaces identifiées | Texte structuré, avec l'horizon estimé |
| Groupe de pairs de référence | Y compris hors univers |
| Auteur, date, confiance | |
| **Date d'expiration** | Évaluation périmée au-delà de 18 mois |

> **⚙ Aucune évaluation qualitative n'est saisie, et c'est ce qui vide le quadrant cible.** Les deux garde-fous - concurrent hors Europe dans le groupe de pairs, et évaluation revue par un humain - sont implémentés comme conditions **bloquantes** du niveau `solid`. La seconde n'est remplie par aucun titre. **L'absence de `solid` est donc mécanique, pas empirique.**
>
> **Dette T9 :** les 6 groupes manuels sont marqués `is_complete = true` alors que tous les concurrents hors univers portent `"ca_musd": null`. Le refus de saisir des chiffres non sourcés est juste, mais `relative_share` et `rank_by_revenue` **ne peuvent donc pas être calculés contre SharkNinja ou BYD** : le garde-fou anti-Lim1 est levé avant que le calcul qu'il protège ne soit possible.

### 8.2 Pourquoi la date d'expiration compte

Les positions concurrentielles bougent lentement, mais elles bougent - et une évaluation ancienne inspire exactement la même confiance qu'une récente, ce qui est le problème. La péremption force la revue.

*Un titre dont l'évaluation est périmée reste dans le screener, mais son quadrant s'affiche comme non qualifié plutôt que comme cible.*

### 8.3 Le bon usage du LLM, en phase 2

L'évaluation qualitative est, avec l'extraction de PDF, **le second endroit où un LLM apporte une valeur réelle et non substituable** : lire dix rapports annuels et une revue de presse sectorielle, en extraire les menaces citées et les parts de marché mentionnées, produire une synthèse structurée.

C'est de la **synthèse documentaire vérifiable**, pas de la prédiction. Chaque affirmation doit citer sa source et être traçable jusqu'au document. À comparer avec le pool « expliquer pourquoi le cours a bougé », qui est le mauvais usage - une fabrique à narratifs invérifiables.

**Garde-fou : l'agent produit une évaluation, il ne la valide pas.** Le champ `reviewed_by` reste humain, et une évaluation non revue ne fait jamais passer un titre dans le quadrant cible.

### 8.4 L'import du dossier : brouillon, acquittement, verdicts

Trois règles issues du premier dossier réel (adidas, août 2026) :

- **Un bloquant ne détruit plus le travail.** Le prompt 4 signale presque toujours des points à vérifier — c'est son rôle, pas un accident. Un dossier porteur de `blocking_issues` est donc **conservé en brouillon** au lieu d'être refusé : sans validation, sans projection, mais sans perte. Rien n'est complété automatiquement.
- **L'acquittement est nominatif et tracé.** L'analyste qui a vérifié les points bloquants les acquitte à l'import ; le dossier conserve `quality_control.blocking_issues_reviewed = {par, le}`. Sans nom, rien n'est levé.
- **Les verdicts sont posés par l'analyste, à l'import.** Le prompt 4 *propose* un bloc `strategic_assessment` (position, durabilité, sources de rente, menaces, justification) sur l'entreprise étudiée — c'est ce qui fait du dossier une analyse de l'instrument, pas seulement de ses concurrents. L'écran d'import permet de les confirmer ou de les corriger ; ce sont eux qui se projettent vers `moat_assessments`. Sans verdicts, le titre ne peut pas atteindre `solid`.

L'appariement des sociétés (fiche du prompt 2 ↔ concurrent du prompt 1, profils résumés du prompt 4 ↔ fiches détaillées) tolère casse, ponctuation et suffixes juridiques : « NIKE, Inc. » et « Nike Inc. » sont la même société, et une fiche détaillée n'est jamais écrasée par son résumé.

> **Révision du 2026-08-21 — un défaut de génération n'est pas un défaut de dossier.** Constaté sur EssilorLuxottica : sur six bloquants du prompt 4, deux ne parlaient pas de l'entreprise mais de la **sortie du modèle** — « JSON incomplet (coupé en deux fois) », « URLs tronquées dans les sources ». Ils pesaient exactement autant qu'une couverture concurrentielle absente : conclusion interdite, confiance plafonnée à 30. Or le dossier importé était complet — 22 blocs, 254 000 caractères. **Plafonner la confiance d'une analyse parce que la génération a bafouillé revient à noter l'entreprise sur la qualité de son imprimante.**
>
> `schema.defaut_de_generation` sépare les deux espèces. La classification porte sur le **sujet** de la phrase, jamais sur un adjectif seul : il faut un mot qui désigne la sortie (`json`, `url`, `réponse`, `fenêtre de contexte`…) **et** un mot qui la dit abîmée (`tronqué`, `coupé`, `incomplet`…). « Fiches concurrentielles incomplètes » contient « incomplet » et reste un défaut de dossier. Un défaut de génération est rétrogradé en IMPORTANT, reste affiché avec sa correction — *relancer le prompt* — et n'interdit plus l'import ni la conclusion.
>
> **Ce que cette révision ne change pas :** un manque de substance bloque toujours, et l'acquittement reste nominatif. La liste de bloquants demeure du **texte figé écrit par le prompt 4**, jamais reconfrontée au dossier — elle peut donc rester vraie alors que le trou a été comblé par un import ultérieur. Requalifier un bloquant périmé se fait à la main, dans `quality_control.blocking_issues_requalifies` (code, verdict, constat, preuve, par, le), la liste d'origine étant conservée dans `blocking_issues_origine`. Remesurer automatiquement à chaque import reste à faire.

### 8.5 Le prompt 5 : synthèse décisionnelle et scoring

Ajouté en août 2026, l'écran passe de « Dossier concurrentiel » à « Analyses ».
Le prompt 5 produit un avis structuré à partir de **toutes** les données de
l'outil — pas seulement du dossier concurrentiel — avec une règle centrale :

> **Les scores mesurent la solidité de l'analyse et l'attractivité relative du
> dossier, jamais le cours futur.** Un LLM peut produire une réponse très
> assurée sur des données incomplètes, anciennes ou contradictoires : la
> séparation des scores existe pour empêcher cela.

Quatre décisions de conception :

- **Trois scores séparés, jamais agrégés.** Attractivité (le dossier),
  confiance (la robustesse de l'analyse elle-même : fraîcheur, couverture,
  sources, cohérence), alignement (qualité × risque × prix). Une entreprise
  attractive avec une confiance faible se surveille, elle ne s'achète pas.
- **L'abstention est un verdict.** Six conclusions dont « insuffisant pour
  conclure » — valide et respectable quand les données ne portent pas une
  opinion. Un bloquant du contrôle qualité non acquitté nominativement
  interdit toute conclusion et plafonne la confiance à 30/100.
- **Les données sont injectées, pas ressaisies.** L'outil compose le prompt
  avec un instantané quantitatif (prix, tendance, régime, ratios, qualité,
  évaluation) et le dossier complet en JSON. Un bloc `null` se signale, ne
  s'estime pas — et la synthèse est datée par construction.
- **La synthèse ne touche pas le moteur.** Elle vit dans le dossier (blocs
  `synthese`, `scoring`, `decision_gate`), ne projette rien vers
  `moat_assessments` ni `quality_scores`, et n'efface pas une validation :
  un dossier signé le reste, la synthèse ajoutée porte son propre état
  (`human_review_status = not_reviewed`). Une nouvelle synthèse remplace
  l'ancienne — deux avis datés contradictoires ne s'additionnent pas.

---

## 9. Conséquence sur l'ordre des opérations

**Les specs actuelles font : prix d'abord, fondamentaux en vérification. La méthode de Marie fait l'inverse en amont.**

> *« Choisis un leader et regarde si sa position concurrentielle est durable »* puis *« ensuite, le prix »*.

Le prix vient bien en second dans la sélection, même si le signal de prix est ce qui déclenche l'attention au quotidien.

**Architecture retenue - les deux, découplés :**

```
   FILTRE AMONT (trimestriel)          SIGNAL (hebdomadaire)
   Qualité, indépendant du prix        Prix, indépendant de la qualité
   ├── leadership                      ├── z-score
   ├── rente                           ├── qualité du fit
   └── érosion                         └── persistance
            │                                   │
            └──────────────┬────────────────────┘
                           ▼
                    MATRICE QUALITÉ × PRIX
                    (le screener réel)
```

**Deux fréquences distinctes, et c'est délibéré.** La qualité se recalcule au rythme des publications de comptes - trimestriellement au plus. La recalculer chaque semaine créerait une illusion de mouvement là où il n'y en a pas, et pousserait à réagir à du bruit comptable.

**Règle stricte :** un titre dont la qualité n'a jamais été évaluée n'apparaît **jamais** comme opportunité. Il apparaît comme *signal de prix non qualifié* - ce qui est exactement son statut.

---

## À challenger en priorité

1. **Seuil de coût du capital fixe à 8% plutôt que WACC par titre.** Je défends fermement ce choix : un WACC estimé titre par titre est un chiffre bruité déguisé en précision. Mais c'est discutable, et le seuil relatif au secteur est probablement le meilleur des deux.
2. **L'érosion à trois pentes sur 5 ans est peu puissante.** Elle ne détectera que les cas francs. Alternative : abaisser le seuil de significativité, au prix de faux positifs.
3. **Le régime cyclique distinct** est indispensable mais introduit une classification supplémentaire - qui décide qu'un titre est cyclique ? Proposition : volatilité du ROIC au-delà d'un seuil, avec surcharge manuelle.
4. **L'obligation d'un concurrent hors Europe dans tout groupe de pairs.** Contraignant, mais c'est le seul remède à la limite Lim1, qui est la plus dangereuse du document.
5. **La fréquence trimestrielle de la qualité.** Tu voudras peut-être la voir bouger plus souvent. Ma position : elle ne bouge pas plus souvent, et prétendre le contraire serait du bruit.
6. **Les 5 ans de fondamentaux gratuits sont le vrai plafond de ce document.** Si un poste de dépense doit être accepté dans tout le projet, c'est celui-là - 15 à 20 ans de ROIC - et non les cours, qui sont gratuits.
