# 03 - Moteur analytique

**Langage :** Python. **Dépendances :** numpy, pandas, statsmodels, arch (pour DF-GLS et bootstrap).
**Principe :** le moteur tourne côté VPS, la base ne fait que stocker. Aucun calcul lourd en SQL.

> **État : implémenté et conforme sur l'essentiel.** L'ADF est bien appelé avec `regression="ct"` sur le **log-prix** et non sur les résidus - l'erreur que §3.2 signale comme la plus coûteuse et la plus silencieuse est évitée, documentée en tête de module, et couverte par un test anti-régression qui montre que la version fautive rejette à tort sur une marche aléatoire (p < 0.05) là où la bonne ne rejette pas (p > 0.10). Écarts signalés en ligne par des blocs `⚙ Réel`.

---

## 1. Le modèle de base

### 1.1 Formulation

Pour un instrument, sur une fenêtre de N années à fréquence hebdomadaire, on estime par moindres carrés ordinaires :

```
log(P_t) = α + β·t + ε_t
```

où `t` est exprimé **en années** depuis le début de la fenêtre.

Trois quantités en sortent :

| Grandeur | Formule | Interprétation |
|---|---|---|
| Pente annualisée | `exp(β) − 1` | Rendement annuel moyen de la tendance |
| Écart-type résiduel | `σ = sqrt(Σεᵢ² / (n−2))` | Dispersion autour de la tendance |
| Score de position | `z = (log P_T − α − β·T) / σ` | Position courante en écarts-types |

C'est très exactement la méthode Hiboo, et elle tient en quatre lignes de numpy. **La difficulté n'est pas là - elle est dans tout ce qui l'entoure.**

### 1.2 Choix de la fenêtre : glissante, pas expansive

Fenêtre **glissante** de N années, N défini par `regression_policies.window_years`.

*Justification :* une fenêtre expansive - tout l'historique disponible - donne un poids croissant au passé lointain et ne s'adapte jamais à un changement de régime. Une fenêtre glissante de 20 ans reste longue tout en oubliant progressivement ce qui n'est plus pertinent.

*Marie de Raismes justifie la stabilité autrement : "le fait de prendre un historique d'au moins 20 ans fait que les modifications des deux années qui suivent sont marginales". C'est vrai, et c'est un argument en faveur de la fenêtre glissante : elle bouge peu, donc on ne perd rien à l'utiliser.*

### 1.3 Fréquence : hebdomadaire

L'estimation porte sur les barres hebdomadaires, jamais quotidiennes.

*Justification statistique, et pas seulement de volume :* la puissance d'estimation d'une tendance dépend de **l'étendue temporelle, pas du nombre de points** (Shiller & Perron, 1985). 1 560 points hebdomadaires sur 30 ans contiennent quasiment la même information sur la tendance que 7 560 points quotidiens, avec cinq fois moins de bruit de microstructure.

### 1.4 Pondération : aucune

OLS simple, observations équipondérées.

*Alternative envisageable : moindres carrés pondérés avec décroissance exponentielle, qui donnerait plus de poids au passé récent. Écartée en v1 - c'est un paramètre libre supplémentaire, donc une porte ouverte au surajustement, et ça éloigne de la méthode de référence qu'on cherche à reproduire.*

---

## 2. Préparation des données - là où se cachent les vrais problèmes

Ordre des opérations, strictement.

### Étape 1 - Ajustement des cours

Reconstitution de la série ajustée depuis `bars.close` (brut) et `corporate_actions` :

```
close_ajusté(t) = close_brut(t) × facteur_cumulé(t)
```

où `facteur_cumulé(t)` est le produit des ratios de tous les splits postérieurs à `t`.

**Deux séries sont calculées :**
- `factor_price` : splits seuls → comparable aux graphes Hiboo
- `factor_total` : splits + dividendes réinvestis → économiquement correct

**Décision v1 :** la régression porte sur la série **`factor_price`**, pour rester comparable à la référence. `factor_total` est calculé et stocké, et sert à la mesure de performance.

