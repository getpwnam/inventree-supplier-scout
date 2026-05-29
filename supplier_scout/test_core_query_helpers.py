"""Unit tests for SupplierScout query and token helper logic.

These tests exercise deterministic helper behavior in core.py and avoid
requiring a full InvenTree runtime by stubbing external modules.
"""

import sys
import types
import unittest


def _install_core_stubs():
    """Install minimal stubs required to import supplier_scout.core."""

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

    if "company.models" not in sys.modules:
        company_module = types.ModuleType("company")
        company_models_module = types.ModuleType("company.models")

        class _Manager:
            def filter(self, *args, **kwargs):
                del args, kwargs
                return self

            def first(self):
                return None

            def create(self, *args, **kwargs):
                del args, kwargs
                return None

            def delete(self):
                return None

            def only(self, *args, **kwargs):
                del args, kwargs
                return []

            def select_related(self, *args, **kwargs):
                del args, kwargs
                return self

        class Company:
            objects = _Manager()

        class ManufacturerPart:
            objects = _Manager()

        class SupplierPart:
            objects = _Manager()

        class SupplierPriceBreak:
            objects = _Manager()

        company_models_module.Company = Company
        company_models_module.ManufacturerPart = ManufacturerPart
        company_models_module.SupplierPart = SupplierPart
        company_models_module.SupplierPriceBreak = SupplierPriceBreak

        company_module.models = company_models_module
        sys.modules["company"] = company_module
        sys.modules["company.models"] = company_models_module

    if "part.models" not in sys.modules:
        part_module = types.ModuleType("part")
        part_models_module = types.ModuleType("part.models")

        class _Manager:
            def filter(self, *args, **kwargs):
                del args, kwargs
                return self

            def first(self):
                return None

            def create(self, *args, **kwargs):
                del args, kwargs
                return None

        class Part:
            objects = _Manager()

        part_models_module.Part = Part
        part_module.models = part_models_module
        sys.modules["part"] = part_module
        sys.modules["part.models"] = part_models_module

    if "django.conf" not in sys.modules:
        django_module = types.ModuleType("django")
        django_conf_module = types.ModuleType("django.conf")

        class _Settings:
            DEBUG = False

        django_conf_module.settings = _Settings()

        django_http_module = types.ModuleType("django.http")

        class JsonResponse(dict):
            def __init__(self, data=None, status=200):
                super().__init__(data or {})
                self.status_code = status

        django_http_module.JsonResponse = JsonResponse

        django_urls_module = types.ModuleType("django.urls")

        def re_path(*args, **kwargs):
            return (args, kwargs)

        django_urls_module.re_path = re_path

        sys.modules["django"] = django_module
        sys.modules["django.conf"] = django_conf_module
        sys.modules["django.http"] = django_http_module
        sys.modules["django.urls"] = django_urls_module

    plugin_module = sys.modules.get("plugin")
    if plugin_module is None:
        plugin_module = types.ModuleType("plugin")
        sys.modules["plugin"] = plugin_module

    if not hasattr(plugin_module, "InvenTreePlugin"):

        class InvenTreePlugin:
            pass

        plugin_module.InvenTreePlugin = InvenTreePlugin

    plugin_mixins_module = sys.modules.get("plugin.mixins")
    if plugin_mixins_module is None:
        plugin_mixins_module = types.ModuleType("plugin.mixins")
        sys.modules["plugin.mixins"] = plugin_mixins_module

    if not hasattr(plugin_mixins_module, "SettingsMixin"):

        class SettingsMixin:
            pass

        plugin_mixins_module.SettingsMixin = SettingsMixin

    if not hasattr(plugin_mixins_module, "UrlsMixin"):

        class UrlsMixin:
            pass

        plugin_mixins_module.UrlsMixin = UrlsMixin

    if not hasattr(plugin_mixins_module, "UserInterfaceMixin"):

        class UserInterfaceMixin:
            pass

        plugin_mixins_module.UserInterfaceMixin = UserInterfaceMixin

    if not hasattr(plugin_mixins_module, "APICallMixin"):

        class APICallMixin:
            pass

        plugin_mixins_module.APICallMixin = APICallMixin

    supplier_module = sys.modules.get("plugin.mixins.supplier")
    if supplier_module is None:
        supplier_module = types.ModuleType("plugin.mixins.supplier")
        sys.modules["plugin.mixins.supplier"] = supplier_module

    if not hasattr(supplier_module, "Supplier"):

        class Supplier:
            def __init__(self, slug="", name=""):
                self.slug = slug
                self.name = name

        supplier_module.Supplier = Supplier

    if not hasattr(supplier_module, "SearchResult"):

        class SearchResult:
            def __init__(self, **kwargs):
                self.__dict__.update(kwargs)

        supplier_module.SearchResult = SearchResult

    if not hasattr(supplier_module, "ImportParameter"):

        class ImportParameter:
            def __init__(self, name, value):
                self.name = name
                self.value = value

        supplier_module.ImportParameter = ImportParameter

    if not hasattr(supplier_module, "PartNotFoundError"):

        class PartNotFoundError(Exception):
            pass

        supplier_module.PartNotFoundError = PartNotFoundError

    if not hasattr(supplier_module, "PartImportError"):

        class PartImportError(Exception):
            pass

        supplier_module.PartImportError = PartImportError

    plugin_mixins_module.supplier = supplier_module
    plugin_module.mixins = plugin_mixins_module

    if "users.permissions" not in sys.modules:
        users_module = types.ModuleType("users")
        users_permissions_module = types.ModuleType("users.permissions")

        def check_user_role(*args, **kwargs):
            del args, kwargs
            return True

        users_permissions_module.check_user_role = check_user_role
        users_module.permissions = users_permissions_module

        sys.modules["users"] = users_module
        sys.modules["users.permissions"] = users_permissions_module


