# Copyright (c) 2026, Lakshana and contributors
# For license information, please see license.txt

"""Tests for remote TMS EDI Document mirroring."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from openas2_manager.openas2 import tms_edi


class TestTMSEdiSync(FrappeTestCase):
	def setUp(self):
		super().setUp()
		self.suffix = frappe.generate_hash(length=6)
		base = 20000 + (int(self.suffix, 16) % 20000)
		self.instance = frappe.get_doc(
			{
				"doctype": "OpenAS2 Instance",
				"instance_name": f"TMS EDI Test {self.suffix}",
				"instance_type": "Shipper",
				"as2_id": f"SHIPPER_EDI_{self.suffix}",
				"host": "localhost",
				"port": base,
				"protocol": "HTTPS",
				"http_enabled": 0,
				"https_enabled": 1,
				"https_port": base,
				"mdn_http_enabled": 0,
				"mdn_https_enabled": 1,
				"mdn_https_port": base + 1,
				"tms_site_url": "http://shipper.test:8000",
			}
		)
		self.instance.insert(ignore_permissions=True)

	def tearDown(self):
		frappe.db.delete("OpenAS2 EDI Document", {"instance": self.instance.name})
		frappe.delete_doc("OpenAS2 Instance", self.instance.name, force=True, ignore_permissions=True)
		super().tearDown()

	def test_upsert_and_list(self):
		name = tms_edi.upsert_edi_mirror(
			self.instance,
			{
				"name": "EDI-SHIP-1",
				"file_name": "LOAD054_204.edi",
				"transaction_type": "204",
				"status": "Processed",
				"direction": "Outbound",
				"partner": "Broker Partner",
				"as2_message_id": "<msg-1>",
				"modified": "2026-09-23 10:00:00",
			},
		)
		self.assertTrue(name)
		doc = frappe.get_doc("OpenAS2 EDI Document", name)
		self.assertEqual(doc.tms, "Shipper")
		self.assertEqual(doc.tms_doc_name, "EDI-SHIP-1")
		self.assertIn("shipper.test", doc.tms_url)
		self.assertIn("EDI-SHIP-1", doc.tms_url)

		listed = tms_edi.get_edi_documents(tms="Shipper")
		self.assertFalse(listed.get("ok", True))
		self.assertEqual(listed["rows"], [])
		self.assertTrue(listed.get("error"))
		self.assertEqual(listed.get("source"), "OpenAS2 database")

	def test_sync_uses_remote_fetch(self):
		remote_rows = [
			{
				"name": "EDI-REMOTE-9",
				"file_name": "ACK990.edi",
				"transaction_type": "990",
				"status": "Success",
				"modified": "2026-09-23 11:00:00",
			}
		]
		with patch.object(tms_edi, "fetch_edi_documents_from_tms", return_value=remote_rows):
			with patch.object(tms_edi, "resolve_tms_auth", return_value=("key", "secret")):
				stats = tms_edi.sync_instance_edi_documents(self.instance)
		self.assertEqual(stats["edi_documents"], 1)
		self.assertTrue(
			frappe.db.exists(
				"OpenAS2 EDI Document",
				{"tms": "Shipper", "tms_doc_name": "EDI-REMOTE-9"},
			)
		)

	def test_skip_without_url(self):
		self.instance.tms_site_url = ""
		self.instance.save(ignore_permissions=True)
		with patch.object(tms_edi, "get_tms_site_config", return_value={}):
			stats = tms_edi.sync_instance_edi_documents(self.instance)
		self.assertTrue(stats["skipped"])
		self.assertTrue(stats["notes"])

	def test_find_mirrored_by_file(self):
		tms_edi.upsert_edi_mirror(
			self.instance,
			{
				"name": "EDI-FIND-1",
				"file_name": "FINDME_204.edi",
				"as2_message_id": "<find-me>",
				"modified": "2026-09-23 12:00:00",
			},
		)
		hit = tms_edi.find_mirrored_edi_document("FINDME_204.edi", None, instance=self.instance.name)
		self.assertEqual(hit.tms_doc_name, "EDI-FIND-1")

	def test_webhook_ingest(self):
		frappe.conf.openas2_tms_webhook_token = "test-webhook-token"
		with patch.object(frappe, "get_request_header", return_value="test-webhook-token"):
			result = tms_edi.ingest_tms_edi_document(
				tms="Shipper",
				name="EDI-PUSH-1",
				file_name="PUSH_204.edi",
				status="Sent",
				direction="Outbound",
				transaction_type="204",
			)
		self.assertTrue(result["ok"])
		self.assertTrue(
			frappe.db.exists(
				"OpenAS2 EDI Document",
				{"tms": "Shipper", "tms_doc_name": "EDI-PUSH-1"},
			)
		)

	def test_webhook_rejects_bad_token(self):
		frappe.conf.openas2_tms_webhook_token = "expected"
		with patch.object(frappe, "get_request_header", return_value="wrong"):
			with self.assertRaises(frappe.PermissionError):
				tms_edi.ingest_tms_edi_document(tms="Shipper", name="EDI-X")


if __name__ == "__main__":
	unittest.main()
