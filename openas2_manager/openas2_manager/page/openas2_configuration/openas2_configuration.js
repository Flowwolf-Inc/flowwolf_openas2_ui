// Copyright (c) 2026, Lakshana and contributors
// For license information, please see license.txt

frappe.pages["openas2-configuration"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("OpenAS2 Configuration"),
		single_column: true,
	});

	frappe.breadcrumbs.add("OpenAS2 Manager");
	$(wrapper).addClass("oa2-config-page-wrapper");
	document.body.classList.add("oa2-has-sidebar");
	document.body.classList.add("oa2-use-inpage-sidebar");
	document.body.classList.remove("oa2-using-global-sidebar");
	document.body.classList.remove("oa2-sidebar-mounted");

	page.add_inner_button(__("New Instance"), () => {
		frappe.new_doc("OpenAS2 Instance");
	});

	wrapper.config_list = new openas2_manager.OpenAS2ConfigurationList(page);
	if (window.openas2_manager && openas2_manager.sync_layout) openas2_manager.sync_layout();
	wrapper.config_list.pin_header_button();
	[0, 90, 260].forEach((ms) => setTimeout(() => wrapper.config_list && wrapper.config_list.pin_header_button(), ms));
	if (window.openas2_manager && openas2_manager.sync_sidebar) {
		openas2_manager.sync_sidebar();
	}
};

frappe.pages["openas2-configuration"].on_page_show = function (wrapper) {
	document.body.classList.add("oa2-has-sidebar");
	document.body.classList.add("oa2-use-inpage-sidebar");
	document.body.classList.remove("oa2-using-global-sidebar");
	document.body.classList.remove("oa2-sidebar-mounted");
	if (wrapper.config_list) {
		wrapper.config_list.apply_theme(wrapper.config_list.get_theme());
		const opts = frappe.route_options || {};
		if (opts.oa2_action === "new-configuration") {
			frappe.route_options = null;
			frappe.new_doc("OpenAS2 Instance");
		} else if (opts.oa2_open_configuration) {
			const name = opts.oa2_open_configuration;
			frappe.route_options = null;
			setTimeout(() => wrapper.config_list && wrapper.config_list.open_edit_popup(name), 120);
		}
	}
	if (window.openas2_manager && openas2_manager.sync_layout) openas2_manager.sync_layout();
	if (wrapper.config_list) {
		const pin = () => wrapper.config_list && wrapper.config_list.pin_header_button();
		pin();
		[0, 90, 260].forEach((ms) => setTimeout(pin, ms));
	}
	if (window.openas2_manager && openas2_manager.sync_sidebar) {
		openas2_manager.sync_sidebar();
	}
};

frappe.provide("openas2_manager");

