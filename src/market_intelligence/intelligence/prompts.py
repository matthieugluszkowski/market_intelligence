"""Les quatre prompts du dossier concurrentiel (doc 08 SS8.2).

L'outil **compose** les prompts et **importe** le JSON. Il n'appelle aucune API :
entre les deux, le travail se fait ailleurs - ChatGPT, Claude, Perplexity - et
surtout, il se relit.

L'ordre n'est pas indifferent. Le prompt 1 sert a comprendre le marche **avant**
de choisir les concurrents ; la liste sort de ce prompt, elle est corrigee a la
main, et seulement ensuite le prompt 2 s'applique concurrent par concurrent.
Analyser en profondeur un concurrent mal choisi coute plus cher que de ne pas
l'analyser.
"""

from __future__ import annotations

# Ce que l'outil connait deja : le titre est choisi dans l'univers, son nom et sa
# date de reference viennent de la base. Rien d'autre n'est demande a l'analyste.
VARIABLES_CONNUES = ("ENTREPRISE_ANALYSEE", "DATE_DE_REFERENCE",
                     "PAYS_ET_ZONE_GEOGRAPHIQUE", "OBJECTIF_DE_L_ANALYSE")

# Ce que le LLM doit **etablir lui-meme** au prompt 1, et restituer dans son JSON.
#
# Les faire saisir a la main serait du travail inutile - un LLM sait dire dans
# quel sous-secteur opere adidas et a qui il vend - mais surtout ce serait
# imposer une reponse a une question qui fait partie de l'analyse. **Le perimetre
# d'un marche n'est pas une donnee d'entree, c'est le premier livrable du
# cadrage.** Le fixer d'avance revient a decider ou s'arrete la concurrence avant
# d'avoir regarde.
VARIABLES_A_ETABLIR = ("SECTEUR_ACTIVITE", "SOUS_SECTEUR", "MARCHE_CIBLE",
                       "PRODUIT_OU_SERVICE", "CLIENTS_CIBLES")

# Facultatives : ce que l'analyste ajoute s'il en dispose.
VARIABLES_FACULTATIVES = ("CONCURRENTS_CONNUS", "INFORMATIONS_INTERNES")

VARIABLES = (
    "ENTREPRISE_ANALYSEE", "SECTEUR_ACTIVITE", "SOUS_SECTEUR",
    "PAYS_ET_ZONE_GEOGRAPHIQUE", "MARCHE_CIBLE", "PRODUIT_OU_SERVICE",
    "CLIENTS_CIBLES", "CONCURRENTS_CONNUS", "DATE_DE_REFERENCE",
    "OBJECTIF_DE_L_ANALYSE", "INFORMATIONS_INTERNES", "CONCURRENT",
    "ANALYSE_FONCTIONNELLE", "FICHES_CONCURRENTIELLES", "ANALYSE_DES_LEADERS",
    # Prompt 5 : remplies par l'outil, jamais saisies. C'est le renversement
    # qui rend la synthese possible - les donnees sont deja en base.
    "TICKER", "DEVISE", "HORIZON_ANALYSE", "DONNEES_QUANTITATIVES",
    "DOSSIER_ANALYSES",
)

_SOURCES = """HIERARCHIE DES SOURCES

Par ordre de valeur decroissante. Une source de rang inferieur ne contredit
jamais une source de rang superieur sans que le conflit soit signale.

1. sites officiels des entreprises
2. rapports annuels, documents reglementaires, presentations investisseurs
3. bases reglementaires et publications d organismes publics
4. communiques de presse
5. documentation produit et pages tarifaires
6. offres d emploi, souvent plus precoces que la communication officielle
7. avis clients et plateformes specialisees
8. presse economique et technologique
9. reseaux sociaux, signal secondaire uniquement

Ne considere jamais une affirmation marketing comme un fait independant.
Lorsque plusieurs sources se contredisent, signale le conflit au lieu de choisir.
N invente aucune donnee manquante.

Pour chaque information importante, conserve la source, l URL, la date de
publication ou de consultation, et le niveau de fiabilite."""

