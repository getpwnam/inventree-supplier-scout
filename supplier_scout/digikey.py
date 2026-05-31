"""DigiKey supplier adapter."""

import time

try:
    from django.utils.translation import gettext_lazy as _  # type: ignore[import-not-found]
except Exception:  # pragma: no cover - fallback for isolated unit tests

    def _(value):
        return value


from .adapters import SupplierAPIClient
from .mouser import MouserSupplierAdapter


DIGIKEY_CLIENT_ID_SETTING = "DIGIKEY_CLIENT_ID"
DIGIKEY_CLIENT_SECRET_SETTING = "DIGIKEY_CLIENT_SECRET"


DIGIKEY_SETTINGS = {
    "DIGIKEY_PK": {
        "name": _("DigiKey Supplier ID"),
        "description": _("Primary key of the DigiKey supplier"),
        "model": "company.company",
    },
    DIGIKEY_CLIENT_ID_SETTING: {
        "name": _("DigiKey OAuth2 client ID"),
        "description": _("DigiKey API OAuth2 client ID"),
    },
    DIGIKEY_CLIENT_SECRET_SETTING: {
        "name": _("DigiKey OAuth2 client secret"),
        "description": _("DigiKey API OAuth2 client secret"),
        "protected": True,
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
    DIGIKEY_CLIENT_ID_SETTING: {
        "name": _("DigiKey OAuth2 client ID (user override)"),
        "description": _("User-specific DigiKey OAuth2 client ID"),
        "protected": True,
    },
    DIGIKEY_CLIENT_SECRET_SETTING: {
        "name": _("DigiKey OAuth2 client secret (user override)"),
        "description": _("User-specific DigiKey OAuth2 client secret"),
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
    min_price_quantity_setting = "DIGIKEY_MIN_PRICE_QUANTITY"
    max_price_quantity_setting = "DIGIKEY_MAX_PRICE_QUANTITY"
    cache_ttl_setting = "DIGIKEY_CACHE_TTL"
    cache_dir_name = "inventree_digikey"
    SEARCH_ENDPOINT = "https://api.digikey.com/services/partsearch/v3/partnumbersearch"
    KEYWORD_ENDPOINT = "https://api.digikey.com/services/partsearch/v3/keywordsearch"
    TOKEN_ENDPOINT = "https://api.digikey.com/v1/oauth2/token"

    def __init__(self, plugin):
        super().__init__(plugin)
        self.transport = SupplierAPIClient(
            plugin,
            base_url="https://api.digikey.com",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        self._oauth_access_token = ""
        self._oauth_access_token_expires_at = 0
        self._request_user = None

    def _get_client_id(self, user=None):
        if user is not None:
            user_client_id = self.plugin.get_user_setting(
                DIGIKEY_CLIENT_ID_SETTING, user=user, backup_value=None
            )
            if user_client_id not in (None, ""):
                return str(user_client_id).strip()

        global_client_id = self.get_setting(DIGIKEY_CLIENT_ID_SETTING, backup_value="")
        return str(global_client_id).strip()

    def _get_client_secret(self, user=None):
        if user is not None:
            user_client_secret = self.plugin.get_user_setting(
                DIGIKEY_CLIENT_SECRET_SETTING, user=user, backup_value=None
            )
            if user_client_secret not in (None, ""):
                return str(user_client_secret).strip()

        global_client_secret = self.get_setting(
            DIGIKEY_CLIENT_SECRET_SETTING, backup_value=""
        )
        return str(global_client_secret).strip()

    def has_search_credentials(self, user=None):
        return (
            self._get_client_id(user=user) != ""
            and self._get_client_secret(user=user) != ""
        )

    def _get_oauth_access_token(self, user=None):
        now_ts = int(time.time())
        if self._oauth_access_token and now_ts < self._oauth_access_token_expires_at:
            return self._oauth_access_token

        response = self.transport.api_call(
            self.TOKEN_ENDPOINT,
            method="POST",
            data={
                "client_id": self._get_client_id(user=user),
                "client_secret": self._get_client_secret(user=user),
                "grant_type": "client_credentials",
            },
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
            simple_response=False,
            endpoint_is_url=True,
            timeout=15,
        )

        payload = response.json()
        access_token = str(payload.get("access_token") or "").strip()
        expires_in_seconds = int(payload.get("expires_in") or 300)
        refresh_margin_seconds = 60
        self._oauth_access_token = access_token
        self._oauth_access_token_expires_at = max(
            now_ts + 1, now_ts + expires_in_seconds - refresh_margin_seconds
        )
        return access_token

    def _post(self, url, payload, user=None):
        self.enforce_api_rate_limits(cost=1)
        if user is None:
            user = self._request_user

        client_id = self._get_client_id(user=user)
        access_token = self._get_oauth_access_token(user=user)

        headers = self.transport.api_headers
        headers["Authorization"] = "Bearer " + access_token
        headers["X-DIGIKEY-Client-Id"] = client_id

        return self.transport.api_call(
            url,
            method="POST",
            json=payload,
            headers=headers,
            simple_response=False,
            endpoint_is_url=True,
            timeout=15,
        )

    def _build_search_url(self, user=None):
        del user
        return self.SEARCH_ENDPOINT

    def _build_keyword_url(self, user=None):
        del user
        return self.KEYWORD_ENDPOINT

    def get_candidates(
        self, query, max_results=25, user=None, min_qty=None, max_qty=None
    ):
        self._request_user = user
        try:
            return super().get_candidates(
                query=query,
                max_results=max_results,
                user=user,
                min_qty=min_qty,
                max_qty=max_qty,
            )
        finally:
            self._request_user = None
