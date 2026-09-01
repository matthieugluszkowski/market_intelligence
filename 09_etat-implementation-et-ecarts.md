# 09 - État d'implémentation et registre des écarts

*Établi par relecture du code au 19 août 2026. Ce document trace la distance entre les specs 00-08 et le système réellement construit.*

---

## 1. Trois natures d'écart, à ne pas confondre

C'est la distinction qui structure tout ce document, et la confondre rendrait la documentation inutilisable.

| Nature | Définition | Traitement |
|---|---|---|
| **Décision** | On a changé d'avis en connaissance de cause. La spec avait tort ou l'hypothèse ne tenait pas. | **La spec est corrigée.** L'écart disparaît. |
| **Avancement** | Conforme à la spec, pas encore construit. | Reste dans la roadmap. Aucune correction de spec. |
| **Dette** | Le code diverge de la spec sans que ce soit voulu, ou une intention est portée sans être effective. | **Registre §5.** À corriger, priorisé. |

Une dette n'est pas un reproche : plusieurs sont la conséquence directe et prévisible de décisions justes prises en amont.

---

## 2. État réel, avec les chiffres

| Lot | État | Réalité mesurée |
|---|---|---|
| L0 Socle | ✅ | Supabase free tier, 27 tables, 11 migrations suivies par empreinte SHA-256, keepalive en cron sur VPS Lightsail |
| L1 Référentiel | ✅ | **57 titres** chargés sur 59 au CSV. FR 29, DE 10, NL 8, ES 4, BE 3, IT 3 |
| L2 Ingestion cours | ✅ | **122 000 barres**, ~6 min. Hebdo sur historique maximal, quotidien 3 ans |
| L3 Corporate actions + qualité | ✅ | 9 contrôles livrés, **2 non éprouvables** sur l'univers actuel |
| L4 Moteur analytique | ✅ | 57 régressions, ~2 min |
| L5 Screener + fiche | ✅ | 3 écrans Streamlit, 18 tests de conformité graphique |
| L6 Fondamentaux | ✅ | **7 044 faits, 33 concepts, 100% des titres avec ≥3 exercices** (seuil spec : 80%) |
| L6b Qualité | ✅ | 57 scores, 6 groupes de pairs manuels, 14 concurrents hors univers |
| L7 Orchestration | 🟡 | Cycle de 8 h en cron sur le VPS depuis le 2026-08-21 ; rapport hebdomadaire et alerte sur échec : non faits |
| L8 Sectoriel + portefeuille | ⬜ | — |
| L9 Extraction PDF | ⬜ | — |
| L10 Veille externe | ✅ | Consensus, notations et dépêches collectés chez Zonebourse et Boursier.com ; 30 tests, dont deux d'architecture qui vérifient qu'aucun calcul ne les lit |

**169 tests.** Effort réel : de l'ordre de 20 jours-homme pour L0 à L6b, cohérent avec la fourchette optimiste de la spec 05.

### Les résultats, qui sont plus intéressants que l'avancement

**Verdicts de régression : 38 `weak`, 19 `rejected`, 0 `good`.**

Quatre titres seulement rejettent la racine unitaire au seuil brut de 5% - Ahold, Getlink, Michelin, Hermès. Sur 54 tests - trois titres sont écartés en amont pour historique insuffisant et ne sont pas testés - un taux de rejet de 7.4% est **statistiquement indiscernable du taux de faux positifs de 5%**. La correction BHY divise le seuil par 4.56 et n'en laisse passer aucun.

**C'est le résultat le plus important du projet à ce stade, et il valide la méthode par la négative.** La spec 03 §3.3 annonçait que `weak` serait le cas majoritaire et qu'une répartition à 80% de `good` signalerait un bug. La réalité est plus dure encore : **aucun titre européen de l'univers ne présente de retour à la tendance statistiquement établi sur 20 ans.** Un système qui aurait affiché des z-scores rassurants sans ce diagnostic aurait fabriqué de la confiance sur du sable.

**Verdicts de qualité : 49 `watch`, 7 `unqualified`, 1 `eroding`, 0 `solid`.**
Régimes : 25 `rent`, 15 `cyclical`, 12 `no_moat`, 1 `eroding`, 4 `unknown`.

