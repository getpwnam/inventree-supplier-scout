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
from pathlib import Path
from unittest.mock import MagicMock


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


class DummyPlugin:
    """Minimal plugin interface required by adapter under test."""

    def __init__(self, settings=None):
        self.settings = settings or {}

    def get_setting(self, key, backup_value=None):
        return self.settings.get(key, backup_value)

    def get_effective_setting(self, key, user=None, backup_value=None):
        del user
        return self.get_setting(key, backup_value=backup_value)


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
                "MOUSERLANGUAGE": "English",
                "MOUSER_MIN_PRICE_QUANTITY": 1,
            })
        )

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


if __name__ == "__main__":
    unittest.main()
