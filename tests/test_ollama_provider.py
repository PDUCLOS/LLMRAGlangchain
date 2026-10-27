"""Provider Ollama : contrat d'interface et compteurs LLMOps (HTTP simulé, sans GPU)."""

from __future__ import annotations

import httpx
import pytest

from erp_ai.config import Settings
from erp_ai.providers.embeddings import OllamaEmbeddings, build_embedding_provider
from erp_ai.providers.llm import OllamaChatLLM, build_llm, ollama_usage

CHAT_RESPONSE = {
    "message": {"role": "assistant", "content": "  Le délai est de 30 jours [S1].  "},
    "prompt_eval_count": 812,
    "eval_count": 40,
    "load_duration": 120_000_000,
    "prompt_eval_duration": 90_000_000,
    "eval_duration": 500_000_000,
}


def _mock_client(handler) -> httpx.Client:
    return httpx.Client(base_url="http://ollama.test", transport=httpx.MockTransport(handler))


@pytest.fixture
def ollama_settings() -> Settings:
    return Settings(llm_provider="ollama", embedding_provider="ollama")


def test_build_selectionne_ollama(ollama_settings: Settings) -> None:
    assert isinstance(build_llm(ollama_settings), OllamaChatLLM)
    assert isinstance(build_embedding_provider(ollama_settings), OllamaEmbeddings)


def test_complete_envoie_le_prompt_et_mesure_l_usage(ollama_settings: Settings) -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        captured.update(json.loads(request.content))
        return httpx.Response(200, json=CHAT_RESPONSE)

    llm = OllamaChatLLM(ollama_settings)
    llm._client = _mock_client(handler)

    answer = llm.complete("système", "question")

    assert answer == "Le délai est de 30 jours [S1]."
    assert captured["model"] == ollama_settings.ollama_chat_model
    assert captured["think"] is False
    assert captured["options"]["temperature"] == 0.0
    assert [m["role"] for m in captured["messages"]] == ["system", "user"]
    assert llm.last_usage == {
        "tokens_in": 812,
        "tokens_out": 40,
        "load_ms": 120.0,
        "prompt_ms": 90.0,
        "eval_ms": 500.0,
        "tokens_per_s": 80.0,
    }


def test_ollama_usage_tolere_les_champs_absents() -> None:
    usage = ollama_usage({})
    assert usage["tokens_in"] == 0
    assert usage["tokens_per_s"] == 0.0


def test_embeddings_renvoient_les_vecteurs_et_la_dimension(ollama_settings: Settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"embeddings": [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]})

    emb = OllamaEmbeddings(ollama_settings)
    emb._client = _mock_client(handler)

    assert emb.embed_documents(["a", "b"]) == [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
    assert emb.dim == 3
    assert emb.embed_query("a") == [0.1, 0.2, 0.3]
