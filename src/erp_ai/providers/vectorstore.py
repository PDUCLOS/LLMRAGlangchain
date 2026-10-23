"""Base vectorielle : Azure AI Search en cible, index local déterministe en dev.

L'index local est un fichier JSON (`data/vectorstore.json`) : les vecteurs
sont rangés par identifiant de fragment. L'implémentation Azure utilise
Azure AI Search (index vectoriel HNSW + recherche hybride + ranker
sémantique). Les deux exposent la même interface `VectorStore`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from erp_ai.config import Settings, get_settings


@dataclass
class VectorItem:
    """Un fragment indexé : identifiant, vecteur et métadonnées."""

    chunk_id: str
    vector: list[float]
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class ScoredItem:
    """Un fragment retourné par la recherche, avec son score."""

    chunk_id: str
    score: float
    meta: dict[str, Any] = field(default_factory=dict)


class VectorStore:
    """Interface commune des bases vectorielles."""

    name: str

    def upsert(self, items: list[VectorItem]) -> int: ...

    def search(
        self, vector: list[float], top_k: int = 5, allowed_ids: set[str] | None = None
    ) -> list[ScoredItem]: ...

    def count(self) -> int: ...


class LocalVectorStore:
    """Index vectoriel local (fichier JSON), sans dépendance externe."""

    name = "local-json"

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._data: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            self._data = json.loads(self.path.read_text(encoding="utf-8"))

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._data, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)

    def upsert(self, items: list[VectorItem]) -> int:
        for item in items:
            self._data[str(item.chunk_id)] = {
                "vector": [round(float(x), 6) for x in item.vector],
                "meta": item.meta,
            }
        self._save()
        return len(items)

    def search(
        self, vector: list[float], top_k: int = 5, allowed_ids: set[str] | None = None
    ) -> list[ScoredItem]:
        if not self._data:
            return []
        query = np.asarray(vector, dtype=np.float32)
        norm = float(np.linalg.norm(query))
        if norm > 0:
            query = query / norm

        results: list[ScoredItem] = []
        for chunk_id, payload in self._data.items():
            if allowed_ids is not None and chunk_id not in allowed_ids:
                continue
            candidate = np.asarray(payload["vector"], dtype=np.float32)
            if candidate.shape != query.shape:
                continue
            cnorm = float(np.linalg.norm(candidate))
            if cnorm == 0:
                continue
            score = float(np.dot(query, candidate) / cnorm)
            results.append(ScoredItem(chunk_id=chunk_id, score=score, meta=payload.get("meta", {})))
        results.sort(key=lambda item: item.score, reverse=True)
        return results[:top_k]

    def count(self) -> int:
        return len(self._data)


class AzureAISearchVectorStore:
    """Index vectoriel managé Azure AI Search."""

    name = "azure-ai-search"

    def __init__(self, settings: Settings) -> None:
        from azure.core.credentials import AzureKeyCredential
        from azure.search.documents import SearchClient

        self._index = settings.azure_search_index
        self._client = SearchClient(
            endpoint=settings.azure_search_endpoint,
            index_name=self._index,
            credential=AzureKeyCredential(settings.azure_search_api_key),
        )

    def upsert(self, items: list[VectorItem]) -> int:
        docs = [
            {
                "id": item.chunk_id,
                "content": item.meta.get("texte", ""),
                "vector": item.vector,
                "meta": item.meta,
            }
            for item in items
        ]
        if not docs:
            return 0
        self._client.upload_documents(documents=docs)
        return len(docs)

    def search(
        self, vector: list[float], top_k: int = 5, allowed_ids: set[str] | None = None
    ) -> list[ScoredItem]:
        from azure.search.documents.models import VectorizedQuery

        query = VectorizedQuery(
            vector=vector,
            k_nearest_neighbors=top_k * 4,
            fields="vector",
        )
        results = self._client.search(
            vector_queries=[query],
            top=top_k,
            include_total_count=True,
        )
        out: list[ScoredItem] = []
        for doc in results:
            chunk_id = str(doc.get("id"))
            if allowed_ids is not None and chunk_id not in allowed_ids:
                continue
            out.append(
                ScoredItem(
                    chunk_id=chunk_id,
                    score=float(doc.get("@search.score", 0.0)),
                    meta=doc.get("meta") or {},
                )
            )
        return out

    def count(self) -> int:
        return int(self._client.get_count_results().count or 0)


def build_vector_store(settings: Settings | None = None) -> VectorStore:
    """Construit la base vectorielle selon la configuration."""
    settings = settings or get_settings()
    if settings.vector_store_provider.lower() in {"azure", "azure_ai_search"}:
        return AzureAISearchVectorStore(settings)
    return LocalVectorStore(settings.vectorstore_path)
