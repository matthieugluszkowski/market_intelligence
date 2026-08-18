"""Configuration centralisee, lue depuis .env.

Aucun secret en dur dans le code : tout passe par l'environnement (L0).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"Variable d'environnement manquante : {name}. "
            f"Copier .env.example en .env et la renseigner."
        )
    return value


@dataclass(frozen=True)
class Settings:
    # --- base ---
    database_url: str          # pooler transaction (pgbouncer) : requetes applicatives
    direct_url: str            # pooler session : DDL, migrations, transactions longues
    supabase_project_ref: str

    # --- stockage froid ---
    cold_storage_path: Path

    # --- ingestion ---
    stooq_rate_limit_sec: float
    yfinance_rate_limit_sec: float
    http_timeout_sec: int
    http_max_retries: int
    amf_api_base: str
    ecb_api_base: str
    esef_api_base: str

    # --- moteur analytique ---
    method_version: int
    dilution_threshold_12m: float
    jump_alert_threshold: float

    # --- exploitation ---
    log_level: str


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        database_url=_require("DATABASE_URL"),
        direct_url=_require("DIRECT_URL"),
        supabase_project_ref=os.getenv("SUPABASE_PROJECT_REF", ""),
        cold_storage_path=Path(
            os.getenv("COLD_STORAGE_PATH", PROJECT_ROOT / "data" / "parquet")
        ),
        stooq_rate_limit_sec=float(os.getenv("STOOQ_RATE_LIMIT_SEC", "1.0")),
        yfinance_rate_limit_sec=float(os.getenv("YFINANCE_RATE_LIMIT_SEC", "2.0")),
        http_timeout_sec=int(os.getenv("HTTP_TIMEOUT_SEC", "30")),
        http_max_retries=int(os.getenv("HTTP_MAX_RETRIES", "3")),
        amf_api_base=os.getenv("AMF_API_BASE", "https://api.info-financiere.fr/api/v1"),
        ecb_api_base=os.getenv("ECB_API_BASE", "https://data-api.ecb.europa.eu/service/data"),
        esef_api_base=os.getenv("ESEF_API_BASE", "https://filings.xbrl.org"),
        method_version=int(os.getenv("METHOD_VERSION", "1")),
        dilution_threshold_12m=float(os.getenv("DILUTION_THRESHOLD_12M", "0.50")),
        jump_alert_threshold=float(os.getenv("JUMP_ALERT_THRESHOLD", "0.25")),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
    )
