#!/usr/bin/env bash
set -euo pipefail

# Reset generated plugin static files back to HEAD.
# Useful when branch switching leaves only compiled artifact diffs.

FORCE="${1:-}"
REPO_ROOT="$(git rev-parse --show-toplevel)"

cd "${REPO_ROOT}"

if [[ "${FORCE}" != "--force" ]]; then
  if ! git diff --quiet -- frontend/src; then
    echo "Frontend source changes detected in frontend/src."
    echo "Refusing to reset generated static files without confirmation."
    echo "Re-run with --force if you really want to discard static diffs now."
    exit 1
  fi
fi

git restore --staged --worktree supplier_scout/static

echo "Reset generated static artifacts to HEAD: supplier_scout/static"
