#!/usr/bin/env bash
set -euo pipefail

# Rebuild frontend assets and sync plugin statics into the local InvenTree dev path.
# Intended for fast branch-switch testing in this workspace.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
FRONTEND_DIR="${REPO_ROOT}/frontend"
STATIC_DIR="${REPO_ROOT}/supplier_scout/static"
TARGET_DIR="${INVENTREE_STATIC_PLUGIN_DIR:-/home/inventree/dev/static/plugins/supplierscout}"
LOCKFILE="${FRONTEND_DIR}/package-lock.json"
LOCK_HASH_FILE="${REPO_ROOT}/.git/.supplier-scout-frontend-lock.sha256"

if [[ ! -d "${FRONTEND_DIR}" ]]; then
  echo "frontend directory not found: ${FRONTEND_DIR}" >&2
  exit 1
fi

if [[ ! -f "${LOCKFILE}" ]]; then
  echo "package-lock.json not found: ${LOCKFILE}" >&2
  exit 1
fi

mkdir -p "${TARGET_DIR}"

NEW_HASH="$(sha256sum "${LOCKFILE}" | awk '{print $1}')"
OLD_HASH=""

if [[ -f "${LOCK_HASH_FILE}" ]]; then
  OLD_HASH="$(cat "${LOCK_HASH_FILE}")"
fi

pushd "${FRONTEND_DIR}" >/dev/null
if [[ "${NEW_HASH}" != "${OLD_HASH}" ]]; then
  echo "Detected frontend lockfile change. Running npm ci..."
  npm ci
else
  echo "Frontend lockfile unchanged. Reusing existing node_modules."
fi

npm run translate
npm run build
popd >/dev/null

printf '%s\n' "${NEW_HASH}" > "${LOCK_HASH_FILE}"

rsync -av --delete "${STATIC_DIR}/" "${TARGET_DIR}/"

echo "Frontend static refresh complete."
echo "Source : ${STATIC_DIR}/"
echo "Target : ${TARGET_DIR}/"
