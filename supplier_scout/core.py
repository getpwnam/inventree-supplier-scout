"""Supplier Scout plugin core implementation."""

import json
import logging
import re
import time
from difflib import SequenceMatcher

from common.models import InvenTreeSetting
from company.models import Company
from company.models import ManufacturerPart
from company.models import SupplierPart
from company.models import SupplierPriceBreak
from django.conf import settings
from django.http import JsonResponse
from django.urls import re_path

try:
    from django.utils.translation import gettext_lazy as _  # type: ignore[import-not-found]
except Exception:  # pragma: no cover - fallback for isolated unit tests

    def _(value):
        return value


from part.models import Part
from plugin import InvenTreePlugin
from plugin.mixins import ScheduleMixin
from plugin.mixins import SettingsMixin
from plugin.mixins import UrlsMixin
from plugin.mixins import UserInterfaceMixin
from plugin.mixins import supplier
from users.permissions import check_user_role

from . import PLUGIN_VERSION
from .adapters import build_supplier_settings
from .adapters import build_supplier_schedule_settings
from .adapters import build_supplier_user_settings
from .mouser import MouserSupplierAdapter


logger = logging.getLogger(__name__)


class SupplierScout(
    ScheduleMixin,
    SettingsMixin,
    UrlsMixin,
    UserInterfaceMixin,
    InvenTreePlugin,
):
    """SupplierScout plugin."""

    TITLE = _("Supplier Scout")
    NAME = "SupplierScout"
    SLUG = "supplierscout"
    DESCRIPTION = _("Part search, matching and ordering with popular suppliers")
    VERSION = PLUGIN_VERSION

    AUTHOR = "Charles Price"
    WEBSITE = "https://github.com/getpwnam/inventree-supplier-scout"
    LICENSE = "MIT"
    ADMIN_SOURCE = "Settings.js:renderPluginSettings"

    SUPPLIER_ADAPTERS = {
        "mouser": MouserSupplierAdapter,
    }

    SETTINGS = {
        **build_supplier_settings(SUPPLIER_ADAPTERS.values()),
        **build_supplier_schedule_settings(SUPPLIER_ADAPTERS.values()),
        "RESYNC_SCHEDULER_TICK_MINUTES": {
            "name": _("Supplier resync scheduler tick (minutes)"),
            "description": _(
                "How often the scheduler checks for supplier resync work. Per-supplier intervals control actual refresh frequency."
            ),
            "validator": int,
            "default": 15,
        },
        "RANKING_STRATEGY": {
            "name": _("Candidate ranking strategy"),
            "description": _("Default ranking strategy for supplier suggestions"),
            "choices": [
                ("balanced", _("Balanced score")),
                ("availability", _("Availability first")),
                ("price", _("Price first")),
            ],
            "default": "balanced",
        },
        "TOKEN_PARAMETER_NAMES": {
            "name": _("Token parameter names"),
            "description": _(
                "Comma or newline separated parameter names used for token generation. Leave empty to use all parameters."
            ),
            "default": "",
        },
        "TOKEN_INCLUDE_CATEGORY_NAMES": {
            "name": _("Include category name tokens"),
            "description": _(
                "Include part category names (and parents) in generated search tokens."
            ),
            "default": True,
        },
        "TOKEN_NAME_MODE": {
            "name": _("Name token strategy"),
            "description": _(
                "How part name/description tokens are used in auto-generated supplier queries."
            ),
            "choices": [
                ("fallback", _("Only when structured tokens are unavailable")),
                ("always", _("Always include name and description tokens")),
                ("never", _("Never include name and description tokens")),
            ],
            "default": "fallback",
        },
    }

    USER_SETTINGS = {
        **build_supplier_user_settings(SUPPLIER_ADAPTERS.values()),
        "RANKING_STRATEGY": {
            "name": _("Candidate ranking strategy (user override)"),
            "description": _("User-specific ranking strategy (overrides global value)"),
            "choices": [
                ("balanced", _("Balanced score")),
                ("availability", _("Availability first")),
                ("price", _("Price first")),
            ],
            "default": "balanced",
        },
        "TOP_N_CANDIDATES": {
            "name": _("Top N candidate results (user override)"),
            "description": _("Default number of ranked candidates shown"),
            "default": 10,
        },
        "TOKEN_NAME_MODE": {
            "name": _("Name token strategy (user override)"),
            "description": _(
                "How part name/description tokens are used in auto-generated supplier queries."
            ),
            "choices": [
                ("fallback", _("Only when structured tokens are unavailable")),
                ("always", _("Always include name and description tokens")),
                ("never", _("Never include name and description tokens")),
            ],
            "default": "fallback",
        },
    }

    SCHEDULED_TASKS = {
        "supplier_resync_tick": {
            "func": "scheduled_supplier_resync",
            "schedule": "I",
            "minutes": 15,
        }
    }

    def get_effective_setting(self, key, user=None, backup_value=None):
        """Return user setting value if available, otherwise fallback to global setting."""
        if user and key in getattr(self, "user_settings", {}):
            user_value = self.get_user_setting(key, user, backup_value=None)
            if user_value not in [None, ""]:
                return user_value
        return self.get_setting(key, backup_value=backup_value)

    def get_scheduled_tasks(self):
        tasks = dict(self.SCHEDULED_TASKS)
        tick_minutes = self._to_int_from_string(
            self.get_setting("RESYNC_SCHEDULER_TICK_MINUTES", backup_value=15),
            default=15,
        )
        tasks["supplier_resync_tick"]["minutes"] = max(1, tick_minutes)
        return tasks

    # SupplierMixin-compatible internals ---------------------------------
    # These methods mirror the SupplierMixin contract so migration can happen
    # later without changing core data extraction / import behavior.

    def _resolve_supplier_registration_from_slug(self, supplier_slug):
        slug_text = str(supplier_slug or "").strip().lower()
        if slug_text == "":
            return None

        if ":" in slug_text:
            supplier_key, supplier_pk = slug_text.split(":", 1)
            supplier_key = supplier_key.strip()
            try:
                supplier_pk = int(supplier_pk)
            except Exception:
                return None

            for registration in self._get_registered_suppliers():
                if (
                    str(registration.get("key") or "").strip().lower() == supplier_key
                    and int(registration.get("pk") or 0) == supplier_pk
                ):
                    return registration
            return None

        matches = [
            registration
            for registration in self._get_registered_suppliers()
            if str(registration.get("key") or "").strip().lower() == slug_text
        ]

        if len(matches) == 1:
            return matches[0]

        return None

    def _normalize_import_payload(self, data):
        payload = dict(data or {})
        if "candidate" in payload and isinstance(payload.get("candidate"), dict):
            candidate = dict(payload.get("candidate") or {})
            for key in ["_supplier_key", "_supplier_pk"]:
                if key in payload and key not in candidate:
                    candidate[key] = payload.get(key)
            return candidate
        return payload

    def get_suppliers(self):
        suppliers = []
        for registration in self._get_registered_suppliers():
            adapter = self._get_supplier_definition(registration.get("key"))
            if adapter is None:
                continue

            if not adapter.has_search_credentials(user=None):
                continue

            suppliers.append(
                supplier.Supplier(
                    slug=f"{registration.get('key')}:{registration.get('pk')}",
                    name=str(registration.get("name") or registration.get("key") or ""),
                )
            )

        return suppliers

    def get_search_results(self, supplier_slug, term):
        registration = self._resolve_supplier_registration_from_slug(supplier_slug)
        if registration is None:
            return []

        supplier_pk = int(registration.get("pk") or 0)
        if supplier_pk <= 0:
            return []

        adapter = self._get_supplier_definition(registration.get("key"))
        if adapter is None:
            return []

        max_candidates = self._get_supplier_max_candidates(supplier_pk, default=40)
        response = self.get_candidates(
            supplier=supplier_pk,
            query=str(term or "").strip(),
            max_results=max_candidates,
            user=None,
        )

        if response.get("error_status") != "OK":
            return []

        results = []
        search_term = str(term or "").strip().lower()
        for candidate_raw in response.get("candidates", []):
            candidate = adapter.normalize_candidate(candidate_raw)
            sku = adapter.get_candidate_supplier_part_number(candidate)
            mpn = adapter.get_candidate_manufacturer_part_number(candidate)

            if sku == "":
                continue

            supplier_part = (
                SupplierPart.objects.filter(
                    supplier_id=supplier_pk,
                    SKU__iexact=sku,
                )
                .select_related("part")
                .first()
            )

            unit_price = candidate.get("unit_price")
            unit_price_text = ""
            if unit_price not in [None, ""]:
                unit_price_text = f"{self._to_float(unit_price, default=0.0):g}"

            currency = ""
            breaks = candidate.get("price_breaks") or []
            if breaks:
                currency = str(breaks[0].get("currency") or "").strip()
            if unit_price_text and currency:
                unit_price_text = f"{unit_price_text} {currency}"

            exact = False
            if search_term:
                exact = search_term in [sku.lower(), mpn.lower()]

            results.append(
                supplier.SearchResult(
                    sku=sku,
                    id=sku,
                    name=mpn or sku,
                    description=str(candidate.get("description") or "").strip() or None,
                    exact=exact,
                    price=unit_price_text or None,
                    link=str(candidate.get("supplier_link") or "").strip() or None,
                    image_url=str(candidate.get("image_url") or "").strip() or None,
                    existing_part=getattr(supplier_part, "part", None),
                )
            )

        return results

    def get_import_data(self, supplier_slug, part_id):
        registration = self._resolve_supplier_registration_from_slug(supplier_slug)
        if registration is None:
            raise supplier.PartNotFoundError()

        supplier_pk = int(registration.get("pk") or 0)
        if supplier_pk <= 0:
            raise supplier.PartNotFoundError()

        adapter = self._get_supplier_definition(registration.get("key"))
        if adapter is None:
            raise supplier.PartNotFoundError()

        part_key = str(part_id or "").strip()
        if part_key == "":
            raise supplier.PartNotFoundError()

        response = self.get_candidates(
            supplier=supplier_pk,
            query=part_key,
            max_results=self._get_supplier_max_candidates(supplier_pk, default=40),
            user=None,
        )

        if response.get("error_status") != "OK":
            raise supplier.PartNotFoundError()

        selected = None
        for candidate_raw in response.get("candidates", []):
            candidate = adapter.normalize_candidate(candidate_raw)
            sku = adapter.get_candidate_supplier_part_number(candidate)
            mpn = adapter.get_candidate_manufacturer_part_number(candidate)
            if part_key.lower() in [sku.lower(), mpn.lower()]:
                selected = candidate
                break

        if selected is None and response.get("candidates"):
            selected = adapter.normalize_candidate(response.get("candidates", [])[0])

        if selected is None:
            raise supplier.PartNotFoundError()

        selected["_supplier_key"] = registration.get("key")
        selected["_supplier_pk"] = supplier_pk
        return selected

    def get_pricing_data(self, data):
        candidate = self._normalize_import_payload(data)
        pricing = {}

        for price_break in candidate.get("price_breaks", []) or []:
            quantity = self._to_int_from_string(price_break.get("quantity"), default=0)
            if quantity <= 0:
                continue

            price = self._to_float(price_break.get("price"), default=0.0)
            currency = str(price_break.get("currency") or "").strip()
            if currency == "":
                currency = InvenTreeSetting.get_setting("INVENTREE_DEFAULT_CURRENCY")

            pricing[quantity] = (price, currency)

        return pricing

    def get_parameters(self, data):
        candidate = self._normalize_import_payload(data)
        parameters = []

        for name, value in (candidate.get("spec_attributes") or {}).items():
            name_text = str(name or "").strip()
            value_text = str(value or "").strip()
            if name_text == "" or value_text == "":
                continue
            parameters.append(
                supplier.ImportParameter(name=name_text, value=value_text)
            )

        packaging = str(candidate.get("packaging") or "").strip()
        if packaging:
            parameters.append(
                supplier.ImportParameter(name="Packaging", value=packaging)
            )

        return parameters

    def import_part(self, data, *, category=None, creation_user=None):
        candidate = self._normalize_import_payload(data)
        name = str(
            candidate.get("manufacturer_part_number")
            or candidate.get("supplier_part_number")
            or ""
        ).strip()

        if name == "":
            raise supplier.PartImportError(
                _("Candidate does not include a usable part name")
            )

        part = Part.objects.filter(name__iexact=name).first()
        if part is None:
            if category is None:
                raise supplier.PartImportError(
                    _("Category is required when importing a new part")
                )

            part = Part.objects.create(
                name=name,
                description=str(candidate.get("description") or "").strip(),
                purchaseable=True,
                category=category,
            )

        return part

    def import_manufacturer_part(self, data, *, part):
        candidate = self._normalize_import_payload(data)
        supplier_key = str(candidate.get("_supplier_key") or "").strip().lower()
        adapter = self._get_supplier_definition(supplier_key)
        if adapter is None:
            raise supplier.PartImportError(_("Unknown supplier adapter for import"))

        manufacturer_part = self._resolve_candidate_manufacturer_part(
            part=part,
            candidate=candidate,
            adapter=adapter,
        )

        if manufacturer_part is None:
            raise supplier.PartImportError(_("Failed to resolve manufacturer part"))

        return manufacturer_part

    def import_supplier_part(self, data, *, part, manufacturer_part):
        candidate = self._normalize_import_payload(data)
        supplier_pk = self._to_int_from_string(candidate.get("_supplier_pk"), default=0)
        if supplier_pk <= 0:
            raise supplier.PartImportError(
                _("Supplier import context is missing supplier PK")
            )

        supplier_company = Company.objects.filter(pk=supplier_pk).first()
        if supplier_company is None:
            raise supplier.PartImportError(_("Supplier company not found"))

        supplier_key = str(candidate.get("_supplier_key") or "").strip().lower()
        adapter = self._get_supplier_definition(supplier_key)
        if adapter is None:
            raise supplier.PartImportError(_("Unknown supplier adapter for import"))

        candidate = adapter.normalize_candidate(candidate)
        sku = adapter.get_candidate_supplier_part_number(candidate)
        if sku == "":
            raise supplier.PartImportError(_("Candidate supplier part number missing"))

        supplier_part = SupplierPart.objects.filter(
            part=part,
            supplier=supplier_company,
            SKU__iexact=sku,
        ).first()

        update_data = adapter.build_supplier_part_update_data(candidate)
        if supplier_part is None:
            supplier_part = SupplierPart.objects.create(
                part=part,
                supplier=supplier_company,
                manufacturer_part=manufacturer_part,
                SKU=sku,
                **update_data,
            )
        else:
            supplier_part.manufacturer_part = manufacturer_part
            for key, value in update_data.items():
                setattr(supplier_part, key, value)
            supplier_part.save()

        SupplierPriceBreak.objects.filter(part=supplier_part).delete()
        for quantity, (price, currency) in self.get_pricing_data(candidate).items():
            SupplierPriceBreak.objects.create(
                part=supplier_part,
                quantity=quantity,
                price=price,
                price_currency=currency,
            )

        return supplier_part

    def _normalize_param_name(self, value):
        text = str(value or "").strip().lower()
        return re.sub(r"[^a-z0-9]+", "", text)

    def _get_token_parameter_filters(self):
        configured = str(
            self.get_setting("TOKEN_PARAMETER_NAMES", backup_value="") or ""
        )
        if configured.strip() == "":
            return set()

        tokens = re.split(r"[\n,;]+", configured)
        return {
            self._normalize_param_name(token)
            for token in tokens
            if self._normalize_param_name(token) != ""
        }

    def _setting_to_bool(self, value, default=False):
        if isinstance(value, bool):
            return value
        if value is None:
            return default

        text = str(value).strip().lower()
        if text in ["1", "true", "yes", "on", "y"]:
            return True
        if text in ["0", "false", "no", "off", "n"]:
            return False

        return default

    def _get_name_token_mode(self, user=None):
        mode = (
            str(
                self.get_effective_setting(
                    "TOKEN_NAME_MODE", user=user, backup_value="fallback"
                )
                or "fallback"
            )
            .strip()
            .lower()
        )

        if mode not in ["fallback", "always", "never"]:
            return "fallback"

        return mode

    def _to_float(self, value, default=0.0):
        try:
            if value is None:
                return default
            if isinstance(value, (int, float)):
                return float(value)

            clean = str(value).strip()
            clean = re.sub(r"[^0-9,\.\-]+", "", clean)

            if clean.count(",") > 0 and clean.count(".") > 0:
                if clean.rfind(",") > clean.rfind("."):
                    clean = clean.replace(".", "").replace(",", ".")
                else:
                    clean = clean.replace(",", "")
            elif clean.count(",") > 0 and clean.count(".") == 0:
                comma_parts = clean.split(",")
                if len(comma_parts) == 2 and len(comma_parts[1]) <= 3:
                    clean = ".".join(comma_parts)
                else:
                    clean = "".join(comma_parts)

            return float(clean)
        except Exception:
            return default

    def _to_int_from_string(self, value, default=0):
        if value is None:
            return default
        if isinstance(value, int):
            return value

        text = str(value)
        match = re.search(r"\d+", text.replace(",", ""))
        if match:
            try:
                return int(match.group(0))
            except Exception:
                pass
        return default

    def _decode_eia_cap_code(self, token):
        text = str(token or "").strip()
        if not re.match(r"^\d{3}$", text):
            return ""
        try:
            sig = int(text[:2])
            zeros = int(text[2])
            value_pf = sig * (10**zeros)
        except Exception:
            return ""

        if value_pf >= 1_000_000:
            return f"{value_pf / 1_000_000:g}uF"
        if value_pf >= 1_000:
            return f"{value_pf / 1_000:g}nF"
        return f"{value_pf:g}pF"

    def _normalize_capacitance_token(self, token):
        text = str(token or "").strip()
        lower = text.lower()

        if re.match(r"^\d+(\.\d+)?(pf|nf|uf|mf|f)$", lower):
            unit = (
                lower[-2:] if lower.endswith(("pf", "nf", "uf", "mf")) else lower[-1:]
            )
            value = lower[: -len(unit)]
            normalized_unit = unit.replace("f", "F") if len(unit) == 2 else "F"
            return f"{value}{normalized_unit}"

        if re.match(r"^\d+(\.\d+)?[pnu]$", lower):
            value = lower[:-1]
            unit = lower[-1]
            unit_map = {"p": "pF", "n": "nF", "u": "uF"}
            return f"{value}{unit_map.get(unit, '')}"

        match = re.match(r"^(\d+)([pnu])(\d+)$", lower)
        if match:
            whole, unit, frac = match.groups()
            unit_map = {"p": "pF", "n": "nF", "u": "uF"}
            return f"{whole}.{frac}{unit_map.get(unit, '')}"

        return ""

    def _normalize_resistance_token(self, token):
        text = str(token or "").strip()
        lower = text.lower()

        if lower == "0r":
            return "0ohm"

        match = re.match(r"^(\d*)r(\d*)$", lower)
        if match:
            whole, frac = match.groups()
            if whole == "" and frac == "":
                return ""
            whole = whole or "0"
            if frac:
                return f"{whole}.{frac}ohm"
            return f"{whole}ohm"

        match = re.match(r"^(\d+)([km])(\d+)$", lower)
        if match:
            whole, unit, frac = match.groups()
            suffix = "kOhm" if unit == "k" else "MOhm"
            return f"{whole}.{frac}{suffix}"

        if re.match(r"^\d+(\.\d+)?(ohm|kohm|mohm|r|k|m)$", lower):
            if lower.endswith("ohm"):
                return lower
            if lower.endswith("r"):
                return f"{lower[:-1]}ohm"
            if lower.endswith("k"):
                return f"{lower[:-1]}kOhm"
            if lower.endswith("m"):
                return f"{lower[:-1]}MOhm"

        return ""

    def _tokenize_text(self, text, include_trace=False):
        if not text:
            return ([], []) if include_trace else []

        chunks = re.split(r"[^A-Za-z0-9%._+-]+", str(text))
        tokens = []
        trace = []

        def add_token(token_value, rule, fragment):
            token_text = str(token_value or "").strip()
            if len(token_text) < 2:
                return

            tokens.append(token_text)

            if include_trace:
                trace.append({
                    "token": token_text,
                    "rule": rule,
                    "fragment": str(fragment or ""),
                })

        for chunk in chunks:
            token = chunk.strip()
            if len(token) < 2:
                continue

            add_token(token, "raw_chunk", token)

            for sub in re.split(r"[_\-/]+", token):
                sub_token = sub.strip()
                if len(sub_token) >= 2:
                    add_token(sub_token, "split_subtoken", token)

            lower = token.lower()
            if re.match(r"^\d+(\.\d+)?p$", lower):
                numeric = lower[:-1]
                add_token(f"{numeric}pf", "shorthand_p_to_pf", token)
                add_token(f"{numeric}pF", "shorthand_p_to_pF", token)
            elif re.match(r"^\d+(\.\d+)?n$", lower):
                numeric = lower[:-1]
                add_token(f"{numeric}nf", "shorthand_n_to_nf", token)
                add_token(f"{numeric}nF", "shorthand_n_to_nF", token)
            elif re.match(r"^\d+(\.\d+)?u$", lower):
                numeric = lower[:-1]
                add_token(f"{numeric}uf", "shorthand_u_to_uf", token)
                add_token(f"{numeric}uF", "shorthand_u_to_uF", token)
            elif re.match(r"^\d+(\.\d+)?k$", lower):
                numeric = lower[:-1]
                add_token(f"{numeric}kohm", "shorthand_k_to_kohm", token)
                add_token(f"{numeric}kOhm", "shorthand_k_to_kOhm", token)

            cap_normalized = self._normalize_capacitance_token(token)
            if cap_normalized:
                add_token(cap_normalized, "normalized_capacitance", token)

            res_normalized = self._normalize_resistance_token(token)
            if res_normalized:
                add_token(res_normalized, "normalized_resistance", token)

            cap_code = self._decode_eia_cap_code(token)
            if cap_code:
                add_token(cap_code, "decoded_eia_cap_code", token)

        if include_trace:
            return tokens, trace

        return tokens

    def _extract_part_tokens(self, part, user=None):
        tokens = []
        sources = []
        token_origins = {}
        parameter_filters = self._get_token_parameter_filters()

        category_names = []
        seen_categories = set()
        include_categories = self._setting_to_bool(
            self.get_setting("TOKEN_INCLUDE_CATEGORY_NAMES", backup_value=True),
            default=True,
        )

        if include_categories:
            category = getattr(part, "category", None)

            # Include the direct category and its parent chain as token sources.
            while category is not None:
                category_pk = getattr(category, "pk", id(category))
                if category_pk in seen_categories:
                    break
                seen_categories.add(category_pk)

                category_name = str(getattr(category, "name", "") or "").strip()
                if category_name:
                    category_names.append(category_name)

                category = getattr(category, "parent", None)

        def register_origins(base_context, token_trace):
            for origin in token_trace:
                token_key = str(origin.get("token") or "").lower()
                if token_key == "":
                    continue

                token_origins.setdefault(token_key, []).append({
                    **base_context,
                    "rule": origin.get("rule", ""),
                    "fragment": origin.get("fragment", ""),
                })

        base_fields = [
            ("name", getattr(part, "name", "")),
            ("description", getattr(part, "description", "")),
            ("IPN", getattr(part, "IPN", "")),
            ("SKU", getattr(part, "SKU", "")),
        ]

        manufacturer_part = ManufacturerPart.objects.filter(part=part).first()
        if manufacturer_part is not None:
            mpn = getattr(manufacturer_part, "MPN", None) or getattr(
                manufacturer_part, "part_number", None
            )
            if mpn:
                base_fields.append(("manufacturer_part", mpn))

        for source_name, source_value in base_fields:
            source_tokens, source_trace = self._tokenize_text(
                source_value, include_trace=True
            )
            if source_tokens:
                tokens.extend(source_tokens)
                sources.append({
                    "source": source_name,
                    "value": str(source_value),
                    "tokens": source_tokens,
                    "token_trace": source_trace,
                })
                register_origins(
                    {
                        "source": source_name,
                        "value": str(source_value),
                    },
                    source_trace,
                )

        for category_name in category_names:
            category_tokens, category_trace = self._tokenize_text(
                category_name, include_trace=True
            )
            if category_tokens:
                tokens.extend(category_tokens)
                sources.append({
                    "source": "category",
                    "value": category_name,
                    "tokens": category_tokens,
                    "token_trace": category_trace,
                })
                register_origins(
                    {
                        "source": "category",
                        "value": category_name,
                    },
                    category_trace,
                )

        param_sets = []
        if hasattr(part, "parameters"):
            param_sets.append(getattr(part, "parameters"))
        if hasattr(part, "parameters_list"):
            param_sets.append(getattr(part, "parameters_list"))

        for param_set in param_sets:
            try:
                params = param_set.all()
            except Exception:
                continue

            for param in params:
                template = getattr(param, "template", None)
                template_name = (
                    getattr(template, "name", "") if template is not None else ""
                )
                param_data = getattr(param, "data", "")
                template_unit = str(
                    getattr(template, "units", "") if template is not None else ""
                ).strip()

                if parameter_filters:
                    normalized_name = self._normalize_param_name(template_name)
                    if normalized_name not in parameter_filters:
                        continue

                param_value_text = str(param_data or "").strip()
                param_tokens, param_trace = self._tokenize_text(
                    param_value_text, include_trace=True
                )

                numeric_value = param_value_text
                if template_unit and re.match(r"^[-+]?\d+(\.\d+)?$", numeric_value):
                    for unitized_text in [
                        f"{numeric_value}{template_unit}",
                        f"{numeric_value} {template_unit}",
                    ]:
                        extra_tokens, extra_trace = self._tokenize_text(
                            unitized_text, include_trace=True
                        )
                        for trace_entry in extra_trace:
                            trace_entry["rule"] = (
                                f"unitized_{trace_entry.get('rule', 'raw_chunk')}"
                            )
                            trace_entry["fragment"] = (
                                f"{trace_entry.get('fragment', '')} | template_unit={template_unit}"
                            )
                        param_tokens.extend(extra_tokens)
                        param_trace.extend(extra_trace)

                if param_tokens:
                    tokens.extend(param_tokens)
                    sources.append({
                        "source": "parameter",
                        "name": str(template_name),
                        "value": str(param_data),
                        "tokens": param_tokens,
                        "token_trace": param_trace,
                    })
                    register_origins(
                        {
                            "source": "parameter",
                            "name": str(template_name),
                            "value": str(param_data),
                        },
                        param_trace,
                    )

        deduped = []
        seen = set()
        for token in tokens:
            key = token.lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(token)

        token_attribution = {
            token: token_origins.get(token.lower(), []) for token in deduped
        }

        return {
            "tokens": deduped,
            "sources": sources,
            "token_attribution": token_attribution,
        }

    def _extract_search_hints(self, part, token_data):
        hints = {
            "component_type": "",
            "capacitance": "",
            "resistance": "",
            "inductance": "",
            "package": "",
            "tolerance": "",
            "voltage": "",
        }

        name = str(getattr(part, "name", "") or "").strip().lower()
        if re.match(r"^c[_\-]", name):
            hints["component_type"] = "capacitor"
        elif re.match(r"^r[_\-]", name):
            hints["component_type"] = "resistor"
        elif re.match(r"^l[_\-]", name):
            hints["component_type"] = "inductor"

        for source in token_data.get("sources", []):
            if source.get("source") != "parameter":
                continue

            param_name = str(source.get("name") or "").lower()
            param_value = str(source.get("value") or "").strip()
            if not param_value:
                continue

            if "capacit" in param_name and not hints["capacitance"]:
                hints["capacitance"] = param_value
                if not hints["component_type"]:
                    hints["component_type"] = "capacitor"

            if ("resist" in param_name or "ohm" in param_name) and not hints[
                "resistance"
            ]:
                hints["resistance"] = param_value
                if not hints["component_type"]:
                    hints["component_type"] = "resistor"

            if "induct" in param_name and not hints["inductance"]:
                hints["inductance"] = param_value
                if not hints["component_type"]:
                    hints["component_type"] = "inductor"

            if (
                "package" in param_name or "case" in param_name or "size" in param_name
            ) and not hints["package"]:
                hints["package"] = param_value

            if "tolerance" in param_name and not hints["tolerance"]:
                hints["tolerance"] = param_value

            if ("voltage" in param_name or "rated" in param_name) and not hints[
                "voltage"
            ]:
                hints["voltage"] = param_value

        for token in token_data.get("tokens", []):
            token_text = str(token).strip()
            lower = token_text.lower()

            if not hints["package"] and re.match(r"^\d{4}$", token_text):
                hints["package"] = token_text

            if not hints["tolerance"] and re.match(r"^\d+(\.\d+)?%$", token_text):
                hints["tolerance"] = token_text

            if not hints["voltage"] and re.match(r"^\d+(\.\d+)?v$", lower):
                hints["voltage"] = token_text

            if not hints["capacitance"] and re.match(
                r"^\d+(\.\d+)?(pf|nf|uf|mf|f|p|n|u)$", lower
            ):
                hints["capacitance"] = token_text

            if not hints["capacitance"]:
                cap_normalized = self._normalize_capacitance_token(token_text)
                if cap_normalized:
                    hints["capacitance"] = cap_normalized

            if not hints["capacitance"]:
                cap_code = self._decode_eia_cap_code(token_text)
                if cap_code:
                    hints["capacitance"] = cap_code

            if not hints["resistance"] and re.match(
                r"^\d+(\.\d+)?(r|ohm|k|kohm|mohm)$", lower
            ):
                hints["resistance"] = token_text

            if not hints["resistance"]:
                res_normalized = self._normalize_resistance_token(token_text)
                if res_normalized:
                    hints["resistance"] = res_normalized

            if not hints["inductance"] and re.match(r"^\d+(\.\d+)?(uh|mh|h)$", lower):
                hints["inductance"] = token_text

        return hints

    def _build_semantic_query(self, token_data, hints, user=None):
        plan = self._build_query_plan(token_data, hints, user=user)
        query_tokens = plan.get("query_tokens", [])

        deduped = []
        seen = set()
        for token in query_tokens:
            clean = token.strip()
            if len(clean) < 2:
                continue

            key = clean.lower()
            if key in seen:
                continue

            seen.add(key)
            deduped.append(clean)

        return " ".join(deduped[:10])

    def _build_query_plan(self, token_data, hints, user=None):
        query_tokens = []

        def source_tokens(source_name):
            values = []
            for source in token_data.get("sources", []):
                if source.get("source") != source_name:
                    continue
                for token in source.get("tokens", []):
                    values.append(str(token))
            return values

        if hints.get("component_type"):
            query_tokens.append(hints["component_type"])

        for key in [
            "capacitance",
            "resistance",
            "inductance",
            "package",
            "tolerance",
            "voltage",
        ]:
            value = str(hints.get(key) or "").strip()
            if value:
                query_tokens.append(value)

        for source_name in ["manufacturer_part", "IPN", "SKU", "parameter", "category"]:
            query_tokens.extend(source_tokens(source_name))

        has_structured_tokens = any(
            source.get("source")
            in [
                "manufacturer_part",
                "IPN",
                "SKU",
                "parameter",
                "category",
            ]
            and bool(source.get("tokens"))
            for source in token_data.get("sources", [])
        )

        name_mode = self._get_name_token_mode(user=user)
        include_name_tokens = name_mode == "always" or (
            name_mode == "fallback" and not has_structured_tokens
        )

        if include_name_tokens:
            for source_name in ["name", "description"]:
                query_tokens.extend(source_tokens(source_name))

        if not query_tokens:
            for token in token_data.get("tokens", []):
                query_tokens.append(str(token))

        structured_source_names = [
            "manufacturer_part",
            "IPN",
            "SKU",
            "parameter",
            "category",
        ]
        named_source_names = ["name", "description"]

        source_token_map = {
            source_name: source_tokens(source_name)
            for source_name in structured_source_names + named_source_names
        }

        return {
            "name_mode": name_mode,
            "has_structured_tokens": has_structured_tokens,
            "include_name_tokens": include_name_tokens,
            "source_token_map": source_token_map,
            "query_tokens": query_tokens,
        }

    def _default_part_query(self, part, user=None):
        token_data = self._extract_part_tokens(part, user=user)
        hints = self._extract_search_hints(part, token_data)
        semantic_query = self._build_semantic_query(token_data, hints, user=user)
        if semantic_query:
            return semantic_query

        tokens = token_data.get("tokens", [])
        if tokens:
            return " ".join(tokens[:6])
        return ""

    def _build_initial_search_query(self, part, user=None):
        token_data = self._extract_part_tokens(part, user=user)
        semantic_hints = self._extract_search_hints(part, token_data)
        query = self._build_semantic_query(token_data, semantic_hints, user=user)

        if query == "":
            query = self._default_part_query(part, user=user)

        return query

    def _parse_quantity_value(self, raw_value, kind, default_unit=None):
        text = str(raw_value or "").strip().lower().replace("μ", "u")
        if text == "":
            return None

        target_unit = {
            "voltage": "v",
            "current": "a",
            "power": "w",
        }.get(kind)
        if target_unit is None:
            return None

        scales = {
            "": 1.0,
            "k": 1000.0,
            "m": 0.001,
            "u": 0.000001,
            "n": 0.000000001,
        }

        values = []
        pattern = re.compile(r"([-+]?\d+(?:\.\d+)?)\s*([kmun]?)\s*([vaw])\b")
        for match in pattern.finditer(text):
            unit = match.group(3)
            if unit != target_unit:
                continue

            try:
                parsed_value = float(match.group(1)) * scales.get(match.group(2), 1.0)
            except Exception:
                continue

            values.append(parsed_value)

        if values:
            return max(values)

        # Fallback for plain numeric values where unit is supplied by template.
        if default_unit:
            unit_text = str(default_unit or "").strip().lower().replace("μ", "u")
            unit_match = re.match(r"^([kmun]?)([vaw])$", unit_text)
            number_match = re.match(r"^[-+]?\d+(?:\.\d+)?$", text)
            if unit_match and number_match and unit_match.group(2) == target_unit:
                try:
                    return float(text) * scales.get(unit_match.group(1), 1.0)
                except Exception:
                    return None

        return None

    def _extract_numeric_constraints(self, part):
        constraints = {}

        param_sets = []
        if hasattr(part, "parameters"):
            param_sets.append(getattr(part, "parameters"))
        if hasattr(part, "parameters_list"):
            param_sets.append(getattr(part, "parameters_list"))

        for param_set in param_sets:
            try:
                params = param_set.all()
            except Exception:
                continue

            for param in params:
                template = getattr(param, "template", None)
                name = str(
                    getattr(template, "name", "") if template is not None else ""
                )
                unit = str(
                    getattr(template, "units", "") if template is not None else ""
                )
                value = getattr(param, "data", "")

                name_lower = name.lower()
                kind = None
                operator = None

                if "voltage" in name_lower:
                    kind = "voltage"
                    operator = "min"
                elif "current" in name_lower:
                    kind = "current"
                    if any(token in name_lower for token in ["consum", "draw", "load"]):
                        operator = "max"
                    else:
                        operator = "min"

                if kind is None or operator is None:
                    continue

                parsed_value = self._parse_quantity_value(
                    value, kind=kind, default_unit=unit
                )
                if parsed_value is None:
                    continue

                key = (kind, operator)
                existing = constraints.get(key)

                if existing is None:
                    constraints[key] = {
                        "kind": kind,
                        "op": operator,
                        "value": parsed_value,
                        "source": name,
                        "raw_value": str(value),
                        "unit": unit,
                    }
                    continue

                # Keep stricter bounds across multiple parameters.
                if operator == "min" and parsed_value > existing["value"]:
                    constraints[key] = {
                        "kind": kind,
                        "op": operator,
                        "value": parsed_value,
                        "source": name,
                        "raw_value": str(value),
                        "unit": unit,
                    }
                elif operator == "max" and parsed_value < existing["value"]:
                    constraints[key] = {
                        "kind": kind,
                        "op": operator,
                        "value": parsed_value,
                        "source": name,
                        "raw_value": str(value),
                        "unit": unit,
                    }

        return list(constraints.values())

    def _extract_candidate_constraint_value(self, candidate, constraint):
        kind = constraint.get("kind")
        if kind not in ["voltage", "current", "power"]:
            return None

        fields = []
        spec_attributes = candidate.get("spec_attributes") or {}
        if isinstance(spec_attributes, dict):
            if kind == "voltage":
                fields.extend([
                    value
                    for name, value in spec_attributes.items()
                    if "voltage" in str(name).lower()
                ])
            elif kind == "current":
                fields.extend([
                    value
                    for name, value in spec_attributes.items()
                    if "current" in str(name).lower()
                ])
            elif kind == "power":
                fields.extend([
                    value
                    for name, value in spec_attributes.items()
                    if "power" in str(name).lower()
                ])

        fields.append(candidate.get("description") or "")

        values = []
        for field in fields:
            parsed = self._parse_quantity_value(field, kind=kind)
            if parsed is not None:
                values.append(parsed)

        if not values:
            return None

        if constraint.get("op") == "min":
            return max(values)
        return min(values)

    def _rank_candidates(
        self, query, candidates, user=None, top_n=10, constraints=None
    ):
        if not candidates:
            return []

        strategy = self.get_effective_setting(
            "RANKING_STRATEGY", user=user, backup_value="balanced"
        )
        strategy = (strategy or "balanced").lower().strip()
        if strategy not in ["balanced", "availability", "price"]:
            strategy = "balanced"

        prices = []
        for candidate in candidates:
            unit_price = candidate.get("unit_price")
            if unit_price is None:
                breaks = candidate.get("price_breaks") or []
                if breaks:
                    unit_price = self._to_float(breaks[0].get("price"))
            if unit_price is not None:
                prices.append(self._to_float(unit_price, default=0.0))

        min_price = min(prices) if prices else 0.0
        max_price = max(prices) if prices else 0.0
        price_span = (max_price - min_price) if max_price > min_price else 1.0

        ranked = []
        query_text = (query or "").lower().strip()

        for candidate in candidates:
            compare_text = " ".join([
                str(candidate.get("supplier_part_number") or ""),
                str(candidate.get("manufacturer_part_number") or ""),
                str(candidate.get("description") or ""),
                str(candidate.get("manufacturer_name") or ""),
            ]).lower()

            match_score = (
                SequenceMatcher(None, query_text, compare_text).ratio() * 100.0
                if query_text
                else 0.0
            )
            available_quantity = self._to_int_from_string(
                candidate.get("available_quantity"), default=0
            )
            availability_score = min(available_quantity, 10000) / 10000.0 * 100.0

            unit_price = candidate.get("unit_price")
            if unit_price is None:
                breaks = candidate.get("price_breaks") or []
                if breaks:
                    unit_price = self._to_float(breaks[0].get("price"))
            unit_price = self._to_float(unit_price, default=0.0)

            if prices:
                price_score = (max_price - unit_price) / price_span * 100.0
            else:
                price_score = 0.0

            if strategy == "price":
                final_score = (
                    0.35 * match_score + 0.15 * availability_score + 0.50 * price_score
                )
            elif strategy == "availability":
                final_score = (
                    0.35 * match_score + 0.50 * availability_score + 0.15 * price_score
                )
            else:
                final_score = (
                    0.45 * match_score + 0.35 * availability_score + 0.20 * price_score
                )

            constraint_matches = 0
            constraint_violations = 0
            constraint_unknown = 0

            for constraint in constraints or []:
                candidate_value = self._extract_candidate_constraint_value(
                    candidate, constraint
                )
                if candidate_value is None:
                    constraint_unknown += 1
                    continue

                required = float(constraint.get("value", 0.0))
                op = constraint.get("op")
                if op == "min":
                    if candidate_value >= required:
                        constraint_matches += 1
                    else:
                        constraint_violations += 1
                elif op == "max":
                    if candidate_value <= required:
                        constraint_matches += 1
                    else:
                        constraint_violations += 1

            # Penalize likely violations while still allowing manual review.
            final_score -= constraint_violations * 20.0

            reasons = [
                f"match={round(match_score, 1)}",
                f"availability={available_quantity}",
            ]
            if unit_price > 0:
                reasons.append(f"price={unit_price}")
            if constraints:
                reasons.append(f"constraint_matches={constraint_matches}")
                reasons.append(f"constraint_violations={constraint_violations}")
                reasons.append(f"constraint_unknown={constraint_unknown}")

            enriched = dict(candidate)
            enriched["available_quantity"] = available_quantity
            enriched["unit_price"] = unit_price
            enriched["score"] = round(final_score, 2)
            enriched["reasons"] = reasons
            enriched["constraint_matches"] = constraint_matches
            enriched["constraint_violations"] = constraint_violations
            enriched["constraint_unknown"] = constraint_unknown
            ranked.append(enriched)

        ranked.sort(
            key=lambda c: (
                -self._to_float(c.get("score")),
                -self._to_int_from_string(c.get("available_quantity")),
                self._to_float(c.get("unit_price"), default=10**9),
            )
        )

        return ranked[: max(int(top_n), 1)]

    def _resolve_candidate_manufacturer_part(self, part, candidate, adapter):
        mpn = adapter.get_candidate_manufacturer_part_number(candidate)
        manufacturer_name = adapter.get_candidate_manufacturer_name(candidate)

        if mpn == "":
            return ManufacturerPart.objects.filter(part=part).first()

        manufacturer = None
        if manufacturer_name:
            manufacturer = Company.objects.filter(
                name__iexact=manufacturer_name
            ).first()
            if manufacturer is None:
                manufacturer = Company.objects.create(
                    name=manufacturer_name,
                    is_manufacturer=True,
                    is_supplier=False,
                )
            elif not manufacturer.is_manufacturer:
                manufacturer.is_manufacturer = True
                manufacturer.save(update_fields=["is_manufacturer"])

        manufacturer_part = None
        if manufacturer is not None:
            manufacturer_part = ManufacturerPart.objects.filter(
                part=part,
                manufacturer=manufacturer,
                MPN__iexact=mpn,
            ).first()

        if manufacturer_part is None:
            manufacturer_part = ManufacturerPart.objects.filter(
                part=part, MPN__iexact=mpn
            ).first()

        if manufacturer_part is None:
            manufacturer_part = ManufacturerPart.objects.create(
                part=part,
                manufacturer=manufacturer,
                MPN=mpn,
                description=str(candidate.get("description") or ""),
                link=adapter.get_candidate_datasheet_url(candidate)
                or str(candidate.get("supplier_link") or ""),
            )

        return manufacturer_part

    def _upsert_supplier_part_candidate(self, part, supplier, candidate):
        registration = self._get_supplier_registration(
            getattr(supplier, "pk", supplier)
        )
        adapter = self._get_supplier_definition(
            registration.get("key") if registration else ""
        )
        if adapter is None:
            return {"status": "error", "message": "Unknown supplier adapter"}

        candidate = adapter.normalize_candidate(candidate)

        sku = adapter.get_candidate_supplier_part_number(candidate)
        if not sku:
            return {
                "status": "error",
                "message": "Candidate supplier part number missing",
            }

        manufacturer_part = self._resolve_candidate_manufacturer_part(
            part=part, candidate=candidate, adapter=adapter
        )
        if manufacturer_part is None:
            return {
                "status": "error",
                "message": "Could not resolve manufacturer part (candidate missing manufacturer part number and part has no manufacturer parts)",
            }

        supplier_part = SupplierPart.objects.filter(
            part=part,
            supplier=supplier,
            SKU__iexact=sku,
        ).first()

        update_data = adapter.build_supplier_part_update_data(candidate)

        if supplier_part is None:
            supplier_part = SupplierPart.objects.create(
                part=part,
                supplier=supplier,
                manufacturer_part=manufacturer_part,
                SKU=sku,
                **update_data,
            )
            created = True
        else:
            for key, value in update_data.items():
                setattr(supplier_part, key, value)
            supplier_part.save()
            created = False

        SupplierPriceBreak.objects.filter(part=supplier_part).delete()
        for pb in candidate.get("price_breaks", []):
            quantity = self._to_int_from_string(pb.get("quantity"), default=0)
            if quantity <= 0:
                continue

            price = self._to_float(pb.get("price"), default=0.0)
            currency = pb.get("currency") or InvenTreeSetting.get_setting(
                "INVENTREE_DEFAULT_CURRENCY"
            )
            SupplierPriceBreak.objects.create(
                part=supplier_part,
                quantity=quantity,
                price=price,
                price_currency=currency,
            )

        datasheet = adapter.get_candidate_datasheet_url(candidate)
        if datasheet and hasattr(part, "link"):
            part.link = datasheet
            part.save(update_fields=["link"])

        return {
            "status": "created" if created else "updated",
            "supplier_part_pk": supplier_part.pk,
            "sku": supplier_part.SKU,
        }

    def _decode_json_body(self, request):
        try:
            return json.loads(request.body or "{}")
        except Exception:
            return {}

    def _get_supplier_definition(self, supplier_key):
        adapter_class = self.SUPPLIER_ADAPTERS.get(
            str(supplier_key or "").strip().lower()
        )
        if adapter_class is None:
            return None
        return adapter_class(self)

    def _get_supplier_registration(self, supplier_pk):
        try:
            supplier_pk = int(supplier_pk)
        except Exception:
            return None

        for registration in self._get_registered_suppliers():
            if supplier_pk == registration["pk"]:
                return registration

        return None

    def _get_registered_suppliers(self):
        suppliers = []

        for supplier_key in self.SUPPLIER_ADAPTERS:
            adapter = self._get_supplier_definition(supplier_key)
            if adapter is None:
                continue

            registration = adapter.get_registered_supplier()
            if registration is not None:
                suppliers.append(registration)

        return suppliers

    def _get_search_ready_suppliers(self, user=None):
        """Return registered suppliers with valid search credentials."""
        ready = []

        for registration in self._get_registered_suppliers():
            adapter = self._get_supplier_definition(registration.get("key"))
            if adapter is None:
                continue

            if adapter.has_search_credentials(user=user):
                ready.append(registration)

        return ready

    def _get_supplier_max_candidates(self, supplier_pk, default=40):
        registration = self._get_supplier_registration(supplier_pk)
        if registration is None:
            return default

        adapter = self._get_supplier_definition(registration.get("key"))
        if adapter is None:
            return default

        return adapter.get_max_candidates(default=default)

    def _supplier_metric_key(self, supplier_key, suffix):
        key = re.sub(r"[^A-Za-z0-9]+", "_", str(supplier_key or "").upper()).strip(
            "_"
        )
        return f"{key}_{suffix}"

    def _supplier_metric_int(self, supplier_key, suffix, default=0):
        key = self._supplier_metric_key(supplier_key, suffix)
        return self._to_int_from_string(self.get_setting(key, backup_value=default), default=default)

    def _increment_supplier_metric(self, supplier_key, suffix, amount=1):
        amount = int(amount or 0)
        key = self._supplier_metric_key(supplier_key, suffix)
        current = self._supplier_metric_int(supplier_key, suffix, default=0)
        self.set_setting(key, current + amount)

    def _record_supplier_query_metrics(self, supplier_key, response):
        self._increment_supplier_metric(supplier_key, "QUERY_TOTAL", amount=1)
        self.set_setting(self._supplier_metric_key(supplier_key, "QUERY_LAST_TS"), int(time.time()))

        status = str((response or {}).get("error_status") or "").strip().upper()
        candidates = len((response or {}).get("candidates", []) or [])

        if status == "OK":
            self._increment_supplier_metric(supplier_key, "QUERY_OK", amount=1)
            self._increment_supplier_metric(
                supplier_key,
                "QUERY_CANDIDATE_TOTAL",
                amount=max(0, int(candidates)),
            )
        else:
            self._increment_supplier_metric(supplier_key, "QUERY_ERROR", amount=1)

    def _get_supplier_query_metrics(self, supplier_key):
        return {
            "total_queries": self._supplier_metric_int(supplier_key, "QUERY_TOTAL", default=0),
            "ok_queries": self._supplier_metric_int(supplier_key, "QUERY_OK", default=0),
            "error_queries": self._supplier_metric_int(supplier_key, "QUERY_ERROR", default=0),
            "total_candidates_returned": self._supplier_metric_int(
                supplier_key, "QUERY_CANDIDATE_TOTAL", default=0
            ),
            "last_query_ts": self._supplier_metric_int(supplier_key, "QUERY_LAST_TS", default=0),
        }

    def _get_dashboard_metrics_payload(self):
        suppliers = []

        for registration in self._get_registered_suppliers():
            supplier_key = registration.get("key")
            adapter = self._get_supplier_definition(supplier_key)
            if adapter is None:
                continue

            suppliers.append({
                "supplier_pk": int(registration.get("pk") or 0),
                "supplier_key": supplier_key,
                "supplier_name": registration.get("name") or supplier_key,
                "configured": adapter.has_search_credentials(user=None),
                "query_metrics": self._get_supplier_query_metrics(supplier_key),
                "api_usage": adapter.get_api_usage_status(),
                "cache_status": adapter.get_cache_status(),
            })

        return {
            "message": "OK",
            "suppliers": suppliers,
            "updated_ts": int(time.time()),
        }

    def _get_resync_last_attempt_setting_key(self, supplier_key):
        key = re.sub(r"[^A-Za-z0-9]+", "_", str(supplier_key or "").upper()).strip(
            "_"
        )
        return f"{key}_RESYNC_LAST_ATTEMPT_TS"

    def _get_resync_last_success_setting_key(self, supplier_key):
        key = re.sub(r"[^A-Za-z0-9]+", "_", str(supplier_key or "").upper()).strip(
            "_"
        )
        return f"{key}_RESYNC_LAST_SUCCESS_TS"

    def _get_resync_cursor_setting_key(self, supplier_key):
        key = re.sub(r"[^A-Za-z0-9]+", "_", str(supplier_key or "").upper()).strip(
            "_"
        )
        return f"{key}_RESYNC_CURSOR_PK"

    def _get_resync_last_success_timestamp(self, supplier_key):
        key = self._get_resync_last_success_setting_key(supplier_key)
        return self._to_int_from_string(self.get_setting(key, backup_value=0), default=0)

    def _set_resync_attempt_timestamp(self, supplier_key, ts):
        self.set_setting(self._get_resync_last_attempt_setting_key(supplier_key), int(ts))

    def _set_resync_success_timestamp(self, supplier_key, ts):
        self.set_setting(self._get_resync_last_success_setting_key(supplier_key), int(ts))

    def _get_resync_cursor_pk(self, supplier_key):
        key = self._get_resync_cursor_setting_key(supplier_key)
        return self._to_int_from_string(self.get_setting(key, backup_value=0), default=0)

    def _set_resync_cursor_pk(self, supplier_key, pk):
        self.set_setting(self._get_resync_cursor_setting_key(supplier_key), int(pk or 0))

    def _is_supplier_resync_due(self, adapter, now_ts):
        interval_seconds = max(1, adapter.get_resync_interval_minutes(default=1440)) * 60
        last_success = self._get_resync_last_success_timestamp(adapter.key)

        if last_success <= 0:
            return True

        return (int(now_ts) - int(last_success)) >= interval_seconds

    def _select_resync_candidate(self, adapter, supplier_part, candidates):
        sku_target = str(getattr(supplier_part, "SKU", "") or "").strip().lower()
        mpn_target = ""
        manufacturer_part = getattr(supplier_part, "manufacturer_part", None)
        if manufacturer_part is not None:
            mpn_target = str(getattr(manufacturer_part, "MPN", "") or "").strip().lower()

        normalized = [adapter.normalize_candidate(candidate) for candidate in (candidates or [])]

        if sku_target:
            for candidate in normalized:
                if (
                    adapter.get_candidate_supplier_part_number(candidate).strip().lower()
                    == sku_target
                ):
                    return candidate

        if mpn_target:
            for candidate in normalized:
                if (
                    adapter.get_candidate_manufacturer_part_number(candidate)
                    .strip()
                    .lower()
                    == mpn_target
                ):
                    return candidate

        return None

    def _select_resync_supplier_parts(
        self,
        registration,
        adapter,
        *,
        part_pk=None,
        use_round_robin=True,
    ):
        supplier_pk = int(registration.get("pk") or 0)
        supplier = Company.objects.filter(pk=supplier_pk).first()
        if supplier is None:
            return supplier, []

        batch_size = adapter.get_resync_batch_size(default=100)

        queryset = (
            SupplierPart.objects.filter(supplier_id=supplier_pk)
            .select_related("part", "manufacturer_part")
            .order_by("pk")
        )

        if part_pk is not None:
            queryset = queryset.filter(part_id=int(part_pk))

        if part_pk is not None or not use_round_robin:
            return supplier, list(queryset[:batch_size])

        cursor = self._get_resync_cursor_pk(adapter.key)
        supplier_parts = list(queryset.filter(pk__gt=cursor)[:batch_size])

        if not supplier_parts and cursor > 0:
            supplier_parts = list(queryset[:batch_size])

        return supplier, supplier_parts

    def _resync_registered_supplier(
        self,
        registration,
        adapter,
        *,
        part_pk=None,
        use_round_robin=True,
    ):
        supplier_pk = int(registration.get("pk") or 0)
        supplier, supplier_parts = self._select_resync_supplier_parts(
            registration,
            adapter,
            part_pk=part_pk,
            use_round_robin=use_round_robin,
        )

        if supplier is None:
            return {
                "status": "error",
                "updated": 0,
                "created": 0,
                "failed": 1,
                "skipped": 0,
                "processed": 0,
                "message": "Supplier company not found",
            }

        max_candidates = adapter.get_max_candidates(default=10)

        first_pk = supplier_parts[0].pk if supplier_parts else None
        last_pk = supplier_parts[-1].pk if supplier_parts else None

        summary = {
            "status": "ok",
            "updated": 0,
            "created": 0,
            "failed": 0,
            "skipped": 0,
            "processed": len(supplier_parts),
            "first_supplier_part_pk": first_pk,
            "last_supplier_part_pk": last_pk,
            "round_robin": bool(part_pk is None and use_round_robin),
        }

        for supplier_part in supplier_parts:
            part = getattr(supplier_part, "part", None)
            if part is None:
                summary["skipped"] += 1
                continue

            query = str(getattr(supplier_part, "SKU", "") or "").strip()
            if query == "":
                manufacturer_part = getattr(supplier_part, "manufacturer_part", None)
                query = str(getattr(manufacturer_part, "MPN", "") or "").strip()

            if query == "":
                summary["skipped"] += 1
                continue

            try:
                response = adapter.get_candidates(
                    query,
                    max_results=max_candidates,
                    user=None,
                )
            except Exception:
                summary["failed"] += 1
                continue

            if response.get("error_status") != "OK":
                summary["failed"] += 1
                continue

            selected = self._select_resync_candidate(
                adapter,
                supplier_part,
                response.get("candidates", []),
            )

            if selected is None:
                summary["skipped"] += 1
                continue

            selected["_supplier_key"] = registration.get("key")
            selected["_supplier_pk"] = supplier_pk

            upsert_result = self._upsert_supplier_part_candidate(part, supplier, selected)
            status = str(upsert_result.get("status") or "").lower()
            if status == "updated":
                summary["updated"] += 1
            elif status == "created":
                summary["created"] += 1
            else:
                summary["failed"] += 1

        if part_pk is None and use_round_robin:
            if supplier_parts:
                self._set_resync_cursor_pk(adapter.key, supplier_parts[-1].pk)
            elif self._get_resync_cursor_pk(adapter.key) > 0:
                self._set_resync_cursor_pk(adapter.key, 0)

        return summary

    def scheduled_supplier_resync(self):
        now_ts = self._to_int_from_string(time.time(), default=0)
        registrations = self._get_registered_suppliers()

        for registration in registrations:
            supplier_key = registration.get("key")
            adapter = self._get_supplier_definition(supplier_key)
            if adapter is None:
                continue

            if not adapter.get_resync_enabled():
                continue

            if not adapter.has_search_credentials(user=None):
                continue

            if not self._is_supplier_resync_due(adapter, now_ts):
                continue

            self._set_resync_attempt_timestamp(supplier_key, now_ts)

            try:
                result = self._resync_registered_supplier(registration, adapter)
            except Exception as exc:
                logger.warning(
                    "Supplier scheduled resync failed for %s: %s",
                    supplier_key,
                    exc,
                )
                continue

            if result.get("failed", 0) == 0:
                self._set_resync_success_timestamp(supplier_key, now_ts)

            logger.info(
                "Supplier resync for %s processed=%s updated=%s created=%s failed=%s skipped=%s",
                supplier_key,
                result.get("processed", 0),
                result.get("updated", 0),
                result.get("created", 0),
                result.get("failed", 0),
                result.get("skipped", 0),
            )

    def get_candidates(
        self, supplier, query, max_results=25, user=None, min_qty=None, max_qty=None
    ):
        registration = self._get_supplier_registration(supplier)
        if registration is not None:
            adapter = self._get_supplier_definition(registration.get("key"))
            if adapter is not None:
                response = adapter.get_candidates(
                    query,
                    max_results=max_results,
                    user=user,
                    min_qty=min_qty,
                    max_qty=max_qty,
                )
                self._record_supplier_query_metrics(registration.get("key"), response)
                return response

        return {
            "error_status": _("Unknown supplier for candidate search"),
            "candidates": [],
        }

    def setup_urls(self):
        return [
            re_path(
                r"searchcandidates(?:\.(?P<format>json))?$",
                self.search_candidates,
                name="search-candidates",
            ),
            re_path(
                r"applycandidates(?:\.(?P<format>json))?$",
                self.apply_candidates,
                name="apply-candidates",
            ),
            re_path(
                r"runresync(?:\.(?P<format>json))?$",
                self.run_resync,
                name="run-resync",
            ),
            re_path(
                r"ratelimitstatus(?:\.(?P<format>json))?$",
                self.rate_limit_status,
                name="rate-limit-status",
            ),
            re_path(
                r"dashboardmetrics(?:\.(?P<format>json))?$",
                self.dashboard_metrics,
                name="dashboard-metrics",
            ),
            re_path(
                r"tokendebug(?:\.(?P<format>json))?$",
                self.token_debug,
                name="token-debug",
            ),
        ]

    def _get_rate_limit_status_payload(self, supplier_pk=None):
        suppliers = []

        for registration in self._get_registered_suppliers():
            try:
                registration_pk = int(registration.get("pk") or 0)
            except Exception:
                registration_pk = 0

            if supplier_pk is not None and registration_pk != int(supplier_pk):
                continue

            adapter = self._get_supplier_definition(registration.get("key"))
            if adapter is None:
                continue

            usage = adapter.get_api_usage_status()
            usage["supplier_pk"] = registration_pk
            usage["configured"] = adapter.has_search_credentials(user=None)
            suppliers.append(usage)

        return {
            "message": "OK",
            "suppliers": suppliers,
            "updated_ts": int(time.time()),
        }

    def rate_limit_status(self, request):
        supplier_pk = None

        if request.method.upper() == "GET":
            raw_supplier = (request.GET or {}).get("supplier")
        else:
            raw_supplier = self._decode_json_body(request).get("supplier")

        try:
            if raw_supplier not in [None, ""]:
                supplier_pk = int(raw_supplier)
        except Exception:
            return JsonResponse({"message": "Invalid supplier id"}, status=400)

        return JsonResponse(self._get_rate_limit_status_payload(supplier_pk=supplier_pk))

    def run_resync(self, request):
        data = self._decode_json_body(request)

        try:
            supplier_pk = int(data.get("supplier"))
        except Exception:
            return JsonResponse({"message": "Invalid supplier id"}, status=400)

        part_pk = None
        try:
            if data.get("part_pk") not in [None, ""]:
                part_pk = int(data.get("part_pk"))
        except Exception:
            return JsonResponse({"message": "Invalid part id"}, status=400)

        action = str(data.get("action") or "").strip().lower()

        registration = self._get_supplier_registration(supplier_pk)
        if registration is None:
            return JsonResponse({"message": "Unknown supplier"}, status=404)

        adapter = self._get_supplier_definition(registration.get("key"))
        if adapter is None:
            return JsonResponse({"message": "Unknown supplier adapter"}, status=404)

        if not adapter.has_search_credentials(user=request.user):
            return JsonResponse(
                {"message": "Supplier credentials are not configured"},
                status=400,
            )

        cursor_before = self._get_resync_cursor_pk(adapter.key)

        if action == "reset_cursor":
            user = getattr(request, "user", None)
            is_admin = bool(
                getattr(user, "is_superuser", False)
                or getattr(user, "is_staff", False)
            )

            if not is_admin:
                return JsonResponse(
                    {"message": "Admin permission required for cursor reset"},
                    status=403,
                )

            self._set_resync_cursor_pk(adapter.key, 0)

            return JsonResponse({
                "message": "OK",
                "scope": "supplier",
                "action": "reset_cursor",
                "supplier_pk": supplier_pk,
                "cursor_before": cursor_before,
                "cursor_after": 0,
            })

        now_ts = self._to_int_from_string(time.time(), default=0)
        self._set_resync_attempt_timestamp(adapter.key, now_ts)

        try:
            result = self._resync_registered_supplier(
                registration,
                adapter,
                part_pk=part_pk,
                use_round_robin=part_pk is None,
            )
        except Exception as exc:
            return JsonResponse(
                {"message": f"Resync failed: {exc}"},
                status=500,
            )

        if result.get("failed", 0) == 0:
            self._set_resync_success_timestamp(adapter.key, now_ts)

        cursor_after = self._get_resync_cursor_pk(adapter.key)

        scope = "part" if part_pk is not None else "supplier"
        result["message"] = "OK"
        result["scope"] = scope
        result["supplier_pk"] = supplier_pk
        result["action"] = "resync"
        result["cursor_before"] = cursor_before
        result["cursor_after"] = cursor_after
        if part_pk is not None:
            result["part_pk"] = part_pk

        return JsonResponse(result)

    def dashboard_metrics(self, request):
        del request
        return JsonResponse(self._get_dashboard_metrics_payload())

    def token_debug(self, request):
        """Return token attribution debug data for a part.

        Accepts part PK via query string (?pk=123) or JSON body {"pk": 123}.
        """
        try:
            data = {}

            if request.method.upper() == "GET":
                data = request.GET or {}
            else:
                data = self._decode_json_body(request)

            try:
                part_pk = int(data.get("pk"))
            except Exception:
                return JsonResponse({"message": "Invalid part id"}, status=400)

            part = Part.objects.filter(id=part_pk).first()
            if not part:
                return JsonResponse({"message": "Part not found"}, status=404)

            token_data = self._extract_part_tokens(part, user=request.user)
            semantic_hints = self._extract_search_hints(part, token_data)
            query_plan = self._build_query_plan(
                token_data, semantic_hints, user=request.user
            )
            query = self._build_initial_search_query(part, user=request.user)

            payload = {
                "message": "OK",
                "part_pk": part.pk,
                "query": query,
                "debug": {
                    "tokens": token_data.get("tokens", []),
                    "token_sources": token_data.get("sources", []),
                    "token_attribution": token_data.get("token_attribution", {}),
                    "semantic_hints": semantic_hints,
                    "query_debug": {
                        "name_mode": query_plan.get("name_mode"),
                        "has_structured_tokens": query_plan.get(
                            "has_structured_tokens", False
                        ),
                        "include_name_tokens": query_plan.get(
                            "include_name_tokens", False
                        ),
                        "source_token_map": query_plan.get("source_token_map", {}),
                        "final_query_tokens": query_plan.get("query_tokens", []),
                    },
                },
            }

            if getattr(settings, "DEBUG", False):
                logger.debug(
                    "SupplierScout token debug for part %s: %s",
                    part.pk,
                    json.dumps(payload.get("debug", {}), ensure_ascii=True),
                )

            return JsonResponse(payload)
        except Exception as e:
            import traceback

            return JsonResponse(
                {
                    "message": f"Exception during token debug: {str(e)}",
                    "debug": {
                        "error_type": type(e).__name__,
                        "error_traceback": traceback.format_exc(),
                    },
                },
                status=500,
            )

    def get_ui_panels(self, request, context, **kwargs):
        return []

    def get_ui_dashboard_items(self, request, context, **kwargs):
        del context, kwargs

        suppliers = self._get_registered_suppliers()
        if not suppliers:
            return []

        return [
            {
                "key": "supplierscout-dashboard-metrics",
                "title": "Supplier Scout Metrics",
                "description": _("Supplier query, cache, and API usage diagnostics"),
                "source": self.plugin_static_file(
                    "Dashboard.js:renderSupplierScoutDashboardItem"
                ),
                "context": {
                    "metrics_url": f"/{self.base_url}dashboardmetrics",
                },
                "options": {
                    "width": 6,
                    "height": 3,
                },
            }
        ]

    def get_ui_primary_actions(self, request, context, **kwargs):
        actions = []
        context = context or {}

        part_pk = None
        if context.get("target_model") == "part" and context.get("target_id"):
            try:
                part_pk = int(context.get("target_id"))
            except Exception:
                part_pk = None

        if part_pk is None:
            location = str(context.get("location") or "").strip()
            match = re.search(r"/part/(\d+)(?:/|$)", location)
            if match:
                try:
                    part_pk = int(match.group(1))
                except Exception:
                    part_pk = None

        if part_pk is None:
            return actions

        part = Part.objects.filter(pk=part_pk).first()
        if part is None or not part.purchaseable:
            return actions

        has_permission = (
            check_user_role(request.user, "part", "change")
            or check_user_role(request.user, "part", "delete")
            or check_user_role(request.user, "part", "add")
        )
        if not has_permission:
            return actions

        suppliers = self._get_search_ready_suppliers(user=request.user)
        action_enabled = len(suppliers) > 0

        actions.append({
            "key": "supplierscout-part-match-action",
            "title": "Supplier Match",
            "icon": "ti:search",
            "source": self.plugin_static_file("Panel.js:getFeature?v=20260529a"),
            "context": {
                "title": "Supplier Part Matching",
                "search_url": f"/{self.base_url}searchcandidates",
                "apply_url": f"/{self.base_url}applycandidates",
                "run_resync_url": f"/{self.base_url}runresync",
                "rate_status_url": f"/{self.base_url}ratelimitstatus",
                "default_query": self._build_initial_search_query(
                    part, user=request.user
                ),
                "part_pk": part.pk,
                "show_score": bool(getattr(settings, "DEBUG", False)),
                "top_n": int(
                    self.get_effective_setting(
                        "TOP_N_CANDIDATES", user=request.user, backup_value=10
                    )
                    or 10
                ),
                "suppliers": suppliers,
            },
            "options": {
                "color": "blue" if action_enabled else "gray",
                "disabled": not action_enabled,
                "tooltip": "Configure at least one supplier API key in plugin settings"
                if not action_enabled
                else "",
            },
        })

        return actions

    def search_candidates(self, request):
        try:
            data = self._decode_json_body(request)

            try:
                part_pk = int(data.get("pk"))
            except Exception:
                return JsonResponse({"message": "Invalid part id"})

            part = Part.objects.filter(id=part_pk).first()
            if not part:
                return JsonResponse({"message": "Part not found"})

            try:
                supplier_pk = int(data.get("supplier"))
            except Exception:
                return JsonResponse({"message": "Invalid supplier id"})

            try:
                top_n = int(
                    data.get("top_n")
                    or self.get_effective_setting(
                        "TOP_N_CANDIDATES", user=request.user, backup_value=10
                    )
                    or 10
                )
            except Exception:
                top_n = 10

            max_candidates = self._get_supplier_max_candidates(supplier_pk, default=40)

            # Extract optional min/max quantity overrides from request
            try:
                min_qty = int(data.get("min_qty")) if data.get("min_qty") else None
            except (ValueError, TypeError):
                min_qty = None

            try:
                max_qty = int(data.get("max_qty")) if data.get("max_qty") else None
            except (ValueError, TypeError):
                max_qty = None

            query = str(data.get("query") or "").strip()
            token_data = self._extract_part_tokens(part, user=request.user)
            semantic_hints = self._extract_search_hints(part, token_data)
            numeric_constraints = self._extract_numeric_constraints(part)

            if getattr(settings, "DEBUG", False):
                logger.debug(
                    "SupplierScout token attribution for part %s: %s",
                    part.pk,
                    json.dumps(
                        token_data.get("token_attribution", {}), ensure_ascii=True
                    ),
                )

            if query == "":
                query = self._build_initial_search_query(part, user=request.user)

            if query == "":
                return JsonResponse({
                    "message": "Could not derive a search query from this part",
                    "debug": {
                        "tokens": token_data.get("tokens", []),
                        "token_sources": token_data.get("sources", []),
                        "token_attribution": token_data.get("token_attribution", {}),
                        "semantic_hints": semantic_hints,
                        "numeric_constraints": numeric_constraints,
                    },
                })

            response = self.get_candidates(
                supplier=supplier_pk,
                query=query,
                max_results=max_candidates,
                user=request.user,
                min_qty=min_qty,
                max_qty=max_qty,
            )

            registration = self._get_supplier_registration(supplier_pk)
            adapter = self._get_supplier_definition(
                registration.get("key") if registration else ""
            )
            if adapter is None:
                return JsonResponse({"message": "Unknown supplier adapter"})

            if response.get("error_status") != "OK":
                return JsonResponse({
                    "message": response.get("error_status", "Candidate search failed"),
                    "debug": {
                        "tokens": token_data.get("tokens", []),
                        "token_sources": token_data.get("sources", []),
                        "token_attribution": token_data.get("token_attribution", {}),
                        "semantic_hints": semantic_hints,
                        "numeric_constraints": numeric_constraints,
                        "query": query,
                        "supplier_response": response.get("debug", {}),
                    },
                })

            ranked = self._rank_candidates(
                query=query,
                candidates=[
                    adapter.normalize_candidate(candidate)
                    for candidate in response.get("candidates", [])
                ],
                user=request.user,
                top_n=top_n,
                constraints=numeric_constraints,
            )

            existing_supplier_parts = SupplierPart.objects.filter(
                part=part, supplier_id=supplier_pk
            ).only("pk", "SKU")
            existing_by_sku = {}

            for supplier_part in existing_supplier_parts:
                sku_key = str(getattr(supplier_part, "SKU", "") or "").strip().lower()
                if sku_key:
                    existing_by_sku[sku_key] = supplier_part.pk

            for candidate in ranked:
                sku = adapter.get_candidate_supplier_part_number(candidate)
                existing_pk = existing_by_sku.get(sku.lower())
                candidate["existing_supplier_part"] = existing_pk is not None
                candidate["existing_supplier_part_pk"] = existing_pk
                candidate["action"] = "update" if existing_pk is not None else "create"

            message = (
                "OK"
                if len(ranked) > 0
                else "No supplier matches returned for the current query"
            )

            return JsonResponse({
                "message": message,
                "query": query,
                "candidates": ranked,
                "count": len(ranked),
                "debug": {
                    "tokens": token_data.get("tokens", []),
                    "token_sources": token_data.get("sources", []),
                    "token_attribution": token_data.get("token_attribution", {}),
                    "semantic_hints": semantic_hints,
                    "numeric_constraints": numeric_constraints,
                    "query": query,
                },
            })
        except Exception as e:
            import traceback

            error_details = traceback.format_exc()
            return JsonResponse(
                {
                    "message": f"Exception during candidate search: {str(e)}",
                    "debug": {
                        "error_type": type(e).__name__,
                        "error_traceback": error_details,
                    },
                },
                status=500,
            )

    def apply_candidates(self, request):
        try:
            data = self._decode_json_body(request)

            try:
                part_pk = int(data.get("pk"))
            except Exception:
                return JsonResponse({"message": "Invalid part id"})

            part = Part.objects.filter(id=part_pk).first()
            if not part:
                return JsonResponse({"message": "Part not found"})

            try:
                supplier_pk = int(data.get("supplier"))
            except Exception:
                return JsonResponse({"message": "Invalid supplier id"})

            supplier = Company.objects.filter(id=supplier_pk).first()
            if not supplier:
                return JsonResponse({"message": "Supplier not found"})

            candidates = data.get("candidates") or []
            if not isinstance(candidates, list) or len(candidates) == 0:
                return JsonResponse({"message": "No candidates selected"})

            results = []
            created = 0
            updated = 0
            errors = 0

            for candidate in candidates:
                if not isinstance(candidate, dict):
                    errors += 1
                    results.append({
                        "status": "error",
                        "message": "Invalid candidate payload",
                    })
                    continue

                try:
                    result = self._upsert_supplier_part_candidate(
                        part=part,
                        supplier=supplier,
                        candidate=candidate,
                    )
                except Exception as exc:
                    errors += 1
                    results.append({"status": "error", "message": str(exc)})
                    continue

                if result.get("status") == "created":
                    created += 1
                elif result.get("status") == "updated":
                    updated += 1
                else:
                    errors += 1

                results.append(result)

            return JsonResponse({
                "message": "OK",
                "created": created,
                "updated": updated,
                "errors": errors,
                "results": results,
            })
        except Exception as e:
            import traceback

            error_details = traceback.format_exc()
            return JsonResponse(
                {
                    "message": f"Exception during candidate apply: {str(e)}",
                    "debug": {
                        "error_type": type(e).__name__,
                        "error_traceback": error_details,
                    },
                },
                status=500,
            )