_STATUTS = """STATUT DE CHAQUE AFFIRMATION

Une phrase sans statut est inexploitable trois mois plus tard : on ne sait plus
si elle a ete verifiee ou deduite. Chaque affirmation porte donc l un de :

- FAIT_VERIFIE            etabli par une source primaire citee
- DECLARATION_ENTREPRISE  l entreprise l affirme ; ce n est pas un fait independant
- DONNEE_SECONDAIRE       reprise d un agregateur, non remontee a la source
- SIGNAL                  indice de trajectoire
- ESTIMATION              chiffre calcule ou approche, avec sa methode
- INTERPRETATION          ta lecture a partir des elements reunis
- HYPOTHESE               affirmation prospective, non demontrable

« Leader du marche europeen » figure dans le rapport annuel de la moitie des
societes d un secteur : c est une DECLARATION_ENTREPRISE, jamais un FAIT_VERIFIE."""

_LANGUE = """LANGUE DE LA REPONSE

Ta reponse est integralement en francais - sections, analyses, justifications,
tableaux, et les valeurs textuelles du JSON final. Restent inchanges : les
cles du JSON, et les valeurs d enumeration imposees par le format (statuts
comme FAIT_VERIFIE, types comme direct/indirect, niveaux low/medium/high,
classifications comme study_buy). Une analyse en anglais est a refaire."""

_ENTETE = """CE QUI T EST FOURNI

- Entreprise etudiee : {{ENTREPRISE_ANALYSEE}}
- Zone geographique : {{PAYS_ET_ZONE_GEOGRAPHIQUE}}
- Date de reference : {{DATE_DE_REFERENCE}}
- Objectif de l analyse : {{OBJECTIF_DE_L_ANALYSE}}
- Concurrents deja identifies, le cas echeant : {{CONCURRENTS_CONNUS}}
- Contexte complementaire, le cas echeant : {{INFORMATIONS_INTERNES}}

CE QUE TU DOIS ETABLIR TOI-MEME

Les elements suivants ne te sont pas donnes : **c est a toi de les determiner et
de les restituer explicitement**, en citant tes sources.

Ils font partie du resultat de l analyse, pas de ses donnees d entree. Le
perimetre d un marche n est pas une hypothese de depart, c est le premier
livrable du cadrage : le fixer d avance reviendrait a decider ou s arrete la
concurrence avant d avoir regarde.

- secteur d activite
- sous-secteur precis
- produit ou service analyse, et son perimetre
- marche cible
- clients cibles, en distinguant acheteurs, prescripteurs et utilisateurs finaux

Indications eventuellement fournies par l analyste - a traiter comme des pistes,
non comme des consignes. **Contredis-les si tes sources le justifient**, en
expliquant pourquoi : secteur {{SECTEUR_ACTIVITE}}, sous-secteur
{{SOUS_SECTEUR}}, produit {{PRODUIT_OU_SERVICE}}, marche {{MARCHE_CIBLE}},
clients {{CLIENTS_CIBLES}}."""


CADRAGE = f"""Tu es un analyste senior en strategie produit, intelligence de marche et
analyse fonctionnelle.

{_ENTETE}

OBJECTIF

Produis une analyse fonctionnelle et strategique du marche permettant de :

1. comprendre le besoin client ;
2. identifier les fonctions couvertes par les solutions existantes ;
3. distinguer les fonctions indispensables, differenciantes et secondaires ;
4. identifier les categories de concurrents ;
5. preparer une comparaison structuree entre l entreprise etudiee et ses concurrents.

{_SOURCES}

{_LANGUE}

ANALYSE A PRODUIRE

0. **Cadrage.** Etablis d abord, et affirme explicitement : secteur,
   sous-secteur, produit ou service analyse, marche cible, clients cibles.
   Chacun avec sa source et son statut. Si l analyste a fourni une indication et
   que tes sources la contredisent, dis-le et explique pourquoi.

1. Definition du marche : perimetre inclus, perimetre exclu, tendances
   structurantes, facteurs reglementaires, technologiques et economiques.

2. Problemes et besoins clients : problemes rencontres, utilisateurs concernes,
   distinction entre acheteurs, prescripteurs et utilisateurs finaux, taches que
   les clients cherchent a accomplir, frustrations, criteres de decision.

3. Analyse fonctionnelle. Matrice contenant, par fonction : description, type
   d utilisateur, importance, frequence d utilisation, couverture par l entreprise
   etudiee, couverture par les concurrents, difficulte de mise en oeuvre,
   potentiel de differenciation. Classe chaque fonction en fonction coeur,
   necessaire, differenciante ou accessoire.

4. Cartographie des acteurs : leaders mondiaux, leaders regionaux, concurrents
   directs, concurrents indirects, nouveaux entrants, solutions internes ou
   alternatives manuelles, plateformes adjacentes pouvant devenir concurrentes.

5. Selection initiale des concurrents. Au maximum 5 directs, 5 indirects,
   5 acteurs de reference. Pour chacun : pourquoi il est pertinent, son degre de
   concurrence, le segment concerne, et **ce qui doit etre verifie a la main**.

   Cette liste sera relue et corrigee par un humain avant toute analyse
   detaillee. Signale explicitement les choix dont tu es le moins sur.

6. Synthese strategique : quel est le veritable probleme client, quelles
   fonctions determinent reellement le choix, sur quels criteres l entreprise
   etudiee peut gagner, quels criteres rendent la concurrence difficile a battre,
   quelles informations manquent encore.

{_STATUTS}

FORMAT DE SORTIE

Sections A. Resume executif, B. Definition du marche, C. Besoins clients,
D. Matrice fonctionnelle, E. Cartographie des acteurs, F. Concurrents proposes,
G. Points a verifier manuellement, H. Sources.

Termine par un objet JSON valide. Le bloc `scoping` porte ce que tu as etabli
toi-meme au point 0 :

{{
  "scoping": {{
    "sector": null, "subsector": null, "product_or_service": null,
    "target_market": null, "target_customers": null, "geography": null,
    "status": "INTERPRETATION", "sources": []
  }},
  "market_definition": {{}},
  "customer_needs": [],
  "functional_matrix": [],
  "actor_mapping": [],
  "proposed_competitors": [],
  "manual_verifications": [],
  "sources": []
}}

Chaque concurrent propose porte au minimum : company_name, country (code ISO a
deux lettres), competition_type (direct, indirect, reference ou emerging),
relevance_explanation, status, sources."""


