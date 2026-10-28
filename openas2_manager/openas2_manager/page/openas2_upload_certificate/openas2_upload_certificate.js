// Copyright (c) 2026, Lakshana and contributors
// For license information, please see license.txt

frappe.pages["openas2-upload-certificate"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Create Certificate"),
		single_column: true,
	});
	frappe.breadcrumbs.add("OpenAS2 Manager");
	$(wrapper).addClass("oa2-config-page-wrapper oa2-upload-certificate-page-wrapper");
	document.body.classList.add("oa2-has-sidebar", "oa2-use-inpage-sidebar");
	document.body.classList.remove("oa2-using-global-sidebar", "oa2-sidebar-mounted");
	wrapper.upload_certificate_page = new openas2_manager.OpenAS2UploadCertificatePage(page);
	if (window.openas2_manager && openas2_manager.sync_layout) openas2_manager.sync_layout();
};

frappe.pages["openas2-upload-certificate"].on_page_show = function (wrapper) {
	document.body.classList.add("oa2-has-sidebar", "oa2-use-inpage-sidebar");
	document.body.classList.remove("oa2-using-global-sidebar", "oa2-sidebar-mounted");
	if (wrapper.upload_certificate_page) {
		wrapper.upload_certificate_page.apply_theme(wrapper.upload_certificate_page.get_theme());
	}
	if (window.openas2_manager && openas2_manager.sync_layout) openas2_manager.sync_layout();
};

frappe.provide("openas2_manager");

