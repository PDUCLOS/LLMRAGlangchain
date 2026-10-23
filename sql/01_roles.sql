-- ===========================================================================
-- erp-ai-copilot — Rôles et comptes applicatifs SQL Server
--
-- Principe de sécurité : l'application n'utilise jamais `sa`.
--   * erp_app        : lecture/écriture sur les tables métier et IA (API)
--   * erp_readonly   : SELECT uniquement (compte utilisé par le Text-to-SQL)
--   * erp_ingest     : insertion des documents et fragments (ingestion)
--
-- Exécution : sqlcmd -S localhost -U sa -P <mot de passe> -i sql/01_roles.sql
-- Les mots de passe sont à fournir via variables de session SQLCMD.
-- ===========================================================================

USE [erp_ai];
GO

-- --- Compte applicatif principal -------------------------------------------
IF NOT EXISTS (SELECT 1 FROM sys.server_principals WHERE name = 'erp_app')
    CREATE LOGIN [erp_app] WITH PASSWORD = '$(AppPassword)', CHECK_POLICY = ON;
GO

IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = 'erp_app')
    CREATE USER [erp_app] FOR LOGIN [erp_app];
GO

-- --- Compte lecture seule (Text-to-SQL, agents) ----------------------------
IF NOT EXISTS (SELECT 1 FROM sys.server_principals WHERE name = 'erp_readonly')
    CREATE LOGIN [erp_readonly] WITH PASSWORD = '$(ReadOnlyPassword)', CHECK_POLICY = ON;
GO

IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = 'erp_readonly')
    CREATE USER [erp_readonly] FOR LOGIN [erp_readonly];
GO

-- --- Compte d'ingestion ----------------------------------------------------
IF NOT EXISTS (SELECT 1 FROM sys.server_principals WHERE name = 'erp_ingest')
    CREATE LOGIN [erp_ingest] WITH PASSWORD = '$(IngestPassword)', CHECK_POLICY = ON;
GO

IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = 'erp_ingest')
    CREATE USER [erp_ingest] FOR LOGIN [erp_ingest];
GO

-- --- Droits ----------------------------------------------------------------
GRANT SELECT, INSERT, UPDATE, DELETE ON dbo.client            TO [erp_app];
GRANT SELECT, INSERT, UPDATE, DELETE ON dbo.article           TO [erp_app];
GRANT SELECT, INSERT, UPDATE, DELETE ON dbo.facture           TO [erp_app];
GRANT SELECT, INSERT, UPDATE, DELETE ON dbo.ligne_facture     TO [erp_app];
GRANT SELECT, INSERT, UPDATE, DELETE ON dbo.reglement         TO [erp_app];
GRANT SELECT, INSERT, UPDATE, DELETE ON dbo.ecriture_comptable TO [erp_app];
GRANT SELECT, INSERT, UPDATE, DELETE ON dbo.document          TO [erp_app];
GRANT SELECT, INSERT, UPDATE, DELETE ON dbo.chunk             TO [erp_app];
GRANT SELECT, INSERT, UPDATE, DELETE ON dbo.ingestion_log     TO [erp_app];
GRANT SELECT, INSERT                  ON dbo.ai_usage_log      TO [erp_app];
GRANT SELECT, INSERT, UPDATE          ON dbo.conversation      TO [erp_app];
GRANT EXECUTE ON dbo.usp_get_impayes                           TO [erp_app];

-- Lecture seule stricte pour le Text-to-SQL : SELECT sur les tables métier,
-- aucune permission d'écriture, aucune permission sur les tables IA.
GRANT SELECT ON dbo.client            TO [erp_readonly];
GRANT SELECT ON dbo.article           TO [erp_readonly];
GRANT SELECT ON dbo.facture           TO [erp_readonly];
GRANT SELECT ON dbo.ligne_facture     TO [erp_readonly];
GRANT SELECT ON dbo.reglement         TO [erp_readonly];
GRANT SELECT ON dbo.ecriture_comptable TO [erp_readonly];
GRANT EXECUTE ON dbo.usp_get_impayes  TO [erp_readonly];
DENY  INSERT, UPDATE, DELETE ON dbo.client            TO [erp_readonly];
DENY  INSERT, UPDATE, DELETE ON dbo.article           TO [erp_readonly];
DENY  INSERT, UPDATE, DELETE ON dbo.facture           TO [erp_readonly];
DENY  INSERT, UPDATE, DELETE ON dbo.ligne_facture     TO [erp_readonly];
DENY  INSERT, UPDATE, DELETE ON dbo.reglement         TO [erp_readonly];
DENY  INSERT, UPDATE, DELETE ON dbo.ecriture_comptable TO [erp_readonly];

-- Ingestion : lecture/écriture sur le corpus documentaire uniquement.
GRANT SELECT, INSERT, UPDATE, DELETE ON dbo.document      TO [erp_ingest];
GRANT SELECT, INSERT, UPDATE, DELETE ON dbo.chunk         TO [erp_ingest];
GRANT SELECT, INSERT, UPDATE, DELETE ON dbo.ingestion_log TO [erp_ingest];
