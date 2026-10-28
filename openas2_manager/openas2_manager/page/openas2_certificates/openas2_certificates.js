// Copyright (c) 2026, Lakshana and contributors
// For license information, please see license.txt

frappe.pages["openas2-certificates"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Certificates"),
		single_column: true,
	});

	frappe.breadcrumbs.add("OpenAS2 Manager");
	$(wrapper).addClass("oa2-config-page-wrapper");
	document.body.classList.add("oa2-has-sidebar");
	document.body.classList.add("oa2-use-inpage-sidebar");
	document.body.classList.remove("oa2-using-global-sidebar");
	document.body.classList.remove("oa2-sidebar-mounted");

	page.add_inner_button(__("New Certificate"), () => {
		frappe.new_doc("AS2 Certificate");
	});

	wrapper.certificates_list = new openas2_manager.OpenAS2CertificatesList(page);
	if (window.openas2_manager && openas2_manager.sync_layout) openas2_manager.sync_layout();
	wrapper.certificates_list.pin_header_button();
	[0, 90, 260].forEach((ms) => setTimeout(() => wrapper.certificates_list && wrapper.certificates_list.pin_header_button(), ms));
	if (window.openas2_manager && openas2_manager.sync_sidebar) {
		openas2_manager.sync_sidebar();
	}
};

frappe.pages["openas2-certificates"].on_page_show = function (wrapper) {
	document.body.classList.add("oa2-has-sidebar");
	document.body.classList.add("oa2-use-inpage-sidebar");
	document.body.classList.remove("oa2-using-global-sidebar");
	document.body.classList.remove("oa2-sidebar-mounted");
	if (wrapper.certificates_list) {
		wrapper.certificates_list.apply_theme(wrapper.certificates_list.get_theme());
		const opts = frappe.route_options || {};
		if (opts.oa2_action === "new-certificate") {
			frappe.route_options = null;
			frappe.new_doc("AS2 Certificate");
		} else if (opts.oa2_open_certificate) {
			const name = opts.oa2_open_certificate;
			frappe.route_options = null;
			setTimeout(() => wrapper.certificates_list && wrapper.certificates_list.open_edit_popup(name), 120);
		}
	}
	if (window.openas2_manager && openas2_manager.sync_layout) openas2_manager.sync_layout();
	if (wrapper.certificates_list) {
		const pin = () => wrapper.certificates_list && wrapper.certificates_list.pin_header_button();
		pin();
		[0, 90, 260].forEach((ms) => setTimeout(pin, ms));
	}
	if (window.openas2_manager && openas2_manager.sync_sidebar) {
		openas2_manager.sync_sidebar();
	}
};

frappe.provide("openas2_manager");