> **⚙ Réel : `factor_price = 1.0` partout, et ce n'est pas un oubli.** Le `Close` de Yahoo est **déjà rétro-ajusté des splits** ; réappliquer les ratios de `corporate_actions` diviserait la série une seconde fois. Air Liquide, qui distribue une action gratuite pour dix tous les deux ans, verrait son historique divisé par 1.1 à chaque opération. **C'est le type d'erreur qui ne se voit pas : la courbe reste lisse, seule la pente est fausse.** Voir doc 00 P4 amendé et doc 09 D-A.
>
> `factor_total` ne porte donc que les dividendes. Vérifié sur Air Liquide, 1 390 barres : **écart médian 0.036%**, exact sur les dates récentes, maximum 3.9% sur une semaine de détachement de 2009. Le résidu vient de la granularité hebdomadaire ; le supprimer exigerait 30 ans de quotidien à chaque calcul, ce qui rendrait les facteurs non reconstructibles depuis les seules tables `raw` - **violation de P1. L'approximation est le prix de ce principe, et elle est mesurée.**
>
> **Garde-fou manquant :** rien n'empêche un branchement futur sur une source servant le cours nominal, qui produirait alors silencieusement des pentes fausses.

### Étape 2 - Filtres d'éligibilité, avant tout calcul

Un instrument est écarté si l'une de ces conditions est vraie :

| Condition | Motif |
|---|---|
| Historique < `min_years` de la politique | `short_history` |
| Nombre d'observations < `min_observations` | `insufficient_data` |
| Dilution détectée dans la fenêtre | `dilution_detected` |
| Politique = `excluded` (crypto, FX) | `policy_excluded` |
| Problème qualité bloquant non résolu | `data_quality` |
| Trous > 10% des observations attendues | `too_many_gaps` |

**Le filtre de dilution mérite d'être détaillé,** parce que c'est celui qui n'existe nulle part ailleurs et qui évite le plus gros piège.

```
Si nombre d'actions(t) / nombre d'actions(t−12 mois) > 1.5
    → invalider la régression sur toute fenêtre incluant t
    → marquer quality_reasons = ['dilution_detected']
    → l'instrument sort du screener jusqu'à ce que 20 ans se soient écoulés
      depuis l'événement, ou jusqu'à revue manuelle
```

*Sans ce filtre, Atos, Casino, Solocal et leurs semblables apparaîtront en tête du screener avec un z-score de −4, parce que la droite historique a été calculée sur une valeur par action qui n'existe plus. C'est le piège le plus coûteux de toute la méthode, et il est invisible sur le graphe.*

> **⚙ Réel : implémenté plus strictement (doc 09 D-I).** Comparaison au **minimum glissant sur 365 jours** plutôt qu'au point à −12 mois, sur un nombre d'actions **neutralisé des splits**. Sans cette neutralisation, quatre faux positifs - Dassault ×5.09, Michelin ×4.0, Aena ×10.7, Prosus ×2.43. Une seule alerte par titre, contre 203 lignes pour Prosus autrement.
>
> **Éprouvé sur données synthétiques** : Atos et Casino ne sont pas dans les 57 titres. *Cela teste la règle, là où un titre réel ne ferait que la constater.*

### Étape 3 - Traitement des trous

Interpolation interdite. Un jour sans cotation est un jour sans donnée : on l'omet, on ne l'invente pas.

*L'interpolation crée une autocorrélation artificielle qui fausse tous les tests de diagnostic en aval.*

---

## 3. Estimation et diagnostics

### 3.1 Ajustement

```python
import numpy as np

def fit_log_linear(dates, prices):
    t = (dates - dates[0]).days / 365.25          # en années
    y = np.log(prices)
    X = np.column_stack([np.ones_like(t), t])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    sigma = np.sqrt((resid ** 2).sum() / (len(y) - 2))
    return {
        "intercept":     beta[0],
        "slope_annual":  np.exp(beta[1]) - 1,
        "sigma_resid":   sigma,
        "z_score":       resid[-1] / sigma,
        "r_squared":     1 - (resid ** 2).sum() / ((y - y.mean()) ** 2).sum(),
    }
```

