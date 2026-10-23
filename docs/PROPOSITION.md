# Proposition — Copilote IA & automatisation ERP (Sage / EBP) sur Azure

**Objet :** validation de faisabilité avant production du code.
**Version :** 1.0 — 23/10/2026
**Pièces jointes :** `architecture.drawio` (4 pages) · dépôt `LLMRAGlangchain`

---

## 1. Ce qui est demandé, et ce que je propose

L'offre cherche un profil capable de **déployer des solutions IA et
d'automatisation chez des clients equipped ERP (Sage, EBP)**, depuis l'audit
des besoins jusqu'au déploiement et à la formation.

Plutôt qu'une maquette isolée, je propose de construire **un produit de
référence réutilisable** : un copilote ERP multi-clients, que l'on peut
déployer chez n'importe quel client de la société (revendeur / éditeur
Sage-EBP). C'est exactement le type de livrable que l'offre Search & Files
veut produire : une nouvelle offre IA qui se déploie et se facture par
client.

**Sujet retenu :** un **copilote de gestion** pour une PME/ETI distributrice
(BTP / négoce), qui répond aux questions de la DAF et du contrôle de gestion
à partir :

* du **référentiel ERP** (clients, factures, règlements, stocks, écritures) ;
* de la **documentation** (procédure de relance, politique de remises,
  contrat-cadre, guide de clôture comptable, notes internes) ;
* et qui **agit** : relance client rédigée puis validée avant envoi.

---

## 2. Les 3 cas d'usage démontrables (par ordre de valeur métier)

| # | Cas d'usage | Qui | Valeur | Difficulté |
|---|---|---|---|---|
| 1 | **Relance client assistée** | DAF / recouvrement | Cash : chaque jour de retard coûte de la trésorerie | RAG + SQL + agent + validation humaine |
| 2 | **Question-réponse sur la gestion** (« quelles factures dépassent 90 jours ? ») | DAF, contrôleur, commercial | Gain de temps sur l'analyse | RAG hybride + Text-to-SQL en lecture seule |
| 3 | **Restitution et pilotage** | Direction | Tableau de bord DAF alimenté par une vue analytique | SQL + Power BI + Power Automate |

Ces trois cas couvrent **l'intégralité des compétences listées dans l'offre**
(§ 11).

---

## 3. Choix structurants (et pourquoi)

| Sujet | Choix | Justification |
|---|---|---|
| Base relationnelle | **SQL Server** | Exigé « indispensable » dans l'offre. Azure SQL Database en production, conteneur SQL Server 2022 en dev. Le reste du schéma est portable (SQLAlchemy). |
| Base vectorielle | **Azure AI Search** (index vectoriel HNSW + hybride + ranker sémantique) | Base vectorielle **managée**, pas une brique à opérer. Repli dev : index local déterministe derrière la même interface. |
| Modèles | **Azure AI Foundry** (Azure OpenAI : `gpt-4.1-mini` + `text-embedding-3-small`) | Cible Azure de l'offre ; le catalogue Foundry permet de changer de modèle sans toucher au code. |
| Orchestration | **Chaîne RAG écrite explicitement** + **variante LangChain optionnelle** | On montre la maîtrise du mécanisme (pas de boîte noire) tout en maîtrisant la bibliothèque demandée dans l'offre. |
| Intégration ERP | **API REST** (contrat Sage / EBP), émulateur fourni | Pas de dépendance à une licence ERP pour démontrer ; le point de branchement est isolé. |
| Automatisation | **Power Automate** (déclencheur, approbation, écriture ERP) | Cœur de l'offre ; le flux est piloté par l'API Python. |
| Restitution | **Power BI** sur une vue analytique SQL | Pas d'export, pas de copie de données ; le modèle sémantique est versionné dans le dépôt. |
| Runtime | **FastAPI** (App Service / Functions) | Standard, portable, testable. |
| Coût | **Mode local déterministe** par défaut | La démo tourne sans abonnement ; le passage Azure se fait par variable d'environnement. |

