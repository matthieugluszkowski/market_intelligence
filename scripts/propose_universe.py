"""Propose des candidats pour le referentiel de l'univers (lot L1).

**Ce script ne charge rien.** Il ecrit des lignes candidates dans
`db/seeds/universe.csv` ; `verify_universe.py` reste le seul gardien, et
`load_universe.py` le seul a ecrire en base. La chaine des trois controles L1
n'est pas contournee, elle est alimentee.

Le piege que ce script doit eviter
-----------------------------------
Yahoo raisonne en **place de cotation**, jamais en pays de la societe. Une
requete sur la region `de` rend 9 064 lignes ou NVIDIA, Apple et Alphabet
occupent les premieres places : ce sont des cotations etrangeres a Francfort.
Charger ca remplirait un univers « zone euro PEA » de valeurs americaines.
Trois filtres successifs l'evitent :

1. **place principale** - Francfort, Stuttgart, Munich et Dusseldorf sont
   ecartes au profit de XETRA seul, ce qui supprime au passage les triplons
   (`NVD.DE`, `NVD.F`, `NVDG.F` designent la meme action) ;
2. **devise de cotation ET devise de publication en EUR** - Zebra Technologies
   cote en euros a XETRA mais publie ses comptes en dollars ;
3. **pays du siege**, lu dans `Ticker.info`, confronte a la liste UE/EEE qui
   fait l'eligibilite PEA. C'est le seul controle qui tranche vraiment, et il
   coute une requete par candidat.

L'ISIN reste **vide** pour ces lignes, et c'est delibere : `Ticker.isin` de
yfinance fait une recherche par nom et rend le premier homonyme mondial - il
donne un ISIN canadien pour LVMH, argentin pour ASML, chilien pour Enel. Un
ISIN faux passe la cle de controle Luhn et associerait pour toujours une courbe
a la mauvaise societe. Un ISIN absent se voit ; un ISIN faux, jamais.

Usage :
    python scripts/propose_universe.py                 # complete jusqu'a 600 titres
    python scripts/propose_universe.py --total 300     # cible totale differente
    python scripts/propose_universe.py --dry-run       # n'ecrit pas le CSV
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
import unicodedata
from datetime import date
from pathlib import Path

import yfinance as yf
from yfinance import EquityQuery

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from market_intelligence.intelligence.schema import normalise_nom  # noqa: E402

UNIVERSE_CSV = ROOT / "db" / "seeds" / "universe.csv"
COLONNES = ["internal_code", "isin", "name", "exchange_code", "currency",
            "sector_code", "country_iso2", "yfinance_symbol", "stooq_symbol", "notes"]

CAP_MINIMALE = 300_000_000
PAUSE_SCREENER = 1.5
PAUSE_INFO = 0.5

# Place -> pays de la place. Sert a preferer la cotation du pays du siege quand
# une societe est cotee sur plusieurs places : Vienne rend 449 candidats en
# euros, dont une majorite de societes allemandes ou italiennes qui y sont
# secondairement cotees. Enregistrer Siemens sur la place viennoise donnerait
# une serie de cours etroite et trouee pour une valeur qui cote a XETRA.
PAYS_DE_LA_PLACE = {
    "XPAR": "FR", "XETR": "DE", "XAMS": "NL", "XMIL": "IT", "XMAD": "ES",
    "XBRU": "BE", "XLIS": "PT", "XDUB": "IE", "XHEL": "FI", "XWBO": "AT",
}

# Code de place Yahoo -> (libelle rendu par le screener, code MIC de la table
# exchanges, nombre de pages a parcourir).
#
# **Interroger la place, jamais la region.** La region `de` couvre six places
# allemandes a la fois - Francfort, Stuttgart, Munich, Dusseldorf, Berlin,
# XETRA - soit 9 064 lignes dont le haut du classement est occupe par les
# cotations americaines, chacune presente deux ou trois fois. Descendre dix
# pages dans ce melange ne remontait que 115 societes allemandes ; interroger
# `GER` directement en rend 289 pour trois pages. Mesure du 2026-08-21.
PLACES: dict[str, tuple[str, str, int]] = {
    "PAR": ("Paris", "XPAR", 2),
    "GER": ("XETRA", "XETR", 3),
    "AMS": ("Amsterdam", "XAMS", 1),
    "MIL": ("Milan", "XMIL", 4),
    "MCE": ("MCE", "XMAD", 1),
    "BRU": ("Brussels", "XBRU", 1),
    "LIS": ("Lisbon", "XLIS", 1),
    "ISE": ("Irish", "XDUB", 1),
    "HEL": ("Helsinki", "XHEL", 1),
    "VIE": ("Vienna", "XWBO", 4),
}

# Eligibilite PEA : Union europeenne et Espace economique europeen.
EEE = {
    "Austria": "AT", "Belgium": "BE", "Bulgaria": "BG", "Croatia": "HR",
    "Cyprus": "CY", "Czech Republic": "CZ", "Czechia": "CZ", "Denmark": "DK",
    "Estonia": "EE", "Finland": "FI", "France": "FR", "Germany": "DE",
    "Greece": "GR", "Hungary": "HU", "Iceland": "IS", "Ireland": "IE",
    "Italy": "IT", "Latvia": "LV", "Liechtenstein": "LI", "Lithuania": "LT",
    "Luxembourg": "LU", "Malta": "MT", "Netherlands": "NL", "Norway": "NO",
    "Poland": "PL", "Portugal": "PT", "Romania": "RO", "Slovakia": "SK",
    "Slovenia": "SI", "Spain": "ES", "Sweden": "SE",
}

# Taxonomie yfinance -> codes de la table sectors (11 secteurs).
SECTEURS = {
    "Technology": "10", "Communication Services": "15", "Healthcare": "20",
    "Financial Services": "30", "Real Estate": "35", "Consumer Cyclical": "40",
    "Consumer Defensive": "45", "Industrials": "50", "Basic Materials": "55",
    "Energy": "60", "Utilities": "65",
}


def ascii_plat(texte: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texte or "")
                   if not unicodedata.combining(c))


# Formes juridiques que la liste du projet ne connait pas encore, et que les
# places europeennes ecrivent chacune a leur facon. Sans elles, « Siemens » et
# « Siemens Aktiengesellschaft » sont deux societes, « KBC Groep » et « KBC
# Group NV » aussi - et le referentiel se remplit de doublons que rien ne
# signale.
_SUFFIXES_EN_PLUS = {
    "aktiengesellschaft", "abp", "groep", "grupo", "gruppo", "societe",
    "anonyme", "sca", "saa", "ord", "shs", "reg", "npv", "sp", "aps",
}


def cle_societe(nom: str) -> str:
    """Cle de deduplication d'une societe, toutes places confondues.

    Les jetons d'une lettre disparaissent : « S.A. » et « S.p.A. » se decoupent
    en lettres isolees, qui feraient diverger deux ecritures du meme nom.
    """
    base = normalise_nom(ascii_plat(nom)).split()
    utiles = [m for m in base if len(m) > 1 and m not in _SUFFIXES_EN_PLUS]
    return " ".join(utiles or base)


def sortie(texte: str) -> None:
    """Impression tolerante : la console Windows n'est pas en UTF-8."""
    print(texte.encode("ascii", "replace").decode("ascii"))


