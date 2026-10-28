// Copyright (c) 2026, Lakshana and contributors
// For license information, please see license.txt

/**
 * Persistent EDI AS2 left sidebar on dashboard + all OA2 pages (light + dark).
 */
(function () {
	const DASHBOARD = "openas2-dashboard";
	const DASHBOARD_PATH = "/app/" + DASHBOARD;
	const THEME_KEY = "oa2-dashboard-theme";
	const SIDEBAR_ID = "oa2-app-sidebar";
	const FORCE_CSS_ID = "oa2-sidebar-force-css";
	const DESK_CHROME_CSS_ID = "oa2-desk-chrome-hide-css";

	const OA2_PAGES = new Set([
		"openas2-dashboard",
		"openas2-configuration",
		"openas2-messages",
		"openas2-errors",
		"openas2-partnerships",
		"openas2-partners",
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

	const OA2_SLUGS = new Set([
		"openas2-dashboard",
		"openas2-configuration",
		"openas2-messages",
		"openas2-errors",
		"openas2-partnerships",
		"openas2-partners",
		"openas2-certificates",
		"as2-partner",
		"as2-certificate",
		"openas2-instance",
		"openas2-partnership",
		"openas2-message-log",
		"openas2-configuration-change",
		"openas2-restart-log",
		"openas2-runtime-log",
		"openas2-provisioning-log",
		"list",
		"form",
	]);

	frappe.re_route = frappe.re_route || {};
	frappe.re_route["openas2-manager"] = DASHBOARD;

	const ICONS = {
		home: `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M4 10.5 12 4l8 6.5"/><path d="M6.5 9.5V20h11V9.5"/></svg>`,
		configuration: `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M12 3.5v2.2M12 18.3v2.2M4.9 6.4l1.6 1.6M17.5 16l1.6 1.6M3.5 12h2.2M18.3 12h2.2M4.9 17.6l1.6-1.6M17.5 8l1.6-1.6"/></svg>`,
		partners: `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="9" cy="8" r="2.4"/><circle cx="16.5" cy="9" r="2"/><path d="M4.5 18.5c.6-2.6 2.6-4 4.5-4s3.9 1.4 4.5 4"/><path d="M13.8 18.5c.4-1.8 1.7-3 3-3 1.4 0 2.5.9 3 2.5"/></svg>`,
		certificates: `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3.5 19 6.5v5.2c0 4.2-2.8 7.8-7 9-4.2-1.2-7-4.8-7-9V6.5L12 3.5z"/></svg>`,
		monitoring: `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M7 16a4.5 4.5 0 0 1 .4-9 5.5 5.5 0 0 1 10.5 1.6A3.8 3.8 0 0 1 18.5 16H7z"/></svg>`,
		logs: `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M7 3.5h7.2L19 8.3V20a1.5 1.5 0 0 1-1.5 1.5h-10A1.5 1.5 0 0 1 6 20V5A1.5 1.5 0 0 1 7.5 3.5H7z"/><path d="M14 3.5V8h4.8"/><path d="M9 12.5h6M9 16h4"/></svg>`,
		settings: `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h10"/><path d="M4 12h16"/><path d="M4 17h8"/><circle cx="16.5" cy="7" r="2"/><circle cx="14.5" cy="17" r="2"/><circle cx="10" cy="12" r="2"/></svg>`,
	};

	const NAV_ITEMS = [
		{ key: "home", label: "Home", icon: "home", route: "openas2-dashboard" },
		{ key: "configuration", label: "Configuration", icon: "configuration", route: "openas2-configuration" },
		{ key: "partners", label: "Partners", icon: "partners", route: "openas2-partners" },
		{ key: "certificates", label: "Certificates", icon: "certificates", route: "openas2-certificates" },
		{ key: "monitoring", label: "Monitoring", icon: "monitoring", route: "openas2-messages" },
		{ key: "logs", label: "Logs", icon: "logs", route: "openas2-logs" },
		{ key: "settings", label: "Settings", icon: "settings", route: "openas2-settings" },
	];

	function t(msg) {
		try {
			return typeof __ === "function" ? __(msg) : msg;
		} catch (e) {
			return msg;
		}
	}

	function esc(s) {
		try {
			return frappe.utils.escape_html(String(s || ""));
		} catch (e) {
			return String(s || "")
				.replace(/&/g, "&amp;")
				.replace(/</g, "&lt;")
				.replace(/>/g, "&gt;")
				.replace(/"/g, "&quot;");
		}
	}

	function get_theme() {
		try {
			return localStorage.getItem(THEME_KEY) === "dark" ? "dark" : "light";
		} catch (e) {
			return "light";
		}
	}

	function path_parts() {
		try {
			return (window.location.pathname || "")
				.replace(/\/+$/, "")
				.split("/")
				.filter(Boolean);
		} catch (e) {
			return [];
		}
	}

	function get_route() {
		try {
			return (frappe.get_route && frappe.get_route()) || [];
		} catch (e) {
			return [];
		}
	}

	function needs_dashboard_redirect() {
		const parts = path_parts();
		if (!parts.length || parts[0] !== "app") return false;
		if (parts.length === 1) return true;

		const p1 = (parts[1] || "").toLowerCase();
		const p2 = (parts[2] || "").toLowerCase();

		if (p1 === DASHBOARD) return false;
		if (p1 === "openas2-manager") return true;
		if ((p1 === "workspace" || p1 === "workspaces") && p2 === "openas2-manager") return true;

		try {
			const route = get_route();
			if (route[0] === "Workspaces") {
				const title = String(route[route.length - 1] || "");
				if (title === "OpenAS2 Manager") return true;
			}
		} catch (e) {
			/* ignore */
		}
		return false;
	}

	function open_dashboard() {
		if ((window.location.pathname || "").replace(/\/+$/, "") === DASHBOARD_PATH) return;
		try {
			window.location.replace(DASHBOARD_PATH);
		} catch (e) {
			window.location.href = DASHBOARD_PATH;
		}
	}

	function is_oa2_doctype_name(name) {
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
		if (["List", "Form", "Tree", "Report", "list", "form"].includes(r0) && is_oa2_doctype_name(r1)) {
			return true;
		}

		const parts = path_parts();
		if (parts[0] === "app") {
			if (parts.length === 1) return true;
			const slug = (parts[1] || "").toLowerCase();
			if (OA2_PAGES.has(slug) || OA2_SLUGS.has(slug)) return true;
			if (slug.indexOf("openas2") === 0 || slug.indexOf("as2-") === 0) return true;
			// /app/list/as2-partner etc.
			if ((slug === "list" || slug === "form") && parts[2]) {
				const d = decodeURIComponent(parts[2]).replace(/-/g, " ");
				if (is_oa2_doctype_name(d) || is_oa2_doctype_name(parts[2])) return true;
				const slug2 = parts[2].toLowerCase();
				if (slug2.indexOf("openas2") === 0 || slug2.indexOf("as2") === 0) return true;
			}
		}

		// Stay visible if already showing and still under /app
		if (document.body && document.body.classList.contains("oa2-has-sidebar") && parts[0] === "app") {
			const slug = (parts[1] || "").toLowerCase();
			if (!slug || OA2_PAGES.has(slug) || slug.indexOf("openas2") >= 0 || slug.indexOf("as2") >= 0) {
				return true;
			}
		}

		return false;
	}

	function active_key() {
		const route = get_route();
		const r0 = String(route[0] || "");
		const r1 = String(route[1] || "");
		const r0l = r0.toLowerCase();
		const parts = path_parts();
		const slug = ((parts[1] || "") + "").toLowerCase();

		if (r0l === "openas2-dashboard" || slug === "openas2-dashboard" || r0 === "Workspaces") {
			return "home";
		}
		if (r0l === "openas2-configuration" || slug === "openas2-configuration") return "configuration";
		if (r0l === "openas2-messages" || r0l === "openas2-errors" || slug === "openas2-messages") {
			return "monitoring";
		}
		if (r0l === "openas2-partnerships" || r0l === "openas2-partners" || slug === "openas2-partners") {
			return "partners";
		}
		if (r0l === "openas2-certificates" || slug === "openas2-certificates") {
			return "certificates";
		}

		if (r0l === "openas2-logs" || slug === "openas2-logs") return "logs";
		if (r0l === "openas2-settings" || slug === "openas2-settings") return "settings";
		if (r0 === "List" || r0 === "Form" || r0 === "list" || r0 === "form") {
			if (r1 === "AS2 Partner" || r1 === "OpenAS2 Partnership") return "partners";
			if (r1 === "AS2 Certificate") return "certificates";
			if (r1 === "OpenAS2 Message Log") return "logs";
			if (r1 === "OpenAS2 Instance") {
				return r0 === "Form" || r0 === "form" ? "configuration" : "settings";
			}
		}

		if (slug === "as2-certificate" || slug.indexOf("as2-certificate") === 0) return "certificates";
		if (slug === "as2-partner" || slug.indexOf("as2-partner") === 0) return "partners";
		if (slug === "openas2-message-log" || slug === "openas2-logs") return "logs";
		if (slug === "openas2-instance") return "settings";

		return "home";
	}

	function sidebar_html() {
		const active = active_key();
		const nav = NAV_ITEMS.map((item) => {
			const isActive = item.key === active;
			return `<button type="button" class="oa2-nav-item${isActive ? " active" : ""}" data-oa2-route="${esc(
				item.route
			)}" data-oa2-key="${esc(item.key)}">
				<span class="oa2-nav-icon">${ICONS[item.icon]}</span>
				<span class="oa2-nav-label">${esc(t(item.label))}</span>
			</button>`;
		}).join("");

		return `
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
					<div class="oa2-brand-tagline">${esc(t("Secure. Converted. Compliant"))}</div>
				</div>
				<span class="oa2-brand-dot" title="${esc(t("Online"))}"></span>
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
					<strong>${esc(t("AS2 Communication"))}</strong>
					<span>${esc(t("Secure B2B exchange with your business partners"))}</span>
				</div>
				<div class="oa2-footer-pulse" aria-hidden="true">
					<svg viewBox="0 0 40 16" width="28" height="12" fill="none" stroke="currentColor" stroke-width="1.6">
						<path d="M1 8h8l3-5 4 10 3-5h10"/>
					</svg>
				</div>
			</div>
		`;
	}

	function inpage_sidebar_markup() {
		const theme = get_theme();
		return `<aside class="oa2-sidebar-inpage" aria-label="EDI AS2" data-oa2-theme="${esc(
			theme
		)}">${sidebar_html()}</aside>`;
	}

	function refresh_inpage_sidebars() {
		const theme = get_theme();
		const html = sidebar_html();
		document.querySelectorAll(".oa2-sidebar-inpage").forEach(function (node) {
			// Only (re)fill when empty — never wipe existing brand/nav/footer markup
			if (!node.querySelector(".oa2-sidebar-brand") || !node.querySelector(".oa2-nav-item")) {
				node.innerHTML = html;
			} else {
				// Update active nav state in place
				const active = active_key();
				node.querySelectorAll(".oa2-nav-item").forEach(function (btn) {
					const key = btn.getAttribute("data-oa2-key");
					const route = btn.getAttribute("data-oa2-route") || btn.getAttribute("data-route") || "";
					let isActive = key === active;
					if (!key) {
						if (active === "home" && route.indexOf("dashboard") !== -1) isActive = true;
						else if (active === "configuration" && route.indexOf("configuration") !== -1) isActive = true;
						else if (active === "partners" && route.indexOf("partner") !== -1) isActive = true;
						else if (active === "certificates" && route.indexOf("certificate") !== -1) isActive = true;
						else if (active === "monitoring" && route.indexOf("message") !== -1) isActive = true;
						else if (active === "logs" && (route.indexOf("Message Log") !== -1 || route.indexOf("openas2-logs") !== -1)) isActive = true;
						else if (active === "settings" && (route.indexOf("Instance") !== -1 || route.indexOf("openas2-settings") !== -1)) isActive = true;
						else isActive = false;
					}
					btn.classList.toggle("active", !!isActive);
				});
			}
			node.setAttribute("data-oa2-theme", theme);
			node.style.setProperty("display", "flex", "important");
			node.style.setProperty("visibility", "visible", "important");
			node.style.setProperty("flex-direction", "column", "important");
			node.style.setProperty(
				"background",
				theme === "dark"
					? "#1a1f27"
					: "linear-gradient(180deg,#0b1f4d 0%,#002b7f 55%,#003399 100%)",
				"important"
			);
			node.style.setProperty("color", "#fff", "important");
		});
	}

	function navigate_oa2_route(route) {
		if (!route) return;
		document.body.classList.add("oa2-has-sidebar");
		try {
			frappe.set_route(...route.split("/"));
		} catch (err) {
			window.location.href = "/app/" + route.toLowerCase().replace(/\s+/g, "-");
		}
		setTimeout(sync, 50);
		setTimeout(sync, 250);
	}

	function ensure_force_css() {
		let style = document.getElementById(FORCE_CSS_ID);
		if (!style) {
			style = document.createElement("style");
			style.id = FORCE_CSS_ID;
			document.head.appendChild(style);
		}
		/* Pad only when JS confirms the navy panel is painted (oa2-sidebar-mounted). */
		style.textContent = `
#oa2-app-sidebar.oa2-sidebar-global{
	position:fixed!important;top:0!important;left:0!important;bottom:0!important;
	width:248px!important;height:100vh!important;height:100dvh!important;
	min-height:100vh!important;min-height:100dvh!important;max-height:none!important;
	z-index:10000!important;
	display:flex!important;visibility:visible!important;opacity:1!important;
	flex-direction:column!important;box-sizing:border-box!important;
	padding:1.1rem .85rem .85rem!important;overflow:hidden!important;
	background:linear-gradient(180deg,#0b1f4d 0%,#002b7f 55%,#003399 100%)!important;
	color:#fff!important;box-shadow:4px 0 24px rgba(0,20,60,.18)!important;
	pointer-events:auto!important;
}
body.oa2-use-inpage-sidebar .oa2-sidebar-inpage,
body.oa2-use-inpage-sidebar .oa2-config-list-page .oa2-sidebar-inpage,
body.oa2-use-inpage-sidebar .oa2-home .oa2-sidebar-inpage{
	display:flex!important;align-self:stretch!important;
	height:100%!important;min-height:100%!important;max-height:none!important;
	background:linear-gradient(180deg,#0b1f4d 0%,#002b7f 55%,#003399 100%)!important;
	color:#fff!important;
}
body[data-oa2-theme="light"] .oa2-sidebar-inpage,
.oa2-sidebar-inpage[data-oa2-theme="light"]{
	background:linear-gradient(180deg,#0b1f4d 0%,#002b7f 55%,#003399 100%)!important;
	color:#fff!important;
}
body[data-oa2-theme="dark"] .oa2-sidebar-inpage,
.oa2-sidebar-inpage[data-oa2-theme="dark"]{
	background:#1a1f27!important;color:#e5e7eb!important;
}
body.oa2-use-inpage-sidebar .oa2-sidebar-inpage .oa2-sidebar-brand,
body.oa2-use-inpage-sidebar .oa2-sidebar-inpage .oa2-sidebar-nav,
body.oa2-use-inpage-sidebar .oa2-sidebar-inpage .oa2-sidebar-footer,
body.oa2-use-inpage-sidebar .oa2-sidebar-inpage .oa2-brand-text,
body.oa2-use-inpage-sidebar .oa2-sidebar-inpage .oa2-brand-title,
body.oa2-use-inpage-sidebar .oa2-sidebar-inpage .oa2-brand-tagline,
body.oa2-use-inpage-sidebar .oa2-sidebar-inpage .oa2-nav-label,
body.oa2-use-inpage-sidebar .oa2-sidebar-inpage .oa2-footer-art,
body.oa2-use-inpage-sidebar .oa2-sidebar-inpage .oa2-footer-copy,
body.oa2-use-inpage-sidebar .oa2-sidebar-inpage .oa2-footer-pulse,
.oa2-config-list-page .oa2-sidebar-inpage .oa2-sidebar-footer,
.oa2-config-list-page .oa2-sidebar-inpage .oa2-footer-art,
.oa2-config-list-page .oa2-sidebar-inpage .oa2-footer-copy,
.oa2-config-list-page .oa2-sidebar-inpage .oa2-brand-text,
.oa2-config-list-page .oa2-sidebar-inpage .oa2-nav-label{
	display:block!important;visibility:visible!important;opacity:1!important;
}
body.oa2-use-inpage-sidebar .oa2-sidebar-inpage .oa2-sidebar-brand,
body.oa2-use-inpage-sidebar .oa2-sidebar-inpage .oa2-sidebar-nav,
.oa2-config-list-page .oa2-sidebar-inpage .oa2-sidebar-brand,
.oa2-config-list-page .oa2-sidebar-inpage .oa2-sidebar-nav{
	display:flex!important;
}
body.oa2-use-inpage-sidebar .oa2-sidebar-inpage .oa2-footer-art,
body.oa2-use-inpage-sidebar .oa2-sidebar-inpage .oa2-footer-pulse,
.oa2-config-list-page .oa2-sidebar-inpage .oa2-footer-art,
.oa2-config-list-page .oa2-sidebar-inpage .oa2-footer-pulse{
	display:flex!important;justify-content:center!important;
}
body.oa2-use-inpage-sidebar .oa2-sidebar-inpage .oa2-footer-copy,
.oa2-config-list-page .oa2-sidebar-inpage .oa2-footer-copy{
	display:flex!important;flex-direction:column!important;
}
body[data-oa2-theme="dark"] .oa2-config-list-page .oa2-sidebar-footer,
.oa2-config-list-page[data-oa2-theme="dark"] .oa2-sidebar-footer{
	background:linear-gradient(160deg,#bfdbfe 0%,#93c5fd 100%)!important;
	border-radius:14px!important;color:#0f172a!important;
	padding:.85rem .65rem .7rem!important;margin:.35rem .15rem .15rem!important;
}
body[data-oa2-theme="dark"] .oa2-config-list-page .oa2-footer-copy strong,
.oa2-config-list-page[data-oa2-theme="dark"] .oa2-footer-copy strong{color:#0f172a!important}
body[data-oa2-theme="dark"] .oa2-config-list-page .oa2-footer-copy span,
.oa2-config-list-page[data-oa2-theme="dark"] .oa2-footer-copy span{color:#334155!important}
body[data-oa2-theme="dark"] .oa2-config-list-page .oa2-footer-pulse,
.oa2-config-list-page[data-oa2-theme="dark"] .oa2-footer-pulse{color:#1e3a8a!important}
body.oa2-use-inpage-sidebar .oa2-config-list-page,
body.oa2-use-inpage-sidebar .oa2-home,
body.oa2-use-inpage-sidebar .oa2-app-frame{
	height:calc(100vh - 48px + 30px)!important;min-height:calc(100vh - 48px + 30px)!important;
}
body.oa2-hide-desk-chrome.oa2-use-inpage-sidebar .oa2-config-list-page,
body.oa2-hide-desk-chrome.oa2-use-inpage-sidebar .oa2-home,
body.oa2-hide-desk-chrome.oa2-use-inpage-sidebar .oa2-monitor-page,
body.oa2-hide-desk-chrome.oa2-use-inpage-sidebar .oa2-app-frame{
	height:100vh!important;min-height:100vh!important;max-height:100vh!important;
	height:100dvh!important;min-height:100dvh!important;max-height:100dvh!important;
}
body.oa2-use-inpage-sidebar .oa2-sidebar-inpage,
body.oa2-use-inpage-sidebar .oa2-main-pane{
	height:100%!important;min-height:100%!important;max-height:none!important;align-self:stretch!important;
}
body:not(.oa2-has-sidebar) #oa2-app-sidebar.oa2-sidebar-global,
body.oa2-use-inpage-sidebar:not(.oa2-sidebar-mounted) #oa2-app-sidebar.oa2-sidebar-global{display:none!important}
body.oa2-sidebar-mounted #oa2-app-sidebar.oa2-sidebar-global{display:flex!important;visibility:visible!important;opacity:1!important}
body.oa2-sidebar-mounted .oa2-sidebar-inpage{display:none!important}
body.oa2-use-inpage-sidebar .oa2-sidebar-inpage,
body:not(.oa2-sidebar-mounted) .oa2-sidebar-inpage{display:flex!important;visibility:visible!important;position:relative!important;left:auto!important;top:auto!important;flex:0 0 248px!important;width:248px!important;height:100%!important;margin:0!important}
body.oa2-has-sidebar,body.oa2-use-inpage-sidebar,body.oa2-sidebar-mounted{padding-left:0!important;margin-left:0!important}
.oa2-dashboard-wrapper .layout-side-section,.oa2-config-page-wrapper .layout-side-section,.oa2-monitor-page-wrapper .layout-side-section,body.oa2-has-sidebar .layout-side-section{display:none!important;width:0!important;max-width:0!important;flex:0 0 0!important;padding:0!important;margin:0!important}
.oa2-dashboard-wrapper .layout-main-section-wrapper,.oa2-config-page-wrapper .layout-main-section-wrapper,.oa2-monitor-page-wrapper .layout-main-section-wrapper,body.oa2-has-sidebar .layout-main-section-wrapper{width:100%!important;max-width:none!important;flex:1 1 100%!important;margin:0!important;padding:0!important}
body.oa2-has-sidebar .main-section,body.oa2-has-sidebar #body,body.oa2-has-sidebar .page-container,body.oa2-has-sidebar .container.page-container,body.oa2-has-sidebar .layout-main,body.oa2-has-sidebar .layout-main-section,body.oa2-has-sidebar .page-body,body.oa2-has-sidebar .oa2-home,body.oa2-has-sidebar .oa2-app-frame,body.oa2-has-sidebar .oa2-config-list-page,body.oa2-has-sidebar .oa2-monitor-page{margin-left:0!important;margin-right:0!important;padding-left:0!important;padding-right:0!important;left:0!important;width:100%!important;max-width:none!important}
.oa2-dashboard-wrapper.page-container,.oa2-config-page-wrapper.page-container,.oa2-monitor-page-wrapper.page-container,.oa2-dashboard-wrapper .page-body,.oa2-config-page-wrapper .page-body,.oa2-monitor-page-wrapper .page-body{width:100%!important;max-width:none!important;height:100vh!important;max-height:100vh!important;height:100dvh!important;max-height:100dvh!important;overflow:hidden!important;margin:0!important;padding:0!important}
.oa2-dashboard-wrapper .page-head,.oa2-config-page-wrapper .page-head,.oa2-monitor-page-wrapper .page-head{display:none!important}
.oa2-home-shell,.oa2-config-shell,.oa2-monitor-shell{max-width:none!important;width:100%!important;margin-left:0!important;margin-right:0!important}
body.oa2-has-sidebar .body-sidebar-container,body.oa2-has-sidebar .body-sidebar,body.oa2-has-sidebar .desk-sidebar,body.oa2-use-inpage-sidebar .body-sidebar-container,body.oa2-use-inpage-sidebar .body-sidebar{display:none!important;width:0!important;min-width:0!important;margin:0!important;padding:0!important;flex:0 0 0!important}
#oa2-app-sidebar.oa2-sidebar-global{display:none!important;width:0!important;pointer-events:none!important}
body.oa2-sidebar-mounted.oa2-using-global-sidebar:not(.oa2-use-inpage-sidebar) #oa2-app-sidebar.oa2-sidebar-global{display:flex!important;width:248px!important;pointer-events:auto!important}
body.oa2-sidebar-mounted .main-section,
body.oa2-sidebar-mounted #body,
body.oa2-sidebar-mounted .navbar,
body.oa2-sidebar-mounted header.navbar,
body.oa2-sidebar-mounted .layout-main-section-wrapper,
body.oa2-sidebar-mounted .layout-main,
body.oa2-sidebar-mounted .layout-main-section,
body.oa2-sidebar-mounted .page-container,
body.oa2-sidebar-mounted .container.page-container,
body.oa2-sidebar-mounted .sticky-top{
	margin-left:0!important;width:100%!important;max-width:none!important;
}
body.oa2-use-inpage-sidebar .oa2-app-frame{display:flex!important}
body[data-oa2-theme="dark"] #oa2-app-sidebar.oa2-sidebar-global,
#oa2-app-sidebar.oa2-sidebar-global[data-oa2-theme="dark"]{
	background:#1a1f27!important;color:#e5e7eb!important;
}
body[data-oa2-theme="light"] #oa2-app-sidebar.oa2-sidebar-global,
#oa2-app-sidebar.oa2-sidebar-global[data-oa2-theme="light"]{
	background:linear-gradient(180deg,#0b1f4d 0%,#002b7f 55%,#003399 100%)!important;color:#fff!important;
}
@media (max-width:900px){
	#oa2-app-sidebar.oa2-sidebar-global{width:0!important;display:none!important}
	body.oa2-sidebar-mounted,body.oa2-has-sidebar,body.oa2-use-inpage-sidebar{padding-left:0!important}
}

/* Hide Frappe Desk shell on ALL OpenAS2 pages in this bench */
body.oa2-hide-desk-chrome .sticky-top,
body.oa2-hide-desk-chrome header.navbar,
body.oa2-hide-desk-chrome .navbar,
body.oa2-hide-desk-chrome #navbar-breadcrumbs,
body.oa2-hide-desk-chrome .search-bar,
body.oa2-hide-desk-chrome #navbar-search,
body.oa2-hide-desk-chrome .announcement-widget,
body.oa2-hide-desk-chrome .layout-side-section,
body.oa2-hide-desk-chrome .body-sidebar,
body.oa2-hide-desk-chrome .body-sidebar-container,
body.oa2-hide-desk-chrome .desk-sidebar{
	display:none!important;visibility:hidden!important;height:0!important;min-height:0!important;
	max-height:0!important;overflow:hidden!important;opacity:0!important;pointer-events:none!important;
	margin:0!important;padding:0!important;border:0!important;
}
body.oa2-hide-desk-chrome{
	padding:0!important;margin:0!important;overflow:hidden!important;
}
body.oa2-hide-desk-chrome .main-section,
body.oa2-hide-desk-chrome #body,
body.oa2-hide-desk-chrome .container.page-container,
body.oa2-hide-desk-chrome .page-container,
body.oa2-hide-desk-chrome .layout-main-section-wrapper,
body.oa2-hide-desk-chrome .layout-main,
body.oa2-hide-desk-chrome .layout-main-section,
body.oa2-hide-desk-chrome .page-body,
body.oa2-hide-desk-chrome .page-content,
body.oa2-hide-desk-chrome .page-content-wrapper{
	margin:0!important;padding:0!important;max-width:none!important;width:100%!important;
	border:0!important;box-shadow:none!important;
}
body.oa2-hide-desk-chrome .oa2-dashboard-wrapper.page-container,
body.oa2-hide-desk-chrome .oa2-dashboard-wrapper .layout-main-section-wrapper,
body.oa2-hide-desk-chrome .oa2-dashboard-wrapper .layout-main-section,
body.oa2-hide-desk-chrome .oa2-dashboard-wrapper .page-body,
body.oa2-hide-desk-chrome .oa2-config-page-wrapper.page-container,
body.oa2-hide-desk-chrome .oa2-config-page-wrapper .layout-main-section-wrapper,
body.oa2-hide-desk-chrome .oa2-config-page-wrapper .layout-main-section,
body.oa2-hide-desk-chrome .oa2-config-page-wrapper .page-body,
body.oa2-hide-desk-chrome .oa2-monitor-page-wrapper.page-container,
body.oa2-hide-desk-chrome .oa2-monitor-page-wrapper .layout-main-section-wrapper,
body.oa2-hide-desk-chrome .oa2-monitor-page-wrapper .layout-main-section,
body.oa2-hide-desk-chrome .oa2-monitor-page-wrapper .page-body{
	height:100vh!important;min-height:100vh!important;max-height:100vh!important;
	height:100dvh!important;min-height:100dvh!important;max-height:100dvh!important;
	overflow:hidden!important;margin:0!important;padding:0!important;
}
body.oa2-hide-desk-chrome .oa2-home,
body.oa2-hide-desk-chrome .oa2-config-list-page,
body.oa2-hide-desk-chrome .oa2-monitor-page{
	margin:0!important;padding:0!important;height:100%!important;min-height:100%!important;max-height:100%!important;
}
body.oa2-hide-desk-chrome.oa2-use-inpage-sidebar .oa2-home,
body.oa2-hide-desk-chrome.oa2-use-inpage-sidebar .oa2-config-list-page,
body.oa2-hide-desk-chrome.oa2-use-inpage-sidebar .oa2-monitor-page,
body.oa2-hide-desk-chrome.oa2-use-inpage-sidebar .oa2-app-frame{
	height:100vh!important;min-height:100vh!important;max-height:100vh!important;
	height:100dvh!important;min-height:100dvh!important;max-height:100dvh!important;
}
body.oa2-hide-desk-chrome .page-head{display:none!important}
`;
	}

	function path_is_oa2() {
		try {
			const path = String(window.location.pathname || "").toLowerCase();
			if (path.indexOf("/app/openas2") !== -1) return true;
			if (path.indexOf("/app/as2-") !== -1) return true;
			if (path.indexOf("/app/list/as2") !== -1 || path.indexOf("/app/list/openas2") !== -1) return true;
			if (path.indexOf("/app/form/as2") !== -1 || path.indexOf("/app/form/openas2") !== -1) return true;
			const parts = path.split("/").filter(Boolean);
			if (parts[0] === "app" && parts[1] && OA2_PAGES.has(parts[1])) return true;
		} catch (e) {
			/* ignore */
		}
		return false;
	}

	function ensure_desk_chrome_css() {
		let style = document.getElementById(DESK_CHROME_CSS_ID);
		if (!style) {
			style = document.createElement("style");
			style.id = DESK_CHROME_CSS_ID;
			(document.head || document.documentElement).appendChild(style);
		}
		style.textContent = `
html.oa2-hide-desk-chrome body .sticky-top,
html.oa2-hide-desk-chrome body header.navbar,
html.oa2-hide-desk-chrome body .navbar,
html.oa2-hide-desk-chrome body #navbar-breadcrumbs,
html.oa2-hide-desk-chrome body .search-bar,
html.oa2-hide-desk-chrome body #navbar-search,
html.oa2-hide-desk-chrome body .announcement-widget,
body.oa2-hide-desk-chrome .sticky-top,
body.oa2-hide-desk-chrome header.navbar,
body.oa2-hide-desk-chrome .navbar,
body.oa2-hide-desk-chrome #navbar-breadcrumbs,
body.oa2-hide-desk-chrome .search-bar,
body.oa2-hide-desk-chrome #navbar-search,
body.oa2-hide-desk-chrome .announcement-widget,
body.oa2-hide-desk-chrome .layout-side-section,
body.oa2-hide-desk-chrome .body-sidebar,
body.oa2-hide-desk-chrome .body-sidebar-container {
	display: none !important;
	visibility: hidden !important;
	height: 0 !important;
	min-height: 0 !important;
	max-height: 0 !important;
	overflow: hidden !important;
	opacity: 0 !important;
	pointer-events: none !important;
	margin: 0 !important;
	padding: 0 !important;
	border: 0 !important;
	position: absolute !important;
	left: -9999px !important;
	top: -9999px !important;
}
html.oa2-hide-desk-chrome,
html.oa2-hide-desk-chrome body,
body.oa2-hide-desk-chrome {
	padding: 0 !important;
	margin: 0 !important;
	overflow: hidden !important;
}
html.oa2-hide-desk-chrome body .main-section,
html.oa2-hide-desk-chrome body #body,
html.oa2-hide-desk-chrome body .page-container,
html.oa2-hide-desk-chrome body .container.page-container,
html.oa2-hide-desk-chrome body .layout-main-section-wrapper,
html.oa2-hide-desk-chrome body .layout-main-section,
html.oa2-hide-desk-chrome body .page-body,
body.oa2-hide-desk-chrome .main-section,
body.oa2-hide-desk-chrome #body,
body.oa2-hide-desk-chrome .page-container,
body.oa2-hide-desk-chrome .container.page-container,
body.oa2-hide-desk-chrome .layout-main-section-wrapper,
body.oa2-hide-desk-chrome .layout-main-section,
body.oa2-hide-desk-chrome .page-body {
	margin: 0 !important;
	padding: 0 !important;
	max-width: none !important;
	width: 100% !important;
	border: 0 !important;
}
html.oa2-hide-desk-chrome body .oa2-dashboard-wrapper.page-container,
html.oa2-hide-desk-chrome body .oa2-dashboard-wrapper .layout-main-section-wrapper,
html.oa2-hide-desk-chrome body .oa2-dashboard-wrapper .layout-main-section,
html.oa2-hide-desk-chrome body .oa2-dashboard-wrapper .page-body,
html.oa2-hide-desk-chrome body .oa2-config-page-wrapper.page-container,
html.oa2-hide-desk-chrome body .oa2-config-page-wrapper .layout-main-section-wrapper,
html.oa2-hide-desk-chrome body .oa2-config-page-wrapper .layout-main-section,
html.oa2-hide-desk-chrome body .oa2-config-page-wrapper .page-body,
html.oa2-hide-desk-chrome body .oa2-monitor-page-wrapper.page-container,
html.oa2-hide-desk-chrome body .oa2-monitor-page-wrapper .layout-main-section-wrapper,
html.oa2-hide-desk-chrome body .oa2-monitor-page-wrapper .layout-main-section,
html.oa2-hide-desk-chrome body .oa2-monitor-page-wrapper .page-body,
body.oa2-hide-desk-chrome .oa2-dashboard-wrapper.page-container,
body.oa2-hide-desk-chrome .oa2-dashboard-wrapper .layout-main-section-wrapper,
body.oa2-hide-desk-chrome .oa2-dashboard-wrapper .layout-main-section,
body.oa2-hide-desk-chrome .oa2-dashboard-wrapper .page-body,
body.oa2-hide-desk-chrome .oa2-config-page-wrapper.page-container,
body.oa2-hide-desk-chrome .oa2-config-page-wrapper .layout-main-section-wrapper,
body.oa2-hide-desk-chrome .oa2-config-page-wrapper .layout-main-section,
body.oa2-hide-desk-chrome .oa2-config-page-wrapper .page-body,
body.oa2-hide-desk-chrome .oa2-monitor-page-wrapper.page-container,
body.oa2-hide-desk-chrome .oa2-monitor-page-wrapper .layout-main-section-wrapper,
body.oa2-hide-desk-chrome .oa2-monitor-page-wrapper .layout-main-section,
body.oa2-hide-desk-chrome .oa2-monitor-page-wrapper .page-body {
	height: 100vh !important;
	min-height: 100vh !important;
	max-height: 100vh !important;
	height: 100dvh !important;
	min-height: 100dvh !important;
	max-height: 100dvh !important;
	overflow: hidden !important;
	margin: 0 !important;
	padding: 0 !important;
}
html.oa2-hide-desk-chrome body .oa2-home,
html.oa2-hide-desk-chrome body .oa2-config-list-page,
html.oa2-hide-desk-chrome body .oa2-monitor-page,
html.oa2-hide-desk-chrome body .oa2-app-frame,
body.oa2-hide-desk-chrome .oa2-home,
body.oa2-hide-desk-chrome .oa2-config-list-page,
body.oa2-hide-desk-chrome .oa2-monitor-page,
body.oa2-hide-desk-chrome .oa2-app-frame {
	margin: 0 !important;
	padding: 0 !important;
	height: 100vh !important;
	min-height: 100vh !important;
	max-height: 100vh !important;
	height: 100dvh !important;
	min-height: 100dvh !important;
	max-height: 100dvh !important;
}
html.oa2-hide-desk-chrome body .page-head,
body.oa2-hide-desk-chrome .page-head {
	display: none !important;
}
`;
	}

	function hide_desk_chrome_nodes() {
		const nodes = document.querySelectorAll(
			".sticky-top, header.navbar, .navbar.navbar-expand, nav.navbar, #navbar-breadcrumbs, .search-bar, #navbar-search, .announcement-widget"
		);
		nodes.forEach(function (el) {
			el.style.setProperty("display", "none", "important");
			el.style.setProperty("visibility", "hidden", "important");
			el.style.setProperty("height", "0", "important");
			el.style.setProperty("max-height", "0", "important");
			el.style.setProperty("overflow", "hidden", "important");
			el.style.setProperty("opacity", "0", "important");
			el.style.setProperty("pointer-events", "none", "important");
			el.setAttribute("data-oa2-chrome-hidden", "1");
		});
	}

	function restore_desk_chrome_nodes() {
		document.querySelectorAll('[data-oa2-chrome-hidden="1"]').forEach(function (el) {
			el.style.removeProperty("display");
			el.style.removeProperty("visibility");
			el.style.removeProperty("height");
			el.style.removeProperty("max-height");
			el.style.removeProperty("overflow");
			el.style.removeProperty("opacity");
			el.style.removeProperty("pointer-events");
			el.removeAttribute("data-oa2-chrome-hidden");
		});
	}

	function apply_desk_chrome_visibility() {
		/* Reverted: do not hide Frappe desk chrome */
		return;
	}

	function start_desk_chrome_observer() {
		return;
	}

	function ensure_desk_chrome_css() {
		return;
	}

	function path_is_oa2() {
		return false;
	}

	function hide_desk_chrome_nodes() {
		return;
	}

	function restore_desk_chrome_nodes() {
		return;
	}

	function clear_global_layout() {
		document.body.classList.remove("oa2-sidebar-mounted");
		document.body.classList.remove("oa2-using-global-sidebar");
		document.body.style.removeProperty("padding-left");
	}

	function apply_oa2_full_bleed() {
		/* Same full-viewport treatment Home applies in openas2_dashboard.js —
		 * run for every OA2 page so Frappe .container / empty col-lg-2 cannot
		 * leave a blank strip on the right. Scoped to OA2 wrappers + body flags.
		 * List/Form (Logs, Settings) rely on body.oa2-has-sidebar CSS only —
		 * do not set inline styles on generic .page-container (leaks to Desk). */
		document.body.classList.add("no-sidebar");
		document.body.classList.add("oa2-has-sidebar");

		document.querySelectorAll(
			".oa2-dashboard-wrapper, .oa2-config-page-wrapper, .oa2-monitor-page-wrapper"
		).forEach(function (wrap) {
			wrap.style.setProperty("width", "100%", "important");
			wrap.style.setProperty("max-width", "none", "important");
			wrap.style.setProperty("margin-left", "0", "important");
			wrap.style.setProperty("margin-right", "0", "important");
			wrap.style.setProperty("padding-left", "0", "important");
			wrap.style.setProperty("padding-right", "0", "important");
			wrap.querySelectorAll(".layout-side-section").forEach(function (side) {
				side.classList.add("hide-sidebar");
				side.style.setProperty("display", "none", "important");
				side.style.setProperty("width", "0", "important");
			});
			wrap.querySelectorAll(
				".layout-main, .layout-main-section-wrapper, .layout-main-section, .page-body, .oa2-config-shell, .oa2-monitor-shell, .oa2-home-shell"
			).forEach(function (node) {
				node.style.setProperty("width", "100%", "important");
				node.style.setProperty("max-width", "none", "important");
				node.style.setProperty("margin-left", "0", "important");
				node.style.setProperty("margin-right", "0", "important");
			});
		});
	}

	function clear_oa2_full_bleed() {
		document.body.classList.remove("no-sidebar");
	}

	function show_inpage_sidebar() {
		clear_global_layout();
		document.body.classList.add("oa2-has-sidebar");
		document.body.classList.add("oa2-use-inpage-sidebar");
		document.body.classList.remove("oa2-sidebar-mounted");
		document.body.classList.remove("oa2-using-global-sidebar");
		apply_oa2_full_bleed();
		const el = document.getElementById(SIDEBAR_ID);
		if (el) {
			el.style.setProperty("display", "none", "important");
		}
		refresh_inpage_sidebars();
	}

	function is_dashboard_route() {
		const route = get_route();
		if (route && route[0] === DASHBOARD) return true;
		const parts = path_parts();
		return parts.indexOf(DASHBOARD) !== -1;
	}

	function sidebar_is_painted(el) {
		if (!el || !document.body.contains(el)) return false;
		const style = window.getComputedStyle(el);
		if (style.display === "none" || style.visibility === "hidden" || style.opacity === "0") {
			return false;
		}
		const rect = el.getBoundingClientRect();
		return rect.width >= 180 && rect.height >= 120;
	}

	function apply_theme(el) {
		const theme = get_theme();
		if (el) el.setAttribute("data-oa2-theme", theme);
		if (document.body) {
			document.body.setAttribute("data-oa2-theme", theme);
		}
		try {
			document.documentElement.setAttribute("data-oa2-theme", theme);
		} catch (e) {
			/* ignore */
		}
		document.querySelectorAll(".oa2-sidebar-inpage, .oa2-home, .oa2-app-frame").forEach(function (node) {
			node.setAttribute("data-oa2-theme", theme);
		});
	}

	function ensure_sidebar() {
		ensure_force_css();
		let el = document.getElementById(SIDEBAR_ID);
		if (!el) {
			el = document.createElement("aside");
			el.id = SIDEBAR_ID;
			el.className = "oa2-sidebar oa2-sidebar-global";
			el.setAttribute("aria-label", "EDI AS2");
			document.body.appendChild(el);

			el.addEventListener("click", function (e) {
				const btn = e.target.closest("[data-oa2-route]");
				if (!btn) return;
				e.preventDefault();
				navigate_oa2_route(btn.getAttribute("data-oa2-route"));
			});
		}
		el.innerHTML = sidebar_html();
		apply_theme(el);
		return el;
	}

	function show_sidebar() {
		ensure_force_css();
		document.body.style.setProperty("padding-left", "0", "important");

		// Prefer the in-page EDI AS2 panel whenever the page embeds it
		// (Home, Configuration, Partners, Certificates — light + dark).
		if (document.querySelector(".oa2-sidebar-inpage")) {
			show_inpage_sidebar();
			return;
		}

		// Fallback: fixed global sidebar for pages without in-page markup
		document.body.classList.remove("oa2-use-inpage-sidebar");

		let el = null;
		try {
			el = ensure_sidebar();
		} catch (err) {
			console.error("openas2 sidebar mount failed", err);
			return;
		}
		if (!el) return;

		el.style.removeProperty("display");
		el.style.setProperty("display", "flex", "important");
		el.style.setProperty("visibility", "visible", "important");
		el.style.setProperty("opacity", "1", "important");
		el.style.setProperty("z-index", "10000", "important");
		el.style.setProperty("position", "fixed", "important");
		el.style.setProperty("top", "0", "important");
		el.style.setProperty("left", "0", "important");
		el.style.setProperty("bottom", "0", "important");
		el.style.setProperty("width", "248px", "important");
		el.style.setProperty("height", "100vh", "important");
		el.style.setProperty("min-height", "100vh", "important");
		el.style.setProperty("max-height", "none", "important");
		el.style.setProperty("bottom", "0", "important");
		el.style.setProperty(
			"background",
			get_theme() === "dark"
				? "#1a1f27"
				: "linear-gradient(180deg,#0b1f4d 0%,#002b7f 55%,#003399 100%)",
			"important"
		);
		el.style.setProperty("color", "#fff", "important");
		el.style.setProperty("pointer-events", "auto", "important");

		document.body.classList.add("oa2-has-sidebar");
		document.body.classList.add("oa2-using-global-sidebar");
		document.body.classList.add("oa2-sidebar-mounted");
		apply_theme(el);
		apply_oa2_full_bleed();

		document.querySelectorAll(".oa2-sidebar-inpage").forEach(function (node) {
			node.style.setProperty("display", "none", "important");
		});

		requestAnimationFrame(function () {
			if (!is_oa2_context() || document.querySelector(".oa2-sidebar-inpage")) return;
			const node = document.getElementById(SIDEBAR_ID);
			if (!node) return;
			node.style.setProperty("display", "flex", "important");
			document.body.classList.add("oa2-sidebar-mounted");
			document.body.classList.remove("oa2-use-inpage-sidebar");
		});
		setTimeout(function () {
			if (!is_oa2_context() || document.querySelector(".oa2-sidebar-inpage")) return;
			const node = document.getElementById(SIDEBAR_ID);
			if (!node) return;
			node.style.setProperty("display", "flex", "important");
			document.body.classList.add("oa2-has-sidebar");
			document.body.classList.add("oa2-using-global-sidebar");
			document.body.classList.add("oa2-sidebar-mounted");
			document.body.classList.remove("oa2-use-inpage-sidebar");
		}, 150);
	}

	function hide_sidebar() {
		if (is_oa2_context()) {
			show_sidebar();
			return;
		}
		const el = document.getElementById(SIDEBAR_ID);
		if (el) {
			el.style.setProperty("display", "none", "important");
		}
		document.body.classList.remove("oa2-has-sidebar");
		document.body.classList.remove("oa2-use-inpage-sidebar");
		clear_global_layout();
		clear_oa2_full_bleed();
		document.querySelectorAll(".oa2-sidebar-inpage").forEach(function (node) {
			node.style.removeProperty("display");
		});
	}

	function sync() {
		if (needs_dashboard_redirect()) {
			open_dashboard();
			return;
		}
		ensure_force_css();
		if (is_oa2_context()) {
			show_sidebar();
		} else {
			hide_sidebar();
		}
	}

	function boot() {
		ensure_force_css();
		sync();
		if (window.__oa2_sidebar_bound) return;
		window.__oa2_sidebar_bound = true;

		document.addEventListener("click", function (e) {
			const btn = e.target.closest(".oa2-sidebar-inpage [data-oa2-route], .oa2-sidebar-inpage [data-route]");
			if (!btn) return;
			e.preventDefault();
			navigate_oa2_route(btn.getAttribute("data-oa2-route") || btn.getAttribute("data-route"));
		});

		if (frappe.router && frappe.router.on) {
			frappe.router.on("change", function () {
				sync();
				setTimeout(sync, 50);
				setTimeout(sync, 200);
			});
		}
		if (window.jQuery) {
			jQuery(document).on("page-change", function () {
				sync();
				setTimeout(sync, 50);
				setTimeout(sync, 200);
			});
		}

		window.addEventListener("storage", function (e) {
			if (e.key === THEME_KEY) {
				const el = document.getElementById(SIDEBAR_ID);
				if (el) apply_theme(el);
				refresh_inpage_sidebars();
			}
		});

		const obs = new MutationObserver(function () {
			const el = document.getElementById(SIDEBAR_ID);
			if (el && document.body.classList.contains("oa2-has-sidebar")) {
				apply_theme(el);
			}
		});
		try {
			obs.observe(document.documentElement, {
				attributes: true,
				attributeFilter: ["data-oa2-theme"],
			});
			obs.observe(document.body, {
				attributes: true,
				attributeFilter: ["data-oa2-theme", "class"],
			});
		} catch (e) {
			/* ignore */
		}

		let tries = 0;
		const timer = setInterval(function () {
			tries += 1;
			sync();
			if (tries > 40) clearInterval(timer);
		}, 200);
	}

	if (needs_dashboard_redirect()) open_dashboard();

	if (window.jQuery) {
		jQuery(document).on("app_ready", boot);
		jQuery(function () {
			if (window.frappe && frappe.boot) boot();
			else boot();
		});
	} else {
		document.addEventListener("DOMContentLoaded", boot);
		window.addEventListener("load", boot);
	}

	window.openas2_manager = window.openas2_manager || {};
	window.openas2_manager.sync_sidebar = sync;
	window.openas2_manager.apply_desk_chrome = apply_desk_chrome_visibility;
	window.openas2_manager.inpage_sidebar_html = inpage_sidebar_markup;
	window.openas2_manager.apply_sidebar_theme = function () {
		const el = document.getElementById(SIDEBAR_ID);
		if (el) apply_theme(el);
		refresh_inpage_sidebars();
		sync();
	};
})();
