"""Variante LangChain de la chaîne RAG (LCEL).

La chaîne native (`erp_ai.rag.retrieval` + `erp_ai.service`) reste la
référence : elle est explicite, sans dépendance, et c'est elle que la CI
exerce en priorité. Cette variante montre la **même chose avec LangChain**,
comme demandé dans l'offre :

    question -> retriever (RunnableLambda) -> contexte sourcé
             -> prompt ChatPromptTemplate -> LLM -> réponse

Choix techniques :
  * le retriever reste **le nôtre** (recherche hybride BM25 + vecteurs) : on
    ne remplace pas un algorithme éprouvé par un composant de bibliothèque ;
  * le format des sources est **strictement identique** à celui de la chaîne
    native (`format_source_blocks`), donc les citations sont les mêmes ;
  * le modèle peut être `AzureChatOpenAI` (langchain-openai) ou n'importe
    quel ChatLLM conforme à notre interface (mode local, tests) ;
  * en cas de panne, l'appelant retombe sur la chaîne native.
"""

from __future__ import annotations

from typing import Any

from erp_ai.config import Settings
from erp_ai.providers.llm import ChatLLM
from erp_ai.rag.prompts import SYSTEM_PROMPT, format_source_blocks

try:  # pragma: no cover - dépend de l'installation
    from langchain_core.documents import Document
    from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
    from langchain_core.messages import AIMessage
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.runnables import Runnable, RunnableLambda, RunnablePassthrough

    LANGCHAIN_AVAILABLE = True
except ImportError:  # pragma: no cover - installation sans langchain
    LANGCHAIN_AVAILABLE = False
    Document = Any  # type: ignore[assignment,misc]


def chunks_to_documents(chunks: list[Any]) -> list[Any]:
    """Convertit les fragments récupérés en `Document` LangChain."""
    docs = []
    for chunk in chunks:
        docs.append(
            Document(
                page_content=chunk.texte,
                metadata={
                    "chunk_id": chunk.chunk_id,
                    "document_id": chunk.document_id,
                    "titre": chunk.titre,
                    "section": chunk.section,
                    "type_doc": chunk.type_doc,
                    "client_code": chunk.client_code,
                    "version": chunk.version,
                    "score": chunk.score,
                    "source_ref": chunk.source_ref,
                },
            )
        )
    return docs


def documents_to_sources(documents: list[Any]) -> list[dict]:
    """Reconvertit des `Document` en sources compatibles avec les prompts."""
    return [
        {
            "titre": (doc.metadata or {}).get("titre", ""),
            "section": (doc.metadata or {}).get("section"),
            "type_doc": (doc.metadata or {}).get("type_doc", ""),
            "client_code": (doc.metadata or {}).get("client_code"),
            "version": (doc.metadata or {}).get("version", ""),
            "texte": doc.page_content,
        }
        for doc in documents
    ]


def build_azure_chat_model(settings: Settings) -> Any:
    """Construit un `AzureChatOpenAI` (langchain-openai)."""
    from langchain_openai import AzureChatOpenAI

    return AzureChatOpenAI(
        azure_deployment=settings.azure_openai_chat_deployment,
        api_key=settings.azure_openai_api_key,
        azure_endpoint=settings.azure_openai_endpoint,
        api_version=settings.azure_openai_api_version,
        temperature=0.0,
    )


def build_rag_chain(
    settings: Settings,
    retriever: Any,
    llm: ChatLLM | None = None,
    chat_model: Any | None = None,
) -> Any:
    """Construit la chaîne RAG LangChain (LCEL).

    Args:
        settings: configuration de l'application.
        retriever: notre `Retriever` (recherche hybride).
        llm: ChatLLM de repli (mode local) si `chat_model` n'est pas fourni.
        chat_model: modèle LangChain (ex. `AzureChatOpenAI`) si disponible.
    """
    answer_chain = build_answer_chain(settings, llm=llm, chat_model=chat_model)

    chain: Runnable = {
        "context": RunnableLambda(lambda question: chunks_to_documents(retriever.search(question)))
        | RunnableLambda(lambda docs: format_source_blocks(documents_to_sources(docs))),
        "question": RunnablePassthrough(),
    } | answer_chain
    return chain


def build_answer_chain(
    settings: Settings,
    llm: ChatLLM | None = None,
    chat_model: Any | None = None,
) -> Any:
    """Chaîne LangChain à partir d'un contexte déjà récupéré.

    `prompt -> modèle -> texte` : le service lui passe les sources qu'il a
    déjà sélectionnées, ce qui évite une seconde récupération et garantit
    que les citations correspondent exactement aux sources affichées.
    """
    if not LANGCHAIN_AVAILABLE:
        raise RuntimeError(
            "LangChain n'est pas installé : `pip install -e '.[langchain]'` ou RAG_CHAIN=native."
        )

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", SYSTEM_PROMPT),
            ("human", "[SOURCES]\n{context}\n[/SOURCES]\n\n[QUESTION]\n{question}\n[/QUESTION]"),
        ]
    )

    if chat_model is not None:
        model_step: Any = chat_model
    else:
        if llm is None:
            raise ValueError("Il faut fournir `chat_model` ou `llm`.")

        def _call_native(prompt_value: Any) -> AIMessage:
            return AIMessage(content=llm.complete(SYSTEM_PROMPT, prompt_value.to_string()))

        model_step = RunnableLambda(_call_native)

    def _extract_text(output: Any) -> str:
        if hasattr(output, "content"):
            return str(output.content)
        return str(output)

    chain: Runnable = prompt | model_step | RunnableLambda(_extract_text)
    return chain


def build_fake_chain(settings: Settings, retriever: Any, responses: list[str]) -> Any:
    """Construit une chaîne avec un modèle factice (tests hors ligne)."""
    if not LANGCHAIN_AVAILABLE:
        raise RuntimeError("LangChain n'est pas installé.")
    return build_rag_chain(
        settings,
        retriever,
        chat_model=GenericFakeChatModel(messages=iter(responses)),
    )
