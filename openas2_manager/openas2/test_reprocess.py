# Copyright (c) 2026, Lakshana and contributors
# For license information, please see license.txt

"""Reprocess queues a new outbox file and leaves the original message alone."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from openas2_manager.openas2.reprocess import (
	assess_reprocess,
	perform_reprocess,
	queue_outbound_files,
)
from openas2_manager.openas2.remote_tracking import RemoteAccessDenied
from openas2_manager.openas2.test_x12_json import _interchange, _txn

PAGE_JS = (
	Path(__file__).resolve().parents[1]
	/ "openas2_manager"
	/ "page"
	/ "openas2_messages"
	/ "openas2_messages.js"
)


def _edi(code: str = "204") -> str:
	return _interchange(_txn(code, ["B2**SCAC**LOAD1"]))


def _detail(**overrides) -> dict:
	row = {
		"direction": "Outbound",
		"status": "Sent",
		"instance": "OpenAS2-A",
		"remote_as2_id": "BROKER_AS2",
		"local_as2_id": "SHIPPER_AS2",
	}
	row.update(overrides)
	return row


class TestAssessReprocess(unittest.TestCase):
	def test_rejects_missing_inbound_queued_duplicate_and_non_edi(self):
		edi = _edi()
		payload = {"available": True, "payload": edi}
		self.assertIn("not found", assess_reprocess(None, payload)[0])
		self.assertIn("outbound", assess_reprocess(_detail(direction="Inbound"), payload)[0])
		self.assertIn("already queued", assess_reprocess(_detail(status="Queued"), payload)[0])
		self.assertIn("Duplicate", assess_reprocess(_detail(status="Duplicate"), payload)[0])
		self.assertIn("does not contain", assess_reprocess(_detail(), {"available": False, "reason": "not_edi"})[0])
		self.assertEqual(assess_reprocess(_detail(), payload)[1], [edi])


class TestQueueOutboundFiles(unittest.TestCase):
	def setUp(self):
		self.tmp = tempfile.TemporaryDirectory()
		self.home = Path(self.tmp.name)
		self.outbox = self.home / "data" / "outbox" / "BROKER_AS2"
		self.outbox.mkdir(parents=True)
		self.original = self.outbox / "already-there.edi"
		self.original.write_text("KEEP", encoding="utf-8")

	def tearDown(self):
		self.tmp.cleanup()

	def test_writes_new_files_and_keeps_the_original(self):
		first = _edi("204")
		second = _edi("214")
		count = queue_outbound_files(self.home, "BROKER_AS2", [first, second], "42-20261021120000000000")
		self.assertEqual(count, 2)
		self.assertEqual((self.outbox / "reprocess-42-20261021120000000000-1.edi").read_text(encoding="utf-8"), first)
		self.assertEqual((self.outbox / "reprocess-42-20261021120000000000-2.edi").read_text(encoding="utf-8"), second)
		self.assertEqual(self.original.read_text(encoding="utf-8"), "KEEP")

	def test_does_not_create_a_missing_outbox(self):
		missing = self.home / "data" / "outbox" / "NO_SUCH"
		with self.assertRaises(FileNotFoundError):
			queue_outbound_files(self.home, "NO_SUCH", [_edi()], "7-20261021120000000000")
		self.assertFalse(missing.exists())

	def test_rejects_parent_directory_receiver_ids(self):
		before = {path.name for path in self.home.rglob("*")}
		with self.assertRaises(ValueError):
			queue_outbound_files(self.home, "..", [_edi()], "7-20261021120000000000")
		self.assertEqual({path.name for path in self.home.rglob("*")}, before)

	def test_does_not_overwrite_an_existing_queue_file(self):
		name = "reprocess-9-20261021120000000000-1.edi"
		target = self.outbox / name
		target.write_text("ORIGINAL", encoding="utf-8")
		with self.assertRaises(FileExistsError):
			queue_outbound_files(self.home, "BROKER_AS2", [_edi()], "9-20261021120000000000")
		self.assertEqual(target.read_text(encoding="utf-8"), "ORIGINAL")


class TestReprocessMessage(unittest.TestCase):
	def setUp(self):
		self.tmp = tempfile.TemporaryDirectory()
		self.home = Path(self.tmp.name)
		self.outbox = self.home / "data" / "outbox" / "BROKER_AS2"
		self.outbox.mkdir(parents=True)

	def tearDown(self):
		self.tmp.cleanup()

	def _call(self, detail, payload, receiver_dir=True):
		if not receiver_dir and self.outbox.exists():
			self.outbox.rmdir()
		instance = SimpleNamespace(
			name="OpenAS2-A",
			as2_id="SHIPPER_AS2",
			openas2_home=str(self.home),
			inbox_path="",
			outbox_path="",
		)
		with (
			patch(
				"openas2_manager.openas2.remote_tracking.remote_message_details",
				return_value=detail,
			),
			patch(
				"openas2_manager.openas2.remote_tracking.remote_message_payload",
				return_value=payload,
			) as payload_call,
			patch("openas2_manager.access.assert_instance_access"),
			patch("openas2_manager.openas2.reprocess.frappe.get_doc", return_value=instance),
		):
			result = perform_reprocess("remote:42")
		return result, payload_call

	def test_queues_the_selected_message_without_changing_it(self):
		edi = _edi()
		original_payload = {"available": True, "payload": edi}
		result, payload_call = self._call(_detail(), original_payload)
		self.assertTrue(result["ok"])
		self.assertEqual(result["queued"], 1)
		self.assertIn("not changed", result["message"])
		queued = list(self.outbox.glob("reprocess-42-*.edi"))
		self.assertEqual(len(queued), 1)
		self.assertEqual(queued[0].read_text(encoding="utf-8"), edi)
		self.assertEqual(original_payload["payload"], edi)
		payload_call.assert_called_once_with("remote:42", full=True)

	def test_inbound_and_missing_messages_are_not_queued(self):
		inbound, _payload_call = self._call(
			_detail(direction="Inbound"),
			{"available": True, "payload": _edi()},
		)
		self.assertFalse(inbound["ok"])
		self.assertIn("outbound", inbound["message"])
		self.assertEqual(list(self.outbox.glob("reprocess-*.edi")), [])

		missing, payload_call = self._call(None, {"available": True, "payload": _edi()})
		self.assertFalse(missing["ok"])
		self.assertIn("not found", missing["message"])
		payload_call.assert_not_called()
		self.assertFalse(perform_reprocess("MSG-LOG-1")["ok"])

	def test_missing_outbox_is_reported(self):
		result, _payload_call = self._call(_detail(), {"available": True, "payload": _edi()}, receiver_dir=False)
		self.assertFalse(result["ok"])
		self.assertIn("outbox", result["message"])
		self.assertFalse(self.outbox.exists())

	def test_access_denied_is_not_reported_as_success(self):
		with (
			patch(
				"openas2_manager.openas2.remote_tracking.remote_message_details",
				side_effect=RemoteAccessDenied(),
			),
			patch(
				"openas2_manager.openas2.reprocess.frappe.throw",
				side_effect=PermissionError("denied"),
			),
		):
			with self.assertRaises(PermissionError):
				perform_reprocess("remote:42")
		self.assertEqual(list(self.outbox.glob("reprocess-*.edi")), [])


class TestReprocessButton(unittest.TestCase):
	def test_button_sits_beside_download_and_calls_the_backend(self):
		text = PAGE_JS.read_text(encoding="utf-8")
		download = text.index('class="oa2-payload-download-btn"')
		reprocess = text.index('class="oa2-payload-reprocess"')
		copy = text.index('class="oa2-payload-copy"')
		self.assertLess(download, reprocess)
		self.assertLess(reprocess, copy)
		self.assertIn("openas2_manager.openas2.reprocess.reprocess_message", text)
		self.assertIn("This transaction will be processed again.", text)
		self.assertIn("Reprocessing", text)
		self.assertIn("_reprocess_running", text)
