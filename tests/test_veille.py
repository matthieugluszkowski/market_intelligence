"""Veille externe : consensus, notations, depeches (lot L10).

Ce que ces tests protegent
---------------------------
Deux choses, et la seconde compte plus que la premiere.

**Que la lecture des pages rende les bons chiffres.** Les fixtures sont des
extraits reels des deux sources, collectes le 2026-08-25 sur EssilorLuxottica.
Un parseur d'HTML se casse le jour ou la source change sa mise en page - et il
se casse **silencieusement**, en rendant `None` la ou il rendait 23. Les valeurs
sont donc verifiees une par une : si un test tombe ici, la page a change et le
selecteur est a reprendre, ce qui est exactement l'information voulue.

**Qu'aucun calcul ne les regarde.** Un consensus d'analystes est
structurellement optimiste et revise apres coup. Le brancher sur le score
reviendrait a acheter ce que tout le monde recommande deja, c'est-a-dire
l'inverse d'un screener de decote. Le dernier test de ce fichier verifie que
personne n'a cede a la tentation - c'est une regle d'architecture, elle ne se
defend pas dans une revue de code six mois plus tard.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from market_intelligence.collectors import boursier, extraction, zonebourse  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(nom: str) -> str:
    return (FIXTURES / nom).read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def consensus() -> dict:
    return zonebourse.parse_consensus(_fixture("zonebourse_consensus.html"), "url")


@pytest.fixture(scope="module")
def notations() -> dict:
    return zonebourse.parse_notations(_fixture("zonebourse_notations.html"), "url")


@pytest.fixture(scope="module")
def depeches() -> list:
    return boursier.parse_depeches(_fixture("boursier_depeches.html"))


@pytest.fixture(scope="module")
def article() -> dict:
    return boursier.parse_article(_fixture("boursier_article.html"))


# --------------------------------------------------------------------------- #
# Consensus
# --------------------------------------------------------------------------- #
def test_le_consensus_rend_les_chiffres_publies(consensus):
    """Les six valeurs qui s'affichent sur la fiche, verifiees une par une."""
    assert consensus["recommandation"] == "ACHETER"
    assert consensus["nombre_d_analystes"] == 23
    assert consensus["cours_de_cloture"] == pytest.approx(161.70)
    assert consensus["objectif_moyen"] == pytest.approx(243.30)
    assert consensus["ecart_moyen_pct"] == pytest.approx(50.47)
    assert consensus["devise"] == "EUR"


def test_la_fourchette_des_objectifs_encadre_la_moyenne(consensus):
    """Un haut sous le bas signalerait deux lignes appariees a l'envers - la
    panne la plus vicieuse d'un decoupage par expression reguliere."""
    assert consensus["objectif_bas"] <= consensus["objectif_moyen"] <= consensus["objectif_haut"]
    assert consensus["ecart_bas_pct"] <= consensus["ecart_moyen_pct"] <= consensus["ecart_haut_pct"]


def test_la_barre_du_consensus_vient_de_la_note_publiee(consensus):
    """« ACHETER » est un intervalle, pas un point : sans la note chiffree, la
    barre placerait au milieu de l'intervalle un titre qui en touche le bord."""
    assert consensus["note"] == pytest.approx(8.4)
    assert consensus["note_max"] == pytest.approx(10.0)
    assert consensus["note_pct"] == pytest.approx(84.0)


def test_sans_note_la_barre_se_replie_sur_le_libelle():
    """Repere grossier, et assume : mieux vaut un curseur approximatif qu'une
    barre vide a cote d'une recommandation affichee."""
    milieu = zonebourse._en_pourcentage(None, None, "CONSERVER")
    achat = zonebourse._en_pourcentage(None, None, "ACHETER")
    assert 40 < milieu < 60
    assert achat > milieu
    assert zonebourse._en_pourcentage(None, None, "libelle inconnu") is None