CONCURRENT = f"""Tu es un analyste senior specialise en intelligence concurrentielle, strategie
produit et due diligence commerciale.

- Entreprise etudiee par notre equipe : {{{{ENTREPRISE_ANALYSEE}}}}
- Secteur : {{{{SECTEUR_ACTIVITE}}}}
- Produit ou service analyse : {{{{PRODUIT_OU_SERVICE}}}}
- **Concurrent a analyser : {{{{CONCURRENT}}}}**
- Zone geographique : {{{{PAYS_ET_ZONE_GEOGRAPHIQUE}}}}
- Date de reference : {{{{DATE_DE_REFERENCE}}}}
- Concurrents deja identifies : {{{{CONCURRENTS_CONNUS}}}}

Informations internes disponibles : {{{{INFORMATIONS_INTERNES}}}}

OBJECTIF

Produis une fiche concurrentielle complete, factuelle et exploitable.

L objectif n est pas de decrire l entreprise. Il faut expliquer **en quoi elle
est reellement concurrente**, quelles sont ses forces et ses faiblesses, quelle
trajectoire elle semble suivre, et ce que cela implique pour notre entreprise.

REGLES IMPERATIVES

1. Cherche d abord les sources primaires.
2. Cite chaque information importante avec une URL et une date.
3. Distingue les faits des declarations commerciales.
4. Ne transforme jamais une absence d information en conclusion negative.
5. Indique explicitement les donnees non disponibles.
6. Ne deduis pas une strategie d un seul signal.
7. Pour tout chiffre : annee, devise, perimetre, source.
8. Si une donnee est ancienne, dis qu elle doit etre actualisee.
9. **Ne fabrique aucun chiffre** de chiffre d affaires, de clients, de parts de
   marche ou de financement.
10. Lorsque tu formules une appreciation, explique ce qui la justifie.

{_SOURCES}

{_LANGUE}

ANALYSE DEMANDEE

1. Identite : raison sociale, marques, siege, date de creation, dirigeants, pays
   d activite, statut juridique, actionnariat ou investisseurs.

2. Activite : proposition de valeur, produits et services, segments clients, cas
   d usage, secteurs servis, zones geographiques, modele economique, canaux.

3. Pertinence concurrentielle : concurrence directe et indirecte, recouvrement
   des clients, des besoins et des fonctions, **zones ou ce concurrent ne
   constitue pas une menace reelle**, niveau global - faible, moyen, fort,
   critique.

4. Offre et fonctionnalites : tableau fonctionnalite / presence / maturite /
   preuve / couverture estimee chez nous / avantage concurrentiel.

5. Positionnement : message principal, promesse client, segments privilegies,
   differenciation revendiquee, **differenciation reellement demontree**, image
   de marque, niveau de confiance inspire par les preuves.

6. Prix et packaging : modele de tarification, niveaux d offre, prix publies,
   prix non publics, frais d installation, engagement, couts variables,
   comparaison avec notre offre, degre de confiance.

7. Forces, classees en : produit, technologie, distribution, marque, prix,
   donnees, partenaires, financement, reglementation, equipe, effet reseau.

8. Faiblesses et vulnerabilites : limites produit, dependance a des clients ou
   marches, dependance technologique, risques financiers et reglementaires,
   problemes signales par les utilisateurs, complexite d integration, lenteur
   d innovation, faiblesse geographique, dependance a une personne.

9. Signaux de trajectoire : recrutements, nouvelles fonctionnalites, changements
   de prix, nouvelles zones, partenariats, acquisitions, licenciements, levees de
   fonds, evolution de la communication et des avis, changements de dirigeants.
   Pour chacun : date, source, interpretation prudente, niveau de confiance.

10. Trois scenarios a 12-36 mois - favorable au concurrent, central, defavorable.
    Pour chacun : hypotheses, elements declencheurs, consequences pour nous,
    indicateurs a surveiller, probabilite qualitative.

11. Appreciation finale : pourquoi ce concurrent est important, sa menace
    principale, sa vulnerabilite principale, l avantage a ne pas lui laisser,
    l evolution qui modifierait le rapport de force, et **ce qui doit etre
    verifie par un humain avant decision**.

{_STATUTS}

FORMAT DE SORTIE

Sections A a M : Resume executif, Identite et activite, Pertinence
concurrentielle, Produit et fonctionnalites, Positionnement, Prix et modele
economique, Forces, Faiblesses, Signaux de trajectoire, Scenarios futurs,
Appreciation strategique, Donnees manquantes, Sources.

Termine par un JSON valide :

{{
  "company_identity": {{}},
  "business_model": {{}},
  "competitive_relevance": {{}},
  "products_and_features": [],
  "positioning": {{}},
  "pricing": {{}},
  "strengths": [],
  "weaknesses": [],
  "trajectory_signals": [],
  "future_scenarios": [],
  "strategic_assessment": {{}},
  "missing_information": [],
  "sources": []
}}"""


