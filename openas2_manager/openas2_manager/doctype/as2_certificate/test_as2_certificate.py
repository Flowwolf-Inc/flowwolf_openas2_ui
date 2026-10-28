# Copyright (c) 2026, Lakshana and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

from openas2_manager.certificates.generation import request_certificate_generation


class TestAS2Certificate(FrappeTestCase):
	def tearDown(self):
		frappe.db.rollback()

	def _make_certificate(self, **overrides):
		doc = frappe.get_doc(
			{
				"doctype": "AS2 Certificate",
				"certificate_name": overrides.get("certificate_name", "TEST_SHIPPER_CERT"),
				"certificate_type": overrides.get("certificate_type", "Both"),
				"owner_type": overrides.get("owner_type", "Shipper"),
				"purpose": overrides.get("purpose", "Own Key Pair"),
				"x509_alias": overrides.get("x509_alias", "testalias"),
				"common_name": overrides.get("common_name", "shipper.example.local"),
				"valid_from": overrides.get("valid_from", today()),
				"valid_until": overrides.get("valid_until", add_days(today(), 365)),
				"status": overrides.get("status", "Active"),
				"description": overrides.get("description", "Unit test certificate"),
			}
		)
		doc.insert()
		return doc

	def test_create_certificate(self):
		doc = self._make_certificate()
		self.assertEqual(doc.name, "TEST_SHIPPER_CERT")
		self.assertEqual(doc.status, "Active")
		self.assertTrue(frappe.db.exists("AS2 Certificate", "TEST_SHIPPER_CERT"))
		self.assertTrue(doc.expiry_info)

	def test_required_fields(self):
		doc = frappe.get_doc(
			{
				"doctype": "AS2 Certificate",
				"certificate_name": "MISSING_CN",
				"certificate_type": "Signing",
				"owner_type": "Broker",
			}
		)
		with self.assertRaises(frappe.ValidationError):
			doc.insert()

	def test_duplicate_certificate_name(self):
		self._make_certificate(certificate_name="DUP_CERT")
		with self.assertRaises(frappe.DuplicateEntryError):
			self._make_certificate(certificate_name="DUP_CERT", common_name="other.example.local")

	def test_invalid_validity_dates(self):
		with self.assertRaises(frappe.ValidationError):
			self._make_certificate(
				certificate_name="BAD_DATES",
				valid_from=today(),
				valid_until=add_days(today(), -1),
			)

	def test_status_auto_expired(self):
		doc = self._make_certificate(
			certificate_name="EXPIRED_CERT",
			valid_from=add_days(today(), -30),
			valid_until=add_days(today(), -1),
			status="Active",
		)
		self.assertEqual(doc.status, "Expired")

	def test_revoked_not_overwritten_by_expiry(self):
		doc = self._make_certificate(
			certificate_name="REVOKED_CERT",
			valid_from=add_days(today(), -30),
			valid_until=add_days(today(), -1),
			status="Revoked",
		)
		self.assertEqual(doc.status, "Revoked")

	def test_partner_certificate_link(self):
		cert = self._make_certificate(certificate_name="LINK_CERT", owner_type="Broker")
		partner = frappe.get_doc(
			{
				"doctype": "AS2 Partner",
				"partner_name": "Cert Link Partner",
				"as2_id": "CERT_LINK_PARTNER",
				"partner_type": "Broker",
				"as2_url": "https://broker.example.local/as2",
				"certificate": cert.name,
			}
		)
		partner.insert()
		self.assertEqual(partner.certificate, cert.name)
		self.assertEqual(frappe.db.get_value("AS2 Partner", partner.name, "certificate"), cert.name)

	def test_generation_creates_keypair_without_exposing_private_key(self):
		cert = self._make_certificate(
			certificate_name="GEN_OWN_CERT",
			x509_alias="genown",
			purpose="Own Key Pair",
			status="Draft",
		)
		result = request_certificate_generation(cert.name)
		self.assertTrue(result.get("ok"))
		self.assertFalse(result.get("private_key_returned"))
		self.assertTrue(result.get("public_certificate_file"))
		self.assertTrue(result.get("keystore_path"))
		serialized = frappe.as_json(result).lower()
		self.assertNotIn("begin private key", serialized)
		self.assertNotIn("begin rsa private key", serialized)
		self.assertNotIn("broker123", serialized)
		self.assertNotIn("testas2", serialized)
		# Reload — private key flag set, public attached
		cert.reload()
		self.assertEqual(cert.private_key_stored, 1)
		self.assertEqual(cert.exchange_status, "Ready to Share")
		self.assertTrue(cert.certificate_file)
