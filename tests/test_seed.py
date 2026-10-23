"""Intégrité du jeu de données de démonstration.

Ces contrôles sont ceux qu'un client retrouverait dans son ERP : une facture
doit correspondre à la somme de ses lignes, les écritures doivent
s'équilibrer, un règlement doit exister si et seulement si la facture est
soldée. Le pipeline IA ne peut pas propager des données incohérentes.
"""

from __future__ import annotations

import sqlalchemy as sa

from erp_ai.db import models


def test_volumes(engine) -> None:
    with engine.connect() as conn:
        assert conn.execute(sa.select(sa.func.count()).select_from(models.client)).scalar_one() == 8
        assert conn.execute(sa.select(sa.func.count()).select_from(models.article)).scalar_one() == 10
        assert conn.execute(sa.select(sa.func.count()).select_from(models.facture)).scalar_one() == 30
        assert (
            conn.execute(sa.select(sa.func.count()).select_from(models.document)).scalar_one() == 5
        )


def test_facture_egale_somme_des_lignes(engine) -> None:
    with engine.connect() as conn:
        lignes = conn.execute(
            sa.select(
                models.ligne_facture.c.facture_id,
                sa.func.sum(models.ligne_facture.c.montant_ht).label("somme"),
            ).group_by(models.ligne_facture.c.facture_id)
        ).mappings().all()
        sommes = {row["facture_id"]: float(row["somme"]) for row in lignes}
        factures = conn.execute(
            sa.select(models.facture.c.id, models.facture.c.montant_ht)
        ).mappings().all()

    for facture in factures:
        assert round(sommes[facture["id"]], 2) == round(float(facture["montant_ht"]), 2), (
            f"Facture {facture['id']} : montant incohérent avec ses lignes"
        )


def test_ttc_egal_ht_au_dixieme(engine) -> None:
    with engine.connect() as conn:
        rows = conn.execute(
            sa.select(models.facture.c.montant_ht, models.facture.c.montant_ttc)
        ).mappings().all()
    for row in rows:
        ht = float(row["montant_ht"])
        ttc = float(row["montant_ttc"])
        assert abs(round(ht * 1.2, 2) - ttc) < 0.02


def test_reglement_coherent_avec_le_statut(engine) -> None:
    with engine.connect() as conn:
        rows = conn.execute(
            sa.select(
                models.facture.c.id,
                models.facture.c.statut,
                sa.func.count(models.reglement.c.id).label("nb_reglements"),
            )
            .select_from(
                models.facture.outerjoin(
                    models.reglement, models.reglement.c.facture_id == models.facture.c.id
                )
            )
            .group_by(models.facture.c.id)
        ).mappings().all()

    statuts = {row["statut"] for row in rows}
    assert statuts <= {"PAYE", "PARTIEL", "IMPAYE", "RETARD"}
    for row in rows:
        nb = int(row["nb_reglements"])
        if row["statut"] == "PAYE":
            assert nb == 1, "Une facture payée doit avoir exactement un règlement"
        elif row["statut"] == "PARTIEL":
            assert nb == 1, "Une facture partielle doit avoir un règlement partiel"
        else:
            assert nb == 0, "Une facture impayée ne doit avoir aucun règlement"


def test_ecritures_equilibrees(engine) -> None:
    with engine.connect() as conn:
        total_debit = conn.execute(
            sa.select(sa.func.sum(models.ecriture_comptable.c.debit))
        ).scalar_one()
        total_credit = conn.execute(
            sa.select(sa.func.sum(models.ecriture_comptable.c.credit))
        ).scalar_one()
    assert round(float(total_debit), 2) == round(float(total_credit), 2), (
        "La balance des écritures n'est pas équilibrée"
    )


def test_client_inactif_existe_pour_tester_le_rbac(engine) -> None:
    with engine.connect() as conn:
        row = conn.execute(
            sa.select(models.client.c.code, models.client.c.actif).where(
                models.client.c.code == "CLI-008"
            )
        ).mappings().first()
    assert row is not None
    assert not bool(row["actif"])
