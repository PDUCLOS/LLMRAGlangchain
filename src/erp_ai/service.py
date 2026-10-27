"""Service applicatif : orchestre retrieval, outils SQL, LLM et observabilité.

C'est le point d'entrée unique utilisé par l'API REST, la CLI et (en
production) par les flux Power Automate et l'agent Copilot Studio.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any

import sqlalchemy as sa

from erp_ai.agents.safe_sql import SqlGuardError
from erp_ai.agents.tools import ErpTools, SqlAgent
from erp_ai.config import Settings, get_settings
from erp_ai.db import models
from erp_ai.db.engine import create_engine_for
from erp_ai.observability.usage import estimate_cost, log_usage, new_request_id, usage_summary
from erp_ai.providers.embeddings import build_embedding_provider
from erp_ai.providers.llm import build_llm
from erp_ai.providers.vectorstore import build_vector_store
from erp_ai.rag.chunking import estimate_tokens
from erp_ai.rag.langchain_chain import LANGCHAIN_AVAILABLE, build_answer_chain
from erp_ai.rag.prompts import SYSTEM_PROMPT, build_user_prompt, format_source_blocks
from erp_ai.rag.retrieval import Retriever

logger = logging.getLogger(__name__)

ROLES = {"daf", "controleur", "commercial", "admin"}


def _format_row(row: dict[str, Any]) -> str:
    """Formate une ligne SQL en phrase lisible (le LLM local l'indexe)."""
    parts = [f"{key.replace('_', ' ')} : {value}" for key, value in row.items()]
    return " ; ".join(parts) + "."


class CopilotService:
    """Facade applicative du copilote ERP."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.engine = create_engine_for(self.settings)
        self.embeddings = build_embedding_provider(self.settings)
        self.vector_store = build_vector_store(self.settings)
        self.llm = build_llm(self.settings)
        self.retriever = Retriever(self.engine, self.embeddings, self.vector_store, self.settings)
        self.tools = ErpTools(self.engine, self.settings)
        self.sql_agent = SqlAgent(self.engine, self.llm, self.settings)
        self._lc_chain: Any | None = None
        self._lc_usage: dict[str, Any] = {}

    # -- Santé -----------------------------------------------------------
    def health(self) -> dict[str, Any]:
        """État des dépendances (base, providers, index)."""
        db_ok = True
        nb_clients = 0
        try:
            with self.engine.connect() as conn:
                nb_clients = conn.execute(
                    sa.select(sa.func.count()).select_from(models.client)
                ).scalar_one()
        except Exception as exc:  # pragma: no cover - dépend de l'infra
            db_ok = False
            nb_clients = f"erreur: {exc}"

        return {
            "status": "ok" if db_ok else "degraded",
            "environment": self.settings.environment,
            "database": {
                "ok": db_ok,
                "dialect": self.engine.dialect.name,
                "clients": nb_clients,
            },
            "providers": {
                "llm": self.llm.name,
                "model": self.llm.model,
                "embeddings": self.embeddings.name,
                "vector_store": self.vector_store.name,
            },
            "index": {"fragments": self.vector_store.count()},
        }

    # -- Ingestion --------------------------------------------------------
    def ingest(self, force: bool = False) -> dict[str, int]:
        """Indexe les documents de la base."""
        return self.retriever.index_documents(force=force)

    # -- Conversation -----------------------------------------------------
    def ask(
        self,
        question: str,
        client_id: int | None = None,
        role: str = "daf",
        top_k: int | None = None,
    ) -> dict[str, Any]:
        """Répond à une question (RAG + éventuellement outil SQL)."""
        if role not in ROLES:
            raise ValueError(f"Rôle inconnu : {role}")
        if role == "commercial" and client_id is None:
            raise PermissionError("Un commercial doit préciser le client concerné.")

        started = time.perf_counter()
        request_id = new_request_id()
        chain_used = "none"
        generation_ms = 0
        top_k = top_k or self.settings.top_k

        retrieved = self.retriever.search(question, client_id=client_id, top_k=top_k)
        sources: list[dict[str, Any]] = [
            {
                "titre": item.titre,
                "section": item.section,
                "type_doc": item.type_doc,
                "client_code": item.client_code,
                "version": item.version,
                "texte": item.texte,
                "score": item.score,
                "source_ref": item.source_ref,
            }
            for item in retrieved
        ]

        # Outil SQL : uniquement si l'intention est reconnue et validée.
        sql_info: dict[str, Any] | None = None
        try:
            intent = self.sql_agent.detect_intent(question)
            if intent:
                result = self.sql_agent.run(question)
                sql_info = {"sql": result.sql, "rowcount": result.rowcount}
                for row in result.rows[:10]:
                    sources.append(
                        {
                            "titre": "Requête ERP (SQL en lecture seule)",
                            "section": intent,
                            "type_doc": "sql",
                            "client_code": None,
                            "version": "-",
                            "texte": _format_row(row),
                            "score": None,
                            "source_ref": "",
                        }
                    )
        except SqlGuardError:
            sql_info = None

        if not sources:
            answer = (
                "Je n'ai pas de source suffisante dans le corpus pour répondre à cette "
                "question. Aucune donnée n'a été inventée."
            )
            statut = "REFUS"
        else:
            for index, source in enumerate(sources, start=1):
                source["source_ref"] = source.get("source_ref") or f"S{index}"
            if hasattr(self.llm, "last_usage"):
                self.llm.last_usage = None
            gen_started = time.perf_counter()
            answer = self._answer_with_langchain(question, sources)
            chain_used = "langchain" if answer is not None else "native"
            if answer is None:
                prompt = build_user_prompt(sources, question)
                answer = self.llm.complete(SYSTEM_PROMPT, prompt)
            generation_ms = int((time.perf_counter() - gen_started) * 1000)
            statut = "OK"

        # Compteurs réels du modèle si disponibles (Ollama, LangChain), sinon estimation.
        measured = (
            dict(self._lc_usage)
            if chain_used == "langchain" and self._lc_usage
            else dict(getattr(self.llm, "last_usage", None) or {})
        )
        tokens_mesures = bool(measured.get("tokens_in"))
        tokens_in = int(measured.get("tokens_in") or 0) or (
            estimate_tokens(SYSTEM_PROMPT) + estimate_tokens(build_user_prompt(sources, question))
        )
        tokens_out = int(measured.get("tokens_out") or 0) or estimate_tokens(answer)
        cout = estimate_cost(self.settings, self.llm.model, tokens_in, tokens_out)
        latence_ms = int((time.perf_counter() - started) * 1000)

        log_usage(
            self.engine,
            request_id=request_id,
            provider=self.llm.name,
            modele=self.llm.model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cout_eur=cout,
            latence_ms=latence_ms,
            question=question,
            user_role=role,
            client_id=client_id,
            statut=statut,
        )

        with self.engine.begin() as conn:
            conn.execute(
                models.conversation.insert().values(
                    request_id=request_id,
                    role=role,
                    client_id=client_id,
                    question=question,
                    reponse=answer,
                    sources=[
                        {
                            "ref": s["source_ref"],
                            "document": s["titre"],
                            "section": s["section"],
                        }
                        for s in sources
                    ],
                    feedback=None,
                    cree_le=datetime.now(),
                )
            )

        return {
            "request_id": request_id,
            "answer": answer,
            "sources": [
                {
                    "ref": s["source_ref"],
                    "document": s["titre"],
                    "section": s["section"],
                    "type": s["type_doc"],
                    "score": s["score"],
                }
                for s in sources
            ],
            "sql": sql_info,
            "usage": {
                "provider": self.llm.name,
                "model": self.llm.model,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "cout_eur": cout,
                "latence_ms": latence_ms,
                "generation_ms": generation_ms,
                "retrieval_ms": max(latence_ms - generation_ms, 0),
                "tokens_mesures": tokens_mesures,
                "tokens_per_s": measured.get("tokens_per_s"),
                "chain": chain_used,
            },
            "statut": statut,
        }

    def _answer_with_langchain(self, question: str, sources: list[dict]) -> str | None:
        """Génère la réponse via la chaîne LangChain (si activée).

        Retourne `None` si la chaîne LangChain n'est pas activée, pas
        installée ou en erreur : l'appelant bascule alors sur la chaîne
        native, qui reste la référence.
        """
        if self.settings.rag_chain.lower() != "langchain" or not LANGCHAIN_AVAILABLE:
            return None
        try:
            if self._lc_chain is None:
                chat_model = None
                provider = self.settings.llm_provider.lower()
                if provider == "azure":
                    from erp_ai.rag.langchain_chain import build_azure_chat_model

                    chat_model = build_azure_chat_model(self.settings)
                elif provider == "ollama":
                    from erp_ai.rag.langchain_chain import build_ollama_chat_model

                    chat_model = build_ollama_chat_model(self.settings)
                self._lc_chain = build_answer_chain(
                    self.settings, llm=self.llm, chat_model=chat_model, usage_sink=self._lc_usage
                )
            context = format_source_blocks(sources)
            return self._lc_chain.invoke({"context": context, "question": question})
        except Exception as exc:  # pragma: no cover - dépend de l'installation
            logger.warning("Chaîne LangChain indisponible, repli sur la chaîne native : %s", exc)
            return None

    def run_sql(self, question: str) -> dict[str, Any]:
        """Exécute une requête SQL encadrée (démonstration Text-to-SQL)."""
        result = self.sql_agent.run(question)
        return {"sql": result.sql, "rowcount": result.rowcount, "rows": result.rows}

    def usage(self, days: int = 30) -> list[dict[str, Any]]:
        """Synthèse de consommation."""
        return usage_summary(self.engine, days=days)
