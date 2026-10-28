# Copyright (c) 2026, Lakshana and contributors
# For license information, please see license.txt

"""Unit tests for Phase 2 runtime control (mocked Agent; no real process kills)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from openas2_manager.openas2 import runtime_control as rc


class TestOpenAS2RuntimeControl(FrappeTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		self._tmpdir = tempfile.TemporaryDirectory()
		self.root = Path(self._tmpdir.name)
		self.instances = self.root / "instances"
		slug = f"broker_rt_{frappe.generate_hash(length=8).lower()}"
		self.home = self.instances / slug
		(self.home / "config").mkdir(parents=True)
		(self.home / "keystore").mkdir(parents=True)
		(self.home / "logs").mkdir(parents=True)
		(self.home / "config" / "config.xml").write_text("<openas2/>", encoding="utf-8")

		self.instance = frappe.get_doc(
			{
				"doctype": "OpenAS2 Instance",
				"instance_name": f"RT Test {frappe.generate_hash(length=6)}",
				"instance_type": "Broker",
				"as2_id": f"RT-{frappe.generate_hash(length=6)}",
				"host": "127.0.0.1",
				"port": 18082,
				"http_port": 18082,
				"protocol": "HTTP",
				"status": "Active",
				"lifecycle_status": "Stopped",
				"provision_source": "Manager Provisioned",
				"control_mode": "agent",
				"instance_slug": slug,
				"openas2_home": str(self.home),
				"windows_home": str(self.home),
			}
		)
		self.instance.insert(ignore_permissions=True)

		self._patches = [
			patch(
				"openas2_manager.openas2.runtime_control.get_instances_root",
				return_value=self.instances,
			),
			patch(
				"openas2_manager.openas2.paths.get_instances_root",
				return_value=self.instances,
			),
			patch.object(rc, "agent_token", return_value="test-token"),
			patch.object(rc, "agent_url", return_value="http://127.0.0.1:9475"),
		]
		for p in self._patches:
			p.start()
		self.addCleanup(self._cleanup)

	def _cleanup(self):
		for p in self._patches:
			p.stop()
		self._tmpdir.cleanup()

	def test_manifest_written_under_home(self):
		path = rc.write_manager_manifest(self.instance)
		self.assertTrue(path.is_file())
		data = json.loads(path.read_text(encoding="utf-8"))
		self.assertEqual(data["slug"], self.instance.instance_slug)
		self.assertEqual(data["http_port"], 18082)

	def test_path_traversal_rejected(self):
		evil = frappe.get_doc(
			{
				"doctype": "OpenAS2 Instance",
				"instance_name": f"Evil {frappe.generate_hash(length=6)}",
				"instance_type": "Broker",
				"as2_id": f"EVIL-{frappe.generate_hash(length=6)}",
				"host": "127.0.0.1",
				"port": 18083,
				"protocol": "HTTP",
				"status": "Active",
				"provision_source": "Manager Provisioned",
				"instance_slug": "evil",
				"openas2_home": "/tmp/not-under-instances",
			}
		)
		evil.insert(ignore_permissions=True)
		with self.assertRaises(frappe.ValidationError):
			rc.write_manager_manifest(evil)
		frappe.delete_doc("OpenAS2 Instance", evil.name, force=True, ignore_permissions=True)

	def test_legacy_instance_blocked(self):
		legacy = frappe.get_doc(
			{
				"doctype": "OpenAS2 Instance",
				"instance_name": f"Legacy {frappe.generate_hash(length=6)}",
				"instance_type": "Broker",
				"as2_id": f"LEG-{frappe.generate_hash(length=6)}",
				"host": "127.0.0.1",
				"port": 10080,
				"protocol": "HTTPS",
				"status": "Active",
				"provision_source": "External",
				"openas2_home": str(self.home),
				"instance_slug": "legacy",
			}
		)
		legacy.insert(ignore_permissions=True)
		with self.assertRaises(frappe.ValidationError):
			rc.runtime_status(legacy.name)
		frappe.delete_doc("OpenAS2 Instance", legacy.name, force=True, ignore_permissions=True)

	def test_start_requires_confirmation(self):
		with self.assertRaises(frappe.ValidationError):
			rc.runtime_control(self.instance.name, "start", confirmed=0)

	def test_start_success_updates_lifecycle(self):
		fake = {
			"ok": True,
			"agent": {
				"ok": True,
				"lifecycle_status": "Running",
				"pid": 4242,
				"process_running": True,
				"port_listening": True,
				"openas2_health": "Process+Port OK",
			},
		}
		with patch.object(rc, "call_agent", return_value=fake):
			result = rc.runtime_control(self.instance.name, "start", confirmed=1)
		self.assertTrue(result["ok"])
		self.instance.reload()
		self.assertEqual(self.instance.lifecycle_status, "Running")
		self.assertEqual(self.instance.runtime_pid, 4242)

	def test_start_failure_sets_failed(self):
		fake = {"ok": False, "error": "keystore missing"}
		with patch.object(rc, "call_agent", return_value=fake):
			result = rc.runtime_control(self.instance.name, "start", confirmed=1)
		self.assertFalse(result["ok"])
		self.instance.reload()
		self.assertEqual(self.instance.lifecycle_status, "Failed")

	def test_unauthorized(self):
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			rc.runtime_control(self.instance.name, "start", confirmed=1)

	def test_invalid_action(self):
		with self.assertRaises(frappe.ValidationError):
			rc.runtime_control(self.instance.name, "explode", confirmed=1)


if __name__ == "__main__":
	unittest.main()
