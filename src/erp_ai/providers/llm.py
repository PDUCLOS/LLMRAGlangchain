"""LLM : Azure OpenAI en cible, Ollama sur GPU local, extractif déterministe en test.

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
        return f"D'après les documents disponibles :\n{corps}\n\nSources : {refs}."


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


class OllamaChatLLM:
    """Complétion via un serveur Ollama (modèle open-weight sur GPU local).

    Après chaque appel, `last_usage` contient les compteurs réels renvoyés
    par Ollama (tokens d'entrée / sortie, temps de chargement, de traitement
    du prompt et de génération) : c'est la base des métriques LLMOps.
    """

    def __init__(self, settings: Settings) -> None:
        import httpx

        self.name = "ollama"
        self.model = settings.ollama_chat_model
        self._num_ctx = settings.ollama_num_ctx
        self._client = httpx.Client(
            base_url=settings.ollama_base_url, timeout=settings.ollama_timeout_s
        )
        self.last_usage: dict[str, float] | None = None

    def complete(self, system: str, user: str, *, temperature: float = 0.0) -> str:
        response = self._client.post(
            "/api/chat",
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "stream": False,
                "think": False,
                "options": {"temperature": temperature, "num_ctx": self._num_ctx, "seed": 42},
            },
        )
        response.raise_for_status()
        data = response.json()
        self.last_usage = ollama_usage(data)
        return (data.get("message") or {}).get("content", "").strip()


def ollama_usage(data: dict) -> dict[str, float]:
    """Extrait les compteurs d'une réponse Ollama (durées en ns -> ms)."""
    eval_count = int(data.get("eval_count") or 0)
    eval_ms = (data.get("eval_duration") or 0) / 1e6
    return {
        "tokens_in": int(data.get("prompt_eval_count") or 0),
        "tokens_out": eval_count,
        "load_ms": round((data.get("load_duration") or 0) / 1e6, 1),
        "prompt_ms": round((data.get("prompt_eval_duration") or 0) / 1e6, 1),
        "eval_ms": round(eval_ms, 1),
        "tokens_per_s": round(eval_count / (eval_ms / 1000), 1) if eval_ms else 0.0,
    }


def build_llm(settings: Settings | None = None) -> ChatLLM:
    """Construit le LLM selon la configuration."""
    settings = settings or get_settings()
    provider = settings.llm_provider.lower()
    if provider == "azure":
        return AzureChatLLM(settings)
    if provider == "ollama":
        return OllamaChatLLM(settings)
    return ExtractiveLocalLLM()