openas2_manager.OpenAS2CertificatesList = class OpenAS2CertificatesList {
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
		const button = this.$body.find(".oa2-create-certificate").get(0);
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
		const active = activeKey || "certificates";
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
				${this.sidebar_html("certificates")}
				<div class="oa2-main-pane">
					<div class="oa2-config-shell">
						<header class="oa2-config-header">
							<div>
								<h1 class="oa2-config-title">${__("Certificates")}</h1>
								<p class="oa2-config-subtitle">
									${__("AS2 Certificate records — purpose, type, alias, and validity.")}
								</p>
							</div>
							<div class="oa2-config-header-actions">
								<button type="button" class="oa2-btn oa2-btn-blue oa2-create-certificate">${__("Create Certificate")}</button>
							</div>
						</header>
					</div>
				</div>
			</div>
		`);

		this.pin_header_button();

		this.$body.on("click", ".oa2-create-certificate", (e) => {
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

		if (window.openas2_manager && openas2_manager.sync_sidebar) {
			openas2_manager.sync_sidebar();
		}
	}

	close_edit_popup() {
		this.$body.find(".oa2-edit-modal-root").remove();
		this._edit_doc = null;
		this._cert_mode = null;
	}

	open_create_popup() {
		this.close_edit_popup();
		this._cert_mode = "create";
		this.load_link_options((opts) => {
			this.render_edit_popup(
				{
					purpose: "Own Key Pair",
					certificate_type: "Both",
					status: "Draft",
					key_size: "2048",
					validity_days: 825,
				},
				opts || {}
			);
		});
	}

	open_edit_popup(name) {
		this.close_edit_popup();
		frappe.call({
			method: "frappe.client.get",
			args: { doctype: "AS2 Certificate", name },
			freeze: true,
			freeze_message: __("Loading certificate…"),
			callback: (r) => {
				const doc = r.message;
				if (!doc) {
					frappe.msgprint(__("Could not load this AS2 Certificate."));
					return;
				}
				this._edit_doc = doc;
				this._cert_mode = "edit";
				this.load_link_options((opts) => {
					this.render_edit_popup(doc, opts || {});
				});
			},
			error: () => {
				frappe.msgprint(__("Failed to load AS2 Certificate."));
			},
		});
	}

	load_link_options(done) {
		const out = { instances: [], partners: [] };
		let pending = 2;
		const finish = () => {
			pending -= 1;
			if (pending <= 0) done(out);
		};

		frappe.call({
			method: "frappe.client.get_list",
			args: {
				doctype: "OpenAS2 Instance",
				fields: ["name", "instance_name"],
				limit_page_length: 200,
				order_by: "instance_name asc",
			},
			callback: (r) => {
				out.instances = r.message || [];
				finish();
			},
			error: () => finish(),
		});

		frappe.call({
			method: "frappe.client.get_list",
			args: {
				doctype: "AS2 Partner",
				fields: ["name", "partner_name"],
				limit_page_length: 200,
				order_by: "partner_name asc",
			},
			callback: (r) => {
				out.partners = r.message || [];
				finish();
			},
			error: () => finish(),
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
			const labelKey = opts.link_label || "name";
			const choices = [`<option value="">${__("— None —")}</option>`]
				.concat(
					options.map((o) => {
						const val = o.name || "";
						const labelText = o[labelKey] || val;
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
		} else if (type === "Password") {
			control = `<input type="password" class="oa2-edit-input" id="${id}" name="${fieldname}" data-fieldname="${fieldname}" data-type="Password" value="" placeholder="${__(
				"Leave blank to keep current"
			)}" autocomplete="new-password" ${readonly}/>`;
		} else if (type === "Int") {
			control = `<input type="number" class="oa2-edit-input" id="${id}" name="${fieldname}" data-fieldname="${fieldname}" data-type="Int" value="${this.esc_raw(
				value == null || value === "" ? "" : value
			)}" min="0" ${readonly}/>`;
		} else if (type === "Date") {
			control = `<input type="date" class="oa2-edit-input" id="${id}" name="${fieldname}" data-fieldname="${fieldname}" data-type="Date" value="${this.esc_raw(
				value
			)}" ${readonly}/>`;
		} else if (type === "File") {
			control = `<input type="file" class="oa2-edit-input" id="${id}" data-cert-file="1" accept=".cer,.crt,.pem,.der" />`;
		} else if (type === "Small Text") {
			control = `<textarea class="oa2-edit-input oa2-edit-textarea" id="${id}" name="${fieldname}" data-fieldname="${fieldname}" rows="3" ${readonly}>${this.esc_raw(
				value
			)}</textarea>`;
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

	render_edit_popup(doc, linkOpts) {
		const theme = this.get_theme();
		const instances = (linkOpts && linkOpts.instances) || [];
		const partners = (linkOpts && linkOpts.partners) || [];
		const f = (name, label, type, opts) => this.field_input(name, label, type, doc[name], opts);

		const creating = this._cert_mode === "create" || !doc.name;
		const nav = [
			["details", __("Certificate Details")],
			["file", __("Certificate File")],
			["identity", __("X509 / Identity")],
			["security", __("Security")],
			["validity", __("Validity")],
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
				this.section("Certificate Details", [
					f("certificate_name", "Certificate Name", "Data", { reqd: 1, readonly: !creating }),
					f("purpose", "Purpose", "Select", {
						reqd: 1,
						options: "Own Key Pair\nPartner Public Certificate",
					}),
					f("owner_type", "Company / TMS", "Select", {
						reqd: 1,
						options: "\nShipper\nBroker\nCarrier\nCompanyC",
					}),
					f("openas2_instance", "OpenAS2 Instance", "Link", {
						link_options: instances,
						link_label: "instance_name",
					}),
					f("certificate_type", "Certificate Type", "Select", {
						reqd: 1,
						options: "Signing\nEncryption\nBoth",
					}),
					f("status", "Status", "Select", {
						reqd: 1,
						options: "Draft\nActive\nExpired\nRevoked",
					}),
					f("description", "Description", "Small Text"),
				].join(""))
			),
			this.edit_panel(
				"file",
				false,
				this.section("Certificate File", [
					f("certificate_upload", "Certificate File", "File"),
					`<p class="oa2-edit-hint">${__(
						"Public certificate only (.cer, .crt, or .pem). Required for a partner public certificate."
					)}</p>`,
					f("certificate_file", "Stored Certificate File", "Data"),
					f("public_cert_fingerprint", "Public Cert Fingerprint (SHA-256)", "Data", { readonly: 1 }),
					f("exchange_partner", "Exchange Partner", "Link", {
						link_options: partners,
						link_label: "partner_name",
					}),
					f("exchange_status", "Exchange Status", "Select", {
						options: "Not Shared\nReady to Share\nShared With Partner\nPartner Cert Imported",
					}),
					f("exchange_notes", "Exchange Notes", "Small Text"),
				].join(""))
			),
			this.edit_panel(
				"identity",
				false,
				this.section("X509 / Identity", [
					f("x509_alias", "X509 Alias", "Data", { reqd: 1 }),
					f("common_name", "Common Name (CN)", "Data", { reqd: 1 }),
					f("organization", "Organization (O)", "Data"),
				].join(""))
			),
			this.edit_panel(
				"security",
				false,
				this.section("Security", [
					f("key_size", "Key Size", "Select", { options: "2048\n4096" }),
					f("keystore_password", "Keystore Password", "Password"),
					f("keystore_path", "Keystore Path (.p12)", "Data", { readonly: 1 }),
					f("private_key_stored", "Private Key File Created", "Check", { readonly: 1 }),
					f("generation_notes", "Generation Notes", "Small Text", { readonly: 1 }),
				].join(""))
			),
			this.edit_panel(
				"validity",
				false,
				this.section("Validity", [
					f("valid_from", "Valid From", "Date", { readonly: 1 }),
					f("valid_until", "Valid Until", "Date", { readonly: 1 }),
					f("validity_days", "Validity Days", "Int"),
					f("expiry_info", "Expiry Information", "Small Text", { readonly: 1 }),
				].join(""))
			),
		].join("");
		const body = `<nav class="oa2-edit-nav" aria-label="${__("Certificate sections")}">${nav}</nav><div class="oa2-edit-pane">${panels}</div>`;

		const title = doc.certificate_name || doc.name || __("New Certificate");
		const saveLabel = creating ? __("Create Certificate") : __("Save Certificate");
		const $modal = $(`
			<div class="oa2-edit-modal-root" data-oa2-theme="${theme}" role="dialog" aria-modal="true" aria-labelledby="oa2-edit-modal-title">
				<div class="oa2-edit-modal-backdrop" data-oa2-cancel="1"></div>
				<div class="oa2-edit-modal">
					<header class="oa2-edit-modal-header">
						<div>
							<h2 id="oa2-edit-modal-title" class="oa2-edit-modal-title">${creating ? __("Create Certificate") : __("Edit") + " " + this.esc(title)}</h2>
							<p class="oa2-edit-modal-sub">${__("AS2 Certificate")}${
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
			if (this._cert_mode === "create") this.save_create_popup();
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

	save_create_popup() {
		if (this.saving) return;
		const updates = this.collect_edit_values();
		if (
			!updates.certificate_name ||
			!updates.certificate_type ||
			!updates.owner_type ||
			!updates.common_name ||
			!updates.x509_alias ||
			!updates.purpose
		) {
			frappe.msgprint(
				__("Certificate name, type, company, common name, X509 alias, and purpose are required.")
			);
			return;
		}
		const fileInput = this.$body.find("[data-cert-file]").get(0);
		const file = fileInput && fileInput.files && fileInput.files[0];
		if (updates.purpose === "Partner Public Certificate" && !file) {
			frappe.msgprint(__("Attach the partner public certificate file before saving."));
			return;
		}
		const doc = {
			doctype: "AS2 Certificate",
			certificate_name: updates.certificate_name,
			certificate_type: updates.certificate_type,
			purpose: updates.purpose,
			owner_type: updates.owner_type,
			common_name: updates.common_name,
			x509_alias: updates.x509_alias,
			status: updates.status || "Draft",
		};
		[
			"organization",
			"openas2_instance",
			"description",
			"key_size",
			"validity_days",
			"exchange_partner",
			"exchange_status",
			"exchange_notes",
			"certificate_file",
		].forEach((key) => {
			if (updates[key] !== undefined && updates[key] !== "" && updates[key] != null) doc[key] = updates[key];
		});
		if (updates.keystore_password) doc.keystore_password = updates.keystore_password;
		if (doc.purpose === "Own Key Pair") {
			doc.key_size = doc.key_size || "2048";
			if (doc.validity_days == null) doc.validity_days = updates.validity_days || 825;
		}
		this.saving = true;
		const $btn = this.$body.find(".oa2-edit-btn-update");
		$btn.prop("disabled", true).text(__("Saving…"));
		const fail = () => {
			this.saving = false;
			$btn.prop("disabled", false).text(__("Create Certificate"));
		};
		frappe.call({
			method: "frappe.client.insert",
			args: { doc },
			freeze: true,
			freeze_message: __("Creating certificate…"),
			callback: (r) => {
				const name = r && r.message && r.message.name;
				if (!name) {
					fail();
					return;
				}
				const done = () => {
					this.saving = false;
					frappe.show_alert({ message: __("Certificate created"), indicator: "green" });
					this.close_edit_popup();
					this.load();
				};
				if (doc.purpose === "Partner Public Certificate") {
					this.upload_certificate_file(name, file)
						.then(() => {
							frappe.call({
								method: "openas2_manager.certificates.generation.import_partner_public_certificate",
								args: { name },
								callback: done,
								error: fail,
							});
						})
						.catch(fail);
					return;
				}
				frappe.call({
					method: "openas2_manager.certificates.generation.generate_own_keypair",
					args: { name },
					callback: done,
					error: fail,
				});
			},
			error: fail,
		});
	}

	upload_certificate_file(docname, file) {
		const data = new FormData();
		data.append("file", file, file.name);
		data.append("doctype", "AS2 Certificate");
		data.append("docname", docname);
		data.append("fieldname", "certificate_file");
		data.append("is_private", "1");
		return fetch("/api/method/upload_file", {
			method: "POST",
			headers: {
				"X-Frappe-CSRF-Token": frappe.csrf_token,
				Accept: "application/json",
			},
			body: data,
		}).then(async (res) => {
			const body = await res.json();
			if (!res.ok || body.exc) {
				frappe.msgprint(body._server_messages || __("Could not upload the certificate file."));
				throw new Error("upload");
			}
			return body.message;
		});
	}

	save_edit_popup() {
		if (!this._edit_doc || !this._edit_doc.name) return;
		const updates = this.collect_edit_values();
		if (
			!updates.purpose ||
			!updates.owner_type ||
			!updates.x509_alias ||
			!updates.certificate_type ||
			!updates.status ||
			!updates.common_name
		) {
			frappe.msgprint(
				__("Purpose, Company, X509 Alias, Certificate Type, Status, and Common Name are required.")
			);
			return;
		}

		const name = this._edit_doc.name;
		const $btn = this.$body.find(".oa2-edit-btn-update");
		$btn.prop("disabled", true).text(__("Saving…"));

		frappe.call({
			method: "frappe.client.set_value",
			args: {
				doctype: "AS2 Certificate",
				name: name,
				fieldname: updates,
			},
			freeze: true,
			freeze_message: __("Saving…"),
			callback: (r) => {
				if (r.exc) {
					$btn.prop("disabled", false).text(__("Save Certificate"));
					frappe.msgprint(__("Failed to update AS2 Certificate."));
					return;
				}
				frappe.show_alert({ message: __("Certificate updated"), indicator: "green" });
				this.close_edit_popup();
				this.load();
			},
			error: () => {
				$btn.prop("disabled", false).text(__("Save Certificate"));
				frappe.msgprint(__("Failed to update AS2 Certificate."));
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
		else if (s === "draft") tone = "muted";
		else if (s === "expired") tone = "warn";
		else if (s === "revoked") tone = "failed";
		return `<span class="oa2-pill oa2-pill-${tone}">${this.esc(status || "—")}</span>`;
	}

	purpose_badge(purpose) {
		const p = (purpose || "").toLowerCase();
		let tone = "muted";
		if (p.indexOf("own") === 0) tone = "blue";
		else if (p.indexOf("partner") === 0) tone = "purple";
		return `<span class="oa2-type-pill oa2-type-${tone}"><i class="oa2-type-dot"></i>${this.esc(
			purpose || "—"
		)}</span>`;
	}

	type_badge(type) {
		const t = (type || "").toLowerCase();
		let tone = "muted";
		if (t === "signing") tone = "purple";
		else if (t === "encryption") tone = "blue";
		else if (t === "both") tone = "green";
		return `<span class="oa2-type-pill oa2-type-${tone}"><i class="oa2-type-dot"></i>${this.esc(
			type || "—"
		)}</span>`;
	}

	company_badge(company) {
		const c = (company || "").toLowerCase();
		let tone = "muted";
		if (c === "broker") tone = "blue";
		else if (c === "carrier") tone = "green";
		else if (c === "shipper") tone = "orange";
		else if (c === "companyc") tone = "purple";
		return `<span class="oa2-type-pill oa2-type-${tone}"><i class="oa2-type-dot"></i>${this.esc(
			company || "—"
		)}</span>`;
	}

	load() {
		/* Certificate list removed from this page; keep for save callbacks. */
	}
};
