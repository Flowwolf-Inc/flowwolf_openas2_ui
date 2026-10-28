// Copyright (c) 2026, Lakshana and contributors
// For license information, please see license.txt

frappe.pages["openas2-settings"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Settings"),
		single_column: true,
	});
	frappe.breadcrumbs.add("OpenAS2 Manager");
	$(wrapper).addClass("oa2-config-page-wrapper oa2-settings-page-wrapper");
	document.body.classList.add("oa2-has-sidebar", "oa2-use-inpage-sidebar");
	document.body.classList.remove("oa2-using-global-sidebar", "oa2-sidebar-mounted");
	wrapper.settings_page = new openas2_manager.OpenAS2SettingsPage(page);
	if (window.openas2_manager && openas2_manager.sync_layout) openas2_manager.sync_layout();
};

frappe.pages["openas2-settings"].on_page_show = function (wrapper) {
	document.body.classList.add("oa2-has-sidebar", "oa2-use-inpage-sidebar");
	document.body.classList.remove("oa2-using-global-sidebar", "oa2-sidebar-mounted");
	if (wrapper.settings_page) {
		wrapper.settings_page.apply_theme(wrapper.settings_page.get_theme());
	}
	if (window.openas2_manager && openas2_manager.sync_layout) openas2_manager.sync_layout();
};

frappe.provide("openas2_manager");