Aucun `solid` : c'est **mécanique**, pas empirique. Les deux garde-fous de la spec 08 - un concurrent hors Europe dans le groupe de pairs, et une évaluation qualitative revue par un humain - sont implémentés comme conditions bloquantes, et la seconde n'est remplie par aucun titre. Le quadrant cible est donc structurellement vide tant que la saisie qualitative n'a pas lieu.

**Cohérence prix / fondamentaux : 35 `confirmé`, 17 `suspect`, 5 `indéterminable`.**

**Cas de référence du doc 08 :** Arkema `cyclical`/`watch` ✅, BMW 1 pente d'érosion sur les 2 calculées, `cyclical`/`watch` ✅, Seb `no_moat`/`watch` avec SharkNinja dans son groupe ✅. Nestlé et Atos **hors univers** - suisse non éligible PEA pour l'un, écarté en L1 pour l'autre - donc éprouvés sur données synthétiques.

**Statistiques de régime, Seb au 18 août 2026 :** z = −2.16, 4 épisodes sous −2σ depuis 2006 soit 6.0% du temps, durée médiane 8 semaines, **épisode en cours 46 semaines, le plus long jamais observé**, creux supplémentaire médian −7.7%, demi-vie 3.4 ans.

*Ce dernier bloc est exactement ce que la spec 03 §4 réclamait à la place d'une probabilité. « Le plus long épisode jamais observé, avec une demi-vie de 3.4 ans » est une information de gestion. « 95% de chances de remonter » n'en était pas une.*

---

## 3. Écarts de décision - les specs sont corrigées

Neuf décisions ont modifié les specs. Les plus structurantes d'abord.

> **Correspondance de numérotation.** Le doc 06 §1 reprend ces mêmes décisions sous les numéros **D17 à D27** : D-A y est scindée en D17 et D18, D-D en D21 et D22. Les deux listes couvrent le même ensemble.

### D-A - Le principe P4 est amendé : le cours nominal n'existe pas *(docs 00 et 01 · = D17 et D18)*

**Ce que disait la spec :** stocker le cours **non ajusté**, l'ajusté est un calcul.

**Ce qu'on a découvert :** Yahoo ne sert pas le cours nominal. Sa colonne `Close` est **rétro-ajustée des splits** - Dassault Systèmes cotait ~133€ en juin 2019, l'API renvoie 26.70€, soit divisé par le 5:1 de juillet 2021. Le cours nominal d'époque n'est disponible chez **aucune source gratuite**.

**Reformulation retenue.** Ce que P4 protège n'est pas le caractère nominal, c'est la **reproductibilité**. Sur ce critère les deux colonnes de Yahoo se comportent en sens opposés : `Adj Close` est réécrit à **chaque dividende**, `Close` seulement aux splits - 2 fois en 12 ans sur Dassault. On stocke donc `Close`, jamais `Adj Close`, et le principe devient : *stocker la série la plus stable dans le temps que la source expose, et ne jamais dépendre d'une colonne recalculée rétroactivement à chaque événement*.

**Conséquence directe : `factor_price = 1.0` partout.** Appliquer en plus les ratios de `corporate_actions` diviserait la série une seconde fois. Air Liquide, qui distribue une action gratuite pour dix tous les deux ans, verrait son historique divisé par 1.1 à chaque opération. **C'est le type d'erreur qui ne se voit pas : la courbe reste lisse, seule la pente est fausse.**

**Coût résiduel, non résorbable :** les splits antérieurs à la première ingestion sont déjà incorporés, `adjustment_factors` ne les rejouera pas, et la comparaison à un graphe affichant le nominal sera décalée d'un **facteur multiplicatif constant** - L'Oréal ÷20, EssilorLuxottica ÷20.44. Le test de superposition avec Hiboo doit en tenir compte : *un écart constant valide la forme, un écart qui dérive signale un vrai problème*.

### D-B - yfinance devient source primaire *(doc 02 · = D19)*

**Ce que disait la spec :** Stooq en primaire, pour sa robustesse - un CSV par URL ne casse pas.

**Ce qu'on a découvert :** l'endpoint `/q/d/l/` renvoie désormais une page de vérification navigateur à **preuve de travail JavaScript**, constaté depuis deux IP indépendantes. L'argument de robustesse ne tient plus.

