# 06 - Décisions d'architecture et points ouverts

---

## 1. Décisions actées

Format compact : décision, alternative écartée, motif, réversibilité.

### D1 - Postgres strictement standard, aucune fonctionnalité Supabase propriétaire
**Écarté :** exploiter RLS, Edge Functions, Realtime.
**Motif :** la migration vers le VPS doit rester un `pg_dump | psql`. La contrainte de 500 Mo sera atteinte tôt ou tard.
**Réversibilité :** totale tant qu'on s'y tient. Nulle si on commence à en dépendre.

### D2 - Stockage à deux températures : hebdomadaire long en base, quotidien complet en Parquet froid
**Écarté :** tout le quotidien en base.
**Motif :** divise le volume par cinq sans perte d'information sur la tendance longue - la puissance d'estimation dépend de l'étendue temporelle, pas de la fréquence (Shiller-Perron, 1985).
**Réversibilité :** bonne, l'archive froide contient tout.
**⚙ Non tenue (dette T8) :** l'archive Parquet relit `bars` et aucun job ne descend sous 3 ans de quotidien. **Il n'y a qu'une température** - l'archive froide ne contient pas tout.

### D3 - Cours brut stocké, ajustement calculé — **amendé par D17 et D18**
**Écarté :** stocker l'`adj_close` du provider.
**Motif :** l'`adj_close` est recalculé rétroactivement à chaque dividende. Un backtest bâti dessus n'est pas reproductible et on ne s'en aperçoit jamais.
**Réversibilité :** faible - il faudrait retélécharger.
**⚙ Amendement :** le cours nominal n'existe chez aucune source gratuite. On stocke `Close` (rétro-ajusté des splits, réécrit 2 fois en 12 ans) et non `Adj Close` (réécrit à chaque dividende) ; l'ajustement de splits **n'est pas recalculé**, `factor_price = 1.0`. Le principe protège la reproductibilité, pas le caractère nominal.

### D4 - Bitemporalité systématique (`period_end` / `published_at`, `as_of_date`)
**Écarté :** ne stocker que la date de la donnée.
**Motif :** sans ça, tout look-ahead bias est structurel et irrattrapable.
**Réversibilité :** nulle. L'information passée ne se reconstitue pas.

### D5 - Historisation hebdomadaire de `regression_fits`
**Écarté :** table à état courant, mise à jour en place.
**Motif :** produit un jeu hors échantillon réel par simple écoulement du temps. Coût : quelques Mo par an.
**Réversibilité :** nulle dans le sens rétroactif. **C'est la décision la plus importante du projet.**

### D6 - Identité par ISIN, tickers dans une table de mapping temporel
**Écarté :** ticker comme clé.
**Motif :** les tickers changent, sont réutilisés, diffèrent par provider.
**Réversibilité :** coûteuse.

### D7 - Politique de régression comme donnée, pas comme constante de code
**Écarté :** paramètres en dur.
**Motif :** ajouter une classe d'actif ne doit pas être un chantier ; l'exclusion de la crypto doit être lisible dans la donnée.
**Réversibilité :** bonne.

### D8 - Régression sur barres hebdomadaires, fenêtre glissante
**Écarté :** quotidien, ou fenêtre expansive.
**Motif :** hebdomadaire pour le rapport signal/bruit ; glissante pour s'adapter aux changements de régime.
**Réversibilité :** totale, c'est un recalcul.

### D9 - Filtre de dilution bloquant
**Écarté :** ne rien faire, comme les screeners du marché.
**Motif :** évite les faux signaux extrêmes sur les sociétés massivement diluées mais toujours cotées - Atos, Casino, Solocal.
**Réversibilité :** totale.

### D10 - Aucun score composite, aucune probabilité affichée
**Écarté :** une note sur 100.
**Motif :** agréger des grandeurs incomparables fabrique une précision fausse, et la précision fausse fait prendre des positions plus grosses.
**Réversibilité :** totale, mais ce serait une régression de conception.

### D11 - Aucune sortie entre deux rapports hebdomadaires
**Écarté :** alertes, notifications, temps réel.
**Motif :** plus le feedback est fréquent, plus le rendement accumulé baisse (Thaler, Tversky, Kahneman & Schwartz, 1997). L'outil ne doit pas augmenter la fréquence de décision.
**Réversibilité :** totale, mais c'est un choix de fond.

