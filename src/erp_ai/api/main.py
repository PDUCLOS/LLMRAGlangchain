"""API REST du copilote ERP.

Routes exposées :
  GET  /health              état de l'application et des dépendances
  POST /ingest              (re)construction de l'index vectoriel
  POST /chat                question métier -> réponse ancrée + citations
  POST /sql                 démonstration Text-to-SQL encadré
  GET  /usage               consommation (tokens, coût, latence)
  /mock/erp/*              émulateur d'API ERP (Sage / EBP)
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

from erp_ai.api.mock_erp import router as mock_erp_router
from erp_ai.service import CopilotService


class ChatRequest(BaseModel):
    """Requête de conversation."""

    question: str = Field(..., min_length=2, max_length=1000)
    client_id: int | None = Field(None, description="Restreint la recherche à un client")
    role: str = Field("daf", description="daf | controleur | commercial | admin")
    top_k: int | None = Field(None, ge=1, le=20)


class SqlRequest(BaseModel):
    """Requête de démonstration Text-to-SQL."""

    question: str = Field(..., min_length=2, max_length=1000)


@lru_cache(maxsize=1)
def get_service() -> CopilotService:
    """Service applicatif (singleton) : moteur, providers et index."""
    return CopilotService()


def create_app() -> FastAPI:
    """Construit l'application FastAPI."""
    app = FastAPI(
        title="Copilote IA ERP",
        version="0.1.0",
        description=(
            "Assistant IA & automatisation ERP : RAG documentaire, requêtes SQL "
            "en lecture seule sur le référentiel de gestion, agents d'automatisation "
            "(relances) et restitution Power BI / Teams."
        ),
    )
    app.include_router(mock_erp_router)

    @app.get("/health", tags=["système"])
    def health(service: CopilotService = Depends(get_service)) -> dict[str, Any]:
        """État de l'application et des dépendances."""
        return service.health()

    @app.post("/ingest", tags=["système"])
    def ingest(
        force: bool = False, service: CopilotService = Depends(get_service)
    ) -> dict[str, int]:
        """(Re)construit l'index vectoriel à partir des documents en base."""
        return service.ingest(force=force)

    @app.post("/chat", tags=["copilote"])
    def chat(
        payload: ChatRequest, service: CopilotService = Depends(get_service)
    ) -> dict[str, Any]:
        """Question métier -> réponse ancrée, citations, SQL exécuté et coût."""
        try:
            return service.ask(
                question=payload.question,
                client_id=payload.client_id,
                role=payload.role,
                top_k=payload.top_k,
            )
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/sql", tags=["copilote"])
    def sql(payload: SqlRequest, service: CopilotService = Depends(get_service)) -> dict[str, Any]:
        """Traduction d'une question en SQL, exécution en lecture seule."""
        from erp_ai.agents.safe_sql import SqlGuardError

        try:
            return service.run_sql(payload.question)
        except SqlGuardError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/usage", tags=["système"])
    def usage(days: int = 30, service: CopilotService = Depends(get_service)) -> dict[str, Any]:
        """Consommation des 30 derniers jours (tokens, coût, latence)."""
        return {"jours": days, "lignes": service.usage(days=days)}

    return app


app = create_app()
