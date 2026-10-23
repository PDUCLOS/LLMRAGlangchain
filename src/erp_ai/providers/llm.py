"""LLM : Azure OpenAI en cible, extractif déterministe en local.

L'implémentation locale n'est pas un modèle de langage : elle compose une
réponse à partir des passages fournis, avec les mêmes citations et le même
format que le chemin Azure. Elle sert à démontrer la mécanique (ancrage,
citations, refus, mesure des coûts) sans dépendance cloud.

Le basculement local -> Azure se fait uniquement par variable d'environnement.
"""

from __future__ import annotations

import re
from typing import Protocol

from erp_ai.config import Settings, get_settings

SOURCE_BLOCK_RE = re.compile(
    r"<<<SOURCE id=\"?(?P<id>\d+)\"?(?P<attrs>[^>]*)>>>\n(?P<text>.*?)\n<<<END SOURCE>>>",
    re.DOTALL,
)
QUESTION_RE = re.compile(r"\[QUESTION\]\n(?P<q>.*?)\n\[/QUESTION\]", re.DOTALL)
ATTR_RE = re.compile(r'(\w+)="([^"]*)"')


class ChatLLM(Protocol):
    """Interface commune des fournisseurs de complétion."""

    name: str
    model: str

    def complete(self, system: str, user: str, *, temperature: float = 0.0) -> str: ...


class ExtractiveLocalLLM:
    """Réponse extractive déterministe, ancrée sur les passages fournis.

    Principe : on ne reformule pas, on sélectionne les phrases les plus
    proches de la question parmi les passages reçus, puis on restitue la
    citation. Comportement volontairement conservateur : si aucun passage ne
    mentionne de terme significatif de la question, la réponse est un refus.
    """

    name = "local-extractive"
    model = "extractive-v1"

    def complete(self, system: str, user: str, *, temperature: float = 0.0) -> str:
        sources = [
            {
                "id": m.group("id"),
                "attrs": dict(ATTR_RE.findall(m.group("attrs"))),
                "text": m.group("text").strip(),
            }
            for m in SOURCE_BLOCK_RE.finditer(user)
        ]
        q_match = QUESTION_RE.search(user)
        question = q_match.group("q").strip() if q_match else ""

        if not sources:
            return (
                "Je n'ai pas de source documentaire permettant de répondre à cette "
                "question. Aucune donnée n'a été inventée."
            )

        terms = {t.lower() for t in re.findall(r"[\wÀ-ÿ]{4,}", question)}
        scored: list[tuple[int, str, str]] = []
        for src in sources:
            for sentence in re.split(r"(?<=[.!?])\s+", src["text"]):
                sent_terms = {t.lower() for t in re.findall(r"[\wÀ-ÿ]{4,}", sentence)}
                overlap = len(terms & sent_terms)
                if overlap:
                    scored.append((overlap, sentence.strip(), src["id"]))

        if not scored:
            return (
                "Les sources disponibles ne permettent pas de répondre précisément à "
                "cette question. Je préfère ne rien avancer plutôt que d'inventer un "
                "élément absent des documents."
            )

        scored.sort(key=lambda item: (-item[0], item[1]))
        best = scored[0][0]
        retenues = [s for s in scored if s[0] >= max(1, best // 2)][:4]

        lignes = []
        for _score, phrase, src_id in retenues:
            lignes.append(f"- {phrase} [S{src_id}]")
        corps = "\n".join(lignes)
        refs = ", ".join("S" + s["id"] for s in sources)
        return (
            "D'après les documents disponibles :\n"
            f"{corps}\n\n"
            f"Sources : {refs}."
        )


class AzureChatLLM:
    """Complétion Azure OpenAI (déploiement Azure AI Foundry)."""

    def __init__(self, settings: Settings) -> None:
        from openai import AzureOpenAI  # import tardif : optionnel

        self.name = "azure-openai"
        self.model = settings.azure_openai_chat_deployment
        self._client = AzureOpenAI(
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_api_version,
        )

    def complete(self, system: str, user: str, *, temperature: float = 0.0) -> str:
        response = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
        )
        return response.choices[0].message.content or ""


def build_llm(settings: Settings | None = None) -> ChatLLM:
    """Construit le LLM selon la configuration."""
    settings = settings or get_settings()
    if settings.llm_provider.lower() == "azure":
        return AzureChatLLM(settings)
    return ExtractiveLocalLLM()
