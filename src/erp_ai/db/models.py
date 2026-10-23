"""Schéma relationnel — source de vérité unique.

Le même schéma est créé par `metadata.create_all()` (dev portable, SQLite ou
SQL Server) et par `sql/00_schema.sql` (T-SQL enrichi : vues, procédures
stockées, index). Un test de parité (`tests/test_schema_parity.py`) vérifie
que les deux ne divergent pas.

Conventions :
  * tables métier ERP  : client, article, facture, ligne_facture, reglement,
                          ecriture_comptable
  * tables IA          : document, chunk, ingestion_log, ai_usage_log,
                          conversation
"""

from __future__ import annotations

import sqlalchemy as sa

metadata = sa.MetaData()

# ---------------------------------------------------------------------------
# ERP — référentiel de gestion
# ---------------------------------------------------------------------------

client = sa.Table(
    "client",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("code", sa.String(20), nullable=False, unique=True),
    sa.Column("raison_sociale", sa.String(160), nullable=False),
    sa.Column("secteur", sa.String(80)),
    sa.Column("pays", sa.String(60)),
    sa.Column("ville", sa.String(80)),
    sa.Column("encours_autorise", sa.Numeric(18, 2), nullable=False, server_default="0"),
    sa.Column("actif", sa.Boolean, nullable=False, server_default=sa.text("1")),
    sa.Column("date_creation", sa.DateTime, nullable=False),
)

article = sa.Table(
    "article",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("code", sa.String(30), nullable=False, unique=True),
    sa.Column("designation", sa.String(200), nullable=False),
    sa.Column("famille", sa.String(80)),
    sa.Column("unite", sa.String(20), nullable=False, server_default="U"),
    sa.Column("prix_unitaire_ht", sa.Numeric(18, 2), nullable=False, server_default="0"),
    sa.Column("tva_taux", sa.Numeric(5, 2), nullable=False, server_default="20"),
    sa.Column("stock_actuel", sa.Integer, nullable=False, server_default="0"),
    sa.Column("actif", sa.Boolean, nullable=False, server_default=sa.text("1")),
)

facture = sa.Table(
    "facture",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("numero", sa.String(30), nullable=False, unique=True),
    sa.Column("client_id", sa.Integer, sa.ForeignKey("client.id"), nullable=False),
    sa.Column("date_emission", sa.DateTime, nullable=False),
    sa.Column("date_echeance", sa.DateTime, nullable=False),
    sa.Column("montant_ht", sa.Numeric(18, 2), nullable=False, server_default="0"),
    sa.Column("montant_ttc", sa.Numeric(18, 2), nullable=False, server_default="0"),
    sa.Column("statut", sa.String(20), nullable=False, server_default="IMPAYE"),
    sa.Column("devise", sa.String(3), nullable=False, server_default="EUR"),
    sa.Column("commentaire", sa.String(400)),
)

ligne_facture = sa.Table(
    "ligne_facture",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("facture_id", sa.Integer, sa.ForeignKey("facture.id"), nullable=False),
    sa.Column("article_id", sa.Integer, sa.ForeignKey("article.id"), nullable=False),
    sa.Column("quantite", sa.Numeric(18, 3), nullable=False, server_default="0"),
    sa.Column("prix_unitaire_ht", sa.Numeric(18, 2), nullable=False, server_default="0"),
    sa.Column("montant_ht", sa.Numeric(18, 2), nullable=False, server_default="0"),
)

reglement = sa.Table(
    "reglement",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("facture_id", sa.Integer, sa.ForeignKey("facture.id"), nullable=False),
    sa.Column("date_reglement", sa.DateTime, nullable=False),
    sa.Column("montant", sa.Numeric(18, 2), nullable=False, server_default="0"),
    sa.Column("mode", sa.String(20), nullable=False, server_default="VIREMENT"),
)

ecriture_comptable = sa.Table(
    "ecriture_comptable",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("journal", sa.String(10), nullable=False, server_default="VE"),
    sa.Column("compte", sa.String(20), nullable=False),
    sa.Column("libelle", sa.String(200), nullable=False),
    sa.Column("date_ecriture", sa.DateTime, nullable=False),
    sa.Column("debit", sa.Numeric(18, 2), nullable=False, server_default="0"),
    sa.Column("credit", sa.Numeric(18, 2), nullable=False, server_default="0"),
    sa.Column("piece", sa.String(30)),
)

