"""Tests des outils métier (impayés, chiffre d'affaires, SQL encadré)."""

from __future__ import annotations

from datetime import date

import pytest

from erp_ai.agents.safe_sql import SqlGuardError, validate_readonly_sql
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


def test_seuil_de_retard_extrait_de_la_question() -> None:
    from erp_ai.agents.tools import SqlAgent

    assert SqlAgent.extract_min_jours("Factures en retard au-delà de 60 jours ?") == 60
    assert SqlAgent.extract_min_jours("impayés depuis plus de 90 jours") == 90
    assert SqlAgent.extract_min_jours("retard supérieur à 30 j") == 30
    assert SqlAgent.extract_min_jours("quelles factures sont en retard ?") == 0


def test_agent_impayes_applique_le_seuil_de_la_question(engine, settings) -> None:
    from erp_ai.agents.tools import SqlAgent

    agent = SqlAgent(engine, None, settings)
    reference = date(2026, 11, 1)
    resultat = agent.run(
        "Quelles factures sont en retard de paiement au-delà de 60 jours ?",
        aujourdhui=reference,
    )
    attendu = ErpTools(engine, settings).impayes(min_jours=60, aujourdhui=reference)
    assert resultat.rowcount == len(attendu) > 0
    assert resultat.meta["min_jours"] == 60
    # La lecture reste une requête SQL validée par le garde-fou.
    assert resultat.sql == validate_readonly_sql(resultat.sql, settings.allowed_tables)
    assert all(ligne["jours_retard"] >= 60 for ligne in resultat.rows)
    assert {ligne["numero"] for ligne in resultat.rows} == {a["numero"] for a in attendu}


def test_agent_impayes_expose_l_anciennete(engine, settings) -> None:
    from erp_ai.agents.tools import SqlAgent

    agent = SqlAgent(engine, None, settings)
    resultat = agent.run("factures en retard au-delà de 30 jours", aujourdhui=date(2026, 11, 1))
    assert resultat.rows
    for colonne in ("numero", "client", "montant_ttc", "date_echeance", "jours_retard"):
        assert colonne in resultat.rows[0]


def test_agent_impayes_sans_seuil_renvoie_tous_les_impayes(engine, settings) -> None:
    from erp_ai.agents.tools import SqlAgent

    agent = SqlAgent(engine, None, settings)
    reference = date(2026, 11, 1)
    resultat = agent.run("quelles factures sont en retard ?", aujourdhui=reference)
    assert resultat.meta["min_jours"] == 0
    assert resultat.rowcount == len(ErpTools(engine, settings).impayes(aujourdhui=reference))