**Point de méthode assumé :** LangChain est proposé en *variante*, pas en
colonne vertébrale. Le code reste lisible et le RRF (fusion BM25 + vecteurs)
est explicite. Un entretien technique préfère souvent « je sais ce que fait
ma bibliothèque » à « j'ai appelé une classe ».

---

## 4. Architecture cible

Voir `architecture.drawio` :

* **Page 1** — Architecture cible Azure (4 couches + bandeau transverse
  gouvernance).
* **Page 2** — Pipeline RAG (indexation / interrogation / garde-fous).
* **Page 3** — Séquence du cas métier « relance impayés ».
* **Page 4** — Dev local, CI/CD, et la contrainte ARM64.

Le flux principal :

```
SI client (Sage, EBP, SharePoint, fichiers)
        ↓  Power Automate (déclencheurs) / Azure Functions (connecteurs REST)
Blob Storage (bronze) → Chunking structurel → Embeddings (text-embedding-3-small)
        ↓
Azure AI Search (index vectoriel + hybride + ranker sémantique)
        ↓
Agent (Azure AI Foundry) + outils : sql_query (lecture seule) · erp_rest
        ↓
API FastAPI (LangChain) → Teams / Copilot Studio / Power BI / portail web
```

Le bandeau transverse : Entra ID (RBAC), Key Vault + Managed Identity,
private endpoints, Application Insights, journal de prompts, coût par client,
évaluation continue, RGPD & AI Act.

---

## 5. Le pipeline RAG, étape par étape

**Indexation (offline)**

1. **Collecte** — connecteurs REST (Sage/EBP), SharePoint/OneDrive, fichiers, e-mails.
2. **Normalisation** — nettoyage, déduplication par hash, métadonnées (client, type, version, date, ACL).
3. **Parsing** — PDF/DOCX/XLSX → texte + tableaux.
4. **Chunking structurel** — par section (titres respectés), ~800 tokens, chevauchement 100, **titre de section indexé** (améliore nettement le rappel).
5. **Embeddings** — `text-embedding-3-small`, lot.
6. **Indexation** — Azure AI Search : champ vectoriel HNSW + champs texte + ranker sémantique + champ de filtre ACL/`client_id`.
7. **Journalisation** — `document`, `chunk`, `ingestion_log`.

**Interrogation (temps réel)**

8. Reformulation → **recherche hybride** (vecteur + BM25) → fusion **RRF** → filtrage ACL → **reranking** sémantique → top-k.
9. **Outils** : `sql_query` (lecture seule, garde-fou déterministe), `erp_rest`, calculs de KPI.
10. **Génération ancrée** : prompt système strict, citations `[S1]`, refus explicite si les sources ne suffisent pas.
11. **Restitution** : réponse + sources + SQL exécuté + coût + latence.

**Garde-fous** : deux verrous indépendants sur le SQL (compte applicatif
`erp_readonly` en `SELECT` seul **+** validation déterministe des tables et
mots-clés), approbation humaine obligatoire avant toute écriture ERP, filtrage
par client, masquage des données personnelles, journalisation de chaque appel.

---

## 6. Cas métier de bout en bout (page 3 du drawio)