# ---------------------------------------------------------------------------
# IA — documents, fragments, exploitation
# ---------------------------------------------------------------------------

document = sa.Table(
    "document",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("source", sa.String(60), nullable=False),  # sharepoint | erp | fichier
    sa.Column("type_doc", sa.String(60), nullable=False),  # procedure | contrat | manuel
    sa.Column("titre", sa.String(250), nullable=False),
    sa.Column("client_id", sa.Integer, sa.ForeignKey("client.id")),
    sa.Column("date_doc", sa.DateTime),
    sa.Column("chemin", sa.String(400)),
    sa.Column("hash", sa.String(64), nullable=False, unique=True),
    sa.Column("version", sa.String(20), nullable=False, server_default="1.0"),
    sa.Column("date_ingestion", sa.DateTime, nullable=False),
    sa.Column("contenu", sa.Text, nullable=False),
)

chunk = sa.Table(
    "chunk",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("document_id", sa.Integer, sa.ForeignKey("document.id"), nullable=False),
    sa.Column("ordinal", sa.Integer, nullable=False),
    sa.Column("texte", sa.Text, nullable=False),
    sa.Column("section", sa.String(250)),
    sa.Column("page", sa.Integer),
    sa.Column("nb_tokens", sa.Integer, nullable=False, server_default="0"),
    sa.Column("meta", sa.JSON),
    sa.Column("hash", sa.String(64), nullable=False),
)

ingestion_log = sa.Table(
    "ingestion_log",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("document_id", sa.Integer, sa.ForeignKey("document.id")),
    sa.Column("statut", sa.String(20), nullable=False),  # OK | KO | PARTIEL
    sa.Column("message", sa.String(500)),
    sa.Column("nb_chunks", sa.Integer, nullable=False, server_default="0"),
    sa.Column("debut", sa.DateTime, nullable=False),
    sa.Column("fin", sa.DateTime),
)

ai_usage_log = sa.Table(
    "ai_usage_log",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("horodatage", sa.DateTime, nullable=False),
    sa.Column("request_id", sa.String(40), nullable=False),
    sa.Column("user_role", sa.String(30)),
    sa.Column("client_id", sa.Integer),
    sa.Column("provider", sa.String(30), nullable=False),
    sa.Column("modele", sa.String(60), nullable=False),
    sa.Column("tokens_in", sa.Integer, nullable=False, server_default="0"),
    sa.Column("tokens_out", sa.Integer, nullable=False, server_default="0"),
    sa.Column("cout_eur", sa.Numeric(12, 6), nullable=False, server_default="0"),
    sa.Column("latence_ms", sa.Integer, nullable=False, server_default="0"),
    sa.Column("question", sa.String(1000)),
    sa.Column("statut", sa.String(20), nullable=False, server_default="OK"),
)

conversation = sa.Table(
    "conversation",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("request_id", sa.String(40), nullable=False),
    sa.Column("role", sa.String(30)),
    sa.Column("client_id", sa.Integer),
    sa.Column("question", sa.Text, nullable=False),
    sa.Column("reponse", sa.Text, nullable=False),
    sa.Column("sources", sa.JSON),
    sa.Column("feedback", sa.Integer),
    sa.Column("cree_le", sa.DateTime, nullable=False),
)


# ---------------------------------------------------------------------------
# Vues applicatives (forme SQL portable, cf. sql/00_schema.sql pour la version
# T-SQL enrichie). Définies ici pour éviter toute dépendance à un dialecte.
# ---------------------------------------------------------------------------

VW_IMPAYES = sa.text(
    """
    SELECT f.numero                AS numero,
           f.montant_ttc           AS montant_ttc,
           f.date_echeance         AS date_echeance,
           f.statut                AS statut,
           c.id                    AS client_id,
           c.code                  AS client_code,
           c.raison_sociale        AS raison_sociale
      FROM facture f
      JOIN client c ON c.id = f.client_id
     WHERE f.statut <> 'PAYE'
     ORDER BY f.date_echeance
    """
)
