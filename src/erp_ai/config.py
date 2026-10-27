"""Configuration centralisée (12-factor light).

Tout se pilote par variables d'environnement ou fichier `.env` :
on passe de SQLite/local à SQL Server/Azure sans toucher au code.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Paramètres de l'application."""

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Application ------------------------------------------------------
    app_name: str = "erp-ai-copilot"
    environment: str = "local"
    log_level: str = "INFO"
    data_dir: str = "./data"

    # --- Base de données --------------------------------------------------
    # mssql+pyodbc://... en cible ; sqlite:///./data/dev.db en dev rapide.
    database_url: str = "sqlite:///./data/dev.db"

    # --- Providers (bascule local <-> Azure) ------------------------------
    llm_provider: str = "local"  # local | ollama | azure
    embedding_provider: str = "local"  # local | ollama | azure
    vector_store_provider: str = "local"  # local | azure_ai_search
    # Chaîne de génération : native (écrite explicitement) ou langchain (LCEL)
    rag_chain: str = "native"  # native | langchain

    # --- Azure AI Foundry / Azure OpenAI ---------------------------------
    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_chat_deployment: str = "gpt-4.1-mini"
    azure_openai_embedding_deployment: str = "text-embedding-3-small"
    azure_openai_api_version: str = "2024-10-21"

    # --- Ollama (LLM et embeddings locaux sur GPU) ---------------------
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_chat_model: str = "qwen3.5:9b"
    ollama_embedding_model: str = "bge-m3"
    ollama_num_ctx: int = 8192
    ollama_timeout_s: float = 180.0

    # --- Azure AI Search --------------------------------------------------
    azure_search_endpoint: str = ""
    azure_search_index: str = "erp-docs"
    azure_search_api_key: str = ""

    # --- Entra ID ---------------------------------------------------------
    azure_tenant_id: str = ""
    azure_client_id: str = ""
    azure_client_secret: str = ""

    # --- Stockage objet ---------------------------------------------------
    azure_storage_account: str = ""
    azure_storage_container: str = "erp-docs"
    azure_storage_connection_string: str = ""

    # --- RAG --------------------------------------------------------------
    embedding_dim: int = 384
    chunk_size: int = 800
    chunk_overlap: int = 100
    top_k: int = 5
    bm25_k1: float = 1.5
    bm25_b: float = 0.75

    # --- Garde-fous SQL ---------------------------------------------------
    sql_allowed_tables: str = "client,article,facture,ligne_facture,reglement,ecriture_comptable"
    sql_readonly_user: str = "erp_readonly"
    sql_readonly_password: str = ""

    # --- Coûts (EUR / 1M tokens) -----------------------------------------
    cost_chat_input_eur_per_mtok: float = 0.40
    cost_chat_output_eur_per_mtok: float = 1.20
    cost_embedding_eur_per_mtok: float = 0.02

    # --- Dérivés ----------------------------------------------------------
    @property
    def is_sqlserver(self) -> bool:
        return self.database_url.startswith("mssql")

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def allowed_tables(self) -> set[str]:
        return {t.strip().lower() for t in self.sql_allowed_tables.split(",") if t.strip()}

    @property
    def data_path(self) -> Path:
        p = Path(self.data_dir)
        if not p.is_absolute():
            p = PROJECT_ROOT / p
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def vectorstore_path(self) -> Path:
        return self.data_path / "vectorstore.json"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Renvoie la configuration (cachée pour ne pas re-lire le .env)."""
    return Settings()


def reset_settings_cache() -> None:
    """À appeler dans les tests après modification de l'environnement."""
    get_settings.cache_clear()
