# 10 - Watchlist

> **État : implémenté.** Migration 013, module `watchlist.py`, écran dédié, étoile
> et filtre dans le screener, bouton de suivi sur la fiche instrument.

**Version :** v1, août 2026.

---

## 1. Pourquoi cette fonctionnalité existe

Le screener rend 57 lignes. La watchlist dit lesquelles on suit.

La différence n'est pas cosmétique, et elle porte toute la fonctionnalité :
**le screener est une requête, la watchlist est une décision.** Une requête se
rejoue et change de résultat ; une décision reste. Un titre qu'on suit depuis huit
mois et qui repasse sous −2σ ne se *découvre* pas, il se *retrouve* — et ces deux
situations n'appellent pas la même conduite.

Concrètement, elle répond à trois questions que le screener seul ne sait pas
traiter :

| Question | Ce que le screener en dit | Ce que la watchlist en dit |
|---|---|---|
| Quels titres est-ce que je suis vraiment ? | rien — il rend ce qui passe les filtres du jour | la liste, explicitement |
| Ce titre a-t-il baissé depuis que je le regarde ? | rien — il ne connaît que l'instant | la dérive du z-score |
| Pourquoi je le regardais, déjà ? | rien | la note écrite à l'ajout |

## 2. Ce qu'elle n'est pas

**Ce n'est pas un portefeuille.** Suivre n'est pas détenir. La confusion serait
coûteuse : un titre suivi et un titre détenu n'appellent pas la même attention, et
mélanger les deux fabrique un portefeuille fantôme dont on mesure la performance
sans y avoir engagé d'argent. Le portefeuille fait l'objet du doc 11.

**Ce n'est pas une alerte.** Aucune notification, conformément au principe I1 du
doc 04 : *le silence est une fonctionnalité*. La watchlist se consulte, elle ne
sonne pas.

**Ce n'est pas un filtre calculé.** Rien ne l'alimente automatiquement. Un titre
n'y entre que par un geste, et c'est ce geste qui lui donne sa valeur.

## 3. Modèle de données

```sql
create table watchlist (
  id             bigint generated always as identity primary key,
  instrument_id  bigint not null references instruments(id) on delete cascade,
  added_at       timestamptz not null default now(),
  note           text,
  z_at_add       double precision,
  fit_at_add     text,
  quality_at_add text,
  removed_at     timestamptz,
  removal_reason text
);

create unique index watchlist_active_unique
  on watchlist (instrument_id) where removed_at is null;
```

### 3.1 Trois choix de conception

**Le retrait est un horodatage, pas une suppression.** Savoir qu'on a suivi
Kering pendant huit mois puis qu'on l'a retiré est une information ; l'effacer
laisse croire qu'on ne l'a jamais regardé. C'est le même raisonnement que pour le
journal d'anomalies et pour `regression_fits` — et il produit, gratuitement, un
historique de ce à quoi on s'est intéressé.

L'index unique porte sur `removed_at is null` : un titre n'est suivi qu'une fois
à la fois, mais rien n'empêche de le reprendre après retrait. **C'est une
reprise, et elle doit se voir.**

**L'état du titre est figé à l'ajout.** `z_at_add`, `fit_at_add`,
`quality_at_add` enregistrent ce que le système affirmait ce jour-là. Sans eux,
on ne peut plus dire trois mois plus tard si le titre a baissé depuis qu'on le
suit ou s'il était déjà bas — et c'est exactement la question qu'on se pose en
rouvrant sa liste.

C'est le même principe que `positions.z_at_entry` et que le `as_of_date` de
`regression_fits` : quelques octets aujourd'hui, une information non
reconstituable plus tard.

**La note s'écrit en ajoutant, jamais après.** Même rôle que `positions.thesis` :
relire dans un an pourquoi on avait mis un titre sous surveillance est le seul
antidote fiable au biais rétrospectif — on reconstruit spontanément une
justification de ce qu'on a fait. L'interface la demande au moment de l'ajout et
n'offre pas de la remplir plus tard.

## 4. Les écrans

### 4.1 Screener — étoile et filtre

Une colonne `★` en tête de tableau, et une case **Watchlist seulement** dans la
rangée de filtres. Le filtre est délibérément **hors du seuil de z-score** : on
veut voir un titre suivi même s'il est repassé au-dessus du seuil, sinon on perd
de vue exactement les titres dont on attend le retour.

### 4.2 Fiche instrument — le bouton et la note

Un bouton **★ Suivre ce titre** dans l'en-tête. Le clic ouvre un formulaire qui
demande la note avant de valider — c'est une friction assumée, et c'est la seule
de tout l'écran.

Une fois suivi, l'en-tête affiche la date d'ajout et la dérive :
`z à l'ajout −2,16 → −2,41 (−0,25)`.

### 4.3 Écran Watchlist

Quatre chiffres en tête : titres suivis, combien sous −1,5σ, combien en baisse
depuis l'ajout, durée médiane de suivi.

Puis le tableau, trié par z-score croissant. **La colonne qu'on vient regarder
est `Dérive`.** Une dérive négative ne dit pas qu'il faut acheter : elle dit que
le régime de décote se prolonge, ce qui est une information différente — et les
statistiques de régime de la fiche disent combien de temps ces épisodes durent
habituellement sur ce titre.

Deux dépliables : les **notes de suivi**, et les **titres retirés** avec leur
raison et leur durée de suivi.

## 5. Critères d'acceptation

- un titre ajouté deux fois ne crée pas de doublon ;
- un titre retiré puis repris crée une seconde ligne, et l'historique montre les
  deux périodes ;
- `z_at_add` reflète le z-score du dernier calcul disponible à l'ajout, et ne
  bouge plus ;
- le retrait n'efface aucune ligne ;
- l'étoile du screener et l'état du bouton de la fiche sont cohérents dans la
  même seconde — pas de cache sur la lecture de l'appartenance.

## 6. Ce qui viendra ensuite

**Le rapport hebdomadaire (L7)** ouvrira sur la watchlist plutôt que sur le
screener complet : c'est la liste qu'on relit, pas celle qu'on découvre.

**Le portefeuille (doc 11)** s'y adosse. Le flux naturel est
`watchlist → position` : on suit, puis on achète. Le passage de l'un à l'autre
doit reprendre la note de suivi comme point de départ de la thèse — sans la
recopier automatiquement, parce qu'une thèse d'achat n'est pas une note de
surveillance.

---

## À challenger

1. **Une seule liste, sans catégories ni étiquettes.** C'est délibéré : deux
   listes deviennent trois, et le classement remplace la décision. Si le besoin
   apparaît, une étiquette libre coûte une colonne.
2. **Pas de limite de taille.** Une watchlist de 40 titres sur 57 ne veut plus
   rien dire, mais la contrainte doit venir de la discipline, pas du logiciel.
3. **La note n'est pas modifiable.** Assumé : une note qu'on peut réécrire perd
   sa fonction d'antidote au biais rétrospectif. Le retrait puis la reprise
   permettent d'en écrire une nouvelle, en conservant l'ancienne.
