# Copyright (c) 2026, Lakshana and contributors
# For license information, please see license.txt

"""Unit tests for controlled OpenAS2 restart helper.

These tests never restart real Shipper/Broker/Carrier OpenAS2 installs.
Process control is mocked.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from openas2_manager.openas2 import restart as rs


def _make_fake_linux_home(root: Path) -> Path:
	home = root / "OpenAS2Test"
	(home / "bin").mkdir(parents=True)
	(home / "config").mkdir(parents=True)
	(home / "config" / "config.xml").write_text("<openas2/>", encoding="utf-8")
	(home / "config" / "partnerships.xml").write_text("<partnerships/>", encoding="utf-8")
	script = home / "bin" / rs.ALLOWED_START_SCRIPT
	script.write_text("#!/bin/sh\necho ok\n", encoding="utf-8")
	script.chmod(0o755)
	return home


class TestOpenAS2Restart(FrappeTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		self._tmpdir = tempfile.TemporaryDirectory()
		self.home = _make_fake_linux_home(Path(self._tmpdir.name))
		self.instance = frappe.get_doc(
			{
				"doctype": "OpenAS2 Instance",
				"instance_name": f"Restart Test {frappe.generate_hash(length=6)}",
				"instance_type": "Broker",
				"as2_id": f"RST-{frappe.generate_hash(length=6)}",
				"openas2_home": str(self.home),
				"host": "127.0.0.1",
				"port": 19999,
				"protocol": "HTTP",
				"http_enabled": 1,
				"http_port": 19999,
				"https_enabled": 0,
				"mdn_enabled": 0,
				"mdn_http_enabled": 0,
				"mdn_https_enabled": 0,
				"status": "Active",
			}
		)
		self.instance.insert(ignore_permissions=True)

	def tearDown(self):
		self._tmpdir.cleanup()
		super().tearDown()

	def test_permission_check(self):
		with patch("frappe.get_roles", return_value=["All"]):
			with self.assertRaises(frappe.PermissionError):
				rs.restart_openas2_instance(self.instance.name, confirmed=1)

	def test_confirmation_requirement(self):
		with self.assertRaises(frappe.ValidationError):
			rs.restart_openas2_instance(self.instance.name, confirmed=0)

	def test_unknown_instance(self):
		with self.assertRaises(Exception):
			rs.restart_openas2_instance("Does-Not-Exist-XYZ", confirmed=1)

	def test_missing_openas2_home(self):
		self.instance.db_set("openas2_home", "/tmp/openas2_missing_home_xyz", update_modified=False)
		self.instance.reload()
		result = rs.restart_openas2_instance(self.instance.name, confirmed=1)
		self.assertEqual(result["result"], "Not Available")
		self.assertIn("not found", (result["message"] or "").lower())
		log = frappe.get_doc("OpenAS2 Restart Log", result["restart_log"])
		self.assertEqual(log.result, "Not Available")

	def test_missing_configuration(self):
		(self.home / "config" / "config.xml").unlink()
		result = rs.restart_openas2_instance(self.instance.name, confirmed=1)
		self.assertEqual(result["result"], "Not Available")
		self.assertIn("Configuration file not found", result["message"] or "")

	def test_restart_unavailable_windows_mount(self):
		"""Simulate Windows-mounted install without Linux Java — must not fake restart."""
		with (
			patch.object(rs, "_is_windows_mounted_path", return_value=True),
			patch.object(rs, "_linux_java_available", return_value=False),
		):
			cap = rs.discover_restart_capability(self.instance)
			self.assertFalse(cap["available"])
			result = rs.restart_openas2_instance(self.instance.name, confirmed=1)
		self.assertEqual(result["result"], "Not Available")
		self.assertFalse(result["openas2_restarted"])
		self.assertIn("Manual restart required", result["message"] or "")
		self.assertEqual(result["as2_status"], "Not Verified")
		log = frappe.get_doc("OpenAS2 Restart Log", result["restart_log"])
		self.assertEqual(log.result, "Not Available")

	def test_successful_restart_mocked(self):
		with (
			patch.object(rs, "_is_windows_mounted_path", return_value=False),
			patch.object(rs, "_linux_java_available", return_value=True),
			patch.object(
				rs,
				"_stop_instance",
				return_value={"process_status": "Stopped", "detail": "mocked stop"},
			),
			patch.object(
				rs,
				"_start_instance",
				return_value={"process_status": "Running", "detail": "mocked start", "pid": 4242},
			),
			patch.object(rs, "_check_tcp", return_value="Reachable"),
		):
			result = rs.restart_openas2_instance(self.instance.name, confirmed=1)

		self.assertEqual(result["result"], "Success")
		self.assertEqual(result["process_status"], "Running")
		self.assertEqual(result["tcp_status"], "Reachable")
		self.assertEqual(result["as2_status"], "Not Verified")
		self.assertTrue(result["openas2_restarted"])
		self.assertIn("AS2 Protocol: Not Verified", result["message"])
		log = frappe.get_doc("OpenAS2 Restart Log", result["restart_log"])
		self.assertEqual(log.result, "Success")
		self.assertEqual(log.instance, self.instance.name)
		self.assertEqual(log.requested_by, "Administrator")
		self.assertTrue(log.started_at)
		self.assertTrue(log.completed_at)

	def test_failed_restart(self):
		with (
			patch.object(rs, "_is_windows_mounted_path", return_value=False),
			patch.object(rs, "_linux_java_available", return_value=True),
			patch.object(
				rs,
				"_stop_instance",
				return_value={"process_status": "Stopped", "detail": "ok"},
			),
			patch.object(
				rs,
				"_start_instance",
				return_value={"process_status": "Failed", "detail": "boom", "pid": None},
			),
		):
			result = rs.restart_openas2_instance(self.instance.name, confirmed=1)

		self.assertEqual(result["result"], "Failed")
		self.assertEqual(result["process_status"], "Failed")
		self.assertFalse(result["openas2_restarted"])
		log = frappe.get_doc("OpenAS2 Restart Log", result["restart_log"])
		self.assertEqual(log.result, "Failed")
		self.assertIn("boom", log.error_message or "")

	def test_tcp_verification_not_reachable(self):
		with (
			patch.object(rs, "_is_windows_mounted_path", return_value=False),
			patch.object(rs, "_linux_java_available", return_value=True),
			patch.object(
				rs,
				"_stop_instance",
				return_value={"process_status": "Stopped", "detail": "ok"},
			),
			patch.object(
				rs,
				"_start_instance",
				return_value={"process_status": "Running", "detail": "ok", "pid": 1},
			),
			patch.object(rs, "_check_tcp", return_value="Not Reachable"),
		):
			result = rs.restart_openas2_instance(self.instance.name, confirmed=1)

		self.assertEqual(result["result"], "Failed")
		self.assertEqual(result["process_status"], "Running")
		self.assertEqual(result["tcp_status"], "Not Reachable")
		self.assertEqual(result["as2_status"], "Not Verified")

	def test_audit_log_creation(self):
		with (
			patch.object(rs, "_is_windows_mounted_path", return_value=True),
			patch.object(rs, "_linux_java_available", return_value=False),
		):
			result = rs.restart_openas2_instance(self.instance.name, confirmed=1)
		self.assertTrue(frappe.db.exists("OpenAS2 Restart Log", result["restart_log"]))

	def test_no_arbitrary_command_execution(self):
		"""Start helper must only invoke fixed start-openas2.sh under home."""
		calls = []

		class FakeProc:
			def wait(self, timeout=None):
				return 0

		def fake_popen(argv, **kwargs):
			calls.append((argv, kwargs))
			# Simulate PID file written by start script
			pid_path = self.home / "bin" / rs.ALLOWED_PID_NAME
			pid_path.write_text("12345\n", encoding="utf-8")
			return FakeProc()

		with (
			patch.object(rs, "_is_windows_mounted_path", return_value=False),
			patch.object(rs, "_linux_java_available", return_value=True),
			patch.object(rs, "_stop_instance", return_value={"process_status": "Stopped", "detail": "ok"}),
			patch.object(rs, "_pid_alive", return_value=True),
			patch.object(rs, "_pid_belongs_to_instance", return_value=True),
			patch.object(rs, "_check_tcp", return_value="Reachable"),
			patch("subprocess.Popen", side_effect=fake_popen),
		):
			result = rs.restart_openas2_instance(self.instance.name, confirmed=1)

		self.assertEqual(result["result"], "Success")
		self.assertEqual(len(calls), 1)
		argv, kwargs = calls[0]
		self.assertEqual(Path(argv[0]).name, "start-openas2.sh")
		self.assertEqual(len(argv), 1)  # no user EXTRA args
		self.assertFalse(kwargs.get("shell"))
		self.assertTrue(str(argv[0]).startswith(str(self.home.resolve())))

	def test_no_secret_exposure(self):
		cap = rs.get_restart_capability(self.instance.name)
		blob = frappe.as_json(cap).lower()
		for banned in ("password", "private key", "-storepass", "secret"):
			self.assertNotIn(banned, blob)
		# Must not dump raw absolute home in capability API when converting displays
		# (home key stripped)
		self.assertNotIn("home", cap)

	def test_no_automatic_restart_after_apply(self):
		from openas2_manager.openas2 import partnership_config as pc

		suffix = frappe.generate_hash(length=4)
		local = frappe.get_doc(
			{
				"doctype": "AS2 Partner",
				"partner_name": f"Local-{suffix}",
				"partner_type": "Broker",
				"as2_id": f"LOCAL_{suffix}",
				"as2_url": "http://127.0.0.1:1/as2",
				"status": "Active",
			}
		).insert(ignore_permissions=True)
		remote = frappe.get_doc(
			{
				"doctype": "AS2 Partner",
				"partner_name": f"Remote-{suffix}",
				"partner_type": "Shipper",
				"as2_id": f"REMOTE_{suffix}",
				"as2_url": "http://127.0.0.1:1/as2",
				"status": "Active",
			}
		).insert(ignore_permissions=True)
		doc = frappe.get_doc(
			{
				"doctype": "OpenAS2 Partnership",
				"instance": self.instance.name,
				"partnership_name": f"No-Auto-Restart-{suffix}",
				"local_partner": local.name,
				"remote_partner": remote.name,
				"local_partner_name": local.partner_name,
				"remote_partner_name": remote.partner_name,
				"local_as2_id": local.as2_id,
				"remote_as2_id": remote.as2_id,
				"local_x509_alias": "broker",
				"remote_x509_alias": "shipper",
				"remote_url": "http://127.0.0.1:1/as2",
				"status": "Draft",
			}
		)
		doc.insert(ignore_permissions=True)
		with patch.object(rs, "restart_openas2_instance") as mock_restart:
			preview = pc.preview_partnership_change(doc.name)
			applied = pc.apply_configuration_change(preview["configuration_change"])
			mock_restart.assert_not_called()
		self.assertFalse(preview["restart_openas2"])
		self.assertFalse(applied["openas2_restarted"])
		self.assertTrue(applied.get("offer_restart"))

	def test_start_rejects_non_approved_script_name(self):
		evil = self.home / "bin" / "evil.sh"
		evil.write_text("#!/bin/sh\necho no\n", encoding="utf-8")
		with self.assertRaises(Exception):
			rs._start_instance(self.home, evil)


if __name__ == "__main__":
	unittest.main()
