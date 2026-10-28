# Copyright (c) 2026, Lakshana and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import date_diff, getdate, today


class AS2Certificate(Document):
	"""AS2 certificate workflow for own key pairs and partner public exchange.

	Private keys exist only in PKCS12 files on disk. This DocType stores
	metadata, public attachment, and exchange status — never private key PEM.
	"""

	def before_insert(self):
		self._apply_default_owner_type()

	def validate(self):
		self._apply_default_owner_type()
		self._normalize_fields()
		self._validate_required_values()
		self._validate_owner_company_access()
		self._validate_unique_certificate_name()
		self._validate_purpose_rules()
		self._validate_validity_dates()
		self._apply_expiry_status()
		self._update_expiry_info()

	def _apply_default_owner_type(self):
		"""Set Company / TMS from the logged-in company role when missing."""
		from openas2_manager.access import get_user_company_types, is_system_manager

		if self.owner_type:
			return
		if is_system_manager():
			return
		allowed = get_user_company_types()
		if len(allowed) == 1:
			self.owner_type = allowed[0]

	def _normalize_fields(self):
		if self.certificate_name:
			self.certificate_name = self.certificate_name.strip()
		if self.common_name:
			self.common_name = self.common_name.strip()
		if self.x509_alias:
			self.x509_alias = self.x509_alias.strip()
		if self.organization:
			self.organization = self.organization.strip()
		if not self.purpose:
			self.purpose = "Own Key Pair"
		if not self.exchange_status:
			self.exchange_status = "Not Shared"
		if not self.validity_days:
			self.validity_days = 825
		if not self.key_size:
			self.key_size = "2048"

	def _validate_owner_company_access(self):
		"""Company users may only create/edit certificates for their own TMS."""
		from openas2_manager.access import get_user_company_types, is_system_manager

		if is_system_manager():
			return
		allowed = get_user_company_types()
		if not allowed:
			frappe.throw(frappe._("Not permitted to manage AS2 Certificates."), frappe.PermissionError)
		if self.owner_type and self.owner_type not in allowed:
			frappe.throw(
				frappe._("You can only manage certificates for {0}.").format(
					", ".join(allowed)
				),
				frappe.PermissionError,
			)

	def _validate_required_values(self):
		if not self.certificate_name:
			frappe.throw(frappe._("Certificate Name is required."))
		if not self.certificate_type:
			frappe.throw(frappe._("Certificate Type is required."))
		if not self.owner_type:
			frappe.throw(frappe._("Company / TMS is required."))
		if not self.common_name:
			frappe.throw(frappe._("Common Name (CN) is required."))
		if not self.x509_alias:
			frappe.throw(frappe._("X509 Alias is required."))
		if not self.status:
			self.status = "Draft"

	def _validate_unique_certificate_name(self):
		existing = frappe.db.exists(
			"AS2 Certificate",
			{"certificate_name": self.certificate_name, "name": ["!=", self.name or ""]},
		)
		if existing:
			frappe.throw(
				frappe._("Certificate Name {0} is already used by {1}.").format(
					frappe.bold(self.certificate_name), frappe.bold(existing)
				),
				frappe.DuplicateEntryError,
			)

	def _validate_purpose_rules(self):
		if self.purpose == "Partner Public Certificate" and self.private_key_stored:
			frappe.throw(
				frappe._("Partner Public Certificate must not include a private key file.")
			)

	def _validate_validity_dates(self):
		if self.valid_from and self.valid_until:
			if getdate(self.valid_until) < getdate(self.valid_from):
				frappe.throw(frappe._("Valid Until cannot be before Valid From."))

	def _apply_expiry_status(self):
		if self.status in ("Revoked", "Draft"):
			return
		if not self.valid_until:
			return
		if getdate(self.valid_until) < getdate(today()):
			self.status = "Expired"

	def _update_expiry_info(self):
		if self.status == "Revoked":
			self.expiry_info = frappe._("Certificate is revoked.")
			return
		if self.status == "Draft" and not self.valid_until:
			self.expiry_info = frappe._("Draft — generate or import a certificate.")
			return
		if not self.valid_until:
			self.expiry_info = frappe._("No expiry date set.")
			return

		until = getdate(self.valid_until)
		today_date = getdate(today())
		days = date_diff(until, today_date)

		if days < 0:
			self.expiry_info = frappe._("Expired {0} day(s) ago (Valid Until: {1}).").format(
				abs(days), until
			)
		elif days == 0:
			self.expiry_info = frappe._("Expires today ({0}).").format(until)
		elif days <= 30:
			self.expiry_info = frappe._(
				"Expiring soon: {0} day(s) remaining (Valid Until: {1})."
			).format(days, until)
		else:
			self.expiry_info = frappe._("{0} day(s) remaining (Valid Until: {1}).").format(
				days, until
			)
