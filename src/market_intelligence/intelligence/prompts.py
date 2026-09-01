"""Le prompt du dossier de position concurrentielle (doc 08 SS8.2).

L'outil **compose** le prompt et **importe** le JSON. Il n'appelle aucune API :
entre les deux, le travail se fait ailleurs - ChatGPT, Claude, Perplexity - et
surtout, il se relit.

Un seul prompt, et c'est le sujet
----------------------------------
La version precedente en comptait cinq, pour 34 000 caracteres de consignes et
un dossier de vingt-deux blocs : besoins clients, analyse fonctionnelle,
tendances de marche, scenarios prospectifs, controle qualite, synthese
decisionnelle, sept notes par categorie, trois scores. Sur EssilorLuxottica,
ce dispositif a rendu **30/100 de confiance et un refus de conclure** pour un
dossier dont le paragraphe de synthese disait « leader incontesté ». Le detail
avait mange la conclusion, et le cout d'entree - cinq copier-coller par titre -
faisait qu'on ne lancait l'analyse presque jamais.

Ce prompt pose quatre questions et n'en pose aucune autre :

1. L'entreprise est-elle leader de son marche ?
2. Depuis quand - et si elle l'a perdu, depuis quand ?
3. Qui sont ses concurrents, et **en quoi chacun est une menace** ?
4. Quelles autres menaces pesent sur elle, et en quoi c'est dangereux ?

**Aucune note n'est demandee au modele.** Un LLM a qui l'on demande un score en
invente un, et deux executions du meme prompt donnent deux nombres. Le score se
calcule dans `intelligence.position`, par une formule affichee a l'ecran.
"""

from __future__ import annotations

# Ce que l'outil connait deja : le titre est choisi dans l'univers, son nom et sa
# date de reference viennent de la base. Rien d'autre n'est demande a l'analyste.
VARIABLES_CONNUES = ("ENTREPRISE_ANALYSEE", "DATE_DE_REFERENCE",
                     "PAYS_ET_ZONE_GEOGRAPHIQUE")

# Ce que le LLM doit **etablir lui-meme** et restituer dans son JSON.
#
# **Le perimetre d'un marche n'est pas une donnee d'entree, c'est un livrable.**
# Le fixer d'avance revient a decider ou s'arrete la concurrence avant d'avoir
# regarde - et c'est ainsi qu'on declare leader une entreprise dont on a exclu
# le concurrent qui la menace.
VARIABLES_A_ETABLIR = ("MARCHE_CIBLE",)

# Facultatives : ce que l'analyste ajoute s'il en dispose.
VARIABLES_FACULTATIVES = ("CONCURRENTS_CONNUS", "INFORMATIONS_INTERNES")

VARIABLES = (
    "ENTREPRISE_ANALYSEE", "PAYS_ET_ZONE_GEOGRAPHIQUE", "DATE_DE_REFERENCE",
    "MARCHE_CIBLE", "CONCURRENTS_CONNUS", "INFORMATIONS_INTERNES",
)

_SOURCES = """SOURCES

Par ordre de valeur decroissante : sites officiels et documents reglementaires,
rapports annuels et presentations investisseurs, organismes publics et
regulateurs, communiques de presse, documentation produit, presse economique.

Ne considere jamais une affirmation marketing comme un fait independant.
« Leader du marche » figure dans le rapport annuel de la moitie des societes
d un secteur. Lorsque deux sources se contredisent, signale le conflit au lieu
de choisir. N invente aucune donnee manquante : `null` est une reponse."""

_STATUTS = """STATUT DE CHAQUE AFFIRMATION

Une phrase sans statut est inexploitable six mois plus tard : on ne sait plus si
elle a ete verifiee ou deduite. Chaque bloc porte donc l un de :

- FAIT_VERIFIE            etabli par une source primaire citee
- DECLARATION_ENTREPRISE  l entreprise l affirme ; ce n est pas un fait independant
- ESTIMATION              chiffre calcule ou approche, avec sa methode
- INTERPRETATION          ta lecture a partir des elements reunis"""

_LANGUE = """LANGUE

Ta reponse est integralement en francais, y compris les valeurs textuelles du
JSON. Restent inchangees : les cles du JSON, et les valeurs d enumeration
imposees ci-dessous (leader, solid, eleve, directe, brand...)."""


