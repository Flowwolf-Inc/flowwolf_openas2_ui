// Copyright (c) 2026, Lakshana and contributors
// For license information, please see license.txt

frappe.ui.form.on("AS2 Certificate", {
	onload(frm) {
		if (frm.is_new() && !frm.doc.owner_type) {
			_default_owner_type(frm);
		}
	},

	refresh(frm) {
		frm.set_intro(
			__(
				"Own Key Pair: create private (.p12 on disk) + public (.cer to share). Partner Public: attach only their public cert. Private keys are never shown in the UI."
			)
		);

		_toggle_sections(frm);
		_show_expiry_indicator(frm);
		if (frm.is_new() && !frm.doc.owner_type) {
			_default_owner_type(frm);
		}

		if (frm.is_new()) {
			return;
		}

		if (frm.doc.purpose === "Own Key Pair") {
			frm.add_custom_button(__("Generate Key Pair"), () => {
				frappe.confirm(
					__(
						"Create a new private+public certificate? Private key will be written only to a .p12 file on disk (not shown here)."
					),
					() => {
						frappe.call({
							method: "openas2_manager.certificates.generation.generate_own_keypair",
							args: { name: frm.doc.name },
							freeze: true,
							freeze_message: __("Generating certificate with OpenSSL..."),
							callback(r) {
								const result = r.message || {};
								frm.reload_doc().then(() => {
									frappe.msgprint({
										title: __("Key Pair"),
										indicator: result.ok ? "green" : "red",
										message: __(result.message || "Done."),
									});
								});
							},
						});
					}
				);
			}, __("Certificates"));

			if (frm.doc.certificate_file) {
				frm.add_custom_button(__("Mark Shared With Partner"), () => {
					frappe.prompt(
						[
							{
								fieldname: "partner",
								fieldtype: "Link",
								options: "AS2 Partner",
								label: __("Partner"),
								default: frm.doc.exchange_partner,
							},
						],
						(values) => {
							frappe.call({
								method: "openas2_manager.certificates.generation.mark_public_shared",
								args: { name: frm.doc.name, partner: values.partner },
								freeze: true,
								callback(r) {
									const result = r.message || {};
									frm.reload_doc().then(() => {
										frappe.show_alert({
											message: __(result.message || "Marked shared."),
											indicator: "green",
										});
									});
								},
							});
						},
						__("Exchange Public Certificate"),
						__("Mark Shared")
					);
				}, __("Certificates"));
			}
		}

		if (frm.doc.purpose === "Partner Public Certificate") {
			frm.add_custom_button(__("Import Partner Public Cert"), () => {
				frappe.call({
					method:
						"openas2_manager.certificates.generation.import_partner_public_certificate",
					args: { name: frm.doc.name },
					freeze: true,
					freeze_message: __("Validating partner public certificate..."),
					callback(r) {
						const result = r.message || {};
						frm.reload_doc().then(() => {
							frappe.msgprint({
								title: __("Partner Certificate"),
								indicator: result.ok ? "green" : "orange",
								message: __(result.message || "Done."),
							});
						});
					},
				});
			}, __("Certificates"));
		}

		if (frm.doc.certificate_file) {
			frm.add_custom_button(__("Open Public Certificate"), () => {
				window.open(frm.doc.certificate_file, "_blank");
			}, __("Certificates"));
		}
	},

	purpose(frm) {
		_toggle_sections(frm);
		if (frm.doc.purpose === "Partner Public Certificate") {
			frm.set_value("exchange_status", "Not Shared");
			frm.set_value("private_key_stored", 0);
		}
	},
});

function _toggle_sections(frm) {
	const own = frm.doc.purpose === "Own Key Pair";
	frm.toggle_display("own_keypair_section", own);
	frm.set_df_property("validity_days", "hidden", own ? 0 : 1);
	frm.set_df_property("key_size", "hidden", own ? 0 : 1);
	frm.set_df_property("keystore_password", "hidden", own ? 0 : 1);
}

function _default_owner_type(frm) {
	const role_map = {
		"OpenAS2 Broker User": "Broker",
		"OpenAS2 Shipper User": "Shipper",
		"OpenAS2 Carrier User": "Carrier",
		"OpenAS2 CompanyC User": "CompanyC",
	};
	for (const [role, company] of Object.entries(role_map)) {
		if (frappe.user.has_role(role)) {
			frm.set_value("owner_type", company);
			return;
		}
	}
}

function _show_expiry_indicator(frm) {
	if (frm.doc.status === "Revoked") {
		frm.dashboard.set_headline_alert(__("This certificate is revoked."), "red");
		return;
	}
	if (frm.doc.status === "Expired") {
		frm.dashboard.set_headline_alert(
			__("This certificate is expired (Valid Until: {0}).", [frm.doc.valid_until]),
			"orange"
		);
		return;
	}
	if (frm.doc.exchange_status === "Ready to Share") {
		frm.dashboard.set_headline_alert(
			__("Public certificate ready — share the .cer with your partner."),
			"blue"
		);
	}
	if (frm.doc.expiry_info && frm.doc.expiry_info.indexOf("Expiring soon") !== -1) {
		frm.dashboard.set_headline_alert(frm.doc.expiry_info, "yellow");
	}
}