**Conséquence assumée et non résolue :** yfinance est seul, ce qui contredit frontalement « aucune source ne doit être un point de défaillance unique ». Les symboles Stooq sont conservés en `instruments.attributes.stooq_symbol_unverified`, non chargés dans `instrument_symbols` - *les inscrire non vérifiés reviendrait à fabriquer la confiance qu'on cherche à établir*. Voir dette T3, qui est plus grave que l'absence de source elle-même.

### D-C - `published_at` est estimé, avec un drapeau *(docs 01 et 02 · = D20)*

**Le problème :** yfinance ne sert **aucune date de publication**. Le principe P2 - bitemporalité - devenait inapplicable.

**Les deux mauvaises réponses écartées :** stocker `period_end` comme `published_at` ferait croire que les comptes 2024 étaient connus au 31 décembre 2024 - du look-ahead pur et invisible. Laisser `null` rendrait tout filtre point-in-time inopérant.

**La réponse retenue :** la directive Transparence impose quatre mois aux émetteurs européens. `period_end + 122 jours` est une date à laquelle l'information était **certainement** disponible. Nouvelle colonne `published_at_estimated` sur `financial_facts` et `financial_reports`.

**Le raisonnement qui décide est asymétrique** : errer tard ne produit qu'un excès de prudence, errer tôt fabrique du look-ahead. On erre donc délibérément du côté tardif.

*C'est aussi le seul vrai argument pour construire un jour le parseur ESEF : non pas la couverture - yfinance atteint déjà 100% du critère - mais le fait qu'**ESEF porte les vraies dates de dépôt**.*

### D-D - Le régime cyclique est déclaré à la main, la déclaration prime sur la détection *(docs 01 et 08 · = D21 et D22)*

**Ce que disait la spec :** régime détecté par volatilité du ROIC, avec surcharge manuelle possible.

**Deux bugs successifs ont montré que la détection ne peut pas fonctionner sur 4 exercices.**

D'abord un cyclique classé en value trap : Arkema sortait `eroding` alors que le doc 08 dit explicitement *bas de cycle, pas érosion*. Puis, après correction, l'inverse : un ROIC qui s'effondre de 18% à 2% a une volatilité très élevée et sortait `cyclical`, donc protégé du verdict d'érosion - **c'était exactement le cas Atos**.

**Le discriminant ajouté** (`R2_TENDANCE_MONOTONE = 0.70`) est juste : un cycle redescend **et** remonte, un effondrement est monotone. Il n'existait pas dans la spec et il est nécessaire.

**Mais il ne suffit pas, et c'est une limite de fond.** Avec quatre exercices, la fenêtre ne couvre souvent que la *descente* d'un cycle, et une descente de cycle est **statistiquement indiscernable d'une érosion** : même pente, même monotonie. C'est la limite L2 du doc 08 - cinq ans, c'est court pour une notion de durabilité - et **aucune amélioration du code ne la lève.**

**Sortie retenue :** `db/seeds/004_cycliques.sql` déclare 12 cycliques à la main, sur le même principe que les groupes de pairs manuels. À revoir quand huit exercices seront disponibles.

### D-E - Verdict `indéterminable` ajouté à la cohérence prix/fondamentaux *(doc 03 · = D23)*

La spec ne prévoyait que `confirmé` et `suspect`. **Traiter un critère non évaluable comme un critère réussi fabrique de faux signaux.** Troisième état ajouté : 5 titres y tombent.

### D-F - Ratios neutralisés pour le secteur financier *(doc 03 · = D24)*

La notion de chiffre d'affaires n'a pas de définition stable pour un assureur - Allianz sortait à 25% d'écart sur la marge nette là où les industriels tombent à 0.0%. Marge brute, opérationnelle, nette, EV/CA, EV/EBIT, dette nette/EBITDA, gearing et couverture des intérêts sont mis à `null` pour l'ICB 30, et le critère de levier y est neutralisé - **une banque a structurellement un levier de 15 à 20, elle sortirait `suspect` à chaque passage pour une raison qui n'en est pas une.**

