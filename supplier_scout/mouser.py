"""Mouser supplier adapter."""

import hashlib
import json
import re
import time
from pathlib import Path

from common.models import InvenTreeSetting

try:
    from django.utils.translation import get_language  # type: ignore[import-not-found]
    from django.utils.translation import gettext_lazy as _  # type: ignore[import-not-found]
except Exception:  # pragma: no cover - fallback for isolated unit tests

    def _(value):
        return value

    def get_language():
        return "en"


from .adapters import BaseSupplierAdapter
from .adapters import SupplierAPIRateLimitError
from .adapters import SupplierAPIClient


MOUSER_SETTINGS = {
    "MOUSER_PK": {
        "name": _("Mouser Supplier ID"),
        "description": _("Primary key of the Mouser supplier"),
        "model": "company.company",
    },
    "MOUSERSEARCHKEY": {
        "name": _("Mouser search API key"),
        "description": _("Mouser part search API key"),
    },
    "MOUSER_MAX_CANDIDATES": {
        "name": _("Mouser max candidates"),
        "description": _("Maximum number of Mouser candidates considered for ranking"),
        "default": 40,
    },
    "MOUSER_MIN_PRICE_QUANTITY": {
        "name": _("Mouser minimum quantity for price selection"),
        "description": _(
            "Select the best price for at least this quantity (e.g., 1 for single units, 10 for tape). Leave blank for no limit."
        ),
        "default": 1,
    },
    "MOUSER_MAX_PRICE_QUANTITY": {
        "name": _("Mouser maximum quantity for price selection"),
        "description": _(
            "Prefer prices for quantities up to this number (e.g., 50 for hobby, 1000 for production). Leave blank for no limit."
        ),
        "default": "",
    },
    "MOUSER_CACHE_TTL": {
        "name": _("Mouser response cache TTL"),
        "description": _(
            "Cache Mouser API responses for this many seconds (3600 = 1 hour, 0 = disabled). Reduces API calls and rate limiting."
        ),
        "default": 3600,
    },
}

MOUSER_USER_SETTINGS = {
    "MOUSERSEARCHKEY": {
        "name": _("Mouser search API key (user override)"),
        "description": _("User-specific Mouser search API key"),
        "protected": True,
    },
    "MOUSER_MIN_PRICE_QUANTITY": {
        "name": _("Mouser minimum quantity for price selection (user override)"),
        "description": _(
            "Select the best price for at least this quantity (e.g., 1 for single units, 10 for tape)."
        ),
    },
    "MOUSER_MAX_PRICE_QUANTITY": {
        "name": _("Mouser maximum quantity for price selection (user override)"),
        "description": _(
            "Prefer prices for quantities up to this number (e.g., 50 for hobby, 1000 for production)."
        ),
    },
}


