# Development Workflow

This directory contains local developer tooling for branch switching, frontend static sync, and generated artifact cleanup.

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
