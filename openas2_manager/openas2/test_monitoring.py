# Copyright (c) 2026, Lakshana and contributors
# For license information, please see license.txt

"""Unit tests for read-only OpenAS2 message monitoring.

Uses temporary directories only — never touches real OpenAS2 installs.
"""

from __future__ import annotations

import os
import stat
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from openas2_manager.openas2 import monitoring as mon


class TestOpenAS2Monitoring(FrappeTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		self.suffix = frappe.generate_hash(length=6)
		self.local_id = f"LOC_{self.suffix}"
		self.remote_shipper = f"SHP_{self.suffix}"
		self.remote_carrier = f"CAR_{self.suffix}"

		self._tmpdir = tempfile.TemporaryDirectory()
		self.home = Path(self._tmpdir.name) / "OpenAS2Mock"
		(self.home / "logs").mkdir(parents=True)
		(self.home / "config").mkdir(parents=True)
		(self.home / "data" / "inbox" / self.local_id / "inbox" / "processed").mkdir(parents=True)
		(self.home / "data" / "inbox" / self.local_id / "inbox" / "error").mkdir(parents=True)
		(self.home / "data" / "outbox" / "error" / "2026-09-03" / self.remote_shipper).mkdir(
			parents=True
		)

		out_mid = f"<20260903084500+0530-346-{self.remote_shipper}_{self.local_id}_LOAD054_204.edi>"
		in_mid = f"<20260903084600+0530-111-{self.remote_carrier}_{self.local_id}_LOAD054_990.edi>"
		fail_mid = f"<20260903084700+0530-222-{self.local_id}_{self.remote_shipper}_LOAD054_214.edi>"
		sample_log = f"""\
08:45:00.100 [AS2DirectoryPollingModule] INFO  org.openas2.processor.receiver.MessageBuilderModule -- File assigned to message: LOAD054_204.edi [{out_mid}]
08:45:00.200 [AS2DirectoryPollingModule] INFO  org.openas2.processor.sender.AS2SenderModule -- Connecting to: https://localhost:10443 [{out_mid}]
08:45:01.000 [pool-6-thread-1] INFO  org.openas2.util.AS2Util -- Partner {self.local_id} responded with MDN [automatic-action/MDN-sent-automatically; processed] [{out_mid}]
08:45:01.100 [pool-6-thread-1] INFO  org.openas2.util.AS2Util -- Message sent and MDN received successfully. [{out_mid}]
08:46:00.000 [pool-4-thread-1] INFO  org.openas2.processor.receiver.AS2ReceiverHandler -- received 100 bytes in 0.1 seconds at 1 KBps 127.0.0.1 1 [{in_mid}]
08:46:00.500 [pool-4-thread-1] INFO  org.openas2.processor.storage.MessageFileModule -- stored message to C:\\\\data\\\\inbox\\\\{self.local_id}\\\\inbox\\\\x.edi [{in_mid}]
08:47:00.000 [pool-4-thread-1] ERROR org.openas2.processor.sender.AS2SenderModule -- Connection failed to partner password=secret-value [{fail_mid}]
09:00:00.000 [main] ERROR org.openas2.processor.receiver.NetModule -- Failed transferring data over HTTP connection: Socket closed
"""
		(self.home / "logs" / "log-20260903.txt").write_text(sample_log, encoding="utf-8")
		(
			self.home
			/ "data"
			/ "inbox"
			/ self.local_id
			/ "inbox"
			/ f"{self.remote_shipper}-99999-LOAD100_204.edi"
		).write_text("ISA*", encoding="utf-8")
		(
			self.home
			/ "data"
			/ "inbox"
			/ self.local_id
			/ "inbox"
			/ "error"
			/ f"{self.remote_shipper}-11111-LOAD101_210.edi"
		).write_text("BAD", encoding="utf-8")
		(
			self.home
			/ "data"
			/ "outbox"
			/ "error"
			/ "2026-09-03"
			/ self.remote_shipper
			/ f"20260903090000+0530-333-{self.local_id}_{self.remote_shipper}_LOAD102_820.edi"
		).write_text("x", encoding="utf-8")

		# Companion instances so Message-ID AS2 IDs are known to the parser
		for offset, (as2_id, itype) in enumerate(
			(
				(self.remote_shipper, "Shipper"),
				(self.remote_carrier, "Carrier"),
			)
		):
			base = 12000 + (offset * 10)
			frappe.get_doc(
				{
					"doctype": "OpenAS2 Instance",
					"instance_name": f"Mon {itype} {self.suffix}",
					"instance_type": itype,
					"as2_id": as2_id,
					"openas2_home": str(self.home),
					"host": "127.0.0.1",
					"port": base,
					"protocol": "HTTPS",
					"http_enabled": 0,
					"https_enabled": 1,
					"https_port": base,
					"mdn_http_enabled": 0,
					"mdn_https_enabled": 1,
					"mdn_https_port": base + 1,
					"status": "Inactive",
				}
			).insert(ignore_permissions=True)

		self.instance = frappe.get_doc(
			{
				"doctype": "OpenAS2 Instance",
				"instance_name": f"Mon Broker {self.suffix}",
				"instance_type": "Broker",
				"as2_id": self.local_id,
				"openas2_home": str(self.home),
				"host": "127.0.0.1",
				"port": 10443,
				"protocol": "HTTPS",
				"http_enabled": 0,
				"https_enabled": 1,
				"https_port": 10443,
				"mdn_http_enabled": 0,
				"mdn_https_enabled": 1,
				"mdn_https_port": 10444,
				"status": "Active",
			}
		)
		self.instance.insert(ignore_permissions=True)

	def tearDown(self):
		self._tmpdir.cleanup()
		super().tearDown()

	def test_message_log_creation(self):
		mon.discover_instance_messages(self.instance)
		count = frappe.db.count("OpenAS2 Message Log", {"instance": self.instance.name})
		self.assertGreater(count, 0)

	def test_inbound_message(self):
		mon.discover_instance_messages(self.instance)
		rows = frappe.get_all(
			"OpenAS2 Message Log",
			filters={"instance": self.instance.name, "direction": "Inbound"},
			fields=["message_id", "status", "transaction_type"],
		)
		self.assertTrue(rows)
		self.assertTrue(any(r.transaction_type in ("990", "204", "210") for r in rows))

	def test_outbound_message(self):
		mon.discover_instance_messages(self.instance)
		rows = frappe.get_all(
			"OpenAS2 Message Log",
			filters={"instance": self.instance.name, "direction": "Outbound"},
			pluck="message_id",
		)
		self.assertTrue(rows)

	def test_filtering(self):
		mon.discover_instance_messages(self.instance)
		data = mon.get_messages(instance=self.instance.name, direction="Outbound")
		self.assertEqual(data["rows"], [])
		self.assertTrue(data.get("error"))
		stored = frappe.get_all(
			"OpenAS2 Message Log",
			filters={"instance": self.instance.name, "direction": "Outbound"},
			pluck="name",
		)
		self.assertTrue(stored)

	def test_transaction_filtering(self):
		mon.discover_instance_messages(self.instance)
		data = mon.get_messages(instance=self.instance.name, transaction_type="204")
		self.assertEqual(data["rows"], [])
		stored = frappe.get_all(
			"OpenAS2 Message Log",
			filters={"instance": self.instance.name, "transaction_type": "204"},
			pluck="name",
		)
		self.assertTrue(stored)

	def test_status_filtering(self):
		mon.discover_instance_messages(self.instance)
		data = mon.get_messages(instance=self.instance.name, status="Failed")
		self.assertEqual(data["rows"], [])
		self.assertTrue(data.get("error"))
		stored = frappe.get_all(
			"OpenAS2 Message Log",
			filters={"instance": self.instance.name, "status": "Failed"},
			pluck="name",
		)
		self.assertTrue(stored)

	def test_duplicate_message(self):
		mid = f"<dup-test-{self.suffix}>"
		name = mon.upsert_message_log(
			self.instance.name,
			{
				"message_id": mid,
				"direction": "Inbound",
				"status": "Duplicate",
				"mdn_status": "Not Required",
				"transaction_type": "204",
				"file_name": "dup_204.edi",
				"source": "OpenAS2 log",
				"timestamp": datetime(2026, 9, 3, 10, 0, 0),
			},
		)
		name2 = mon.upsert_message_log(
			self.instance.name,
			{
				"message_id": mid,
				"direction": "Inbound",
				"status": "Duplicate",
				"source": "OpenAS2 log",
				"timestamp": datetime(2026, 9, 3, 10, 1, 0),
			},
		)
		self.assertEqual(name, name2)
		self.assertEqual(frappe.get_doc("OpenAS2 Message Log", name).status, "Duplicate")

	def test_failed_message(self):
		mon.discover_instance_messages(self.instance)
		failed = frappe.get_all(
			"OpenAS2 Message Log",
			filters={"instance": self.instance.name, "status": "Failed"},
			fields=["error_message", "message_id"],
		)
		self.assertGreater(len(failed), 0)

	def test_missing_log(self):
		for f in (self.home / "logs").glob("*.txt"):
			f.unlink()
		stats = mon.discover_instance_messages(self.instance)
		self.assertTrue(stats["missing_logs"])

	def test_unreadable_log(self):
		bad = self.home / "logs" / "log-20260904.txt"
		bad.write_text("08:00:00.000 [t] ERROR x -- boom\n", encoding="utf-8")
		os.chmod(bad, 0)
		try:
			msgs, orphans = mon.parse_log_file(
				bad,
				home=self.home,
				instance_as2_id=self.local_id,
				known_as2_ids=[self.local_id, self.remote_shipper],
			)
			self.assertTrue(orphans or msgs == {})
		finally:
			os.chmod(bad, stat.S_IRUSR | stat.S_IWUSR)

	def test_sensitive_value_redaction(self):
		text = mon.redact_sensitive("Connection failed password=secret-value storepass=abc")
		self.assertNotIn("secret-value", text)
		self.assertIn("[REDACTED]", text)
		mon.discover_instance_messages(self.instance)
		rows = frappe.get_all(
			"OpenAS2 Message Log",
			filters={"instance": self.instance.name, "status": "Failed"},
			fields=["error_message"],
		)
		blob = " ".join(r.error_message or "" for r in rows)
		self.assertNotIn("secret-value", blob)

	def test_existing_edi_document_linking(self):
		with patch.object(mon, "find_related_edi_document", return_value="EDI-TEST-1"):
			name = mon.upsert_message_log(
				self.instance.name,
				{
					"message_id": f"<edi-link-{self.suffix}>",
					"direction": "Outbound",
					"status": "Success",
					"file_name": "LOAD054_204.edi",
					"transaction_type": "204",
					"source": "OpenAS2 log",
					"timestamp": datetime(2026, 9, 3, 11, 0, 0),
				},
			)
		doc = frappe.get_doc("OpenAS2 Message Log", name)
		self.assertEqual(doc.edi_document, "EDI-TEST-1")
		details = mon.get_message_details(name)
		self.assertEqual(details["edi_document"], "EDI-TEST-1")

	def test_read_only_behavior(self):
		before = {str(p): p.read_bytes() for p in self.home.rglob("*") if p.is_file()}
		before_logs = frappe.db.count("OpenAS2 Message Log", {"instance": self.instance.name})
		with patch(
			"openas2_manager.openas2.tms_edi.sync_all_tms_edi_documents",
			return_value=[{"edi_documents": 0}],
		):
			mon.refresh_monitoring(self.instance.name)
		for path, content in before.items():
			self.assertEqual(Path(path).read_bytes(), content)
		self.assertEqual(
			frappe.db.count("OpenAS2 Message Log", {"instance": self.instance.name}),
			before_logs,
		)
		# Company roles receive write through Custom DocPerm in seed_company_access.
		# Once those rows exist, get_meta hides the standard System Manager rule.
		# The DocType permission itself stays read-only.
		standard = frappe.get_all(
			"DocPerm",
			filters={"parent": "OpenAS2 Message Log", "role": "System Manager", "permlevel": 0},
			fields=["read", "write", "create"],
		)
		self.assertTrue(standard)
		self.assertTrue(all(int(row.read or 0) == 1 for row in standard))
		self.assertTrue(all(int(row.write or 0) == 0 and int(row.create or 0) == 0 for row in standard))

	def test_refresh_rereads_database_and_does_not_scan_files(self):
		before = frappe.db.count("OpenAS2 Message Log", {"instance": self.instance.name})
		with (
			patch(
				"openas2_manager.openas2.remote_tracking.list_live_messages",
				return_value={"rows": [{"name": "remote:1"}], "count": 1},
			) as listed,
			patch(
				"openas2_manager.openas2.remote_tracking.refresh_edi_card_counts",
				return_value={"ok": True},
			) as edi_refresh,
			patch(
				"openas2_manager.openas2.tms_edi.sync_all_tms_edi_documents",
				return_value=[{"edi_documents": 2}],
			) as tms,
			patch.object(mon, "discover_instance_messages") as discover,
		):
			result = mon.refresh_monitoring(self.instance.name)
		self.assertTrue(result["ok"])
		self.assertNotIn("error", result)
		self.assertIn("OpenAS2 database", result["message"])
		listed.assert_called_once()
		edi_refresh.assert_called_once()
		tms.assert_not_called()
		discover.assert_not_called()
		self.assertEqual(
			frappe.db.count("OpenAS2 Message Log", {"instance": self.instance.name}),
			before,
		)

	def test_refresh_database_failure_is_not_success(self):
		with (
			patch("openas2_manager.openas2.remote_tracking.list_live_messages", return_value=None),
			patch(
				"openas2_manager.openas2.tms_edi.sync_all_tms_edi_documents",
				return_value=[{"edi_documents": 1}],
			),
			patch.object(mon, "discover_instance_messages") as discover,
		):
			result = mon.refresh_monitoring(self.instance.name)
		self.assertFalse(result["ok"])
		self.assertEqual(result["error"], "The OpenAS2 database could not be read.")
		discover.assert_not_called()


if __name__ == "__main__":
	unittest.main()
