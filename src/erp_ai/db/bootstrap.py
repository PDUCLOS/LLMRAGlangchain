"""Création du schéma et chargement du jeu de données de démonstration.

`init_db()` est idempotent : si des clients existent déjà, il ne recharge
rien. Le seed produit un jeu cohérent (somme des lignes = montant HT de la
facture, écritures en partie double, règlements cohérents avec le statut).
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.engine import Engine

from erp_ai.db import demo_data, models

TVA = Decimal("1.20")


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def init_db(engine: Engine) -> dict[str, int]:
    """Crée les tables si besoin puis charge le jeu de démonstration."""
    models.metadata.create_all(engine)
    return seed(engine)


def seed(engine: Engine) -> dict[str, int]:
    """Charge le jeu de démonstration (no-op si déjà chargé)."""
    with engine.begin() as conn:
        deja = conn.execute(sa.select(sa.func.count()).select_from(models.client)).scalar_one()
        if deja:
            return {"skipped": True, "clients": deja}  # type: ignore[dict-item]

        now = datetime.now()

        # --- Clients ------------------------------------------------------
        client_ids: dict[str, int] = {}
        for code, raison, secteur, pays, ville, encours, actif in demo_data.CLIENTS:
            res = conn.execute(
                models.client.insert().values(
                    code=code,
                    raison_sociale=raison,
                    secteur=secteur,
                    pays=pays,
                    ville=ville,
                    encours_autorise=Decimal(str(encours)),
                    actif=actif,
                    date_creation=now,
                )
            )
            client_ids[code] = int(res.inserted_primary_key[0])

        # --- Articles -----------------------------------------------------
        article_ids: dict[str, int] = {}
        for code, designation, famille, unite, prix, tva, stock in demo_data.ARTICLES:
            res = conn.execute(
                models.article.insert().values(
                    code=code,
                    designation=designation,
                    famille=famille,
                    unite=unite,
                    prix_unitaire_ht=Decimal(str(prix)),
                    tva_taux=Decimal(str(tva)),
                    stock_actuel=stock,
                    actif=True,
                )
            )
            article_ids[code] = int(res.inserted_primary_key[0])

        prix = {c: Decimal(str(p)) for c, _d, _f, _u, p, _t, _s in demo_data.ARTICLES}

        # --- Factures, lignes, règlements, écritures ----------------------
        nb_factures = nb_lignes = nb_reglements = nb_ecritures = 0
        for idx, (numero, code_client, date_emission, delai, statut) in enumerate(
            demo_data.FACTURES
        ):
            date_emp = demo_data._dt(date_emission)
            date_eche = demo_data._add_days(date_emission, delai)

            montant_ht = Decimal("0")
            lignes = []
            for art_code, qte in demo_data._lignes(idx):
                pu = prix[art_code]
                montant = (pu * Decimal(str(qte))).quantize(Decimal("0.01"))
                montant_ht += montant
                lignes.append((art_code, Decimal(str(qte)), pu, montant))

            montant_ht = montant_ht.quantize(Decimal("0.01"))
            montant_ttc = (montant_ht * TVA).quantize(Decimal("0.01"))

            res = conn.execute(
                models.facture.insert().values(
                    numero=numero,
                    client_id=client_ids[code_client],
                    date_emission=date_emp,
                    date_echeance=date_eche,
                    montant_ht=montant_ht,
                    montant_ttc=montant_ttc,
                    statut=statut,
                    devise="EUR",
                    commentaire=None,
                )
            )
            facture_id = int(res.inserted_primary_key[0])
            nb_factures += 1

            for art_code, qte, pu, montant in lignes:
                conn.execute(
                    models.ligne_facture.insert().values(
                        facture_id=facture_id,
                        article_id=article_ids[art_code],
                        quantite=qte,
                        prix_unitaire_ht=pu,
                        montant_ht=montant,
                    )
                )
                nb_lignes += 1

            # Règlements : total si PAYE, partiel si PARTIEL, aucun sinon.
            if statut == "PAYE":
                conn.execute(
                    models.reglement.insert().values(
                        facture_id=facture_id,
                        date_reglement=demo_data._add_days(date_emission, delai - 2),
                        montant=montant_ttc,
                        mode="VIREMENT",
                    )
                )
                nb_reglements += 1
            elif statut == "PARTIEL":
                conn.execute(
                    models.reglement.insert().values(
                        facture_id=facture_id,
                        date_reglement=demo_data._add_days(date_emission, 20),
                        montant=(montant_ttc * Decimal("0.6")).quantize(Decimal("0.01")),
                        mode="VIREMENT",
                    )
                )
                nb_reglements += 1

            # Écritures en partie double : 411 D (TTC) / 706 C (HT) / 44571 C (TVA).
            ecritures = [
                ("VE", "411000", f"Client {code_client} - {numero}", montant_ttc, Decimal("0"), numero),
                ("VE", "706000", f"Ventes {numero}", Decimal("0"), montant_ht, numero),
                ("VE", "445710", f"TVA collectée {numero}", Decimal("0"), montant_ttc - montant_ht, numero),
            ]
            for journal, compte, libelle, debit, credit, piece in ecritures:
                conn.execute(
                    models.ecriture_comptable.insert().values(
                        journal=journal,
                        compte=compte,
                        libelle=libelle,
                        date_ecriture=date_emp,
                        debit=debit,
                        credit=credit,
                        piece=piece,
                    )
                )
                nb_ecritures += 1

        # --- Corpus documentaire ------------------------------------------
        nb_docs = 0
        for doc in demo_data.documents():
            conn.execute(
                models.document.insert().values(
                    source=doc["source"],
                    type_doc=doc["type_doc"],
                    titre=doc["titre"],
                    client_id=doc["client_id"],
                    date_doc=doc["date_doc"],
                    chemin=doc["chemin"],
                    hash=_hash(doc["contenu"]),
                    version=doc["version"],
                    date_ingestion=now,
                    contenu=doc["contenu"],
                )
            )
            nb_docs += 1

    return {
        "clients": len(demo_data.CLIENTS),
        "articles": len(demo_data.ARTICLES),
        "factures": nb_factures,
        "lignes_facture": nb_lignes,
        "reglements": nb_reglements,
        "ecritures_comptables": nb_ecritures,
        "documents": nb_docs,
    }
