"""Tests de l'API REST (FastAPI) et de l'émulateur d'ERP."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(service):
    from erp_ai.api.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client


def test_health(client) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["database"]["dialect"] == "sqlite"
    assert payload["providers"]["llm"] == "local-extractive"


def test_chat_repond_avec_des_sources(client) -> None:
    response = client.post(
        "/chat",
        json={"question": "Quels sont les délais de paiement appliqués aux clients ?"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["answer"]
    assert payload["sources"], "La réponse doit être sourcée"
    assert payload["statut"] == "OK"
    assert payload["usage"]["tokens_out"] > 0
    assert any("relance" in s["document"].lower() for s in payload["sources"])


def test_chat_refuse_si_aucune_source(client) -> None:
    response = client.post("/chat", json={"question": "question improbable xyzzy"})
    payload = response.json()
    # soit une réponse sourcée, soit un refus explicite : jamais d'affirmation
    # sans source.
    assert payload["statut"] in {"OK", "REFUS"}
    if payload["statut"] == "REFUS":
        assert "source" in payload["answer"].lower()


def test_chat_interdit_le_role_inconnu(client) -> None:
    response = client.post("/chat", json={"question": "test", "role": "dg"})
    assert response.status_code == 400


def test_chat_commercial_doit_preciser_un_client(client) -> None:
    response = client.post("/chat", json={"question": "mes impayés", "role": "commercial"})
    assert response.status_code == 403


def test_sql_encadre(client) -> None:
    response = client.post("/sql", json={"question": "quelles factures sont en retard ?"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["rowcount"] > 0
    assert payload["sql"].upper().startswith("SELECT")


def test_sql_refuse_une_question_hors_perimetre(client) -> None:
    response = client.post("/sql", json={"question": "raconte-moi une histoire"})
    assert response.status_code == 400


def test_ingest(client) -> None:
    response = client.post("/ingest", params={"force": True})
    assert response.status_code == 200
    assert response.json()["documents"] == 5


def test_usage(client) -> None:
    client.post("/chat", json={"question": "procédure de relance"})
    response = client.get("/usage")
    assert response.status_code == 200
    assert response.json()["lignes"]


def test_mock_erp_clients(client) -> None:
    response = client.get("/mock/erp/clients")
    assert response.status_code == 200
    assert len(response.json()) == 8


def test_mock_erp_detail_client(client) -> None:
    response = client.get("/mock/erp/clients/CLI-001")
    assert response.status_code == 200
    payload = response.json()
    assert payload["client"]["raison_sociale"] == "Batipont SAS"
    assert payload["factures"]


def test_mock_erp_client_inconnu(client) -> None:
    assert client.get("/mock/erp/clients/CLI-999").status_code == 404


def test_mock_erp_relance(client) -> None:
    response = client.post(
        "/mock/erp/relances",
        json={
            "client_code": "CLI-003",
            "numero_facture": "F-2026-0010",
            "niveau": 2,
            "montant": 1250.40,
            "message": "Relance de votre facture en attente de règlement.",
        },
    )
    assert response.status_code == 200
    assert response.json()["statut"] == "ENVOYEE"
    assert client.get("/mock/erp/relances").json()
