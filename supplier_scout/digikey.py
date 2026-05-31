"""DigiKey supplier adapter."""

try:
    from django.utils.translation import gettext_lazy as _  # type: ignore[import-not-found]
except Exception:  # pragma: no cover - fallback for isolated unit tests

    def _(value):
        return value


from .mouser import MouserSupplierAdapter


DIGIKEY_SEARCH_API_KEY_SETTING = "DIGIKEY_APIKEY_SEARCH"


DIGIKEY_SETTINGS = {
    "DIGIKEY_PK": {
        "name": _("DigiKey Supplier ID"),
        "description": _("Primary key of the DigiKey supplier"),
        "model": "company.company",
    },
    DIGIKEY_SEARCH_API_KEY_SETTING: {
        "name": _("DigiKey search API key"),
        "description": _("DigiKey part search API key"),
    },
    "DIGIKEY_MAX_CANDIDATES": {
        "name": _("DigiKey max candidates"),
        "description": _("Maximum number of DigiKey candidates considered for ranking"),
        "default": 40,
    },
    "DIGIKEY_MIN_PRICE_QUANTITY": {
        "name": _("DigiKey minimum quantity for price selection"),
        "description": _(
            "Select the best price for at least this quantity (e.g., 1 for single units, 10 for tape). Leave blank for no limit."
        ),
        "default": 1,
    },
    "DIGIKEY_MAX_PRICE_QUANTITY": {
        "name": _("DigiKey maximum quantity for price selection"),
        "description": _(
            "Prefer prices for quantities up to this number (e.g., 50 for hobby, 1000 for production). Leave blank for no limit."
        ),
        "default": "",
    },
    "DIGIKEY_CACHE_TTL": {
        "name": _("DigiKey response cache TTL"),
        "description": _(
            "Cache DigiKey API responses for this many seconds (3600 = 1 hour, 0 = disabled). Reduces API calls and rate limiting."
        ),
        "default": 3600,
    },
}


DIGIKEY_USER_SETTINGS = {
    DIGIKEY_SEARCH_API_KEY_SETTING: {
        "name": _("DigiKey search API key (user override)"),
        "description": _("User-specific DigiKey search API key"),
        "protected": True,
    },
    "DIGIKEY_MIN_PRICE_QUANTITY": {
        "name": _("DigiKey minimum quantity for price selection (user override)"),
        "description": _(
            "Select the best price for at least this quantity (e.g., 1 for single units, 10 for tape)."
        ),
    },
    "DIGIKEY_MAX_PRICE_QUANTITY": {
        "name": _("DigiKey maximum quantity for price selection (user override)"),
        "description": _(
            "Prefer prices for quantities up to this number (e.g., 50 for hobby, 1000 for production)."
        ),
    },
}


class DigikeySupplierAdapter(MouserSupplierAdapter):
    key = "digikey"
    name = "DigiKey"
    settings = DIGIKEY_SETTINGS
    user_settings = DIGIKEY_USER_SETTINGS
    company_setting = "DIGIKEY_PK"
    max_candidates_setting = "DIGIKEY_MAX_CANDIDATES"
    api_rate_limit_per_second_default = 1
    api_daily_limit_default = 1000
    search_api_key_setting = DIGIKEY_SEARCH_API_KEY_SETTING
    min_price_quantity_setting = "DIGIKEY_MIN_PRICE_QUANTITY"
    max_price_quantity_setting = "DIGIKEY_MAX_PRICE_QUANTITY"
    cache_ttl_setting = "DIGIKEY_CACHE_TTL"
    cache_dir_name = "inventree_digikey"
