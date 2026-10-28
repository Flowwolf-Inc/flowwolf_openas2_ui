// Copyright (c) 2026, Lakshana and contributors
// For license information, please see license.txt

frappe.pages["openas2-dashboard"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Home"),
		single_column: true,
	});
	frappe.breadcrumbs.add("OpenAS2 Manager");
	$(wrapper).addClass("oa2-dashboard-wrapper");
	/* Collapse Frappe's empty col-lg-2 layout-side-section (reserves ~17% width) */
	document.body.classList.add("no-sidebar");
	document.body.classList.add("oa2-dashboard-route");
	$(wrapper).find(".layout-side-section").addClass("hide-sidebar").hide();
	/* Kill Frappe container max-width so OA2 fills the viewport */
	$(wrapper).css({ width: "100%", maxWidth: "none", margin: "0", padding: "0" });
	$(wrapper).find(".layout-main, .layout-main-section-wrapper, .layout-main-section, .page-body")
		.css({ width: "100%", maxWidth: "none", marginLeft: "0", marginRight: "0", paddingLeft: "0", paddingRight: "0" });
	/* Hide Frappe desk navbar for this page only */
	$(".sticky-top, header.navbar, .navbar.navbar-expand").attr("data-oa2-dash-nav", "1").hide();
	document.body.classList.add("oa2-has-sidebar");
	document.body.classList.add("oa2-use-inpage-sidebar");
	document.body.classList.remove("oa2-using-global-sidebar");
	document.body.classList.remove("oa2-sidebar-mounted");
	document.body.classList.remove("oa2-hide-desk-chrome");
	document.documentElement.classList.remove("oa2-hide-desk-chrome");
	wrapper.dashboard_page = new openas2_manager.OpenAS2DashboardPage(page);
	document.querySelectorAll(".oa2-sidebar-inpage").forEach(function (node) {
		node.style.setProperty("display", "flex", "important");
		node.style.setProperty("visibility", "visible", "important");
	});
	if (window.openas2_manager && openas2_manager.sync_sidebar) {
		openas2_manager.sync_sidebar();
	}
	setTimeout(() => {
		document.body.classList.add("no-sidebar");
		$(wrapper).find(".layout-side-section").addClass("hide-sidebar").hide();
		document.querySelectorAll(".oa2-sidebar-inpage").forEach(function (node) {
			node.style.setProperty("display", "flex", "important");
		});
		if (window.openas2_manager && openas2_manager.sync_sidebar) {
			openas2_manager.sync_sidebar();
		}
	}, 100);
};

frappe.pages["openas2-dashboard"].on_page_show = function (wrapper) {
	document.body.classList.add("no-sidebar");
	document.body.classList.add("oa2-dashboard-route");
	$(".oa2-dashboard-wrapper .layout-side-section").addClass("hide-sidebar").hide();
	$(".oa2-dashboard-wrapper").css({ width: "100%", maxWidth: "none", margin: "0", padding: "0" });
	$(".oa2-dashboard-wrapper .layout-main, .oa2-dashboard-wrapper .layout-main-section-wrapper, .oa2-dashboard-wrapper .layout-main-section, .oa2-dashboard-wrapper .page-body")
		.css({ width: "100%", maxWidth: "none", marginLeft: "0", marginRight: "0", paddingLeft: "0", paddingRight: "0" });
	$(".sticky-top, header.navbar, .navbar.navbar-expand").attr("data-oa2-dash-nav", "1").hide();
	document.body.classList.add("oa2-has-sidebar");
	document.body.classList.add("oa2-use-inpage-sidebar");
	document.body.classList.remove("oa2-using-global-sidebar");
	document.body.classList.remove("oa2-sidebar-mounted");
	document.body.classList.remove("oa2-hide-desk-chrome");
	document.documentElement.classList.remove("oa2-hide-desk-chrome");
	document.querySelectorAll(".oa2-sidebar-inpage").forEach(function (node) {
		node.style.setProperty("display", "flex", "important");
	});
	if (window.openas2_manager && openas2_manager.sync_sidebar) {
		openas2_manager.sync_sidebar();
	}
	if (wrapper && wrapper.dashboard_page && wrapper.dashboard_page.start_polling) {
		wrapper.dashboard_page.start_polling();
	}
};

frappe.pages["openas2-dashboard"].on_page_hide = function (wrapper) {
	document.body.classList.remove("no-sidebar");
	document.body.classList.remove("oa2-dashboard-route");
	$('[data-oa2-dash-nav="1"]').show().removeAttr("data-oa2-dash-nav");
	if (wrapper && wrapper.dashboard_page && wrapper.dashboard_page.stop_polling) {
		wrapper.dashboard_page.stop_polling();
	}
	if (window.openas2_manager && openas2_manager.sync_sidebar) {
		setTimeout(openas2_manager.sync_sidebar, 0);
	}
};

frappe.provide("openas2_manager");