1. Planificateur Power Automate (quotidien 08:00).
2. `POST /agents/relance-impayes` sur l'API Python.
3. Lecture du référentiel (procédure stockée `usp_get_impayes` / vue `vw_impayes`).
4. Enrichissement : contexte client, historique, contrats (RAG).
5. L'agent **rédige** la relance (montant, ton, échéance) et **propose** le niveau.
6. Écriture d'un brouillon via l'API REST ERP (jamais d'envoi direct).
7. **Approbation humaine** (Teams / Power Automate Approval).
8. Envoi + journalisation (qui, quoi, quand, combien, coût IA).

---

## 7. Power Platform & Microsoft 365

| Outil | Usage concret dans le projet |
|---|---|
| **Power Automate** | Flux planifié (relance), approbation, écriture ERP, notification Teams. Déclaration de flux versionnable dans le dépôt. |
| **Power BI** | Modèle sémantique (TMDL) versionné, source = vue analytique SQL (DirectQuery), indicateurs : CA, marge par famille, recouvrement 30/60 j, encours. |
| **Copilot Studio** | Agent métier branché sur l'API (même backend que Teams et le portail). |
| **Microsoft 365** | Teams comme interface du copilote, SharePoint comme source documentaire, Entra ID comme fournisseur d'identité. |
| **Microsoft Copilot** | Positionné comme *accélérateur* (Copilot Studio + Graph), pas comme cœur du dispositif : l'agent reste maîtrisé, versionné et évaluable. |

---

## 8. Gouvernance, conformité, coût

* **Sécurité** : Entra ID (OAuth2/OIDC), RBAC par rôle (DAF / contrôleur /
  commercial), Key Vault + Managed Identity, private endpoints, journalisation.
* **Données** : hébergement UE, minimisation, masquage PII avant envoi au
  modèle, rétention paramétrable (procédure de relance : 5 ans).
* **AI Act / RGPD** : registre des prompts et des modèles, traçabilité des
  requêtes, information de l'utilisateur, validation humaine sur les actions.
* **FinOps** : chaque appel journalisé (modèle, tokens, coût EUR, latence) →
  tableau de coût par client et par mois, alertes de plafond. C'est l'argument
  qui répond à la question « combien ce client me coûte-t-il ? ».
* **Évaluation continue** : gold set de 10 questions métier, seuils bloquants
  en CI (taux de succès de recherche, couverture des mots-clés).

---

## 9. Contrainte matériel : ARM64 vs x86-64 — réponse directe

**Constaté sur ta machine (macOS 27 / Docker 29.8.2) :** SQL Server n'existe
pas en image ARM64 ; le conteneur `linux/amd64` **segfault sous émulation**
(`qemu: uncaught target signal 11`, exit 139). Azure SQL Edge, qui était la
solution ARM64, est **retiré depuis le 30/09/2025**.

**Conséquence : oui, il faut une machine x86-64 pour la cible SQL Server.**

* **LG Gram 16 (x86-64)** = environnement de développement principal :
  SQL Server natif en conteneur, CI locale, et futur déploiement Azure.
* **Mac ARM64** = poste de lecture/écriture légère : le code, les tests et la
  démo tournent en SQLite, sans conteneur SQL Server.

C'est précisément pour ça que **rien dans le code ne dépend du SGBD local** :
un seul schéma, deux moteurs, un test de parité qui garantit que le schéma
Python et le schéma T-SQL ne divergent pas.

> Détail d'installation utile : sur macOS, le fichier `.pth` d'installation
> éditable d'`uv` est marqué « hidden » par le système de fichiers, et
> **CPython ≥ 3.12.13 ignore volontairement les `.pth` cachés** (correctif
> sécurité). Le script `scripts/bootstrap.sh` écrit donc un `.pth` au nom
> neutre et le `Makefile` force `PYTHONPATH=src` : ça marche partout.

---

## 10. Séquencement

| Phase | Contenu | Livrable | État |
|---|---|---|---|
| **0** | Validation de la proposition, choix du sujet | Ce document + drawio | **Fait — à valider** |
| **1** | Socle données + API | Schéma SQL Server, jeu de démo, API FastAPI, CLI | **Fait** (dans le dépôt) |
| **2** | RAG complet | Ingestion, chunking, embeddings, index, recherche hybride, citations, évaluation | **Fait** (mode local ; à brancher sur Azure) |
| **3** | Agents & automatisation | Text-to-SQL encadré, outil de relance, flux Power Automate, modèle Power BI |amorcé (outils + garde-fous + émulateur ERP) |
| **4** | Déploiement Azure | Bicep (Foundry, AI Search, Azure SQL, App Service, Key Vault, Monitor), CI/CD | À faire |
| **5** | Copilot Studio / M365 | Agent Copilot Studio, connecteur Teams, formation | À faire |
| **6** | Industrialisation consulting | Guide d'installation client, chiffrage, avant-vente, offre | À faire |

Les phases 1 et 2 sont **déjà implémentées et testées** dans le dépôt
(60 tests, 100 % de réussite sur le gold set) : la faisabilité technique est
donc déjà démontrée, pas supposée.

---

## 11. Mapping offre ↔ livrables

| Compétence demandée | Livrable dans le projet | Statut |
|---|---|---|
| SQL Server | `sql/00_schema.sql` (schéma, vues, procédure stockée), `sql/01_roles.sql` (droits fins), tests sur SQL Server réel en CI | Fait |
| Microsoft Power Automate | Flux d'approbation et de relance pilotant l'API | À faire (phase 3) |
| Power BI | Modèle sémantique versionné sur vue analytique | À faire (phase 3) |
| Microsoft 365 | Teams (interface), SharePoint (source), Entra ID (identité) | Partiel |
| Microsoft Copilot | Agent Copilot Studio sur le même backend | À faire (phase 5) |
| API REST | Connecteurs + émulateur d'API ERP (Sage/EBP) | Fait (contrat) |
| Python | API, CLI, moteur RAG, outils, tests, CI | Fait |
| Sage 100 / EBP | Contrat d'API REST + point de branchement isolé | Contractuel |
| Azure AI / Azure OpenAI | Bascule par variable d'environnement, deployments Foundry | Prêt |
| LangChain | Variante LCEL de la chaîne RAG (`RAG_CHAIN=langchain`), même retriever, mêmes citations, repli automatique sur la chaîne native | Fait |
| Architecture RAG | Pipeline complet documenté et testé | Fait |
| Bases de données vectorielles | Azure AI Search (cible) + index local (dev) | Fait |
| Métiers compta / gestion commerciale | Le cas d'usage est la gestion (relance, recouvrement, marge) | Fait |
| Accompagnement / documentation | README, ADRs, guide d'installation client | En cours |

---

## 12. Budget Azure (estimation, à confirmer sur les tarifs en vigueur)

| Poste | Hypothèse | Ordre de grandeur |
|---|---|---|
| Azure SQL Database | serverless, base de démonstration | quelques €/mois |
| Azure AI Search | S1, quelques milliers de fragments | quelques €/mois |
| Azure OpenAI (`gpt-4.1-mini` + embeddings) | pay-as-you-go, démo + 10 clients | quelques €/mois (variable selon l'usage) |
| App Service / Functions | plan petit | quelques €/mois |
| Observabilité | Log Analytics | à surveiller (peut dériver vite) |

**Cible : un coût par client qui reste marginal** (< 20 €/mois pour un client
standard), grâce au cache, au choix de modèle par tâche et au plafonnement
par client. Les chiffres exacts sont à recaler sur le simulateur de coût
Azure une fois les volumes réels connus.

---

## 13. Risques et parades

| Risque | Impact | Parade |
|---|---|---|
| Hallucination sur un chiffre | Fort (décision de gestion) | Chiffres par SQL, jamais par le LLM ; citations obligatoires ; refus si pas de source |
| Écriture ERP erronée | Fort | Compte SQL en lecture seule, garde-fou déterministe, approbation humaine, journalisation |
| Données clients hors UE / PII | Fort | Hébergement UE, minimisation, masquage avant envoi, contrat de sous-traitance |
| Fuite inter-clients | Fort | Filtre `client_id` + ACL au niveau de l'index, RBAC, tests de non-fuite |
| Coût IA qui dérive | Moyen | Journal de coût par client, plafonds, modèle petit par défaut, cache |
| Dépendance à un modèle unique | Moyen | Abstraction `ChatLLM` / `EmbeddingProvider` : changement de modèle = une variable d'environnement |
| SQL Server indisponible en local | Faible | Abstraction SQL, mode SQLite, CI x86-64 |

---

## 14. Ce que j'attends de toi pour la suite

1. **Valider (ou corriger) cette proposition** : sujet, périmètre, choix
   techniques, Priorités.
2. **L'énoncé des compétences** que l'entreprise attend — tu me l'as promis :
   je l'alignerai sur ce que le projet couvre déjà, et je compléterai ce qui
   manque (LangChain, Power Automate, Bicep, Power BI).
3. **Le format attendu** pour la restitution (dépôt GitHub public, dossier
   de candidature, démonstration en direct ?).

---

*Annexe : `architecture.drawio` (4 pages), dépôt GitHub
`PDUCLOS/LLMRAGlangchain` (code, tests, CI).*
