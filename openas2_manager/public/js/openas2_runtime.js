// Copyright (c) 2026, Lakshana and contributors
// For license information, please see license.txt

frappe.provide("openas2_manager.runtime");

openas2_manager.runtime.confirm_and_run = function (instanceName, action) {
	if (!frappe.user.has_role("System Manager")) {
		frappe.msgprint({
			title: __("Not permitted"),
			indicator: "red",
			message: __("Only System Managers may control OpenAS2 runtimes."),
		});
		return;
	}
	const labels = {
		start: __("Start"),
		stop: __("Stop"),
		restart: __("Restart"),
	};
	frappe.confirm(
		__(
			"Confirm {0} for instance {1}? Only this Manager-provisioned instance will be affected.",
			[labels[action] || action, instanceName]
		),
		() => {
			frappe.call({
				method: "openas2_manager.openas2.runtime_control.runtime_control",
				args: {
					instance_name: instanceName,
					action: action,
					confirmed: 1,
				},
				freeze: true,
				freeze_message: __("Contacting Runtime Agent..."),
				callback(r) {
					const result = r.message || {};
					frappe.msgprint({
						title: __("Runtime {0}", [labels[action] || action]),
						indicator: result.ok ? "green" : "red",
						message: __(result.message || result.error || "No response"),
					});
					if (cur_frm && cur_frm.doc && cur_frm.doc.name === instanceName) {
						cur_frm.reload_doc();
					}
				},
			});
		}
	);
};

openas2_manager.runtime.refresh_status = function (instanceName) {
	frappe.call({
		method: "openas2_manager.openas2.runtime_control.runtime_status",
		args: { instance_name: instanceName },
		freeze: true,
		freeze_message: __("Refreshing runtime status..."),
		callback(r) {
			const result = r.message || {};
			const agent = result.agent || {};
			frappe.msgprint({
				title: __("Runtime Status"),
				indicator: result.ok ? "green" : "orange",
				message: result.ok
					? __(
							"Lifecycle: {0}<br>PID: {1}<br>Port listening: {2}<br>Health: {3}<br>AS2 protocol: Not Verified",
							[
								agent.lifecycle_status,
								agent.pid || "—",
								agent.port_listening ? __("Yes") : __("No"),
								agent.openas2_health || "—",
							]
					  )
					: __(result.error || "Agent unreachable"),
			});
			if (cur_frm && cur_frm.doc && cur_frm.doc.name === instanceName) {
				cur_frm.reload_doc();
			}
		},
	});
};

openas2_manager.runtime.health = function (instanceName) {
	frappe.call({
		method: "openas2_manager.openas2.runtime_control.runtime_health",
		args: { instance_name: instanceName },
		freeze: true,
		callback(r) {
			const result = r.message || {};
			const agent = result.agent || {};
			const health = agent.health || {};
			frappe.msgprint({
				title: __("Health Check"),
				indicator: result.ok && health.openas2_healthy ? "green" : "orange",
				message: result.ok
					? __(
							"Process running: {0}<br>Port listening: {1}<br>OpenAS2 healthy (process+port): {2}<br>AS2 protocol: Not Verified",
							[
								health.process_running ? __("Yes") : __("No"),
								health.port_listening ? __("Yes") : __("No"),
								health.openas2_healthy ? __("Yes") : __("No"),
							]
					  )
					: __(result.error || "Health check failed"),
			});
			if (cur_frm && cur_frm.doc && cur_frm.doc.name === instanceName) {
				cur_frm.reload_doc();
			}
		},
	});
};

openas2_manager.runtime.view_logs = function (instanceName) {
	frappe.call({
		method: "openas2_manager.openas2.runtime_control.runtime_logs",
		args: { instance_name: instanceName, lines: 200 },
		freeze: true,
		freeze_message: __("Fetching logs..."),
		callback(r) {
			const result = r.message || {};
			if (!result.ok) {
				frappe.msgprint({
					title: __("Logs"),
					indicator: "red",
					message: __(result.error || "Could not fetch logs"),
				});
				return;
			}
			const d = new frappe.ui.Dialog({
				title: __("Runtime Logs — {0}", [instanceName]),
				size: "extra-large",
				fields: [
					{
						fieldtype: "HTML",
						options:
							"<pre style='max-height:60vh;overflow:auto;white-space:pre-wrap;'></pre>",
					},
				],
			});
			d.show();
			const pre = d.$wrapper.find("pre");
			pre.text(result.lines || __("(empty)"));
			if (result.source) {
				d.set_title(__("Runtime Logs — {0} ({1})", [instanceName, result.source]));
			}
		},
	});
};
