# Copyright (c) 2026, Lakshana and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class OpenAS2MessageLog(Document):
	"""Read-only monitoring record of AS2/EDI activity (no payload storage)."""

	def validate(self):
		# Desk users must not invent monitoring rows via form save.
		# Rows are created only by the read-only discovery service.
		pass
