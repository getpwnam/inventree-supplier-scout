"""Unit tests for DigiKey supplier adapter configuration behavior."""

import sys
import types
import unittest
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

from supplier_scout.digikey import DigikeySupplierAdapter  # noqa: E402


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

        adapter._post("https://api.digikey.com/services/partsearch/v3/keywordsearch", {})

        _, kwargs = adapter.transport.api_call.call_args
        self.assertEqual(
            kwargs["headers"]["Authorization"],
            "Bearer " + "access-token",
        )
        self.assertEqual(
            kwargs["headers"]["X-DIGIKEY-Client-Id"],
            "global-client-id",
        )


if __name__ == "__main__":
    unittest.main()
