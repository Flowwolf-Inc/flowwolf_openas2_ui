// Copyright (c) 2026, Lakshana and contributors
// For license information, please see license.txt

frappe.pages["openas2-partners"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Partners"),
		single_column: true,
	});

	frappe.breadcrumbs.add("OpenAS2 Manager");
	$(wrapper).addClass("oa2-config-page-wrapper");
	document.body.classList.add("oa2-has-sidebar");
	document.body.classList.add("oa2-use-inpage-sidebar");
	document.body.classList.remove("oa2-using-global-sidebar");
	document.body.classList.remove("oa2-sidebar-mounted");

	page.add_inner_button(__("New Partner"), () => {
		frappe.new_doc("AS2 Partner");
	});

	wrapper.partners_list = new openas2_manager.OpenAS2PartnersList(page);
	if (window.openas2_manager && openas2_manager.sync_layout) openas2_manager.sync_layout();
	wrapper.partners_list.pin_header_button();
	[0, 90, 260].forEach((ms) => setTimeout(() => wrapper.partners_list && wrapper.partners_list.pin_header_button(), ms));
	if (window.openas2_manager && openas2_manager.sync_sidebar) {
		openas2_manager.sync_sidebar();
	}
};

frappe.pages["openas2-partners"].on_page_show = function (wrapper) {
	document.body.classList.add("oa2-has-sidebar");
	document.body.classList.add("oa2-use-inpage-sidebar");
	document.body.classList.remove("oa2-using-global-sidebar");
	document.body.classList.remove("oa2-sidebar-mounted");
	if (wrapper.partners_list) {
		wrapper.partners_list.apply_theme(wrapper.partners_list.get_theme());
		wrapper.partners_list.remove_item_lists();
		const opts = frappe.route_options || {};
		if (opts.oa2_action === "new-partner") {
			frappe.route_options = null;
			frappe.new_doc("AS2 Partner");
		} else if (opts.oa2_open_partnership || opts.oa2_open_partner || opts.oa2_open_partnerships) {
			const partnership = opts.oa2_open_partnership || "";
			const partner = opts.oa2_open_partner || opts.oa2_open_partnerships || "";
			frappe.route_options = null;
			wrapper.partners_list.open_from_assistant(partner, partnership);
		}
	}
	if (window.openas2_manager && openas2_manager.sync_layout) openas2_manager.sync_layout();
	if (wrapper.partners_list) {
		const pin = () => wrapper.partners_list && wrapper.partners_list.pin_header_button();
		pin();
		[0, 90, 260].forEach((ms) => setTimeout(pin, ms));
	}
	if (window.openas2_manager && openas2_manager.sync_sidebar) {
		openas2_manager.sync_sidebar();
	}
};

frappe.provide("openas2_manager");

