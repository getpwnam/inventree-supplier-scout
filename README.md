# SupplierScout

**SupplierScout** is an [InvenTree](https://inventree.org) plugin that automatically finds, matches, and imports supplier parts for your inventory. Given any purchaseable part in InvenTree, it derives a search query from the part's name, parameters, IPN, MPN, and category, then searches configured supplier APIs, ranks the results, and lets you add or update supplier parts and price breaks with one click.

## Features

- **Automatic query derivation** — builds a supplier search query from the part's name, Internal Part Number (IPN), Manufacturer Part Number (MPN), parameters, and category hierarchy, with normalisation for passive component values (capacitance, resistance, EIA codes, engineering shorthand).
- **Candidate ranking** — scores results using a configurable mix of text-match similarity, stock availability, and unit price; supports *balanced*, *availability-first*, and *price-first* strategies.
- **One-click import** — select one or more candidates and add or update supplier parts, manufacturer parts, and price breaks directly from the part detail page.
- **Scheduled resync** — periodically refreshes existing supplier-part metadata and price breaks in the background, with per-supplier interval and batch-size controls.
- **Response caching** — caches API responses to reduce quota usage and improve responsiveness.
- **API usage tracking** — per-supplier request counters and daily-limit enforcement with a dashboard widget showing live metrics.
- **Per-user supplier credentials** — users can store their own supplier credentials (API key or OAuth2 client credentials), overriding global settings for their own searches.
- **Token debug endpoint** — inspect exactly which tokens were extracted from a part and how the final search query was constructed.

## Supported Suppliers

| Supplier | Search | Scheduled Resync | Notes |
|---|---|---|---|
| **DigiKey** | ✅ | ✅ | Uses DigiKey OAuth2 client credentials (`client_id` + `client_secret`) for authenticated API access; response caching |
| **Mouser Electronics** | ✅ | ✅ | Part-number and keyword search; response caching; per-user API keys |

Additional suppliers can be added by implementing a `BaseSupplierAdapter` subclass.

## Installation

### Via the InvenTree Plugin Manager (recommended)

1. Open InvenTree → **Settings → Plugins**.
2. Click **Install Plugin**.
3. Enter the package name: `inventree-supplier-scout`
4. Click **Install** and then **Activate**.

### Via the Command Line

```bash
pip install inventree-supplier-scout
```

After installation, restart InvenTree and activate the plugin in **Settings → Plugins**.

### From Source

```bash
git clone https://github.com/getpwnam/inventree-supplier-scout.git
cd inventree-supplier-scout
pip install -e .
```

### InvenTree system configuration requirements

Supplier Scout depends on InvenTree plugin integration features. A system administrator should verify these are enabled before users start configuration:

- **Plugin UI integration** so the **Supplier Match** action and dashboard widget can be rendered in the web interface.
- **Background workers and scheduled tasks** so scheduled supplier resync jobs can run.
- **Plugin URL / API route integration** so plugin endpoints under `/plugin/supplierscout/` are available.

## Initial Setup

After activating the plugin, you must configure at least one supplier before you can search:

1. Open **Settings → Plugins** and click on **Supplier Scout → Plugin Settings**.
2. Set either **DigiKey Supplier ID** (`DIGIKEY_PK`) or **Mouser Supplier ID** (`MOUSER_PK`) to the primary key of your supplier company record in InvenTree.
3. Set credentials for your chosen supplier:
   - DigiKey: `DIGIKEY_CLIENT_ID` and `DIGIKEY_CLIENT_SECRET`
   - Mouser: `MOUSER_APIKEY_SEARCH`
4. Save. The *Supplier Match* action will now appear on every purchaseable part.
   If you only set API credentials without a supplier company ID, the action
   will stay hidden because the plugin has not been registered against a
   supplier record yet.

## User Documentation

- **Getting started (web UI)**: [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md)
- **API reference**: [docs/API.md](docs/API.md)

## How Search Tokens Are Derived

SupplierScout builds a keyword search query from a part's structured data rather than relying on the part name alone. The goal is to generate a query that a supplier's API will match against real component listings.

### Token Sources

Tokens are extracted from the following sources, in priority order:

| Source | Description |
|---|---|
| **Manufacturer Part Number (MPN)** | Highest-signal identifier; used first if available |
| **IPN** | Internal Part Number |
| **SKU** | Supplier-facing stock-keeping unit |
| **Part parameters** | Parameter values (e.g., `100nF`, `10kΩ`, `0402`), with unit template attached |
| **Part category names** | Direct category and every ancestor up the tree (configurable) |
| **Part name / description** | Fallback when no structured tokens exist (configurable) |

### Text Tokenisation

Each source value is split on non-alphanumeric boundaries (spaces, dashes, slashes, underscores). Sub-tokens are also extracted from compound tokens. The following normalisation rules are applied to every fragment:

| Rule | Input example | Output tokens |
|---|---|---|
| Raw chunk | `100nF` | `100nF` |
| Split sub-token | `MLCC-0402` | `MLCC`, `0402` |
| Shorthand expansion | `4.7n` | `4.7nf`, `4.7nF` |
| Shorthand expansion | `10k` | `10kohm`, `10kOhm` |
| Capacitance normalisation | `4n7` | `4.7nF` |
| Resistance normalisation | `4R7` | `4.7ohm` |
| EIA capacitor code | `104` | `100nF` |
| Unitised parameter | value=`100`, unit=`nF` | `100nF`, `100 nF` |

Tokens shorter than two characters are discarded. Duplicate tokens (case-insensitive) are removed.

### Semantic Hints and Query Plan

After token extraction, SupplierScout inspects the tokens for semantic clues:

- **Component type** — inferred from the part name prefix (`C_`/`C-` → capacitor, `R_`/`R-` → resistor, `L_`/`L-` → inductor) or from parameter names containing *capacit*, *resist*, *induct*.
- **Electrical characteristics** — capacitance, resistance, inductance, package, tolerance, voltage, and current values are extracted from parameters and tokens.

The final query is assembled from:

1. Component type hint (e.g., `capacitor`)
2. Electrical characteristic values (e.g., `100nF`, `0402`, `10%`, `25V`)
3. Structured tokens (MPN → IPN → SKU → parameters → category)
4. Name/description tokens — included *always*, *never*, or only as *fallback* when no structured tokens exist (controlled by `TOKEN_NAME_MODE`)

The query is capped at ten tokens before being sent to the supplier API.

### Numeric Constraints

Voltage and current parameter values are also extracted as hard constraints. Candidates whose spec attributes violate these constraints (e.g., rated voltage below the required minimum) receive a score penalty, so they appear lower in the ranked list.

### Inspecting Token Extraction

Use the **Token Debug** endpoint to see exactly what SupplierScout extracted from a part:

```
GET /plugin/supplierscout/tokendebug?pk=<part_pk>
```

The response includes the full token list, per-source breakdown, semantic hints, and the final query token sequence.

## Configuration Reference

Settings are managed through the InvenTree plugin settings UI (**Settings → Plugins → Supplier Scout**). Scope labels below indicate where each setting is stored:

- **Global** — applies to all users; set by an administrator in plugin settings.
- **User** — per-user override; each user sets their own value in their personal plugin settings. An empty value falls back to the global setting.

### DigiKey

| Setting key | Scope | Default | Description |
|---|---|---|---|
| `DIGIKEY_PK` | Global | — | Primary key of the DigiKey supplier company record in InvenTree. Must be set before search works. |
| `DIGIKEY_CLIENT_ID` | Global, User | Global: `—` / User: `—` | DigiKey OAuth2 client ID. User scope overrides global when set. |
| `DIGIKEY_CLIENT_SECRET` | Global, User | Global: `—` / User: `—` | DigiKey OAuth2 client secret (stored encrypted). User scope overrides global when set. |
| `DIGIKEY_MAX_CANDIDATES` | Global | `40` | Maximum number of raw DigiKey results fetched before ranking. |
| `DIGIKEY_MIN_PRICE_QUANTITY` | Global, User | Global: `1` / User: `—` | Minimum quantity used when selecting the best price break. User scope overrides global when set. |
| `DIGIKEY_MAX_PRICE_QUANTITY` | Global, User | Global: *(empty)* / User: `—` | Upper bound for price-break quantity selection. User scope overrides global when set. |
| `DIGIKEY_CACHE_TTL` | Global | `3600` | How long (in seconds) to cache DigiKey API responses on disk. Set to `0` to disable caching. Cache files are stored in `~/.cache/inventree_digikey/`. |

### DigiKey Scheduled Resync

| Setting key | Scope | Default | Description |
|---|---|---|---|
| `DIGIKEY_RESYNC_ENABLED` | Global | `False` | Enable periodic background refresh of existing DigiKey supplier parts. |
| `DIGIKEY_RESYNC_INTERVAL_MINUTES` | Global | `1440` | How often to run a DigiKey resync (in minutes). Default is once per day. |
| `DIGIKEY_RESYNC_BATCH_SIZE` | Global | `100` | Maximum number of existing DigiKey supplier parts to refresh per scheduled run. Uses a round-robin cursor to spread work across runs. |
| `DIGIKEY_API_RATE_LIMIT_PER_SECOND` | Global | `1` | Maximum DigiKey API requests per second. Set to `0` to disable rate limiting. |
| `DIGIKEY_API_DAILY_LIMIT` | Global | `1000` | Maximum DigiKey API requests per day. Requests beyond this limit raise an error until midnight UTC. Set to `0` for no limit. |

### Mouser Electronics

| Setting key | Scope | Default | Description |
|---|---|---|---|
| `MOUSER_PK` | Global | — | Primary key of the Mouser supplier company record in InvenTree. Must be set before search works. |
| `MOUSER_APIKEY_SEARCH` | Global, User | Global: `—` / User: `—` | Mouser Part Search API key (stored encrypted). Obtain from the [Mouser API Hub](https://www.mouser.com/api-hub/). User scope overrides global when set. |
| `MOUSER_MAX_CANDIDATES` | Global | `40` | Maximum number of raw Mouser results fetched before ranking. Higher values improve match quality at the cost of more API calls. |
| `MOUSER_MIN_PRICE_QUANTITY` | Global, User | Global: `1` / User: `—` | Minimum quantity used when selecting the best price break (e.g., `1` for single-unit prices, `10` for tape-and-reel). User scope overrides global when set. |
| `MOUSER_MAX_PRICE_QUANTITY` | Global, User | Global: *(empty)* / User: `—` | Upper bound for price-break quantity selection. Leave empty to use the smallest available price break above the minimum. User scope overrides global when set. |
| `MOUSER_CACHE_TTL` | Global | `3600` | How long (in seconds) to cache Mouser API responses on disk. Set to `0` to disable caching. Cache files are stored in `~/.cache/inventree_mouser/`. |

### Mouser Scheduled Resync

| Setting key | Scope | Default | Description |
|---|---|---|---|
| `MOUSER_RESYNC_ENABLED` | Global | `False` | Enable periodic background refresh of existing Mouser supplier parts. |
| `MOUSER_RESYNC_INTERVAL_MINUTES` | Global | `1440` | How often to run a Mouser resync (in minutes). Default is once per day. |
| `MOUSER_RESYNC_BATCH_SIZE` | Global | `100` | Maximum number of existing Mouser supplier parts to refresh per scheduled run. Uses a round-robin cursor to spread work across runs. |
| `MOUSER_API_RATE_LIMIT_PER_SECOND` | Global | `1` | Maximum Mouser API requests per second. Set to `0` to disable rate limiting. |
| `MOUSER_API_DAILY_LIMIT` | Global | `1000` | Maximum Mouser API requests per day. Requests beyond this limit raise an error until midnight UTC. Set to `0` for no limit. |

### General Scheduler

| Setting key | Scope | Default | Description |
|---|---|---|---|
| `RESYNC_SCHEDULER_TICK_MINUTES` | Global | `15` | How often the background scheduler checks whether any supplier is due for a resync. The per-supplier interval settings control the actual refresh frequency; this is just the polling granularity. |

### Candidate Ranking

| Setting key | Scope | Default | Description |
|---|---|---|---|
| `RANKING_STRATEGY` | Global, User | Global: `balanced` / User: *(empty)* | Candidate ranking strategy. `balanced` weights match similarity (45 %), availability (35 %), and price (20 %). `availability` prioritises stock (50 %). `price` prioritises cost (50 %). User scope overrides global when set. |
| `TOP_N_CANDIDATES` | User | *(empty)* | Number of ranked candidates displayed in the search panel. Leave empty to use the default of `10`. |

### Token Generation

| Setting key | Scope | Default | Description |
|---|---|---|---|
| `TOKEN_PARAMETER_NAMES` | Global | *(empty)* | Comma- or newline-separated list of parameter template names to include in token extraction. Leave empty to use **all** parameters. Example: `Capacitance, Voltage Rating, Package`. |
| `TOKEN_INCLUDE_CATEGORY_NAMES` | Global | `True` | When enabled, the part's direct category name and every ancestor category name are added as token sources. Disable if category names interfere with search results. |
| `TOKEN_NAME_MODE` | Global, User | Global: `fallback` / User: *(empty)* | Controls when the part name and description are included as search tokens. `fallback` — only when no structured tokens (MPN, IPN, parameters, categories) are available. `always` — always append name tokens. `never` — never include name tokens. User scope overrides global when set. |

## Testing and Coverage

See [development/TESTING.md](development/TESTING.md) for test commands, local CI-equivalent checks, and coverage details.

## Development Docs

Developer-focused documentation and helper scripts live under [development/](development/):

- [development/README.md](development/README.md) - workflow, sourcemaps, branch-switch guidance.
- [development/TESTING.md](development/TESTING.md) - backend/frontend checks and coverage.
- [development/frontend.md](development/frontend.md) - frontend-specific setup and build notes.
- [development/TODO.md](development/TODO.md) - engineering backlog and design notes.
