# 00 - Vue d'ensemble et principes d'architecture

**Projet :** market intelligence - couche data pour screener de décote multi-actifs
**Version :** v1 - spec de cadrage, à challenger
**Date :** août 2026

---

## 1. Objet de la v1

Construire la **couche donnée** : collecte, normalisation, stockage, calcul analytique et restitution. Aucun agent IA en v1.

Le livrable est un système qui répond à quatre questions - **deux sur le prix, deux sur la qualité** :

1. Où se situe le cours d'un actif par rapport à sa tendance longue, en écarts-types ? *(la droite de régression Hiboo)*
2. Quels actifs, aujourd'hui, sont sous un seuil de décote donné ?
3. L'entreprise est-elle un leader dont la position produit une rente ? *(doc 08)*
4. Cette rente s'érode-t-elle ? *(doc 08)*

**Les deux jambes sont d'égale importance et se calculent indépendamment.** Marie de Raismes est explicite : la droite de régression est *« un outil statistique, donc il a ses limites, il faut toujours le compléter par l'analyse fondamentale »*, et son critère de qualité est **la position concurrentielle durable**. Un système qui ne traiterait que le prix produirait des value traps avec une belle courbe.

## 2. Périmètre acté

| Dimension | Décision v1 | Cible |
|---|---|---|
| Univers | **586 titres** Europe éligibles PEA — 57 au départ, élargi le 2026-08-21 (cible initiale : 250) | 60 000 valeurs, architecture prête |
| Classes d'actifs | Actions uniquement | Actions, ETF, indices, matières premières, FX. *Crypto hors modèle - doc 07 §4* |
| Analyse qualité | Volet quantitatif (ROIC, rente, érosion) | + volet qualitatif assisté LLM |
| Base | Supabase free tier, si le volume tient | Postgres + TimescaleDB sur VPS |
| Cours | 30 ans, gratuit | idem |
| Fondamentaux | 5 ans gratuits + extraction PDF à la demande | idem |
| Restitution | Dashboard Streamlit + rapport hebdomadaire | idem |
| Agents IA | Hors périmètre | Phase 2 |

## 3. Les six principes qui structurent tout le reste

### P1 - Séparation stricte raw / derived

Les tables **raw** sont append-only et immuables : ce que le provider a envoyé, tel quel, daté. Les tables **derived** sont intégralement reconstructibles à partir des raw.

*Conséquence :* changer la méthode de calcul d'une régression n'exige jamais de re-télécharger. On tronque, on relance, on compare. C'est ce qui rend le système capable d'évoluer sans dette.

### P2 - Bitemporalité systématique

Chaque fait porte **deux dates** : la date à laquelle il se rapporte (`period_end`, `price_date`) et la date à laquelle on l'a connu (`published_at`, `ingested_at`).

*Conséquence :* toute analyse peut être rejouée "telle qu'on la voyait au 15 mars 2019". Sans ça, le look-ahead bias est structurel et irrattrapable. Ce champ coûte 4 octets aujourd'hui et est impossible à reconstituer plus tard.

### P3 - L'identité d'un instrument n'est pas son ticker

Les tickers changent, sont réutilisés, diffèrent selon le provider. La clé métier est l'**ISIN** ; les tickers vivent dans une table de mapping avec validité temporelle.

*Conséquence :* on ne perd pas l'historique quand une société change de nom, et on ne fusionne pas deux sociétés par accident.

### P4 - On stocke la série la plus stable dans le temps, jamais une colonne recalculée à chaque événement

*Principe amendé après implémentation - voir doc 09 §3, D-A. La formulation initiale était : « on stocke le cours non ajusté ». Elle supposait que le cours nominal était disponible. Il ne l'est pas.*

Aucune source gratuite ne sert le cours nominal d'époque. La colonne `Close` de Yahoo est **rétro-ajustée des splits** : Dassault Systèmes cotait ~133€ en juin 2019, l'API renvoie 26.70€, soit divisé par le 5:1 de juillet 2021.

**Ce que ce principe protège n'est pas le caractère nominal, c'est la reproductibilité.** Sur ce critère les deux colonnes de Yahoo se comportent en sens opposés :

