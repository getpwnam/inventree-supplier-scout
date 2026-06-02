# Changelog

All notable changes to this project will be documented in this file.

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
