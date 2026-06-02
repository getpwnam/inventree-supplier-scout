# Changelog

All notable changes to this project will be documented in this file.

## v0.1.1 - 2026-06-02

### Summary

This release fixes a reliability issue where the Supplier Match primary action
could disappear from part pages when plugin UI feature generation encountered
invalid user-scoped setting values.

### Fixes

- Hardened TOP_N_CANDIDATES parsing for primary action context generation.
  Invalid values now safely fall back to 10.
- Primary action rendering no longer fails due to non-numeric user override
  values.
- Hardened supplier credential readiness checks.
- If user-specific credential lookup raises an exception, checks now fall back
  to global credentials.
- Prevents full primary-action drop when user-scoped credential settings are
  malformed.

### Affected Behavior

- Before: /api/plugins/ui/features/primary_action/ could return [] when part
  and permissions were valid.
- After: primary action remains available, with safe fallback behavior for
  invalid user-scoped values.

### Validation Performed

- Confirmed primary action endpoint returns expected Supplier Scout action for
  purchaseable part.
- Set user override TOP_N_CANDIDATES to abc; endpoint still returns action
  with top_n: 10.
- Added and executed regression test:

```bash
python3 -m unittest supplier_scout.test_core_query_helpers.TestSupplierScoutCoreHelpers.test_search_ready_suppliers_fallbacks_to_global_credentials
```

### Notes

- This release focuses on resilience and is backward-compatible with existing
  plugin settings.