LEADERS = f"""Tu es un analyste principal en strategie, intelligence economique et prospective
de marche.

{_ENTETE}

OBJECTIF

Comprendre qui dirige reellement le marche, pourquoi ces acteurs ont pris cette
position, quelles capacites sont difficiles a reproduire, quelles evolutions
pourraient redistribuer les cartes, et comment l entreprise etudiee peut defendre
ou ameliorer sa position.

{_SOURCES}

{_LANGUE}

Ne donne aucun classement sans expliquer la methode. Ne confonds pas chiffre
d affaires, part de marche, notoriete, base clients, volume d utilisateurs,
avantage technologique et influence sectorielle : ce sont sept classements
differents, et ils ne donnent pas le meme vainqueur.

ANALYSE DEMANDEE

1. Definition du leadership. Quels criteres sont pertinents ici : taille,
   croissance, rentabilite, couverture geographique, profondeur fonctionnelle,
   innovation, distribution, fidelite client, ecosysteme, conformite, donnees,
   couts de changement.

2. Classement ou segmentation des leaders. Pour chacun : critere de leadership,
   preuves, segment domine, **limites du classement**, niveau de confiance.

3. Analyse des leaders : origine de l avantage, clientele, modele economique,
   architecture produit, distribution, partenariats, barrieres a l entree,
   vulnerabilites, evolution recente.

4. Tendances structurantes - technologiques, reglementaires, economiques,
   societales, comportementales, geographiques, de distribution, de couts. Pour
   chacune : horizon, preuves, gagnants et perdants potentiels, impact sur
   l entreprise etudiee.

5. Au moins cinq points de rupture possibles : nouvelle reglementation,
   innovation, baisse de couts, arrivee d un acteur puissant, consolidation,
   changement de comportement client, dependance a une plateforme, crise
   d approvisionnement ou de financement.

6. Trois scenarios de marche a 12-36 mois - continuite, acceleration, rupture.
   Pour chacun : hypotheses, indicateurs avances, acteurs favorises et fragilises,
   consequences pour l entreprise etudiee, decisions a preparer.

7. Recommandations strategiques, utiles a la decision sans etre faussement
   precises : capacites a developper, fonctions a prioriser, segments a eviter,
   partenariats a envisager, risques a surveiller, avantages a proteger,
   informations a collecter ensuite.

8. **Conclusion contradictoire.** Presente le meilleur argument en faveur de
   l entreprise etudiee, le meilleur argument contre elle, l hypothese la plus
   fragile de ton analyse, et l information qui - si elle etait fausse -
   changerait la conclusion.

{_STATUTS}

FORMAT DE SORTIE

Sections A a K : Resume executif, Methode de classement, Leaders du marche,
Avantages defendables, Tendances structurantes, Points de rupture, Scenarios,
Implications, Recommandations, Conclusion contradictoire, Sources.

Termine par un JSON valide :

{{
  "market_leadership_method": {{}},
  "market_leaders": [],
  "defensible_advantages": [],
  "structural_trends": [],
  "disruption_points": [],
  "market_scenarios": [],
  "implications_for_company": [],
  "recommendations": [],
  "contrarian_conclusion": {{}},
  "sources": []
}}"""


