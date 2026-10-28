// Copyright (c) 2026, Lakshana and contributors
// For license information, please see license.txt

frappe.pages["openas2-create-communication"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Create OpenAS2 Configuration"),
		single_column: true,
	});
	frappe.breadcrumbs.add("OpenAS2 Manager");
	$(wrapper).addClass("oa2-config-page-wrapper oa2-create-comm-page-wrapper");
	document.body.classList.add("oa2-has-sidebar", "oa2-use-inpage-sidebar");
	document.body.classList.remove("oa2-using-global-sidebar", "oa2-sidebar-mounted");
	wrapper.create_comm_page = new openas2_manager.OpenAS2CreateCommunicationPage(page);
	if (window.openas2_manager && openas2_manager.sync_layout) openas2_manager.sync_layout();
};

frappe.pages["openas2-create-communication"].on_page_show = function (wrapper) {
	document.body.classList.add("oa2-has-sidebar", "oa2-use-inpage-sidebar");
	document.body.classList.remove("oa2-using-global-sidebar", "oa2-sidebar-mounted");
	if (wrapper.create_comm_page) {
		wrapper.create_comm_page.apply_theme(wrapper.create_comm_page.get_theme());
	}
	if (window.openas2_manager && openas2_manager.sync_layout) openas2_manager.sync_layout();
};

frappe.provide("openas2_manager");