_install_core_stubs()

from supplier_scout.core import SupplierScout  # noqa: E402


class TestSupplierScoutCoreHelpers(unittest.TestCase):
    """Validate core tokenization and query planning behavior."""

    def setUp(self):
        self.settings = {
            "TOKEN_NAME_MODE": "fallback",
        }
        self.scout = object.__new__(SupplierScout)
        self.scout.get_setting = lambda key, backup_value=None: self.settings.get(
            key, backup_value
        )
        self.scout.get_effective_setting = (
            lambda key, user=None, backup_value=None: self.settings.get(
                key, backup_value
            )
        )

    def test_normalize_capacitance_token_variants(self):
        self.assertEqual(self.scout._normalize_capacitance_token("10u"), "10uF")
        self.assertEqual(self.scout._normalize_capacitance_token("4n7"), "4.7nF")
        self.assertEqual(self.scout._normalize_capacitance_token("100NF"), "100nF")
        self.assertEqual(self.scout._normalize_capacitance_token("x"), "")

    def test_normalize_resistance_token_variants(self):
        self.assertEqual(self.scout._normalize_resistance_token("0R"), "0ohm")
        self.assertEqual(self.scout._normalize_resistance_token("4R7"), "4.7ohm")
        self.assertEqual(self.scout._normalize_resistance_token("10k"), "10kOhm")
        self.assertEqual(self.scout._normalize_resistance_token("1m5"), "1.5MOhm")
        self.assertEqual(self.scout._normalize_resistance_token("abc"), "")

    def test_decode_eia_cap_code(self):
        self.assertEqual(self.scout._decode_eia_cap_code("104"), "100nF")
        self.assertEqual(self.scout._decode_eia_cap_code("225"), "2.2uF")
        self.assertEqual(self.scout._decode_eia_cap_code("1x4"), "")

    def test_get_name_token_mode_invalid_falls_back(self):
        self.settings["TOKEN_NAME_MODE"] = "unexpected"
        self.assertEqual(self.scout._get_name_token_mode(), "fallback")

    def test_query_plan_fallback_skips_name_with_structured_tokens(self):
        self.settings["TOKEN_NAME_MODE"] = "fallback"
        token_data = {
            "tokens": ["ATMEGA328", "microcontroller"],
            "sources": [
                {"source": "parameter", "tokens": ["ATMEGA328"]},
                {"source": "name", "tokens": ["microcontroller"]},
            ],
        }

        plan = self.scout._build_query_plan(token_data, hints={}, user=None)

        self.assertFalse(plan["include_name_tokens"])
        self.assertIn("ATMEGA328", plan["query_tokens"])
        self.assertNotIn("microcontroller", plan["query_tokens"])

    def test_query_plan_fallback_includes_name_without_structured_tokens(self):
        self.settings["TOKEN_NAME_MODE"] = "fallback"
        token_data = {
            "tokens": ["sensor", "module"],
            "sources": [
                {"source": "name", "tokens": ["sensor"]},
                {"source": "description", "tokens": ["module"]},
            ],
        }

        plan = self.scout._build_query_plan(token_data, hints={}, user=None)

        self.assertTrue(plan["include_name_tokens"])
        self.assertEqual(plan["query_tokens"], ["sensor", "module"])

    def test_query_plan_always_includes_name(self):
        self.settings["TOKEN_NAME_MODE"] = "always"
        token_data = {
            "tokens": ["LM7805", "regulator"],
            "sources": [
                {"source": "manufacturer_part", "tokens": ["LM7805"]},
                {"source": "name", "tokens": ["regulator"]},
            ],
        }

        plan = self.scout._build_query_plan(token_data, hints={}, user=None)

        self.assertTrue(plan["include_name_tokens"])
        self.assertEqual(plan["query_tokens"], ["LM7805", "regulator"])

    def test_build_semantic_query_dedupes_and_limits_tokens(self):
        self.settings["TOKEN_NAME_MODE"] = "always"
        token_data = {
            "tokens": [],
            "sources": [
                {
                    "source": "name",
                    "tokens": [
                        "a",
                        "Token1",
                        "token1",
                        "Token2",
                        "Token3",
                        "Token4",
                        "Token5",
                        "Token6",
                        "Token7",
                        "Token8",
                        "Token9",
                        "Token10",
                        "Token11",
                    ],
                }
            ],
        }

        query = self.scout._build_semantic_query(token_data, hints={}, user=None)

        self.assertEqual(
            query,
            "Token1 Token2 Token3 Token4 Token5 Token6 Token7 Token8 Token9 Token10",
        )

    def test_parse_quantity_value_with_units_and_template_fallback(self):
        self.assertEqual(
            self.scout._parse_quantity_value("3.3V", kind="voltage"),
            3.3,
        )
        self.assertEqual(
            self.scout._parse_quantity_value("500mA", kind="current"),
            0.5,
        )
        self.assertEqual(
            self.scout._parse_quantity_value("250", kind="voltage", default_unit="mV"),
            0.25,
        )
        self.assertIsNone(self.scout._parse_quantity_value("abc", kind="voltage"))

    def test_extract_candidate_constraint_value_from_spec_and_description(self):
        candidate = {
            "spec_attributes": {
                "Rated Voltage": "16V",
                "Current": "2A",
            },
            "description": "General purpose component 1A",
        }

        self.assertEqual(
            self.scout._extract_candidate_constraint_value(
                candidate,
                {"kind": "voltage", "op": "min", "value": 5.0},
            ),
            16.0,
        )
        self.assertEqual(
            self.scout._extract_candidate_constraint_value(
                candidate,
                {"kind": "current", "op": "max", "value": 1.5},
            ),
            1.0,
        )

    def test_rank_candidates_price_strategy_prefers_cheaper_candidate(self):
        self.settings["RANKING_STRATEGY"] = "price"

        candidates = [
            {
                "supplier_part_number": "SKU-A",
                "manufacturer_part_number": "MPN-A",
                "description": "High quality regulator",
                "manufacturer_name": "VendorA",
                "available_quantity": 200,
                "unit_price": 2.0,
                "price_breaks": [{"quantity": 1, "price": 2.0}],
            },
            {
                "supplier_part_number": "SKU-B",
                "manufacturer_part_number": "MPN-B",
                "description": "High quality regulator",
                "manufacturer_name": "VendorB",
                "available_quantity": 200,
                "unit_price": 1.0,
                "price_breaks": [{"quantity": 1, "price": 1.0}],
            },
        ]

        ranked = self.scout._rank_candidates(
            query="regulator",
            candidates=candidates,
            user=None,
            top_n=2,
            constraints=[],
        )

        self.assertEqual(ranked[0]["supplier_part_number"], "SKU-B")
        self.assertGreaterEqual(ranked[0]["score"], ranked[1]["score"])

    def test_rank_candidates_applies_constraint_penalty(self):
        self.settings["RANKING_STRATEGY"] = "balanced"

        candidates = [
            {
                "supplier_part_number": "SKU-pass",
                "manufacturer_part_number": "MPN-pass",
                "description": "15V regulator",
                "manufacturer_name": "VendorA",
                "available_quantity": 100,
                "unit_price": 1.0,
                "spec_attributes": {"Rated Voltage": "16V"},
                "price_breaks": [{"quantity": 1, "price": 1.0}],
            },
            {
                "supplier_part_number": "SKU-fail",
                "manufacturer_part_number": "MPN-fail",
                "description": "3V regulator",
                "manufacturer_name": "VendorB",
                "available_quantity": 100,
                "unit_price": 1.0,
                "spec_attributes": {"Rated Voltage": "3V"},
                "price_breaks": [{"quantity": 1, "price": 1.0}],
            },
        ]

        constraints = [{"kind": "voltage", "op": "min", "value": 5.0}]
        ranked = self.scout._rank_candidates(
            query="regulator",
            candidates=candidates,
            user=None,
            top_n=2,
            constraints=constraints,
        )

        by_sku = {candidate["supplier_part_number"]: candidate for candidate in ranked}

        self.assertEqual(by_sku["SKU-pass"]["constraint_violations"], 0)
        self.assertEqual(by_sku["SKU-fail"]["constraint_violations"], 1)
        self.assertGreater(by_sku["SKU-pass"]["score"], by_sku["SKU-fail"]["score"])

    def test_extract_numeric_constraints_from_part_parameters(self):
        class Template:
            def __init__(self, name, units):
                self.name = name
                self.units = units

        class Parameter:
            def __init__(self, template, data):
                self.template = template
                self.data = data

        class ParameterSet:
            def __init__(self, params):
                self._params = params

            def all(self):
                return self._params

        class FakePart:
            def __init__(self, params):
                self.parameters = ParameterSet(params)

        params = [
            Parameter(Template("Voltage", "V"), "5"),
            Parameter(Template("Current consumption", "mA"), "250"),
        ]

        constraints = self.scout._extract_numeric_constraints(FakePart(params))
        by_key = {(item["kind"], item["op"]): item for item in constraints}

        self.assertIn(("voltage", "min"), by_key)
        self.assertIn(("current", "max"), by_key)
        self.assertEqual(by_key[("voltage", "min")]["value"], 5.0)
        self.assertEqual(by_key[("current", "max")]["value"], 0.25)


if __name__ == "__main__":
    unittest.main()
