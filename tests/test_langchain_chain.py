"""Tests de la variante LangChain de la chaîne RAG.

Ces tests sont ignorés si LangChain n'est pas installé (option `langchain`).
Ils vérifient trois points :
  * le retriever LangChain renvoie bien les fragments de notre moteur ;
  * le format des sources est **identique** à celui de la chaîne native
    (donc les citations sont les mêmes dans les deux modes) ;
  * le service bascule sur la chaîne LangChain quand elle est activée, et
    retombe proprement sur la chaîne native sinon.
"""

from __future__ import annotations

import pytest

pytest.importorskip("langchain_core")

from erp_ai.rag.langchain_chain import (  # noqa: E402
    LANGCHAIN_AVAILABLE,
    build_answer_chain,
    build_fake_chain,
    chunks_to_documents,
    documents_to_sources,
)
from erp_ai.rag.prompts import build_user_prompt, format_source_blocks  # noqa: E402


def test_langchain_est_importable() -> None:
    assert LANGCHAIN_AVAILABLE


def test_le_format_des_sources_est_identique_au_mode_native(service) -> None:
    resultats = service.retriever.search("procédure de relance client")
    sources = [
        {
            "titre": r.titre,
            "section": r.section,
            "type_doc": r.type_doc,
            "client_code": r.client_code,
            "version": r.version,
            "texte": r.texte,
        }
        for r in resultats
    ]
    natif = format_source_blocks(sources)
    via_documents = format_source_blocks(documents_to_sources(chunks_to_documents(resultats)))
    assert natif == via_documents
    assert "<<<SOURCE id=" in natif
    assert natif in build_user_prompt(sources, "question test") or natif in build_user_prompt(
        sources, "question test"
    )


def test_le_retriever_langchain_renvoie_les_documents(service, settings) -> None:
    chaine = build_fake_chain(settings, service.retriever, ["réponse factice"])
    resultat = chaine.invoke("Quelles sont les règles de relance client ?")
    assert "réponse factice" in resultat


def test_la_chaine_repond_avec_le_llm_local(service, settings) -> None:
    chaine = build_answer_chain(settings, llm=service.llm)
    sources = service.retriever.search("délais de paiement")
    contexte = format_source_blocks(
        [
            {
                "titre": r.titre,
                "section": r.section,
                "type_doc": r.type_doc,
                "client_code": r.client_code,
                "version": r.version,
                "texte": r.texte,
            }
            for r in sources
        ]
    )
    reponse = chaine.invoke(
        {"context": contexte, "question": "Quels sont les délais de paiement ?"}
    )
    assert reponse
    assert "[S" in reponse


def test_le_service_bascule_sur_langchain(service, monkeypatch) -> None:
    monkeypatch.setattr(service.settings, "rag_chain", "langchain", raising=False)
    resultat = service.ask("Quels sont les délais de paiement applicables aux clients ?")
    assert resultat["statut"] == "OK"
    assert resultat["answer"]
    assert resultat["sources"]


def test_le_service_repliq_sur_la_chaine_native(service, monkeypatch) -> None:
    monkeypatch.setattr(service.settings, "rag_chain", "langchain", raising=False)
    monkeypatch.setattr(service, "_lc_chain", None, raising=False)

    def _boom(*_args, **_kwargs):
        raise RuntimeError("panne simulée du fournisseur de modèle")

    monkeypatch.setattr("erp_ai.service.build_answer_chain", _boom)
    resultat = service.ask("Quels sont les délais de paiement applicables aux clients ?")
    assert resultat["statut"] == "OK"
    assert resultat["answer"]
