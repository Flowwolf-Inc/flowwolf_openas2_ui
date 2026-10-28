# Copyright (c) 2026, Lakshana and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.utils import FrappeTestCase


class TestAS2Partner(FrappeTestCase):
	def tearDown(self):
		frappe.db.rollback()

	def _make_partner(self, **overrides):
		doc = frappe.get_doc(
			{
				"doctype": "AS2 Partner",
				"partner_name": overrides.get("partner_name", "Test Shipper"),
				"as2_id": overrides.get("as2_id", "TEST_SHIPPER_AS2ID"),
				"partner_type": overrides.get("partner_type", "Shipper"),
				"as2_url": overrides.get("as2_url", "https://shipper.example.local/as2"),
				"status": overrides.get("status", "Active"),
				"encryption_enabled": overrides.get("encryption_enabled", 0),
				"signing_enabled": overrides.get("signing_enabled", 0),
				"mdn_enabled": overrides.get("mdn_enabled", 0),
				"mdn_mode": overrides.get("mdn_mode"),
				"description": overrides.get("description", "Unit test partner"),
			}
		)
		doc.insert()
		return doc

	def test_create_partner(self):
		doc = self._make_partner()
		self.assertEqual(doc.name, "TEST_SHIPPER_AS2ID")
		self.assertEqual(doc.status, "Active")
		self.assertTrue(frappe.db.exists("AS2 Partner", "TEST_SHIPPER_AS2ID"))

	def test_default_status_is_active(self):
		doc = frappe.get_doc(
			{
				"doctype": "AS2 Partner",
				"partner_name": "Default Status Partner",
				"as2_id": "DEFAULT_STATUS_AS2ID",
				"partner_type": "Broker",
				"as2_url": "https://broker.example.local/as2",
			}
		)
		doc.insert()
		self.assertEqual(doc.status, "Active")

	def test_duplicate_as2_id_is_rejected(self):
		self._make_partner(as2_id="DUP_AS2ID", partner_name="First")
		with self.assertRaises(frappe.DuplicateEntryError):
			self._make_partner(as2_id="DUP_AS2ID", partner_name="Second")

	def test_required_fields(self):
		doc = frappe.get_doc(
			{
				"doctype": "AS2 Partner",
				"partner_name": "Missing URL",
				"as2_id": "MISSING_URL_AS2ID",
				"partner_type": "Carrier",
			}
		)
		with self.assertRaises(frappe.ValidationError):
			doc.insert()

	def test_mdn_mode_required_when_enabled(self):
		with self.assertRaises(frappe.ValidationError):
			self._make_partner(
				as2_id="MDN_REQUIRED_AS2ID",
				mdn_enabled=1,
				mdn_mode=None,
			)

	def test_mdn_mode_cleared_when_disabled(self):
		doc = self._make_partner(
			as2_id="MDN_CLEAR_AS2ID",
			mdn_enabled=0,
			mdn_mode="Synchronous",
		)
		self.assertFalse(doc.mdn_mode)

	def test_certificate_link_field(self):
		cert = frappe.get_doc(
			{
				"doctype": "AS2 Certificate",
				"certificate_name": "PARTNER_LINK_CERT",
				"certificate_type": "Both",
				"owner_type": "Shipper",
				"common_name": "partner-link.example.local",
				"status": "Active",
			}
		)
		cert.insert()
		partner = self._make_partner(as2_id="PARTNER_WITH_CERT", partner_name="With Cert")
		partner.certificate = cert.name
		partner.save()
		self.assertEqual(frappe.db.get_value("AS2 Partner", partner.name, "certificate"), cert.name)
