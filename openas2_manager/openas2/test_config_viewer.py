# Copyright (c) 2026, Lakshana and contributors
# For license information, please see license.txt

import tempfile
from pathlib import Path
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from openas2_manager.openas2 import config_viewer as cv


SAMPLE_CONFIG = """<?xml version="1.0" encoding="UTF-8"?>
<openas2>
  <properties
    as2_keystore="%home%/broker_as2.p12"
    as2_keystore_password="broker123"
    ssl_keystore_password="testas2"
    module.AS2ReceiverModule.http.enabled="true"
    module.AS2ReceiverModule.http.port="10080"
    module.AS2ReceiverModule.https.enabled="true"
    module.AS2ReceiverModule.https.port="10443"
    module.AS2MDNReceiverModule.http.enabled="true"
    module.AS2MDNReceiverModule.http.port="10081"
    module.AS2MDNReceiverModule.https.enabled="true"
    module.AS2MDNReceiverModule.https.port="10444"
    as2_async_mdn_url="http://localhost:10081"
    storageBaseDir="%home%/../data"
    pollerConfigBase.outboxdir="$properties.storageBaseDir$/outbox/$partnership.receiver.as2_id$"
    module.MessageFileModule.filename="$properties.storageBaseDir$/$msg.sender.as2_id$-$msg.receiver.as2_id$/inbox/$msg.headers.message-id$"
  />
  <certificates classname="org.openas2.cert.PKCS12CertificateFactory"
                identifier="as2_certs"
                filename="$properties.as2_keystore$"
                password="$properties.as2_keystore_password$"/>
</openas2>
"""

SAMPLE_PARTNERSHIPS = """<?xml version="1.0" encoding="UTF-8"?>
<partnerships>
  <partner name="Broker" as2_id="BROKER_AS2ID" x509_alias="broker"/>
  <partner name="Carrier" as2_id="CARRIER_AS2ID" x509_alias="carrier"/>
  <partnership name="Broker-to-Carrier">
    <sender name="Broker"/>
    <receiver name="Carrier"/>
    <pollerConfig enabled="true"/>
    <attribute name="as2_url" value="https://localhost:11443"/>
    <attribute name="encrypt" value="3DES"/>
    <attribute name="sign" value="SHA-256"/>
    <attribute name="as2_mdn_to" value="edi@broker.com"/>
    <attribute name="as2_mdn_options" value="signed-receipt-protocol=optional"/>
  </partnership>
</partnerships>
"""


