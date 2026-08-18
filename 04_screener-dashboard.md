# 04 - Screener, dashboard et rapport hebdomadaire

**Techno :** Streamlit + Altair. **Déploiement :** VPS, derrière authentification basique.

---

## 1. Trois principes d'interface, avant les écrans

### I1 - Le silence est une fonctionnalité

Aucune notification, aucun rafraîchissement temps réel, aucun ticker clignotant. Le dashboard se consulte, il n'alerte pas.

*Justification, développée dans l'avis critique : Thaler, Tversky, Kahneman & Schwartz (1997) ont montré expérimentalement que plus le feedback est fréquent, plus la prise de risque diminue et plus le rendement accumulé baisse. Un outil qui augmente la fréquence de consultation détruit ce qu'il prétend améliorer.*

Conséquence concrète : le rapport hebdomadaire est le canal principal. Le dashboard sert à creuser un titre, pas à surveiller.

### I2 - L'incertitude est affichée, pas masquée

Un fit `weak` s'affiche comme `weak`, avec la raison. Un intervalle de confiance large s'affiche large. Aucun arrondi rassurant.

*Le cas majoritaire sera « on ne sait pas trancher », et l'interface doit rendre ça normal plutôt que honteux.*

### I3 - Toute visualisation a un jumeau tabulaire

Chaque graphe est doublé d'un tableau consultable, avec les valeurs exactes. C'est une exigence d'accessibilité, et c'est aussi la seule façon de vérifier qu'un graphe ne ment pas.

---

## 2. Système visuel

Palette validée par le validateur du référentiel dataviz, en clair **et** en sombre. Le mode sombre est un jeu de valeurs choisi pour la surface sombre, pas une inversion automatique.

### Rôles de couleur

| Rôle | Clair | Sombre | Usage |
|---|---|---|---|
| Surface graphe | `#fcfcfb` | `#1a1a19` | Fond |
| Encre primaire | `#0b0b0b` | `#ffffff` | Titres, valeurs |
| Encre secondaire | `#52514e` | `#c3c2b7` | Légendes |
| Encre atténuée | `#898781` | `#898781` | Axes, graduations |
| Grille | `#e1e0d9` | `#2c2c2a` | Filets pleins, jamais pointillés |
| **Série 1 - cours** | `#2a78d6` | `#3987e5` | La courbe de prix |
| **Série 2 - pair/comparaison** | `#eb6834` | `#d95926` | Un titre comparé, un indice |
| **Série 3 - médiane secteur** | `#1baf7a` | `#199e70` | Référence sectorielle |

**Trois séries au maximum sur les nuages de points.** Le référentiel plafonne les formes « toutes paires » (scatter, small multiples) à trois slots : au-delà, les paires jaune/orange échouent aux seuils de discernabilité. Au-delà de trois, on facette en petits multiples.

*Validation exécutée : toutes vérifications au vert en clair et en sombre, pire paire CVD ΔE 9.2 / 9.4, pire paire vision normale 24.0 / 20.9. Un avertissement de contraste sur l'aqua en mode clair (2.74:1) impose la règle de relief - labels directs visibles ou vue tabulaire, ce que le principe I3 garantit déjà.*

### Échelle divergente pour le z-score

Le z-score porte une **polarité** - décoté d'un côté, surcoté de l'autre, neutre au milieu. C'est le cas d'usage exact d'une échelle divergente.

| Pôle | Clair | Sombre |
|---|---|---|
| Décoté (z ≤ 0) | bleu `#2a78d6` | `#3987e5` |
| Point neutre (z = 0) | gris `#f0efec` | `#383835` |
| Surcoté (z ≥ 0) | rouge `#e34948` | `#e66767` |

*Le point neutre est gris, jamais une teinte : il doit se lire comme « rien ». Et les deux pôles sont chaud/froid, pour se lire comme opposés.*

### Statuts de qualité - palette réservée, jamais réutilisée

