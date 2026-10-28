// Copyright (c) 2026, Lakshana and contributors
// For license information, please see license.txt

frappe.pages["openas2-messages"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Monitoring"),
		single_column: true,
	});
	frappe.breadcrumbs.add("OpenAS2 Manager");
	$(wrapper).addClass("oa2-monitor-page-wrapper");
	document.body.classList.add("oa2-has-sidebar");
	document.body.classList.add("oa2-use-inpage-sidebar");
	document.body.classList.add("oa2-hide-desk-chrome");
	document.body.classList.remove("oa2-using-global-sidebar");
	document.body.classList.remove("oa2-sidebar-mounted");
	wrapper.messages_page = new openas2_manager.OpenAS2MessagesPage(page);
	if (window.openas2_manager && openas2_manager.sync_sidebar) {
		openas2_manager.sync_sidebar();
	}
	if (window.openas2_manager && openas2_manager.apply_desk_chrome) {
		openas2_manager.apply_desk_chrome();
	}
};

frappe.pages["openas2-messages"].on_page_show = function (wrapper) {
	document.body.classList.add("oa2-has-sidebar");
	document.body.classList.add("oa2-use-inpage-sidebar");
	document.body.classList.add("oa2-hide-desk-chrome");
	document.body.classList.remove("oa2-using-global-sidebar");
	document.body.classList.remove("oa2-sidebar-mounted");
	if (wrapper && wrapper.messages_page) {
		const monitor = wrapper.messages_page;
		monitor.apply_theme(monitor.get_theme());
		monitor.apply_route_options();
		if (monitor._rows_shown) {
			monitor.load_rows({ background: true });
		} else if (!monitor._rows_loading) {
			monitor.load_rows();
		}
		monitor.start_live_updates();
	}
	if (window.openas2_manager && openas2_manager.sync_sidebar) {
		openas2_manager.sync_sidebar();
	}
	if (window.openas2_manager && openas2_manager.apply_desk_chrome) {
		openas2_manager.apply_desk_chrome();
	}
};

	frappe.pages["openas2-messages"].on_page_hide = function (wrapper) {
	if (wrapper && wrapper.messages_page && wrapper.messages_page.stop_live_updates) {
		wrapper.messages_page.stop_live_updates();
	}
	if (wrapper && wrapper.messages_page && wrapper.messages_page.close_edi_modal) {
		wrapper.messages_page.close_edi_modal();
	}
};

frappe.provide("openas2_manager");

