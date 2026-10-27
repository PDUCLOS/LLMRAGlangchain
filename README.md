# erp-ai-copilot

**Copilote IA & automatisation ERP (Sage / EBP) sur Azure** — projet de
référence d'une offre de conseil : ingestion documentaire, RAG, requêtes SQL
en lecture seule sur le référentiel de gestion, agents d'automatisation
(relances), restitution Power BI / Teams, gouvernance et pilotage du coût IA.

> **Vitrine du projet** (démo, démarche, résultats LLMOps, guide Kubernetes) :
> [`docs/index.html`](docs/index.html), publiable telle quelle sur GitHub Pages
> (Settings › Pages › branche `main`, dossier `/docs`). Vidéo de présentation :
> [`docs/video/copilote-erp-promo.mp4`](docs/video/copilote-erp-promo.mp4).

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
| LangChain | Variante LCEL de la chaîne RAG (`RAG_CHAIN=langchain`), même format de sources et mêmes citations que la chaîne native |
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

## 4 bis. Mode GPU local (Ollama) et banc LLMOps

Entre le mode `local` (déterministe, pour la CI) et Azure, le provider
`ollama` sert un **vrai LLM open-weight sur le GPU** de la machine, avec des
embeddings neuronaux multilingues. Aucune donnée ne sort du poste.

```bash
ollama pull qwen3.5:9b && ollama pull bge-m3
pip install -e ".[dev,ollama]"

export LLM_PROVIDER=ollama EMBEDDING_PROVIDER=ollama
export DATA_DIR=./data/ollama DATABASE_URL=sqlite:///./data/ollama/dev.db
make init-db && make ingest
make ask Q="Quel est le barème des remises selon le chiffre d'affaires ?"
RAG_CHAIN=langchain make ask Q="..."   # même chose via ChatOllama (LCEL)
```

Chaque appel journalise les **compteurs réels** renvoyés par Ollama (tokens
d'entrée et de sortie, débit en tokens/s) au lieu d'une estimation.

`make bench` compare quatre configurations (extractif d'origine, qwen3.5 en
chaîne native, qwen3.5 via LangChain, gemma4) sur le gold set et trois
questions adverses (hors corpus, injection de prompt). Il mesure hit@k, MRR,
couverture, citations valides, refus, fidélité notée par deux LLM juges,
latence p50/p95, débit et coût équivalent Azure. `make report` produit le
tableau de bord HTML.

---

## 4 ter. Interface, conteneur et Kubernetes

- **Interface de chat** : `erp-ai serve` puis http://127.0.0.1:8000 (citations
  cliquables, SQL exécuté, tokens, latence et coût de chaque réponse). Lien de démo :
  `/?q=Quelles factures sont en retard de plus de 60 jours ?`
- **Image Docker** (`Dockerfile`) : une seule image pour l'API, le Job d'ingestion et
  le banc LLMOps ; utilisateur non root, healthcheck, pilote ODBC 18 inclus.
  `erp-ai init-db` crée la base SQL Server si elle n'existe pas.
- **Kubernetes** (`deploy/k8s`, kustomize) : base commune + overlays `local-gpu`
  (Docker Desktop, k3s) et `cloud` (AKS, Azure SQL, Azure Files, TLS). API répliquée
  avec HPA, Ollama sur nœud GPU, SQL Server en StatefulSet, Job d'ingestion, CronJob
  du banc LLMOps, NetworkPolicy. Guide pas à pas dans la vitrine.

```bash
docker build -t erp-ai-copilot:0.2.0 .
kubectl apply -k deploy/k8s/overlays/local-gpu
kubectl -n erp-ai port-forward svc/erp-ai-api 8000:80
```

---

## 5. Deux chaînes RAG, une seule logique

| Mode | Activation | Ce que c'est |
|---|---|---|
| **native** (défaut) | `RAG_CHAIN=native` | La chaîne écrite explicitement : retrieval → prompt → LLM → citations. Lisible, sans dépendance, c'est celle que la CI exerce. |
| **langchain** | `RAG_CHAIN=langchain` | La même chose en **LCEL** : `retriever \| context \| prompt \| modèle \| extract`. Le retriever, le format des sources et les citations sont **strictement les mêmes** — seul le chaînage change. |

```bash
pip install -e ".[langchain]"
RAG_CHAIN=langchain python -m erp_ai.cli ask "Quels sont les délais de paiement ?"
```

En mode Azure, la variante LangChain utilise `AzureChatOpenAI`
(`langchain-openai`). Si la chaîne LangChain échoue, le service **retombe
automatiquement sur la chaîne native** : une panne de la bibliothèque ne
coupe jamais le service.

---

## 6. Structure du dépôt

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
├── scripts/                    # bootstrap, export, banc LLMOps, vidéo de présentation
├── deploy/k8s/                 # manifestes Kubernetes (kustomize : base + overlays)
├── Dockerfile                  # image unique : API, ingestion, banc
└── .github/workflows/ci.yml    # CI x86-64 avec service SQL Server
```

---

## 7. Garde-fous (le vrai sujet d'un déploiement ERP)

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

## 8. Tests et CI

```bash
make test          # tests hors SQL Server (SQLite, < 30 s)
make test-all      # tout
pytest -m sqlserver  # tests sur SQL Server réel (runner x86-64)
```

La CI (`ubuntu-latest`) démarre un **service SQL Server** et exécute les tests
sur les deux cibles. Le gold set `eval/gold_set.json` est évalué à chaque
exécution : une régression de pertinence ou de réponse fait échouer le build.

---

## 9. Transfert vers une autre machine

```bash
make export        # -> dist/erp-ai-copilot-<date>.tar.gz (sans .venv, sans data)
```

ou, plus simple si le dépôt est sur Git :

```bash
git clone <url> erp-ai-copilot
```

Voir [`docs/PROPOSITION.md`](docs/PROPOSITION.md) § 9 pour la procédure de
transfert détaillée vers le LG Gram.
