"""Unit tests for SupplierScout query and token helper logic.

These tests exercise deterministic helper behavior in core.py and avoid
requiring a full InvenTree runtime by stubbing external modules.
"""

import sys
import types
import unittest
from unittest.mock import patch


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

    if not hasattr(plugin_mixins_module, "ScheduleMixin"):

        class ScheduleMixin:
            pass

        plugin_mixins_module.ScheduleMixin = ScheduleMixin

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
from supplier_scout.adapters import SupplierAPIClient  # noqa: E402


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

    def test_user_setting_defaults_do_not_override_globals(self):
        self.assertEqual(SupplierScout.USER_SETTINGS["TOKEN_NAME_MODE"]["default"], "")
        self.assertEqual(SupplierScout.USER_SETTINGS["RANKING_STRATEGY"]["default"], "")
        self.assertEqual(SupplierScout.USER_SETTINGS["TOP_N_CANDIDATES"]["default"], "")

    def test_supplier_adapters_include_digikey_and_mouser(self):
        self.assertIn("digikey", SupplierScout.SUPPLIER_ADAPTERS)
        self.assertIn("mouser", SupplierScout.SUPPLIER_ADAPTERS)

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

    def test_get_rate_limit_status_payload_includes_supplier_usage(self):
        class FakeAdapter:
            key = "mouser"

            def get_api_usage_status(self):
                return {
                    "supplier_key": "mouser",
                    "rate_limit_per_second": 1,
                    "daily_limit": 1000,
                    "daily_count": 42,
                    "daily_remaining": 958,
                    "daily_percent_used": 4.2,
                    "daily_reset_at": "2030-01-02T00:00:00Z",
                }

            def has_search_credentials(self, user=None):
                del user
                return True

        self.scout._get_registered_suppliers = lambda: [
            {"key": "mouser", "pk": 7, "name": "Mouser"}
        ]
        self.scout._get_supplier_definition = (
            lambda supplier_key: FakeAdapter() if supplier_key == "mouser" else None
        )

        payload = self.scout._get_rate_limit_status_payload(supplier_pk=7)

        self.assertEqual(payload["message"], "OK")
        self.assertEqual(len(payload["suppliers"]), 1)
        self.assertEqual(payload["suppliers"][0]["supplier_pk"], 7)
        self.assertEqual(payload["suppliers"][0]["daily_count"], 42)
        self.assertTrue(payload["suppliers"][0]["configured"])

    def test_search_candidates_requires_part_write_permission(self):
        request = types.SimpleNamespace(user=types.SimpleNamespace())

        with patch("supplier_scout.core.check_user_role", return_value=False):
            response = self.scout.search_candidates(request)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response["message"], "Permission denied")

    def test_apply_candidates_requires_part_write_permission(self):
        request = types.SimpleNamespace(user=types.SimpleNamespace())

        with patch("supplier_scout.core.check_user_role", return_value=False):
            response = self.scout.apply_candidates(request)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response["message"], "Permission denied")

    def test_rate_limit_status_requires_part_write_permission(self):
        request = types.SimpleNamespace(
            user=types.SimpleNamespace(),
            method="GET",
            GET={},
        )

        with patch("supplier_scout.core.check_user_role", return_value=False):
            response = self.scout.rate_limit_status(request)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response["message"], "Permission denied")

    def test_run_resync_requires_admin_for_supplier_wide_resync(self):
        request = types.SimpleNamespace(user=types.SimpleNamespace())
        self.scout._decode_json_body = lambda _request: {"supplier": 7}
        self.scout._get_supplier_registration = lambda supplier_pk: {
            "pk": supplier_pk,
            "key": "mouser",
        }
        self.scout._get_supplier_definition = (
            lambda supplier_key: types.SimpleNamespace(
                key=supplier_key,
                has_search_credentials=lambda user=None: True,
            )
        )

        with patch("supplier_scout.core.check_user_role", return_value=True):
            response = self.scout.run_resync(request)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response["message"], "Admin permission required for supplier resync"
        )

    def test_token_debug_does_not_return_tracebacks(self):
        request = types.SimpleNamespace(
            user=types.SimpleNamespace(),
            method="GET",
            GET={"pk": 1},
        )

        with (
            patch("supplier_scout.core.check_user_role", return_value=True),
            patch(
                "supplier_scout.core.Part.objects.filter",
                side_effect=RuntimeError("boom"),
            ),
        ):
            response = self.scout.token_debug(request)

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response["message"], "Token debug failed")
        self.assertNotIn("debug", response)

    def test_search_candidates_does_not_return_tracebacks(self):
        request = types.SimpleNamespace(user=types.SimpleNamespace())
        self.scout._decode_json_body = lambda _request: {"pk": 1}

        with (
            patch("supplier_scout.core.check_user_role", return_value=True),
            patch(
                "supplier_scout.core.Part.objects.filter",
                side_effect=RuntimeError("boom"),
            ),
        ):
            response = self.scout.search_candidates(request)

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response["message"], "Candidate search failed")
        self.assertNotIn("debug", response)

    def test_apply_candidates_does_not_return_tracebacks(self):
        request = types.SimpleNamespace(user=types.SimpleNamespace())
        self.scout._decode_json_body = lambda _request: {"pk": 1}

        with (
            patch("supplier_scout.core.check_user_role", return_value=True),
            patch(
                "supplier_scout.core.Part.objects.filter",
                side_effect=RuntimeError("boom"),
            ),
        ):
            response = self.scout.apply_candidates(request)

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response["message"], "Candidate apply failed")
        self.assertNotIn("debug", response)

    def test_apply_candidates_refreshes_part_pricing_after_success(self):
        class FakePart:
            def __init__(self):
                self.updated = 0

            def update_pricing(self):
                self.updated += 1

        class FakeQueryResult:
            def __init__(self, part=None):
                self._part = part

            def first(self):
                return self._part

        fake_part = FakePart()
        fake_supplier = types.SimpleNamespace(pk=7)

        request = types.SimpleNamespace(user=types.SimpleNamespace())
        self.scout._decode_json_body = lambda _request: {
            "pk": 1,
            "supplier": 7,
            "candidates": [{"supplier_part_number": "SKU-1"}],
        }

        with (
            patch("supplier_scout.core.check_user_role", return_value=True),
            patch(
                "supplier_scout.core.Part.objects.filter",
                return_value=FakeQueryResult(fake_part),
            ),
            patch(
                "supplier_scout.core.Company.objects.filter",
                return_value=FakeQueryResult(fake_supplier),
            ),
            patch.object(
                self.scout,
                "_upsert_supplier_part_candidate",
                return_value={
                    "status": "created",
                    "supplier_part_pk": 11,
                    "sku": "SKU-1",
                },
            ),
        ):
            response = self.scout.apply_candidates(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["created"], 1)
        self.assertEqual(response["errors"], 0)
        self.assertEqual(fake_part.updated, 1)

    def test_apply_candidates_refreshes_part_pricing_for_multiple_candidates(self):
        class FakePart:
            def __init__(self):
                self.updated = 0

            def update_pricing(self):
                self.updated += 1

        class FakeQueryResult:
            def __init__(self, part=None):
                self._part = part

            def first(self):
                return self._part

        fake_part = FakePart()
        fake_supplier = types.SimpleNamespace(pk=7)

        request = types.SimpleNamespace(user=types.SimpleNamespace())
        self.scout._decode_json_body = lambda _request: {
            "pk": 1,
            "supplier": 7,
            "candidates": [
                {"supplier_part_number": "SKU-1"},
                {"supplier_part_number": "SKU-2"},
            ],
        }

        with (
            patch("supplier_scout.core.check_user_role", return_value=True),
            patch(
                "supplier_scout.core.Part.objects.filter",
                return_value=FakeQueryResult(fake_part),
            ),
            patch(
                "supplier_scout.core.Company.objects.filter",
                return_value=FakeQueryResult(fake_supplier),
            ),
            patch.object(
                self.scout,
                "_upsert_supplier_part_candidate",
                side_effect=[
                    {"status": "created", "supplier_part_pk": 11, "sku": "SKU-1"},
                    {"status": "created", "supplier_part_pk": 12, "sku": "SKU-2"},
                ],
            ),
        ):
            response = self.scout.apply_candidates(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["created"], 2)
        self.assertEqual(response["updated"], 0)
        self.assertEqual(response["errors"], 0)
        self.assertEqual(fake_part.updated, 1)

    def test_search_candidates_all_suppliers_records_supplier_failures(self):
        class FakePartManager:
            def filter(self, **kwargs):
                del kwargs
                return self

            def first(self):
                return object()

        class FakeAdapter:
            def normalize_candidate(self, candidate):
                return dict(candidate)

            def get_candidate_supplier_part_number(self, candidate):
                return str(candidate.get("supplier_part_number") or "")

        from supplier_scout import core as core_module

        original_part_objects = core_module.Part.objects
        try:
            core_module.Part.objects = FakePartManager()

            queried_suppliers = []

            def _fake_get_candidates(supplier, **kwargs):
                del kwargs
                queried_suppliers.append(supplier)
                if supplier == 2:
                    return {"error_status": "Rate limit exceeded"}
                return {"error_status": "OK", "candidates": []}

            self.scout._decode_json_body = lambda request: {
                "pk": 1,
                "query": "resistor",
            }
            self.scout._extract_part_tokens = lambda part, user=None: {
                "tokens": [],
                "sources": [],
                "token_attribution": {},
            }
            self.scout._extract_search_hints = lambda part, token_data: {}
            self.scout._extract_numeric_constraints = lambda part: []
            self.scout._get_search_ready_suppliers = lambda user=None: [
                {"pk": 1, "key": "ok", "name": "OK Supplier"},
                {"pk": 2, "key": "bad", "name": "Bad Supplier"},
            ]
            self.scout._get_supplier_definition = (
                lambda supplier_key: FakeAdapter()
                if supplier_key in ["ok", "bad"]
                else None
            )
            self.scout._get_supplier_max_candidates = (
                lambda supplier_pk, default=40: default
            )
            self.scout.get_candidates = _fake_get_candidates

            response = self.scout.search_candidates(
                types.SimpleNamespace(user=types.SimpleNamespace())
            )

            self.assertEqual(
                response["message"],
                "No supplier matches returned for the current query",
            )
            self.assertEqual(queried_suppliers, [1, 2])
            self.assertEqual(len(response["debug"]["supplier_failures"]), 1)
            self.assertEqual(
                response["debug"]["supplier_failures"][0]["supplier_pk"], 2
            )
            self.assertEqual(
                response["debug"]["supplier_failures"][0]["message"],
                "Rate limit exceeded",
            )
        finally:
            core_module.Part.objects = original_part_objects

    def test_search_candidates_all_suppliers_includes_supplier_metadata_and_existing_detection(
        self,
    ):
        class FakePartManager:
            def filter(self, **kwargs):
                del kwargs
                return self

            def first(self):
                return object()

        class FakeSupplierPartRecord:
            def __init__(self, pk, supplier_id, sku):
                self.pk = pk
                self.supplier_id = supplier_id
                self.SKU = sku

        class FakeSupplierPartManager:
            def __init__(self, rows):
                self._rows = list(rows)

            def filter(self, **kwargs):
                del kwargs
                return self

            def only(self, *args, **kwargs):
                del args, kwargs
                return list(self._rows)

        class FakeAdapter:
            def normalize_candidate(self, candidate):
                return dict(candidate)

            def get_candidate_supplier_part_number(self, candidate):
                return str(candidate.get("supplier_part_number") or "")

        from supplier_scout import core as core_module

        original_part_objects = core_module.Part.objects
        original_supplier_part_objects = core_module.SupplierPart.objects

        try:
            core_module.Part.objects = FakePartManager()
            core_module.SupplierPart.objects = FakeSupplierPartManager([
                FakeSupplierPartRecord(pk=11, supplier_id=1, sku="SKU-1")
            ])

            self.scout._decode_json_body = lambda request: {
                "pk": 1,
                "query": "ic",
                "top_n": 10,
            }
            self.scout._extract_part_tokens = lambda part, user=None: {
                "tokens": [],
                "sources": [],
                "token_attribution": {},
            }
            self.scout._extract_search_hints = lambda part, token_data: {}
            self.scout._extract_numeric_constraints = lambda part: []
            self.scout._get_search_ready_suppliers = lambda user=None: [
                {"pk": 1, "key": "mouser", "name": "Mouser"},
                {"pk": 2, "key": "digikey", "name": "DigiKey"},
            ]
            self.scout._get_supplier_definition = (
                lambda supplier_key: FakeAdapter()
                if supplier_key in ["mouser", "digikey"]
                else None
            )
            self.scout._get_supplier_max_candidates = (
                lambda supplier_pk, default=40: default
            )
            self.scout.get_candidates = lambda supplier, **kwargs: {
                "error_status": "OK",
                "candidates": [
                    {
                        "supplier_part_number": "SKU-1",
                        "manufacturer_part_number": f"MPN-{supplier}",
                    }
                ],
            }
            self.scout._rank_candidates = (
                lambda query, candidates, user=None, top_n=10, constraints=None: list(
                    candidates
                )
            )

            response = self.scout.search_candidates(
                types.SimpleNamespace(user=types.SimpleNamespace())
            )

            self.assertEqual(response["message"], "OK")
            self.assertEqual(response["count"], 2)

            by_supplier_pk = {
                candidate["_supplier_pk"]: candidate
                for candidate in response["candidates"]
            }

            self.assertEqual(by_supplier_pk[1]["_supplier_key"], "mouser")
            self.assertEqual(by_supplier_pk[1]["_supplier_name"], "Mouser")
            self.assertEqual(by_supplier_pk[2]["_supplier_key"], "digikey")
            self.assertEqual(by_supplier_pk[2]["_supplier_name"], "DigiKey")

            self.assertTrue(by_supplier_pk[1]["existing_supplier_part"])
            self.assertEqual(by_supplier_pk[1]["existing_supplier_part_pk"], 11)
            self.assertFalse(by_supplier_pk[2]["existing_supplier_part"])
            self.assertIsNone(by_supplier_pk[2]["existing_supplier_part_pk"])
        finally:
            core_module.Part.objects = original_part_objects
            core_module.SupplierPart.objects = original_supplier_part_objects

    def test_is_supplier_resync_due_uses_interval_and_last_success(self):
        class FakeAdapter:
            key = "mouser"

            def get_resync_interval_minutes(self, default=1440):
                del default
                return 60

        now_ts = 1_000_000
        key = self.scout._get_resync_last_success_setting_key("mouser")

        # Never synced before -> due
        self.settings.pop(key, None)
        self.assertTrue(self.scout._is_supplier_resync_due(FakeAdapter(), now_ts))

        # Last success too recent -> not due
        self.settings[key] = now_ts - (30 * 60)
        self.assertFalse(self.scout._is_supplier_resync_due(FakeAdapter(), now_ts))

        # Last success older than interval -> due
        self.settings[key] = now_ts - (61 * 60)
        self.assertTrue(self.scout._is_supplier_resync_due(FakeAdapter(), now_ts))

    def test_select_resync_candidate_prefers_sku_then_mpn(self):
        class FakeAdapter:
            def normalize_candidate(self, candidate):
                return dict(candidate)

            def get_candidate_supplier_part_number(self, candidate):
                return str(candidate.get("supplier_part_number") or "")

            def get_candidate_manufacturer_part_number(self, candidate):
                return str(candidate.get("manufacturer_part_number") or "")

        class ManufacturerPart:
            MPN = "MPN-42"

        class SupplierPartRecord:
            SKU = "SKU-123"
            manufacturer_part = ManufacturerPart()

        adapter = FakeAdapter()
        supplier_part = SupplierPartRecord()

        candidates = [
            {
                "supplier_part_number": "SKU-123",
                "manufacturer_part_number": "MPN-OTHER",
            },
            {
                "supplier_part_number": "SKU-OTHER",
                "manufacturer_part_number": "MPN-42",
            },
        ]

        selected = self.scout._select_resync_candidate(
            adapter, supplier_part, candidates
        )
        self.assertIsNotNone(selected)
        self.assertEqual(selected.get("supplier_part_number"), "SKU-123")

    def test_select_resync_candidate_returns_none_when_no_exact_match(self):
        class FakeAdapter:
            def normalize_candidate(self, candidate):
                return dict(candidate)

            def get_candidate_supplier_part_number(self, candidate):
                return str(candidate.get("supplier_part_number") or "")

            def get_candidate_manufacturer_part_number(self, candidate):
                return str(candidate.get("manufacturer_part_number") or "")

        class ManufacturerPart:
            MPN = "MPN-42"

        class SupplierPartRecord:
            SKU = "SKU-123"
            manufacturer_part = ManufacturerPart()

        selected = self.scout._select_resync_candidate(
            FakeAdapter(),
            SupplierPartRecord(),
            [
                {
                    "supplier_part_number": "SKU-OTHER",
                    "manufacturer_part_number": "MPN-OTHER",
                }
            ],
        )

        self.assertIsNone(selected)

    def test_select_resync_supplier_parts_round_robin_wraparound(self):
        class FakeSupplierPart:
            def __init__(self, pk):
                self.pk = pk

        class FakeQuerySet:
            def __init__(self, items):
                self._items = list(items)

            def filter(self, **kwargs):
                items = self._items
                if "pk__gt" in kwargs:
                    threshold = int(kwargs.get("pk__gt") or 0)
                    items = [item for item in items if item.pk > threshold]
                if "part_id" in kwargs:
                    part_id = int(kwargs.get("part_id") or 0)
                    # In this test all fake rows map to part_id=1
                    items = items if part_id == 1 else []
                return FakeQuerySet(items)

            def select_related(self, *args, **kwargs):
                del args, kwargs
                return self

            def order_by(self, *args, **kwargs):
                del args, kwargs
                return self

            def __getitem__(self, key):
                return self._items[key]

        class FakeSupplierPartManager:
            def __init__(self, items):
                self._items = items

            def filter(self, **kwargs):
                supplier_id = int(kwargs.get("supplier_id") or 0)
                del supplier_id
                return FakeQuerySet(self._items)

        class FakeCompanyQuery:
            def first(self):
                return object()

        class FakeCompanyManager:
            def filter(self, **kwargs):
                del kwargs
                return FakeCompanyQuery()

        class FakeAdapter:
            key = "mouser"

            def get_resync_batch_size(self, default=100):
                del default
                return 2

        from supplier_scout import core as core_module

        original_supplier_part_objects = core_module.SupplierPart.objects
        original_company_objects = core_module.Company.objects

        try:
            core_module.SupplierPart.objects = FakeSupplierPartManager([
                FakeSupplierPart(1),
                FakeSupplierPart(2),
                FakeSupplierPart(3),
            ])
            core_module.Company.objects = FakeCompanyManager()

            self.scout._get_resync_cursor_pk = lambda supplier_key: 2
            supplier, rows = self.scout._select_resync_supplier_parts(
                {"pk": 7},
                FakeAdapter(),
                part_pk=None,
                use_round_robin=True,
            )

            self.assertIsNotNone(supplier)
            self.assertEqual([row.pk for row in rows], [3])

            self.scout._get_resync_cursor_pk = lambda supplier_key: 99
            supplier, rows = self.scout._select_resync_supplier_parts(
                {"pk": 7},
                FakeAdapter(),
                part_pk=None,
                use_round_robin=True,
            )

            self.assertIsNotNone(supplier)
            self.assertEqual([row.pk for row in rows], [1, 2])
        finally:
            core_module.SupplierPart.objects = original_supplier_part_objects
            core_module.Company.objects = original_company_objects

    def test_get_dashboard_metrics_payload_includes_query_and_cache(self):
        class FakeAdapter:
            key = "mouser"

            def has_search_credentials(self, user=None):
                del user
                return True

            def get_api_usage_status(self):
                return {
                    "rate_limit_per_second": 1,
                    "daily_limit": 1000,
                    "daily_count": 10,
                    "daily_remaining": 990,
                }

            def get_cache_status(self):
                return {
                    "enabled": True,
                    "cache_backend": "filesystem",
                    "cache_file_count": 5,
                }

        self.scout._get_registered_suppliers = lambda: [
            {"key": "mouser", "pk": 7, "name": "Mouser"}
        ]
        self.scout._get_supplier_definition = (
            lambda supplier_key: FakeAdapter() if supplier_key == "mouser" else None
        )

        self.settings[self.scout._supplier_metric_key("mouser", "QUERY_TOTAL")] = 3
        self.settings[self.scout._supplier_metric_key("mouser", "QUERY_OK")] = 2
        self.settings[self.scout._supplier_metric_key("mouser", "QUERY_ERROR")] = 1
        self.settings[
            self.scout._supplier_metric_key("mouser", "QUERY_CANDIDATE_TOTAL")
        ] = 9

        payload = self.scout._get_dashboard_metrics_payload()

        self.assertEqual(payload["message"], "OK")
        self.assertEqual(len(payload["suppliers"]), 1)
        supplier = payload["suppliers"][0]
        self.assertEqual(supplier["supplier_name"], "Mouser")
        self.assertEqual(supplier["query_metrics"]["total_queries"], 3)
        self.assertEqual(supplier["query_metrics"]["ok_queries"], 2)
        self.assertEqual(supplier["query_metrics"]["error_queries"], 1)
        self.assertEqual(supplier["cache_status"]["cache_file_count"], 5)

    def test_supplier_api_client_logs_redacted_request_in_debug_mode(self):
        client = SupplierAPIClient(
            plugin=types.SimpleNamespace(
                get_setting=lambda key, backup_value=None: backup_value
            ),
            base_url="https://api.example.invalid",
        )
        response = types.SimpleNamespace(status_code=200)
        settings_module = sys.modules["django.conf"].settings
        settings_module.DEBUG = True

        with (
            patch(
                "supplier_scout.adapters.APICallMixin.api_call",
                return_value=response,
                create=True,
            ) as mock_api_call,
            patch("supplier_scout.adapters.logger") as mock_logger,
        ):
            result = client.api_call(
                "https://api.example.invalid/search?apiKey=secret-key&query=abc",
                method="POST",
                json={"apiKey": "secret-key", "query": "abc"},
                headers={
                    "Authorization": "secret-token",
                    "X-Trace": "trace-123",
                },
            )

        self.assertIs(result, response)
        mock_api_call.assert_called_once()
        self.assertEqual(mock_logger.debug.call_count, 2)

        logged_text = " ".join(
            str(argument)
            for call in mock_logger.debug.call_args_list
            for argument in call.args
        )
        self.assertIn("***", logged_text)
        self.assertNotIn("secret-key", logged_text)
        self.assertNotIn("secret-token", logged_text)
        self.assertIn("trace-123", logged_text)

    def test_supplier_api_client_skips_logging_when_debug_disabled(self):
        client = SupplierAPIClient(
            plugin=types.SimpleNamespace(
                get_setting=lambda key, backup_value=None: backup_value
            ),
            base_url="https://api.example.invalid",
        )
        response = types.SimpleNamespace(status_code=200)
        settings_module = sys.modules["django.conf"].settings
        settings_module.DEBUG = False

        with (
            patch(
                "supplier_scout.adapters.APICallMixin.api_call",
                return_value=response,
                create=True,
            ),
            patch("supplier_scout.adapters.logger") as mock_logger,
        ):
            result = client.api_call(
                "https://api.example.invalid/search?apiKey=secret-key",
                method="GET",
            )

        self.assertIs(result, response)
        mock_logger.debug.assert_not_called()


if __name__ == "__main__":
    unittest.main()
