"""Émulateur d'API ERP (format Sage / EBP).

Sert à démontrer la partie « intégration ERP par API REST » sans licence
ERP : les routes imitent la forme des API de gestion (clients, factures,
relances) et lisent la même base que l'application.

En production, ce module est remplacé par un connecteur réel :
  * Sage 100 / Sage X3 : API REST (OAuth2 client credentials, versionné) ;
  * EBP Gestion Commerciale : API REST ebp-partenaire / ebp-api.
Le contrat reste identique côté application (voir `ErpRestClient`).
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from erp_ai.db import models

router = APIRouter(prefix="/mock/erp", tags=["ERP (mock)"])


def _engine():
    from erp_ai.service import CopilotService

    return CopilotService().engine


class RelanceRequest(BaseModel):
    """Demande de relance d'une facture."""

    client_code: str = Field(..., description="Code client")
    numero_facture: str = Field(..., description="Numéro de facture")
    niveau: int = Field(1, ge=1, le=3, description="Niveau de relance (1, 2 ou 3)")
    message: str = Field("", description="Message rédigé par l'IA")
    montant: float = Field(0.0, ge=0)


@router.get("/health")
def health() -> dict[str, Any]:
    """État de l'ERP simulé."""
    return {"erp": "mock", "api": "v1", "statut": "ok"}


@router.get("/clients")
def liste_clients() -> list[dict[str, Any]]:
    """Liste des clients (équivalent GET /clients d'un ERP)."""
    engine = _engine()
    with engine.connect() as conn:
        rows = (
            conn.execute(
                sa.select(
                    models.client.c.code,
                    models.client.c.raison_sociale,
                    models.client.c.secteur,
                    models.client.c.ville,
                    models.client.c.encours_autorise,
                    models.client.c.actif,
                ).order_by(models.client.c.code)
            )
            .mappings()
            .all()
        )
    return [dict(row) for row in rows]


@router.get("/clients/{code}")
def detail_client(code: str) -> dict[str, Any]:
    """Détail d'un client et de ses factures."""
    engine = _engine()
    with engine.connect() as conn:
        client = (
            conn.execute(sa.select(models.client).where(models.client.c.code == code))
            .mappings()
            .first()
        )
        if client is None:
            raise HTTPException(status_code=404, detail=f"Client inconnu : {code}")
        factures = (
            conn.execute(
                sa.select(
                    models.facture.c.numero,
                    models.facture.c.date_emission,
                    models.facture.c.date_echeance,
                    models.facture.c.montant_ht,
                    models.facture.c.montant_ttc,
                    models.facture.c.statut,
                )
                .where(models.facture.c.client_id == client["id"])
                .order_by(models.facture.c.date_emission.desc())
            )
            .mappings()
            .all()
        )
    return {"client": dict(client), "factures": [dict(row) for row in factures]}


@router.get("/factures")
def liste_factures(
    statut: str | None = None, client_code: str | None = None
) -> list[dict[str, Any]]:
    """Factures, filtrables par statut et par client."""
    engine = _engine()
    stmt = (
        sa.select(
            models.facture.c.numero,
            models.facture.c.montant_ttc,
            models.facture.c.date_echeance,
            models.facture.c.statut,
            models.client.c.code.label("client_code"),
            models.client.c.raison_sociale,
        )
        .select_from(
            models.facture.join(models.client, models.facture.c.client_id == models.client.c.id)
        )
        .order_by(models.facture.c.date_echeance)
    )
    if statut:
        stmt = stmt.where(models.facture.c.statut == statut)
    if client_code:
        stmt = stmt.where(models.client.c.code == client_code)
    with engine.connect() as conn:
        return [dict(row) for row in conn.execute(stmt).mappings().all()]


@router.post("/relances")
def creer_relance(payload: RelanceRequest) -> dict[str, Any]:
    """Enregistre une relance (équivalent POST /relances de l'ERP)."""
    from erp_ai.config import get_settings

    path = get_settings().data_path / "relances.json"
    relances: list[dict[str, Any]] = []
    if path.exists():
        relances = json.loads(path.read_text(encoding="utf-8"))

    relance = {
        "id": uuid.uuid4().hex[:12],
        "client_code": payload.client_code,
        "numero_facture": payload.numero_facture,
        "niveau": payload.niveau,
        "montant": payload.montant,
        "message": payload.message,
        "cree_le": datetime.now().isoformat(timespec="seconds"),
        "statut": "ENVOYEE",
    }
    relances.append(relance)
    path.write_text(json.dumps(relances, ensure_ascii=False, indent=2), encoding="utf-8")
    return relance


@router.get("/relances")
def lister_relances() -> list[dict[str, Any]]:
    """Relances enregistrées."""
    from erp_ai.config import get_settings

    path = get_settings().data_path / "relances.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))
