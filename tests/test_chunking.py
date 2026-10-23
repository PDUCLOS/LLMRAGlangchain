"""Tests du découpage documentaire (structure, taille, chevauchement)."""

from __future__ import annotations

from erp_ai.db.demo_data import DOC_PROCEDURE_RELANCE
from erp_ai.rag.chunking import chunk_document, estimate_tokens, split_sections


def test_les_titres_sont_isoles() -> None:
    sections = split_sections(DOC_PROCEDURE_RELANCE)
    titres = [titre for titre, _ in sections]
    assert "3. Escalade de la relance" in titres
    assert "2. Règle des délais de paiement" in titres
    assert "Procédure de relance client" in titres


def test_les_fragments_respectent_la_taille_avec_chevauchement() -> None:
    size, overlap = 200, 30
    drafts = chunk_document(DOC_PROCEDURE_RELANCE, size=size, overlap=overlap)
    assert len(drafts) > 1
    for draft in drafts:
        assert draft.nb_tokens <= size + overlap + 20, (
            f"Fragment trop long ({draft.nb_tokens} tokens) : {draft.texte[:80]}…"
        )
        assert draft.texte.strip()


def test_les_fragments_sont_ordonnes_et_numerotes() -> None:
    drafts = chunk_document(DOC_PROCEDURE_RELANCE, size=200, overlap=30)
    assert [d.ordinal for d in drafts] == list(range(len(drafts)))


def test_le_chevauchement_est_present_au_sein_d_une_section() -> None:
    """Le chevauchement évite de perdre l'information à la frontière.

    Il est appliqué entre deux fragments consécutifs d'une même section :
    on ne mélange jamais deux sections différentes.
    """
    drafts = chunk_document(DOC_PROCEDURE_RELANCE, size=80, overlap=20)
    paires = [(a, b) for a, b in zip(drafts, drafts[1:], strict=False) if a.section == b.section]
    assert paires, "Aucune paire de fragments consécutifs dans la même section"
    for premier, second in paires:
        queue_premier = premier.texte.split()[-10:]
        assert " ".join(queue_premier) in second.texte, (
            "Le chevauchement devrait être repris au début du fragment suivant"
        )


def test_les_metadonnees_sont_conservees() -> None:
    drafts = chunk_document(
        DOC_PROCEDURE_RELANCE,
        size=200,
        overlap=30,
        document_id=7,
        titre="Procédure de relance client",
        extra_meta={"type_doc": "procedure"},
    )
    for draft in drafts:
        assert draft.meta["document_id"] == 7
        assert draft.meta["titre"] == "Procédure de relance client"
        assert draft.meta["type_doc"] == "procedure"
        assert draft.section


def test_estimation_de_tokens() -> None:
    assert estimate_tokens("") == 0
    assert estimate_tokens("un deux trois") == 3
    assert estimate_tokens("Facture n°2026-0042 : 1 250,00 EUR.") > 5


def test_un_document_vide_ne_produit_aucun_fragment() -> None:
    assert chunk_document("", size=200, overlap=30) == []
