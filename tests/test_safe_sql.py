"""Tests du garde-fou SQL (lecture seule stricte)."""

from __future__ import annotations

import pytest

from erp_ai.agents.safe_sql import SqlGuardError, validate_readonly_sql

ALLOWED = {"client", "article", "facture", "ligne_facture", "reglement", "ecriture_comptable"}


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM client",
        "SELECT c.raison_sociale, SUM(f.montant_ht) FROM facture f JOIN client c ON c.id=f.client_id GROUP BY c.raison_sociale",
        "WITH imp AS (SELECT * FROM facture) SELECT * FROM imp",
        "SELECT COUNT(*) FROM ecriture_comptable WHERE journal = 'VE'",
    ],
)
def test_les_lectures_sont_acceptees(sql: str) -> None:
    assert validate_readonly_sql(sql, ALLOWED)


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE client SET encours_autorise = 0",
        "DELETE FROM facture",
        "DROP TABLE client",
        "INSERT INTO client (code) VALUES ('X')",
        "TRUNCATE TABLE facture",
        "EXEC sp_executesql N'SELECT 1'",
        "SELECT * FROM client; DELETE FROM client",
        "SELECT * INTO backup_client FROM client",
        "SELECT * FROM sys.tables",
    ],
)
def test_les_ecritures_et_les_risques_sont_bloques(sql: str) -> None:
    with pytest.raises(SqlGuardError):
        validate_readonly_sql(sql, ALLOWED)


def test_les_tables_non_autorisees_sont_bloquees() -> None:
    with pytest.raises(SqlGuardError, match="non autorisée"):
        validate_readonly_sql("SELECT * FROM salaries", ALLOWED)


def test_une_requete_vide_est_refusee() -> None:
    with pytest.raises(SqlGuardError):
        validate_readonly_sql("   ", ALLOWED)


def test_le_point_virgule_final_est_accepte() -> None:
    assert validate_readonly_sql("SELECT * FROM client;", ALLOWED) == "SELECT * FROM client"
