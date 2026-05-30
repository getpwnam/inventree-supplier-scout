from plugin.mixins import APICallMixin
import re
import time
from datetime import datetime
from datetime import timedelta

try:
    from django.utils.translation import gettext_lazy as _  # type: ignore[import-not-found]
except Exception:  # pragma: no cover - fallback for isolated unit tests

    def _(value):
        return value


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
    api_rate_limit_per_second_default = 0
    api_daily_limit_default = 0

    def __init__(self, plugin):
        self.plugin = plugin

    def get_setting(self, key, backup_value=None):
        return self.plugin.get_setting(key, backup_value=backup_value)

    @classmethod
    def get_resync_enabled_setting_key(cls):
        return f"{str(cls.key or '').upper()}_RESYNC_ENABLED"

    @classmethod
    def get_resync_interval_setting_key(cls):
        return f"{str(cls.key or '').upper()}_RESYNC_INTERVAL_MINUTES"

    @classmethod
    def get_resync_batch_size_setting_key(cls):
        return f"{str(cls.key or '').upper()}_RESYNC_BATCH_SIZE"

    @classmethod
    def get_api_rate_limit_setting_key(cls):
        return f"{str(cls.key or '').upper()}_API_RATE_LIMIT_PER_SECOND"

    @classmethod
    def get_api_daily_limit_setting_key(cls):
        return f"{str(cls.key or '').upper()}_API_DAILY_LIMIT"

    def get_effective_setting(self, key, user=None, backup_value=None):
        return self.plugin.get_effective_setting(
            key, user=user, backup_value=backup_value
        )

    def get_resync_enabled(self):
        value = self.get_setting(
            self.get_resync_enabled_setting_key(),
            backup_value=False,
        )
        if isinstance(value, bool):
            return value
        text = str(value or "").strip().lower()
        return text in ["1", "true", "yes", "on", "y"]

    def get_resync_interval_minutes(self, default=1440):
        try:
            interval = int(
                self.get_setting(
                    self.get_resync_interval_setting_key(), backup_value=default
                )
                or default
            )
        except Exception:
            interval = default

        return max(1, interval)

    def get_resync_batch_size(self, default=100):
        try:
            batch_size = int(
                self.get_setting(
                    self.get_resync_batch_size_setting_key(), backup_value=default
                )
                or default
            )
        except Exception:
            batch_size = default

        return max(1, batch_size)

    def get_api_rate_limit_per_second(self):
        default = int(getattr(self, "api_rate_limit_per_second_default", 0) or 0)
        try:
            value = int(
                self.get_setting(
                    self.get_api_rate_limit_setting_key(),
                    backup_value=default,
                )
                or default
            )
        except Exception:
            value = default
        return max(0, value)

    def get_api_daily_limit(self):
        default = int(getattr(self, "api_daily_limit_default", 0) or 0)
        try:
            value = int(
                self.get_setting(
                    self.get_api_daily_limit_setting_key(),
                    backup_value=default,
                )
                or default
            )
        except Exception:
            value = default
        return max(0, value)

    def _runtime_setting_key(self, suffix):
        key_prefix = re.sub(r"[^A-Za-z0-9]+", "_", str(self.key or "").upper()).strip(
            "_"
        )
        return f"{key_prefix}_{suffix}"

    def _set_runtime_setting(self, key, value):
        setter = getattr(self.plugin, "set_setting", None)
        if callable(setter):
            try:
                setter(key, value)
                return
            except Exception:
                pass

        store = getattr(self.plugin, "settings", None)
        if isinstance(store, dict):
            store[key] = value

    def enforce_api_rate_limits(self, cost=1):
        cost = max(1, int(cost or 1))

        rate_limit = self.get_api_rate_limit_per_second()
        now_ts = time.time()

        if rate_limit > 0:
            window_start_key = self._runtime_setting_key("API_SECOND_WINDOW_START")
            window_count_key = self._runtime_setting_key("API_SECOND_WINDOW_COUNT")

            try:
                window_start = float(self.get_setting(window_start_key, backup_value=0) or 0)
            except Exception:
                window_start = 0.0

            try:
                window_count = int(self.get_setting(window_count_key, backup_value=0) or 0)
            except Exception:
                window_count = 0

            elapsed = now_ts - window_start
            if window_start <= 0 or elapsed >= 1.0:
                window_start = now_ts
                window_count = 0

            if window_count + cost > rate_limit:
                sleep_for = max(0.0, 1.0 - elapsed)
                if sleep_for > 0:
                    time.sleep(sleep_for)
                now_ts = time.time()
                window_start = now_ts
                window_count = 0

            window_count += cost
            self._set_runtime_setting(window_start_key, f"{window_start:.6f}")
            self._set_runtime_setting(window_count_key, window_count)

        daily_limit = self.get_api_daily_limit()
        if daily_limit > 0:
            daily_date_key = self._runtime_setting_key("API_DAILY_DATE")
            daily_count_key = self._runtime_setting_key("API_DAILY_COUNT")

            today = datetime.utcnow().date().isoformat()
            saved_date = str(self.get_setting(daily_date_key, backup_value=today) or "")

            try:
                daily_count = int(self.get_setting(daily_count_key, backup_value=0) or 0)
            except Exception:
                daily_count = 0

            if saved_date != today:
                saved_date = today
                daily_count = 0

            if daily_count + cost > daily_limit:
                raise SupplierAPIRateLimitError(
                    _("%(supplier)s daily API limit reached (%(limit)s requests/day)")
                    % {
                        "supplier": str(self.name or self.key or "Supplier"),
                        "limit": daily_limit,
                    }
                )

            daily_count += cost
            self._set_runtime_setting(daily_date_key, saved_date)
            self._set_runtime_setting(daily_count_key, daily_count)

    def get_api_usage_status(self):
        rate_limit = self.get_api_rate_limit_per_second()
        daily_limit = self.get_api_daily_limit()

        daily_date_key = self._runtime_setting_key("API_DAILY_DATE")
        daily_count_key = self._runtime_setting_key("API_DAILY_COUNT")

        today = datetime.utcnow().date().isoformat()
        saved_date = str(self.get_setting(daily_date_key, backup_value=today) or "")

        try:
            daily_count = int(self.get_setting(daily_count_key, backup_value=0) or 0)
        except Exception:
            daily_count = 0

        if saved_date != today:
            daily_count = 0
            saved_date = today

        if daily_limit > 0:
            remaining_daily = max(0, daily_limit - daily_count)
            percent_used = min(100.0, (daily_count / daily_limit) * 100.0)
        else:
            remaining_daily = None
            percent_used = 0.0

        try:
            parsed_date = datetime.strptime(saved_date, "%Y-%m-%d")
            reset_at = (parsed_date + timedelta(days=1)).strftime("%Y-%m-%dT00:00:00Z")
        except Exception:
            reset_at = ""

        return {
            "supplier_key": self.key,
            "supplier_name": self.name,
            "rate_limit_per_second": rate_limit,
            "daily_limit": daily_limit,
            "daily_count": daily_count,
            "daily_remaining": remaining_daily,
            "daily_percent_used": round(percent_used, 2),
            "daily_reset_at": reset_at,
        }

    def get_cache_status(self):
        """Return supplier-specific cache diagnostics for dashboard reporting."""
        return {
            "enabled": False,
            "cache_backend": "none",
        }

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


