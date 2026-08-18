"""Acces base.

Deux connexions distinctes, et la distinction n'est pas cosmetique :

- `connect()`      -> pooler transaction (port 6543, pgbouncer). Pour les requetes
                      applicatives. Les instructions preparees cote serveur y sont
                      incompatibles, d'ou `prepare_threshold=None`.
- `connect_direct()`-> pooler session (port 5432). Obligatoire pour le DDL, les
                      migrations et toute transaction longue.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import psycopg

from .config import get_settings

logger = logging.getLogger(__name__)

# Parametres que Supabase met dans l'URL a destination de Prisma et que libpq
# rejette ("invalid URI query parameter"). On les retire au lieu de tronquer
# l'URL : le .env reste copiable tel quel depuis le dashboard Supabase.
_NON_LIBPQ_PARAMS = {"pgbouncer", "connection_limit", "pool_timeout", "schema"}


def _sanitize(url: str) -> str:
    parts = urlsplit(url)
    if not parts.query:
        return url
    kept = [(k, v) for k, v in parse_qsl(parts.query) if k not in _NON_LIBPQ_PARAMS]
    return urlunsplit(parts._replace(query=urlencode(kept)))


@contextmanager
def connect(autocommit: bool = False) -> Iterator[psycopg.Connection]:
    """Connexion applicative via le pooler transaction."""
    settings = get_settings()
    conn = psycopg.connect(
        _sanitize(settings.database_url),
        autocommit=autocommit,
        prepare_threshold=None,  # pgbouncer en mode transaction ne suit pas les prepared statements
    )
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def connect_direct(autocommit: bool = False) -> Iterator[psycopg.Connection]:
    """Connexion session : DDL, migrations, transactions longues."""
    settings = get_settings()
    conn = psycopg.connect(_sanitize(settings.direct_url), autocommit=autocommit)
    try:
        yield conn
    finally:
        conn.close()


def fetch_all(sql: str, params: tuple | None = None) -> list[tuple]:
    with connect() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def fetch_one(sql: str, params: tuple | None = None) -> tuple | None:
    with connect() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()