| Statut | Couleur | Icône | Libellé obligatoire |
|---|---|---|---|
| `good` | `#0ca30c` | ● | « Retour à la tendance soutenu par les données » |
| `weak` | `#fab219` | ▲ | « Test non concluant » |
| `rejected` | `#d03b3b` | ■ | « Régression invalide » + raison |

**Icône et libellé systématiques.** La couleur ne porte jamais seule l'information - deux des statuts passent sous 3:1 sur surface claire, et surtout un daltonien doit pouvoir lire le tableau.

---

## 3. Les écrans

### Écran 1 - Screener

**Une seule rangée de filtres, au-dessus de tout ce qu'ils cadrent.** Jamais de filtre à l'intérieur d'une carte de graphe.

| Filtre | Valeurs | Défaut |
|---|---|---|
| Classe d'actif | actions / ETF / indices / … | actions |
| Seuil de z-score | curseur −4 à +4 | ≤ −1.5 |
| Qualité du fit | good / weak / rejected | good + weak |
| Secteur | multi-sélection | tous |
| Pays | multi-sélection | tous |
| Capitalisation | curseur | tous |
| Cohérence fondamentale | confirmé / suspect / tous | tous |
| Persistance | ≥ N semaines sous le seuil | ≥ 1 |
| **Quadrant** | cible / watchlist / value trap / à éviter / non qualifié | cible + watchlist |
| **Niveau de qualité** | solide / à surveiller / en érosion / non qualifié | solide + à surveiller |
| **Régime** | rente / cyclique / érosion / sans barrière | tous |

**Tableau de résultats, colonnes :**

```
Nom │ Quadrant │ z │ Fit │ Qualité │ Régime │ Érosion │ ROIC−seuil │ Demi-vie │ Sem. sous seuil │ z rel. pairs
```

Quatre choix de conception à noter.

**Le tri par défaut n'est ni le z-score seul, ni la qualité seule.** Trier par décote met en tête les pièges ; trier par qualité met en tête les titres chers. Tri par défaut : quadrant (cible d'abord), puis z croissant à l'intérieur du quadrant.

**La colonne `Érosion` affiche le décompte 0 à 3, pas un verdict.** Trois pentes négatives significatives se lisent `3/3`. C'est plus honnête qu'un feu tricolore et ça se relit d'une semaine sur l'autre.

**`z rel. pairs` est aussi visible que `z`.** Un titre à −2σ dans un groupe entier à −2σ est un pari sectoriel ; isolé parmi des pairs à leur moyenne, c'est un pari spécifique. Ce sont deux décisions différentes et l'écran doit les distinguer d'emblée.

**Le nombre d'épisodes historiques est en infobulle sur la colonne `z`.** Un titre qui passe sous −2σ tous les trois ans n'envoie pas le même signal qu'un titre qui le fait pour la deuxième fois en trente ans.

**Aucune colonne de score composite sur 100.** Voir doc 03 §8.

### Écran 2 - Fiche instrument

C'est l'écran central. Cinq blocs, dans cet ordre : le prix d'abord parce que c'est ce qui déclenche l'attention, la qualité ensuite parce que c'est ce qui décide.

#### Bloc A - Le graphe de régression

La visualisation principale du produit.

| Élément | Spécification |
|---|---|
| Cours | Ligne 2px, série 1 bleu, échelle **logarithmique** en y |
| Droite de tendance | Ligne 2px, encre secondaire, pleine |
| Bandes ±1σ | Aplat gris à 8% d'opacité |
| Bandes ±2σ | Aplat gris à 4% d'opacité |
| Bornes de bandes | Filets 1px, encre atténuée, **pleins** |
| Point courant | Marqueur 8px minimum, anneau 2px de la couleur de surface |
| Grille | Filets pleins, une nuance au-dessus de la surface |
| Survol | Réticule + infobulle : date, cours, valeur ajustée, z |

