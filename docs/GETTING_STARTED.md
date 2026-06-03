# Getting Started (Web UI)

This quickstart walks through the day-to-day Supplier Scout workflow in the InvenTree web interface.

## 1) Open a purchaseable part

Open any purchaseable part record, then use the **Supplier Match** action in the part actions bar.

![Supplier Match action screenshot](images/supplier-match-action.png)

## 2) Optionally refine search criteria

In the Supplier Match panel, refine the search before running it:

1. Confirm or edit the generated search query.
2. Choose a supplier (or all configured suppliers).

![Supplier Match panel screenshot](images/supplier-match-panel.png)

## 3) Search and review matches

Click **Find Matches** to review ranked candidates with part number, stock, and pricing.

![Candidate review table screenshot](images/candidate-review-table.png)

## 4) Import selected candidates

Select one or more rows and click **Add Selected** to create or update supplier parts and import price breaks.

![Supplier pricing screenshot](images/supplier-pricing.png)

## 5) Monitor API usage from the dashboard

Open the InvenTree dashboard to see **Supplier Scout Metrics** for query volume, API budget usage, and cache diagnostics.

![Dashboard widget screenshot](images/dashboard-query-metrics.png)

## 6) Verify plugin settings

If UI actions are missing, check plugin settings and supplier credentials first.

![Plugin settings screenshot](images/plugin-settings.png)

## Troubleshooting checklist

- Confirm a supplier company ID is configured (`DIGIKEY_PK` and/or `MOUSER_PK`).
- Confirm supplier credentials are set globally or per-user.
- Confirm your InvenTree system has plugin UI integration enabled.
- For async/scheduled operations, confirm the background worker is running.

For endpoint-level troubleshooting and payload details, see [API.md](API.md).