| Colonne | Réécrite à chaque | Fréquence réelle |
|---|---|---|
| `Adj Close` | dividende | plusieurs fois par an |
| `Close` | split | 2 fois en 12 ans sur Dassault |

On stocke donc **`Close`, jamais `Adj Close`**, et l'on ne dépend jamais d'une valeur recalculée rétroactivement à chaque événement. Un backtest lancé en janvier et relancé en juin doit donner le même résultat.

**Conséquence : `factor_price = 1.0`.** Les splits étant déjà incorporés dans `Close`, appliquer en plus les ratios de `corporate_actions` diviserait la série une seconde fois. Air Liquide, qui distribue une action gratuite pour dix tous les deux ans, verrait son historique divisé par 1.1 à chaque opération. **C'est le type d'erreur qui ne se voit pas : la courbe reste lisse, seule la pente est fausse.**

**Coût résiduel assumé :** la comparaison à un graphe affichant le cours nominal sera décalée d'un facteur multiplicatif constant - L'Oréal ÷20, EssilorLuxottica ÷20.44. Pour le test de superposition avec Hiboo, la règle de lecture est : *un écart constant valide la forme, un écart qui dérive dans le temps signale un vrai problème*.

### P5 - Le système génère son propre out-of-sample

Chaque semaine, on calcule et on **historise** les paramètres de régression de chaque instrument, dans une table dédiée.

*Conséquence, et c'est le point le plus important de cette spec :* dans 12 mois tu disposes de 52 observations réellement hors échantillon, produites en temps réel, sans look-ahead possible. Dans 36 mois, d'un vrai track record. Coût aujourd'hui : une table et un champ `as_of_date`. Coût si on l'ajoute plus tard : impossible, l'information n'existe pas rétroactivement.

C'est la validation de la méthode obtenue gratuitement, sans faire de backtest.

**⚠ Ce principe est le seul du document qui ne s'auto-répare pas**, et c'est pour cette raison qu'il a été le premier à être mis sous cron. Depuis le 2026-08-21, le cycle tourne toutes les 8 heures (`scripts/cycle.py`, sur GitHub Actions depuis le 2026-09-01) : l'historisation ne dépend plus de quelqu'un qui y pense. Ce qui restait vrai le reste toutefois pour le passé - **une observation non écrite ne se rattrape jamais**, et les semaines antérieures au cron manquent définitivement.

### P6 - La méthode dépend de la classe d'actif, explicitement

Une droite log-linéaire sur 20 ans a un sens pour L'Oréal, pas pour le bitcoin ni pour l'or. La politique de régression est une **donnée**, pas une constante en dur dans le code.

*Conséquence :* étendre aux matières premières ou à la crypto consiste à insérer une ligne dans une table de politiques, pas à réécrire le moteur.

## 4. Vue d'ensemble du flux

```
  SOURCES              INGESTION          STOCKAGE                CALCUL                RESTITUTION
┌──────────┐         ┌────────────┐    ┌────────────┐    ┌──────────────────┐    ┌────────────┐
│ yfinance │         │            │    │  RAW       │    │ PRIX (hebdo)     │    │ Streamlit  │
│  ✅ seul │ ──────▶ │ collectors │──▶ │  bars      │──▶ │  régression      │─┐  │ matrice    │
│ Stooq ✕  │         │ normalise  │    │  fund.     │    │  z-score         │ │  │ qualité    │
│ ESEF  ⬜ │         │ valide     │    │  actions   │    │  stationnarité   │ ├─▶│  × prix    │
│ AMF   ⬜ │         │            │    │  shares    │    ├──────────────────┤ │  │            │
└──────────┘         └────────────┘    │  fx        │    │ QUALITÉ (trim.)  │ │  │ rapport    │
                            │          └────────────┘    │  leadership      │─┘  │ hebdo      │
                            ▼                 │          │  rente (ROIC)    │    └────────────┘
                     ┌────────────┐    ┌────────────┐    │  érosion         │
                     │ quarantaine│    │ archive    │    └──────────────────┘
                     │ anomalies  │    │ Parquet    │          │        │
                     └────────────┘    │ (froid)    │          ▼        ▼
                                       └────────────┘   ┌──────────┐ ┌──────────┐
                                                        │regression│ │ quality  │
                                                        │  _fits   │ │ _scores  │
                                                        │historisé │ │historisé │
                                                        └──────────┘ └──────────┘
```

