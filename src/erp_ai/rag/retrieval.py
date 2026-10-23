"""Recherche hybride : BM25 (lexical) + vecteurs (sémantique), fusion RRF.

Pourquoi hybride : les questions de gestion sont souvent mixtes — « quelles
factures dépassent 90 jours de retard ? » mélange une notion chiffrée (le
seuil) et une notion métier (le retard). Le BM26/le BM25 est plus robuste sur
les montants et les références, le vecteur sur les reformulations. La fusion
Reciprocal Rank Fusion évite de devoir calibrer deux scores incomparable.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

import sqlalchemy as sa
from sqlalchemy.engine import Engine

from erp_ai.config import Settings, get_settings
from erp_ai.db import models
from erp_ai.providers.embeddings import EmbeddingProvider
from erp_ai.providers.vectorstore import VectorItem, VectorStore
from erp_ai.rag.chunking import chunk_document

_TOKEN_RE = re.compile(r"[\wÀ-ÿ]{2,}", re.UNICODE)
_STOPWORDS = {
    "les", "des", "une", "pour", "avec", "sur", "dans", "par", "est", "sont",
    "les", "leur", "que", "qui", "quoi", "comment", "quel", "quelle", "combien",
    "les", "au", "aux", "du", "de", "la", "le", "et", "ou", "a", "à", "en",
}

RRF_K = 60


def _stem(token: str) -> str:
    """Normalisation légère du français (accord singulier/pluriel).

    « délais » et « délai » doivent remonter au même fragment ; « règles »
    et « règle » aussi. On ne fait pas de stemming lourd : on retire
    simplement le « s » final quand il n'est pas double.
    """
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def _tokenize(text: str) -> list[str]:
    return [
        _stem(t.lower())
        for t in _TOKEN_RE.findall(text)
        if t.lower() not in _STOPWORDS and len(t) > 2
    ]


class BM25:
    """BM25 Okapi minimal sur un corpus en mémoire."""

    def __init__(self, corpus: list[list[str]], k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self.corpus_size = len(corpus)
        self.doc_len = [len(doc) for doc in corpus]
        self.avgdl = (sum(self.doc_len) / self.corpus_size) if self.corpus_size else 0.0
        self.doc_freqs = [Counter(doc) for doc in corpus]
        df: Counter[str] = Counter()
        for doc in self.doc_freqs:
            df.update(doc.keys())
        self.idf = {
            term: math.log(1 + (self.corpus_size - freq + 0.5) / (freq + 0.5))
            for term, freq in df.items()
        }

    def scores(self, query: list[str]) -> list[float]:
        out = [0.0] * self.corpus_size
        for term in query:
            idf = self.idf.get(term)
            if idf is None:
                continue
            for i, freqs in enumerate(self.doc_freqs):
                freq = freqs.get(term, 0)
                if not freq:
                    continue
                denom = freq + self.k1 * (
                    1 - self.b + self.b * (self.doc_len[i] / (self.avgdl or 1.0))
                )
                out[i] += idf * (freq * (self.k1 + 1)) / denom
        return out


@dataclass
class RetrievedChunk:
    """Fragment retenu par la recherche, avec sa provenance et son score."""

    chunk_id: int
    document_id: int
    titre: str
    section: str | None
    texte: str
    type_doc: str
    client_code: str | None
    version: str
    score: float
    source_ref: str = ""


class Retriever:
    """Indexe les documents et interroge l'index hybride."""

    def __init__(
        self,
        engine: Engine,
        embedding_provider: EmbeddingProvider,
        vector_store: VectorStore,
        settings: Settings | None = None,
    ) -> None:
        self.engine = engine
        self.embeddings = embedding_provider
        self.vector_store = vector_store
        self.settings = settings or get_settings()

    # -- Indexation ------------------------------------------------------
    def index_documents(self, force: bool = False) -> dict[str, int]:
        """Découpe, vectorise et indexe les documents de la base."""
        with self.engine.begin() as conn:
            docs = conn.execute(
                sa.select(
                    models.document.c.id,
                    models.document.c.titre,
                    models.document.c.type_doc,
                    models.document.c.version,
                    models.document.c.client_id,
                    models.document.c.contenu,
                )
            ).mappings().all()

            nb_docs = nb_chunks = 0
            for doc in docs:
                existing = conn.execute(
                    sa.select(sa.func.count())
                    .select_from(models.chunk)
                    .where(models.chunk.c.document_id == doc["id"])
                ).scalar_one()
                if existing and not force:
                    continue

                if existing:
                    conn.execute(models.chunk.delete().where(models.chunk.c.document_id == doc["id"]))

                drafts = chunk_document(
                    doc["contenu"],
                    size=self.settings.chunk_size,
                    overlap=self.settings.chunk_overlap,
                    document_id=doc["id"],
                    titre=doc["titre"],
                    extra_meta={"type_doc": doc["type_doc"], "version": doc["version"]},
                )
                if not drafts:
                    continue

                vectors = self.embeddings.embed_documents([d.texte for d in drafts])
                items: list[VectorItem] = []
                for draft, vector in zip(drafts, vectors, strict=True):
                    hash_ = hashlib.sha256(draft.texte.encode("utf-8")).hexdigest()
                    res = conn.execute(
                        models.chunk.insert().values(
                            document_id=doc["id"],
                            ordinal=draft.ordinal,
                            texte=draft.texte,
                            section=draft.section,
                            page=draft.page,
                            nb_tokens=draft.nb_tokens,
                            meta=draft.meta,
                            hash=hash_,
                        )
                    )
                    chunk_id = int(res.inserted_primary_key[0])
                    items.append(
                        VectorItem(
                            chunk_id=str(chunk_id),
                            vector=list(vector),
                            meta={
                                "texte": draft.texte,
                                "section": draft.section,
                                "titre": doc["titre"],
                                "type_doc": doc["type_doc"],
                                "version": doc["version"],
                                "document_id": doc["id"],
                            },
                        )
                    )
                    nb_chunks += 1

                self.vector_store.upsert(items)
                nb_docs += 1

        return {"documents": nb_docs, "chunks": nb_chunks}

    # -- Recherche -------------------------------------------------------
    def _load_corpus(self, client_id: int | None) -> list[dict[str, Any]]:
        stmt = (
            sa.select(
                models.chunk.c.id,
                models.chunk.c.texte,
                models.chunk.c.section,
                models.document.c.id.label("document_id"),
                models.document.c.titre,
                models.document.c.type_doc,
                models.document.c.version,
                models.client.c.code.label("client_code"),
            )
            .select_from(
                models.chunk.join(
                    models.document, models.chunk.c.document_id == models.document.c.id
                ).outerjoin(models.client, models.document.c.client_id == models.client.c.id)
            )
        )
        if client_id is not None:
            stmt = stmt.where(
                sa.or_(
                    models.document.c.client_id.is_(None),
                    models.document.c.client_id == client_id,
                )
            )
        with self.engine.connect() as conn:
            return [dict(row) for row in conn.execute(stmt).mappings().all()]

    def search(
        self,
        question: str,
        client_id: int | None = None,
        top_k: int | None = None,
    ) -> list[RetrievedChunk]:
        """Recherche hybride et fusion RRF."""
        top_k = top_k or self.settings.top_k
        corpus = self._load_corpus(client_id)
        if not corpus:
            return []

        # 1. BM25 (lexical)
        tokens = [_tokenize(row["texte"]) for row in corpus]
        bm25 = BM25(tokens, k1=self.settings.bm25_k1, b=self.settings.bm25_b)
        bm25_scores = bm25.scores(_tokenize(question))
        ranked = sorted(
            zip(corpus, bm25_scores, strict=True),
            key=lambda item: item[1],
            reverse=True,
        )[: top_k * 6]
        bm25_rank = {row["id"]: rank for rank, (row, _score) in enumerate(ranked, start=1)}

        # 2. Vecteurs (sémantique)
        allowed = {str(row["id"]) for row in corpus}
        query_vector = self.embeddings.embed_query(question)
        vector_hits = self.vector_store.search(query_vector, top_k=top_k * 6, allowed_ids=allowed)
        vector_rank = {int(hit.chunk_id): rank for rank, hit in enumerate(vector_hits, start=1)}

        # 3. Fusion Reciprocal Rank Fusion
        fused: dict[int, float] = {}
        for chunk_id, rank in bm25_rank.items():
            fused[chunk_id] = fused.get(chunk_id, 0.0) + 1.0 / (RRF_K + rank)
        for chunk_id, rank in vector_rank.items():
            fused[chunk_id] = fused.get(chunk_id, 0.0) + 1.0 / (RRF_K + rank)

        by_id = {row["id"]: row for row in corpus}
        results: list[RetrievedChunk] = []
        for chunk_id, score in sorted(fused.items(), key=lambda item: item[1], reverse=True):
            row = by_id.get(chunk_id)
            if row is None:
                continue
            results.append(
                RetrievedChunk(
                    chunk_id=int(chunk_id),
                    document_id=int(row.get("document_id") or 0),
                    titre=row["titre"],
                    section=row["section"],
                    texte=row["texte"],
                    type_doc=row["type_doc"],
                    client_code=row["client_code"],
                    version=row["version"],
                    score=round(float(score), 6),
                )
            )
            if len(results) >= top_k:
                break

        for index, item in enumerate(results, start=1):
            item.source_ref = f"S{index}"
        return results
