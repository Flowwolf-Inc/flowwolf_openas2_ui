// Copyright (c) 2026, Lakshana and contributors
// For license information, please see license.txt

frappe.pages["openas2-create-configuration"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Create Configuration"),
		single_column: true,
	});
	frappe.breadcrumbs.add("OpenAS2 Manager");
	$(wrapper).addClass("oa2-config-page-wrapper oa2-create-config-page-wrapper");
	document.body.classList.add("oa2-has-sidebar", "oa2-use-inpage-sidebar");
	document.body.classList.remove("oa2-using-global-sidebar", "oa2-sidebar-mounted");
	wrapper.create_configuration_page = new openas2_manager.OpenAS2CreateConfigurationPage(page);
	if (window.openas2_manager && openas2_manager.sync_layout) openas2_manager.sync_layout();
};

frappe.pages["openas2-create-configuration"].on_page_show = function (wrapper) {
	document.body.classList.add("oa2-has-sidebar", "oa2-use-inpage-sidebar");
	document.body.classList.remove("oa2-using-global-sidebar", "oa2-sidebar-mounted");
	if (wrapper.create_configuration_page) {
		wrapper.create_configuration_page.apply_theme(wrapper.create_configuration_page.get_theme());
		wrapper.create_configuration_page.load_certificates();
	}
	if (window.openas2_manager && openas2_manager.sync_layout) openas2_manager.sync_layout();
};

frappe.provide("openas2_manager");

