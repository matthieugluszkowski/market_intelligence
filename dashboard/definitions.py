"""Définitions des indicateurs de la fiche instrument.

Un chiffre sans définition se lit comme une autorité ; avec sa définition, il
redevient un argument qu'on peut contester. Chaque bloc de la fiche a donc son
glossaire, affiché dans un expander **au plus près des chiffres** — pas dans une
page d'aide que personne n'ouvre.

Règle d'écriture : une définition dit ce que l'indicateur mesure, puis comment
le lire — jamais de formule seule, jamais de jargon sans traduction.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

COLONNES = ["Indicateur", "Ce que c'est", "Comment le lire"]

DIAGNOSTICS = [
    ("z actuel",
     "Écart entre le cours du jour et sa tendance de long terme, mesuré en "
     "écarts types (σ) des résidus de la régression.",
     "0 = sur la tendance. Négatif = sous la tendance (décote apparente). "
     "−2 est le seuil d'attention du screener : historiquement rare pour un "
     "titre discipliné."),
    ("Demi-vie",
     "Temps nécessaire pour qu'un écart à la tendance se résorbe de moitié, "
     "estimé sur le comportement passé du titre.",
     "Quelques mois = rappel rapide vers la tendance. « non établie » = le "
     "retour vers la tendance n'est pas démontré statistiquement — le z-score "
     "se lit alors avec prudence."),
    ("Sous −2σ depuis",
     "Nombre de semaines consécutives que le cours vient de passer sous le "
     "seuil de −2σ.",
     "Un épisode long est un régime, pas un accident : la décote peut durer "
     "des mois. La date affichée est le premier franchissement."),
    ("Pente annuelle",
     "Croissance tendancielle du cours, annualisée, estimée par régression "
     "linéaire sur le logarithme du prix.",
     "+8 % = en tendance, le titre progresse de 8 % par an sur la fenêtre "
     "étudiée. C'est la pente de la droite du graphe, pas la performance "
     "récente."),
    ("r²",
     "Part des variations du cours expliquée par la tendance (entre 0 et 1).",
     "Proche de 1 = cours discipliné autour de sa droite ; faible = la "
     "tendance décrit mal ce titre et le z-score perd de son sens."),
    ("Solidité concurrentielle",
     "La conclusion du dossier de position : leader, challenger, suiveur ou "
     "acteur de niche — puis le score sur 100, son ancienneté et sa durabilité.",
     "C'est le constat qui se lit d'abord, le score ensuite : 78/100 ne dit rien "
     "tant qu'on ignore s'il note un leader ou un suiveur. « brouillon » = "
     "dossier non relu, donc rien de projeté et titre non qualifié."),
    ("Qualité du fit",
     "Verdict des tests statistiques (ADF, DF-GLS, KPSS) sur la validité de la "
     "régression : le retour vers la tendance est-il démontré ? Affiché dans "
     "« Detail technique des tests », avec les tests qui le produisent.",
     "« Retour à la tendance soutenu » = les tests confirment. « Test non "
     "concluant » ou « régression invalide » = le z-score ne doit pas fonder "
     "une décision seul. C'est une propriété de la méthode appliquée à ce "
     "titre, pas un jugement sur l'entreprise."),
]

REGIME = [
    ("Épisodes sous −2σ",
     "Nombre de passages historiques du cours sous le seuil de −2σ.",
     "Peu d'épisodes = peu de recul statistique : les chiffres de ce bloc se "
     "lisent comme des ordres de grandeur."),
    ("Part du temps sous le seuil",
     "Fraction de l'historique que le titre a passée sous −2σ.",
     "5 % = le titre est rarement aussi décoté qu'aujourd'hui. C'est une "
     "fréquence passée, pas une probabilité de rebond."),
    ("Durée médiane / maximale",
     "Durée typique et pire durée observée d'un épisode sous −2σ.",
     "Donne l'ordre de grandeur du temps à passer sous le seuil avant un "
     "retour — la patience nécessaire, mesurée sur le passé."),
    ("Baisse supplémentaire (médiane / pire)",
     "Ce que le titre a encore perdu APRÈS avoir franchi −2σ, avant de "
     "toucher son point bas.",
     "Franchir le seuil n'est pas le point bas : −10 % médian signifie qu'en "
     "général, il restait 10 % de baisse à encaisser."),
    ("Rendements après franchissement",
     "Performance observée aux horizons donnés (6, 12, 24 mois) après chaque "
     "franchissement passé du seuil.",
     "Une distribution, jamais une promesse : l'étendue min–max informe "
     "davantage que la médiane, surtout sur peu d'épisodes."),
]

QUALITE = [
    ("Niveau (tier)",
     "Synthèse de la position concurrentielle : solid (position établie), "
     "watch (à surveiller), eroding (rente en érosion), unqualified (jamais "
     "évaluée).",
     "Seul un dossier concurrentiel validé par un analyste peut faire passer "
     "un titre en solid. Croisé avec la décote : une décote sur un titre "
     "eroding est un ajustement de prix, pas une opportunité."),
    ("Régime",
     "Nature de la rente économique : rent (rente installée), cyclical "
     "(rentabilité cyclique), eroding (en érosion), no_moat (pas de "
     "barrière), unknown (indéterminé).",
     "Décrit le mécanisme derrière les chiffres du bloc, pas un verdict "
     "d'achat."),
    ("Quadrant",
     "Croisement de la décote (z-score) et de la qualité (tier) : c'est la "
     "grille de lecture du screener.",
     "La cible est « décoté ET solide ». Décoté sans qualité établie = à "
     "instruire, pas à acheter."),
    ("Part relative au plus grand pair (Q1)",
     "Chiffre d'affaires de l'entreprise divisé par celui du plus grand "
     "concurrent de son groupe de pairs.",
     "1,00 = même taille que le leader ; au-dessus de 1, c'est elle le "
     "leader ; 0,50 = moitié de la taille du leader."),
    ("Rang par chiffre d'affaires (Q1)",
     "Position de l'entreprise dans son groupe de pairs, classé par chiffre "
     "d'affaires.",
     "1 = plus gros acteur du groupe. Le rang dépend de la composition du "
     "groupe : un groupe incomplet flatte le rang."),
    ("ROIC moyen (Q2)",
     "Return on Invested Capital : ce que rapporte chaque euro investi dans "
     "l'outil de production, en moyenne sur 5 ans.",
     "Au-dessus de ~8 % (coût moyen du capital), l'entreprise crée de la "
     "valeur ; en dessous, elle en détruit même si elle est bénéficiaire."),
    ("Écart au seuil de 8 % (Q2)",
     "ROIC moyen moins 8 %, le seuil retenu comme coût du capital.",
     "+5 pts = rente confortable ; proche de 0 = rentabilité juste normale ; "
     "négatif = pas de rente."),
    ("Écart à la médiane des pairs (Q2)",
     "ROIC de l'entreprise moins le ROIC médian de son groupe de pairs.",
     "Positif = plus rentable que ses concurrents : c'est la signature d'un "
     "avantage compétitif, quelle qu'en soit la source."),
    ("Persistance (Q2)",
     "Nombre d'exercices, sur ceux disponibles, où le ROIC a dépassé le "
     "seuil de 8 %.",
     "5/5 = rente constante ; 2/5 = rentabilité épisodique. Une rente se "
     "juge à sa constance, pas à sa pointe."),
    ("Marge brute moyenne (Q2)",
     "(Chiffre d'affaires − coût des ventes) / chiffre d'affaires, en "
     "moyenne sur 5 ans.",
     "Une marge brute élevée et stable signale un pouvoir de prix — la "
     "matière première d'une rente."),
    ("Pentes ROIC / marge / part (Q3)",
     "Variation annuelle moyenne, sur 5 ans, du ROIC, de la marge brute et "
     "de la part relative.",
     "Négatif = érosion en cours. C'est la direction qui compte ici, pas le "
     "niveau : une rente élevée qui s'érode vite reste une alerte."),
    ("Drapeaux d'érosion (Q3)",
     "Nombre de pentes (sur 3) significativement négatives.",
     "0/3 = aucune érosion détectée ; 3/3 = érosion sur tous les fronts. Un "
     "décompte, volontairement pas un feu tricolore."),
    ("Position (évaluation qualitative)",
     "Verdict d'un analyste sur la place de l'entreprise : leader, "
     "challenger, follower ou niche.",
     "Posé à l'import du dossier concurrentiel, jamais calculé. leader = "
     "domine son marché ; niche = domine un segment étroit."),
    ("Durabilité (évaluation qualitative)",
     "Verdict sur la résistance de la barrière concurrentielle : solid, "
     "watch, eroding ou none.",
     "C'est la question que les comptes ne peuvent pas trancher : un ROIC "
     "passé élevé ne dit rien d'une rupture à venir."),
]

FONDAMENTAUX = [
    ("PER",
     "Cours divisé par le bénéfice net par action.",
     "« Combien d'années de bénéfice actuel pour payer l'action » : 12x est "
     "modéré, 25x exige une forte croissance pour se justifier. Sans objet "
     "si le bénéfice est négatif."),
    ("EV/EBIT",
     "Valeur d'entreprise (capitalisation + dette nette) divisée par le "
     "résultat opérationnel.",
     "Mesure de cherté indépendante de la structure d'endettement — c'est "
     "elle qui permet de comparer deux entreprises inégalement endettées."),
    ("EV/CA",
     "Valeur d'entreprise divisée par le chiffre d'affaires.",
     "Utile quand le résultat est déprimé ou négatif ; se lit toujours avec "
     "la marge : 2x le CA d'une entreprise à 5 % de marge est cher."),
    ("P/B",
     "Cours divisé par l'actif net comptable par action (Price to Book).",
     "Sous 1 = le marché price l'entreprise sous ses fonds propres — décote "
     "réelle ou actifs surévalués, c'est la question à instruire."),
    ("Rendement du FCF",
     "Trésorerie libre générée sur l'exercice, rapportée à la "
     "capitalisation boursière.",
     "Ce que l'entreprise pourrait rendre à l'actionnaire sans s'endetter : "
     "6 % de FCF yield finance dividende et rachats ; 1 % = valorisation "
     "exigeante."),
    ("Rendement du dividende",
     "Dividende par action divisé par le cours.",
     "À croiser avec le taux de distribution : un rendement élevé financé à "
     "100 % du bénéfice est fragile."),
    ("Marge brute",
     "(Chiffre d'affaires − coût des ventes) / chiffre d'affaires.",
     "Le pouvoir de prix brut, avant frais de structure."),
    ("Marge opérationnelle",
     "Résultat opérationnel (EBIT) / chiffre d'affaires.",
     "Ce qui reste après tous les coûts d'exploitation — la marge qui juge "
     "le modèle économique."),
    ("Marge nette",
     "Résultat net / chiffre d'affaires.",
     "Après intérêts et impôts. Sensible aux éléments exceptionnels : une "
     "marge nette isolée peut mentir, la série ne ment pas."),
    ("ROE",
     "Résultat net / capitaux propres (Return on Equity).",
     "Rentabilité pour l'actionnaire. Gonflable par la dette : un ROE de "
     "20 % avec un gearing de 200 % n'a rien d'un exploit."),
    ("ROCE",
     "Résultat opérationnel / capitaux employés (fonds propres + dette "
     "nette).",
     "Rentabilité de l'ensemble des capitaux mobilisés, insensible au levier "
     "— le juge de paix de l'allocation du capital."),
    ("ROIC",
     "Résultat opérationnel après impôt / capital investi.",
     "La mesure de rente retenue par le bloc D : au-dessus du coût du "
     "capital (~8 %), l'entreprise crée de la valeur."),
    ("Dette nette / EBITDA",
     "Dette financière nette divisée par l'excédent brut d'exploitation.",
     "Années d'EBITDA nécessaires pour rembourser la dette : sous 1x = "
     "bilan solide ; au-delà de ~3x, la dette pilote les décisions."),
    ("Couverture des intérêts",
     "Résultat opérationnel / charge d'intérêts.",
     "Combien de fois le résultat couvre les intérêts : sous 3x, une "
     "récession met le dividende — puis l'entreprise — sous pression."),
    ("Gearing",
     "Dette nette / capitaux propres.",
     "Le levier du bilan : 50 % est courant, 150 % exige des flux très "
     "stables pour rester confortable."),
    ("Croissance CA 3 / 5 ans",
     "Croissance annualisée du chiffre d'affaires sur la période.",
     "La trajectoire d'activité, lissée. À comparer à l'inflation : 2 % par "
     "an en euros courants est une stagnation réelle."),
    ("Croissance RN 3 ans",
     "Croissance annualisée du résultat net sur 3 ans.",
     "Plus volatile que le CA ; un écart durable entre les deux (CA stable, "
     "RN en baisse) signale une pression sur les marges."),
    ("Taux de distribution",
     "Dividende versé / résultat net (payout).",
     "Sous 60 %, le dividende a de la marge ; proche de 100 %, il dépend du "
     "moindre accident de résultat."),
    ("Dilution nette 3 ans",
     "Variation du nombre d'actions en circulation sur 3 ans.",
     "Positif = émissions d'actions : chaque part pèse moins lourd. Négatif "
     "= rachats : la part de chaque actionnaire augmente sans qu'il agisse."),
]

DOSSIER = [
    ("Position",
     "leader, challenger, suiveur ou acteur de niche sur le marché que "
     "l'analyse a délimité.",
     "Le périmètre du marché est la décision la plus lourde de l'analyse : un "
     "périmètre trop étroit fabrique un leader en excluant celui qui le menace."),
    ("Depuis / perdue en",
     "L'année où l'entreprise a atteint sa position — ou celle où elle a perdu "
     "le leadership.",
     "« Leader » sans « depuis quand » ne dit pas si la position est établie ou "
     "fraîche, et c'est toute la différence entre une rente et un accident. "
     "Une perte récente est une trajectoire ; une perte ancienne, un état de "
     "fait que le marché a déjà digéré."),
    ("Durabilité",
     "solide, à surveiller, en érosion, aucune — la résistance attendue de la "
     "position, pas sa force actuelle.",
     "Un leader dont la rente s'érode depuis cinq ans est plus dangereux qu'un "
     "challenger stable : c'est la question que personne n'affiche."),
    ("Sources de rente",
     "Ce qui protège la position : brand, patent, switching, network, cost, "
     "scale, regulatory, distribution.",
     "Ce qui ne rentre dans aucune de ces cases est en général une qualité "
     "opérationnelle, pas une barrière."),
    ("Danger d'une menace",
     "élevé, moyen ou faible, avec l'explication du mécanisme par lequel la "
     "menace ferait mal.",
     "Une menace faible ne retire aucun point : compter chaque menace recensée "
     "punirait le dossier le plus complet, alors qu'un concurrent identifié "
     "puis jugé peu dangereux est une information rassurante."),
    ("Menace directe / indirecte",
     "Directe = attaque le cœur de marché ; indirecte = substitut, "
     "réglementation, rupture technologique.",
     "Les menaces réelles viennent presque toujours de l'extérieur de "
     "l'univers européen — un dossier où tous les concurrents sont européens "
     "est suspect."),
    ("Solidité concurrentielle",
     "Un score sur 100 calculé à partir des verdicts : position, ancienneté, "
     "durabilité, menaces pondérées par leur danger.",
     "Calculé ici, jamais demandé au modèle : deux exécutions du même prompt "
     "donneraient deux notes. Le barème s'affiche à côté du total — un score "
     "dont on ne voit pas la construction ne se discute pas, il se subit."),
    ("Statut du dossier",
     "brouillon = importé sans relecture ; validé = relu et signé par un "
     "analyste nommé.",
     "Seul un dossier validé projette ses verdicts vers l'évaluation "
     "qualitative et le groupe de pairs, et peut faire passer le titre en "
     "solid."),
    ("Statut d'une affirmation",
     "FAIT_VERIFIE (source primaire), DECLARATION_ENTREPRISE (l'entreprise "
     "l'affirme), ESTIMATION, INTERPRETATION, MIGRE (repris d'un ancien "
     "dossier par conversion).",
     "« Leader du marché » figure dans le rapport annuel de la moitié des "
     "sociétés d'un secteur : c'est une déclaration, pas un fait."),
]


MATRICE = [
    ("Le principe",
     "La méthode a deux jambes : la **qualité** (position concurrentielle, "
     "rente, érosion — bloc D de la fiche) et le **prix** (z-score, écart à la "
     "tendance). Cette matrice les croise : c'est l'écran de synthèse du "
     "système.",
     "Aucune des deux jambes ne suffit seule : une décote sans qualité est "
     "souvent un piège, une qualité sans décote est déjà payée."),
    ("Axe horizontal — z-score",
     "Écart du cours à sa tendance de long terme, en écarts types. Négatif = "
     "décote apparente (à gauche), positif = surcote (à droite).",
     "Le trait vertical est le seuil de décote choisi (−1,5 par défaut)."),
    ("Axe vertical — ROIC − 8 %",
     "Écart entre la rentabilité du capital investi et le seuil de 8 % retenu "
     "comme coût du capital.",
     "Au-dessus de 0 : l'entreprise crée de la valeur (rente). En dessous : "
     "pas de rente, même si elle est bénéficiaire. C'est une projection "
     "chiffrée de la qualité — le quadrant officiel se calcule sur le niveau "
     "(tier), pas sur cet axe."),
    ("Forme du point — régime",
     "rond = rent (rente installée) · losange = cyclical · triangle = eroding "
     "· carré = no_moat · croix = unknown.",
     "La forme porte le régime pour rester lisible par un daltonien : la "
     "couleur est déjà prise par le z-score."),
    ("CIBLE",
     "Qualité `solid` (position établie, validée par un dossier concurrentiel "
     "relu) ET décote sous le seuil.",
     "Le seul quadrant d'achat potentiel — et il est normal qu'il soit vide "
     "longtemps : `solid` exige un concurrent hors Europe dans le groupe de "
     "pairs et une évaluation qualitative revue par un humain."),
    ("WATCHLIST",
     "Qualité établie mais prix non attractif, ou qualité encore à confirmer "
     "(`watch`).",
     "On suit, on n'achète pas : soit le prix n'y est pas, soit la rente "
     "n'est pas démontrée."),
    ("VALUE TRAP",
     "Décote ET position qui se dégrade (`eroding`).",
     "La liste la plus importante de l'écran : les titres qui ont l'air "
     "d'opportunités et n'en sont pas. La décote sur une position qui s'érode "
     "est un ajustement de prix correct — c'est là qu'on perd de l'argent."),
    ("À ÉVITER",
     "Cher ET position qui se dégrade.",
     "Peu dangereux en pratique : on n'était pas tenté."),
    ("NON QUALIFIÉ",
     "Position concurrentielle jamais évaluée (pas de dossier concurrentiel "
     "validé, ou fondamentaux insuffisants).",
     "Le statut réel de la majorité de l'univers en phase de qualification. "
     "Un signal de prix sur un titre non qualifié est un candidat à "
     "instruire, jamais une cible."),
]

PORTEFEUILLE = [
    ("Fictif (paper)",
     "Position simulée, sans argent engagé, exécutée à la dernière clôture "
     "hebdomadaire connue.",
     "Mesure la méthode, pas l'investisseur : elle supprime la peur de la "
     "perte et l'attente. Jamais agrégée avec le réel."),
    ("Support",
     "Où la position réelle est détenue : PEA, CTO, PER, assurance-vie… "
     "Déclaré dans l'onglet Supports.",
     "Sert à trois choses vérifiables : l'éligibilité géographique (un PEA "
     "n'accepte que des émetteurs UE/EEE), le plafond de versements, et la "
     "comparaison de performance à fiscalité identique. Sans objet en paper."),
    ("PRU",
     "Prix de revient unitaire : moyenne pondérée des achats, hors frais.",
     "Inchangé par une vente partielle. Les frais sont suivis à part — noyés "
     "dans le PRU, leur poids disparaît."),
    ("Investi",
     "Quantité × PRU + frais cumulés.",
     "Ce qui est réellement sorti (ou serait sorti, en paper) pour cette "
     "ligne."),
    ("Valeur / +/- value",
     "Quantité × dernière clôture hebdomadaire ; la +/- value est l'écart à "
     "l'investi.",
     "Latente tant que la position est ouverte : rien n'est acquis avant la "
     "vente."),
    ("Rdt total",
     "Rendement dividendes réinvestis, calculé via le facteur de rendement "
     "total (vérifié contre l'Adj Close Yahoo, écart médian 0,036 %).",
     "La seule mesure économiquement juste : la +/- value simple ignore les "
     "dividendes touchés en route."),
    ("z entrée / z actuel",
     "Le z-score du titre le jour de l'ouverture (figé, avec la ligne de "
     "calcul exacte via fit_id) et celui du dernier calcul.",
     "C'est la raison d'être de ce portefeuille : relire plus tard ce que le "
     "système affirmait au moment de la décision. z qui remonte vers 0 = la "
     "décote se referme."),
    ("Thèse « à relire »",
     "Chaque position porte une date de revue, 12 mois après l'ouverture.",
     "Relire la thèse écrite à l'achat est le seul antidote fiable au biais "
     "rétrospectif."),
    ("Verdict de thèse",
     "À la fermeture : vérifiée, infirmée, ou « on ne peut pas savoir ».",
     "La troisième réponse est la plus importante : une thèse peut être "
     "juste et la position perdante, ou l'inverse. Forcer un verdict binaire "
     "fabrique de l'apprentissage sur du bruit."),
]

# Les avis de tiers collectés chez Zonebourse et Boursier.com (lot L10). Le
# glossaire compte ici double : ces chiffres viennent d'ailleurs, avec leurs
# conventions, et rien à l'écran ne dit spontanément qu'une note de 24 % est un
# rang sectoriel plutôt qu'une probabilité.
VEILLE = [
    ("Recommandation moyenne",
     "L'avis agrégé des analystes qui suivent le titre, tel que la source le "
     "publie : de « vendre » à « acheter ».",
     "Un consensus est **structurellement optimiste** et révisé après coup : il "
     "n'entre dans aucun calcul de cette application. Il sert à savoir si la "
     "décote est un secret — et surtout à repérer les cas où il contredit le "
     "modèle, qui sont les plus intéressants."),
    ("Nombre d'analystes",
     "Combien de bureaux couvrent le titre.",
     "Trois analystes ne font pas un consensus. Sur une petite capitalisation, "
     "l'avis moyen peut être celui de deux maisons dont l'une est courtier du "
     "groupe."),
    ("Objectif de cours",
     "Prix moyen visé à douze mois par les analystes, et l'écart au cours "
     "actuel. La fourchette haute et basse encadre la dispersion.",
     "Un écart haut/bas très large traduit un désaccord, donc une difficulté à "
     "évaluer la société — pas une opportunité plus grande. L'objectif moyen "
     "suit le cours plus souvent qu'il ne l'anticipe."),
    ("Notations (Trader, Investisseur, Qualité…)",
     "Des **rangs** calculés par la source : « 24 % » signifie mieux noté que "
     "24 % de son univers de comparaison sur ce critère.",
     "Ce n'est ni une probabilité, ni une performance, ni une note sur 100. Deux "
     "titres à 60 % ne sont pas équivalents : les univers de comparaison "
     "diffèrent."),
    ("Points forts / points faibles",
     "Des phrases produites automatiquement par la source à partir de ses "
     "propres notations.",
     "Reproduites telles quelles. Ce n'est pas une analyse relue — ni la nôtre : "
     "la seule analyse relue de cette application est le dossier de position "
     "concurrentielle, et elle porte le nom de qui l'a validée."),
    ("Dépêches",
     "Les actualités du titre chez Boursier.com : titre, date, et texte complet "
     "pour les plus récentes.",
     "Le modèle lit vingt ans de cours et ignore la semaine dernière. Une "
     "démission, un avertissement sur résultats ou une dégradation expliquent "
     "souvent ce qu'aucun test statistique ne dira — et c'est ce qui sépare une "
     "décote d'un effondrement justifié."),
    ("Date de collecte",
     "Le jour où ces pages ont été lues. Chaque collecte est conservée.",
     "Une dépêche de trois semaines affichée sans sa date se lit comme une "
     "nouvelle du jour. Si l'âge indiqué surprend, relancer la collecte."),
]


def glossaire(lignes: list[tuple[str, str, str]],
              titre: str = "Que signifient ces indicateurs ?") -> None:
    """Affiche un glossaire dans un expander, au plus près des chiffres."""
    with st.expander(titre):
        st.dataframe(pd.DataFrame(lignes, columns=COLONNES),
                     use_container_width=True, hide_index=True)
