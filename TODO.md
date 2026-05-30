# TODO

## Panel UX overhaul

### 1. General layout tightening
- Modal overall feels unwieldy; needs a tighter, denser layout.
- Supplier select: make it compact (`size='xs'`), add an **"All Supported"** default option at top (searches all configured suppliers).
- Quantity boxes (Min/Max): small inline inputs side-by-side, not full-width.
- **"Find Matches" button**: move to the bottom action bar (alongside Cancel / Add / Update Selected), remove from the header group.

### 2. Token generation checkbox panel
When the user expands "Show Search Query":
- Show checkboxes to control which token groups are included:
  - [ ] Part name  (`TOKEN_NAME_MODE`)
  - [ ] Part name tokens  (split/extracted tokens)
  - [ ] Category names  (`TOKEN_INCLUDE_CATEGORY_NAMES`)
  - [ ] Parameters  (`TOKEN_PARAMETER_NAMES`)
- Default checkbox state = derived from the effective `TOKEN_NAME_MODE` setting for the current user.
- The resulting keyword tokens appear in a **Mantine `TagsInput`** — each token is a removable pill chip; user can add/delete tags manually.
- The `TagsInput` value is what gets sent as the search payload, so user edits are fully respected.
- Replaces the current plain textarea entirely.

---

## Static asset sync automation
After every `npm run build`, files must be synced to the InvenTree dev static dir:
```
rsync -av --delete \
  /home/inventree-supplier-scout/supplier_scout/static/ \
  /home/inventree/dev/static/plugins/supplierscout/
```
Skill added: use `/static-asset-sync` to run this workflow in chat.

Combined skill added: use `/build-and-sync-static-assets` to run build + sync in one command.

Future improvement: add a post-build step (Vite plugin, `package.json` script, or VS Code task) so this happens automatically even without chat invocation.
