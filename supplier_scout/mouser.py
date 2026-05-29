"""Mouser supplier adapter."""

import re

from common.models import InvenTreeSetting

from .adapters import BaseSupplierAdapter
from .adapters import SupplierAPIClient


MOUSER_SETTINGS = {
    "MOUSER_PK": {
        "name": "Mouser Supplier ID",
        "description": "Primary key of the Mouser supplier",
        "model": "company.company",
    },
    "MOUSERSEARCHKEY": {
        "name": "Mouser search API key",
        "description": "Mouser part search API key",
    },
    "MOUSER_MAX_CANDIDATES": {
        "name": "Mouser max candidates",
        "description": "Maximum number of Mouser candidates considered for ranking",
        "default": 40,
    },
    "MOUSERLANGUAGE": {
        "name": "Mouser API language",
        "description": "Language for Mouser API responses",
        "choices": [
            ("English", "English"),
            ("German", "German"),
        ],
        "default": "English",
    },
}

MOUSER_USER_SETTINGS = {
    "MOUSERSEARCHKEY": {
        "name": "Mouser search API key (user override)",
        "description": "User-specific Mouser search API key",
        "protected": True,
    },
}


class MouserSupplierAdapter(BaseSupplierAdapter):
    key = "mouser"
    name = "Mouser"
    settings = MOUSER_SETTINGS
    user_settings = MOUSER_USER_SETTINGS
    company_setting = "MOUSER_PK"
    max_candidates_setting = "MOUSER_MAX_CANDIDATES"

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

    def _post(self, url, payload):
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

    def _build_candidate_from_part(self, part_data):
        price_breaks = []
        min_price = None

        for price_break in part_data.get("PriceBreaks", []) or []:
            price_value = self.reformat_mouser_price(price_break.get("Price"))
            price_breaks.append({
                "quantity": price_break.get("Quantity"),
                "price": price_value,
                "currency": price_break.get("Currency"),
            })

            if min_price is None or price_value < min_price:
                min_price = price_value

        availability = (
            part_data.get("AvailabilityInStock")
            or part_data.get("Availability")
            or part_data.get("MouserATS")
            or 0
        )

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
            "unit_price": min_price,
            "available_quantity": self._extract_stock_qty(availability),
        }

    def _search_mouser_parts(self, url, payload):
        try:
            response = self._post(url, payload)
        except Exception:
            return {
                "error_status": "Connection to Mouser API failed",
                "parts": [],
            }

        try:
            response_data = response.json()
        except Exception:
            return {
                "error_status": "Invalid JSON response from Mouser",
                "parts": [],
            }

        errors = response_data.get("Errors") or []
        if errors:
            code = errors[0].get("Code")
            message = errors[0].get("Message") or code or "Mouser search error"

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

    def get_candidates(self, query, max_results=25, user=None):
        query = str(query or "").strip()
        if query == "":
            return {
                "error_status": "Search query cannot be empty",
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
                candidates.append(self._build_candidate_from_part(part_data))

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
        attribute_names = {
            "packaging": {"German": "Verpackung", "English": "Packaging"}
        }
        package = ""
        try:
            attributes = part_data["ProductAttributes"]
        except Exception:
            return None

        language = (self.get_setting("MOUSERLANGUAGE") or "English").strip()
        if language not in attribute_names["packaging"]:
            language = "English"

        packaging_name = attribute_names["packaging"].get(language, "Packaging")

        for attribute in attributes:
            if attribute.get("AttributeName") == packaging_name:
                package = package + attribute.get("AttributeValue", "") + ", "

        return package or None

    def reformat_mouser_price(self, price):
        price = str(price or "").replace(".", "")
        price = price.replace(",", ".")
        non_decimal = re.compile(r"[^\d.]+")
        price = non_decimal.sub("", price)
        if price == "":
            return 0
        return float(price)