### 3.2 Diagnostics - la partie qui distingue ce système d'un screener naïf

**Test de racine unitaire, avec la bonne spécification.**

```python
from statsmodels.tsa.stattools import adfuller, kpss

# ⚠ SUR LE LOG-PRIX, avec constante ET tendance. PAS sur les résidus.
adf = adfuller(np.log(prices), regression="ct", autolag="AIC")
kps = kpss(np.log(prices), regression="ct", nlags="auto")
```

> **⚙ Résultat mesuré : 38 `weak`, 19 `rejected`, 0 `good` sur 57 titres.** Quatre titres seulement rejettent la racine unitaire au seuil brut de 5% - Ahold, Getlink, Michelin, Hermès. **Sur 54 tests, un taux de rejet de 7.4% est statistiquement indiscernable du taux de faux positifs de 5%.** La correction BHY divise le seuil par 4.56 et n'en laisse passer aucun.
>
> C'est le résultat le plus important du projet à ce stade. §3.3 annonçait que `weak` serait majoritaire ; la réalité est plus dure : **aucun titre européen de l'univers ne présente de retour à la tendance statistiquement établi sur 20 ans.** Le système dit qu'il ne sait pas, ce qui est le comportement voulu - et ce qu'un screener qui afficherait seulement des z-scores ne dirait jamais.

**Ce point précis est celui où l'implémentation naïve échoue silencieusement.** Appliquer un ADF standard aux résidus d'une régression aux coefficients estimés invalide les valeurs critiques et sur-rejette massivement : on obtiendrait une liste de titres « stationnaires » entièrement fictive. Par le théorème de Frisch-Waugh, le test correct est l'ADF avec constante et tendance directement sur le log-prix, avec les valeurs critiques τ_τ (≈ −3.41 à 5%).

**DF-GLS, parce que l'ADF manque de puissance.**

```python
from arch.unitroot import DFGLS
dfgls = DFGLS(np.log(prices), trend="ct")
```

*Elliott-Rothenberg-Stock (1996) est nettement plus puissant que l'ADF sur les alternatives proches de la racine unitaire - exactement notre cas.*

**Intervalle de confiance sur la racine autorégressive, plutôt qu'un verdict binaire.**

C'est le point méthodologique le plus important de cette section. Sur 20 ans, aucun test ne distingue de façon fiable ρ = 1 de ρ = 0.99. Rendre un verdict binaire « stationnaire / non stationnaire » revient à fabriquer une certitude qui n'existe pas.

**On rapporte donc un intervalle** - par inversion du test (méthode de Stock, 1991) ou par bootstrap par blocs - stocké dans `ar1_ci_low` / `ar1_ci_high`. Un intervalle [0.94, 1.02] dit la vérité : on ne sait pas.

> **⚙ Réel : bootstrap par blocs, et il ne décide de rien.** 400 tirages, blocs de 26 semaines, graine dérivée de l'instrument et de la date - donc reproductible. L'intervalle est **anti-conservateur près de la racine unitaire** : sur Seb il ressort à [0.943 ; 0.968], qui exclut 1, alors que le DF-GLS sur le même titre ne rejette pas. **C'est le test qui a raison.** L'intervalle est affiché parce qu'il dit l'incertitude, mais **le DF-GLS arbitre seul `fit_quality`**. Une inversion de test à la Stock corrigerait le point ; non prise en v1.

**Demi-vie du retour à la moyenne.**

```python
# Δε_t = λ·ε_{t−1} + u_t   →   demi-vie = −ln(2) / ln(1+λ)
d_resid   = np.diff(resid)
lag_resid = resid[:-1]
lam = np.linalg.lstsq(lag_resid[:, None], d_resid, rcond=None)[0][0]
half_life = -np.log(2) / np.log(1 + lam) if -2 < lam < 0 else np.inf
```

