# Copyright (c) 2026, Lakshana and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.utils import FrappeTestCase


class TestOpenAS2Partnership(FrappeTestCase):
	def tearDown(self):
		frappe.db.rollback()

	def _make_instance(self, **overrides):
		name = overrides.get("instance_name", f"PInst-{frappe.generate_hash(length=6)}")
		doc = frappe.get_doc(
			{
				"doctype": "OpenAS2 Instance",
				"instance_name": name,
				"instance_type": overrides.get("instance_type", "Broker"),
				"as2_id": overrides.get("as2_id", f"T_{frappe.generate_hash(length=8)}"),
				"host": "localhost",
				"port": 10443,
				"protocol": "HTTPS",
				"http_enabled": 1,
				"http_port": 10080,
				"https_enabled": 1,
				"https_port": 10443,
				"mdn_enabled": 0,
				"mdn_http_enabled": 0,
				"mdn_https_enabled": 0,
				"openas2_home": overrides.get("openas2_home", "/tmp/openas2-test"),
				"status": "Active",
			}
		)
		doc.insert()
		return doc

	def _make_partner(self, **overrides):
		suffix = frappe.generate_hash(length=6)
		doc = frappe.get_doc(
			{
				"doctype": "AS2 Partner",
				"partner_name": overrides.get("partner_name", f"Partner {suffix}"),
				"partner_type": overrides.get("partner_type", "Broker"),
				"as2_id": overrides.get("as2_id", f"AS2_{suffix}"),
				"as2_url": overrides.get("as2_url", "https://localhost:11443"),
				"status": "Active",
				"encryption_enabled": overrides.get("encryption_enabled", 1),
				"signing_enabled": overrides.get("signing_enabled", 1),
				"mdn_enabled": overrides.get("mdn_enabled", 1),
				"mdn_mode": overrides.get("mdn_mode", "Synchronous"),
			}
		)
		doc.insert()
		return doc

	def _make_partnership(self, instance, local, remote, **overrides):
		doc = frappe.get_doc(
			{
				"doctype": "OpenAS2 Partnership",
				"partnership_name": overrides.get(
					"partnership_name",
					f"{local.partner_name}-to-{remote.partner_name}",
				),
				"instance": instance.name,
				"local_partner": local.name,
				"remote_partner": remote.name,
				"local_partner_name": overrides.get("local_partner_name", local.partner_name),
				"remote_partner_name": overrides.get("remote_partner_name", remote.partner_name),
				"local_as2_id": overrides.get("local_as2_id", local.as2_id),
				"remote_as2_id": overrides.get("remote_as2_id", remote.as2_id),
				"local_x509_alias": overrides.get("local_x509_alias", local.partner_type.lower()),
				"remote_x509_alias": overrides.get("remote_x509_alias", remote.partner_type.lower()),
				"remote_url": overrides.get("remote_url", remote.as2_url),
				"encryption_enabled": 1,
				"signing_enabled": 1,
				"mdn_enabled": 1,
				"mdn_mode": "Synchronous",
				"status": overrides.get("status", "Draft"),
			}
		)
		doc.insert()
		return doc

	def test_create_with_required_fields(self):
		inst = self._make_instance()
		local = self._make_partner(partner_name="Broker", partner_type="Broker", as2_id="BRK_REQ")
		remote = self._make_partner(
			partner_name="Carrier",
			partner_type="Carrier",
			as2_id="CAR_REQ",
			as2_url="https://localhost:11443",
		)
		doc = self._make_partnership(inst, local, remote)
		self.assertEqual(doc.status, "Draft")
		self.assertEqual(doc.local_partner, local.name)
		self.assertEqual(doc.remote_partner, remote.name)
		self.assertEqual(doc.remote_url, "https://localhost:11443")
		self.assertTrue(doc.direction_hint)

	def test_autofill_from_partners_on_save(self):
		inst = self._make_instance()
		local = self._make_partner(partner_name="Shipper", partner_type="Shipper", as2_id="SHP_AF")
		remote = self._make_partner(
			partner_name="Broker",
			partner_type="Broker",
			as2_id="BRK_AF",
			as2_url="https://broker.example.local/as2",
		)
		doc = frappe.get_doc(
			{
				"doctype": "OpenAS2 Partnership",
				"instance": inst.name,
				"local_partner": local.name,
				"remote_partner": remote.name,
				"status": "Draft",
			}
		)
		doc.insert()
		self.assertEqual(doc.partnership_name, "Shipper-to-Broker")
		self.assertEqual(doc.local_as2_id, "SHP_AF")
		self.assertEqual(doc.remote_as2_id, "BRK_AF")
		self.assertEqual(doc.remote_url, "https://broker.example.local/as2")
		self.assertEqual(doc.local_x509_alias, "shipper")
		self.assertEqual(doc.remote_x509_alias, "broker")

	def test_missing_remote_partner_fails(self):
		inst = self._make_instance()
		local = self._make_partner(as2_id="ONLY_LOCAL")
		doc = frappe.get_doc(
			{
				"doctype": "OpenAS2 Partnership",
				"partnership_name": "Incomplete",
				"instance": inst.name,
				"local_partner": local.name,
				"local_as2_id": local.as2_id,
				"local_partner_name": local.partner_name,
				"local_x509_alias": "broker",
			}
		)
		with self.assertRaises(frappe.ValidationError):
			doc.insert()

	def test_same_partners_rejected(self):
		inst = self._make_instance()
		partner = self._make_partner(as2_id="SAME_BOTH")
		doc = frappe.get_doc(
			{
				"doctype": "OpenAS2 Partnership",
				"partnership_name": "Same-to-Same",
				"instance": inst.name,
				"local_partner": partner.name,
				"remote_partner": partner.name,
				"local_partner_name": partner.partner_name,
				"remote_partner_name": partner.partner_name,
				"local_as2_id": partner.as2_id,
				"remote_as2_id": partner.as2_id,
				"local_x509_alias": "broker",
				"remote_x509_alias": "broker",
				"remote_url": partner.as2_url,
			}
		)
		with self.assertRaises(frappe.ValidationError):
			doc.insert()

	def test_invalid_url_rejected(self):
		inst = self._make_instance()
		local = self._make_partner(as2_id="URL_L")
		remote = self._make_partner(as2_id="URL_R", partner_type="Carrier")
		doc = frappe.get_doc(
			{
				"doctype": "OpenAS2 Partnership",
				"partnership_name": "Bad-URL",
				"instance": inst.name,
				"local_partner": local.name,
				"remote_partner": remote.name,
				"local_partner_name": local.partner_name,
				"remote_partner_name": remote.partner_name,
				"local_as2_id": local.as2_id,
				"remote_as2_id": remote.as2_id,
				"local_x509_alias": "broker",
				"remote_x509_alias": "carrier",
				"remote_url": "ftp://not-as2",
			}
		)
		with self.assertRaises(frappe.ValidationError):
			doc.insert()