# --------------------------------------------------------------------------- #
# 1. Candidats, par place et par capitalisation decroissante
# --------------------------------------------------------------------------- #

def candidats_d_une_place(place: str, libelle: str, mic: str, pages: int) -> list[dict]:
    retenus: list[dict] = []
    vus: set[str] = set()
    for page in range(pages):
        requete = EquityQuery("and", [
            EquityQuery("eq", ["exchange", place]),
            EquityQuery("gt", ["intradaymarketcap", CAP_MINIMALE]),
        ])
        try:
            reponse = yf.screen(requete, offset=page * 250, size=250,
                                sortField="intradaymarketcap", sortAsc=False)
        except Exception as exc:  # noqa: BLE001 - une place ratee n'arrete pas le reste
            sortie(f"  {place} page {page + 1} : echec {type(exc).__name__} {exc}")
            break

        lignes = reponse.get("quotes", [])
        if not lignes:
            break

        for ligne in lignes:
            symbole = ligne.get("symbol")
            if not symbole or symbole in vus:
                continue
            vus.add(symbole)
            if ligne.get("quoteType") != "EQUITY":
                continue
            if ligne.get("fullExchangeName") != libelle:
                continue
            # Devise de cotation et devise de publication : les deux doivent
            # etre l'euro. La seconde elimine les cotations etrangeres.
            if ligne.get("currency") != "EUR" or ligne.get("financialCurrency") != "EUR":
                continue
            retenus.append({
                "symbole": symbole,
                "nom": ligne.get("longName") or ligne.get("shortName") or "",
                "capitalisation": ligne.get("marketCap") or 0,
                "exchange_code": mic,
            })
        if len(lignes) < 250:
            break
        time.sleep(PAUSE_SCREENER)
    return retenus