**Points de spécification qui comptent :**

- **Axe y logarithmique obligatoire.** Le modèle est linéaire en log ; un axe linéaire courberait la droite et rendrait le graphe faux à l'œil.
- **Un seul axe y.** Jamais de second axe pour le volume ou un autre indicateur - c'est l'erreur de graphique la plus fréquente et elle invente des corrélations.
- **Les bandes ne sont pas des séries catégorielles.** Ce sont des zones de référence : gris neutres, jamais une teinte de la palette de séries.
- **Aucune valeur écrite sur chaque point.** Étiquetage direct sélectif - le point courant, les extrêmes - et l'infobulle porte le reste.
- **Zones d'épisodes historiques sous seuil** surlignées en fond très léger, pour rendre visible que la décote est un régime et non un instant.

#### Bloc B - Bandeau de diagnostics

Vignettes de statistiques, chiffres en graisse normale, chiffres proportionnels et non tabulaires.

```
   z actuel        Demi-vie      Sous seuil depuis    Pente annuelle    Qualité
    −2.34           14 mois          9 semaines            +6.2%      ▲ Non concluant
```

Sous le bandeau, en dépliable, le détail technique : ADF, DF-GLS, KPSS, Durbin-Watson, intervalle de confiance sur la racine autorégressive, nombre d'observations, fenêtre effective.

*L'intervalle de confiance sur la racine AR s'affiche en clair, par exemple `[0.94 ; 1.02]`, avec la mention « intervalle incluant 1 : le retour à la tendance n'est pas établi ». C'est le principe I2.*

#### Bloc C - Statistiques de régime

Le bloc qui remplace le raisonnement erroné en probabilités.

| Métrique | Exemple |
|---|---|
| Épisodes sous −2σ sur l'historique | 3 |
| Durée médiane d'un épisode | 11 mois |
| Durée maximale observée | 26 mois |
| Baisse supplémentaire médiane après franchissement | −18% |
| Rendement médian à 5 ans après franchissement | +64% |
| Étendue observée à 5 ans | −12% à +180% |

**Bandeau d'avertissement permanent en tête du bloc :** *ces statistiques sont calculées sur l'historique complet, donc in-sample. Elles décrivent le passé du titre, elles ne sont pas une probabilité.*

#### Bloc D - Position concurrentielle

Le pendant qualité du bloc A. Spécification au doc 08.

- **Verdict et quadrant**, avec le motif de classement
- **Les trois questions**, chacune avec sa mesure : leadership (part relative, rang, stabilité), rente (ROIC contre seuil et contre pairs, persistance, pricing power), érosion (les trois pentes, chacune affichée séparément)
- **Petits multiples de tendance** sur 5 ans : ROIC, marge brute, part relative - trois graphes côte à côte, même échelle temporelle, une série chacun. *C'est la lecture d'érosion la plus directe possible : trois courbes qui descendent ensemble n'ont pas besoin de commentaire.*
- **Groupe de pairs** utilisé, avec mention explicite s'il est incomplet - c'est-à-dire sans concurrent hors Europe
- **Évaluation qualitative** : sources du moat, menaces identifiées avec leur horizon, date de la dernière revue et **date de péremption**
- **Bandeau si l'évaluation est périmée** : le titre est traité comme non qualifié tant qu'elle n'est pas revue

#### Bloc E - Fondamentaux

Tableau des ratios sur 5 ans, avec la source et la date de publication de chaque valeur. Verdict de cohérence prix / fondamentaux, avec le détail du critère en échec le cas échéant.

Les valeurs issues d'une extraction LLM sont **marquées visuellement** et affichent leur score de confiance, avec un lien vers la page du PDF d'origine. Une valeur extraite d'un PDF n'a pas le statut d'une valeur XBRL, et ça doit rester lisible jusque dans l'écran final.

### Écran 3 - Matrice qualité × prix

