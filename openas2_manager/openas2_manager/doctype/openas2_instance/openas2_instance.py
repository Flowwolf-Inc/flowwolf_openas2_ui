# Copyright (c) 2026, Lakshana and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class OpenAS2Instance(Document):
	"""OpenAS2 server instance configuration for the central management UI.

	Stores listener, MDN, and keystore metadata. Manager-provisioned instances
	also receive allocated ports and filesystem homes. Does not exchange
	EDI/MDN or start Java runtimes from DocType save.
	"""

	def validate(self):
		self._normalize_fields()
		self._validate_required_values()
		self._validate_unique_fields()
		self._sync_primary_listener()
		self._validate_port()
		self._validate_allocated_ports()
		self._validate_listener_ports()
		self._build_published_as2_url()

	def _normalize_fields(self):
		if self.instance_name:
			self.instance_name = self.instance_name.strip()
		if self.as2_id:
			self.as2_id = self.as2_id.strip()
		if self.host:
			self.host = self.host.strip()
		if self.inbox_path:
			self.inbox_path = self.inbox_path.strip()
		if self.outbox_path:
			self.outbox_path = self.outbox_path.strip()
		if self.openas2_home:
			self.openas2_home = self.openas2_home.strip()
		if self.instance_slug:
			self.instance_slug = self.instance_slug.strip()
		if self.as2_keystore_path:
			self.as2_keystore_path = self.as2_keystore_path.strip()
		if self.ssl_keystore_path:
			self.ssl_keystore_path = self.ssl_keystore_path.strip()
		if self.x509_alias:
			self.x509_alias = self.x509_alias.strip()
		if self.async_mdn_url:
			self.async_mdn_url = self.async_mdn_url.strip()
		if not self.lifecycle_status:
			self.lifecycle_status = "Unknown"
		if not self.provision_source:
			self.provision_source = "External"
		if not self.control_mode:
			self.control_mode = "none"
		if not self.certificate_status:
			self.certificate_status = "Unknown"
		if not self.mdn_mode:
			self.mdn_mode = "Synchronous"
		# Keep master MDN flag aligned with listener toggles.
		if self.mdn_http_enabled or self.mdn_https_enabled:
			self.mdn_enabled = 1

	def _validate_required_values(self):
		if not self.instance_name:
			frappe.throw(frappe._("Name is required."))
		if not self.instance_type:
			frappe.throw(frappe._("Instance Type is required."))
		if not self.as2_id:
			frappe.throw(frappe._("AS2 ID is required."))
		if not self.host:
			frappe.throw(frappe._("Host is required."))
		if not self.protocol:
			self.protocol = "HTTPS"
		if not self.status:
			self.status = "Active"
		if not self.connection_status:
			self.connection_status = "Unknown"
		if not self.http_enabled and not self.https_enabled:
			frappe.throw(frappe._("Enable at least one of HTTP or HTTPS."))
		if self.mdn_mode == "Asynchronous" and self.mdn_enabled:
			if not (self.mdn_http_enabled or self.mdn_https_enabled):
				frappe.throw(
					frappe._("Asynchronous MDN requires MDN HTTP and/or MDN HTTPS enabled.")
				)

	def _sync_primary_listener(self):
		"""Keep legacy primary port/protocol in sync with enable toggles."""
		if self.protocol == "HTTPS" and self.https_enabled and self.https_port:
			self.port = int(self.https_port)
		elif self.protocol == "HTTP" and self.http_enabled and self.http_port:
			self.port = int(self.http_port)
		elif self.https_enabled and self.https_port:
			self.protocol = "HTTPS"
			self.port = int(self.https_port)
		elif self.http_enabled and self.http_port:
			self.protocol = "HTTP"
			self.port = int(self.http_port)

	def _build_published_as2_url(self):
		host = self.host or "localhost"
		scheme = (self.protocol or "HTTPS").lower()
		port = self.port
		if not port:
			self.published_as2_url = ""
			return
		default_port = 443 if scheme == "https" else 80
		if int(port) == default_port:
			self.published_as2_url = f"{scheme}://{host}"
		else:
			self.published_as2_url = f"{scheme}://{host}:{int(port)}"

	def _validate_unique_fields(self):
		existing_name = frappe.db.exists(
			"OpenAS2 Instance",
			{"instance_name": self.instance_name, "name": ["!=", self.name or ""]},
		)
		if existing_name:
			frappe.throw(
				frappe._("Name {0} is already used by {1}.").format(
					frappe.bold(self.instance_name), frappe.bold(existing_name)
				),
				frappe.DuplicateEntryError,
			)

		existing_as2 = frappe.db.exists(
			"OpenAS2 Instance",
			{"as2_id": self.as2_id, "name": ["!=", self.name or ""]},
		)
		if existing_as2:
			frappe.throw(
				frappe._("AS2 ID {0} is already used by instance {1}.").format(
					frappe.bold(self.as2_id), frappe.bold(existing_as2)
				),
				frappe.DuplicateEntryError,
			)

		if self.instance_slug:
			existing_slug = frappe.db.exists(
				"OpenAS2 Instance",
				{"instance_slug": self.instance_slug, "name": ["!=", self.name or ""]},
			)
			if existing_slug:
				frappe.throw(
					frappe._("Instance slug {0} is already used by {1}.").format(
						frappe.bold(self.instance_slug), frappe.bold(existing_slug)
					),
					frappe.DuplicateEntryError,
				)

	def _validate_port(self):
		try:
			port = int(self.port)
		except (TypeError, ValueError):
			frappe.throw(frappe._("Primary Port must be an integer."))
		if port < 1 or port > 65535:
			frappe.throw(frappe._("Primary Port must be between 1 and 65535."))
		self.port = port

	def _validate_allocated_ports(self):
		for field in (
			"http_port",
			"https_port",
			"mdn_http_port",
			"mdn_https_port",
			"health_port",
			"tracking_port",
		):
			val = getattr(self, field, None)
			if val in (None, ""):
				continue
			try:
				port = int(val)
			except (TypeError, ValueError):
				frappe.throw(frappe._("{0} must be an integer.").format(field))
			if port < 1 or port > 65535:
				frappe.throw(frappe._("{0} must be between 1 and 65535.").format(field))
			setattr(self, field, port)

	def _validate_listener_ports(self):
		if self.http_enabled and not self.http_port:
			frappe.throw(frappe._("HTTP Port is required when Enable HTTP is checked."))
		if self.https_enabled and not self.https_port:
			frappe.throw(frappe._("HTTPS Port is required when Enable HTTPS is checked."))
		if self.mdn_enabled and self.mdn_http_enabled and not self.mdn_http_port:
			frappe.throw(frappe._("MDN HTTP Port is required when Enable MDN HTTP is checked."))
		if self.mdn_enabled and self.mdn_https_enabled and not self.mdn_https_port:
			frappe.throw(frappe._("MDN HTTPS Port is required when Enable MDN HTTPS is checked."))


@frappe.whitelist()
def request_keystore_setup(instance_name: str | None = None) -> dict:
	"""Desk action for keystore creation — integration pending (no fake certs)."""
	from openas2_manager.access import assert_instance_access
	from openas2_manager.certificates.generation import inspect_generation_capability

	if instance_name:
		assert_instance_access(instance_name)

	capability = inspect_generation_capability()
	return {
		"ok": False,
		"pending": True,
		"message": (
			"Keystore generation is pending integration with Java keytool.\n\n"
			"Fill AS2 Keystore Path, X509 Alias, and (optionally) password on this form. "
			"Today Sync from config.xml reads existing keystore settings from OpenAS2; "
			"generation/import into the live .p12 is not enabled yet.\n\n"
			f"Linux keytool: {capability.get('linux_keytool') or 'not found'}\n"
			f"Windows keytool: {capability.get('windows_keytool') or 'not found'}"
		),
	}