POSITION = f"""Tu es un analyste en intelligence concurrentielle. Tu reponds a
quatre questions sur une entreprise cotee, et **a aucune autre**.

CE QUI T EST FOURNI

- Entreprise etudiee : {{{{ENTREPRISE_ANALYSEE}}}}
- Zone geographique : {{{{PAYS_ET_ZONE_GEOGRAPHIQUE}}}}
- Date de reference : {{{{DATE_DE_REFERENCE}}}}
- Marche, si l analyste a une idee : {{{{MARCHE_CIBLE}}}}
- Concurrents deja identifies, le cas echeant : {{{{CONCURRENTS_CONNUS}}}}
- Contexte complementaire, le cas echeant : {{{{INFORMATIONS_INTERNES}}}}

Les indications de l analyste sont des pistes, pas des consignes : **contredis
les si tes sources le justifient**, en expliquant pourquoi.

LES QUATRE QUESTIONS

**1 - Sur quel marche, et quelle position ?**

Definis d abord le marche pertinent - c est toi qui le delimites, et c est la
decision la plus lourde de l analyse : un perimetre trop etroit fabrique un
leader en excluant celui qui le menace. Dis ce que tu inclus et ce que tu
exclus.

Puis tranche : `leader`, `challenger`, `suiveur` ou `niche`. Appuie le verdict
sur une preuve verifiable - part de marche, rang, chiffre d affaires compare -
et non sur la communication de l entreprise.

**2 - Depuis quand ?**

L annee ou l entreprise a **atteint** cette position. « Leader » sans « depuis
quand » ne dit pas si la position est etablie ou fraiche, et c est toute la
difference entre une rente et un accident.

Si l entreprise **a perdu** une position de leader, donne l annee de la perte
dans `perdue_en` et mets le verdict a ce qu elle est aujourd hui. Une position
perdue l an dernier et une position perdue il y a quinze ans ne se lisent pas
pareil.

Evalue enfin la **durabilite** de la position - `solid`, `watch`, `eroding`,
`none` - et dis **ce qui la protege** parmi : brand, patent, switching, network,
cost, scale, regulatory, distribution. Ce qui ne rentre dans aucune de ces cases
est en general une qualite operationnelle, pas une barriere.

**3 - Qui sont les concurrents, et en quoi chacun est une menace ?**

Cite les nommement - c est la partie la plus utile du dossier. Pour chacun :
son pays, s il attaque `directe`ment le coeur de marche ou `indirecte`ment par
un substitut, son niveau de danger (`eleve`, `moyen`, `faible`) et surtout
**pourquoi il est dangereux**, en une ou deux phrases concretes.

Un concurrent nomme sans raison ne se relit pas : dans six mois on ne saura plus
pourquoi il figurait la. Et un concurrent recense puis juge peu dangereux est
une information rassurante - ne l omets pas pour autant.

Cherche explicitement **hors de la zone geographique fournie**. Les menaces
reelles viennent presque toujours de l exterieur : un concurrent americain,
chinois, ou non cote. Un dossier ou tous les concurrents sont europeens est
suspect.

**4 - Quelles autres menaces, et en quoi c est dangereux ?**

Celles qui ne portent pas un nom d entreprise : reglementaire, technologique,
commerciale, financiere. Meme exigence - un niveau de danger, et une explication
concrete du mecanisme par lequel la menace ferait mal.

Pour chaque menace, des deux categories, indique un **signal a surveiller** :
l evenement observable qui dirait que la menace se realise.

CE QU ON NE TE DEMANDE PAS

Pas de note, pas de score, pas de pourcentage de confiance : ils se calculent
ailleurs a partir de tes verdicts. Pas de scenarios prospectifs, pas de
valorisation, pas d analyse financiere, pas de recommandation d achat ou de
vente. Pas d analyse fonctionnelle ni de besoins clients. Si tu as envie
d ajouter une section, c est qu elle n a pas sa place ici.

{_SOURCES}

{_STATUTS}

{_LANGUE}

FORMAT DE SORTIE

Reponds par **un seul objet JSON**, sans texte avant ni apres, respectant
exactement cette structure. `null` partout ou tu ne sais pas.

{{
  "version": 2,
  "entreprise": "{{{{ENTREPRISE_ANALYSEE}}}}",
  "date_reference": "{{{{DATE_DE_REFERENCE}}}}",
  "marche": "le perimetre que tu as retenu, inclusions et exclusions",
  "position": {{
    "verdict": "leader | challenger | suiveur | niche",
    "depuis": 2018,
    "perdue_en": null,
    "preuve": "part de marche, rang, ou chiffre compare, avec sa source",
    "statut": "FAIT_VERIFIE | DECLARATION_ENTREPRISE | ESTIMATION | INTERPRETATION"
  }},
  "durabilite": {{
    "verdict": "solid | watch | eroding | none",
    "sources_de_rente": ["brand", "patent", "switching", "network", "cost",
                         "scale", "regulatory", "distribution"],
    "justification": "ce qui protege la position, et ce qui l entame"
  }},
  "concurrents": [
    {{
      "nom": "raison sociale",
      "pays": "code ou nom du pays",
      "type": "directe | indirecte",
      "danger": "eleve | moyen | faible",
      "pourquoi_dangereux": "le mecanisme concret, une a deux phrases",
      "signal_a_surveiller": "l evenement observable qui dirait que ca arrive",
      "statut": "FAIT_VERIFIE | ESTIMATION | INTERPRETATION"
    }}
  ],
  "autres_menaces": [
    {{
      "nom": "intitule court",
      "nature": "reglementaire | technologique | commerciale | financiere | autre",
      "type": "directe | indirecte",
      "danger": "eleve | moyen | faible",
      "pourquoi_dangereux": "le mecanisme concret",
      "signal_a_surveiller": "l evenement observable",
      "statut": "FAIT_VERIFIE | ESTIMATION | INTERPRETATION"
    }}
  ],
  "resume": "un paragraphe : la position, son anciennete, ce qui la protege, ce qui la menace",
  "sources": [{{"titre": null, "url": null, "date": null}}]
}}"""


PROMPTS = {
    "position": ("Position concurrentielle", POSITION,
                 "Un seul prompt, une seule reponse JSON. Qui est leader, "
                 "depuis quand, qui le menace et en quoi c est dangereux. "
                 "**Aucune note n est demandee au modele** : le score se "
                 "calcule ici, a partir des verdicts."),
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
