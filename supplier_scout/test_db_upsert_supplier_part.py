"""Database-backed tests for supplier part upsert behavior."""

import unittest

try:
    from InvenTree.unit_test import InvenTreeTestCase
    from company.models import Company, ManufacturerPart, SupplierPart, SupplierPriceBreak
    from part.models import Part

    INVENTREE_TESTS_AVAILABLE = True
except ModuleNotFoundError:
    InvenTreeTestCase = unittest.TestCase
    INVENTREE_TESTS_AVAILABLE = False

from supplier_scout.core import SupplierScout


class _FakeAdapter:
    """Small adapter stub exposing methods used by upsert path."""

    key = "fake"

    def normalize_candidate(self, candidate):
        return dict(candidate)

    def get_candidate_supplier_part_number(self, candidate):
        return str(candidate.get("supplier_part_number") or "").strip()

    def get_candidate_manufacturer_part_number(self, candidate):
        return str(candidate.get("manufacturer_part_number") or "").strip()

    def get_candidate_manufacturer_name(self, candidate):
        return str(candidate.get("manufacturer_name") or "").strip()

    def build_supplier_part_update_data(self, candidate):
        return {
            "description": str(candidate.get("description") or ""),
            "link": str(candidate.get("supplier_link") or ""),
        }

    def get_candidate_datasheet_url(self, candidate):
        return str(candidate.get("datasheet") or "").strip()


@unittest.skipUnless(INVENTREE_TESTS_AVAILABLE, "InvenTree test dependencies unavailable")
class SupplierScoutDatabaseUpsertTests(InvenTreeTestCase):
    """Ensure supplier part upsert performs expected database writes."""

    def setUp(self):
        self.scout = object.__new__(SupplierScout)
        self.adapter = _FakeAdapter()

        self.scout._get_supplier_registration = lambda supplier_pk: {
            "pk": int(supplier_pk),
            "key": "fake",
        }
        self.scout._get_supplier_definition = (
            lambda supplier_key: self.adapter if supplier_key == "fake" else None
        )

    def test_upsert_creates_then_updates_supplier_part_and_price_breaks(self):
        part = Part.objects.create(name="Scout DB Part", component=True)
        supplier = Company.objects.create(name="Scout Supplier", is_supplier=True)

        create_candidate = {
            "supplier_part_number": "SKU-100",
            "manufacturer_part_number": "MPN-100",
            "manufacturer_name": "Scout Manufacturer",
            "description": "Initial supplier part description",
            "supplier_link": "https://supplier.example/item/SKU-100",
            "datasheet": "https://datasheets.example/MPN-100.pdf",
            "price_breaks": [
                {"quantity": 1, "price": 0.45, "currency": "USD"},
                {"quantity": 10, "price": 0.30, "currency": "USD"},
            ],
        }

        result = self.scout._upsert_supplier_part_candidate(
            part=part,
            supplier=supplier,
            candidate=create_candidate,
        )

        self.assertEqual(result["status"], "created")

        supplier_part = SupplierPart.objects.get(
            part=part, supplier=supplier, SKU="SKU-100"
        )
        self.assertEqual(supplier_part.description, "Initial supplier part description")
        self.assertEqual(
            SupplierPriceBreak.objects.filter(part=supplier_part).count(), 2
        )

        manufacturer_part = ManufacturerPart.objects.get(part=part, MPN="MPN-100")
        self.assertEqual(manufacturer_part.manufacturer.name, "Scout Manufacturer")

        part.refresh_from_db()
        self.assertEqual(part.link, "https://datasheets.example/MPN-100.pdf")

        update_candidate = {
            "supplier_part_number": "SKU-100",
            "manufacturer_part_number": "MPN-100",
            "manufacturer_name": "Scout Manufacturer",
            "description": "Updated supplier part description",
            "supplier_link": "https://supplier.example/item/SKU-100-v2",
            "datasheet": "https://datasheets.example/MPN-100-v2.pdf",
            "price_breaks": [
                {"quantity": 25, "price": 0.22, "currency": "USD"},
            ],
        }

        result = self.scout._upsert_supplier_part_candidate(
            part=part,
            supplier=supplier,
            candidate=update_candidate,
        )

        self.assertEqual(result["status"], "updated")
        self.assertEqual(
            SupplierPart.objects.filter(
                part=part, supplier=supplier, SKU="SKU-100"
            ).count(),
            1,
        )

        supplier_part.refresh_from_db()
        self.assertEqual(supplier_part.description, "Updated supplier part description")
        self.assertEqual(
            list(
                SupplierPriceBreak.objects.filter(part=supplier_part)
                .values_list("quantity", flat=True)
                .order_by("quantity")
            ),
            [25],
        )

        part.refresh_from_db()
        self.assertEqual(part.link, "https://datasheets.example/MPN-100-v2.pdf")