CONTROLE = """Tu es un controleur qualite charge de valider un dossier d intelligence de
marche avant son integration dans une base de donnees.

Analyses a controler :

{{ANALYSE_FONCTIONNELLE}}

{{FICHES_CONCURRENTIELLES}}

{{ANALYSE_DES_LEADERS}}

OBJECTIF

Controle la coherence, la qualite des sources, les doublons et les
contradictions. Verifie notamment :

1. qu aucune entreprise n est classee concurrente sans justification ;
2. que les faits sont separes des interpretations ;
3. que les affirmations importantes disposent d une source ;
4. que les dates sont presentes ;
5. que les chiffres indiquent leur perimetre et leur devise ;
6. que les informations contradictoires sont signalees ;
7. que les conclusions ne depassent pas les preuves disponibles ;
8. que les noms d entreprises et de produits sont homogenes ;
9. que les URLs semblent completes ;
10. que le JSON final est syntaxiquement valide ;
11. que les informations personnelles ou confidentielles ont ete supprimees ;
12. que rien n est presente comme certain quand ce n est qu une estimation.

Pour chaque probleme : identifiant, niveau BLOQUANT / IMPORTANT / MINEUR,
element concerne, explication, correction proposee.

Produis ensuite la liste des donnees validees, celle des donnees a revoir
manuellement, celle des donnees a supprimer, puis la version JSON normalisee.

SYNTHESE SUR L ENTREPRISE ETUDIEE

Le dossier ne vaut que s il conclut sur l entreprise etudiee elle-meme, pas
seulement sur ses concurrents. Le bloc `strategic_assessment` porte cette
synthese, etablie a partir de l ensemble des analyses controlees :

- position_verdict : leader, challenger, follower ou niche
- durability_verdict : solid, watch, eroding ou none
- moat_sources : parmi brand, patent, switching, network, cost, scale
- threats : les menaces principales qui pesent sur la position
- main_strengths / main_weaknesses : de l entreprise etudiee, pas des concurrents
- rationale : la justification en quelques phrases, appuyee sur le dossier

Ce sont des **propositions** : l analyste les confirme, les corrige ou les pose
lui-meme au moment de l import. La validation reste humaine.

Le bloc `quality_control.blocking_issues` ne liste que les problemes NON
resolus. Tant qu il en reste, le dossier sera conserve en brouillon : il ne
validera pas le titre.

LANGUE DE LA REPONSE

Ta reponse est integralement en francais - controle, listes et valeurs
textuelles du JSON normalise. Restent inchanges : les cles du JSON et les
valeurs d enumeration imposees (statuts, low/medium/high, draft).

REGLE IMPORTANTE

**Ne complete jamais silencieusement une donnee manquante.** Utilise `null`
lorsqu une valeur n est pas disponible. Ne transforme jamais une hypothese en
fait. Un dossier qui a l air complet et ne l est pas est plus dangereux qu un
dossier visiblement incomplet.

FORMAT DE SORTIE

Le JSON normalise respecte exactement cette structure :

{
  "analysis_metadata": {
    "analysis_id": null, "company_analyzed": null, "sector": null,
    "subsector": null, "geography": null, "reference_date": "AAAA-MM-JJ",
    "analyst": null, "status": "draft"
  },
  "market_definition": {
    "description": null, "included_scope": [], "excluded_scope": [],
    "confidence": "low"
  },
  "customer_needs": [],
  "competitors": [
    {
      "company_name": null, "normalized_name": null, "country": null,
      "competition_type": "direct", "relevance_score": 0,
      "relevance_explanation": null, "status": "ESTIMATION", "sources": []
    }
  ],
  "functional_analysis": [
    {
      "function_name": null, "description": null, "importance": "medium",
      "company_coverage": "unknown", "competitor_coverage": [],
      "differentiation_potential": "medium", "status": "ESTIMATION", "sources": []
    }
  ],
  "company_profiles": [],
  "market_leaders": [],
  "market_trends": [],
  "future_scenarios": [],
  "strategic_assessment": {
    "position_verdict": null, "durability_verdict": null,
    "moat_sources": [], "threats": [], "main_strengths": [],
    "main_weaknesses": [], "rationale": null, "status": "INTERPRETATION"
  },
  "manual_review": [],
  "quality_control": {
    "validated": false, "quality_score": null, "blocking_issues": [],
    "review_date": null
  },
  "sources": [{"title": null, "url": null, "date": null, "reliability": null}]
}

`analyst` reste `null` et `validated` reste `false` : seul un humain les
renseigne, au moment de l import."""


