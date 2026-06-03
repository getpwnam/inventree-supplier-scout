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

## System Requirements

Supplier Scout depends on InvenTree plugin integration features. A system administrator should verify these are enabled before users start configuration:

- **Plugin UI integration** so the **Supplier Match** action and dashboard widget can be rendered in the web interface.
- **Background workers and scheduled tasks** so scheduled supplier resync jobs can run.
- **Plugin URL / API route integration** so plugin endpoints under `/plugin/supplierscout/` are available.

Runtime dependencies are installed automatically from the package. To build or modify the frontend locally, you will also need Node.js and `npm`.

## Quick Install

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

## Quick Setup

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

## Screenshot

![Supplier Match action screenshot](docs/images/supplier-match-action.png)

## Documentation

- **User guide**: [docs/USER_GUIDE.md](docs/USER_GUIDE.md)
- **Configuration**: [docs/CONFIGURATION.md](docs/CONFIGURATION.md)
- **API reference**: [docs/API.md](docs/API.md)
- **Search token extraction**: [docs/SEARCH_TOKENS.md](docs/SEARCH_TOKENS.md)
- **Development guide**: [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)

