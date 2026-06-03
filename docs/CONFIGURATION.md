# Configuration Reference

Settings are managed through the InvenTree plugin settings UI under **Settings -> Plugins -> Supplier Scout**.

## Scope Model

- **Global**: applies to all users and is managed by an administrator.
- **User**: per-user override stored in each user's plugin settings. Empty user values fall back to the global value.

## Required Supplier Mapping And Credentials

You must configure at least one supplier company mapping before searches are available.

- Set `DIGIKEY_PK` and/or `MOUSER_PK` to the primary key of the supplier company record in InvenTree.
- Then configure matching credentials:
  - DigiKey: `DIGIKEY_CLIENT_ID` and `DIGIKEY_CLIENT_SECRET`
  - Mouser: `MOUSER_APIKEY_SEARCH`
- If credentials are set without the supplier company ID, the **Supplier Match** action stays hidden because the plugin is not registered against a supplier record.

## DigiKey

| Setting key | Scope | Default | Description |
|---|---|---|---|
| `DIGIKEY_PK` | Global | — | Primary key of the DigiKey supplier company record in InvenTree. Must be set before search works. |
| `DIGIKEY_CLIENT_ID` | Global, User | Global: `—` / User: `—` | DigiKey OAuth2 client ID. User scope overrides global when set. |
| `DIGIKEY_CLIENT_SECRET` | Global, User | Global: `—` / User: `—` | DigiKey OAuth2 client secret stored encrypted. User scope overrides global when set. |
| `DIGIKEY_MAX_CANDIDATES` | Global | `40` | Maximum number of raw DigiKey results fetched before ranking. |
| `DIGIKEY_MIN_PRICE_QUANTITY` | Global, User | Global: `1` / User: `—` | Minimum quantity used when selecting the best price break. User scope overrides global when set. |
| `DIGIKEY_MAX_PRICE_QUANTITY` | Global, User | Global: *(empty)* / User: `—` | Upper bound for price-break quantity selection. User scope overrides global when set. |
| `DIGIKEY_CACHE_TTL` | Global | `3600` | How long, in seconds, to cache DigiKey API responses on disk. Set to `0` to disable caching. Cache files are stored in `~/.cache/inventree_digikey/`. |

## DigiKey Scheduled Resync

| Setting key | Scope | Default | Description |
|---|---|---|---|
| `DIGIKEY_RESYNC_ENABLED` | Global | `False` | Enable periodic background refresh of existing DigiKey supplier parts. |
| `DIGIKEY_RESYNC_INTERVAL_MINUTES` | Global | `1440` | How often to run a DigiKey resync, in minutes. Default is once per day. |
| `DIGIKEY_RESYNC_BATCH_SIZE` | Global | `100` | Maximum number of existing DigiKey supplier parts to refresh per scheduled run. Uses a round-robin cursor to spread work across runs. |
| `DIGIKEY_API_RATE_LIMIT_PER_SECOND` | Global | `1` | Maximum DigiKey API requests per second. Set to `0` to disable rate limiting. |
| `DIGIKEY_API_DAILY_LIMIT` | Global | `1000` | Maximum DigiKey API requests per day. Requests beyond this limit raise an error until midnight UTC. Set to `0` for no limit. |

## Mouser Electronics

| Setting key | Scope | Default | Description |
|---|---|---|---|
| `MOUSER_PK` | Global | — | Primary key of the Mouser supplier company record in InvenTree. Must be set before search works. |
| `MOUSER_APIKEY_SEARCH` | Global, User | Global: `—` / User: `—` | Mouser Part Search API key stored encrypted. Obtain it from the [Mouser API Hub](https://www.mouser.com/api-hub/). User scope overrides global when set. |
| `MOUSER_MAX_CANDIDATES` | Global | `40` | Maximum number of raw Mouser results fetched before ranking. Higher values improve match quality at the cost of more API calls. |
| `MOUSER_MIN_PRICE_QUANTITY` | Global, User | Global: `1` / User: `—` | Minimum quantity used when selecting the best price break, such as `1` for single-unit prices or `10` for tape-and-reel. User scope overrides global when set. |
| `MOUSER_MAX_PRICE_QUANTITY` | Global, User | Global: *(empty)* / User: `—` | Upper bound for price-break quantity selection. Leave empty to use the smallest available price break above the minimum. User scope overrides global when set. |
| `MOUSER_CACHE_TTL` | Global | `3600` | How long, in seconds, to cache Mouser API responses on disk. Set to `0` to disable caching. Cache files are stored in `~/.cache/inventree_mouser/`. |

## Mouser Scheduled Resync

| Setting key | Scope | Default | Description |
|---|---|---|---|
| `MOUSER_RESYNC_ENABLED` | Global | `False` | Enable periodic background refresh of existing Mouser supplier parts. |
| `MOUSER_RESYNC_INTERVAL_MINUTES` | Global | `1440` | How often to run a Mouser resync, in minutes. Default is once per day. |
| `MOUSER_RESYNC_BATCH_SIZE` | Global | `100` | Maximum number of existing Mouser supplier parts to refresh per scheduled run. Uses a round-robin cursor to spread work across runs. |
| `MOUSER_API_RATE_LIMIT_PER_SECOND` | Global | `1` | Maximum Mouser API requests per second. Set to `0` to disable rate limiting. |
| `MOUSER_API_DAILY_LIMIT` | Global | `1000` | Maximum Mouser API requests per day. Requests beyond this limit raise an error until midnight UTC. Set to `0` for no limit. |

## Scheduler

| Setting key | Scope | Default | Description |
|---|---|---|---|
| `RESYNC_SCHEDULER_TICK_MINUTES` | Global | `15` | How often the background scheduler checks whether any supplier is due for a resync. The per-supplier interval settings control the actual refresh frequency; this is the polling granularity. |

## Candidate Ranking

| Setting key | Scope | Default | Description |
|---|---|---|---|
| `RANKING_STRATEGY` | Global, User | Global: `balanced` / User: *(empty)* | Candidate ranking strategy. `balanced` weights match similarity, availability, and price. `availability` prioritises stock. `price` prioritises cost. User scope overrides global when set. |
| `TOP_N_CANDIDATES` | User | *(empty)* | Number of ranked candidates displayed in the search panel. Leave empty to use the default of `10`. |

## Token Generation

| Setting key | Scope | Default | Description |
|---|---|---|---|
| `TOKEN_PARAMETER_NAMES` | Global | *(empty)* | Comma- or newline-separated list of parameter template names to include in token extraction. Leave empty to use all parameters. Example: `Capacitance, Voltage Rating, Package`. |
| `TOKEN_INCLUDE_CATEGORY_NAMES` | Global | `True` | When enabled, the part's direct category name and every ancestor category name are added as token sources. Disable if category names interfere with search results. |
| `TOKEN_NAME_MODE` | Global, User | Global: `fallback` / User: *(empty)* | Controls when the part name and description are included as search tokens. `fallback` uses them only when no structured tokens exist. `always` always appends them. `never` excludes them. User scope overrides global when set. |

## Common Configuration Checks

- Confirm at least one supplier company ID is configured with `DIGIKEY_PK` and/or `MOUSER_PK`.
- Confirm matching credentials are set globally or per-user.
- Confirm InvenTree plugin UI integration is enabled.
- Confirm the InvenTree background worker is running if you expect scheduled or async resync behavior.