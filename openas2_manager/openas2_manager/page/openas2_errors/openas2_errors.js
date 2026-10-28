// Copyright (c) 2026, Lakshana and contributors
// For license information, please see license.txt

frappe.pages["openas2-errors"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("OpenAS2 Errors"),
		single_column: true,
	});
	frappe.breadcrumbs.add("OpenAS2 Manager");
	document.body.classList.add("oa2-has-sidebar");
	document.body.classList.add("oa2-using-global-sidebar");
	document.body.classList.remove("oa2-use-inpage-sidebar");
	wrapper.errors_page = new openas2_manager.OpenAS2ErrorsPage(page);
	if (window.openas2_manager && openas2_manager.sync_sidebar) {
		openas2_manager.sync_sidebar();
	}
};

frappe.pages["openas2-errors"].on_page_show = function () {
	document.body.classList.add("oa2-has-sidebar");
	document.body.classList.add("oa2-using-global-sidebar");
	document.body.classList.remove("oa2-use-inpage-sidebar");
	if (window.openas2_manager && openas2_manager.sync_sidebar) {
		openas2_manager.sync_sidebar();
	}
};

frappe.provide("openas2_manager");

openas2_manager.OpenAS2ErrorsPage = class OpenAS2ErrorsPage {
	constructor(page) {
		this.page = page;
		this.$body = $(page.body);
		this.make();
		this.load();
	}

	make() {
		this.page.set_primary_action(__("Refresh"), () => {
			frappe.call({
				method: "openas2_manager.openas2.monitoring.refresh_monitoring",
				freeze: true,
				callback: () => this.load(),
			});
		});
		this.page.add_inner_button(__("All Messages"), () => frappe.set_route("openas2-messages"));
		this.$body.html(`
			<div class="alert alert-warning">
				${__("Only errors discovered from OpenAS2 sources or recorded by this app are shown. Nothing is fabricated.")}
			</div>
			<div class="errors-table"></div>
		`);
		this.$table = this.$body.find(".errors-table");
	}

	load() {
		frappe.call({
			method: "openas2_manager.openas2.monitoring.get_errors",
			callback: (r) => {
				const message = (r && r.message) || {};
				const rows = message.rows || [];
				if (message.error) {
					this.$table.html(
						`<div class="text-muted">${frappe.utils.escape_html(message.error)}</div>`
					);
					return;
				}
				if (!rows.length) {
					this.$table.html(`<div class="text-muted">${__("No errors discovered.")}</div>`);
					return;
				}
				const body = rows
					.map((r) => {
						const time = r.timestamp ? frappe.datetime.str_to_user(r.timestamp) : "—";
						return `<tr>
							<td>${frappe.utils.escape_html(time)}</td>
							<td>${frappe.utils.escape_html(r.instance_label || r.instance || "—")}</td>
							<td>${frappe.utils.escape_html(r.direction || "—")}</td>
							<td>${frappe.utils.escape_html(r.transaction_type || "—")}</td>
							<td>${frappe.utils.escape_html(r.partner || r.remote_as2_id || "—")}</td>
							<td>${frappe.utils.escape_html(r.error_message || "—")}</td>
							<td>${frappe.utils.escape_html(r.status || "—")}</td>
						</tr>`;
					})
					.join("");
				this.$table.html(`
					<div class="table-responsive"><table class="table table-bordered table-sm">
					<thead><tr>
						<th>${__("Time")}</th><th>${__("Instance")}</th><th>${__("Direction")}</th>
						<th>${__("Transaction")}</th><th>${__("Partner")}</th>
						<th>${__("Error")}</th><th>${__("Status")}</th>
					</tr></thead><tbody>${body}</tbody></table></div>`);
			},
		});
	}
};
