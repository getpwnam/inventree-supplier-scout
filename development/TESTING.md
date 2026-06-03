# Testing and Coverage

For release-specific steps and a one-command readiness script, see [development/RELEASING.md](RELEASING.md).

## Backend Translation Check

Run the backend translation guard locally:

```bash
python3 .github/scripts/check_backend_translations.py
```

This check fails if user-facing backend strings are not wrapped for translation
using the gettext alias `_()` in plugin Python code.

Run unit tests with InvenTree invoke (recommended):

```bash
cd /home/inventree
invoke dev.test -r supplier_scout
```

To run only the database-backed test:

```bash
cd /home/inventree
invoke dev.test -r supplier_scout.test_db_upsert_supplier_part -v 2
```

Note: `invoke` must be run from the main InvenTree source tree (the directory
containing `tasks.py`), not from this plugin repository root.

Run plugin tests directly with unittest (standalone fallback):

```bash
python3 -m unittest discover -s supplier_scout -p "test_*.py"
```

Run tests with coverage and generate XML for Codecov (standalone fallback):

```bash
python3 -m pip install coverage
coverage run -m unittest discover -s supplier_scout -p "test_*.py"
coverage report -m
coverage xml
```

Coverage is uploaded in CI via the GitHub Actions workflow at `.github/workflows/ci.yaml`.
If `CODECOV_TOKEN` is not configured, CI will skip Codecov upload and still enforce the local coverage threshold.

## Manual API Smoke Tests

Supplier Scout endpoints are mounted under `/plugin/supplierscout/` inside the running InvenTree instance.

Browser-based checks are often the easiest option because they reuse your authenticated session and CSRF context. In Edge or Chrome dev tools, run `fetch(...)` from an InvenTree page after opening the app in the browser.

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

### Clear one supplier cache

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

### Clear all supplier caches

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

### Reset the scheduled resync cursor

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

### Run a synchronous supplier resync

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

### Run an asynchronous supplier resync

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

### Poll background task status

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

### Token debug and rate limit status

```js
fetch('/plugin/supplierscout/tokendebug.json?pk=123', {
	credentials: 'same-origin',
}).then((r) => r.json())

fetch('/plugin/supplierscout/ratelimitstatus.json?supplier=7', {
	credentials: 'same-origin',
}).then((r) => r.json())
```

Use these endpoints to verify query construction and supplier quota visibility while testing the search panel.

## Run CI Checks Locally (Pipeline Equivalent)

Run the backend CI checks locally:

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

Run the frontend CI checks locally:

```bash
cd frontend
npm ci
npm run translate
npm run build
npm run lint
```

Run the frontend checks locally:

```bash
cd frontend

npm ci
npm run translate
npm run build
npm run lint
```

## See CI and Coverage on GitHub

1. Push a branch and open a pull request.
2. Open the repository `Actions` tab and select `CI Checks`.
3. Review logs for the `ci` and `frontend` jobs.
4. Check Codecov status/comment on the pull request after coverage upload.

## Codecov Token (Optional)

- For private or pre-release repositories, set `CODECOV_TOKEN` as a GitHub Actions repository secret to enable Codecov uploads.
- If no token is configured, CI still runs tests and enforces coverage with `--fail-under`.
