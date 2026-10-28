// Copyright (c) 2026, Lakshana and contributors
// For license information, please see license.txt

frappe.pages["openas2-partnerships"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("OpenAS2 Partnerships"),
		single_column: true,
	});
	frappe.breadcrumbs.add("OpenAS2 Manager");
	document.body.classList.add("oa2-has-sidebar");
	document.body.classList.add("oa2-using-global-sidebar");
	document.body.classList.remove("oa2-use-inpage-sidebar");
	wrapper.partnerships_page = new openas2_manager.OpenAS2PartnershipsPage(page);
	if (window.openas2_manager && openas2_manager.sync_sidebar) {
		openas2_manager.sync_sidebar();
	}
};

frappe.pages["openas2-partnerships"].on_page_show = function () {
	document.body.classList.add("oa2-has-sidebar");
	document.body.classList.add("oa2-using-global-sidebar");
	document.body.classList.remove("oa2-use-inpage-sidebar");
	if (window.openas2_manager && openas2_manager.sync_sidebar) {
		openas2_manager.sync_sidebar();
	}
};

frappe.provide("openas2_manager");

openas2_manager.OpenAS2PartnershipsPage = class OpenAS2PartnershipsPage {
	constructor(page) {
		this.page = page;
		this.instance = null;
		this.last_preview = null;
		this.$body = $(page.body).addClass("openas2-partnerships-page");
		this.make();
		this.load_instances();
	}

	make() {
		this.page.set_primary_action(__("New Partnership"), () => this.new_partnership());
		this.page.add_inner_button(__("Preview Changes"), () => this.preview_selected());
		this.page.add_inner_button(__("Apply Approved Changes"), () => this.apply_approved());
		this.page.add_inner_button(__("Restart OpenAS2"), () => {
			openas2_manager.restart.prompt_and_restart(this.instance);
		});

		this.$body.empty().append(`
			<div class="alert alert-warning">
				<strong>${__("Important")}</strong>:
				${__(
					"Applying changes writes OpenAS2 partnerships.xml (with backup). OpenAS2 is NOT restarted automatically. Saving a partnership form alone does not modify OpenAS2."
				)}
			</div>
			<div class="frappe-control" style="max-width:420px;margin-bottom:1rem;">
				<label class="control-label">${__("Select OpenAS2 Instance")}</label>
				<div class="instance-wrap"></div>
			</div>
			<div class="content-area"></div>
		`);
		this.$content = this.$body.find(".content-area");
		this.instance_field = frappe.ui.form.make_control({
			parent: this.$body.find(".instance-wrap"),
			df: {
				fieldtype: "Link",
				options: "OpenAS2 Instance",
				fieldname: "instance",
				change: () => {
					this.instance = this.instance_field.get_value();
					if (this.instance) {
						this.refresh();
					}
				},
			},
			render_input: true,
		});
	}

	load_instances() {
		// Link control is enough; optional default first instance
		frappe.db.get_list("OpenAS2 Instance", { fields: ["name"], limit: 1 }).then((rows) => {
			if (rows && rows[0]) {
				this.instance_field.set_value(rows[0].name);
			}
		});
	}

	refresh() {
		if (!this.instance) {
			return;
		}
		frappe.call({
			method: "openas2_manager.openas2.partnership_config.list_instance_partnerships",
			args: { instance_name: this.instance },
			freeze: true,
			callback: (r) => this.render(r.message || {}),
		});
	}

	render(data) {
		const xmlRows = data.xml_partnerships || [];
		const frappeRows = data.frappe_partnerships || [];
		const proposed = data.proposed_changes || [];

		let html = `<div class="text-muted" style="margin-bottom:0.75rem;">
			${__("Source")}: <code>${frappe.utils.escape_html(data.source || "—")}</code>
		</div>`;

		if (data.xml_error) {
			html += `<div class="alert alert-warning">${frappe.utils.escape_html(data.xml_error)}</div>`;
		}

		html += `<div class="frappe-card" style="padding:1rem;margin-bottom:1rem;">
			<h5>${__("Current Partnerships")} <small class="text-muted">(${__("from partnerships.xml")})</small></h5>
			${this.table_xml(xmlRows)}
		</div>`;

		html += `<div class="frappe-card" style="padding:1rem;margin-bottom:1rem;">
			<h5>${__("Frappe Partnership Records")}</h5>
			${this.table_frappe(frappeRows)}
		</div>`;

		html += `<div class="frappe-card" style="padding:1rem;margin-bottom:1rem;">
			<h5>${__("Proposed / Approved Changes")}</h5>
			${this.table_proposed(proposed)}
		</div>`;

		html += `<div class="preview-area"></div>`;
		this.$content.html(html);
		this.bind_row_actions();
		if (this.last_preview) {
			this.render_preview(this.last_preview);
		}
	}

	table_xml(rows) {
		if (!rows.length) {
			return `<div class="text-muted">${__("No partnerships in XML.")}</div>`;
		}
		return `<div class="table-responsive"><table class="table table-bordered table-sm">
			<thead><tr>
				<th>${__("Partnership Name")}</th>
				<th>${__("Local AS2 ID")}</th>
				<th>${__("Remote AS2 ID")}</th>
				<th>${__("Remote URL")}</th>
				<th>${__("Encryption")}</th>
				<th>${__("Signing")}</th>
				<th>${__("MDN")}</th>
				<th>${__("Status")}</th>
			</tr></thead>
			<tbody>${rows
				.map(
					(r) => `<tr>
				<td>${frappe.utils.escape_html(r.partnership_name || "—")}</td>
				<td>${frappe.utils.escape_html(r.local_as2_id || "—")}</td>
				<td>${frappe.utils.escape_html(r.remote_as2_id || "—")}</td>
				<td>${frappe.utils.escape_html(r.remote_url || "—")}</td>
				<td>${frappe.utils.escape_html(r.encryption || "—")}</td>
				<td>${frappe.utils.escape_html(r.signing || "—")}</td>
				<td>${frappe.utils.escape_html(r.mdn || "—")}</td>
				<td>${frappe.utils.escape_html(r.status || "—")}</td>
			</tr>`
				)
				.join("")}</tbody></table></div>`;
	}

	table_frappe(rows) {
		if (!rows.length) {
			return `<div class="text-muted">${__("No Frappe partnership records for this instance.")}</div>`;
		}
		return `<div class="table-responsive"><table class="table table-bordered table-sm">
			<thead><tr>
				<th>${__("Partnership Name")}</th>
				<th>${__("Local AS2 ID")}</th>
				<th>${__("Remote AS2 ID")}</th>
				<th>${__("Remote URL")}</th>
				<th>${__("Enc")}</th>
				<th>${__("Sign")}</th>
				<th>${__("MDN")}</th>
				<th>${__("Status")}</th>
				<th></th>
			</tr></thead>
			<tbody>${rows
				.map(
					(r) => `<tr data-partnership="${frappe.utils.escape_html(r.name)}">
				<td><button type="button" class="btn btn-link btn-xs btn-open-ps" data-name="${frappe.utils.escape_html(
						r.name
					)}">${frappe.utils.escape_html(r.partnership_name)}</button></td>
				<td>${frappe.utils.escape_html(r.local_as2_id || "—")}</td>
				<td>${frappe.utils.escape_html(r.remote_as2_id || "—")}</td>
				<td>${frappe.utils.escape_html(r.remote_url || "—")}</td>
				<td>${r.encryption_enabled ? "Y" : "N"}</td>
				<td>${r.signing_enabled ? "Y" : "N"}</td>
				<td>${r.mdn_enabled ? "Y" : "N"}</td>
				<td>${frappe.utils.escape_html(r.status || "—")}</td>
				<td><button class="btn btn-xs btn-default btn-preview-one">${__("Preview")}</button></td>
			</tr>`
				)
				.join("")}</tbody></table></div>`;
	}

	table_proposed(rows) {
		if (!rows.length) {
			return `<div class="text-muted">${__("No proposed changes. Preview a partnership first.")}</div>`;
		}
		return `<div class="table-responsive"><table class="table table-bordered table-sm">
			<thead><tr>
				<th>${__("Change")}</th>
				<th>${__("Type")}</th>
				<th>${__("Partnership")}</th>
				<th>${__("Requested")}</th>
				<th></th>
			</tr></thead>
			<tbody>${rows
				.map(
					(r) => `<tr data-change="${frappe.utils.escape_html(r.name)}">
				<td><code>${frappe.utils.escape_html(r.name)}</code></td>
				<td>${frappe.utils.escape_html(r.change_type)}</td>
				<td>${frappe.utils.escape_html(r.partnership || "—")}</td>
				<td>${frappe.utils.escape_html(String(r.requested_at || ""))}</td>
				<td>
					<button class="btn btn-xs btn-primary btn-apply-one">${__("Apply")}</button>
				</td>
			</tr>`
				)
				.join("")}</tbody></table></div>`;
	}

	bind_row_actions() {
		this.$content.find(".btn-preview-one").on("click", (e) => {
			const name = $(e.currentTarget).closest("tr").data("partnership");
			this.preview_partnership(name);
		});
		this.$content.find(".btn-apply-one").on("click", (e) => {
			const name = $(e.currentTarget).closest("tr").data("change");
			this.apply_change(name);
		});
		this.$content.find(".btn-open-ps").on("click", (e) => {
			e.preventDefault();
			const name = $(e.currentTarget).attr("data-name");
			if (!name || !openas2_manager.partnership_ui) return;
			openas2_manager.partnership_ui.open({
				name: name,
				defaults: { instance: this.instance || undefined },
				on_save: () => this.refresh(),
			});
		});
	}

	new_partnership() {
		if (!openas2_manager.partnership_ui) return;
		openas2_manager.partnership_ui.open({
			defaults: { instance: this.instance || undefined, status: "Draft" },
			on_save: () => this.refresh(),
		});
	}

	preview_selected() {
		frappe.prompt(
			[
				{
					fieldname: "partnership",
					label: __("OpenAS2 Partnership"),
					fieldtype: "Link",
					options: "OpenAS2 Partnership",
					reqd: 1,
					get_query: () => ({
						filters: this.instance ? { instance: this.instance } : {},
					}),
				},
			],
			(values) => this.preview_partnership(values.partnership),
			__("Preview Configuration Change")
		);
	}

	preview_partnership(name) {
		frappe.call({
			method: "openas2_manager.openas2.partnership_config.preview_partnership_change",
			args: { partnership_name: name },
			freeze: true,
			freeze_message: __("Generating proposal (no write)…"),
			callback: (r) => {
				this.last_preview = r.message;
				this.refresh();
			},
		});
	}

	render_preview(data) {
		const cls = data.classification || {};
		const html = `
		<div class="frappe-card" style="padding:1rem;margin-bottom:1rem;">
			<h5>${__("Configuration Proposal")} — ${frappe.utils.escape_html(data.change_type || "")}
				<span class="indicator-pill blue">${__("NOT APPLIED YET")}</span>
			</h5>
			<p>${__("Audit")}: <code>${frappe.utils.escape_html(data.configuration_change || "")}</code></p>
			<p>${__("Added")}: ${frappe.utils.escape_html((cls.added || []).join(", ") || "—")} |
			   ${__("Modified")}: ${frappe.utils.escape_html((cls.modified || []).join(", ") || "—")} |
			   ${__("Removed")}: ${frappe.utils.escape_html((cls.removed || []).join(", ") || "—")}</p>
			<details open><summary><strong>${__("CURRENT CONFIGURATION")}</strong></summary>
				<pre class="diff-block">${frappe.utils.escape_html(data.current_xml_redacted || "")}</pre>
			</details>
			<details open><summary><strong>${__("PROPOSED CONFIGURATION")}</strong></summary>
				<pre class="diff-block">${frappe.utils.escape_html(data.proposed_xml_redacted || "")}</pre>
			</details>
			<details open><summary><strong>${__("DIFF")}</strong></summary>
				<pre class="diff-block">${frappe.utils.escape_html(data.diff_redacted || data.diff || "")}</pre>
			</details>
		</div>`;
		this.$content.find(".preview-area").html(html);
	}

	apply_approved() {
		if (!this.instance) {
			frappe.msgprint(__("Select an instance first."));
			return;
		}
		frappe.confirm(
			__(
				"Apply all Proposed configuration changes for this instance? This will modify OpenAS2 partnerships.xml (backup first). OpenAS2 will NOT be restarted."
			),
			() => {
				frappe.call({
					method: "openas2_manager.openas2.partnership_config.apply_all_proposed_for_instance",
					args: { instance_name: this.instance },
					freeze: true,
					callback: (r) => {
						const msg = r.message || {};
						if (msg.offer_restart) {
							openas2_manager.restart.offer_after_apply(
								msg.instance || this.instance,
								msg.message
							);
						} else {
							frappe.msgprint(msg.message);
						}
						this.last_preview = null;
						this.refresh();
					},
				});
			}
		);
	}

	apply_change(name) {
		frappe.confirm(
			__(
				"Apply this configuration change now? This writes partnerships.xml after creating a backup. OpenAS2 will NOT be restarted."
			),
			() => {
				frappe.call({
					method: "openas2_manager.openas2.partnership_config.apply_configuration_change",
					args: { configuration_change: name },
					freeze: true,
					callback: (r) => {
						const msg = r.message || {};
						if (msg.offer_restart) {
							openas2_manager.restart.offer_after_apply(
								msg.instance || this.instance,
								msg.message
							);
						} else {
							frappe.msgprint(msg.message);
						}
						this.last_preview = null;
						this.refresh();
					},
				});
			}
		);
	}
};