**Cette métrique est plus actionnable que le z-score lui-même.** Un titre à −2σ avec une demi-vie de 18 mois et un titre à −2σ avec une demi-vie de 9 ans ne sont pas la même proposition, alors qu'ils ont le même score. C'est l'information qui manque totalement dans la présentation Hiboo.

**Durbin-Watson**, diagnostic gratuit d'autocorrélation résiduelle, à afficher systématiquement.

### 3.3 Verdict de qualité

> **⚙ Constantes réelles, dont trois n'étaient pas dans la spec.** Seuil de « DF-GLS très loin du rejet » : `dfgls_crit_5 / 2` ≈ −1.44, un `/2` sans justification statistique qui pilote directement le taux de `rejected`. Bootstrap : 400 tirages, blocs de 26. `min_observations = 500` (≈9.6 ans) est **dominé par `min_years = 15`** et ne peut donc jamais se déclencher seul - le critère est vide de contenu (dette T27).
>
> **Dette T12 :** la demi-vie est convertie par `× 7.0` et les horizons de régime par `SEMAINES_PAR_AN`, tous deux codés en dur. La politique `real_deflated` travaille en mensuel : une demi-vie de 10 mois serait écrite 70 jours au lieu de ~304. Latent, se déclenche à la première matière première.

```
fit_quality =
  'good'      si  DF-GLS rejette la racine unitaire à 5%
                  ET n_obs ≥ min_observations
                  ET aucune raison bloquante
                  ET r² ≥ 0.5

  'weak'      si  le test ne tranche pas (cas le plus fréquent, et c'est normal)
                  ET aucune raison bloquante

  'rejected'  si  raison bloquante
                  OU historique insuffisant
                  OU DF-GLS très loin du rejet
```

**`weak` doit être le cas majoritaire, et l'interface doit l'assumer.** Si la répartition sortait à 80% de `good`, ce serait le signe d'un bug, pas d'un univers exceptionnel. Un système honnête dit qu'il ne sait pas la plupart du temps.

*Note : le verdict de qualité est lui-même soumis à la multiplicité - sur 54 tests à 5%, on attend près de 3 faux `good`. Le seuil doit être corrigé (Benjamini-Hochberg-Yekutieli), ce qui vaut aussi bien ici qu'au chapitre du screening.*

---

## 4. Interprétation du z-score - ce qu'on affiche et ce qu'on n'affiche pas

### Ce qu'on n'affichera jamais

> « Ce titre est à −2σ, donc il a 95% de chances de remonter. »

**C'est faux et c'est le contresens central de la méthode telle qu'elle est vendue.** Les résidus sont fortement autocorrélés : les épisodes hors bande ne sont pas des événements indépendants de fréquence 5%, ce sont des **régimes qui durent**. « Moins de 5% du temps » est une fréquence temporelle, pas une probabilité de retournement.

### Ce qu'on affiche à la place - les statistiques de régime

Pour chaque instrument, calculées sur l'historique disponible et **explicitement étiquetées comme in-sample** :

| Métrique | Question à laquelle elle répond |
|---|---|
| Nombre d'épisodes sous −2σ | Est-ce vraiment rare pour ce titre ? |
| Durée médiane et maximale d'un épisode | Combien de temps faut-il tenir ? |
| Drawdown médian **après** franchissement du seuil | Combien ça peut encore baisser ? |
| Rendement à 1, 3 et 5 ans après franchissement | Distribution, pas moyenne |
| Demi-vie estimée | Vitesse de rappel vers la tendance |
| Semaines consécutives sous le seuil, en cours | Depuis quand ? |