openas2_manager.OpenAS2ConfigurationList = class OpenAS2ConfigurationList {
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
		const button = this.$body.find(".oa2-create-service").get(0);
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
		const active = activeKey || "configuration";
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
				${this.sidebar_html("configuration")}
				<div class="oa2-main-pane">
					<div class="oa2-config-shell">
						<header class="oa2-config-header">
							<div>
								<h1 class="oa2-config-title">${__("Configurations")}</h1>
								<p class="oa2-config-subtitle">
									${__("OpenAS2 Instance records — manage endpoints, listeners, and identity settings.")}
								</p>
							</div>
							<div class="oa2-config-header-actions">
								<button type="button" class="oa2-btn oa2-btn-blue oa2-create-service">${__("Create Configuration")}</button>
							</div>
						</header>
					</div>
				</div>
			</div>
		`);

		this.pin_header_button();

		this.$body.on("click", ".oa2-create-service", (e) => {
			e.preventDefault();
			const open = () => {
				if (!window.openas2_manager || !openas2_manager.provision) return;
				openas2_manager.provision.prompt_and_create({
					on_success: () => this.load(),
				});
			};
			if (window.openas2_manager && openas2_manager.provision) {
				open();
				return;
			}
			frappe.require("/assets/openas2_manager/js/openas2_provision.js", open);
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

		if (window.openas2_manager && openas2_manager.sync_sidebar) {
			openas2_manager.sync_sidebar();
		}
	}

	close_edit_popup() {
		this.$body.find(".oa2-edit-modal-root").remove();
		this._edit_doc = null;
	}

	open_edit_popup(name) {
		this.close_edit_popup();
		frappe.call({
			method: "frappe.client.get",
			args: { doctype: "OpenAS2 Instance", name },
			freeze: true,
			freeze_message: __("Loading instance…"),
			callback: (r) => {
				const doc = r.message;
				if (!doc) {
					frappe.msgprint(__("Could not load this OpenAS2 Instance."));
					return;
				}
				this._edit_doc = doc;
				this.render_edit_popup(doc);
			},
			error: () => {
				frappe.msgprint(__("Failed to load OpenAS2 Instance."));
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
			const options = (opts.options || "").split("\n").filter((o) => o !== undefined);
			const choices = options
				.map((o) => {
					const sel = String(value || "") === o ? " selected" : "";
					return `<option value="${this.esc_raw(o)}"${sel}>${this.esc_raw(o || "—")}</option>`;
				})
				.join("");
			control = `<select class="oa2-edit-input" id="${id}" name="${fieldname}" data-fieldname="${fieldname}" ${readonly}>${choices}</select>`;
		} else if (type === "Check") {
			const checked = cint(value) ? " checked" : "";
			control = `<label class="oa2-edit-check"><input type="checkbox" id="${id}" name="${fieldname}" data-fieldname="${fieldname}" data-type="Check"${checked} ${readonly}/> <span>${__("Enabled")}</span></label>`;
		} else if (type === "Password") {
			control = `<input type="password" class="oa2-edit-input" id="${id}" name="${fieldname}" data-fieldname="${fieldname}" data-type="Password" value="" placeholder="${__(
				"Leave blank to keep current"
			)}" autocomplete="new-password" ${readonly}/>`;
		} else if (type === "Small Text") {
			control = `<textarea class="oa2-edit-input oa2-edit-textarea" id="${id}" name="${fieldname}" data-fieldname="${fieldname}" rows="3" ${readonly}>${this.esc_raw(
				value
			)}</textarea>`;
		} else if (type === "Int") {
			control = `<input type="number" class="oa2-edit-input" id="${id}" name="${fieldname}" data-fieldname="${fieldname}" data-type="Int" value="${this.esc_raw(
				value == null || value === "" ? "" : value
			)}" min="0" ${readonly}/>`;
		} else if (type === "Datetime") {
			control = `<input type="text" class="oa2-edit-input" id="${id}" name="${fieldname}" data-fieldname="${fieldname}" value="${this.esc_raw(
				value
			)}" ${readonly}/>`;
		} else {
			control = `<input type="text" class="oa2-edit-input" id="${id}" name="${fieldname}" data-fieldname="${fieldname}" value="${this.esc_raw(
				value
			)}" ${readonly}/>`;
		}

		return `<div class="oa2-edit-field${opts.readonly ? " is-readonly" : ""}">
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

	render_edit_popup(doc) {
		const theme = this.get_theme();
		const f = (name, label, type, opts) => this.field_input(name, label, type, doc[name], opts);
		const nav = [
			["identity", __("Identity")],
			["listeners", __("AS2 Listeners")],
			["security", __("Security")],
			["mdn", __("MDN Settings")],
			["storage", __("Storage")],
		]
			.map(
				([key, label], i) =>
					`<button type="button" class="oa2-edit-nav-btn${i === 0 ? " is-active" : ""}" data-section="${key}">${label}</button>`
			)
			.join("");
		const panels = [
			this.edit_panel(
				"identity",
				true,
				this.section("Identity", [
					f("instance_name", "Name", "Data", { reqd: 1 }),
					f("instance_type", "Instance Type", "Select", {
						reqd: 1,
						options: "Shipper\nBroker\nCarrier\nCompanyC",
					}),
					f("as2_id", "AS2 ID", "Data", { reqd: 1 }),
					f("host", "Host", "Data", { reqd: 1 }),
					f("status", "Status", "Select", { reqd: 1, options: "Active\nInactive\nError" }),
					f("description", "Description", "Small Text"),
				].join("")) +
					this.section("Operations", [
						f("lifecycle_status", "Lifecycle Status", "Select", {
							options: "Unknown\nProvisioning\nStopped\nStarting\nRunning\nStopping\nFailed",
						}),
						f("provision_source", "Provision Source", "Select", {
							options: "External\nManager Provisioned",
						}),
						f("connection_status", "Connection Status", "Select", {
							options: "Unknown\nConnected\nFailed",
							readonly: 1,
						}),
						f("last_tested", "Last Tested", "Datetime", { readonly: 1 }),
					].join(""))
			),
			this.edit_panel(
				"listeners",
				false,
				this.section("AS2 Listeners", [
					f("http_enabled", "Enable HTTP", "Check"),
					f("http_port", "HTTP Port", "Int"),
					f("https_enabled", "Enable HTTPS", "Check"),
					f("https_port", "HTTPS Port", "Int"),
					f("health_port", "Health Port", "Int"),
					f("tracking_port", "Tracking Port", "Int"),
				].join("")) +
					this.section("URL to share with partners", [
						f("protocol", "Primary Protocol", "Select", { reqd: 1, options: "HTTP\nHTTPS" }),
						f("port", "Primary Port", "Int", { reqd: 1 }),
						f("published_as2_url", "Published AS2 URL", "Data", { readonly: 1 }),
					].join(""))
			),
			this.edit_panel(
				"security",
				false,
				this.section("Security", [
					f("as2_keystore_path", "AS2 Keystore Path", "Data"),
					f("x509_alias", "X509 Alias", "Data"),
					f("as2_keystore_password", "AS2 Keystore Password", "Password"),
					f("ssl_keystore_path", "SSL Keystore Path", "Data"),
					f("certificate_status", "Certificate Status", "Select", {
						options: "Unknown\nDeferred\nConfigured\nMissing",
					}),
				].join(""))
			),
			this.edit_panel(
				"mdn",
				false,
				this.section("MDN Settings", [
					f("mdn_mode", "MDN Mode", "Select", { options: "Synchronous\nAsynchronous" }),
					f("mdn_enabled", "MDN Enabled", "Check"),
					f("mdn_http_enabled", "Enable MDN HTTP", "Check"),
					f("mdn_http_port", "MDN HTTP Port", "Int"),
					f("mdn_https_enabled", "Enable MDN HTTPS", "Check"),
					f("mdn_https_port", "MDN HTTPS Port", "Int"),
					f("async_mdn_url", "Async MDN URL", "Data"),
				].join(""))
			),
			this.edit_panel(
				"storage",
				false,
				this.section("Storage", [
					f("openas2_home", "OpenAS2 Home", "Data"),
					f("windows_home", "Windows Home", "Data", { readonly: 1 }),
					f("inbox_path", "Inbox Path", "Data"),
					f("outbox_path", "Outbox Path", "Data"),
					f("instance_slug", "Instance Slug", "Data", { readonly: 1 }),
				].join("")) +
					this.section("Runtime Control", [
						f("control_mode", "Control Mode", "Select", {
							options: "none\nagent\nwindows_service\nlinux_start_script",
						}),
						f("service_name", "Service Name", "Data", { readonly: 1 }),
						f("provisioned_on", "Provisioned On", "Datetime", { readonly: 1 }),
						f("runtime_pid", "Runtime PID", "Int", { readonly: 1 }),
						f("process_status", "Process Status", "Select", {
							options: "\nUnknown\nStopped\nRunning",
							readonly: 1,
						}),
						f("port_status", "Port Status", "Select", {
							options: "\nUnknown\nListening\nNot Listening",
							readonly: 1,
						}),
						f("openas2_health", "OpenAS2 Health", "Data", { readonly: 1 }),
						f("last_health_check", "Last Health Check", "Datetime", { readonly: 1 }),
						f("last_error", "Last Error", "Small Text", { readonly: 1 }),
					].join(""))
			),
		].join("");
		const body = `<nav class="oa2-edit-nav" aria-label="${__("Configuration sections")}">${nav}</nav><div class="oa2-edit-pane">${panels}</div>`;

		const title = doc.instance_name || doc.name;
		const $modal = $(`
			<div class="oa2-edit-modal-root" data-oa2-theme="${theme}" role="dialog" aria-modal="true" aria-labelledby="oa2-edit-modal-title">
				<div class="oa2-edit-modal-backdrop" data-oa2-cancel="1"></div>
				<div class="oa2-edit-modal">
					<header class="oa2-edit-modal-header">
						<div>
							<h2 id="oa2-edit-modal-title" class="oa2-edit-modal-title">${__("Edit")} ${this.esc(title)}</h2>
							<p class="oa2-edit-modal-sub">${__("OpenAS2 Instance")} · <span class="oa2-mono">${this.esc(
								doc.name
							)}</span></p>
						</div>
						<button type="button" class="oa2-edit-modal-close" data-oa2-cancel="1" aria-label="${__("Cancel")}">×</button>
					</header>
					<div class="oa2-edit-modal-body oa2-edit-layout">${body}</div>
					<footer class="oa2-edit-modal-footer">
						<button type="button" class="oa2-edit-btn-cancel" data-oa2-cancel="1">${__("Cancel")}</button>
						<button type="button" class="oa2-edit-btn-update">${__("Save Configuration")}</button>
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
			this.save_edit_popup();
		});

		$modal.on("keydown", (e) => {
			if (e.key === "Escape") {
				e.preventDefault();
				this.close_edit_popup();
			}
		});
	}

	collect_edit_values() {
		const $root = this.$body.find(".oa2-edit-modal-root");
		const updates = {};
		$root.find("[data-fieldname]").each((_, el) => {
			const $el = $(el);
			if ($el.is(":disabled") || $el.prop("readonly")) return;
			const fieldname = $el.attr("data-fieldname");
			const type = $el.attr("data-type") || "";
			if (type === "Check") {
				updates[fieldname] = $el.is(":checked") ? 1 : 0;
			} else if (type === "Password") {
				const v = $el.val();
				if (v) updates[fieldname] = v;
			} else if (type === "Int") {
				const v = $el.val();
				updates[fieldname] = v === "" || v == null ? null : cint(v);
			} else {
				updates[fieldname] = $el.val();
			}
		});
		return updates;
	}

	save_edit_popup() {
		if (!this._edit_doc || !this._edit_doc.name) return;
		const updates = this.collect_edit_values();
		if (!updates.instance_name || !updates.as2_id || !updates.host || !updates.instance_type) {
			frappe.msgprint(__("Name, Instance Type, AS2 ID, and Host are required."));
			return;
		}

		const name = this._edit_doc.name;
		const $btn = this.$body.find(".oa2-edit-btn-update");
		$btn.prop("disabled", true).text(__("Saving…"));

		frappe.call({
			method: "frappe.client.set_value",
			args: {
				doctype: "OpenAS2 Instance",
				name: name,
				fieldname: updates,
			},
			freeze: true,
			freeze_message: __("Saving…"),
			callback: (r) => {
				if (r.exc) {
					$btn.prop("disabled", false).text(__("Save Configuration"));
					frappe.msgprint(__("Failed to update OpenAS2 Instance."));
					return;
				}
				frappe.show_alert({ message: __("Instance updated"), indicator: "green" });
				this.close_edit_popup();
				this.load();
			},
			error: () => {
				$btn.prop("disabled", false).text(__("Save Configuration"));
				frappe.msgprint(__("Failed to update OpenAS2 Instance."));
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
		else if (s === "error") tone = "failed";
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
		/* Instance list removed from this page; keep for save callbacks. */
	}
};
