# 11 - Portefeuille et paper trading

> **État : spécification, non implémenté.** À situer en L8 de la roadmap
> (doc 05), après L7. Le doc 01 §7 pose déjà la table `positions` ; ce document
> la complète et la reprend.

**Version :** v1, août 2026. **À challenger avant développement.**

---

## 1. Objet, et la raison qui n'est pas évidente

Suivre ses positions dans un fichier ne demande pas un logiciel. Un tableur le
fait, et le fait bien.

**Ce que le tableur ne fait pas, c'est relier une position au signal qui l'a
déclenchée.** Le système sait qu'un titre était à −2,3σ le jour de l'achat, avec
un fit `weak`, une demi-vie de 3,4 ans, une qualité `watch` et 46 semaines
consécutives sous le seuil. Ces cinq chiffres ne se retrouvent pas trois ans plus
tard — `regression_fits` les a figés, mais encore faut-il qu'une position les
pointe.

**C'est la seule raison valable de mettre le portefeuille dans cet outil plutôt
qu'ailleurs.** Si le portefeuille n'enregistrait que quantité, prix et date, il
n'aurait rien à faire ici.

### 1.1 La thèse écrite avant

`positions.thesis` existe déjà au doc 01 §7, et son commentaire dit l'essentiel :

> Écrire la thèse au moment de l'achat et la relire deux ans plus tard est le
> seul antidote fiable au biais rétrospectif — on reconstruit spontanément une
> justification de ce qu'on a fait.

Ce document en fait une **contrainte** et non une bonne pratique : une position
sans thèse ne s'enregistre pas. C'est la seule friction imposée de toute la
fonctionnalité, et elle est délibérée.

## 2. Périmètre

| | v1 | Plus tard |
|---|---|---|
| Positions réelles | oui | |
| Positions fictives (paper trading) | oui | |
| Supports multiples | oui | |
| Passage d'ordre | **jamais** | **jamais** |
| Connexion à un broker | non | à évaluer |
| Import de relevé | non | CSV, oui |
| Fiscalité calculée | non | estimation indicative |
| Devises étrangères | non — univers 100 % EUR | avec `fx_rates` |

**Aucun passage d'ordre, aucune connexion à un broker, jamais.** C'est la ligne
du doc 00 §6 et elle ne bouge pas : *le système propose, tu décides*. Un outil
qui peut exécuter change de nature — il devient un endroit où l'on agit vite,
alors que tout le reste est conçu pour ralentir.

**Aucun conseil.** L'outil enregistre et mesure. Il ne recommande pas d'acheter,
ne dimensionne pas une position, ne calcule pas d'allocation cible.

## 3. Les supports

### 3.1 Pourquoi le support est une entité et pas un champ texte

Trois raisons, dans l'ordre.

**Les règles d'éligibilité diffèrent, et elles sont vérifiables.** Le PEA n'accepte
que des titres de sociétés ayant leur siège dans l'Union européenne ou l'Espace
économique européen. L'univers en compte 57, dont **aucun** n'est suisse ou
britannique — mais le jour où Richemont ou Nestlé entrent dans la base pour
servir de pairs, un achat en PEA doit être refusé. Le système a l'information :
`instruments.country_iso2`.

**Les plafonds de versement sont par support, pas par titre.** Ils ne se
déduisent d'aucune position prise isolément.

**La performance nette n'est comparable qu'à fiscalité identique.** Comparer le
rendement d'une ligne en PEA et d'une ligne en CTO sans le dire produit une
conclusion fausse sur la méthode.

### 3.2 Table `accounts`

```sql
create table accounts (
  id             bigint generated always as identity primary key,
  code           text not null unique,        -- 'PEA_CM', 'CTO_BOURSO', 'PER_LINXEA'
  label          text not null,
  kind           text not null,               -- 'PEA','PEA_PME','PER','CTO','AV','PAPER'
  broker         text,
  currency       char(3) not null default 'EUR' references currencies(code),
  opened_at      date,
  -- Règles d'éligibilité et plafonds, en données et non en dur dans le code.
  eligible_countries text[],                  -- null = aucune restriction
  contribution_cap   numeric(14,2),           -- plafond de versements, null = aucun
  is_paper       boolean not null default false,
  notes          text,
  constraint account_kind_check
    check (kind in ('PEA','PEA_PME','PER','CTO','AV','PAPER'))
);
```

**`eligible_countries` et `contribution_cap` sont des données, pas du code.** Même
principe que `regression_policies` au doc 01 §6.1 : les règles changent, et une
règle en dur dans un `if` se découvre le jour où elle a déjà produit une erreur.

### 3.3 Ce que l'outil vérifie, et ce qu'il ne vérifie pas

**Il vérifie** l'éligibilité géographique et le cumul des versements contre le
plafond déclaré.

**Il ne vérifie pas** la fiscalité, les durées de détention, les conditions de
retrait ou de déblocage. Ces règles évoluent, dépendent de la situation
personnelle, et un outil qui les affirmerait donnerait un conseil qu'il n'est pas
en position de donner.

