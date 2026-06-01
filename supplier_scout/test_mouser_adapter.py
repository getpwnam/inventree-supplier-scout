"""Unit tests for the Mouser supplier adapter.

These tests target deterministic helper behavior and avoid depending on a full
InvenTree runtime by stubbing required external modules.
"""

import json
import os
import sys
import tempfile
import types
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import patch


def _install_inventree_stubs():
    """Install minimal stubs for external InvenTree modules."""
    if "common.models" not in sys.modules:
        common_module = types.ModuleType("common")
        common_models_module = types.ModuleType("common.models")

        class InvenTreeSetting:
            @staticmethod
            def get_setting(_key):
                return "USD"

        common_models_module.InvenTreeSetting = InvenTreeSetting
        common_module.models = common_models_module

        sys.modules["common"] = common_module
        sys.modules["common.models"] = common_models_module

    if "plugin.mixins" not in sys.modules:
        plugin_module = types.ModuleType("plugin")
        plugin_mixins_module = types.ModuleType("plugin.mixins")

        class APICallMixin:
            pass

        plugin_mixins_module.APICallMixin = APICallMixin
        plugin_module.mixins = plugin_mixins_module

        sys.modules["plugin"] = plugin_module
        sys.modules["plugin.mixins"] = plugin_mixins_module


_install_inventree_stubs()

from supplier_scout.mouser import MouserSupplierAdapter  # noqa: E402
from supplier_scout.adapters import SupplierAPIRateLimitError  # noqa: E402


class DummyPlugin:
    """Minimal plugin interface required by adapter under test."""

    def __init__(self, settings=None, user_settings=None):
        self.settings = settings or {}
        self.user_settings = user_settings or {}

    def get_setting(self, key, backup_value=None):
        return self.settings.get(key, backup_value)

    def get_effective_setting(self, key, user=None, backup_value=None):
        del user
        return self.get_setting(key, backup_value=backup_value)

    def get_user_setting(self, key, user=None, backup_value=None):
        del user
        return self.user_settings.get(key, backup_value)

    def set_setting(self, key, value):
        self.settings[key] = value


