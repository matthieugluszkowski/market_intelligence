"""Verifie le referentiel de l'univers avant chargement (lot L1).

Le piege du lot L1, explicite dans 05_roadmap-et-lot.md : *un mapping faux ne se
voit jamais - il produit simplement une belle courbe pour la mauvaise societe*.
D'ou trois controles independants, et le refus de charger ce qui n'a pas ete
verifie par un telechargement reel :

1. **Cle de controle ISIN** (Luhn mod 10) : attrape les fautes de frappe.
2. **Cotation reelle** : telechargement de l'historique hebdomadaire. Un symbole
   qui ne renvoie rien, ou moins de 15 ans, est signale.
3. **Coherence devise et raison sociale** : la devise annoncee par le provider
   doit correspondre au referentiel, et le nom rapporte doit ressembler au nom
   attendu. C'est ce controle qui attrape le cas Seb / SEB banque suedoise.

Usage :
    python scripts/verify_universe.py                 # verifie, ecrit le rapport
    python scripts/verify_universe.py --limit 5       # echantillon
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import time
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from market_intelligence.config import get_settings  # noqa: E402

UNIVERSE_CSV = ROOT / "db" / "seeds" / "universe_50.csv"
REPORT_CSV = ROOT / "db" / "seeds" / "universe_50_verification.csv"

MIN_YEARS = 15          # seuil du lot L2 : >= 15 ans d'historique hebdomadaire
MIN_NAME_RATIO = 0.55   # en dessous, le nom rapporte ne ressemble plus au nom attendu


# --------------------------------------------------------------------------- #
# 1. Cle de controle ISIN
# --------------------------------------------------------------------------- #
def isin_is_valid(isin: str) -> bool:
    """ISO 6166 : lettres converties en nombres, puis Luhn mod 10."""
    if not re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}[0-9]", isin or ""):
        return False
    digits = "".join(str(int(c, 36)) for c in isin)
    total, double = 0, True
    for char in reversed(digits[:-1]):
        value = int(char) * (2 if double else 1)
        total += value - 9 if value > 9 else value
        double = not double
    return (total + int(digits[-1])) % 10 == 0


# --------------------------------------------------------------------------- #
# 2 et 3. Cotation reelle, devise, raison sociale
# --------------------------------------------------------------------------- #
def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    # Umlauts : Yahoo renvoie "Munchener" apres depouillement des accents, la saisie
    # ASCII usuelle est "Muenchener". On rabat les deux formes sur la meme.
    text = text.replace("ue", "u").replace("oe", "o").replace("ae", "a").replace("ss", "s")
    text = re.sub(r"\b(sa|se|nv|ag|plc|sca|spa|group|groupe|holding|international|"
                  r"the|inc|company|co|kgaa|ab|as|oyj|gesellschaft|aktiengesellschaft|"
                  r"in|de|und|et)\b", " ", text)
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def name_similarity(expected: str, reported: str) -> float:
    a, b = _normalize(expected), _normalize(reported)
    if not a or not b:
        return 0.0
    # un nom court contenu dans l'autre suffit : "SEB" dans "SEB SA"
    if a in b or b in a:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


def probe(symbol: str, expected_name: str, expected_currency: str) -> dict:
    import yfinance as yf

    out = {
        "n_obs": 0, "first": "", "last": "", "years": 0.0, "last_close": "",
        "reported_currency": "", "reported_name": "", "name_ratio": 0.0, "error": "",
    }
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="max", interval="1wk", auto_adjust=False)
        if hist.empty:
            out["error"] = "aucune cotation"
            return out
        out["n_obs"] = len(hist)
        out["first"] = str(hist.index[0].date())
        out["last"] = str(hist.index[-1].date())
        out["years"] = round((hist.index[-1] - hist.index[0]).days / 365.25, 1)
        out["last_close"] = round(float(hist["Close"].iloc[-1]), 4)

        try:
            info = ticker.get_info()
        except Exception:  # noqa: BLE001 - metadonnees optionnelles, la cotation prime
            info = {}
        out["reported_currency"] = (info.get("currency") or "").upper()
        out["reported_name"] = info.get("longName") or info.get("shortName") or ""
        out["name_ratio"] = round(name_similarity(expected_name, out["reported_name"]), 2)
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


def verdict(row: dict, res: dict) -> tuple[str, str]:
    """Retourne (statut, raisons). Seul 'ok' autorise le chargement sans revue.

    Bloquant : ISIN invalide, aucune cotation, nom incoherent. Les trois signent
    un mapping faux, et un mapping faux ne doit jamais entrer en base.
    Avertissement : historique court ou devise divergente - la ligne est chargeable
    mais le lot L2 devra en tenir compte.
    """
    blocking, warnings = [], []

    if not isin_is_valid(row["isin"]):
        blocking.append("isin_checksum")

    if res["error"]:
        blocking.append("pas_de_cotation")
        return "rejete", "|".join(blocking)

    if res["reported_name"] and res["name_ratio"] < MIN_NAME_RATIO:
        blocking.append(f"nom_divergent({res['name_ratio']}:{res['reported_name'][:30]})")

    # Aucune grande capitalisation europeenne n'a douze jours d'historique. En
    # dessous d'un an, ce n'est pas une jeune societe, c'est un flux tronque chez
    # le provider - constate sur plusieurs valeurs de Madrid. Bloquant : charger
    # la ligne donnerait une regression sur trois points.
    if res["years"] < 1.0:
        blocking.append(f"historique_tronque_provider({res['n_obs']}pts)")
    elif res["years"] < MIN_YEARS:
        warnings.append(f"historique_{res['years']}a")

    reported_ccy = res["reported_currency"]
    # GBX/GBP : le LSE cote en pence, ce n'est pas une incoherence.
    if (reported_ccy and reported_ccy != row["currency"]
            and {reported_ccy, row["currency"]} != {"GBX", "GBP"}):
        warnings.append(f"devise_{reported_ccy}_vs_{row['currency']}")

    if blocking:
        return "rejete", "|".join(blocking + warnings)
    if warnings:
        return "avertissement", "|".join(warnings)
    return "ok", ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=0, help="ne verifier que les N premiers")
    args = parser.parse_args()

    settings = get_settings()
    rows = list(csv.DictReader(UNIVERSE_CSV.open(encoding="utf-8")))
    if args.limit:
        rows = rows[: args.limit]

    print(f"{len(rows)} instruments a verifier "
          f"(debit menage : {settings.yfinance_rate_limit_sec}s entre appels)\n")

    results = []
    for i, row in enumerate(rows, 1):
        res = probe(row["yfinance_symbol"], row["name"], row["currency"])
        status, reasons = verdict(row, res)
        flag = {"ok": " ", "avertissement": "!", "rejete": "X"}[status]
        print(
            f"{flag} {i:>3}/{len(rows)} {row['yfinance_symbol']:<10} {row['name'][:28]:<28} "
            f"{res['years']:>5}a n={res['n_obs']:<5} {str(res['last_close']):>10} "
            f"{res['reported_currency']:<4} {reasons}"
        )
        results.append({**row, **res, "status": status, "reasons": reasons})
        if i < len(rows):
            time.sleep(settings.yfinance_rate_limit_sec)

    with REPORT_CSV.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(results[0].keys()))
        writer.writeheader()
        writer.writerows(results)

    counts = {s: sum(1 for r in results if r["status"] == s) for s in ("ok", "avertissement", "rejete")}
    print(f"\nok={counts['ok']}  avertissement={counts['avertissement']}  rejete={counts['rejete']}")
    print(f"Rapport : {REPORT_CSV.relative_to(ROOT)}")

    isins = [r["isin"] for r in results if r["status"] != "rejete"]
    dupes = {i for i in isins if isins.count(i) > 1}
    if dupes:
        print(f"!!! DOUBLONS D'ISIN : {dupes}")
        return 1
    print("Zero doublon d'ISIN.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