openas2_manager.OpenAS2UploadCertificatePage = class OpenAS2UploadCertificatePage {
	constructor(page) {
		this.page = page;
		this.THEME_KEY = "oa2-dashboard-theme";
		this.saving = false;
		this.docName = "";
		this.$body = $(page.body).addClass("oa2-config-list-page oa2-upload-certificate-page");
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
		const active = "certificates";
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
		const id = "oa2-cert-" + name;
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
		const inputType = type === "password" ? "password" : type === "number" ? "number" : type === "file" ? "file" : "text";
		const accept = type === "file" ? ' accept=".cer,.crt,.pem,.der"' : "";
		const wide = type === "file" ? " oa2-set-wide" : "";
		return `<label class="oa2-set-field${wide}" for="${id}"><span>${frappe.utils.escape_html(label)}${mark}</span><input id="${id}" type="${inputType}" data-field="${name}" autocomplete="off"${accept} /></label>`;
	}

	section(title, hint, inner, extraClass) {
		return `<section class="oa2-config-card oa2-set-card${extraClass ? " " + extraClass : ""}"><header class="oa2-set-card-head"><h2>${frappe.utils.escape_html(title)}</h2>${hint ? `<p>${frappe.utils.escape_html(hint)}</p>` : ""}</header><div class="oa2-set-grid">${inner}</div></section>`;
	}

	preview_row(key, label) {
		return `<div><dt>${frappe.utils.escape_html(label)}</dt><dd data-preview="${key}">—</dd></div>`;
	}

	make() {
		const identity =
			this.field("certificate_name", __("Certificate name"), "text", { required: true }) +
			this.field("certificate_type", __("Certificate type"), "select", {
				required: true,
				options: [
					{ value: "", label: __("Select a certificate type") },
					"Signing",
					"Encryption",
					"Both",
				],
			}) +
			this.field("purpose", __("Purpose"), "select", {
				required: true,
				options: [
					{ value: "Own Key Pair", label: __("Own Key Pair") },
					{ value: "Partner Public Certificate", label: __("Partner Public Certificate") },
				],
			}) +
			this.field("owner_type", __("Company / TMS"), "select", {
				required: true,
				options: [
					{ value: "", label: __("Select a company") },
					"Shipper",
					"Broker",
					"Carrier",
					"CompanyC",
				],
			}) +
			this.field("common_name", __("Common name"), "text", { required: true }) +
			this.field("x509_alias", __("X509 alias"), "text", { required: true }) +
			this.field("organization", __("Organization"), "text");

		const file =
			this.field("certificate_file", __("Certificate file"), "file", { required: true }) +
			`<p class="oa2-file-name oa2-set-wide" data-file-name>${__("Public certificate only (.cer, .crt, or .pem).")}</p>`;

		const keystore =
			this.field("key_size", __("Key size"), "select", { options: ["2048", "4096"] }) +
			this.field("validity_days", __("Validity days"), "number") +
			this.field("keystore_password", __("Keystore password"), "password");

		const preview = [
			["certificate_name", __("Certificate name")],
			["certificate_type", __("Certificate type")],
			["purpose", __("Purpose")],
			["status", __("Status")],
			["x509_alias", __("X509 alias")],
			["common_name", __("Common name")],
			["keystore_path", __("Keystore path")],
			["private_key_stored", __("Private key file")],
			["certificate_file", __("Public certificate file")],
			["public_cert_fingerprint", __("Fingerprint")],
			["valid_from", __("Valid from")],
			["valid_until", __("Valid until")],
			["expiry_info", __("Expiry")],
			["exchange_status", __("Exchange status")],
		]
			.map((row) => this.preview_row(row[0], row[1]))
			.join("");

		this.$body.html(`
			<div class="oa2-app-frame">
				${this.sidebar_html()}
				<div class="oa2-main-pane">
					<div class="oa2-config-shell">
						<header class="oa2-config-header">
							<div>
								<h1 class="oa2-config-title">${__("Create Certificate")}</h1>
								<p class="oa2-config-subtitle">${__("Create an AS2 Certificate. Own key pairs are generated on the server. Partner certificates upload a public file only.")}</p>
							</div>
							<div class="oa2-config-header-actions"></div>
						</header>
						<form class="oa2-set-form" novalidate>
							${this.section(__("Certificate"), __("Name, type, and identity stored on the AS2 Certificate."), identity)}
							${this.section(__("Certificate file"), __("Required for a partner public certificate."), file, "oa2-cert-public")}
							${this.section(__("Keystore / private key"), __("Used only when creating your own key pair. The private key stays in the .p12 file."), keystore, "oa2-cert-own")}
							<section class="oa2-config-card oa2-set-card">
								<header class="oa2-set-card-head"><h2>${__("Certificate details")}</h2><p>${__("Filled from the saved AS2 Certificate after upload.")}</p></header>
								<dl class="oa2-preview">${preview}</dl>
							</section>
							<div class="oa2-form-actions">
								<button type="button" class="oa2-btn oa2-btn-secondary oa2-cert-cancel">${__("Cancel / Back")}</button>
								<button type="submit" class="oa2-btn oa2-btn-primary oa2-cert-save">${__("Save / Upload Certificate")}</button>
							</div>
						</form>
					</div>
				</div>
			</div>
		`);

		this.$body.find('[data-field="validity_days"]').val("825");
		this.$body.on("click", ".oa2-sidebar-inpage [data-route]", (e) => {
			e.preventDefault();
			const route = $(e.currentTarget).attr("data-route");
			if (route) frappe.set_route(route);
		});
		this.$body.on("click", ".oa2-cert-cancel", (e) => {
			e.preventDefault();
			frappe.set_route("openas2-certificates");
		});
		this.$body.on("change", '[data-field="purpose"]', () => this.sync_purpose());
		this.$body.on("change", '[data-field="certificate_file"]', (e) => {
			const fileObj = e.currentTarget.files && e.currentTarget.files[0];
			this.$body.find("[data-file-name]").text(fileObj ? fileObj.name : __("Public certificate only (.cer, .crt, or .pem)."));
		});
		this.$body.on("submit", "form", (e) => {
			e.preventDefault();
			this.save();
		});
		this.sync_purpose();
	}

	sync_purpose() {
		const own = this.value("purpose") !== "Partner Public Certificate";
		this.$body.find(".oa2-cert-own").prop("hidden", !own);
		this.$body.find(".oa2-cert-public").prop("hidden", own);
	}

	value(name) {
		return String(this.$body.find(`[data-field="${name}"]`).val() || "").trim();
	}

	selected_file() {
		const input = this.$body.find('[data-field="certificate_file"]').get(0);
		return input && input.files && input.files[0] ? input.files[0] : null;
	}

	call(method, args) {
		return new Promise((resolve, reject) => {
			frappe.call({
				method,
				args,
				callback: (r) => resolve(r && r.message),
				error: () => reject(new Error(method)),
			});
		});
	}

	upload_file(docname, file) {
		const data = new FormData();
		data.append("file", file, file.name);
		data.append("doctype", "AS2 Certificate");
		data.append("docname", docname);
		data.append("fieldname", "certificate_file");
		data.append("is_private", "1");
		return fetch("/api/method/upload_file", {
			method: "POST",
			headers: {
				"X-Frappe-CSRF-Token": frappe.csrf_token,
				Accept: "application/json",
			},
			body: data,
		}).then(async (res) => {
			const body = await res.json();
			if (!res.ok || body.exc) {
				frappe.msgprint(body._server_messages || __("Could not upload the certificate file."));
				throw new Error("upload");
			}
			return body.message;
		});
	}

	doc_payload() {
		const purpose = this.value("purpose") || "Own Key Pair";
		const doc = {
			doctype: "AS2 Certificate",
			certificate_name: this.value("certificate_name"),
			certificate_type: this.value("certificate_type"),
			purpose,
			owner_type: this.value("owner_type"),
			common_name: this.value("common_name"),
			x509_alias: this.value("x509_alias"),
			organization: this.value("organization"),
			status: "Draft",
		};
		if (purpose === "Own Key Pair") {
			doc.key_size = this.value("key_size") || "2048";
			doc.validity_days = cint(this.value("validity_days") || "825");
			const password = this.value("keystore_password");
			if (password) doc.keystore_password = password;
		}
		return doc;
	}

	async save() {
		if (this.saving) return;
		const doc = this.doc_payload();
		if (!doc.certificate_name || !doc.certificate_type || !doc.owner_type || !doc.common_name || !doc.x509_alias) {
			frappe.msgprint(__("Certificate name, type, company, common name, and X509 alias are required."));
			return;
		}
		const file = this.selected_file();
		if (doc.purpose === "Partner Public Certificate" && !file && !this.docName) {
			frappe.msgprint(__("Attach the partner public certificate file before saving."));
			return;
		}
		this.saving = true;
		const $save = this.$body.find(".oa2-cert-save").prop("disabled", true);
		try {
			if (!this.docName) {
				const created = await this.call("frappe.client.insert", { doc });
				this.docName = created && created.name;
			} else {
				const updates = Object.assign({}, doc);
				delete updates.doctype;
				if (!updates.keystore_password) delete updates.keystore_password;
				await this.call("frappe.client.set_value", {
					doctype: "AS2 Certificate",
					name: this.docName,
					fieldname: updates,
				});
			}
			if (!this.docName) return;
			if (doc.purpose === "Partner Public Certificate") {
				if (file) await this.upload_file(this.docName, file);
				await this.call("openas2_manager.certificates.generation.import_partner_public_certificate", {
					name: this.docName,
				});
			} else {
				await this.call("openas2_manager.certificates.generation.generate_own_keypair", {
					name: this.docName,
				});
			}
			const saved = await this.call("frappe.client.get", {
				doctype: "AS2 Certificate",
				name: this.docName,
			});
			this.render_preview(saved || {});
			frappe.show_alert({
				message: __("Certificate {0} saved", [doc.certificate_name]),
				indicator: "green",
			});
		} catch (e) {
			if (this.docName) {
				try {
					const saved = await this.call("frappe.client.get", {
						doctype: "AS2 Certificate",
						name: this.docName,
					});
					this.render_preview(saved || {});
				} catch (err) {
					/* leave the preview unchanged */
				}
			}
		} finally {
			this.saving = false;
			$save.prop("disabled", false);
		}
	}

	render_preview(doc) {
		const show = (key) => {
			let value = doc[key];
			if (key === "private_key_stored") value = cint(value) ? __("Created") : __("Not created");
			if (value == null || value === "") value = "—";
			this.$body.find(`[data-preview="${key}"]`).text(String(value));
		};
		[
			"certificate_name",
			"certificate_type",
			"purpose",
			"status",
			"x509_alias",
			"common_name",
			"keystore_path",
			"private_key_stored",
			"certificate_file",
			"public_cert_fingerprint",
			"valid_from",
			"valid_until",
			"expiry_info",
			"exchange_status",
		].forEach(show);
	}
};
