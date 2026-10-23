"""Tests de la recherche hybride (BM25 + vecteurs, fusion RRF)."""

from __future__ import annotations

from erp_ai.rag.retrieval import BM25, _tokenize


def test_bm25_classe_les_documents_pertains_en_tete() -> None:
    corpus = [
        _tokenize("la procédure de relance client envoie un rappel de courtoisie"),
        _tokenize("le budget de communication_graphique du mois est arrêté"),
        _tokenize("relance client : rappel puis relance ferme puis mise en demeure"),
    ]
    scores = BM25(corpus).scores(_tokenize("relance client"))
    assert scores[0] > scores[1]
    assert scores[2] > scores[1]


def test_recherche_retourne_le_bon_document(service) -> None:
    resultats = service.retriever.search("Comment se déroule l'escalade des relances client ?")
    assert resultats
    titres = [r.titre for r in resultats]
    assert any("Procédure de relance client" in t for t in titres), titres


def test_recherche_cloture_mensuelle(service) -> None:
    resultats = service.retriever.search("Quelles sont les étapes de la clôture mensuelle ?")
    assert resultats
    assert any("clôture comptable" in r.titre for r in resultats)


def test_les_sources_sont_referencees(service) -> None:
    resultats = service.retriever.search("politique de remise commerciale")
    assert [r.source_ref for r in resultats] == [f"S{i}" for i in range(1, len(resultats) + 1)]


def test_filtrage_par_client(service) -> None:
    # Tous les documents de démonstration sont globaux : le filtre ne doit pas
    # casser la recherche, mais les documents rattachés à un autre client
    # doivent être exclus.
    resultats = service.retriever.search("délai de paiement", client_id=1)
    assert resultats
    for item in resultats:
        assert item.client_code in (None, "CLI-001")


def test_recherche_sans_corpus(service) -> None:
    assert service.retriever.search("inexistant", top_k=3) is not None


def test_ingestion_est_idempotente(service) -> None:
    avant = service.retriever.index_documents(force=False)
    assert avant["documents"] == 0
    apres = service.retriever.index_documents(force=True)
    assert apres["documents"] == 5
    assert apres["chunks"] > 10
