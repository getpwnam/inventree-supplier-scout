# Changelog

All notable changes to this project will be documented in this file.

## v0.1.2 - Unreleased

### Added

- Added a compatibility matrix and release compatibility policy to project
  documentation.
- Clarified frontend CI steps by separating dependency installation from the
  build and lint stages.

### Changed

- Pinned frontend dependencies to a stable-compatible UI surface to avoid
  cross-track dependency drift.
- Removed strict plugin-version frontend checks that produced noisy mismatch
  warnings across supported InvenTree tracks.
- Updated local testing documentation with stable and edge frontend build
  validation steps.
- Set plugin runtime minimum InvenTree requirement to `>=1.4.0.dev0`.

### User Impact

- SupplierScout requires InvenTree `>=1.4.0.dev0`.
- SupplierScout uses the header primary action entry point on supported
  InvenTree builds.
- Plugin UI no longer reports misleading version mismatch warnings during normal
  cross-track use.

### Developer Experience

- Frontend compatibility is validated in CI with a dedicated frontend build and
  lint job.

## v0.1.1 - 2026-06-02

### Fixed

- Fixed an issue where the Supplier Match action could disappear from part
  pages even when supplier integrations were configured.
- Improved resilience when optional user-specific plugin settings contain
  invalid values.

### User Impact

- The Supplier Match button now remains available more reliably.
- Invalid user override values no longer hide the primary action.

### Compatibility

- Backward-compatible with existing plugin configuration.

### Developer Experience

- Added a release checklist and a one-command release readiness script to make
  packaging and publish preparation more consistent.
