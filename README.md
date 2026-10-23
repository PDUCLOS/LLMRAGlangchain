# erp-ai-copilot

**Copilote IA & automatisation ERP (Sage / EBP) sur Azure** — projet de
référence d'une offre de conseil : ingestion documentaire, RAG, requêtes SQL
en lecture seule sur le référentiel de gestion, agents d'automatisation
(relances), restitution Power BI / Teams, gouvernance et pilotage du coût IA.

> Ce dépôt est la **base technique** du projet. Le diagnostic complet
> (architecture cible, pipeline, séquencement, budget, risques) est dans
> [`docs/PROPOSITION.md`](docs/PROPOSITION.md) et les schémas dans
> [`docs/architecture.drawio`](docs/architecture.drawio) (4 pages).

---

## 1. Ce que le projet démontre

| Compétence de l'offre | Ce qui est implémenté ici |
|---|---|
| SQL Server | Schéma T-SQL complet (`sql/00_schema.sql`), vues métier, procédure stockée, rôles applicatifs à droits fins |
| API REST ERP | Émulateur d'API Sage/EBP (`src/erp_ai/api/mock_erp.py`) + client d'ERP prêt à brancher |
| Python | API FastAPI, CLI, moteur RAG, outils métier, tests pytest, CI GitHub Actions |
| RAG | Ingestion → découpage structurel → embeddings → index hybride → recherche BM25+vecteurs → réponse ancrée avec citations |
| Bases de données vectorielles | Azure AI Search en cible, index local déterministe en dev, derrière une interface unique |
| Azure AI / Azure OpenAI | Bascule par variable d'environnement : modèle, embeddings, registre de prompts, agents |
| LangChain | Non imposé : le pipeline est écrit explicitement (chaîne RAG lisible, pas de boîte noire) |
| Power Automate / Power BI / M365 | Points d'intégration documentés (`flows/`, `powerbi/`) + API prête à être appelée par un flux |
| Accompagnement client | Traçabilité des prompts, journal d'ingestion, mesure de coût par client, documentation |

---

## 2. Démarrage rapide (2 minutes, sans Azure)

```bash
git clone <url> erp-ai-copilot && cd erp-ai-copilot
cp .env.example .env

make install        # venv Python 3.12 + dépendances
make init-db        # schéma + jeu de données de démonstration
make ingest         # indexation vectorielle
make ask Q="Quelles sont les règles de relance client ?"
make serve          # API sur http://127.0.0.1:8000/docs
make test           # suite de tests
```

Le mode `local` est **100 % hors ligne et déterministe** : embeddings par
hachage features, LLM extractif, index vectoriel en fichier JSON. Le code, le
schéma, les prompts et les tests ne changent pas quand on passe sur Azure —
seules les variables d'environnement changent.

---

## 3. Passer sur SQL Server (LG Gram x86-64 ou CI)

SQL Server ne publie **aucune image ARM64** : sur Mac Apple Silicon, le
conteneur segfault sous émulation (constaté sur macOS 27 / Docker 29). Sur
x86-64, il tourne nativement.

```bash
# 1. Base SQL Server (conteneur natif sur x86)
docker compose --profile sqlserver up -d sqlserver

# 2. Compte applicatif (mots de passe à personaliser)
sqlcmd -S localhost -U sa -P "$MSSQL_SA_PASSWORD" -i sql/01_roles.sql

# 3. Configuration
export DATABASE_URL="mssql+pyodbc://erp_app:<MOT_DE_PASSE>@localhost:1433/erp_ai?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes"
pip install -e ".[dev,sqlserver]"

make init-db && make ingest && make test
```

Prérequis : `msodbcsql18` (ou `msodbcsql17`) installé, et le pilote ODBC
correspondant.

> Le compte `erp_readonly` est celui utilisé pour le Text-to-SQL : il n'a que
> des droits `SELECT`. C'est le deuxième verrou, indépendant du garde-fou
> applicatif.

---

## 4. Passer sur Azure

```bash
export LLM_PROVIDER=azure
export EMBEDDING_PROVIDER=azure
export VECTOR_STORE_PROVIDER=azure_ai_search
export AZURE_OPENAI_ENDPOINT="https://<ressource>.openai.azure.com/"
export AZURE_OPENAI_API_KEY="..."
export AZURE_SEARCH_ENDPOINT="https://<ressource>.search.windows.net"
export AZURE_SEARCH_API_KEY="..."
```

Le provisionnement (AI Foundry, Azure OpenAI, AI Search, Azure SQL, App
Service, Key Vault, Application Insights) est prévu en phase 4 de la
proposition, en Bicep (`infra/`).

---

## 5. Structure du dépôt

```
erp-ai-copilot/
├── docs/
│   ├── architecture.drawio     # 4 pages : cible Azure, pipeline RAG, séquence métier, dev/CI
│   └── PROPOSITION.md          # diagnostic, architecture, séquencement, risques
├── eval/gold_set.json          # questions de non-régression (seuils bloquants en CI)
├── sql/
│   ├── 00_schema.sql           # schéma SQL Server + vues + procédure stockée
│   └── 01_roles.sql            # rôles et comptes à droits fins
├── src/erp_ai/
│   ├── config.py               # configuration 12-factor
│   ├── service.py              # orchestration (retrieval → SQL → LLM → logging)
│   ├── db/                     # schéma, moteur, bootstrap, jeu de démo
│   ├── providers/              # LLM, embeddings, base vectorielle (local | Azure)
│   ├── rag/                    # découpage, prompts, recherche hybride
│   ├── agents/                 # outils métier + garde-fou SQL
│   ├── observability/          # journal d'usage, coût, latence
│   └── api/                    # FastAPI + émulateur d'API ERP
├── tests/                      # pytest (schéma, seed, RAG, garde-fous, API)
├── scripts/                    # bootstrap, export pour transfert
└── .github/workflows/ci.yml    # CI x86-64 avec service SQL Server
```

---

## 6. Garde-fous (le vrai sujet d'un déploiement ERP)

1. **Lecture seule par construction** — le compte SQL applicatif utilisé par
   le Text-to-SQL n'a que des droits `SELECT` ; en plus, chaque requête est
   validée par `validate_readonly_sql()` (une seule instruction, tables en
   liste blanche, aucun mot-clé DDL/DML).
2. **Ancrage obligatoire** — la réponse cite ses sources ; sans source
   exploitable, le système refuse au lieu d'inventer.
3. **Validation humaine** — toute action sur l'ERP (relance) passe par une
   approbation ; le bot propose, l'humain décide.
4. **Traçabilité** — chaque appel est journalisé (rôle, client, modèle,
   tokens, coût, latence, citations).
5. **Confidentialité** — filtrage par client, masquage des données
   personnelles avant envoi au modèle, hébergement UE.

---

## 7. Tests et CI

```bash
make test          # tests hors SQL Server (SQLite, < 30 s)
make test-all      # tout
pytest -m sqlserver  # tests sur SQL Server réel (runner x86-64)
```

La CI (`ubuntu-latest`) démarre un **service SQL Server** et exécute les tests
sur les deux cibles. Le gold set `eval/gold_set.json` est évalué à chaque
exécution : une régression de pertinence ou de réponse fait échouer le build.

---

## 8. Transfert vers une autre machine

```bash
make export        # -> dist/erp-ai-copilot-<date>.tar.gz (sans .venv, sans data)
```

ou, plus simple si le dépôt est sur Git :

```bash
git clone <url> erp-ai-copilot
```

Voir [`docs/PROPOSITION.md`](docs/PROPOSITION.md) § 9 pour la procédure de
transfert détaillée vers le LG Gram.
