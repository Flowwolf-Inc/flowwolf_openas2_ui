// Copyright (c) 2026, Lakshana and contributors
// For license information, please see license.txt

frappe.listview_settings["OpenAS2 Instance"] = {
	onload(listview) {
		if (!frappe.user.has_role("System Manager")) {
			return;
		}
		listview.page.add_inner_button(__("Create OpenAS2 Communication"), () => {
			openas2_manager.provision.prompt_and_create();
		});
	},
};