> **Les paramètres de `accounts` sont saisis par l'utilisateur et à vérifier
> auprès de son établissement ou d'un professionnel.** Le système les traite comme
> une configuration déclarée, jamais comme une vérité fiscale.

## 4. Modèle de données

### 4.1 `positions`, reprise du doc 01 §7

```sql
alter table positions
  add column account_id     bigint references accounts(id),
  add column is_paper       boolean not null default false,
  add column fit_id         bigint references regression_fits(id),
  add column quality_score_id bigint references quality_scores(id),
  add column watchlist_id   bigint references watchlist(id),
  add column fees           double precision default 0,
  add column closed_price   double precision,
  add column close_reason   text,
  add column review_at      date;

alter table positions
  add constraint position_thesis_required check (thesis is not null and length(thesis) >= 30);
```

**`fit_id` et `quality_score_id` sont le cœur de la fonctionnalité.** Ils pointent
la ligne exacte de `regression_fits` et de `quality_scores` en vigueur à l'achat.
Trois ans plus tard, on relit ce que le système affirmait — pas une
reconstitution, la ligne d'origine.

`watchlist_id` relie la position à la période de suivi qui l'a précédée : depuis
combien de temps on regardait ce titre avant d'acheter est une information sur la
discipline, pas sur le titre.

**`review_at` est une date de revue, pas une alerte.** Elle sert au rapport
hebdomadaire à dire « cette thèse a un an, relis-la » — dans le rapport, jamais
en notification.

### 4.2 `transactions`

`positions` décrit une ligne détenue ; `transactions` décrit les mouvements. Les
séparer permet les renforts et les cessions partielles sans réécrire le prix de
revient à la main.

```sql
create table transactions (
  id             bigint generated always as identity primary key,
  position_id    bigint not null references positions(id) on delete cascade,
  kind           text not null,               -- 'buy','sell','dividend','fee','split_adj'
  executed_at    date not null,
  quantity       double precision,
  price          double precision,
  amount         double precision,            -- montant signé, devise du support
  fees           double precision default 0,
  price_source   text not null,               -- 'close','manual','statement'
  note           text,
  created_at     timestamptz not null default now(),
  constraint transaction_kind_check
    check (kind in ('buy','sell','dividend','fee','split_adj'))
);
```

**`price_source` porte la sincérité de la mesure.** Une position exécutée au
cours de clôture et une position dont on a saisi le prix à la main ne se lisent
pas pareil, et l'agrégat doit pouvoir les séparer.

## 5. Paper trading

### 5.1 Ce que c'est, et le piège qu'il faut nommer

Prendre des positions fictives pour éprouver la méthode sans engager d'argent.

**Le piège est connu et il faut le dire avant d'écrire la première ligne de
code :** le paper trading mesure la méthode, pas l'investisseur. Il supprime
exactement ce qui fait échouer les gens — la peur de la perte, la tentation de
vendre au creux, l'attente de dix-huit mois sans rien faire. Un résultat de paper
trading n'est donc **pas** une prédiction de ce qu'on obtiendrait réellement.

C'est malgré tout utile pour une raison précise : il produit des **positions
datées, avec leur `fit_id`**, et c'est ce qui alimentera le principe P5 du côté
décision — dans trois ans, savoir ce qu'ont fait les titres qu'on aurait achetés.

### 5.2 Le prix d'exécution : la dernière clôture connue

**Décision retenue :** une position fictive s'exécute au cours de la dernière
barre hebdomadaire en base, avec `price_source = 'close'`.

Trois raisons.

**Cohérence avec le reste du système.** Toute la chaîne — régression, z-score,
statistiques de régime — travaille sur l'hebdomadaire. Un prix d'exécution
intraday introduirait une précision que rien d'autre ne porte.

**Reproductibilité.** Rejouer un paper trade donne le même résultat. Un prix
saisi à la main ne le garantit pas.

**Le biais rétrospectif, surtout.** Saisir soi-même le prix d'entrée ouvre la
porte au choix d'un bon point d'entrée après coup, et c'est précisément le biais
que tout le projet combat sur le prix. On choisit toujours un meilleur point
d'entrée quand on connaît la suite.

*La saisie manuelle reste possible pour rejouer un achat réel passé, mais la
position porte alors `price_source = 'manual'` et les agrégats de performance la
distinguent.*

### 5.3 Un support dédié, jamais mélangé

Les positions fictives vivent dans un `account` de `kind = 'PAPER'`, jamais dans
un support réel. **Aucun écran n'agrège du réel et du fictif dans le même
chiffre.** Le seul endroit où les deux se croisent est une comparaison
explicitement étiquetée.

## 6. Ce qu'on mesure

### 6.1 Performance

| Mesure | Définition | Pourquoi |
|---|---|---|
| Plus-value latente | `(cours − PRU) × quantité` | l'évidence |
| Rendement total | via `adjustment_factors.factor_total` | dividendes réinvestis, seule mesure économiquement juste |
| Rendement annualisé | sur la durée de détention | comparable entre lignes |
| Écart au marché | contre un indice de référence | une hausse de 12 % dans un marché à +18 % n'est pas une réussite |