class MouserSupplierAdapter(BaseSupplierAdapter):
    key = "mouser"
    name = "Mouser"
    settings = MOUSER_SETTINGS
    user_settings = MOUSER_USER_SETTINGS
    company_setting = "MOUSER_PK"
    max_candidates_setting = "MOUSER_MAX_CANDIDATES"
    api_rate_limit_per_second_default = 1
    api_daily_limit_default = 1000

    COUNTRY_CODES = {
        "AUD": "AU",
        "CAD": "CA",
        "CNY": "CN",
        "GBP": "GB",
        "JPY": "JP",
        "NZD": "NZ",
        "USD": "US",
        "EUR": "DE",
    }

    SEARCH_ENDPOINT = "https://api.mouser.com/api/v1/search/partnumber"
    KEYWORD_ENDPOINT = "https://api.mouser.com/api/v1/search/keyword"

    def __init__(self, plugin):
        super().__init__(plugin)
        self.transport = SupplierAPIClient(
            plugin,
            base_url="https://api.mouser.com",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

    def has_search_credentials(self, user=None):
        api_key = str(
            self.get_effective_setting("MOUSERSEARCHKEY", user=user, backup_value="")
            or ""
        ).strip()
        return api_key != ""

    def _get_cache_dir(self):
        """Return the cache directory path, creating it if necessary."""
        cache_dir = Path.home() / ".cache" / "inventree_mouser"
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir

    def _build_cache_key(self, url, payload):
        """Build a unique cache key from URL and payload."""
        key_str = f"{url}:{json.dumps(payload, sort_keys=True)}"
        return hashlib.sha256(key_str.encode()).hexdigest()

    def _get_cache_ttl_seconds(self):
        """Get cache TTL in seconds from settings."""
        try:
            ttl = int(self.get_setting("MOUSER_CACHE_TTL") or 3600)
            return max(0, ttl)  # Ensure non-negative
        except (ValueError, TypeError):
            return 3600

    def _get_cached_response(self, url, payload):
        """Get cached response if fresh, otherwise fetch from API and cache it.

        Returns the response object or None if not found/stale.
        """
        ttl_seconds = self._get_cache_ttl_seconds()
        if ttl_seconds <= 0:
            # Caching disabled
            return None

        cache_key = self._build_cache_key(url, payload)
        cache_file = self._get_cache_dir() / f"{cache_key}.json"

        # Check if cache exists and is fresh
        if cache_file.exists():
            try:
                stat = cache_file.stat()
                age_seconds = time.time() - stat.st_mtime

                if age_seconds < ttl_seconds:
                    # Cache is fresh, load and return it
                    data = json.loads(cache_file.read_text())
                    return data
            except (OSError, json.JSONDecodeError):
                # Cache file corrupted or unreadable, proceed to API call
                pass

        return None

    def _cache_response(self, url, payload, response_data):
        """Store response in cache."""
        ttl_seconds = self._get_cache_ttl_seconds()
        if ttl_seconds <= 0:
            # Caching disabled
            return

        try:
            cache_key = self._build_cache_key(url, payload)
            cache_file = self._get_cache_dir() / f"{cache_key}.json"
            cache_file.write_text(json.dumps(response_data, indent=2))
        except (OSError, json.JSONDecodeError):
            # Silently fail if cache write fails
            pass

    def get_cache_status(self):
        ttl_seconds = self._get_cache_ttl_seconds()

        if ttl_seconds <= 0:
            return {
                "enabled": False,
                "cache_backend": "filesystem",
                "cache_ttl_seconds": 0,
                "cache_path": "",
                "cache_file_count": 0,
                "cache_size_bytes": 0,
            }

        try:
            cache_dir = self._get_cache_dir()
            files = [entry for entry in cache_dir.glob("*.json") if entry.is_file()]
            total_bytes = 0
            for entry in files:
                try:
                    total_bytes += entry.stat().st_size
                except OSError:
                    pass

            return {
                "enabled": True,
                "cache_backend": "filesystem",
                "cache_ttl_seconds": ttl_seconds,
                "cache_path": str(cache_dir),
                "cache_file_count": len(files),
                "cache_size_bytes": total_bytes,
            }
        except Exception:
            return {
                "enabled": True,
                "cache_backend": "filesystem",
                "cache_ttl_seconds": ttl_seconds,
                "cache_path": "",
                "cache_file_count": 0,
                "cache_size_bytes": 0,
            }

    def _post(self, url, payload):
        self.enforce_api_rate_limits(cost=1)
        return self.transport.api_call(
            url,
            method="POST",
            json=payload,
            headers=self.transport.api_headers,
            simple_response=False,
            endpoint_is_url=True,
            timeout=15,
        )

    def _build_search_url(self, user=None):
        api_key = self.get_effective_setting(
            "MOUSERSEARCHKEY", user=user, backup_value=""
        )
        currency = InvenTreeSetting.get_setting("INVENTREE_DEFAULT_CURRENCY")
        country = self.COUNTRY_CODES.get(currency, "US")
        return (
            self.SEARCH_ENDPOINT
            + "?apiKey="
            + api_key
            + "&countryCode="
            + country
            + "&currencyCode="
            + currency
        )

    def _build_keyword_url(self, user=None):
        api_key = self.get_effective_setting(
            "MOUSERSEARCHKEY", user=user, backup_value=""
        )
        currency = InvenTreeSetting.get_setting("INVENTREE_DEFAULT_CURRENCY")
        country = self.COUNTRY_CODES.get(currency, "US")
        return (
            self.KEYWORD_ENDPOINT
            + "?apiKey="
            + api_key
            + "&countryCode="
            + country
            + "&currencyCode="
            + currency
        )

    def _extract_stock_qty(self, value):
        if value is None:
            return 0

        text = str(value).replace(",", "")
        match = re.search(r"\d+", text)
        if match:
            try:
                return int(match.group(0))
            except Exception:
                pass

        return 0

    def _build_candidate_from_part(
        self, part_data, min_qty=None, max_qty=None, user=None
    ):
        price_breaks = []
        min_price = None
        filtered_price = None
        spec_attributes = {}

        # Get quantity range settings for price selection (use provided values or fall back to settings)
        if min_qty is None:
            try:
                min_qty_setting = (
                    self.get_effective_setting("MOUSER_MIN_PRICE_QUANTITY", user=user)
                    or 1
                )
                min_qty = int(min_qty_setting) if min_qty_setting else 1
            except (ValueError, TypeError):
                min_qty = 1

        if max_qty is None:
            try:
                max_qty_setting = (
                    self.get_effective_setting("MOUSER_MAX_PRICE_QUANTITY", user=user)
                    or ""
                )
                max_qty = int(max_qty_setting) if max_qty_setting else None
            except (ValueError, TypeError):
                max_qty = None

        for price_break in part_data.get("PriceBreaks", []) or []:
            price_value = self.reformat_mouser_price(price_break.get("Price"))
            qty = price_break.get("Quantity") or 1

            price_breaks.append({
                "quantity": qty,
                "price": price_value,
                "currency": price_break.get("Currency"),
            })

            # Track absolute minimum price (fallback)
            if min_price is None or price_value < min_price:
                min_price = price_value

        # Find price for smallest quantity within preferred range
        filtered_price = None
        for price_break in price_breaks:
            qty = price_break.get("quantity", 1)
            if qty >= min_qty and (max_qty is None or qty <= max_qty):
                filtered_price = price_break.get("price")
                break  # Since first match is smallest quantity in range

        availability = (
            part_data.get("AvailabilityInStock")
            or part_data.get("Availability")
            or part_data.get("MouserATS")
            or 0
        )

        for attribute in part_data.get("ProductAttributes") or []:
            attr_name = str(attribute.get("AttributeName") or "").strip()
            attr_value = str(attribute.get("AttributeValue") or "").strip()
            if attr_name and attr_value:
                spec_attributes[attr_name] = attr_value

        # Use filtered price if available (within preferred quantity range),
        # otherwise fall back to absolute minimum
        unit_price = filtered_price if filtered_price is not None else min_price

        return {
            "supplier_part_number": part_data.get("MouserPartNumber"),
            "manufacturer_part_number": part_data.get("ManufacturerPartNumber"),
            "manufacturer_name": part_data.get("Manufacturer"),
            "supplier_link": part_data.get("ProductDetailUrl"),
            "datasheet_url": part_data.get("DataSheetUrl") or "",
            "image_url": part_data.get("ImagePath") or "",
            "lifecycle_status": part_data.get("LifecycleStatus") or "",
            "description": part_data.get("Description") or "",
            "pack_quantity": part_data.get("Mult") or 1,
            "packaging": self.get_mouser_package(part_data),
            "price_breaks": price_breaks,
            "unit_price": unit_price,
            "available_quantity": self._extract_stock_qty(availability),
            "spec_attributes": spec_attributes,
        }

    def _search_mouser_parts(self, url, payload):
        # Try to get cached response
        cached_data = self._get_cached_response(url, payload)
        if cached_data is not None:
            response_data = cached_data
        else:
            # Cache miss or disabled, fetch from API
            try:
                response = self._post(url, payload)
            except SupplierAPIRateLimitError as exc:
                return {
                    "error_status": str(exc),
                    "parts": [],
                }
            except Exception:
                return {
                    "error_status": _("Connection to Mouser API failed"),
                    "parts": [],
                }

            try:
                response_data = response.json()
            except Exception:
                return {
                    "error_status": _("Invalid JSON response from Mouser"),
                    "parts": [],
                }

            # Cache the response for future requests
            self._cache_response(url, payload, response_data)

        errors = response_data.get("Errors") or []
        if errors:
            code = errors[0].get("Code")
            message = errors[0].get("Message") or code or _("Mouser search error")

            if code in ["SearchNotFound", "NotFound"]:
                return {"error_status": "OK", "parts": []}

            return {
                "error_status": message,
                "parts": [],
            }

        if response_data.get("Message"):
            return {
                "error_status": str(response_data.get("Message")),
                "parts": [],
            }

        parts = (response_data.get("SearchResults") or {}).get("Parts") or []

        return {
            "error_status": "OK",
            "parts": parts,
        }

    def get_candidates(
        self, query, max_results=25, user=None, min_qty=None, max_qty=None
    ):
        query = str(query or "").strip()
        if query == "":
            return {
                "error_status": _("Search query cannot be empty"),
                "candidates": [],
                "debug": {},
            }

        part_payload = {
            "SearchByPartRequest": {
                "mouserPartNumber": query,
                "partSearchOptions": "None",
            }
        }
        keyword_payload = {
            "SearchByKeywordRequest": {
                "keyword": query,
                "records": max(int(max_results), 1),
                "startingRecord": 0,
                "searchOptions": "None",
            }
        }

        seen = set()
        candidates = []
        attempts = []

        for mode, url, payload in [
            ("partnumber", self._build_search_url(user=user), part_payload),
            ("keyword", self._build_keyword_url(user=user), keyword_payload),
        ]:
            result = self._search_mouser_parts(url, payload)
            attempts.append({
                "mode": mode,
                "status": result.get("error_status"),
                "result_count": len(result.get("parts", [])),
            })

            if result.get("error_status") != "OK":
                continue

            for part_data in result.get("parts", []):
                supplier_part_number = str(
                    part_data.get("MouserPartNumber") or ""
                ).strip()
                if not supplier_part_number or supplier_part_number in seen:
                    continue

                seen.add(supplier_part_number)
                candidates.append(
                    self._build_candidate_from_part(
                        part_data, min_qty=min_qty, max_qty=max_qty, user=user
                    )
                )

                if len(candidates) >= max(int(max_results), 1):
                    break

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

    def get_mouser_package(self, part_data):
        try:
            attributes = part_data["ProductAttributes"]
        except Exception:
            return None

        language = str(get_language() or "en").strip().lower().replace("_", "-")
        packaging_labels = ["Packaging", "Verpackung"]
        if language.startswith("de"):
            packaging_labels = ["Verpackung", "Packaging"]

        packaging_name_set = {label.casefold() for label in packaging_labels}
        matches = []
        for attribute in attributes:
            attribute_name = str(attribute.get("AttributeName") or "").strip()
            attribute_value = str(attribute.get("AttributeValue") or "").strip()
            if attribute_name.casefold() in packaging_name_set and attribute_value:
                matches.append(attribute_value)

        return ", ".join(matches) or None

    def reformat_mouser_price(self, price):
        # Remove currency symbols and whitespace
        price = str(price or "").strip()
        non_numeric = re.compile(r"[^\d.,]+")
        price = non_numeric.sub("", price)

        if not price:
            return 0

        # Determine which separator is decimal by position
        # The rightmost separator is typically the decimal separator
        last_comma = price.rfind(",")
        last_dot = price.rfind(".")

        if last_comma > last_dot:
            # European format: comma is decimal, dots are thousands
            price = price.replace(".", "")
            price = price.replace(",", ".")
        else:
            # US format: dot is decimal, commas are thousands
            price = price.replace(",", "")

        try:
            return float(price)
        except ValueError:
            return 0
