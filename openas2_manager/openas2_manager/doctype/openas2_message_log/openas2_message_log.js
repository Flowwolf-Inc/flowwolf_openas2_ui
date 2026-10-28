// Copyright (c) 2026, Lakshana and contributors
// For license information, please see license.txt

frappe.ui.form.on("OpenAS2 Message Log", {
	refresh(frm) {
		frm.disable_form();
		frm.set_intro(
			__(
				"Read-only monitoring record. Use OpenAS2 Messages → Refresh to discover activity. Editing, resend, and delete are not available."
			)
		);
		frm.page.clear_primary_action();
		if (frm.doc.edi_document && frappe.boot.user.can_read.includes("EDI Document")) {
			frm.add_custom_button(__("Open EDI Document"), () => {
				frappe.set_route("Form", "EDI Document", frm.doc.edi_document);
			});
		}
	},
});
