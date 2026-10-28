// Copyright (c) 2026, Lakshana and contributors
// For license information, please see license.txt

frappe.provide("openas2_manager.restart");

openas2_manager.restart.CONFIRM_MESSAGE = __(
	"You are about to restart the selected OpenAS2 instance.\nActive AS2 communication may be temporarily unavailable.\nContinue?"
);

/**
 * Explicit Restart OpenAS2 flow with confirmation.
 * Never auto-called from Apply / Preview / DocType save.
 */
openas2_manager.restart.prompt_and_restart = function (instance_name) {
	if (!instance_name) {
		frappe.msgprint(__("Select an OpenAS2 Instance first."));
		return;
	}

	if (!frappe.user.has_role("System Manager")) {
		frappe.msgprint({
			title: __("Not Permitted"),
			indicator: "red",
			message: __("Only System Managers may restart OpenAS2."),
		});
		return;
	}

	frappe.confirm(openas2_manager.restart.CONFIRM_MESSAGE, () => {
		frappe.call({
			method: "openas2_manager.openas2.restart.restart_openas2_instance",
			args: { instance_name: instance_name, confirmed: 1 },
			freeze: true,
			freeze_message: __("Restarting OpenAS2 (controlled)…"),
			callback(r) {
				openas2_manager.restart.show_result(r.message || {});
			},
		});
	});
};

openas2_manager.restart.show_result = function (result) {
	const indicator =
		result.result === "Success"
			? "green"
			: result.result === "Not Available"
				? "orange"
				: "red";

	let message = frappe.utils.escape_html(result.message || "");
	message = message.replace(/\n/g, "<br>");

	if (result.result === "Not Available" && result.discovery) {
		const d = result.discovery;
		message +=
			"<hr><p><strong>" +
			__("Detected installation") +
			"</strong></p><ul>" +
			`<li>${__("Home")}: <code>${frappe.utils.escape_html(d.home_display || "—")}</code></li>` +
			`<li>${__("Start script")}: <code>${frappe.utils.escape_html(d.start_script || "—")}</code></li>` +
			`<li>${__("config.xml")}: <code>${frappe.utils.escape_html(d.config_xml || "—")}</code></li>` +
			"</ul>";
		if (result.manual_hint) {
			message +=
				"<p class='text-muted'>" +
				frappe.utils.escape_html(result.manual_hint) +
				"</p>";
		}
	}

	if (result.restart_log) {
		message +=
			`<p class="text-muted">${__("Audit log")}: ` +
			`<a href="/app/openas2-restart-log/${encodeURIComponent(result.restart_log)}">` +
			frappe.utils.escape_html(result.restart_log) +
			"</a></p>";
	}

	frappe.msgprint({
		title: __("Restart Result"),
		indicator,
		message,
	});
};

/**
 * After successful Apply — prompt only; never auto-restart.
 */
openas2_manager.restart.offer_after_apply = function (instance_name, apply_message) {
	const d = new frappe.ui.Dialog({
		title: __("Configuration Applied"),
		fields: [
			{
				fieldtype: "HTML",
				options: `<p>${frappe.utils.escape_html(
					apply_message ||
						__(
							"Configuration applied successfully. OpenAS2 may need to be restarted to load the changes."
						)
				)}</p>
				<p class="text-muted">${__(
					"OpenAS2 was not restarted automatically. Restart only if you want to load the new configuration now."
				)}</p>`,
			},
		],
		primary_action_label: __("Restart OpenAS2"),
		primary_action() {
			d.hide();
			openas2_manager.restart.prompt_and_restart(instance_name);
		},
		secondary_action_label: __("Close"),
		secondary_action() {
			d.hide();
		},
	});
	d.show();
};
