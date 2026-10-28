// Copyright (c) 2026, Lakshana and contributors
// AI Assistant panel. Does not restyle existing OpenAS2 pages.

(function () {
	"use strict";

	const CHAT = "openas2_manager.openas2.assistant.chat";
	const CONFIRM = "openas2_manager.openas2.assistant.confirm_assistant_action";
	const CANCEL = "openas2_manager.openas2.assistant.cancel_assistant_action";
	const ANALYZE = "openas2_manager.openas2.assistant.analyze_transaction";
	const HISTORY_LIST = "openas2_manager.openas2.assistant_history.list_conversations";
	const HISTORY_GET = "openas2_manager.openas2.assistant_history.get_conversation";
	const HISTORY_RECORD = "openas2_manager.openas2.assistant_history.record_turn";
	const HISTORY_DELETE = "openas2_manager.openas2.assistant_history.delete_conversation";
	const HISTORY_CLEAR = "openas2_manager.openas2.assistant_history.clear_conversation_context";
	const UI_VER = "20261009stack";

	const SPARK_ICON =
		'<svg class="oa2-ai-spark" viewBox="0 0 24 24" aria-hidden="true" focusable="false">' +
		'<path fill="currentColor" d="M12 2.4l1.05 5.5 5.5 1.05-5.5 1.05L12 15.5l-1.05-5.5-5.5-1.05 5.5-1.05L12 2.4z"/>' +
		'<path fill="currentColor" d="M18.1 14.1l.48 1.9 1.9.48-1.9.48-.48 1.9-.48-1.9-1.9-.48 1.9-.48.48-1.9z"/>' +
		"</svg>";

	const SUGGESTIONS = [
		{ label: "Show failed EDI transactions", prompt: "Show failed EDI transactions", hint: "Transactions" },
		{ label: "Find a partner", prompt: "Find a partner", hint: "Partners" },
		{ label: "Analyze this transaction", prompt: "Analyze this transaction", hint: "Analyze" },
		{ label: "Check recent activity", prompt: "Check recent activity", hint: "Activity" },
		{ label: "Show configuration", prompt: "Show configuration", hint: "Configuration" },
		{ label: "Create a partner", prompt: "Create a partner", hint: "Create" },
	];

	const QUICK_ACTIONS = [
		{ label: "Analyze", prompt: "Analyze " },
		{ label: "Search", prompt: "Find " },
		{ label: "Create", prompt: "Create " },
		{ label: "Explain", prompt: "Explain " },
	];

	const LOADING_MESSAGE = "Thinking…";

	const LINK_LABELS = {
		partner: "Partner",
		partnership: "Partnership",
		certificate: "Certificate",
		configuration: "Configuration",
		edi: "EDI Transaction",
		log: "Log",
	};

	const OPEN_LABELS = {
		partner: "Open Partner",
		partnership: "Open Partnership",
		certificate: "Open Certificate",
		configuration: "Open Configuration",
		edi: "Open Transaction",
		log: "Open Log",
	};

	const ANALYSIS_LABELS = [
		"Transaction summary",
		"Issue",
		"Evidence",
		"Cause",
		"Impact",
		"Suggested fix",
		"Related data",
		"Related logs",
	];

	function esc(value) {
		return frappe.utils.escape_html(value == null ? "" : String(value));
	}

	function context() {
		const route = (frappe.get_route && frappe.get_route()) || [];
		const ctx = { page: route.join("/") };
		if (String(route[0] || "") === "Form" && route[1] === "AS2 Partner" && route[2]) {
			ctx.partner = route[2];
		}
		if (String(route[0] || "") === "Form" && route[1] === "OpenAS2 Instance" && route[2]) {
			ctx.configuration = route[2];
		}
		if (String(route[0] || "") === "Form" && route[1] === "AS2 Certificate" && route[2]) {
			ctx.certificate = route[2];
		}
		if (String(route[0] || "") === "Form" && route[1] === "OpenAS2 Partnership" && route[2]) {
			ctx.partnership = route[2];
		}
		const view = document.querySelector(".oa2-partnership-view");
		if (view && !view.hasAttribute("hidden")) {
			const id = view.querySelector(".oa2-ps-partner-id");
			const label = view.querySelector(".oa2-ps-partner-name");
			if (id && id.textContent.trim()) ctx.partner = id.textContent.trim();
			if (label && label.textContent.trim()) ctx.partner_label = label.textContent.trim();
		}
		const edi = document.querySelector(".oa2-edi-modal.is-open");
		if (edi && edi.getAttribute("data-oa2-edi")) {
			ctx.edi_document = edi.getAttribute("data-oa2-edi");
		}
		return ctx;
	}

	function theme() {
		try {
			return localStorage.getItem("oa2-dashboard-theme") === "dark" ? "dark" : "light";
		} catch (e) {
			return "light";
		}
	}

	function format_text(text) {
		return esc(text)
			.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
			.replace(/\n/g, "<br>");
	}

	function parse_analysis_sections(text) {
		const lines = String(text || "").split("\n");
		const sections = [];
		let current = null;
		const labelSet = {};
		ANALYSIS_LABELS.forEach(function (label) {
			labelSet[label.toLowerCase()] = label;
		});

		lines.forEach(function (raw) {
			const line = raw.trimEnd();
			const key = line.trim().toLowerCase();
			if (labelSet[key]) {
				current = { title: labelSet[key], body: [] };
				sections.push(current);
				return;
			}
			if (!current) {
				current = { title: "Failure Analysis", body: [] };
				sections.push(current);
			}
			if (line.trim()) current.body.push(line);
		});

		return sections.filter(function (section) {
			return section.body.length || section.title === "Failure Analysis";
		});
	}

	function welcome_html() {
		const chips = SUGGESTIONS.map(function (item) {
			return (
				'<button type="button" class="oa2-ai-suggest" data-oa2-prompt="' +
				esc(item.prompt) +
				'">' +
				'<span class="oa2-ai-suggest-hint">' +
				esc(item.hint || "Ask") +
				"</span>" +
				'<span class="oa2-ai-suggest-label">' +
				esc(item.label) +
				"</span></button>"
			);
		}).join("");
		return (
			'<div class="oa2-ai-welcome">' +
			'<div class="oa2-ai-welcome-icon" aria-hidden="true">' +
			SPARK_ICON +
			"</div>" +
			'<h3 class="oa2-ai-welcome-title">Your OpenAS2 Copilot</h3>' +
			'<p class="oa2-ai-welcome-sub">Ask about partners, certificates, configurations, EDI transactions, monitoring, or logs.</p>' +
			'<div class="oa2-ai-suggests" role="group" aria-label="Suggested questions">' +
			chips +
			"</div></div>"
		);
	}

	function quick_actions_html() {
		return (
			'<div class="oa2-ai-quick" role="group" aria-label="Quick actions">' +
			QUICK_ACTIONS.map(function (item) {
				return (
					'<button type="button" class="oa2-ai-chip" data-oa2-chip="' +
					esc(item.prompt) +
					'">' +
					esc(item.label) +
					"</button>"
				);
			}).join("") +
			"</div>"
		);
	}

	function ensure_panel() {
		let panel = document.querySelector(".oa2-ai-panel");
		if (panel) {
			panel.setAttribute("data-oa2-theme", theme());
			ensure_history_chrome(panel);
			refresh_copy(panel);
			return panel;
		}
		panel = document.createElement("div");
		panel.className = "oa2-ai-panel";
		panel.setAttribute("data-oa2-theme", theme());
		panel.setAttribute("role", "dialog");
		panel.setAttribute("aria-label", "OpenAS2 Copilot");
		panel.innerHTML =
			'<header class="oa2-ai-header"><div class="oa2-ai-brand">' +
			'<span class="oa2-ai-mark" aria-hidden="true">' +
			SPARK_ICON +
			'</span><div class="oa2-ai-header-text">' +
			"<h2>OpenAS2 Copilot</h2>" +
			'<p class="oa2-ai-header-sub">Your intelligent OpenAS2 assistant</p></div></div>' +
			'<div class="oa2-ai-header-actions">' +
			'<button type="button" class="oa2-ai-new">New chat</button>' +
			'<button type="button" class="oa2-ai-history-toggle" aria-expanded="false">History</button>' +
			'<button type="button" class="oa2-ai-close" aria-label="Close">×</button></div></header>' +
			'<div class="oa2-ai-history" hidden>' +
			'<div class="oa2-ai-history-list" role="list"></div>' +
			"</div>" +
			'<div class="oa2-ai-body">' +
			welcome_html() +
			'<div class="oa2-ai-log" aria-live="polite"></div>' +
			"</div>" +
			'<div class="oa2-ai-composer">' +
			quick_actions_html() +
			'<form class="oa2-ai-form">' +
			'<textarea rows="1" placeholder="Ask anything about OpenAS2…" aria-label="Message"></textarea>' +
			'<button type="submit" class="oa2-ai-send" aria-label="Send" title="Send">' +
			'<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path fill="currentColor" d="M5 12h11.2l-3.8-3.8 1.4-1.4L20 12l-6.2 5.2-1.4-1.4 3.8-3.8H5z"/></svg>' +
			"</button>" +
			"</form>" +
			'<p class="oa2-ai-hint">Enter to send · Shift+Enter for a new line</p>' +
			"</div>";
		document.body.appendChild(panel);
		refresh_copy(panel);
		return panel;
	}

	function refresh_copy(panel) {
		if (!panel) return;
		panel.setAttribute("aria-label", "OpenAS2 Copilot");
		const h2 = panel.querySelector(".oa2-ai-header h2");
		if (h2) h2.textContent = "OpenAS2 Copilot";
		const sub = panel.querySelector(".oa2-ai-header-sub");
		if (sub) sub.textContent = "Your intelligent OpenAS2 assistant";
		const input = panel.querySelector(".oa2-ai-form textarea");
		if (input && !input.value) input.setAttribute("placeholder", "Ask anything about OpenAS2…");
		const text = panel.querySelector(".oa2-ai-header-text");
		if (text && !panel.querySelector(".oa2-ai-brand")) {
			const brand = document.createElement("div");
			brand.className = "oa2-ai-brand";
			const mark = document.createElement("span");
			mark.className = "oa2-ai-mark";
			mark.setAttribute("aria-hidden", "true");
			mark.innerHTML = SPARK_ICON;
			text.parentNode.insertBefore(brand, text);
			brand.appendChild(mark);
			brand.appendChild(text);
		}
		const welcome = panel.querySelector(".oa2-ai-welcome");
		const welcomeTitle = welcome && welcome.querySelector(".oa2-ai-welcome-title");
		if (welcome && (!welcomeTitle || welcomeTitle.textContent !== "Your OpenAS2 Copilot")) {
			welcome.outerHTML = welcome_html();
		}
	}

	function ensure_history_chrome(panel) {
		if (!panel.querySelector(".oa2-ai-header-actions")) {
			const close = panel.querySelector(".oa2-ai-close");
			const actions = document.createElement("div");
			actions.className = "oa2-ai-header-actions";
			actions.innerHTML =
				'<button type="button" class="oa2-ai-new">New chat</button>' +
				'<button type="button" class="oa2-ai-history-toggle" aria-expanded="false">History</button>';
			if (close && close.parentNode) {
				close.parentNode.insertBefore(actions, close);
				actions.appendChild(close);
			}
		}
		if (!panel.querySelector(".oa2-ai-history")) {
			const history = document.createElement("div");
			history.className = "oa2-ai-history";
			history.setAttribute("hidden", "");
			history.innerHTML = '<div class="oa2-ai-history-list" role="list"></div>';
			const body = panel.querySelector(".oa2-ai-body");
			if (body) panel.insertBefore(history, body);
		}
	}

	function mark_chatting(panel) {
		panel.classList.add("has-chat");
		const welcome = panel.querySelector(".oa2-ai-welcome");
		if (welcome) welcome.setAttribute("hidden", "");
	}

	function set_busy(panel, busy) {
		if (!panel) return;
		panel.classList.toggle("is-busy", !!busy);
		const sendBtn = panel.querySelector(".oa2-ai-send");
		const input = panel.querySelector("textarea");
		if (sendBtn) sendBtn.disabled = !!busy;
		if (input) input.disabled = !!busy;
		panel.querySelectorAll(".oa2-ai-suggest, .oa2-ai-chip, .oa2-ai-new, .oa2-ai-history-toggle, .oa2-ai-history-item, .oa2-ai-history-delete").forEach(function (el) {
			el.disabled = !!busy;
		});
	}

	function scroll_log(panel) {
		const log = panel && panel.querySelector(".oa2-ai-log");
		if (log) log.scrollTop = log.scrollHeight;
	}

	function go_route(page, options) {
		frappe.route_options = options || {};
		try {
			frappe.set_route(page);
		} catch (err) {
			window.location.href = "/app/" + String(page).toLowerCase().replace(/\s+/g, "-");
		}
	}

	function open_record(link) {
		if (!link || !link.type) return;
		const name = link.name || "";
		if (window.console && console.debug) {
			console.debug("openas2 assistant navigate", link);
		}
		if (link.type === "partner") {
			go_route("openas2-partners", { oa2_open_partner: name });
			return;
		}
		if (link.type === "partnership") {
			go_route("openas2-partners", {
				oa2_open_partnership: name,
				oa2_open_partner: link.partner || "",
			});
			return;
		}
		if (link.type === "certificate") {
			go_route("openas2-certificates", { oa2_open_certificate: name });
			return;
		}
		if (link.type === "configuration") {
			go_route("openas2-configuration", { oa2_open_configuration: name });
			return;
		}
		if (link.type === "edi") {
			go_route("openas2-messages", { oa2_open_edi: name, tab: "transactions" });
			return;
		}
		if (link.type === "log") {
			if (link.edi) {
				go_route("openas2-messages", { oa2_open_edi: link.edi, tab: "transactions" });
				return;
			}
			go_route("openas2-logs", {
				oa2_search: link.search || name,
				oa2_level: "Error",
			});
		}
	}

	function format_when(value) {
		if (!value) return "";
		const text = String(value);
		try {
			return frappe.datetime.str_to_user ? frappe.datetime.str_to_user(text) : text;
		} catch (e) {
			return text;
		}
	}

	function split_title(link) {
		const raw = String(link.title || link.name || "Open");
		const parts = raw.split(/\s*[—–-]\s*/);
		if (link.type === "edi" && parts.length >= 2) {
			return { primary: parts.slice(1).join(" — ").trim() || raw, badge: parts[0].trim() };
		}
		return { primary: raw, badge: "" };
	}

	function status_tone(meta) {
		const s = String(meta || "").toLowerCase();
		if (!s) return "";
		if (/(fail|error|stopped|revoked)/.test(s)) return "is-failed";
		if (/(success|active|received|sent|applied)/.test(s)) return "is-success";
		if (/(pending|draft|warn|duplicate)/.test(s)) return "is-warn";
		return "";
	}

	function links_box(links, heading) {
		if (!links || !links.length) return null;
		const box = document.createElement("div");
		box.className = "oa2-ai-links";
		if (heading) {
			const h = document.createElement("div");
			h.className = "oa2-ai-links-heading";
			h.textContent = heading;
			box.appendChild(h);
		}
		links.forEach(function (link) {
			if (!link || !link.type) return;
			const btn = document.createElement("button");
			btn.type = "button";
			const tone = status_tone(link.meta);
			btn.className =
				"oa2-ai-link oa2-ai-link-" +
				esc(link.type) +
				(tone ? " " + tone : "");
			btn.setAttribute("data-oa2-link-type", link.type);
			btn.setAttribute("data-oa2-link-name", link.name || "");
			btn.setAttribute("title", (OPEN_LABELS[link.type] || "Open") + " · " + (link.name || ""));

			const kind = document.createElement("span");
			kind.className = "oa2-ai-link-kind";
			kind.textContent = LINK_LABELS[link.type] || link.type;
			btn.appendChild(kind);

			const parsed = split_title(link);
			const badgeBits = [parsed.badge, link.meta].filter(Boolean);
			if (badgeBits.length) {
				const badge = document.createElement("span");
				badge.className = "oa2-ai-link-badge";
				badge.textContent = badgeBits.join(" • ");
				btn.appendChild(badge);
			}

			const nameEl = document.createElement("span");
			nameEl.className = "oa2-ai-link-name";
			nameEl.textContent = parsed.primary;
			btn.appendChild(nameEl);

			if (link.subtitle) {
				const sub = document.createElement("span");
				sub.className = "oa2-ai-link-sub";
				sub.textContent = link.subtitle;
				btn.appendChild(sub);
			}
			const when = format_when(link.when);
			if (when) {
				const meta = document.createElement("span");
				meta.className = "oa2-ai-link-meta";
				meta.textContent = when;
				btn.appendChild(meta);
			}

			const go = document.createElement("span");
			go.className = "oa2-ai-link-go";
			go.textContent = "Open";
			btn.appendChild(go);

			btn.addEventListener("click", function (event) {
				event.preventDefault();
				event.stopPropagation();
				open_record(link);
			});
			box.appendChild(btn);
		});
		return box.querySelector(".oa2-ai-link") ? box : null;
	}

	function analysis_box(text, links) {
		const wrap = document.createElement("div");
		wrap.className = "oa2-ai-analysis";
		const heading = document.createElement("div");
		heading.className = "oa2-ai-analysis-title";
		heading.textContent = "Failure Analysis";
		wrap.appendChild(heading);

		const sections = parse_analysis_sections(text);
		const preferred = [
			"Issue",
			"Cause",
			"Suggested fix",
			"Impact",
			"Evidence",
			"Related data",
			"Related logs",
			"Transaction summary",
		];
		const byTitle = {};
		sections.forEach(function (section) {
			byTitle[section.title] = section;
		});

		preferred.forEach(function (title) {
			const section = byTitle[title];
			if (!section || !section.body.length) return;
			if (title === "Transaction summary") return;
			const block = document.createElement("section");
			block.className = "oa2-ai-analysis-block";
			const h = document.createElement("h4");
			h.textContent = title === "Suggested fix" ? "Suggested Fix" : title;
			block.appendChild(h);
			const p = document.createElement("p");
			p.innerHTML = format_text(section.body.join("\n"));
			block.appendChild(p);
			wrap.appendChild(block);
		});

		const ediLinks = (links || []).filter(function (link) {
			return link && link.type === "edi";
		});
		if (ediLinks.length) {
			const block = document.createElement("section");
			block.className = "oa2-ai-analysis-block";
			const h = document.createElement("h4");
			h.textContent = "Transaction";
			block.appendChild(h);
			const cards = links_box(ediLinks);
			if (cards) block.appendChild(cards);
			wrap.appendChild(block);
		}

		const otherLinks = (links || []).filter(function (link) {
			return link && link.type && link.type !== "edi";
		});
		if (otherLinks.length) {
			const cards = links_box(otherLinks, "Related");
			if (cards) wrap.appendChild(cards);
		}

		if (!wrap.querySelector(".oa2-ai-analysis-block") && text) {
			const p = document.createElement("p");
			p.className = "oa2-ai-msg-text";
			p.innerHTML = format_text(text);
			wrap.appendChild(p);
			const cards = links_box(links || []);
			if (cards) wrap.appendChild(cards);
		}

		return wrap;
	}

	function add_message(panel, text, mine, extra, opts) {
		const log = panel.querySelector(".oa2-ai-log");
		const node = document.createElement("div");
		const options = opts || {};
		node.className =
			"oa2-ai-msg" +
			(mine ? " is-user" : " is-assistant") +
			(options.error ? " is-error" : "") +
			(options.loading ? " is-loading" : "");
		if (text) {
			const body = document.createElement("div");
			body.className = "oa2-ai-msg-text";
			if (mine || options.plain) {
				body.textContent = text;
			} else {
				body.innerHTML = format_text(text);
			}
			node.appendChild(body);
		}
		if (options.loading) {
			const dots = document.createElement("span");
			dots.className = "oa2-ai-typing";
			dots.setAttribute("aria-hidden", "true");
			dots.innerHTML = "<i></i><i></i><i></i>";
			node.appendChild(dots);
		}
		if (extra) node.appendChild(extra);
		log.appendChild(node);
		scroll_log(panel);
		return node;
	}

	function show_loading(panel) {
		return add_message(panel, LOADING_MESSAGE, false, null, { loading: true, plain: true });
	}

	function clear_loading(node) {
		if (node && node.parentNode) node.parentNode.removeChild(node);
	}

	function run_confirm(panel, token) {
		const loading = show_loading(panel);
		set_busy(panel, true);
		frappe.call({
			method: CONFIRM,
			args: { token: token },
			callback: function (r) {
				clear_loading(loading);
				set_busy(panel, false);
				const data = r.message || {};
				const links = links_box(data.links || []);
				add_message(panel, data.reply || "Done.", false, links);
				remember_turn(panel, "", data);
			},
			error: function (r) {
				clear_loading(loading);
				set_busy(panel, false);
				add_error(panel, friendly_error(r), null);
			},
		});
	}

	function guide_box(guide) {
		const box = document.createElement("div");
		box.className = "oa2-ai-confirm";
		(guide.options || []).forEach(function (option) {
			const choice = document.createElement("button");
			choice.type = "button";
			choice.textContent = option;
			choice.addEventListener("click", function () {
				send(ensure_panel(), option);
			});
			box.appendChild(choice);
		});
		(guide.actions || []).forEach(function (action) {
			const btn = document.createElement("button");
			btn.type = "button";
			if (action.confirm) btn.className = "oa2-ai-go";
			btn.textContent = action.label || "Continue";
			btn.addEventListener("click", function () {
				const panel = ensure_panel();
				if (action.confirm) run_confirm(panel, action.confirm);
				else if (action.message) send(panel, action.message);
			});
			box.appendChild(btn);
		});
		return box;
	}

	function confirm_box(payload) {
		const box = document.createElement("div");
		box.className = "oa2-ai-confirm";
		const go = document.createElement("button");
		go.type = "button";
		go.className = "oa2-ai-go";
		go.textContent = payload.title || "Confirm";
		const stop = document.createElement("button");
		stop.type = "button";
		stop.textContent = "Cancel";
		go.addEventListener("click", function () {
			go.disabled = true;
			stop.disabled = true;
			run_confirm(ensure_panel(), payload.token);
		});
		stop.addEventListener("click", function () {
			go.disabled = true;
			stop.disabled = true;
			frappe.call({
				method: CANCEL,
				args: { token: payload.token },
				callback: function (r) {
					const panel = ensure_panel();
					const reply = (r.message && r.message.reply) || "Cancelled. Nothing was changed.";
					add_message(panel, reply, false);
					remember_turn(panel, "", { reply: reply, kind: "message", links: [] });
				},
			});
		});
		box.appendChild(stop);
		box.appendChild(go);
		return box;
	}

	function server_error(r) {
		const msg =
			(r && r.message) ||
			(r && r._server_messages && String(r._server_messages)) ||
			"The request failed.";
		return typeof msg === "string" ? msg : "The request failed.";
	}

	function friendly_error(r) {
		const raw = server_error(r);
		if (/permission|not permitted|guest/i.test(raw)) return raw;
		return "I couldn't complete that request. Please try again.";
	}

	function add_error(panel, message, retryPrompt) {
		const actions = document.createElement("div");
		actions.className = "oa2-ai-error-actions";
		if (retryPrompt) {
			const again = document.createElement("button");
			again.type = "button";
			again.className = "oa2-ai-retry";
			again.textContent = "Try again";
			again.addEventListener("click", function () {
				send(panel, retryPrompt);
			});
			actions.appendChild(again);
		}
		add_message(panel, message, false, actions.childNodes.length ? actions : null, {
			error: true,
			plain: true,
		});
	}

	function list_heading_from_reply(reply) {
		const first = String(reply || "").split("\n")[0] || "";
		if (
			/found\s+\d+/i.test(first) ||
			/partners|transactions|certificates|configurations|partnerships|logs/i.test(first)
		) {
			return first.replace(/\.?\s*$/, "");
		}
		return "";
	}

	function render_reply(panel, data) {
		const kind = data.kind || "message";
		const reply = data.reply || "No reply was returned.";
		const links = data.links || [];

		if (kind === "error") {
			add_message(panel, reply, false, null, { error: true });
			return;
		}

		if (kind === "analysis") {
			add_message(panel, null, false, analysis_box(reply, links));
			return;
		}

		const wrap = document.createElement("div");
		wrap.className = "oa2-ai-extra";
		if (data.guide) wrap.appendChild(guide_box(data.guide));
		if (kind === "confirm" && data.confirm) {
			wrap.appendChild(confirm_box(data.confirm));
		}

		let bodyText = reply;
		if (links.length) {
			const heading = list_heading_from_reply(reply);
			if (heading) bodyText = heading;
			const cards = links_box(links);
			if (cards) wrap.appendChild(cards);
		}

		add_message(panel, bodyText, false, wrap.childNodes.length ? wrap : null);
	}

	function send(panel, preset) {
		if (!panel || panel.classList.contains("is-busy")) return;
		const input = panel.querySelector("textarea");
		const text = (preset != null ? String(preset) : (input && input.value) || "").trim();
		if (!text) return;
		if (input) input.value = "";
		autosize(input);
		mark_chatting(panel);
		add_message(panel, text, true);
		const loading = show_loading(panel);
		set_busy(panel, true);
		panel._oa2_last_prompt = text;
		frappe.call({
			method: CHAT,
			args: { message: text, context: JSON.stringify(context()) },
			callback: function (r) {
				clear_loading(loading);
				set_busy(panel, false);
				const data = r.message || {};
				if (window.console && console.debug) {
					console.debug("openas2 assistant", {
						question: text,
						kind: data.kind,
						links: data.links,
						reply: data.reply,
					});
				}
				render_reply(panel, data);
				remember_turn(panel, text, data);
			},
			error: function (r) {
				clear_loading(loading);
				set_busy(panel, false);
				const message = friendly_error(r);
				add_error(panel, message, text);
				remember_turn(panel, text, { reply: message, kind: "error", links: [] });
			},
		});
	}

	function history_when(value) {
		if (!value) return "";
		let dt = null;
		try {
			dt = frappe.datetime.str_to_obj ? frappe.datetime.str_to_obj(value) : new Date(String(value).replace(" ", "T"));
		} catch (e) {
			dt = null;
		}
		if (!dt || isNaN(dt.getTime())) return "";
		const now = new Date();
		const startToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
		const startThat = new Date(dt.getFullYear(), dt.getMonth(), dt.getDate());
		const diffDays = Math.round((startToday - startThat) / 86400000);
		let time = "";
		try {
			time = dt.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
		} catch (err) {
			time = "";
		}
		if (diffDays === 0) return time ? "Today, " + time : "Today";
		if (diffDays === 1) return "Yesterday";
		try {
			return dt.toLocaleDateString([], { month: "short", day: "numeric" });
		} catch (err2) {
			return "";
		}
	}

	function remember_turn(panel, userText, data) {
		if (!panel) return;
		const payload = data || {};
		const reply = payload.reply != null ? String(payload.reply) : "";
		const links = payload.links || [];
		if (!String(userText || "").trim() && !reply.trim() && !links.length) return;
		panel._oa2_save_queue = (panel._oa2_save_queue || Promise.resolve()).then(function () {
			return new Promise(function (resolve) {
				frappe.call({
					method: HISTORY_RECORD,
					args: {
						conversation: panel._oa2_conversation || "",
						user_message: userText || "",
						reply: reply,
						kind: payload.kind || "message",
						links: JSON.stringify(links),
					},
					callback: function (r) {
						const saved = (r && r.message) || {};
						if (saved.ok && saved.name) {
							panel._oa2_conversation = saved.name;
							load_history(panel, 0);
						}
						resolve();
					},
					error: function () {
						resolve();
					},
				});
			});
		});
	}

	function show_history_note(panel, text) {
		const list = panel && panel.querySelector(".oa2-ai-history-list");
		if (!list) return;
		list.innerHTML = '<p class="oa2-ai-history-empty">' + esc(text) + "</p>";
	}

	function set_active_history(panel, name) {
		if (!panel) return;
		panel.querySelectorAll(".oa2-ai-history-item").forEach(function (item) {
			item.classList.toggle("is-active", !!name && item.getAttribute("data-oa2-conversation") === name);
		});
	}

	function render_history_list(panel, rows, hasMore) {
		const list = panel.querySelector(".oa2-ai-history-list");
		if (!list) return;
		if (!rows || !rows.length) {
			show_history_note(panel, "No conversations yet.");
			return;
		}
		list.innerHTML = rows
			.map(function (row) {
				const active = panel._oa2_conversation && panel._oa2_conversation === row.name;
				return (
					'<div class="oa2-ai-history-row" role="listitem">' +
					'<button type="button" class="oa2-ai-history-item' +
					(active ? " is-active" : "") +
					'" data-oa2-conversation="' +
					esc(row.name) +
					'">' +
					'<span class="oa2-ai-history-title">' +
					esc(row.title || "Conversation") +
					"</span>" +
					'<span class="oa2-ai-history-time">' +
					esc(history_when(row.modified)) +
					"</span></button>" +
					'<button type="button" class="oa2-ai-history-delete" data-oa2-conversation="' +
					esc(row.name) +
					'" aria-label="Delete conversation">×</button></div>'
				);
			})
			.join("");
		if (hasMore) {
			const more = document.createElement("button");
			more.type = "button";
			more.className = "oa2-ai-history-more";
			more.textContent = "Older conversations";
			more.addEventListener("click", function () {
				load_history(panel, (panel._oa2_history_start || 0) + 30, true);
			});
			list.appendChild(more);
		}
	}

	function load_history(panel, start, append) {
		if (!panel) return;
		frappe.call({
			method: HISTORY_LIST,
			args: { start: start || 0, limit: 30 },
			callback: function (r) {
				const data = r.message || {};
				if (data.ok === false) {
					show_history_note(panel, data.error || "Couldn't load conversations.");
					return;
				}
				const rows = data.conversations || [];
				if (append && start) {
					panel._oa2_history_rows = (panel._oa2_history_rows || []).concat(rows);
				} else {
					panel._oa2_history_rows = rows;
					panel._oa2_history_start = 0;
				}
				panel._oa2_history_start = start || 0;
				render_history_list(panel, panel._oa2_history_rows, !!data.has_more);
			},
			error: function () {
				show_history_note(panel, "Couldn't load conversations.");
			},
		});
	}

	function render_saved_conversation(panel, conversation) {
		const log = panel.querySelector(".oa2-ai-log");
		if (log) log.innerHTML = "";
		const messages = (conversation && conversation.messages) || [];
		if (!messages.length) {
			panel.classList.remove("has-chat");
			const welcome = panel.querySelector(".oa2-ai-welcome");
			if (welcome) welcome.removeAttribute("hidden");
		} else {
			mark_chatting(panel);
			messages.forEach(function (msg) {
				if ((msg.role || "") === "user") {
					add_message(panel, msg.content || "", true);
					return;
				}
				render_reply(panel, {
					reply: msg.content || "",
					kind: msg.kind || "message",
					links: msg.links || [],
				});
			});
		}
		panel._oa2_conversation = conversation.name;
		set_active_history(panel, conversation.name);
		const box = panel.querySelector(".oa2-ai-history");
		const toggle = panel.querySelector(".oa2-ai-history-toggle");
		if (box) box.setAttribute("hidden", "");
		if (toggle) toggle.setAttribute("aria-expanded", "false");
		scroll_log(panel);
	}

	function open_conversation(panel, name) {
		if (!panel || !name || panel.classList.contains("is-busy")) return;
		set_busy(panel, true);
		frappe.call({
			method: HISTORY_GET,
			args: { name: name },
			callback: function (r) {
				set_busy(panel, false);
				const data = r.message || {};
				if (!data.ok) {
					add_error(panel, data.error || "Couldn't open that conversation.", null);
					return;
				}
				render_saved_conversation(panel, data);
			},
			error: function () {
				set_busy(panel, false);
				add_error(panel, "Couldn't open that conversation.", null);
			},
		});
	}

	function start_new_chat(panel) {
		if (!panel || panel.classList.contains("is-busy")) return;
		panel._oa2_conversation = "";
		const log = panel.querySelector(".oa2-ai-log");
		if (log) log.innerHTML = "";
		panel.classList.remove("has-chat");
		const welcome = panel.querySelector(".oa2-ai-welcome");
		if (welcome) welcome.removeAttribute("hidden");
		set_active_history(panel, "");
		const box = panel.querySelector(".oa2-ai-history");
		const toggle = panel.querySelector(".oa2-ai-history-toggle");
		if (box) box.setAttribute("hidden", "");
		if (toggle) toggle.setAttribute("aria-expanded", "false");
		const input = panel.querySelector("textarea");
		if (input) {
			input.value = "";
			autosize(input);
			input.focus();
		}
		frappe.call({ method: HISTORY_CLEAR });
	}

	function toggle_history(panel) {
		const box = panel && panel.querySelector(".oa2-ai-history");
		const toggle = panel && panel.querySelector(".oa2-ai-history-toggle");
		if (!box || !toggle) return;
		const open = box.hasAttribute("hidden");
		if (open) {
			box.removeAttribute("hidden");
			toggle.setAttribute("aria-expanded", "true");
			load_history(panel, 0);
		} else {
			box.setAttribute("hidden", "");
			toggle.setAttribute("aria-expanded", "false");
		}
	}

	function delete_history_item(panel, name) {
		if (!panel || !name) return;
		frappe.call({
			method: HISTORY_DELETE,
			args: { name: name },
			callback: function (r) {
				const data = r.message || {};
				if (!data.ok) {
					show_history_note(panel, data.error || "Couldn't delete that conversation.");
					load_history(panel, 0);
					return;
				}
				if (panel._oa2_conversation === name) start_new_chat(panel);
				load_history(panel, 0);
			},
			error: function () {
				show_history_note(panel, "Couldn't delete that conversation.");
			},
		});
	}

	function autosize(textarea) {
		if (!textarea) return;
		textarea.style.height = "auto";
		textarea.style.height = Math.min(Math.max(textarea.scrollHeight, 36), 96) + "px";
	}

	function apply_chip(panel, prompt) {
		const input = panel.querySelector("textarea");
		if (!input || panel.classList.contains("is-busy")) return;
		input.value = prompt;
		input.focus();
		const pos = input.value.length;
		try {
			input.setSelectionRange(pos, pos);
		} catch (e) {
			/* ignore */
		}
		autosize(input);
	}

	function render_analysis(host, data) {
		const sections = (data && data.sections) || [];
		host.innerHTML = sections
			.map(function (section) {
				return (
					'<section class="oa2-ai-section"><h3>' +
					esc(section.title) +
					"</h3><p>" +
					esc(section.body) +
					"</p></section>"
				);
			})
			.join("");
	}

	function load_analysis(name, host) {
		if (!name || !host) return;
		if (host.getAttribute("data-loaded") === name) return;
		host.setAttribute("data-loaded", name);
		host.innerHTML = '<p class="oa2-ai-section">Reading the stored transaction…</p>';
		frappe.call({
			method: ANALYZE,
			args: { name: name },
			callback: function (r) {
				render_analysis(host, r.message || {});
			},
			error: function (r) {
				host.innerHTML = '<p class="oa2-ai-section">' + esc(friendly_error(r)) + "</p>";
			},
		});
	}

	function sync_theme() {
		const panel = document.querySelector(".oa2-ai-panel");
		if (panel) panel.setAttribute("data-oa2-theme", theme());
	}

	const STACK_PANELS = ".oa2-ai-panel, .oa2-edit-modal-root, .oa2-edi-modal";
	const STACK_FRONT = "oa2-stack-front";
	const STACK_LIFT = "oa2-stack-lift";
	const STACK_BACKDROP = ".oa2-edit-modal-backdrop, .oa2-edi-modal-backdrop";
	let stackActive = null;
	let stackLifted = null;
	let stackSwallowClick = false;

	function stack_shown(panel) {
		if (!panel || panel.hidden) return false;
		if (panel.classList.contains("oa2-ai-panel") || panel.classList.contains("oa2-edi-modal")) {
			return panel.classList.contains("is-open");
		}
		return true;
	}

	function stack_traps(el) {
		const style = window.getComputedStyle(el);
		if (style.position !== "static" && style.zIndex !== "auto") return true;
		if (style.transform && style.transform !== "none") return true;
		if (style.filter && style.filter !== "none") return true;
		if (style.perspective && style.perspective !== "none") return true;
		if (parseFloat(style.opacity) < 1) return true;
		if (style.isolation === "isolate") return true;
		if (style.mixBlendMode && style.mixBlendMode !== "normal") return true;
		const backdrop = style.backdropFilter || style.webkitBackdropFilter;
		if (backdrop && backdrop !== "none") return true;
		if (style.clipPath && style.clipPath !== "none") return true;
		if (style.contain && /(paint|layout|strict|content)/.test(style.contain)) return true;
		if (/(transform|opacity|filter|perspective)/.test(style.willChange || "")) return true;
		return false;
	}

	function stack_release_lift() {
		if (!stackLifted) return;
		stackLifted.classList.remove(STACK_LIFT);
		if (stackLifted.dataset.oa2StackPos) {
			stackLifted.style.position = "";
			delete stackLifted.dataset.oa2StackPos;
		}
		stackLifted = null;
	}

	function stack_lift(panel) {
		stack_release_lift();
		if (!panel || panel.classList.contains("oa2-ai-panel")) return;
		let node = panel.parentElement;
		let top = null;
		while (node && node !== document.body && node !== document.documentElement) {
			if (stack_traps(node)) top = node;
			node = node.parentElement;
		}
		if (!top) return;
		stackLifted = top;
		if (window.getComputedStyle(top).position === "static") {
			top.dataset.oa2StackPos = "1";
			top.style.position = "relative";
		}
		top.classList.add(STACK_LIFT);
	}

	function bring_to_front(panel) {
		if (!stack_shown(panel) || stackActive === panel) return;
		document.querySelectorAll("." + STACK_FRONT).forEach(function (el) {
			if (el !== panel) el.classList.remove(STACK_FRONT);
		});
		panel.classList.add(STACK_FRONT);
		stack_lift(panel);
		stackActive = panel;
	}

	function stack_panel_from(node) {
		if (!node || !node.closest) return null;
		const panel = node.closest(STACK_PANELS);
		return stack_shown(panel) ? panel : null;
	}

	function stack_copilot_at(x, y) {
		const panel = document.querySelector(".oa2-ai-panel.is-open");
		if (!stack_shown(panel)) return null;
		const rect = panel.getBoundingClientRect();
		if (x < rect.left || x > rect.right || y < rect.top || y > rect.bottom) return null;
		return panel;
	}

	function bind_stacking() {
		if (window.__oa2_stack_bound === UI_VER) return;
		window.__oa2_stack_bound = UI_VER;
		document.addEventListener(
			"pointerdown",
			function (event) {
				if (event.button != null && event.button !== 0) return;
				const backdrop = event.target.closest && event.target.closest(STACK_BACKDROP);
				const copilot = backdrop && stack_copilot_at(event.clientX, event.clientY);
				if (copilot) {
					stackSwallowClick = true;
					bring_to_front(copilot);
					return;
				}
				const panel = stack_panel_from(event.target);
				if (panel) bring_to_front(panel);
			},
			true
		);
		document.addEventListener(
			"click",
			function (event) {
				if (!stackSwallowClick) return;
				stackSwallowClick = false;
				const backdrop = event.target.closest && event.target.closest(STACK_BACKDROP);
				if (!backdrop) return;
				event.preventDefault();
				event.stopPropagation();
			},
			true
		);
		const observer = new MutationObserver(function (records) {
			records.forEach(function (record) {
				if (record.type === "childList") {
					record.addedNodes.forEach(function (node) {
						if (!node || node.nodeType !== 1) return;
						if (node.matches && node.matches(STACK_PANELS)) bring_to_front(node);
						else if (node.querySelector) {
							const found = node.querySelector(STACK_PANELS);
							if (found) bring_to_front(found);
						}
					});
					record.removedNodes.forEach(function (node) {
						if (!node || node.nodeType !== 1 || stackActive == null) return;
						const matches =
							(node.matches && node.matches(STACK_PANELS) && node) ||
							(node.contains && node.contains(stackActive));
						if (matches) {
							stackActive = null;
							stack_release_lift();
						}
					});
					return;
				}
				const panel = record.target;
				if (!panel || !panel.matches || !panel.matches(STACK_PANELS)) return;
				if (record.attributeName === "class") {
					const wasOpen = (record.oldValue || "").split(/\s+/).indexOf("is-open") !== -1;
					if (!wasOpen && panel.classList.contains("is-open")) bring_to_front(panel);
					return;
				}
				if (record.attributeName === "hidden" && stack_shown(panel)) bring_to_front(panel);
			});
		});
		observer.observe(document.body, {
			childList: true,
			subtree: true,
			attributes: true,
			attributeFilter: ["class", "hidden"],
			attributeOldValue: true,
		});
	}

	function bind() {
		window.__oa2_ai_send = send;
		if (!window.__oa2_ai_capture) {
			window.__oa2_ai_capture = true;
			document.addEventListener(
				"submit",
				function (event) {
					const form = event.target.closest && event.target.closest(".oa2-ai-form");
					if (!form) return;
					event.preventDefault();
					event.stopImmediatePropagation();
					send(form.closest(".oa2-ai-panel"));
				},
				true
			);
			document.addEventListener("keydown", function (event) {
				const area = event.target.closest && event.target.closest(".oa2-ai-form textarea");
				if (!area) return;
				if (event.key === "Enter" && !event.shiftKey) {
					event.preventDefault();
					send(area.closest(".oa2-ai-panel"));
				}
			});
			document.addEventListener("input", function (event) {
				const area = event.target.closest && event.target.closest(".oa2-ai-form textarea");
				if (area) autosize(area);
			});
			document.addEventListener("click", function (event) {
				if (event.target.closest && event.target.closest("[data-oa2-theme-toggle], .oa2-theme-toggle")) {
					setTimeout(sync_theme, 0);
				}
			});
			window.addEventListener("storage", function (event) {
				if (event.key === "oa2-dashboard-theme") sync_theme();
			});
		}
		if (window.__oa2_ai_bound === UI_VER) return;
		window.__oa2_ai_bound = UI_VER;
		bind_stacking();
		document.addEventListener("click", function (event) {
			const open = event.target.closest && event.target.closest(".oa2-ai-open");
			if (open) {
				event.preventDefault();
				const panel = ensure_panel();
				panel.setAttribute("data-oa2-theme", theme());
				panel.classList.add("is-open");
				bring_to_front(panel);
				const input = panel.querySelector("textarea");
				if (input && !panel.classList.contains("is-busy")) input.focus();
				scroll_log(panel);
				if (!panel._oa2_history_ready) {
					panel._oa2_history_ready = true;
					if (!panel._oa2_conversation) frappe.call({ method: HISTORY_CLEAR });
					load_history(panel, 0);
				}
				return;
			}
			const newer = event.target.closest && event.target.closest(".oa2-ai-new");
			if (newer) {
				event.preventDefault();
				start_new_chat(newer.closest(".oa2-ai-panel") || ensure_panel());
				return;
			}
			const historyToggle = event.target.closest && event.target.closest(".oa2-ai-history-toggle");
			if (historyToggle) {
				event.preventDefault();
				toggle_history(historyToggle.closest(".oa2-ai-panel") || ensure_panel());
				return;
			}
			const historyDelete = event.target.closest && event.target.closest(".oa2-ai-history-delete");
			if (historyDelete) {
				event.preventDefault();
				delete_history_item(
					historyDelete.closest(".oa2-ai-panel") || ensure_panel(),
					historyDelete.getAttribute("data-oa2-conversation")
				);
				return;
			}
			const historyItem = event.target.closest && event.target.closest(".oa2-ai-history-item");
			if (historyItem) {
				event.preventDefault();
				open_conversation(
					historyItem.closest(".oa2-ai-panel") || ensure_panel(),
					historyItem.getAttribute("data-oa2-conversation")
				);
				return;
			}
			const close = event.target.closest && event.target.closest(".oa2-ai-close");
			if (close) {
				event.preventDefault();
				const panel = close.closest(".oa2-ai-panel");
				if (panel) panel.classList.remove("is-open");
				return;
			}
			const suggest = event.target.closest && event.target.closest(".oa2-ai-suggest");
			if (suggest) {
				event.preventDefault();
				const panel = suggest.closest(".oa2-ai-panel") || ensure_panel();
				send(panel, suggest.getAttribute("data-oa2-prompt") || suggest.textContent);
				return;
			}
			const chip = event.target.closest && event.target.closest(".oa2-ai-chip");
			if (chip) {
				event.preventDefault();
				const panel = chip.closest(".oa2-ai-panel") || ensure_panel();
				apply_chip(panel, chip.getAttribute("data-oa2-chip") || "");
				return;
			}
			const tab = event.target.closest && event.target.closest('.oa2-edi-modal-tab[data-tab="analysis"]');
			if (tab) {
				const modal = tab.closest(".oa2-edi-modal");
				const host = modal && modal.querySelector(".oa2-ai-analysis-host");
				load_analysis(modal && modal.getAttribute("data-oa2-edi"), host);
			}
		});
	}

	frappe.provide("openas2_manager");
	openas2_manager.open_assistant_record = open_record;

	if (window.jQuery) {
		jQuery(document).on("app_ready", bind);
		jQuery(function () {
			bind();
		});
	} else {
		document.addEventListener("DOMContentLoaded", bind);
	}
	bind();
})();
