// Copyright (c) 2026, Lakshana and contributors
// For license information, please see license.txt

frappe.ui.form.on("OpenAS2 Partnership", {
	refresh(frm) {
		if (window.openas2_manager && openas2_manager.partnership_ui && !frm._oa2_ps_custom) {
			frm._oa2_ps_custom = true;
			const isNew = frm.is_new();
			if (frm.page && frm.page.wrapper) frm.page.wrapper.hide();
			openas2_manager.partnership_ui.open({
				name: isNew ? null : frm.doc.name,
				partner_name: frm.doc.remote_partner || frm.doc.local_partner || null,
				defaults: {
					instance: frm.doc.instance,
					remote_partner: frm.doc.remote_partner,
					local_partner: frm.doc.local_partner,
					status: frm.doc.status,
				},
			});
			frappe.set_route("openas2-partners");
			return;
		}
		frm.set_intro(
			__(
				"Required: Instance, Local Partner, Remote Partner, AS2 IDs, X509 aliases, and Remote URL. Saving does NOT write partnerships.xml — use OpenAS2 Partnerships → Preview / Apply."
			)
		);
		_set_direction_hint(frm);

		if (!frm.is_new()) {
			frm.add_custom_button(__("Open Partnerships Page"), () => {
				frappe.set_route("openas2-partnerships");
			});
			frm.add_custom_button(__("Preview Configuration Change"), () => {
				frappe.call({
					method: "openas2_manager.openas2.partnership_config.preview_partnership_change",
					args: { partnership_name: frm.doc.name },
					freeze: true,
					callback(r) {
						const d = r.message || {};
						frappe.msgprint({
							title: __("Configuration Preview"),
							indicator: "blue",
							message: `<p><strong>${__("Change")}:</strong> ${frappe.utils.escape_html(
								d.change_type || ""
							)}</p>
							<p><strong>${__("Audit")}:</strong> ${frappe.utils.escape_html(
								d.configuration_change || ""
							)}</p>
							<p>${__(
								"Open the OpenAS2 Partnerships page to review CURRENT / PROPOSED / DIFF and Apply."
							)}</p>`,
						});
					},
				});
			});
		}
	},

	instance(frm) {
		if (!frm.doc.instance) {
			return;
		}
		frappe.db.get_value(
			"OpenAS2 Instance",
			frm.doc.instance,
			["as2_id", "instance_type"],
			(r) => {
				if (!r) {
					return;
				}
				if (!frm.doc.local_as2_id && r.as2_id) {
					frm.set_value("local_as2_id", r.as2_id);
				}
				if (!frm.doc.local_partner_name && r.instance_type) {
					frm.set_value("local_partner_name", r.instance_type);
				}
				if (!frm.doc.local_x509_alias && r.instance_type) {
					frm.set_value("local_x509_alias", String(r.instance_type).toLowerCase());
				}
			}
		);
	},

	local_partner(frm) {
		_fill_from_partner(frm, "local");
		_maybe_name(frm);
		_set_direction_hint(frm);
	},

	remote_partner(frm) {
		_fill_from_partner(frm, "remote");
		_maybe_name(frm);
		_set_direction_hint(frm);
	},

	local_certificate(frm) {
		_fill_alias_from_certificate(frm, "local_certificate", "local_x509_alias");
	},

	remote_certificate(frm) {
		_fill_alias_from_certificate(frm, "remote_certificate", "remote_x509_alias");
	},

	local_partner_name(frm) {
		_maybe_name(frm);
		_set_direction_hint(frm);
	},

	remote_partner_name(frm) {
		_maybe_name(frm);
		_set_direction_hint(frm);
	},

	mdn_enabled(frm) {
		if (!frm.doc.mdn_enabled) {
			frm.set_value("mdn_mode", "");
		} else if (!frm.doc.mdn_mode) {
			frm.set_value("mdn_mode", "Synchronous");
		}
	},
});

function _fill_from_partner(frm, side) {
	const link_field = side === "local" ? "local_partner" : "remote_partner";
	const partner = frm.doc[link_field];
	if (!partner) {
		return;
	}

	frappe.db.get_value(
		"AS2 Partner",
		partner,
		[
			"partner_name",
			"as2_id",
			"as2_url",
			"partner_type",
			"certificate",
			"encryption_enabled",
			"signing_enabled",
			"mdn_enabled",
			"mdn_mode",
		],
		(r) => {
			if (!r) {
				return;
			}
			if (side === "local") {
				frm.set_value("local_partner_name", r.partner_name);
				frm.set_value("local_as2_id", r.as2_id);
				if (r.certificate) {
					frm.set_value("local_certificate", r.certificate);
				} else if (r.partner_type) {
					frm.set_value("local_x509_alias", String(r.partner_type).toLowerCase());
				}
			} else {
				frm.set_value("remote_partner_name", r.partner_name);
				frm.set_value("remote_as2_id", r.as2_id);
				frm.set_value("remote_url", r.as2_url);
				if (r.certificate) {
					frm.set_value("remote_certificate", r.certificate);
				} else if (r.partner_type) {
					frm.set_value("remote_x509_alias", String(r.partner_type).toLowerCase());
				}
				if (frm.is_new()) {
					frm.set_value("encryption_enabled", r.encryption_enabled ? 1 : 0);
					frm.set_value("signing_enabled", r.signing_enabled ? 1 : 0);
					frm.set_value("mdn_enabled", r.mdn_enabled ? 1 : 0);
					if (r.mdn_enabled && r.mdn_mode) {
						frm.set_value("mdn_mode", r.mdn_mode);
					}
				}
			}
		}
	);
}

function _fill_alias_from_certificate(frm, cert_field, alias_field) {
	const cert = frm.doc[cert_field];
	if (!cert) {
		return;
	}
	frappe.db.get_value("AS2 Certificate", cert, "x509_alias", (r) => {
		if (r && r.x509_alias) {
			frm.set_value(alias_field, r.x509_alias);
		}
	});
}

function _maybe_name(frm) {
	if (frm.doc.partnership_name) {
		return;
	}
	const local = frm.doc.local_partner_name;
	const remote = frm.doc.remote_partner_name;
	if (local && remote) {
		frm.set_value("partnership_name", `${local}-to-${remote}`);
	}
}

function _set_direction_hint(frm) {
	const local = frm.doc.local_partner_name || __("Local");
	const remote = frm.doc.remote_partner_name || __("Remote");
	frm.set_value(
		"direction_hint",
		__(
			"Creates outbound {0} → {1}. Save stores the draft in Frappe only. Use OpenAS2 Partnerships → Preview / Apply to write partnerships.xml.",
			[local, remote]
		)
	);
}
