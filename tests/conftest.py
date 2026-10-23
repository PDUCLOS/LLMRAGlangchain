"""Fixtures de test.

Les tests s'exécutent sans aucun service externe : base SQLite temporaire,
providers locaux (embeddings par hachage, LLM extractif, index vectoriel
fichier). C'est ce qui permet de faire tourner la CI sur n'importe quelle
machine, y compris en ARM64.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from erp_ai.config import Settings, reset_settings_cache

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def settings(tmp_path_factory: pytest.TempPathFactory) -> Settings:
    """Configuration de test : SQLite + providers locaux, données isolées.

    Si `ERP_AI_TEST_DATABASE_URL` est défini (CI sur runner x86-64), les
    tests s'exécutent sur un vrai SQL Server au lieu de SQLite.
    """
    data_dir = tmp_path_factory.mktemp("erp_ai_data")
    db_url = os.environ.get("ERP_AI_TEST_DATABASE_URL") or f"sqlite:///{data_dir / 'test.db'}"
    os.environ["DATABASE_URL"] = db_url
    os.environ["DATA_DIR"] = str(data_dir)
    os.environ["LLM_PROVIDER"] = "local"
    os.environ["EMBEDDING_PROVIDER"] = "local"
    os.environ["VECTOR_STORE_PROVIDER"] = "local"
    os.environ["ENVIRONMENT"] = "test"
    reset_settings_cache()

    yield Settings(
        database_url=db_url,
        data_dir=str(data_dir),
        llm_provider="local",
        embedding_provider="local",
        vector_store_provider="local",
        environment="test",
    )

    for key in (
        "DATABASE_URL",
        "DATA_DIR",
        "LLM_PROVIDER",
        "EMBEDDING_PROVIDER",
        "VECTOR_STORE_PROVIDER",
        "ENVIRONMENT",
    ):
        os.environ.pop(key, None)
    reset_settings_cache()


@pytest.fixture(scope="session")
def engine(settings: Settings):
    """Moteur SQL initialisé avec le jeu de données de démonstration."""
    from erp_ai.db.bootstrap import init_db
    from erp_ai.db.engine import create_engine_for

    eng = create_engine_for(settings)
    init_db(eng)
    return eng


@pytest.fixture()
def service(settings: Settings, engine) -> Iterator:
    """Service applicatif avec l'index vectoriel reconstruit."""
    from erp_ai.service import CopilotService

    reset_settings_cache()
    svc = CopilotService()
    svc.ingest(force=True)
    yield svc
    reset_settings_cache()
