#!/usr/bin/env bash
# ===========================================================================
# erp-ai-copilot — installation locale (macOS / Linux)
#
#   bash scripts/bootstrap.sh
#
# Détection d'architecture : le projet fonctionne partout, mais SQL Server
# n'existe qu'en x86-64. Sur ARM64 (Mac Apple Silicon), la base se fait en
# SQLite ; sur x86-64 (LG Gram, Linux, CI), on peut démarrer SQL Server.
# ===========================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PY_VERSION="${PY_VERSION:-3.12}"
ARCH="$(uname -m)"

echo "==> erp-ai-copilot — bootstrap"
echo "    dossier : $ROOT"
echo "    archi   : $ARCH"
echo "    python  : $PY_VERSION"

# --- 1. Environnement virtuel ---------------------------------------------
if [ ! -d .venv ]; then
  if command -v uv >/dev/null 2>&1; then
    uv venv --python "$PY_VERSION" .venv
  elif command -v python"$PY_VERSION" >/dev/null 2>&1; then
    python"$PY_VERSION" -m venv .venv
  else
    echo "[ERREUR] Python $PY_VERSION introuvable. Installer uv : brew install uv" >&2
    exit 1
  fi
fi

# --- 2. Dépendances --------------------------------------------------------
if command -v uv >/dev/null 2>&1; then
  uv pip install --python .venv/bin/python -e ".[dev]"
else
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/python -m pip install -e ".[dev]"
fi

# --- 3. Rendre le package importable --------------------------------------
# macOS marque comme « hidden » tout fichier dont le nom commence par « _ ».
# Or CPython >= 3.12.13 ignore volontairement les fichiers .pth cachés : le
# .pth d'installation éditable (_editable_impl_*.pth) n'est donc jamais lu.
# On écrit un .pth au nom neutre, qui n'est pas marqué hidden.
SITE_PACKAGES="$(.venv/bin/python -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')"
echo "$ROOT/src" > "$SITE_PACKAGES/erp_ai_src.pth"
echo "    [ok] .pth d'accessibilité écrit : $SITE_PACKAGES/erp_ai_src.pth"

# --- 4. Configuration ------------------------------------------------------
if [ ! -f .env ]; then
  cp .env.example .env
  echo "    [ok] .env créé depuis .env.example (à personnaliser)"
else
  echo "    [ok] .env déjà présent"
fi

# --- 5. Base de données et index ------------------------------------------
if [ "$ARCH" = "x86_64" ] || [ "$ARCH" = "amd64" ]; then
  echo "    [i] Architecture x86-64 : SQL Server est utilisable en conteneur natif."
  echo "        docker compose --profile sqlserver up -d sqlserver"
  echo "        puis DATABASE_URL=mssql+pyodbc://... dans .env"
else
  echo "    [i] Architecture $ARCH : SQL Server n'existe pas en natif."
  echo "        La base locale se fait en SQLite (identique en schéma, pas en moteur)."
fi

export PYTHONPATH="$ROOT/src"
.venv/bin/python -m erp_ai.cli init-db
.venv/bin/python -m erp_ai.cli ingest

echo
echo "==> Terminé. Pour démarrer l'API :"
echo "    make serve      # http://127.0.0.1:8000/docs"
echo "    make ask Q=\"Quelles sont les règles de relance client ?\""
