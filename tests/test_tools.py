"""Tests des outils métier (impayés, chiffre d'affaires, SQL encadré)."""

from __future__ import annotations

from datetime import date

import pytest

from erp_ai.agents.safe_sql import SqlGuardError
from erp_ai.agents.tools import ErpTools


def test_impayes_excluent_les_factures_payees(engine, settings) -> None:
    tools = ErpTools(engine, settings)
    impayes = tools.impayes()
    assert impayes
    assert all(ligne["statut"] != "PAYE" for ligne in impayes)


def test_le_retard_est_calcule_en_python(engine, settings) -> None:
    tools = ErpTools(engine, settings)
    reference = date(2026, 11, 1)
    impayes = tools.impayes(aujourdhui=reference)
    assert impayes
    for ligne in impayes:
        echeance = date.fromisoformat(ligne["date_echeance"])
        assert ligne["jours_retard"] == (reference - echeance).days


def test_le_seuil_de_retard_est_applique(engine, settings) -> None:
    tools = ErpTools(engine, settings)
    reference = date(2026, 11, 1)
    tous = tools.impayes(aujourdhui=reference)
    filtre = tools.impayes(min_jours=60, aujourdhui=reference)
    assert len(filtre) < len(tous)
    assert all(ligne["jours_retard"] >= 60 for ligne in filtre)


def test_synthese_impayes_est_coherente(engine, settings) -> None:
    tools = ErpTools(engine, settings)
    synthese = tools.synthese_impayes(aujourdhui=date(2026, 11, 1))
    lignes = tools.impayes(aujourdhui=date(2026, 11, 1))
    assert synthese["nb_factures"] == len(lignes)
    assert synthese["total_ttc"] == pytest.approx(
        sum(ligne["montant_ttc"] for ligne in lignes), abs=0.01
    )
    assert sum(synthese["par_tranche"].values()) == pytest.approx(synthese["total_ttc"], abs=0.01)


def test_chiffre_affaires_annuel(engine, settings) -> None:
    tools = ErpTools(engine, settings)
    ca = tools.chiffre_affaires(2026)
    assert ca["total_ht"] > 0
    assert ca["par_client"]
    assert ca["par_client"] == sorted(ca["par_client"], key=lambda r: -r["ca_ht"])


def test_sql_encadre_accepte_une_lecture(engine, settings) -> None:
    tools = ErpTools(engine, settings)
    resultat = tools.run_readonly_sql(
        "SELECT c.raison_sociale, COUNT(*) AS nb FROM facture f "
        "JOIN client c ON c.id = f.client_id GROUP BY c.raison_sociale"
    )
    assert resultat.rowcount > 0
    assert "raison_sociale" in resultat.rows[0]


def test_sql_encadre_refuse_une_ecriture(engine, settings) -> None:
    tools = ErpTools(engine, settings)
    with pytest.raises(SqlGuardError):
        tools.run_readonly_sql("UPDATE facture SET statut = 'PAYE'")


def test_detection_d_intention(engine, settings) -> None:
    from erp_ai.agents.tools import SqlAgent

    agent = SqlAgent(engine, None, settings)
    assert agent.detect_intent("quelles factures sont en retard ?") == "impayes"
    assert agent.detect_intent("quel est le chiffre d'affaires ?") == "ca"
    assert agent.detect_intent("raconte-moi une histoire") is None
