// Copyright (c) 2026, Lakshana and contributors
// For license information, please see license.txt

frappe.ui.form.on("OpenAS2 Instance", {
	refresh(frm) {
		// Always show Name in Identity (autoname no longer hides this field).
		frm.set_df_property("instance_name", "hidden", 0);
		frm.toggle_display("instance_name", true);

		const is_external = frm.doc.provision_source !== "Manager Provisioned";
		const home_hint = frm.doc.windows_home || frm.doc.openas2_home || "";

		frm.set_intro(
			__(
				"Edit fields here, then click Save — changes are stored in Frappe. Sync from config.xml only loads from the OpenAS2 folder into this form; it does not replace Save."
			)
		);
		if (home_hint) {
			frm.dashboard.set_headline(__("OpenAS2 home: {0}", [home_hint]));
		}

		const editable_when_external = [
			"http_enabled",
			"https_enabled",
			"http_port",
			"https_port",
			"mdn_enabled",
			"mdn_mode",
			"mdn_http_enabled",
			"mdn_https_enabled",
			"mdn_http_port",
			"mdn_https_port",
			"async_mdn_url",
			"as2_keystore_path",
			"ssl_keystore_path",
			"x509_alias",
			"health_port",
			"tracking_port",
		];
		editable_when_external.forEach((field) => {
			frm.set_df_property(field, "read_only", is_external ? 0 : 1);
		});
		// Identity fields are always editable when the user has write permission.
		["instance_name", "as2_id", "host", "status", "mdn_mode", "protocol", "port"].forEach(
			(field) => {
				frm.set_df_property(field, "read_only", 0);
			}
		);

		if (frm.is_new() && frappe.user.has_role("System Manager")) {
			frm.add_custom_button(__("Create OpenAS2 Communication"), () => {
				openas2_manager.provision.prompt_and_create();
			});
		}

		if (!frm.is_new()) {
			frm.add_custom_button(__("Test Connection"), () => {
				frappe.call({
					method: "openas2_manager.openas2.connection.test_instance_connection",
					args: { name: frm.doc.name },
					freeze: true,
					freeze_message: __("Testing listener reachability..."),
					callback(r) {
						const result = r.message || {};
						frm.reload_doc();
						const indicator =
							result.connection_status === "Connected"
								? "green"
								: result.connection_status === "Failed"
									? "red"
									: "orange";
						frappe.msgprint({
							title: __("Test Connection"),
							indicator,
							message: __(result.message || "No response from test service."),
						});
					},
				});
			});

			if (frm.doc.openas2_home || frm.doc.inbox_path) {
				frm.add_custom_button(__("Sync from config.xml"), () => {
					frappe.call({
						method: "openas2_manager.openas2.config_viewer.sync_instance_from_config",
						args: { instance_name: frm.doc.name },
						freeze: true,
						freeze_message: __("Reading OpenAS2 config.xml..."),
						callback(r) {
							const result = r.message || {};
							frm.reload_doc().then(() => {
								frappe.show_alert({
									message: __(result.message || "Synced."),
									indicator: "green",
								});
							});
						},
					});
				});

				frm.add_custom_button(__("View Raw Config"), () => {
					frappe.set_route("openas2-configuration");
				});
			}

			frm.add_custom_button(__("Generate Keystore"), () => {
				frappe.call({
					method:
						"openas2_manager.openas2_manager.doctype.openas2_instance.openas2_instance.request_keystore_setup",
					args: { instance_name: frm.doc.name },
					freeze: true,
					callback(r) {
						const result = r.message || {};
						frappe.msgprint({
							title: __("Generate Keystore"),
							indicator: result.ok ? "green" : "orange",
							message: __(
								result.message ||
									"Keystore generation is pending integration with keytool."
							),
						});
					},
				});
			}, __("Certificates"));

			if (frappe.user.has_role("System Manager")) {
				const provisioned = frm.doc.provision_source === "Manager Provisioned";

				if (provisioned) {
					frm.add_custom_button(__("Start"), () => {
						openas2_manager.runtime.confirm_and_run(frm.doc.name, "start");
					}, __("Runtime"));
					frm.add_custom_button(__("Stop"), () => {
						openas2_manager.runtime.confirm_and_run(frm.doc.name, "stop");
					}, __("Runtime"));
					frm.add_custom_button(__("Restart"), () => {
						openas2_manager.runtime.confirm_and_run(frm.doc.name, "restart");
					}, __("Runtime"));
					frm.add_custom_button(__("Status"), () => {
						openas2_manager.runtime.refresh_status(frm.doc.name);
					}, __("Runtime"));
					frm.add_custom_button(__("Health Check"), () => {
						openas2_manager.runtime.health(frm.doc.name);
					}, __("Runtime"));
					frm.add_custom_button(__("View Logs"), () => {
						openas2_manager.runtime.view_logs(frm.doc.name);
					}, __("Runtime"));
				} else {
					frm.add_custom_button(__("Restart OpenAS2"), () => {
						openas2_manager.restart.prompt_and_restart(frm.doc.name);
					});
				}
			}
		}
	},

	http_enabled(frm) {
		if (frm.doc.http_enabled && !frm.doc.protocol) {
			frm.set_value("protocol", "HTTP");
		}
	},

	https_enabled(frm) {
		if (frm.doc.https_enabled) {
			frm.set_value("protocol", "HTTPS");
		}
	},

	protocol(frm) {
		if (frm.doc.protocol === "HTTPS" && frm.doc.https_port) {
			frm.set_value("port", frm.doc.https_port);
		} else if (frm.doc.protocol === "HTTP" && frm.doc.http_port) {
			frm.set_value("port", frm.doc.http_port);
		}
	},

	http_port(frm) {
		if (frm.doc.protocol === "HTTP") {
			frm.set_value("port", frm.doc.http_port);
		}
	},

	https_port(frm) {
		if (frm.doc.protocol === "HTTPS") {
			frm.set_value("port", frm.doc.https_port);
		}
	},

	mdn_mode(frm) {
		if (frm.doc.mdn_mode === "Asynchronous" && !frm.doc.mdn_enabled) {
			frm.set_value("mdn_enabled", 1);
		}
	},

	after_save(frm) {
		frappe.show_alert({
			message: __("Saved to Frappe: {0}", [frm.doc.instance_name || frm.doc.name]),
			indicator: "green",
		});
	},
});
