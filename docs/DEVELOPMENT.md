# Development

This guide consolidates contributor workflow, testing, frontend development, release checks, and local helper scripts for Supplier Scout.

## Contributing

When making changes:

1. Keep the Python plugin code, frontend sources, and generated static artifacts consistent.
2. Run the relevant checks in this guide before opening or updating a pull request.
3. Use the frontend workflow section when working on UI code.
4. Use the release section for versioning and publish validation, not for normal feature work.

## Local Environment Notes

### Background workers in the dev container

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

### Sourcemaps

When frontend code is bundled, many source files become a few compiled JavaScript files in `supplier_scout/static/`.
Sourcemaps (`*.js.map`) are metadata files that let browser dev tools map compiled code back to the original TypeScript and TSX source for debugging.

In short:

- Keep sourcemaps when debugging frontend behavior.
- Expect sourcemap diffs when frontend bundles change.
- If you are only validating behavior and not debugging minified code, sourcemap-only diffs are usually low risk.

## Frontend Workflow

### Architecture

The frontend integrates natively with the InvenTree user interface and uses React with Mantine to match the InvenTree stack.

- [React](https://react.dev/)
- [Mantine](https://mantine.dev/)
- [Vite](https://vitejs.dev/)

### Install frontend dependencies

From the `frontend` directory:

```bash
npm ci
```

### Translate frontend strings

```bash
npm run translate
```

### Build frontend assets

```bash
npm run build
```

This compiles the frontend into `../supplier_scout/static` so the built assets are bundled into the Python package.

For local branch-switch testing with InvenTree dev static serving, run from the repository root:

```bash
./development/scripts/refresh-branch-static.sh
```

This rebuilds frontend assets and syncs `supplier_scout/static/` into `/home/inventree/dev/static/plugins/supplierscout/`.

### Run the frontend dev server

```bash
npm run dev
```

This usually starts on `localhost:5174` and reloads automatically when source files change.

You will also need the InvenTree frontend dev server running on `localhost:5173`, using `invoke dev.frontend-server` in the InvenTree repository.

### Linting and formatting

```bash
npm run lint
```

```bash
npm run lint:fix
```

## Testing And Coverage

### Backend translation check

Run the backend translation guard locally:

```bash
python3 .github/scripts/check_backend_translations.py
```

This check fails if user-facing backend strings are not wrapped for translation using the gettext alias `_()` in plugin Python code.

### Backend tests with InvenTree invoke

```bash
cd /home/inventree
invoke dev.test -r supplier_scout
```

To run only the database-backed test:

```bash
cd /home/inventree
invoke dev.test -r supplier_scout.test_db_upsert_supplier_part -v 2
```

`invoke` must be run from the main InvenTree source tree, the directory containing `tasks.py`, not from this plugin repository root.

### Standalone test fallback

```bash
python3 -m unittest discover -s supplier_scout -p "test_*.py"
```

### Coverage fallback

```bash
python3 -m pip install coverage
coverage run -m unittest discover -s supplier_scout -p "test_*.py"
coverage report -m
coverage xml
```

Coverage is uploaded in CI via `.github/workflows/ci.yaml`. If `CODECOV_TOKEN` is not configured, CI skips Codecov upload and still enforces the local coverage threshold.

### Manual API smoke tests

Supplier Scout endpoints are mounted under `/plugin/supplierscout/` inside the running InvenTree instance.

Browser-based checks are often easiest because they reuse your authenticated session and CSRF context. In browser dev tools, run `fetch(...)` from an InvenTree page after opening the app.

If your console session does not already define a CSRF helper, paste this first:

```js
function getCookie(name) {
	return document.cookie
		.split(';')
		.map((item) => item.trim())
		.find((item) => item.startsWith(`${name}=`))
		?.slice(name.length + 1) || '';
}
```

#### Clear one supplier cache

```js
fetch('/plugin/supplierscout/clearcache.json', {
	method: 'POST',
	credentials: 'same-origin',
	headers: {
		'Content-Type': 'application/json',
		'X-CSRFToken': getCookie('csrftoken'),
	},
	body: JSON.stringify({ supplier: 7 }),
}).then((r) => r.json())
```

Expected result:

- HTTP `200`
- `scope: "supplier"`
- `cache.cleared_file_count` and `cache.failed_file_count`

#### Clear all supplier caches

```js
fetch('/plugin/supplierscout/clearcache.json', {
	method: 'POST',
	credentials: 'same-origin',
	headers: {
		'Content-Type': 'application/json',
		'X-CSRFToken': getCookie('csrftoken'),
	},
	body: JSON.stringify({}),
}).then((r) => r.json())
```

Expected result:

- HTTP `200`
- `scope: "all"`
- `suppliers` array with per-supplier cache results

#### Reset the scheduled resync cursor

```js
fetch('/plugin/supplierscout/runresync.json', {
	method: 'POST',
	credentials: 'same-origin',
	headers: {
		'Content-Type': 'application/json',
		'X-CSRFToken': getCookie('csrftoken'),
	},
	body: JSON.stringify({ supplier: 7, action: 'reset_cursor' }),
}).then((r) => r.json())
```

Expected result:

- HTTP `200`
- `action: "reset_cursor"`
- `cursor_after: 0`

#### Run a synchronous supplier resync

```js
fetch('/plugin/supplierscout/runresync.json', {
	method: 'POST',
	credentials: 'same-origin',
	headers: {
		'Content-Type': 'application/json',
		'X-CSRFToken': getCookie('csrftoken'),
	},
	body: JSON.stringify({ supplier: 7 }),
}).then((r) => r.json())
```

Expected result:

- HTTP `200`
- `action: "resync"`
- counters like `processed`, `updated`, `failed`, and `skipped`

#### Run an asynchronous supplier resync

```js
fetch('/plugin/supplierscout/runresync.json', {
	method: 'POST',
	credentials: 'same-origin',
	headers: {
		'Content-Type': 'application/json',
		'X-CSRFToken': getCookie('csrftoken'),
	},
	body: JSON.stringify({ supplier: 7, async: true }),
}).then((r) => r.json())
```

Expected result:

- HTTP `202`
- `queued: true`
- `task_id` and `task_url`

Important:

- The queued task will stay pending until the InvenTree background worker is running.
- Start it from `/home/inventree`, not this plugin repo:

```bash
cd /home/inventree
source dev/venv/bin/activate
invoke worker
```

#### Poll background task status

```js
fetch('/api/background-task/<task_id>/', {
	credentials: 'same-origin',
}).then((r) => r.json())
```

Expected result for a successful run:

- `exists: true`
- `pending: false`
- `complete: true`
- `success: true`
- `http_status: 200`

#### Token debug and rate limit status

```js
fetch('/plugin/supplierscout/tokendebug.json?pk=123', {
	credentials: 'same-origin',
}).then((r) => r.json())

fetch('/plugin/supplierscout/ratelimitstatus.json?supplier=7', {
	credentials: 'same-origin',
}).then((r) => r.json())
```

Use these endpoints to verify query construction and supplier quota visibility while testing the search panel.

### Run CI checks locally

Backend checks:

```bash
python3 -m pip install -U ruff coverage wheel setuptools twine build
ruff check
python3 .github/scripts/check_backend_translations.py
cd /home/inventree
invoke dev.test -r supplier_scout
cd /home/inventree-supplier-scout
coverage run -m unittest discover -s supplier_scout -p "test_*.py"
coverage report -m --fail-under=50
coverage xml
python3 -m build
```

Frontend checks:

```bash
cd frontend
npm ci
npm run translate
npm run build
npm run lint
```

### CI and coverage on GitHub

1. Push a branch and open a pull request.
2. Open the repository `Actions` tab and select `CI Checks`.
3. Review logs for the `ci` and `frontend` jobs.
4. Check Codecov status or pull-request comment after coverage upload.

### Codecov token

- For private or pre-release repositories, set `CODECOV_TOKEN` as a GitHub Actions repository secret to enable Codecov uploads.
- If no token is configured, CI still runs tests and enforces coverage with `--fail-under`.

## Release Workflow

This guide is a reusable template for `v0.1.1` and later releases.

### Versioning

1. Update plugin version in `supplier_scout/__init__.py`:

```python
PLUGIN_VERSION = "0.1.1"
```

2. Commit and push the version bump.

### One-command release readiness check

Run this from the plugin repository root:

```bash
bash development/scripts/release-readiness.sh
```

This command performs:

- backend translation check
- plugin unittest run
- frontend build with `npm ci`, `translate`, and `build`
- package build for `sdist` and `wheel`
- `twine check` validation

### Manual release checklist

1. Ensure the working tree is clean.
2. Confirm `supplier_scout/__init__.py` version matches the intended tag.
3. Run `bash development/scripts/release-readiness.sh`.
4. Confirm GitHub Actions secret `PYPI_API_TOKEN` is set.
5. Create a GitHub release with a matching tag, for example `v0.1.1`.
6. Do not mark as pre-release unless the package version is pre-release, such as `rc`, `b`, or `a`.
7. Watch `.github/workflows/pypi.yaml` until publish is green.
8. Verify the package appears on PyPI.
9. Validate install in a clean environment:

```bash
rm -rf /tmp/iss-test
python3 -m venv /tmp/iss-test
/tmp/iss-test/bin/pip install -q --upgrade pip
/tmp/iss-test/bin/pip install inventree-supplier-scout
/tmp/iss-test/bin/python -c "import importlib.metadata as m; print(m.version('inventree-supplier-scout'))"
```

### Post-release checks

1. Verify plugin entrypoint metadata:

```bash
/tmp/iss-test/bin/python -c "import importlib.metadata as m; print([e.value for e in m.entry_points(group='inventree_plugins') if e.name == 'SupplierScout'])"
```

2. Validate plugin route registration in local InvenTree runtime:

```bash
cd /home/inventree
source dev/venv/bin/activate
/home/inventree/dev/venv/bin/python src/backend/InvenTree/manage.py shell -c "from plugin.registry import registry; p = registry.plugins.get('supplierscout') or registry.plugins_full.get('supplierscout'); print([getattr(u, 'name', None) for u in p.setup_urls()])"
```

## Helper Scripts

All helper scripts live under `development/scripts/`.

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

Enable automatic refresh after checkout or merge when frontend or static paths changed:

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