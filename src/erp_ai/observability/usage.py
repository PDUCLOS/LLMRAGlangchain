"""Journalisation de l'usage IA et calcul de coût."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.engine import Engine

from erp_ai.config import Settings
from erp_ai.db import models


def new_request_id() -> str:
    """Identifiant de requête court et traçable."""
    return uuid.uuid4().hex[:16]


def estimate_cost(
    settings: Settings,
    model: str,
    tokens_in: int,
    tokens_out: int,
    embedding: bool = False,
) -> float:
    """Estime le coût en euros (tarifs indicatifs configurables)."""
    if embedding:
        return round(tokens_in * settings.cost_embedding_eur_per_mtok / 1_000_000, 6)
    cost_in = tokens_in * settings.cost_chat_input_eur_per_mtok / 1_000_000
    cost_out = tokens_out * settings.cost_chat_output_eur_per_mtok / 1_000_000
    return round(cost_in + cost_out, 6)


def log_usage(
    engine: Engine,
    *,
    request_id: str,
    provider: str,
    modele: str,
    tokens_in: int = 0,
    tokens_out: int = 0,
    cout_eur: float = 0.0,
    latence_ms: int = 0,
    question: str | None = None,
    user_role: str | None = None,
    client_id: int | None = None,
    statut: str = "OK",
) -> None:
    """Écrit une ligne dans `ai_usage_log`."""
    with engine.begin() as conn:
        conn.execute(
            models.ai_usage_log.insert().values(
                horodatage=datetime.now(),
                request_id=request_id,
                user_role=user_role,
                client_id=client_id,
                provider=provider,
                modele=modele,
                tokens_in=int(tokens_in),
                tokens_out=int(tokens_out),
                cout_eur=Decimal(str(round(cout_eur, 6))),
                latence_ms=int(latence_ms),
                question=(question or "")[:1000] or None,
                statut=statut,
            )
        )


def usage_summary(engine: Engine, days: int = 30) -> list[dict[str, Any]]:
    """Agrégat de consommation par jour, modèle et client."""
    since = datetime.now() - timedelta(days=days)
    # `date()` n'existe pas en T-SQL ; `CAST(... AS DATE)` donne un entier sous SQLite.
    horodatage = models.ai_usage_log.c.horodatage
    jour = (
        sa.cast(horodatage, sa.Date) if engine.dialect.name == "mssql" else sa.func.date(horodatage)
    )
    stmt = (
        sa.select(
            jour.label("jour"),
            models.ai_usage_log.c.modele,
            models.ai_usage_log.c.provider,
            sa.func.count().label("nb_appels"),
            sa.func.sum(models.ai_usage_log.c.tokens_in).label("tokens_in"),
            sa.func.sum(models.ai_usage_log.c.tokens_out).label("tokens_out"),
            sa.func.sum(models.ai_usage_log.c.cout_eur).label("cout_eur"),
            sa.func.avg(models.ai_usage_log.c.latence_ms).label("latence_moy"),
        )
        .where(models.ai_usage_log.c.horodatage >= since)
        .group_by(jour, models.ai_usage_log.c.modele, models.ai_usage_log.c.provider)
        .order_by(jour.desc())
    )
    with engine.connect() as conn:
        rows = conn.execute(stmt).mappings().all()
    return [
        {
            "jour": str(row["jour"]),
            "modele": row["modele"],
            "provider": row["provider"],
            "nb_appels": int(row["nb_appels"] or 0),
            "tokens_in": int(row["tokens_in"] or 0),
            "tokens_out": int(row["tokens_out"] or 0),
            "cout_eur": round(float(row["cout_eur"] or 0), 6),
            "latence_moy_ms": int(float(row["latence_moy"] or 0)),
        }
        for row in rows
    ]