*État réel : ✅ construit · ✕ inaccessible (preuve de travail JavaScript, voir doc 09 D-B) · ⬜ non construit. `fx` et les déflateurs restent vides - l'univers est mono-devise.*

**Deux fréquences de calcul distinctes, et c'est délibéré.** Le prix se recalcule chaque semaine ; la qualité se recalcule au rythme des publications de comptes, donc trimestriellement au plus. Recalculer la qualité chaque semaine créerait une illusion de mouvement là où il n'y en a pas.

## 5. Stratégie de stockage à deux températures

C'est l'arbitrage qui permet de tenir dans 500 Mo tout en restant scalable.

| Couche | Contenu | Support | Volume mesuré, 57 titres |
|---|---|---|---|
| **Chaud** | Hebdomadaire 30 ans + quotidien 3 ans | Postgres/Supabase | **~15 Mo** |
| **Froid** | ~~Quotidien complet 30 ans~~ · *⚙ miroir du chaud (T8)* | Parquet sur VPS | ~15 Mo |

**Pourquoi l'hebdomadaire suffit pour la régression.** Shiller & Perron (1985) ont montré que la puissance des tests sur séries temporelles dépend de **l'étendue temporelle, pas de la fréquence d'observation**. Passer du quotidien à l'hebdomadaire sur 30 ans fait perdre presque zéro information sur la tendance longue, et divise le volume par cinq. 1 560 points hebdomadaires sur 30 ans, c'est amplement suffisant pour estimer deux paramètres.

Le quotidien reste nécessaire sur la fenêtre récente, pour les signaux et l'exécution.

**Le froid n'est pas une sauvegarde, c'est la source de vérité.** Si on veut un jour du quotidien sur 30 ans, on recharge depuis Parquet sans retoucher au provider.

> **⚙ Réel - dette T8 : il n'y a qu'une température.** `export_cold.py` relit `bars`, or aucun job ne télécharge de quotidien au-delà de 3 ans. L'archive Parquet est donc un **miroir exact** de la couche chaude, pas une couche plus profonde. La phrase ci-dessus décrit une capacité qui n'existe pas : recharger 30 ans de quotidien depuis Parquet est aujourd'hui impossible.

### Le calcul qui décide de Supabase

Ligne de barre en Postgres, index compris : **~100 octets**.

| Scénario | Lignes | Volume estimé |
|---|---|---|
| **57 titres, réel mesuré** | **122 000** | **~15 Mo** |
| **586 titres, réel mesuré (2026-08-21)** | **1 080 000** | **303 Mo** |
| 250 titres, quotidien 30 ans | 1.9 M | ~200 Mo |
| 250 titres, **stratégie deux températures** | 580 k | **~60 Mo** |
| 1 500 titres, deux températures | 3.5 M | ~350 Mo |
| 5 000 titres, deux températures | 11.6 M | ~1.2 Go |
| 60 000 titres, deux températures | 140 M | ~14 Go |

**Verdict révisé au 2026-08-21 : le free tier tient, mais il ne tient plus « confortablement ».** À 586 titres la base pèse **303 Mo, soit 61% du quota de 500 Mo**. La marge restante est d'environ 350 titres, et non de 400 comme le laissait croire la ligne ci-dessus. Au-delà de ~900 titres, la bascule sur le VPS devient obligatoire, pas optionnelle.

**Pourquoi l'estimation était fausse d'un facteur trois.** Le tableau ne comptait que les barres. Or les barres ne font que la moitié du poids : `adjustment_factors` pèse **80 Mo à lui seul** — une ligne par barre hebdomadaire, 639 112 lignes, soit plus que `bars_1d` — et `shares_outstanding` 26 Mo pour 274 621 lignes. Le coût réel est de **0,52 Mo par titre**, contre 0,26 Mo estimé.