class SupplierAPIRateLimitError(RuntimeError):
    """Raised when a supplier API daily usage limit is exceeded."""


def build_supplier_settings(adapter_classes):
    settings = {}
    for adapter_class in adapter_classes:
        settings.update(getattr(adapter_class, "settings", {}) or {})
    return settings


def build_supplier_schedule_settings(adapter_classes):
    settings = {}

    for adapter_class in adapter_classes:
        supplier_name = str(getattr(adapter_class, "name", "Supplier") or "Supplier")
        enabled_key = adapter_class.get_resync_enabled_setting_key()
        interval_key = adapter_class.get_resync_interval_setting_key()
        batch_size_key = adapter_class.get_resync_batch_size_setting_key()
        api_rate_limit_key = adapter_class.get_api_rate_limit_setting_key()
        api_daily_limit_key = adapter_class.get_api_daily_limit_setting_key()
        default_rate = int(
            getattr(adapter_class, "api_rate_limit_per_second_default", 0) or 0
        )
        default_daily = int(getattr(adapter_class, "api_daily_limit_default", 0) or 0)

        settings[enabled_key] = {
            "name": _("Enable %(supplier)s scheduled resync")
            % {"supplier": supplier_name},
            "description": _(
                "Enable periodic refresh of supplier part metadata and price breaks for %(supplier)s"
            )
            % {"supplier": supplier_name},
            "validator": bool,
            "default": False,
        }
        settings[interval_key] = {
            "name": _("%(supplier)s resync interval (minutes)")
            % {"supplier": supplier_name},
            "description": _(
                "How often to refresh %(supplier)s supplier parts (in minutes)"
            )
            % {"supplier": supplier_name},
            "validator": int,
            "default": 1440,
        }
        settings[batch_size_key] = {
            "name": _("%(supplier)s resync batch size")
            % {"supplier": supplier_name},
            "description": _(
                "Maximum number of existing %(supplier)s supplier parts to process per scheduled run"
            )
            % {"supplier": supplier_name},
            "validator": int,
            "default": 100,
        }
        settings[api_rate_limit_key] = {
            "name": _("%(supplier)s API calls per second")
            % {"supplier": supplier_name},
            "description": _(
                "Maximum %(supplier)s API requests per second (0 = unlimited)"
            )
            % {"supplier": supplier_name},
            "validator": int,
            "default": default_rate,
        }
        settings[api_daily_limit_key] = {
            "name": _("%(supplier)s API calls per day")
            % {"supplier": supplier_name},
            "description": _(
                "Maximum %(supplier)s API requests per day (0 = unlimited)"
            )
            % {"supplier": supplier_name},
            "validator": int,
            "default": default_daily,
        }

    return settings


def build_supplier_user_settings(adapter_classes):
    settings = {}
    for adapter_class in adapter_classes:
        settings.update(getattr(adapter_class, "user_settings", {}) or {})
    return settings
