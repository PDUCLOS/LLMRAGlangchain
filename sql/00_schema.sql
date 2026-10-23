-- ===========================================================================
-- erp-ai-copilot — Schéma SQL Server (cible)
--
-- Rôle de ce fichier : version de référence « production » du schéma, avec
-- l'infrastructure SQL Server que SQLAlchemy ne sait pas déclarer :
--   * identity(1,1) explicite ;
--   * vues métier (vw_impayes, vw_ca_client, vw_tranche_anciennete) ;
--   * procédure stockée de relance (usp_get_impayes) ;
--   * index ciblés et contraintes de cohérence.
--
-- La source de vérité applicative reste `src/erp_ai/db/models.py` ; un test
-- (tests/test_schema_parity.py) vérifie que les deux ne divergent pas.
--
-- Exécution : sqlcmd -S localhost -U sa -P <mot de passe> -i sql/00_schema.sql
-- ===========================================================================

IF OBJECT_ID('dbo.vw_tranche_anciennete', 'V') IS NOT NULL DROP VIEW dbo.vw_tranche_anciennete;
IF OBJECT_ID('dbo.vw_ca_client', 'V') IS NOT NULL DROP VIEW dbo.vw_ca_client;
IF OBJECT_ID('dbo.vw_impayes', 'V') IS NOT NULL DROP VIEW dbo.vw_impayes;
IF OBJECT_ID('dbo.usp_get_impayes', 'P') IS NOT NULL DROP PROCEDURE dbo.usp_get_impayes;

-- ---------------------------------------------------------------------------
-- ERP — référentiel de gestion
-- ---------------------------------------------------------------------------
IF OBJECT_ID('dbo.client', 'U') IS NOT NULL DROP TABLE dbo.client;
CREATE TABLE dbo.client (
    id                INT             IDENTITY(1,1) NOT NULL,
    code              NVARCHAR(20)    NOT NULL,
    raison_sociale   NVARCHAR(160)   NOT NULL,
    secteur           NVARCHAR(80)    NULL,
    pays              NVARCHAR(60)    NULL,
    ville             NVARCHAR(80)    NULL,
    encours_autorise  DECIMAL(18,2)   NOT NULL CONSTRAINT DF_client_encours DEFAULT (0),
    actif             BIT             NOT NULL CONSTRAINT DF_client_actif DEFAULT (1),
    date_creation     DATETIME2       NOT NULL,
    CONSTRAINT PK_client PRIMARY KEY (id),
    CONSTRAINT UQ_client_code UNIQUE (code)
);

IF OBJECT_ID('dbo.article', 'U') IS NOT NULL DROP TABLE dbo.article;
CREATE TABLE dbo.article (
    id                 INT             IDENTITY(1,1) NOT NULL,
    code               NVARCHAR(30)    NOT NULL,
    designation        NVARCHAR(200)   NOT NULL,
    famille            NVARCHAR(80)    NULL,
    unite              NVARCHAR(20)    NOT NULL CONSTRAINT DF_article_unite DEFAULT ('U'),
    prix_unitaire_ht   DECIMAL(18,2)   NOT NULL CONSTRAINT DF_article_prix DEFAULT (0),
    tva_taux           DECIMAL(5,2)    NOT NULL CONSTRAINT DF_article_tva DEFAULT (20),
    stock_actuel       INT             NOT NULL CONSTRAINT DF_article_stock DEFAULT (0),
    actif              BIT             NOT NULL CONSTRAINT DF_article_actif DEFAULT (1),
    CONSTRAINT PK_article PRIMARY KEY (id),
    CONSTRAINT UQ_article_code UNIQUE (code)
);

