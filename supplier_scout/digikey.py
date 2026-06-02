"""DigiKey supplier adapter."""

import time
from urllib.parse import urlparse
from urllib.parse import urlunparse

try:
    from django.utils.translation import gettext_lazy as _  # type: ignore[import-not-found]
except Exception:  # pragma: no cover - fallback for isolated unit tests

    def _(value):
        return value


from .adapters import SupplierAPIClient
from .adapters import SupplierAPIRateLimitError
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
    # DigiKey Product Information API v4 exposes keyword search at this route.
    # MPN / DigiKey part numbers are supported as keyword inputs.
    SEARCH_ENDPOINT = "https://api.digikey.com/products/v4/search/keyword"
    KEYWORD_ENDPOINT = "https://api.digikey.com/products/v4/search/keyword"
    TOKEN_ENDPOINT = "https://api.digikey.com/v1/oauth2/token"

    DIGIKEY_SITE_OVERRIDES = {
        "GB": "UK",
    }

    DIGIKEY_SITE_HOSTS = {
        "US": "www.digikey.com",
        "UK": "www.digikey.co.uk",
        "IE": "www.digikey.ie",
        "DE": "www.digikey.de",
        "FR": "www.digikey.fr",
        "IT": "www.digikey.it",
        "ES": "www.digikey.es",
        "NL": "www.digikey.nl",
        "SE": "www.digikey.se",
        "NO": "www.digikey.no",
        "DK": "www.digikey.dk",
        "FI": "www.digikey.fi",
        "CH": "www.digikey.ch",
        "AT": "www.digikey.at",
        "BE": "www.digikey.be",
        "PL": "www.digikey.pl",
        "CZ": "www.digikey.cz",
        "HU": "www.digikey.hu",
        "RO": "www.digikey.ro",
        "PT": "www.digikey.pt",
        "CA": "www.digikey.ca",
        "AU": "www.digikey.com.au",
        "NZ": "www.digikey.co.nz",
        "SG": "www.digikey.sg",
        "HK": "www.digikey.hk",
        "JP": "www.digikey.co.jp",
        "KR": "www.digikey.kr",
        "TW": "www.digikey.com.tw",
        "CN": "www.digikey.cn",
    }

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
            try:
                user_client_id = self.plugin.get_user_setting(
                    DIGIKEY_CLIENT_ID_SETTING, user=user, backup_value=None
                )
                if user_client_id not in (None, ""):
                    return str(user_client_id).strip()
            except Exception as error:
                import logging

                logging.getLogger(__name__).warning(
                    "SupplierScout user credential read failed supplier=%s setting=%s user=%s error=%s",
                    getattr(self, "key", "digikey"),
                    DIGIKEY_CLIENT_ID_SETTING,
                    getattr(user, "username", None) or getattr(user, "pk", None),
                    error,
                )

        global_client_id = self.get_setting(DIGIKEY_CLIENT_ID_SETTING, backup_value="")
        return str(global_client_id).strip()

    def _get_client_secret(self, user=None):
        if user is not None:
            try:
                user_client_secret = self.plugin.get_user_setting(
                    DIGIKEY_CLIENT_SECRET_SETTING, user=user, backup_value=None
                )
                if user_client_secret not in (None, ""):
                    return str(user_client_secret).strip()
            except Exception:
                pass

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
        headers["X-DIGIKEY-Locale-Language"] = self._get_locale_language_code()
        headers["X-DIGIKEY-Locale-Currency"] = self._get_locale_currency_code()
        headers["X-DIGIKEY-Locale-Site"] = self._get_digikey_site_code()

        response = self.transport.api_call(
            url,
            method="POST",
            json=payload,
            headers=headers,
            simple_response=False,
            endpoint_is_url=True,
            timeout=15,
        )

        return response

    def _get_digikey_site_code(self):
        site = str(self._get_locale_country_code() or "US").upper()
        return self.DIGIKEY_SITE_OVERRIDES.get(site, site)

    def _get_digikey_link_language_code(self):
        language = str(self._get_locale_language_code() or "en").lower()
        if language == "zhs":
            return "zh-cn"
        if language == "zht":
            return "zh-tw"
        return language

    def _build_digikey_product_link(self, product_url):
        url_text = str(product_url or "").strip()
        if url_text == "":
            return ""

        parsed = urlparse(url_text)
        site_code = str(self._get_digikey_site_code() or "US").upper()

        host = self.DIGIKEY_SITE_HOSTS.get(site_code)
        if host:
            parsed = parsed._replace(netloc=host)

        return urlunparse(parsed._replace(query=""))

    def _build_search_url(self, user=None):
        del user
        return self.SEARCH_ENDPOINT

    def _build_keyword_url(self, user=None):
        del user
        return self.KEYWORD_ENDPOINT

    def _search_digikey_products(self, url, payload):
        # Try to get cached response
        cached_data = self._get_cached_response(url, payload)
        from_cache = cached_data is not None
        if cached_data is not None:
            response_data = cached_data
        else:
            # Cache miss or disabled, fetch from API
            try:
                response = self._post(url, payload)
            except SupplierAPIRateLimitError as exc:
                return {
                    "error_status": str(exc),
                    "products": [],
                }
            except Exception:
                return {
                    "error_status": _("Connection to DigiKey API failed"),
                    "products": [],
                }

            try:
                response_data = response.json()
            except Exception:
                return {
                    "error_status": _("Invalid JSON response from DigiKey"),
                    "products": [],
                }

            # Cache the response for future requests
            self._cache_response(url, payload, response_data)

        if not isinstance(response_data, dict):
            return {
                "error_status": _("Invalid response payload from DigiKey"),
                "products": [],
            }

        try:
            status_code = int(response_data.get("status") or 0)
        except Exception:
            status_code = 0

        if status_code >= 400:
            detail = str(response_data.get("detail") or "").strip()
            title = str(response_data.get("title") or "").strip()
            message = detail or title or _("DigiKey search error")
            return {
                "error_status": message,
                "products": [],
            }

        errors = self._coerce_list(response_data.get("Errors") or [])
        if errors:
            error = self._coerce_mapping(errors[0])
            code = error.get("Code")
            message = error.get("Message") or code or _("DigiKey search error")

            if code in ["SearchNotFound", "NotFound"]:
                return {"error_status": "OK", "products": []}

            return {
                "error_status": message,
                "products": [],
            }

        products = self._coerce_list(response_data.get("Products") or [])

        return {
            "error_status": "OK",
            "products": products,
            "from_cache": from_cache,
        }

    def _build_candidate_from_product(self, product_data, min_qty=None, max_qty=None):
        product_data = self._coerce_mapping(product_data)
        price_breaks = []
        min_price = None
        filtered_price = None

        if min_qty is None:
            try:
                min_qty_setting = (
                    self.get_effective_setting(
                        self.min_price_quantity_setting, user=self._request_user
                    )
                    or 1
                )
                min_qty = int(min_qty_setting) if min_qty_setting else 1
            except (ValueError, TypeError):
                min_qty = 1

        if max_qty is None:
            try:
                max_qty_setting = (
                    self.get_effective_setting(
                        self.max_price_quantity_setting, user=self._request_user
                    )
                    or ""
                )
                max_qty = int(max_qty_setting) if max_qty_setting else None
            except (ValueError, TypeError):
                max_qty = None

        variations = [
            variation
            for variation in self._coerce_list(
                product_data.get("ProductVariations") or []
            )
            if isinstance(variation, dict)
        ]
        primary_variation = variations[0] if variations else {}
        pricing = self._coerce_list(
            primary_variation.get("StandardPricing")
            or product_data.get("StandardPricing")
            or []
        )

        for price_break in pricing:
            if not isinstance(price_break, dict):
                continue
            try:
                qty = int(price_break.get("BreakQuantity") or 1)
            except Exception:
                qty = 1

            try:
                price_value = float(price_break.get("UnitPrice") or 0)
            except Exception:
                price_value = 0

            price_breaks.append({
                "quantity": qty,
                "price": price_value,
                "currency": self._get_locale_currency_code(),
            })

            if min_price is None or price_value < min_price:
                min_price = price_value

        for price_break in price_breaks:
            qty = price_break.get("quantity", 1)
            if qty >= min_qty and (max_qty is None or qty <= max_qty):
                filtered_price = price_break.get("price")
                break

        description = self._coerce_mapping(product_data.get("Description") or {})
        manufacturer = self._coerce_mapping(product_data.get("Manufacturer") or {})
        package_type = self._coerce_mapping(primary_variation.get("PackageType") or {})

        supplier_part_number = str(
            primary_variation.get("DigiKeyProductNumber")
            or product_data.get("DigiKeyProductNumber")
            or ""
        ).strip()

        available_quantity = (
            primary_variation.get("QuantityAvailableForPackageType")
            or primary_variation.get("QuantityAvailable")
            or product_data.get("QuantityAvailable")
            or 0
        )

        try:
            available_quantity = int(available_quantity)
        except Exception:
            available_quantity = self._extract_stock_qty(available_quantity)

        return {
            "supplier_part_number": supplier_part_number,
            "manufacturer_part_number": product_data.get("ManufacturerProductNumber"),
            "manufacturer_name": manufacturer.get("Name"),
            "supplier_link": self._build_digikey_product_link(
                product_data.get("ProductUrl")
            ),
            "datasheet_url": product_data.get("DatasheetUrl") or "",
            "image_url": product_data.get("PhotoUrl") or "",
            "lifecycle_status": "",
            "description": description.get("ProductDescription")
            or description.get("DetailedDescription")
            or "",
            "pack_quantity": 1,
            "packaging": package_type.get("Name") or "",
            "price_breaks": price_breaks,
            "unit_price": filtered_price if filtered_price is not None else min_price,
            "available_quantity": available_quantity,
            "spec_attributes": {},
        }

    def get_candidates(
        self, query, max_results=25, user=None, min_qty=None, max_qty=None
    ):
        self._request_user = user
        try:
            query = str(query or "").strip()
            if query == "":
                return {
                    "error_status": _("Search query cannot be empty"),
                    "candidates": [],
                    "debug": {},
                }

            keyword_payload = {
                "Keywords": query,
                "Limit": max(int(max_results), 1),
                "Offset": 0,
            }

            seen = set()
            candidates = []
            attempts = []

            result = self._search_digikey_products(
                self._build_keyword_url(user=user),
                keyword_payload,
            )
            attempts.append({
                "mode": "keyword",
                "status": result.get("error_status"),
                "result_count": len(result.get("products", [])),
            })

            if result.get("error_status") == "OK":
                for product_data in result.get("products", []):
                    if not isinstance(product_data, dict):
                        continue
                    candidate = self._build_candidate_from_product(
                        product_data,
                        min_qty=min_qty,
                        max_qty=max_qty,
                    )
                    supplier_part_number = str(
                        candidate.get("supplier_part_number") or ""
                    ).strip()
                    if not supplier_part_number or supplier_part_number in seen:
                        continue

                    seen.add(supplier_part_number)
                    if result.get("from_cache") is True:
                        candidate["_from_cache"] = True
                    candidates.append(candidate)

                    if len(candidates) >= max(int(max_results), 1):
                        break

            return {
                "error_status": "OK",
                "candidates": candidates,
                "debug": {
                    "attempts": attempts,
                    "max_results": int(max_results),
                    "returned_candidates": len(candidates),
                },
            }
        finally:
            self._request_user = None
