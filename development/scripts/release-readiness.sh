#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

echo "== SupplierScout release readiness =="
echo "repo: ${REPO_ROOT}"

cd "${REPO_ROOT}"

if [[ -n "$(git status --porcelain)" ]]; then
  echo "ERROR: Working tree is not clean. Commit or stash changes first."
  git status --short
  exit 1
fi

echo
echo "== Backend translation guard =="
python3 .github/scripts/check_backend_translations.py

echo
echo "== Plugin unit tests =="
python3 -m unittest discover -s supplier_scout -p "test_*.py"

echo
echo "== Frontend build =="
cd frontend
npm ci
npm run translate
npm run build

cd "${REPO_ROOT}"

echo
echo "== Package build and validation =="
python3 -m build
python3 -m twine check dist/*

echo
echo "== Artifacts =="
ls -1 dist

echo
echo "Release readiness checks passed."