### D-G - Le DF-GLS arbitre seul la stationnarité *(docs 01 et 03 · = D25)*

L'intervalle bootstrap sur la racine AR(1) est **anti-conservateur près de la racine unitaire**. Constaté sur Seb : l'intervalle ressort à [0.943 ; 0.968], qui exclut 1, alors que le DF-GLS ne rejette pas. **C'est le test qui a raison.** L'intervalle reste affiché - il dit l'incertitude - mais n'alimente pas `fit_quality`. Une inversion de test à la Stock (1991) corrigerait ce point ; non prise en v1.

### D-H - Cycle de vie complet des anomalies *(docs 01 et 02 · = D26)*

La spec ne demandait que « quarantaine plutôt que rejet ». Deux défauts constatés en exploitation ont imposé davantage :

- une première version purgeait les anomalies non résolues avant chaque recalcul : une anomalie vue en août et toujours présente en octobre **perdait sa date de première détection**, et toute note de diagnostic disparaissait
- une anomalie résolue à la main **réapparaissait au recalcul suivant**, la condition sous-jacente étant toujours vraie. La liste ne diminuait jamais et la revue manuelle ne servait à rien

**Ajouts :** `fingerprint` (empreinte stable), `last_seen_at`, `run_count`, `resolved_kind` distinguant clôture automatique et acquittement humain, index unique partiel sur les anomalies ouvertes, CLI `scripts/anomalies.py` qui **refuse une clôture sans note** - *une résolution sans note ne sert à rien dans six mois*.

### D-I - Filtre de dilution renforcé *(docs 01, 02 et 03 · = D27)*

La spec disait « +50% sur 12 mois glissants ». Le code compare au **minimum glissant sur 365 jours**, sur un nombre d'actions **préalablement neutralisé des splits**. Sans cette neutralisation, quatre faux positifs : Dassault ×5.09, Michelin ×4.0, Aena ×10.7, Prosus ×2.43. Plus une alerte unique par titre - 203 lignes pour Prosus autrement.

---

## 4. Écarts d'avancement - conformes, non construits

Aucune correction de spec. Ces éléments restent au plan.

| Élément | Doc | Lot |
|---|---|---|
| Collecteurs ESEF/XBRL, API AMF, BCE (FX), Eurostat (IPCH) | 02 | L6 partiel, L9 |
| Régime B - extraction PDF par LLM | 02 §3 | L9 |
| Écran 4 vue sectorielle, écran 5 portefeuille | 04 | L8 |
| Écran 6 qualité des données | 04 | L7 |
| ~~Orchestrateur et crons~~ (fait le 2026-08-21) · rapport hebdomadaire, alerte sur échec | 02 §4.4, 04 §4 | L7 |
| Enveloppes CLI des jobs | 02 §4.1 | L7 |
| Déflation IPCH pour `real_deflated` | 03 §6 | Phase 3 |
| Lien ETF → indice répliqué | 03 §6 | Phase 3 |
| Tables `financial_reports`, `index_memberships`, `positions`, `screener_snapshots` | 01 | créées, jamais écrites |
| Évaluations qualitatives `moat_assessments` | 08 §8 | saisie à faire |

**Deux ont un effet immédiat qu'il faut voir.** L'absence d'évaluations qualitatives rend le quadrant cible vide par construction. L'absence d'orchestrateur signifie qu'**aucun fit ne s'historise tout seul** - or le principe P5, la décision la plus importante du projet, ne produit sa valeur que par accumulation hebdomadaire régulière. Un pipeline lancé à la main quand on y pense ne construit pas un jeu hors échantillon.

---

## 5. Registre de dette

Classé par gravité décroissante. Le niveau 1 fausse une lecture ou un résultat.

### Niveau 1 - fausse ce qui est affiché ou calculé

**T1 - L'axe de la matrice qualité × prix est inversé dans le mauvais sens.**
`scale=alt.Scale(domain=[4, -4])` place +4 à gauche et −4 à droite : **les titres décotés apparaissent à droite**, alors que le titre de l'axe affiché indique « ← décote … surcoté → ». Le libellé et l'encodage se contredisent : un lecteur qui fait confiance à la flèche lit le nuage exactement à l'envers. *Correction : une ligne.*

