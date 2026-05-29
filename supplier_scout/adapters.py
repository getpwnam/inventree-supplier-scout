from plugin.mixins import APICallMixin


class SupplierAPIClient(APICallMixin):
    """APICallMixin wrapper for supplier-specific HTTP transports."""

    API_URL_SETTING = "_SUPPLIER_API_URL"
    API_TOKEN_SETTING = None

    def __init__(self, plugin, base_url, headers=None):
        self.plugin = plugin
        self._api_url = str(base_url or "").rstrip("/")
        self._api_headers = dict(headers or {})

    @property
    def api_url(self):
        return self._api_url

    @property
    def api_headers(self):
        return dict(self._api_headers)

    def get_setting(self, key, backup_value=None):
        return self.plugin.get_setting(key, backup_value=backup_value)


class BaseSupplierAdapter:
    """Base adapter for supplier settings, registration and lookups."""

    key = ""
    name = ""
    settings = {}
    user_settings = {}
    company_setting = ""
    max_candidates_setting = ""

    def __init__(self, plugin):
        self.plugin = plugin

    def get_setting(self, key, backup_value=None):
        return self.plugin.get_setting(key, backup_value=backup_value)

    def get_effective_setting(self, key, user=None, backup_value=None):
        return self.plugin.get_effective_setting(
            key, user=user, backup_value=backup_value
        )

    def get_registered_supplier(self):
        try:
            supplier_pk = int(self.get_setting(self.company_setting))
        except Exception:
            return None

        if supplier_pk <= 0:
            return None

        return {
            "key": self.key,
            "name": self.name,
            "pk": supplier_pk,
        }

    def get_max_candidates(self, default=40):
        if not self.max_candidates_setting:
            return default

        try:
            return int(
                self.get_setting(self.max_candidates_setting, backup_value=default)
                or default
            )
        except Exception:
            return default

    def get_candidates(self, query, max_results=25, user=None):
        raise NotImplementedError()

    def has_search_credentials(self, user=None):
        """Return whether this supplier is configured for search requests."""
        return True

    def normalize_price_breaks(self, price_breaks):
        normalized = []

        for price_break in price_breaks or []:
            normalized.append({
                "quantity": self.plugin._to_int_from_string(
                    price_break.get("quantity", price_break.get("Quantity")),
                    default=0,
                ),
                "price": self.plugin._to_float(
                    price_break.get("price", price_break.get("Price")),
                    default=0.0,
                ),
                "currency": price_break.get("currency")
                or price_break.get("Currency")
                or "",
            })

        return normalized

    def normalize_candidate(self, candidate):
        normalized = dict(candidate or {})
        normalized["supplier_part_number"] = str(
            normalized.get("supplier_part_number") or normalized.get("SKU") or ""
        ).strip()
        normalized["manufacturer_part_number"] = str(
            normalized.get("manufacturer_part_number") or normalized.get("MPN") or ""
        ).strip()
        normalized["manufacturer_name"] = str(
            normalized.get("manufacturer_name") or normalized.get("manufacturer") or ""
        ).strip()
        normalized["supplier_link"] = str(
            normalized.get("supplier_link") or normalized.get("URL") or ""
        ).strip()
        normalized["datasheet_url"] = str(normalized.get("datasheet_url") or "").strip()
        normalized["image_url"] = str(normalized.get("image_url") or "").strip()
        normalized["lifecycle_status"] = str(
            normalized.get("lifecycle_status") or ""
        ).strip()
        normalized["description"] = str(normalized.get("description") or "").strip()
        normalized["packaging"] = str(
            normalized.get("packaging") or normalized.get("package") or ""
        ).strip()
        normalized["pack_quantity"] = normalized.get("pack_quantity") or 1
        normalized["available_quantity"] = self.plugin._to_int_from_string(
            normalized.get("available_quantity", normalized.get("quantity_available")),
            default=0,
        )
        normalized["price_breaks"] = self.normalize_price_breaks(
            normalized.get("price_breaks") or []
        )

        unit_price = normalized.get("unit_price")
        if unit_price is None and normalized["price_breaks"]:
            unit_price = normalized["price_breaks"][0].get("price")
        normalized["unit_price"] = self.plugin._to_float(unit_price, default=0.0)

        return normalized

    def get_candidate_supplier_part_number(self, candidate):
        return str(candidate.get("supplier_part_number") or "").strip()

    def get_candidate_manufacturer_part_number(self, candidate):
        return str(candidate.get("manufacturer_part_number") or "").strip()

    def get_candidate_manufacturer_name(self, candidate):
        return str(candidate.get("manufacturer_name") or "").strip()

    def get_candidate_datasheet_url(self, candidate):
        return str(candidate.get("datasheet_url") or "").strip()

    def build_supplier_part_update_data(self, candidate):
        return {
            "link": candidate.get("supplier_link") or "",
            "note": candidate.get("lifecycle_status") or "",
            "packaging": candidate.get("packaging") or "",
            "pack_quantity": candidate.get("pack_quantity") or 1,
            "description": candidate.get("description") or "",
        }


def build_supplier_settings(adapter_classes):
    settings = {}
    for adapter_class in adapter_classes:
        settings.update(getattr(adapter_class, "settings", {}) or {})
    return settings


def build_supplier_user_settings(adapter_classes):
    settings = {}
    for adapter_class in adapter_classes:
        settings.update(getattr(adapter_class, "user_settings", {}) or {})
    return settings