openas2_manager.OpenAS2DashboardPage = class OpenAS2DashboardPage {
	constructor(page) {
		this.page = page;
		this.$body = $(page.body).addClass("oa2-home");
		this.THEME_KEY = "oa2-dashboard-theme";
		this._kpi_by_code = {};
		this._last_kpi_shells = null;
		this.make();
		this.load_dashboard();
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
		this.ensure_theme_styles();
		this.$body.attr("data-oa2-theme", t);
		const $wrap = this.$body.closest(".oa2-dashboard-wrapper");
		if ($wrap.length) {
			$wrap.attr("data-oa2-theme", t);
		}
		document.documentElement.setAttribute("data-oa2-theme", t);
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

	theme_toggle_html() {
		const sun = `<svg class="oa2-theme-icon oa2-theme-icon-sun" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2.2M12 19.8V22M4.9 4.9l1.6 1.6M17.5 17.5l1.6 1.6M2 12h2.2M19.8 12H22M4.9 19.1l1.6-1.6M17.5 6.5l1.6-1.6"/></svg>`;
		const moon = `<svg class="oa2-theme-icon oa2-theme-icon-moon" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20.5 14.2A7.8 7.8 0 0 1 9.8 3.5 7.9 7.9 0 1 0 20.5 14.2z"/></svg>`;
		return `
			<button
				type="button"
				class="oa2-theme-switch"
				role="switch"
				aria-checked="false"
				aria-label="${__("Toggle light / dark theme")}"
				title="${__("Toggle light / dark theme")}"
			>
				<span class="oa2-theme-track" aria-hidden="true">
					${sun}
					${moon}
					<span class="oa2-theme-thumb"></span>
				</span>
			</button>
		`;
	}

	ensure_theme_styles() {
		let style = document.getElementById("oa2-theme-runtime-css");
		if (!style) {
			style = document.createElement("style");
			style.id = "oa2-theme-runtime-css";
			document.head.appendChild(style);
		}
		style.textContent = `
/* toggle — compact sun/moon pill */
.oa2-theme-toggle{display:inline-flex;align-items:center;user-select:none}
.oa2-theme-side{display:none!important}
.oa2-theme-switch{appearance:none;-webkit-appearance:none;border:0;padding:0;margin:0;background:transparent;cursor:pointer;display:inline-flex;align-items:center;line-height:0}
.oa2-theme-switch input{display:none!important}
.oa2-theme-track{display:block;width:46px;height:26px;border-radius:999px;background:#e2e8f0;border:1px solid #cbd5e1;box-sizing:border-box;position:relative;box-shadow:inset 0 1px 2px rgba(15,23,42,.06);overflow:hidden;transition:background .28s ease,border-color .28s ease,box-shadow .28s ease}
.oa2-theme-icon{position:absolute;top:50%;transform:translateY(-50%);z-index:1;pointer-events:none;opacity:.55;transition:opacity .28s ease,color .28s ease}
.oa2-theme-icon-sun{left:6px;color:#f59e0b}
.oa2-theme-icon-moon{right:6px;color:#64748b}
.oa2-theme-thumb{position:absolute;top:2px;left:2px;width:20px;height:20px;border-radius:999px;background:#fff;box-shadow:0 1px 3px rgba(15,23,42,.22),0 0 0 1px rgba(15,23,42,.04);transition:transform .28s cubic-bezier(.4,0,.2,1);z-index:2}
.oa2-theme-switch:focus-visible .oa2-theme-track{outline:2px solid #2563eb;outline-offset:2px}
.oa2-theme-switch.is-dark .oa2-theme-track,.oa2-theme-switch[aria-checked="true"] .oa2-theme-track,.oa2-theme-toggle.is-dark .oa2-theme-track{background:#1e293b;border-color:#334155;box-shadow:inset 0 1px 2px rgba(0,0,0,.35)}
.oa2-theme-switch.is-dark .oa2-theme-thumb,.oa2-theme-switch[aria-checked="true"] .oa2-theme-thumb,.oa2-theme-toggle.is-dark .oa2-theme-thumb{transform:translateX(20px)}
.oa2-theme-switch.is-dark .oa2-theme-icon-sun,.oa2-theme-switch[aria-checked="true"] .oa2-theme-icon-sun,.oa2-theme-toggle.is-dark .oa2-theme-icon-sun{opacity:.35;color:#94a3b8}
.oa2-theme-switch.is-dark .oa2-theme-icon-moon,.oa2-theme-switch[aria-checked="true"] .oa2-theme-icon-moon,.oa2-theme-toggle.is-dark .oa2-theme-icon-moon{opacity:.95;color:#e2e8f0}
.oa2-theme-switch:not(.is-dark):not([aria-checked="true"]) .oa2-theme-icon-sun,.oa2-theme-toggle:not(.is-dark) .oa2-theme-icon-sun{opacity:.95}
.oa2-theme-dots,.oa2-theme-dot{display:none!important}
.oa2-home[data-oa2-theme="dark"] .oa2-theme-track{background:#e5e7eb;border-color:transparent;box-shadow:inset 0 0 0 1px #d1d5db}
.oa2-home[data-oa2-theme="dark"] .oa2-theme-switch.is-dark .oa2-theme-track,.oa2-home[data-oa2-theme="dark"] .oa2-theme-switch[aria-checked="true"] .oa2-theme-track,.oa2-home[data-oa2-theme="dark"] .oa2-theme-toggle.is-dark .oa2-theme-track{background:#374151;border-color:transparent;box-shadow:inset 0 0 0 1px #4b5563}

/* dark theme — soft enterprise slate; does not alter light */
.oa2-dashboard-wrapper[data-oa2-theme="dark"].page-container,
.oa2-dashboard-wrapper[data-oa2-theme="dark"] .layout-main-section-wrapper,
.oa2-dashboard-wrapper[data-oa2-theme="dark"] .layout-main-section,
.oa2-dashboard-wrapper[data-oa2-theme="dark"] .page-body,
.oa2-home[data-oa2-theme="dark"],
.oa2-home[data-oa2-theme="dark"] .oa2-main-pane{background:#1c212b!important;color:#e8eaed!important}
.oa2-home[data-oa2-theme="dark"] .oa2-sidebar-inpage{background:#1a1f27!important;color:#e5e7eb!important;box-shadow:4px 0 24px rgba(0,0,0,.5)}
.oa2-home[data-oa2-theme="dark"] .oa2-brand-title{color:#fff!important}
.oa2-home[data-oa2-theme="dark"] .oa2-brand-tagline{color:rgba(255,255,255,.78)!important;opacity:1}
.oa2-home[data-oa2-theme="dark"] .oa2-brand-mark{border-color:rgba(255,255,255,.85);color:#fff;background:transparent}
.oa2-home[data-oa2-theme="dark"] .oa2-brand-dot{background:#38bdf8;box-shadow:0 0 0 3px rgba(56,189,248,.25)}
.oa2-home[data-oa2-theme="dark"] .oa2-nav-item{color:rgba(255,255,255,.92)!important}
.oa2-home[data-oa2-theme="dark"] .oa2-nav-item:hover{background:rgba(255,255,255,.1)!important;color:#fff!important}
.oa2-home[data-oa2-theme="dark"] .oa2-nav-item.active{background:rgba(59,130,246,.35)!important;color:#fff!important;box-shadow:inset 3px 0 0 #60a5fa!important}
.oa2-home[data-oa2-theme="dark"] .oa2-sidebar-footer{background:linear-gradient(160deg,#bfdbfe 0%,#93c5fd 100%)!important;border-radius:14px;padding:.85rem .65rem .7rem;margin:.35rem .15rem .15rem;color:#0f172a!important}
.oa2-home[data-oa2-theme="dark"] .oa2-footer-copy strong{color:#0f172a!important}
.oa2-home[data-oa2-theme="dark"] .oa2-footer-copy span{color:#334155!important;opacity:1}
.oa2-home[data-oa2-theme="dark"] .oa2-footer-pulse{color:#1e3a8a!important}
.oa2-home[data-oa2-theme="dark"] .oa2-home-subtitle,
.oa2-home[data-oa2-theme="dark"] .oa2-kpi-label,
.oa2-home[data-oa2-theme="dark"] .oa2-muted,
.oa2-home[data-oa2-theme="dark"] .oa2-change-flat,
.oa2-home[data-oa2-theme="dark"] .oa2-empty,
.oa2-home[data-oa2-theme="dark"] .oa2-qa span:nth-child(2),
.oa2-home[data-oa2-theme="dark"] .oa2-qa-chevron,
.oa2-home[data-oa2-theme="dark"] .oa2-table th,
.oa2-home[data-oa2-theme="dark"] .oa2-txn-legend,
.oa2-home[data-oa2-theme="dark"] .oa2-status-legend,
.oa2-home[data-oa2-theme="dark"] .oa2-donut-center span,
.oa2-home[data-oa2-theme="dark"] .oa2-feature p{color:#a8b0bd!important}
.oa2-home[data-oa2-theme="dark"] .oa2-kpi-label{color:#c8ced8!important;font-weight:600}
.oa2-home[data-oa2-theme="dark"] .oa2-qa span:nth-child(2),
.oa2-home[data-oa2-theme="dark"] .oa2-qa-chevron{color:#d5d9e0!important}
.oa2-home[data-oa2-theme="dark"] .oa2-muted{color:#a8b0bd!important}
.oa2-home[data-oa2-theme="dark"] .oa2-home-datetime{background:#262c38!important;border:1px solid #3a4252;border-radius:999px;padding:.4rem .85rem;color:#a8b0bd!important;box-shadow:none}
.oa2-home[data-oa2-theme="dark"] .oa2-card{background:#262c38!important;border-color:#3a4252!important;box-shadow:0 1px 2px rgba(0,0,0,.18),0 8px 20px rgba(0,0,0,.16);color:#e8eaed!important}
.oa2-home[data-oa2-theme="dark"] .oa2-card h3,
.oa2-home[data-oa2-theme="dark"] .oa2-home-title,
.oa2-home[data-oa2-theme="dark"] .oa2-kpi-value,
.oa2-home[data-oa2-theme="dark"] .oa2-donut-total,
.oa2-home[data-oa2-theme="dark"] .oa2-qa,
.oa2-home[data-oa2-theme="dark"] .oa2-list-row,
.oa2-home[data-oa2-theme="dark"] .oa2-table td,
.oa2-home[data-oa2-theme="dark"] .oa2-mono{color:#e8eaed!important}
.oa2-home[data-oa2-theme="dark"] .oa2-feature-blue .oa2-feature-head{background:linear-gradient(135deg,#2a3a4f 0%,#334e7a 100%)!important}
.oa2-home[data-oa2-theme="dark"] .oa2-feature-green .oa2-feature-head{background:linear-gradient(135deg,#2a3f35 0%,#3a5f48 100%)!important}
.oa2-home[data-oa2-theme="dark"] .oa2-feature-purple .oa2-feature-head{background:linear-gradient(135deg,#342a45 0%,#4a3a5f 100%)!important}
.oa2-home[data-oa2-theme="dark"] .oa2-kpi{border-top:3px solid transparent;height:100%;min-height:0;padding:.55rem .75rem}
.oa2-kpi-row{align-items:stretch!important;height:fit-content!important}
.oa2-kpi{height:100%!important;min-height:0}
.oa2-top-left,.oa2-top-right{display:flex;flex-direction:column;gap:.85rem;min-width:0}
.oa2-top-board{align-items:start}
.oa2-home[data-oa2-theme="dark"] .oa2-kpi-blue{background:#2a3a4f!important;border-color:#4a6fa5!important;border-top-color:#6b8fc2}
.oa2-home[data-oa2-theme="dark"] .oa2-kpi-green{background:#2a3f35!important;border-color:#4a8a62!important;border-top-color:#6ba87c}
.oa2-home[data-oa2-theme="dark"] .oa2-kpi-orange{background:#3f3428!important;border-color:#b07a3a!important;border-top-color:#c9964a}
.oa2-home[data-oa2-theme="dark"] .oa2-kpi-teal{background:#342a45!important;border-color:#7a5fa0!important;border-top-color:#9580b5}
.oa2-home[data-oa2-theme="dark"] .oa2-card-head,
.oa2-home[data-oa2-theme="dark"] .oa2-table th,
.oa2-home[data-oa2-theme="dark"] .oa2-table td{border-color:#3a4252!important}
.oa2-home[data-oa2-theme="dark"] .oa2-view-all,
.oa2-home[data-oa2-theme="dark"] .oa2-view-all:visited,
.oa2-home[data-oa2-theme="dark"] .oa2-table a,
.oa2-home[data-oa2-theme="dark"] .oa2-table a:visited,
.oa2-home[data-oa2-theme="dark"] .oa2-view-link,
.oa2-home[data-oa2-theme="dark"] .oa2-view-link:visited{color:#7dd3fc!important;-webkit-text-fill-color:#7dd3fc!important;font-weight:800!important;text-decoration:underline!important;opacity:1!important}
.oa2-home[data-oa2-theme="dark"] .oa2-qa:hover,
.oa2-home[data-oa2-theme="dark"] .oa2-list-row:hover{background:#2e3542!important}
.oa2-home[data-oa2-theme="dark"] .oa2-kpi-icon .icon,
.oa2-home[data-oa2-theme="dark"] .oa2-qa-icon .icon,
.oa2-home[data-oa2-theme="dark"] .oa2-feature-icon .icon,
.oa2-home[data-oa2-theme="dark"] .oa2-kpi-icon svg,
.oa2-home[data-oa2-theme="dark"] .oa2-qa-icon svg,
.oa2-home[data-oa2-theme="dark"] .oa2-feature-icon svg{stroke:currentColor!important;fill:none!important;opacity:1!important;color:inherit!important}
.oa2-home[data-oa2-theme="dark"] .oa2-kpi-blue .oa2-kpi-icon,
.oa2-home[data-oa2-theme="dark"] .oa2-feature-blue .oa2-feature-icon,
.oa2-home[data-oa2-theme="dark"] .oa2-tone-blue{background:#5b8fd4!important;color:#eef0f3!important}
.oa2-home[data-oa2-theme="dark"] .oa2-kpi-green .oa2-kpi-icon,
.oa2-home[data-oa2-theme="dark"] .oa2-feature-green .oa2-feature-icon,
.oa2-home[data-oa2-theme="dark"] .oa2-tone-green{background:#5da87a!important;color:#eef0f3!important}
.oa2-home[data-oa2-theme="dark"] .oa2-kpi-orange .oa2-kpi-icon{background:#c9954a!important;color:#eef0f3!important}
.oa2-home[data-oa2-theme="dark"] .oa2-kpi-teal .oa2-kpi-icon,
.oa2-home[data-oa2-theme="dark"] .oa2-tone-teal,
.oa2-home[data-oa2-theme="dark"] .oa2-feature-purple .oa2-feature-icon,
.oa2-home[data-oa2-theme="dark"] .oa2-tone-purple{background:#9a7bb8!important;color:#eef0f3!important}
.oa2-home[data-oa2-theme="dark"] .oa2-btn{border:0;font-weight:600;color:#1e293b!important}
.oa2-home[data-oa2-theme="dark"] .oa2-btn-blue{background:#c5d8f0!important}
.oa2-home[data-oa2-theme="dark"] .oa2-btn-green{background:#c5e0d0!important}
.oa2-home[data-oa2-theme="dark"] .oa2-btn-purple{background:#ddd0ea!important}
.oa2-home[data-oa2-theme="dark"] .oa2-btn-teal{background:#c5dde0!important}
.oa2-home[data-oa2-theme="dark"] .oa2-badge-blue{background:rgba(91,143,212,.18)!important;color:#a8c4e8!important}
.oa2-home[data-oa2-theme="dark"] .oa2-badge-green,
.oa2-home[data-oa2-theme="dark"] .oa2-badge-success{background:rgba(93,168,122,.16)!important;color:#9bc9ab!important}
.oa2-home[data-oa2-theme="dark"] .oa2-badge-purple{background:rgba(154,123,184,.18)!important;color:#c4b0d8!important}
.oa2-home[data-oa2-theme="dark"] .oa2-badge-teal{background:rgba(90,160,170,.16)!important;color:#9ec8cf!important}
.oa2-home[data-oa2-theme="dark"] .oa2-badge-warn{background:rgba(201,149,74,.16)!important;color:#d4b07a!important}
.oa2-home[data-oa2-theme="dark"] .oa2-badge-muted{background:#3a4252!important;color:#c8ced8!important}
.oa2-home[data-oa2-theme="dark"] .oa2-badge-failed{background:rgba(200,100,100,.16)!important;color:#d4a0a0!important}
.oa2-home[data-oa2-theme="dark"] .oa2-avatar{background:rgba(91,143,212,.22)!important;color:#c5d8f0!important}
.oa2-home[data-oa2-theme="dark"] .oa2-cert-icon{background:#3a4252!important;color:#c8ced8!important}
.oa2-home[data-oa2-theme="dark"] .oa2-monitoring-card{background:linear-gradient(160deg,#2a3a4f 0%,#2a4550 55%,#2f4a52 100%)!important;border-color:#3a4252!important;color:#e8eaed!important}
.oa2-home[data-oa2-theme="dark"] .oa2-monitoring-card h3,
.oa2-home[data-oa2-theme="dark"] .oa2-monitoring-card p{color:rgba(232,234,237,.92)!important}
.oa2-home[data-oa2-theme="dark"] .oa2-monitoring-card .oa2-btn-teal{background:rgba(232,234,237,.92)!important;color:#1e293b!important}
.oa2-home[data-oa2-theme="dark"] .oa2-table-wrap{border-color:#3a4252!important}
.oa2-home[data-oa2-theme="dark"] .oa2-change-up{color:#9bc9ab!important}
.oa2-home[data-oa2-theme="dark"] .oa2-change-down{color:#d4b07a!important}
.oa2-home[data-oa2-theme="dark"] .oa2-dot.success{background:#6ba87c!important}
.oa2-home[data-oa2-theme="dark"] .oa2-dot.pending{background:#c9964a!important}
.oa2-home[data-oa2-theme="dark"] .oa2-dot.failed{background:#c86a6a!important}
.oa2-home[data-oa2-theme="dark"] .oa2-txn-legend,
.oa2-home[data-oa2-theme="dark"] .oa2-txn-legend li{color:#c8ced8!important}
.oa2-home[data-oa2-theme="dark"] .oa2-txn-legend strong{color:#e8eaed!important;font-weight:700}
.oa2-home[data-oa2-theme="dark"] .oa2-txn-legend i{filter:none;box-shadow:none;opacity:.9}
.oa2-home[data-oa2-theme="dark"] .oa2-donut-total{color:#e8eaed!important}
.oa2-home[data-oa2-theme="dark"] .oa2-donut-center span{color:#a8b0bd!important}
.oa2-home[data-oa2-theme="dark"] .oa2-txn-card h3,
.oa2-home[data-oa2-theme="dark"] .oa2-monitoring-card h3,
.oa2-home[data-oa2-theme="dark"] .oa2-quick-actions h3{color:#e8eaed!important}
.oa2-home[data-oa2-theme="dark"] .oa2-mon-icon{background:rgba(232,234,237,.16)!important;color:#e8eaed!important}
.oa2-home[data-oa2-theme="dark"] .oa2-qa-icon svg,
.oa2-home[data-oa2-theme="dark"] .oa2-qa-icon .icon,
.oa2-home[data-oa2-theme="dark"] .oa2-kpi-icon svg,
.oa2-home[data-oa2-theme="dark"] .oa2-kpi-icon .icon,
.oa2-home[data-oa2-theme="dark"] .oa2-feature-icon svg,
.oa2-home[data-oa2-theme="dark"] .oa2-feature-icon .icon,
.oa2-home[data-oa2-theme="dark"] .oa2-mon-icon svg,
.oa2-home[data-oa2-theme="dark"] .oa2-mon-icon .icon{stroke:#eef0f3!important;color:#eef0f3!important;fill:none!important;opacity:.95!important;filter:none}
.oa2-home[data-oa2-theme="dark"] .oa2-qa,
.oa2-home[data-oa2-theme="dark"] .oa2-qa span:nth-child(2),
.oa2-home[data-oa2-theme="dark"] .oa2-qa-chevron,
.oa2-home[data-oa2-theme="dark"] .oa2-kpi-label{color:#d5d9e0!important}
`;
	}

	mount_theme_toggle() {
		this.ensure_theme_styles();
		let $toggle = this.$body.find(".oa2-theme-toggle");
		if (!$toggle.length) {
			const $actions = this.$body.find(".oa2-home-header-actions");
			if ($actions.length) {
				$actions.prepend(`<div class="oa2-theme-toggle" role="group" aria-label="${__("Theme")}"></div>`);
				$toggle = this.$body.find(".oa2-theme-toggle");
			}
		}
		if (!$toggle.length) return;
		$toggle.html(this.theme_toggle_html());
		$toggle.find('input[type="checkbox"]').remove();
	}

	user_menu_html() {
		const uid = frappe.session.user || "";
		const info = (frappe.user_info && frappe.user_info(uid)) || {};
		const fullname = frappe.utils.escape_html(
			frappe.session.user_fullname || info.fullname || uid || __("User")
		);
		const abbr = frappe.utils.escape_html(info.abbr || frappe.get_abbr(fullname) || "U");
		const image = info.image || (frappe.user && frappe.user.image && frappe.user.image()) || "";
		const avatar = image
			? `<img class="oa2-user-avatar-img" src="${frappe.utils.escape_html(image)}" alt="">`
			: `<span class="oa2-user-avatar-abbr">${abbr}</span>`;

		return `
			<button type="button" class="oa2-user-btn" aria-haspopup="menu" aria-expanded="false" title="${fullname}">
				<span class="oa2-user-avatar">${avatar}</span>
			</button>
			<div class="oa2-user-dropdown" role="menu" hidden>
				<div class="oa2-user-dropdown-head">
					<span class="oa2-user-dropdown-avatar">${avatar}</span>
					<div class="oa2-user-dropdown-meta">
						<div class="oa2-user-dropdown-name">${fullname}</div>
						<div class="oa2-user-dropdown-id">${frappe.utils.escape_html(uid)}</div>
					</div>
				</div>
				<button type="button" class="oa2-user-logout" role="menuitem">
					<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10 4H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h4"/><path d="M16 12H8"/><path d="m14 8 4 4-4 4"/></svg>
					<span>${__("Log Out")}</span>
				</button>
			</div>
		`;
	}

	mount_user_menu() {
		let $menu = this.$body.find(".oa2-user-menu");
		if (!$menu.length) {
			const $actions = this.$body.find(".oa2-home-header-actions");
			if ($actions.length) {
				$actions.append(`<div class="oa2-user-menu"></div>`);
				$menu = this.$body.find(".oa2-user-menu");
			}
		}
		if (!$menu.length) return;
		$menu.html(this.user_menu_html());

		this.$body.off("click.oa2user").on("click.oa2user", ".oa2-user-btn", (e) => {
			e.preventDefault();
			e.stopPropagation();
			const $wrap = $(e.currentTarget).closest(".oa2-user-menu");
			const open = !$wrap.hasClass("is-open");
			this.$body.find(".oa2-user-menu").removeClass("is-open");
			this.$body.find(".oa2-user-btn").attr("aria-expanded", "false");
			this.$body.find(".oa2-user-dropdown").prop("hidden", true);
			if (open) {
				$wrap.addClass("is-open");
				$wrap.find(".oa2-user-btn").attr("aria-expanded", "true");
				$wrap.find(".oa2-user-dropdown").prop("hidden", false);
			}
		});

		this.$body.off("click.oa2logout").on("click.oa2logout", ".oa2-user-logout", (e) => {
			e.preventDefault();
			e.stopPropagation();
			this.$body.find(".oa2-user-menu").removeClass("is-open");
			this.$body.find(".oa2-user-dropdown").prop("hidden", true);
			if (frappe.app && typeof frappe.app.logout === "function") {
				frappe.app.logout();
			} else {
				frappe.call({
					method: "logout",
					callback: () => {
						window.location.href = "/login";
					},
				});
			}
		});

		this.$body.off("click.oa2userdd").on("click.oa2userdd", ".oa2-user-dropdown", (e) => {
			e.stopPropagation();
		});

		$(document)
			.off("click.oa2userdoc")
			.on("click.oa2userdoc", () => {
				this.$body.find(".oa2-user-menu").removeClass("is-open");
				this.$body.find(".oa2-user-btn").attr("aria-expanded", "false");
				this.$body.find(".oa2-user-dropdown").prop("hidden", true);
			});
	}

	sidebar_html() {
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
			{ key: "home", label: __("Home"), icon: "home", route: "openas2-dashboard", active: true },
			{ key: "configuration", label: __("Configuration"), icon: "configuration", route: "openas2-configuration" },
			{ key: "partners", label: __("Partners"), icon: "partners", route: "openas2-partners" },
			{ key: "certificates", label: __("Certificates"), icon: "certificates", route: "openas2-certificates" },
			{ key: "monitoring", label: __("Monitoring"), icon: "monitoring", route: "openas2-messages" },
			{ key: "logs", label: __("Logs"), icon: "logs", route: "List/OpenAS2 Message Log" },
			{ key: "settings", label: __("Settings"), icon: "settings", route: "List/OpenAS2 Instance" },
		];
		const nav = items
			.map(
				(item) => `<button type="button" class="oa2-nav-item${item.active ? " active" : ""}" data-route="${item.route}">
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
		this.page.set_secondary_action(__("Refresh"), () => {
			frappe.call({
				method: "openas2_manager.openas2.monitoring.refresh_monitoring",
				freeze: true,
				callback: (r) => {
					const msg = (r && r.message) || {};
					if (msg.ok === false || msg.error) {
						frappe.show_alert({
							message: msg.error || msg.message || __("The OpenAS2 database could not be read."),
							indicator: "red",
						});
					}
					this.load_dashboard();
				},
				error: () => {
					frappe.show_alert({
						message: __("The OpenAS2 database could not be read."),
						indicator: "red",
					});
					this.load_dashboard();
				},
			});
		});

		this.$body.html(`
			<div class="oa2-app-frame">
				${this.sidebar_html()}
				<div class="oa2-main-pane">
					<div class="oa2-home-shell">
						<header class="oa2-home-header">
							<div class="oa2-home-header-copy">
								<h1 class="oa2-home-title">
									${__("Welcome")}, ${frappe.utils.escape_html(frappe.session.user_fullname || frappe.session.user || __("User"))} 👋
								</h1>
								<p class="oa2-home-subtitle">
									${__(
										"Manage your AS2 configuration, partnerships, certificates and monitor EDI transactions – all in one place."
									)}
								</p>
							</div>
							<div class="oa2-home-header-actions">
								<div class="oa2-theme-toggle" role="group" aria-label="${__("Theme")}"></div>
								<div class="oa2-home-datetime" aria-live="polite"></div>
								<div class="oa2-user-menu"></div>
							</div>
						</header>

						<section class="oa2-top-board" aria-label="${__("Overview")}">
							<div class="oa2-top-left">
								<div class="oa2-kpi-row" aria-label="${__("EDI statistics")}"></div>
								<p class="oa2-kpi-notice oa2-muted" hidden></p>
								<div class="oa2-action-cards"></div>
							</div>
							<div class="oa2-top-right">
								<div class="oa2-card oa2-quick-actions">
									<h3>${__("Quick Actions")}</h3>
									<button type="button" class="oa2-qa" data-action="new-partner">
										<span class="oa2-qa-icon oa2-tone-blue">${frappe.utils.icon("add", "sm")}</span>
										<span>${__("Add Partner")}</span>
										<span class="oa2-qa-chevron">›</span>
									</button>
									<button type="button" class="oa2-qa" data-action="new-certificate">
										<span class="oa2-qa-icon oa2-tone-purple">${frappe.utils.icon("upload", "sm")}</span>
										<span>${__("Create Certificate")}</span>
										<span class="oa2-qa-chevron">›</span>
									</button>
									<button type="button" class="oa2-qa" data-action="create-service">
										<span class="oa2-qa-icon oa2-tone-teal">${frappe.utils.icon("setting-gear", "sm")}</span>
										<span>${__("Create Configuration")}</span>
										<span class="oa2-qa-chevron">›</span>
									</button>
								</div>
								<div class="oa2-card oa2-monitoring-card">
									<h3>${__("Monitoring")}</h3>
									<p>${__("Track AS2 message flow, MDN status, and delivery health in real time.")}</p>
									<button type="button" class="oa2-btn oa2-btn-teal" data-route="openas2-messages">
										${__("View Monitoring")}
									</button>
								</div>
							</div>
						</section>

						<section class="oa2-lists-grid">
							<div class="oa2-card oa2-list-card">
								<div class="oa2-card-head">
									<h3>${__("Recent Partners")}</h3>
									<a href="#" class="oa2-view-all" data-route="openas2-partners">${__("View All")} →</a>
								</div>
								<div class="oa2-partner-list"></div>
							</div>
							<div class="oa2-card oa2-list-card">
								<div class="oa2-card-head">
									<h3>${__("Recent Certificates")}</h3>
									<a href="#" class="oa2-view-all" data-route="openas2-certificates">${__("View All")} →</a>
								</div>
								<div class="oa2-cert-list"></div>
							</div>
							<div class="oa2-card oa2-txn-card">
								<div class="oa2-card-head">
									<h3>${__("EDI Transactions")}</h3>
								</div>
								<div class="oa2-donut-wrap">
									<svg class="oa2-donut" viewBox="0 0 120 120" role="img" aria-label="${__("EDI Transactions")}"></svg>
									<div class="oa2-donut-center">
										<strong class="oa2-donut-total">0</strong>
										<span>${__("Transactions")}</span>
									</div>
								</div>
								<div class="oa2-edi-status"></div>
								<div class="oa2-edi-split"></div>
							</div>
						</section>

						<section class="oa2-card oa2-messages-card">
							<div class="oa2-card-head">
								<h3>${__("Recent Messages")}</h3>
								<a href="#" class="oa2-view-all" data-route="openas2-messages">${__("View All")} →</a>
							</div>
							<div class="oa2-table-wrap">
								<table class="oa2-table">
									<thead>
										<tr>
											<th>${__("Message ID")}</th>
											<th>${__("Partner")}</th>
											<th>${__("EDI Type")}</th>
											<th>${__("Direction")}</th>
											<th>${__("Status")}</th>
											<th>${__("Timestamp")}</th>
											<th></th>
										</tr>
									</thead>
									<tbody class="oa2-messages-body"></tbody>
								</table>
							</div>
						</section>
					</div>
				</div>
			</div>
		`);

		this.$datetime = this.$body.find(".oa2-home-datetime");
		this.$kpis = this.$body.find(".oa2-kpi-row");
		this.$kpiNotice = this.$body.find(".oa2-kpi-notice");
		this.$actions = this.$body.find(".oa2-action-cards");
		this.$partners = this.$body.find(".oa2-partner-list");
		this.$certs = this.$body.find(".oa2-cert-list");
		this.$ediStatus = this.$body.find(".oa2-edi-status");
		this.$ediSplit = this.$body.find(".oa2-edi-split");
		this.$txnCard = this.$body.find(".oa2-txn-card");
		this.$donut = this.$body.find(".oa2-donut");
		this.$donutTotal = this.$body.find(".oa2-donut-total");
		this._edi_chart_snapshot = null;
		this.$messages = this.$body.find(".oa2-messages-body");

		this.mount_theme_toggle();
		this.mount_user_menu();
		this.apply_theme(this.get_theme());
		if (window.openas2_manager && typeof openas2_manager.sync_layout === "function") {
			openas2_manager.sync_layout();
		}
		this.$body.off("click.oa2theme").on("click.oa2theme", ".oa2-theme-switch", (e) => {
			e.preventDefault();
			const next = this.get_theme() === "dark" ? "light" : "dark";
			this.apply_theme(next);
		});

		this.start_polling();

		this.$body.on("click", "[data-remote-message]", (e) => {
			e.preventDefault();
			const name = $(e.currentTarget).attr("data-remote-message");
			if (!name) return;
			frappe.route_options = { tab: "messages", oa2_open_message: name };
			frappe.set_route("openas2-messages");
		});

		this.$body.on("click", "[data-route]", (e) => {
			if ($(e.currentTarget).is(".oa2-qa")) return;
			e.preventDefault();
			const route = $(e.currentTarget).attr("data-route");
			if (!route) return;
			frappe.set_route(...route.split("/"));
		});

		this.$body.on("click", ".oa2-kpi[data-txn]", (e) => {
			e.preventDefault();
			const txn = $(e.currentTarget).attr("data-txn");
			if (!txn) return;
			frappe.route_options = {
				tab: "transactions",
				transaction_type: txn,
			};
			frappe.set_route("openas2-messages");
		});

		this.$body.on("keydown", ".oa2-kpi[data-txn]", (e) => {
			if (e.key !== "Enter" && e.key !== " ") return;
			e.preventDefault();
			$(e.currentTarget).trigger("click");
		});

		this.$body.on("click", ".oa2-qa", (e) => {
			e.preventDefault();
			const $btn = $(e.currentTarget);
			const action = $btn.attr("data-action") || "";
			const route = $btn.attr("data-route") || "";
			if (action === "new-partner") {
				frappe.route_options = null;
				frappe.set_route("openas2-add-partner");
			} else if (action === "create-service") {
				const open = () => {
					if (!window.openas2_manager || !openas2_manager.provision) return;
					openas2_manager.provision.prompt_and_create({
						on_success: (result) => {
							if (result && result.result === "Success") {
								frappe.set_route("openas2-configuration");
							}
						},
					});
				};
				if (window.openas2_manager && openas2_manager.provision) open();
				else frappe.require("/assets/openas2_manager/js/openas2_provision.js", open);
			} else if (action === "new-certificate") {
				frappe.route_options = null;
				frappe.set_route("openas2-upload-certificate");
			} else if (route.indexOf("OpenAS2 Instance") !== -1) {
				frappe.route_options = null;
				frappe.set_route("openas2-create-configuration");
			} else if (route === "openas2-messages" || action === "view-logs") {
				frappe.set_route("openas2-logs");
			} else if (route) {
				frappe.set_route(...route.split("/"));
			}
		});
	}

	tick_clock() {
		const formatted = frappe.datetime.str_to_user(frappe.datetime.now_datetime());
		const tz = frappe.boot.time_zone?.user || frappe.boot.sysdefaults?.time_zone || "";
		this.$datetime.text(tz ? `${formatted} (${tz})` : formatted);
	}

	esc(v) {
		return frappe.utils.escape_html(String(v == null ? "" : v));
	}

	badge(text, tone) {
		return `<span class="oa2-badge oa2-badge-${tone}">${this.esc(text)}</span>`;
	}

	change_badge(pct) {
		if (pct == null || pct === "" || !Number.isFinite(Number(pct))) {
			return `<span class="oa2-change oa2-change-flat">—</span>`;
		}
		const n = Number(pct);
		const tone = n > 0 ? "up" : n < 0 ? "down" : "flat";
		const arrow = n > 0 ? "↑ " : n < 0 ? "↓ " : "";
		return `<span class="oa2-change oa2-change-${tone}">${arrow}${Math.abs(n)}%</span>`;
	}

	kpi_icon(code) {
		const map = {
			"204": "mail",
			"990": "tick",
			"210": "stock",
			"214": "file",
		};
		return frappe.utils.icon(map[code] || "file", "sm");
	}

	kpi_count_valid(count) {
		return count !== null && count !== undefined;
	}

	default_kpi_cards() {
		return [
			{ code: "204", label: __("Load Tender"), count: null, last_7: null, change_pct: null, available: false },
			{ code: "990", label: __("Ack"), count: null, last_7: null, change_pct: null, available: false },
			{ code: "210", label: __("Invoice"), count: null, last_7: null, change_pct: null, available: false },
			{ code: "214", label: __("Status"), count: null, last_7: null, change_pct: null, available: false },
		];
	}

	store_kpi_snapshot(kpis) {
		for (const k of kpis || []) {
			const code = String(k?.code || "");
			if (!code || !this.kpi_count_valid(k.count)) {
				continue;
			}
			this._kpi_by_code[code] = Object.assign({}, k);
		}
	}

	kpis_for_display(incoming) {
		const list = incoming || [];
		if (list.length) {
			const hasAnyValid = list.some((k) => this.kpi_count_valid(k.count));
			const hasSnapshot = Object.keys(this._kpi_by_code).length > 0;
			if (hasAnyValid || !hasSnapshot) {
				this._last_kpi_shells = list.map((k) => Object.assign({}, k));
			}
		}
		this.store_kpi_snapshot(list);
		const shells =
			list.length > 0
				? list
				: this._last_kpi_shells && this._last_kpi_shells.length
					? this._last_kpi_shells
					: this.default_kpi_cards();
		return shells.map((k) => {
			const code = String(k?.code || "");
			const held = this._kpi_by_code[code];
			if (!held || this.kpi_count_valid(k.count)) {
				return k;
			}
			return Object.assign({}, k, {
				count: held.count,
				last_7: held.last_7 !== null && held.last_7 !== undefined ? held.last_7 : k.last_7,
				change_pct:
					held.change_pct !== null && held.change_pct !== undefined ? held.change_pct : k.change_pct,
				available: held.available !== false,
				note: k.note || held.note || "",
			});
		});
	}

	set_kpi_notice(displayKpis, options) {
		const opts = options || {};
		const kpis = displayKpis || [];
		const anyVisible = kpis.some((k) => this.kpi_count_valid(k.count));
		let text = "";
		if (opts.failed && anyVisible) {
			text = __("Could not refresh EDI totals. Showing last received counts.");
		} else if (opts.failed && !anyVisible) {
			text = __("The OpenAS2 database could not be read.");
		} else if (opts.rawMissing && anyVisible) {
			text = __("Refreshing EDI totals in the background. Showing last received counts.");
		}
		if (!this.$kpiNotice || !this.$kpiNotice.length) {
			return;
		}
		if (text) {
			this.$kpiNotice.text(text).prop("hidden", false);
		} else {
			this.$kpiNotice.text("").prop("hidden", true);
		}
	}

	ingest_edi_kpi_totals(payload) {
		const data = payload || {};
		if (data.edi_counts_available !== true) {
			return false;
		}
		const byType = data.edi_status_by_type || {};
		const labels = {
			"204": __("Load Tender"),
			"990": __("Ack"),
			"210": __("Invoice"),
			"214": __("Status"),
		};
		let updated = false;
		for (const code of ["204", "990", "210", "214"]) {
			const row = byType[code];
			if (!row || !this.kpi_count_valid(row.total)) {
				continue;
			}
			const count = Number(row.total);
			if (!Number.isFinite(count)) {
				continue;
			}
			const prev = this._kpi_by_code[code] || {};
			this._kpi_by_code[code] = Object.assign({}, prev, {
				code,
				label: prev.label || labels[code],
				count,
				available: true,
			});
			updated = true;
		}
		return updated;
	}

	refresh_kpi_card_row(options) {
		const opts = options || {};
		const displayKpis = this.kpis_for_display(this._last_kpi_shells || []);
		this.render_kpis(displayKpis);
		if (opts.notice) {
			this.set_kpi_notice(displayKpis, opts.notice);
		}
		return displayKpis;
	}

	render_kpis(kpis) {
		const tones = ["blue", "green", "orange", "teal"];
		this.$kpis.html(
			(kpis || [])
				.map((k, i) => {
					const tone = tones[i % tones.length];
					const code = k.code || "";
					const countMissing = !this.kpi_count_valid(k.count);
					const value = countMissing ? this.esc(__("Unavailable")) : this.esc(k.count);
					const last7 = k.last_7 == null ? "—" : k.last_7;
					const meta = countMissing
						? this.change_badge(null)
						: `${this.change_badge(k.change_pct)}<span class="oa2-muted">${this.esc(
								last7
						  )} ${__("in the last 7 days")}</span>`;
					const title = countMissing
						? this.esc(k.note || "")
						: `${__("View")} ${this.esc(code)} ${__("in Monitoring")}`;
					return `<article class="oa2-card oa2-kpi oa2-kpi-${tone}" data-txn="${this.esc(
						code
					)}" role="button" tabindex="0" title="${title}">
						<div class="oa2-kpi-icon">${this.kpi_icon(code)}</div>
						<div class="oa2-kpi-body">
							<div class="oa2-kpi-label">${this.esc(code)} – ${this.esc(k.label)}</div>
							<div class="oa2-kpi-value">${value}</div>
							<div class="oa2-kpi-meta">
								${meta}
							</div>
						</div>
					</article>`;
				})
				.join("")
		);
	}

	render_action_cards(s) {
		const cfg = s.config || {};
		const pstats = s.partner_stats || {};
		const cstats = s.certificate_stats || {};
		const typeBadge = (cfg.types || []).slice(0, 2).map((t) => this.badge(t, "blue")).join(" ");
		this.$actions.html(`
			<article class="oa2-card oa2-feature oa2-feature-blue">
				<div class="oa2-feature-head">
					<div class="oa2-feature-badges">
						${this.badge(cfg.status || "—", "blue")}
						${typeBadge || this.badge(__("Instances"), "muted")}
					</div>
				</div>
				<div class="oa2-feature-body">
					<div class="oa2-feature-title-row">
						<div class="oa2-feature-icon">${frappe.utils.icon("setting-gear", "md")}</div>
						<h3>${__("Configuration")}</h3>
					</div>
					<p>${__("Review OpenAS2 instance settings, listeners, and published AS2 endpoints.")}</p>
					<button type="button" class="oa2-btn oa2-btn-blue" data-route="openas2-configuration">
						${__("Manage Configuration")}
					</button>
				</div>
			</article>
			<article class="oa2-card oa2-feature oa2-feature-green">
				<div class="oa2-feature-head">
					<div class="oa2-feature-badges">
						${this.badge(`${pstats.total || 0} ${__("Partners")}`, "green")}
						${this.badge(`${pstats.active || 0} ${__("Active")}`, "success")}
					</div>
				</div>
				<div class="oa2-feature-body">
					<div class="oa2-feature-title-row">
						<div class="oa2-feature-icon">${frappe.utils.icon("users", "md")}</div>
						<h3>${__("Partners / Partnerships")}</h3>
					</div>
					<p>${__("Manage AS2 partners and partnerships used for secure B2B exchange.")}</p>
					<button type="button" class="oa2-btn oa2-btn-green" data-route="openas2-partners">
						${__("Manage Partners")}
					</button>
				</div>
			</article>
			<article class="oa2-card oa2-feature oa2-feature-purple">
				<div class="oa2-feature-head">
					<div class="oa2-feature-badges">
						${this.badge(`${cstats.active || 0} ${__("Active")}`, "purple")}
						${this.badge(__("Signing"), "muted")}
					</div>
				</div>
				<div class="oa2-feature-body">
					<div class="oa2-feature-title-row">
						<div class="oa2-feature-icon">${frappe.utils.icon("lock", "md")}</div>
						<h3>${__("Certificates")}</h3>
					</div>
					<p>${__("Create, import, and track signing and encryption certificates.")}</p>
					<button type="button" class="oa2-btn oa2-btn-purple" data-route="openas2-certificates">
						${__("Manage Certificates")}
					</button>
				</div>
			</article>
		`);
	}

	render_partners(rows) {
		if (!rows || !rows.length) {
			this.$partners.html(`<p class="oa2-empty">${__("No partners yet.")}</p>`);
			return;
		}
		this.$partners.html(
			rows
				.map((p) => {
					const statusTone = (p.status || "").toLowerCase() === "active" ? "success" : "warn";
					const typeTone = "blue";
					return `<a class="oa2-list-row" href="/app/as2-partner/${encodeURIComponent(p.name)}">
						<span class="oa2-avatar">${this.esc(p.initials || "?")}</span>
						<span class="oa2-list-main">
							<strong>${this.esc(p.partner_name || p.name)}</strong>
							<span class="oa2-muted">${this.esc(p.as2_url || p.as2_id || "")}</span>
						</span>
						<span class="oa2-list-tags">
							${this.badge(p.partner_type || "—", typeTone)}
							${this.badge(p.status || "—", statusTone)}
						</span>
					</a>`;
				})
				.join("")
		);
	}

	render_certs(rows) {
		if (!rows || !rows.length) {
			this.$certs.html(`<p class="oa2-empty">${__("No certificates yet.")}</p>`);
			return;
		}
		this.$certs.html(
			rows
				.map((c) => {
					const statusTone = (c.status || "").toLowerCase() === "active" ? "success" : "muted";
					const until = c.valid_until
						? frappe.datetime.str_to_user(c.valid_until)
						: __("No expiry");
					return `<a class="oa2-list-row" href="/app/as2-certificate/${encodeURIComponent(c.name)}">
						<span class="oa2-cert-ico">${frappe.utils.icon("file", "sm")}</span>
						<span class="oa2-list-main">
							<strong>${this.esc(c.certificate_name || c.name)}</strong>
							<span class="oa2-muted">${this.esc(c.certificate_type || "")} · ${this.esc(until)}</span>
						</span>
						${this.badge(c.status || "—", statusTone)}
					</a>`;
				})
				.join("")
		);
	}

	edi_row(code, label, row) {
		const stats = row || {};
		const success = Number(stats.success) || 0;
		const progress = Number(stats.in_progress) || 0;
		const failure = Number(stats.failure) || 0;
		const total = Number(stats.total) || success + progress + failure;
		const parts = [
			["success", success],
			["progress", progress],
			["failure", failure],
		].filter(([, n]) => n > 0);
		const bar = parts.length
			? parts
					.map(([tone, n]) => {
						return `<span class="oa2-edi-seg oa2-edi-${tone}" style="flex:${n} 1 0">${n}</span>`;
					})
					.join("")
			: `<span class="oa2-edi-seg oa2-edi-empty"></span>`;
		const breakdown = `<div class="oa2-edi-breakdown" aria-label="${__("Status counts")}">
			<span class="oa2-edi-stat oa2-edi-success">${__("Success")} ${success}</span>
			<span class="oa2-edi-stat oa2-edi-progress">${__("In Progress")} ${progress}</span>
			<span class="oa2-edi-stat oa2-edi-failure">${__("Failure")} ${failure}</span>
		</div>`;
		return `<div class="oa2-edi-row">
			<span class="oa2-edi-code" title="${this.esc(label)}">${this.esc(code)}</span>
			<div class="oa2-edi-meter">
				<strong class="oa2-edi-total">${total}</strong>
				<div class="oa2-edi-bar" title="${__("Success")} ${success}, ${__("In Progress")} ${progress}, ${__(
			"Failure"
		)} ${failure}">${bar}</div>
				${breakdown}
			</div>
		</div>`;
	}

	set_edi_chart_banner(text) {
		if (!this.$txnCard || !this.$txnCard.length) return;
		let $banner = this.$txnCard.find(".oa2-edi-chart-banner");
		if (!$banner.length) {
			$banner = $('<p class="oa2-edi-chart-banner oa2-muted" hidden></p>');
			this.$ediStatus.after($banner);
		}
		const msg = (text || "").trim();
		if (msg) {
			$banner.text(msg).prop("hidden", false);
		} else {
			$banner.text("").prop("hidden", true);
		}
	}

	render_edi_chart_loading(refreshing, data) {
		const note = refreshing
			? __("Loading EDI transaction totals…")
			: (data && (data.edi_counts_limitation || data.error)) ||
				__("EDI status breakdown is not available yet.");
		this.$donutTotal.text("…");
		this.$donut.html(
			`<circle class="oa2-donut-track" cx="60" cy="60" r="42" fill="none" stroke-width="16"/>`
		);
		this.$ediStatus.html(
			`<p class="oa2-edi-chart-note oa2-muted oa2-edi-chart-loading">${this.esc(note)}</p>`
		);
		this.set_edi_chart_banner("");
		if (!this._edi_chart_snapshot) {
			this.$ediSplit.html("");
		}
	}

	render_edi_chart_data(data) {
		const byType = data.edi_status_by_type || {};
		const pick = (code) => byType[code] || { total: 0, success: 0, in_progress: 0, failure: 0 };
		const success = Number(data.success) || 0;
		const progress = Number(data.in_progress) || 0;
		const failure = Number(data.failure) || 0;
		const total = Number(data.transactions_total) || 0;
		this.$donutTotal.text(String(total));

		const segments = [
			["#16a34a", success],
			["#eab308", progress],
			["#dc2626", failure],
		].filter(([, count]) => count > 0);
		const r = 42;
		const c = 2 * Math.PI * r;
		const gap = segments.length > 1 ? 3 : 0;
		let offset = 0;
		let arcs = `<circle class="oa2-donut-track" cx="60" cy="60" r="${r}" fill="none" stroke-width="16"/>`;
		if (total > 0) {
			arcs += segments
				.map(([color, count]) => {
					const len = Math.max((count / total) * c - gap, 0.5);
					const el = `<circle cx="60" cy="60" r="${r}" fill="none"
						stroke="${color}" stroke-width="16"
						stroke-dasharray="${len} ${c - len}" stroke-dashoffset="${-offset}"
						transform="rotate(-90 60 60)"/>`;
					offset += (count / total) * c;
					return el;
				})
				.join("");
		}
		this.$donut.html(arcs);

		this.$ediStatus.html(
			`<ul class="oa2-txn-legend" aria-label="${__("Transaction status")}">${[
				["success", __("Success"), success],
				["progress", __("In Progress"), progress],
				["failure", __("Failure"), failure],
			]
				.map(
					([tone, label, count]) =>
						`<li><i class="oa2-edi-dot oa2-edi-${tone}"></i><span>${this.esc(
							label
						)} (${count})</span></li>`
				)
				.join("")}</ul>`
		);
		this.$ediSplit.html(
			`<div class="oa2-edi-col">${this.edi_row("204", __("Load Tender"), pick("204"))}${this.edi_row(
				"214",
				__("Status"),
				pick("214")
			)}</div><div class="oa2-edi-col">${this.edi_row("990", __("Ack"), pick("990"))}${this.edi_row(
				"210",
				__("Invoice"),
				pick("210")
			)}</div>`
		);
	}

	apply_edi_chart_from_summary(summary) {
		const s = summary || {};
		const chartReady =
			s.edi_counts_available === true || s.edi_chart_ready === true;
		if (!chartReady || !s.edi_status_by_type) {
			return;
		}
		this._edi_skip_chart_fetch = true;
		this._edi_chart_last_fetch = Date.now();
		this.apply_edi_transactions({
			ok: true,
			edi_counts_available: true,
			edi_refresh_in_progress: s.edi_refresh_in_progress === true,
			edi_status_by_type: s.edi_status_by_type,
			transactions_total: s.transactions_total,
			success: s.success,
			in_progress: s.in_progress,
			failure: s.failure,
		});
	}

	apply_edi_transactions(payload) {
		const data = payload || {};
		const available = data.edi_counts_available === true;
		const refreshing = data.edi_refresh_in_progress === true;

		if (available) {
			this._edi_chart_snapshot = data;
			if (this.ingest_edi_kpi_totals(data)) {
				this.refresh_kpi_card_row();
			}
			this.render_edi_chart_data(data);
			if (refreshing) {
				this.set_edi_chart_banner(__("Refreshing totals in the background…"));
			} else {
				this.set_edi_chart_banner("");
			}
			return;
		}

		const snap = this._edi_chart_snapshot;
		if (snap && snap.edi_counts_available === true) {
			this.render_edi_chart_data(snap);
			if (refreshing) {
				this.set_edi_chart_banner(__("Refreshing totals in the background…"));
			} else {
				const msg = data.edi_counts_limitation || data.error || "";
				this.set_edi_chart_banner(msg);
			}
			return;
		}

		this.render_edi_chart_loading(refreshing, data);
	}

	status_tone(status) {
		const s = (status || "").toLowerCase();
		if (s === "success") return "success";
		if (s === "failed") return "failed";
		return "pending";
	}

	render_messages(rows, errorText) {
		if (errorText) {
			this.$messages.html(
				`<tr><td colspan="7" class="oa2-empty">${this.esc(errorText)}</td></tr>`
			);
			return;
		}
		if (!rows || !rows.length) {
			this.$messages.html(
				`<tr><td colspan="7" class="oa2-empty">${__("No recent messages.")}</td></tr>`
			);
			return;
		}
		this.$messages.html(
			rows
				.map((m) => {
					const dirTone = (m.direction || "").toLowerCase() === "inbound" ? "blue" : "teal";
					const st = this.status_tone(m.status);
					const ts = m.timestamp ? frappe.datetime.str_to_user(m.timestamp) : "—";
					const messageName = m.name || "";
					const view = String(messageName).indexOf("remote:") === 0
						? `<a href="#" class="oa2-view-link" data-remote-message="${this.esc(
								messageName
						  )}" style="color:#7dd3fc;font-weight:800;text-decoration:underline">${__(
								"View"
						  )}</a>`
						: `<a class="oa2-view-link" href="/app/openas2-message-log/${encodeURIComponent(
								messageName
						  )}" style="color:#7dd3fc;font-weight:800;text-decoration:underline">${__(
								"View"
						  )}</a>`;
					return `<tr>
						<td class="oa2-mono">${this.esc(m.message_id_display || m.name)}</td>
						<td>
							<span class="oa2-partner-cell">
								<span class="oa2-avatar sm">${this.esc(m.initials || "?")}</span>
								${this.esc(m.partner_label || "—")}
							</span>
						</td>
						<td>${this.esc(m.transaction_type_label || __("Unknown"))}</td>
						<td>${this.badge(m.direction || "—", dirTone)}</td>
						<td><span class="oa2-status"><i class="oa2-dot ${st}"></i>${this.esc(
							m.status || "—"
						)}</span></td>
						<td class="oa2-muted">${this.esc(ts)}</td>
						<td>${view}</td>
					</tr>`;
				})
				.join("")
		);
	}

	stop_polling() {
		if (this._clock) {
			clearInterval(this._clock);
			this._clock = null;
		}
		if (this._txn) {
			clearInterval(this._txn);
			this._txn = null;
		}
		if (this._kpis_retry_timer) {
			clearTimeout(this._kpis_retry_timer);
			this._kpis_retry_timer = null;
		}
		if (this._edi_retry_timer) {
			clearTimeout(this._edi_retry_timer);
			this._edi_retry_timer = null;
		}
	}

	start_polling() {
		this.stop_polling();
		this.tick_clock();
		this._clock = setInterval(() => this.tick_clock(), 30000);
		this._txn = setInterval(() => {
			this.load_kpis();
			this.load_edi_transactions();
		}, 15000);
	}

	load_dashboard() {
		this.load_kpis();
		this.load_edi_transactions();
		this.load_activity();
	}

	load_edi_transactions() {
		if (
			this._edi_skip_chart_fetch &&
			this._edi_chart_snapshot &&
			Date.now() - (this._edi_chart_last_fetch || 0) < 12000
		) {
			this._edi_skip_chart_fetch = false;
			return;
		}
		this._edi_skip_chart_fetch = false;
		if (!this._edi_chart_snapshot) {
			this.render_edi_chart_loading(true, {});
		}
		const requestId = (this._edi_request || 0) + 1;
		this._edi_request = requestId;
		frappe.call({
			method: "openas2_manager.openas2.monitoring.get_edi_transactions_counts",
			callback: (r) => {
				if (this._edi_request !== requestId) return;
				const payload = r.message || {};
				this._edi_chart_last_fetch = Date.now();
				this.apply_edi_transactions(payload);
				this.maybe_retry_edi_chart(payload);
			},
		});
	}

	maybe_retry_edi_chart(payload) {
		if (payload?.edi_counts_available === true) {
			this._edi_retries = 0;
			return;
		}
		if (payload?.edi_refresh_in_progress !== true) {
			return;
		}
		if ((this._edi_retries || 0) >= 24) {
			return;
		}
		this._edi_retries = (this._edi_retries || 0) + 1;
		clearTimeout(this._edi_retry_timer);
		this._edi_retry_timer = setTimeout(() => this.load_edi_transactions(), 15000);
	}

	load_kpis() {
		const requestId = (this._kpis_request || 0) + 1;
		this._kpis_request = requestId;
		frappe.call({
			method: "openas2_manager.openas2.monitoring.get_dashboard_summary",
			args: { kpis_only: 1 },
			callback: (r) => {
				if (this._kpis_request !== requestId) return;
				const s = r.message || {};
				const displayKpis = this.kpis_for_display(s.kpis);
				const rawMissing = (s.kpis || []).some((k) => !this.kpi_count_valid(k.count));
				this.render_kpis(displayKpis);
				this.set_kpi_notice(displayKpis, { failed: false, rawMissing });
				this.apply_edi_chart_from_summary(s);
				this.render_action_cards(s);
				this.render_partners(s.recent_partners);
				this.render_certs(s.recent_certificates);
				this.maybe_retry_kpis(s, displayKpis);
			},
			error: (err) => {
				if (this._kpis_request !== requestId) return;
				if (typeof console !== "undefined" && console.error) {
					console.error("OpenAS2 dashboard KPI refresh failed", err);
				}
				const displayKpis = this.kpis_for_display([]);
				this.render_kpis(displayKpis);
				this.set_kpi_notice(displayKpis, { failed: true });
				this.maybe_retry_kpis({ kpis: [] }, displayKpis);
			},
		});
	}

	maybe_retry_kpis(summary, displayKpis) {
		const kpis = displayKpis || summary?.kpis || [];
		const kpiPending = kpis.some((k) => !this.kpi_count_valid(k.count));
		if (!kpiPending) {
			this._kpis_retries = 0;
			return;
		}
		if ((this._kpis_retries || 0) >= 12) {
			return;
		}
		this._kpis_retries = (this._kpis_retries || 0) + 1;
		clearTimeout(this._kpis_retry_timer);
		this._kpis_retry_timer = setTimeout(() => this.load_kpis(), 5000);
	}

	load_activity() {
		const requestId = (this._activity_request || 0) + 1;
		this._activity_request = requestId;
		frappe.call({
			method: "openas2_manager.openas2.monitoring.get_dashboard_summary",
			args: { activity_only: 1 },
			callback: (r) => {
				if (this._activity_request !== requestId) return;
				const s = r.message || {};
				this.render_messages(s.recent_messages, s.messages_error);
			},
			error: () => {
				if (this._activity_request !== requestId) return;
				this.render_messages([], __("The OpenAS2 database could not be read."));
			},
		});
	}
};