Le rendement total s'appuie sur `factor_total`, déjà calculé et **vérifié contre
l'`Adj Close` de Yahoo** (README, lot L3) : écart médian 0,036 %.

### 6.2 Ce qu'on mesure sur la méthode, et la réserve qui va avec

Pour chaque position fermée : le z-score à l'entrée, le z-score à la sortie, la
durée de détention, le rendement obtenu, et le rendement qu'aurait donné le même
capital sur l'indice.

**La réserve est de taille et doit s'afficher en tête d'écran.** Dix positions ne
mesurent pas une méthode. La dispersion des rendements individuels est telle que
la moyenne d'un petit nombre de lignes est dominée par le hasard — c'est le même
argument que celui qui interdit de lire « −2σ donc 95 % de chances de remonter »
au doc 03 §4.

**Le vrai jeu de validation n'est pas le portefeuille, c'est `regression_fits`.**
Le doc 05 le dit en phase 4 : au bout de 12 à 24 mois d'historisation, on dispose
du comportement effectif de **tous** les titres après signal, et pas seulement des
dix qu'on a achetés. Le portefeuille mesure les décisions ; `regression_fits`
mesure la méthode.

## 7. Les écrans

### Écran 8 - Portefeuille

Une ligne par position ouverte : titre, support, quantité, PRU, cours, plus-value
latente, rendement total, z à l'entrée, z actuel, durée de détention, âge de la
thèse.

**Le support est une colonne, jamais un onglet.** Voir en un coup d'œil qu'une
concentration est sur un seul support est utile ; le découper en onglets la
masque.

Les positions fictives apparaissent **grisées et étiquetées**, et n'entrent dans
aucun total.

### Écran 9 - Prendre une position

Trois étapes, dans cet ordre, et l'ordre compte.

1. **Le titre et le support.** L'éligibilité est vérifiée ici ; un titre non
   éligible au support choisi est refusé avec le motif.
2. **La thèse.** Champ obligatoire, minimum 30 caractères. L'écran affiche à
   côté ce que le système affirme aujourd'hui — z-score, fit, qualité, régime,
   statistiques de régime — pour que la thèse s'écrive **en regard** de ces
   chiffres, et non à leur place.
3. **La quantité et le prix.** Clôture par défaut, saisie possible avec marquage.

**La thèse avant le montant, délibérément.** Décider combien avant de dire
pourquoi inverse le raisonnement.

### Écran 10 - Position fermée, revue

À la clôture d'une ligne : la thèse d'origine, la raison de sortie, le rendement
obtenu, et une question — *la thèse s'est-elle vérifiée ?* Trois réponses
possibles : oui, non, on ne peut pas savoir.

**La troisième réponse est la plus importante et doit être proposée en premier.**
Une thèse peut être juste et la position perdante, ou fausse et la position
gagnante. Forcer un verdict binaire fabrique de l'apprentissage sur du bruit.

## 8. Ce que ce document ne tranche pas

1. **L'indice de référence.** CAC 40, Stoxx 600, MSCI Europe ? Le choix change
   l'écart mesuré, et aucun n'est neutre. À trancher avant L8.
2. **Le traitement des versements.** Le plafond PEA porte sur les versements, pas
   sur la valorisation. Le suivre exige de saisir les mouvements d'espèces, ce qui
   double la saisie. Alternative : ne suivre que l'indicatif, et l'afficher comme
   tel.
3. **Les frais.** Les inclure au PRU ou les porter à part ? À part est plus
   lisible et rend leur poids visible, ce qui est en soi une information.
4. **Le paper trading a-t-il sa place en v1 ?** L'argument contre : il rassure
   sans engager, et le temps qu'on y passe ne produit pas de décision.
   L'argument pour, plus fort : il produit des positions datées avec leur
   `fit_id`, et c'est ce qui alimente la mesure à trois ans.

---

## À challenger en priorité

1. **La thèse obligatoire à 30 caractères minimum.** C'est une contrainte
   arbitraire et elle irritera. Je la maintiendrais quand même : une thèse vide
   ou en trois mots ne remplit pas sa fonction, et l'irritation est le prix de la
   discipline.
2. **Le prix de clôture par défaut plutôt que la saisie.** Défendable dans les
   deux sens. Ce qui n'est pas négociable, c'est le marquage : une position au
   prix saisi doit se distinguer dans les agrégats.
3. **`fit_id` sur la position.** C'est la seule chose qui justifie que ce
   portefeuille vive ici plutôt que dans un tableur. Si on devait ne garder
   qu'une ligne de cette spécification, ce serait celle-là.
4. **Ne pas calculer la fiscalité.** Tentant, et ce serait une erreur : les règles
   changent, dépendent de la situation personnelle, et un chiffre affiché est lu
   comme une vérité.