### D12 - La qualité est calculée indépendamment du prix, à fréquence trimestrielle
**Écarté :** un score unique mêlant décote et qualité ; ou un recalcul hebdomadaire de la qualité.
**Motif :** deux questions distinctes, deux rythmes distincts. La qualité ne bouge qu'au rythme des publications de comptes ; la recalculer chaque semaine fabriquerait du mouvement là où il n'y en a pas. Les deux ne se croisent qu'au screener, dans la matrice qualité × prix.
**Réversibilité :** totale.

### D13 - Un titre non évalué en qualité n'est jamais une opportunité
**Écarté :** afficher les signaux de prix seuls comme des opportunités.
**Motif :** c'est exactement la définition du value trap. Un signal de prix non qualifié s'affiche comme tel - quadrant `unqualified`.
**Réversibilité :** totale, mais ce serait revenir à un demi-système.

### D14 - Tout groupe de pairs qualifié contient un concurrent hors Europe
**Écarté :** groupes de pairs strictement sectoriels et automatiques.
**Motif :** les menaces réelles viennent presque toujours de l'extérieur de l'univers - Shark Ninja contre Seb, BYD contre BMW, Revolut contre les bancaires. Un groupe purement européen est structurellement aveugle et d'autant plus rassurant.
**Réversibilité :** totale, mais c'est le seul remède à la limite la plus dangereuse du doc 08.

### D15 - Les évaluations qualitatives périment au bout de 18 mois
**Écarté :** évaluation permanente jusqu'à révision manuelle.
**Motif :** une évaluation de 2026 inspire la même confiance qu'une de 2029 - c'est le problème. La péremption force la revue.
**Réversibilité :** totale.

### D16 - Aucun agent LLM en v1, sauf extraction PDF en L9
**Écarté :** le design multi-pools d'origine.
**Motif :** l'explication a posteriori des mouvements produit du bruit crédible ; l'extraction de PDF produit de la donnée vérifiable.
**Réversibilité :** totale, c'est une phase 2.

---

### D17 à D25 - décisions prises pendant l'implémentation

*Détail et motifs : doc 09 §3, qui numérote les mêmes décisions de D-A à D-I. La colonne « réf. 09 » donne la correspondance - D-A y couvre D17 et D18, D-D couvre D21 et D22.*

| # | réf. 09 | Décision | Motif en une ligne |
|---|---|---|---|
| **D17** | D-A | P4 amendé : on stocke `Close` (rétro-ajusté des splits), pas le cours nominal | Le nominal n'existe chez aucune source gratuite. Ce que P4 protège est la reproductibilité, et `Close` est réécrit 2 fois en 12 ans contre plusieurs fois par an pour `Adj Close` |
| **D18** | D-A | `factor_price = 1.0` | Réappliquer les ratios diviserait la série une seconde fois. **Erreur invisible : la courbe reste lisse, seule la pente est fausse** |
| **D19** | D-B | yfinance source primaire et unique | Stooq renvoie une preuve de travail JavaScript. Contredit « aucun point de défaillance unique » - **reste à arbitrer** |
| **D20** | D-C | `published_at` estimé à `period_end + 122 j`, avec drapeau | yfinance ne sert aucune date de publication. Asymétrie : errer tard coûte de la prudence, errer tôt fabrique du look-ahead |
| **D21** | D-D | Régime cyclique déclaré à la main, la déclaration prime sur la détection | Sur 4 exercices, une descente de cycle est **statistiquement indiscernable d'une érosion**. Aucun code ne lève cette limite |
| **D22** | D-D | `R2_TENDANCE_MONOTONE = 0.70` ajouté | Un cycle redescend **et** remonte, un effondrement est monotone. Sans lui, Atos était classé cyclique donc protégé du verdict d'érosion |
| **D23** | D-E | Troisième verdict `indéterminable` en cohérence prix/fondamentaux | Traiter un critère non évaluable comme réussi fabrique de faux signaux |
| **D24** | D-F | Ratios neutralisés pour le secteur financier (ICB 30) | Une banque a un levier structurel de 15 à 20 : elle sortirait `suspect` à chaque passage pour une raison qui n'en est pas une |
| **D25** | D-G | Le DF-GLS arbitre seul la stationnarité | L'intervalle bootstrap est anti-conservateur près de la racine unitaire. Sur Seb il exclut 1 quand le DF-GLS ne rejette pas - **c'est le test qui a raison** |
| **D26** | D-H | Cycle de vie complet des anomalies : empreinte stable, `run_count`, distinction auto/manuel | Une anomalie perdait sa date de première détection à chaque recalcul, et une anomalie acquittée réapparaissait - la revue manuelle ne servait à rien |
| **D27** | D-I | Filtre de dilution renforcé : minimum glissant 365 j, actions neutralisées des splits | Sans neutralisation, quatre faux positifs - Dassault ×5.09, Michelin ×4.0, Aena ×10.7, Prosus ×2.43 |

