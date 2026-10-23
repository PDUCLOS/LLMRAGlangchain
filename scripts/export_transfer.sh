#!/usr/bin/env bash
# ===========================================================================
# erp-ai-copilot — export pour transfert vers une autre machine
#
#   bash scripts/export_transfer.sh
#
# Produit dist/erp-ai-copilot-<date>.tar.gz contenant le code, la
# documentation et les tests — sans l'environnement virtuel, sans les
# données locales et sans l'historique git.
# ===========================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

DATE="$(date +%Y%m%d-%H%M)"
OUT_DIR="$ROOT/dist"
ARCHIVE="$OUT_DIR/erp-ai-copilot-$DATE.tar.gz"

mkdir -p "$OUT_DIR"

tar -czf "$ARCHIVE" \
  --exclude='.venv' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='.pytest_cache' \
  --exclude='.ruff_cache' \
  --exclude='.mypy_cache' \
  --exclude='data' \
  --exclude='dist' \
  --exclude='.env' \
  --exclude='.DS_Store' \
  .

echo "Archive créée : $ARCHIVE"
echo "Taille : $(du -h "$ARCHIVE" | cut -f1)"
echo
echo "Restauration sur la machine cible :"
echo "    tar -xzf $(basename "$ARCHIVE") -C ~/erp-ai-copilot"
echo "    cd ~/erp-ai-copilot && bash scripts/bootstrap.sh"
