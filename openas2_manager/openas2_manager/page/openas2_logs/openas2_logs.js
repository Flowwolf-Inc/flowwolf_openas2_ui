// Copyright (c) 2026, Lakshana and contributors
// For license information, please see license.txt

frappe.pages["openas2-logs"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Logs"),
		single_column: true,
	});

	frappe.breadcrumbs.add("OpenAS2 Manager");
	$(wrapper).addClass("oa2-config-page-wrapper oa2-logs-page-wrapper");
	document.body.classList.add("oa2-has-sidebar");
	document.body.classList.add("oa2-use-inpage-sidebar");
	document.body.classList.remove("oa2-using-global-sidebar");
	document.body.classList.remove("oa2-sidebar-mounted");

	wrapper.logs_page = new openas2_manager.OpenAS2LogsPage(page);
	if (window.openas2_manager && openas2_manager.sync_sidebar) {
		openas2_manager.sync_sidebar();
	}
	if (window.openas2_manager && openas2_manager.sync_layout) {
		openas2_manager.sync_layout();
	}
};

frappe.pages["openas2-logs"].on_page_show = function (wrapper) {
	document.body.classList.add("oa2-has-sidebar");
	document.body.classList.add("oa2-use-inpage-sidebar");
	document.body.classList.remove("oa2-using-global-sidebar");
	document.body.classList.remove("oa2-sidebar-mounted");
	if (wrapper.logs_page) {
		wrapper.logs_page.apply_theme(wrapper.logs_page.get_theme());
		const opts = frappe.route_options || {};
		if (opts.oa2_search || opts.oa2_level || opts.oa2_date_from || opts.oa2_date_to) {
			wrapper.logs_page.apply_assistant_filters(opts);
			frappe.route_options = null;
		}
		wrapper.logs_page.load();
	}
	if (window.openas2_manager && openas2_manager.sync_sidebar) {
		openas2_manager.sync_sidebar();
	}
	if (window.openas2_manager && openas2_manager.sync_layout) {
		openas2_manager.sync_layout();
	}
};

frappe.provide("openas2_manager");

