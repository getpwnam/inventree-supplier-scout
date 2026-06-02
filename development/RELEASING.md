# Releasing SupplierScout

This guide is a reusable template for `v0.1.1` and later releases.

## Versioning

1. Update plugin version in `supplier_scout/__init__.py`:

```python
PLUGIN_VERSION = "0.1.1"
```

2. Commit and push the version bump.

## One-Command Release Readiness Check

Run this from the plugin repository root:

```bash
bash development/scripts/release-readiness.sh
```

This command performs:

- backend translation check
- plugin unittest run
- frontend build (`npm ci`, `translate`, `build`)
- package build (`sdist` and `wheel`)
- `twine check` validation

## Manual Release Checklist

1. Ensure working tree is clean.
2. Confirm `supplier_scout/__init__.py` version matches the intended tag.
3. Run `bash development/scripts/release-readiness.sh`.
4. Confirm GitHub Actions secret `PYPI_API_TOKEN` is set.
5. Create a GitHub Release with matching tag, for example `v0.1.1`.
6. Do not mark as pre-release unless package version is pre-release (`rc`, `b`, `a`).
7. Watch `.github/workflows/pypi.yaml` until publish is green.
8. Verify package appears on PyPI.
9. Validate install in a clean environment:

```bash
rm -rf /tmp/iss-test
python3 -m venv /tmp/iss-test
/tmp/iss-test/bin/pip install -q --upgrade pip
/tmp/iss-test/bin/pip install inventree-supplier-scout
/tmp/iss-test/bin/python -c "import importlib.metadata as m; print(m.version('inventree-supplier-scout'))"
```

## Post-Release Checks

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
