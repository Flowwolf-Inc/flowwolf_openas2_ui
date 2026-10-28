# Copyright (c) 2026, Lakshana and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class AS2Partner(Document):
	"""Trading partner configuration for central OpenAS2 management.

	This DocType stores partner identity and AS2 connection settings only.
	It does not perform OpenAS2 communication, certificate generation,
	or live connection tests.
	"""

	def validate(self):
		self._normalize_fields()
		self._validate_required_values()
		self._validate_unique_as2_id()
		self._validate_mdn_settings()

	def _normalize_fields(self):
		if self.partner_name:
			self.partner_name = self.partner_name.strip()
		if self.as2_id:
			self.as2_id = self.as2_id.strip()
		if self.as2_url:
			self.as2_url = self.as2_url.strip()

	def _validate_required_values(self):
		if not self.partner_name:
			frappe.throw(frappe._("Partner Name is required."))
		if not self.as2_id:
			frappe.throw(frappe._("AS2 ID is required."))
		if not self.as2_url:
			frappe.throw(frappe._("AS2 URL is required."))
		if not self.partner_type:
			frappe.throw(frappe._("Partner Type is required."))
		if not self.status:
			self.status = "Active"

	def _validate_unique_as2_id(self):
		"""Enforce unique AS2 ID even when renaming is involved."""
		existing = frappe.db.exists(
			"AS2 Partner",
			{"as2_id": self.as2_id, "name": ["!=", self.name or ""]},
		)
		if existing:
			frappe.throw(
				frappe._("AS2 ID {0} is already used by partner {1}.").format(
					frappe.bold(self.as2_id), frappe.bold(existing)
				),
				frappe.DuplicateEntryError,
			)

	def _validate_mdn_settings(self):
		if self.mdn_enabled and not self.mdn_mode:
			frappe.throw(frappe._("MDN Mode is required when MDN is enabled."))
		if not self.mdn_enabled:
			self.mdn_mode = None