SYNTHESE = """Tu es un analyste senior independant, specialise en analyse d entreprise,
valorisation, intelligence concurrentielle et analyse des risques.

Ta mission : produire une evaluation synthetique et contradictoire de
l entreprise etudiee, a partir des DONNEES DE L OUTIL fournies ci-dessous.
Elles sont ta seule matiere : tu peux les critiquer, les juger insuffisantes,
jamais les completer en silence.

CE QUE MESURENT LES SCORES - LA REGLE CENTRALE

Les scores mesurent la solidite de l analyse et l attractivite relative du
dossier. **Ils ne predisent pas le cours futur**, et rien dans ta reponse ne
doit le laisser croire. Un LLM peut produire une reponse tres assuree sur des
donnees incompletes, anciennes ou contradictoires : la separation des scores
existe pour empecher cela.

- score d attractivite : qualite et interet potentiel du dossier ;
- score de confiance : robustesse, fraicheur, coherence et verifiabilite de
  l analyse - il ne dit PAS si l action va monter ;
- score d alignement : coherence entre qualite, risque, perspectives et prix ;
- verdict : une des six conclusions, dont s abstenir.

INTERDITS

- aucune certitude artificielle : l incertitude s affiche, elle ne se lisse pas ;
- aucune donnee inventee : une donnee absente est dite absente ;
- aucun conseil financier personnalise, aucun ordre, aucune garantie ;
- « INSUFFISANT POUR CONCLURE » est une reponse valide et respectable.

CONTRAT DE SORTIE - NON NEGOCIABLE

Ta reponse suit le FORMAT DE SORTIE decrit en fin de prompt et se termine
OBLIGATOIREMENT par le bloc JSON final - y compris si tu conclus
« INSUFFISANT POUR CONCLURE », et y compris si les donnees te parviennent en
fichier joint plutot que dans le prompt : un fichier joint est une source de
donnees, pas un document a resumer.

CONTEXTE

- Entreprise etudiee : {{ENTREPRISE_ANALYSEE}}
- Identifiant : {{TICKER}}
- Secteur : {{SECTEUR_ACTIVITE}} · Sous-secteur : {{SOUS_SECTEUR}}
- Devise : {{DEVISE}}
- Date de reference : {{DATE_DE_REFERENCE}}
- Horizon d analyse : {{HORIZON_ANALYSE}}
- Objectif : {{OBJECTIF_DE_L_ANALYSE}}

DONNEES QUANTITATIVES DE L OUTIL (JSON, dans le prompt ou en fichier joint)

Prix et tendance (z-score, regression, statistiques de regime), ratios
fondamentaux, qualite quantitative (rente, erosion), evaluation qualitative.
Un bloc null ou absent est une donnee manquante : signale-la, ne l estime pas.

{{DONNEES_QUANTITATIVES}}

DOSSIER D ANALYSES DE L OUTIL (JSON, dans le prompt ou en fichier joint)

Le dossier accumule par les prompts 1 a 4 : cadrage, concurrents, fiches
concurrentielles, leaders, tendances, scenarios, controle qualite, synthese
strategique.

{{DOSSIER_ANALYSES}}

CONTROLE PREALABLE OBLIGATOIRE

Avant tout score, verifie : la date de chaque donnee importante ; la coherence
entre la date du prix et celle des comptes ; devises, unites et perimetres ;
les doublons ; les contradictions entre analyses ; les sources ; les problemes
BLOQUANTS du controle qualite ; les indicateurs manquants ou aberrants.

Regle des bloquants :
- un probleme BLOQUANT non resolu ET non acquitte nominativement
  (`quality_control.blocking_issues` present sans
  `quality_control.blocking_issues_reviewed`) interdit toute conclusion
  d investissement : limite-toi a un diagnostic de qualite et plafonne le
  score de confiance a 30/100 ;
- un bloquant acquitte par un analyste nomme ne plafonne plus la confiance,
  mais reste cite dans les limites de l analyse.

Donnees anciennes ou manquantes : baisse le score de confiance, indique l age
ou l absence, n utilise jamais une estimation a la place d un fait.

ANALYSE DEMANDEE

1. Fondamentaux : qualite economique (croissance, marges, tresorerie,
   rentabilite des capitaux, recurrence), solidite financiere (dette,
   liquidite, dilution, resistance a un scenario defavorable), avantage
   concurrentiel (a partir du dossier), gouvernance **uniquement si le dossier
   porte des elements - ne deduis rien du silence**, risques (sectoriel,
   reglementaire, technologique, geographique, concentration, liquidite).

2. Valorisation : le niveau actuel par rapport a l historique du titre, aux
   comparables du dossier, a la croissance, aux marges, aux risques. Une
   decote ne prouve rien seule : explique ce qui la justifie ou non - qualite,
   croissance, risque, dette, perception, information manquante. Presente
   trois scenarios (defavorable, central, favorable) avec hypotheses et
   conditions d invalidation. Pas de cible de prix si les hypotheses ne la
   justifient pas.

3. Prix et moment de marche : tendance, z-score, regime, episodes passes sous
   le seuil - en disant si ces signaux confirment, contredisent ou n apportent
   rien a l analyse fondamentale. Un indicateur technique n est jamais une
   preuve de valeur intrinseque.

SCORES

**Score d attractivite /100** - ponderation indicative : qualite economique 20,
solidite financiere 15, avantage concurrentiel 15, management et gouvernance
10, croissance et potentiel du marche 10, valorisation actuelle 20, risques et
resilience 10. Pour chaque categorie : note, maximum, justification, donnees
utilisees, donnees manquantes, confiance de la note. Une note elevee ne
compense jamais un risque critique ; un risque de solvabilite critique
plafonne le score global.

**Score de confiance /100** - grille : controle qualite 20, fraicheur des
donnees 15, couverture des indicateurs importants 15, qualite des sources 15,
coherence entre sources 10, coherence fondamentaux/prix/valorisation 10,
couverture concurrentielle 10, clarte des hypotheses et scenarios 5.
Lecture : 85-100 elevee · 70-84 correcte · 50-69 limitee · 30-49 faible ·
0-29 non exploitable. **Sous 50, aucune conclusion forte.** Une entreprise
attractive avec une confiance faible se place sous surveillance, jamais en
achat a etudier.

**Score d alignement /100** (facultatif) : le rapport entre qualite
fondamentale, risque, perspectives et prix actuel est-il coherent ? Explique
les desaccords : excellente mais chere, mediocre mais decotee, attractive
uniquement dans le scenario favorable...

VERDICT

Un parmi : ACHAT A ETUDIER · CONSERVATION A ETUDIER · SURVEILLANCE ·
ATTENDRE UNE MEILLEURE VALORISATION · EVITER OU ATTENDRE · INSUFFISANT POUR
CONCLURE.

Accompagne de : la these en trois phrases maximum ; les trois elements les
plus favorables ; les trois risques les plus importants ; le principal facteur
d invalidation ; les donnees a actualiser ; les conditions qui feraient
evoluer l avis ; les indicateurs a surveiller ; la date recommandee de
revision.

""" + _STATUTS + "\n\n" + _LANGUE + """

FORMAT DE SORTIE

Sections A. Verdict, B. Score d attractivite, C. Score de confiance,
D. Score d alignement, E. Notes par categorie, F. Fondamentaux,
G. Valorisation, H. Prix et marche, I. Forces, J. Risques, K. Hypotheses
critiques, L. Donnees manquantes ou a actualiser, M. Conditions
d invalidation, N. Indicateurs a surveiller, O. Conclusion.

Termine imperativement par un JSON valide, sans texte autour :

{
  "analysis_metadata": {
    "company_analyzed": null, "ticker": null, "reference_date": null,
    "analysis_horizon": null, "status": "draft"
  },
  "quality_gate": {
    "passed": false, "blocking_issues": [], "blocking_issues_acknowledged": false,
    "important_issues": [], "manual_review_required": true,
    "conclusion_allowed": false
  },
  "scores": {
    "attractiveness_score": null, "confidence_score": null,
    "alignment_score": null, "maximum_confidence_allowed": null,
    "score_version": "1.0", "scored_by": "llm"
  },
  "category_scores": [
    {
      "category": "economic_quality", "score": null, "maximum": 20,
      "justification": null, "evidence": [], "missing_data": [],
      "confidence": "low"
    }
  ],
  "valuation_assessment": {
    "current_price": null, "currency": null,
    "valuation_status": "cheap|fair|expensive|uncertain",
    "valuation_method": [], "bear_case": {}, "base_case": {}, "bull_case": {},
    "key_assumptions": [], "invalidation_conditions": []
  },
  "market_assessment": {
    "trend": null, "volatility": null,
    "technical_signal": "positive|neutral|negative|unavailable",
    "fundamental_signal": "positive|neutral|negative|unavailable",
    "alignment": "confirmed|mixed|contradictory|unavailable"
  },
  "recommendation_status": {
    "classification": "study_buy|study_hold|monitor|wait_for_better_valuation|avoid_or_wait|insufficient_to_conclude",
    "rationale": null, "not_investment_advice": true
  },
  "key_strengths": [], "key_risks": [], "critical_hypotheses": [],
  "missing_or_stale_data": [], "monitoring_indicators": [],
  "review_triggers": [], "review_recommended_at": null,
  "sources": []
}

`scored_by` reste `llm` : un humain peut relire cette synthese, jamais la
produire retroactivement. Les scores mesurent le dossier, pas le cours futur."""