*Mesuré à 57 titres : 122 000 barres, 7 044 faits, backfill ~6 min (cycle complet ~23 min). Mesuré à 586 titres : 1 080 000 barres, 70 393 faits, 13 379 opérations sur titre, cycle complet forcé en **104 min** — dont 44 min de cours, 25 min d'opérations sur titre et 33 min de fondamentaux. Le temps reste dominé par le débit ménagé vers yfinance, pas par le calcul : les régressions sur 586 titres prennent 73 secondes.*

**Deux réserves sur Supabase free, à connaître avant de s'engager :**

1. **Pause automatique après 7 jours sans requête.** Un cron hebdomadaire suffit à l'éviter, mais si le cron échoue deux fois, le projet se met en pause et demande une réactivation manuelle. *Mitigation : un ping quotidien trivial, indépendant du pipeline principal.*
2. **500 Mo de RAM partagée et snapshots sur 7 jours seulement.** Les calculs lourds ne doivent pas tourner dans la base. *Mitigation : le moteur analytique tourne en Python côté VPS, la base ne fait que stocker.*

**Décision d'architecture qui en découle : rester en Postgres strictement standard.** *⚙ Tenue : aucune fonctionnalité propriétaire Supabase dans le schéma livré.* La migration vers le VPS doit être un `pg_dump | psql`, pas un chantier.

## 6. Ce que la v1 ne fait délibérément pas

- **Aucune notification entre deux rapports hebdomadaires.** Le silence est une fonctionnalité - voir l'argument de second ordre dans l'avis critique.
- **Aucun passage d'ordre, aucune connexion à un broker.** Le système propose, tu décides.
- **Aucun agent LLM.** Phase 2, et sur un périmètre réduit.
- **Aucun intraday.** Ni utile ni compatible avec l'horizon de décision.
- **Aucun scoring de confiance composite.** Un z-score et un verdict de qualité de donnée, pas une note sur 100 qui agrège l'incomparable.

## 7. Liste des documents

**L'ordre de lecture n'est pas l'ordre de numérotation** - la numérotation reflète l'ordre de production. Commencer par le 07.

| Ordre | Fichier | Contenu |
|---|---|---|
| 1 | `07_expression-de-besoin.md` | **Point d'entrée.** Origine, besoins, périmètre d'actifs, matrice de couverture |
| 2 | `00_vue-densemble.md` | Ce document. Principes d'architecture, volumétrie |
| 3 | `08_position-concurrentielle.md` | **La jambe qualité** : leadership, rente, érosion, matrice qualité × prix |
| 4 | `03_moteur-analytique.md` | La jambe prix : régression, z-scores, stationnarité, politiques par classe |
| 5 | `01_modele-de-donnees.md` | Schéma complet, DDL SQL, justification de chaque table |
| 6 | `02_ingestion-et-sources.md` | Providers, pipeline, qualité, résilience |
| 7 | `04_screener-dashboard.md` | Écrans, filtres, rapport hebdomadaire |
| 8 | `05_roadmap-et-lot.md` | Découpage en lots livrables, estimation d'effort |
| 9 | `06_décisions-et-points-ouverts.md` | Arbitrages assumés et questions non tranchées |
| 10 | `09_etat-implementation-et-ecarts.md` | **État réel du code, écarts, registre de dette** |

*Le doc 09 est le seul à décrire le système tel qu'il est plutôt que tel qu'il devrait être. À lire avant toute reprise de développement.*

---

## À challenger en priorité

1. **La stratégie deux températures.** Elle repose sur l'idée que l'hebdomadaire suffit pour la tendance longue. Si tu veux un jour backtester finement des points d'entrée quotidiens, il faudra recharger depuis Parquet - faisable, mais c'est une friction assumée.
2. **Supabase plutôt que le VPS.** Le free tier tient, mais avec deux contraintes opérationnelles réelles. Le VPS n'a aucune de ces contraintes et coûte zéro de plus. Le seul vrai gain de Supabase est l'absence d'administration.
3. **Le principe P5** (historisation hebdomadaire des fits) est celui que je défendrais le plus fermement. Il transforme un système de screening en dispositif de validation, sans effort supplémentaire.
