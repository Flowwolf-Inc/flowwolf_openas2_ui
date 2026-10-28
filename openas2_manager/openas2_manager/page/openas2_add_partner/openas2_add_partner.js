// Copyright (c) 2026, Lakshana and contributors
// For license information, please see license.txt

frappe.pages["openas2-add-partner"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Add Partner"),
		single_column: true,
	});
	frappe.breadcrumbs.add("OpenAS2 Manager");
	$(wrapper).addClass("oa2-config-page-wrapper oa2-add-partner-page-wrapper");
	document.body.classList.add("oa2-has-sidebar", "oa2-use-inpage-sidebar");
	document.body.classList.remove("oa2-using-global-sidebar", "oa2-sidebar-mounted");
	wrapper.add_partner_page = new openas2_manager.OpenAS2AddPartnerPage(page);
	if (window.openas2_manager && openas2_manager.sync_layout) openas2_manager.sync_layout();
};

frappe.pages["openas2-add-partner"].on_page_show = function (wrapper) {
	document.body.classList.add("oa2-has-sidebar", "oa2-use-inpage-sidebar");
	document.body.classList.remove("oa2-using-global-sidebar", "oa2-sidebar-mounted");
	if (wrapper.add_partner_page) {
		wrapper.add_partner_page.apply_theme(wrapper.add_partner_page.get_theme());
		wrapper.add_partner_page.load_certificates();
	}
	if (window.openas2_manager && openas2_manager.sync_layout) openas2_manager.sync_layout();
};

frappe.provide("openas2_manager");