> **⚙ Réel, sur Seb au 18 août 2026 :** z = −2.16 · 4 épisodes sous −2σ depuis 2006, soit 6.0% du temps · durée médiane 8 semaines, maximum 46 · **épisode en cours 46 semaines, le plus long jamais observé** · creux supplémentaire médian −7.7%, pire −17.0% · rendement post-franchissement +75% à 1 an et +169% à 3 ans, **sur n = 3, in-sample** · demi-vie 3.4 ans.
>
> *Exactement ce que ce paragraphe réclamait. « Le plus long épisode jamais observé, avec une demi-vie de 3.4 ans » est une information de gestion. « 95% de chances de remonter » n'en était pas une.*
>
> Réserve : la « distribution » des rendements est réduite à min / médiane / max, sans quartiles.

**C'est la distribution du temps de premier passage, et elle change complètement la lecture.** Découvrir qu'un titre reste typiquement 14 mois sous −2σ avec un creux supplémentaire de 20% est une information de gestion, pas une statistique décorative. C'est exactement le vécu que Marie décrit sur Seb : *« on a commencé à l'acheter à −2 écarts-types et on a plongé à −2.66 »*.

---

## 5. Le calcul hebdomadaire et l'accumulation hors échantillon

> **⚙ Orchestré depuis le 2026-08-21, et le pas est passé de la semaine au jour.** Le cron du VPS lance `scripts/cycle.py` toutes les 8 heures ; `compute_fits` y tourne à chaque passage. L'accumulation hors échantillon décrite ci-dessous est donc **quotidienne** et non plus hebdomadaire, et la série hebdomadaire reste extractible telle quelle par filtre sur le jour de la semaine.
>
> **Une conséquence à connaître sur l'écriture.** Le conflit sur `as_of_date` se résout maintenant en mise à jour, sans quoi les deuxième et troisième passages du jour calculeraient sans rien écrire : dans la journée, le dernier passage remplace le précédent. **Dès que le jour est passé, la ligne est figée définitivement** - l'observation historisée est le dernier état connu de ce jour-là, jamais un mélange, jamais une réécriture rétrospective. Voir README §*Ce que P5 devient avec un cycle de 8 heures*.

```
Chaque dimanche, pour chaque instrument éligible :
   1. charger les barres hebdo ≤ as_of_date              ← aucune donnée future
   2. appliquer les filtres d'éligibilité
   3. estimer le modèle sur la fenêtre de la politique
   4. calculer les diagnostics
   5. INSÉRER une ligne dans regression_fits (jamais de mise à jour)
   6. produire le cliché de screener
```

**Le point 5 est le mécanisme décrit dans le principe P5.** Chaque ligne est un enregistrement de ce que le système affirmait à cette date, avec les seules informations dont il disposait. Il n'est jamais réécrit.

Au bout d'un an : 52 observations réellement hors échantillon. Au bout de trois ans : un jeu de données que personne ne publie - le comportement effectif des titres après un signal, mesuré en temps réel, sans possibilité de look-ahead.

*C'est la validation de la méthode obtenue par simple écoulement du temps, sans backtest. Le coût est d'un champ `as_of_date` et de quelques mégaoctets par an.*

### Versionnement des méthodes

`method_version` sur `regression_fits`. Changer une formule signifie incrémenter la version et recalculer, sans écraser l'ancienne. On peut ainsi comparer deux méthodes sur la même période, et l'historique reste interprétable.

---

## 6. Politiques par classe d'actif

### Actions - `loglin_20y`
Le cas de référence. Fenêtre 20 ans, hebdomadaire, minimum 15 ans.

### Indices et ETF - `loglin_30y`
Fenêtre 30 ans. *Marie justifie ce choix par la stabilité du régime monétaire depuis les années 1990. C'est raisonnable et ça permet de répondre directement à la question « l'ETF est-il cher aujourd'hui ».*

**Précision utile sur les ETF :** un ETF récent n'a pas 30 ans d'historique, mais **l'indice qu'il réplique en a**. La régression se fait sur l'indice, et le z-score de l'indice est attribué à l'ETF via un lien de référence. Sans ça, aucun ETF n'est analysable.

### Matières premières - `real_deflated`
Fenêtre 50 ans, mensuelle, **sur les prix déflatés** par l'IPCH.