openas2_manager.OpenAS2MessagesPage = class OpenAS2MessagesPage {
	constructor(page) {
		this.page = page;
		this.THEME_KEY = "oa2-dashboard-theme";
		this.tab = "messages";
		this.filters = {
			partner: "",
			status: "",
			transaction_type: "",
			date_from: "",
			date_to: "",
			search: "",
		};
		this.rows = [];
		this.message_page_size = 100;
		this.$body = $(page.body).addClass("oa2-monitor-page");
		this.make();
		this.apply_theme(this.get_theme());
		this.refresh_clock();
		this.load_monitoring_filter_options();
		this.apply_route_options();
		this.load_rows();
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
		if (this.$ediModal) this.$ediModal.attr("data-oa2-theme", t);
		const $wrap = this.$body.closest(".oa2-monitor-page-wrapper");
		if ($wrap.length) $wrap.attr("data-oa2-theme", t);
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

	sidebar_html() {
		const active = "monitoring";
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
		this.page.clear_actions && this.page.clear_actions();
		this.$body.html(`
			<div class="oa2-app-frame">
				${this.sidebar_html()}
				<div class="oa2-main-pane oa2-monitor-main">
					<div class="oa2-monitor-shell">
						<header class="oa2-monitor-header">
							<div>
								<h1 class="oa2-monitor-title">${__("Monitoring")}</h1>
								<p class="oa2-monitor-subtitle">${__(
									"View AS2 messages, EDI transactions and system activity."
								)}</p>
							</div>
							<div class="oa2-monitor-header-actions">
								<div class="oa2-theme-toggle" role="group" aria-label="${__("Theme")}">
									<span class="oa2-theme-side oa2-theme-light">${__("Light")}</span>
									<button type="button" class="oa2-theme-switch" role="switch" aria-checked="false" aria-label="${__(
										"Toggle light / dark theme"
									)}">
										<span class="oa2-theme-track" aria-hidden="true">
											<span class="oa2-theme-thumb"></span>
											<span class="oa2-theme-dots">
												<span class="oa2-theme-dot oa2-theme-dot-lg"></span>
												<span class="oa2-theme-dot oa2-theme-dot-sm"></span>
											</span>
										</span>
									</button>
									<span class="oa2-theme-side oa2-theme-dark">${__("Dark")}</span>
								</div>
								<span class="oa2-monitor-datetime"></span>
								<span class="oa2-monitor-online">${__("System Online")}</span>
							</div>
						</header>

						<div class="oa2-monitor-list">
						<div class="oa2-kpi-row oa2-monitor-kpis" aria-label="${__("EDI counts")}"></div>

						<div class="oa2-monitor-tabs" role="tablist">
							<button type="button" class="oa2-monitor-tab active" data-tab="messages">${__(
								"AS2 Messages"
							)}</button>
							<button type="button" class="oa2-monitor-tab" data-tab="transactions">${__(
								"EDI Transactions"
							)}</button>
							<button type="button" class="oa2-monitor-tab" data-tab="logs">${__("System Logs")}</button>
						</div>

						<div class="oa2-monitor-filters">
							<select class="oa2-mon-filter" data-filter="partner" aria-label="${__("Partner")}">
								<option value="">${__("All Partners")}</option>
							</select>
							<select class="oa2-mon-filter" data-filter="status" aria-label="${__("Status")}">
								<option value="">${__("All Statuses")}</option>
							</select>
							<select class="oa2-mon-filter" data-filter="transaction_type" aria-label="${__(
								"EDI Transaction"
							)}">
								<option value="">${__("All EDI Types")}</option>
							</select>
							<input type="date" class="oa2-mon-filter" data-filter="date_from" aria-label="${__(
								"From date"
							)}" />
							<input type="search" class="oa2-mon-filter oa2-mon-search" data-filter="search" placeholder="${__(
								"Search messages"
							)}" aria-label="${__("Search messages")}" />
							<button type="button" class="oa2-mon-refresh">${__("Refresh")}</button>
						</div>

						<div class="oa2-monitor-content">
							<p class="oa2-monitor-total" aria-live="polite"></p>
							<div class="oa2-monitor-table-wrap">
								<table class="oa2-monitor-table" aria-label="${__("AS2 Messages")}">
									<thead>
										<tr>
											<th>${__("Date / Time")}</th>
											<th>${__("Partner")}</th>
											<th>${__("Transaction")}</th>
											<th>${__("Message ID")}</th>
											<th>${__("Status")}</th>
											<th>${__("MDN Status")}</th>
											<th>${__("Actions")}</th>
										</tr>
									</thead>
									<tbody class="oa2-monitor-tbody">
										<tr><td colspan="7" class="oa2-monitor-empty">${__("Loading…")}</td></tr>
									</tbody>
								</table>
							</div>
						</div>
						</div>
						<div class="oa2-message-page" hidden></div>
					</div>
				</div>
			</div>
			<div class="oa2-edi-modal" hidden>
				<div class="oa2-edi-modal-backdrop"></div>
				<div class="oa2-edi-modal-dialog" role="dialog" aria-modal="true" aria-labelledby="oa2-edi-modal-title">
					<header class="oa2-edi-modal-header">
						<h2 id="oa2-edi-modal-title">${__("EDI Transaction Details")}</h2>
						<button type="button" class="oa2-edi-modal-close" aria-label="${__("Close")}">×</button>
					</header>
					<div class="oa2-edi-modal-body"></div>
				</div>
			</div>
		`);

		this.$tbody = this.$body.find(".oa2-monitor-tbody");
		this.$total = this.$body.find(".oa2-monitor-total");
		this.$monitorList = this.$body.find(".oa2-monitor-list");
		this.$messagePage = this.$body.find(".oa2-message-page");
		this._payload_cache = {};
		$("body > .oa2-edi-modal").remove();
		this.$ediModal = this.$body.find(".oa2-edi-modal").attr("data-oa2-theme", this.get_theme());
		this.$ediModal.appendTo(document.body);
		this.$partner = this.$body.find('[data-filter="partner"]');
		this.$statusFilter = this.$body.find('[data-filter="status"]');
		this.$txnFilter = this.$body.find('[data-filter="transaction_type"]');

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

		this.$body.on("click", ".oa2-kpi[data-txn]", (e) => {
			e.preventDefault();
			const txn = $(e.currentTarget).attr("data-txn");
			if (!txn) return;
			this.filters.transaction_type = txn;
			this.$body.find('[data-filter="transaction_type"]').val(txn);
			this.set_tab("transactions");
			this.load_counts();
		});

		this.$body.on("click", ".oa2-monitor-tab", (e) => {
			e.preventDefault();
			const tab = $(e.currentTarget).attr("data-tab");
			this.set_tab(tab);
		});

		this.$body.on("change", ".oa2-mon-filter", () => this.read_filters_and_load());
		this.$body.on("input", ".oa2-mon-search", () => {
			clearTimeout(this._search_timer);
			this._search_timer = setTimeout(() => this.read_filters_and_load(), 250);
		});

		this.$body.on("click", ".oa2-mon-refresh", (e) => {
			e.preventDefault();
			this.refresh_sources();
		});

		this.$body.on("click", ".oa2-mon-view", (e) => {
			e.preventDefault();
			e.stopPropagation();
			const $btn = $(e.currentTarget);
			const ediName = $btn.attr("data-edi");
			if (ediName) {
				this.open_edi_drawer(ediName);
				return;
			}
			const name = $btn.attr("data-name");
			if (name) this.show_message_page(name);
		});

		this.$body.on("click", ".oa2-message-back", (e) => {
			e.preventDefault();
			this.hide_message_page();
		});

		this.$body.on("click", ".oa2-payload-copy", (e) => {
			e.preventDefault();
			const jsonReady = this._payload_mode === "json" && this._payload_json && this._payload_json.available && this._payload_json.json;
			const text = jsonReady ? this._payload_json.json : this._payload_text || "";
			if (!text || (!jsonReady && !this._payload_ok)) return;
			const $btn = $(e.currentTarget);
			const label = $btn.text();
			const done = () => {
				$btn.text(__("Copied"));
				setTimeout(() => $btn.text(label), 1200);
			};
			if (navigator.clipboard && navigator.clipboard.writeText) {
				navigator.clipboard.writeText(text).then(done).catch(() => this.copy_text_fallback(text, done));
			} else {
				this.copy_text_fallback(text, done);
			}
		});

		this.$body.on("click", ".oa2-payload-full", (e) => {
			e.preventDefault();
			const name = this._details_name || "";
			if (name) this.load_remote_payload(name, true);
		});

		this.$body.on("click", ".oa2-payload-mode", (e) => {
			e.preventDefault();
			const mode = $(e.currentTarget).attr("data-mode") === "json" ? "json" : "raw";
			this._payload_mode = mode;
			this.sync_payload_tab();
			if (mode === "json") this.show_json_view();
			else this.show_raw_view();
		});

		this.$body.on("click", ".oa2-payload-reprocess", (e) => {
			e.preventDefault();
			this.confirm_reprocess();
		});

		this.$body.on("click", ".oa2-payload-download-btn", (e) => {
			e.preventDefault();
			e.stopPropagation();
			const $menu = this.$messagePage.find(".oa2-payload-menu");
			const willOpen = $menu.is("[hidden]");
			this.$messagePage.find(".oa2-payload-menu").attr("hidden", true);
			if (willOpen) {
				this.update_download_state();
				$menu.removeAttr("hidden");
				$(e.currentTarget).attr("aria-expanded", "true");
			} else {
				$(e.currentTarget).attr("aria-expanded", "false");
			}
		});

		this.$body.on("click", ".oa2-download-choice", (e) => {
			e.preventDefault();
			const kind = $(e.currentTarget).attr("data-download");
			this.$messagePage.find(".oa2-payload-menu").attr("hidden", true);
			this.$messagePage.find(".oa2-payload-download-btn").attr("aria-expanded", "false");
			this.download_payload(kind);
		});

		this.$body.on("click", (e) => {
			if ($(e.target).closest(".oa2-payload-download").length) return;
			this.$messagePage.find(".oa2-payload-menu").attr("hidden", true);
			this.$messagePage.find(".oa2-payload-download-btn").attr("aria-expanded", "false");
		});

		this.$ediModal.on("click", ".oa2-edi-modal-backdrop, .oa2-edi-modal-close", (e) => {
			e.preventDefault();
			this.close_edi_modal();
		});

		this.$ediModal.on("click", ".oa2-edi-modal-tab", (e) => {
			e.preventDefault();
			const tab = $(e.currentTarget).attr("data-tab");
			this.$ediModal.find(".oa2-edi-modal-tab").removeClass("is-active").attr("aria-selected", "false");
			$(e.currentTarget).addClass("is-active").attr("aria-selected", "true");
			this.$ediModal.find(".oa2-edi-panel").attr("hidden", true);
			this.$ediModal.find(`.oa2-edi-panel[data-panel="${tab}"]`).removeAttr("hidden");
		});

		this.$ediModal.on("click", ".oa2-edi-copy", (e) => {
			e.preventDefault();
			const kind = $(e.currentTarget).attr("data-copy");
			const text = kind === "json" ? this._edi_json_text : this._edi_raw_text;
			if (!text) return;
			const $btn = $(e.currentTarget);
			const label = $btn.text();
			const done = () => {
				$btn.text(__("Copied"));
				setTimeout(() => $btn.text(label), 1200);
			};
			if (navigator.clipboard && navigator.clipboard.writeText) {
				navigator.clipboard.writeText(text).then(done).catch(() => this.copy_text_fallback(text, done));
			} else {
				this.copy_text_fallback(text, done);
			}
		});

		$(document).off("keydown.oa2edi").on("keydown.oa2edi", (e) => {
			if (e.key === "Escape" && this.$ediModal.hasClass("is-open")) {
				this.close_edi_modal();
			}
		});

		if (window.openas2_manager && openas2_manager.sync_sidebar) {
			openas2_manager.sync_sidebar();
		}

		this.start_live_updates();
		this.load_counts();
	}

	start_live_updates() {
		const restart = !!this._live_timer;
		this.stop_live_updates();
		// Reload the remote message list while the page is open.
		this._live_timer = setInterval(() => this.pull_live(), 15000);

		if (frappe.realtime && frappe.realtime.on) {
			this._rt_handler = () => {
				if (document.hidden) return;
				this.schedule_background_refresh();
			};
			frappe.realtime.on("openas2_monitoring_updated", this._rt_handler);
		}
		if (!restart) this.schedule_background_refresh();
	}

	pull_live() {
		if (document.hidden) return;
		this.schedule_background_refresh();
	}

	schedule_background_refresh() {
		if (this._refresh_timer) return;
		this._refresh_timer = setTimeout(() => {
			this._refresh_timer = null;
			if (document.hidden) return;
			this.load_counts();
			this.load_rows({ background: true });
		}, 400);
	}

	stop_live_updates() {
		if (this._live_timer) {
			clearInterval(this._live_timer);
			this._live_timer = null;
		}
		if (this._refresh_timer) {
			clearTimeout(this._refresh_timer);
			this._refresh_timer = null;
		}
		if (this._rt_handler && frappe.realtime && frappe.realtime.off) {
			frappe.realtime.off("openas2_monitoring_updated", this._rt_handler);
			this._rt_handler = null;
		}
	}

	refresh_clock() {
		const tick = () => {
			const $el = this.$body.find(".oa2-monitor-datetime");
			if ($el.length) {
				$el.text(frappe.datetime.str_to_user(frappe.datetime.now_datetime()));
			}
		};
		tick();
		this._clock = setInterval(tick, 30000);
	}

	set_tab(tab) {
		this.tab = tab || "messages";
		this.$body.find(".oa2-monitor-tab").removeClass("active");
		this.$body.find(`.oa2-monitor-tab[data-tab="${this.tab}"]`).addClass("active");
		this.hide_message_page();
		this.close_edi_modal();
		this.load_rows();
	}

	apply_route_options() {
		const opts = frappe.route_options || {};
		const txn = opts.transaction_type || opts.transaction || "";
		const tab = opts.tab || "";
		const openEdi = opts.oa2_open_edi || "";
		const openMessage = opts.oa2_open_message || "";

		if (txn) {
			this.filters.transaction_type = String(txn);
			this.$body.find('[data-filter="transaction_type"]').val(this.filters.transaction_type);
		}
		if (tab === "transactions" || tab === "messages" || tab === "logs") {
			this.tab = tab;
			this.$body.find(".oa2-monitor-tab").removeClass("active");
			this.$body.find(`.oa2-monitor-tab[data-tab="${this.tab}"]`).addClass("active");
		} else if (txn || openEdi) {
			// KPI cards → EDI Transactions filtered by type
			this.tab = "transactions";
			this.$body.find(".oa2-monitor-tab").removeClass("active");
			this.$body.find('.oa2-monitor-tab[data-tab="transactions"]').addClass("active");
		}

		// Consume so a later refresh doesn't re-apply stale options
		frappe.route_options = null;
		if (openEdi) {
			setTimeout(() => this.open_edi_drawer(openEdi), 180);
		}
		if (openMessage) {
			this.tab = "messages";
			this.$body.find(".oa2-monitor-tab").removeClass("active");
			this.$body.find('.oa2-monitor-tab[data-tab="messages"]').addClass("active");
			setTimeout(() => this.show_message_page(openMessage), 180);
		}
	}

	read_filters_and_load() {
		const prevFrom = this.filters.date_from || "";
		const prevTo = this.filters.date_to || "";
		this.filters.partner = this.$body.find('[data-filter="partner"]').val() || "";
		this.filters.status = this.$body.find('[data-filter="status"]').val() || "";
		this.filters.transaction_type =
			this.$body.find('[data-filter="transaction_type"]').val() || "";
		this.filters.date_from = this.$body.find('[data-filter="date_from"]').val() || "";
		this.filters.date_to = this.$body.find('[data-filter="date_to"]').val() || "";
		this.filters.search = (this.$body.find('[data-filter="search"]').val() || "").trim();
		if (this.filters.date_from !== prevFrom || this.filters.date_to !== prevTo) {
			this.load_monitoring_filter_options({ preserve: true });
		}
		this.load_counts();
		this.load_rows();
	}

	_filter_option_exists($select, value) {
		if (!value) {
			return true;
		}
		return (
			$select.find("option").filter(function () {
				return $(this).val() === value;
			}).length > 0
		);
	}

	apply_monitoring_filter_options(payload, options) {
		const data = payload || {};
		const preserve = (options && options.preserve) !== false;
		const saved = preserve
			? {
					partner: this.filters.partner || this.$partner.val() || "",
					status: this.filters.status || this.$statusFilter.val() || "",
					transaction_type:
						this.filters.transaction_type || this.$txnFilter.val() || "",
			  }
			: { partner: "", status: "", transaction_type: "" };

		this.$partner.find('option:not([value=""])').remove();
		(data.partners || []).forEach((label) => {
			const text = String(label || "").trim();
			if (!text) return;
			this.$partner.append(
				`<option value="${frappe.utils.escape_html(text)}">${frappe.utils.escape_html(text)}</option>`
			);
		});

		this.$statusFilter.find('option:not([value=""])').remove();
		(data.statuses || []).forEach((status) => {
			const text = String(status || "").trim();
			if (!text) return;
			this.$statusFilter.append(
				`<option value="${frappe.utils.escape_html(text)}">${frappe.utils.escape_html(
					__(text)
				)}</option>`
			);
		});

		this.$txnFilter.find('option:not([value=""])').remove();
		(data.transaction_types || []).forEach((item) => {
			const code = String((item && item.code) || "").trim();
			if (!code) return;
			const label = String((item && item.label) || code).trim();
			this.$txnFilter.append(
				`<option value="${frappe.utils.escape_html(code)}">${frappe.utils.escape_html(
					label
				)}</option>`
			);
		});

		const restore = [
			["partner", this.$partner, "partner"],
			["status", this.$statusFilter, "status"],
			["transaction_type", this.$txnFilter, "transaction_type"],
		];
		restore.forEach(([key, $el, filterKey]) => {
			const value = saved[key] || "";
			if (value && this._filter_option_exists($el, value)) {
				$el.val(value);
				this.filters[filterKey] = value;
			} else {
				$el.val("");
				this.filters[filterKey] = "";
			}
		});
	}

	load_monitoring_filter_options(options) {
		if (this._filter_options_loading) {
			this._filter_options_reload = true;
			return;
		}
		this._filter_options_loading = true;
		const requestId = (this._filter_options_request || 0) + 1;
		this._filter_options_request = requestId;
		frappe.call({
			method: "openas2_manager.openas2.monitoring.get_monitoring_filter_options",
			args: {
				date_from: this.filters.date_from || null,
				date_to: this.filters.date_to || null,
			},
			callback: (r) => {
				if (this._filter_options_request !== requestId) return;
				this._filter_options_loading = false;
				const message = (r && r.message) || {};
				const failed =
					message.ok === false ||
					(!message.partners && !message.statuses && !message.transaction_types && message.error);
				if (failed) {
					frappe.show_alert({
						message: message.error || __("Filter options could not be loaded."),
						indicator: "orange",
					});
					this.apply_monitoring_filter_options(
						{ partners: [], statuses: [], transaction_types: [] },
						options
					);
				} else {
					this.apply_monitoring_filter_options(message, options);
				}
				if (this._filter_options_reload) {
					this._filter_options_reload = false;
					this.load_monitoring_filter_options(options);
				}
			},
			error: () => {
				if (this._filter_options_request !== requestId) return;
				this._filter_options_loading = false;
				frappe.show_alert({
					message: __("Filter options could not be loaded."),
					indicator: "orange",
				});
				this.apply_monitoring_filter_options(
					{ partners: [], statuses: [], transaction_types: [] },
					options
				);
				if (this._filter_options_reload) {
					this._filter_options_reload = false;
					this.load_monitoring_filter_options(options);
				}
			},
		});
	}

	refresh_sources() {
		frappe.call({
			method: "openas2_manager.openas2.monitoring.refresh_monitoring",
			freeze: true,
			freeze_message: __("Refreshing monitoring data…"),
			callback: (r) => {
				frappe.unfreeze();
				const msg = (r && r.message) || {};
				if (msg.ok === false || msg.error) {
					frappe.show_alert({
						message: msg.error || msg.message || __("The OpenAS2 database could not be read."),
						indicator: "red",
					});
				} else {
					frappe.show_alert({
						message: msg.message || __("Refreshed"),
						indicator: "green",
					});
				}
				this.load_monitoring_filter_options({ preserve: true });
				this.load_rows();
			},
			error: () => {
				frappe.unfreeze();
				frappe.show_alert({
					message: __("The OpenAS2 database could not be read."),
					indicator: "red",
				});
				this.load_rows();
			},
		});
	}

	load_counts() {
		if (this._counts_loading) return;
		this._counts_loading = true;
		const requestId = (this._counts_request || 0) + 1;
		this._counts_request = requestId;
		const timer = setTimeout(() => {
			if (this._counts_request === requestId) this._counts_loading = false;
		}, 20000);
		frappe.call({
			method: "openas2_manager.openas2.monitoring.get_dashboard_summary",
			args: { kpis_only: 1 },
			callback: (r) => {
				clearTimeout(timer);
				if (this._counts_request !== requestId) return;
				this._counts_loading = false;
				const kpis = ((r && r.message) || {}).kpis || [];
				const tones = ["blue", "green", "orange", "teal"];
				const selected = this.filters.transaction_type || "";
				this.$body.find(".oa2-monitor-kpis").html(
					kpis
						.map((k, i) => {
							const code = k.code || "";
							const active = code === selected ? " is-active" : "";
							const unavailable = k.available === false;
							const value = unavailable ? __("Unavailable") : k.count;
							const meta = unavailable
								? k.summary || ""
								: `${k.last_7 || 0} ${__("in the last 7 days")}`;
							const title = unavailable
								? k.note || k.summary || ""
								: `${__("View")} ${code}`;
							return `<article class="oa2-card oa2-kpi oa2-kpi-${tones[i % tones.length]}${active}" data-txn="${frappe.utils.escape_html(
								code
							)}" role="button" tabindex="0" title="${frappe.utils.escape_html(title)}">
								<div class="oa2-kpi-icon">${frappe.utils.icon(
									{ "204": "mail", "990": "tick", "210": "stock", "214": "file" }[code] || "file",
									"sm"
								)}</div>
								<div class="oa2-kpi-body">
									<div class="oa2-kpi-label">${frappe.utils.escape_html(code)} – ${frappe.utils.escape_html(
										k.label || ""
									)}</div>
									<div class="oa2-kpi-value">${frappe.utils.escape_html(value)}</div>
									<div class="oa2-kpi-meta">
										<span class="oa2-muted">${frappe.utils.escape_html(meta)}</span>
									</div>
								</div>
							</article>`;
						})
						.join("")
				);
			},
			error: () => {
				clearTimeout(timer);
				if (this._counts_request === requestId) this._counts_loading = false;
			},
		});
	}

	row_signature(rows) {
		return (rows || [])
			.map((row) =>
				[row.name, row.status, row.mdn_status, row.timestamp, row.transaction_type].join("\t")
			)
			.join("\n");
	}

	total_label(tab) {
		if (tab === "transactions") return __("Total Transactions");
		if (tab === "logs") return __("Total Logs");
		return __("Total Messages");
	}

	render_list_total(tab, message) {
		if (!this.$total || this.tab !== tab) return;
		const failed =
			!message || message.ok === false || message.total === null || message.total === undefined;
		const value = failed ? __("Unavailable") : String(message.total);
		this.$total.text(`${this.total_label(tab)}: ${value}`);
	}

	load_list_total() {
		const tab = this.tab || "messages";
		const requestId = (this._total_request || 0) + 1;
		this._total_request = requestId;
		if (this.$total) this.$total.text(`${this.total_label(tab)}: ${__("…")}`);
		const args = {
			date_from: this.filters.date_from || null,
			date_to: this.filters.date_to || null,
			partner: this.filters.partner || null,
			search: this.filters.search || null,
		};
		if (this.filters.status) args.status = this.filters.status;
		if (this.filters.transaction_type) args.transaction_type = this.filters.transaction_type;
		if (tab === "logs") args.errors_only = 1;
		frappe.call({
			method: "openas2_manager.openas2.monitoring.get_list_total",
			args,
			callback: (r) => {
				if (this._total_request !== requestId) return;
				this.render_list_total(tab, (r && r.message) || {});
			},
			error: () => {
				if (this._total_request !== requestId) return;
				this.render_list_total(tab, { ok: false, total: null });
			},
		});
	}

	load_rows(options) {
		const background = !!(options && options.background);
		if (!background) this.load_list_total();
		if (this.tab === "transactions") {
			this.load_edi_documents(background);
			return;
		}

		if (this._rows_loading) {
			if (!background) this._rows_again = true;
			return;
		}
		this._rows_loading = true;
		const requestId = (this._rows_request || 0) + 1;
		this._rows_request = requestId;

		const args = {
			date_from: this.filters.date_from || null,
			date_to: this.filters.date_to || null,
			limit: this.message_page_size,
		};
		if (this.filters.status) args.status = this.filters.status;
		if (this.filters.transaction_type) args.transaction_type = this.filters.transaction_type;
		if (this.filters.partner) args.partner = this.filters.partner;
		if (this.filters.search) args.search = this.filters.search;
		if (this.tab === "logs") args.errors_only = 1;

		if (!this._rows_shown) {
			this.$tbody.html(
				`<tr><td colspan="7" class="oa2-monitor-empty">${__("Loading…")}</td></tr>`
			);
			this.set_table_headers("messages");
		}

		const finish = () => {
			if (this._rows_request !== requestId) return;
			clearTimeout(timer);
			this._rows_loading = false;
			if (!this._rows_again) return;
			this._rows_again = false;
			this.load_rows();
		};
		const timer = setTimeout(() => {
			if (this._rows_request !== requestId || !this._rows_loading) return;
			this._rows_loading = false;
			if (!this._rows_shown) {
				this.$tbody.html(
					`<tr><td colspan="7" class="oa2-monitor-empty">${__(
						"The message list took too long to load."
					)}</td></tr>`
				);
			}
		}, 20000);
		frappe.call({
			method: "openas2_manager.openas2.monitoring.get_messages",
			args,
			callback: (r) => {
				if (this._rows_request !== requestId) return;
				try {
					const message = (r && r.message) || {};
					if (message.error) {
						this.rows = [];
						this._rows_shown = true;
						this._rows_signature = "";
						this.$tbody.html(
							`<tr><td colspan="7" class="oa2-monitor-empty">${frappe.utils.escape_html(
								message.error
							)}</td></tr>`
						);
						return;
					}
					const rows = message.rows || [];
					const signature = this.row_signature(rows);
					this.rows = rows;
					this._rows_shown = true;
					if (signature !== this._rows_signature) {
						this._rows_signature = signature;
						this.render_table(rows);
					}
				} finally {
					finish();
				}
			},
			error: () => {
				if (this._rows_request !== requestId) return;
				const queued = this._rows_again;
				this._rows_again = false;
				clearTimeout(timer);
				this._rows_loading = false;
				if (!this._rows_shown) {
					this.$tbody.html(
						`<tr><td colspan="7" class="oa2-monitor-empty">${__(
							"Failed to load messages."
						)}</td></tr>`
					);
				}
				if (queued) this.load_rows();
			},
		});
	}

	load_edi_documents(background) {
		if (this._edi_loading) return;
		this._edi_loading = true;
		const requestId = (this._edi_request || 0) + 1;
		this._edi_request = requestId;
		const args = {
			date_from: this.filters.date_from || null,
			date_to: this.filters.date_to || null,
			limit: 200,
		};
		if (this.filters.status) args.status = this.filters.status;
		if (this.filters.transaction_type) args.transaction_type = this.filters.transaction_type;
		if (this.filters.partner) args.partner = this.filters.partner;

		if (!background || !this._edi_shown) {
			this.$tbody.html(
				`<tr><td colspan="9" class="oa2-monitor-empty">${__("Loading…")}</td></tr>`
			);
			this.set_table_headers("transactions");
		}

		const timer = setTimeout(() => {
			if (this._edi_request !== requestId || !this._edi_loading) return;
			this._edi_loading = false;
			if (!this._edi_shown) {
				this.$tbody.html(
					`<tr><td colspan="9" class="oa2-monitor-empty">${__(
						"The EDI list took too long to load."
					)}</td></tr>`
				);
			}
		}, 20000);
		frappe.call({
			method: "openas2_manager.openas2.tms_edi.get_edi_documents",
			args,
			callback: (r) => {
				if (this._edi_request !== requestId) return;
				const message = (r && r.message) || {};
				if (message.error && !(message.rows || []).length) {
					this._edi_shown = true;
					this.$tbody.html(
						`<tr><td colspan="8" class="oa2-monitor-empty">${frappe.utils.escape_html(
							message.error
						)}</td></tr>`
					);
					return;
				}
				let rows = message.rows || [];
				if (this.filters.partner) {
					const p = this.filters.partner.toLowerCase();
					rows = rows.filter(
						(row) => String(row.partner_name || "").toLowerCase() === p
					);
				}
				if (this.filters.search) {
					const q = this.filters.search.toLowerCase();
					rows = rows.filter((row) =>
						[
							row.tms,
							row.tms_doc_name,
							row.file_name,
							row.transaction_type,
							row.status,
							row.partner_name,
							row.sent_from,
							row.received_by,
							row.reference_number,
							row.as2_message_id,
						]
							.join(" ")
							.toLowerCase()
							.includes(q)
					);
				}
				this.rows = rows;
				this._edi_shown = true;
				const signature = this.row_signature(rows);
				if (!background || signature !== this._edi_signature) {
					this._edi_signature = signature;
					this.render_edi_table(rows);
				}
			},
			error: () => {
				if (this._edi_request !== requestId) return;
				if (!this._edi_shown) {
					this.$tbody.html(
						`<tr><td colspan="9" class="oa2-monitor-empty">${__(
							"Failed to load EDI documents."
						)}</td></tr>`
					);
				}
			},
			always: () => {
				clearTimeout(timer);
				if (this._edi_request === requestId) this._edi_loading = false;
			},
		});
	}

	set_table_headers(mode) {
		const $head = this.$body.find(".oa2-monitor-table thead tr");
		if (mode === "transactions") {
			$head.html(`
				<th>${__("Date / Time")}</th>
				<th>${__("TMS")}</th>
				<th>${__("Type")}</th>
				<th>${__("Sent From")}</th>
				<th>${__("Received By")}</th>
				<th>${__("EDI Document")}</th>
				<th>${__("Status")}</th>
				<th>${__("Actions")}</th>
			`);
		} else {
			$head.html(`
				<th>${__("Date / Time")}</th>
				<th>${__("Partner")}</th>
				<th>${__("Transaction")}</th>
				<th>${__("Message ID")}</th>
				<th>${__("Status")}</th>
				<th>${__("MDN Status")}</th>
				<th>${__("Actions")}</th>
			`);
		}
	}

	render_edi_table(rows) {
		if (!rows.length) {
			this.$tbody.html(
				`<tr><td colspan="8" class="oa2-monitor-empty">${__(
					"No messages were returned from the OpenAS2 database."
				)}</td></tr>`
			);
			return;
		}
		this.$tbody.html(
			rows
				.map((r) => {
					const time = r.document_timestamp
						? frappe.datetime.str_to_user(r.document_timestamp)
						: "—";
					const docLabel = r.tms_doc_name || r.file_name || "—";
					const openBtn = r.tms_url
						? `<a class="oa2-mon-link" href="${frappe.utils.escape_html(
								r.tms_url
						  )}" target="_blank" rel="noopener">${__("Open")}</a>`
						: "";
					const viewBtn = `<button type="button" class="oa2-mon-view" data-edi="${frappe.utils.escape_html(
						r.name
					)}" style="color:#ffffff;background:#2563eb;-webkit-text-fill-color:#ffffff;border:0;border-radius:6px;padding:0.18rem 0.6rem;font-weight:800">${__("View")}</button>`;
					const actions = [viewBtn, openBtn].filter(Boolean).join(" ");
					return `<tr data-edi="${frappe.utils.escape_html(r.name)}">
						<td>${frappe.utils.escape_html(time)}</td>
						<td>${frappe.utils.escape_html(r.tms || "—")}</td>
						<td><span class="oa2-mon-link">${frappe.utils.escape_html(
							r.transaction_type || __("Unknown")
						)}</span></td>
						<td>${frappe.utils.escape_html(r.sent_from || "—")}</td>
						<td>${frappe.utils.escape_html(r.received_by || "—")}</td>
						<td class="oa2-mono" title="${frappe.utils.escape_html(docLabel)}">${frappe.utils.escape_html(
							docLabel
						)}</td>
						<td>${this.status_pill(r.status)}</td>
						<td>${actions || "—"}</td>
					</tr>`;
				})
				.join("")
		);
	}

	status_pill(status) {
		const s = String(status || "").toLowerCase();
		let tone = "muted";
		if (s.includes("fail") || s.includes("error")) tone = "failed";
		else if (s.includes("queue") || s.includes("pending")) tone = "warn";
		else if (s.includes("success") || s.includes("process") || s.includes("received") || s.includes("sent") || s.includes("mdn"))
			tone = "success";
		return `<span class="oa2-mon-pill oa2-mon-pill-${tone}">${frappe.utils.escape_html(
			status || "—"
		)}</span>`;
	}

	render_table(rows) {
		if (!rows.length) {
			this.$tbody.html(
				`<tr><td colspan="7" class="oa2-monitor-empty">${__(
					"No messages found. Click Refresh to discover from OpenAS2 sources."
				)}</td></tr>`
			);
			return;
		}
		this.$tbody.html(
			rows
				.map((r) => {
					const time = r.timestamp ? frappe.datetime.str_to_user(r.timestamp) : "—";
					const partner = r.partner || r.remote_as2_id || "—";
					const txn = r.transaction_type || __("Unknown");
					const mid = r.message_id_display || r.message_id || "—";
					return `<tr data-name="${frappe.utils.escape_html(r.name)}">
						<td>${frappe.utils.escape_html(time)}</td>
						<td>${frappe.utils.escape_html(partner)}</td>
						<td><span class="oa2-mon-link">${frappe.utils.escape_html(txn)}</span></td>
						<td class="oa2-mono" title="${frappe.utils.escape_html(mid)}"><span class="oa2-mon-link">${frappe.utils.escape_html(
							mid
						)}</span></td>
						<td>${this.status_pill(r.status)}</td>
						<td>${frappe.utils.escape_html(r.mdn_status || "—")}</td>
						<td><button type="button" class="oa2-mon-view" data-name="${frappe.utils.escape_html(
							r.name
						)}" style="color:#ffffff;background:#2563eb;-webkit-text-fill-color:#ffffff;border:0;border-radius:6px;padding:0.18rem 0.6rem;font-weight:800">${__("View")}</button></td>
					</tr>`;
				})
				.join("")
		);
	}

	hide_message_page() {
		this._details_name = "";
		this._payload_request = "";
		this._download_after_load = "";
		if (this.$messagePage) this.$messagePage.attr("hidden", true).empty();
		if (this.$monitorList) this.$monitorList.removeAttr("hidden");
	}

	close_edi_modal() {
		if (!this.$ediModal) return;
		this.$ediModal.attr("hidden", true).removeClass("is-open");
		this._edi_raw_text = "";
		this._edi_json_text = "";
	}

	copy_text_fallback(text, done) {
		const el = document.createElement("textarea");
		el.value = text;
		el.setAttribute("readonly", "");
		el.style.position = "fixed";
		el.style.left = "-9999px";
		document.body.appendChild(el);
		el.select();
		try {
			document.execCommand("copy");
			if (done) done();
		} catch (err) {
			// Leave the button label unchanged when the browser blocks the copy.
		}
		el.remove();
	}

	pretty_json(raw) {
		const text = raw == null ? "" : String(raw);
		if (!text.trim()) return "";
		try {
			return JSON.stringify(JSON.parse(text), null, 2);
		} catch (err) {
			return text;
		}
	}

	format_edi(raw) {
		const text = raw == null ? "" : String(raw).replace(/\r\n/g, "\n").replace(/\r/g, "\n");
		if (!text.trim()) return "";
		if (!text.includes("~")) return text.trim();
		const segments = text
			.split("~")
			.map((part) => part.replace(/\n/g, "").trim())
			.filter(Boolean);
		return segments.map((part) => part + "~").join("\n");
	}

	edi_type_names() {
		return {
			"204": __("Motor Carrier Load Tender"),
			"990": __("Load Tender Response"),
			"214": __("Transportation Carrier Shipment Status"),
			"210": __("Motor Carrier Freight Details and Invoice"),
			"810": __("Invoice"),
			"820": __("Payment Order/Remittance Advice"),
			"997": __("Functional Acknowledgment"),
		};
	}

	filename_transaction_type(fileName) {
		const match = String(fileName || "").match(
			/(?:^|[_\-.])(204|990|214|210|810|820|997)(?:[_\-.]|$)/i
		);
		return match ? match[1] : "";
	}

	resolved_transaction_type(detail, payloadCode) {
		const names = this.edi_type_names();
		const fromPayload = names[payloadCode] ? String(payloadCode) : "";
		const fromFile = this.filename_transaction_type(detail && detail.file_name);
		const stored = String((detail && detail.transaction_type) || "");
		const fromStored = names[stored] ? stored : "";
		return fromPayload || fromFile || fromStored || "";
	}

	transaction_label(code) {
		if (!code) return __("Unknown");
		return `EDI ${code}`;
	}

	show_message_page(name) {
		const requested = String(name || "");
		if (!requested) return;
		this._details_name = requested;
		this._payload_text = "";
		this._message_detail = null;
		if (this.$monitorList) this.$monitorList.attr("hidden", true);
		if (this.$messagePage) {
			this.$messagePage.removeAttr("hidden").html(`
				<button type="button" class="oa2-message-back">${__("Back to Monitoring")}</button>
				<p class="oa2-message-loading">${__("Loading message details…")}</p>
			`);
		}
		frappe.call({
			method: "openas2_manager.openas2.monitoring.get_message_details",
			args: { name: requested },
			callback: (r) => {
				if (this._details_name !== requested) return;
				this.render_message_page((r && r.message) || {});
			},
			error: () => {
				if (this._details_name !== requested) return;
				this.render_message_error(__("The message could not be loaded."));
			},
		});
	}

	render_message_error(message) {
		if (!this.$messagePage) return;
		this.$messagePage.html(`
			<button type="button" class="oa2-message-back">${__("Back to Monitoring")}</button>
			<p class="oa2-message-loading">${frappe.utils.escape_html(message || __("The message could not be loaded."))}</p>
		`);
	}

	open_edi_drawer(name) {
		frappe.call({
			method: "openas2_manager.openas2.tms_edi.get_edi_document_details",
			args: { name },
			freeze: true,
			freeze_message: __("Loading EDI…"),
			callback: (r) => {
				const d = r.message || {};
				this.render_edi_drawer(d);
			},
		});
	}

	render_edi_drawer(d) {
		const typeLabels = {
			"204": __("Load Tender"),
			"990": __("Response"),
			"214": __("Status"),
			"210": __("Freight Invoice"),
			"810": __("Invoice"),
			"820": __("Payment"),
		};
		const txn = d.transaction_type || "";
		const title = txn
			? `${txn}${typeLabels[txn] ? " — " + typeLabels[txn] : ""}`
			: __("EDI Document");
		const time = d.document_timestamp
			? frappe.datetime.str_to_user(d.document_timestamp)
			: "—";
		const ediRaw = d.edi_content || "";
		const ediAligned = this.format_edi(ediRaw);
		const jsonPretty = this.pretty_json(d.json_content || "");
		this._edi_raw_text = ediAligned;
		this._edi_json_text = jsonPretty;
		const ediPreview = ediAligned
			? frappe.utils.escape_html(ediAligned)
			: frappe.utils.escape_html(__("No EDI content synced for this document yet. Click Refresh on Monitoring, or wait for the next TMS webhook."));
		const jsonPreview = jsonPretty
			? frappe.utils.escape_html(jsonPretty)
			: frappe.utils.escape_html(__("JSON will appear once EDI content is available."));
		const fileName = d.file_name || "";
		const docName = d.tms_doc_name || "";
		const primaryName = fileName || docName;
		const extraName = fileName && docName && fileName !== docName ? docName : "";
		let documentHtml = "—";
		if (primaryName) {
			const primary = frappe.utils.escape_html(primaryName);
			documentHtml = d.tms_url
				? `<a class="oa2-mon-link" href="${frappe.utils.escape_html(
						d.tms_url
				  )}" target="_blank" rel="noopener">${primary}</a>`
				: primary;
			if (extraName) {
				documentHtml += `<span class="oa2-edi-sub">${frappe.utils.escape_html(extraName)}</span>`;
			}
		}
		const copyEdi = ediAligned
			? `<button type="button" class="oa2-edi-copy" data-copy="edi">${__("Copy")}</button>`
			: "";
		const copyJson = jsonPretty
			? `<button type="button" class="oa2-edi-copy" data-copy="json">${__("Copy")}</button>`
			: "";

		this.$ediModal.attr("data-oa2-edi", d.name || "");
		this.$ediModal.find(".oa2-edi-modal-body").html(`
			<dl class="oa2-edi-summary" aria-label="${__("Transaction summary")}">
				<div><dt>${__("Status")}</dt><dd>${this.status_pill(d.status)}</dd></div>
				<div><dt>${__("EDI Type")}</dt><dd>${frappe.utils.escape_html(title)}</dd></div>
				<div><dt>${__("TMS")}</dt><dd>${frappe.utils.escape_html(d.tms || "—")}</dd></div>
				<div><dt>${__("Sent From")}</dt><dd>${frappe.utils.escape_html(d.sent_from || "—")}</dd></div>
				<div><dt>${__("Received By")}</dt><dd>${frappe.utils.escape_html(d.received_by || "—")}</dd></div>
				<div><dt>${__("TMS Document / Filename")}</dt><dd>${documentHtml}</dd></div>
				<div><dt>${__("Reference")}</dt><dd>${frappe.utils.escape_html(d.reference_number || "—")}</dd></div>
				<div><dt>${__("Date / Time")}</dt><dd>${frappe.utils.escape_html(time)}</dd></div>
				<div><dt>${__("Direction")}</dt><dd>${frappe.utils.escape_html(d.direction || "—")}</dd></div>
			</dl>
			<div class="oa2-edi-stage">
				<div class="oa2-edi-modal-tabs" role="tablist">
					<button type="button" class="oa2-edi-modal-tab is-active" data-tab="edi" role="tab" aria-selected="true">${__("EDI")}</button>
					<button type="button" class="oa2-edi-modal-tab" data-tab="json" role="tab" aria-selected="false">${__("JSON")}</button>
					<button type="button" class="oa2-edi-modal-tab" data-tab="analysis" role="tab" aria-selected="false">✨ ${__("AI Analysis")}</button>
				</div>
				<div class="oa2-edi-panel" data-panel="edi" role="tabpanel">
					<div class="oa2-edi-panel-bar">
						<span>${ediAligned ? `${ediAligned.length} ${__("characters")}` : ""}</span>
						${copyEdi}
					</div>
					<pre class="oa2-edi-code">${ediPreview}</pre>
				</div>
				<div class="oa2-edi-panel" data-panel="json" role="tabpanel" hidden>
					<div class="oa2-edi-panel-bar">
						<span>${jsonPretty ? `${jsonPretty.length} ${__("characters")}` : ""}</span>
						${copyJson}
					</div>
					<pre class="oa2-edi-code">${jsonPreview}</pre>
				</div>
				<div class="oa2-edi-panel" data-panel="analysis" role="tabpanel" hidden>
					<div class="oa2-ai-analysis-host"></div>
				</div>
			</div>
		`);

		this.hide_message_page();
		this.$ediModal.removeAttr("hidden").addClass("is-open");
	}

	detail_value(value) {
		const text = value == null ? "" : String(value).trim();
		return text;
	}

	detail_field(label, value, html) {
		const text = html ? value : this.detail_value(value);
		if (!text) return "";
		const body = html ? text : frappe.utils.escape_html(text);
		return `<div><dt>${label}</dt><dd>${body}</dd></div>`;
	}

	detail_row(label, value) {
		const text = this.detail_value(value) || "—";
		return `<div><dt>${label}</dt><dd>${frappe.utils.escape_html(text)}</dd></div>`;
	}

	detail_section(title, fields) {
		const body = (fields || []).filter(Boolean).join("");
		if (!body) return "";
		return `<section class="oa2-message-section"><h2>${title}</h2><dl class="oa2-message-dl">${body}</dl></section>`;
	}

	render_message_page(d) {
		this._message_detail = d || {};
		this._payload_mode = "raw";
		this._payload_text = "";
		this._payload_ok = false;
		this._payload_truncated = false;
		this._payload_full = false;
		this._payload_json = null;
		this._payload_total = 0;
		this._payload_error = "";
		this._download_after_load = "";
		const time = d.timestamp ? frappe.datetime.str_to_user(d.timestamp) : "";
		const code = this.resolved_transaction_type(d, "");
		const names = this.edi_type_names();
		const typeName = names[code] || "";
		const listedType = d.transaction_type || __("Unknown");
		const detectedText = code
			? `${this.transaction_label(code)}${typeName ? " — " + typeName : ""}`
			: names[listedType]
				? `${this.transaction_label(listedType)} — ${names[listedType]}`
				: __("Unknown");
		const identity = d.file_name || d.message_id_display || d.message_id || d.name || "";
		const direction = this.detail_value(d.direction);
		const dirClass = direction.toLowerCase() === "inbound" ? "is-in" : "is-out";
		const fromRemote =
			d.source === "OpenAS2 database" || String(d.name || "").indexOf("remote:") === 0;
		let edi = "";
		if (d.edi_document_route && d.edi_document) {
			edi = `<a class="oa2-mon-link" href="${frappe.utils.escape_html(d.edi_document_route)}">${frappe.utils.escape_html(
				d.edi_document
			)}</a>`;
		} else if (d.edi_document) {
			edi = frappe.utils.escape_html(d.edi_document);
		}
		const dir = direction.toLowerCase();
		const sender = dir === "inbound" ? d.remote_as2_id : dir === "outbound" ? d.local_as2_id : "";
		const receiver = dir === "inbound" ? d.local_as2_id : dir === "outbound" ? d.remote_as2_id : "";
		const transport = [
			this.detail_field(__("Signature Algorithm"), d.signature_algorithm),
			this.detail_field(__("Encryption Algorithm"), d.encryption_algorithm),
			this.detail_field(__("Compression"), d.compression),
			this.detail_field(__("Content Type"), d.content_type),
			this.detail_field(__("Resend Status"), d.resend_status),
			this.detail_field(__("Resend Count"), d.resend_count),
			this.detail_field(__("Previous Message ID"), d.previous_message_id),
			this.detail_field(__("MDN ID"), d.mdn_id),
		];
		const localPayload = fromRemote ? "" : this.detail_value(d.raw_reference);
		const localPointer = localPayload.indexOf("msg_metadata:") === 0;

		this.$messagePage.html(`
			<button type="button" class="oa2-message-back">${__("Back to Monitoring")}</button>
			<header class="oa2-message-head">
				<p class="oa2-message-kicker">${__("Message Details")}</p>
				<div class="oa2-message-title-row">
					<h1 class="oa2-message-type">${frappe.utils.escape_html(this.transaction_label(code))}</h1>
					${typeName ? `<p class="oa2-message-type-name">${frappe.utils.escape_html(typeName)}</p>` : ""}
				</div>
				<p class="oa2-message-identity">${frappe.utils.escape_html(identity || "—")}</p>
				<div class="oa2-message-badges">
					${d.status ? this.status_pill(d.status) : ""}
					${direction ? `<span class="oa2-dir-badge ${dirClass}">${frappe.utils.escape_html(direction)}</span>` : ""}
					${time ? `<span class="oa2-message-time">${frappe.utils.escape_html(time)}</span>` : ""}
				</div>
			</header>
			<div class="oa2-message-grid">
				${this.detail_section(__("Partner / AS2 Information"), [
					this.detail_row(__("Partner Name"), d.partner),
					this.detail_row(__("Local AS2 ID"), d.local_as2_id),
					this.detail_row(__("Remote AS2 ID"), d.remote_as2_id),
					this.detail_row(__("MDN Status"), d.mdn_status),
					this.detail_row(__("OpenAS2 State"), d.state),
					this.detail_row(__("Timestamp"), time),
				])}
				${this.detail_section(__("EDI Information"), [
					`<div><dt>${__("Detected Transaction Type")}</dt><dd class="oa2-detected-type">${frappe.utils.escape_html(
						detectedText
					)}</dd></div>`,
					this.detail_field(__("EDI Document"), edi, true),
					this.detail_row(__("Filename"), d.file_name),
					this.detail_row(__("Message ID"), d.message_id_display || d.message_id),
					this.detail_row(__("Direction"), direction),
					this.detail_row(__("Sender"), sender),
					this.detail_row(__("Receiver"), receiver),
				])}
				${this.detail_section(__("Transport Information"), transport)}
			</div>
			<section class="oa2-message-section oa2-payload-section">
				<div class="oa2-payload-bar">
					<h2 class="oa2-payload-heading">${__("Raw EDI")}</h2>
					<div class="oa2-payload-actions">
						<div class="oa2-payload-switch" role="tablist" aria-label="${__("Payload view")}">
							<button type="button" class="oa2-payload-mode is-active" role="tab" id="oa2-payload-tab-raw" aria-controls="oa2-payload-panel" data-mode="raw" aria-selected="true" aria-pressed="true">${__("Raw EDI")}</button>
							<button type="button" class="oa2-payload-mode" role="tab" id="oa2-payload-tab-json" aria-controls="oa2-payload-panel" data-mode="json" aria-selected="false" aria-pressed="false">${__("JSON")}</button>
						</div>
						<div class="oa2-payload-download">
							<button type="button" class="oa2-payload-download-btn" aria-expanded="false" aria-haspopup="menu">${__("Download")}</button>
							<div class="oa2-payload-menu" role="menu" hidden>
								<button type="button" class="oa2-download-choice" data-download="edi" role="menuitem">${__("Download Raw EDI")}</button>
								<button type="button" class="oa2-download-choice" data-download="json" role="menuitem" disabled>${__("Download JSON")}</button>
								<p class="oa2-download-hint"></p>
							</div>
						</div>
						<button type="button" class="oa2-payload-reprocess">${__("Reprocess")}</button>
						<button type="button" class="oa2-payload-copy" hidden>${__("Copy Payload")}</button>
					</div>
				</div>
				<pre id="oa2-payload-panel" class="oa2-payload" role="tabpanel" aria-labelledby="oa2-payload-tab-raw" aria-live="polite"></pre>
				<p class="oa2-payload-meta"></p>
				<button type="button" class="oa2-payload-full" hidden>${__("Load full payload")}</button>
			</section>
		`);

		if (fromRemote) {
			this.load_remote_payload(d.name, false);
			return;
		}
		if (localPayload && !localPointer) {
			this.show_local_payload(localPayload);
			return;
		}
		this.$messagePage.find(".oa2-payload").text(__("This message has no EDI payload."));
		this.$messagePage.find(".oa2-payload-meta").text("");
	}

	apply_detected_type(payloadCode) {
		const detail = this._message_detail || {};
		const code = this.resolved_transaction_type(detail, payloadCode || "");
		const names = this.edi_type_names();
		const typeName = names[code] || "";
		this.$messagePage.find(".oa2-message-type").text(this.transaction_label(code));
		const $name = this.$messagePage.find(".oa2-message-type-name");
		if (typeName) {
			if ($name.length) $name.text(typeName);
			else this.$messagePage.find(".oa2-message-title-row").append(
				$("<p>").addClass("oa2-message-type-name").text(typeName)
			);
		}
		this.$messagePage.find(".oa2-detected-type").text(
			code ? `${this.transaction_label(code)}${typeName ? " — " + typeName : ""}` : __("Unknown")
		);
	}

	show_local_payload(text) {
		const value = String(text || "");
		this._payload_text = value;
		this._payload_ok = Boolean(value);
		this._payload_truncated = false;
		this._payload_full = true;
		this._payload_total = value.length;
		this._payload_error = value ? "" : __("This message has no EDI payload.");
		this._payload_json = null;
		if (this._payload_mode === "json" && value) {
			this.show_json_view();
			return;
		}
		this.show_raw_view();
	}

	load_remote_payload(name, full) {
		const requested = String(name || "");
		const cacheKey = `${requested}:${full ? "full" : "preview"}`;
		this._payload_request = cacheKey;
		const cached = this._payload_cache[cacheKey];
		if (cached) {
			this.show_remote_payload(cached, full);
			return;
		}
		const $pre = this.$messagePage.find(".oa2-payload");
		$pre.addClass("is-loading").text(__("Loading payload…"));
		this.$messagePage.find(".oa2-payload-full").attr("hidden", true);
		frappe.call({
			method: "openas2_manager.openas2.monitoring.get_remote_message_payload",
			args: { name: requested, full: full ? 1 : 0 },
			callback: (r) => {
				if (this._payload_request !== cacheKey) return;
				const message = (r && r.message) || {};
				if (message.available || message.reason === "empty") {
					this._payload_cache[cacheKey] = message;
				}
				this.show_remote_payload(message, full);
			},
			error: () => {
				if (this._payload_request !== cacheKey) return;
				this.show_remote_payload({ available: false, reason: "denied", payload: "" }, full);
			},
		});
	}

	show_remote_payload(message, full) {
		const pendingDownload = this._download_after_load;
		this._download_after_load = "";
		const $pre = this.$messagePage.find(".oa2-payload");
		if (!$pre.length) return;
		$pre.removeClass("is-loading");
		if (message && message.reason === "truncated" && !full && this._details_name) {
			this.load_remote_payload(this._details_name, true);
			return;
		}
		const text = message && message.available ? String(message.payload || "") : "";
		const total = Number((message && message.payload_chars) || 0);
		if (message && message.transaction_type) {
			this.apply_detected_type(message.transaction_type);
		}
		this._payload_full = Boolean(full);
		this._payload_json = null;
		if (text) {
			this._payload_text = text;
			this._payload_ok = true;
			this._payload_total = total || text.length;
			this._payload_truncated = total > text.length;
			this._payload_error = "";
			if (this._payload_mode === "json") this.show_json_view();
			else this.show_raw_view();
			if (pendingDownload === "edi") this.finish_download("edi");
			return;
		}
		this._payload_text = "";
		this._payload_ok = false;
		this._payload_truncated = false;
		this._payload_total = message && message.reason === "empty" ? 0 : total;
		if (message && message.reason === "empty") {
			this._payload_error = __("This message has no EDI payload.");
		} else if (message && message.reason === "not_edi") {
			this._payload_error = __("This message does not contain an X12 EDI attachment.");
		} else if (message && message.reason === "unavailable") {
			this._payload_error = __("The remote message could not be read.");
		} else if (message && message.reason === "denied") {
			this._payload_error = __("Not permitted to access this message.");
		} else {
			this._payload_error = __("This message has no EDI payload.");
		}
		this.show_raw_view();
	}

	sync_payload_tab() {
		const mode = this._payload_mode === "json" ? "json" : "raw";
		const $tabs = this.$messagePage.find(".oa2-payload-mode");
		$tabs.removeClass("is-active").attr("aria-pressed", "false").attr("aria-selected", "false");
		$tabs.filter(`[data-mode="${mode}"]`).addClass("is-active").attr("aria-pressed", "true").attr("aria-selected", "true");
		this.$messagePage.find(".oa2-payload-heading").text(mode === "json" ? __("JSON") : __("Raw EDI"));
		this.$messagePage.find(".oa2-payload").attr(
			"aria-labelledby",
			mode === "json" ? "oa2-payload-tab-json" : "oa2-payload-tab-raw"
		);
	}

	show_raw_view() {
		this.sync_payload_tab();
		const $pre = this.$messagePage.find(".oa2-payload");
		const $meta = this.$messagePage.find(".oa2-payload-meta");
		const $copy = this.$messagePage.find(".oa2-payload-copy");
		const $full = this.$messagePage.find(".oa2-payload-full");
		if (!$pre.length) return;
		$pre.removeClass("is-loading");
		if (this._payload_ok && this._payload_text) {
			const text = this._payload_text;
			$pre.text(text);
			$copy.removeAttr("hidden");
			const total = this._payload_total || this._payload_text.length;
			let note = `${total} ${__("characters")}`;
			if (this._payload_truncated) {
				note = `${__("Preview truncated")} · ${this._payload_text.length} / ${total} ${__("characters")}`;
			}
			$meta.text(note);
			if (this._payload_truncated && !this._payload_full) $full.removeAttr("hidden");
			else $full.attr("hidden", true);
		} else {
			$pre.text(this._payload_error || __("This message has no EDI payload."));
			$copy.attr("hidden", true);
			$full.attr("hidden", true);
			$meta.text(this._payload_total === 0 ? `0 ${__("characters")}` : "");
		}
		this.update_download_state();
	}

	show_json_view() {
		this.sync_payload_tab();
		const $pre = this.$messagePage.find(".oa2-payload");
		if (!$pre.length) return;
		if (!this._payload_ok || !this._payload_text) {
			$pre.removeClass("is-loading").text(
				__("JSON conversion is unavailable because the EDI payload could not be retrieved.")
			);
			this.$messagePage.find(".oa2-payload-meta").text("");
			this.$messagePage.find(".oa2-payload-copy").attr("hidden", true);
			this.update_download_state();
			return;
		}
		if (this._payload_truncated && !this._payload_full && this._details_name) {
			this.load_remote_payload(this._details_name, true);
			return;
		}
		const cached = this._payload_json;
		if (cached && cached.for_text === this._payload_text) {
			this.render_json(cached);
			return;
		}
		const text = this._payload_text;
		$pre.addClass("is-loading").text(__("Converting to JSON…"));
		this.$messagePage.find(".oa2-payload-full").attr("hidden", true);
		frappe.call({
			method: "openas2_manager.openas2.monitoring.convert_message_payload_json",
			args: { payload: text },
			callback: (r) => {
				if (this._payload_text !== text || this._payload_mode !== "json") return;
				const message = Object.assign({ for_text: text }, (r && r.message) || {});
				this._payload_json = message;
				this.render_json(message);
			},
			error: () => {
				if (this._payload_text !== text || this._payload_mode !== "json") return;
				this._payload_json = {
					available: false,
					reason: "invalid",
					for_text: text,
					json: "",
					message: __("JSON conversion is unavailable because the payload could not be converted."),
				};
				this.render_json(this._payload_json);
			},
		});
	}

	render_json(message) {
		const $pre = this.$messagePage.find(".oa2-payload");
		const $meta = this.$messagePage.find(".oa2-payload-meta");
		const $copy = this.$messagePage.find(".oa2-payload-copy");
		if (!$pre.length || this._payload_mode !== "json") return;
		$pre.removeClass("is-loading");
		if (message && message.available && message.json) {
			let pretty = String(message.json);
			try {
				pretty = JSON.stringify(JSON.parse(pretty), null, 2);
				message.json = pretty;
			} catch (e) {
				message.available = false;
				message.json = "";
				message.message = __("JSON conversion is unavailable because the result was not valid JSON.");
			}
		}
		if (message && message.available && message.json) {
			$pre.text(message.json);
			$copy.removeAttr("hidden");
			const total = this._payload_total || (this._payload_text || "").length;
			$meta.text(`${message.json.length} ${__("JSON characters")} · ${total} ${__("payload characters")}`);
		} else {
			$pre.text((message && message.message) || __("JSON conversion is unavailable for this message."));
			$copy.attr("hidden", true);
			$meta.text("");
		}
		this.$messagePage.find(".oa2-payload-full").attr("hidden", true);
		this.update_download_state();
	}

	update_download_state() {
		const $edi = this.$messagePage.find('[data-download="edi"]');
		const $json = this.$messagePage.find('[data-download="json"]');
		const $hint = this.$messagePage.find(".oa2-download-hint");
		if (this._payload_ok && this._payload_text) $edi.prop("disabled", false).removeAttr("title");
		else {
			$edi.prop("disabled", true).attr("title", this._payload_error || __("The EDI payload is not available."));
		}
		const jsonReady = Boolean(this._payload_json && this._payload_json.available && this._payload_json.json);
		if (jsonReady) {
			$json.prop("disabled", false).removeAttr("title");
			$hint.text("");
			return;
		}
		const why = (this._payload_json && this._payload_json.message)
			|| __("JSON conversion is unavailable until this message can be converted.");
		$json.prop("disabled", true).attr("title", why);
		$hint.text(why);
	}

	payload_filename(ext) {
		const detail = this._message_detail || {};
		let source = String(detail.file_name || detail.message_id || detail.name || "message");
		source = source.split(/[\\/]/).pop();
		source = source.replace(/\.(edi|txt|json)$/i, "");
		source = source.replace(/[^A-Za-z0-9._-]+/g, "_").replace(/^[._]+|[._]+$/g, "");
		if (!source) source = "message";
		return `${source.slice(0, 80)}${ext}`;
	}

	save_download(filename, text, mime) {
		if (!filename || !text) return;
		const blob = new Blob([text], { type: mime || "text/plain" });
		const url = URL.createObjectURL(blob);
		const link = document.createElement("a");
		link.href = url;
		link.download = filename;
		document.body.appendChild(link);
		link.click();
		link.remove();
		URL.revokeObjectURL(url);
	}

	download_payload(kind) {
		if (
			kind !== "json" &&
			this._payload_truncated &&
			!this._payload_full &&
			this._details_name
		) {
			this._download_after_load = "edi";
			this.load_remote_payload(this._details_name, true);
			return;
		}
		this.finish_download(kind);
	}

	finish_download(kind) {
		if (kind === "json") {
			const parsed = this._payload_json;
			if (!parsed || !parsed.available || !parsed.json) return;
			let body = "";
			try {
				body = JSON.stringify(JSON.parse(parsed.json), null, 2);
			} catch (e) {
				return;
			}
			if (!body || body === "null") return;
			this.save_download(this.payload_filename(".json"), body, "application/json");
			return;
		}
		if (!this._payload_ok || !this._payload_text) return;
		const name = String((this._message_detail || {}).file_name || "");
		const ext = /\.txt$/i.test(name) ? ".txt" : ".edi";
		this.save_download(this.payload_filename(ext), this._payload_text, "text/plain");
	}

	confirm_reprocess() {
		if (this._reprocess_running) return;
		const name = this._details_name;
		if (!name) return;
		this._reprocess_running = true;
		this.$body.find(".oa2-payload-reprocess").prop("disabled", true);
		frappe.confirm(
			__(
				"This transaction will be processed again. The original message will not be changed or deleted."
			),
			() => this.submit_reprocess(name),
			() => {
				this._reprocess_running = false;
				this.$body.find(".oa2-payload-reprocess").prop("disabled", false).text(__("Reprocess"));
			}
		);
	}

	submit_reprocess(name) {
		const $btn = this.$body.find(".oa2-payload-reprocess");
		$btn.prop("disabled", true).text(__("Reprocessing…"));
		frappe.call({
			method: "openas2_manager.openas2.reprocess.reprocess_message",
			args: { name },
			callback: (r) => {
				const result = (r && r.message) || {};
				if (result.ok) {
					frappe.show_alert({ message: result.message, indicator: "green" });
					this._payload_cache = {};
					this.show_message_page(name);
					this.load_counts();
					this.load_rows({ background: true });
					return;
				}
				frappe.show_alert({
					message: result.message || __("The transaction could not be processed again."),
					indicator: "red",
				});
			},
			error: (r) => {
				frappe.show_alert({
					message: this.reprocess_error_message(r),
					indicator: "red",
				});
			},
			always: () => {
				this._reprocess_running = false;
				this.$body.find(".oa2-payload-reprocess").prop("disabled", false).text(__("Reprocess"));
			},
		});
	}

	reprocess_error_message(r) {
		const server = r && (r._server_messages || (r.responseJSON && r.responseJSON._server_messages));
		if (server) {
			try {
				const parsed = typeof server === "string" ? JSON.parse(server) : server;
				const first = JSON.parse(parsed[0] || "{}");
				if (first.message) return first.message;
			} catch (e) {
				return __("The transaction could not be processed again.");
			}
		}
		return __("The transaction could not be processed again.");
	}
};