class TestOpenAS2ConfigViewer(FrappeTestCase):
	def tearDown(self):
		frappe.db.rollback()

	def _make_home(self, with_config=True, with_partnerships=True):
		tmp = tempfile.TemporaryDirectory()
		self.addCleanup(tmp.cleanup)
		home = Path(tmp.name)
		(home / "config").mkdir()
		(home / "lib").mkdir()
		(home / "lib" / "openas2-server-4.8.3.jar").write_text("jar", encoding="utf-8")
		if with_config:
			(home / "config" / "config.xml").write_text(SAMPLE_CONFIG, encoding="utf-8")
		if with_partnerships:
			(home / "config" / "partnerships.xml").write_text(SAMPLE_PARTNERSHIPS, encoding="utf-8")
		return home

	def _make_instance(self, home: Path, **overrides):
		doc = frappe.get_doc(
			{
				"doctype": "OpenAS2 Instance",
				"instance_name": overrides.get("instance_name", "Viewer Test Broker"),
				"instance_type": overrides.get("instance_type", "Broker"),
				"as2_id": overrides.get("as2_id", "VIEWER_TEST_BROKER"),
				"host": "localhost",
				"port": 10443,
				"protocol": "HTTPS",
				"openas2_home": str(home),
				"inbox_path": str(home / "data" / "inbox" / "BROKER_AS2ID" / "inbox"),
				"outbox_path": str(home / "data" / "outbox" / "CARRIER_AS2ID"),
				"mdn_enabled": 1,
				"status": "Active",
			}
		)
		doc.insert()
		return doc

	def test_instance_configuration_lookup(self):
		home = self._make_home()
		inst = self._make_instance(home)
		result = cv.get_instance_configuration(inst.name)
		self.assertTrue(result["read_only"])
		self.assertFalse(result["writes_performed"])
		self.assertEqual(result["instance"]["as2_id"], "VIEWER_TEST_BROKER")
		self.assertEqual(result["openas2_version"], "4.8.3")
		self.assertEqual(result["server"]["https_port"], "10443")
		self.assertEqual(result["server"]["http_port"], "10080")
		self.assertEqual(result["certificate"]["keystore_type"], "PKCS12")
		self.assertEqual(result["certificate"]["keystore_name"], "broker_as2.p12")
		self.assertTrue(result["last_read"])
		self.assertTrue(result["configuration_source"])

	def test_missing_config_xml(self):
		home = self._make_home(with_config=False, with_partnerships=True)
		inst = self._make_instance(home, instance_name="Missing Config", as2_id="MISS_CFG")
		result = cv.get_instance_configuration(inst.name)
		self.assertIn("Configuration file not found.", result["errors"])
		self.assertEqual(result["raw"]["config_error"], "Configuration file not found.")

	def test_missing_partnerships_xml(self):
		home = self._make_home(with_config=True, with_partnerships=False)
		inst = self._make_instance(home, instance_name="Missing Partners", as2_id="MISS_PART")
		result = cv.get_instance_configuration(inst.name)
		self.assertIn("Partnership configuration not found.", result["errors"])
		self.assertEqual(result["raw"]["partnerships_error"], "Partnership configuration not found.")

	def test_xml_parsing(self):
		parsed = cv.parse_config_xml(SAMPLE_CONFIG)
		self.assertEqual(parsed["https_port"], "10443")
		self.assertEqual(parsed["http_port"], "10080")
		self.assertEqual(parsed["mdn_https_port"], "10444")
		self.assertEqual(parsed["certificate_factory"], "org.openas2.cert.PKCS12CertificateFactory")
		self.assertEqual(parsed["keystore_type"], "PKCS12")
		self.assertEqual(parsed["properties_safe"]["as2_keystore_password"], cv.REDACTED)

	def test_sensitive_value_redaction(self):
		redacted = cv.redact_xml_text(SAMPLE_CONFIG)
		self.assertNotIn("broker123", redacted)
		self.assertNotIn("testas2", redacted)
		self.assertIn('as2_keystore_password="********"', redacted)
		self.assertIn('ssl_keystore_password="********"', redacted)
		self.assertIn('password="********"', redacted)
		# Non-sensitive values preserved
		self.assertIn('module.AS2ReceiverModule.https.port="10443"', redacted)

	def test_partnership_parsing(self):
		parsed = cv.parse_partnerships_xml(SAMPLE_PARTNERSHIPS, local_as2_id="BROKER_AS2ID")
		self.assertEqual(len(parsed["partners"]), 2)
		self.assertEqual(len(parsed["partnerships"]), 1)
		row = parsed["partnerships"][0]
		self.assertEqual(row["local_as2_id"], "BROKER_AS2ID")
		self.assertEqual(row["remote_as2_id"], "CARRIER_AS2ID")
		self.assertEqual(row["remote_url"], "https://localhost:11443")
		self.assertEqual(row["encryption"], "3DES")
		self.assertEqual(row["signing"], "SHA-256")
		self.assertEqual(row["mdn"], "Enabled")

	def test_read_only_behavior_never_opens_write(self):
		home = self._make_home()
		inst = self._make_instance(home, instance_name="RO Check", as2_id="RO_CHECK")
		opened_modes = []
		real_open = Path.open

		def tracking_open(self, mode="r", *args, **kwargs):
			opened_modes.append(mode)
			if any(c in str(mode) for c in "wax"):
				raise AssertionError(f"Write mode attempted: {mode} on {self}")
			return real_open(self, mode, *args, **kwargs)

		with patch.object(Path, "open", tracking_open):
			result = cv.get_instance_configuration(inst.name)

		self.assertTrue(result["read_only"])
		self.assertFalse(result["writes_performed"])
		self.assertTrue(opened_modes)
		self.assertTrue(all(str(m).startswith("r") and "w" not in str(m) for m in opened_modes))

	def test_derive_home_from_inbox_path(self):
		home = self._make_home()
		inst = self._make_instance(home, instance_name="Derive Home", as2_id="DERIVE_HOME")
		inst.openas2_home = ""
		inst.inbox_path = str(home / "data" / "inbox" / "x" / "inbox")
		inst.save()
		resolved = cv.resolve_openas2_home(inst)
		self.assertEqual(resolved, home)

	def test_payload_has_no_plaintext_passwords(self):
		home = self._make_home()
		inst = self._make_instance(home, instance_name="No Secrets", as2_id="NO_SECRETS")
		result = cv.get_instance_configuration(inst.name)
		blob = frappe.as_json(result)
		self.assertNotIn("broker123", blob)
		self.assertNotIn("testas2", blob)
		self.assertNotIn("BEGIN PRIVATE KEY", blob.upper())
