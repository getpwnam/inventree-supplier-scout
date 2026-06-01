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

echo "Installed local hooks path: .githooks"
echo "Hooks will run frontend rebuild/sync only when frontend/static files changed."
