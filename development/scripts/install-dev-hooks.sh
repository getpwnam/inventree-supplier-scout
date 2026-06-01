#!/usr/bin/env bash
set -euo pipefail

# Install optional local git hooks to auto-refresh plugin frontend statics
# after checkout/merge when frontend files changed.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

if [[ ! -d "${REPO_ROOT}/.git" ]]; then
  echo "Not a git repository: ${REPO_ROOT}" >&2
  exit 1
fi

chmod +x "${REPO_ROOT}/.githooks/post-checkout"
chmod +x "${REPO_ROOT}/.githooks/post-merge"

git -C "${REPO_ROOT}" config core.hooksPath .githooks

# Install pre-commit into .githooks so it is picked up by the custom hooksPath.
if command -v pre-commit > /dev/null 2>&1; then
  pre-commit install --hook-type pre-commit --git-dir "${REPO_ROOT}/.git" --overwrite 2>/dev/null || true
  # pre-commit installs to .git/hooks by default; move it to .githooks instead.
  if [[ -f "${REPO_ROOT}/.git/hooks/pre-commit" ]]; then
    mv "${REPO_ROOT}/.git/hooks/pre-commit" "${REPO_ROOT}/.githooks/pre-commit"
    chmod +x "${REPO_ROOT}/.githooks/pre-commit"
    echo "pre-commit hook installed to .githooks/pre-commit"
  fi
else
  echo "Warning: pre-commit not found; skipping pre-commit hook installation." >&2
fi

echo "Installed local hooks path: .githooks"
echo "Hooks will run frontend rebuild/sync only when frontend/static files changed."