# --------------------------------------------------------------------------- #
# 2. Confirmation du pays du siege, un candidat a la fois
# --------------------------------------------------------------------------- #

def confirme(candidat: dict) -> dict | None:
    """Rend le candidat enrichi du pays et du secteur, ou None s'il est hors PEA."""
    try:
        info = yf.Ticker(candidat["symbole"]).info
    except Exception:  # noqa: BLE001 - un titre muet est un titre qu'on n'ajoute pas
        return None
    pays = EEE.get((info.get("country") or "").strip())
    if not pays:
        return None
    nom = info.get("longName") or candidat["nom"]
    if not nom:
        return None
    return {**candidat, "nom": nom, "country_iso2": pays,
            "sector_code": SECTEURS.get(info.get("sector") or "")}


# --------------------------------------------------------------------------- #
# 3. Code interne, unique et lisible
# --------------------------------------------------------------------------- #

# Uniquement des formes juridiques : « societe », « banco » ou « group » restent,
# parce qu'ils portent le nom. Sans eux, Societe Generale devient GENERALE.
FORMES_JURIDIQUES = {"sa", "se", "nv", "bv", "ag", "plc", "spa", "oyj", "abp",
                     "ab", "as", "asa", "kgaa", "gmbh", "sas", "sarl", "ltd",
                     "limited", "aktiengesellschaft", "anonyme", "inc", "corp"}
LONGUEUR_CODE = 16


def code_interne(nom: str, pays: str, deja_pris: set[str]) -> str:
    """Code interne lisible et unique : EQ:PAYS:RACINE.

    La ponctuation est retiree **a l'interieur** des mots, pas utilisee pour les
    ecarter : « E.ON SE » donnait EON, ecarte comme non alphanumerique, puis SE
    comme seul mot restant - d'ou un code EQ:DE:SE. Meme cause pour
    « CaixaBank, S.A. », qui tombait sur le code de repli.
    """
    mots = ["".join(c for c in mot if c.isalnum())
            for mot in ascii_plat(nom).upper().replace("-", " ").split()]
    mots = [m for m in mots if m]
    if not mots:
        mots = ["TITRE"]
    utiles = [m for m in mots if m.lower() not in FORMES_JURIDIQUES] or mots
    # Les initiales et titres ne nomment personne : « Dr. Ing. h.c. F. Porsche »
    # donnait DRINGHC. Aucun sigle utile ne fait moins de trois lettres (RWE,
    # SAP, EON, ASM), donc le seuil ne coute rien.
    parlants = [m for m in utiles if len(m) > 2] or utiles
    racine = "".join(parlants[:3])[:LONGUEUR_CODE] or "TITRE"

    code = f"EQ:{pays}:{racine}"
    suffixe = 2
    while code in deja_pris:
        code = f"EQ:{pays}:{racine}{suffixe}"
        suffixe += 1
    deja_pris.add(code)
    return code


# --------------------------------------------------------------------------- #
# 4. Fusion avec l'existant
# --------------------------------------------------------------------------- #

