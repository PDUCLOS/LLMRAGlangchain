"""Embeddings : Azure OpenAI en cible, hachage déterministe en local.

L'implémentation locale n'est pas un modèle neuronal : c'est un vecteur de
hachage features (unigrammes + bigrammes) normalisé. Elle permet de faire
tourner la démo et les tests sans compte Azure, avec des propriétés
suffisantes pour un classement lexical approché, combiné au BM25 dans la
recherche hybride.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from collections.abc import Sequence
from typing import Protocol

import numpy as np

from erp_ai.config import Settings, get_settings

_TOKEN_RE = re.compile(r"[\wÀ-ÿ]+", re.UNICODE)


class EmbeddingProvider(Protocol):
    """Interface commune des fournisseurs d'embeddings."""

    dim: int
    name: str

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class HashingEmbeddings:
    """Embeddings déterministes, sans dépendance externe ni réseau."""

    def __init__(self, dim: int = 384) -> None:
        self.dim = dim
        self.name = "local-hashing"

    @staticmethod
    def _features(text: str) -> list[str]:
        tokens = [t.lower() for t in _TOKEN_RE.findall(text)]
        bigrams = [f"{a}_{b}" for a, b in zip(tokens, tokens[1:], strict=False)]
        return tokens + bigrams

    def _embed_one(self, text: str) -> np.ndarray:
        vec = np.zeros(self.dim, dtype=np.float32)
        counts = Counter(self._features(text))
        for feature, count in counts.items():
            digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "big") % self.dim
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vec[index] += sign * (1.0 + math.log(count))
        norm = float(np.linalg.norm(vec))
        return vec / norm if norm > 0 else vec

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed_one(t).tolist() for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed_one(text).tolist()


class AzureOpenAIEmbeddings:
    """Embeddings Azure OpenAI (text-embedding-3-small par défaut)."""

    def __init__(self, settings: Settings) -> None:
        from openai import AzureOpenAI  # import tardif : optionnel

        self.name = "azure-openai"
        self.model = settings.azure_openai_embedding_deployment
        self.dim = settings.embedding_dim if settings.embedding_dim > 0 else 1536
        self._client = AzureOpenAI(
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_api_version,
        )

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        result = self._client.embeddings.create(model=self.model, input=list(texts))
        return [item.embedding for item in result.data]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


def build_embedding_provider(settings: Settings | None = None) -> EmbeddingProvider:
    """Construit le fournisseur d'embeddings selon la configuration."""
    settings = settings or get_settings()
    if settings.embedding_provider.lower() == "azure":
        return AzureOpenAIEmbeddings(settings)
    return HashingEmbeddings(dim=settings.embedding_dim)