openas2_manager.OpenAS2SettingsPage = class OpenAS2SettingsPage {
	constructor(page) {
		this.page = page;
		this.THEME_KEY = "oa2-dashboard-theme";
		this.instance = "";
		this.snapshot = null;
		this.$body = $(page.body).addClass("oa2-config-list-page oa2-settings-page");
		this.make();
		this.apply_theme(this.get_theme());
		this.load();
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
		try {
			localStorage.setItem(this.THEME_KEY, t);
		} catch (e) {
			/* ignore */
		}
		if (window.openas2_manager && openas2_manager.apply_oa2_theme) {
			openas2_manager.apply_oa2_theme(t);
		}
	}

	sidebar_html() {
		const active = "settings";
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

	field(name, label, type, options) {
		const id = "oa2-set-" + name;
		if (type === "check") {
			return `<label class="oa2-set-check" for="${id}"><input id="${id}" type="checkbox" data-field="${name}" /><span>${frappe.utils.escape_html(label)}</span></label>`;
		}
		if (type === "select") {
			const opts = (options || [])
				.map((o) => `<option value="${frappe.utils.escape_html(o)}">${frappe.utils.escape_html(o)}</option>`)
				.join("");
			return `<label class="oa2-set-field"><span>${frappe.utils.escape_html(label)}</span><select id="${id}" data-field="${name}">${opts}</select></label>`;
		}
		if (type === "textarea") {
			return `<label class="oa2-set-field oa2-set-wide"><span>${frappe.utils.escape_html(label)}</span><textarea id="${id}" data-field="${name}" rows="3"></textarea></label>`;
		}
		const inputType = type === "number" ? "number" : "text";
		return `<label class="oa2-set-field"><span>${frappe.utils.escape_html(label)}</span><input id="${id}" type="${inputType}" data-field="${name}" /></label>`;
	}

	section(title, hint, inner) {
		return `<section class="oa2-config-card oa2-set-card"><header class="oa2-set-card-head"><h2>${frappe.utils.escape_html(title)}</h2>${hint ? `<p>${frappe.utils.escape_html(hint)}</p>` : ""}</header><div class="oa2-set-grid">${inner}</div></section>`;
	}

	make() {
		const general =
			this.field("instance_name", __("Instance name"), "text") +
			this.field("instance_type", __("Instance type"), "select", ["Shipper", "Broker", "Carrier", "CompanyC"]) +
			this.field("status", __("Status"), "select", ["Active", "Inactive", "Error"]) +
			this.field("host", __("Host"), "text") +
			this.field("description", __("Description"), "textarea");
		const instance =
			this.field("provision_source", __("Provision source"), "select", ["External", "Manager Provisioned"]) +
			this.field("control_mode", __("Control mode"), "select", ["none", "agent", "windows_service", "linux_start_script"]) +
			this.field("lifecycle_status", __("Lifecycle status"), "text") +
			this.field("connection_status", __("Connection status"), "text") +
			this.field("published_as2_url", __("Published AS2 URL"), "text");
		const identity =
			this.field("as2_id", __("AS2 ID"), "text") +
			this.field("protocol", __("Primary protocol"), "select", ["HTTP", "HTTPS"]) +
			this.field("x509_alias", __("X509 alias"), "text");
		const listener =
			this.field("http_enabled", __("Enable HTTP"), "check") +
			this.field("http_port", __("HTTP port"), "number") +
			this.field("https_enabled", __("Enable HTTPS"), "check") +
			this.field("https_port", __("HTTPS port"), "number") +
			this.field("port", __("Primary port"), "number") +
			this.field("health_port", __("Health port"), "number") +
			this.field("tracking_port", __("Tracking port"), "number");
		const mdn =
			this.field("mdn_enabled", __("MDN enabled"), "check") +
			this.field("mdn_mode", __("MDN mode"), "select", ["Synchronous", "Asynchronous"]) +
			this.field("mdn_http_enabled", __("Enable MDN HTTP"), "check") +
			this.field("mdn_http_port", __("MDN HTTP port"), "number") +
			this.field("mdn_https_enabled", __("Enable MDN HTTPS"), "check") +
			this.field("mdn_https_port", __("MDN HTTPS port"), "number") +
			this.field("async_mdn_url", __("Async MDN URL"), "text");
		const security =
			this.field("as2_keystore_path", __("AS2 keystore path"), "text") +
			this.field("ssl_keystore_path", __("SSL keystore path"), "text") +
			this.field("certificate_status", __("Certificate status"), "select", ["Unknown", "Deferred", "Configured", "Missing"]);
		const storage =
			this.field("openas2_home", __("OpenAS2 home"), "text") +
			this.field("windows_home", __("Windows home"), "text") +
			this.field("inbox_path", __("Inbox path"), "text") +
			this.field("outbox_path", __("Outbox path"), "text") +
			this.field("instance_slug", __("Instance slug"), "text");

		this.$body.html(`
			<div class="oa2-app-frame">
				${this.sidebar_html()}
				<div class="oa2-main-pane">
					<div class="oa2-config-shell">
						<header class="oa2-config-header">
							<div>
								<h1 class="oa2-config-title">${__("Settings")}</h1>
								<p class="oa2-config-subtitle">${__("OpenAS2 instance configuration stored in Frappe. Values marked from config.xml are read from the instance files.")}</p>
							</div>
							<div class="oa2-config-header-actions">
								<div class="oa2-theme-toggle" role="group" aria-label="${__("Theme")}">
									<button type="button" class="oa2-theme-switch" role="switch" aria-checked="false" aria-label="${__("Toggle light / dark theme")}" title="${__("Toggle light / dark theme")}">
										<span class="oa2-theme-track" aria-hidden="true">
											<svg class="oa2-theme-icon oa2-theme-icon-sun" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2.2M12 19.8V22M4.9 4.9l1.6 1.6M17.5 17.5l1.6 1.6M2 12h2.2M19.8 12H22M4.9 19.1l1.6-1.6M17.5 6.5l1.6-1.6"/></svg>
											<svg class="oa2-theme-icon oa2-theme-icon-moon" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20.5 14.2A7.8 7.8 0 0 1 9.8 3.5 7.9 7.9 0 1 0 20.5 14.2z"/></svg>
											<span class="oa2-theme-thumb"></span>
										</span>
									</button>
								</div>
								<button type="button" class="oa2-btn oa2-btn-secondary oa2-set-reset">${__("Reset")}</button>
								<button type="button" class="oa2-btn oa2-btn-primary oa2-set-save">${__("Save")}</button>
							</div>
						</header>
						<div class="oa2-set-instance">
							<label class="oa2-set-field"><span>${__("OpenAS2 instance")}</span>
								<select class="oa2-set-instance-select" aria-label="${__("OpenAS2 instance")}"></select>
							</label>
						</div>
						<div class="oa2-set-empty" hidden></div>
						<div class="oa2-set-form">
							${this.section(__("General Settings"), __("Identity and status for this instance."), general)}
							${this.section(__("OpenAS2 Instance Settings"), __("How this instance is provisioned and controlled."), instance)}
							${this.section(__("AS2 Identity"), __("AS2 ID and certificate alias shared with partners."), identity)}
							${this.section(__("Listener / Port Configuration"), __("HTTP and HTTPS receive ports. XML ports are shown below when config.xml can be read."), listener)}
							<div class="oa2-set-xml" data-xml="listener"></div>
							${this.section(__("MDN Settings"), __("Message disposition notification listeners."), mdn)}
							<div class="oa2-set-xml" data-xml="mdn"></div>
							${this.section(__("Security / Encryption Settings"), __("Keystore paths on the instance. Encryption and signing algorithms come from partnerships.xml."), security)}
							<div class="oa2-set-xml" data-xml="security"></div>
							${this.section(__("Storage / File Paths"), __("Home, inbox, and outbox paths."), storage)}
							<div class="oa2-set-xml" data-xml="storage"></div>
							<section class="oa2-config-card oa2-set-card">
								<header class="oa2-set-card-head"><h2>${__("Logging Settings")}</h2><p>${__("Log-related properties found in config.xml. These are read-only here.")}</p></header>
								<div class="oa2-set-xml" data-xml="logging"></div>
							</section>
						</div>
					</div>
				</div>
			</div>
		`);

		["lifecycle_status", "connection_status", "published_as2_url", "windows_home", "instance_slug"].forEach((name) => {
			this.$body.find(`[data-field="${name}"]`).prop("readonly", true);
		});

		this.$body.on("click", ".oa2-sidebar-inpage [data-route]", (e) => {
			e.preventDefault();
			const route = $(e.currentTarget).attr("data-route");
			if (route) frappe.set_route(route);
		});
		this.$body.on("change", ".oa2-set-instance-select", (e) => {
			this.instance = e.currentTarget.value;
			this.load();
		});
		this.$body.on("click", ".oa2-set-reset", (e) => {
			e.preventDefault();
			this.load();
		});
		this.$body.on("click", ".oa2-set-save", (e) => {
			e.preventDefault();
			this.save();
		});
		this.$body.on("click", ".oa2-theme-switch", (e) => {
			e.preventDefault();
			this.apply_theme(this.get_theme() === "dark" ? "light" : "dark");
		});
	}

	esc(v) {
		return frappe.utils.escape_html(v == null || v === "" ? "—" : String(v));
	}

	fill(settings) {
		this.$body.find("[data-field]").each((_, el) => {
			const name = el.getAttribute("data-field");
			const val = settings[name];
			if (el.type === "checkbox") el.checked = !!Number(val);
			else el.value = val == null ? "" : val;
		});
	}

	collect() {
		const values = {};
		this.$body.find("[data-field]").each((_, el) => {
			if (el.readOnly) return;
			const name = el.getAttribute("data-field");
			values[name] = el.type === "checkbox" ? (el.checked ? 1 : 0) : el.value;
		});
		return values;
	}

	render_xml(xml) {
		const show = (key, html) => this.$body.find(`[data-xml="${key}"]`).html(html || "");
		if (!xml) {
			["listener", "mdn", "security", "storage", "logging"].forEach((k) => show(k, ""));
			return;
		}
		const server = xml.server || {};
		show(
			"listener",
			`<p class="oa2-set-note">${__("config.xml")} · HTTP ${this.esc(server.http_port)} (${server.http_enabled ? __("enabled") : __("disabled")}) · HTTPS ${this.esc(server.https_port)} (${server.https_enabled ? __("enabled") : __("disabled")})</p>`
		);
		const mdn = xml.mdn || {};
		show(
			"mdn",
			`<p class="oa2-set-note">${__("config.xml")} · ${this.esc(mdn.mdn_mode)} · HTTP ${this.esc(mdn.mdn_http_port)} · HTTPS ${this.esc(mdn.mdn_https_port)}</p>`
		);
		const cert = xml.certificate || {};
		const secRows = (xml.security || [])
			.map(
				(r) =>
					`<li>${this.esc(r.partnership)} — ${__("encrypt")} ${this.esc(r.encryption)}, ${__("sign")} ${this.esc(r.signing)}</li>`
			)
			.join("");
		show(
			"security",
			`<p class="oa2-set-note">${__("config.xml")} · ${this.esc(cert.keystore_type)} · ${this.esc(cert.keystore_name)} · ${this.esc(cert.certificate_factory)}</p>${secRows ? `<ul class="oa2-set-note-list">${secRows}</ul>` : `<p class="oa2-set-note">${__("No encrypt/sign attributes were found in partnerships.xml.")}</p>`}`
		);
		const dirs = xml.directories || {};
		show(
			"storage",
			`<p class="oa2-set-note">${__("config.xml")} · ${__("storage")} ${this.esc(xml.storage_base_dir)} · ${__("inbox")} ${this.esc(dirs.inbox)} · ${__("outbox")} ${this.esc(dirs.outbox)} · ${__("version")} ${this.esc(xml.version)}</p>`
		);
		const logs = xml.logging || {};
		const keys = Object.keys(logs);
		show(
			"logging",
			keys.length
				? `<ul class="oa2-set-note-list">${keys
						.map((k) => `<li><code>${this.esc(k)}</code> ${this.esc(logs[k])}</li>`)
						.join("")}</ul>`
				: `<p class="oa2-set-note">${__("No log properties were found in config.xml for this instance.")}${(xml.errors || []).length ? " " + this.esc(xml.errors[0]) : ""}</p>`
		);
	}

	load() {
		frappe.call({
			method: "openas2_manager.openas2.settings_api.get_settings",
			args: { instance_name: this.instance || "" },
			callback: (r) => {
				const msg = (r && r.message) || {};
				const instances = msg.instances || [];
				const $sel = this.$body.find(".oa2-set-instance-select");
				const current = this.instance || (msg.settings && msg.settings.name) || "";
				$sel.html(
					instances
						.map(
							(row) =>
								`<option value="${frappe.utils.escape_html(row.name)}"${row.name === current ? " selected" : ""}>${frappe.utils.escape_html(row.instance_name || row.name)} · ${frappe.utils.escape_html(row.instance_type || "")}</option>`
						)
						.join("")
				);
				if (!instances.length || !msg.settings) {
					this.$body.find(".oa2-set-form").attr("hidden", true);
					this.$body.find(".oa2-set-empty").removeAttr("hidden").text(__("No OpenAS2 instances are available."));
					return;
				}
				this.$body.find(".oa2-set-empty").attr("hidden", true);
				this.$body.find(".oa2-set-form").removeAttr("hidden");
				this.instance = msg.settings.name;
				this.snapshot = msg.settings;
				this.fill(msg.settings);
				this.render_xml(msg.xml || {});
			},
		});
	}

	save() {
		if (!this.instance) return;
		frappe.call({
			method: "openas2_manager.openas2.settings_api.save_settings",
			args: { instance_name: this.instance, values: this.collect() },
			freeze: true,
			freeze_message: __("Saving settings…"),
			callback: (r) => {
				const msg = (r && r.message) || {};
				if (msg.settings) {
					this.snapshot = msg.settings;
					this.fill(msg.settings);
					this.render_xml(msg.xml || {});
					frappe.show_alert({ message: __("Settings saved"), indicator: "green" });
				}
			},
		});
	}
};
