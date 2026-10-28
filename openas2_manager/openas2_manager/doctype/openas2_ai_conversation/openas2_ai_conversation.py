# Copyright (c) 2026, Lakshana and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class OpenAS2AIConversation(Document):
	def before_insert(self):
		if not self.user:
			self.user = frappe.session.user
		if self.user != frappe.session.user:
			frappe.throw(frappe._("You can only create your own conversations."), frappe.PermissionError)

	def validate(self):
		if self.user != frappe.session.user:
			frappe.throw(frappe._("You can only update your own conversations."), frappe.PermissionError)
