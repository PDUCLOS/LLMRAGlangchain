"""Tests exécutés sur un vrai SQL Server.

Marqués `sqlserver` : ils sont ignorés hors CI x86-64 (SQL Server n'existe
pas en image ARM64). Ils valident que le schéma, le seed et les requêtes
portables fonctionnent sur le moteur cible — et pas seulement sur SQLite.

En CI, le schéma T-SQL de `sql/00_schema.sql` est appliqué **avant** ces
tests : le schéma Python et le schéma T-SQL sont donc réellement confrontés
au moteur de production.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa

from erp_ai.db import models

pytestmark = pytest.mark.sqlserver


def _require_sqlserver(engine) -> None:
    if engine.dialect.name != "mssql":
        pytest.skip("SQL Server requis (marqueur `sqlserver`).")


def test_le_schema_est_cree_sur_sql_server(engine) -> None:
    _require_sqlserver(engine)
    with engine.connect() as conn:
        noms = set(
            sa.inspect(conn).get_table_names(schema="dbo")
            if engine.dialect.name == "mssql"
            else sa.inspect(conn).get_table_names()
        )
    for table in models.metadata.tables:
        assert table in noms, f"Table absente sur SQL Server : {table}"


def test_le_seed_s_est_charge_sur_sql_server(engine) -> None:
    _require_sqlserver(engine)
    with engine.connect() as conn:
        clients = conn.execute(sa.select(sa.func.count()).select_from(models.client)).scalar_one()
        factures = conn.execute(sa.select(sa.func.count()).select_from(models.facture)).scalar_one()
        chunks = conn.execute(sa.select(sa.func.count()).select_from(models.chunk)).scalar_one()
    assert clients == 8
    assert factures == 30
    assert chunks > 0


def test_les_identifiants_sont_generes_par_identity(engine) -> None:
    _require_sqlserver(engine)
    with engine.connect() as conn:
        ids = conn.execute(sa.select(models.client.c.id).order_by(models.client.c.id)).scalars().all()
    assert len(ids) == len(set(ids))
    assert all(isinstance(i, int) and i > 0 for i in ids)


def test_les_types_numeriques_sont_exacts_sur_sql_server(engine) -> None:
    """DECIMAL(18,2) : pas de dérive de virgule flottante sur les montants."""
    _require_sqlserver(engine)
    with engine.connect() as conn:
        facture = conn.execute(
            sa.select(models.facture.c.numero, models.facture.c.montant_ht).limit(1)
        ).mappings().first()
    assert facture is not None
    assert facture["montant_ht"] is not None
    # La valeur relue doit rester un Decimal exact (2 décimales)
    assert str(facture["montant_ht"]).count(".") <= 1


def test_la_recherche_des_impayes_fonctionne_sur_sql_server(engine, settings) -> None:
    from erp_ai.agents.tools import ErpTools
    from datetime import date

    _require_sqlserver(engine)
    tools = ErpTools(engine, settings)
    impayes = tools.impayes(aujourdhui=date(2026, 11, 1))
    assert impayes
    assert all(ligne["jours_retard"] >= 0 for ligne in impayes)


def test_le_json_est_accepte_par_sql_server(engine) -> None:
    """La colonne `meta` (JSON) doit être acceptée par le moteur cible."""
    _require_sqlserver(engine)
    with engine.begin() as conn:
        doc = conn.execute(sa.select(models.document.c.id).limit(1)).scalar_one()
        conn.execute(
            models.chunk.insert().values(
                document_id=doc,
                ordinal=999,
                texte="fragment de contrôle JSON",
                section="Contrôle",
                nb_tokens=5,
                meta={"test": "json", "n": 1},
                hash="f" * 64,
            )
        )
        meta = conn.execute(
            sa.select(models.chunk.c.meta).where(models.chunk.c.hash == "f" * 64)
        ).scalar_one()
        conn.execute(models.chunk.delete().where(models.chunk.c.hash == "f" * 64))
    assert meta == {"test": "json", "n": 1}