class MockResponse:
    """Simple response object with json() for adapter transport stubs."""

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class TestMouserSupplierAdapter(unittest.TestCase):
    """Coverage for Mouser-specific normalization and cache behavior."""

    def setUp(self):
        self.adapter = MouserSupplierAdapter(
            DummyPlugin({
                "MOUSER_CACHE_TTL": 3600,
                "MOUSER_MIN_PRICE_QUANTITY": 1,
            })
        )

    def test_get_mouser_package_uses_active_locale_with_fallback(self):
        part_data = {
            "ProductAttributes": [
                {"AttributeName": "Packaging", "AttributeValue": "Reel"},
                {"AttributeName": "Verpackung", "AttributeValue": "Gurt"},
            ]
        }

        with patch("supplier_scout.mouser.get_language", return_value="en-us"):
            self.assertEqual(self.adapter.get_mouser_package(part_data), "Reel, Gurt")

        with patch("supplier_scout.mouser.get_language", return_value="de-DE"):
            self.assertEqual(self.adapter.get_mouser_package(part_data), "Reel, Gurt")

    def test_mouser_api_rate_defaults(self):
        self.assertEqual(self.adapter.get_api_rate_limit_per_second(), 1)
        self.assertEqual(self.adapter.get_api_daily_limit(), 1000)

    def test_daily_api_limit_blocks_when_exceeded(self):
        self.adapter.plugin.settings["MOUSER_API_RATE_LIMIT_PER_SECOND"] = 0
        self.adapter.plugin.settings["MOUSER_API_DAILY_LIMIT"] = 2

        self.adapter.enforce_api_rate_limits(cost=1)
        self.adapter.enforce_api_rate_limits(cost=1)

        with self.assertRaises(SupplierAPIRateLimitError):
            self.adapter.enforce_api_rate_limits(cost=1)

    @patch("supplier_scout.mouser.InvenTreeSetting")
    def test_build_keyword_url_uses_new_setting_key(self, mock_setting):
        mock_setting.get_setting.return_value = "EUR"
        adapter = MouserSupplierAdapter(
            DummyPlugin(settings={"MOUSER_APIKEY_SEARCH": "abc123"})
        )

        url = adapter._build_keyword_url()

        self.assertIn("apiKey=abc123", url)
        self.assertIn("countryCode=DE", url)
        self.assertIn("currencyCode=EUR", url)

    @patch("supplier_scout.mouser.get_language")
    @patch("supplier_scout.mouser.InvenTreeSetting")
    def test_build_keyword_url_prefers_language_region_for_country(
        self, mock_setting, mock_get_language
    ):
        def setting_side_effect(key):
            if key == "INVENTREE_DEFAULT_CURRENCY":
                return "EUR"
            return ""

        mock_setting.get_setting.side_effect = setting_side_effect
        mock_get_language.return_value = "en-us"
        adapter = MouserSupplierAdapter(
            DummyPlugin(settings={"MOUSER_APIKEY_SEARCH": "abc123"})
        )

        url = adapter._build_keyword_url()

        self.assertIn("countryCode=US", url)
        self.assertIn("currencyCode=EUR", url)

    def test_post_raises_when_daily_limit_reached(self):
        self.adapter.plugin.settings["MOUSER_API_RATE_LIMIT_PER_SECOND"] = 0
        self.adapter.plugin.settings["MOUSER_API_DAILY_LIMIT"] = 1
        self.adapter.plugin.settings["MOUSER_API_DAILY_COUNT"] = 1
        self.adapter.plugin.settings["MOUSER_API_DAILY_DATE"] = (
            datetime.utcnow().date().isoformat()
        )

        self.adapter.transport.api_call = MagicMock(return_value=MockResponse({}))

        with self.assertRaises(SupplierAPIRateLimitError):
            self.adapter._post("https://example.invalid", {"q": "x"})

        self.adapter.transport.api_call.assert_not_called()

    def test_reformat_mouser_price_supports_common_formats(self):
        self.assertEqual(self.adapter.reformat_mouser_price("1.456,34 €"), 1456.34)
        self.assertEqual(self.adapter.reformat_mouser_price("1,456.34 $"), 1456.34)
        self.assertEqual(self.adapter.reformat_mouser_price("1,56"), 1.56)
        self.assertEqual(self.adapter.reformat_mouser_price("invalid"), 0)

    def test_build_candidate_prefers_smallest_quantity_in_selected_range(self):
        part_data = {
            "MouserPartNumber": "P-1",
            "ManufacturerPartNumber": "M-1",
            "PriceBreaks": [
                {"Quantity": 1, "Price": "$2.00", "Currency": "USD"},
                {"Quantity": 10, "Price": "$1.50", "Currency": "USD"},
                {"Quantity": 100, "Price": "$1.20", "Currency": "USD"},
            ],
            "AvailabilityInStock": "1,250 In Stock",
            "ProductAttributes": [],
        }

        candidate = self.adapter._build_candidate_from_part(
            part_data, min_qty=10, max_qty=99
        )

        self.assertEqual(candidate["unit_price"], 1.5)
        self.assertEqual(candidate["available_quantity"], 1250)

    def test_build_candidate_falls_back_to_absolute_min_price(self):
        part_data = {
            "MouserPartNumber": "P-1",
            "ManufacturerPartNumber": "M-1",
            "PriceBreaks": [
                {"Quantity": 1, "Price": "$2.00", "Currency": "USD"},
                {"Quantity": 10, "Price": "$1.50", "Currency": "USD"},
                {"Quantity": 100, "Price": "$1.20", "Currency": "USD"},
            ],
            "ProductAttributes": [],
        }

        candidate = self.adapter._build_candidate_from_part(
            part_data, min_qty=1000, max_qty=2000
        )

        self.assertEqual(candidate["unit_price"], 1.2)

    def test_build_cache_key_is_stable_for_payload_order(self):
        url = "https://example.invalid/search"
        key_a = self.adapter._build_cache_key(url, {"b": 2, "a": 1})
        key_b = self.adapter._build_cache_key(url, {"a": 1, "b": 2})
        self.assertEqual(key_a, key_b)
        self.assertEqual(len(key_a), 64)

    def test_build_cache_key_ignores_api_key_query_parameter(self):
        url_a = (
            "https://example.invalid/search"
            "?apiKey=secret-a&countryCode=US&currencyCode=USD"
        )
        url_b = (
            "https://example.invalid/search"
            "?apiKey=secret-b&countryCode=US&currencyCode=USD"
        )

        key_a = self.adapter._build_cache_key(url_a, {"query": "abc"})
        key_b = self.adapter._build_cache_key(url_b, {"query": "abc"})

        self.assertEqual(key_a, key_b)

    def test_get_cache_dir_uses_restrictive_permissions(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            home_path = Path(temp_dir)

            with patch("supplier_scout.mouser.Path.home", return_value=home_path):
                cache_dir = self.adapter._get_cache_dir()

            self.assertEqual(cache_dir.stat().st_mode & 0o777, 0o700)

    def test_get_cache_ttl_parses_and_bounds_values(self):
        self.assertEqual(self.adapter._get_cache_ttl_seconds(), 3600)

        self.adapter.plugin.settings["MOUSER_CACHE_TTL"] = -10
        self.assertEqual(self.adapter._get_cache_ttl_seconds(), 0)

        self.adapter.plugin.settings["MOUSER_CACHE_TTL"] = "not-a-number"
        self.assertEqual(self.adapter._get_cache_ttl_seconds(), 3600)

    def test_get_cached_response_returns_fresh_cache(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            self.adapter._get_cache_dir = MagicMock(return_value=temp_path)

            url = "https://example.invalid/search"
            payload = {"query": "abc"}
            cache_key = self.adapter._build_cache_key(url, payload)
            cache_file = temp_path / f"{cache_key}.json"
            cache_file.write_text(json.dumps({"value": 123}), encoding="utf-8")

            cached = self.adapter._get_cached_response(url, payload)
            self.assertEqual(cached, {"value": 123})

    def test_cache_response_writes_restrictive_file_permissions(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            self.adapter._get_cache_dir = MagicMock(return_value=temp_path)

            url = "https://example.invalid/search"
            payload = {"query": "abc"}
            self.adapter._cache_response(url, payload, {"value": 123})

            cache_key = self.adapter._build_cache_key(url, payload)
            cache_file = temp_path / f"{cache_key}.json"

            self.assertTrue(cache_file.exists())
            self.assertEqual(cache_file.stat().st_mode & 0o777, 0o600)

    def test_get_cached_response_ignores_stale_cache(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            self.adapter._get_cache_dir = MagicMock(return_value=temp_path)
            self.adapter.plugin.settings["MOUSER_CACHE_TTL"] = 1

            url = "https://example.invalid/search"
            payload = {"query": "abc"}
            cache_key = self.adapter._build_cache_key(url, payload)
            cache_file = temp_path / f"{cache_key}.json"
            cache_file.write_text(json.dumps({"value": 123}), encoding="utf-8")

            stale_time = cache_file.stat().st_mtime - 5
            os.utime(cache_file, (stale_time, stale_time))

            cached = self.adapter._get_cached_response(url, payload)
            self.assertIsNone(cached)

    def test_search_uses_cache_without_transport_call(self):
        response_payload = {
            "SearchResults": {
                "Parts": [
                    {
                        "MouserPartNumber": "SKU-1",
                        "ManufacturerPartNumber": "MPN-1",
                        "PriceBreaks": [{"Quantity": 1, "Price": "$1.00"}],
                        "ProductAttributes": [],
                    }
                ]
            }
        }

        self.adapter._get_cached_response = MagicMock(return_value=response_payload)
        self.adapter._post = MagicMock()

        result = self.adapter._search_mouser_parts(
            "https://example.invalid", {"query": "abc"}
        )

        self.assertEqual(result["error_status"], "OK")
        self.assertEqual(len(result["parts"]), 1)
        self.assertTrue(result["from_cache"])
        self.adapter._post.assert_not_called()

    def test_search_handles_not_found_error_as_empty_ok(self):
        self.adapter._get_cached_response = MagicMock(return_value=None)
        self.adapter._post = MagicMock(
            return_value=MockResponse({
                "Errors": [
                    {
                        "Code": "SearchNotFound",
                        "Message": "No results",
                    }
                ]
            })
        )

        result = self.adapter._search_mouser_parts(
            "https://example.invalid", {"query": "abc"}
        )

        self.assertEqual(result, {"error_status": "OK", "parts": []})

    def test_search_rejects_non_mapping_response_payload(self):
        self.adapter._get_cached_response = MagicMock(return_value=["unexpected"])
        self.adapter._post = MagicMock()

        result = self.adapter._search_mouser_parts(
            "https://example.invalid", {"query": "abc"}
        )

        self.assertEqual(
            result,
            {
                "error_status": "Invalid response payload from Mouser",
                "parts": [],
            },
        )
        self.adapter._post.assert_not_called()

    def test_get_candidates_skips_non_mapping_part_entries(self):
        self.adapter._search_mouser_parts = MagicMock(
            side_effect=[
                {
                    "error_status": "OK",
                    "from_cache": True,
                    "parts": [
                        {
                            "MouserPartNumber": "SKU-1",
                            "ManufacturerPartNumber": "MPN-1",
                            "PriceBreaks": [
                                "bad-price-break",
                                {"Quantity": 1, "Price": "$1.00", "Currency": "USD"},
                            ],
                            "ProductAttributes": [
                                "bad-attribute",
                                {
                                    "AttributeName": "Packaging",
                                    "AttributeValue": "Reel",
                                },
                            ],
                        },
                        "bad-part",
                    ],
                },
                {"error_status": "OK", "parts": []},
            ]
        )

        result = self.adapter.get_candidates("abc", max_results=5)

        self.assertEqual(result["error_status"], "OK")
        self.assertEqual(len(result["candidates"]), 1)
        self.assertEqual(result["candidates"][0]["supplier_part_number"], "SKU-1")
        self.assertEqual(result["candidates"][0]["packaging"], "Reel")
        self.assertEqual(len(result["candidates"][0]["price_breaks"]), 1)
        self.assertTrue(result["candidates"][0]["_from_cache"])


if __name__ == "__main__":
    unittest.main()