def test_une_page_sans_encart_de_consensus_rend_rien():
    """`None`, jamais un dictionnaire vide de valeurs : un encart absent doit se
    voir a l'ecran comme absent, pas se confondre avec un consensus neutre."""
    assert zonebourse.parse_consensus("<html><body>rien</body></html>") is None
    assert zonebourse.parse_consensus("") is None


# --------------------------------------------------------------------------- #
# Notations
# --------------------------------------------------------------------------- #
def test_les_notations_rendent_un_rang_par_critere(notations):
    notes = {n["libelle"]: n["note_pct"] for n in notations["notes"]}
    assert notes["Trader"] == pytest.approx(24.0)
    assert notes["Investisseur"] == pytest.approx(59.0)
    assert notes["Globale"] == pytest.approx(27.0)
    assert all(n["note_pct"] is None or 0 <= n["note_pct"] <= 100
               for n in notations["notes"])


def test_une_notation_en_lettres_reste_une_lettre(notations):
    """Le rang ESG est « AA ». Le convertir en pourcentage inventerait une
    precision que la source ne publie pas."""
    esg = [n for n in notations["notes"] if n["libelle"] == "ESG MSCI"]
    assert esg and esg[0]["mention"] == "AA" and esg[0]["note_pct"] is None


def test_le_constat_est_la_premiere_phrase_de_la_source(notations):
    assert notations["constat"].startswith(
        "La société présente une situation fondamentale dégradée")


def test_forces_et_faiblesses_ne_se_melangent_pas(notations):
    """Trois forces et sept faiblesses dans la fixture : les intervertir
    retournerait le sens du bloc sans rien casser de visible."""
    assert len(notations["points_forts"]) == 3
    assert len(notations["points_faibles"]) == 7
    assert any("croissance des bénéfices" in t for t in notations["points_forts"])
    assert any("valorisation du groupe" in t for t in notations["points_faibles"])


# --------------------------------------------------------------------------- #
# Depeches
# --------------------------------------------------------------------------- #
def test_les_depeches_sortent_titrees_et_datees(depeches):
    assert len(depeches) >= 15
    assert all(d.titre and d.url.startswith("https://www.boursier.com")
               for d in depeches)
    tete = depeches[1]
    assert tete.titre == "EssilorLuxottica : Leonardo Maria Del Vecchio quitte le navire"
    assert tete.publie_le == "2026-08-25T10:39:01"


def test_les_depeches_sont_du_plus_recent_au_plus_ancien(depeches):
    """La source les sert dans cet ordre ; on ne re-trie pas, on le verifie -
    un jour ou elle changera d'avis, l'ecran afficherait un mois de retard en
    tete de liste sans que rien ne le signale."""
    dates = [d.publie_le for d in depeches if d.publie_le]
    assert dates == sorted(dates, reverse=True)


def test_le_titre_perd_le_compteur_de_commentaires(depeches):
    """Le compteur est dans le meme lien que le titre : « ... dégrade 1 »."""
    assert not any(re.search(r"\s\d+$", d.titre) for d in depeches)


def test_l_article_rend_son_texte_et_sa_signature(article):
    assert article["titre"].startswith("EssilorLuxottica")
    assert article["auteur"] == "Jean-Baptiste André"
    assert article["publie_le"].startswith("2026-08-25T10:39")
    assert len(article["paragraphes"]) >= 4
    assert article["texte"].startswith("(Boursier.com)")


def test_l_article_ne_ramasse_ni_partage_ni_signature(article):
    """La barre de partage et le pave « Par X, publie le Y » sont dans le corps
    de l'article : sans filtre, ils arrivent en tete du texte deroule."""
    assert not any(p.startswith(("Par ", "Publié le")) for p in article["paragraphes"])
    assert "Partager" not in article["texte"]


def test_les_balises_en_ligne_ne_coupent_pas_les_mots(article):
    """La source met le nom de la societe en gras au milieu des phrases. Retirer
    ces balises en laissant une espace produit « d' EssilorLuxottica . »."""
    assert "d'EssilorLuxottica" in article["texte"]
    assert " ." not in article["texte"]


