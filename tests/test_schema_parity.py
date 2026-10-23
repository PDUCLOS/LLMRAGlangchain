"""Parité entre le schéma Python (models.py) et le schéma SQL Server (T-SQL).

Ce test est le garde-fou contre la dérive du schéma : si une colonne est
ajoutée d'un côté et pas de l'autre, la CI échoue. C'est ce qui permet de
garder un seul schéma pour deux cibles (SQLite en dev, SQL Server en cible).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from erp_ai.db import models

SQL_FILE = Path(__file__).resolve().parents[1] / "sql" / "00_schema.sql"

CREATE_TABLE_RE = re.compile(
    r"CREATE TABLE dbo\.(\w+)\s*\((.*?)\n\);", re.DOTALL | re.IGNORECASE
)
COLUMN_RE = re.compile(r"^([a-z_][a-z0-9_]*)\s+[A-Z]", re.IGNORECASE)


def _parse_sql_tables(text: str) -> dict[str, set[str]]:
    tables: dict[str, set[str]] = {}
    for name, body in CREATE_TABLE_RE.findall(text):
        columns: set[str] = set()
        for line in body.splitlines():
            stripped = line.strip().rstrip(",")
            if not stripped or stripped.upper().startswith("CONSTRAINT"):
                continue
            match = COLUMN_RE.match(stripped)
            if match:
                columns.add(match.group(1).lower())
        tables[name.lower()] = columns
    return tables


@pytest.fixture(scope="module")
def sql_tables() -> dict[str, set[str]]:
    assert SQL_FILE.exists(), f"Schéma T-SQL introuvable : {SQL_FILE}"
    return _parse_sql_tables(SQL_FILE.read_text(encoding="utf-8"))


def test_meme_ensemble_de_tables(sql_tables: dict[str, set[str]]) -> None:
    orm_tables = {name.lower() for name in models.metadata.tables}
    assert orm_tables == set(sql_tables), (
        f"Écart de tables — SQL Server uniquement : {sorted(set(sql_tables) - orm_tables)}, "
        f"ORM uniquement : {sorted(orm_tables - set(sql_tables))}"
    )


def test_memes_colonnes(sql_tables: dict[str, set[str]]) -> None:
    manquantes: list[str] = []
    for table_name, table in models.metadata.tables.items():
        sql_columns = sql_tables.get(table_name.lower(), set())
        for column in table.columns:
            if column.name.lower() not in sql_columns:
                manquantes.append(f"{table_name}.{column.name}")
    assert not manquantes, f"Colonnes absentes du schéma T-SQL : {manquantes}"


def test_vues_metier_presentes() -> None:
    texte = SQL_FILE.read_text(encoding="utf-8")
    for vue in ("vw_impayes", "vw_ca_client", "vw_tranche_anciennete"):
        assert f"CREATE VIEW dbo.{vue}" in texte, f"Vue manquante : {vue}"
    assert "CREATE PROCEDURE dbo.usp_get_impayes" in texte
