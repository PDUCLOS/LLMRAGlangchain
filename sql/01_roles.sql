-- ===========================================================================
-- erp-ai-copilot — Rôles et comptes applicatifs SQL Server
--
-- Principe de sécurité : l'application n'utilise jamais `sa`.
-- Trois rôles, un par usage, avec le strict minimum :
--
--   erp_app        rôle applicatif  : lecture/écriture ERP + tables IA
--   erp_ro         rôle lecture seule : SELECT sur les tables métier
--                   (compte utilisé par le Text-to-SQL — aucune écriture)
--   erp_ingest     rôle d'ingestion : corpus documentaire et fragments
--
-- L'absence de droits d'écriture est obtenue par l'ABSENCE de droits
-- (privilège minimal), pas par des DENY : moins de surface, moins de
-- surprises, et un compte ne peut rien écrire parce qu'il n'y a jamais eu
-- droit d'écriture.
--
-- Exécution :
--   sqlcmd -S localhost -U sa -P <mot de passe> -v AppPassword="..." \
--           -v ReadOnlyPassword="..." -v IngestPassword="..." \
--           -i sql/01_roles.sql
-- ===========================================================================

USE [erp_ai];
GO

-- --- Rôles applicatifs ----------------------------------------------------
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = 'erp_app_role' AND type = 'R')
    CREATE ROLE erp_app_role;
GO
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = 'erp_ro_role' AND type = 'R')
    CREATE ROLE erp_ro_role;
GO
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = 'erp_ingest_role' AND type = 'R')
    CREATE ROLE erp_ingest_role;
GO

-- --- Connexions ------------------------------------------------------------
IF NOT EXISTS (SELECT 1 FROM sys.server_principals WHERE name = 'erp_app')
    CREATE LOGIN [erp_app] WITH PASSWORD = '$(AppPassword)', CHECK_POLICY = ON;
GO
IF NOT EXISTS (SELECT 1 FROM sys.server_principals WHERE name = 'erp_readonly')
    CREATE LOGIN [erp_readonly] WITH PASSWORD = '$(ReadOnlyPassword)', CHECK_POLICY = ON;
GO
IF NOT EXISTS (SELECT 1 FROM sys.server_principals WHERE name = 'erp_ingest')
    CREATE LOGIN [erp_ingest] WITH PASSWORD = '$(IngestPassword)', CHECK_POLICY = ON;
GO

-- --- Utilisateurs ----------------------------------------------------------
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = 'erp_app')
    CREATE USER [erp_app] FOR LOGIN [erp_app];
GO
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = 'erp_readonly')
    CREATE USER [erp_readonly] FOR LOGIN [erp_readonly];
GO
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = 'erp_ingest')
    CREATE USER [erp_ingest] FOR LOGIN [erp_ingest];
GO

-- --- Droits du rôle applicatif ---------------------------------------------
GRANT SELECT, INSERT, UPDATE, DELETE ON dbo.client             TO [erp_app_role];
GRANT SELECT, INSERT, UPDATE, DELETE ON dbo.article            TO [erp_app_role];
GRANT SELECT, INSERT, UPDATE, DELETE ON dbo.facture            TO [erp_app_role];
GRANT SELECT, INSERT, UPDATE, DELETE ON dbo.ligne_facture      TO [erp_app_role];
GRANT SELECT, INSERT, UPDATE, DELETE ON dbo.reglement          TO [erp_app_role];
GRANT SELECT, INSERT, UPDATE, DELETE ON dbo.ecriture_comptable TO [erp_app_role];
GRANT SELECT, INSERT, UPDATE, DELETE ON dbo.document           TO [erp_app_role];
GRANT SELECT, INSERT, UPDATE, DELETE ON dbo.chunk              TO [erp_app_role];
GRANT SELECT, INSERT, UPDATE, DELETE ON dbo.ingestion_log      TO [erp_app_role];
GRANT SELECT, INSERT                 ON dbo.ai_usage_log       TO [erp_app_role];
GRANT SELECT, INSERT, UPDATE         ON dbo.conversation       TO [erp_app_role];
GRANT EXECUTE ON dbo.usp_get_impayes                          TO [erp_app_role];

-- --- Droits du rôle lecture seule (Text-to-SQL, agents) -------------------
-- SELECT sur les tables métier uniquement : ni tables IA, ni écriture.
GRANT SELECT ON dbo.client             TO [erp_ro_role];
GRANT SELECT ON dbo.article            TO [erp_ro_role];
GRANT SELECT ON dbo.facture            TO [erp_ro_role];
GRANT SELECT ON dbo.ligne_facture      TO [erp_ro_role];
GRANT SELECT ON dbo.reglement          TO [erp_ro_role];
GRANT SELECT ON dbo.ecriture_comptable TO [erp_ro_role];
GRANT EXECUTE ON dbo.usp_get_impayes   TO [erp_ro_role];

-- --- Droits du rôle d'ingestion -------------------------------------------
GRANT SELECT, INSERT, UPDATE, DELETE ON dbo.document      TO [erp_ingest_role];
GRANT SELECT, INSERT, UPDATE, DELETE ON dbo.chunk         TO [erp_ingest_role];
GRANT SELECT, INSERT, UPDATE, DELETE ON dbo.ingestion_log TO [erp_ingest_role];

-- --- Affectation des utilisateurs aux rôles --------------------------------
ALTER ROLE erp_app_role   ADD MEMBER [erp_app];
ALTER ROLE erp_ro_role    ADD MEMBER [erp_readonly];
ALTER ROLE erp_ingest_role ADD MEMBER [erp_ingest];
GO