openas2_manager.OpenAS2LogsPage = class OpenAS2LogsPage {
	constructor(page) {
		this.page = page;
		this.THEME_KEY = "oa2-dashboard-theme";
		this.PAGE_SIZE = 50;
		this.offset = 0;
		this.total = 0;
		this.filters = {
			search: "",
			level: "All",
			date_from: "",
			date_to: "",
			source: "All",
		};
		this.$body = $(page.body).addClass("oa2-config-list-page oa2-logs-page");
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

	apply_assistant_filters(opts) {
		opts = opts || {};
		if (opts.oa2_search != null) {
			this.filters.search = String(opts.oa2_search || "");
			this.$body.find(".oa2-logs-search").val(this.filters.search);
		}
		if (opts.oa2_level) {
			this.filters.level = String(opts.oa2_level);
			this.$body.find(".oa2-logs-level").val(this.filters.level);
		}
		if (opts.oa2_date_from) {
			this.filters.date_from = String(opts.oa2_date_from);
			this.$body.find(".oa2-logs-date-from").val(this.filters.date_from);
		}
		if (opts.oa2_date_to) {
			this.filters.date_to = String(opts.oa2_date_to);
			this.$body.find(".oa2-logs-date-to").val(this.filters.date_to);
		}
		this.offset = 0;
	}

	apply_theme(theme) {
		const t = theme === "dark" ? "dark" : "light";
		this.$body.attr("data-oa2-theme", t);
		this.$body.find(".oa2-sidebar-inpage").attr("data-oa2-theme", t);
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
		if (window.openas2_manager && openas2_manager.apply_oa2_theme) {
			openas2_manager.apply_oa2_theme(t);
		}
	}

	sidebar_html(activeKey) {
		const active = activeKey || "logs";
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
			{ key: "logs", label: __("Logs"), icon: "logs", route: "openas2-logs" },
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
				${this.sidebar_html("logs")}
				<div class="oa2-main-pane">
					<div class="oa2-config-shell oa2-logs-shell">
						<header class="oa2-config-header">
							<div>
								<h1 class="oa2-config-title">${__("Logs")}</h1>
								<p class="oa2-config-subtitle">
									${__("OpenAS2 system and EDI activity — messages, runtime, restarts, and configuration changes.")}
								</p>
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
								<button type="button" class="oa2-btn oa2-btn-secondary oa2-logs-refresh">
									${__("Refresh")}
								</button>
							</div>
						</header>

						<section class="oa2-logs-toolbar" aria-label="${__("Log filters")}">
							<div class="oa2-logs-search-wrap">
								<input type="search" class="oa2-logs-search" placeholder="${__("Search logs…")}" aria-label="${__("Search logs")}" />
							</div>
							<select class="oa2-logs-filter oa2-logs-level" aria-label="${__("Filter by log level")}">
								<option value="All">${__("All levels")}</option>
								<option value="Info">${__("Info")}</option>
								<option value="Warning">${__("Warning")}</option>
								<option value="Error">${__("Error")}</option>
							</select>
							<select class="oa2-logs-filter oa2-logs-source" aria-label="${__("Filter by source")}">
								<option value="All">${__("All sources")}</option>
								<option value="EDI / Message">${__("EDI / Message")}</option>
								<option value="Runtime">${__("Runtime")}</option>
								<option value="Restart">${__("Restart")}</option>
								<option value="Provisioning">${__("Provisioning")}</option>
								<option value="Configuration">${__("Configuration")}</option>
							</select>
							<input type="date" class="oa2-logs-filter oa2-logs-date-from" aria-label="${__("From date")}" />
							<input type="date" class="oa2-logs-filter oa2-logs-date-to" aria-label="${__("To date")}" />
						</section>

						<section class="oa2-config-card oa2-logs-card">
							<div class="oa2-config-table-wrap oa2-logs-table-wrap">
								<table class="oa2-config-table oa2-logs-table" aria-label="${__("System and EDI logs")}">
									<thead>
										<tr>
											<th class="oa2-logs-col-time">${__("Date / Time")}</th>
											<th class="oa2-logs-col-level">${__("Level")}</th>
											<th>${__("Event / Message")}</th>
											<th class="oa2-logs-col-source">${__("Source")}</th>
											<th class="oa2-logs-col-component">${__("Component")}</th>
											<th class="oa2-logs-col-status">${__("Status")}</th>
										</tr>
									</thead>
									<tbody class="oa2-logs-tbody">
										<tr>
											<td colspan="6" class="oa2-config-empty">${__("Loading…")}</td>
										</tr>
									</tbody>
								</table>
							</div>
							<footer class="oa2-logs-pager">
								<span class="oa2-logs-pager-meta"></span>
								<div class="oa2-logs-pager-actions">
									<button type="button" class="oa2-btn oa2-btn-secondary oa2-logs-prev" disabled>${__("Previous")}</button>
									<button type="button" class="oa2-btn oa2-btn-secondary oa2-logs-next" disabled>${__("Next")}</button>
								</div>
							</footer>
						</section>
					</div>
				</div>
			</div>
		`);

		this.$tbody = this.$body.find(".oa2-logs-tbody");
		this.$pagerMeta = this.$body.find(".oa2-logs-pager-meta");
		this.$prev = this.$body.find(".oa2-logs-prev");
		this.$next = this.$body.find(".oa2-logs-next");

		this.bind_events();
	}

	bind_events() {
		this.$body.on("click", ".oa2-theme-switch", (e) => {
			e.preventDefault();
			this.apply_theme(this.get_theme() === "dark" ? "light" : "dark");
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

		this.$body.on("click", ".oa2-logs-refresh", (e) => {
			e.preventDefault();
			this.refresh();
		});

		let searchTimer = null;
		this.$body.on("input", ".oa2-logs-search", (e) => {
			const val = e.currentTarget.value || "";
			clearTimeout(searchTimer);
			searchTimer = setTimeout(() => {
				this.filters.search = val.trim();
				this.offset = 0;
				this.load();
			}, 280);
		});

		this.$body.on("change", ".oa2-logs-level", (e) => {
			this.filters.level = e.currentTarget.value || "All";
			this.offset = 0;
			this.load();
		});

		this.$body.on("change", ".oa2-logs-source", (e) => {
			this.filters.source = e.currentTarget.value || "All";
			this.offset = 0;
			this.load();
		});

		this.$body.on("change", ".oa2-logs-date-from", (e) => {
			this.filters.date_from = e.currentTarget.value || "";
			this.offset = 0;
			this.load();
		});

		this.$body.on("change", ".oa2-logs-date-to", (e) => {
			this.filters.date_to = e.currentTarget.value || "";
			this.offset = 0;
			this.load();
		});

		this.$body.on("click", ".oa2-logs-prev", (e) => {
			e.preventDefault();
			if (this.offset <= 0) return;
			this.offset = Math.max(0, this.offset - this.PAGE_SIZE);
			this.load();
		});

		this.$body.on("click", ".oa2-logs-next", (e) => {
			e.preventDefault();
			if (this.offset + this.PAGE_SIZE >= this.total) return;
			this.offset += this.PAGE_SIZE;
			this.load();
		});

		this.$body.on("click", ".oa2-logs-row[data-doctype][data-name]", (e) => {
			const $row = $(e.currentTarget);
			const dt = $row.attr("data-doctype");
			const name = $row.attr("data-name");
			if (!dt || !name) return;
			if (String(name).indexOf("remote:") === 0) {
				frappe.route_options = { oa2_open_message: name };
				frappe.set_route("openas2-messages");
				return;
			}
			frappe.set_route("Form", dt, name);
		});
	}

	level_pill(level) {
		const l = level || "Info";
		let cls = "oa2-pill oa2-pill-info";
		if (l === "Error") cls = "oa2-pill oa2-pill-failed";
		else if (l === "Warning") cls = "oa2-pill oa2-pill-warn";
		return `<span class="${cls}">${frappe.utils.escape_html(l)}</span>`;
	}

	status_pill(status) {
		const s = status || "—";
		let cls = "oa2-pill oa2-pill-muted";
		const lower = String(s).toLowerCase();
		if (lower === "success" || lower === "received" || lower === "sent" || lower === "applied") {
			cls = "oa2-pill oa2-pill-success";
		} else if (lower === "failed" || lower === "error" || lower === "rolled back") {
			cls = "oa2-pill oa2-pill-failed";
		} else if (lower === "pending" || lower === "duplicate" || lower === "proposed" || lower === "not available") {
			cls = "oa2-pill oa2-pill-warn";
		}
		return `<span class="${cls}">${frappe.utils.escape_html(s)}</span>`;
	}

	render_rows(rows) {
		if (!rows || !rows.length) {
			this.$tbody.html(`
				<tr>
					<td colspan="6" class="oa2-config-empty oa2-logs-empty">
						<div class="oa2-logs-empty-title">${__("No logs found")}</div>
						<div class="oa2-logs-empty-copy">${__(
							"There are no system or EDI activity logs for the current filters. Try clearing search or date filters, or click Refresh."
						)}</div>
					</td>
				</tr>
			`);
			return;
		}

		const html = rows
			.map((row) => {
				const ts = frappe.utils.escape_html(row.timestamp_display || row.timestamp || "—");
				const event = frappe.utils.escape_html(row.event || "—");
				const source = frappe.utils.escape_html(row.source || "—");
				const component = frappe.utils.escape_html(row.component || "—");
				return `<tr class="oa2-logs-row" data-doctype="${frappe.utils.escape_html(
					row.doctype || ""
				)}" data-name="${frappe.utils.escape_html(row.name || "")}" title="${__("Open log record")}">
					<td class="oa2-logs-col-time oa2-mono">${ts}</td>
					<td class="oa2-logs-col-level">${this.level_pill(row.level)}</td>
					<td class="oa2-logs-col-event"><span class="oa2-logs-event">${event}</span></td>
					<td class="oa2-logs-col-source">${source}</td>
					<td class="oa2-logs-col-component">${component}</td>
					<td class="oa2-logs-col-status">${this.status_pill(row.status)}</td>
				</tr>`;
			})
			.join("");
		this.$tbody.html(html);
	}

	update_pager() {
		const start = this.total === 0 ? 0 : this.offset + 1;
		const end = Math.min(this.offset + this.PAGE_SIZE, this.total);
		this.$pagerMeta.text(
			this.total === 0
				? __("No entries")
				: __("Showing {0}–{1} of {2}", [start, end, this.total])
		);
		this.$prev.prop("disabled", this.offset <= 0);
		this.$next.prop("disabled", this.offset + this.PAGE_SIZE >= this.total);
	}

	load() {
		this.$tbody.html(
			`<tr><td colspan="6" class="oa2-config-empty">${__("Loading…")}</td></tr>`
		);

		frappe.call({
			method: "openas2_manager.openas2.system_logs.get_system_logs",
			args: {
				search: this.filters.search || "",
				level: this.filters.level || "All",
				date_from: this.filters.date_from || "",
				date_to: this.filters.date_to || "",
				source: this.filters.source || "All",
				limit: this.PAGE_SIZE,
				offset: this.offset,
			},
			callback: (r) => {
				const msg = (r && r.message) || {};
				const rows = msg.rows || [];
				this.total = msg.total || 0;
				if (msg.error && !rows.length) {
					this.$tbody.html(
						`<tr><td colspan="6" class="oa2-config-empty oa2-logs-empty">${frappe.utils.escape_html(
							msg.error
						)}</td></tr>`
					);
					this.update_pager();
					return;
				}
				this.render_rows(rows);
				if (msg.error) {
					this.$tbody.prepend(
						`<tr><td colspan="6" class="oa2-config-empty">${frappe.utils.escape_html(
							msg.error
						)}</td></tr>`
					);
				}
				this.update_pager();
			},
			error: () => {
				this.$tbody.html(
					`<tr><td colspan="6" class="oa2-config-empty">${__(
						"Could not load logs. Check permissions and try Refresh."
					)}</td></tr>`
				);
				this.total = 0;
				this.update_pager();
			},
		});
	}

	refresh() {
		frappe.call({
			method: "openas2_manager.openas2.system_logs.refresh_system_logs",
			freeze: true,
			freeze_message: __("Refreshing logs…"),
			callback: (r) => {
				const msg = (r && r.message) || {};
				this.offset = 0;
				if (msg.ok === false || msg.error) {
					frappe.show_alert({
						message: msg.error || __("The OpenAS2 database could not be read."),
						indicator: "red",
					});
				}
				this.load();
			},
			error: () => {
				frappe.show_alert({
					message: __("The OpenAS2 database could not be read."),
					indicator: "red",
				});
				this.offset = 0;
				this.load();
			},
		});
	}
};
