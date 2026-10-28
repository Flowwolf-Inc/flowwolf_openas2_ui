// OpenAS2 Partnership create/edit UI. Belongs to the OpenAS2 Partnership DocType.
// Do not route to the standard Frappe form.

frappe.provide("openas2_manager");

openas2_manager.partnership_ui = {
	open(opts) {
		this._queued = opts || {};
		clearTimeout(this._open_timer);
		this._open_timer = setTimeout(() => this._open(this._queued), 40);
	},

	_open(opts) {
		opts = opts || {};
		this.close();
		this.on_save = opts.on_save || null;
		this.partner = opts.partner || null;
		// AS2 Partner autoname is as2_id, so the Link value is the document name.
		this.linked_partner = (opts.partner && opts.partner.name) || opts.partner_name || null;
		this.partner_name = this.linked_partner;
		this.defaults = opts.defaults || {};
		this.mode = opts.name ? "edit" : "create";
		this.doc = null;
		this.lock_side = "remote";
		this.saving = false;
		const pending = { instances: [], partners: [], certs: [], doc: null, partner: this.partner };
		let left = 3 + (opts.name ? 1 : 0) + (!this.partner && this.partner_name ? 1 : 0);
		let started = false;
		const done = () => {
			left -= 1;
			if (left > 0 || started) return;
			started = true;
			if (opts.name && !pending.doc) {
				frappe.msgprint(__("Could not load this partnership."));
				return;
			}
			this.partner = pending.partner || this.partner;
			this.doc = pending.doc;
			this.partners = pending.partners;
			this.certs = pending.certs;
			this.instances = pending.instances;
			this.render();
		};
		const lists = [
			["OpenAS2 Instance", ["name", "instance_name"], "instance_name asc", "instances"],
			["AS2 Partner", ["name", "partner_name", "as2_id", "as2_url", "certificate"], "partner_name asc", "partners"],
			["AS2 Certificate", ["name", "certificate_name", "x509_alias"], "certificate_name asc", "certs"],
		];
		lists.forEach(([doctype, fields, order_by, key]) => {
			frappe.call({
				method: "frappe.client.get_list",
				args: { doctype, fields, order_by, limit_page_length: 200 },
				callback: (r) => {
					pending[key] = r.message || [];
					done();
				},
				error: done,
			});
		});
		if (opts.name) {
			frappe.call({
				method: "frappe.client.get",
				args: { doctype: "OpenAS2 Partnership", name: opts.name },
				callback: (r) => {
					pending.doc = r.message || null;
					done();
				},
				error: done,
			});
		}
		if (!this.partner && this.partner_name) {
			frappe.call({
				method: "frappe.client.get",
				args: { doctype: "AS2 Partner", name: this.partner_name },
				callback: (r) => {
					pending.partner = r.message || null;
					done();
				},
				error: done,
			});
		}
	},

	close() {
		$(".oa2-ps-ui").remove();
		this.doc = null;
	},

	theme() {
		try {
			return localStorage.getItem("oa2-dashboard-theme") === "dark" ? "dark" : "light";
		} catch (e) {
			return "light";
		}
	},

	esc(value) {
		return frappe.utils.escape_html(value == null ? "" : String(value));
	},

	field(fieldname, label, type, value, opts) {
		opts = opts || {};
		const id = "oa2-ps-" + fieldname;
		const locked = opts.readonly ? "readonly disabled" : "";
		const req = opts.reqd ? '<span class="oa2-req">*</span>' : "";
		let control = "";
		if (type === "Select") {
			const choices = (opts.options || "")
				.split("\n")
				.map((o) => {
					const sel = String(value || "") === o ? " selected" : "";
					return `<option value="${this.esc(o)}"${sel}>${this.esc(o || "—")}</option>`;
				})
				.join("");
			control = `<select class="oa2-edit-input" id="${id}" data-fieldname="${fieldname}" ${locked}>${choices}</select>`;
		} else if (type === "Link") {
			const options = opts.link_options || [];
			const choices = [`<option value="">${__("Select")}</option>`]
				.concat(
					options.map((o) => {
						const val = o.name || "";
						const text = (opts.link_label && o[opts.link_label]) || o.certificate_name || o.partner_name || val;
						const sel = String(value || "") === val ? " selected" : "";
						return `<option value="${this.esc(val)}"${sel}>${this.esc(text)}</option>`;
					})
				)
				.join("");
			control = `<select class="oa2-edit-input" id="${id}" data-fieldname="${fieldname}" ${locked}>${choices}</select>`;
		} else if (type === "Check") {
			const checked = cint(value) ? " checked" : "";
			control = `<label class="oa2-edit-check"><input type="checkbox" id="${id}" data-fieldname="${fieldname}" data-type="Check"${checked} ${locked}/> <span>${__(
				"Enabled"
			)}</span></label>`;
		} else if (type === "Small Text") {
			control = `<textarea class="oa2-edit-input oa2-edit-textarea" id="${id}" data-fieldname="${fieldname}" rows="3" ${locked}>${this.esc(
				value
			)}</textarea>`;
		} else {
			control = `<input type="text" class="oa2-edit-input" id="${id}" data-fieldname="${fieldname}" value="${this.esc(
				value
			)}" ${locked}/>`;
		}
		return `<div class="oa2-edit-field${opts.readonly ? " is-readonly" : ""}${opts.wide ? " oa2-edit-wide" : ""}">
			<label class="oa2-edit-label" for="${id}">${__(label)} ${req}</label>
			${control}
		</div>`;
	},

	panel(key, active, inner) {
		return `<section class="oa2-edit-section" data-section-panel="${key}" ${active ? "" : "hidden"}>${inner}</section>`;
	},

	section(title, html) {
		return `<div class="oa2-edit-group"><h3 class="oa2-edit-section-title">${__(title)}</h3><div class="oa2-edit-grid">${html}</div></div>`;
	},

	render() {
		const creating = this.mode === "create" || !this.doc;
		const partner = this.partner || {};
		let doc = this.doc || {};
		if (creating) {
			doc = Object.assign(
				{
					status: "Draft",
					instance: this.defaults.instance || "",
					remote_partner: partner.name || this.defaults.remote_partner || "",
					remote_partner_name: partner.partner_name || "",
					remote_as2_id: partner.as2_id || "",
					remote_url: partner.as2_url || "",
					remote_certificate: partner.certificate || "",
					encryption_enabled: partner.encryption_enabled == null ? 1 : cint(partner.encryption_enabled),
					signing_enabled: partner.signing_enabled == null ? 1 : cint(partner.signing_enabled),
					mdn_enabled: partner.mdn_enabled == null ? 1 : cint(partner.mdn_enabled),
					mdn_mode: partner.mdn_mode || "Synchronous",
				},
				doc
			);
			if (!doc.instance && (this.instances || []).length === 1) doc.instance = this.instances[0].name;
			const cert = (this.certs || []).find((c) => c.name === partner.certificate);
			if (cert && cert.x509_alias) doc.remote_x509_alias = cert.x509_alias;
		}
		const selected = partner.name || "";
		const lockRemote =
			!!selected &&
			(creating || !doc.local_partner || doc.remote_partner === selected || doc.local_partner !== selected);
		this.lock_side = selected ? (lockRemote ? "remote" : "local") : null;
		const others = (this.partners || []).filter((p) => !selected || p.name !== selected);
		const f = (name, label, type, opts) => this.field(name, label, type, doc[name], opts);
		const localLocked = this.lock_side === "local";
		const remoteLocked = this.lock_side === "remote";
		const selectedText = partner.partner_name
			? partner.partner_name + (partner.as2_id ? " · " + partner.as2_id : "")
			: "";
		const selectedField = selected
			? `<div class="oa2-edit-field oa2-edit-wide is-readonly">
				<label class="oa2-edit-label">${__("Selected Partner")}</label>
				<input type="text" class="oa2-edit-input" readonly value="${this.esc(selectedText)}" />
				<input type="hidden" data-fieldname="remote_partner" value="${this.esc(this.linked_partner || selected)}" />
			</div>`
			: f("remote_partner", "Selected Partner", "Link", { reqd: true, link_options: this.partners });
		const nav = [
			["details", __("Partnership Details")],
			["identities", __("AS2 Identities")],
			["endpoint", __("Endpoint")],
			["certificates", __("Certificates")],
			["mdn", __("MDN Settings")],
			["security", __("Security")],
			["advanced", __("Advanced")],
		]
			.map(
				([key, label], i) =>
					`<button type="button" class="oa2-edit-nav-btn${i === 0 ? " is-active" : ""}" data-section="${key}">${label}</button>`
			)
			.join("");
		const panels = [
			this.panel(
				"details",
				true,
				this.section(
					"Partnership Details",
					f("partnership_name", "Partnership Name", "Data", { reqd: true, readonly: !creating }) +
						selectedField +
						f("instance", "OpenAS2 Instance", "Link", {
							reqd: true,
							link_options: this.instances,
							link_label: "instance_name",
						}) +
						f("status", "Status", "Select", { options: "Draft\nActive\nInactive" }) +
						f("description", "Description", "Small Text", { wide: true })
				)
			),
			this.panel(
				"identities",
				false,
				this.section(
					"AS2 Identities",
					f("local_partner", "Local Partner", "Link", {
						reqd: true,
						readonly: localLocked,
						link_options: localLocked ? this.partners : others,
					}) +
						f("local_as2_id", "Local AS2 ID", "Data", { reqd: true }) +
						f("remote_as2_id", "Partner AS2 ID", "Data", { reqd: true, readonly: remoteLocked })
				)
			),
			this.panel("endpoint", false, this.section("Endpoint", f("remote_url", "AS2 URL", "Data", { reqd: true, wide: true }))),
			this.panel(
				"certificates",
				false,
				this.section(
					"Certificates",
					f("local_certificate", "Local Certificate", "Link", { link_options: this.certs }) +
						f("remote_certificate", "Partner Certificate", "Link", { link_options: this.certs }) +
						f("local_x509_alias", "Local X509 Alias", "Data") +
						f("remote_x509_alias", "Remote X509 Alias", "Data")
				)
			),
			this.panel(
				"mdn",
				false,
				this.section(
					"MDN Settings",
					f("mdn_enabled", "MDN Enabled", "Check") +
						f("mdn_mode", "MDN Mode", "Select", { options: "\nSynchronous\nAsynchronous" })
				)
			),
			this.panel(
				"security",
				false,
				this.section(
					"Security",
					f("encryption_enabled", "Encryption Enabled", "Check") +
						f("signing_enabled", "Signing Enabled", "Check")
				)
			),
			this.panel(
				"advanced",
				false,
				this.section(
					"Advanced",
					f("local_partner_name", "Local Partner Name", "Data") +
						f("remote_partner_name", "Remote Partner Name", "Data", { readonly: remoteLocked }) +
						f("direction_hint", "How to create", "Small Text", { readonly: true, wide: true })
				)
			),
		].join("");
		const title = creating ? __("Add Partnership") : __("Edit Partnership");
		const action = creating ? __("Create Partnership") : __("Save Partnership");
		const sub = selectedText || __("OpenAS2 Partnership");
		const $modal = $(`
			<div class="oa2-ps-ui oa2-edit-modal-root" data-oa2-theme="${this.theme()}" role="dialog" aria-modal="true" aria-labelledby="oa2-ps-modal-title">
				<div class="oa2-edit-modal-backdrop" data-oa2-ps-cancel="1"></div>
				<div class="oa2-edit-modal">
					<header class="oa2-edit-modal-header">
						<div>
							<h2 id="oa2-ps-modal-title" class="oa2-edit-modal-title">${this.esc(title)}</h2>
							<p class="oa2-edit-modal-sub">${this.esc(sub)}</p>
						</div>
						<button type="button" class="oa2-edit-modal-close" data-oa2-ps-cancel="1" aria-label="${__("Cancel")}">×</button>
					</header>
					<div class="oa2-edit-modal-body oa2-edit-layout">
						<nav class="oa2-edit-nav" aria-label="${__("Partnership sections")}">${nav}</nav>
						<div class="oa2-edit-pane">${panels}</div>
					</div>
					<footer class="oa2-edit-modal-footer">
						<button type="button" class="oa2-edit-btn-cancel" data-oa2-ps-cancel="1">${__("Cancel")}</button>
						<button type="button" class="oa2-edit-btn-update">${action}</button>
					</footer>
				</div>
			</div>
		`);
		$(document.body).append($modal);
		this.$modal = $modal;
		this.refresh_hint();
		$modal.on("click", ".oa2-edit-nav-btn", (e) => {
			e.preventDefault();
			const key = $(e.currentTarget).attr("data-section");
			$modal.find(".oa2-edit-nav-btn").removeClass("is-active");
			$(e.currentTarget).addClass("is-active");
			$modal.find("[data-section-panel]").attr("hidden", true);
			$modal.find(`[data-section-panel="${key}"]`).removeAttr("hidden");
		});
		$modal.on("click", "[data-oa2-ps-cancel]", (e) => {
			e.preventDefault();
			this.close();
		});
		$modal.on("change", "[data-fieldname='local_partner'], [data-fieldname='remote_partner']", (e) => {
			const field = $(e.currentTarget).attr("data-fieldname");
			this.apply_partner(field === "local_partner" ? "local" : "remote");
			this.refresh_hint();
		});
		$modal.on("change", "[data-fieldname='local_certificate'], [data-fieldname='remote_certificate']", (e) => {
			const field = $(e.currentTarget).attr("data-fieldname");
			const side = field.indexOf("local") === 0 ? "local" : "remote";
			const cert = (this.certs || []).find((c) => c.name === $(e.currentTarget).val());
			if (cert && cert.x509_alias) this.$modal.find(`[data-fieldname='${side}_x509_alias']`).val(cert.x509_alias);
		});
		$modal.on("click", ".oa2-edit-btn-update", (e) => {
			e.preventDefault();
			this.save();
		});
		$modal.on("keydown", (e) => {
			if (e.key === "Escape") {
				e.preventDefault();
				this.close();
			}
		});
	},

	apply_partner(side) {
		const name = this.$modal.find(`[data-fieldname='${side}_partner']`).val();
		const row = (this.partners || []).find((p) => p.name === name);
		if (!row) return;
		this.$modal.find(`[data-fieldname='${side}_partner_name']`).val(row.partner_name || "");
		this.$modal.find(`[data-fieldname='${side}_as2_id']`).val(row.as2_id || "");
		if (side === "remote" && row.as2_url && !this.$modal.find("[data-fieldname='remote_url']").val()) {
			this.$modal.find("[data-fieldname='remote_url']").val(row.as2_url);
		}
		if (row.certificate) {
			this.$modal.find(`[data-fieldname='${side}_certificate']`).val(row.certificate);
			const cert = (this.certs || []).find((c) => c.name === row.certificate);
			if (cert && cert.x509_alias) this.$modal.find(`[data-fieldname='${side}_x509_alias']`).val(cert.x509_alias);
		}
	},

	refresh_hint() {
		if (!this.$modal) return;
		const local =
			this.$modal.find("[data-fieldname='local_partner_name']").val() ||
			this.$modal.find("[data-fieldname='local_as2_id']").val() ||
			__("Local");
		const remote =
			this.$modal.find("[data-fieldname='remote_partner_name']").val() ||
			this.$modal.find("[data-fieldname='remote_as2_id']").val() ||
			(this.partner && this.partner.partner_name) ||
			__("Remote");
		this.$modal
			.find("[data-fieldname='direction_hint']")
			.val(
				__("Creates outbound") +
					" " +
					local +
					" → " +
					remote +
					". " +
					__(
						"Save stores the record here. On the partnership list, Preview checks the file and Apply writes partnerships.xml. OpenAS2 is not started."
					)
			);
	},

	collect() {
		const updates = {};
		this.$modal.find("[data-fieldname]").each((_, el) => {
			const $el = $(el);
			if ($el.is(":disabled") || $el.prop("readonly")) return;
			const fieldname = $el.attr("data-fieldname");
			updates[fieldname] = $el.attr("data-type") === "Check" ? ($el.is(":checked") ? 1 : 0) : $el.val();
		});
		if (this.mode === "create" && this.linked_partner) {
			updates.remote_partner = this.linked_partner;
		} else if (this.lock_side === "remote" && this.partner) {
			updates.remote_partner = this.partner.name;
		} else if (this.lock_side === "local" && this.partner) {
			updates.local_partner = this.partner.name;
		}
		return updates;
	},

	save() {
		if (this.saving) return;
		const values = this.collect();
		const partner = this.partner || {};
		["local", "remote"].forEach((side) => {
			const row = (this.partners || []).find((p) => p.name === values[side + "_partner"]);
			if (!row) return;
			if (!values[side + "_partner_name"]) values[side + "_partner_name"] = row.partner_name || "";
			if (!values[side + "_as2_id"]) values[side + "_as2_id"] = row.as2_id || "";
			if (side === "remote" && !values.remote_url) values.remote_url = row.as2_url || "";
			if (!values[side + "_certificate"] && row.certificate) values[side + "_certificate"] = row.certificate;
			const cert = (this.certs || []).find((c) => c.name === (values[side + "_certificate"] || ""));
			if (cert && cert.x509_alias && !values[side + "_x509_alias"]) values[side + "_x509_alias"] = cert.x509_alias;
		});
		if (!values.instance || !values.local_partner || !values.remote_partner) {
			frappe.msgprint(__("OpenAS2 Instance, Local Partner, and Remote Partner are required."));
			return;
		}
		if (values.local_partner === values.remote_partner) {
			frappe.msgprint(__("Local Partner and Remote Partner must be different."));
			return;
		}
		const url = (values.remote_url || "").trim();
		if (!/^https?:\/\//i.test(url)) {
			frappe.msgprint(__("Remote AS2 URL must start with http:// or https://."));
			return;
		}
		if (cint(values.mdn_enabled) && !values.mdn_mode) {
			frappe.msgprint(__("MDN Mode is required when MDN is enabled."));
			return;
		}
		const payload = {
			instance: values.instance,
			status: values.status || "Draft",
			description: values.description || "",
			local_partner: values.local_partner,
			local_partner_name: values.local_partner_name || "",
			local_as2_id: values.local_as2_id || "",
			local_x509_alias: values.local_x509_alias || "",
			remote_partner: values.remote_partner,
			remote_partner_name: values.remote_partner_name || partner.partner_name || "",
			remote_as2_id: values.remote_as2_id || partner.as2_id || "",
			remote_url: url,
			encryption_enabled: values.encryption_enabled ? 1 : 0,
			signing_enabled: values.signing_enabled ? 1 : 0,
			mdn_enabled: values.mdn_enabled ? 1 : 0,
			mdn_mode: values.mdn_enabled ? values.mdn_mode : null,
		};
		if (creating && this.linked_partner) {
			payload.remote_partner = this.linked_partner;
			const linked =
				(this.partners || []).find((p) => p.name === this.linked_partner) || this.partner || {};
			if (!payload.remote_partner_name) payload.remote_partner_name = linked.partner_name || "";
			if (!payload.remote_as2_id) payload.remote_as2_id = linked.as2_id || linked.name || "";
			if (!payload.remote_url && linked.as2_url) payload.remote_url = linked.as2_url;
		}
		if (values.partnership_name) payload.partnership_name = values.partnership_name;
		if (values.local_certificate) payload.local_certificate = values.local_certificate;
		if (values.remote_certificate) payload.remote_certificate = values.remote_certificate;
		if (values.remote_x509_alias) payload.remote_x509_alias = values.remote_x509_alias;
		const creating = this.mode === "create";
		const $btn = this.$modal.find(".oa2-edit-btn-update");
		this.saving = true;
		$btn.prop("disabled", true).text(__("Saving…"));
		frappe.call({
			method: creating ? "frappe.client.insert" : "frappe.client.set_value",
			args: creating
				? { doc: Object.assign({ doctype: "OpenAS2 Partnership" }, payload) }
				: { doctype: "OpenAS2 Partnership", name: (this.doc && this.doc.name) || "", fieldname: payload },
			callback: (r) => {
				this.saving = false;
				if (!r || r.exc || (creating && (!r.message || !r.message.name))) {
					$btn.prop("disabled", false).text(creating ? __("Create Partnership") : __("Save Partnership"));
					return;
				}
				frappe.show_alert({
					message: creating ? __("Partnership created") : __("Partnership saved"),
					indicator: "green",
				});
				const saved = this.on_save;
				this.close();
				if (saved) saved(r.message);
			},
			error: () => {
				this.saving = false;
				$btn.prop("disabled", false).text(creating ? __("Create Partnership") : __("Save Partnership"));
			},
		});
	},
};