*Justification : la tendance nominale d'une matière première est essentiellement de l'inflation. En termes réels, la tendance longue de l'or est proche de zéro sur un siècle - une droite ascendante n'aurait aucun sens. Et la rupture de Bretton Woods en 1971 interdit toute régression qui la traverse : la fenêtre doit commencer après.*

### Crypto et FX - `excluded`
Aucune régression log-linéaire.

*Justification : ce n'est pas que la pente soit élevée - environ 58% de rendement annualisé sur dix ans pour le bitcoin, bien davantage si l'on remonte plus loin. **C'est que la pente n'est pas un paramètre stable : elle dépend entièrement de la date de départ choisie.** C'est la définition d'un régime non stationnaire, et aucun modèle à tendance déterministe ne s'y applique.*

*Si l'on y tient un jour, la forme fonctionnelle candidate est log-log (« power law »), et elle exige sa propre politique, ses propres diagnostics et sa propre validation. Ce n'est pas un paramètre à changer, c'est un autre modèle.*

---

## 7. Couche fondamentale

### 7.1 Ratios calculés

Depuis `financial_facts`, avec le point-in-time respecté - on n'utilise que les faits dont `published_at ≤ as_of_date`.

| Famille | Ratios |
|---|---|
| Valorisation | PER, EV/EBIT, EV/CA, P/B, rendement du FCF, rendement du dividende |
| Rentabilité | Marge opérationnelle, marge nette, ROE, ROCE |
| Solidité | Dette nette / EBITDA, couverture des intérêts, gearing |
| Dynamique | Croissance du CA et du résultat sur 3 et 5 ans, régularité |
| Distribution | Taux de distribution, historique de dividende, dilution nette |

### 7.2 Contrôle de cohérence prix / fondamentaux

Répond directement à la consigne de Marie : *« une fois que tu as vu qu'il y avait un signal de prix, tu vérifies que c'est cohérent avec les fondamentaux »*.

```
signal_confirmé  si  z ≤ seuil
                 ET  CA non décroissant sur 3 ans
                 ET  résultat opérationnel positif sur au moins 3 des 5 derniers exercices
                 ET  dette nette / EBITDA < 4
                 ET  aucune dilution nette significative

signal_suspect   si  z ≤ seuil mais un critère fondamental est en échec
                     → c'est un value trap potentiel, pas une opportunité
```

> **⚙ Deux amendements réels.**
>
> **(a) Un troisième verdict, `indéterminable`.** La spec n'avait que `confirmé` et `suspect` : **traiter un critère non évaluable comme un critère réussi fabrique de faux signaux.** Répartition mesurée : 35 `confirmé`, 17 `suspect`, 5 `indéterminable`.
>
> **(b) Les ratios sont neutralisés pour le secteur financier (ICB 30).** La notion de chiffre d'affaires n'a pas de définition stable pour un assureur - Allianz sortait à 25% d'écart sur la marge nette là où les industriels tombent à 0.0%. Marges, EV/CA, EV/EBIT, dette nette/EBITDA, gearing et couverture des intérêts passent à `null`, et le critère de levier est neutralisé : **une banque a structurellement un levier de 15 à 20, elle sortirait `suspect` à chaque passage pour une raison qui n'en est pas une.**
>
> **Biais connu à corriger (dette T28) :** presque tous les `suspect` le sont pour `ca_non_decroissant`, et la fenêtre de 3 ans démarre en **2022, année du pic d'inflation**. BASF, Engie, Iberdrola, Arkema et Telefónica affichent une croissance négative parce que leur base de départ est exceptionnelle, pas parce qu'elles se délitent. À recalibrer sur une médiane sectorielle plutôt que sur zéro.

**Sortir les signaux suspects est aussi utile que sortir les bons.** C'est la liste des titres qui ont l'air décotés et ne le sont pas - et c'est là qu'on perd de l'argent.

*Ce contrôle est un filtre de solvabilité, pas un jugement de qualité. Une entreprise peut cocher toutes ces cases et perdre sa position concurrentielle - c'est l'objet du doc 08.*

