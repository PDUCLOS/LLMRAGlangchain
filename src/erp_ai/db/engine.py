"""Construction du moteur SQL et gestion des sessions.

Deux cibles supportées par le même code :
  * SQL Server (mssql+pyodbc) — cible de référence, x86-64 / Windows / Linux
  * SQLite — dev rapide, tests unitaires, machine ARM64 sans conteneur

La création du moteur est volontairement tolérante : un `import pyodbc` absent
ne casse pas l'import du package, seulement l'usage du dialecte MSSQL.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.engine import Engine

from erp_ai.config import Settings, get_settings


def _ensure_sqlite_dir(url: str) -> None:
    """Crée le répertoire du fichier SQLite si nécessaire."""
    prefix = "sqlite:///"
    if not url.startswith(prefix):
        return
    raw = url[len(prefix) :]
    if not raw or raw == ":memory:":
        return
    path = Path(raw)
    if path.parent and str(path.parent) not in {"", "."}:
        path.parent.mkdir(parents=True, exist_ok=True)


def _resolve_sqlite_url(url: str) -> str:
    """Résout un chemin SQLite relatif par rapport à la racine du projet.

    Évite que la base se crée dans le répertoire courant de l'appelant.
    """
    prefix = "sqlite:///"
    if not url.startswith(prefix):
        return url
    raw = url[len(prefix) :]
    if not raw or raw == ":memory:" or raw.startswith("/"):
        return url
    from erp_ai.config import PROJECT_ROOT

    return f"{prefix}{PROJECT_ROOT / raw}"


def ensure_sqlserver_database(url: str) -> bool:
    """Crée la base SQL Server de l'URL si elle n'existe pas (connexion via `master`).

    Rend `erp-ai init-db` ré-exécutable sur un serveur neuf (conteneur,
    StatefulSet Kubernetes) sans étape manuelle. Retourne True si créée.
    """
    target = sa.engine.make_url(url)
    database = target.database
    if not database or database.lower() == "master":
        return False
    admin = sa.create_engine(target.set(database="master"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            exists = conn.execute(
                sa.text("SELECT CASE WHEN DB_ID(:db) IS NULL THEN 0 ELSE 1 END"), {"db": database}
            ).scalar_one()
            if exists:
                return False
            conn.exec_driver_sql(f"CREATE DATABASE [{database.replace(']', ']]')}]")
            return True
    finally:
        admin.dispose()


def create_engine_for(settings: Settings | None = None) -> Engine:
    """Crée l'`Engine` correspondant à `settings.database_url`."""
    settings = settings or get_settings()
    url = _resolve_sqlite_url(settings.database_url)

    if url.startswith("mssql"):
        return sa.create_engine(
            url,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
            pool_recycle=1800,
            future=True,
        )

    if url.startswith("sqlite"):
        _ensure_sqlite_dir(url)
        return sa.create_engine(
            url,
            connect_args={"check_same_thread": False},
            future=True,
        )

    return sa.create_engine(url, pool_pre_ping=True, future=True)


@contextmanager
def session_scope(engine: Engine) -> Iterator[sa.Connection]:
    """Session transactionnelle : commit en sortie, rollback sur exception."""
    with engine.begin() as conn:
        yield conn
