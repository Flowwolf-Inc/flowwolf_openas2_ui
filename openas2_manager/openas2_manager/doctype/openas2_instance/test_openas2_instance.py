# Copyright (c) 2026, Lakshana and contributors
# For license information, please see license.txt

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from openas2_manager.openas2.connection import test_instance_connection


class TestOpenAS2Instance(FrappeTestCase):
	def tearDown(self):
		frappe.db.rollback()

	def _make_instance(self, **overrides):
		doc = frappe.get_doc(
			{
				"doctype": "OpenAS2 Instance",
				"instance_name": overrides.get("instance_name", "Test Broker Instance"),
				"instance_type": overrides.get("instance_type", "Broker"),
				"as2_id": overrides.get("as2_id", "TEST_BROKER_INSTANCE_AS2ID"),
				"host": overrides.get("host", "127.0.0.1"),
				"port": overrides.get("port", 10443),
				"protocol": overrides.get("protocol", "HTTPS"),
				"inbox_path": overrides.get("inbox_path", "/tmp/openas2/inbox"),
				"outbox_path": overrides.get("outbox_path", "/tmp/openas2/outbox"),
				"mdn_enabled": overrides.get("mdn_enabled", 1),
				"status": overrides.get("status", "Active"),
				"description": overrides.get("description", "Unit test instance"),
			}
		)
		doc.insert()
		return doc

	def test_create_instance(self):
		doc = self._make_instance()
		self.assertEqual(doc.name, "Test Broker Instance")
		self.assertEqual(doc.connection_status, "Unknown")
		self.assertTrue(frappe.db.exists("OpenAS2 Instance", "Test Broker Instance"))

	def test_required_fields(self):
		doc = frappe.get_doc(
			{
				"doctype": "OpenAS2 Instance",
				"instance_name": "Missing Host",
				"instance_type": "Shipper",
				"as2_id": "MISSING_HOST_AS2ID",
				"port": 12443,
			}
		)
		with self.assertRaises(frappe.ValidationError):
			doc.insert()

	def test_duplicate_instance_name(self):
		self._make_instance(instance_name="Dup Name", as2_id="DUP_NAME_AS2ID")
		with self.assertRaises(frappe.DuplicateEntryError):
			self._make_instance(instance_name="Dup Name", as2_id="DUP_NAME_AS2ID_2")

	def test_duplicate_as2_id(self):
		self._make_instance(instance_name="First Inst", as2_id="DUP_AS2_INSTANCE")
		with self.assertRaises(frappe.DuplicateEntryError):
			self._make_instance(instance_name="Second Inst", as2_id="DUP_AS2_INSTANCE")

	def test_default_status(self):
		doc = frappe.get_doc(
			{
				"doctype": "OpenAS2 Instance",
				"instance_name": "Default Status Inst",
				"instance_type": "Carrier",
				"as2_id": "DEFAULT_STATUS_INST",
				"host": "localhost",
				"port": 11443,
			}
		)
		doc.insert()
		self.assertEqual(doc.status, "Active")
		self.assertEqual(doc.protocol, "HTTPS")
		self.assertEqual(doc.connection_status, "Unknown")
		self.assertEqual(doc.mdn_enabled, 1)

	def test_connection_success_records_status(self):
		doc = self._make_instance(instance_name="Conn OK", as2_id="CONN_OK_AS2ID", port=10443)
		with patch(
			"openas2_manager.openas2.connection.tcp_reachability_check",
			return_value={"reachable": True, "error": None, "check_type": "tcp_connect"},
		):
			result = test_instance_connection(doc.name)

		self.assertEqual(result["connection_status"], "Connected")
		self.assertFalse(result["as2_protocol_verified"])
		self.assertFalse(result["edi_sent"])
		self.assertFalse(result["config_modified"])
		doc.reload()
		self.assertEqual(doc.connection_status, "Connected")
		self.assertTrue(doc.last_tested)

	def test_connection_failure_records_status(self):
		doc = self._make_instance(instance_name="Conn Fail", as2_id="CONN_FAIL_AS2ID", port=9)
		with patch(
			"openas2_manager.openas2.connection.tcp_reachability_check",
			return_value={
				"reachable": False,
				"error": "Connection refused",
				"check_type": "tcp_connect",
			},
		):
			result = test_instance_connection(doc.name)

		self.assertEqual(result["connection_status"], "Failed")
		self.assertFalse(result["as2_protocol_verified"])
		doc.reload()
		self.assertEqual(doc.connection_status, "Failed")
		self.assertTrue(doc.last_tested)

	def test_no_secret_fields(self):
		meta = frappe.get_meta("OpenAS2 Instance")
		secretish = [
			f.fieldname
			for f in meta.fields
			if any(
				token in (f.fieldname or "").lower()
				for token in ("password", "private_key", "secret", "keystore_password", "db_pwd")
			)
		]
		self.assertEqual(secretish, [])
