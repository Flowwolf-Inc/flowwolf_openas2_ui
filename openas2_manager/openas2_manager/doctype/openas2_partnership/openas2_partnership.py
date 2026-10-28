# Copyright (c) 2026, Lakshana and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class OpenAS2Partnership(Document):
	"""Proposed OpenAS2 partnership configuration (Frappe-side).

	Saving this DocType does **not** write partnerships.xml.
	Use Preview / Apply on the OpenAS2 Partnerships page.
	"""

	def before_naming(self):
		# Autoname uses partnership_name before validate — fill from partners first.
		self._normalize()
		self._apply_partner_defaults()
		self._suggest_partnership_name()

	def validate(self):
		self._normalize()
		self._apply_partner_defaults()
		self._suggest_partnership_name()
		self._validate_required()
		self._validate_partners_distinct()
		self._validate_unique_name()
		self._validate_remote_url()
		self._validate_mdn()
		self._validate_instance()
		self._update_direction_hint()

	def _normalize(self):
		for field in (
			"partnership_name",
			"local_as2_id",
			"remote_as2_id",
			"remote_url",
			"local_partner_name",
			"remote_partner_name",
			"local_x509_alias",
			"remote_x509_alias",
		):
			value = getattr(self, field, None)
			if value:
				setattr(self, field, value.strip())

	def _apply_partner_defaults(self):
		"""Fill identity fields from linked AS2 Partner / Certificate when empty."""
		if self.local_partner and frappe.db.exists("AS2 Partner", self.local_partner):
			local = frappe.get_cached_doc("AS2 Partner", self.local_partner)
			if not self.local_partner_name:
				self.local_partner_name = local.partner_name
			if not self.local_as2_id:
				self.local_as2_id = local.as2_id
			if not self.local_x509_alias and local.certificate:
				alias = frappe.db.get_value("AS2 Certificate", local.certificate, "x509_alias")
				if alias:
					self.local_x509_alias = alias
			elif not self.local_x509_alias and local.partner_type:
				self.local_x509_alias = str(local.partner_type).lower()

		if self.remote_partner and frappe.db.exists("AS2 Partner", self.remote_partner):
			remote = frappe.get_cached_doc("AS2 Partner", self.remote_partner)
			if not self.remote_partner_name:
				self.remote_partner_name = remote.partner_name
			if not self.remote_as2_id:
				self.remote_as2_id = remote.as2_id
			if not self.remote_url:
				self.remote_url = remote.as2_url
			if not self.remote_x509_alias and remote.certificate:
				alias = frappe.db.get_value("AS2 Certificate", remote.certificate, "x509_alias")
				if alias:
					self.remote_x509_alias = alias
			elif not self.remote_x509_alias and remote.partner_type:
				self.remote_x509_alias = str(remote.partner_type).lower()

			# Prefer remote partner security defaults only when creating / unset
			if self.is_new():
				self.encryption_enabled = 1 if remote.encryption_enabled else self.encryption_enabled
				self.signing_enabled = 1 if remote.signing_enabled else self.signing_enabled
				if remote.mdn_enabled:
					self.mdn_enabled = 1
					if remote.mdn_mode:
						self.mdn_mode = remote.mdn_mode

		if self.local_certificate and frappe.db.exists("AS2 Certificate", self.local_certificate):
			alias = frappe.db.get_value("AS2 Certificate", self.local_certificate, "x509_alias")
			if alias:
				self.local_x509_alias = alias

		if self.remote_certificate and frappe.db.exists("AS2 Certificate", self.remote_certificate):
			alias = frappe.db.get_value("AS2 Certificate", self.remote_certificate, "x509_alias")
			if alias:
				self.remote_x509_alias = alias

	def _suggest_partnership_name(self):
		if self.partnership_name:
			return
		if self.local_partner_name and self.remote_partner_name:
			self.partnership_name = f"{self.local_partner_name}-to-{self.remote_partner_name}"

	def _validate_required(self):
		checks = [
			("partnership_name", "Partnership Name"),
			("instance", "OpenAS2 Instance"),
			("local_partner", "Local Partner"),
			("remote_partner", "Remote Partner"),
			("local_as2_id", "Local AS2 ID"),
			("remote_as2_id", "Remote AS2 ID"),
			("remote_url", "Remote AS2 URL"),
			("local_partner_name", "Local Partner Name"),
			("remote_partner_name", "Remote Partner Name"),
			("local_x509_alias", "Local X509 Alias"),
			("remote_x509_alias", "Remote X509 Alias"),
		]
		for field, label in checks:
			if not getattr(self, field, None):
				frappe.throw(frappe._("{0} is required.").format(label))
		if not self.status:
			self.status = "Draft"

	def _validate_partners_distinct(self):
		if self.local_partner and self.remote_partner and self.local_partner == self.remote_partner:
			frappe.throw(frappe._("Local Partner and Remote Partner must be different."))
		if (
			self.local_as2_id
			and self.remote_as2_id
			and self.local_as2_id == self.remote_as2_id
		):
			frappe.throw(frappe._("Local AS2 ID and Remote AS2 ID must be different."))

	def _validate_unique_name(self):
		existing = frappe.db.exists(
			"OpenAS2 Partnership",
			{"partnership_name": self.partnership_name, "name": ["!=", self.name or ""]},
		)
		if existing:
			frappe.throw(
				frappe._("Partnership Name {0} already exists.").format(
					frappe.bold(self.partnership_name)
				),
				frappe.DuplicateEntryError,
			)

	def _validate_remote_url(self):
		url = (self.remote_url or "").lower()
		if not (url.startswith("http://") or url.startswith("https://")):
			frappe.throw(frappe._("Remote AS2 URL must start with http:// or https://."))

	def _validate_mdn(self):
		if self.mdn_enabled and not self.mdn_mode:
			frappe.throw(frappe._("MDN Mode is required when MDN is enabled."))
		if not self.mdn_enabled:
			self.mdn_mode = None

	def _validate_instance(self):
		if not frappe.db.exists("OpenAS2 Instance", self.instance):
			frappe.throw(frappe._("OpenAS2 Instance {0} does not exist.").format(self.instance))

	def _update_direction_hint(self):
		local = self.local_partner_name or "Local"
		remote = self.remote_partner_name or "Remote"
		self.direction_hint = frappe._(
			"Creates outbound {0} → {1}. Save stores the draft in Frappe only. "
			"Use OpenAS2 Partnerships → Preview / Apply to write partnerships.xml."
		).format(local, remote)
