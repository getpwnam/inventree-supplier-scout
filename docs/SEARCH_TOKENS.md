# Search Token Extraction

SupplierScout builds supplier search queries from structured part data rather than relying on the part name alone. The goal is to produce queries that supplier APIs can match against real component listings.

## Token Sources

Tokens are extracted from the following sources, in priority order:

| Source | Description |
|---|---|
| **Manufacturer Part Number (MPN)** | Highest-signal identifier and first choice when available |
| **IPN** | Internal Part Number |
| **SKU** | Supplier-facing stock-keeping unit |
| **Part parameters** | Parameter values such as `100nF`, `10kOhm`, or `0402`, combined with unit template metadata |
| **Part category names** | Direct category and every ancestor up the tree when enabled |
| **Part name / description** | Fallback source when structured tokens are limited or disabled |

## Text Tokenisation

Each source value is split on non-alphanumeric boundaries such as spaces, dashes, slashes, and underscores. Sub-tokens are also extracted from compound tokens. The following normalisation rules are applied:

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

Tokens shorter than two characters are discarded. Duplicate tokens are removed case-insensitively.

## Semantic Hints And Query Plan

After token extraction, SupplierScout inspects the token set for semantic clues:

- **Component type**: inferred from the part name prefix (`C_` or `C-` for capacitor, `R_` or `R-` for resistor, `L_` or `L-` for inductor) or from parameter names containing `capacit`, `resist`, or `induct`.
- **Electrical characteristics**: capacitance, resistance, inductance, package, tolerance, voltage, and current values are extracted from parameters and tokens.

The final query is assembled from:

1. Component type hint, such as `capacitor`
2. Electrical characteristic values, such as `100nF`, `0402`, `10%`, or `25V`
3. Structured tokens in priority order: MPN, IPN, SKU, parameters, categories
4. Name and description tokens, included according to `TOKEN_NAME_MODE`

The query is capped at ten tokens before being sent to the supplier API.

## Numeric Constraints

Voltage and current parameter values are also extracted as hard constraints. Candidates whose spec attributes violate these constraints, such as a rated voltage below the required minimum, receive a score penalty and rank lower.

## Inspecting Token Extraction

Use the **Token Debug** endpoint to inspect exactly what SupplierScout extracted from a part:

```text
GET /plugin/supplierscout/tokendebug?pk=<part_pk>
```

The response includes the full token list, per-source breakdown, semantic hints, and the final query token sequence.

For endpoint details and response structure, see [API.md](API.md).