**L'écran de synthèse du système, et l'écran d'accueil par défaut.** Spécification fonctionnelle au doc 08 §6.

**Forme : nuage de points, un point par titre.**

| Canal | Encodage |
|---|---|
| Abscisse | z-score, de −4 à +4, axe inversé pour que « décoté » soit à gauche |
| Ordonnée | Écart de rente (ROIC − seuil), en points |
| Quadrants | Quatre zones délimitées par des filets pleins, encre atténuée |
| Couleur du point | Palette divergente sur le z-score - jamais sur le quadrant |
| Forme du marqueur | Rond = rente · Losange = cyclique · Triangle = érosion |
| Taille | Constante. **Pas d'encodage de la capitalisation** |
| Point atténué | Qualité non évaluée ou périmée |

**Quatre décisions d'encodage à noter.**

**La forme du marqueur porte le régime, pas la couleur.** La couleur est déjà prise par le z-score, et surtout un daltonien doit pouvoir distinguer un cyclique d'un titre en érosion. Le canal de forme est libre, on l'utilise.

**Taille constante, pas de bulle par capitalisation.** Un nuage de bulles encode mal les magnitudes - l'œil compare des surfaces - et la capitalisation n'entre pas dans la décision ici. La colonne existe dans le tableau.

**Les libellés de quadrant sont écrits en toutes lettres dans les coins** : `CIBLE`, `WATCHLIST`, `VALUE TRAP`, `À ÉVITER`. Un quadrant qui ne se comprend qu'en croisant deux axes mentalement ne se comprend pas.

**Le quadrant value trap est affiché, pas masqué.** C'est la liste des titres qui ont l'air d'opportunités et n'en sont pas. La voir chaque semaine vaut mieux que ne pas la voir - c'est là qu'on perd de l'argent, pas dans le quadrant « à éviter » qu'on n'achète jamais.

**Sous le nuage, quatre listes**, une par quadrant, avec le motif de classement pour chaque titre. Jumeau tabulaire complet, conformément au principe I3.

**Filtre supplémentaire dans la rangée du haut :** `quadrant`, multi-sélection, avec `unqualified` décoché par défaut.

### Écran 4 - Vue sectorielle

Répond à « le secteur entier est-il décoté, ou seulement ce titre ».

- **Nuage de points** z-score en abscisse, marge opérationnelle en ordonnée, un point par titre du secteur, titre courant mis en relief et les autres en gris. *Un point mis en avant, le reste atténué - pas huit teintes quand l'histoire porte sur un seul titre.*
- **Distribution des z-scores du secteur** en histogramme, coloré selon l'échelle divergente - bleu à gauche, gris au centre, rouge à droite. Marqueur de la position du titre.
- **Tableau des pairs**, avec rang de marge, rang de croissance, z-score, capitalisation.

### Écran 5 - Portefeuille

- Positions, z à l'entrée contre z actuel, performance
- **La thèse écrite à l'achat, affichée en regard.** C'est le seul antidote fiable au biais rétrospectif : on reconstruit spontanément une justification de ce qu'on a fait.
- Concentration par secteur, par pays, par devise
- **Alerte de corrélation** : ton patrimoine et tes revenus dépendent-ils du même facteur ? *C'est la question que le prompt de Dothée pose, et elle mérite une réponse calculée plutôt qu'une intuition.*

### Écran 6 - Qualité des données

Écran d'administration, mais à consulter avant toute décision.

- Anomalies ouvertes par sévérité
- Titres exclus du screener et pourquoi
- Divergences entre sources
- Dernières exécutions d'ingestion, fraîcheur des données par source
- Couverture des fondamentaux

*Un dashboard qui ne montre pas l'état de ses données invite à faire confiance à des chiffres invérifiables.*

---

## 4. Le rapport hebdomadaire

Le livrable principal. HTML autonome, envoyé le dimanche, archivé.

### Structure