PROMPTS = {
    "cadrage": ("1 · Cadrage et analyse fonctionnelle", CADRAGE,
                "Comprendre le marche AVANT de choisir les concurrents. "
                "Une fois par titre."),
    "concurrent": ("2 · Fiche d un concurrent", CONCURRENT,
                   "Une fiche homogene par concurrent. **Un concurrent a la "
                   "fois**, apres verification manuelle de la liste."),
    "leaders": ("3 · Leaders, marche et perspectives", LEADERS,
                "Qui dirige, pourquoi, et ce qui peut redistribuer les cartes. "
                "Une fois par titre."),
    "controle": ("4 · Controle qualite et normalisation", CONTROLE,
                 "Verifie avant integration et produit le JSON normalise. "
                 "Non facultatif."),
    "synthese": ("5 · Synthese decisionnelle et scoring", SYNTHESE,
                 "Trois scores separes - attractivite du dossier, confiance "
                 "dans l analyse, alignement qualite/prix - et un verdict qui "
                 "peut etre de s abstenir. **Les scores mesurent la solidite "
                 "du dossier, jamais le cours futur.** Les donnees sont "
                 "injectees par l outil : a lancer apres le prompt 4."),
}


def compose(cle: str, variables: dict) -> str:
    """Remplace les {{VARIABLES}} du prompt.

    Le marqueur depend de la nature de la variable, et cette distinction porte
    tout le dispositif :

    - une variable **a etablir** laissee vide devient « a determiner par toi » :
      c'est une consigne, pas un manque ;
    - une variable **facultative** vide le dit explicitement, pour que le LLM ne
      la cherche pas ;
    - une variable **connue** vide est un vrai manque, signale comme tel.
    """
    if cle not in PROMPTS:
        raise KeyError(f"prompt inconnu : {cle!r}, attendu {sorted(PROMPTS)}")
    texte = PROMPTS[cle][1]
    for nom in VARIABLES:
        valeur = (variables.get(nom) or "").strip()
        if valeur:
            remplacement = valeur
        elif nom in VARIABLES_A_ETABLIR:
            remplacement = "[a determiner par toi]"
        elif nom in VARIABLES_FACULTATIVES:
            remplacement = "[aucune indication fournie]"
        else:
            remplacement = f"[A RENSEIGNER : {nom}]"
        texte = texte.replace("{{" + nom + "}}", remplacement)
    return texte


def variables_manquantes(cle: str, variables: dict) -> list[str]:
    """Variables **requises** de ce prompt qui ne sont pas renseignees.

    Ni celles que le LLM doit etablir, ni les facultatives : leur absence est
    normale et voulue, la signaler comme un manque serait trompeur.
    """
    texte = PROMPTS[cle][1]
    return [nom for nom in VARIABLES_CONNUES
            if "{{" + nom + "}}" in texte and not (variables.get(nom) or "").strip()]