def lit_existant() -> list[dict]:
    fichier = UNIVERSE_CSV
    if not fichier.exists():
        fichier = UNIVERSE_CSV.with_name("universe_50.csv")
    if not fichier.exists():
        return []
    with fichier.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--total", type=int, default=600,
                        help="nombre total de titres vise dans le CSV (defaut 600)")
    parser.add_argument("--dry-run", action="store_true", help="n'ecrit pas le CSV")
    args = parser.parse_args()

    existant = lit_existant()
    symboles_pris = {r["yfinance_symbol"] for r in existant if r.get("yfinance_symbol")}
    cles_prises = {cle_societe(r["name"]) for r in existant if r.get("name")}
    codes_pris = {r["internal_code"] for r in existant if r.get("internal_code")}
    a_ajouter = max(0, args.total - len(existant))

    sortie(f"{len(existant)} titres deja au referentiel, cible {args.total} "
           f"-> {a_ajouter} a proposer\n")
    if not a_ajouter:
        sortie("Rien a faire.")
        return 0

    candidats: list[dict] = []
    for place, (libelle, mic, pages) in PLACES.items():
        trouves = candidats_d_une_place(place, libelle, mic, pages)
        candidats.extend(trouves)
        sortie(f"  {place} ({libelle:<10}) : {len(trouves):>4} candidats en euros")
        time.sleep(PAUSE_SCREENER)

    candidats.sort(key=lambda c: c["capitalisation"], reverse=True)

    # Une societe, pas une cotation : les multi-cotations sont regroupees avant
    # tout appel reseau, ce qui divise d'autant le nombre de requetes.
    groupes: dict[str, list[dict]] = {}
    for candidat in candidats:
        cle = cle_societe(candidat["nom"])
        if cle:
            groupes.setdefault(cle, []).append(candidat)
    ordonnes = sorted(groupes.items(),
                      key=lambda kv: max(c["capitalisation"] for c in kv[1]),
                      reverse=True)
    sortie(f"\n{len(candidats)} cotations, {len(ordonnes)} societes distinctes. "
           f"Confirmation du pays du siege :\n")

    nouvelles: list[dict] = []
    ecartes = {"hors_eee": 0, "doublon": 0, "cotation_secondaire": 0}
    for cle, cotations in ordonnes:
        if len(nouvelles) >= a_ajouter:
            break
        if cle in cles_prises or any(c["symbole"] in symboles_pris for c in cotations):
            ecartes["doublon"] += 1
            continue

        confirme_ = confirme(cotations[0])
        time.sleep(PAUSE_INFO)
        if confirme_ is None:
            ecartes["hors_eee"] += 1
            continue

        pays = confirme_["country_iso2"]
        maison = next(
            (c for c in cotations if PAYS_DE_LA_PLACE.get(c["exchange_code"]) == pays),
            None,
        )
        if maison is None and pays in PAYS_DE_LA_PLACE.values():
            # La place du siege est couverte, mais cette societe n'y a pas ete
            # trouvee : ce qu'on tient est une cotation secondaire. Une ligne
            # viennoise de valeur allemande cote peu, cote mal, et donnerait une
            # serie trouee la ou la place principale en donne une propre.
            ecartes["cotation_secondaire"] += 1
            continue
        candidat = maison or cotations[0]
        cles_prises.add(cle)
        cles_prises.add(cle_societe(confirme_["nom"]))
        symboles_pris.update(c["symbole"] for c in cotations)

        ligne = {
            "internal_code": code_interne(confirme_["nom"], confirme_["country_iso2"],
                                          codes_pris),
            "isin": "",
            "name": confirme_["nom"],
            "exchange_code": candidat["exchange_code"],
            "currency": "EUR",
            "sector_code": confirme_["sector_code"] or "",
            "country_iso2": confirme_["country_iso2"],
            "yfinance_symbol": candidat["symbole"],
            "stooq_symbol": "",
            "notes": f"candidat screener yahoo {date.today().isoformat()}",
        }
        nouvelles.append(ligne)
        if len(nouvelles) % 25 == 0:
            sortie(f"    {len(nouvelles):>4}/{a_ajouter} retenus "
                   f"(dernier : {ligne['internal_code']})")

    sortie(f"\n{len(nouvelles)} nouvelles lignes | {ecartes['hors_eee']} hors UE/EEE "
           f"ou muettes | {ecartes['doublon']} deja suivies | "
           f"{ecartes['cotation_secondaire']} cotations secondaires ecartees")

    if args.dry_run:
        sortie("--dry-run : rien ecrit.")
        return 0

    with UNIVERSE_CSV.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLONNES)
        writer.writeheader()
        for ligne in existant + nouvelles:
            writer.writerow({c: ligne.get(c, "") or "" for c in COLONNES})

    sortie(f"{UNIVERSE_CSV.name} : {len(existant) + len(nouvelles)} lignes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