IF OBJECT_ID('dbo.facture', 'U') IS NOT NULL DROP TABLE dbo.facture;
CREATE TABLE dbo.facture (
    id              INT             IDENTITY(1,1) NOT NULL,
    numero          NVARCHAR(30)    NOT NULL,
    client_id       INT             NOT NULL,
    date_emission   DATETIME2       NOT NULL,
    date_echeance   DATETIME2       NOT NULL,
    montant_ht      DECIMAL(18,2)   NOT NULL CONSTRAINT DF_facture_ht DEFAULT (0),
    montant_ttc     DECIMAL(18,2)   NOT NULL CONSTRAINT DF_facture_ttc DEFAULT (0),
    statut          NVARCHAR(20)    NOT NULL CONSTRAINT DF_facture_statut DEFAULT ('IMPAYE'),
    devise          NVARCHAR(3)     NOT NULL CONSTRAINT DF_facture_devise DEFAULT ('EUR'),
    commentaire     NVARCHAR(400)   NULL,
    CONSTRAINT PK_facture PRIMARY KEY (id),
    CONSTRAINT UQ_facture_numero UNIQUE (numero),
    CONSTRAINT FK_facture_client FOREIGN KEY (client_id) REFERENCES dbo.client(id),
    CONSTRAINT CK_facture_statut CHECK (statut IN ('PAYE', 'PARTIEL', 'IMPAYE', 'RETARD', 'AVOIR'))
);

IF OBJECT_ID('dbo.ligne_facture', 'U') IS NOT NULL DROP TABLE dbo.ligne_facture;
CREATE TABLE dbo.ligne_facture (
    id                INT             IDENTITY(1,1) NOT NULL,
    facture_id        INT             NOT NULL,
    article_id        INT             NOT NULL,
    quantite          DECIMAL(18,3)   NOT NULL CONSTRAINT DF_ligne_qte DEFAULT (0),
    prix_unitaire_ht  DECIMAL(18,2)   NOT NULL CONSTRAINT DF_ligne_prix DEFAULT (0),
    montant_ht        DECIMAL(18,2)   NOT NULL CONSTRAINT DF_ligne_montant DEFAULT (0),
    CONSTRAINT PK_ligne_facture PRIMARY KEY (id),
    CONSTRAINT FK_ligne_facture FOREIGN KEY (facture_id) REFERENCES dbo.facture(id),
    CONSTRAINT FK_ligne_article FOREIGN KEY (article_id) REFERENCES dbo.article(id)
);

IF OBJECT_ID('dbo.reglement', 'U') IS NOT NULL DROP TABLE dbo.reglement;
CREATE TABLE dbo.reglement (
    id              INT             IDENTITY(1,1) NOT NULL,
    facture_id      INT             NOT NULL,
    date_reglement  DATETIME2       NOT NULL,
    montant         DECIMAL(18,2)   NOT NULL CONSTRAINT DF_reglement_montant DEFAULT (0),
    mode            NVARCHAR(20)    NOT NULL CONSTRAINT DF_reglement_mode DEFAULT ('VIREMENT'),
    CONSTRAINT PK_reglement PRIMARY KEY (id),
    CONSTRAINT FK_reglement_facture FOREIGN KEY (facture_id) REFERENCES dbo.facture(id)
);

IF OBJECT_ID('dbo.ecriture_comptable', 'U') IS NOT NULL DROP TABLE dbo.ecriture_comptable;
CREATE TABLE dbo.ecriture_comptable (
    id            INT             IDENTITY(1,1) NOT NULL,
    journal       NVARCHAR(10)    NOT NULL CONSTRAINT DF_ecriture_journal DEFAULT ('VE'),
    compte        NVARCHAR(20)    NOT NULL,
    libelle       NVARCHAR(200)   NOT NULL,
    date_ecriture DATETIME2       NOT NULL,
    debit         DECIMAL(18,2)   NOT NULL CONSTRAINT DF_ecriture_debit DEFAULT (0),
    credit        DECIMAL(18,2)   NOT NULL CONSTRAINT DF_ecriture_credit DEFAULT (0),
    piece         NVARCHAR(30)    NULL,
    CONSTRAINT PK_ecriture PRIMARY KEY (id),
    CONSTRAINT CK_ecriture_bilan CHECK (debit >= 0 AND credit >= 0)
);