openas2_manager.OpenAS2AddPartnerPage = class OpenAS2AddPartnerPage {
	constructor(page) {
		this.page = page;
		this.THEME_KEY = "oa2-dashboard-theme";
		this.saving = false;
		this.$body = $(page.body).addClass("oa2-config-list-page oa2-add-partner-page");
		this.make();
		this.apply_theme(this.get_theme());
		this.load_certificates();
	}

	get_theme() {
		try {
			return localStorage.getItem(this.THEME_KEY) === "dark" ? "dark" : "light";
		} catch (e) {
			return "light";
		}
	}

	apply_theme(theme) {
		const t = theme === "dark" ? "dark" : "light";
		this.$body.attr("data-oa2-theme", t);
		this.$body.find(".oa2-sidebar-inpage").attr("data-oa2-theme", t);
		const $wrap = this.$body.closest(".oa2-config-page-wrapper");
		if ($wrap.length) $wrap.attr("data-oa2-theme", t);
		if (window.openas2_manager && openas2_manager.apply_oa2_theme) {
			openas2_manager.apply_oa2_theme(t);
		}
	}

	sidebar_html() {
		const active = "partners";
		const icons = {
			home: `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M4 10.5 12 4l8 6.5"/><path d="M6.5 9.5V20h11V9.5"/></svg>`,
			configuration: `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M12 3.5v2.2M12 18.3v2.2M4.9 6.4l1.6 1.6M17.5 16l1.6 1.6M3.5 12h2.2M18.3 12h2.2M4.9 17.6l1.6-1.6M17.5 8l1.6-1.6"/></svg>`,
			partners: `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="9" cy="8" r="2.4"/><circle cx="16.5" cy="9" r="2"/><path d="M4.5 18.5c.6-2.6 2.6-4 4.5-4s3.9 1.4 4.5 4"/><path d="M13.8 18.5c.4-1.8 1.7-3 3-3 1.4 0 2.5.9 3 2.5"/></svg>`,
			certificates: `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3.5 19 6.5v5.2c0 4.2-2.8 7.8-7 9-4.2-1.2-7-4.8-7-9V6.5L12 3.5z"/></svg>`,
			monitoring: `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19V5M8 19v-8M12 19V9M16 19v-5M20 19V7"/></svg>`,
			logs: `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M7 3.5h7.2L19 8.3V20a1.5 1.5 0 0 1-1.5 1.5h-10A1.5 1.5 0 0 1 6 20V5A1.5 1.5 0 0 1 7.5 3.5H7z"/><path d="M14 3.5V8h4.8"/><path d="M9 12.5h6M9 16h4"/></svg>`,
			settings: `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h10"/><path d="M4 12h16"/><path d="M4 17h8"/><circle cx="16.5" cy="7" r="2"/><circle cx="14.5" cy="17" r="2"/><circle cx="10" cy="12" r="2"/></svg>`,
		};
		const items = [
			{ key: "home", label: __("Home"), icon: "home", route: "openas2-dashboard" },
			{ key: "configuration", label: __("Configuration"), icon: "configuration", route: "openas2-configuration" },
			{ key: "partners", label: __("Partners"), icon: "partners", route: "openas2-partners" },
			{ key: "certificates", label: __("Certificates"), icon: "certificates", route: "openas2-certificates" },
			{ key: "monitoring", label: __("Monitoring"), icon: "monitoring", route: "openas2-messages" },
			{ key: "logs", label: __("Logs"), icon: "logs", route: "openas2-logs" },
			{ key: "settings", label: __("Settings"), icon: "settings", route: "openas2-settings" },
		];
		const nav = items
			.map(
				(item) => `<button type="button" class="oa2-nav-item${item.key === active ? " active" : ""}" data-route="${item.route}" data-oa2-route="${item.route}" data-oa2-key="${item.key}">
				<span class="oa2-nav-icon">${icons[item.icon]}</span>
				<span class="oa2-nav-label">${frappe.utils.escape_html(item.label)}</span>
			</button>`
			)
			.join("");
		return `
			<aside class="oa2-sidebar-inpage" aria-label="EDI AS2">
				<div class="oa2-sidebar-brand">
					<div class="oa2-brand-mark" aria-hidden="true">
						<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
							<path d="M7 3.5h7.2L19 8.3V20a1.5 1.5 0 0 1-1.5 1.5h-10A1.5 1.5 0 0 1 6 20V5A1.5 1.5 0 0 1 7.5 3.5H7z"/>
							<path d="M14 3.5V8h4.8"/>
							<path d="M9 13h6M9 16.5h4"/>
						</svg>
					</div>
					<div class="oa2-brand-text">
						<div class="oa2-brand-title">EDI AS2</div>
						<div class="oa2-brand-tagline">${__("Secure. Converted. Compliant")}</div>
					</div>
					<span class="oa2-brand-dot" title="${__("Online")}"></span>
				</div>
				<nav class="oa2-sidebar-nav">${nav}</nav>
				<div class="oa2-sidebar-footer">
					<div class="oa2-footer-art" aria-hidden="true">
						<svg viewBox="0 0 160 100" width="140" height="88">
							<ellipse cx="48" cy="62" rx="34" ry="16" fill="rgba(255,255,255,0.12)"/>
							<ellipse cx="108" cy="68" rx="40" ry="18" fill="rgba(255,255,255,0.16)"/>
							<ellipse cx="80" cy="58" rx="28" ry="12" fill="rgba(147,197,253,0.35)"/>
							<path d="M80 18l22 10v18c0 14-9 26-22 30-13-4-22-16-22-30V28l22-10z" fill="rgba(255,255,255,0.92)"/>
							<path d="M80 34c-5 0-9 4-9 9 0 7 9 14 9 14s9-7 9-14c0-5-4-9-9-9z" fill="#1e3a8a"/>
							<circle cx="80" cy="43" r="3.2" fill="#fff"/>
						</svg>
					</div>
					<div class="oa2-footer-copy">
						<strong>${__("AS2 Communication")}</strong>
						<span>${__("Secure B2B exchange with your business partners")}</span>
					</div>
					<div class="oa2-footer-pulse" aria-hidden="true">
						<svg viewBox="0 0 40 16" width="28" height="12" fill="none" stroke="currentColor" stroke-width="1.6">
							<path d="M1 8h8l3-5 4 10 3-5h10"/>
						</svg>
					</div>
				</div>
			</aside>
		`;
	}

	field(name, label, type, extra) {
		const id = "oa2-partner-" + name;
		const required = extra && extra.required ? " required" : "";
		const mark = extra && extra.required ? " *" : "";
		if (type === "select") {
			const options = ((extra && extra.options) || [])
				.map((opt) => {
					const value = typeof opt === "string" ? opt : opt.value;
					const labelText = typeof opt === "string" ? opt : opt.label;
					return `<option value="${frappe.utils.escape_html(value)}">${frappe.utils.escape_html(labelText)}</option>`;
				})
				.join("");
			return `<label class="oa2-set-field" for="${id}"><span>${frappe.utils.escape_html(label)}${mark}</span><select id="${id}" data-field="${name}"${required}>${options}</select></label>`;
		}
		const inputType = type === "url" ? "url" : "text";
		return `<label class="oa2-set-field" for="${id}"><span>${frappe.utils.escape_html(label)}${mark}</span><input id="${id}" type="${inputType}" data-field="${name}" autocomplete="off"${required} /></label>`;
	}

	check(name, label) {
		const id = "oa2-partner-" + name;
		return `<label class="oa2-set-check" for="${id}"><input id="${id}" type="checkbox" data-field="${name}" /><span>${frappe.utils.escape_html(label)}</span></label>`;
	}

	section(title, hint, inner) {
		return `<section class="oa2-config-card oa2-set-card"><header class="oa2-set-card-head"><h2>${frappe.utils.escape_html(title)}</h2>${hint ? `<p>${frappe.utils.escape_html(hint)}</p>` : ""}</header><div class="oa2-set-grid">${inner}</div></section>`;
	}

	make() {
		const identity =
			this.field("partner_name", __("Partner Name"), "text", { required: true }) +
			this.field("as2_id", __("Partner AS2 ID"), "text", { required: true }) +
			this.field("as2_url", __("Partner URL / Endpoint"), "url", { required: true }) +
			this.field("partner_type", __("Partner Type"), "select", {
				required: true,
				options: [
					{ value: "", label: __("Select a partner type") },
					"Shipper",
					"Broker",
					"Carrier",
					"CompanyC",
				],
			});
		const certificate = this.field("certificate", __("Certificate"), "select", {
			options: [{ value: "", label: __("Loading certificates…") }],
		});
		const encryption = this.check("encryption_enabled", __("Encryption enabled"));
		const signature = this.check("signing_enabled", __("Signing enabled"));
		const mdn =
			this.check("mdn_enabled", __("MDN enabled")) +
			this.field("mdn_mode", __("MDN mode"), "select", {
				options: [
					{ value: "", label: __("Select MDN mode") },
					"Synchronous",
					"Asynchronous",
				],
			});

		this.$body.html(`
			<div class="oa2-app-frame">
				${this.sidebar_html()}
				<div class="oa2-main-pane">
					<div class="oa2-config-shell">
						<header class="oa2-config-header">
							<div>
								<h1 class="oa2-config-title">${__("Add Partner")}</h1>
								<p class="oa2-config-subtitle">${__("Create an AS2 Partner record with identity, endpoint, certificate, and MDN settings.")}</p>
							</div>
							<div class="oa2-config-header-actions"></div>
						</header>
						<form class="oa2-set-form oa2-add-partner-form" novalidate>
							${this.section(__("Partner"), __("Name, AS2 ID, endpoint, and partner type."), identity)}
							${this.section(__("Certificate"), __("Optional link to an existing AS2 Certificate."), certificate)}
							${this.section(__("Encryption settings"), __("Store whether messages to this partner are encrypted."), encryption)}
							${this.section(__("Signature settings"), __("Store whether messages to this partner are signed."), signature)}
							${this.section(__("MDN settings"), __("Message disposition notification for this partner."), mdn)}
							<div class="oa2-add-partner-actions">
								<button type="button" class="oa2-btn oa2-btn-secondary oa2-partner-cancel">${__("Cancel / Back")}</button>
								<button type="submit" class="oa2-btn oa2-btn-primary oa2-partner-save">${__("Save Partner")}</button>
							</div>
						</form>
					</div>
				</div>
			</div>
		`);

		this.$body.on("click", ".oa2-sidebar-inpage [data-route]", (e) => {
			e.preventDefault();
			const route = $(e.currentTarget).attr("data-route");
			if (route) frappe.set_route(route);
		});
		this.$body.on("click", ".oa2-partner-cancel", (e) => {
			e.preventDefault();
			frappe.set_route("openas2-partners");
		});
		this.$body.on("change", '[data-field="mdn_enabled"]', () => this.sync_mdn_mode());
		this.$body.on("submit", ".oa2-add-partner-form", (e) => {
			e.preventDefault();
			this.save();
		});
		this.sync_mdn_mode();
	}

	sync_mdn_mode() {
		const enabled = this.$body.find('[data-field="mdn_enabled"]').is(":checked");
		const $mode = this.$body.find('[data-field="mdn_mode"]');
		$mode.prop("disabled", !enabled);
		if (!enabled) $mode.val("");
	}

	load_certificates() {
		const $select = this.$body.find('[data-field="certificate"]');
		if (!$select.length) return;
		const current = $select.val() || "";
		frappe.call({
			method: "frappe.client.get_list",
			args: {
				doctype: "AS2 Certificate",
				fields: ["name", "certificate_name", "x509_alias"],
				order_by: "certificate_name asc",
				limit_page_length: 200,
			},
			callback: (r) => {
				const rows = r.message || [];
				const options = [`<option value="">${__("No certificate")}</option>`].concat(
					rows.map((row) => {
						const label = row.x509_alias
							? `${row.certificate_name || row.name} (${row.x509_alias})`
							: row.certificate_name || row.name;
						return `<option value="${frappe.utils.escape_html(row.name)}">${frappe.utils.escape_html(label)}</option>`;
					})
				);
				$select.html(options.join(""));
				if (current && $select.find(`option[value="${CSS.escape(current)}"]`).length) {
					$select.val(current);
				}
			},
			error: () => {
				$select.html(`<option value="">${__("Could not load certificates")}</option>`);
			},
		});
	}

	value(name) {
		const $el = this.$body.find(`[data-field="${name}"]`);
		if ($el.is(":checkbox")) return $el.is(":checked") ? 1 : 0;
		return String($el.val() || "").trim();
	}

	save() {
		if (this.saving) return;
		const partner_name = this.value("partner_name");
		const as2_id = this.value("as2_id");
		const as2_url = this.value("as2_url");
		const partner_type = this.value("partner_type");
		const certificate = this.value("certificate");
		const encryption_enabled = this.value("encryption_enabled");
		const signing_enabled = this.value("signing_enabled");
		const mdn_enabled = this.value("mdn_enabled");
		const mdn_mode = this.value("mdn_mode");

		if (!partner_name || !as2_id || !as2_url || !partner_type) {
			frappe.msgprint(__("Partner Name, Partner AS2 ID, Partner URL / Endpoint, and Partner Type are required."));
			return;
		}
		if (mdn_enabled && !mdn_mode) {
			frappe.msgprint(__("MDN Mode is required when MDN is enabled."));
			return;
		}

		const doc = {
			doctype: "AS2 Partner",
			partner_name,
			as2_id,
			as2_url,
			partner_type,
			status: "Active",
			encryption_enabled,
			signing_enabled,
			mdn_enabled,
			mdn_mode: mdn_enabled ? mdn_mode : null,
		};
		if (certificate) doc.certificate = certificate;

		this.saving = true;
		const $save = this.$body.find(".oa2-partner-save").prop("disabled", true);
		frappe.call({
			method: "frappe.client.insert",
			args: { doc },
			freeze: true,
			freeze_message: __("Saving partner…"),
			callback: (r) => {
				this.saving = false;
				$save.prop("disabled", false);
				if (!r || !r.message || !r.message.name) return;
				frappe.show_alert({
					message: __("Partner {0} created", [r.message.partner_name || r.message.name]),
					indicator: "green",
				});
				frappe.set_route("openas2-partners");
			},
			error: () => {
				this.saving = false;
				$save.prop("disabled", false);
			},
		});
	}
};