### 7.3 Décote spécifique ou sectorielle

| Métrique | Calcul |
|---|---|
| Z-score relatif au secteur | z du titre − médiane des z du groupe de pairs |
| Décote spécifique vs sectorielle | Le groupe entier est-il décoté, ou seulement ce titre ? |

> **⚙ Dette T14 : `z rel. pairs` n'existe nulle part dans le dépôt.** Ni dans `analytics/`, ni dans les jobs, ni au dashboard. C'est la métrique que ce paragraphe qualifie de plus discriminante, et c'est la seule du doc 03 à n'avoir aucune ligne de code.

**C'est la métrique la plus discriminante et la plus négligée.** Un titre à −2σ dans un secteur entièrement à −2σ ne raconte pas la même histoire qu'un titre à −2σ isolé parmi des pairs à leur moyenne. Le premier est un pari sectoriel - le secteur automobile européen du podcast. Le second est un pari idiosyncrasique. Ce sont deux décisions différentes.

### 7.4 Position concurrentielle → doc 08

**Tout ce qui touche au leadership, à la rente et à son érosion fait l'objet d'un document dédié.** C'est la seconde jambe de la méthode, d'égale importance avec le prix, et elle ne se réduit pas à quelques ratios en annexe du moteur de régression.

Résumé de l'articulation :

| | Prix (ce document) | Qualité (doc 08) |
|---|---|---|
| Fréquence | Hebdomadaire | Trimestrielle |
| Sortie | `regression_fits` | `quality_scores` |
| Question | Le titre est-il bas ? | L'entreprise mérite-t-elle d'être détenue ? |
| Historisé | Oui, `as_of_date` | Oui, `as_of_date` |

**Les deux se calculent indépendamment et ne se croisent qu'au screener.** Un moteur de prix qui consulterait la qualité, ou l'inverse, introduirait une circularité difficile à diagnostiquer.

**Règle qui s'impose au moteur de prix :** un titre dont la qualité n'a jamais été évaluée produit bien un `regression_fit`, mais n'apparaît **jamais** comme opportunité. Il apparaît comme *signal de prix non qualifié* - quadrant `unqualified`. C'est exactement son statut, et l'afficher autrement serait mentir par omission.

---

## 8. Ce que le moteur ne calcule pas, délibérément

- **Aucun score composite sur 100.** Agréger un z-score, une croissance et un ratio d'endettement dans un chiffre unique détruit l'information et fabrique une fausse précision, qui fait prendre des positions plus grosses.
- **Aucune prévision de cours.** Ni objectif, ni horizon, ni probabilité de gain.
- **Aucun signal de vente automatique.** Le franchissement de +1σ est affiché, il ne déclenche rien.
- **Aucun indicateur d'analyse technique.** RSI, MACD et consorts opèrent sur un horizon incompatible avec la thèse, et Marie elle-même les qualifie d'entrailles de poulet.
- **Aucun backtest en v1.** Non par principe, mais parce que la table `regression_fits` en produira un vrai, en temps réel, sans hypothèse contestable.

---

## À challenger en priorité

1. **Fenêtre glissante plutôt qu'expansive.** Hiboo semble utiliser tout l'historique. La fenêtre glissante s'adapte mieux aux changements de régime mais rend la droite légèrement plus mobile.
2. **Régression sur le cours ajusté des splits seuls, pas sur le rendement total.** Choix de comparabilité avec la référence, pas de justesse économique.
3. **Le filtre de dilution est mon apport le plus fort à la méthode.** Il n'existe nulle part ailleurs, et il évite précisément les Atos. Le seuil de +50% sur 12 mois est à calibrer.
4. **Le remplacement du z-score seul par les statistiques de régime.** C'est un changement d'interface autant que de calcul, et il rend le système moins vendeur et plus honnête. Assume-le ou pas, mais c'est un choix.
5. **L'exclusion de la crypto** est une position ferme de ma part. Si tu veux l'intégrer, il faut un modèle distinct, pas un paramètre différent.
