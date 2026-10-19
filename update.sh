#!/usr/bin/env bash
# ==============================================================================
# CliOS - Script de Mise à Jour Automatique
# Description: Récupère les dernières modifications Git, met à jour les dépendances
#              Python (.venv) et réapplique les permissions.
# Développement uniquement : la production utilise tools/release_cli.py.
# ==============================================================================

set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${SCRIPT_DIR}"
VENV_PIP="${PROJECT_DIR}/.venv/bin/pip"

echo -e "\033[1;34m▶ [1/3] Fetching updates from GitHub...\033[0m"
echo -e "\033[1;33m⚠ Development tool only. Use release_cli.py in production.\033[0m"
cd "$PROJECT_DIR"

if ! git rev-parse --is-inside-work-tree &>/dev/null; then
    echo -e "\033[1;31m[ERROR] The folder ${PROJECT_DIR} is not a valid Git repository.\033[0m" >&2
    exit 1
fi

git fetch origin

CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo 'main')"
echo -e " ℹ Active branch: \033[1m${CURRENT_BRANCH}\033[0m"

# Application de la mise à jour Git
git pull --rebase origin "$CURRENT_BRANCH"
echo -e "\033[1;32m✓ Source code updated successfully.\033[0m"

echo -e "\n\033[1;34m▶ [2/3] Checking Python dependencies...\033[0m"
if [[ -f "$VENV_PIP" && -f "${PROJECT_DIR}/requirements.txt" ]]; then
    echo " ℹ Upgrading Python packages in .venv..."
    "$VENV_PIP" install -r "${PROJECT_DIR}/requirements.txt"
    echo -e "\033[1;32m✓ Python dependencies up to date.\033[0m"
else
    echo " ℹ .venv not found or incomplete, skipping the pip update."
fi

echo -e "\n\033[1;34m▶ [3/3] Reapplying executable permissions...\033[0m"
chmod +x "${PROJECT_DIR}/clios" "${PROJECT_DIR}/install.sh" "${PROJECT_DIR}/update.sh" "${PROJECT_DIR}"/tools/*.sh 2>/dev/null || true
echo -e "\033[1;32m✓ Permissions reapplied.\033[0m"

echo -e "\n\033[1;32m══════════════════════════════════════════════════════════════════\033[0m"
echo -e "\033[1;32m  ✓ CliOS UPDATE COMPLETED SUCCESSFULLY!\033[0m"
echo -e "\033[1;32m══════════════════════════════════════════════════════════════════\033[0m\n"
