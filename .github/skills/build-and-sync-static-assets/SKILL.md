---
name: build-and-sync-static-assets
description: "Build frontend assets and then sync supplier_scout static files to InvenTree dev static serving path in one workflow. Use when preparing UI changes for local runtime verification."
---

# Build And Sync Static Assets

Use this workflow when frontend code changed and runtime must reflect the latest build.

## Goal
Produce fresh frontend bundles and copy them to the InvenTree dev static directory actually served at runtime.

## Steps
1. Build frontend assets:
   cd /home/inventree-supplier-scout/frontend && npm run build
2. Sync output to InvenTree dev static path:
   rsync -av --delete /home/inventree-supplier-scout/supplier_scout/static/ /home/inventree/dev/static/plugins/supplierscout/
3. Report a concise summary of both commands (build result + sync bytes sent/deleted files).

## Optional validation
1. Load manifest: http://127.0.0.1:8000/static/plugins/supplierscout/.vite/manifest.json
2. Resolve `src/Panel.tsx` chunk and fetch it.
3. Confirm marker strings if requested (for example: API Usage, Resync Supplier Batch, Reset Supplier Cursor).

## Notes
- This skill is optimized for local dev in this workspace.
- If you only need copying, use `/static-asset-sync`.