openas2_manager.OpenAS2CreateCommunicationPage = class OpenAS2CreateCommunicationPage {
	constructor(page) {
		this.page = page;
		this.THEME_KEY = "oa2-dashboard-theme";
		this.saving = false;
		this.$body = $(page.body).addClass("oa2-config-list-page oa2-create-comm-page");
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
				(item) => `<button type="button" class="oa2-nav-item${item.key === active ? " active" : ""}" data-route="${item.route}">
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
		const id = "oa2-comm-" + name;
		const mark = extra && extra.required ? " *" : "";
		const hint = extra && extra.hint ? `<small>${frappe.utils.escape_html(extra.hint)}</small>` : "";
		if (type === "select") {
			const options = (extra.options || [])
				.map((opt) => `<option value="${frappe.utils.escape_html(opt)}">${frappe.utils.escape_html(opt)}</option>`)
				.join("");
			return `<label class="oa2-set-field" for="${id}"><span>${frappe.utils.escape_html(label)}${mark}</span><select id="${id}" data-field="${name}">${options}</select>${hint}</label>`;
		}
		return `<label class="oa2-set-field" for="${id}"><span>${frappe.utils.escape_html(label)}${mark}</span><input id="${id}" type="text" data-field="${name}" autocomplete="off" />${hint}</label>`;
	}

	section(title, hint, inner) {
		return `<section class="oa2-config-card oa2-set-card"><header class="oa2-set-card-head"><h2>${frappe.utils.escape_html(title)}</h2>${hint ? `<p>${hint}</p>` : ""}</header><div class="oa2-set-grid">${inner}</div></section>`;
	}

	make() {
		const basic =
			this.field("instance_name", __("Instance Name"), "text", {
				required: true,
				hint: __("Example: Broker ABC"),
			}) +
			this.field("instance_type", __("Type"), "select", {
				required: true,
				options: ["Broker", "Shipper", "Carrier"],
			}) +
			this.field("as2_id", __("AS2 ID"), "text", {
				required: true,
				hint: __("Example: BROKER_ABC"),
			}) +
			this.field("host", __("Host"), "text", { required: true });
		const portNote = `<p class="oa2-set-note oa2-set-wide">${__(
			"Listener port is allocated automatically when this instance is created."
		)}</p>`;
		const security = `<p class="oa2-set-note oa2-set-wide">${__(
			"Certificates are deferred. No keystore is generated during creation, and a fake certificate is not stored."
		)}</p>`;
		const mdn = `<label class="oa2-set-check" for="oa2-comm-mdn_enabled"><input id="oa2-comm-mdn_enabled" type="checkbox" data-field="mdn_enabled" checked /><span>${__(
			"MDN Enabled"
		)}</span></label>`;
		const storage = `<p class="oa2-set-note oa2-set-wide">${__(
			"Instance storage is created automatically. The runtime is created as Stopped and is not started."
		)}</p>`;

		this.$body.html(`
			<div class="oa2-app-frame">
				${this.sidebar_html()}
				<div class="oa2-main-pane">
					<div class="oa2-config-shell">
						<header class="oa2-config-header">
							<div>
								<h1 class="oa2-config-title">${__("Create OpenAS2 Configuration")}</h1>
								<p class="oa2-config-subtitle">${__("Provision an isolated OpenAS2 instance. Ports are assigned for you, and the runtime stays stopped.")}</p>
							</div>
							<div class="oa2-home-header-actions"></div>
						</header>
						<form class="oa2-set-form" novalidate>
							${this.section(__("Basic Information"), __("Name, type, AS2 identity, and host."), basic + portNote)}
							${this.section(__("Security / Certificates"), "", security)}
							${this.section(__("MDN Settings"), __("Message disposition notification for this instance."), mdn)}
							${this.section(__("Configuration / Storage"), "", storage)}
							<div class="oa2-form-actions">
								<button type="button" class="oa2-btn oa2-btn-secondary oa2-comm-back">${__("Cancel")}</button>
								<button type="submit" class="oa2-btn oa2-btn-primary oa2-comm-save">${__("Create Configuration")}</button>
							</div>
						</form>
					</div>
				</div>
			</div>
		`);

		this.$body.find('[data-field="host"]').val("localhost");
		this.$body.on("click", ".oa2-sidebar-inpage [data-route]", (e) => {
			e.preventDefault();
			const route = $(e.currentTarget).attr("data-route");
			if (route) frappe.set_route(route);
		});
		this.$body.on("click", ".oa2-comm-back", (e) => {
			e.preventDefault();
			this.go_back();
		});
		this.$body.on("submit", "form", (e) => {
			e.preventDefault();
			this.create();
		});
	}

	value(name) {
		const $el = this.$body.find(`[data-field="${name}"]`);
		if ($el.is(":checkbox")) return $el.is(":checked") ? 1 : 0;
		return String($el.val() || "").trim();
	}

	go_back() {
		const route =
			(window.openas2_manager &&
				openas2_manager.provision &&
				openas2_manager.provision.return_route) ||
			["openas2-configuration"];
		if (!route.length || route[0] === "openas2-create-communication") {
			frappe.set_route("openas2-configuration");
			return;
		}
		frappe.set_route(...route);
	}

	create() {
		if (this.saving) return;
		if (!frappe.user.has_role("System Manager")) {
			frappe.msgprint({
				title: __("Not permitted"),
				indicator: "red",
				message: __("Only System Managers may provision OpenAS2 instances."),
			});
			return;
		}
		const instance_name = this.value("instance_name");
		const instance_type = this.value("instance_type");
		const as2_id = this.value("as2_id");
		const host = this.value("host") || "localhost";
		if (!instance_name || !instance_type || !as2_id || !host) {
			frappe.msgprint(__("Instance Name, Type, AS2 ID, and Host are required."));
			return;
		}
		this.saving = true;
		const $save = this.$body.find(".oa2-comm-save").prop("disabled", true);
		const opts =
			(window.openas2_manager && openas2_manager.provision && openas2_manager.provision.pending_opts) ||
			{};
		frappe.call({
			method: "openas2_manager.openas2.provisioning.provision_openas2_instance",
			args: {
				instance_name,
				instance_type,
				as2_id,
				mdn_enabled: this.value("mdn_enabled") ? 1 : 0,
				host,
			},
			freeze: true,
			freeze_message: __("Provisioning isolated OpenAS2 instance..."),
			callback: (r) => {
				this.saving = false;
				$save.prop("disabled", false);
				const result = (r && r.message) || {};
				frappe.msgprint({
					title: __("Provisioning Result"),
					indicator: result.result === "Success" ? "green" : "red",
					message: __(result.message || "Provisioning finished."),
				});
				if (typeof opts.on_success === "function") {
					opts.on_success(result);
				}
				if (result.result === "Success") {
					if (String((frappe.get_route() || [])[0] || "") === "openas2-create-communication") {
						this.go_back();
					}
				} else if (typeof opts.on_success !== "function" && result.instance) {
					frappe.set_route("Form", "OpenAS2 Instance", result.instance);
				}
			},
			error: () => {
				this.saving = false;
				$save.prop("disabled", false);
			},
		});
	}
};
