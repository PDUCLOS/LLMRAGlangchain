# ===========================================================================
# erp-ai-copilot — Makefile
# ===========================================================================

SHELL := /bin/bash
# PYTHONPATH est forcé : sur macOS, le fichier .pth d'installation éditable
# d'uv (_editable_impl_*.pth) est marqué « hidden » par le système de
# fichiers, et CPython >= 3.12.13 ignore volontairement les .pth cachés.
# Le code reste donc accessible sans dépendre du mécanisme d'installation.
PY    := PYTHONPATH=src .venv/bin/python
PIP   := .venv/bin/pip

.DEFAULT_GOAL := help
.PHONY: help venv install init-db seed ingest serve test lint fmt typecheck \
        docker-up docker-down docker-logs eval export clean ci

help: ## Afficher l'aide
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

venv: ## Créer l'environnement virtuel (Python 3.12)
	@test -d .venv || (command -v uv >/dev/null && uv venv --python 3.12 .venv || python3.12 -m venv .venv)

install: venv ## Installer les dépendances (editable + dev)
	@if command -v uv >/dev/null; then uv pip install --python $(PY) -e ".[dev]"; else $(PIP) install -e ".[dev]"; fi
	@if [ -f .env ]; then echo "[ok] .env détecté"; else echo "[warn] pas de .env — cp .env.example .env"; fi

init-db: ## Créer le schéma + jeu de données de démonstration
	$(PY) -m erp_ai.cli init-db

seed: init-db ## Alias (données ERP de démonstration)

ingest: ## Ingérer les documents dans l'index vectoriel
	$(PY) -m erp_ai.cli ingest

serve: ## Démarrer l'API (http://127.0.0.1:8000/docs)
	$(PY) -m erp_ai.cli serve

ask: ## Poser une question — ex: make ask Q="combien de factures en retard ?"
	$(PY) -m erp_ai.cli ask "$(Q)"

test: ## Lancer les tests (hors SQL Server)
	$(PY) -m pytest -q -m "not sqlserver and not azure"

test-all: ## Lancer tous les tests
	$(PY) -m pytest -q

lint: ## Linter (ruff)
	@if command -v uv >/dev/null; then PYTHONPATH=src uv run ruff check src tests; else PYTHONPATH=src $(PY) -m ruff check src tests; fi

fmt: ## Formater (ruff)
	@if command -v uv >/dev/null; then PYTHONPATH=src uv run ruff format src tests; else PYTHONPATH=src $(PY) -m ruff format src tests; fi

typecheck: ## Contrôle de types (mypy)
	@if command -v uv >/dev/null; then PYTHONPATH=src uv run mypy src; else PYTHONPATH=src $(PY) -m mypy src; fi

eval: ## Évaluer le RAG sur le gold set
	$(PY) -m erp_ai.cli eval

docker-up: ## Démarrer l'infra locale (SQL Server requis : --profile sqlserver)
	docker compose up -d
	docker compose --profile sqlserver up -d sqlserver

docker-down: ## Arrêter l'infra locale
	docker compose --profile sqlserver down

docker-logs: ## Logs des conteneurs
	docker compose --profile sqlserver logs -f --tail=100

export: ## Exporter l'archive de transfert vers LG Gram
	@bash scripts/export_transfer.sh

ci: lint test ## Contrôles pré-push

clean: ## Nettoyer les artefacts locaux
	rm -rf .pytest_cache .ruff_cache .mypy_cache htmlcov .coverage
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
