"""Découpage structurel des documents en fragments indexables.

Principes :
  * on respecte la structure du document (titres, sections) : un fragment ne
    coupe pas une section en plein milieu sans raison ;
  * on chevauche les fragments voisins (overlap) pour ne pas perdre l'information
    située à la frontière ;
  * on conserve les métadonnées utiles au filtrage (titre, section, client,
    version, type de document) et au filtrage d'accès.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

_TOKEN_RE = re.compile(r"[\wÀ-ÿ]+|[^\w\s]", re.UNICODE)
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


def estimate_tokens(text: str) -> int:
    """Estimation du nombre de tokens (approximation mot/punctuation)."""
    return len(_TOKEN_RE.findall(text))


@dataclass
class ChunkDraft:
    """Fragment à insérer en base et à indexer."""

    ordinal: int
    texte: str
    section: str | None
    page: int | None = None
    nb_tokens: int = 0
    meta: dict[str, Any] = field(default_factory=dict)


def split_sections(text: str) -> list[tuple[str, str]]:
    """Découpe un document en sections (titre, contenu)."""
    sections: list[tuple[str, list[str]]] = []
    current_title = "Préambule"
    current_lines: list[str] = []

    for line in text.splitlines():
        match = _HEADING_RE.match(line.strip())
        if match:
            if current_lines and "".join(current_lines).strip():
                sections.append((current_title, current_lines))
            current_title = match.group(2).strip()
            current_lines = []
        else:
            current_lines.append(line)

    if current_lines and "".join(current_lines).strip():
        sections.append((current_title, current_lines))

    return [
        (title, "\n".join(lines).strip()) for title, lines in sections if "\n".join(lines).strip()
    ]


def _paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def _split_long(text: str, size: int) -> list[str]:
    """Découpe un paragraphe trop long (par phrases, puis par mots)."""
    if estimate_tokens(text) <= size:
        return [text]

    sentences = re.split(r"(?<=[.!?])\s+", text)
    out: list[str] = []
    current = ""
    for sentence in sentences:
        candidate = f"{current} {sentence}".strip()
        if estimate_tokens(candidate) <= size:
            current = candidate
            continue
        if current:
            out.append(current)
        if estimate_tokens(sentence) <= size:
            current = sentence
        else:
            words, current = sentence.split(), ""
            for word in words:
                candidate = f"{current} {word}".strip()
                if estimate_tokens(candidate) <= size:
                    current = candidate
                else:
                    if current:
                        out.append(current)
                    current = word
    if current:
        out.append(current)
    return out


def _overlap_tail(text: str, overlap: int) -> str:
    """Derniers mots d'un fragment, pour servir de préambule au suivant."""
    if overlap <= 0:
        return ""
    words = text.split()
    tail = words[-overlap:] if len(words) > overlap else words
    return " ".join(tail)


def chunk_document(
    contenu: str,
    *,
    size: int = 800,
    overlap: int = 100,
    document_id: int | None = None,
    titre: str | None = None,
    extra_meta: dict[str, Any] | None = None,
) -> list[ChunkDraft]:
    """Découpe un document en fragments indexables."""
    drafts: list[ChunkDraft] = []
    ordinal = 0

    for section_title, section_body in split_sections(contenu):
        buffer: list[str] = []
        buffer_tokens = 0
        tail = ""

        def flush(section_title: str = section_title) -> None:
            nonlocal ordinal, buffer, buffer_tokens, tail
            if not buffer:
                return
            body = "\n\n".join(buffer).strip()
            if body:
                # Le titre de section est préfixé au fragment : il porte le
                # sens (les mots du titre sont souvent ceux de la question)
                # et il est restitué dans les citations.
                texte = f"{section_title}\n\n{body}" if section_title else body
                drafts.append(
                    ChunkDraft(
                        ordinal=ordinal,
                        texte=texte,
                        section=section_title,
                        nb_tokens=estimate_tokens(texte),
                        meta={
                            "section": section_title,
                            "titre": titre,
                            "document_id": document_id,
                            **(extra_meta or {}),
                        },
                    )
                )
                ordinal += 1
                tail = _overlap_tail(body, overlap)
            buffer = []
            buffer_tokens = 0

        for paragraph in _paragraphs(section_body):
            for piece in _split_long(paragraph, size):
                piece_tokens = estimate_tokens(piece)
                if buffer and buffer_tokens + piece_tokens > size:
                    flush()
                if not buffer and tail:
                    # On réinjecte la fin du fragment précédent : l'information
                    # située à la frontière n'est pas perdue.
                    buffer.append(tail)
                    buffer_tokens = estimate_tokens(tail)
                buffer.append(piece)
                buffer_tokens += piece_tokens

        flush()

    return drafts
