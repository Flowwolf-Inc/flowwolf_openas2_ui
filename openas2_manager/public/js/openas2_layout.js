// Copyright (c) 2026, Lakshana and contributors
// For license information, please see license.txt

/**
 * Shared OpenAS2 desk layout — theme toggle, full-bleed width/height, no bottom gap.
 * Loaded via app_include_js. Only activates on OpenAS2 routes; other Desk pages unchanged.
 */
(function () {
	"use strict";

	const THEME_KEY = "oa2-dashboard-theme";
	const STYLE_ID = "oa2-shared-layout-css";
	const COPILOT_ICON =
		'<svg class="oa2-ai-spark" viewBox="0 0 24 24" width="14" height="14" aria-hidden="true" focusable="false"><path fill="currentColor" d="M12 2.4l1.05 5.5 5.5 1.05-5.5 1.05L12 15.5l-1.05-5.5-5.5-1.05 5.5-1.05L12 2.4z"/><path fill="currentColor" d="M18.1 14.1l.48 1.9 1.9.48-1.9.48-.48 1.9-.48-1.9-1.9-.48 1.9-.48.48-1.9z"/></svg>';

	function copilot_button_html() {
		return (
			'<button type="button" class="oa2-ai-open" aria-label="OpenAS2 Copilot">' +
			COPILOT_ICON +
			"<span>Copilot</span></button>"
		);
	}

	function refresh_copilot_button(root) {
		const btn = root && root.querySelector(":scope > .oa2-ai-open, .oa2-ai-open");
		if (!btn || btn.querySelector(".oa2-ai-spark")) return;
		btn.innerHTML = COPILOT_ICON + "<span>Copilot</span>";
		btn.setAttribute("aria-label", "OpenAS2 Copilot");
		btn.removeAttribute("style");
	}

	function ensure_copilot_button_css() {
		if (document.getElementById("oa2-copilot-btn-css")) return;
		const el = document.createElement("style");
		el.id = "oa2-copilot-btn-css";
		el.textContent = [
			"#oa2-shared-header-controls .oa2-ai-open,",
			".oa2-home-header-actions .oa2-ai-open,",
			".oa2-monitor-header-actions .oa2-ai-open,",
			".oa2-config-header-actions .oa2-ai-open{",
			"appearance:none !important;",
			"display:inline-flex !important;",
			"align-items:center !important;",
			"gap:0.35rem !important;",
			"border:1px solid #e8eef5 !important;",
			"background:#fff !important;",
			"color:#0f2744 !important;",
			"border-radius:999px !important;",
			"padding:0.32rem 0.72rem 0.32rem 0.48rem !important;",
			"font-family:Inter,Segoe UI,system-ui,sans-serif !important;",
			"font-size:0.75rem !important;",
			"font-weight:600 !important;",
			"line-height:1.2 !important;",
			"box-shadow:0 1px 2px rgba(15,23,42,.04) !important;",
			"cursor:pointer !important;",
			"}",
			"#oa2-shared-header-controls .oa2-ai-open .oa2-ai-spark,",
			".oa2-home-header-actions .oa2-ai-open .oa2-ai-spark{width:14px;height:14px;color:#1d4ed8 !important;}",
			"body[data-oa2-theme='dark'] #oa2-shared-header-controls .oa2-ai-open,",
			"body[data-oa2-theme='dark'] .oa2-home-header-actions .oa2-ai-open,",
			"body[data-oa2-theme='dark'] .oa2-monitor-header-actions .oa2-ai-open,",
			"body[data-oa2-theme='dark'] .oa2-config-header-actions .oa2-ai-open{",
			"background:#262c38 !important;",
			"border-color:#3a4252 !important;",
			"color:#e8eaed !important;",
			"box-shadow:none !important;",
			"}",
			"body[data-oa2-theme='dark'] .oa2-ai-open .oa2-ai-spark{color:#93c5fd !important;}",
		].join("");
		document.head.appendChild(el);
	}

	const OA2_PAGES = new Set([
		"openas2-dashboard",
		"openas2-configuration",
		"openas2-messages",
		"openas2-errors",
		"openas2-partnerships",
		"openas2-partners",
		"openas2-add-partner",
		"openas2-upload-certificate",
		"openas2-create-configuration",
		"openas2-create-communication",
		"openas2-certificates",
		"openas2-logs",
		"openas2-settings",
	]);

	const OA2_DOCTYPES = new Set([
		"AS2 Partner",
		"AS2 Certificate",
		"OpenAS2 Instance",
		"OpenAS2 Partnership",
		"OpenAS2 Message Log",
		"OpenAS2 Configuration Change",
		"OpenAS2 Restart Log",
		"OpenAS2 Runtime Log",
		"OpenAS2 Provisioning Log",
	]);

	function get_route() {
		try {
			return (frappe.get_route && frappe.get_route()) || [];
		} catch (e) {
			return [];
		}
	}

	function is_oa2_doctype(name) {
		if (!name) return false;
		if (OA2_DOCTYPES.has(name)) return true;
		const n = String(name).toLowerCase();
		return n.indexOf("openas2") === 0 || n.indexOf("as2 ") === 0 || n.indexOf("as2-") === 0;
	}

	function is_oa2_context() {
		const route = get_route();
		const r0 = String(route[0] || "");
		const r1 = String(route[1] || "");
		const r0l = r0.toLowerCase();

		if (OA2_PAGES.has(r0l) || OA2_PAGES.has(r0)) return true;
		if (["List", "Form", "Tree", "Report", "list", "form"].indexOf(r0) !== -1 && is_oa2_doctype(r1)) {
			return true;
		}

		const path = (window.location.pathname || "").toLowerCase();
		if (path.indexOf("/app/openas2-") !== -1 || path.indexOf("/app/as2-") !== -1) return true;
		if (path.indexOf("/app/list/openas2") !== -1 || path.indexOf("/app/list/as2") !== -1) return true;
		if (path.indexOf("/app/form/openas2") !== -1 || path.indexOf("/app/form/as2") !== -1) return true;

		if (document.querySelector(".oa2-dashboard-wrapper, .oa2-config-page-wrapper, .oa2-monitor-page-wrapper, .oa2-app-frame")) {
			return true;
		}
		return false;
	}

	function get_theme() {
		try {
			return localStorage.getItem(THEME_KEY) === "dark" ? "dark" : "light";
		} catch (e) {
			return "light";
		}
	}

	function theme_toggle_html() {
		const sun =
			'<svg class="oa2-theme-icon oa2-theme-icon-sun" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2.2M12 19.8V22M4.9 4.9l1.6 1.6M17.5 17.5l1.6 1.6M2 12h2.2M19.8 12H22M4.9 19.1l1.6-1.6M17.5 6.5l1.6-1.6"/></svg>';
		const moon =
			'<svg class="oa2-theme-icon oa2-theme-icon-moon" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20.5 14.2A7.8 7.8 0 0 1 9.8 3.5 7.9 7.9 0 1 0 20.5 14.2z"/></svg>';
		return (
			'<button type="button" class="oa2-theme-switch" role="switch" aria-checked="false" aria-label="Toggle light / dark theme" title="Toggle light / dark theme">' +
			'<span class="oa2-theme-track" aria-hidden="true">' +
			sun +
			moon +
			'<span class="oa2-theme-thumb"></span>' +
			"</span></button>"
		);
	}

	function ensure_layout_css() {
		let style = document.getElementById(STYLE_ID);
		if (!style) {
			style = document.createElement("style");
			style.id = STYLE_ID;
			document.head.appendChild(style);
		}
		/* Critical full-bleed + bottom-gap kill — mirrors Home, scoped to OA2 body flags only */
		style.textContent = `
body.oa2-has-sidebar,
body.oa2-has-sidebar .main-section,
body.oa2-has-sidebar #body {
	height: 100vh !important;
	max-height: 100vh !important;
	height: 100dvh !important;
	max-height: 100dvh !important;
	overflow: hidden !important;
	margin: 0 !important;
	padding: 0 !important;
}
body.oa2-has-sidebar .container,
body.oa2-has-sidebar .container.page-container,
body.oa2-has-sidebar .page-container,
body.oa2-has-sidebar .layout-main,
body.oa2-has-sidebar .layout-main-section-wrapper,
body.oa2-has-sidebar .layout-main-section,
body.oa2-has-sidebar .page-body,
body.oa2-has-sidebar .page-content,
body.oa2-has-sidebar .page-content-wrapper {
	width: 100% !important;
	max-width: none !important;
	margin-left: 0 !important;
	margin-right: 0 !important;
	padding-left: 0 !important;
	padding-right: 0 !important;
}
body.oa2-has-sidebar .layout-side-section,
body.oa2-has-sidebar .body-sidebar-container,
body.oa2-has-sidebar .body-sidebar,
body.oa2-has-sidebar .desk-sidebar {
	display: none !important;
	width: 0 !important;
	max-width: 0 !important;
	flex: 0 0 0 !important;
}
.oa2-dashboard-wrapper.page-container,
.oa2-config-page-wrapper.page-container,
.oa2-monitor-page-wrapper.page-container,
.oa2-dashboard-wrapper .layout-main-section-wrapper,
.oa2-config-page-wrapper .layout-main-section-wrapper,
.oa2-monitor-page-wrapper .layout-main-section-wrapper,
.oa2-dashboard-wrapper .layout-main-section,
.oa2-config-page-wrapper .layout-main-section,
.oa2-monitor-page-wrapper .layout-main-section,
.oa2-dashboard-wrapper .page-body,
.oa2-config-page-wrapper .page-body,
.oa2-monitor-page-wrapper .page-body,
body.oa2-has-sidebar .oa2-home,
body.oa2-has-sidebar .oa2-config-list-page,
body.oa2-has-sidebar .oa2-monitor-page {
	height: 100vh !important;
	min-height: 100vh !important;
	max-height: 100vh !important;
	height: 100dvh !important;
	min-height: 100dvh !important;
	max-height: 100dvh !important;
	width: 100% !important;
	max-width: none !important;
	overflow: hidden !important;
	margin: 0 !important;
	padding: 0 !important;
}
.oa2-home-shell,
.oa2-config-shell,
.oa2-monitor-shell {
	max-width: none !important;
	width: 100% !important;
	margin-left: 0 !important;
	margin-right: 0 !important;
}
.oa2-dashboard-wrapper .page-head,
.oa2-config-page-wrapper .page-head,
.oa2-monitor-page-wrapper .page-head {
	display: none !important;
}
/* One shared header cluster for every OA2 page (same Home classes) */
#oa2-shared-header-controls {
	display: flex;
	flex-direction: row;
	align-items: center;
	gap: 0.85rem;
	flex-shrink: 0;
}
body.oa2-has-sidebar .oa2-home-header-actions > .oa2-theme-toggle,
body.oa2-has-sidebar .oa2-home-header-actions > .oa2-home-datetime,
body.oa2-has-sidebar .oa2-home-header-actions > .oa2-user-menu,
body.oa2-has-sidebar .oa2-monitor-header-actions > .oa2-theme-toggle,
body.oa2-has-sidebar .oa2-monitor-datetime,
body.oa2-has-sidebar #oa2-shared-list-bar {
	display: none !important;
}
body.oa2-has-sidebar .oa2-home-header,
body.oa2-has-sidebar .oa2-monitor-header {
	align-items: flex-start;
}
body.oa2-has-sidebar .oa2-home-header-actions,
body.oa2-has-sidebar .oa2-config-header-actions,
body.oa2-has-sidebar .oa2-monitor-header-actions {
	display: flex;
	flex-direction: row;
	align-items: center;
	gap: 0.85rem;
}
#oa2-shared-header-controls .oa2-home-datetime {
	flex-shrink: 0;
	color: #64748b;
	font-size: 0.72rem;
	font-weight: 500;
	line-height: 1.2;
	white-space: nowrap;
	display: inline-flex;
	align-items: center;
	background: #fff;
	border: 1px solid #e8eef5;
	border-radius: 999px;
	padding: 0.35rem 0.7rem;
	box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
}
#oa2-shared-header-controls .oa2-user-menu { position: relative; flex-shrink: 0; }
#oa2-shared-header-controls .oa2-user-btn {
	appearance: none; border: 1px solid #e2e8f0; background: #fff; padding: 2px; margin: 0;
	border-radius: 999px; cursor: pointer; display: inline-flex; align-items: center; justify-content: center;
	line-height: 0; box-shadow: 0 1px 2px rgba(15, 23, 42, 0.06);
}
#oa2-shared-header-controls .oa2-user-avatar {
	width: 30px; height: 30px; border-radius: 999px; overflow: hidden; display: grid; place-items: center;
	background: linear-gradient(135deg, #dbeafe 0%, #bfdbfe 100%); color: #1e40af;
	font-size: 0.68rem; font-weight: 700;
}
#oa2-shared-header-controls .oa2-user-avatar-img { width: 100%; height: 100%; object-fit: cover; display: block; }
#oa2-shared-header-controls .oa2-user-dropdown {
	position: absolute; top: calc(100% + 8px); right: 0; min-width: 220px; background: #fff;
	border: 1px solid #e8eef5; border-radius: 12px;
	box-shadow: 0 10px 30px rgba(15, 23, 42, 0.12), 0 2px 6px rgba(15, 23, 42, 0.06);
	padding: 0.45rem; z-index: 40;
}
#oa2-shared-header-controls .oa2-user-dropdown[hidden] { display: none !important; }
#oa2-shared-header-controls .oa2-user-dropdown-head {
	display: flex; align-items: center; gap: 0.65rem; padding: 0.55rem 0.55rem 0.65rem;
	border-bottom: 1px solid #eef2f7; margin-bottom: 0.35rem;
}
#oa2-shared-header-controls .oa2-user-dropdown-avatar {
	width: 34px; height: 34px; border-radius: 999px; overflow: hidden; display: grid; place-items: center;
	background: linear-gradient(135deg, #dbeafe 0%, #bfdbfe 100%); color: #1e40af;
	font-size: 0.7rem; font-weight: 700; flex-shrink: 0;
}
#oa2-shared-header-controls .oa2-user-dropdown-name {
	font-size: 0.82rem; font-weight: 700; color: #0f172a; line-height: 1.25;
}
#oa2-shared-header-controls .oa2-user-dropdown-id { font-size: 0.68rem; color: #64748b; }
#oa2-shared-header-controls .oa2-user-logout {
	appearance: none; width: 100%; border: 0; background: transparent; display: flex; align-items: center;
	gap: 0.55rem; padding: 0.55rem 0.65rem; border-radius: 8px; cursor: pointer;
	color: #b91c1c; font-size: 0.8rem; font-weight: 600; text-align: left;
}
body[data-oa2-theme="dark"] #oa2-shared-header-controls .oa2-home-datetime {
	background: #262c38 !important;
	border: 1px solid #3a4252 !important;
	border-radius: 999px !important;
	color: #a8b0bd !important;
	padding: 0.35rem 0.7rem !important;
	font-size: 0.72rem !important;
	box-shadow: none !important;
}
body[data-oa2-theme="dark"] #oa2-shared-header-controls .oa2-user-btn {
	background: #262c38; border-color: #3a4252;
}
body[data-oa2-theme="dark"] #oa2-shared-header-controls .oa2-user-btn:hover {
	background: #2e3542; border-color: #4a5366;
}
body[data-oa2-theme="dark"] #oa2-shared-header-controls .oa2-user-avatar,
body[data-oa2-theme="dark"] #oa2-shared-header-controls .oa2-user-dropdown-avatar {
	background: linear-gradient(135deg, #2a3a4f 0%, #334e7a 100%); color: #c5d8f0;
}
body[data-oa2-theme="dark"] #oa2-shared-header-controls .oa2-user-dropdown {
	background: #262c38; border-color: #3a4252;
}
body[data-oa2-theme="dark"] #oa2-shared-header-controls .oa2-user-dropdown-head { border-bottom-color: #3a4252; }
body[data-oa2-theme="dark"] #oa2-shared-header-controls .oa2-user-dropdown-name { color: #e8eaed; }
body[data-oa2-theme="dark"] #oa2-shared-header-controls .oa2-user-dropdown-id { color: #a8b0bd; }
/* Shared theme toggle (same as Home) */
.oa2-theme-toggle { display: inline-flex; align-items: center; user-select: none; }
.oa2-theme-side { display: none !important; }
.oa2-theme-dots, .oa2-theme-dot { display: none !important; }
.oa2-theme-switch {
	appearance: none; -webkit-appearance: none; border: 0; padding: 0; margin: 0;
	background: transparent; cursor: pointer; display: inline-flex; align-items: center; line-height: 0;
}
.oa2-theme-track {
	display: block; width: 46px; height: 26px; border-radius: 999px; background: #e2e8f0;
	border: 1px solid #cbd5e1; box-sizing: border-box; position: relative;
	box-shadow: inset 0 1px 2px rgba(15,23,42,.06); overflow: hidden;
}
.oa2-theme-icon { position: absolute; top: 50%; transform: translateY(-50%); z-index: 1; pointer-events: none; opacity: .55; }
.oa2-theme-icon-sun { left: 6px; color: #f59e0b; }
.oa2-theme-icon-moon { right: 6px; color: #64748b; }
.oa2-theme-thumb {
	position: absolute; top: 2px; left: 2px; width: 20px; height: 20px; border-radius: 999px;
	background: #fff; box-shadow: 0 1px 3px rgba(15,23,42,.22); z-index: 2;
	transition: transform .28s cubic-bezier(.4,0,.2,1);
}
.oa2-theme-toggle.is-dark .oa2-theme-track,
.oa2-theme-switch.is-dark .oa2-theme-track,
.oa2-theme-switch[aria-checked="true"] .oa2-theme-track {
	background: #1e293b; border-color: #334155;
}
.oa2-theme-toggle.is-dark .oa2-theme-thumb,
.oa2-theme-switch.is-dark .oa2-theme-thumb,
.oa2-theme-switch[aria-checked="true"] .oa2-theme-thumb { transform: translateX(20px); }
.oa2-theme-toggle.is-dark .oa2-theme-icon-sun { opacity: .35; color: #94a3b8; }
.oa2-theme-toggle.is-dark .oa2-theme-icon-moon { opacity: .95; color: #e2e8f0; }
.oa2-theme-toggle:not(.is-dark) .oa2-theme-icon-sun { opacity: .95; }
/* Shared header toggle uses the Monitoring track and thumb on every page */
#oa2-shared-header-controls .oa2-theme-toggle {
	display: inline-flex;
	align-items: center;
	gap: 0.55rem;
}
#oa2-shared-header-controls .oa2-theme-track {
	position: relative;
	display: inline-block;
	width: 46px;
	height: 24px;
	border-radius: 999px;
	background: #e5e7eb;
	box-shadow: inset 0 0 0 1px #d1d5db;
	box-sizing: border-box;
	overflow: hidden;
}
#oa2-shared-header-controls .oa2-theme-toggle.is-dark .oa2-theme-track,
#oa2-shared-header-controls .oa2-theme-switch.is-dark .oa2-theme-track,
#oa2-shared-header-controls .oa2-theme-switch[aria-checked="true"] .oa2-theme-track {
	background: #374151;
	box-shadow: inset 0 0 0 1px #4b5563;
}
#oa2-shared-header-controls .oa2-theme-thumb {
	position: absolute;
	top: 3px;
	left: 3px;
	width: 18px;
	height: 18px;
	border-radius: 50%;
	background: #fff;
	box-shadow: 0 1px 3px rgba(0, 0, 0, 0.25);
	transition: transform 0.18s ease;
}
#oa2-shared-header-controls .oa2-theme-toggle.is-dark .oa2-theme-thumb,
#oa2-shared-header-controls .oa2-theme-switch.is-dark .oa2-theme-thumb,
#oa2-shared-header-controls .oa2-theme-switch[aria-checked="true"] .oa2-theme-thumb {
	transform: translateX(22px);
	background: #111827;
}
#oa2-shared-header-controls .oa2-theme-icon {
	width: 12px;
	height: 12px;
}
/* List/Form chrome (Logs, Settings) */
.oa2-shared-list-bar {
	display: flex; justify-content: flex-end; align-items: center;
	padding: 0.65rem 1.25rem; gap: 0.75rem;
	background: transparent;
}
body.oa2-has-sidebar.oa2-list-route .layout-main-section {
	height: 100vh !important; max-height: 100vh !important;
	height: 100dvh !important; max-height: 100dvh !important;
	overflow: auto !important;
}
body.oa2-has-sidebar.oa2-list-route {
	overflow: auto !important;
	height: auto !important;
	min-height: 100vh !important;
	max-height: none !important;
}
body.oa2-has-sidebar.oa2-list-route .page-head {
	width: 100% !important; max-width: none !important;
}
`;
	}

	function apply_theme(theme) {
		const t = theme === "dark" ? "dark" : "light";
		try {
			localStorage.setItem(THEME_KEY, t);
		} catch (e) {
			/* ignore */
		}
		try {
			document.documentElement.setAttribute("data-oa2-theme", t);
			document.body.setAttribute("data-oa2-theme", t);
		} catch (e) {
			/* ignore */
		}

		document
			.querySelectorAll(
				".oa2-home, .oa2-config-list-page, .oa2-monitor-page, .oa2-dashboard-wrapper, .oa2-config-page-wrapper, .oa2-monitor-page-wrapper, .oa2-sidebar-inpage, .oa2-app-frame, .oa2-shared-list-bar"
			)
			.forEach(function (node) {
				node.setAttribute("data-oa2-theme", t);
			});

		document.querySelectorAll(".oa2-theme-toggle").forEach(function (toggle) {
			toggle.classList.toggle("is-dark", t === "dark");
			const sw = toggle.querySelector(".oa2-theme-switch");
			if (sw) {
				sw.setAttribute("aria-checked", t === "dark" ? "true" : "false");
				sw.classList.toggle("is-dark", t === "dark");
			}
		});

		if (window.openas2_manager && typeof openas2_manager.apply_sidebar_theme === "function") {
			try {
				openas2_manager.apply_sidebar_theme();
			} catch (e) {
				/* ignore */
			}
		}
	}

	function ensure_toggle_host(root) {
		let toggle = root.querySelector(".oa2-theme-toggle");
		if (toggle) return toggle;

		const actions =
			root.querySelector(".oa2-home-header-actions") ||
			root.querySelector(".oa2-config-header-actions") ||
			root.querySelector(".oa2-monitor-header-actions");
		if (actions) {
			toggle = document.createElement("div");
			toggle.className = "oa2-theme-toggle";
			toggle.setAttribute("role", "group");
			toggle.setAttribute("aria-label", "Theme");
			actions.insertBefore(toggle, actions.firstChild);
			return toggle;
		}
		return null;
	}

	function ensure_list_toggle() {
		const route = get_route();
		const r0 = String(route[0] || "");
		if (["List", "Form", "list", "form"].indexOf(r0) === -1) return;

		let bar = document.getElementById("oa2-shared-list-bar");
		const main = document.querySelector(".layout-main-section");
		if (!main) return;

		if (!bar) {
			bar = document.createElement("div");
			bar.id = "oa2-shared-list-bar";
			bar.className = "oa2-shared-list-bar";
			const toggle = document.createElement("div");
			toggle.className = "oa2-theme-toggle";
			toggle.setAttribute("role", "group");
			toggle.setAttribute("aria-label", "Theme");
			bar.appendChild(toggle);
			main.insertBefore(bar, main.firstChild);
		}
		document.body.classList.add("oa2-list-route");
		return bar.querySelector(".oa2-theme-toggle");
	}

	const SHARED_HEADER_ID = "oa2-shared-header-controls";

	function user_menu_html() {
		const uid = (frappe.session && frappe.session.user) || "";
		const info = (frappe.user_info && frappe.user_info(uid)) || {};
		const rawName =
			(frappe.session && frappe.session.user_fullname) || info.fullname || uid || "User";
		const fullname = frappe.utils.escape_html(rawName);
		const abbr = frappe.utils.escape_html(
			info.abbr || (frappe.get_abbr && frappe.get_abbr(rawName)) || "U"
		);
		const image =
			info.image || (frappe.user && frappe.user.image && frappe.user.image()) || "";
		const avatar = image
			? '<img class="oa2-user-avatar-img" src="' + frappe.utils.escape_html(image) + '" alt="">'
			: '<span class="oa2-user-avatar-abbr">' + abbr + "</span>";
		return (
			'<button type="button" class="oa2-user-btn" aria-haspopup="menu" aria-expanded="false" title="' +
			fullname +
			'"><span class="oa2-user-avatar">' +
			avatar +
			"</span></button>" +
			'<div class="oa2-user-dropdown" role="menu" hidden>' +
			'<div class="oa2-user-dropdown-head"><span class="oa2-user-dropdown-avatar">' +
			avatar +
			'</span><div class="oa2-user-dropdown-meta"><div class="oa2-user-dropdown-name">' +
			fullname +
			'</div><div class="oa2-user-dropdown-id">' +
			frappe.utils.escape_html(uid) +
			"</div></div></div>" +
			'<button type="button" class="oa2-user-logout" role="menuitem">' +
			'<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10 4H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h4"/><path d="M16 12H8"/><path d="m14 8 4 4-4 4"/></svg>' +
			"<span>Log Out</span></button></div>"
		);
	}

	function tick_shared_clock() {
		const el = document.querySelector("#" + SHARED_HEADER_ID + " .oa2-home-datetime");
		if (!el || !frappe.datetime) return;
		let formatted = "";
		try {
			formatted = frappe.datetime.str_to_user(frappe.datetime.now_datetime());
		} catch (e) {
			formatted = "";
		}
		const tz =
			(frappe.boot && frappe.boot.time_zone && frappe.boot.time_zone.user) ||
			(frappe.boot && frappe.boot.sysdefaults && frappe.boot.sysdefaults.time_zone) ||
			"";
		el.textContent = tz ? formatted + " (" + tz + ")" : formatted;
	}

	function ensure_shared_header() {
		let bar = document.getElementById(SHARED_HEADER_ID);
		if (bar) return bar;
		bar = document.createElement("div");
		bar.id = SHARED_HEADER_ID;
		bar.setAttribute("data-oa2-shared-header", "1");
		bar.innerHTML =
			copilot_button_html() +
			'<div class="oa2-theme-toggle oa2-shared-theme" role="group" aria-label="Theme">' +
			theme_toggle_html() +
			"</div>" +
			'<div class="oa2-home-datetime" aria-live="polite"></div>' +
			'<div class="oa2-user-menu">' +
			user_menu_html() +
			"</div>";
		document.body.appendChild(bar);
		tick_shared_clock();
		if (!window.__oa2_shared_clock) {
			window.__oa2_shared_clock = setInterval(tick_shared_clock, 30000);
		}
		return bar;
	}

	function is_shown(el) {
		if (!el) return false;
		return !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
	}

	function visible_actions_host() {
		const nodes = document.querySelectorAll(
			".oa2-home-header-actions, .oa2-config-header-actions, .oa2-monitor-header-actions"
		);
		for (let i = 0; i < nodes.length; i++) {
			if (is_shown(nodes[i])) return nodes[i];
		}
		return null;
	}

	function place_shared_header() {
		const bar = ensure_shared_header();
		ensure_copilot_button_css();
		refresh_copilot_button(bar);
		if (bar && !bar.querySelector(".oa2-ai-open")) {
			bar.insertAdjacentHTML("afterbegin", copilot_button_html());
		}
		const host = visible_actions_host();
		if (!host) {
			hide_shared_header();
			return;
		}
		bar.hidden = false;
		bar.style.display = "flex";
		if (bar.parentElement !== host) {
			host.insertBefore(bar, host.firstChild);
		}
		const sharedToggle = bar.querySelector(".oa2-theme-toggle");
		const pageToggle = host.querySelector(":scope > .oa2-theme-toggle .oa2-theme-icon-sun");
		if (sharedToggle) {
			sharedToggle.style.display =
				host.classList.contains("oa2-config-header-actions") && pageToggle ? "none" : "";
		}
		tick_shared_clock();
	}

	function hide_shared_header() {
		const bar = document.getElementById(SHARED_HEADER_ID);
		if (!bar) return;
		bar.hidden = true;
		bar.style.display = "none";
	}

	function mount_theme_toggles() {
		const roots = document.querySelectorAll(
			".oa2-home, .oa2-config-list-page, .oa2-monitor-page, .oa2-dashboard-wrapper, .oa2-config-page-wrapper, .oa2-monitor-page-wrapper"
		);

		if (roots.length) {
			roots.forEach(function (root) {
				const toggle = ensure_toggle_host(root);
				if (!toggle) return;
				/* Always use the same Home sun/moon control */
				if (!toggle.querySelector(".oa2-theme-icon-sun")) {
					toggle.innerHTML = theme_toggle_html();
				}
			});
		} else {
			const listToggle = ensure_list_toggle();
			if (listToggle && !listToggle.querySelector(".oa2-theme-icon-sun")) {
				listToggle.innerHTML = theme_toggle_html();
			}
		}
	}

	function ensure_assistant_assets() {
		if (!document.querySelector("link[data-oa2-ai-css]")) {
			const link = document.createElement("link");
			link.rel = "stylesheet";
			link.href = "/assets/openas2_manager/css/openas2_assistant.css";
			link.setAttribute("data-oa2-ai-css", "1");
			document.head.appendChild(link);
		}
		if (!window.__oa2_ai_script) {
			window.__oa2_ai_script = true;
			const script = document.createElement("script");
			script.src = "/assets/openas2_manager/js/openas2_assistant.js";
			document.body.appendChild(script);
		}
	}

	function apply_full_bleed() {
		document.body.classList.add("oa2-has-sidebar");
		document.body.classList.add("no-sidebar");

		if (document.querySelector(".oa2-sidebar-inpage")) {
			document.body.classList.add("oa2-use-inpage-sidebar");
		}

		document
			.querySelectorAll(".oa2-dashboard-wrapper, .oa2-config-page-wrapper, .oa2-monitor-page-wrapper")
			.forEach(function (wrap) {
				wrap.style.setProperty("width", "100%", "important");
				wrap.style.setProperty("max-width", "none", "important");
				wrap.style.setProperty("margin", "0", "important");
				wrap.style.setProperty("padding", "0", "important");
				wrap.style.setProperty("height", "100vh", "important");
				wrap.style.setProperty("max-height", "100vh", "important");

				wrap.querySelectorAll(".layout-side-section").forEach(function (side) {
					side.classList.add("hide-sidebar");
					side.style.setProperty("display", "none", "important");
				});

				wrap
					.querySelectorAll(
						".layout-main, .layout-main-section-wrapper, .layout-main-section, .page-body, .oa2-home, .oa2-config-list-page, .oa2-monitor-page, .oa2-home-shell, .oa2-config-shell, .oa2-monitor-shell, .oa2-app-frame"
					)
					.forEach(function (node) {
						node.style.setProperty("width", "100%", "important");
						node.style.setProperty("max-width", "none", "important");
						node.style.setProperty("margin-left", "0", "important");
						node.style.setProperty("margin-right", "0", "important");
					});
			});
	}

	function clear_oa2_layout() {
		document.body.classList.remove("oa2-has-sidebar");
		document.body.classList.remove("oa2-use-inpage-sidebar");
		document.body.classList.remove("oa2-list-route");
		document.body.classList.remove("no-sidebar");
		const bar = document.getElementById("oa2-shared-list-bar");
		if (bar) bar.remove();
		hide_shared_header();
	}

	function maybe_redirect_logs_list() {
		/* Desk List routes → custom OA2 pages (no standard list views). */
		const route = get_route();
		const r0 = String(route[0] || "");
		const r1 = String(route[1] || "");
		if (r0 === "List" && r1 === "OpenAS2 Message Log") {
			try {
				frappe.set_route("openas2-logs");
				return true;
			} catch (e) {
				window.location.href = "/app/openas2-logs";
				return true;
			}
		}
		if (r0 === "List" && r1 === "OpenAS2 Instance") {
			try {
				frappe.set_route("openas2-settings");
				return true;
			} catch (e) {
				window.location.href = "/app/openas2-settings";
				return true;
			}
		}
		if (r0 === "List" && r1 === "AS2 Partner") {
			try {
				frappe.set_route("openas2-partners");
				return true;
			} catch (e) {
				window.location.href = "/app/openas2-partners";
				return true;
			}
		}
		if (r0 === "List" && r1 === "AS2 Certificate") {
			try {
				frappe.set_route("openas2-certificates");
				return true;
			} catch (e) {
				window.location.href = "/app/openas2-certificates";
				return true;
			}
		}
		return false;
	}

	function strip_config_page_item_lists() {
		const route = get_route();
		const r0 = String(route[0] || "").toLowerCase();
		const stripRoutes = {
			"openas2-partners": true,
			"openas2-configuration": true,
			"openas2-certificates": true,
		};
		if (!stripRoutes[r0]) return;
		const shell =
			document.querySelector(".oa2-config-list-page .oa2-config-shell") ||
			document.querySelector(".oa2-config-list-page");
		if (!shell) return;
		shell.querySelectorAll(".oa2-partners-list, table.oa2-config-table, table.oa2-ps-table").forEach(function (table) {
			const card = table.closest("section.oa2-config-card");
			if (card) card.remove();
			else {
				const wrap = table.closest(".oa2-config-table-wrap");
				if (wrap) wrap.remove();
				else table.remove();
			}
		});
	}

	function sync() {
		if (!window.frappe) return;
		if (maybe_redirect_logs_list()) return;
		if (!is_oa2_context()) {
			clear_oa2_layout();
			return;
		}
		ensure_layout_css();
		ensure_assistant_assets();
		apply_full_bleed();
		place_shared_header();
		apply_theme(get_theme());
		strip_config_page_item_lists();

		if (window.openas2_manager && typeof openas2_manager.sync_sidebar === "function") {
			try {
				openas2_manager.sync_sidebar();
			} catch (e) {
				/* ignore */
			}
		}
	}

	function bind_once() {
		if (window.__oa2_layout_bound) return;
		window.__oa2_layout_bound = true;

		document.addEventListener(
			"click",
			function (e) {
				const logout = e.target.closest("#oa2-shared-header-controls .oa2-user-logout");
				if (logout) {
					e.preventDefault();
					e.stopPropagation();
					const menu = document.querySelector("#oa2-shared-header-controls .oa2-user-menu");
					if (menu) menu.classList.remove("is-open");
					const dd = document.querySelector("#oa2-shared-header-controls .oa2-user-dropdown");
					if (dd) dd.hidden = true;
					if (frappe.app && typeof frappe.app.logout === "function") {
						frappe.app.logout();
					}
					return;
				}
				const userBtn = e.target.closest("#oa2-shared-header-controls .oa2-user-btn");
				if (userBtn) {
					e.preventDefault();
					e.stopPropagation();
					const wrap = userBtn.closest(".oa2-user-menu");
					const dd = wrap && wrap.querySelector(".oa2-user-dropdown");
					const open = !(wrap && wrap.classList.contains("is-open"));
					if (wrap) wrap.classList.toggle("is-open", open);
					userBtn.setAttribute("aria-expanded", open ? "true" : "false");
					if (dd) dd.hidden = !open;
					return;
				}
				if (!e.target.closest("#oa2-shared-header-controls .oa2-user-dropdown")) {
					const wrap = document.querySelector("#oa2-shared-header-controls .oa2-user-menu");
					const dd = document.querySelector("#oa2-shared-header-controls .oa2-user-dropdown");
					const btn = document.querySelector("#oa2-shared-header-controls .oa2-user-btn");
					if (wrap) wrap.classList.remove("is-open");
					if (dd) dd.hidden = true;
					if (btn) btn.setAttribute("aria-expanded", "false");
				}
				const themeBtn = e.target.closest(".oa2-theme-switch");
				if (!themeBtn) return;
				if (!is_oa2_context()) return;
				e.preventDefault();
				e.stopPropagation();
				apply_theme(get_theme() === "dark" ? "light" : "dark");
			},
			true
		);

		window.addEventListener("storage", function (e) {
			if (e.key === THEME_KEY && is_oa2_context()) {
				apply_theme(get_theme());
			}
		});

		if (frappe.router && frappe.router.on) {
			frappe.router.on("change", function () {
				setTimeout(sync, 0);
				setTimeout(sync, 80);
				setTimeout(sync, 250);
			});
		}

		if (window.jQuery) {
			jQuery(document).on("page-change", function () {
				setTimeout(sync, 0);
				setTimeout(sync, 80);
			});
		}
	}

	function boot() {
		bind_once();
		sync();
		setTimeout(sync, 100);
		setTimeout(sync, 400);
	}

	window.openas2_manager = window.openas2_manager || {};
	window.openas2_manager.sync_layout = sync;
	window.openas2_manager.apply_oa2_theme = apply_theme;
	window.openas2_manager.get_oa2_theme = get_theme;

	if (window.jQuery) {
		jQuery(document).on("app_ready", boot);
		jQuery(function () {
			boot();
		});
	} else {
		document.addEventListener("DOMContentLoaded", boot);
		window.addEventListener("load", boot);
	}
})();
