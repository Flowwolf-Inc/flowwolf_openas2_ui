# Copyright (c) 2026, Lakshana and contributors
# For license information, please see license.txt

import tempfile
from pathlib import Path
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from openas2_manager.openas2 import partnership_config as pc

BASE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<partnerships>
    <partner name="Broker" as2_id="BROKER_AS2ID" x509_alias="broker"/>
    <partner name="Carrier" as2_id="CARRIER_AS2ID" x509_alias="carrier"/>
    <partnership name="Broker-to-Carrier">
        <sender name="Broker"/>
        <receiver name="Carrier"/>
        <attribute name="as2_url" value="https://localhost:11443"/>
        <attribute name="encrypt" value="3DES"/>
        <attribute name="sign" value="SHA-256"/>
        <attribute name="as2_mdn_options" value="signed-receipt-protocol=optional"/>
    </partnership>
</partnerships>
"""


class TestOpenAS2PartnershipConfig(FrappeTestCase):
	def tearDown(self):
		frappe.db.rollback()

	def _temp_home(self, with_xml=True):
		tmp = tempfile.TemporaryDirectory()
		self.addCleanup(tmp.cleanup)
		home = Path(tmp.name)
		(home / "config").mkdir()
		if with_xml:
			(home / "config" / "partnerships.xml").write_text(BASE_XML, encoding="utf-8")
		return home

	def _make_instance(self, home: Path, **overrides):
		name = overrides.get("instance_name", f"TInst-{frappe.generate_hash(length=6)}")
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
				"openas2_home": str(home),
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
				"partner_name": overrides.get("partner_name", f"PName-{suffix}"),
				"partner_type": overrides.get("partner_type", "Broker"),
				"as2_id": overrides.get("as2_id", f"PID_{suffix}"),
				"as2_url": overrides.get("as2_url", "https://localhost:12443"),
				"status": "Active",
			}
		)
		doc.insert()
		return doc

	def _make_partnership(self, instance_name, **overrides):
		suffix = frappe.generate_hash(length=8)
		local = overrides.get("local_partner_doc") or self._make_partner(
			partner_name=overrides.get("local_partner_name", f"Local-{suffix}"),
			partner_type="Broker",
			as2_id=f"L_{suffix}",
		)
		remote = overrides.get("remote_partner_doc") or self._make_partner(
			partner_name=overrides.get("remote_partner_name", f"Remote-{suffix}"),
			partner_type="Shipper",
			as2_id=f"R_{suffix}",
			as2_url=overrides.get("remote_url", "https://localhost:12443"),
		)
		doc = frappe.get_doc(
			{
				"doctype": "OpenAS2 Partnership",
				"partnership_name": overrides.get("partnership_name", f"P-{suffix}"),
				"instance": instance_name,
				"local_partner": local.name,
				"remote_partner": remote.name,
				"local_as2_id": overrides.get("local_as2_id", local.as2_id),
				"remote_as2_id": overrides.get("remote_as2_id", remote.as2_id),
				"remote_url": overrides.get("remote_url", remote.as2_url),
				"local_partner_name": overrides.get("local_partner_name", local.partner_name),
				"remote_partner_name": overrides.get("remote_partner_name", remote.partner_name),
				"local_x509_alias": overrides.get("local_x509_alias", "broker"),
				"remote_x509_alias": overrides.get("remote_x509_alias", "shipper"),
				"encryption_enabled": overrides.get("encryption_enabled", 1),
				"signing_enabled": overrides.get("signing_enabled", 1),
				"mdn_enabled": overrides.get("mdn_enabled", 1),
				"mdn_mode": overrides.get("mdn_mode", "Synchronous"),
				"status": overrides.get("status", "Draft"),
			}
		)
		# Fixed names must stay intact so they match partnerships.xml.
		# Deleting a committed leftover is rolled back with the test transaction.
		if frappe.db.exists("OpenAS2 Partnership", doc.partnership_name):
			frappe.delete_doc(
				"OpenAS2 Partnership",
				doc.partnership_name,
				force=1,
				ignore_permissions=True,
			)
		doc.insert()
		return doc

	def test_create_partnership(self):
		home = self._temp_home()
		inst = self._make_instance(home)
		doc = self._make_partnership(inst.name)
		self.assertEqual(doc.status, "Draft")
		self.assertTrue(frappe.db.exists("OpenAS2 Partnership", doc.name))

	def test_required_fields(self):
		home = self._temp_home()
		inst = self._make_instance(home)
		local = self._make_partner(partner_name="BrokerOnly")
		doc = frappe.get_doc(
			{
				"doctype": "OpenAS2 Partnership",
				"partnership_name": "Missing Remote Partner",
				"instance": inst.name,
				"local_partner": local.name,
				"local_as2_id": local.as2_id,
				"local_partner_name": local.partner_name,
				"local_x509_alias": "broker",
			}
		)
		with self.assertRaises(frappe.ValidationError):
			doc.insert()

	def test_duplicate_partnership(self):
		home = self._temp_home()
		inst = self._make_instance(home)
		name = f"DupPartner-{frappe.generate_hash(length=6)}"
		self._make_partnership(inst.name, partnership_name=name)
		local = self._make_partner(partner_name="Broker", as2_id=f"DUP_L_{frappe.generate_hash(length=4)}")
		remote = self._make_partner(
			partner_name="Other",
			partner_type="Shipper",
			as2_id=f"DUP_R_{frappe.generate_hash(length=4)}",
		)
		doc = frappe.get_doc(
			{
				"doctype": "OpenAS2 Partnership",
				"partnership_name": name,
				"instance": inst.name,
				"local_partner": local.name,
				"remote_partner": remote.name,
				"local_as2_id": local.as2_id,
				"remote_as2_id": remote.as2_id,
				"remote_url": "https://localhost:1",
				"local_partner_name": "Broker",
				"remote_partner_name": "Other",
				"local_x509_alias": "broker",
				"remote_x509_alias": "other",
				"status": "Draft",
			}
		)
		with self.assertRaises(frappe.DuplicateEntryError):
			doc.insert()

	def test_parse_existing_partnerships_xml(self):
		home = self._temp_home()
		inst = self._make_instance(home)
		listed = pc.list_instance_partnerships(inst.name)
		self.assertFalse(listed["xml_error"])
		names = [r["partnership_name"] for r in listed["xml_partnerships"]]
		self.assertIn("Broker-to-Carrier", names)

	def test_generate_proposed_xml_and_diff(self):
		home = self._temp_home()
		inst = self._make_instance(home)
		doc = self._make_partnership(inst.name, partnership_name="Broker-to-Shipper")
		proposal = pc.build_proposal_for_partnership(doc)
		self.assertEqual(proposal["change_type"], "Add")
		self.assertIn("Broker-to-Shipper", proposal["proposed_xml"])
		self.assertTrue(proposal["diff"])
		self.assertIn("Broker-to-Shipper", proposal["classification"]["added"])
		self.assertFalse(proposal["restart_openas2"])

	def test_preview_creates_audit_without_write(self):
		home = self._temp_home()
		inst = self._make_instance(home)
		before = (home / "config" / "partnerships.xml").read_text(encoding="utf-8")
		doc = self._make_partnership(inst.name, partnership_name="Broker-to-Shipper-2")
		result = pc.preview_partnership_change(doc.name)
		after = (home / "config" / "partnerships.xml").read_text(encoding="utf-8")
		self.assertEqual(before, after)
		self.assertFalse(result["writes_performed"])
		self.assertFalse(result["openas2_restarted"])
		self.assertTrue(frappe.db.exists("OpenAS2 Configuration Change", result["configuration_change"]))
		change = frappe.get_doc("OpenAS2 Configuration Change", result["configuration_change"])
		self.assertEqual(change.status, "Proposed")

	def test_add_partnership_apply(self):
		home = self._temp_home()
		inst = self._make_instance(home)
		doc = self._make_partnership(inst.name, partnership_name="Broker-to-Shipper-Add")
		preview = pc.preview_partnership_change(doc.name)
		result = pc.apply_configuration_change(preview["configuration_change"])
		self.assertEqual(result["status"], "Applied")
		self.assertFalse(result["openas2_restarted"])
		xml = (home / "config" / "partnerships.xml").read_text(encoding="utf-8")
		self.assertIn("Broker-to-Shipper-Add", xml)
		backups = list((home / "config" / "backups").glob("partnerships.xml.*.bak"))
		self.assertTrue(backups)

	def test_modify_partnership_apply(self):
		home = self._temp_home()
		inst = self._make_instance(home)
		doc = self._make_partnership(
			inst.name,
			partnership_name="Broker-to-Carrier",
			remote_url="https://localhost:11999",
			remote_partner_name="Carrier",
			remote_as2_id="CARRIER_AS2ID",
			remote_x509_alias="carrier",
		)
		preview = pc.preview_partnership_change(doc.name)
		self.assertEqual(preview["change_type"], "Modify")
		pc.apply_configuration_change(preview["configuration_change"])
		xml = (home / "config" / "partnerships.xml").read_text(encoding="utf-8")
		self.assertIn("https://localhost:11999", xml)

	def test_backup_creation_and_xml_validation(self):
		home = self._temp_home()
		inst = self._make_instance(home)
		path = home / "config" / "partnerships.xml"
		backup = pc.create_backup(path, home.resolve())
		self.assertTrue(backup.is_file())
		self.assertGreater(backup.stat().st_size, 0)
		with self.assertRaises(Exception):
			pc.validate_xml("<partnerships><broken>")

	def test_atomic_write(self):
		home = self._temp_home()
		target = home / "config" / "partnerships.xml"
		new_xml = BASE_XML.replace("11443", "11444")
		pc.atomic_write_xml(target, new_xml, home.resolve())
		self.assertIn("11444", target.read_text(encoding="utf-8"))
		self.assertFalse(list((home / "config").glob("*.tmp")))

	def test_failed_write_rollback(self):
		home = self._temp_home()
		inst = self._make_instance(home)
		original = (home / "config" / "partnerships.xml").read_text(encoding="utf-8")
		doc = self._make_partnership(inst.name, partnership_name="Broker-to-Shipper-RB")
		preview = pc.preview_partnership_change(doc.name)

		def boom(*args, **kwargs):
			raise RuntimeError("simulated write failure")

		with patch.object(pc, "atomic_write_xml", side_effect=boom):
			with self.assertRaises(Exception):
				pc.apply_configuration_change(preview["configuration_change"])

		after = (home / "config" / "partnerships.xml").read_text(encoding="utf-8")
		# Original preserved because write failed before replace (backup exists, restore attempted)
		self.assertEqual(original, after)
		change = frappe.get_doc("OpenAS2 Configuration Change", preview["configuration_change"])
		self.assertIn(change.status, ("Failed", "Rolled Back"))

	def test_no_automatic_restart_flag(self):
		home = self._temp_home()
		inst = self._make_instance(home)
		doc = self._make_partnership(inst.name, partnership_name="No-Restart")
		preview = pc.preview_partnership_change(doc.name)
		applied = pc.apply_configuration_change(preview["configuration_change"])
		self.assertFalse(preview["restart_openas2"])
		self.assertFalse(applied["openas2_restarted"])

	def test_no_password_private_key_exposure(self):
		home = self._temp_home()
		# Inject a fake password attribute into source XML to ensure redaction
		xml = BASE_XML.replace(
			"</partnerships>",
			'    <partner name="X" as2_id="X" x509_alias="x" password="secret-pass"/>\n</partnerships>',
		)
		(home / "config" / "partnerships.xml").write_text(xml, encoding="utf-8")
		inst = self._make_instance(home)
		doc = self._make_partnership(inst.name, partnership_name="Safe-Preview")
		result = pc.preview_partnership_change(doc.name)
		blob = frappe.as_json(result)
		self.assertNotIn("secret-pass", blob)
		self.assertNotIn("BEGIN PRIVATE KEY", blob.upper())
		self.assertIn("********", result["current_xml_redacted"])

	def test_path_traversal_protection(self):
		home = self._temp_home()
		with self.assertRaises(Exception):
			pc.assert_under_home(home.resolve(), Path("/etc/passwd"))

	def test_saving_doctype_does_not_write_xml(self):
		home = self._temp_home()
		inst = self._make_instance(home)
		before = (home / "config" / "partnerships.xml").read_bytes()
		doc = self._make_partnership(inst.name, partnership_name="Save-Only")
		doc.status = "Active"
		doc.save()
		after = (home / "config" / "partnerships.xml").read_bytes()
		self.assertEqual(before, after)
