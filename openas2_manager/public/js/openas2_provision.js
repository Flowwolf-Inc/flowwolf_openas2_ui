// Copyright (c) 2026, Lakshana and contributors
// For license information, please see license.txt

frappe.provide("openas2_manager.provision");

openas2_manager.provision.prompt_and_create = function (opts) {
	opts = opts || {};
	if (!frappe.user.has_role("System Manager")) {
		frappe.msgprint({
			title: __("Not permitted"),
			indicator: "red",
			message: __("Only System Managers may provision OpenAS2 instances."),
		});
		return;
	}

	let route = ["openas2-configuration"];
	try {
		route = (frappe.get_route && frappe.get_route()) || route;
	} catch (e) {
		route = ["openas2-configuration"];
	}
	openas2_manager.provision.pending_opts = opts;
	openas2_manager.provision.return_route = route.slice();
	frappe.set_route("openas2-create-communication");
};