**T2 - L'érosion ne compte que deux pentes sur trois.**
`quality.evalue()` accepte `serie_part_relative`, mais `compute_quality.py` ne la lui passe jamais. `share_slope_5y` est toujours `null`, `erosion_flags` est borné à 2, et le niveau 3 - *érosion confirmée : la décote n'est pas une opportunité* - **n'existe pas dans les données**. Aggravant : la deuxième pente exige la marge brute, que le doc 08 signale comme irrégulièrement publiée en Europe. En pratique `erosion_flags ≥ 2` exige que les deux seules pentes disponibles soient significatives sur 4 points. **Le quadrant value trap, décrit comme le plus important du système, en est structurellement appauvri** - un seul titre y figure. *Correction : une ligne d'appel plus la construction de la série.*

**T3 - Le contrôle de divergence inter-sources est impossible par schéma, pas seulement faute de source.**
`bars` a pour clé primaire `(instrument_id, freq, ts)` : `source_id` n'y figure pas. **Deux sources ne peuvent pas porter la même barre.** Brancher Stooq demain ne suffirait donc pas : la seconde source serait comptée comme une *révision* de la première et l'écraserait silencieusement, en déclenchant éventuellement une alerte `split_unadjusted` - un mauvais diagnostic. Le code et le README attribuent l'inefficacité du contrôle à l'absence de seconde source ; la cause réelle est la clé primaire. *Correction : `primary key (instrument_id, freq, ts, source_id)` ou table de comparaison dédiée.*

**T4 - Les traces de rejet sont auto-clôturées au passage suivant.**
`record_rejections` écrit `issue_type = "gap"` sans `fingerprint`, et `quality_checks.py` clôt automatiquement toute anomalie sans empreinte dont le type est recalculé - `gap` en fait partie. **Toute barre écartée devient invisible dès le premier contrôle qualité suivant.** Par ailleurs les rejets d'opérations sur titre et de faits financiers ne produisent aucune ligne : ils disparaissent dans un compteur agrégé. *Correction : type dédié `rows_rejected` hors de la liste recalculée, plus une empreinte.*

**T5 - La colonne `Quadrant` du screener est une constante littérale.**
`"Quadrant": "unqualified"` en dur, alors que `quality.quadrant()` existe et est appelé par la matrice. Dès qu'un titre sortira de `unqualified`, les deux écrans afficheront des quadrants contradictoires sans que rien ne le signale.

**T6 - Le curseur de seuil de la matrice ne reclasse rien.**
`quadrant()` accepte `seuil_decote` mais est appelé sans lui. Déplacer le curseur déplace le trait dessiné sans reclasser les titres : le filet peut passer d'un côté d'un point dont le quadrant ne bouge pas.

### Niveau 2 - réduit la portée d'un contrôle ou d'une garantie

**T7 - Les contrôles de série ne voient que 3 ans sur 26.**
Saut de cours, série figée et trou de cotation filtrent tous `freq = '1d'`, et le quotidien ne couvre que 3 ans. **Aucun de ces contrôles ne s'applique à la série hebdomadaire de 20 ans qui porte la régression.** Un point aberrant en 2009 passe sans être vu. Le filtre de dilution et l'alerte `split_unadjusted` compensent partiellement.

**T8 - L'archive Parquet est un miroir du chaud, pas une couche plus profonde.**
`export_cold.py` relit `bars`, or aucun job ne télécharge de quotidien au-delà de 3 ans. **Les deux températures ont la même profondeur** : la stratégie du doc 00 §5 n'a qu'une température. Le docstring du fichier cite pourtant la règle qu'il ne tient pas - *si l'on veut un jour du quotidien sur 30 ans, on recharge depuis Parquet*. C'est précisément impossible.

**T9 - `peer_groups.is_complete = true` alors qu'aucun chiffre d'affaires de concurrent n'est renseigné.**
Les 6 groupes manuels portent tous `"ca_musd": null` pour leurs concurrents hors univers. Le refus de saisir des chiffres non sourcés est juste - *fabriquer la précision qu'on cherche à établir* - mais la conséquence l'est moins : `relative_share` et `rank_by_revenue` **ne peuvent pas être calculés contre SharkNinja ou BYD**. Le drapeau autorise le passage en `solid` sur la base d'un classement resté purement européen. **Le garde-fou anti-Lim1 (limite du doc 08 §7) est levé avant que le calcul qu'il protège ne soit possible.**

