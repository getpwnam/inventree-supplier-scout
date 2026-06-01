"""Unit tests for DigiKey supplier adapter configuration behavior."""

import sys
import types
import unittest
from datetime import datetime
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

from supplier_scout.digikey import DigikeySupplierAdapter  # noqa: E402
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


class TestDigikeySupplierAdapter(unittest.TestCase):
    def test_registered_supplier_uses_digikey_setting_key(self):
        adapter = DigikeySupplierAdapter(DummyPlugin(settings={"DIGIKEY_PK": 42}))
        self.assertEqual(
            adapter.get_registered_supplier(),
            {"key": "digikey", "name": "DigiKey", "pk": 42},
        )

    def test_credentials_lookup_prefers_user_settings_then_global(self):
        adapter = DigikeySupplierAdapter(
            DummyPlugin(
                settings={
                    "DIGIKEY_CLIENT_ID": "global-client-id",
                    "DIGIKEY_CLIENT_SECRET": "global-client-secret",
                },
                user_settings={
                    "DIGIKEY_CLIENT_ID": "user-client-id",
                    "DIGIKEY_CLIENT_SECRET": "user-client-secret",
                },
            )
        )
        self.assertEqual(adapter._get_client_id(user=object()), "user-client-id")
        self.assertEqual(
            adapter._get_client_secret(user=object()), "user-client-secret"
        )

        adapter_without_user_override = DigikeySupplierAdapter(
            DummyPlugin(
                settings={
                    "DIGIKEY_CLIENT_ID": "global-client-id",
                    "DIGIKEY_CLIENT_SECRET": "global-client-secret",
                }
            )
        )
        self.assertEqual(
            adapter_without_user_override._get_client_id(user=object()),
            "global-client-id",
        )
        self.assertEqual(
            adapter_without_user_override._get_client_secret(user=object()),
            "global-client-secret",
        )

    def test_has_search_credentials_requires_both_client_id_and_secret(self):
        adapter = DigikeySupplierAdapter(
            DummyPlugin(
                settings={
                    "DIGIKEY_CLIENT_ID": "client-id",
                    "DIGIKEY_CLIENT_SECRET": "client-secret",
                }
            )
        )
        self.assertTrue(adapter.has_search_credentials())

        missing_secret = DigikeySupplierAdapter(
            DummyPlugin(settings={"DIGIKEY_CLIENT_ID": "client-id"})
        )
        self.assertFalse(missing_secret.has_search_credentials())

        missing_client_id = DigikeySupplierAdapter(
            DummyPlugin(settings={"DIGIKEY_CLIENT_SECRET": "client-secret"})
        )
        self.assertFalse(missing_client_id.has_search_credentials())

    def test_post_uses_oauth_token_and_client_id_header(self):
        adapter = DigikeySupplierAdapter(
            DummyPlugin(
                settings={
                    "DIGIKEY_CLIENT_ID": "global-client-id",
                    "DIGIKEY_CLIENT_SECRET": "global-client-secret",
                }
            )
        )
        adapter.transport.api_call = MagicMock(return_value=MagicMock())
        adapter._get_oauth_access_token = MagicMock(return_value="access-token")

        adapter._post("https://api.digikey.com/products/v4/search/keyword", {})

        _, kwargs = adapter.transport.api_call.call_args
        self.assertEqual(
            kwargs["headers"]["Authorization"],
            "Bearer " + "access-token",
        )
        self.assertEqual(
            kwargs["headers"]["X-DIGIKEY-Client-Id"],
            "global-client-id",
        )
        self.assertEqual(kwargs["headers"]["X-DIGIKEY-Locale-Language"], "en")
        self.assertEqual(kwargs["headers"]["X-DIGIKEY-Locale-Currency"], "USD")
        self.assertEqual(kwargs["headers"]["X-DIGIKEY-Locale-Site"], "US")

    def test_get_candidates_uses_v4_keyword_payload_shape(self):
        adapter = DigikeySupplierAdapter(
            DummyPlugin(
                settings={
                    "DIGIKEY_CLIENT_ID": "global-client-id",
                    "DIGIKEY_CLIENT_SECRET": "global-client-secret",
                }
            )
        )
        adapter._search_digikey_products = MagicMock(
            return_value={"error_status": "OK", "products": []}
        )

        adapter.get_candidates("STM32", max_results=7)

        _, payload = adapter._search_digikey_products.call_args[0]
        self.assertEqual(payload.get("Keywords"), "STM32")
        self.assertEqual(payload.get("Limit"), 7)
        self.assertEqual(payload.get("Offset"), 0)

    def test_search_digikey_products_returns_problem_detail_message(self):
        adapter = DigikeySupplierAdapter(
            DummyPlugin(
                settings={
                    "DIGIKEY_CLIENT_ID": "global-client-id",
                    "DIGIKEY_CLIENT_SECRET": "global-client-secret",
                }
            )
        )
        adapter._get_cached_response = MagicMock(
            return_value={
                "status": 400,
                "detail": "'Keywords' must not be empty.",
            }
        )

        result = adapter._search_digikey_products(
            adapter.KEYWORD_ENDPOINT,
            {"Keywords": ""},
        )

        self.assertEqual(result.get("error_status"), "'Keywords' must not be empty.")
        self.assertEqual(result.get("products"), [])

    @patch("supplier_scout.mouser.get_language")
    @patch("supplier_scout.mouser.InvenTreeSetting")
    def test_candidate_product_link_includes_site_language_currency(
        self, mock_setting, mock_get_language
    ):
        mock_get_language.return_value = "en-gb"
        mock_setting.get_setting.return_value = "GBP"

        adapter = DigikeySupplierAdapter(
            DummyPlugin(
                settings={
                    "DIGIKEY_CLIENT_ID": "global-client-id",
                    "DIGIKEY_CLIENT_SECRET": "global-client-secret",
                }
            )
        )

        candidate = adapter._build_candidate_from_product({
            "ProductUrl": "https://www.digikey.com/en/products/detail/acme/abc/123",
            "Description": {"ProductDescription": "Test"},
            "Manufacturer": {"Name": "Acme"},
            "ProductVariations": [
                {
                    "DigiKeyProductNumber": "123-ABC-ND",
                    "PackageType": {"Name": "Cut Tape"},
                    "StandardPricing": [
                        {"BreakQuantity": 1, "UnitPrice": 1.23},
                    ],
                }
            ],
        })

        link = str(candidate.get("supplier_link") or "")
        self.assertIn("www.digikey.co.uk", link)
        self.assertNotIn("?", link)

    @patch("supplier_scout.mouser.get_language")
    @patch("supplier_scout.mouser.InvenTreeSetting")
    def test_post_locale_headers_follow_language_and_currency(
        self, mock_setting, mock_get_language
    ):
        mock_get_language.return_value = "en-gb"
        mock_setting.get_setting.return_value = "EUR"

        adapter = DigikeySupplierAdapter(
            DummyPlugin(
                settings={
                    "DIGIKEY_CLIENT_ID": "global-client-id",
                    "DIGIKEY_CLIENT_SECRET": "global-client-secret",
                }
            )
        )
        adapter.transport.api_call = MagicMock(return_value=MagicMock())
        adapter._get_oauth_access_token = MagicMock(return_value="access-token")

        adapter._post("https://api.digikey.com/products/v4/search/keyword", {})

        _, kwargs = adapter.transport.api_call.call_args
        self.assertEqual(kwargs["headers"]["X-DIGIKEY-Locale-Language"], "en")
        self.assertEqual(kwargs["headers"]["X-DIGIKEY-Locale-Currency"], "EUR")
        self.assertEqual(kwargs["headers"]["X-DIGIKEY-Locale-Site"], "UK")

    @patch("supplier_scout.mouser.get_language")
    @patch("supplier_scout.mouser.InvenTreeSetting")
    def test_candidate_product_link_uses_ireland_host(
        self, mock_setting, mock_get_language
    ):
        mock_get_language.return_value = "en-ie"
        mock_setting.get_setting.return_value = "EUR"

        adapter = DigikeySupplierAdapter(
            DummyPlugin(
                settings={
                    "DIGIKEY_CLIENT_ID": "global-client-id",
                    "DIGIKEY_CLIENT_SECRET": "global-client-secret",
                }
            )
        )

        link = adapter._build_digikey_product_link(
            "https://www.digikey.com/en/products/detail/yageo/CC0603KRX7R9BB221/302811"
        )

        self.assertIn("www.digikey.ie", link)
        self.assertNotIn("?", link)

    @patch("supplier_scout.mouser.get_language")
    @patch("supplier_scout.mouser.InvenTreeSetting")
    def test_candidate_product_link_uses_australia_host(
        self, mock_setting, mock_get_language
    ):
        mock_get_language.return_value = "en-au"
        mock_setting.get_setting.return_value = "AUD"

        adapter = DigikeySupplierAdapter(
            DummyPlugin(
                settings={
                    "DIGIKEY_CLIENT_ID": "global-client-id",
                    "DIGIKEY_CLIENT_SECRET": "global-client-secret",
                }
            )
        )

        link = adapter._build_digikey_product_link(
            "https://www.digikey.com/en/products/detail/yageo/CC0603KRX7R9BB221/302811"
        )

        self.assertIn("www.digikey.com.au", link)
        self.assertNotIn("?", link)

    def test_digikey_api_rate_defaults(self):
        adapter = DigikeySupplierAdapter(DummyPlugin())
        self.assertEqual(adapter.get_api_rate_limit_per_second(), 1)
        self.assertEqual(adapter.get_api_daily_limit(), 1000)

    def test_daily_api_limit_blocks_when_exceeded(self):
        adapter = DigikeySupplierAdapter(
            DummyPlugin(settings={
                "DIGIKEY_API_RATE_LIMIT_PER_SECOND": 0,
                "DIGIKEY_API_DAILY_LIMIT": 2,
            })
        )

        adapter.enforce_api_rate_limits(cost=1)
        adapter.enforce_api_rate_limits(cost=1)

        with self.assertRaises(SupplierAPIRateLimitError):
            adapter.enforce_api_rate_limits(cost=1)

    def test_post_raises_when_daily_limit_reached(self):
        adapter = DigikeySupplierAdapter(
            DummyPlugin(
                settings={
                    "DIGIKEY_CLIENT_ID": "global-client-id",
                    "DIGIKEY_CLIENT_SECRET": "global-client-secret",
                    "DIGIKEY_API_RATE_LIMIT_PER_SECOND": 0,
                    "DIGIKEY_API_DAILY_LIMIT": 1,
                    "DIGIKEY_API_DAILY_COUNT": 1,
                    "DIGIKEY_API_DAILY_DATE": datetime.utcnow().date().isoformat(),
                }
            )
        )
        adapter.transport.api_call = MagicMock(return_value=MagicMock())

        with self.assertRaises(SupplierAPIRateLimitError):
            adapter._post("https://api.digikey.com/products/v4/search/keyword", {})

        adapter.transport.api_call.assert_not_called()

    def test_resync_enabled_defaults_to_false(self):
        adapter = DigikeySupplierAdapter(DummyPlugin())
        self.assertFalse(adapter.get_resync_enabled())

    def test_resync_enabled_reads_setting(self):
        adapter = DigikeySupplierAdapter(
            DummyPlugin(settings={"DIGIKEY_RESYNC_ENABLED": True})
        )
        self.assertTrue(adapter.get_resync_enabled())

    def test_resync_interval_defaults_to_1440(self):
        adapter = DigikeySupplierAdapter(DummyPlugin())
        self.assertEqual(adapter.get_resync_interval_minutes(), 1440)

    def test_resync_batch_size_defaults_to_100(self):
        adapter = DigikeySupplierAdapter(DummyPlugin())
        self.assertEqual(adapter.get_resync_batch_size(), 100)

    def test_resync_setting_keys_are_digikey_prefixed(self):
        self.assertEqual(
            DigikeySupplierAdapter.get_resync_enabled_setting_key(),
            "DIGIKEY_RESYNC_ENABLED",
        )
        self.assertEqual(
            DigikeySupplierAdapter.get_resync_interval_setting_key(),
            "DIGIKEY_RESYNC_INTERVAL_MINUTES",
        )
        self.assertEqual(
            DigikeySupplierAdapter.get_resync_batch_size_setting_key(),
            "DIGIKEY_RESYNC_BATCH_SIZE",
        )


if __name__ == "__main__":
    unittest.main()
