// Loads the AI Assistant after the existing header is on the page.
// New file so a cached copy of the older layout script cannot hide the button.
(function () {
	"use strict";

	function contrast_css() {
		if (document.getElementById("oa2-mon-view-contrast")) return;
		var el = document.createElement("style");
		el.id = "oa2-mon-view-contrast";
		el.textContent = [
			".oa2-mon-view,.oa2-mon-view *{",
			"color:#ffffff !important;",
			"-webkit-text-fill-color:#ffffff !important;",
			"opacity:1 !important;",
			"}",
			"button.oa2-mon-view,a.oa2-mon-view{",
			"display:inline-block;",
			"background:#2563eb !important;",
			"color:#ffffff !important;",
			"-webkit-text-fill-color:#ffffff !important;",
			"border:0 !important;",
			"border-radius:6px !important;",
			"padding:0.18rem 0.6rem !important;",
			"font-weight:800 !important;",
			"font-size:0.78rem !important;",
			"line-height:1.2 !important;",
			"text-decoration:none !important;",
			"cursor:pointer !important;",
			"}",
			".oa2-home[data-oa2-theme=\"dark\"] .oa2-view-all,",
			".oa2-home[data-oa2-theme=\"dark\"] .oa2-view-all:visited,",
			".oa2-home[data-oa2-theme=\"dark\"] .oa2-table a,",
			".oa2-home[data-oa2-theme=\"dark\"] .oa2-table a:visited,",
			".oa2-home[data-oa2-theme=\"dark\"] .oa2-view-link,",
			".oa2-home[data-oa2-theme=\"dark\"] .oa2-view-link:visited{",
			"color:#7dd3fc !important;",
			"-webkit-text-fill-color:#7dd3fc !important;",
			"font-weight:800 !important;",
			"text-decoration:underline !important;",
			"opacity:1 !important;",
			"}",
		].join("");
		document.head.appendChild(el);
	}

	function place() {
		contrast_css();
		if (!window.frappe || !frappe.get_route) return;
		var route = "";
		try {
			route = (frappe.get_route() || []).join("/").toLowerCase();
		} catch (e) {
			route = "";
		}
		var path = (window.location.pathname || "").toLowerCase();
		var onOpenAS2 =
			route.indexOf("openas2") !== -1 ||
			route.indexOf("as2 ") === 0 ||
			path.indexOf("/app/openas2") !== -1 ||
			path.indexOf("/app/as2") !== -1;
		if (!onOpenAS2) return;

		var bar = document.getElementById("oa2-shared-header-controls");
		var host =
			bar ||
			document.querySelector(
				".oa2-home-header-actions, .oa2-monitor-header-actions, .oa2-config-header-actions"
			);
		if (!host) return;
		var existing = host.querySelector(".oa2-ai-open");
		if (existing) {
			if (!existing.querySelector(".oa2-ai-spark")) {
				existing.innerHTML =
					'<svg class="oa2-ai-spark" viewBox="0 0 24 24" aria-hidden="true" focusable="false">' +
					'<path fill="currentColor" d="M12 2.4l1.05 5.5 5.5 1.05-5.5 1.05L12 15.5l-1.05-5.5-5.5-1.05 5.5-1.05L12 2.4z"/>' +
					'<path fill="currentColor" d="M18.1 14.1l.48 1.9 1.9.48-1.9.48-.48 1.9-.48-1.9-1.9-.48 1.9-.48.48-1.9z"/>' +
					"</svg><span>Copilot</span>";
				existing.setAttribute("aria-label", "OpenAS2 Copilot");
				existing.removeAttribute("style");
			}
			return;
		}
		var btn = document.createElement("button");
		btn.type = "button";
		btn.className = "oa2-ai-open";
		btn.innerHTML =
			'<svg class="oa2-ai-spark" viewBox="0 0 24 24" aria-hidden="true" focusable="false">' +
			'<path fill="currentColor" d="M12 2.4l1.05 5.5 5.5 1.05-5.5 1.05L12 15.5l-1.05-5.5-5.5-1.05 5.5-1.05L12 2.4z"/>' +
			'<path fill="currentColor" d="M18.1 14.1l.48 1.9 1.9.48-1.9.48-.48 1.9-.48-1.9-1.9-.48 1.9-.48.48-1.9z"/>' +
			"</svg><span>Copilot</span>";
		btn.setAttribute("aria-label", "OpenAS2 Copilot");
		host.insertBefore(btn, host.firstChild);
	}

	function boot() {
		var ver = "20261009stack";
		var css = document.querySelector("link[data-oa2-ai-css]");
		if (!css) {
			css = document.createElement("link");
			css.rel = "stylesheet";
			css.setAttribute("data-oa2-ai-css", ver);
			document.head.appendChild(css);
		}
		css.href = "/assets/openas2_manager/css/openas2_assistant.css?v=" + ver;
		if (!document.querySelector('script[data-oa2-ai-js="' + ver + '"]')) {
			var script = document.createElement("script");
			script.src = "/assets/openas2_manager/js/openas2_assistant.js?v=" + ver;
			script.setAttribute("data-oa2-ai-js", ver);
			document.body.appendChild(script);
		}
		place();
		var tries = 0;
		var timer = setInterval(function () {
			place();
			tries += 1;
			if (tries > 20 || document.querySelector(".oa2-ai-open")) clearInterval(timer);
		}, 300);
	}

	if (window.jQuery) {
		jQuery(function () {
			boot();
		});
		jQuery(document).on("app_ready page-change", boot);
	} else {
		document.addEventListener("DOMContentLoaded", boot);
	}
})();
