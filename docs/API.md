# API Reference

Supplier Scout endpoints are exposed under `/plugin/supplierscout/`.

## Endpoint summary

| Endpoint | Method | Permission | Description |
|---|---|---|---|
| `searchcandidates` | POST | Part write | Search one or all configured suppliers for ranked candidate matches |
| `applycandidates` | POST | Part write | Create or update supplier parts and refresh part pricing |
| `runresync` | POST | Part write or Admin | Run or queue a manual supplier resync |
| `clearcache` | POST | Admin | Clear response caches for one supplier or all suppliers |
| `ratelimitstatus` | GET or POST | Part write | Return current API usage and daily quota status |
| `dashboardmetrics` | GET | None | Return dashboard diagnostics for registered suppliers |
| `tokendebug` | GET or POST | Part write | Inspect token extraction and query planning for a part |

Notes:

- Every endpoint also accepts a `.json` suffix (for example `/plugin/supplierscout/runresync.json`).
- Browser requests must satisfy normal InvenTree session + CSRF requirements.
- `Part write` means add/change/delete permission for parts.
- `Admin` means staff or superuser access.

## `POST /plugin/supplierscout/searchcandidates`

Search supplier APIs for a part and return ranked candidates.

### Request body

```json
{
   "pk": 123,
   "supplier": 7,
   "query": "10k 0603 resistor",
   "top_n": 10,
   "min_qty": 1,
   "max_qty": 100
}
```

### Request fields

- `pk` required: InvenTree part primary key.
- `supplier` optional: supplier company primary key. Omit or use `""`, `0`, `"all"`, or `"*"` to search all configured suppliers.
- `query` optional: explicit query string. If omitted/empty, Supplier Scout builds a query from part metadata.
- `top_n` optional: maximum ranked results returned after scoring.
- `min_qty` optional: lower quantity bound when selecting price breaks.
- `max_qty` optional: preferred upper quantity bound when selecting price breaks.

### Response highlights

- `message`, `query`, `count`, and `candidates`.
- Candidate metadata includes rank score and existing supplier-part match info.
- `debug` includes token sources, semantic hints, numeric constraints, and supplier attempt/failure details.

## `POST /plugin/supplierscout/applycandidates`

Create or update supplier parts from candidates returned by `searchcandidates`.

### Request body

```json
{
   "pk": 123,
   "supplier": 7,
   "candidates": [
      {
         "supplier_part_number": "RC0603FR-0710KL",
         "manufacturer_part_number": "RC0603FR-0710KL",
         "description": "10 kOhm Thick Film Resistor 0603",
         "price_breaks": [
            { "quantity": 1, "price": 0.02 },
            { "quantity": 100, "price": 0.01 }
         ]
      }
   ]
}
```

### Response highlights

- `created`, `updated`, `errors`, and per-candidate `results`.
- Part pricing is refreshed automatically when any candidate import succeeds.

## `POST /plugin/supplierscout/runresync`

Trigger a manual resync of existing supplier parts.

### Request body

```json
{
   "supplier": 7,
   "part_pk": 123,
   "async": true
}
```

### Request fields

- `supplier` required: supplier company primary key.
- `part_pk` optional: resync only supplier parts attached to this part.
- `async` optional: truthy (`1`, `true`, `yes`, `on`, `y`) queues background work.
- `action` optional: `reset_cursor` resets the scheduled supplier resync round-robin cursor.

### Permission rules

- Users with part write permission may resync a single part (`part_pk`).
- Supplier-wide resync without `part_pk` requires admin access.
- `action = reset_cursor` requires admin access.

### Operational note

Async resync requires the InvenTree worker from the main checkout:

```bash
cd /home/inventree
source dev/venv/bin/activate
invoke worker
```

## `POST /plugin/supplierscout/clearcache`

Clear cached supplier API responses.

### Request body (single supplier)

```json
{
   "supplier": 7
}
```

### Request body (all suppliers)

```json
{}
```

### Response highlights

- Supplier-specific response returns `scope = supplier` with `cache` diagnostics.
- Global response returns `scope = all` with a `suppliers` list.
- Cache paths are sanitized before being returned.

## `GET|POST /plugin/supplierscout/ratelimitstatus`

Return current API usage state for one supplier or all configured suppliers.

### Inputs

- `GET /plugin/supplierscout/ratelimitstatus?supplier=7`
- `POST` body `{ "supplier": 7 }`
- Omit `supplier` to return all registered suppliers.

### Response highlights

- `updated_ts` timestamp.
- Per-supplier usage includes `configured`, `rate_limit_per_second`, `daily_limit`, `daily_count`, `daily_remaining`, `daily_percent_used`, and `daily_reset_at`.

## `GET /plugin/supplierscout/dashboardmetrics`

Return dashboard diagnostics for every registered supplier.

### Response highlights

- `query_metrics` for historical request totals.
- `api_usage` for current rate-limit counters.
- `cache_status` for dashboard cache diagnostics.

## `GET|POST /plugin/supplierscout/tokendebug`

Inspect how Supplier Scout derived the query for a part.

### Inputs

- `GET /plugin/supplierscout/tokendebug?pk=123`
- `POST` body `{ "pk": 123 }`

### Response highlights

- Top-level `part_pk` and `query`.
- `debug.tokens`, `debug.token_sources`, and `debug.token_attribution`.
- `debug.semantic_hints` for inferred component type and extracted values.
- `debug.query_debug` for name/token plan details.

## Common error responses

Most endpoints return JSON with a `message` on failure.

- `400` invalid supplier or part identifiers.
- `403` missing permission or admin-only operation.
- `404` unknown suppliers or missing parts.
- `500` unexpected internal failure.
- `503` async queue submission failure from `runresync`.