openas2_manager.OpenAS2CreateConfigurationPage = class OpenAS2CreateConfigurationPage {
	constructor(page) {
		this.page = page;
		this.THEME_KEY = "oa2-dashboard-theme";
		this.saving = false;
		this.docName = "";
		this.certificates = [];
		this.$body = $(page.body).addClass("oa2-config-list-page oa2-create-config-page");
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
		const active = "configuration";
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
		const id = "oa2-cfg-" + name;
		const mark = extra && extra.required ? " *" : "";
		if (type === "select") {
			const options = ((extra && extra.options) || [])
				.map((opt) => {
					const value = typeof opt === "string" ? opt : opt.value;
					const labelText = typeof opt === "string" ? opt : opt.label;
					return `<option value="${frappe.utils.escape_html(value)}">${frappe.utils.escape_html(labelText)}</option>`;
				})
				.join("");
			return `<label class="oa2-set-field" for="${id}"><span>${frappe.utils.escape_html(label)}${mark}</span><select id="${id}" data-field="${name}">${options}</select></label>`;
		}
		const inputType = type === "password" ? "password" : type === "number" ? "number" : "text";
		return `<label class="oa2-set-field" for="${id}"><span>${frappe.utils.escape_html(label)}${mark}</span><input id="${id}" type="${inputType}" data-field="${name}" autocomplete="off" /></label>`;
	}

	check(name, label) {
		const id = "oa2-cfg-" + name;
		return `<label class="oa2-set-check" for="${id}"><input id="${id}" type="checkbox" data-field="${name}" /><span>${frappe.utils.escape_html(label)}</span></label>`;
	}

	section(title, hint, inner) {
		return `<section class="oa2-config-card oa2-set-card"><header class="oa2-set-card-head"><h2>${frappe.utils.escape_html(title)}</h2>${hint ? `<p>${frappe.utils.escape_html(hint)}</p>` : ""}</header><div class="oa2-set-grid">${inner}</div></section>`;
	}

	make() {
		const identity =
			this.field("instance_name", __("Configuration name"), "text", { required: true }) +
			this.field("instance_type", __("Instance type"), "select", {
				required: true,
				options: [
					{ value: "", label: __("Select an instance type") },
					"Shipper",
					"Broker",
					"Carrier",
					"CompanyC",
				],
			}) +
			this.field("as2_id", __("AS2 ID"), "text", { required: true }) +
			this.field("host", __("Host"), "text", { required: true }) +
			this.field("protocol", __("Primary protocol"), "select", {
				required: true,
				options: ["HTTPS", "HTTP"],
			}) +
			this.field("listener_port", __("Listener port"), "number", { required: true });

		const storage =
			this.field("openas2_home", __("Storage / data directory"), "text") +
			this.field("inbox_path", __("Inbox path"), "text") +
			this.field("outbox_path", __("Outbox path"), "text");

		const keystore =
			this.field("certificate", __("Certificate"), "select", {
				options: [{ value: "", label: __("Loading certificates…") }],
			}) +
			this.field("x509_alias", __("X509 alias"), "text") +
			this.field("as2_keystore_path", __("AS2 keystore path"), "text") +
			this.field("as2_keystore_password", __("AS2 keystore password"), "password") +
			this.field("ssl_keystore_path", __("SSL keystore path"), "text");

		const security = `
			<div><dt>${__("Signing")}</dt><dd data-sec="signing">—</dd></div>
			<div><dt>${__("Encryption")}</dt><dd data-sec="encryption">—</dd></div>
			<div><dt>${__("Certificate type")}</dt><dd data-sec="type">—</dd></div>
		`;

		const mdn =
			this.check("mdn_enabled", __("MDN enabled")) +
			this.field("mdn_mode", __("MDN mode"), "select", { options: ["Synchronous", "Asynchronous"] }) +
			this.check("mdn_http_enabled", __("Enable MDN HTTP")) +
			this.field("mdn_http_port", __("MDN HTTP port"), "number") +
			this.check("mdn_https_enabled", __("Enable MDN HTTPS")) +
			this.field("mdn_https_port", __("MDN HTTPS port"), "number") +
			this.field("async_mdn_url", __("Async MDN URL"), "text");

		this.$body.html(`
			<div class="oa2-app-frame">
				${this.sidebar_html()}
				<div class="oa2-main-pane">
					<div class="oa2-config-shell">
						<header class="oa2-config-header">
							<div>
								<h1 class="oa2-config-title">${__("Create Configuration")}</h1>
								<p class="oa2-config-subtitle">${__("Create an OpenAS2 Instance with listener, storage, keystore, and MDN settings.")}</p>
							</div>
							<div class="oa2-config-header-actions"></div>
						</header>
						<form class="oa2-set-form" novalidate>
							${this.section(__("Instance"), __("Name, AS2 identity, host, and listener."), identity)}
							${this.section(__("Storage"), __("OpenAS2 home and message directories on this instance."), storage)}
							${this.section(__("Keystore / certificate"), __("Select an existing AS2 Certificate, or enter keystore paths directly."), keystore)}
							<section class="oa2-config-card oa2-set-card">
								<header class="oa2-set-card-head"><h2>${__("Encryption / signature")}</h2><p>${__("Taken from the selected certificate. Signing and encryption are not stored as a second record.")}</p></header>
								<dl class="oa2-preview">${security}</dl>
							</section>
							${this.section(__("MDN settings"), __("Message disposition notification mode and listeners."), mdn)}
							<div class="oa2-form-actions">
								<button type="button" class="oa2-btn oa2-btn-secondary oa2-cfg-cancel">${__("Cancel / Back")}</button>
								<button type="submit" class="oa2-btn oa2-btn-primary oa2-cfg-save">${__("Create Configuration")}</button>
							</div>
						</form>
					</div>
				</div>
			</div>
		`);

		this.$body.find('[data-field="mdn_enabled"]').prop("checked", true);
		this.$body.on("click", ".oa2-sidebar-inpage [data-route]", (e) => {
			e.preventDefault();
			const route = $(e.currentTarget).attr("data-route");
			if (route) frappe.set_route(route);
		});
		this.$body.on("click", ".oa2-cfg-cancel", (e) => {
			e.preventDefault();
			frappe.set_route("openas2-configuration");
		});
		this.$body.on("change", '[data-field="certificate"]', () => this.apply_certificate());
		this.$body.on("change", '[data-field="mdn_enabled"], [data-field="mdn_mode"], [data-field="mdn_http_enabled"], [data-field="mdn_https_enabled"]', () =>
			this.sync_mdn()
		);
		this.$body.on("submit", "form", (e) => {
			e.preventDefault();
			this.save();
		});
		this.sync_mdn();
		this.apply_certificate();
	}

	checked(name) {
		return this.$body.find(`[data-field="${name}"]`).is(":checked") ? 1 : 0;
	}

	value(name) {
		const $el = this.$body.find(`[data-field="${name}"]`);
		if ($el.is(":checkbox")) return this.checked(name);
		return String($el.val() || "").trim();
	}

	sync_mdn() {
		const enabled = !!this.checked("mdn_enabled");
		const asyncMode = this.value("mdn_mode") === "Asynchronous";
		this.$body.find('[data-field="mdn_mode"], [data-field="mdn_http_enabled"], [data-field="mdn_https_enabled"]').prop("disabled", !enabled);
		const httpOn = enabled && !!this.checked("mdn_http_enabled");
		const httpsOn = enabled && !!this.checked("mdn_https_enabled");
		this.$body.find('[data-field="mdn_http_port"]').prop("disabled", !httpOn);
		this.$body.find('[data-field="mdn_https_port"]').prop("disabled", !httpsOn);
		this.$body.find('[data-field="async_mdn_url"]').prop("disabled", !(enabled && asyncMode));
		if (!enabled) {
			this.$body.find('[data-field="mdn_http_enabled"], [data-field="mdn_https_enabled"]').prop("checked", false);
		}
	}

	load_certificates() {
		frappe.call({
			method: "frappe.client.get_list",
			args: {
				doctype: "AS2 Certificate",
				fields: ["name", "certificate_name", "x509_alias", "keystore_path", "certificate_type", "purpose"],
				order_by: "certificate_name asc",
				limit_page_length: 200,
			},
			callback: (r) => {
				this.certificates = r.message || [];
				const current = this.value("certificate");
				const options = [`<option value="">${__("No certificate")}</option>`].concat(
					this.certificates.map((row) => {
						const label = row.x509_alias
							? `${row.certificate_name || row.name} (${row.x509_alias})`
							: row.certificate_name || row.name;
						return `<option value="${frappe.utils.escape_html(row.name)}">${frappe.utils.escape_html(label)}</option>`;
					})
				);
				const $select = this.$body.find('[data-field="certificate"]');
				$select.html(options.join(""));
				if (current) $select.val(current);
				this.apply_certificate();
			},
			error: () => {
				this.$body.find('[data-field="certificate"]').html(`<option value="">${__("Could not load certificates")}</option>`);
			},
		});
	}

	apply_certificate() {
		const name = this.value("certificate");
		const cert = this.certificates.find((row) => row.name === name);
		const type = cert ? cert.certificate_type || "" : "";
		const signing = type === "Signing" || type === "Both" ? __("Enabled") : type ? __("Not used") : "—";
		const encryption = type === "Encryption" || type === "Both" ? __("Enabled") : type ? __("Not used") : "—";
		this.$body.find('[data-sec="signing"]').text(signing);
		this.$body.find('[data-sec="encryption"]').text(encryption);
		this.$body.find('[data-sec="type"]').text(type || "—");
		if (!cert) return;
		if (cert.x509_alias) this.$body.find('[data-field="x509_alias"]').val(cert.x509_alias);
		if (cert.keystore_path) this.$body.find('[data-field="as2_keystore_path"]').val(cert.keystore_path);
	}

	port_or_null(name) {
		const raw = this.value(name);
		if (!raw) return null;
		const port = cint(raw);
		return port > 0 ? port : null;
	}

	async save() {
		if (this.saving) return;
		const instance_name = this.value("instance_name");
		const instance_type = this.value("instance_type");
		const as2_id = this.value("as2_id");
		const host = this.value("host");
		const protocol = this.value("protocol") || "HTTPS";
		const listener = this.port_or_null("listener_port");
		if (!instance_name || !instance_type || !as2_id || !host || !listener) {
			frappe.msgprint(__("Configuration name, instance type, AS2 ID, host, and listener port are required."));
			return;
		}
		const mdn_enabled = this.checked("mdn_enabled");
		const mdn_mode = this.value("mdn_mode") || "Synchronous";
		const mdn_http_enabled = mdn_enabled ? this.checked("mdn_http_enabled") : 0;
		const mdn_https_enabled = mdn_enabled ? this.checked("mdn_https_enabled") : 0;
		const mdn_http_port = this.port_or_null("mdn_http_port");
		const mdn_https_port = this.port_or_null("mdn_https_port");
		if (mdn_http_enabled && !mdn_http_port) {
			frappe.msgprint(__("MDN HTTP port is required when MDN HTTP is enabled."));
			return;
		}
		if (mdn_https_enabled && !mdn_https_port) {
			frappe.msgprint(__("MDN HTTPS port is required when MDN HTTPS is enabled."));
			return;
		}
		if (mdn_enabled && mdn_mode === "Asynchronous" && !mdn_http_enabled && !mdn_https_enabled) {
			frappe.msgprint(__("Asynchronous MDN requires MDN HTTP and/or MDN HTTPS."));
			return;
		}

		const doc = {
			doctype: "OpenAS2 Instance",
			instance_name,
			instance_type,
			as2_id,
			host,
			status: "Active",
			protocol,
			port: listener,
			http_enabled: protocol === "HTTP" ? 1 : 0,
			https_enabled: protocol === "HTTPS" ? 1 : 0,
			http_port: protocol === "HTTP" ? listener : null,
			https_port: protocol === "HTTPS" ? listener : null,
			openas2_home: this.value("openas2_home"),
			inbox_path: this.value("inbox_path"),
			outbox_path: this.value("outbox_path"),
			x509_alias: this.value("x509_alias"),
			as2_keystore_path: this.value("as2_keystore_path"),
			ssl_keystore_path: this.value("ssl_keystore_path"),
			certificate_status: this.value("certificate") ? "Configured" : "Unknown",
			mdn_enabled,
			mdn_mode,
			mdn_http_enabled,
			mdn_https_enabled,
			mdn_http_port: mdn_http_enabled ? mdn_http_port : null,
			mdn_https_port: mdn_https_enabled ? mdn_https_port : null,
			async_mdn_url: mdn_enabled && mdn_mode === "Asynchronous" ? this.value("async_mdn_url") : "",
			provision_source: "External",
		};
		const password = this.value("as2_keystore_password");
		if (password) doc.as2_keystore_password = password;

		this.saving = true;
		const $save = this.$body.find(".oa2-cfg-save").prop("disabled", true);
		try {
			let message;
			if (!this.docName) {
				message = await this.call("frappe.client.insert", { doc });
				this.docName = message && message.name;
			} else {
				const updates = Object.assign({}, doc);
				delete updates.doctype;
				if (!password) delete updates.as2_keystore_password;
				message = await this.call("frappe.client.set_value", {
					doctype: "OpenAS2 Instance",
					name: this.docName,
					fieldname: updates,
				});
			}
			if (!this.docName) return;
			frappe.show_alert({
				message: __("Configuration {0} created", [instance_name]),
				indicator: "green",
			});
			frappe.set_route("openas2-configuration");
		} catch (e) {
			this.saving = false;
			$save.prop("disabled", false);
		}
	}

	call(method, args) {
		return new Promise((resolve, reject) => {
			frappe.call({
				method,
				args,
				freeze: method.indexOf("insert") !== -1 || method.indexOf("set_value") !== -1,
				freeze_message: __("Saving configuration…"),
				callback: (r) => resolve(r && r.message),
				error: () => reject(new Error(method)),
			});
		});
	}
};