-- ---------------------------------------------------------------------------
-- IA — documents, fragments, exploitation
-- ---------------------------------------------------------------------------
IF OBJECT_ID('dbo.document', 'U') IS NOT NULL DROP TABLE dbo.document;
CREATE TABLE dbo.document (
    id              INT             IDENTITY(1,1) NOT NULL,
    source          NVARCHAR(60)    NOT NULL,
    type_doc        NVARCHAR(60)    NOT NULL,
    titre           NVARCHAR(250)   NOT NULL,
    client_id       INT             NULL,
    date_doc        DATETIME2       NULL,
    chemin          NVARCHAR(400)   NULL,
    hash            CHAR(64)        NOT NULL,
    version         NVARCHAR(20)    NOT NULL CONSTRAINT DF_document_version DEFAULT ('1.0'),
    date_ingestion  DATETIME2       NOT NULL,
    contenu         NVARCHAR(MAX)   NOT NULL,
    CONSTRAINT PK_document PRIMARY KEY (id),
    CONSTRAINT UQ_document_hash UNIQUE (hash),
    CONSTRAINT FK_document_client FOREIGN KEY (client_id) REFERENCES dbo.client(id)
);

IF OBJECT_ID('dbo.chunk', 'U') IS NOT NULL DROP TABLE dbo.chunk;
CREATE TABLE dbo.chunk (
    id           INT             IDENTITY(1,1) NOT NULL,
    document_id  INT             NOT NULL,
    ordinal      INT             NOT NULL,
    texte        NVARCHAR(MAX)   NOT NULL,
    section      NVARCHAR(250)   NULL,
    page         INT             NULL,
    nb_tokens    INT             NOT NULL CONSTRAINT DF_chunk_tokens DEFAULT (0),
    meta         NVARCHAR(MAX)   NULL,
    hash         CHAR(64)        NOT NULL,
    CONSTRAINT PK_chunk PRIMARY KEY (id),
    CONSTRAINT FK_chunk_document FOREIGN KEY (document_id) REFERENCES dbo.document(id),
    CONSTRAINT CK_chunk_meta_json CHECK (meta IS NULL OR ISJSON(meta) = 1)
);

IF OBJECT_ID('dbo.ingestion_log', 'U') IS NOT NULL DROP TABLE dbo.ingestion_log;
CREATE TABLE dbo.ingestion_log (
    id          INT             IDENTITY(1,1) NOT NULL,
    document_id INT             NULL,
    statut      NVARCHAR(20)    NOT NULL,
    message     NVARCHAR(500)   NULL,
    nb_chunks   INT             NOT NULL CONSTRAINT DF_ingestion_chunks DEFAULT (0),
    debut       DATETIME2       NOT NULL,
    fin         DATETIME2       NULL,
    CONSTRAINT PK_ingestion_log PRIMARY KEY (id),
    CONSTRAINT FK_ingestion_document FOREIGN KEY (document_id) REFERENCES dbo.document(id)
);

IF OBJECT_ID('dbo.ai_usage_log', 'U') IS NOT NULL DROP TABLE dbo.ai_usage_log;
CREATE TABLE dbo.ai_usage_log (
    id          INT             IDENTITY(1,1) NOT NULL,
    horodatage  DATETIME2       NOT NULL,
    request_id  NVARCHAR(40)    NOT NULL,
    user_role   NVARCHAR(30)    NULL,
    client_id   INT             NULL,
    provider    NVARCHAR(30)    NOT NULL,
    modele      NVARCHAR(60)    NOT NULL,
    tokens_in   INT             NOT NULL CONSTRAINT DF_usage_tokens_in DEFAULT (0),
    tokens_out  INT             NOT NULL CONSTRAINT DF_usage_tokens_out DEFAULT (0),
    cout_eur    DECIMAL(12,6)   NOT NULL CONSTRAINT DF_usage_cout DEFAULT (0),
    latence_ms  INT             NOT NULL CONSTRAINT DF_usage_latence DEFAULT (0),
    question    NVARCHAR(1000)  NULL,
    statut      NVARCHAR(20)    NOT NULL CONSTRAINT DF_usage_statut DEFAULT ('OK'),
    CONSTRAINT PK_ai_usage_log PRIMARY KEY (id)
);

IF OBJECT_ID('dbo.conversation', 'U') IS NOT NULL DROP TABLE dbo.conversation;
CREATE TABLE dbo.conversation (
    id          INT             IDENTITY(1,1) NOT NULL,
    request_id  NVARCHAR(40)    NOT NULL,
    role        NVARCHAR(30)    NULL,
    client_id   INT             NULL,
    question    NVARCHAR(MAX)   NOT NULL,
    reponse     NVARCHAR(MAX)   NOT NULL,
    sources     NVARCHAR(MAX)   NULL,
    feedback    INT             NULL,
    cree_le     DATETIME2       NOT NULL,
    CONSTRAINT PK_conversation PRIMARY KEY (id),
    CONSTRAINT CK_conversation_sources_json CHECK (sources IS NULL OR ISJSON(sources) = 1)
);

