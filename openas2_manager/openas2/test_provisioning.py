# Copyright (c) 2026, Lakshana and contributors
# For license information, please see license.txt

"""Tests for OpenAS2 instance provisioning (Phase 1).

Never starts OpenAS2, never touches Downloads OpenAS20/A/B.
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from openas2_manager.openas2 import port_allocator
from openas2_manager.openas2 import provisioning as prov
from openas2_manager.openas2.paths import slugify_instance_name


class TestOpenAS2Provisioning(FrappeTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		self._tmpdir = tempfile.TemporaryDirectory()
		self.root = Path(self._tmpdir.name)
		self.instances = self.root / "instances"
		self.runtime = self.root / "runtime"
		self.instances.mkdir()
		self.runtime.mkdir()
		self._patches = [
			patch(
				"openas2_manager.openas2.paths.get_instances_root",
				return_value=self.instances,
			),
			patch(
				"openas2_manager.openas2.paths.get_runtime_root",
				return_value=self.runtime,
			),
			patch(
				"openas2_manager.openas2.provisioning.get_instances_root",
				return_value=self.instances,
			),
			patch(
				"openas2_manager.openas2.provisioning.get_runtime_root",
				return_value=self.runtime,
			),
			patch(
				"openas2_manager.openas2.port_allocator.is_port_available",
				return_value=True,
			),
		]
		for p in self._patches:
			p.start()
		self.addCleanup(self._cleanup)

	def _cleanup(self):
		for p in self._patches:
			p.stop()
		self._tmpdir.cleanup()

	def test_slugify(self):
		self.assertEqual(slugify_instance_name("Broker ABC"), "broker_abc")

	def test_allocate_avoids_static_reserved(self):
		ports = port_allocator.allocate_ports_for_type("Broker")
		self.assertNotIn(ports["http_port"], port_allocator.STATIC_RESERVED_PORTS)
		self.assertNotEqual(ports["http_port"], 10080)
		self.assertNotEqual(ports["https_port"], 10443)

	def test_provision_creates_isolated_layout(self):
		result = prov.provision_openas2_instance(
			instance_name="Broker Phase1 Test",
			instance_type="Broker",
			as2_id="BROKER_PHASE1_TEST",
			mdn_enabled=1,
			host="localhost",
		)
		self.assertEqual(result["result"], "Success")
		self.assertEqual(result["lifecycle_status"], "Stopped")
		self.assertFalse(result["runtime_started"])
		self.assertNotIn("as2_keystore_password", result)
		self.assertNotIn("ssl_password", result)

		home = Path(result["openas2_home"])
		self.assertTrue((home / "config" / "config.xml").is_file())
		self.assertTrue((home / "config" / "partnerships.xml").is_file())
		self.assertTrue((home / "keystore" / "README.txt").is_file())
		self.assertTrue((home / "data" / "inbox").is_dir())
		self.assertTrue((home / "logs").is_dir())
		# No fake PKCS12
		self.assertFalse(list(home.joinpath("keystore").glob("*.p12")))

		config = ET.parse(home / "config" / "config.xml").getroot()
		props = config.find("properties")
		self.assertIsNotNone(props)
		self.assertEqual(props.get("module.AS2ReceiverModule.https.enabled"), "false")
		self.assertEqual(props.get("restapi.command.processor.enabled"), "false")

		doc = frappe.get_doc("OpenAS2 Instance", result["instance"])
		self.assertEqual(doc.lifecycle_status, "Stopped")
		self.assertEqual(doc.provision_source, "Manager Provisioned")
		self.assertEqual(doc.certificate_status, "Deferred")
		self.assertEqual(doc.http_port, result["ports"]["http"])

		# Cleanup doc
		frappe.delete_doc("OpenAS2 Instance", doc.name, force=True, ignore_permissions=True)
		shutil.rmtree(home, ignore_errors=True)

	def test_duplicate_as2_id_rejected(self):
		r1 = prov.provision_openas2_instance(
			instance_name="Broker Dup A",
			instance_type="Broker",
			as2_id="BROKER_DUP_X",
			mdn_enabled=1,
		)
		with self.assertRaises(frappe.DuplicateEntryError):
			prov.provision_openas2_instance(
				instance_name="Broker Dup B",
				instance_type="Broker",
				as2_id="BROKER_DUP_X",
				mdn_enabled=1,
			)
		frappe.delete_doc("OpenAS2 Instance", r1["instance"], force=True, ignore_permissions=True)
		shutil.rmtree(r1["openas2_home"], ignore_errors=True)

	def test_non_manager_denied(self):
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			prov.provision_openas2_instance(
				instance_name="Nope",
				instance_type="Broker",
				as2_id="NOPE",
			)


if __name__ == "__main__":
	unittest.main()
