"""Unit tests for DigiKey supplier adapter configuration behavior."""

import sys
import types
import unittest


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

    def test_credentials_lookup_prefers_user_setting_then_global(self):
        adapter = DigikeySupplierAdapter(
            DummyPlugin(
                settings={"DIGIKEY_APIKEY_SEARCH": "global-key"},
                user_settings={"DIGIKEY_APIKEY_SEARCH": "user-key"},
            )
        )
        self.assertEqual(adapter._get_search_api_key(user=object()), "user-key")

        adapter_without_user_key = DigikeySupplierAdapter(
            DummyPlugin(settings={"DIGIKEY_APIKEY_SEARCH": "global-key"})
        )
        self.assertEqual(
            adapter_without_user_key._get_search_api_key(user=object()),
            "global-key",
        )


if __name__ == "__main__":
    unittest.main()
