"""Resolution automatique et enregistrement des URLs Zonebourse et ISINs pour les actions de l'univers.

Ce script parcourt les actions (actions ordinaires et actions a dividende) :
1. Si l'ISIN est absent, le recupere via yfinance et met a jour `instruments.isin`.
2. Resout l'URL canonique Zonebourse (format https://www.zonebourse.com/cours/action/NOM-ID/)
   via mapping direct + cascade multi-moteurs (DDG Lite & Yahoo Search) et l'enregistre dans
   `external_sources` (source_code = 'zonebourse').

Usage :
    python scripts/resolve_zonebourse_urls.py --limit 50
    python scripts/resolve_zonebourse_urls.py --only EQ:FR:TTE,EQ:FR:SAN
    python scripts/resolve_zonebourse_urls.py
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
import time
import urllib.parse
from pathlib import Path

from curl_cffi import requests as c_requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from market_intelligence.db import connect_direct  # noqa: E402
from market_intelligence.jobs.ingest_veille import ECRIT_URL  # noqa: E402

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}

REGEX_ZB = re.compile(r"https?://(?:www\.)?zonebourse\.com/cours/action/([a-zA-Z0-9\-_]+-\d+)/")

# Table de correspondance directe pour les grandes valeurs francaises et europeennes (0ms de latence)
MAPPING_DIRECT = {
    "FR0000120271": "https://www.zonebourse.com/cours/action/TOTALENERGIES-SE-4717/",
    "FR0000120578": "https://www.zonebourse.com/cours/action/SANOFI-4698/",
    "FR0000120073": "https://www.zonebourse.com/cours/action/AIR-LIQUIDE-4605/",
    "FR0000120628": "https://www.zonebourse.com/cours/action/AXA-4615/",
    "FR0000131104": "https://www.zonebourse.com/cours/action/BNP-PARIBAS-4618/",
    "FR0000125486": "https://www.zonebourse.com/cours/action/VINCI-4725/",
    "FR0000121972": "https://www.zonebourse.com/cours/action/SCHNEIDER-ELECTRIC-SE-4699/",
    "FR0000120644": "https://www.zonebourse.com/cours/action/DANONE-4634/",
    "FR0000120321": "https://www.zonebourse.com/cours/action/L-OREAL-4666/",
    "FR0000120503": "https://www.zonebourse.com/cours/action/BOUYGUES-SA-4620/",
    "FR0000133308": "https://www.zonebourse.com/cours/action/ORANGE-4649/",
    "FR0010208488": "https://www.zonebourse.com/cours/action/ENGIE-4995/",
    "FR0010040865": "https://www.zonebourse.com/cours/action/GECINA-4651/",
    "FR0000064578": "https://www.zonebourse.com/cours/action/COVIVIO-5748/",
    "FR0000130452": "https://www.zonebourse.com/cours/action/EIFFAGE-S-A-4638/",
    "FR0013269123": "https://www.zonebourse.com/cours/action/RUBIS-37262425/",
    "FR0000033219": "https://www.zonebourse.com/cours/action/ALTAREA-5310/",
    "FR0000121667": "https://www.zonebourse.com/cours/action/ESSILORLUXOTTICA-4641/",
    "FR0000121014": "https://www.zonebourse.com/cours/action/LVMH-4669/",
    "FR0000052292": "https://www.zonebourse.com/cours/action/HERMES-INTERNATIONAL-4657/",
    "FR0000121485": "https://www.zonebourse.com/cours/action/KERING-4664/",
    "FR0000120685": "https://www.zonebourse.com/cours/action/KLEPIERRE-4665/",
    "FR0000051732": "https://www.zonebourse.com/cours/action/ATOS-SE-4611/",
    "FR0000121501": "https://www.zonebourse.com/cours/action/CASINO-GUICHARD-PERRACHO-4624/",
    "DE0007100000": "https://www.zonebourse.com/cours/action/MERCEDES-BENZ-GROUP-AG-436541/",
    "DE0005190003": "https://www.zonebourse.com/cours/action/BMW-AG-56358353/",
    "DE0008404005": "https://www.zonebourse.com/cours/action/ALLIANZ-SE-436843/",
    "DE0008430026": "https://www.zonebourse.com/cours/action/MUNICH-RE-436858/",
    "DE000A0Z2ZZ5": "https://www.zonebourse.com/cours/action/FREENET-AG-5587638/",
    "DE0007664039": "https://www.zonebourse.com/cours/action/VOLKSWAGEN-AG-436737/",
    "DE0005439004": "https://www.zonebourse.com/cours/action/CTS-EVENTIM-AG-CO-KGAA-435918/",
    "ES0144580Y14": "https://www.zonebourse.com/cours/action/IBERDROLA-S-A-355153/",
    "IT0003128367": "https://www.zonebourse.com/cours/action/ENEL-S-P-A-70935/",
    "NL0000388619": "https://www.zonebourse.com/cours/action/UNILEVER-PLC-4720/",
    "NL0010273215": "https://www.zonebourse.com/cours/action/ASML-HOLDING-N-V-4610/",
}


def cherche_url_zonebourse(session: c_requests.Session, nom: str, isin: str | None, symbole: str | None) -> str | None:
    """Cherche l'URL canonique de l'action sur Zonebourse avec repli multi-moteurs."""
    if isin and isin in MAPPING_DIRECT:
        return MAPPING_DIRECT[isin]

    requetes = []
    if isin:
        requetes.append(f"zonebourse {nom} {isin}")
    if symbole:
        requetes.append(f"zonebourse {nom} {symbole}")
    requetes.append(f"zonebourse cours action {nom}")

    for q in requetes:
        # 1. DDG Lite
        try:
            r = session.post(
                "https://lite.duckduckgo.com/lite/",
                data={"q": q},
                headers=HEADERS,
                timeout=4,
            )
            if r.status_code == 200:
                m = REGEX_ZB.findall(r.text)
                if m:
                    return f"https://www.zonebourse.com/cours/action/{m[0]}/"
        except Exception:  # noqa: BLE001
            pass

        # 2. Yahoo Search
        try:
            q_enc = urllib.parse.quote(q)
            r = session.get(
                f"https://fr.search.yahoo.com/search?p={q_enc}",
                headers=HEADERS,
                timeout=4,
            )
            if r.status_code == 200:
                m = REGEX_ZB.findall(r.text)
                if m:
                    return f"https://www.zonebourse.com/cours/action/{m[0]}/"
        except Exception:  # noqa: BLE001
            pass

        time.sleep(0.3)

    return None


def recupere_isin_yfinance(symbole: str) -> str | None:
    """Interroge yfinance pour obtenir l'ISIN si non renseigne."""
    import yfinance as yf

    try:
        tk = yf.Ticker(symbole)
        isin = tk.isin
        if isin and isin != "-" and len(isin) == 12:
            return isin
    except Exception as exc:  # noqa: BLE001
        logger.debug("isin yfinance %s : %s", symbole, exc)
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", help="codes internes separes par des virgules")
    parser.add_argument("--limit", type=int, default=0, help="nombre max de titres a traiter")
    parser.add_argument("--force", action="store_true", help="ecrase les URLs deja enregistrees")
    parser.add_argument("--delai", type=float, default=0.4, help="pause entre requetes")
    args = parser.parse_args()

    sql = """
    select i.id, i.internal_code, i.name, i.isin, s.symbol,
           (select url from external_sources where instrument_id = i.id and source_code = 'zonebourse') as url_existante
      from instruments i
      left join instrument_symbols s on s.instrument_id = i.id and s.is_primary
     where i.is_active
       and i.asset_class in ('equity', 'dividend_stock')
    """
    params = {}
    if args.only:
        codes = [c.strip() for c in args.only.split(",") if c.strip()]
        sql += " and i.internal_code = any(%(codes)s)"
        params["codes"] = codes

    sql += " order by (i.asset_class = 'dividend_stock') desc, (select count(*) from watchlist where instrument_id = i.id and removed_at is null) desc, i.internal_code"

    session = c_requests.Session(impersonate="chrome120")

    with connect_direct() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            lignes = cur.fetchall()

        if args.limit:
            lignes = lignes[: args.limit]

        print(f"{len(lignes)} action(s) a verifier\n", flush=True)
        nb_trouves = 0
        nb_deja = 0
        nb_isin_maj = 0

        for rang, (inst_id, code, nom, isin, symbole, url_existante) in enumerate(lignes, 1):
            if url_existante and not args.force:
                print(f"[{rang:>3}/{len(lignes)}] {code:<22} deja resolu : {url_existante}", flush=True)
                nb_deja += 1
                continue

            # Si pas d'ISIN, tenter de le trouver
            if not isin and symbole:
                isin_trouve = recupere_isin_yfinance(symbole)
                if isin_trouve:
                    with conn.cursor() as cur:
                        cur.execute(
                            "update instruments set isin = %(isin)s, updated_at = now() where id = %(id)s",
                            {"isin": isin_trouve, "id": inst_id},
                        )
                    conn.commit()
                    isin = isin_trouve
                    nb_isin_maj += 1
                    print(f"  -> ISIN mis a jour pour {code} : {isin}", flush=True)

            # Trouver l'URL Zonebourse
            url_zb = cherche_url_zonebourse(session, nom, isin, symbole)
            if url_zb:
                with conn.cursor() as cur:
                    cur.execute(
                        ECRIT_URL,
                        {"instrument_id": inst_id, "source": "zonebourse", "url": url_zb},
                    )
                conn.commit()
                nb_trouves += 1
                print(f"[{rang:>3}/{len(lignes)}] {code:<22} -> {url_zb}", flush=True)
            else:
                print(f"[{rang:>3}/{len(lignes)}] {code:<22} INTROUVABLE (isin={isin}, sym={symbole})", flush=True)

            time.sleep(args.delai)

    print(
        f"\nBilan : {nb_trouves} URL(s) resolue(s) et enregistree(s), "
        f"{nb_deja} deja presente(s), {nb_isin_maj} ISIN(s) mis a jour.",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