1. **En-tête** - date, nombre de titres analysés, nombre exclus et pourquoi
2. **Mouvements de la semaine** - entrées et sorties du seuil, avec le nombre de semaines de persistance
3. **Trois à cinq dossiers mis en avant** - uniquement du quadrant cible : z-score, qualité du fit, demi-vie, verdict de position concurrentielle, érosion, position sectorielle
4. **Les value traps de la semaine** - titres décotés dont la position s'érode ou dont les fondamentaux sont en échec, avec le motif. *Cette section est aussi utile que la précédente, et c'est celle qu'on est tenté de couper.*
5. **Changements de quadrant** - titres ayant basculé depuis la semaine dernière, dans un sens ou dans l'autre. *Un passage de cible à value trap est l'information la plus importante que le rapport puisse contenir.*
6. **Vue macro** - où en sont les grands indices et ETF sur leur propre droite. La réponse chiffrée à « l'ETF est-il cher en ce moment »
7. **Portefeuille** - z actuel des positions et évolution de leur quadrant, aucune recommandation
8. **Santé du système** - anomalies, couverture, fraîcheur, évaluations de qualité arrivant à péremption

### Ce que le rapport ne contient pas

- Aucune recommandation d'achat ou de vente
- Aucun objectif de cours
- Aucune explication narrative des mouvements de la semaine

*Ce dernier point est délibéré et c'est le plus tentant à transgresser. Marie le dit elle-même : « on explique a posteriori mais ce n'est pas ça la vraie cause ». Un rapport qui explique produit de la confiance sans produire d'information.*

---

## 5. Contraintes techniques Streamlit

| Sujet | Décision |
|---|---|
| Bibliothèque de graphes | Altair, pour le contrôle fin des marques et l'axe log |
| Cache | `st.cache_data` sur les requêtes, TTL 1 h |
| Calcul | Aucun calcul lourd dans l'interface - lecture seule sur `regression_fits` |
| Thème | `.streamlit/config.toml`, deux jeux de valeurs, sombre sélectionné et non inversé |
| Auth | Basique en v1, suffisante pour un usage personnel |
| Rafraîchissement | Au chargement, jamais automatique - cf. principe I1 |
| État de chargement | Maintenir le rendu précédent en opacité réduite, pas de squelette clignotant |

---

## À challenger en priorité

1. **Le tri par quadrant avant le z-score.** Ça masque en première page les titres les plus décotés, qui sont ceux qu'on a envie de voir. C'est volontaire - ce sont aussi les plus dangereux - mais ça se discute.
2. **Le bloc « statistiques de régime » à la place d'un chiffre de probabilité.** C'est plus honnête et nettement moins immédiat à lire. Un utilisateur qui veut « 95% de chances » sera déçu, et c'est le but.
3. **L'absence totale de narratif dans le rapport.** Tu vas vouloir savoir pourquoi Seb a pris −8% cette semaine. Ma position : cette information n'existe pas de façon fiable, et la fabriquer coûte plus qu'elle ne rapporte. À trancher.
4. **Streamlit plutôt qu'une vraie application.** L'itération est rapide, l'esthétique est plafonnée. Si le dashboard doit un jour être montré à des tiers, il faudra reconstruire - et il faudra alors relire le doc sur le régime réglementaire.
5. **Le plafond de trois séries sur les nuages de points** est une contrainte de discernabilité, pas un choix esthétique. Au-delà, on facette.
6. **La matrice qualité × prix en écran d'accueil, plutôt que le screener.** Elle impose de regarder la qualité avant la décote. Si tu préfères ouvrir sur la liste des titres les plus bas, c'est un choix légitime - mais c'est celui qui mène au quadrant value trap.
7. **L'affichage permanent du quadrant value trap.** Il occupe de la place à montrer des titres qu'on n'achètera pas. C'est délibéré : c'est la seule façon de vérifier après coup si le filtre avait raison.
