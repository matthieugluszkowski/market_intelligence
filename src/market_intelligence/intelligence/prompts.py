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
    "target_market": null, "target_customers": null,
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
  "manual_review": [],
  "quality_control": {
    "validated": false, "quality_score": null, "blocking_issues": [],
    "review_date": null
  },
  "sources": [{"title": null, "url": null, "date": null, "reliability": null}]
}

`analyst` reste `null` et `validated` reste `false` : seul un humain les
renseigne, au moment de l import."""


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