**T10 - `dfgls_pvalue` n'est pas persistée.**
C'est la p-value, non la statistique, qui alimente BHY et détermine `good`. La colonne n'existe pas dans `regression_fits`. **Dans trois ans, le verdict ne sera pas reconstructible depuis la table** - ce qui entame le principe P5 exactement là où il compte. Même remarque pour les motifs de `quality_tier`, calculés, affichés, jamais stockés, alors que l'équivalent existe pour les fits.

**T11 - Deux définitions concurrentes du ROIC.**
`quality.py` : `NOPAT / (capitaux propres + dette nette)`. `ratios.py` : `NOPAT / invested_capital`. Le même nom désigne deux grandeurs selon le module, rien ne les réconcilie.

**T12 - Conversions temporelles hebdomadaires codées en dur.**
`demi_vie_semaines * 7.0` et `SEMAINES_PAR_AN` supposent des barres hebdomadaires. La politique `real_deflated` travaille en mensuel : une demi-vie de 10 mois serait écrite 70 jours au lieu de ~304. Latent, se déclenche dès la première matière première.

**T13 - Le tri du screener n'est pas celui de la spec.**
Tri sur `fit_quality` puis z, alors que la spec pose quadrant puis z. Le commentaire du code annonce le tri de la spec, la caption affichée annonce le tri réel. Conséquence de T5.

### Niveau 3 - conformité et hygiène

**T14** - `z rel. pairs` n'existe nulle part dans le dépôt, alors que le doc 03 §7.3 en fait « la métrique la plus discriminante et la plus négligée ».
**T15** - 6 filtres screener sur 11 absents, dont classe d'actif, quadrant, niveau de qualité et régime - trois de ces données sont pourtant déjà ramenées par la requête.
**T16** - Bloc D : les petits multiples de tendance sur 5 ans sont remplacés par des tableaux. `moat_sources`, `threats` et `rationale` sont chargés puis jetés.
**T17** - ~~Bloc E : instantané mono-période au lieu d'une série 5 ans, sans source ni date par valeur ; extractions LLM non marquées visuellement.~~ **Sans objet depuis le 2026-08-25 : le bloc E a été retiré de la fiche.** Un filtre de solvabilité, pas un jugement de qualité — et le verdict de cohérence prix/fondamentaux qu'il portait reste lisible au screener et à la matrice, là où il sert à classer. La dette revient telle quelle si le bloc est remis.
**T18** - Palette de statuts dupliquée en dur dans la fiche et réutilisée pour `quality_tier` et pour la cohérence prix/fondamentaux, alors que `theme.py` énonce la règle transgressée : *une couleur qui sert à deux choses ne sert plus à rien*. Ces valeurs ne suivent pas la bascule clair/sombre.
**T19** - Libellé de statut remplacé par le code technique dans le tableau (`● good` au lieu du libellé complet). L'accessibilité daltonienne est sauve, la lisibilité non.
**T20** - Le jumeau tabulaire de la matrice n'est pas filtré comme le nuage : dès qu'on filtre, il cesse d'être un jumeau.
**T21** - Zones d'épisodes dessinées dans la teinte de série 1, alors que ce sont des zones de référence.
**T22** - Mode sombre partiel : `.streamlit/config.toml` n'a qu'un jeu de valeurs, le chrome Streamlit reste clair, l'état du toggle n'est pas partagé entre écrans.
**T23** - Absents du pipeline : jitter sur le débit, cache disque 24h, circuit breaker à 20% d'échecs. Sans cache, relancer un job en développement retape la source - le principe *rejouer la normalisation sans retélécharger* est affirmé mais impraticable.
**T24** - `fetch_actions` n'a ni retry ni backoff, contrairement aux deux autres collecteurs.
**T25** - Six commandes prescrites par le README pointent vers des fichiers `scripts/` inexistants ; la logique est dans `jobs/`, les enveloppes CLI manquent.
**T26** - Pas d'historisation des ISIN, alors que le CSV documente deux changements (Michelin 2022, Dassault 2021). Même problème temporel que celui qui a justifié `instrument_symbols`, non traité pour la clé métier.
**T27** - `min_observations = 500` (≈9.6 ans) est dominé par `min_years = 15` : le critère ne peut jamais se déclencher seul.
**T28** - Le critère `ca_non_decroissant` est biaisé par une année de base 2022 - pic d'inflation. BASF, Engie, Iberdrola, Arkema, Telefónica sortent `suspect` mécaniquement. À calibrer sur une médiane sectorielle plutôt que sur zéro.
**T29** - Aucun `check` sur les domaines textuels (`fit_quality`, `quality_tier`, `regime`, `quadrant`, `severity`…) : ces valeurs ne vivent qu'en commentaire SQL.
**T30** - L'IP et l'utilisateur du VPS figurent en clair dans le README versionné.

