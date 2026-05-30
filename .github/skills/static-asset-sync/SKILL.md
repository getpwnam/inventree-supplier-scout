---
name: static-asset-sync
description: "Run after frontend build to sync supplier_scout static assets into InvenTree dev static serving path. Use when build output exists but UI looks stale, or when asked to sync plugin statics."
---

# Static Asset Sync

Use this workflow after building frontend assets in this repository.

## Goal
Ensure files from this repository's static output are copied to the InvenTree dev static directory that is actually served at runtime.

## Steps
1. Confirm source static output exists at /home/inventree-supplier-scout/supplier_scout/static/.
2. Run the sync command:
   rsync -av --delete /home/inventree-supplier-scout/supplier_scout/static/ /home/inventree/dev/static/plugins/supplierscout/
3. Report a short result summary including bytes sent and whether any files were deleted.

## Optional validation
1. Read manifest from http://127.0.0.1:8000/static/plugins/supplierscout/.vite/manifest.json.
2. Resolve the chunk for src/Panel.tsx.
3. Fetch the chunk and confirm expected marker strings are present when requested.

## Notes
- This skill performs sync only. It does not build frontend assets.
- Run frontend build first from /home/inventree-supplier-scout/frontend when needed.