-- ---------------------------------------------------------------------------
-- Index
-- ---------------------------------------------------------------------------
CREATE INDEX IX_facture_client      ON dbo.facture (client_id);
CREATE INDEX IX_facture_echeance    ON dbo.facture (date_echeance);
CREATE INDEX IX_facture_statut      ON dbo.facture (statut);
CREATE INDEX IX_ligne_facture       ON dbo.ligne_facture (facture_id);
CREATE INDEX IX_reglement_facture   ON dbo.reglement (facture_id);
CREATE INDEX IX_chunk_document      ON dbo.chunk (document_id);
CREATE INDEX IX_chunk_section       ON dbo.chunk (section);
CREATE INDEX IX_usage_horodatage    ON dbo.ai_usage_log (horodatage);
CREATE INDEX IX_conversation_req    ON dbo.conversation (request_id);

-- ---------------------------------------------------------------------------
-- Vues métier
-- ---------------------------------------------------------------------------
CREATE VIEW dbo.vw_impayes AS
SELECT  f.numero,
        f.montant_ttc,
        f.montant_ht,
        f.date_emission,
        f.date_echeance,
        f.statut,
        DATEDIFF(DAY, f.date_echeance, GETDATE()) AS jours_retard,
        c.id          AS client_id,
        c.code        AS client_code,
        c.raison_sociale,
        c.encours_autorise
FROM    dbo.facture f
JOIN    dbo.client c ON c.id = f.client_id
WHERE   f.statut <> 'PAYE';

CREATE VIEW dbo.vw_tranche_anciennete AS
SELECT  c.raison_sociale,
        CASE WHEN DATEDIFF(DAY, f.date_echeance, GETDATE()) <= 30 THEN '0-30'
             WHEN DATEDIFF(DAY, f.date_echeance, GETDATE()) <= 60 THEN '31-60'
             WHEN DATEDIFF(DAY, f.date_echeance, GETDATE()) <= 90 THEN '61-90'
             ELSE '90+' END                                                        AS tranche,
        COUNT(*)                                                                   AS nb_factures,
        SUM(f.montant_ttc)                                                        AS montant_ttc
FROM    dbo.facture f
JOIN    dbo.client c ON c.id = f.client_id
WHERE   f.statut <> 'PAYE'
GROUP BY c.raison_sociale,
         CASE WHEN DATEDIFF(DAY, f.date_echeance, GETDATE()) <= 30 THEN '0-30'
              WHEN DATEDIFF(DAY, f.date_echeance, GETDATE()) <= 60 THEN '31-60'
              WHEN DATEDIFF(DAY, f.date_echeance, GETDATE()) <= 90 THEN '61-90'
              ELSE '90+' END;

CREATE VIEW dbo.vw_ca_client AS
SELECT  c.id          AS client_id,
        c.code        AS client_code,
        c.raison_sociale,
        YEAR(f.date_emission)                                          AS annee,
        COUNT(*)                                                        AS nb_factures,
        SUM(f.montant_ht)                                               AS ca_ht,
        SUM(f.montant_ttc)                                              AS ca_ttc
FROM    dbo.facture f
JOIN    dbo.client c ON c.id = f.client_id
GROUP BY c.id, c.code, c.raison_sociale, YEAR(f.date_emission);

-- ---------------------------------------------------------------------------
-- Procédure stockée : Impayés d'un client au-delà d'un seuil de retard
-- ---------------------------------------------------------------------------
CREATE PROCEDURE dbo.usp_get_impayes
    @ClientId  INT = NULL,
    @MinJours  INT = 0
AS
BEGIN
    SET NOCOUNT ON;

    SELECT  v.numero,
            v.client_code,
            v.raison_sociale,
            v.montant_ttc,
            v.date_echeance,
            v.jours_retard,
            v.encours_autorise
    FROM    dbo.vw_impayes v
    WHERE   (@ClientId IS NULL OR v.client_id = @ClientId)
      AND   v.jours_retard >= @MinJours
    ORDER BY v.jours_retard DESC;
END;