---

## 6. Ce que le code a fait mieux que la spec

À porter au crédit de l'implémentation, et à conserver.

- **Deux instructions SQL de la spec ne s'exécutaient pas** - `COALESCE` dans une clause `UNIQUE` sur `corporate_actions`, et pire, dans une clé primaire sur `peer_group_members`. Converties en index uniques expressionnels, avec le motif documenté. Un `check` d'identification a été ajouté au passage : la spec permettait une ligne entièrement vide.
- **Le seed de la spec violait sa propre contrainte** : `min_years null` sur une colonne `not null`.
- **Contrôle `split_unadjusted`** - détecte la réécriture rétroactive massive de la série par Yahoo. Inexistant dans la spec, et indispensable au choix de stocker `Close`.
- **`verify_universe.py`** - triple contrôle du référentiel : clé de Luhn sur l'ISIN, téléchargement réel d'une cotation, et **concordance de raison sociale** qui attrape le cas Seb / Skandinaviska Enskilda Banken à 0.19 de similarité. La spec disait que l'étape serait « manuelle et fastidieuse » sans fournir d'outil, alors qu'elle identifiait le risque : *un mapping faux ne se voit jamais*.
- **Chargement par `COPY` en table de transit** puis un seul `insert … select`, avec prédicat `is distinct from` sur le `do update` - ce qui rend le comptage des révisions exploitable et fait passer le backfill d'heures à secondes par titre.
- **Réponse vide de yfinance traitée comme échec temporaire** : Yahoo rate-limite en renvoyant un DataFrame vide, sans quoi un titre refusé serait enregistré comme dépourvu d'historique et classé `rejected` à tort.
- **`R2_TENDANCE_MONOTONE`** - le discriminant cycle / effondrement, absent de la spec et nécessaire.
- **Démarche de validation honnête sur L4** : le critère « paramètres retrouvés à 1% près » n'est pas atteignable sur un tirage unique à σ élevé, et ce n'est pas un défaut du code - l'erreur-type de σ̂ vaut 2.2% sur 1 040 points, il en faudrait 45 000 pour tenir 1%. Trois tests plus forts ont été substitués, et l'écart est expliqué plutôt que masqué.
- **Refus de déclarer la comparaison Hiboo faite** : *déclarer une superposition sans l'avoir constatée serait exactement la validation fictive que ce projet cherche à éviter*.

---

## 7. Priorités

**Corriger avant tout usage décisionnel** - une demi-journée pour l'ensemble : T1 (axe inversé), T2 (troisième pente), T5 (quadrant en dur), T6 (curseur découplé).

**Avant d'ajouter une source** : T3 (clé primaire de `bars`). Sans cette correction, brancher une seconde source dégraderait les données au lieu de les valider.

**~~Le plus urgent qui n'est pas un bug : L7.~~ Traité le 2026-08-21.** Le principe P5 - la décision la plus importante de tout le projet - ne produisait sa valeur que par régularité, et rien ne garantissait cette régularité. Le cycle tourne maintenant toutes les 8 heures sur le VPS : aucune observation ne se perd plus faute d'exécution. Ce qui reste de L7 - rapport hebdomadaire, alerte sur échec - est du confort, pas de la dette irrécupérable.

**À arbitrer, pas à corriger** : la source unique (D-B). Le motif est solide, la conséquence reste ouverte.
