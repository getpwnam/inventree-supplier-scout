# TODO

## Support cart generation (investigation + implementation plan)

### Goal
- Allow users to generate, edit, and submit supplier shopping carts for any registered SupplierScout supplier.
- Support launching cart generation from the Bill of Materials (BOM) page.
- Optionally account for current stock levels so only shortfalls are ordered.

### Proposed backend design
- Add persistent cart models (new Django models in plugin):
  - `SupplierCart` (owner, supplier, status, source, created/updated timestamps).
  - `SupplierCartLine` (part, supplier part reference/SKU, quantity, unit price snapshot, note, line status).
  - `SupplierCartSource` metadata for traceability (`manual`, `bom`, and source object IDs).
- Add JSON endpoints:
  - `cart/create` (manual or BOM-driven cart draft creation).
  - `cart/<id>` GET/PATCH (read/update draft cart and lines).
  - `cart/<id>/submit` POST (submit cart via supplier adapter).
  - `cart/list` GET (active/recent carts for current user).
- Extend supplier adapter contract with optional cart submission method:
  - `submit_cart(cart_payload)` returns external order/cart reference and status.
  - If unsupported, keep cart in `ready` state and return actionable message to export/copy.

### BOM + stock handling approach
- For BOM-based cart creation, resolve required quantities from BOM line items.
- If `use_stock=true`, subtract available stock (configurable source: on-hand only, or on-hand + buildable).
- Skip lines with no shortage; keep skipped summary in response for auditability.
- Preserve unresolved lines in draft with validation warnings (e.g. no supplier candidate chosen).

### Proposed frontend UX
- Add a new primary action on BOM pages: **Generate Supplier Cart**.
- Add a plugin page/modal to:
  - Review generated lines.
  - Edit quantities and chosen supplier items.
  - Add manual lines before submission.
  - Submit cart and display supplier response/reference.
- Add a manual cart entry point from plugin settings/dashboard context so users can build carts from scratch.

### Delivery phases
1. **Data layer + API skeleton**: models, migrations, serializer helpers, draft CRUD.
2. **BOM cart generation**: BOM endpoint + optional stock-offset logic.
3. **Frontend draft editor**: line editing, add/remove items, validation messaging.
4. **Supplier submission adapters**: Mouser first, then generic fallback behavior for unsupported suppliers.
5. **Polish + observability**: audit trail, status transitions, dashboard/cart metrics.

### Acceptance criteria
- Users can create a draft cart from a BOM with optional stock-aware shortage calculation.
- Users can create and edit a manual cart without BOM input.
- Users can add/remove/edit lines before submit.
- Users can submit carts for supported suppliers and receive a persisted submission result.
- Unsupported suppliers return a clear non-fatal message with fallback action.

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