openas2_manager.OpenAS2PartnersList = class OpenAS2PartnersList {
	constructor(page) {
		this.page = page;
		this.THEME_KEY = "oa2-dashboard-theme";
		this.$body = $(page.body).addClass("oa2-config-list-page");
		this.make();
		this.apply_theme(this.get_theme());
	}

	get_theme() {
		try {
			return localStorage.getItem(this.THEME_KEY) === "dark" ? "dark" : "light";
		} catch (e) {
			return "light";
		}
	}

	pin_header_button() {
		const host = this.$body.find(".oa2-config-header-actions").get(0);
		const button = this.$body.find(".oa2-add-partner").get(0);
		const bar = document.getElementById("oa2-shared-header-controls");
		if (!host || !button || !bar || bar.parentElement !== host) return;
		if (button.nextElementSibling !== bar) host.insertBefore(button, bar);
	}

	apply_theme(theme) {
		const t = theme === "dark" ? "dark" : "light";
		this.$body.attr("data-oa2-theme", t);
		this.$body.find(".oa2-sidebar-inpage").attr("data-oa2-theme", t);
		this.$body.find(".oa2-edit-modal-root").attr("data-oa2-theme", t);
		const $wrap = this.$body.closest(".oa2-config-page-wrapper");
		if ($wrap.length) {
			$wrap.attr("data-oa2-theme", t);
		}
		try {
			localStorage.setItem(this.THEME_KEY, t);
		} catch (e) {
			/* ignore */
		}
		const $toggle = this.$body.find(".oa2-theme-toggle");
		const $switch = this.$body.find(".oa2-theme-switch");
		$toggle.toggleClass("is-dark", t === "dark");
		if ($switch.length) {
			$switch.attr("aria-checked", t === "dark" ? "true" : "false");
			$switch.toggleClass("is-dark", t === "dark");
		}
		if (window.openas2_manager && openas2_manager.apply_sidebar_theme) {
			openas2_manager.apply_sidebar_theme();
		}
	}

	sidebar_html(activeKey) {
		const active = activeKey || "partners";
		const icons = {
			home: `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M4 10.5 12 4l8 6.5"/><path d="M6.5 9.5V20h11V9.5"/></svg>`,
			configuration: `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M12 3.5v2.2M12 18.3v2.2M4.9 6.4l1.6 1.6M17.5 16l1.6 1.6M3.5 12h2.2M18.3 12h2.2M4.9 17.6l1.6-1.6M17.5 8l1.6-1.6"/></svg>`,
			partners: `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="9" cy="8" r="2.4"/><circle cx="16.5" cy="9" r="2"/><path d="M4.5 18.5c.6-2.6 2.6-4 4.5-4s3.9 1.4 4.5 4"/><path d="M13.8 18.5c.4-1.8 1.7-3 3-3 1.4 0 2.5.9 3 2.5"/></svg>`,
			certificates: `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3.5 19 6.5v5.2c0 4.2-2.8 7.8-7 9-4.2-1.2-7-4.8-7-9V6.5L12 3.5z"/></svg>`,
			monitoring: `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M7 16a4.5 4.5 0 0 1 .4-9 5.5 5.5 0 0 1 10.5 1.6A3.8 3.8 0 0 1 18.5 16H7z"/></svg>`,
			logs: `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M7 3.5h7.2L19 8.3V20a1.5 1.5 0 0 1-1.5 1.5h-10A1.5 1.5 0 0 1 6 20V5A1.5 1.5 0 0 1 7.5 3.5H7z"/><path d="M14 3.5V8h4.8"/><path d="M9 12.5h6M9 16h4"/></svg>`,
			settings: `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h10"/><path d="M4 12h16"/><path d="M4 17h8"/><circle cx="16.5" cy="7" r="2"/><circle cx="14.5" cy="17" r="2"/><circle cx="10" cy="12" r="2"/></svg>`,
		};
		const items = [
			{ key: "home", label: __("Home"), icon: "home", route: "openas2-dashboard" },
			{ key: "configuration", label: __("Configuration"), icon: "configuration", route: "openas2-configuration" },
			{ key: "partners", label: __("Partners"), icon: "partners", route: "openas2-partners" },
			{ key: "certificates", label: __("Certificates"), icon: "certificates", route: "openas2-certificates" },
			{ key: "monitoring", label: __("Monitoring"), icon: "monitoring", route: "openas2-messages" },
			{ key: "logs", label: __("Logs"), icon: "logs", route: "List/OpenAS2 Message Log" },
			{ key: "settings", label: __("Settings"), icon: "settings", route: "List/OpenAS2 Instance" },
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

	make() {
		this.$body.html(`
			<div class="oa2-app-frame">
				${this.sidebar_html("partners")}
				<div class="oa2-main-pane">
					<div class="oa2-config-shell">
						<header class="oa2-config-header">
							<div>
								<h1 class="oa2-config-title">${__("Partners")}</h1>
								<p class="oa2-config-subtitle">
									${__("AS2 Partner records — identity, endpoint URL, and connection status.")}
								</p>
							</div>
							<div class="oa2-config-header-actions">
								<button type="button" class="oa2-btn oa2-btn-blue oa2-add-partner">${__("Add Partner")}</button>
							</div>
						</header>

						<section class="oa2-partnership-view" hidden>
							<div class="oa2-ps-toolbar">
								<button type="button" class="oa2-ps-back">${__("Back to Partners")}</button>
								<div class="oa2-ps-identity">
									<h2 class="oa2-ps-partner-name"></h2>
									<p class="oa2-ps-partner-id"></p>
								</div>
								<button type="button" class="oa2-btn oa2-btn-blue oa2-ps-add">${__("+ Add Partnership")}</button>
							</div>
							<p class="oa2-ps-note">${__("Apply writes this partnership into that instance's partnerships.xml, after a backup. OpenAS2 is not started.")}</p>
							<div class="oa2-ps-preview" hidden></div>
						</section>
					</div>
				</div>
			</div>
		`);

		this.pin_header_button();
		this.remove_item_lists();

		this.$body.on("click", ".oa2-add-partner", (e) => {
			e.preventDefault();
			this.open_create_popup();
		});

		this.$body.on("click", ".oa2-theme-switch", (e) => {
			e.preventDefault();
			const next = this.get_theme() === "dark" ? "light" : "dark";
			this.apply_theme(next);
		});

		this.$body.on("click", ".oa2-sidebar-inpage [data-route]", (e) => {
			e.preventDefault();
			const route = $(e.currentTarget).attr("data-route");
			if (!route) return;
			try {
				frappe.set_route(...route.split("/"));
			} catch (err) {
				window.location.href = "/app/" + route.toLowerCase().replace(/\s+/g, "-");
			}
		});

		this.$body.on("click", ".oa2-edit-btn", (e) => {
			e.preventDefault();
			const name = $(e.currentTarget).attr("data-name");
			if (name) {
				this.open_edit_popup(name);
			}
		});

		this.$body.on("click", ".oa2-ps-back", (e) => {
			e.preventDefault();
			this.close_partnerships();
		});

		this.$body.on("click", ".oa2-ps-add", (e) => {
			e.preventDefault();
			e.stopPropagation();
			this.open_partnership_editor();
		});

		this.$body.on("click", ".oa2-ps-edit", (e) => {
			e.preventDefault();
			e.stopPropagation();
			const name = $(e.currentTarget).attr("data-name");
			if (name) this.open_partnership_editor(name);
		});

		this.$body.on("click", ".oa2-ps-preview-btn", (e) => {
			e.preventDefault();
			e.stopPropagation();
			const name = $(e.currentTarget).attr("data-name");
			if (name) this.preview_partnership(name);
		});

		this.$body.on("click", ".oa2-ps-apply-btn", (e) => {
			e.preventDefault();
			e.stopPropagation();
			const name = $(e.currentTarget).attr("data-name");
			if (name) this.apply_partnership(name);
		});

		this.$body.on("click", ".oa2-ps-preview-apply", (e) => {
			e.preventDefault();
			const change = $(e.currentTarget).attr("data-change");
			if (change) this.apply_configuration_change(change);
		});

		if (window.openas2_manager && openas2_manager.sync_sidebar) {
			openas2_manager.sync_sidebar();
		}
	}

	close_edit_popup() {
		this.$body.find(".oa2-edit-modal-root").not(".oa2-ps-modal-root").remove();
		this._edit_doc = null;
		this._partner_mode = null;
	}

	open_create_popup() {
		this.close_edit_popup();
		this._partner_mode = "create";
		this.load_certificate_options((certs) => {
			this.render_edit_popup(
				{
					status: "Active",
					partner_type: "",
				},
				certs || []
			);
		});
	}

	open_edit_popup(name) {
		this.close_edit_popup();
		frappe.call({
			method: "frappe.client.get",
			args: { doctype: "AS2 Partner", name },
			freeze: true,
			freeze_message: __("Loading partner…"),
			callback: (r) => {
				const doc = r.message;
				if (!doc) {
					frappe.msgprint(__("Could not load this AS2 Partner."));
					return;
				}
				this._edit_doc = doc;
				this._partner_mode = "edit";
				this.load_certificate_options((certs) => {
					this.render_edit_popup(doc, certs || []);
				});
			},
			error: () => {
				frappe.msgprint(__("Failed to load AS2 Partner."));
			},
		});
	}

	load_certificate_options(done) {
		frappe.call({
			method: "frappe.client.get_list",
			args: {
				doctype: "AS2 Certificate",
				fields: ["name", "certificate_name"],
				limit_page_length: 200,
				order_by: "certificate_name asc",
			},
			callback: (r) => {
				done(r.message || []);
			},
			error: () => {
				done([]);
			},
		});
	}

	field_input(fieldname, label, type, value, opts) {
		opts = opts || {};
		const id = `oa2-edit-${fieldname}`;
		const readonly = opts.readonly ? "readonly disabled" : "";
		const req = opts.reqd ? `<span class="oa2-req">*</span>` : "";
		let control = "";

		if (type === "Select") {
			const options = (opts.options || "").split("\n");
			const choices = options
				.map((o) => {
					const sel = String(value || "") === o ? " selected" : "";
					return `<option value="${this.esc_raw(o)}"${sel}>${this.esc_raw(o || "—")}</option>`;
				})
				.join("");
			control = `<select class="oa2-edit-input" id="${id}" name="${fieldname}" data-fieldname="${fieldname}" ${readonly}>${choices}</select>`;
		} else if (type === "Link") {
			const options = opts.link_options || [];
			const choices = [`<option value="">${__("— None —")}</option>`]
				.concat(
					options.map((o) => {
						const val = o.name || "";
						const labelText = (opts.link_label && o[opts.link_label]) || o.certificate_name || o.partner_name || val;
						const sel = String(value || "") === val ? " selected" : "";
						return `<option value="${this.esc_raw(val)}"${sel}>${this.esc_raw(labelText)}</option>`;
					})
				)
				.join("");
			control = `<select class="oa2-edit-input" id="${id}" name="${fieldname}" data-fieldname="${fieldname}" ${readonly}>${choices}</select>`;
		} else if (type === "Check") {
			const checked = cint(value) ? " checked" : "";
			control = `<label class="oa2-edit-check"><input type="checkbox" id="${id}" name="${fieldname}" data-fieldname="${fieldname}" data-type="Check"${checked} ${readonly}/> <span>${__(
				"Enabled"
			)}</span></label>`;
		} else if (type === "Small Text") {
			control = `<textarea class="oa2-edit-input oa2-edit-textarea" id="${id}" name="${fieldname}" data-fieldname="${fieldname}" rows="3" ${readonly}>${this.esc_raw(
				value
			)}</textarea>`;
		} else {
			control = `<input type="text" class="oa2-edit-input" id="${id}" name="${fieldname}" data-fieldname="${fieldname}" value="${this.esc_raw(
				value
			)}" ${readonly}/>`;
		}

		return `<div class="oa2-edit-field${opts.readonly ? " is-readonly" : ""}${opts.wide ? " oa2-edit-wide" : ""}">
			<label class="oa2-edit-label" for="${id}">${__(label)} ${req}</label>
			${control}
		</div>`;
	}

	section(title, fieldsHtml) {
		return `<div class="oa2-edit-group">
			<h3 class="oa2-edit-section-title">${__(title)}</h3>
			<div class="oa2-edit-grid">${fieldsHtml}</div>
		</div>`;
	}

	edit_panel(key, active, inner) {
		return `<section class="oa2-edit-section" data-section-panel="${key}" ${active ? "" : "hidden"}>${inner}</section>`;
	}

	render_edit_popup(doc, certs) {
		const theme = this.get_theme();
		const f = (name, label, type, opts) => this.field_input(name, label, type, doc[name], opts);
		const creating = this._partner_mode === "create" || !doc.name;
		const nav = [
			["details", __("Partner Details")],
			["identity", __("AS2 Identity")],
			["connection", __("Connection")],
			["certificates", __("Certificates")],
			["mdn", __("MDN Settings")],
			["security", __("Security")],
		]
			.map(
				([key, label], i) =>
					`<button type="button" class="oa2-edit-nav-btn${i === 0 ? " is-active" : ""}" data-section="${key}">${label}</button>`
			)
			.join("");
		const panels = [
			this.edit_panel(
				"details",
				true,
				this.section("Partner Details", [
					f("partner_name", "Partner Name", "Data", { reqd: 1 }),
					f("partner_type", "Partner Type", "Select", {
						reqd: 1,
						options: "\nShipper\nBroker\nCarrier\nCompanyC",
					}),
					f("status", "Status", "Select", { reqd: 1, options: "Active\nInactive" }),
					f("description", "Description", "Small Text"),
				].join(""))
			),
			this.edit_panel(
				"identity",
				false,
				this.section("AS2 Identity", [
					f("as2_id", "AS2 ID", "Data", { reqd: 1, readonly: !creating }),
				].join(""))
			),
			this.edit_panel(
				"connection",
				false,
				this.section("Connection", [f("as2_url", "AS2 URL / Endpoint", "Data", { reqd: 1 })].join(""))
			),
			this.edit_panel(
				"certificates",
				false,
				this.section("Certificates", [
					f("certificate", "Certificate", "Link", { link_options: certs }),
				].join(""))
			),
			this.edit_panel(
				"mdn",
				false,
				this.section("MDN Settings", [
					f("mdn_enabled", "MDN Enabled", "Check"),
					f("mdn_mode", "MDN Mode", "Select", {
						options: "\nSynchronous\nAsynchronous",
					}),
				].join(""))
			),
			this.edit_panel(
				"security",
				false,
				this.section("Security", [
					f("encryption_enabled", "Encryption Enabled", "Check"),
					f("signing_enabled", "Signing Enabled", "Check"),
				].join(""))
			),
		].join("");
		const body = `<nav class="oa2-edit-nav" aria-label="${__("Partner sections")}">${nav}</nav><div class="oa2-edit-pane">${panels}</div>`;
		const title = doc.partner_name || doc.name || __("New Partner");
		const saveLabel = creating ? __("Create Partner") : __("Save Partner");
		const $modal = $(`
			<div class="oa2-edit-modal-root" data-oa2-theme="${theme}" role="dialog" aria-modal="true" aria-labelledby="oa2-edit-modal-title">
				<div class="oa2-edit-modal-backdrop" data-oa2-cancel="1"></div>
				<div class="oa2-edit-modal">
					<header class="oa2-edit-modal-header">
						<div>
							<h2 id="oa2-edit-modal-title" class="oa2-edit-modal-title">${creating ? __("Create Partner") : __("Edit") + " " + this.esc(title)}</h2>
							<p class="oa2-edit-modal-sub">${__("AS2 Partner")}${
								doc.name ? ` · <span class="oa2-mono">${this.esc(doc.name)}</span>` : ""
							}</p>
						</div>
						<button type="button" class="oa2-edit-modal-close" data-oa2-cancel="1" aria-label="${__("Cancel")}">×</button>
					</header>
					<div class="oa2-edit-modal-body oa2-edit-layout">${body}</div>
					<footer class="oa2-edit-modal-footer">
						<button type="button" class="oa2-edit-btn-cancel" data-oa2-cancel="1">${__("Cancel")}</button>
						<button type="button" class="oa2-edit-btn-update">${saveLabel}</button>
					</footer>
				</div>
			</div>
		`);

		this.$body.append($modal);

		$modal.on("click", ".oa2-edit-nav-btn", (e) => {
			e.preventDefault();
			const key = $(e.currentTarget).attr("data-section");
			$modal.find(".oa2-edit-nav-btn").removeClass("is-active");
			$(e.currentTarget).addClass("is-active");
			$modal.find("[data-section-panel]").attr("hidden", true);
			$modal.find(`[data-section-panel="${key}"]`).removeAttr("hidden");
		});

		$modal.on("click", "[data-oa2-cancel]", (e) => {
			e.preventDefault();
			this.close_edit_popup();
		});

		$modal.on("click", ".oa2-edit-btn-update", (e) => {
			e.preventDefault();
			if (this._partner_mode === "create") this.save_create_popup();
			else this.save_edit_popup();
		});

		$modal.on("keydown", (e) => {
			if (e.key === "Escape") {
				e.preventDefault();
				this.close_edit_popup();
			}
		});
	}

	collect_edit_values() {
		const $root = this.$body.find(".oa2-edit-modal-root").not(".oa2-ps-modal-root");
		const updates = {};
		$root.find("[data-fieldname]").each((_, el) => {
			const $el = $(el);
			if ($el.is(":disabled") || $el.prop("readonly")) return;
			const fieldname = $el.attr("data-fieldname");
			const type = $el.attr("data-type") || "";
			if (type === "Check") {
				updates[fieldname] = $el.is(":checked") ? 1 : 0;
			} else {
				updates[fieldname] = $el.val();
			}
		});
		return updates;
	}

	save_create_popup() {
		if (this.saving) return;
		const updates = this.collect_edit_values();
		if (!updates.partner_name || !updates.as2_id || !updates.as2_url || !updates.partner_type) {
			frappe.msgprint(__("Partner Name, AS2 ID, Partner Type, and AS2 URL are required."));
			return;
		}
		if (cint(updates.mdn_enabled) && !updates.mdn_mode) {
			frappe.msgprint(__("MDN Mode is required when MDN is enabled."));
			return;
		}
		const doc = {
			doctype: "AS2 Partner",
			partner_name: updates.partner_name,
			as2_id: updates.as2_id,
			as2_url: updates.as2_url,
			partner_type: updates.partner_type,
			status: updates.status || "Active",
			encryption_enabled: updates.encryption_enabled ? 1 : 0,
			signing_enabled: updates.signing_enabled ? 1 : 0,
			mdn_enabled: updates.mdn_enabled ? 1 : 0,
			mdn_mode: updates.mdn_enabled ? updates.mdn_mode : null,
			description: updates.description || "",
		};
		if (updates.certificate) doc.certificate = updates.certificate;
		this.saving = true;
		const $btn = this.$body.find(".oa2-edit-btn-update");
		$btn.prop("disabled", true).text(__("Saving…"));
		frappe.call({
			method: "frappe.client.insert",
			args: { doc },
			freeze: true,
			freeze_message: __("Creating partner…"),
			callback: (r) => {
				this.saving = false;
				if (!r || !r.message || !r.message.name) {
					$btn.prop("disabled", false).text(__("Create Partner"));
					return;
				}
				frappe.show_alert({ message: __("Partner created"), indicator: "green" });
				this.close_edit_popup();
				this.load();
			},
			error: () => {
				this.saving = false;
				$btn.prop("disabled", false).text(__("Create Partner"));
				frappe.msgprint(__("Failed to create AS2 Partner."));
			},
		});
	}

	save_edit_popup() {
		if (!this._edit_doc || !this._edit_doc.name) return;
		const updates = this.collect_edit_values();
		if (!updates.partner_name || !updates.partner_type || !updates.as2_url || !updates.status) {
			frappe.msgprint(__("Partner Name, Partner Type, Status, and AS2 URL are required."));
			return;
		}
		if (cint(updates.mdn_enabled) && !updates.mdn_mode) {
			frappe.msgprint(__("MDN Mode is required when MDN is enabled."));
			return;
		}

		const name = this._edit_doc.name;
		const $btn = this.$body.find(".oa2-edit-btn-update");
		$btn.prop("disabled", true).text(__("Saving…"));

		frappe.call({
			method: "frappe.client.set_value",
			args: {
				doctype: "AS2 Partner",
				name: name,
				fieldname: updates,
			},
			freeze: true,
			freeze_message: __("Saving…"),
			callback: (r) => {
				if (r.exc) {
					$btn.prop("disabled", false).text(__("Save Partner"));
					frappe.msgprint(__("Failed to update AS2 Partner."));
					return;
				}
				frappe.show_alert({ message: __("Partner updated"), indicator: "green" });
				this.close_edit_popup();
				this.load();
			},
			error: () => {
				$btn.prop("disabled", false).text(__("Save Partner"));
				frappe.msgprint(__("Failed to update AS2 Partner."));
			},
		});
	}

	esc(value) {
		return frappe.utils.escape_html(value == null || value === "" ? "—" : String(value));
	}

	esc_raw(value) {
		return frappe.utils.escape_html(value == null ? "" : String(value));
	}

	status_badge(status) {
		const s = (status || "").toLowerCase();
		let tone = "muted";
		if (s === "active") tone = "success";
		else if (s === "inactive") tone = "warn";
		return `<span class="oa2-pill oa2-pill-${tone}">${this.esc(status || "—")}</span>`;
	}

	type_badge(type) {
		const t = (type || "").toLowerCase();
		let tone = "muted";
		if (t === "broker") tone = "blue";
		else if (t === "carrier") tone = "green";
		else if (t === "shipper") tone = "orange";
		else if (t === "companyc") tone = "purple";
		return `<span class="oa2-type-pill oa2-type-${tone}"><i class="oa2-type-dot"></i>${this.esc(
			type || "—"
		)}</span>`;
	}

	load() {
		this.remove_item_lists();
	}

	remove_item_lists() {
		this.$body
			.find(".oa2-partners-list, table.oa2-config-table, table.oa2-ps-table")
			.each((_, table) => {
				const $card = $(table).closest("section.oa2-config-card");
				if ($card.length) $card.remove();
				else $(table).closest(".oa2-config-table-wrap").remove();
			});
	}

	open_from_assistant(partner, partnership) {
		const openPartner = (partnerName) => {
			if (!partnerName) return;
			if (partnership) {
				this.open_partnerships(partnerName);
				const tryEdit = () => {
					if (this._ps_partner) this.open_partnership_editor(partnership);
					else setTimeout(tryEdit, 120);
				};
				setTimeout(tryEdit, 180);
				return;
			}
			this.open_edit_popup(partnerName);
		};
		if (partner) {
			openPartner(partner);
			return;
		}
		if (!partnership) return;
		frappe.call({
			method: "frappe.client.get",
			args: { doctype: "OpenAS2 Partnership", name: partnership },
			callback: (r) => {
				const doc = r.message || {};
				const partnerName = doc.local_partner || doc.remote_partner || "";
				if (!partnerName) {
					frappe.msgprint(__("Could not open this partnership."));
					return;
				}
				openPartner(partnerName);
			},
		});
	}

	open_partnerships(name) {
		this.close_edit_popup();
		if (openas2_manager.partnership_ui) openas2_manager.partnership_ui.close();
		frappe.call({
			method: "frappe.client.get",
			args: { doctype: "AS2 Partner", name },
			freeze: true,
			freeze_message: __("Loading partner…"),
			callback: (r) => {
				const doc = r.message;
				if (!doc) {
					frappe.msgprint(__("Could not load this AS2 Partner."));
					return;
				}
				this._ps_partner = doc;
				const $view = this.$body.find(".oa2-partnership-view");
				$view.removeAttr("hidden");
				$view.find(".oa2-ps-partner-name").text(doc.partner_name || doc.name || "");
				$view.find(".oa2-ps-partner-id").text(doc.as2_id || doc.name || "");
				this.load_partnerships();
			},
		});
	}

	close_partnerships() {
		if (openas2_manager.partnership_ui) openas2_manager.partnership_ui.close();
		this._ps_partner = null;
		this._ps_preview = null;
		this.$body.find(".oa2-ps-preview").attr("hidden", true).empty();
		this.$body.find(".oa2-partnership-view").attr("hidden", true);
	}

	load_partnerships() {
		const partner = this._ps_partner;
		if (!partner || !partner.name) return;
		frappe.call({
			method: "frappe.client.get_list",
			args: {
				doctype: "OpenAS2 Partnership",
				fields: ["name", "instance"],
				or_filters: [
					["local_partner", "=", partner.name],
					["remote_partner", "=", partner.name],
				],
				limit_page_length: 200,
			},
			callback: (r) => this.load_partnership_files(r.message || []),
		});
	}

	load_partnership_files(rows) {
		const instances = [];
		(rows || []).forEach((row) => {
			if (row.instance && instances.indexOf(row.instance) === -1) instances.push(row.instance);
		});
		this._ps_xml = {};
		if (!instances.length) {
			this.render_partnerships(rows);
			return;
		}
		let left = instances.length;
		instances.forEach((instance) => {
			frappe.call({
				method: "openas2_manager.openas2.partnership_config.list_instance_partnerships",
				args: { instance_name: instance },
				callback: (r) => {
					const xml = (r.message && r.message.xml_partnerships) || [];
					this._ps_xml[instance] = xml.map((item) => item.partnership_name);
					left -= 1;
					if (!left) this.render_partnerships(rows);
				},
				error: () => {
					this._ps_xml[instance] = [];
					left -= 1;
					if (!left) this.render_partnerships(rows);
				},
			});
		});
	}

	partnership_written(row) {
		const names = (this._ps_xml && this._ps_xml[row.instance]) || [];
		return names.indexOf(row.partnership_name) !== -1;
	}

	render_partnerships(_rows) {
		/* Partnership table removed from this page. */
	}

	preview_partnership(name) {
		frappe.call({
			method: "openas2_manager.openas2.partnership_config.preview_partnership_change",
			args: { partnership_name: name },
			freeze: true,
			freeze_message: __("Generating proposal. Nothing is written yet."),
			callback: (r) => {
				if (!r || !r.message) return;
				this._ps_preview = r.message;
				this.render_partnership_preview(r.message);
			},
		});
	}

	render_partnership_preview(data) {
		const cls = data.classification || {};
		const $panel = this.$body.find(".oa2-ps-preview");
		$panel.removeAttr("hidden").html(`
			<h3>${this.esc(data.partnership_name || __("Partnership"))} · ${this.esc(data.change_type || "")}</h3>
			<p>${__("Not written yet. Apply writes partnerships.xml for this instance only. OpenAS2 is not started.")}</p>
			<p>${__("Added")}: ${this.esc((cls.added || []).join(", ") || "—")} ·
				${__("Modified")}: ${this.esc((cls.modified || []).join(", ") || "—")}</p>
			<details open>
				<summary>${__("Current partnerships.xml")}</summary>
				<pre>${this.esc(data.current_xml_redacted || "")}</pre>
			</details>
			<details open>
				<summary>${__("Proposed partnerships.xml")}</summary>
				<pre>${this.esc(data.proposed_xml_redacted || "")}</pre>
			</details>
			<details>
				<summary>${__("Difference")}</summary>
				<pre>${this.esc(data.diff_redacted || "")}</pre>
			</details>
			<button type="button" class="oa2-ps-apply-btn oa2-ps-preview-apply" data-change="${this.esc(data.configuration_change || "")}">${__("Apply")}</button>
		`);
		const node = $panel.get(0);
		if (node && node.scrollIntoView) node.scrollIntoView({ block: "nearest" });
	}

	apply_partnership(name) {
		frappe.confirm(
			__("Write this partnership into that instance's partnerships.xml? A backup is saved first. OpenAS2 will not be started."),
			() => {
				frappe.call({
					method: "openas2_manager.openas2.partnership_config.preview_partnership_change",
					args: { partnership_name: name },
					freeze: true,
					freeze_message: __("Preparing the file change…"),
					callback: (r) => {
						const change = r && r.message && r.message.configuration_change;
						if (!change) return;
						this.apply_configuration_change(change, true);
					},
				});
			}
		);
	}

	apply_configuration_change(name, already_confirmed) {
		const run = () => {
			frappe.call({
				method: "openas2_manager.openas2.partnership_config.apply_configuration_change",
				args: { configuration_change: name },
				freeze: true,
				freeze_message: __("Writing partnerships.xml…"),
				callback: (r) => {
					const msg = (r && r.message) || {};
					this._ps_preview = null;
					this.$body.find(".oa2-ps-preview").attr("hidden", true).empty();
					frappe.show_alert({
						message: __("partnerships.xml written. OpenAS2 was not started."),
						indicator: "green",
					});
					if (!msg || msg.status !== "Applied") {
						frappe.msgprint(__("Apply did not finish. partnerships.xml was not confirmed."));
					}
					this.load_partnerships();
				},
			});
		};
		if (already_confirmed) {
			run();
			return;
		}
		frappe.confirm(
			__("Write this partnership into that instance's partnerships.xml? A backup is saved first. OpenAS2 will not be started."),
			run
		);
	}

	mdn_label(row) {
		if (!cint(row.mdn_enabled)) return __("Off");
		return row.mdn_mode || __("On");
	}

	open_partnership_editor(name) {
		const run = () => {
			if (!this._ps_partner || !openas2_manager.partnership_ui) return;
			openas2_manager.partnership_ui.open({
				name: name || null,
				partner: this._ps_partner,
				on_save: () => this.load_partnerships(),
			});
		};
		if (openas2_manager.partnership_ui) run();
		else frappe.require("/assets/openas2_manager/js/openas2_partnership_ui.js", run);
	}

};
