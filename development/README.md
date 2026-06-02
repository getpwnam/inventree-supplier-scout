# Development Workflow

This directory contains local developer tooling for branch switching, frontend static sync, and generated artifact cleanup.

## Release Workflow

Use [development/RELEASING.md](RELEASING.md) for a reusable release checklist template (including `v0.1.1` guidance).

For an automated readiness pass from repo root:

```bash
bash development/scripts/release-readiness.sh
```

## Background Workers In The Dev Container

Async Supplier Scout resync jobs are consumed by the InvenTree background worker, not by this plugin repository directly.

Start the worker from the main InvenTree checkout:

```bash
cd /home/inventree
source dev/venv/bin/activate
invoke worker
```

Why this matters:

- `invoke` must run from the repository that contains InvenTree's `tasks.py`.
- Running `invoke worker` from `/home/inventree-supplier-scout` fails with `Can't find any collection named 'tasks'!` because this plugin repository does not define the InvenTree invoke task collection.
- Supplier Scout async responses return a task URL like `/api/background-task/<task_id>/`; that task will remain pending until the InvenTree worker is running.

## Sourcemaps (What They Are)

When frontend code is bundled, many source files become a few compiled JavaScript files in `supplier_scout/static/`.
Sourcemaps (`*.js.map`) are metadata files that let browser dev tools map compiled code back to the original TypeScript/TSX source for debugging.

In short:

- Keep sourcemaps when debugging frontend behavior.
- Expect sourcemap diffs when frontend bundles change.
- If you are only validating behavior and not debugging minified code, sourcemap-only diffs are usually low risk.

## Scripts

All scripts are in `development/scripts/`.

### Refresh branch statics

Run after `git switch` or `git pull` when testing another branch:

```bash
./development/scripts/refresh-branch-static.sh
```

What it does:

1. Runs `npm ci` only when `frontend/package-lock.json` changed.
2. Rebuilds frontend assets.
3. Syncs plugin statics to `/home/inventree/dev/static/plugins/supplierscout/`.

Optional custom sync target:

```bash
INVENTREE_STATIC_PLUGIN_DIR=/path/to/inventree/dev/static/plugins/supplierscout ./development/scripts/refresh-branch-static.sh
```

### Install local git hooks

Enable automatic refresh after checkout/merge when frontend or static paths changed:

```bash
./development/scripts/install-dev-hooks.sh
```

This configures local git hooks with `core.hooksPath=.githooks`.

### Reset generated static artifacts

If only generated static files are dirty and you want a clean tree:

```bash
./development/scripts/reset-static-artifacts.sh
```

If frontend source changed and you still want to discard generated static files:

```bash
./development/scripts/reset-static-artifacts.sh --force
```
