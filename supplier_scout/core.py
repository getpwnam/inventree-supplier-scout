"""Supplier Scout plugin core implementation."""

import json
import re
from difflib import SequenceMatcher

from common.models import InvenTreeSetting
from company.models import Company
from company.models import ManufacturerPart
from company.models import SupplierPart
from company.models import SupplierPriceBreak
from django.conf import settings
from django.http import JsonResponse
from django.urls import re_path
from part.models import Part
from plugin import InvenTreePlugin
from plugin.mixins import SettingsMixin
from plugin.mixins import UrlsMixin
from plugin.mixins import UserInterfaceMixin
from users.permissions import check_user_role

from . import PLUGIN_VERSION
from .adapters import build_supplier_settings
from .adapters import build_supplier_user_settings
from .mouser import MouserSupplierAdapter


class SupplierScout(SettingsMixin, UrlsMixin, UserInterfaceMixin, InvenTreePlugin):
    """SupplierScout plugin."""

    TITLE = "Supplier Scout"
    NAME = "SupplierScout"
    SLUG = "supplierscout"
    DESCRIPTION = "Part search, matching and ordering with popular suppliers"
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
        "RANKING_STRATEGY": {
            "name": "Candidate ranking strategy",
            "description": "Default ranking strategy for supplier suggestions",
            "choices": [
                ("balanced", "Balanced score"),
                ("availability", "Availability first"),
                ("price", "Price first"),
            ],
            "default": "balanced",
        },
    }

    USER_SETTINGS = {
        **build_supplier_user_settings(SUPPLIER_ADAPTERS.values()),
        "RANKING_STRATEGY": {
            "name": "Candidate ranking strategy (user override)",
            "description": "User-specific ranking strategy (overrides global value)",
            "choices": [
                ("balanced", "Balanced score"),
                ("availability", "Availability first"),
                ("price", "Price first"),
            ],
            "default": "balanced",
        },
        "TOP_N_CANDIDATES": {
            "name": "Top N candidate results (user override)",
            "description": "Default number of ranked candidates shown",
            "default": 10,
        },
    }

    def get_effective_setting(self, key, user=None, backup_value=None):
        """Return user setting value if available, otherwise fallback to global setting."""
        if user and key in getattr(self, "user_settings", {}):
            user_value = self.get_user_setting(key, user, backup_value=None)
            if user_value not in [None, ""]:
                return user_value
        return self.get_setting(key, backup_value=backup_value)

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

    def _tokenize_text(self, text):
        if not text:
            return []

        chunks = re.split(r"[^A-Za-z0-9%._+-]+", str(text))
        tokens = []

        for chunk in chunks:
            token = chunk.strip()
            if len(token) < 2:
                continue

            tokens.append(token)

            for sub in re.split(r"[_\-/]+", token):
                sub_token = sub.strip()
                if len(sub_token) >= 2:
                    tokens.append(sub_token)

            lower = token.lower()
            if re.match(r"^\d+(\.\d+)?p$", lower):
                numeric = lower[:-1]
                tokens.extend([f"{numeric}pf", f"{numeric}pF"])
            elif re.match(r"^\d+(\.\d+)?n$", lower):
                numeric = lower[:-1]
                tokens.extend([f"{numeric}nf", f"{numeric}nF"])
            elif re.match(r"^\d+(\.\d+)?u$", lower):
                numeric = lower[:-1]
                tokens.extend([f"{numeric}uf", f"{numeric}uF"])
            elif re.match(r"^\d+(\.\d+)?k$", lower):
                numeric = lower[:-1]
                tokens.extend([f"{numeric}kohm", f"{numeric}kOhm"])

            cap_normalized = self._normalize_capacitance_token(token)
            if cap_normalized:
                tokens.append(cap_normalized)

            res_normalized = self._normalize_resistance_token(token)
            if res_normalized:
                tokens.append(res_normalized)

            cap_code = self._decode_eia_cap_code(token)
            if cap_code:
                tokens.append(cap_code)

        return tokens

    def _extract_part_tokens(self, part):
        tokens = []
        sources = []

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
            source_tokens = self._tokenize_text(source_value)
            if source_tokens:
                tokens.extend(source_tokens)
                sources.append({
                    "source": source_name,
                    "value": str(source_value),
                    "tokens": source_tokens,
                })

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
                joined = f"{template_name} {param_data}".strip()
                param_tokens = self._tokenize_text(joined)

                if param_tokens:
                    tokens.extend(param_tokens)
                    sources.append({
                        "source": "parameter",
                        "name": str(template_name),
                        "value": str(param_data),
                        "tokens": param_tokens,
                    })

        deduped = []
        seen = set()
        for token in tokens:
            key = token.lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(token)

        return {
            "tokens": deduped,
            "sources": sources,
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

    def _build_semantic_query(self, token_data, hints):
        query_tokens = []

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

        for source in token_data.get("sources", []):
            if source.get("source") == "manufacturer_part":
                for token in source.get("tokens", []):
                    query_tokens.append(str(token))

        for token in token_data.get("tokens", []):
            query_tokens.append(str(token))

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

    def _default_part_query(self, part):
        token_data = self._extract_part_tokens(part)
        hints = self._extract_search_hints(part, token_data)
        semantic_query = self._build_semantic_query(token_data, hints)
        if semantic_query:
            return semantic_query

        tokens = token_data.get("tokens", [])
        if tokens:
            return " ".join(tokens[:6])
        return ""

    def _rank_candidates(self, query, candidates, user=None, top_n=10):
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

            reasons = [
                f"match={round(match_score, 1)}",
                f"availability={available_quantity}",
            ]
            if unit_price > 0:
                reasons.append(f"price={unit_price}")

            enriched = dict(candidate)
            enriched["available_quantity"] = available_quantity
            enriched["unit_price"] = unit_price
            enriched["score"] = round(final_score, 2)
            enriched["reasons"] = reasons
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

        for supplier in self._get_registered_suppliers():
            if supplier_pk == supplier["pk"]:
                return supplier

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

    def _get_supplier_max_candidates(self, supplier_pk, default=40):
        registration = self._get_supplier_registration(supplier_pk)
        if registration is None:
            return default

        adapter = self._get_supplier_definition(registration.get("key"))
        if adapter is None:
            return default

        return adapter.get_max_candidates(default=default)

    def get_candidates(self, supplier, query, max_results=25, user=None):
        registration = self._get_supplier_registration(supplier)
        if registration is not None:
            adapter = self._get_supplier_definition(registration.get("key"))
            if adapter is not None:
                return adapter.get_candidates(query, max_results=max_results, user=user)

        return {
            "error_status": "Unknown supplier for candidate search",
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
        ]

    def get_ui_panels(self, request, context, **kwargs):
        panels = []
        context = context or {}

        if context.get("target_model") != "part":
            return panels

        target_id = context.get("target_id")
        if target_id is None:
            return panels

        try:
            part = Part.objects.get(pk=target_id)
        except (Part.DoesNotExist, ValueError, TypeError):
            return panels

        has_permission = (
            check_user_role(request.user, "part", "change")
            or check_user_role(request.user, "part", "delete")
            or check_user_role(request.user, "part", "add")
        )
        if not has_permission or not part.purchaseable:
            return panels

        suppliers = self._get_registered_suppliers()
        if not suppliers:
            return panels

        panels.append({
            "key": "supplierscout-part-panel",
            "title": "Supplier Part Matching",
            "icon": "ti:search",
            "source": self.plugin_static_file("Panel.js:renderSupplierScoutPanel"),
            "context": {
                "search_url": f"/{self.base_url}searchcandidates",
                "apply_url": f"/{self.base_url}applycandidates",
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
        })

        return panels

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

        suppliers = self._get_registered_suppliers()
        if not suppliers:
            return actions

        actions.append({
            "key": "supplierscout-part-match-action",
            "title": "Supplier Match",
            "icon": "ti:search",
            "source": self.plugin_static_file("Panel.js:getFeature"),
            "context": {
                "title": "Supplier Part Matching",
                "search_url": f"/{self.base_url}searchcandidates",
                "apply_url": f"/{self.base_url}applycandidates",
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
                "color": "blue",
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

            query = str(data.get("query") or "").strip()
            token_data = self._extract_part_tokens(part)
            semantic_hints = self._extract_search_hints(part, token_data)

            if query == "":
                query = self._build_semantic_query(token_data, semantic_hints)
            if query == "":
                query = self._default_part_query(part)

            if query == "":
                return JsonResponse({
                    "message": "Could not derive a search query from this part",
                    "debug": {
                        "tokens": token_data.get("tokens", []),
                        "token_sources": token_data.get("sources", []),
                        "semantic_hints": semantic_hints,
                    },
                })

            response = self.get_candidates(
                supplier=supplier_pk,
                query=query,
                max_results=max_candidates,
                user=request.user,
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
                        "semantic_hints": semantic_hints,
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
                    "semantic_hints": semantic_hints,
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
