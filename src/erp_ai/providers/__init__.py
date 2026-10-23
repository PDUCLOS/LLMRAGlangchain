"""Providers : LLM, embeddings et base vectorielle.

Chaque famille d'implémentations partage une interface : le code métier
n'appelle jamais directement l'API Azure. Le choix se fait par variable
d'environnement (`LLM_PROVIDER`, `EMBEDDING_PROVIDER`, `VECTOR_STORE_PROVIDER`).

  local             -> tout fonctionne hors ligne, de façon déterministe
  azure             -> Azure OpenAI / Azure AI Foundry
  azure_ai_search   -> Azure AI Search (base vectorielle managée)
"""

from erp_ai.providers.embeddings import (
    AzureOpenAIEmbeddings,
    EmbeddingProvider,
    HashingEmbeddings,
    build_embedding_provider,
)
from erp_ai.providers.llm import AzureChatLLM, ChatLLM, ExtractiveLocalLLM, build_llm
from erp_ai.providers.vectorstore import (
    AzureAISearchVectorStore,
    LocalVectorStore,
    ScoredItem,
    VectorItem,
    VectorStore,
    build_vector_store,
)

__all__ = [
    "AzureChatLLM",
    "AzureAISearchVectorStore",
    "AzureOpenAIEmbeddings",
    "ChatLLM",
    "EmbeddingProvider",
    "ExtractiveLocalLLM",
    "HashingEmbeddings",
    "LocalVectorStore",
    "ScoredItem",
    "VectorItem",
    "VectorStore",
    "build_embedding_provider",
    "build_llm",
    "build_vector_store",
]
