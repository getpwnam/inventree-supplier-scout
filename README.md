# SupplierScout

Part search, matching and ordering with popular suppliers

## Installation

### InvenTree Plugin Manager

... todo ...

### Command Line 

To install manually via the command line, run the following command:

```bash
pip install inventree-supplier-scout
```

## Configuration

... todo ...

## Usage

... todo ...

## Testing and Coverage

Run unit tests locally:

```bash
python3 -m unittest discover -s supplier_scout -p "test_*.py"
```

Run tests with coverage and generate XML for Codecov:

```bash
python3 -m pip install coverage
coverage run -m unittest discover -s supplier_scout -p "test_*.py"
coverage report -m
coverage xml
```

Coverage is uploaded in CI via the GitHub Actions workflow at `.github/workflows/ci.yaml`.
If `CODECOV_TOKEN` is not configured, CI will skip Codecov upload and still enforce the local coverage threshold.

### Run CI Checks Locally (Pipeline Equivalent)

Run the backend CI checks locally:

```bash
python3 -m pip install -U ruff coverage wheel setuptools twine build
ruff check
coverage run -m unittest discover -s supplier_scout -p "test_*.py"
coverage report -m --fail-under=45
coverage xml
python3 -m build
```

Run the frontend CI checks locally:

```bash
cd frontend
npm install
npm run translate
npm run build
npm run lint
```

### See CI and Coverage on GitHub

1. Push a branch and open a pull request.
2. Open the repository `Actions` tab and select `CI Checks`.
3. Review logs for the `ci` and `frontend` jobs.
4. Check Codecov status/comment on the pull request after coverage upload.

### Codecov Token (Optional)

- For private or pre-release repositories, set `CODECOV_TOKEN` as a GitHub Actions repository secret to enable Codecov uploads.
- If no token is configured, CI still runs tests and enforces coverage with `--fail-under`.
