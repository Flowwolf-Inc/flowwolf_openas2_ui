// Copyright (c) 2026, Lakshana and contributors
// For license information, please see license.txt

frappe.ui.form.on("AS2 Partner", {
	refresh(frm) {
		frm.set_intro(
			__(
				"Configuration only — OpenAS2 connection, certificates, messages, and MDNs are not active in this step."
			)
		);
	},

	mdn_enabled(frm) {
		if (!frm.doc.mdn_enabled) {
			frm.set_value("mdn_mode", "");
		}
	},
});