def test_une_page_vide_ne_fait_pas_tomber_la_collecte():
    assert boursier.parse_depeches("") == []
    assert boursier.parse_article("<html></html>") == {}


# --------------------------------------------------------------------------- #
# Adresses des sources
# --------------------------------------------------------------------------- #
def test_l_adresse_boursier_se_deduit_de_l_isin():
    """Aucune table de correspondance a tenir : la source resout par ISIN et
    corrige le slug elle-meme."""
    url = boursier.url_actualites("FR0000121667")
    assert url.endswith("/x-FR0000121667,FR.html")
    assert url.startswith("https://www.boursier.com/actions/actualites/news/")


def test_l_adresse_zonebourse_se_ramene_a_sa_racine():
    """L'utilisateur colle l'onglet ou il se trouve ; on ajoute le notre."""
    racine = "https://www.zonebourse.com/cours/action/ESSILORLUXOTTICA-4641/"
    for collee in (racine, racine + "graphiques/", racine + "societe/?x=1",
                   racine + "notations/#ancre"):
        assert zonebourse.normalise_url(collee) == racine
    assert zonebourse.url_onglet(racine + "societe/", "consensus/") == \
        racine + "consensus/"


# --------------------------------------------------------------------------- #
# Extraction
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("brut, attendu", [
    ("243,30", 243.30), ("+50,47 %", 50.47), ("-12,5", -12.5),
    ("1 234,50", 1234.50), ("23", 23.0), ("—", None), ("", None), (None, None),
])
def test_les_nombres_a_la_francaise_se_lisent(brut, attendu):
    valeur = extraction.nombre(brut)
    if attendu is None:
        assert valeur is None
    else:
        assert valeur == pytest.approx(attendu)


def test_la_devise_se_lit_collee_au_montant():
    """La source ferme une balise entre le montant et la devise, et les balises
    en ligne sont retirees sans rien mettre a la place."""
    assert extraction.devise("161,70EUR") == "EUR"
    assert extraction.devise("161,70 EUR") == "EUR"
    assert extraction.devise("ACHETER") is None, "trois majuscules dans un mot"


def test_les_libelles_se_comparent_sans_accent_ni_ponctuation():
    assert extraction.cle("Nombre d'Analystes") == extraction.cle("nombre d analystes")
    assert extraction.cle("Qualité") == "qualite"


# --------------------------------------------------------------------------- #
# La regle d'architecture
# --------------------------------------------------------------------------- #
def test_aucun_calcul_ne_lit_la_veille():
    """Le consensus n'entre dans **aucun** score, et c'est structurel.

    Il est optimiste par construction et revise apres coup : une methode qui
    l'integrerait acheterait ce que tout le monde recommande deja. Seuls le
    collecteur, son job et le dashboard ont le droit de connaitre ces tables -
    le moteur analytique, jamais.
    """
    autorises = {
        ROOT / "src" / "market_intelligence" / "jobs" / "ingest_veille.py",
        ROOT / "src" / "market_intelligence" / "collectors" / "zonebourse.py",
        ROOT / "src" / "market_intelligence" / "collectors" / "boursier.py",
    }
    fautifs = []
    for chemin in (ROOT / "src").rglob("*.py"):
        if chemin in autorises:
            continue
        texte = chemin.read_text(encoding="utf-8")
        if "external_briefs" in texte or "external_sources" in texte:
            fautifs.append(str(chemin.relative_to(ROOT)))
    assert not fautifs, (
        f"la veille est lue hors du collecteur : {fautifs}. Un consensus "
        f"d'analystes ne doit alimenter aucun calcul.")


def test_le_moteur_analytique_ignore_les_deux_sources():
    for chemin in (ROOT / "src" / "market_intelligence" / "analytics").rglob("*.py"):
        texte = chemin.read_text(encoding="utf-8").lower()
        assert "zonebourse" not in texte and "boursier" not in texte