---

## 2. Points ouverts - à trancher par toi

### PO0 - **Nouveau, et le plus urgent : quand installe-t-on l'orchestrateur ?**
Le principe D5 - l'historisation - est la décision la plus importante du projet, et il ne produit sa valeur que par régularité. **Point clos le 2026-08-21** : le cycle d'ingestion et de calcul tourne en cron toutes les 8 heures sur le VPS, et `regression_fits` reçoit une observation par jour. Les semaines antérieures au cron, elles, manquent définitivement - c'est le seul coût du projet qui ne se rattrape jamais.
*Mon avis : deux jours de travail avant toute autre chose, y compris avant de corriger les dettes T1, T2, T5 et T6.*

### PO1 - Supabase ou VPS dès le départ ?
Le free tier tient largement pour la v1, avec deux contraintes réelles : pause après 7 jours sans requête, et snapshots sur 7 jours seulement. Le VPS n'a aucune de ces contraintes et coûte zéro de plus, mais demande de l'administration.
*Mon avis : Supabase pour démarrer vite, avec la discipline D1 pour que la bascule reste triviale.*

### PO2 - Régression sur le cours simple ou le rendement total ? *(partiellement tranché par D18)*
Le cours simple - splits seuls - est comparable aux graphes Hiboo. Le rendement total dividendes réinvestis est économiquement plus juste. Sur des valeurs à fort rendement comme les bancaires, l'écart est très significatif sur 20 ans.
*Mon avis : calculer les deux, afficher le cours simple par défaut, garder le total pour la mesure de performance.*

### PO3 - Fenêtre glissante ou expansive ?
Hiboo semble utiliser tout l'historique disponible. La fenêtre glissante s'adapte mieux mais bouge davantage.
*Mon avis : glissante, avec la fenêtre stockée dans `regression_fits` pour pouvoir comparer les deux plus tard.*

### PO4 - Modèle EAV ou table large pour les fondamentaux ?
EAV : souple, absorbe trois sources hétérogènes, requêtes plus lourdes. Table large : simple à requêter, migration à chaque nouveau concept.
*Mon avis : EAV, parce que yfinance, XBRL et extraction LLM n'ont pas le même vocabulaire.*

### PO5 - ~~250 titres d'emblée ou 50 puis élargissement ?~~ **Tranché : 57 titres**
*Mon avis : 50, fermement. Le référentiel est le point d'enlisement le plus probable du projet.*

### PO6 - Le rapport doit-il expliquer les mouvements ?
Tu voudras savoir pourquoi un titre a pris −8%. Ma position est que cette information n'existe pas de façon fiable et que la fabriquer coûte plus qu'elle ne rapporte.
*Compromis possible : une section « faits », strictement factuelle - publication de résultats, annonce réglementaire, changement de dirigeant - sans aucune interprétation causale. C'est vérifiable et ce n'est pas un narratif.*

### PO7 - Quel seuil de dilution ?
+50% sur 12 mois glissants est un point de départ arbitraire. À calibrer sur des cas réels.

### PO8 - Le budget de 4€ pour valider contre Hiboo - **toujours ouvert**
Le test de comparaison de L5 est le meilleur contrôle qualité disponible. Il faut un mois d'abonnement DATA. À confirmer que les droites y sont bien incluses - la page tarifaire ne les mentionne pas, le podcast si.

### PO9 - Seuil de coût du capital : absolu, relatif, ou les deux ?
8% en absolu est transparent mais conventionnel. L'écart à la médiane du groupe de pairs est plus robuste - les biais d'estimation communs au secteur s'annulent - mais dépend entièrement de la qualité du groupe de pairs.
*Mon avis : afficher les deux, trancher sur le relatif quand le groupe de pairs est complet, sur l'absolu sinon.*

### PO10 - ~~Qui décide qu'un titre est cyclique ?~~ **Tranché par D21 / D-D : la déclaration manuelle prime sur la détection**
~~Proposition : volatilité du ROIC au-delà d'un seuil, avec surcharge manuelle possible.~~ **Cette proposition a été essayée et a échoué dans les deux sens** : Arkema classé en value trap, puis Atos protégé du verdict d'érosion parce que son effondrement était volatil. La sortie est la déclaration manuelle en seed. **Ce qui reste ouvert : la déclaration n'est ni datée, ni sourcée, ni périmable**, contrairement à `moat_assessments`.

### PO11 - Où tourne le moteur analytique ?
Supabase free ne donne que 500 Mo de RAM partagée. Le calcul doit tourner ailleurs : VPS en cron, ou machine locale. *Mon avis : VPS, pour que le cycle hebdomadaire soit autonome.*

---

## 3. Risques de conception, au-delà de la technique

### R1 - Le système peut être parfaitement construit et la méthode ne pas fonctionner
La spec ne dit rien de la validité de l'approche par droite de régression. Elle construit l'outil qui permettra de le savoir - par D5, en 12 à 24 mois.
*C'est le risque que tu as accepté en écartant l'étape 0. Il est explicite, pas éliminé.*

### R2 - L'effet de second ordre
Un outil de suivi finement instrumenté augmente la fréquence de consultation, qui dégrade les décisions long terme. D11 le contient par conception, mais rien n'empêche d'ouvrir le dashboard tous les matins.
*Le seul remède est comportemental, pas technique.*

### R3 - Le biais d'autorité de son propre outil
Un chiffre qu'on a calculé soi-même inspire plus confiance qu'un chiffre acheté, indépendamment de sa justesse. C'est un renversement du biais habituel et il est plus insidieux.
*Remède partiel : l'affichage systématique de l'incertitude (I2) et la comparaison régulière à une source externe.*

### R4 - Le résultat empirique est plus dur que prévu, et il faut le regarder en face
Sur 57 titres, **0 `good`** : aucun titre européen de l'univers ne présente de retour à la tendance statistiquement établi sur 20 ans. Quatre rejettent au seuil brut de 5%, ce qui est indiscernable du taux de faux positifs, et BHY n'en laisse passer aucun.
*Ce n'est pas un échec du système - c'est le système qui fait son travail. Mais cela veut dire que la méthode de la droite de régression, telle qu'elle est vendue, ne trouve pas de support statistique sur cet univers. Le screener reste utile comme outil de pricing relatif ; il ne peut pas être présenté comme un signal validé. C'est exactement le genre de verdict que R1 annonçait comme possible.*

### R5 - Le coût de maintenance est sous-estimé
Les scrapers cassent. Une source change de format. Un cron échoue silencieusement. Le coût récurrent est de l'ordre de quelques heures par mois, indéfiniment.
*C'est le vrai prix à comparer aux 48€ par an de l'alternative, davantage que l'effort de construction initial.*

### R6 - La qualité est jugée sur 4 exercices, alors qu'elle porte sur la durabilité
La spec visait 5 ans ; le réel est de **4 exercices**. Contradiction assumée et affichée : `quality_scores.confidence` vaut `low` quand la profondeur disponible est courte. C'est le seul endroit du projet où j'estime qu'une dépense de données serait justifiée - pas pour les cours, gratuits, mais pour 15 à 20 ans de ROIC.

### R7 - Le survivorship bias reste non traité
`index_memberships` existe mais ne sera pas remplie faute de données gratuites. Toute analyse rétrospective sera optimiste - d'une ampleur limitée et de signe incertain, mais réelle.
*D5 y échappe partiellement : les fits historisés en temps réel incluent les titres qui se dégraderont ensuite, à condition de ne jamais les supprimer de la base après radiation.*

**Règle qui en découle, et qui coûte zéro aujourd'hui : ne jamais supprimer un instrument radié. Le passer en `is_active = false` avec sa raison de radiation, et conserver tout son historique.** C'est ce qui rendra, dans trois ans, le jeu de données non biaisé - et personne ne pense à le faire au début.

---

## 4. Ce que je défendrais le plus fermement

Par ordre décroissant.

1. **D5, étendu à `quality_scores`** - l'historisation des deux couches. Impossible à rattraper, presque gratuite, et c'est ce qui transforme un screener en dispositif de validation.
2. **D4** - la bitemporalité. Même argument : quatre octets aujourd'hui, irrattrapable demain.
3. **D3** - le cours brut plutôt que l'ajusté. La reproductibilité en dépend entièrement.
4. **La règle de non-suppression des titres radiés** (R7). Coût nul, valeur croissante avec le temps.
5. **D9** - le filtre de dilution. C'est l'apport qui distingue réellement ce système des screeners existants, et c'est celui qui évite de perdre de l'argent sur un faux signal spectaculaire.
6. **D13** - un signal de prix non qualifié n'est pas une opportunité. C'est ce qui empêche le système de devenir une machine à value traps bien graphée.

Les six tiennent en un principe unique : **l'information sur ce qu'on savait à un instant donné ne se reconstitue jamais.** Tout le reste est réversible.
