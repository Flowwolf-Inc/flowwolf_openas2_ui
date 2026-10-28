# Copyright (c) 2026, Lakshana and contributors
# For license information, please see license.txt

"""Natural-language control and analysis over existing OpenAS2 records.

Reads and writes go through existing DocTypes and whitelisted APIs.
No arbitrary SQL, Python, or shell. Analysis uses stored fields only.
"""

from __future__ import annotations

import json
import re
import secrets

import frappe
from frappe.utils import add_days, getdate, now_datetime

PARTNER_TYPES = ("Shipper", "Broker", "Carrier", "CompanyC")
PARTNER_FIELDS = [
	"name",
	"partner_name",
	"partner_type",
	"as2_id",
	"status",
	"as2_url",
	"encryption_enabled",
	"signing_enabled",
	"mdn_enabled",
	"mdn_mode",
	"certificate",
]
PARTNERSHIP_FIELDS = [
	"name",
	"partnership_name",
	"instance",
	"status",
	"local_partner",
	"remote_partner",
	"local_partner_name",
	"remote_partner_name",
	"local_as2_id",
	"remote_as2_id",
	"remote_url",
	"local_certificate",
	"remote_certificate",
	"local_x509_alias",
	"remote_x509_alias",
	"mdn_enabled",
	"mdn_mode",
	"encryption_enabled",
	"signing_enabled",
]
CERTIFICATE_FIELDS = [
	"name",
	"certificate_name",
	"purpose",
	"owner_type",
	"openas2_instance",
	"x509_alias",
	"certificate_type",
	"status",
	"common_name",
	"organization",
	"valid_from",
	"valid_until",
	"exchange_partner",
	"exchange_status",
]
CONFIG_FIELDS = [
	"name",
	"instance_name",
	"instance_type",
	"as2_id",
	"host",
	"status",
	"protocol",
	"http_enabled",
	"https_enabled",
	"http_port",
	"https_port",
	"mdn_enabled",
	"mdn_mode",
	"published_as2_url",
	"connection_status",
]
HIDDEN = {
	"keystore_password",
	"as2_keystore_password",
	"password",
	"api_secret",
	"api_key",
	"private_key",
	"certificate_file",
	"keystore_path",
	"as2_keystore_path",
	"ssl_keystore_path",
}


def _require_user() -> None:
	if frappe.session.user in (None, "", "Guest"):
		frappe.throw(frappe._("Please sign in."), frappe.PermissionError)


_SESSION_STORE: dict[str, dict] = {}


def _cache_get(key: str) -> dict:
	if _SESSION_STORE.get(key):
		return dict(_SESSION_STORE[key])
	raw = frappe.cache().get_value(key)
	if not raw:
		return {}
	if isinstance(raw, dict):
		return raw
	try:
		parsed = json.loads(raw)
	except (TypeError, ValueError):
		return {}
	return parsed if isinstance(parsed, dict) else {}


def _cache_set(key: str, value: dict | None) -> None:
	if not value:
		_SESSION_STORE.pop(key, None)
		frappe.cache().delete_value(key)
		return
	payload = json.loads(json.dumps(value, default=str))
	_SESSION_STORE[key] = payload
	frappe.cache().set_value(key, payload)


def _draft_key() -> str:
	return f"oa2_ai_draft:{frappe.session.user}"


def _pending_key() -> str:
	return f"oa2_ai_pending:{frappe.session.user}"


def _parse_context(context) -> dict:
	if isinstance(context, dict):
		return context
	if isinstance(context, str) and context.strip():
		try:
			parsed = json.loads(context)
		except ValueError:
			return {}
		return parsed if isinstance(parsed, dict) else {}
	return {}


def _allowed_instances() -> list[str] | None:
	from openas2_manager.access import get_allowed_instance_names

	return get_allowed_instance_names()


def _instance_filters() -> dict:
	allowed = _allowed_instances()
	if allowed is None:
		return {}
	return {"instance": ["in", allowed or ["__none__"]]}


def _partner_rows() -> list[dict]:
	from openas2_manager.access import visible_partner_names

	names = visible_partner_names()
	filters = {}
	if names is not None:
		filters["name"] = ["in", names or ["__none__"]]
	return frappe.get_all(
		"AS2 Partner",
		filters=filters,
		fields=PARTNER_FIELDS,
		order_by="partner_name asc",
		limit_page_length=200,
	)


def _find_partner(text: str | None) -> dict | None:
	needle = (text or "").strip().lower()
	if not needle:
		return None
	for row in _partner_rows():
		if needle in {
			(row.name or "").lower(),
			(row.partner_name or "").lower(),
			(row.as2_id or "").lower(),
		}:
			return row
	for row in _partner_rows():
		if needle in (row.partner_name or "").lower() or needle in (row.as2_id or "").lower():
			return row
	return None


def _config_rows() -> list[dict]:
	allowed = _allowed_instances()
	filters = {}
	if allowed is not None:
		filters["name"] = ["in", allowed or ["__none__"]]
	return frappe.get_all(
		"OpenAS2 Instance",
		filters=filters,
		fields=CONFIG_FIELDS,
		order_by="instance_name asc",
		limit_page_length=100,
	)


def _find_configuration(text: str | None) -> dict | None:
	needle = (text or "").strip().lower()
	if not needle:
		return None
	for row in _config_rows():
		labels = {
			(row.name or "").lower(),
			(row.instance_name or "").lower(),
			(row.as2_id or "").lower(),
			(row.instance_type or "").lower(),
		}
		if needle in labels:
			return row
	return None


def _one_instance_name() -> str | None:
	rows = _config_rows()
	if len(rows) == 1:
		return rows[0].name
	return None


def _reply(text: str, **extra) -> dict:
	links = extra.pop("links", None)
	payload = {"reply": text, "kind": extra.pop("kind", "message")}
	if links:
		payload["links"] = [item for item in links if item]
	payload.update(extra)
	return payload


def _reply_list(title: str, rows: list, formatter, builder, kind: str = "message") -> dict:
	listing = _lines(rows, formatter) if rows else ""
	body = title
	if listing and listing != "No matching records are stored.":
		body = f"{title}\n{listing}"
	return _reply(body, kind=kind, links=_links_from(rows, builder))


def _lines(rows: list[dict], formatter) -> str:
	if not rows:
		return "No matching records are stored."
	body = [formatter(row) for row in rows[:30]]
	if len(rows) > 30:
		body.append(f"{len(rows) - 30} more records are not listed here.")
	return "\n".join(body)


def _link(kind: str, name: str | None, title: str, **extra) -> dict | None:
	"""One navigable record for the assistant UI. name is the Frappe document name."""
	docname = (name or "").strip()
	if not docname and kind != "logs":
		return None
	item = {"type": kind, "name": docname, "title": (title or docname).strip() or docname}
	for key, value in extra.items():
		if value not in (None, ""):
			item[key] = value
	return item


def _partner_link(row) -> dict | None:
	return _link(
		"partner",
		row.get("name") if isinstance(row, dict) else row.name,
		(row.get("partner_name") if isinstance(row, dict) else row.partner_name) or "",
		subtitle=f"AS2 ID {(row.get('as2_id') if isinstance(row, dict) else row.as2_id) or '—'} · "
		f"{(row.get('partner_type') if isinstance(row, dict) else row.partner_type) or '—'}",
		meta=(row.get("status") if isinstance(row, dict) else row.status) or "",
	)


def _partnership_link(row, partner: str | None = None) -> dict | None:
	local = (row.get("local_partner") if isinstance(row, dict) else row.local_partner) or ""
	remote = (row.get("remote_partner") if isinstance(row, dict) else row.remote_partner) or ""
	partner_name = partner or local or remote
	title = (row.get("partnership_name") if isinstance(row, dict) else row.partnership_name) or ""
	local_label = (row.get("local_partner_name") if isinstance(row, dict) else row.local_partner_name) or (
		row.get("local_as2_id") if isinstance(row, dict) else row.local_as2_id
	)
	remote_label = (row.get("remote_partner_name") if isinstance(row, dict) else row.remote_partner_name) or (
		row.get("remote_as2_id") if isinstance(row, dict) else row.remote_as2_id
	)
	return _link(
		"partnership",
		row.get("name") if isinstance(row, dict) else row.name,
		title,
		partner=partner_name,
		subtitle=f"{local_label or '—'} → {remote_label or '—'}",
		meta=(row.get("status") if isinstance(row, dict) else row.status) or "",
	)


def _certificate_link(row) -> dict | None:
	return _link(
		"certificate",
		row.get("name") if isinstance(row, dict) else row.name,
		(row.get("certificate_name") if isinstance(row, dict) else row.certificate_name) or "",
		subtitle=f"{(row.get('purpose') if isinstance(row, dict) else row.purpose) or '—'} · "
		f"alias {(row.get('x509_alias') if isinstance(row, dict) else row.x509_alias) or '—'}",
		meta=(row.get("status") if isinstance(row, dict) else row.status) or "",
	)


def _configuration_link(row) -> dict | None:
	return _link(
		"configuration",
		row.get("name") if isinstance(row, dict) else row.name,
		(row.get("instance_name") if isinstance(row, dict) else row.instance_name) or "",
		subtitle=f"{(row.get('instance_type') if isinstance(row, dict) else row.instance_type) or '—'} · "
		f"AS2 ID {(row.get('as2_id') if isinstance(row, dict) else row.as2_id) or '—'}",
		meta=(row.get("status") if isinstance(row, dict) else row.status) or "",
	)


def _edi_link(row) -> dict | None:
	data = row if isinstance(row, dict) else dict(row)
	title = f"{data.get('transaction_type') or 'EDI'} — {data.get('file_name') or data.get('name') or ''}".strip(" —")
	return _link(
		"edi",
		data.get("name"),
		title,
		subtitle=f"{data.get('sent_from') or '—'} → {data.get('received_by') or '—'}",
		meta=data.get("status") or "",
		when=str(data.get("document_timestamp") or ""),
	)


def _log_link(row) -> dict | None:
	data = row if isinstance(row, dict) else dict(row)
	search = data.get("file_name") or data.get("message_id") or data.get("name") or ""
	title = (data.get("error_message") or data.get("status") or "Log")[:120]
	return _link(
		"log",
		data.get("name"),
		title,
		search=search,
		edi=data.get("edi_document") or "",
		subtitle=str(data.get("timestamp") or data.get("creation") or ""),
		meta=data.get("status") or "",
	)


def _links_from(rows: list, builder, limit: int = 30) -> list[dict]:
	out = []
	for row in (rows or [])[:limit]:
		item = builder(row)
		if item:
			out.append(item)
	return out


def _analysis_links(found: dict) -> list[dict]:
	summary = found.get("summary") or {}
	partnership = found.get("partnership") or {}
	links = []
	edi = _edi_link(
		{
			"name": summary.get("name"),
			"transaction_type": summary.get("transaction_type"),
			"file_name": summary.get("file_name"),
			"sent_from": summary.get("sent_from"),
			"received_by": summary.get("received_by"),
			"status": summary.get("status"),
			"document_timestamp": summary.get("timestamp"),
		}
	)
	if edi:
		links.append(edi)
	partner_label = (summary.get("partner") or "").strip()
	if partner_label:
		partner = _find_partner(partner_label)
		if partner:
			item = _partner_link(partner)
			if item:
				links.append(item)
	if partnership.get("name") or partnership.get("partnership_name"):
		partner_for = ""
		if partner_label:
			found_partner = _find_partner(partner_label)
			partner_for = found_partner.name if found_partner else ""
		item = _partnership_link(partnership, partner_for or partnership.get("local_partner"))
		if item:
			links.append(item)
	return links


def get_partners() -> list[dict]:
	return _partner_rows()


def get_partner(name: str) -> dict | None:
	return _find_partner(name)


def get_partnerships(partner: str | None = None) -> list[dict]:
	filters = {}
	allowed = _allowed_instances()
	if allowed is not None:
		filters["instance"] = ["in", allowed or ["__none__"]]
	or_filters = None
	found = _find_partner(partner) if partner else None
	if found:
		or_filters = [
			["local_partner", "=", found.name],
			["remote_partner", "=", found.name],
		]
	return frappe.get_all(
		"OpenAS2 Partnership",
		filters=filters,
		or_filters=or_filters,
		fields=PARTNERSHIP_FIELDS,
		order_by="partnership_name asc",
		limit_page_length=200,
	)


def get_partner_partnerships(partner: str) -> list[dict]:
	return get_partnerships(partner)


def get_certificates(partner: str | None = None) -> list[dict]:
	filters: dict = {}
	allowed = _allowed_instances()
	if allowed is not None:
		filters["openas2_instance"] = ["in", allowed or ["__none__"]]
	found = _find_partner(partner) if partner else None
	if found:
		filters["exchange_partner"] = found.name
	rows = frappe.get_all(
		"AS2 Certificate",
		filters=filters,
		fields=CERTIFICATE_FIELDS,
		order_by="certificate_name asc",
		limit_page_length=200,
	)
	if found and not rows:
		# Own certificates are linked from the partner, not exchange_partner.
		cert_name = frappe.db.get_value("AS2 Partner", found.name, "certificate")
		if cert_name and frappe.db.exists("AS2 Certificate", cert_name):
			row = frappe.db.get_value("AS2 Certificate", cert_name, CERTIFICATE_FIELDS, as_dict=True)
			if row:
				return [row]
	return rows


def get_certificate(name: str) -> dict | None:
	needle = (name or "").strip().lower()
	for row in get_certificates():
		if needle in {
			(row.name or "").lower(),
			(row.certificate_name or "").lower(),
			(row.x509_alias or "").lower(),
			(row.common_name or "").lower(),
		}:
			return row
	return None


def get_configurations() -> list[dict]:
	return _config_rows()


def get_configuration(name: str) -> dict | None:
	return _find_configuration(name)


def get_edi_transactions(**kwargs) -> dict:
	from openas2_manager.openas2.tms_edi import get_edi_documents

	return get_edi_documents(**kwargs)


def get_failed_edi_transactions(**kwargs) -> dict:
	kwargs["status"] = "Failed"
	return get_edi_transactions(**kwargs)


def get_logs(**kwargs) -> dict:
	from openas2_manager.openas2.monitoring import get_messages

	kwargs.setdefault("errors_only", 1)
	kwargs.setdefault("limit", 40)
	return get_messages(**kwargs)


def get_monitoring_data() -> dict:
	from openas2_manager.openas2.monitoring import get_dashboard_summary

	return get_dashboard_summary()


def _fmt_partner(row) -> str:
	return (
		f"{row.partner_name} · type {row.partner_type} · AS2 ID {row.as2_id} · "
		f"{row.status} · {row.as2_url}"
	)


def _fmt_partnership(row) -> str:
	return (
		f"{row.partnership_name} · {row.local_partner_name or row.local_as2_id} → "
		f"{row.remote_partner_name or row.remote_as2_id} · {row.status} · instance {row.instance}"
	)


def _fmt_cert(row) -> str:
	return (
		f"{row.certificate_name} · {row.purpose} · {row.owner_type} · "
		f"alias {row.x509_alias} · {row.status}"
	)


def _fmt_config(row) -> str:
	return (
		f"{row.instance_name} · {row.instance_type} · AS2 ID {row.as2_id} · "
		f"{row.status} · {row.host or 'host not stored'}"
	)


def _fmt_edi(row) -> str:
	when = row.get("document_timestamp") or ""
	return (
		f"{row.get('transaction_type') or 'EDI'} {row.get('file_name') or row.get('name')} · "
		f"{row.get('sent_from') or '—'} → {row.get('received_by') or '—'} · "
		f"{row.get('status') or '—'} · MDN {row.get('mdn_status') or '—'} · {when}"
	)


def _today():
	return getdate(now_datetime())


def _edi_by_reference(text: str) -> list[dict]:
	from openas2_manager.openas2.tms_edi import get_edi_documents

	result = get_edi_documents(limit=500)
	needle = (text or "").strip().lower()
	rows = []
	for row in result.get("rows") or []:
		hay = " ".join(
			str(row.get(key) or "")
			for key in ("file_name", "tms_doc_name", "reference_number", "as2_message_id", "name")
		).lower()
		if needle and re.search(rf"(^|[^a-z0-9]){re.escape(needle)}([^a-z0-9]|$)", hay):
			rows.append(row)
	return rows


def _unique_reference_rows(rows: list[dict]) -> list[dict]:
	"""One card per stored file, in load-tender order rather than newest-document order."""
	seen = set()
	unique = []
	for row in rows or []:
		key = (row.get("file_name") or row.get("name") or "").strip().lower()
		if not key or key in seen:
			continue
		seen.add(key)
		unique.append(row)
	order = {"204": 0, "990": 1, "214": 2, "210": 3, "810": 4, "820": 5}
	unique.sort(
		key=lambda row: (
			order.get(str(row.get("transaction_type") or ""), 9),
			str(row.get("file_name") or ""),
		)
	)
	return unique


def _asks_failure(text: str) -> bool:
	return bool(re.search(r"\b(why|fail|error|analyze|analyse|cause|issue)\b", _normalize(text)))


def _load_reply(needle: str, rows: list[dict]) -> dict:
	shown = _unique_reference_rows(rows)
	statuses = {(row.get("status") or "Unknown") for row in shown}
	if statuses == {"Success"}:
		state = "All of them succeeded."
	elif "Failed" in statuses:
		failed = sum(1 for row in shown if row.get("status") == "Failed")
		state = f"{failed} of them {'is' if failed == 1 else 'are'} stored as Failed."
	else:
		state = "Statuses: " + ", ".join(sorted(statuses)) + "."
	title = f"{needle} is on {len(shown)} stored transaction(s). {state}"
	return _reply_list(title, shown, _fmt_edi, _edi_link)


def _related_logs(message_id: str | None, instance: str | None) -> dict:
	"""Remote message rows for one Message-ID. A database failure is an error, not a local log."""
	if not message_id:
		return {"rows": [], "error": None}
	if instance:
		from openas2_manager.access import assert_instance_access

		assert_instance_access(instance)
	from openas2_manager.openas2.remote_tracking import REMOTE_READ_ERROR, list_live_messages

	live = list_live_messages(
		instance=instance or None,
		message_id=message_id,
		limit=8,
		include_type_preview=False,
	)
	if live is None:
		return {"rows": [], "error": REMOTE_READ_ERROR}
	return {"rows": live.get("rows") or [], "error": None}


def _control_number(edi_content: str | None) -> str:
	text = edi_content or ""
	match = re.search(r"ST\*\d{3}\*([^*\r\n~]+)", text)
	if match:
		return match.group(1).strip()
	match = re.search(r"ISA\*.{0,400}?(\d{9})(?:\*|~)", text)
	return match.group(1) if match else ""


def _classify_failure(status: str, mdn_status: str, errors: list[str]) -> dict:
	blob = "\n".join(errors).strip()
	lower = blob.lower()
	stage = ""
	confidence = ""
	cause = ""
	fix = ""
	if not blob and (status or "") not in ("Failed",) and (mdn_status or "") not in ("Failed", "Pending"):
		return {
			"stage": "",
			"confidence": "",
			"cause": "",
			"fix": "",
			"evidence": "",
		}
	if "int64" in lower and "json serializable" in lower:
		stage = "JSON serialization"
		confidence = "confirmed"
		cause = (
			"The transaction failed during JSON serialization. A value is being returned "
			"as an int64 object instead of a native Python integer."
		)
		fix = "Convert that integer to a plain int before it is written into JSON."
	elif "not json serializable" in lower:
		stage = "JSON serialization"
		confidence = "confirmed"
		cause = "The transaction failed while converting the document into JSON."
		fix = "Convert the non-JSON value to a string, number, or null before saving the JSON."
	elif any(word in lower for word in ("certificate", "x509", "keystore", "signature verify", "sign failure")):
		stage = "certificate processing"
		confidence = "confirmed" if "certificate" in lower or "x509" in lower else "likely"
		cause = "The stored error refers to certificate or signature processing."
		fix = "Check the certificate alias and validity dates on the partnership. Do not change them until you confirm the alias matches the file."
	elif "mdn" in lower and any(word in lower for word in ("fail", "timeout", "error", "pending")):
		stage = "MDN generation"
		confidence = "likely"
		cause = "The stored error mentions the MDN."
		fix = "Compare the MDN status on this transaction with the partner MDN setting on the partnership."
	elif any(word in lower for word in ("parse", "segment", "isa*", "delimiter", "invalid edi")):
		stage = "parsing"
		confidence = "likely"
		cause = "The stored error refers to reading the EDI segments."
		fix = "Open the EDI tab and check the ST segment and separators against the trading partner's expected format."
	elif any(word in lower for word in ("timed out", "timeout", "connection refused", "unreachable", "connect")):
		stage = "transmission"
		confidence = "likely"
		cause = "The stored error refers to connecting to the remote AS2 URL."
		fix = "Confirm the remote AS2 URL on the partnership and that the partner endpoint is reachable."
	elif any(word in lower for word in ("unauthorized", "forbidden", "authentication", "permission")):
		stage = "authentication/authorization"
		confidence = "likely"
		cause = "The stored error refers to authorization."
		fix = "Check the user permissions for this instance. This did not retry or change those permissions."
	elif (mdn_status or "") == "Pending" and (status or "") != "Failed":
		stage = "MDN generation"
		confidence = "likely"
		cause = "The stored MDN status is Pending. The records do not include a separate MDN error."
		fix = "Wait for the next monitoring check, then open the related log if the MDN is still pending."
	elif (status or "") == "Failed" and not blob:
		stage = ""
		confidence = ""
		cause = "Insufficient information to determine the cause."
		fix = "Open the related OpenAS2 log for this message id. No error text is stored on the transaction."
	elif blob:
		stage = "OpenAS2 processing"
		confidence = "likely"
		cause = "The failure is the error text stored on the transaction or its message log. A more specific stage is not identified."
		fix = "Use the error text below as the evidence. Do not apply a change until that text identifies the field to fix."
	else:
		cause = "Insufficient information to determine the cause."
		fix = ""
	return {
		"stage": stage,
		"confidence": confidence,
		"cause": cause,
		"fix": fix,
		"evidence": blob[:1200],
	}


def analyze_edi_record(name: str) -> dict:
	from openas2_manager.openas2.tms_edi import get_edi_document_details

	doc = get_edi_document_details(name)
	related = _related_logs(doc.get("as2_message_id"), doc.get("instance"))
	logs = related.get("rows") or []
	errors = [doc.get("summary") or ""]
	errors.extend((row.get("error_message") or "") for row in logs)
	errors = [item.strip() for item in errors if item and item.strip() and item.strip() != (doc.get("summary") or "")]
	if doc.get("status") == "Failed" and doc.get("as2_status"):
		errors.append(f"AS2 status: {doc.get('as2_status')}")
	failure = _classify_failure(doc.get("status") or "", doc.get("mdn_status") or "", errors)
	partnerships = []
	local_id = ""
	remote_id = ""
	for row in logs:
		local_id = local_id or row.get("local_as2_id") or ""
		remote_id = remote_id or row.get("remote_as2_id") or ""
	if local_id and remote_id:
		if (doc.get("direction") or "") == "Inbound":
			sender_id, receiver_id = remote_id, local_id
		else:
			sender_id, receiver_id = local_id, remote_id
		p_filters = {"local_as2_id": sender_id, "remote_as2_id": receiver_id}
		allowed = _allowed_instances()
		if allowed is not None:
			p_filters["instance"] = ["in", allowed or ["__none__"]]
		partnerships = frappe.get_all(
			"OpenAS2 Partnership",
			filters=p_filters,
			fields=[
				"name",
				"partnership_name",
				"local_partner",
				"remote_partner",
				"local_partner_name",
				"remote_partner_name",
				"local_as2_id",
				"remote_as2_id",
				"local_certificate",
				"remote_certificate",
				"local_x509_alias",
				"remote_x509_alias",
				"remote_url",
				"mdn_mode",
				"status",
			],
			limit_page_length=3,
		)
	sender_cert = ""
	receiver_cert = ""
	if partnerships:
		sender_cert = partnerships[0].get("local_certificate") or partnerships[0].get("local_x509_alias") or ""
		receiver_cert = partnerships[0].get("remote_certificate") or partnerships[0].get("remote_x509_alias") or ""
	edi = doc.get("edi_content") or ""
	control = _control_number(edi)
	summary = {
		"name": doc.get("name"),
		"transaction_type": doc.get("transaction_type") or "",
		"file_name": doc.get("file_name") or "",
		"sent_from": doc.get("sent_from") or "",
		"received_by": doc.get("received_by") or "",
		"sender_as2_id": local_id if doc.get("direction") != "Inbound" else remote_id,
		"receiver_as2_id": remote_id if doc.get("direction") != "Inbound" else local_id,
		"sender_certificate": sender_cert,
		"receiver_certificate": receiver_cert,
		"direction": doc.get("direction") or "",
		"control_number": control,
		"status": doc.get("status") or "",
		"mdn_status": doc.get("mdn_status") or "",
		"partner": doc.get("partner_name") or "",
		"partnership": partnerships[0].get("partnership_name") if partnerships else "",
		"timestamp": str(doc.get("document_timestamp") or ""),
		"instance": doc.get("instance") or "",
		"edi_present": bool(edi),
		"edi_characters": len(edi),
		"json_present": bool(doc.get("json_content")),
	}
	return {
		"summary": summary,
		"failure": failure,
		"logs": logs,
		"logs_error": related.get("error"),
		"partnership": partnerships[0] if partnerships else {},
	}


def _analysis_text(found: dict) -> str:
	summary = found.get("summary") or {}
	failure = found.get("failure") or {}
	parts = [
		"Transaction summary",
		f"Type: {summary.get('transaction_type') or 'not stored'}",
		f"File: {summary.get('file_name') or summary.get('name')}",
		f"Sent from: {summary.get('sent_from') or 'not stored'}",
		f"Received by: {summary.get('received_by') or 'not stored'}",
		f"Sender AS2 ID: {summary.get('sender_as2_id') or 'not stored on the message log'}",
		f"Receiver AS2 ID: {summary.get('receiver_as2_id') or 'not stored on the message log'}",
		f"Sender certificate: {summary.get('sender_certificate') or 'not stored on the partnership'}",
		f"Receiver certificate: {summary.get('receiver_certificate') or 'not stored on the partnership'}",
		f"Direction: {summary.get('direction') or 'not stored'}",
		f"Control number: {summary.get('control_number') or 'not found in the stored EDI'}",
		f"Processing status: {summary.get('status') or 'not stored'}",
		f"MDN status: {summary.get('mdn_status') or 'not stored'}",
		f"Partner: {summary.get('partner') or 'not stored'}",
		f"Partnership: {summary.get('partnership') or 'no matching partnership record'}",
		f"Time: {summary.get('timestamp') or 'not stored'}",
	]
	if summary.get("edi_present"):
		parts.append(f"Raw EDI is stored ({summary.get('edi_characters')} characters).")
	else:
		parts.append("Raw EDI is not stored for this document.")
	if summary.get("json_present"):
		parts.append("Parsed JSON is stored.")
	else:
		parts.append("Parsed JSON is not stored.")
	parts.append("")
	parts.append("Issue")
	if failure.get("stage"):
		parts.append(f"What failed: {failure.get('stage')}")
	elif (summary.get("status") or "") == "Success" and (summary.get("mdn_status") or "") not in ("Pending", "Failed"):
		parts.append("This transaction is stored as Success. No failure is recorded.")
	else:
		parts.append(failure.get("cause") or "Insufficient information to determine the cause.")
	parts.append("")
	parts.append("Evidence")
	parts.append(failure.get("evidence") or "No error text is stored on this transaction or its message log.")
	parts.append("")
	parts.append("Cause")
	if failure.get("confidence") == "confirmed":
		parts.append(failure.get("cause") or "")
	elif failure.get("confidence") == "likely":
		parts.append(f"Likely cause: {failure.get('cause')}")
	else:
		parts.append(failure.get("cause") or "Insufficient information to determine the cause.")
	parts.append("")
	parts.append("Impact")
	parts.append(
		f"{summary.get('transaction_type') or 'This'} {summary.get('direction') or ''} document "
		f"for {summary.get('sent_from') or 'the sender'} to {summary.get('received_by') or 'the receiver'} "
		f"is {summary.get('status') or 'in an unknown status'}."
	)
	parts.append("")
	parts.append("Suggested fix")
	parts.append(failure.get("fix") or "No change is suggested, because the stored records do not identify one.")
	parts.append("")
	parts.append("Related data")
	parts.append(
		f"Transaction {summary.get('name')} · partnership {summary.get('partnership') or 'none'} · "
		f"MDN {summary.get('mdn_status') or 'not stored'}"
	)
	if found.get("logs_error"):
		parts.append("Related logs")
		parts.append(found["logs_error"])
	logs = found.get("logs") or []
	if logs and not found.get("logs_error"):
		parts.append("Related logs")
		for row in logs[:5]:
			err = (row.get("error_message") or "").strip()
			parts.append(
				f"{row.get('timestamp')} · {row.get('status')} · MDN {row.get('mdn_status')}"
				+ (f" · {err[:240]}" if err else "")
			)
	return "\n".join(parts)


def _activity_text() -> str:
	data = get_monitoring_data()
	txn = data.get("transaction_summary") or {}
	cards = data.get("edi_status_by_type") or {}
	type_bits = []
	for code in ("204", "990", "214", "210"):
		bucket = cards.get(code) or {}
		if bucket:
			type_bits.append(
				f"{code}: {bucket.get('total', 0)} total, {bucket.get('success', 0)} success, "
				f"{bucket.get('in_progress', 0)} in progress, {bucket.get('failure', 0)} failed"
			)
	if data.get("messages_error"):
		lines = [data["messages_error"]]
	elif data.get("messages_counts_unavailable"):
		lines = ["Today's message totals are not available from the OpenAS2 database."]
	else:
		lines = [
			f"Messages logged today: {data.get('messages_today', 0)}",
			f"Inbound today: {data.get('inbound', 0)}",
			f"Outbound today: {data.get('outbound', 0)}",
			f"Successful message logs today: {data.get('successful', 0)}",
			f"Failed message logs today: {data.get('failed', 0)}",
			f"Pending MDN today: {data.get('pending_mdn', 0)}",
		]
	if data.get("edi_counts_available") is False:
		lines.append(data.get("edi_counts_limitation") or "EDI transaction totals are not available from msg_metadata.")
	else:
		lines.append(
			"AS2 messages grouped by EDI type. These are not unique business transactions."
		)
		lines.extend(type_bits or ["EDI type totals are not available."])
		if isinstance(txn, dict) and txn:
			lines.append(
				"All stored EDI counts: "
				+ ", ".join(f"{key} {value}" for key, value in txn.items())
			)
		lines.append("These numbers are the current monitoring totals. They are not a sample.")
	return "\n".join(lines)


def _log_analysis(date_from: str | None = None) -> tuple[str, list[dict]]:
	logs = get_logs(limit=40, date_from=date_from)
	if logs.get("error"):
		return logs["error"], []
	rows = logs.get("rows") or []
	if not rows:
		return "No failed or error message logs are stored for your instances.", []
	groups: dict[str, list] = {}
	for row in rows:
		key = ((row.get("error_message") or row.get("status") or "Unknown")[:180]).strip()
		groups.setdefault(key or "Unknown", []).append(row)
	lines = [f"{len(rows)} recent error logs are stored.", ""]
	link_rows = []
	for key, items in list(groups.items())[:8]:
		lines.append(f"{len(items)} · {key}")
		sample = items[0]
		lines.append(
			f"Latest: {sample.get('timestamp') or sample.get('creation') or ''} · "
			f"{sample.get('file_name') or sample.get('message_id') or sample.get('name') or ''}"
		)
		link_rows.append(sample)
	lines.append("")
	lines.append("Grouped by the stored error text. No extra causes were added.")
	return "\n".join(lines), _links_from(link_rows, _log_link, limit=8)


def _log_analysis_text(date_from: str | None = None) -> str:
	text, _links = _log_analysis(date_from=date_from)
	return text


def _normalize_type(value: str | None) -> str:
	text = (value or "").strip().lower().replace(" ", "")
	for item in PARTNER_TYPES:
		if item.lower() == text:
			return item
	return ""


def _grab(pattern: str, text: str) -> str:
	match = re.search(pattern, text, flags=re.I)
	return (match.group(1).strip(" .") if match else "")


def _extract_slots(text: str, action: str) -> dict:
	slots: dict[str, str] = {}
	called = _grab(r"(?:called|named)\s+[\"']?(.+?)[\"']?(?=\s+(?:with|type|as2|url|host|alias|$)|$)", text)
	if called:
		if action in ("create_partner", "update_partner"):
			slots["partner_name"] = called
		elif action in ("create_configuration", "update_configuration"):
			slots["instance_name"] = called
		elif action in ("create_certificate", "update_certificate"):
			slots["certificate_name"] = called
	url = _grab(r"(https?://\S+)", text)
	if url:
		slots["as2_url" if "certificate" not in action else "as2_url"] = url.rstrip(".,)")
		slots["remote_url"] = slots.get("as2_url") or url.rstrip(".,)")
	as2_id = _grab(r"as2\s*id\s*(?:is|=|:)?\s*([A-Za-z0-9_\-]+)", text)
	if as2_id:
		slots["as2_id"] = as2_id
	host = _grab(r"\bhost\s*(?:is|=|:)?\s*([A-Za-z0-9.\-]+)", text)
	if host:
		slots["host"] = host
	alias = _grab(r"(?:alias|x509)\s*(?:is|=|:)?\s*([A-Za-z0-9_\-]+)", text)
	if alias:
		slots["x509_alias"] = alias
	cn = _grab(r"(?:common name|cn)\s*(?:is|=|:)?\s*[\"']?(.+?)[\"']?$", text)
	if cn:
		slots["common_name"] = cn
	status = _grab(r"\bstatus\s*(?:to|is|=|:)?\s*(active|inactive|draft|expired|revoked)\b", text)
	if status:
		slots["status"] = status[:1].upper() + status[1:].lower()
	kind = _normalize_type(_grab(r"\b(?:type|as a|as an)\s+(shipper|broker|carrier|company\s*c)\b", text))
	if not kind:
		kind = _normalize_type(_grab(r"\b(shipper|broker|carrier|company\s*c)\b", text))
	if kind and action in ("create_partner", "update_partner", "create_configuration", "update_configuration", "create_certificate"):
		slots["partner_type"] = kind
		slots["instance_type"] = kind
		slots["owner_type"] = kind
	if re.search(r"partner public", text, re.I):
		slots["purpose"] = "Partner Public Certificate"
	elif re.search(r"own key", text, re.I):
		slots["purpose"] = "Own Key Pair"
	between = re.search(
		r"between\s+[\"']?(.+?)[\"']?\s+and\s+[\"']?(.+?)[\"']?$",
		text,
		flags=re.I,
	)
	if between:
		slots["party_a"] = between.group(1).strip(" .")
		slots["party_b"] = between.group(2).strip(" .")
	with_partner = _grab(r"(?:partnership with|with partner)\s+[\"']?(.+?)[\"']?$", text)
	if with_partner:
		slots["remote_partner"] = with_partner
	status = _grab(r"\bstatus\s*(?:to|is|=|:)?\s*(active|inactive|draft|expired|revoked)\b", text)
	if status:
		slots["status"] = status[:1].upper() + status[1:].lower()
	return {key: value for key, value in slots.items() if value}


def _normalize(text: str) -> str:
	"""Light cleanup so normal wording and small typos still map to a real query."""
	typos = {
		"recorde": "record",
		"recordes": "records",
		"recored": "record",
		"sof": "of",
		"teh": "the",
		"wat": "what",
		"wht": "what",
		"shw": "show",
		"lst": "last",
		"latst": "latest",
		"lates": "latest",
		"transction": "transaction",
		"transctions": "transactions",
		"trasaction": "transaction",
		"trasactions": "transactions",
		"partener": "partner",
		"partnr": "partner",
		"certifcate": "certificate",
		"certficate": "certificate",
		"failng": "failing",
		"falied": "failed",
		"faild": "failed",
		"eror": "error",
		"erro": "error",
	}
	cleaned = re.sub(r"\s+", " ", (text or "").lower()).strip()
	return " ".join(typos.get(word.strip(".,?"), word.strip(".,?")) for word in cleaned.split())


def _log_ai(payload: dict) -> None:
	try:
		frappe.logger("openas2_assistant").info(json.dumps(payload, default=str)[:4000])
	except Exception:
		pass


def _general_answer(text: str) -> str:
	low = _normalize(text)
	if re.search(r"what is (an |a )?mdn|what does mdn mean", low):
		return (
			"An MDN is a Message Disposition Notification. OpenAS2 uses it as the partner's receipt "
			"that an AS2 message arrived. This UI stores that receipt as MDN status on the transaction. "
			"Pending means no receipt is stored yet. Failed means the stored receipt did not succeed."
		)
	if re.search(r"what is (an |a )?as2\b", low):
		return (
			"AS2 is Applicability Statement 2. It is the protocol OpenAS2 uses to send EDI files between "
			"partners over HTTP or HTTPS, with optional signing, encryption, and MDN receipts."
		)
	if re.search(r"difference between 990 and 214|990.*vs.*214", low):
		return (
			"A 990 is the Response to a load tender (accept or decline). A 214 is a Shipment Status "
			"update after the load is moving. They are different stored transaction types."
		)
	if re.search(r"what is (an |a )?(edi )?204\b", low):
		return "EDI 204 is a Motor Carrier Load Tender. In this application it is the load tender sent from a shipper or broker to the next party."
	if re.search(r"what is (an |a )?(edi )?990\b", low):
		return "EDI 990 is a Response to a load tender. It records whether the carrier accepted or declined the 204."
	if re.search(r"what is (an |a )?(edi )?214\b", low):
		return "EDI 214 is a Transportation Carrier Shipment Status Message. It reports movement or appointment status for a load."
	if re.search(r"what is (an |a )?(edi )?210\b", low):
		return "EDI 210 is a Motor Carrier Freight Details and Invoice. In this application it is stored as a Freight Invoice transaction."
	if re.search(r"what is openas2", low):
		return "OpenAS2 is the AS2 gateway this manager watches. Partners, certificates, partnerships, and EDI documents in this UI are the records stored for those OpenAS2 instances."
	return ""


def _classify(text: str) -> str:
	low = _normalize(text)
	if _general_answer(low) and re.search(r"^(what is|what's|whats|explain|difference)\b", low):
		return "general"
	if re.search(r"\b(create|add|new)\b.+\bpartner\b|\bpartner\b.+\b(create|add)\b", low) and "partnership" not in low:
		return "create_partner"
	if re.search(r"\b(create|add|new|setup|set up)\b.+\bpartnership\b|\bconnect\b.+\bpartners\b", low):
		return "create_partnership"
	if re.search(r"\b(create|add|new|generate)\b.+\bcertificate\b", low):
		return "create_certificate"
	if re.search(r"\b(create|add|new)\b.+\b(configuration|instance)\b", low) or re.search(
		r"\bconfigure\b.+\b(broker|carrier|shipper|company\s*c|instance|configuration)\b", low
	):
		return "create_configuration"
	if re.search(r"\b(update|change|edit|set)\b.+\bpartnership\b", low):
		return "update_partnership"
	if re.search(r"\b(update|change|edit|set)\b.+\bcertificate\b", low):
		return "update_certificate"
	if re.search(r"\b(update|change|edit|set)\b.+\b(configuration|instance)\b", low):
		return "update_configuration"
	if re.search(r"\b(update|change|edit|set)\b.+\bpartner\b", low):
		return "update_partner"
	if re.search(r"load\d+", low):
		return "find_reference"
	if re.search(r"\b(last|latest|recent|newest)\b", low) and re.search(r"\bloads?\b", low):
		return "recent_load"
	if _listed_followup(low):
		return "analyze_listed"
	if re.search(r"why .*(that one|this one)|the first one", low):
		return "analyze_listed"
	if re.search(r"why is (the )?mdn|mdn pending|analyze mdn", low):
		return "analyze_mdn"
	if re.search(r"why .*\bfail|analyze this|analyze (the )?(edi )?transaction|explain this error|find the cause", low):
		return "analyze_current"
	if re.search(r"\blogs\b", low):
		return "analyze_logs"
	if re.search(r"what.?s happening|summary of today|openas2 activity|today.?s (edi )?activity", low):
		return "activity"
	if re.search(r"partnership", low):
		return "list_partnerships"
	if re.search(r"\bcertificates?\b", low):
		return "list_certificates"
	if re.search(r"\b(configurations?|instances?)\b", low):
		return "list_configurations"
	if re.search(r"\bpartners?\b", low) and re.search(r"\b(show|list|all|find|open|who)\b", low):
		return "list_partners" if "find" not in low and "who" not in low else "show_partner"
	if re.search(r"\bpartners?\b", low):
		return "list_partners"
	if re.search(r"between\s+.+\s+and\s+", low):
		return "between_parties"
	if re.search(r"how many|count|number of", low) and re.search(r"fail", low):
		return "failed_today" if "today" in low else "count_failed"
	if re.search(r"\bfail", low) and _edi_code(low):
		return "failed_type"
	if re.search(r"\bfail", low) and re.search(r"transaction|edi|show|list", low):
		return "failed_all"
	if _edi_code(low):
		if re.search(r"how many|count|number of", low) and not re.search(r"last|latest|recent|record", low):
			return "count_type"
		return "list_type"
	if re.search(r"\b(last|latest|recent)\b", low) and re.search(r"transaction|edi|record", low):
		return "list_type"
	if re.search(r"\b(fail|error)\b", low):
		return "failed_all"
	if re.search(r"\b(edi|transaction|activity|monitoring|summary)\b", low):
		return "activity"
	return ""


def _topic_key() -> str:
	return f"oa2_ai_topic:{frappe.session.user}"


def _asked_limit(text: str) -> int | None:
	match = re.search(r"\b(?:last|latest|recent|top|first|show)?\s*(\d{1,2})\b", text, flags=re.I)
	if not match:
		return None
	return max(1, min(int(match.group(1)), 30))


def _edi_code(text: str) -> str:
	match = re.search(r"\b(204|990|214|210|810|820)\b", text or "")
	return match.group(1) if match else ""


def _context_partner(context: dict) -> str:
	return (
		(context.get("partner") or context.get("partner_name") or context.get("partner_label") or "")
	).strip()


def _missing(action: str, slots: dict, context: dict) -> list[str]:
	if action == "create_partner":
		need = []
		if not slots.get("partner_name"):
			need.append("Partner Name")
		if not _normalize_type(slots.get("partner_type")):
			need.append("Partner Type (Shipper, Broker, Carrier, or CompanyC)")
		if not slots.get("as2_id"):
			need.append("AS2 ID")
		if not slots.get("as2_url"):
			need.append("AS2 URL")
		return need
	if action == "create_partnership":
		need = []
		if not (slots.get("local_partner") or _context_partner(context)):
			need.append("Local Partner")
		if not slots.get("remote_partner"):
			need.append("Remote Partner")
		if not (slots.get("instance") or _one_instance_name() or context.get("configuration")):
			need.append("OpenAS2 Instance")
		return need
	if action == "create_certificate":
		need = []
		if not slots.get("certificate_name"):
			need.append("Certificate Name")
		if not _normalize_type(slots.get("owner_type")):
			need.append("Company / TMS (Shipper, Broker, Carrier, or CompanyC)")
		if not slots.get("x509_alias"):
			need.append("X509 Alias")
		if not slots.get("common_name"):
			need.append("Common Name (CN)")
		return need
	if action == "create_configuration":
		need = []
		if not slots.get("instance_name"):
			need.append("Name")
		if not _normalize_type(slots.get("instance_type")):
			need.append("Instance Type (Shipper, Broker, Carrier, or CompanyC)")
		if not slots.get("as2_id"):
			need.append("AS2 ID")
		if not slots.get("host"):
			need.append("Host")
		return need
	if action == "update_partner":
		return [] if (slots.get("name") or slots.get("partner_name") or slots.get("as2_url")) else ["Partner"]
	if action == "update_partnership":
		return [] if slots.get("name") else ["Partnership Name"]
	if action == "update_certificate":
		return [] if slots.get("name") else ["Certificate Name"]
	if action == "update_configuration":
		return [] if (slots.get("name") or slots.get("instance_name")) else ["Configuration"]
	return []


def _preview(action: str, slots: dict) -> tuple[str, list[dict]]:
	if action == "create_partner":
		lines = [
			{"label": "Name", "value": slots.get("partner_name")},
			{"label": "Partner Type", "value": _normalize_type(slots.get("partner_type"))},
			{"label": "AS2 ID", "value": slots.get("as2_id")},
			{"label": "AS2 URL", "value": slots.get("as2_url")},
			{"label": "Status", "value": "Active"},
		]
		return "Create Partner", lines
	if action == "update_partner":
		lines = [{"label": "Partner", "value": slots.get("partner_name") or slots.get("name")}]
		for key, label in (
			("as2_url", "AS2 URL"),
			("partner_type", "Partner Type"),
			("status", "Status"),
		):
			if slots.get(key):
				lines.append({"label": label, "value": slots.get(key)})
		return "Update Partner", lines
	if action == "create_partnership":
		lines = [
			{"label": "OpenAS2 Instance", "value": slots.get("instance")},
			{"label": "Local Partner", "value": slots.get("local_partner")},
			{"label": "Remote Partner", "value": slots.get("remote_partner")},
		]
		return "Create Partnership", lines
	if action == "create_certificate":
		lines = [
			{"label": "Certificate Name", "value": slots.get("certificate_name")},
			{"label": "Purpose", "value": slots.get("purpose") or "Own Key Pair"},
			{"label": "Company / TMS", "value": _normalize_type(slots.get("owner_type"))},
			{"label": "X509 Alias", "value": slots.get("x509_alias")},
			{"label": "Common Name", "value": slots.get("common_name")},
			{"label": "Certificate Type", "value": "Both"},
			{"label": "Status", "value": "Draft"},
		]
		return "Create Certificate", lines
	if action == "create_configuration":
		lines = [
			{"label": "Name", "value": slots.get("instance_name")},
			{"label": "Instance Type", "value": _normalize_type(slots.get("instance_type"))},
			{"label": "AS2 ID", "value": slots.get("as2_id")},
			{"label": "Host", "value": slots.get("host")},
			{"label": "HTTPS", "value": "Enabled"},
			{"label": "Status", "value": "Active"},
		]
		return "Create Configuration", lines
	if action == "update_configuration":
		return "Update Configuration", [
			{"label": "Configuration", "value": slots.get("instance_name") or slots.get("name")},
			*[{"label": key, "value": value} for key, value in slots.items() if key not in ("name", "instance_name", "action")],
		]
	return "Confirm", [{"label": key, "value": value} for key, value in slots.items()]


def _stage_confirm(action: str, slots: dict) -> dict:
	title, lines = _preview(action, slots)
	token = secrets.token_hex(16)
	_cache_set(
		_pending_key(),
		{"token": token, "action": action, "slots": slots},
	)
	body = [title, ""] + [f"{line['label']}: {line['value']}" for line in lines]
	body.append("")
	body.append("Nothing has been saved. Confirm to run this, or cancel.")
	return _reply("\n".join(body), kind="confirm", confirm={"token": token, "title": title, "lines": lines})


PARTNER_GUIDE_FIELDS = (
	{"key": "partner_name", "label": "Partner Name", "kind": "text"},
	{"key": "partner_type", "label": "Partner Type", "kind": "select", "options": list(PARTNER_TYPES)},
	{"key": "as2_id", "label": "AS2 ID", "kind": "text"},
	{"key": "as2_url", "label": "AS2 URL", "kind": "url"},
	{"key": "status", "label": "Status", "kind": "select", "options": ["Active", "Inactive"], "suggest": "Active"},
)


def _partner_field(key: str) -> dict:
	for field in PARTNER_GUIDE_FIELDS:
		if field["key"] == key:
			return field
	return PARTNER_GUIDE_FIELDS[0]


def _partner_slots_only(slots: dict) -> dict:
	kept = {}
	for field in PARTNER_GUIDE_FIELDS:
		value = (slots.get(field["key"]) or "").strip()
		if value:
			kept[field["key"]] = value
	return kept


def _guided_partner_slots(text: str) -> dict:
	slots = _extract_slots(text, "create_partner")
	match = re.search(
		r"\b(?:add|create|new)\s+(.+?)\s+as\s+(?:a|an)\s+(?:shipper|broker|carrier|company\s*c\s+)?partner\b",
		text,
		flags=re.I,
	)
	if match:
		name = re.sub(r"\s+", " ", match.group(1)).strip(" .\"'")
		if name and not _normalize_type(name) and name.lower() not in {"a", "an", "the", "partner"}:
			slots["partner_name"] = name
	return _partner_slots_only(slots)


def _save_partner_guide(slots: dict, field: str, phase: str, proposal: str = "", accepted=None) -> None:
	_cache_set(_pending_key(), None)
	_cache_set(
		_draft_key(),
		{
			"action": "create_partner",
			"slots": _partner_slots_only(slots),
			"guide": {
				"field": field,
				"phase": phase,
				"proposal": proposal or "",
				"accepted": list(accepted or []),
			},
		},
	)


def _partner_conflict(slots: dict, field: str | None = None):
	rows = _partner_rows()
	if field in (None, "as2_id") and slots.get("as2_id"):
		needle = slots["as2_id"].strip().lower()
		for row in rows:
			if needle in {(row.as2_id or "").strip().lower(), (row.name or "").strip().lower()}:
				return row, "as2_id"
	if field in (None, "partner_name") and slots.get("partner_name"):
		needle = slots["partner_name"].strip().lower()
		for row in rows:
			if needle == (row.partner_name or "").strip().lower():
				return row, "partner_name"
	return None, ""


def _accept_partner_value(key: str, raw: str) -> tuple[str, str]:
	text = (raw or "").strip().strip("\"'")
	if _SECRET_TEXT.search(text):
		return "", "Private keys and passwords stay out of chat."
	field = _partner_field(key)
	if key == "partner_type":
		value = _normalize_type(text)
		if not value:
			return "", "Choose a partner type: " + ", ".join(field["options"]) + "."
		return value, ""
	if key == "status":
		lower = text.lower()
		if lower == "active":
			return "Active", ""
		if lower == "inactive":
			return "Inactive", ""
		return "", "Choose a status: Active or Inactive."
	if key == "as2_id":
		match = re.search(r"as2\s*id\s*(?:to|is|=|:)?\s*([A-Za-z0-9_\-]+)", text, flags=re.I)
		value = match.group(1) if match else text
		if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_\-]{0,63}", value or ""):
			return "", "AS2 ID can use letters, numbers, underscores, and hyphens."
		return value, ""
	if key == "as2_url":
		match = re.search(r"https?://\S+", text, flags=re.I)
		value = (match.group(0) if match else text).rstrip(".,)")
		if not re.match(r"^https?://[^\s/$.?#].[^\s]*$", value, flags=re.I):
			return "", "AS2 URL should start with http:// or https://."
		return value, ""
	if len(text) < 2 or text.lower() in {"proceed", "edit", "cancel", "create", "yes", "no"}:
		return "", "What should the partner name be?"
	return re.sub(r"\s+", " ", text), ""


def _guide_actions(
	proceed: bool = False,
	edit: bool = False,
	create: str = "",
	cancel: bool = False,
	create_label: str = "Create Partner",
) -> list[dict]:
	actions = []
	if create:
		actions.append({"label": create_label, "confirm": create})
	if proceed:
		actions.append({"label": "✓ Proceed", "message": "Proceed"})
	if edit:
		actions.append({"label": "✎ Edit", "message": "Edit"})
	if cancel:
		actions.append({"label": "Cancel", "message": "Cancel"})
	return actions


def _next_available(base: str, taken: set[str]) -> str:
	folded = {item.strip().lower() for item in taken if item}
	if base.lower() not in folded:
		return base
	number = 2
	while f"{base} {number}".lower() in folded and number < 50:
		number += 1
	return f"{base} {number}"


def _suggest_code(name: str, fallback: str, taken: set[str]) -> str:
	token = re.sub(r"[^A-Za-z0-9]+", "_", name or "").strip("_").upper()
	if not token or not token[0].isalnum():
		token = fallback
	token = token[:48]
	used = {item.strip().upper() for item in taken if item}
	candidate = token[:64]
	number = 2
	while candidate.upper() in used and number < 80:
		suffix = f"_{number}"
		candidate = token[: 64 - len(suffix)] + suffix
		number += 1
	return candidate


def _placeholder_host(name: str) -> str:
	slug = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-") or "partner"
	return f"{slug[:40]}.example"


def _free_port(avoid: str | None = None) -> str:
	used = set()
	for row in frappe.get_all(
		"OpenAS2 Instance",
		fields=["http_port", "https_port", "mdn_http_port", "mdn_https_port"],
		limit_page_length=300,
	):
		for value in (row.http_port, row.https_port, row.mdn_http_port, row.mdn_https_port):
			if not value:
				continue
			try:
				used.add(int(value))
			except (TypeError, ValueError):
				continue
	if avoid:
		try:
			used.add(int(avoid))
		except (TypeError, ValueError):
			pass
	port = 4080
	while port in used and port < 65535:
		port += 1
	return str(port)


def _value_lines(label: str, shown: str, source: str) -> list[str]:
	if source == "existing":
		return ["Selected from existing records", label, shown]
	if source == "suggested":
		return [f"Suggested {label}", shown]
	return [label, shown]


def _ask_partner_field(slots: dict, key: str, error: str = "", intro: bool = False, accepted=None) -> dict:
	field = _partner_field(key)
	kept = [item for item in (accepted or []) if item != key]
	_save_partner_guide(slots, key, "ask", "", kept)
	if key == "partner_name" and intro:
		lead = "Let's create a partner. What should the partner name be?"
	elif key == "partner_name":
		lead = "What should the partner name be?"
	elif key == "partner_type":
		lead = "What type of partner is this?"
	elif key == "as2_id":
		lead = "What AS2 ID should this partner use?"
	elif key == "as2_url":
		lead = "What is the AS2 URL?"
	else:
		lead = "What status should this partner have?"
	lines = []
	if error:
		lines.append(error)
		lines.append("")
	lines.append(lead)
	options = list(field.get("options") or [])
	if options:
		lines.append("")
		lines.append("Choose one:")
		lines.extend(f"- {option}" for option in options)
	return _reply("\n".join(lines), kind="guide", guide={"options": options, "actions": []})


def _show_partner_check(
	slots: dict, key: str, value: str, intro: bool = False, accepted=None, source: str = "confirm"
) -> dict:
	field = _partner_field(key)
	kept = [item for item in (accepted or []) if item != key]
	_save_partner_guide(slots, key, "check", value, kept)
	lines = ["Let's create a partner.", ""] if intro else []
	lines.extend(_value_lines(field["label"], value, source))
	if key == "as2_url" and source == "suggested":
		lines.append("This is a placeholder. No connection is opened.")
	return _reply(
		"\n".join(lines),
		kind="guide",
		guide={"actions": _guide_actions(proceed=True, edit=True)},
	)


def _show_partner_review(slots: dict) -> dict:
	conflict, which = _partner_conflict(slots)
	if conflict:
		return _partner_duplicate_reply(
			slots,
			conflict,
			which,
			[item["key"] for item in PARTNER_GUIDE_FIELDS],
		)
	clean = _partner_slots_only(slots)
	token = secrets.token_hex(16)
	_cache_set(
		_draft_key(),
		{
			"action": "create_partner",
			"slots": clean,
			"guide": {
				"field": "",
				"phase": "review",
				"proposal": "",
				"accepted": [item["key"] for item in PARTNER_GUIDE_FIELDS],
			},
		},
	)
	_cache_set(_pending_key(), {"token": token, "action": "create_partner", "slots": clean})
	lines = ["Review Partner", ""]
	for field in PARTNER_GUIDE_FIELDS:
		lines.append(f"{field['label']}: {clean.get(field['key'])}")
	lines.extend(["", "Everything looks correct?"])
	return _reply(
		"\n".join(lines),
		kind="guide",
		guide={"actions": _guide_actions(create=token, edit=True, cancel=True)},
	)


def _partner_suggestion(key: str, slots: dict) -> tuple[str, str]:
	if key == "partner_name":
		taken = {(row.partner_name or "") for row in _partner_rows()}
		return _next_available("New Partner", taken), "suggested"
	if key == "partner_type":
		return "Broker", "suggested"
	if key == "as2_id":
		taken = {(row.as2_id or "") for row in _partner_rows()}
		return _suggest_code(slots.get("partner_name") or "New Partner", "NEW_PARTNER", taken), "suggested"
	if key == "as2_url":
		return f"https://{_placeholder_host(slots.get('partner_name') or 'partner')}/as2", "suggested"
	if key == "status":
		return "Active", "suggested"
	return "", ""


def _partner_duplicate_reply(slots: dict, row, field: str, accepted=None) -> dict:
	clean = _partner_slots_only(slots)
	clean.pop(field, None)
	kept = [item for item in (accepted or []) if item != field]
	label = (row.partner_name if not isinstance(row, dict) else row.get("partner_name")) or ""
	as2_id = (row.as2_id if not isinstance(row, dict) else row.get("as2_id")) or ""
	if field == "as2_id":
		text = f"AS2 ID {as2_id} is already used by {label or as2_id}. I did not create another partner."
	else:
		text = f"{label} is already a partner. I did not create another record."
	value, source = _partner_suggestion(field, clean)
	if not value:
		_save_partner_guide(clean, field, "ask", "", kept)
		return _reply(text, links=[_partner_link(row)] if _partner_link(row) else None)
	shown = _show_partner_check(clean, field, value, accepted=kept, source=source)
	shown["reply"] = text + "\n\n" + shown["reply"]
	link = _partner_link(row)
	if link:
		shown["links"] = [link]
	return shown


def _partner_guide_next(slots: dict, accepted=None, intro: bool = False) -> dict:
	done = set(accepted or [])
	for field in PARTNER_GUIDE_FIELDS:
		key = field["key"]
		if key in done:
			continue
		if slots.get(key):
			return _show_partner_check(slots, key, slots[key], intro=intro, accepted=accepted, source="confirm")
		value, source = _partner_suggestion(key, slots)
		if not value and field.get("suggest"):
			value, source = field["suggest"], "suggested"
		if value:
			return _show_partner_check(slots, key, value, intro=intro, accepted=accepted, source=source)
		return _ask_partner_field(slots, key, intro=intro, accepted=accepted)
	return _show_partner_review(slots)


def _accept_partner_proposal(slots: dict, guide: dict) -> dict:
	key = guide.get("field") or ""
	value = guide.get("proposal") or slots.get(key) or ""
	accepted = list(guide.get("accepted") or [])
	if not key or not value:
		return _partner_guide_next(slots, accepted)
	clean = _partner_slots_only(slots)
	clean[key] = value
	if key in ("as2_id", "partner_name"):
		conflict, which = _partner_conflict(clean, key)
		if conflict:
			return _partner_duplicate_reply(clean, conflict, which, accepted)
	if key not in accepted:
		accepted.append(key)
	return _partner_guide_next(clean, accepted)


def _field_key_from_text(text: str) -> str:
	low = _normalize(text)
	if re.search(r"as2\s*url|\burl\b", low):
		return "as2_url"
	if re.search(r"as2\s*id", low):
		return "as2_id"
	if re.search(r"partner\s*type|\btype\b", low):
		return "partner_type"
	if re.search(r"\bstatus\b", low):
		return "status"
	if re.search(r"partner\s*name|\bname\b", low):
		return "partner_name"
	return ""


def _explicit_partner_change(text: str, guide: dict) -> tuple[str, str] | None:
	patterns = (
		(r"(?:change|set|update|edit)\s+(?:the\s+)?as2\s*id\s+(?:to\s+)?([A-Za-z0-9_\-]+)", "as2_id"),
		(r"(?:change|set|update|edit)\s+(?:the\s+)?(?:as2\s*url|url)\s+(?:to\s+)?(\S+)", "as2_url"),
		(r"(?:change|set|update|edit)\s+(?:the\s+)?partner\s*name\s+(?:to\s+)?(.+)$", "partner_name"),
		(r"(?:change|set|update|edit)\s+(?:the\s+)?(?:partner\s*)?type\s+(?:to\s+)?(.+)$", "partner_type"),
		(r"(?:change|set|update|edit)\s+(?:the\s+)?status\s+(?:to\s+)?(.+)$", "status"),
		(r"(?:change|set)\s+that\s+to\s+(.+)$", ""),
	)
	for pattern, key in patterns:
		match = re.search(pattern, text, flags=re.I)
		if not match:
			continue
		value = match.group(1).strip()
		if not key:
			key = guide.get("field") or "partner_name"
			if _normalize_type(value) and key != "partner_type":
				key = "partner_type"
		return key, value
	return None


def _partner_guide_turn(text: str, normalized: str) -> dict:
	draft = _cache_get(_draft_key())
	slots = dict(draft.get("slots") or {})
	guide = dict(draft.get("guide") or {})
	phase = guide.get("phase") or "ask"
	field = guide.get("field") or "partner_name"
	accepted = list(guide.get("accepted") or [])
	low = normalized
	if _classify(text) == "create_partner":
		return _partner_guide_next(slots, accepted, intro=not accepted)
	if low in {"cancel", "stop"}:
		_cache_set(_pending_key(), None)
		_cache_set(_draft_key(), None)
		return _reply("Cancelled. Nothing was changed.")
	if phase == "review" and low in {"create it", "create partner", "create the partner"}:
		pending = _cache_get(_pending_key())
		return confirm_assistant_action((pending or {}).get("token"))
	changed = _explicit_partner_change(text, guide)
	if changed:
		key, raw = changed
		value, error = _accept_partner_value(key, raw)
		if error:
			return _ask_partner_field(slots, key, error=error, accepted=accepted)
		clean = _partner_slots_only(slots)
		clean[key] = value
		if key in ("as2_id", "partner_name"):
			conflict, which = _partner_conflict(clean, key)
			if conflict:
				return _partner_duplicate_reply(clean, conflict, which, accepted)
		if key not in accepted:
			accepted.append(key)
		return _partner_guide_next(clean, accepted)
	if low in {"proceed", "continue", "next"} or (phase == "check" and low in {"yes", "ok", "okay", "correct"}):
		return _accept_partner_proposal(slots, guide)
	if re.search(r"\bedit\b.+\b(url|as2 url|as2 id|type|status|name)\b", low):
		return _ask_partner_field(slots, _field_key_from_text(text) or field, accepted=accepted)
	if low in {"edit", "change", "change it", "edit that"}:
		if phase == "review":
			names = [item["label"] for item in PARTNER_GUIDE_FIELDS]
			_save_partner_guide(slots, "", "pick", "", accepted)
			return _reply(
				"Which field should I change?\n\n" + "\n".join(f"- {name}" for name in names),
				kind="guide",
				guide={"options": names, "actions": []},
			)
		return _ask_partner_field(slots, field or "partner_name", accepted=accepted)
	picked = _field_key_from_text(text) if phase == "pick" else ""
	if picked and phase == "pick":
		return _ask_partner_field(slots, picked, accepted=accepted)
	if phase == "ask":
		value, error = _accept_partner_value(field, text)
		if error:
			return _ask_partner_field(slots, field, error=error, accepted=accepted)
		return _show_partner_check(slots, field, value, accepted=accepted)
	if phase == "check":
		value, error = _accept_partner_value(field, text)
		if error:
			return _ask_partner_field(slots, field, error=error, accepted=accepted)
		return _show_partner_check(slots, field, value, accepted=accepted)
	return _show_partner_review(slots)


def _begin_partner_guide(text: str) -> dict:
	slots = _guided_partner_slots(text)
	draft = _cache_get(_draft_key())
	if draft.get("action") == "create_partner" and draft.get("guide") and draft.get("slots"):
		merged = dict(draft.get("slots") or {})
		merged.update(slots)
		slots = _partner_slots_only(merged)
	return _partner_guide_next(slots, [], intro=True)


def _row_value(row, key: str) -> str:
	if row is None:
		return ""
	if isinstance(row, dict):
		return str(row.get(key) or "")
	return str(getattr(row, key, "") or "")


def _partner_edit_change(text: str) -> tuple[str, str]:
	"""Return the partner field a sentence wants to change, plus a value when one was given."""
	raw = (text or "").strip()
	if re.search(r"\bstatus\b", raw, flags=re.I):
		match = re.search(r"\b(active|inactive)\b", raw, flags=re.I)
		if not match:
			return "status", ""
		return "status", "Inactive" if match.group(1).lower() == "inactive" else "Active"
	if re.search(r"\bas2\s*url\b|\burl\b", raw, flags=re.I):
		match = re.search(r"https?://\S+", raw, flags=re.I)
		return "as2_url", match.group(0).rstrip(".,)") if match else ""
	if re.search(r"\bas2\s*id\b", raw, flags=re.I):
		match = re.search(
			r"\bas2\s*id\b(?:\s*(?:to|as|is|=|:)\s*|\s+)([A-Za-z0-9][A-Za-z0-9_\-]{0,63})",
			raw,
			flags=re.I,
		)
		value = match.group(1) if match else ""
		if value.lower() in {"to", "as", "is", "the", "a", "an"}:
			value = ""
		return "as2_id", value
	if re.search(r"\b(?:partner\s*)?type\b", raw, flags=re.I):
		return "partner_type", _normalize_type(raw)
	if re.search(r"\b(?:partner\s*)?name\b", raw, flags=re.I):
		match = re.search(r"\bname\b\s*(?:to|as|is|=|:)\s+[\"']?(.+?)[\"']?$", raw, flags=re.I)
		return "partner_name", re.sub(r"\s+", " ", match.group(1)).strip(" .\"'") if match else ""
	return "", ""


def _partner_edit_query(text: str) -> str:
	raw = re.sub(r"\s+", " ", (text or "").strip())
	cleaned = re.sub(r"^(?:please\s+)?(?:edit|update|change|modify)\s+", "", raw, flags=re.I)
	cleaned = re.sub(r"\s+partners?$", "", cleaned, flags=re.I).strip()
	cleaned = re.sub(r"^(?:the\s+|a\s+|an\s+)?partners?\s+", "", cleaned, flags=re.I).strip()
	cleaned = re.sub(r"^(?:a|an|the)\s+", "", cleaned, flags=re.I).strip(" .\"'")
	if cleaned.lower() in {"", "partner", "partners", "a", "an", "the", "this", "that", "it", "one"}:
		return ""
	return cleaned


def _partner_edit_subject(text: str) -> str:
	cleaned = re.sub(
		r"\b(?:and\s+)?(?:please\s+)?(?:change|update|edit|set|modify)\s+(?:the\s+|its\s+)?"
		r"(?:partner\s+name|partner\s+type|as2\s*url|as2\s*id|status|type|name|url)\b.*$",
		"",
		text or "",
		flags=re.I,
	).strip()
	cleaned = re.sub(
		r"\b(?:partner\s+name|partner\s+type|as2\s*url|as2\s*id|status)\b.*$",
		"",
		cleaned,
		flags=re.I,
	).strip()
	if not cleaned:
		return ""
	return _partner_edit_query(cleaned)


def _is_new_partner_edit(text: str) -> bool:
	if _classify(text) != "update_partner":
		return False
	field, _value = _partner_edit_change(text)
	return bool(_partner_edit_subject(text) or not field)


def _search_partners(query: str) -> list:
	needle = re.sub(r"\s+", " ", (query or "").strip()).lower()
	if not needle or needle in {"partner", "partners", "a", "an", "the"}:
		return []
	exact = []
	partial = []
	seen = set()
	for row in _partner_rows():
		labels = {
			_row_value(row, "name").strip().lower(),
			_row_value(row, "partner_name").strip().lower(),
			_row_value(row, "as2_id").strip().lower(),
		}
		if needle in labels and row.name not in seen:
			exact.append(row)
			seen.add(row.name)
	if exact:
		return exact
	for row in _partner_rows():
		name = _row_value(row, "partner_name").lower()
		as2_id = _row_value(row, "as2_id").lower()
		docname = _row_value(row, "name").lower()
		if needle in {name, as2_id, docname}:
			continue
		if needle in name or needle in as2_id or needle in docname:
			if row.name not in seen:
				partial.append(row)
				seen.add(row.name)
	return partial


def _partner_edit_record(docname: str):
	if not docname or not frappe.db.exists("AS2 Partner", docname):
		return None
	return frappe.db.get_value("AS2 Partner", docname, PARTNER_FIELDS, as_dict=True)


def _save_partner_edit(docname: str, phase: str, field: str = "", proposal: str = "", current: str = "") -> None:
	_cache_set(_pending_key(), None)
	_cache_set(
		_draft_key(),
		{
			"action": "update_partner",
			"slots": {"name": docname or ""},
			"guide": {
				"phase": phase,
				"field": field or "",
				"proposal": proposal or "",
				"current": current or "",
				"partner": docname or "",
			},
		},
	)


def _partner_choices_reply(intro: str, rows: list, field: str = "", proposal: str = "") -> dict:
	_save_partner_edit("", "pick_partner", field, proposal)
	names = [_row_value(row, "partner_name") or _row_value(row, "name") for row in rows[:30]]
	lines = [intro, "", "Choose one:"]
	lines.extend(f"- {name}" for name in names)
	if len(rows) > 30:
		lines.append(f"{len(rows) - 30} more partners are not listed here.")
	lines.extend(["", "Nothing has been saved."])
	return _reply(
		"\n".join(lines),
		kind="guide",
		links=[_partner_link(row) for row in rows[:30]],
		guide={"options": names, "actions": _guide_actions(cancel=True)},
	)


def _show_partner_edit_fields(row) -> dict:
	label = _row_value(row, "partner_name") or _row_value(row, "name")
	_save_partner_edit(row.name, "pick_field")
	lines = [f"Selected record: {label}", ""]
	for field in PARTNER_GUIDE_FIELDS:
		lines.append(f"{field['label']}: {_row_value(row, field['key']) or '—'}")
	lines.extend(["", "Which field should I change?", "Nothing has been saved."])
	return _reply(
		"\n".join(lines),
		kind="guide",
		links=[_partner_link(row)],
		guide={
			"options": [field["label"] for field in PARTNER_GUIDE_FIELDS],
			"actions": _guide_actions(edit=True, cancel=True),
		},
	)


def _ask_partner_edit_value(row, key: str, error: str = "") -> dict:
	field = _partner_field(key)
	current = _row_value(row, key) or "—"
	_save_partner_edit(row.name, "ask", key, "", current)
	lines = []
	if error:
		lines.extend([error, ""])
	lines.extend(
		[
			f"Selected record: {_row_value(row, 'partner_name') or row.name}",
			f"Current {field['label']}: {current}",
			"",
			f"What should the new {field['label']} be?",
			"Nothing has been saved.",
		]
	)
	options = list(field.get("options") or [])
	if options:
		lines.extend(["", "Choose one:"])
		lines.extend(f"- {option}" for option in options)
	return _reply(
		"\n".join(lines),
		kind="guide",
		links=[_partner_link(row)],
		guide={"options": options, "actions": _guide_actions(cancel=True)},
	)


def _show_partner_edit_check(row, key: str, proposed: str) -> dict:
	field = _partner_field(key)
	current = _row_value(row, key) or "—"
	_save_partner_edit(row.name, "check", key, proposed, current)
	lines = [
		f"Selected record: {_row_value(row, 'partner_name') or row.name}",
		f"Current {field['label']}: {current}",
		f"Proposed {field['label']}: {proposed}",
		"",
		"Nothing has been saved.",
	]
	return _reply(
		"\n".join(lines),
		kind="guide",
		links=[_partner_link(row)],
		guide={"actions": _guide_actions(proceed=True, edit=True, cancel=True)},
	)


def _show_partner_edit_review(row, key: str, proposed: str) -> dict:
	field = _partner_field(key)
	current = _row_value(row, key) or "—"
	clean = {"name": row.name, key: proposed}
	token = secrets.token_hex(16)
	_cache_set(
		_draft_key(),
		{
			"action": "update_partner",
			"slots": clean,
			"guide": {
				"phase": "review",
				"field": key,
				"proposal": proposed,
				"current": current,
				"partner": row.name,
			},
		},
	)
	_cache_set(_pending_key(), {"token": token, "action": "update_partner", "slots": clean})
	lines = [
		"Review this update",
		"",
		f"Partner: {_row_value(row, 'partner_name') or row.name}",
		f"Field: {field['label']}",
		f"Current value: {current}",
		f"Proposed value: {proposed}",
		"",
		"Nothing has been saved.",
	]
	return _reply(
		"\n".join(lines),
		kind="guide",
		links=[_partner_link(row)],
		guide={"actions": _guide_actions(create=token, edit=True, cancel=True, create_label="Update Partner")},
	)


def _propose_partner_edit(row, key: str, raw: str) -> dict:
	value, error = _accept_partner_value(key, raw)
	if error:
		return _ask_partner_edit_value(row, key, error=error)
	current = _row_value(row, key)
	if value == current:
		shown = _show_partner_edit_fields(row)
		shown["reply"] = f"That is already the current { _partner_field(key)['label'] }. Nothing was saved.\n\n" + shown["reply"]
		return shown
	if key in {"as2_id", "partner_name"}:
		conflict, _which = _partner_conflict({key: value}, key)
		if conflict and _row_value(conflict, "name") != row.name:
			label = _row_value(conflict, "partner_name") or _row_value(conflict, "name")
			return _ask_partner_edit_value(
				row,
				key,
				error=f"{label} already uses {_partner_field(key)['label']} {value}. I did not change this partner.",
			)
	return _show_partner_edit_check(row, key, value)


def _open_partner_edit(row, field: str = "", proposal: str = "") -> dict:
	if field and proposal:
		return _propose_partner_edit(row, field, proposal)
	if field:
		return _ask_partner_edit_value(row, field)
	return _show_partner_edit_fields(row)


def _begin_partner_edit(text: str, context: dict | None = None) -> dict:
	context = context or {}
	field, proposal = _partner_edit_change(text)
	query = _partner_edit_subject(text)
	if not query and re.search(r"\b(this|current|selected)\s+partner\b", text or "", flags=re.I):
		query = _context_partner(context)
	if not query:
		rows = _partner_rows()
		if not rows:
			_cache_set(_draft_key(), None)
			_cache_set(_pending_key(), None)
			return _reply("No AS2 Partner records are stored. I did not create one.")
		return _partner_choices_reply("Which partner should I edit?", rows, field, proposal)
	matches = _search_partners(query)
	if not matches:
		rows = _partner_rows()
		if not rows:
			return _reply(f"No partner matches \"{query}\". No AS2 Partner records are stored. I did not create one.")
		return _partner_choices_reply(
			f"No partner matches \"{query}\". I did not create one. Which existing partner should I edit?",
			rows,
		)
	if len(matches) > 1:
		return _partner_choices_reply(f"More than one partner matches \"{query}\". Which one should I edit?", matches)
	return _open_partner_edit(matches[0], field, proposal)


def _partner_edit_turn(text: str, normalized: str) -> dict:
	draft = _cache_get(_draft_key())
	guide = dict(draft.get("guide") or {})
	phase = guide.get("phase") or "pick_partner"
	field = guide.get("field") or ""
	low = normalized
	row = _partner_edit_record(guide.get("partner") or (draft.get("slots") or {}).get("name") or "")
	if low in {"cancel", "stop", "no"}:
		_cache_set(_pending_key(), None)
		_cache_set(_draft_key(), None)
		return _reply("Cancelled. Nothing was changed.")
	if phase == "review" and low in {"update it", "update partner", "save", "save it"}:
		pending = _cache_get(_pending_key())
		return confirm_assistant_action((pending or {}).get("token"))
	if _is_new_partner_edit(text) and (_partner_edit_subject(text) or not _partner_edit_change(text)[0]):
		return _begin_partner_edit(text, {})
	change_field, change_value = _partner_edit_change(text)
	if change_field and row and re.search(r"\b(change|update|edit|set|modify)\b", text or "", flags=re.I):
		if change_value:
			return _propose_partner_edit(row, change_field, change_value)
		return _ask_partner_edit_value(row, change_field)
	if low in {"proceed", "continue", "next"} or (phase == "check" and low in {"yes", "ok", "okay", "correct"}):
		if not row or not field:
			return _begin_partner_edit("", {})
		if phase == "check":
			return _show_partner_edit_review(row, field, guide.get("proposal") or "")
		if phase == "ask" and guide.get("proposal"):
			return _show_partner_edit_check(row, field, guide.get("proposal") or "")
	if low in {"edit", "change", "change it", "edit that"}:
		if row and phase in {"check", "review"} and field:
			return _ask_partner_edit_value(row, field)
		if row:
			return _show_partner_edit_fields(row)
		return _begin_partner_edit("", {})
	if phase == "pick_partner":
		matches = _search_partners(text)
		if len(matches) == 1:
			return _open_partner_edit(matches[0], field, guide.get("proposal") or "")
		if len(matches) > 1:
			return _partner_choices_reply(f"More than one partner matches \"{text.strip()}\". Which one should I edit?", matches)
		rows = _partner_rows()
		if not rows:
			_cache_set(_draft_key(), None)
			return _reply(f"No partner matches \"{text.strip()}\". No AS2 Partner records are stored. I did not create one.")
		return _partner_choices_reply(
			f"No partner matches \"{text.strip()}\". I did not create one. Which existing partner should I edit?",
			rows,
			field,
			guide.get("proposal") or "",
		)
	if phase == "pick_field" and row:
		picked = _field_key_from_text(text) or change_field
		if picked:
			return _ask_partner_edit_value(row, picked)
		names = [item["label"] for item in PARTNER_GUIDE_FIELDS]
		return _reply(
			"Which field should I change?\n\n" + "\n".join(f"- {name}" for name in names) + "\n\nNothing has been saved.",
			kind="guide",
			links=[_partner_link(row)],
			guide={"options": names, "actions": _guide_actions(cancel=True)},
		)
	if phase in {"ask", "check"} and row and field:
		return _propose_partner_edit(row, field, text)
	if phase == "review" and row and field:
		return _show_partner_edit_review(row, field, guide.get("proposal") or "")
	return _begin_partner_edit(text, {})


CERTIFICATE_PURPOSES = ("Own Key Pair", "Partner Public Certificate")
CERTIFICATE_TYPES = ("Signing", "Encryption", "Both")
CERTIFICATE_STATUSES = ("Draft", "Active", "Expired", "Revoked")
_SECRET_TEXT = re.compile(r"-----BEGIN |PRIVATE KEY|keystore password", flags=re.I)


def _match_choice(text: str, options: tuple[str, ...] | list[str]) -> str:
	folded = re.sub(r"[^a-z0-9]", "", (text or "").lower())
	for option in options:
		if re.sub(r"[^a-z0-9]", "", option.lower()) == folded:
			return option
	return ""


def _instance_choices() -> list[tuple[str, str]]:
	choices = []
	for row in _config_rows():
		label = (row.instance_name or row.name or "").strip()
		if row.name and label:
			choices.append((label, row.name))
	return choices


def _instance_label(name: str) -> str:
	for label, docname in _instance_choices():
		if docname == name or label == name:
			return label
	return name


def _certificate_guide_fields() -> list[dict]:
	fields = [
		{"key": "certificate_name", "label": "Certificate Name", "kind": "text"},
		{
			"key": "purpose",
			"label": "Purpose",
			"kind": "select",
			"options": list(CERTIFICATE_PURPOSES),
			"suggest": "Own Key Pair",
		},
		{"key": "owner_type", "label": "Company / TMS", "kind": "select", "options": list(PARTNER_TYPES)},
		{"key": "x509_alias", "label": "X509 Alias", "kind": "text"},
		{"key": "common_name", "label": "Common Name (CN)", "kind": "text"},
		{
			"key": "certificate_type",
			"label": "Certificate Type",
			"kind": "select",
			"options": list(CERTIFICATE_TYPES),
			"suggest": "Both",
		},
		{
			"key": "status",
			"label": "Status",
			"kind": "select",
			"options": list(CERTIFICATE_STATUSES),
			"suggest": "Draft",
		},
	]
	choices = _instance_choices()
	if choices:
		fields.append(
			{
				"key": "openas2_instance",
				"label": "OpenAS2 Instance",
				"kind": "select",
				"options": [label for label, _name in choices],
				"optional": True,
				"suggest": choices[0][0] if len(choices) == 1 else "",
			}
		)
	return fields


def _certificate_field(key: str) -> dict:
	for field in _certificate_guide_fields():
		if field["key"] == key:
			return field
	return _certificate_guide_fields()[0]


def _certificate_slots_only(slots: dict) -> dict:
	kept = {}
	for field in _certificate_guide_fields():
		value = (slots.get(field["key"]) or "").strip()
		if value and not _SECRET_TEXT.search(value):
			kept[field["key"]] = value
	return kept


def _guided_certificate_slots(text: str) -> dict:
	slots = _extract_slots(text, "create_certificate")
	if re.search(r"\bencryption\b", text, flags=re.I):
		slots["certificate_type"] = "Encryption"
	elif re.search(r"\bsigning\b", text, flags=re.I):
		slots["certificate_type"] = "Signing"
	if re.search(r"partner public", text, flags=re.I):
		slots["purpose"] = "Partner Public Certificate"
	elif re.search(r"own key|key pair", text, flags=re.I):
		slots["purpose"] = "Own Key Pair"
	match = re.search(
		r"\b(?:add|create|new)\s+(.+?)\s+as\s+(?:a|an)\s+.+?\bcertificate\b",
		text,
		flags=re.I,
	)
	if match:
		name = re.sub(r"\s+", " ", match.group(1)).strip(" .\"'")
		if name and name.lower() not in {"a", "an", "the", "certificate", "encryption", "signing"} and not _normalize_type(name):
			slots["certificate_name"] = name
	return _certificate_slots_only(slots)


def _save_certificate_guide(slots: dict, field: str, phase: str, proposal: str = "", accepted=None) -> None:
	_cache_set(_pending_key(), None)
	_cache_set(
		_draft_key(),
		{
			"action": "create_certificate",
			"slots": _certificate_slots_only(slots),
			"guide": {
				"field": field,
				"phase": phase,
				"proposal": proposal or "",
				"accepted": list(accepted or []),
			},
		},
	)


def _certificate_conflict(slots: dict, field: str | None = None):
	if field not in (None, "certificate_name") or not slots.get("certificate_name"):
		return None
	name = slots["certificate_name"].strip()
	existing = frappe.db.exists("AS2 Certificate", name) or frappe.db.exists(
		"AS2 Certificate", {"certificate_name": name}
	)
	if not existing:
		return None
	if frappe.has_permission("AS2 Certificate", "read", existing):
		return frappe.db.get_value("AS2 Certificate", existing, CERTIFICATE_FIELDS, as_dict=True)
	return {"name": existing, "certificate_name": name}


def _accept_certificate_value(key: str, raw: str) -> tuple[str, str]:
	text = (raw or "").strip().strip("\"'")
	if _SECRET_TEXT.search(text):
		return "", "Private keys and passwords stay out of chat. Use the certificate screen for the key file."
	field = _certificate_field(key)
	if field.get("optional") and _normalize(text) in {"skip", "none", "no", "no instance"}:
		return "", ""
	if key == "purpose":
		value = _match_choice(text, CERTIFICATE_PURPOSES)
		if not value:
			return "", "Choose a purpose: " + ", ".join(CERTIFICATE_PURPOSES) + "."
		return value, ""
	if key == "owner_type":
		value = _normalize_type(text)
		if not value:
			return "", "Choose a company: " + ", ".join(PARTNER_TYPES) + "."
		return value, ""
	if key == "certificate_type":
		value = _match_choice(text, CERTIFICATE_TYPES)
		if not value:
			return "", "Choose a certificate type: " + ", ".join(CERTIFICATE_TYPES) + "."
		return value, ""
	if key == "status":
		value = _match_choice(text, CERTIFICATE_STATUSES)
		if not value:
			return "", "Choose a status: " + ", ".join(CERTIFICATE_STATUSES) + "."
		return value, ""
	if key == "openas2_instance":
		folded = text.lower()
		for label, docname in _instance_choices():
			if folded in {label.lower(), docname.lower()}:
				return docname, ""
		labels = ", ".join(label for label, _name in _instance_choices())
		return "", "Choose an OpenAS2 instance: " + labels + ". Or say skip."
	if key == "x509_alias":
		match = re.search(r"(?:x509\s*)?alias\s*(?:to|is|=|:)?\s*([A-Za-z0-9][A-Za-z0-9_.-]{0,63})", text, flags=re.I)
		value = match.group(1) if match else text
		if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", value or ""):
			return "", "X509 alias can use letters, numbers, dots, underscores, and hyphens."
		return value, ""
	if len(text) < 2 or _normalize(text) in {"proceed", "edit", "cancel", "create", "yes", "no"}:
		lead = "What should the certificate name be?" if key == "certificate_name" else "What is the common name (CN)?"
		return "", lead
	return re.sub(r"\s+", " ", text), ""


def _ask_certificate_field(slots: dict, key: str, error: str = "", intro: bool = False, accepted=None) -> dict:
	field = _certificate_field(key)
	kept = [item for item in (accepted or []) if item != key]
	_save_certificate_guide(slots, key, "ask", "", kept)
	prompts = {
		"certificate_name": "What should the certificate name be?",
		"purpose": "What is this certificate for?",
		"owner_type": "Which company should own this certificate?",
		"x509_alias": "What X509 alias should this certificate use?",
		"common_name": "What is the common name (CN)?",
		"certificate_type": "What certificate type is this?",
		"status": "What status should this certificate have?",
		"openas2_instance": "Which OpenAS2 instance should use this certificate?",
	}
	lead = prompts.get(key, "What value should I use?")
	if key == "certificate_name" and intro:
		lead = "Let's create a certificate. What should the certificate name be?"
	lines = []
	if error:
		lines.extend([error, ""])
	lines.append(lead)
	options = list(field.get("options") or [])
	if options:
		lines.extend(["", "Choose one:", *[f"- {option}" for option in options]])
	if field.get("optional"):
		lines.extend(["", "Say skip if this certificate is not tied to an instance."])
	return _reply("\n".join(lines), kind="guide", guide={"options": options, "actions": []})


def _show_certificate_check(
	slots: dict, key: str, value: str, intro: bool = False, accepted=None, source: str = "confirm"
) -> dict:
	field = _certificate_field(key)
	kept = [item for item in (accepted or []) if item != key]
	_save_certificate_guide(slots, key, "check", value, kept)
	shown = _instance_label(value) if key == "openas2_instance" else value
	lines = ["Let's create a certificate.", ""] if intro else []
	lines.extend(_value_lines(field["label"], shown, source))
	if key == "common_name" and source == "suggested":
		lines.append("This is a placeholder name. No certificate file is created.")
	return _reply("\n".join(lines), kind="guide", guide={"actions": _guide_actions(proceed=True, edit=True)})


def _certificate_review_lines(slots: dict) -> list[str]:
	lines = ["Review Certificate", ""]
	for field in _certificate_guide_fields():
		value = slots.get(field["key"]) or ""
		if field["key"] == "openas2_instance":
			value = _instance_label(value) if value else "not stored"
		lines.append(f"{field['label']}: {value}")
	lines.append("Valid Until: Not set yet")
	lines.extend(["", "Everything looks correct?"])
	return lines


def _show_certificate_review(slots: dict) -> dict:
	conflict = _certificate_conflict(slots)
	if conflict:
		return _certificate_duplicate_reply(
			slots,
			conflict,
			[item["key"] for item in _certificate_guide_fields()],
		)
	clean = _certificate_slots_only(slots)
	token = secrets.token_hex(16)
	_cache_set(
		_draft_key(),
		{
			"action": "create_certificate",
			"slots": clean,
			"guide": {
				"field": "",
				"phase": "review",
				"proposal": "",
				"accepted": [item["key"] for item in _certificate_guide_fields()],
			},
		},
	)
	_cache_set(_pending_key(), {"token": token, "action": "create_certificate", "slots": clean})
	return _reply(
		"\n".join(_certificate_review_lines(clean)),
		kind="guide",
		guide={"actions": _guide_actions(create=token, edit=True, cancel=True, create_label="Create Certificate")},
	)


def _certificate_suggestion(key: str, slots: dict) -> tuple[str, str]:
	if key == "certificate_name":
		taken = {
			row.get("certificate_name") or ""
			for row in frappe.get_all("AS2 Certificate", fields=["certificate_name"], limit_page_length=300)
		}
		return _next_available("New Certificate", taken), "suggested"
	if key == "purpose":
		return "Own Key Pair", "suggested"
	if key == "owner_type":
		return "Broker", "suggested"
	if key == "x509_alias":
		taken = {
			row.get("x509_alias") or ""
			for row in frappe.get_all("AS2 Certificate", fields=["x509_alias"], limit_page_length=300)
		}
		return _suggest_code(slots.get("certificate_name") or "New Certificate", "NEW_CERTIFICATE", taken), "suggested"
	if key == "common_name":
		return _placeholder_host(slots.get("certificate_name") or "certificate"), "suggested"
	if key == "certificate_type":
		return "Both", "suggested"
	if key == "status":
		return "Draft", "suggested"
	if key == "openas2_instance":
		choices = _instance_choices()
		if not choices:
			return "", ""
		return choices[0][1], "existing"
	return "", ""


def _certificate_duplicate_reply(slots: dict, row, accepted=None) -> dict:
	clean = _certificate_slots_only(slots)
	clean.pop("certificate_name", None)
	kept = [item for item in (accepted or []) if item != "certificate_name"]
	label = (row.get("certificate_name") if isinstance(row, dict) else row.certificate_name) or "That name"
	text = f"{label} is already a certificate. I did not create another one."
	value, source = _certificate_suggestion("certificate_name", clean)
	link = _certificate_link(row) if row.get("purpose") or row.get("x509_alias") or row.get("status") else None
	if not value:
		_save_certificate_guide(clean, "certificate_name", "ask", "", kept)
		return _reply(text, links=[link] if link else None)
	shown = _show_certificate_check(clean, "certificate_name", value, accepted=kept, source=source)
	shown["reply"] = text + "\n\n" + shown["reply"]
	if link:
		shown["links"] = [link]
	return shown


def _certificate_guide_next(slots: dict, accepted=None, intro: bool = False) -> dict:
	done = set(accepted or [])
	for field in _certificate_guide_fields():
		key = field["key"]
		if key in done:
			continue
		if slots.get(key):
			return _show_certificate_check(slots, key, slots[key], intro=intro, accepted=accepted, source="confirm")
		value, source = _certificate_suggestion(key, slots)
		if not value and field.get("suggest"):
			value, source = field["suggest"], "suggested"
		if value:
			return _show_certificate_check(slots, key, value, intro=intro, accepted=accepted, source=source)
		return _ask_certificate_field(slots, key, intro=intro, accepted=accepted)
	return _show_certificate_review(slots)


def _accept_certificate_proposal(slots: dict, guide: dict) -> dict:
	key = guide.get("field") or ""
	proposal = guide.get("proposal") or slots.get(key) or ""
	accepted = list(guide.get("accepted") or [])
	if not key:
		return _certificate_guide_next(slots, accepted)
	value, error = _accept_certificate_value(key, proposal)
	if error:
		return _ask_certificate_field(slots, key, error=error, accepted=accepted)
	clean = _certificate_slots_only(slots)
	if value:
		clean[key] = value
	elif not _certificate_field(key).get("optional"):
		return _ask_certificate_field(slots, key, accepted=accepted)
	if key == "certificate_name":
		conflict = _certificate_conflict(clean, key)
		if conflict:
			return _certificate_duplicate_reply(clean, conflict, accepted)
	if key not in accepted:
		accepted.append(key)
	return _certificate_guide_next(clean, accepted)


def _certificate_field_key_from_text(text: str) -> str:
	low = _normalize(text)
	for field in _certificate_guide_fields():
		if low == _normalize(field["label"]):
			return field["key"]
	if re.search(r"common name|\bcn\b", low):
		return "common_name"
	if re.search(r"x509|\balias\b", low):
		return "x509_alias"
	if re.search(r"owner|company|\btms\b", low):
		return "owner_type"
	if re.search(r"certificate type|(?<!owner )(?<!company )\btype\b", low):
		return "certificate_type"
	if re.search(r"\bpurpose\b", low):
		return "purpose"
	if re.search(r"\bstatus\b", low):
		return "status"
	if re.search(r"\binstance\b", low):
		return "openas2_instance"
	if re.search(r"certificate name|\bname\b", low):
		return "certificate_name"
	return ""


def _explicit_certificate_change(text: str, guide: dict) -> tuple[str, str] | None:
	patterns = (
		(r"(?:change|set|update|edit)\s+(?:the\s+)?certificate\s*name\s+(?:to\s+)?(.+)$", "certificate_name"),
		(r"(?:change|set|update|edit)\s+(?:the\s+)?purpose\s+(?:to\s+)?(.+)$", "purpose"),
		(r"(?:change|set|update|edit)\s+(?:the\s+)?(?:company|owner(?:\s*type)?|tms)\s+(?:to\s+)?(.+)$", "owner_type"),
		(r"(?:change|set|update|edit)\s+(?:the\s+)?(?:x509\s*)?alias\s+(?:to\s+)?(\S+)$", "x509_alias"),
		(r"(?:change|set|update|edit)\s+(?:the\s+)?(?:common\s*name|cn)\s+(?:to\s+)?(.+)$", "common_name"),
		(r"(?:change|set|update|edit)\s+(?:the\s+)?certificate\s*type\s+(?:to\s+)?(.+)$", "certificate_type"),
		(r"(?:change|set|update|edit)\s+(?:the\s+)?status\s+(?:to\s+)?(.+)$", "status"),
		(r"(?:change|set|update|edit)\s+(?:the\s+)?(?:openas2\s*)?instance\s+(?:to\s+)?(.+)$", "openas2_instance"),
		(r"(?:change|set)\s+that\s+to\s+(.+)$", ""),
	)
	for pattern, key in patterns:
		match = re.search(pattern, text, flags=re.I)
		if not match:
			continue
		value = match.group(1).strip()
		if not key:
			key = guide.get("field") or "certificate_name"
			if _match_choice(value, CERTIFICATE_TYPES) and key != "certificate_type":
				key = "certificate_type"
			elif _match_choice(value, CERTIFICATE_PURPOSES) and key != "purpose":
				key = "purpose"
			elif _normalize_type(value) and key not in {"owner_type", "certificate_type", "purpose"}:
				key = "owner_type"
		return key, value
	return None


def _certificate_guide_turn(text: str, normalized: str) -> dict:
	draft = _cache_get(_draft_key())
	slots = dict(draft.get("slots") or {})
	guide = dict(draft.get("guide") or {})
	phase = guide.get("phase") or "ask"
	field = guide.get("field") or "certificate_name"
	accepted = list(guide.get("accepted") or [])
	low = normalized
	if _classify(text) == "create_certificate":
		return _certificate_guide_next(slots, accepted, intro=not accepted)
	if low in {"cancel", "stop"}:
		_cache_set(_pending_key(), None)
		_cache_set(_draft_key(), None)
		return _reply("Cancelled. Nothing was changed.")
	if phase == "review" and low in {"create it", "create certificate", "create the certificate"}:
		pending = _cache_get(_pending_key())
		return confirm_assistant_action((pending or {}).get("token"))
	changed = _explicit_certificate_change(text, guide)
	if changed:
		key, raw = changed
		value, error = _accept_certificate_value(key, raw)
		if error:
			return _ask_certificate_field(slots, key, error=error, accepted=accepted)
		clean = _certificate_slots_only(slots)
		if value:
			clean[key] = value
		elif not _certificate_field(key).get("optional"):
			return _ask_certificate_field(slots, key, accepted=accepted)
		else:
			clean.pop(key, None)
		if key == "certificate_name" and value:
			conflict = _certificate_conflict(clean, key)
			if conflict:
				return _certificate_duplicate_reply(clean, conflict, accepted)
		if key not in accepted:
			accepted.append(key)
		return _certificate_guide_next(clean, accepted)
	if low in {"proceed", "continue", "next"} or (phase == "check" and low in {"yes", "ok", "okay", "correct"}):
		return _accept_certificate_proposal(slots, guide)
	if re.search(r"\b(?:edit|change)\b.+\b(name|purpose|company|owner|alias|cn|type|status|instance)\b", low):
		return _ask_certificate_field(slots, _certificate_field_key_from_text(text) or field, accepted=accepted)
	if low in {"edit", "change", "change it", "edit that"}:
		if phase == "review":
			names = [item["label"] for item in _certificate_guide_fields()]
			_save_certificate_guide(slots, "", "pick", "", accepted)
			return _reply(
				"Which field should I change?\n\n" + "\n".join(f"- {name}" for name in names),
				kind="guide",
				guide={"options": names, "actions": []},
			)
		return _ask_certificate_field(slots, field or "certificate_name", accepted=accepted)
	picked = _certificate_field_key_from_text(text) if phase == "pick" else ""
	if picked and phase == "pick":
		return _ask_certificate_field(slots, picked, accepted=accepted)
	if phase in {"ask", "check"}:
		value, error = _accept_certificate_value(field, text)
		optional_skip = (not value and not error and _certificate_field(field).get("optional"))
		if error:
			return _ask_certificate_field(slots, field, error=error, accepted=accepted)
		if optional_skip:
			clean = _certificate_slots_only(slots)
			clean.pop(field, None)
			if field not in accepted:
				accepted.append(field)
			return _certificate_guide_next(clean, accepted)
		return _show_certificate_check(slots, field, value, accepted=accepted)
	return _show_certificate_review(slots)


def _begin_certificate_guide(text: str) -> dict:
	slots = _guided_certificate_slots(text)
	draft = _cache_get(_draft_key())
	if draft.get("action") == "create_certificate" and draft.get("guide") and draft.get("slots"):
		merged = dict(draft.get("slots") or {})
		merged.update(slots)
		slots = _certificate_slots_only(merged)
	return _certificate_guide_next(slots, [], intro=True)


CONFIG_STATUSES = ("Active", "Inactive", "Error")
CONFIG_PROTOCOLS = ("HTTP", "HTTPS")
CONFIG_MDN_MODES = ("Synchronous", "Asynchronous")


def _configuration_guide_fields(slots: dict | None = None) -> list[dict]:
	slots = slots or {}
	fields = [
		{"key": "instance_name", "label": "Name", "kind": "text"},
		{"key": "instance_type", "label": "Instance Type", "kind": "select", "options": list(PARTNER_TYPES)},
		{"key": "as2_id", "label": "AS2 ID", "kind": "text"},
		{"key": "host", "label": "Host", "kind": "text", "suggest": "localhost"},
		{"key": "status", "label": "Status", "kind": "select", "options": list(CONFIG_STATUSES), "suggest": "Active"},
		{
			"key": "protocol",
			"label": "Primary Protocol",
			"kind": "select",
			"options": list(CONFIG_PROTOCOLS),
			"suggest": "HTTPS",
		},
	]
	protocol = slots.get("protocol") or ""
	if protocol == "HTTP":
		fields.append({"key": "http_port", "label": "HTTP Port", "kind": "port"})
	elif protocol == "HTTPS":
		fields.append({"key": "https_port", "label": "HTTPS Port", "kind": "port"})
	if protocol:
		fields.append(
			{
				"key": "mdn_mode",
				"label": "MDN Mode",
				"kind": "select",
				"options": list(CONFIG_MDN_MODES),
				"suggest": "Synchronous",
			}
		)
	if slots.get("mdn_mode") == "Asynchronous":
		fields.append({"key": "mdn_https_port", "label": "MDN HTTPS Port", "kind": "port"})
	return fields


def _configuration_field(key: str, slots: dict | None = None) -> dict:
	for field in _configuration_guide_fields(slots):
		if field["key"] == key:
			return field
	return _configuration_guide_fields(slots)[0]


def _configuration_slots_only(slots: dict) -> dict:
	kept = {}
	allowed = {item["key"] for item in _configuration_guide_fields({"protocol": "HTTPS", "mdn_mode": "Asynchronous"})}
	allowed.update({"protocol", "http_port", "https_port", "mdn_mode", "mdn_https_port"})
	for key in allowed:
		value = (slots.get(key) or "").strip()
		if value and key not in HIDDEN and not _SECRET_TEXT.search(value):
			kept[key] = value
	return kept


def _guided_configuration_slots(text: str) -> dict:
	slots = _extract_slots(text, "create_configuration")
	kind = _normalize_type(_grab(r"\b(shipper|broker|carrier|company\s*c)\b", text))
	if kind:
		slots["instance_type"] = kind
	match = re.search(
		r"\b(?:add|create|new)\s+(.+?)\s+as\s+(?:a|an)\s+.+?\b(?:configuration|instance)\b",
		text,
		flags=re.I,
	)
	if match:
		name = re.sub(r"\s+", " ", match.group(1)).strip(" .\"'")
		if name and name.lower() not in {"a", "an", "the", "configuration", "instance", "openas2"} and not _normalize_type(name):
			slots["instance_name"] = name
	return _configuration_slots_only(slots)


def _save_configuration_guide(slots: dict, field: str, phase: str, proposal: str = "", accepted=None) -> None:
	_cache_set(_pending_key(), None)
	clean = _configuration_slots_only(slots)
	_cache_set(
		_draft_key(),
		{
			"action": "create_configuration",
			"slots": clean,
			"guide": {
				"field": field,
				"phase": phase,
				"proposal": proposal or "",
				"accepted": list(accepted or []),
			},
		},
	)


def _configuration_row(name: str):
	if not name or not frappe.has_permission("OpenAS2 Instance", "read", name):
		return {"name": name, "instance_name": name} if name else None
	return frappe.db.get_value(
		"OpenAS2 Instance",
		name,
		["name", "instance_name", "instance_type", "as2_id", "status", "host"],
		as_dict=True,
	)


def _configuration_conflict(slots: dict, field: str | None = None):
	if field in (None, "instance_name") and slots.get("instance_name"):
		existing = frappe.db.exists("OpenAS2 Instance", {"instance_name": slots["instance_name"].strip()})
		if existing:
			return _configuration_row(existing), "instance_name"
	if field in (None, "as2_id") and slots.get("as2_id"):
		existing = frappe.db.exists("OpenAS2 Instance", {"as2_id": slots["as2_id"].strip()})
		if existing:
			return _configuration_row(existing), "as2_id"
	return None, ""


def _accept_port(raw: str) -> tuple[str, str]:
	match = re.search(r"\b(\d{1,5})\b", raw or "")
	if not match:
		return "", "Enter a port from 1 to 65535."
	port = int(match.group(1))
	if port < 1 or port > 65535:
		return "", "Enter a port from 1 to 65535."
	return str(port), ""


def _accept_configuration_value(key: str, raw: str, slots: dict | None = None) -> tuple[str, str]:
	text = (raw or "").strip().strip("\"'")
	if key in HIDDEN or _SECRET_TEXT.search(text) or re.search(r"\bpassword\b", text, flags=re.I):
		return "", "Passwords and keystore secrets stay out of chat."
	if key in {"http_port", "https_port", "mdn_https_port"} or key == "port":
		return _accept_port(text)
	if key == "instance_type":
		value = _normalize_type(text)
		if not value:
			return "", "Choose an instance type: " + ", ".join(PARTNER_TYPES) + "."
		return value, ""
	if key == "status":
		value = _match_choice(text, CONFIG_STATUSES)
		if not value:
			return "", "Choose a status: " + ", ".join(CONFIG_STATUSES) + "."
		return value, ""
	if key == "protocol":
		value = _match_choice(text, CONFIG_PROTOCOLS)
		if not value:
			return "", "Choose a primary protocol: HTTP or HTTPS."
		return value, ""
	if key == "mdn_mode":
		value = _match_choice(text, CONFIG_MDN_MODES)
		if not value:
			return "", "Choose an MDN mode: Synchronous or Asynchronous."
		return value, ""
	if key == "as2_id":
		match = re.search(r"as2\s*id\s*(?:to|is|=|:)?\s*([A-Za-z0-9][A-Za-z0-9_-]{0,63})", text, flags=re.I)
		value = match.group(1) if match else text
		if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", value or ""):
			return "", "AS2 ID can use letters, numbers, underscores, and hyphens."
		return value, ""
	if key == "host":
		value = text.split()[0].strip(".,)") if text else ""
		if not value or _normalize(value) in {"proceed", "edit", "cancel", "create"}:
			return "", "What host should this instance use?"
		return value, ""
	if len(text) < 2 or _normalize(text) in {"proceed", "edit", "cancel", "create", "yes", "no"}:
		return "", "What should the configuration name be?"
	return re.sub(r"\s+", " ", text), ""


def _configuration_port_key(slots: dict, text: str = "") -> str:
	low = _normalize(text)
	if re.search(r"mdn https", low):
		return "mdn_https_port"
	if re.search(r"\bhttp port\b", low) or (re.search(r"\bhttp\b", low) and "https" not in low):
		return "http_port"
	if slots.get("protocol") == "HTTP":
		return "http_port"
	return "https_port"


def _ask_configuration_field(slots: dict, key: str, error: str = "", intro: bool = False, accepted=None) -> dict:
	field = _configuration_field(key, slots)
	kept = [item for item in (accepted or []) if item != key]
	_save_configuration_guide(slots, key, "ask", "", kept)
	prompts = {
		"instance_name": "What should the configuration name be?",
		"instance_type": "What type of instance is this?",
		"as2_id": "What AS2 ID should this instance use?",
		"host": "What host should this instance use?",
		"status": "What status should this configuration have?",
		"protocol": "Which primary protocol should partners use?",
		"http_port": "What HTTP port should this instance use?",
		"https_port": "What HTTPS port should this instance use?",
		"mdn_mode": "Which MDN mode should this instance use?",
		"mdn_https_port": "What MDN HTTPS port should this instance use?",
	}
	lead = prompts.get(key, "What value should I use?")
	if key == "instance_name" and intro:
		lead = "Let's create a configuration. What should the name be?"
	lines = [error, ""] if error else []
	lines.append(lead)
	options = list(field.get("options") or [])
	if options:
		lines.extend(["", "Choose one:", *[f"- {option}" for option in options]])
	return _reply("\n".join(lines), kind="guide", guide={"options": options, "actions": []})


def _show_configuration_check(
	slots: dict, key: str, value: str, intro: bool = False, accepted=None, source: str = "confirm"
) -> dict:
	field = _configuration_field(key, slots)
	kept = [item for item in (accepted or []) if item != key]
	_save_configuration_guide(slots, key, "check", value, kept)
	lines = ["Let's create a configuration.", ""] if intro else []
	lines.extend(_value_lines(field["label"], value, source))
	if key in {"http_port", "https_port", "mdn_https_port"} and source == "suggested":
		lines.append("This does not open the port or start OpenAS2.")
	return _reply("\n".join(lines), kind="guide", guide={"actions": _guide_actions(proceed=True, edit=True)})


def _published_as2_url(slots: dict) -> str:
	host = (slots.get("host") or "").strip()
	protocol = slots.get("protocol") or ""
	port = slots.get("https_port") if protocol == "HTTPS" else slots.get("http_port")
	if not host or not protocol or not port:
		return "not stored yet"
	scheme = protocol.lower()
	number = int(port)
	if number == (443 if scheme == "https" else 80):
		return f"{scheme}://{host}"
	return f"{scheme}://{host}:{number}"


def _configuration_review_lines(slots: dict) -> list[str]:
	lines = ["Review Configuration", ""]
	for field in _configuration_guide_fields(slots):
		lines.append(f"{field['label']}: {slots.get(field['key'])}")
	https = slots.get("protocol") == "HTTPS"
	lines.extend(
		[
			f"Enable HTTP: {'Yes' if not https else 'No'}",
			f"Enable HTTPS: {'Yes' if https else 'No'}",
			f"Published AS2 URL: {_published_as2_url(slots)}",
			"Lifecycle Status: Unknown",
			"Connection Status: Unknown",
			"Provision Source: External",
			"",
			"This saves the configuration record only. OpenAS2 is not started and no port is opened.",
			"",
			"Everything looks correct?",
		]
	)
	return lines


def _show_configuration_review(slots: dict) -> dict:
	conflict, which = _configuration_conflict(slots)
	if conflict:
		return _configuration_duplicate_reply(slots, conflict, which, [item["key"] for item in _configuration_guide_fields(slots)])
	clean = _configuration_slots_only(slots)
	token = secrets.token_hex(16)
	_cache_set(
		_draft_key(),
		{
			"action": "create_configuration",
			"slots": clean,
			"guide": {
				"field": "",
				"phase": "review",
				"proposal": "",
				"accepted": [item["key"] for item in _configuration_guide_fields(clean)],
			},
		},
	)
	_cache_set(_pending_key(), {"token": token, "action": "create_configuration", "slots": clean})
	return _reply(
		"\n".join(_configuration_review_lines(clean)),
		kind="guide",
		guide={"actions": _guide_actions(create=token, edit=True, cancel=True, create_label="Create Configuration")},
	)


def _configuration_suggestion(key: str, slots: dict) -> tuple[str, str]:
	if key == "instance_name":
		taken = {(row.instance_name or "") for row in _config_rows()}
		return _next_available("New Configuration", taken), "suggested"
	if key == "instance_type":
		return "Broker", "suggested"
	if key == "as2_id":
		taken = {(row.as2_id or "") for row in _config_rows()}
		return _suggest_code(slots.get("instance_name") or "New Configuration", "NEW_CONFIGURATION", taken), "suggested"
	if key == "host":
		return "localhost", "suggested"
	if key == "status":
		return "Active", "suggested"
	if key == "protocol":
		return "HTTPS", "suggested"
	if key in {"http_port", "https_port"}:
		return _free_port(), "suggested"
	if key == "mdn_mode":
		return "Synchronous", "suggested"
	if key == "mdn_https_port":
		return _free_port(slots.get("https_port") or slots.get("http_port")), "suggested"
	return "", ""


def _configuration_duplicate_reply(slots: dict, row, field: str, accepted=None) -> dict:
	clean = _configuration_slots_only(slots)
	clean.pop(field, None)
	kept = [item for item in (accepted or []) if item != field]
	label = (row.get("instance_name") if isinstance(row, dict) else "") or "That configuration"
	as2_id = (row.get("as2_id") if isinstance(row, dict) else "") or ""
	if field == "as2_id":
		text = f"AS2 ID {as2_id or clean.get('as2_id') or ''} is already used by {label}. I did not create another configuration."
	else:
		text = f"{label} is already a configuration. I did not create another one."
	value, source = _configuration_suggestion(field, clean)
	link = _configuration_link(row) if row.get("instance_type") or row.get("as2_id") else None
	if not value:
		_save_configuration_guide(clean, field, "ask", "", kept)
		return _reply(text, links=[link] if link else None)
	shown = _show_configuration_check(clean, field, value, accepted=kept, source=source)
	shown["reply"] = text + "\n\n" + shown["reply"]
	if link:
		shown["links"] = [link]
	return shown


def _configuration_guide_next(slots: dict, accepted=None, intro: bool = False) -> dict:
	done = set(accepted or [])
	for field in _configuration_guide_fields(slots):
		key = field["key"]
		if key in done:
			continue
		if slots.get(key):
			return _show_configuration_check(slots, key, slots[key], intro=intro, accepted=accepted, source="confirm")
		value, source = _configuration_suggestion(key, slots)
		if not value and field.get("suggest"):
			value, source = field["suggest"], "suggested"
		if value:
			return _show_configuration_check(slots, key, value, intro=intro, accepted=accepted, source=source)
		return _ask_configuration_field(slots, key, intro=intro, accepted=accepted)
	return _show_configuration_review(slots)


def _store_configuration_value(slots: dict, key: str, value: str, accepted: list) -> tuple[dict, list]:
	clean = _configuration_slots_only(slots)
	if value:
		clean[key] = value
	if key == "protocol":
		drop = "http_port" if value == "HTTPS" else "https_port"
		clean.pop(drop, None)
		accepted = [item for item in accepted if item != drop]
	if key == "mdn_mode" and value != "Asynchronous":
		clean.pop("mdn_https_port", None)
		accepted = [item for item in accepted if item != "mdn_https_port"]
	if key not in accepted:
		accepted.append(key)
	return clean, accepted


def _accept_configuration_proposal(slots: dict, guide: dict) -> dict:
	key = guide.get("field") or ""
	proposal = guide.get("proposal") or slots.get(key) or ""
	accepted = list(guide.get("accepted") or [])
	if not key or not proposal:
		return _configuration_guide_next(slots, accepted)
	value, error = _accept_configuration_value(key, proposal, slots)
	if error:
		return _ask_configuration_field(slots, key, error=error, accepted=accepted)
	clean, accepted = _store_configuration_value(slots, key, value, accepted)
	if key in ("instance_name", "as2_id"):
		conflict, which = _configuration_conflict(clean, key)
		if conflict:
			return _configuration_duplicate_reply(clean, conflict, which, accepted)
	return _configuration_guide_next(clean, accepted)


def _configuration_field_key_from_text(text: str, slots: dict) -> str:
	low = _normalize(text)
	for field in _configuration_guide_fields(slots):
		if low == _normalize(field["label"]):
			return field["key"]
	if re.search(r"mdn https port|mdn https", low):
		return "mdn_https_port"
	if re.search(r"\bmdn\b", low):
		return "mdn_mode"
	if re.search(r"\bport\b", low):
		return _configuration_port_key(slots, text)
	if re.search(r"primary protocol|\bprotocol\b", low):
		return "protocol"
	if re.search(r"instance type|\btype\b", low):
		return "instance_type"
	if re.search(r"as2\s*id", low):
		return "as2_id"
	if re.search(r"\bhost\b", low):
		return "host"
	if re.search(r"\bstatus\b", low):
		return "status"
	if re.search(r"\bname\b", low):
		return "instance_name"
	return ""


def _explicit_configuration_change(text: str, guide: dict, slots: dict) -> tuple[str, str] | None:
	patterns = (
		(r"(?:change|set|update|edit)\s+(?:the\s+)?as2\s*id\s+(?:to\s+)?([A-Za-z0-9_-]+)", "as2_id"),
		(r"(?:change|set|update|edit)\s+(?:the\s+)?host\s+(?:to\s+)?(\S+)", "host"),
		(r"(?:change|set|update|edit)\s+(?:the\s+)?name\s+(?:to\s+)?(.+)$", "instance_name"),
		(r"(?:change|set|update|edit)\s+(?:the\s+)?(?:instance\s*)?type\s+(?:to\s+)?(.+)$", "instance_type"),
		(r"(?:change|set|update|edit)\s+(?:the\s+)?status\s+(?:to\s+)?(.+)$", "status"),
		(r"(?:change|set|update|edit)\s+(?:the\s+)?(?:primary\s*)?protocol\s+(?:to\s+)?(.+)$", "protocol"),
		(r"(?:change|set|update|edit)\s+(?:the\s+)?mdn(?:\s*mode)?\s+(?:to\s+)?(.+)$", "mdn_mode"),
		(r"(?:change|set|update|edit)\s+(?:the\s+)?(?:https|http|mdn https)?\s*port\s+(?:to\s+)?(\d{1,5})", "port"),
		(r"(?:change|set)\s+that\s+to\s+(.+)$", ""),
	)
	for pattern, key in patterns:
		match = re.search(pattern, text, flags=re.I)
		if not match:
			continue
		value = match.group(1).strip()
		if key == "port":
			key = _configuration_port_key(slots, text)
		elif not key:
			key = guide.get("field") or "instance_name"
			if _normalize_type(value):
				key = "instance_type"
			elif _match_choice(value, CONFIG_PROTOCOLS):
				key = "protocol"
			elif _match_choice(value, CONFIG_MDN_MODES):
				key = "mdn_mode"
		return key, value
	return None


def _configuration_guide_turn(text: str, normalized: str) -> dict:
	draft = _cache_get(_draft_key())
	slots = dict(draft.get("slots") or {})
	guide = dict(draft.get("guide") or {})
	phase = guide.get("phase") or "ask"
	field = guide.get("field") or "instance_name"
	accepted = list(guide.get("accepted") or [])
	low = normalized
	if _classify(text) == "create_configuration":
		return _configuration_guide_next(slots, accepted, intro=not accepted)
	if low in {"cancel", "stop"}:
		_cache_set(_pending_key(), None)
		_cache_set(_draft_key(), None)
		return _reply("Cancelled. Nothing was changed.")
	if phase == "review" and low in {"create it", "create configuration", "create the configuration"}:
		pending = _cache_get(_pending_key())
		return confirm_assistant_action((pending or {}).get("token"))
	changed = _explicit_configuration_change(text, guide, slots)
	if changed:
		key, raw = changed
		value, error = _accept_configuration_value(key, raw, slots)
		if error:
			return _ask_configuration_field(slots, key, error=error, accepted=accepted)
		clean, accepted = _store_configuration_value(slots, key, value, accepted)
		if key in ("instance_name", "as2_id"):
			conflict, which = _configuration_conflict(clean, key)
			if conflict:
				return _configuration_duplicate_reply(clean, conflict, which, accepted)
		return _configuration_guide_next(clean, accepted)
	if low in {"proceed", "continue", "next"} or (phase == "check" and low in {"yes", "ok", "okay", "correct"}):
		return _accept_configuration_proposal(slots, guide)
	if re.search(r"\b(?:edit|change)\b.+\b(name|type|as2 id|host|status|protocol|port|mdn)\b", low):
		return _ask_configuration_field(slots, _configuration_field_key_from_text(text, slots) or field, accepted=accepted)
	if low in {"edit", "change", "change it", "edit that"}:
		if phase == "review":
			names = [item["label"] for item in _configuration_guide_fields(slots)]
			_save_configuration_guide(slots, "", "pick", "", accepted)
			return _reply(
				"Which field should I change?\n\n" + "\n".join(f"- {name}" for name in names),
				kind="guide",
				guide={"options": names, "actions": []},
			)
		return _ask_configuration_field(slots, field or "instance_name", accepted=accepted)
	picked = _configuration_field_key_from_text(text, slots) if phase == "pick" else ""
	if picked and phase == "pick":
		return _ask_configuration_field(slots, picked, accepted=accepted)
	if phase in {"ask", "check"}:
		value, error = _accept_configuration_value(field, text, slots)
		if error:
			return _ask_configuration_field(slots, field, error=error, accepted=accepted)
		return _show_configuration_check(slots, field, value, accepted=accepted)
	return _show_configuration_review(slots)


def _begin_configuration_guide(text: str) -> dict:
	slots = _guided_configuration_slots(text)
	draft = _cache_get(_draft_key())
	if draft.get("action") == "create_configuration" and draft.get("guide") and draft.get("slots"):
		merged = dict(draft.get("slots") or {})
		merged.update(slots)
		slots = _configuration_slots_only(merged)
	return _configuration_guide_next(slots, [], intro=True)


CONFIGURATION_EDIT_FIELDS = (
	("instance_name", "Name"),
	("instance_type", "Instance Type"),
	("as2_id", "AS2 ID"),
	("host", "Host"),
	("status", "Status"),
	("protocol", "Primary Protocol"),
	("http_port", "HTTP Port"),
	("https_port", "HTTPS Port"),
	("mdn_mode", "MDN Mode"),
	("mdn_https_port", "MDN HTTPS Port"),
)


def _configuration_edit_change(text: str) -> tuple[str, str]:
	"""Return the configuration field a sentence wants to change, plus a value when one was given."""
	raw = (text or "").strip()
	if re.search(r"\bstatus\b", raw, flags=re.I):
		match = re.search(r"\b(active|inactive|error)\b", raw, flags=re.I)
		if not match:
			return "status", ""
		word = match.group(1).lower()
		return "status", word[:1].upper() + word[1:]
	if re.search(r"\bas2\s*id\b", raw, flags=re.I):
		match = re.search(
			r"\bas2\s*id\b(?:\s*(?:to|as|is|=|:)\s*|\s+)([A-Za-z0-9][A-Za-z0-9_\-]{0,63})",
			raw,
			flags=re.I,
		)
		value = match.group(1) if match else ""
		if value.lower() in {"to", "as", "is", "the", "a", "an"}:
			value = ""
		return "as2_id", value
	if re.search(r"\bmdn\s*https\s*port\b", raw, flags=re.I):
		match = re.search(r"\b(\d{1,5})\b", raw)
		return "mdn_https_port", match.group(1) if match else ""
	if re.search(r"\bhttps\s*port\b", raw, flags=re.I):
		match = re.search(r"\b(\d{1,5})\b", raw)
		return "https_port", match.group(1) if match else ""
	if re.search(r"\bhttp\s*port\b", raw, flags=re.I):
		match = re.search(r"\b(\d{1,5})\b", raw)
		return "http_port", match.group(1) if match else ""
	if re.search(r"\bmdn\b", raw, flags=re.I):
		return "mdn_mode", _match_choice(raw, CONFIG_MDN_MODES)
	if re.search(r"\bprotocol\b", raw, flags=re.I):
		return "protocol", _match_choice(raw, CONFIG_PROTOCOLS)
	if re.search(r"\bport\b", raw, flags=re.I):
		match = re.search(r"\b(\d{1,5})\b", raw)
		key = "https_port" if re.search(r"\bhttps\b", raw, flags=re.I) else "http_port"
		return key, match.group(1) if match else ""
	if re.search(r"\bhost\b", raw, flags=re.I):
		match = re.search(r"\bhost\b\s*(?:to|as|is|=|:)\s+(\S+)", raw, flags=re.I)
		return "host", match.group(1).rstrip(".,)") if match else ""
	if re.search(r"\b(?:instance\s*)?type\b", raw, flags=re.I):
		return "instance_type", _normalize_type(raw)
	if re.search(r"\b(?:configuration\s*|instance\s*)?name\b", raw, flags=re.I):
		match = re.search(r"\bname\b\s*(?:to|as|is|=|:)\s+[\"']?(.+?)[\"']?$", raw, flags=re.I)
		return "instance_name", re.sub(r"\s+", " ", match.group(1)).strip(" .\"'") if match else ""
	return "", ""


def _configuration_edit_query(text: str) -> str:
	raw = re.sub(r"\s+", " ", (text or "").strip())
	cleaned = re.sub(r"^(?:please\s+)?(?:edit|update|change|modify)\s+", "", raw, flags=re.I)
	cleaned = re.sub(r"\s+(?:configurations?|instances?)$", "", cleaned, flags=re.I).strip()
	cleaned = re.sub(r"^(?:the\s+|a\s+|an\s+)?(?:configurations?|instances?)\s+", "", cleaned, flags=re.I).strip()
	cleaned = re.sub(r"^(?:a|an|the)\s+", "", cleaned, flags=re.I).strip(" .\"'")
	if cleaned.lower() in {
		"",
		"configuration",
		"configurations",
		"instance",
		"instances",
		"a",
		"an",
		"the",
		"this",
		"that",
		"it",
		"one",
	}:
		return ""
	return cleaned


def _configuration_edit_subject(text: str) -> str:
	cleaned = re.sub(
		r"\b(?:and\s+)?(?:please\s+)?(?:change|update|edit|set|modify)\s+(?:the\s+|its\s+)?"
		r"(?:configuration\s+name|instance\s+name|instance\s+type|as2\s*id|mdn\s*https\s*port|"
		r"https\s*port|http\s*port|mdn\s*mode|primary\s+protocol|protocol|mdn|host|status|port|type|name)\b.*$",
		"",
		text or "",
		flags=re.I,
	).strip()
	cleaned = re.sub(
		r"\b(?:configuration\s+name|instance\s+name|instance\s+type|as2\s*id|mdn\s*mode|primary\s+protocol|status)\b.*$",
		"",
		cleaned,
		flags=re.I,
	).strip()
	if not cleaned:
		return ""
	return _configuration_edit_query(cleaned)


def _is_new_configuration_edit(text: str) -> bool:
	if _classify(text) != "update_configuration":
		return False
	field, _value = _configuration_edit_change(text)
	return bool(_configuration_edit_subject(text) or not field)


def _search_configurations(query: str) -> list:
	needle = re.sub(r"\s+", " ", (query or "").strip()).lower()
	if not needle or needle in {"configuration", "configurations", "instance", "instances", "a", "an", "the"}:
		return []
	exact = []
	partial = []
	seen = set()
	for row in _config_rows():
		labels = {
			_row_value(row, "name").strip().lower(),
			_row_value(row, "instance_name").strip().lower(),
			_row_value(row, "as2_id").strip().lower(),
		}
		if needle in labels and row.name not in seen:
			exact.append(row)
			seen.add(row.name)
	if exact:
		return exact
	for row in _config_rows():
		name = _row_value(row, "instance_name").lower()
		as2_id = _row_value(row, "as2_id").lower()
		docname = _row_value(row, "name").lower()
		if needle in name or needle in as2_id or needle in docname:
			if row.name not in seen:
				partial.append(row)
				seen.add(row.name)
	return partial


def _configuration_edit_record(docname: str):
	fields = list(dict.fromkeys([*CONFIG_FIELDS, "mdn_https_port", "http_enabled", "https_enabled"]))
	if not docname or not frappe.db.exists("OpenAS2 Instance", docname):
		return None
	return frappe.db.get_value("OpenAS2 Instance", docname, fields, as_dict=True)


def _configuration_edit_label(key: str) -> str:
	for field, label in CONFIGURATION_EDIT_FIELDS:
		if field == key:
			return label
	return key


def _save_configuration_edit(docname: str, phase: str, field: str = "", proposal: str = "", current: str = "") -> None:
	_cache_set(_pending_key(), None)
	_cache_set(
		_draft_key(),
		{
			"action": "update_configuration",
			"slots": {"name": docname or ""},
			"guide": {
				"phase": phase,
				"field": field or "",
				"proposal": proposal or "",
				"current": current or "",
				"configuration": docname or "",
			},
		},
	)


def _configuration_choices_reply(intro: str, rows: list, field: str = "", proposal: str = "") -> dict:
	_save_configuration_edit("", "pick_configuration", field, proposal)
	names = [_row_value(row, "instance_name") or _row_value(row, "name") for row in rows[:30]]
	lines = [intro, "", "Choose one:"]
	lines.extend(f"- {name}" for name in names)
	if len(rows) > 30:
		lines.append(f"{len(rows) - 30} more configurations are not listed here.")
	lines.extend(["", "Nothing has been saved."])
	return _reply(
		"\n".join(lines),
		kind="guide",
		links=[_configuration_link(row) for row in rows[:30]],
		guide={"options": names, "actions": _guide_actions(cancel=True)},
	)


def _show_configuration_edit_fields(row) -> dict:
	label = _row_value(row, "instance_name") or _row_value(row, "name")
	_save_configuration_edit(row.name, "pick_field")
	lines = [f"Selected record: {label}", ""]
	for key, field_label in CONFIGURATION_EDIT_FIELDS:
		if key == "mdn_https_port" and _row_value(row, "mdn_mode") != "Asynchronous":
			continue
		shown = _row_value(row, key) or "—"
		lines.append(f"{field_label}: {shown}")
	lines.extend(["", "Which field should I change?", "Nothing has been saved."])
	options = [
		field_label
		for key, field_label in CONFIGURATION_EDIT_FIELDS
		if not (key == "mdn_https_port" and _row_value(row, "mdn_mode") != "Asynchronous")
	]
	return _reply(
		"\n".join(lines),
		kind="guide",
		links=[_configuration_link(row)],
		guide={"options": options, "actions": _guide_actions(edit=True, cancel=True)},
	)


def _ask_configuration_edit_value(row, key: str, error: str = "") -> dict:
	label = _configuration_edit_label(key)
	current = _row_value(row, key) or "—"
	_save_configuration_edit(row.name, "ask", key, "", current)
	lines = [error, ""] if error else []
	lines.extend(
		[
			f"Selected record: {_row_value(row, 'instance_name') or row.name}",
			f"Current {label}: {current}",
			"",
			f"What should the new {label} be?",
			"Nothing has been saved.",
		]
	)
	field = _configuration_field(key, {"protocol": _row_value(row, "protocol"), "mdn_mode": _row_value(row, "mdn_mode")})
	options = list(field.get("options") or [])
	if options:
		lines.extend(["", "Choose one:", *[f"- {option}" for option in options]])
	return _reply(
		"\n".join(lines),
		kind="guide",
		links=[_configuration_link(row)],
		guide={"options": options, "actions": _guide_actions(cancel=True)},
	)


def _show_configuration_edit_check(row, key: str, proposed: str) -> dict:
	label = _configuration_edit_label(key)
	current = _row_value(row, key) or "—"
	_save_configuration_edit(row.name, "check", key, proposed, current)
	lines = [
		f"Selected record: {_row_value(row, 'instance_name') or row.name}",
		f"Current {label}: {current}",
		f"Proposed {label}: {proposed}",
		"",
		"Nothing has been saved. OpenAS2 will not be started.",
	]
	return _reply(
		"\n".join(lines),
		kind="guide",
		links=[_configuration_link(row)],
		guide={"actions": _guide_actions(proceed=True, edit=True, cancel=True)},
	)


def _show_configuration_edit_review(row, key: str, proposed: str) -> dict:
	label = _configuration_edit_label(key)
	current = _row_value(row, key) or "—"
	clean = {"name": row.name, key: proposed}
	token = secrets.token_hex(16)
	_cache_set(
		_draft_key(),
		{
			"action": "update_configuration",
			"slots": clean,
			"guide": {
				"phase": "review",
				"field": key,
				"proposal": proposed,
				"current": current,
				"configuration": row.name,
			},
		},
	)
	_cache_set(_pending_key(), {"token": token, "action": "update_configuration", "slots": clean})
	lines = [
		"Review this update",
		"",
		f"Configuration: {_row_value(row, 'instance_name') or row.name}",
		f"Field: {label}",
		f"Current value: {current}",
		f"Proposed value: {proposed}",
		"",
		"Nothing has been saved. OpenAS2 will not be started.",
	]
	return _reply(
		"\n".join(lines),
		kind="guide",
		links=[_configuration_link(row)],
		guide={"actions": _guide_actions(create=token, edit=True, cancel=True, create_label="Update Configuration")},
	)


def _configuration_edit_conflict(row, key: str, value: str):
	if key == "instance_name":
		existing = frappe.db.exists(
			"OpenAS2 Instance",
			{"instance_name": value, "name": ["!=", row.name]},
		)
		return _configuration_edit_record(existing) if existing else None
	if key == "as2_id":
		existing = frappe.db.exists(
			"OpenAS2 Instance",
			{"as2_id": value, "name": ["!=", row.name]},
		)
		return _configuration_edit_record(existing) if existing else None
	return None


def _propose_configuration_edit(row, key: str, raw: str) -> dict:
	slots = {"protocol": _row_value(row, "protocol"), "mdn_mode": _row_value(row, "mdn_mode")}
	value, error = _accept_configuration_value(key, raw, slots)
	if error:
		return _ask_configuration_edit_value(row, key, error=error)
	current = _row_value(row, key)
	if value == current:
		shown = _show_configuration_edit_fields(row)
		shown["reply"] = (
			f"That is already the current {_configuration_edit_label(key)}. Nothing was saved.\n\n" + shown["reply"]
		)
		return shown
	conflict = _configuration_edit_conflict(row, key, value) if key in {"instance_name", "as2_id"} else None
	if conflict:
		label = _row_value(conflict, "instance_name") or _row_value(conflict, "name")
		return _ask_configuration_edit_value(
			row,
			key,
			error=f"{label} already uses {_configuration_edit_label(key)} {value}. I did not change this configuration.",
		)
	return _show_configuration_edit_check(row, key, value)


def _open_configuration_edit(row, field: str = "", proposal: str = "") -> dict:
	if field and proposal:
		return _propose_configuration_edit(row, field, proposal)
	if field:
		return _ask_configuration_edit_value(row, field)
	return _show_configuration_edit_fields(row)


def _begin_configuration_edit(text: str, context: dict | None = None) -> dict:
	context = context or {}
	field, proposal = _configuration_edit_change(text)
	query = _configuration_edit_subject(text)
	if not query and re.search(r"\b(this|current|selected)\s+(?:configuration|instance)\b", text or "", flags=re.I):
		query = (context.get("configuration") or "").strip()
	if not query:
		rows = _config_rows()
		if not rows:
			_cache_set(_draft_key(), None)
			_cache_set(_pending_key(), None)
			return _reply("No OpenAS2 configurations are stored. I did not create one.")
		return _configuration_choices_reply("Which configuration should I edit?", rows, field, proposal)
	matches = _search_configurations(query)
	if not matches:
		rows = _config_rows()
		if not rows:
			return _reply(f"No configuration matches \"{query}\". No OpenAS2 configurations are stored. I did not create one.")
		return _configuration_choices_reply(
			f"No configuration matches \"{query}\". I did not create one. Which existing configuration should I edit?",
			rows,
		)
	if len(matches) > 1:
		return _configuration_choices_reply(
			f"More than one configuration matches \"{query}\". Which one should I edit?",
			matches,
		)
	return _open_configuration_edit(matches[0], field, proposal)


def _configuration_edit_turn(text: str, normalized: str) -> dict:
	draft = _cache_get(_draft_key())
	guide = dict(draft.get("guide") or {})
	phase = guide.get("phase") or "pick_configuration"
	field = guide.get("field") or ""
	low = normalized
	row = _configuration_edit_record(guide.get("configuration") or (draft.get("slots") or {}).get("name") or "")
	if low in {"cancel", "stop", "no"}:
		_cache_set(_pending_key(), None)
		_cache_set(_draft_key(), None)
		return _reply("Cancelled. Nothing was changed.")
	if phase == "review" and low in {"update it", "update configuration", "save", "save it"}:
		pending = _cache_get(_pending_key())
		return confirm_assistant_action((pending or {}).get("token"))
	if _is_new_configuration_edit(text) and (_configuration_edit_subject(text) or not _configuration_edit_change(text)[0]):
		return _begin_configuration_edit(text, {})
	change_field, change_value = _configuration_edit_change(text)
	if change_field and row and re.search(r"\b(change|update|edit|set|modify)\b", text or "", flags=re.I):
		if change_value:
			return _propose_configuration_edit(row, change_field, change_value)
		return _ask_configuration_edit_value(row, change_field)
	if low in {"proceed", "continue", "next"} or (phase == "check" and low in {"yes", "ok", "okay", "correct"}):
		if not row or not field:
			return _begin_configuration_edit("", {})
		if phase == "check":
			return _show_configuration_edit_review(row, field, guide.get("proposal") or "")
		if phase == "ask" and guide.get("proposal"):
			return _show_configuration_edit_check(row, field, guide.get("proposal") or "")
	if low in {"edit", "change", "change it", "edit that"}:
		if row and phase in {"check", "review"} and field:
			return _ask_configuration_edit_value(row, field)
		if row:
			return _show_configuration_edit_fields(row)
		return _begin_configuration_edit("", {})
	if phase == "pick_configuration":
		matches = _search_configurations(text)
		if len(matches) == 1:
			return _open_configuration_edit(matches[0], field, guide.get("proposal") or "")
		if len(matches) > 1:
			return _configuration_choices_reply(
				f"More than one configuration matches \"{text.strip()}\". Which one should I edit?",
				matches,
			)
		rows = _config_rows()
		if not rows:
			_cache_set(_draft_key(), None)
			return _reply(f"No configuration matches \"{text.strip()}\". No OpenAS2 configurations are stored. I did not create one.")
		return _configuration_choices_reply(
			f"No configuration matches \"{text.strip()}\". I did not create one. Which existing configuration should I edit?",
			rows,
			field,
			guide.get("proposal") or "",
		)
	if phase == "pick_field" and row:
		picked = _configuration_field_key_from_text(text, {"protocol": _row_value(row, "protocol")}) or change_field
		if picked:
			return _ask_configuration_edit_value(row, picked)
		names = [label for key, label in CONFIGURATION_EDIT_FIELDS if not (key == "mdn_https_port" and _row_value(row, "mdn_mode") != "Asynchronous")]
		return _reply(
			"Which field should I change?\n\n" + "\n".join(f"- {name}" for name in names) + "\n\nNothing has been saved.",
			kind="guide",
			links=[_configuration_link(row)],
			guide={"options": names, "actions": _guide_actions(cancel=True)},
		)
	if phase in {"ask", "check"} and row and field:
		return _propose_configuration_edit(row, field, text)
	if phase == "review" and row and field:
		return _show_configuration_edit_review(row, field, guide.get("proposal") or "")
	return _begin_configuration_edit(text, {})


PARTNERSHIP_STATUSES = ("Draft", "Active", "Inactive")
PARTNERSHIP_MDN_MODES = ("Synchronous", "Asynchronous")


def _partner_choice_label(row) -> str:
	label = (row.partner_name or row.name or "").strip()
	names = [item.partner_name for item in _partner_rows() if (item.partner_name or "") == (row.partner_name or "")]
	if len(names) > 1 and row.as2_id:
		return f"{label} ({row.as2_id})"
	return label


def _partner_choices(exclude: str | None = None) -> list[tuple[str, str]]:
	choices = []
	for row in _partner_rows():
		if exclude and row.name == exclude:
			continue
		label = _partner_choice_label(row)
		if row.name and label:
			choices.append((label, row.name))
	return choices


def _certificate_choices() -> list[tuple[str, str]]:
	choices = []
	for row in get_certificates():
		label = (row.certificate_name or row.name or "").strip()
		if row.name and label:
			choices.append((label, row.name))
	return choices


def _partner_record(name: str):
	if not name or not frappe.db.exists("AS2 Partner", name):
		return None
	return frappe.db.get_value("AS2 Partner", name, PARTNER_FIELDS, as_dict=True)


def _exact_partner(text: str, exclude: str | None = None):
	needle = (text or "").strip().lower()
	if not needle:
		return None
	hits = []
	for row in _partner_rows():
		if exclude and row.name == exclude:
			continue
		labels = {
			(row.name or "").strip().lower(),
			(row.partner_name or "").strip().lower(),
			(row.as2_id or "").strip().lower(),
			_partner_choice_label(row).strip().lower(),
		}
		if needle in labels:
			hits.append(row)
	if len(hits) == 1:
		return hits[0]
	if len(hits) > 1:
		return hits
	kind = _normalize_type(text)
	if kind:
		typed = [row for row in _partner_rows() if (row.partner_type or "") == kind and row.name != exclude]
		if len(typed) == 1:
			return typed[0]
		if len(typed) > 1:
			return typed
	return None


def _yes_no(value: str | None, default: str = "Yes") -> str:
	text = (value or "").strip().lower()
	if text in {"no", "n", "false", "0", "disabled", "off"}:
		return "No"
	if text in {"yes", "y", "true", "1", "enabled", "on"}:
		return "Yes"
	return default


def _partnership_alias(partner, certificate: str | None = None) -> str:
	if certificate and frappe.db.exists("AS2 Certificate", certificate):
		alias = frappe.db.get_value("AS2 Certificate", certificate, "x509_alias")
		if alias:
			return alias
	if partner and partner.certificate:
		alias = frappe.db.get_value("AS2 Certificate", partner.certificate, "x509_alias")
		if alias:
			return alias
	if partner and partner.partner_type:
		return str(partner.partner_type).lower()
	return ""


def _partnership_derived(slots: dict) -> dict:
	local = _partner_record(slots.get("local_partner") or "")
	remote = _partner_record(slots.get("remote_partner") or "")
	derived = {}
	if local:
		derived["local_partner_name"] = local.partner_name or ""
		derived["local_as2_id"] = local.as2_id or ""
		derived["local_x509_alias"] = _partnership_alias(local, slots.get("local_certificate"))
	if remote:
		derived["remote_partner_name"] = remote.partner_name or ""
		derived["remote_as2_id"] = remote.as2_id or ""
		derived["remote_url"] = remote.as2_url or ""
		derived["remote_x509_alias"] = _partnership_alias(remote, slots.get("remote_certificate"))
	if derived.get("local_partner_name") and derived.get("remote_partner_name"):
		derived["suggested_name"] = f"{derived['local_partner_name']}-to-{derived['remote_partner_name']}"
	return derived


def _partnership_guide_fields(slots: dict | None = None) -> list[dict]:
	slots = slots or {}
	fields = [
		{
			"key": "instance",
			"label": "OpenAS2 Instance",
			"kind": "select",
			"options": [label for label, _name in _instance_choices()],
			"suggest": _instance_choices()[0][0] if len(_instance_choices()) == 1 else "",
		},
		{
			"key": "local_partner",
			"label": "Local Partner",
			"kind": "select",
			"options": [label for label, _name in _partner_choices()],
		},
		{
			"key": "remote_partner",
			"label": "Remote Partner",
			"kind": "select",
			"options": [label for label, _name in _partner_choices(slots.get("local_partner"))],
		},
	]
	if _certificate_choices():
		local = _partner_record(slots.get("local_partner") or "")
		remote = _partner_record(slots.get("remote_partner") or "")
		local_suggest = ""
		remote_suggest = ""
		known = {label for label, _name in _certificate_choices()}
		if local and local.certificate:
			local_suggest = frappe.db.get_value("AS2 Certificate", local.certificate, "certificate_name") or ""
			if local_suggest not in known:
				local_suggest = ""
		if remote and remote.certificate:
			remote_suggest = frappe.db.get_value("AS2 Certificate", remote.certificate, "certificate_name") or ""
			if remote_suggest not in known:
				remote_suggest = ""
		fields.extend(
			[
				{
					"key": "local_certificate",
					"label": "Local Certificate",
					"kind": "select",
					"options": [label for label, _name in _certificate_choices()],
					"optional": True,
					"suggest": local_suggest,
				},
				{
					"key": "remote_certificate",
					"label": "Remote Certificate",
					"kind": "select",
					"options": [label for label, _name in _certificate_choices()],
					"optional": True,
					"suggest": remote_suggest,
				},
			]
		)
	suggest_name = _partnership_derived(slots).get("suggested_name") or ""
	fields.extend(
		[
			{"key": "partnership_name", "label": "Partnership Name", "kind": "text", "suggest": suggest_name},
			{
				"key": "status",
				"label": "Status",
				"kind": "select",
				"options": list(PARTNERSHIP_STATUSES),
				"suggest": "Draft",
			},
			{"key": "encryption_enabled", "label": "Encryption Enabled", "kind": "select", "options": ["Yes", "No"], "suggest": "Yes"},
			{"key": "signing_enabled", "label": "Signing Enabled", "kind": "select", "options": ["Yes", "No"], "suggest": "Yes"},
			{"key": "mdn_enabled", "label": "MDN Enabled", "kind": "select", "options": ["Yes", "No"], "suggest": "Yes"},
		]
	)
	if _yes_no(slots.get("mdn_enabled"), "Yes") == "Yes":
		remote = _partner_record(slots.get("remote_partner") or "")
		mode = remote.mdn_mode if remote and remote.mdn_mode in PARTNERSHIP_MDN_MODES else "Synchronous"
		fields.append(
			{
				"key": "mdn_mode",
				"label": "MDN Mode",
				"kind": "select",
				"options": list(PARTNERSHIP_MDN_MODES),
				"suggest": mode,
			}
		)
	return fields


def _partnership_field(key: str, slots: dict | None = None) -> dict:
	for field in _partnership_guide_fields(slots):
		if field["key"] == key:
			return field
	return _partnership_guide_fields(slots)[0]


def _partnership_slots_only(slots: dict) -> dict:
	allowed = {
		"instance",
		"local_partner",
		"remote_partner",
		"local_certificate",
		"remote_certificate",
		"partnership_name",
		"status",
		"encryption_enabled",
		"signing_enabled",
		"mdn_enabled",
		"mdn_mode",
	}
	kept = {}
	for key in allowed:
		value = (slots.get(key) or "").strip()
		if value and not _SECRET_TEXT.search(value):
			kept[key] = value
	return kept


def _guided_partnership_slots(text: str, context: dict | None = None) -> dict:
	context = context or {}
	slots: dict[str, str] = {}
	between = re.search(r"\bbetween\s+(.+?)\s+and\s+(.+?)$", text, flags=re.I)
	if between:
		local = _exact_partner(between.group(1).strip(" .\"'"))
		remote = _exact_partner(between.group(2).strip(" .\"'"))
		if local and not isinstance(local, list):
			slots["local_partner"] = local.name
		if remote and not isinstance(remote, list) and remote.name != slots.get("local_partner"):
			slots["remote_partner"] = remote.name
	ctx_partner = _context_partner(context)
	if ctx_partner and not slots.get("local_partner"):
		found = _exact_partner(ctx_partner)
		if found and not isinstance(found, list):
			slots["local_partner"] = found.name
	config = (context.get("configuration") or "").strip()
	if config:
		for label, docname in _instance_choices():
			if config.lower() in {label.lower(), docname.lower()}:
				slots["instance"] = docname
	return _partnership_slots_only(slots)


def _save_partnership_guide(slots: dict, field: str, phase: str, proposal: str = "", accepted=None) -> None:
	_cache_set(_pending_key(), None)
	_cache_set(
		_draft_key(),
		{
			"action": "create_partnership",
			"slots": _partnership_slots_only(slots),
			"guide": {
				"field": field,
				"phase": phase,
				"proposal": proposal or "",
				"accepted": list(accepted or []),
			},
		},
	)


def _partnership_conflict(slots: dict):
	name = (slots.get("partnership_name") or "").strip()
	if name:
		existing = frappe.db.exists("OpenAS2 Partnership", {"partnership_name": name})
		if existing:
			return existing, "name"
	instance = slots.get("instance")
	local = slots.get("local_partner")
	remote = slots.get("remote_partner")
	if instance and local and remote:
		existing = frappe.db.get_value(
			"OpenAS2 Partnership",
			{"instance": instance, "local_partner": local, "remote_partner": remote},
			"name",
		)
		if existing:
			return existing, "pair"
	return None, ""


def _display_partnership_value(key: str, value: str) -> str:
	if key == "instance":
		return _instance_label(value)
	if key in {"local_partner", "remote_partner"}:
		row = _partner_record(value)
		return _partner_choice_label(row) if row else value
	if key in {"local_certificate", "remote_certificate"}:
		label = frappe.db.get_value("AS2 Certificate", value, "certificate_name") if value else ""
		return label or value
	return value


def _accept_partnership_value(key: str, raw: str, slots: dict) -> tuple[str, str]:
	text = (raw or "").strip().strip("\"'")
	if _SECRET_TEXT.search(text):
		return "", "Private keys and passwords stay out of chat."
	field = _partnership_field(key, slots)
	if field.get("optional") and _normalize(text) in {"skip", "none", "no", "no certificate"}:
		return "", ""
	if key == "instance":
		folded = text.lower()
		for label, docname in _instance_choices():
			if folded in {label.lower(), docname.lower()}:
				return docname, ""
		if not _instance_choices():
			return "", "No OpenAS2 instance is stored yet. Create a configuration first. I did not create one."
		return "", "Choose an OpenAS2 instance: " + ", ".join(label for label, _name in _instance_choices()) + "."
	if key in {"local_partner", "remote_partner"}:
		exclude = slots.get("local_partner") if key == "remote_partner" else None
		found = _exact_partner(text, exclude)
		if isinstance(found, list):
			labels = ", ".join(_partner_choice_label(row) for row in found[:12])
			return "", f"More than one partner matches {text}. Choose one: {labels}."
		if not found:
			return "", f"I couldn't find a partner named {text}. I did not create one. Choose an existing partner, or say Create a partner first."
		if key == "remote_partner" and found.name == slots.get("local_partner"):
			return "", "Local Partner and Remote Partner must be different."
		return found.name, ""
	if key in {"local_certificate", "remote_certificate"}:
		folded = text.lower()
		for label, docname in _certificate_choices():
			if folded in {label.lower(), docname.lower()}:
				return docname, ""
		return "", "Choose a certificate, or say skip. I did not create one."
	if key == "status":
		value = _match_choice(text, PARTNERSHIP_STATUSES)
		if not value:
			return "", "Choose a status: Draft, Active, or Inactive."
		return value, ""
	if key in {"encryption_enabled", "signing_enabled", "mdn_enabled"}:
		if _normalize(text) not in {"yes", "no"}:
			return "", "Choose Yes or No."
		choice = "Yes" if _normalize(text) == "yes" else "No"
		remote = _partner_record(slots.get("remote_partner") or "")
		forced = {
			"encryption_enabled": bool(remote and remote.encryption_enabled),
			"signing_enabled": bool(remote and remote.signing_enabled),
			"mdn_enabled": bool(remote and remote.mdn_enabled),
		}
		if choice == "No" and forced.get(key):
			label = {"encryption_enabled": "encryption", "signing_enabled": "signing", "mdn_enabled": "MDN"}[key]
			return "", f"The remote partner has {label} enabled. Saving uses that setting. Change the remote partner to turn it off."
		return choice, ""
	if key == "mdn_mode":
		value = _match_choice(text, PARTNERSHIP_MDN_MODES)
		if not value:
			return "", "Choose an MDN mode: Synchronous or Asynchronous."
		remote = _partner_record(slots.get("remote_partner") or "")
		if remote and remote.mdn_enabled and remote.mdn_mode in PARTNERSHIP_MDN_MODES and value != remote.mdn_mode:
			return "", f"The remote partner uses {remote.mdn_mode} MDN. Saving uses that mode. Change the remote partner to use a different mode."
		return value, ""
	if key == "partnership_name":
		if len(text) < 2 or _normalize(text) in {"proceed", "edit", "cancel", "create", "yes", "no"}:
			return "", "What should the partnership name be?"
		return re.sub(r"\s+", " ", text), ""
	if key in {"local_as2_id", "remote_as2_id", "local_x509_alias", "remote_x509_alias", "remote_url"}:
		return "", "That value comes from the selected partner. Change the partner instead of typing a new identity."
	return "", "Choose one of the stored records."


def _ask_partnership_field(slots: dict, key: str, error: str = "", intro: bool = False, accepted=None) -> dict:
	field = _partnership_field(key, slots)
	kept = [item for item in (accepted or []) if item != key]
	_save_partnership_guide(slots, key, "ask", "", kept)
	prompts = {
		"instance": "Which OpenAS2 instance should own this partnership?",
		"local_partner": "Which partner is the local sender?",
		"remote_partner": "Which partner is the remote receiver?",
		"local_certificate": "Which local certificate should this partnership use?",
		"remote_certificate": "Which remote certificate should this partnership use?",
		"partnership_name": "What should the partnership name be?",
		"status": "What status should this partnership record have?",
		"encryption_enabled": "Should encryption be enabled?",
		"signing_enabled": "Should signing be enabled?",
		"mdn_enabled": "Should MDN be enabled?",
		"mdn_mode": "Which MDN mode should this partnership use?",
	}
	lead = prompts.get(key, "What value should I use?")
	if key == "instance" and intro:
		lead = "Let's create a partnership. " + lead
	lines = [error, ""] if error else []
	lines.append(lead)
	options = list(field.get("options") or [])
	if options:
		lines.extend(["", "Choose one:", *[f"- {option}" for option in options]])
	if field.get("optional"):
		lines.extend(["", "Say skip if you do not want to link a certificate."])
	if not options and key == "instance":
		lines.append("No OpenAS2 instance is stored yet. Create a configuration first. I did not create one.")
	return _reply("\n".join(lines), kind="guide", guide={"options": options, "actions": []})


def _show_partnership_check(
	slots: dict, key: str, value: str, intro: bool = False, accepted=None, source: str = "confirm"
) -> dict:
	field = _partnership_field(key, slots)
	kept = [item for item in (accepted or []) if item != key]
	_save_partnership_guide(slots, key, "check", value, kept)
	lines = ["Let's create a partnership.", ""] if intro else []
	lines.extend(_value_lines(field["label"], _display_partnership_value(key, value), source))
	return _reply("\n".join(lines), kind="guide", guide={"actions": _guide_actions(proceed=True, edit=True)})


def _partnership_review_lines(slots: dict) -> list[str]:
	derived = _partnership_derived(slots)
	lines = ["Review Partnership", ""]
	for field in _partnership_guide_fields(slots):
		value = slots.get(field["key"]) or ""
		if not value and field.get("optional"):
			shown = "not selected"
		else:
			shown = _display_partnership_value(field["key"], value)
		lines.append(f"{field['label']}: {shown}")
	lines.extend(
		[
			f"Local Partner Name: {derived.get('local_partner_name') or 'not stored'}",
			f"Local AS2 ID: {derived.get('local_as2_id') or 'not stored'}",
			f"Local X509 Alias: {derived.get('local_x509_alias') or 'not stored'}",
			f"Remote Partner Name: {derived.get('remote_partner_name') or 'not stored'}",
			f"Remote AS2 ID: {derived.get('remote_as2_id') or 'not stored'}",
			f"Remote X509 Alias: {derived.get('remote_x509_alias') or 'not stored'}",
			f"Remote AS2 URL: {derived.get('remote_url') or 'not stored'}",
			"",
			"This saves the partnership record only. partnerships.xml was not changed, and OpenAS2 was not updated.",
			"",
			"Everything looks correct?",
		]
	)
	return lines


def _show_partnership_review(slots: dict) -> dict:
	ready = _partnership_ready_error(slots)
	if ready:
		_save_partnership_guide(slots, "", "review", "", [item["key"] for item in _partnership_guide_fields(slots)])
		return _reply(ready + "\n\nSay Edit to change a field. Nothing was saved.")
	conflict, which = _partnership_conflict(slots)
	if conflict:
		return _partnership_duplicate_reply(slots, conflict, which)
	clean = _partnership_slots_only(slots)
	token = secrets.token_hex(16)
	_cache_set(
		_draft_key(),
		{
			"action": "create_partnership",
			"slots": clean,
			"guide": {
				"field": "",
				"phase": "review",
				"proposal": "",
				"accepted": [item["key"] for item in _partnership_guide_fields(clean)],
			},
		},
	)
	_cache_set(_pending_key(), {"token": token, "action": "create_partnership", "slots": clean})
	return _reply(
		"\n".join(_partnership_review_lines(clean)),
		kind="guide",
		guide={"actions": _guide_actions(create=token, edit=True, cancel=True, create_label="Create Partnership")},
	)


def _partnership_ready_error(slots: dict) -> str:
	instance = (slots.get("instance") or "").strip()
	if not instance or not frappe.db.exists("OpenAS2 Instance", instance):
		return "That OpenAS2 instance is not stored. I did not create a partnership."
	local = _partner_record(slots.get("local_partner") or "")
	remote = _partner_record(slots.get("remote_partner") or "")
	if not local or not remote:
		return "The local and remote partners must be stored partners. I did not create a partnership."
	if local.name == remote.name or (local.as2_id and local.as2_id == remote.as2_id):
		return "Local Partner and Remote Partner must be different. I did not create a partnership."
	for key in ("local_certificate", "remote_certificate"):
		if slots.get(key) and not frappe.db.exists("AS2 Certificate", slots[key]):
			return "That certificate is not stored. I did not create one."
	derived = _partnership_derived(slots)
	url = (derived.get("remote_url") or "").lower()
	if not url.startswith(("http://", "https://")):
		return "The remote partner has no http or https AS2 URL. I did not invent one."
	missing = [
		label
		for key, label in (
			("local_as2_id", "Local AS2 ID"),
			("remote_as2_id", "Remote AS2 ID"),
			("local_partner_name", "Local Partner Name"),
			("remote_partner_name", "Remote Partner Name"),
			("local_x509_alias", "Local X509 Alias"),
			("remote_x509_alias", "Remote X509 Alias"),
		)
		if not derived.get(key)
	]
	if missing:
		return "The selected partner is missing " + ", ".join(missing) + ". I did not invent a value."
	return ""


def _partnership_suggestion(key: str, slots: dict) -> tuple[str, str]:
	if key == "instance":
		choices = _instance_choices()
		if not choices:
			return "", ""
		return choices[0][1], "existing"
	if key == "local_partner":
		choices = _partner_choices()
		if not choices:
			return "", ""
		return choices[0][1], "existing"
	if key == "remote_partner":
		local = slots.get("local_partner")
		instance = slots.get("instance")
		for _label, docname in _partner_choices(local):
			if (
				instance
				and local
				and frappe.db.get_value(
					"OpenAS2 Partnership",
					{"instance": instance, "local_partner": local, "remote_partner": docname},
					"name",
				)
			):
				continue
			return docname, "existing"
		return "", ""
	if key in {"local_certificate", "remote_certificate"}:
		partner_key = "local_partner" if key == "local_certificate" else "remote_partner"
		partner = _partner_record(slots.get(partner_key) or "")
		known = {docname for _label, docname in _certificate_choices()}
		if partner and partner.certificate and (not known or partner.certificate in known):
			if frappe.db.exists("AS2 Certificate", partner.certificate):
				return partner.certificate, "existing"
		if len(known) == 1:
			return next(iter(known)), "existing"
		return "", ""
	if key == "partnership_name":
		base = _partnership_derived(slots).get("suggested_name") or "New Partnership"
		taken = {
			row.partnership_name or ""
			for row in frappe.get_all("OpenAS2 Partnership", fields=["partnership_name"], limit_page_length=300)
		}
		return _next_available(base, taken), "suggested"
	if key == "status":
		return "Draft", "suggested"
	if key in {"encryption_enabled", "signing_enabled", "mdn_enabled"}:
		return "Yes", "suggested"
	if key == "mdn_mode":
		remote = _partner_record(slots.get("remote_partner") or "")
		if remote and remote.mdn_mode in PARTNERSHIP_MDN_MODES:
			return remote.mdn_mode, "existing"
		return "Synchronous", "suggested"
	return "", ""


def _partnership_duplicate_reply(slots: dict, existing: str, which: str) -> dict:
	row = frappe.db.get_value("OpenAS2 Partnership", existing, PARTNERSHIP_FIELDS, as_dict=True) or {"name": existing}
	clean = _partnership_slots_only(slots)
	link = _partnership_link(row, row.get("local_partner"))
	if which == "pair":
		text = (
			f"{row.get('partnership_name') or existing} already connects these partners on this instance. "
			"I did not create another partnership."
		)
		clean.pop("remote_partner", None)
		field = "remote_partner"
	else:
		text = f"{row.get('partnership_name') or existing} is already a partnership. I did not create another one."
		clean.pop("partnership_name", None)
		field = "partnership_name"
	accepted = [item["key"] for item in _partnership_guide_fields(clean) if item["key"] != field]
	value, source = _partnership_suggestion(field, clean)
	if not value:
		_save_partnership_guide(clean, field, "ask", "", accepted)
		ask = _ask_partnership_field(clean, field, error=text, accepted=accepted)
		if link:
			ask["links"] = [link]
		return ask
	shown = _show_partnership_check(clean, field, value, accepted=accepted, source=source)
	shown["reply"] = text + "\n\n" + shown["reply"]
	if link:
		shown["links"] = [link]
	return shown


def _partnership_guide_next(slots: dict, accepted=None, intro: bool = False) -> dict:
	done = set(accepted or [])
	for field in _partnership_guide_fields(slots):
		key = field["key"]
		if key in done:
			continue
		if slots.get(key):
			return _show_partnership_check(slots, key, slots[key], intro=intro, accepted=accepted, source="confirm")
		value, source = _partnership_suggestion(key, slots)
		if not value and field.get("suggest"):
			value, source = field["suggest"], "suggested" if key not in {"instance", "local_partner", "remote_partner", "local_certificate", "remote_certificate"} else "existing"
		if value:
			return _show_partnership_check(slots, key, value, intro=intro, accepted=accepted, source=source)
		return _ask_partnership_field(slots, key, intro=intro, accepted=accepted)
	return _show_partnership_review(slots)


def _store_partnership_value(slots: dict, key: str, value: str, accepted: list) -> tuple[dict, list]:
	previous = _partnership_derived(slots)
	clean = _partnership_slots_only(slots)
	accepted = list(accepted)
	if value:
		clean[key] = value
	else:
		clean.pop(key, None)
	if key == "local_partner":
		if clean.get("remote_partner") == value:
			clean.pop("remote_partner", None)
			accepted = [item for item in accepted if item != "remote_partner"]
		clean.pop("local_certificate", None)
		accepted = [item for item in accepted if item != "local_certificate"]
	if key == "remote_partner":
		clean.pop("remote_certificate", None)
		accepted = [item for item in accepted if item != "remote_certificate"]
		if clean.get("partnership_name") and clean.get("partnership_name") == previous.get("suggested_name"):
			clean.pop("partnership_name", None)
			accepted = [item for item in accepted if item != "partnership_name"]
	if key == "mdn_enabled" and value == "No":
		clean.pop("mdn_mode", None)
		accepted = [item for item in accepted if item != "mdn_mode"]
	if key not in accepted:
		accepted.append(key)
	return clean, accepted


def _accept_partnership_proposal(slots: dict, guide: dict) -> dict:
	key = guide.get("field") or ""
	proposal = guide.get("proposal") or slots.get(key) or ""
	accepted = list(guide.get("accepted") or [])
	if not key or not proposal:
		return _partnership_guide_next(slots, accepted)
	value, error = _accept_partnership_value(key, proposal, slots)
	if error:
		return _ask_partnership_field(slots, key, error=error, accepted=accepted)
	if key == "partnership_name":
		clean, accepted = _store_partnership_value(slots, key, value, accepted)
		conflict, which = _partnership_conflict(clean)
		if conflict and which == "name":
			return _partnership_duplicate_reply(clean, conflict, which)
		return _partnership_guide_next(clean, accepted)
	clean, accepted = _store_partnership_value(slots, key, value, accepted)
	return _partnership_guide_next(clean, accepted)


def _partnership_field_key_from_text(text: str, slots: dict) -> str:
	low = _normalize(text)
	for field in _partnership_guide_fields(slots):
		if low == _normalize(field["label"]):
			return field["key"]
	if re.search(r"remote certificate", low):
		return "remote_certificate"
	if re.search(r"local certificate|\bcertificate\b", low):
		return "local_certificate"
	if re.search(r"remote partner", low):
		return "remote_partner"
	if re.search(r"local partner", low):
		return "local_partner"
	if re.search(r"\binstance\b", low):
		return "instance"
	if re.search(r"partnership name|\bname\b", low):
		return "partnership_name"
	if re.search(r"encryption", low):
		return "encryption_enabled"
	if re.search(r"signing", low):
		return "signing_enabled"
	if re.search(r"mdn mode|\bmdn\b", low):
		return "mdn_mode" if "mode" in low or slots.get("mdn_enabled") == "Yes" else "mdn_enabled"
	if re.search(r"\bstatus\b", low):
		return "status"
	return ""


def _explicit_partnership_change(text: str, guide: dict, slots: dict) -> tuple[str, str] | None:
	patterns = (
		(r"(?:change|set|update|edit)\s+(?:the\s+)?remote\s+partner\s+(?:to\s+)?(.+)$", "remote_partner"),
		(r"(?:change|set|update|edit)\s+(?:the\s+)?local\s+partner\s+(?:to\s+)?(.+)$", "local_partner"),
		(r"(?:change|set|update|edit)\s+(?:the\s+)?remote\s+certificate\s+(?:to\s+)?(.+)$", "remote_certificate"),
		(r"(?:change|set|update|edit)\s+(?:the\s+)?local\s+certificate\s+(?:to\s+)?(.+)$", "local_certificate"),
		(r"(?:change|set|update|edit)\s+(?:the\s+)?partnership\s+name\s+(?:to\s+)?(.+)$", "partnership_name"),
		(r"(?:change|set|update|edit)\s+(?:the\s+)?status\s+(?:to\s+)?(.+)$", "status"),
		(r"(?:change|set|update|edit)\s+(?:the\s+)?encryption\s+(?:to\s+)?(.+)$", "encryption_enabled"),
		(r"(?:change|set|update|edit)\s+(?:the\s+)?signing\s+(?:to\s+)?(.+)$", "signing_enabled"),
		(r"(?:change|set|update|edit)\s+(?:the\s+)?mdn(?:\s*mode)?\s+(?:to\s+)?(.+)$", "mdn_mode"),
		(r"(?:change|set|update|edit)\s+(?:the\s+)?instance\s+(?:to\s+)?(.+)$", "instance"),
		(r"(?:change|set)\s+that\s+to\s+(.+)$", ""),
	)
	for pattern, key in patterns:
		match = re.search(pattern, text, flags=re.I)
		if not match:
			continue
		value = match.group(1).strip()
		if not key:
			key = guide.get("field") or "remote_partner"
		if key == "mdn_mode" and _normalize(value) in {"yes", "no"}:
			key = "mdn_enabled"
		return key, value
	if re.search(r"\b(local|remote)\s+as2\s*id\b|\bx509\b|\bremote url\b", text, flags=re.I):
		return "identity", ""
	return None


def _partnership_guide_turn(text: str, normalized: str) -> dict:
	draft = _cache_get(_draft_key())
	slots = dict(draft.get("slots") or {})
	guide = dict(draft.get("guide") or {})
	phase = guide.get("phase") or "ask"
	field = guide.get("field") or "instance"
	accepted = list(guide.get("accepted") or [])
	low = normalized
	if _classify(text) == "create_partnership":
		return _partnership_guide_next(slots, accepted, intro=not accepted)
	if low in {"cancel", "stop"}:
		_cache_set(_pending_key(), None)
		_cache_set(_draft_key(), None)
		return _reply("Cancelled. Nothing was changed.")
	if phase == "review" and low in {"create it", "create partnership", "create the partnership"}:
		pending = _cache_get(_pending_key())
		return confirm_assistant_action((pending or {}).get("token"))
	changed = _explicit_partnership_change(text, guide, slots)
	if changed:
		key, raw = changed
		if key == "identity":
			return _reply("That identity comes from the selected partner. Change the local or remote partner instead.")
		value, error = _accept_partnership_value(key, raw, slots)
		if error:
			return _ask_partnership_field(slots, key, error=error, accepted=accepted)
		clean, accepted = _store_partnership_value(slots, key, value, accepted)
		if key == "partnership_name":
			conflict, which = _partnership_conflict(clean)
			if conflict and which == "name":
				return _partnership_duplicate_reply(clean, conflict, which)
		return _partnership_guide_next(clean, accepted)
	if low in {"proceed", "continue", "next"} or (phase == "check" and low in {"yes", "ok", "okay", "correct"}):
		return _accept_partnership_proposal(slots, guide)
	if re.search(r"\b(?:edit|change)\b.+\b(partner|certificate|instance|name|status|encryption|signing|mdn)\b", low):
		target = _partnership_field_key_from_text(text, slots) or field
		return _ask_partnership_field(slots, target, accepted=accepted)
	if low in {"edit", "change", "change it", "edit that"}:
		if phase == "review":
			names = [item["label"] for item in _partnership_guide_fields(slots)]
			_save_partnership_guide(slots, "", "pick", "", accepted)
			return _reply(
				"Which field should I change?\n\n" + "\n".join(f"- {name}" for name in names),
				kind="guide",
				guide={"options": names, "actions": []},
			)
		return _ask_partnership_field(slots, field or "instance", accepted=accepted)
	picked = _partnership_field_key_from_text(text, slots) if phase == "pick" else ""
	if picked and phase == "pick":
		return _ask_partnership_field(slots, picked, accepted=accepted)
	if phase in {"ask", "check"}:
		value, error = _accept_partnership_value(field, text, slots)
		optional_skip = field and not value and not error and _partnership_field(field, slots).get("optional")
		if error:
			return _ask_partnership_field(slots, field, error=error, accepted=accepted)
		if optional_skip:
			clean, accepted = _store_partnership_value(slots, field, "", accepted)
			return _partnership_guide_next(clean, accepted)
		return _show_partnership_check(slots, field, value, accepted=accepted)
	return _show_partnership_review(slots)


def _begin_partnership_guide(text: str, context: dict | None = None) -> dict:
	slots = _guided_partnership_slots(text, context or {})
	draft = _cache_get(_draft_key())
	if draft.get("action") == "create_partnership" and draft.get("guide") and draft.get("slots"):
		merged = dict(draft.get("slots") or {})
		merged.update(slots)
		slots = _partnership_slots_only(merged)
	return _partnership_guide_next(slots, [], intro=True)


def _prepare_write(action: str, slots: dict, context: dict) -> dict:
	slots = dict(slots)
	if action == "create_partnership":
		local_text = slots.get("local_partner") or _context_partner(context)
		local = _find_partner(local_text)
		remote = _find_partner(slots.get("remote_partner"))
		if local_text and not local:
			return _reply(f"No stored partner matches \"{local_text}\".")
		if slots.get("remote_partner") and not remote:
			return _reply(f"No stored partner matches \"{slots.get('remote_partner')}\".")
		if local:
			slots["local_partner"] = local.name
		if remote:
			slots["remote_partner"] = remote.name
		instance = slots.get("instance") or context.get("configuration") or _one_instance_name() or ""
		if instance and not _find_configuration(instance):
			# instance may already be a document name
			if frappe.db.exists("OpenAS2 Instance", instance):
				from openas2_manager.access import assert_instance_access

				assert_instance_access(instance)
				slots["instance"] = instance
			else:
				return _reply(f"No stored configuration matches \"{instance}\".")
		elif instance:
			found = _find_configuration(instance)
			slots["instance"] = found.name if found else instance
	missing = _missing(action, slots, context)
	_cache_set(_draft_key(), {"action": action, "slots": slots})
	if missing:
		return _reply(
			"Sure. I need the following information:\n- " + "\n- ".join(missing) + "\n\nPlease provide the missing information."
		)
	return _stage_confirm(action, slots)


def _friendly_error(exc: Exception, action: str) -> str:
	message = str(exc).strip() or exc.__class__.__name__
	titles = {
		"create_partner": "Partner creation failed.",
		"update_partner": "Partner update failed.",
		"create_partnership": "Partnership creation failed.",
		"update_partnership": "Partnership update failed.",
		"create_certificate": "Certificate creation failed.",
		"update_certificate": "Certificate update failed.",
		"create_configuration": "Configuration creation failed.",
		"update_configuration": "Configuration update failed.",
	}
	return f"{titles.get(action, 'The action failed.')}\n\nReason:\n{message}"


def _execute(action: str, slots: dict) -> dict:
	try:
		if action == "create_partner":
			if not frappe.has_permission("AS2 Partner", "create"):
				frappe.throw(frappe._("Not permitted to create AS2 Partner."), frappe.PermissionError)
			doc = frappe.get_doc(
				{
					"doctype": "AS2 Partner",
					"partner_name": slots.get("partner_name"),
					"partner_type": _normalize_type(slots.get("partner_type")),
					"as2_id": slots.get("as2_id"),
					"as2_url": slots.get("as2_url"),
					"status": slots.get("status") if slots.get("status") in ("Active", "Inactive") else "Active",
				}
			)
			conflict, _which = _partner_conflict(
				{
					"partner_name": doc.partner_name,
					"as2_id": doc.as2_id,
				}
			)
			if conflict:
				existing_id = (getattr(conflict, "as2_id", None) or "").lower()
				existing_name = (getattr(conflict, "name", None) or "").lower()
				which = (
					"as2_id"
					if (doc.as2_id or "").lower() in {existing_id, existing_name}
					else "partner_name"
				)
				return _partner_duplicate_reply(
					{
						"partner_name": doc.partner_name,
						"partner_type": doc.partner_type,
						"as2_id": doc.as2_id,
						"as2_url": doc.as2_url,
						"status": doc.status,
					},
					conflict,
					which,
					[item["key"] for item in PARTNER_GUIDE_FIELDS if item["key"] != which],
				)
			doc.insert()
			frappe.db.commit()
			return _reply("Partner created successfully.", links=[_partner_link(doc.as_dict())])
		if action == "update_partner":
			target = (slots.get("name") or "").strip()
			found = _partner_edit_record(target) if target else None
			if not found:
				matches = _search_partners(slots.get("partner_name") or target)
				found = matches[0] if len(matches) == 1 else None
			if not found:
				return _reply("That partner is not available. I did not create one.")
			if not frappe.has_permission("AS2 Partner", "write", found.name):
				frappe.throw(frappe._("Not permitted to update this partner."), frappe.PermissionError)
			doc = frappe.get_doc("AS2 Partner", found.name)
			original = {key: _row_value(doc, key) for key in ("partner_name", "partner_type", "as2_id", "as2_url", "status")}
			if slots.get("as2_url") and slots["as2_url"] != original["as2_url"]:
				doc.as2_url = slots["as2_url"]
			if slots.get("partner_type"):
				kind = _normalize_type(slots["partner_type"])
				if kind and kind != original["partner_type"]:
					doc.partner_type = kind
			if slots.get("status") in ("Active", "Inactive") and slots["status"] != original["status"]:
				doc.status = slots["status"]
			if slots.get("partner_name") and slots["partner_name"] != original["partner_name"]:
				conflict, _which = _partner_conflict({"partner_name": slots["partner_name"]}, "partner_name")
				if conflict and _row_value(conflict, "name") != doc.name:
					return _reply(
						f"{_row_value(conflict, 'partner_name')} already uses that partner name. I did not change {doc.partner_name}.",
						links=[_partner_link(conflict)],
					)
				doc.partner_name = slots["partner_name"]
			if slots.get("as2_id") and slots["as2_id"] != original["as2_id"]:
				conflict, _which = _partner_conflict({"as2_id": slots["as2_id"]}, "as2_id")
				if conflict and _row_value(conflict, "name") != doc.name:
					return _reply(
						f"{_row_value(conflict, 'partner_name') or _row_value(conflict, 'as2_id')} already uses AS2 ID {slots['as2_id']}. I did not change {doc.partner_name}.",
						links=[_partner_link(conflict)],
					)
				doc.as2_id = slots["as2_id"]
			changed = any(_row_value(doc, key) != original[key] for key in original)
			if not changed:
				return _reply(f"Nothing changed for {doc.partner_name}. The partner was not saved.")
			doc.save()
			frappe.db.commit()
			return _reply(f"Partner {doc.partner_name} was updated.", links=[_partner_link(doc.as_dict())])
		if action == "create_partnership":
			from openas2_manager.access import assert_instance_access

			ready = _partnership_ready_error(slots)
			if ready:
				return _reply(ready)
			assert_instance_access(slots.get("instance") or "")
			if not frappe.has_permission("OpenAS2 Partnership", "create"):
				frappe.throw(frappe._("Not permitted to create a partnership."), frappe.PermissionError)
			conflict, which = _partnership_conflict(slots)
			if conflict:
				return _partnership_duplicate_reply(slots, conflict, which)
			derived = _partnership_derived(slots)
			payload = {
				"doctype": "OpenAS2 Partnership",
				"partnership_name": slots.get("partnership_name"),
				"instance": slots.get("instance"),
				"status": slots.get("status") if slots.get("status") in PARTNERSHIP_STATUSES else "Draft",
				"local_partner": slots.get("local_partner"),
				"remote_partner": slots.get("remote_partner"),
				"local_partner_name": derived.get("local_partner_name"),
				"remote_partner_name": derived.get("remote_partner_name"),
				"local_as2_id": derived.get("local_as2_id"),
				"remote_as2_id": derived.get("remote_as2_id"),
				"local_x509_alias": derived.get("local_x509_alias"),
				"remote_x509_alias": derived.get("remote_x509_alias"),
				"remote_url": derived.get("remote_url"),
				"encryption_enabled": 1 if _yes_no(slots.get("encryption_enabled")) == "Yes" else 0,
				"signing_enabled": 1 if _yes_no(slots.get("signing_enabled")) == "Yes" else 0,
				"mdn_enabled": 1 if _yes_no(slots.get("mdn_enabled")) == "Yes" else 0,
			}
			if slots.get("local_certificate"):
				payload["local_certificate"] = slots["local_certificate"]
			if slots.get("remote_certificate"):
				payload["remote_certificate"] = slots["remote_certificate"]
			if payload["mdn_enabled"]:
				payload["mdn_mode"] = (
					slots.get("mdn_mode") if slots.get("mdn_mode") in PARTNERSHIP_MDN_MODES else "Synchronous"
				)
			doc = frappe.get_doc(payload)
			doc.insert()
			frappe.db.commit()
			return _reply(
				"Partnership created successfully. The record is saved. "
				"partnerships.xml was not changed, and OpenAS2 was not updated.",
				links=[_partnership_link(doc.as_dict(), doc.local_partner)],
			)
		if action == "create_certificate":
			if not frappe.has_permission("AS2 Certificate", "create"):
				frappe.throw(frappe._("Not permitted to create a certificate."), frappe.PermissionError)
			conflict = _certificate_conflict(slots, "certificate_name")
			if conflict:
				return _certificate_duplicate_reply(
					slots,
					conflict,
					[item["key"] for item in _certificate_guide_fields() if item["key"] != "certificate_name"],
				)
			purpose = slots.get("purpose") if slots.get("purpose") in CERTIFICATE_PURPOSES else "Own Key Pair"
			certificate_type = slots.get("certificate_type") if slots.get("certificate_type") in CERTIFICATE_TYPES else "Both"
			status = slots.get("status") if slots.get("status") in CERTIFICATE_STATUSES else "Draft"
			instance = slots.get("openas2_instance") or ""
			if instance and not frappe.db.exists("OpenAS2 Instance", instance):
				instance = ""
			doc = frappe.get_doc(
				{
					"doctype": "AS2 Certificate",
					"certificate_name": slots.get("certificate_name"),
					"purpose": purpose,
					"owner_type": _normalize_type(slots.get("owner_type")),
					"x509_alias": slots.get("x509_alias"),
					"common_name": slots.get("common_name"),
					"certificate_type": certificate_type,
					"status": status,
					"openas2_instance": instance or None,
				}
			)
			doc.insert()
			frappe.db.commit()
			return _reply("Certificate created successfully.", links=[_certificate_link(doc.as_dict())])
		if action == "create_configuration":
			if not frappe.has_permission("OpenAS2 Instance", "create"):
				frappe.throw(frappe._("Not permitted to create a configuration."), frappe.PermissionError)
			conflict, which = _configuration_conflict(slots)
			if conflict:
				return _configuration_duplicate_reply(
					slots,
					conflict,
					which,
					[item["key"] for item in _configuration_guide_fields(slots) if item["key"] != which],
				)
			protocol = slots.get("protocol") if slots.get("protocol") in CONFIG_PROTOCOLS else "HTTPS"
			https = protocol == "HTTPS"
			mdn_mode = slots.get("mdn_mode") if slots.get("mdn_mode") in CONFIG_MDN_MODES else "Synchronous"
			async_mdn = mdn_mode == "Asynchronous"
			doc = frappe.get_doc(
				{
					"doctype": "OpenAS2 Instance",
					"instance_name": slots.get("instance_name"),
					"instance_type": _normalize_type(slots.get("instance_type")),
					"as2_id": slots.get("as2_id"),
					"host": slots.get("host"),
					"status": slots.get("status") if slots.get("status") in CONFIG_STATUSES else "Active",
					"protocol": protocol,
					"http_enabled": 0 if https else 1,
					"https_enabled": 1 if https else 0,
					"http_port": None if https else int(slots.get("http_port") or 0),
					"https_port": int(slots.get("https_port") or 0) if https else None,
					"mdn_mode": mdn_mode,
					"mdn_enabled": 1,
					"mdn_http_enabled": 0,
					"mdn_https_enabled": 1 if async_mdn else 0,
					"mdn_https_port": int(slots.get("mdn_https_port") or 0) if async_mdn else None,
					"lifecycle_status": "Unknown",
					"connection_status": "Unknown",
					"provision_source": "External",
					"control_mode": "none",
				}
			)
			doc.insert()
			frappe.db.commit()
			return _reply(
				"Configuration created successfully. The record is saved. OpenAS2 was not started.",
				links=[_configuration_link(doc.as_dict())],
			)
		if action == "update_configuration":
			from openas2_manager.access import assert_instance_access

			target = (slots.get("name") or "").strip()
			found = _configuration_edit_record(target) if target else None
			if not found:
				matches = _search_configurations(slots.get("instance_name") or target)
				found = matches[0] if len(matches) == 1 else None
			if not found:
				return _reply("That configuration is not available. I did not create one.")
			assert_instance_access(found.name)
			if not frappe.has_permission("OpenAS2 Instance", "write", found.name):
				frappe.throw(frappe._("Not permitted to update this configuration."), frappe.PermissionError)
			doc = frappe.get_doc("OpenAS2 Instance", found.name)
			original = {
				key: _row_value(doc, key)
				for key, _label in CONFIGURATION_EDIT_FIELDS
			}
			original["http_enabled"] = _row_value(doc, "http_enabled")
			original["https_enabled"] = _row_value(doc, "https_enabled")
			if slots.get("instance_name") and slots["instance_name"] != original["instance_name"]:
				conflict = _configuration_edit_conflict(doc, "instance_name", slots["instance_name"])
				if conflict:
					label = _row_value(conflict, "instance_name") or _row_value(conflict, "name")
					return _reply(
						f"{label} already uses that configuration name. I did not change {doc.instance_name}.",
						links=[_configuration_link(conflict)],
					)
				doc.instance_name = slots["instance_name"]
			if slots.get("instance_type"):
				kind = _normalize_type(slots["instance_type"])
				if kind and kind != original["instance_type"]:
					doc.instance_type = kind
			if slots.get("as2_id") and slots["as2_id"] != original["as2_id"]:
				conflict = _configuration_edit_conflict(doc, "as2_id", slots["as2_id"])
				if conflict:
					label = _row_value(conflict, "instance_name") or _row_value(conflict, "as2_id")
					return _reply(
						f"{label} already uses AS2 ID {slots['as2_id']}. I did not change {doc.instance_name}.",
						links=[_configuration_link(conflict)],
					)
				doc.as2_id = slots["as2_id"]
			if slots.get("host") and slots["host"] != original["host"]:
				doc.host = slots["host"]
			if slots.get("status") in CONFIG_STATUSES and slots["status"] != original["status"]:
				doc.status = slots["status"]
			if slots.get("protocol") in CONFIG_PROTOCOLS and slots["protocol"] != original["protocol"]:
				doc.protocol = slots["protocol"]
				if slots["protocol"] == "HTTPS":
					doc.https_enabled = 1
					doc.http_enabled = 0
				else:
					doc.http_enabled = 1
					doc.https_enabled = 0
			if slots.get("mdn_mode") in CONFIG_MDN_MODES and slots["mdn_mode"] != original["mdn_mode"]:
				doc.mdn_mode = slots["mdn_mode"]
			for key in ("http_port", "https_port", "mdn_https_port"):
				if slots.get(key) and slots[key] != original.get(key):
					doc.set(key, int(slots[key]))
			for key in ("http_port", "https_port", "mdn_http_port", "mdn_https_port", "health_port", "tracking_port"):
				if key in slots:
					continue
				try:
					blank = int(doc.get(key) or 0) == 0
				except (TypeError, ValueError):
					blank = False
				if blank:
					doc.set(key, None)
			changed = any(_row_value(doc, key) != original[key] for key in original)
			if not changed:
				return _reply(f"Nothing changed for {doc.instance_name}. The configuration was not saved.")
			doc.save()
			frappe.db.commit()
			return _reply(
				f"Configuration {doc.instance_name} was updated. OpenAS2 was not started.",
				links=[_configuration_link(doc.as_dict())],
			)
		if action == "update_partnership":
			from openas2_manager.access import assert_instance_access

			matches = [
				row
				for row in get_partnerships()
				if (slots.get("name") or "").strip().lower()
				in {
					(row.name or "").lower(),
					(row.partnership_name or "").lower(),
				}
			]
			if not matches:
				return _reply("That partnership is not available.")
			row = matches[0]
			assert_instance_access(row.instance)
			if not frappe.has_permission("OpenAS2 Partnership", "write", row.name):
				frappe.throw(frappe._("Not permitted to update this partnership."), frappe.PermissionError)
			doc = frappe.get_doc("OpenAS2 Partnership", row.name)
			changed = False
			if slots.get("status") in ("Draft", "Active", "Inactive"):
				doc.status = slots["status"]
				changed = True
			if slots.get("remote_url"):
				doc.remote_url = slots["remote_url"]
				changed = True
			if not changed:
				return _reply("Tell me the status or remote AS2 URL to change. Nothing was saved.")
			doc.save()
			frappe.db.commit()
			return _reply(f"Partnership {doc.partnership_name} was updated.")
		if action == "update_certificate":
			found = get_certificate(slots.get("name") or slots.get("certificate_name") or "")
			if not found:
				return _reply("That certificate is not available.")
			if not frappe.has_permission("AS2 Certificate", "write", found.name):
				frappe.throw(frappe._("Not permitted to update this certificate."), frappe.PermissionError)
			doc = frappe.get_doc("AS2 Certificate", found.name)
			changed = False
			if slots.get("status") in ("Draft", "Active", "Expired", "Revoked"):
				doc.status = slots["status"]
				changed = True
			if slots.get("common_name"):
				doc.common_name = slots["common_name"]
				changed = True
			if slots.get("x509_alias"):
				doc.x509_alias = slots["x509_alias"]
				changed = True
			if not changed:
				return _reply("Tell me the status, common name, or alias to change. Nothing was saved.")
			doc.save()
			frappe.db.commit()
			return _reply(f"Certificate {doc.certificate_name} was updated. Private key material was not changed.")
	except Exception as exc:
		frappe.db.rollback()
		return _reply(_friendly_error(exc, action), kind="error")
	return _reply("That action is not available.")


def _remember_edi(action: str, filters: dict, rows: list) -> None:
	_cache_set(
		_topic_key(),
		{
			"action": action,
			"filters": filters,
			"transaction_type": filters.get("transaction_type") or "",
			"limit": filters.get("limit") or 0,
			"failed": filters.get("status") == "Failed",
			"results": [
				{
					"name": row.get("name"),
					"file_name": row.get("file_name"),
					"status": row.get("status"),
					"transaction_type": row.get("transaction_type"),
					"reference_number": row.get("reference_number"),
				}
				for row in (rows or [])[:40]
			],
		},
	)


def _fetch_edi(filters: dict) -> dict:
	kwargs: dict = {}
	if filters.get("transaction_type"):
		kwargs["transaction_type"] = filters["transaction_type"]
	if filters.get("status"):
		kwargs["status"] = filters["status"]
	if filters.get("date_from"):
		kwargs["date_from"] = str(filters["date_from"])
	if filters.get("date_to"):
		kwargs["date_to"] = str(filters["date_to"])
	need_scan = True
	kwargs["limit"] = min(int(filters.get("limit") or 2000), 2000) if filters.get("count_only") else 2000
	if kwargs.get("status") == "Failed":
		result = get_failed_edi_transactions(**{k: v for k, v in kwargs.items() if k != "status"})
	else:
		result = get_edi_transactions(**kwargs)
	rows = list(result.get("rows") or [])
	party_a = (filters.get("party_a") or "").lower().strip()
	party_b = (filters.get("party_b") or "").lower().strip()
	partner = (filters.get("partner") or "").lower().strip()
	mdn = filters.get("mdn_status")
	matched = []
	for row in rows:
		sent = (row.get("sent_from") or "").lower()
		recv = (row.get("received_by") or "").lower()
		pname = (row.get("partner_name") or "").lower()
		if party_a and party_b and not (party_a in sent + " " + recv and party_b in sent + " " + recv):
			continue
		if partner and partner not in sent and partner not in recv and partner not in pname:
			continue
		if mdn and (row.get("mdn_status") or "") != mdn:
			continue
		matched.append(row)
	limit = int(filters.get("limit") or 40)
	return {"rows": matched[:limit], "count": len(matched), "method": "get_failed_edi_transactions" if kwargs.get("status") == "Failed" else "get_edi_transactions"}


def _listed_followup(text: str) -> bool:
	low = _normalize(text)
	ordinal = (
		r"\d{1,2}(?:st|nd|rd|th)|first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth"
	)
	if re.search(rf"\b({ordinal})\b", low) and re.search(
		r"\b(one|item|result|transaction|record|file|row|analyze|analyse|open|explain|why)\b",
		low,
	):
		return True
	if re.fullmatch(rf"(?:the |that |this )?(?:{ordinal})(?: one)?", low):
		return True
	return bool(re.search(r"\b(last|final) one\b", low))


def _ordinal_index(text: str) -> int:
	"""Zero-based index. -1 means the last stored result."""
	low = _normalize(text)
	if re.search(r"\b(last|final) one\b", low):
		return -1
	match = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)\b", low)
	if match:
		return max(0, int(match.group(1)) - 1)
	words = (
		("first", 0),
		("second", 1),
		("third", 2),
		("fourth", 3),
		("fifth", 4),
		("sixth", 5),
		("seventh", 6),
		("eighth", 7),
		("ninth", 8),
		("tenth", 9),
	)
	for word, idx in words:
		if re.search(rf"\b{word}\b", low):
			return idx
	return 0


def _result_index(text: str, count: int) -> int | None:
	if count <= 0:
		return None
	idx = _ordinal_index(text)
	if idx < 0:
		return count - 1
	if idx >= count:
		return None
	return idx


def _resolve_edi_name(text: str, context: dict) -> str:
	name = (context.get("edi_document") or "").strip()
	if name and not _listed_followup(text):
		return name
	topic = _cache_get(_topic_key())
	results = topic.get("results") or []
	if results:
		idx = _result_index(text, len(results))
		if idx is None:
			return ""
		name = (results[idx] or {}).get("name") or ""
		if name:
			return name
	match = re.search(r"(LOAD\d+)", text, flags=re.I)
	if match:
		rows = _edi_by_reference(match.group(1))
		if rows:
			return rows[0].get("name") or ""
	if topic.get("filters"):
		rows = (_fetch_edi(topic.get("filters") or {}).get("rows") or [])
		idx = _result_index(text, len(rows))
		if idx is not None:
			return rows[idx].get("name") or ""
	return ""


def _is_filter_followup(text: str) -> bool:
	low = _normalize(text)
	return bool(
		re.fullmatch(r"(only |just )?(204|990|214|210|810|820)s?", low)
		or re.fullmatch(r"(show (me )?the )?last \d+", low)
		or low in ("failed", "successful", "success", "today", "yesterday", "pending", "pending mdn")
		or re.search(r"^(only|just)\b", low)
	)


def _merge_followup(text: str, action: str) -> str:
	topic = _cache_get(_topic_key())
	if not topic:
		return action
	if _is_filter_followup(text):
		return topic.get("action") or action
	return action


def _read_intent(action: str, text: str, context: dict) -> dict:
	low = _normalize(text)
	topic = _cache_get(_topic_key())
	if action == "general":
		answer = _general_answer(text)
		_log_ai({"intent": "general", "action": "none", "question": text})
		return _reply(answer)
	if action == "list_partners":
		rows = get_partners()
		_log_ai({"intent": action, "action": "get_partners", "count": len(rows), "question": text})
		if not rows:
			return _reply("I couldn't find any matching partners.")
		return _reply_list("Partners", rows, _fmt_partner, _partner_link)
	if action == "show_partner":
		named = ""
		for row in get_partners():
			label = (row.partner_name or "").strip()
			if label and label.lower() in low:
				named = label
				break
		name = named or _grab(r"(?:partner)\s+[\"']?(.+?)[\"']?$", text) or _context_partner(context)
		row = get_partner(name)
		_log_ai({"intent": "get_partner", "action": "get_partner", "partner": name, "question": text})
		if not row:
			return _reply("That partner is not available." if name else "Which partner should I open?")
		return _reply(_fmt_partner(row), links=[_partner_link(row)])
	if action == "list_partnerships":
		partner = _context_partner(context)
		match = re.search(r"for\s+[\"']?(.+?)[\"']?$", text, flags=re.I)
		if match:
			partner = match.group(1).strip()
		if not partner:
			for row in get_partners():
				label = (row.partner_name or "").strip()
				if label and label.lower() in low:
					partner = label
					break
		method = "get_partner_partnerships" if partner else "get_partnerships"
		rows = get_partnerships(partner or None)
		_log_ai({"intent": action, "action": method, "partner": partner, "count": len(rows), "question": text})
		if not rows:
			return _reply("I couldn't find any matching partnerships.")
		found = _find_partner(partner) if partner else None
		title = f"Partnerships for {found.partner_name if found else partner}" if partner else "Partnerships"
		partner_name = found.name if found else None
		return _reply_list(title, rows, _fmt_partnership, lambda row: _partnership_link(row, partner_name))
	if action == "list_certificates":
		if re.search(r"expir", low) and context.get("certificate"):
			row = get_certificate(context.get("certificate"))
			if not row and frappe.db.exists("AS2 Certificate", context.get("certificate")):
				row = frappe.db.get_value("AS2 Certificate", context.get("certificate"), CERTIFICATE_FIELDS, as_dict=True)
			_log_ai({"intent": "get_certificate", "action": "get_certificate", "name": context.get("certificate")})
			if not row:
				return _reply("That certificate is not available.")
			until = row.get("valid_until") or "not stored"
			return _reply(
				f"{row.get('certificate_name')} expires {until}. Status {row.get('status')}.",
				links=[_certificate_link(row)],
			)
		rows = get_certificates()
		_log_ai({"intent": action, "action": "get_certificates", "count": len(rows), "question": text})
		if not rows:
			return _reply("I couldn't find any matching certificates.")
		return _reply_list("Certificates", rows, _fmt_cert, _certificate_link)
	if action == "list_configurations":
		rows = get_configurations()
		_log_ai({"intent": action, "action": "get_configurations", "count": len(rows), "question": text})
		if not rows:
			return _reply("I couldn't find any matching configurations.")
		return _reply_list("Configurations", rows, _fmt_config, _configuration_link)
	if action == "activity":
		_log_ai({"intent": "summarize_monitoring", "action": "get_monitoring_data", "question": text})
		return _reply(_activity_text())
	if action in ("failed_today", "count_failed", "failed_all", "failed_type", "count_type", "list_type", "between_parties"):
		filters: dict = {}
		if topic.get("filters") and (_is_filter_followup(text) or _merge_followup(text, action) != action):
			filters.update(topic.get("filters") or {})
		code = _edi_code(low) or str(filters.get("transaction_type") or topic.get("transaction_type") or "")
		if code:
			filters["transaction_type"] = code
		if action in ("failed_today", "count_failed", "failed_all", "failed_type") or re.search(r"\bfail", low) or (
			_is_filter_followup(text) and topic.get("failed")
		):
			filters["status"] = "Failed"
		if re.search(r"\bsuccess", low):
			filters["status"] = "Success"
		if "yesterday" in low:
			day = add_days(_today(), -1)
			filters["date_from"] = str(day)
			filters["date_to"] = str(day)
		elif "today" in low or action == "failed_today":
			filters["date_from"] = str(_today())
		limit = _asked_limit(low) or int(filters.get("limit") or 0)
		if limit:
			filters["limit"] = limit
		if action in ("count_type", "count_failed", "failed_today") and not limit:
			filters["count_only"] = True
			filters["limit"] = 2000
		if action == "between_parties":
			slots = _extract_slots(text, "between")
			filters["party_a"] = slots.get("party_a") or filters.get("party_a")
			filters["party_b"] = slots.get("party_b") or filters.get("party_b")
		method_filters = dict(filters)
		fetched = _fetch_edi(method_filters)
		rows = fetched["rows"]
		_remember_edi(action, method_filters, rows if not filters.get("count_only") else fetched["rows"])
		_log_ai(
			{
				"intent": action,
				"action": fetched["method"],
				"filters": method_filters,
				"count": fetched["count"],
				"question": text,
			}
		)
		if not fetched["count"]:
			return _reply("I couldn't find any matching transactions.")
		if filters.get("count_only") or action in ("count_type", "count_failed") and not _asked_limit(low):
			label = " ".join(
				part
				for part in (
					"failed" if filters.get("status") == "Failed" else "",
					code or "",
				)
				if part
			).strip() or "matching"
			when = " today" if filters.get("date_from") == str(_today()) and not filters.get("date_to") else ""
			sample_rows = rows[:8]
			return _reply_list(
				f"I found {fetched['count']} stored {label} transaction(s){when}.",
				sample_rows,
				_fmt_edi,
				_edi_link,
			)
		shown = rows[: int(filters.get("limit") or 40)]
		title = f"I found {fetched['count']} matching transaction(s). Showing {len(shown)}:"
		return _reply_list(title, shown, _fmt_edi, _edi_link)
	if action == "recent_load":
		fetched = _fetch_edi({"transaction_type": "204", "limit": 1})
		row = (fetched.get("rows") or [None])[0]
		if not row:
			wider = _fetch_edi({"limit": 40})
			for candidate in wider.get("rows") or []:
				blob = " ".join(
					str(candidate.get(key) or "")
					for key in ("reference_number", "file_name", "tms_doc_name")
				)
				if re.search(r"load\d+", blob, flags=re.I):
					row = candidate
					break
		_log_ai({"intent": action, "action": "get_edi_transactions", "question": text})
		if not row:
			return _reply("I couldn't find a recent load.")
		blob = " ".join(str(row.get(key) or "") for key in ("reference_number", "file_name", "tms_doc_name"))
		match = re.search(r"(LOAD\d+)", blob, flags=re.I)
		if match:
			needle = match.group(1).upper()
			rows = _edi_by_reference(needle) or [row]
			_remember_edi(action, {"reference": needle}, _unique_reference_rows(rows))
			return _load_reply(needle, rows)
		_remember_edi(action, {"transaction_type": "204", "limit": 1}, [row])
		return _reply_list(f"Most recent load tender: {row.get('file_name') or row.get('name')}", [row], _fmt_edi, _edi_link)
	if action == "find_reference":
		match = re.search(r"(LOAD\d+)", text, flags=re.I)
		needle = (match.group(1) if match else text).upper()
		rows = _edi_by_reference(needle)
		_log_ai({"intent": action, "action": "get_edi_transactions", "reference": needle, "count": len(rows), "question": text})
		if not rows:
			return _reply(f"I couldn't find any stored transactions for {needle}.")
		shown = _unique_reference_rows(rows)
		_remember_edi(action, {"reference": needle}, shown)
		failed = [item for item in shown if item.get("status") == "Failed"]
		if _asks_failure(text) and failed:
			found = analyze_edi_record(failed[0].get("name"))
			return _reply(_analysis_text(found), kind="analysis", links=_analysis_links(found))
		return _load_reply(needle, shown)
	if action in ("analyze_current", "analyze_listed", "analyze_mdn"):
		name = _resolve_edi_name(text, context)
		_log_ai({"intent": action, "action": "analyze_edi_transaction", "name": name, "question": text})
		if not name:
			if action == "analyze_listed":
				results = (_cache_get(_topic_key()).get("results") or [])
				if results:
					return _reply(f"The last list has {len(results)} transactions. Ask for one of those.")
				return _reply("Show transactions first, or name a load such as LOAD062.")
			if action == "analyze_mdn":
				fetched = _fetch_edi({"mdn_status": "Pending", "limit": 20})
				if not fetched["count"]:
					return _reply("I couldn't find any transactions with a stored MDN status of Pending.")
				_remember_edi(action, {"mdn_status": "Pending"}, fetched["rows"])
				return _reply_list(
					"CONFIRMED: these stored transactions have MDN status Pending.",
					fetched["rows"],
					_fmt_edi,
					_edi_link,
				)
			return _reply("Open an EDI transaction first, or tell me the load or file name.")
		found = analyze_edi_record(name)
		if action == "analyze_mdn":
			summary = found.get("summary") or {}
			mdn = summary.get("mdn_status") or "not stored"
			return _reply(
				f"CONFIRMED: stored MDN status for {summary.get('file_name') or name} is {mdn}.\n\n"
				+ _analysis_text(found),
				kind="analysis",
				links=_analysis_links(found),
			)
		return _reply(_analysis_text(found), kind="analysis", links=_analysis_links(found))
	if action == "analyze_logs":
		date_from = str(_today()) if "today" in low else None
		_log_ai({"intent": action, "action": "get_logs", "filters": {"date_from": date_from}, "question": text})
		text_out, log_links = _log_analysis(date_from=date_from)
		return _reply(text_out, kind="analysis", links=log_links)
	for row in get_partners():
		label = (row.partner_name or "").strip()
		if label and label.lower() in low:
			rows = get_partnerships(label)
			_log_ai({"intent": "named_partner", "action": "get_partner_partnerships", "partner": label})
			links = [_partner_link(row)]
			links.extend(_links_from(rows, lambda item: _partnership_link(item, row.name)))
			return _reply(
				_fmt_partner(row) + "\n\nPartnerships",
				links=[item for item in links if item],
			)
	_log_ai({"intent": "unknown", "action": "none", "question": text})
	return _reply(
		"I did not match that to a stored partner, partnership, certificate, configuration, EDI file, or log. "
		"Ask about one of those, or name a load such as LOAD062."
	)


@frappe.whitelist()
def chat(message: str | None = None, context=None) -> dict:
	"""Answer one assistant turn from real OpenAS2 records."""
	_require_user()
	text = (message or "").strip()
	normalized = _normalize(text)
	ctx = _parse_context(context)
	if not text:
		return _reply("Ask about partners, partnerships, certificates, configurations, EDI, or logs.")
	low = normalized
	pending = _cache_get(_pending_key())
	if pending and low in ("cancel", "no", "stop"):
		_cache_set(_pending_key(), None)
		_cache_set(_draft_key(), None)
		return _reply("Cancelled. Nothing was changed.")
	if pending and low in ("yes", "confirm", "create", "update"):
		return confirm_assistant_action(pending.get("token"))
	draft = _cache_get(_draft_key())
	if draft.get("action") == "update_partner" and draft.get("guide"):
		action_now = _classify(normalized)
		if action_now in {"list_partners", "show_partner"} and not re.search(
			r"\b(show|list|all|find|what|which|who|how many|my)\b", normalized
		):
			action_now = ""
		if action_now in ("", "update_partner"):
			return _partner_edit_turn(text, normalized)
		_cache_set(_draft_key(), None)
		_cache_set(_pending_key(), None)
	elif _is_new_partner_edit(text):
		_cache_set(_draft_key(), None)
		_cache_set(_pending_key(), None)
		return _begin_partner_edit(text, ctx)
	if draft.get("action") == "update_configuration" and draft.get("guide"):
		action_now = _classify(normalized)
		if action_now == "list_configurations" and not re.search(
			r"\b(show|list|all|find|what|which|who|how many|my)\b", normalized
		):
			action_now = ""
		if action_now in ("", "update_configuration"):
			return _configuration_edit_turn(text, normalized)
		_cache_set(_draft_key(), None)
		_cache_set(_pending_key(), None)
	elif _is_new_configuration_edit(text):
		_cache_set(_draft_key(), None)
		_cache_set(_pending_key(), None)
		return _begin_configuration_edit(text, ctx)
	if draft.get("action") == "create_partner" and draft.get("guide"):
		action_now = _classify(normalized)
		if action_now in {"list_partners", "show_partner"} and not re.search(
			r"\b(show|list|all|find|what|which|who|how many|my)\b", normalized
		):
			action_now = ""
		if action_now in ("", "create_partner", "update_partner"):
			if action_now == "create_partner":
				extra = _guided_partner_slots(text)
				if extra:
					merged = dict(draft.get("slots") or {})
					merged.update(extra)
					guide = dict(draft.get("guide") or {})
					guide["accepted"] = [key for key in (guide.get("accepted") or []) if key not in extra]
					_cache_set(
						_draft_key(),
						{"action": "create_partner", "slots": _partner_slots_only(merged), "guide": guide},
					)
			return _partner_guide_turn(text, normalized)
		_cache_set(_draft_key(), None)
		_cache_set(_pending_key(), None)
	elif draft.get("action") == "create_certificate" and draft.get("guide"):
		action_now = _classify(normalized)
		if action_now == "list_certificates" and not re.search(
			r"\b(show|list|all|find|what|which|who|how many|my)\b", normalized
		):
			action_now = ""
		if action_now in ("", "create_certificate", "update_certificate"):
			if action_now == "create_certificate":
				extra = _guided_certificate_slots(text)
				if extra:
					merged = dict(draft.get("slots") or {})
					merged.update(extra)
					guide = dict(draft.get("guide") or {})
					guide["accepted"] = [key for key in (guide.get("accepted") or []) if key not in extra]
					_cache_set(
						_draft_key(),
						{"action": "create_certificate", "slots": _certificate_slots_only(merged), "guide": guide},
					)
			return _certificate_guide_turn(text, normalized)
		_cache_set(_draft_key(), None)
		_cache_set(_pending_key(), None)
	elif draft.get("action") == "create_configuration" and draft.get("guide"):
		action_now = _classify(normalized)
		if action_now == "list_configurations" and not re.search(
			r"\b(show|list|all|find|what|which|who|how many|my)\b", normalized
		):
			action_now = ""
		if action_now in ("", "create_configuration", "update_configuration"):
			if action_now == "create_configuration":
				extra = _guided_configuration_slots(text)
				if extra:
					merged = dict(draft.get("slots") or {})
					merged.update(extra)
					guide = dict(draft.get("guide") or {})
					guide["accepted"] = [key for key in (guide.get("accepted") or []) if key not in extra]
					_cache_set(
						_draft_key(),
						{
							"action": "create_configuration",
							"slots": _configuration_slots_only(merged),
							"guide": guide,
						},
					)
			return _configuration_guide_turn(text, normalized)
		_cache_set(_draft_key(), None)
		_cache_set(_pending_key(), None)
	elif draft.get("action") == "create_partnership" and draft.get("guide"):
		action_now = _classify(normalized)
		if action_now in {"list_partners", "show_partner", "list_certificates", "list_partnerships"} and not re.search(
			r"\b(show|list|all|find|what|which|who|how many|my)\b", normalized
		):
			action_now = ""
		if action_now in (
			"",
			"create_partnership",
			"update_partnership",
			"update_partner",
			"update_certificate",
			"update_configuration",
		):
			if action_now == "create_partnership":
				extra = _guided_partnership_slots(text, ctx)
				if extra:
					merged = dict(draft.get("slots") or {})
					merged.update(extra)
					guide = dict(draft.get("guide") or {})
					guide["accepted"] = [key for key in (guide.get("accepted") or []) if key not in extra]
					_cache_set(
						_draft_key(),
						{
							"action": "create_partnership",
							"slots": _partnership_slots_only(merged),
							"guide": guide,
						},
					)
			return _partnership_guide_turn(text, normalized)
		_cache_set(_draft_key(), None)
		_cache_set(_pending_key(), None)
	action = _classify(normalized)
	action = _merge_followup(normalized, action)
	_log_ai({"stage": "classified", "question": text, "intent": action, "context": {k: ctx.get(k) for k in ctx}})
	draft = _cache_get(_draft_key())
	if action:
		if action == "create_partner":
			_cache_set(_pending_key(), None)
			return _begin_partner_guide(text)
		if action == "create_certificate":
			_cache_set(_pending_key(), None)
			return _begin_certificate_guide(text)
		if action == "create_configuration":
			_cache_set(_pending_key(), None)
			return _begin_configuration_guide(text)
		if action == "create_partnership":
			_cache_set(_pending_key(), None)
			return _begin_partnership_guide(text, ctx)
		if action == "update_partner":
			_cache_set(_pending_key(), None)
			return _begin_partner_edit(text, ctx)
		if action == "update_configuration":
			_cache_set(_pending_key(), None)
			return _begin_configuration_edit(text, ctx)
		if action.startswith("create") or action.startswith("update"):
			_cache_set(_pending_key(), None)
			slots = _extract_slots(text, action)
			if action.startswith("update"):
				target = _grab(r"(?:partner|partnership|certificate|configuration|instance)\s+[\"']?(.+?)[\"']?(?=\s+(?:set|to|url|status)|$)", text)
				if target:
					slots["name"] = target
				elif _context_partner(ctx) and "partner" in action:
					slots["name"] = _context_partner(ctx)
			return _prepare_write(action, slots, ctx)
		_cache_set(_draft_key(), None)
		_cache_set(_pending_key(), None)
		return _read_intent(action, normalized, ctx)
	follow_up = (
		draft.get("action")
		and "?" not in text
		and not re.search(r"\b(show|list|why|what|who|analyze|explain|how many|find|tell me)\b", low)
		and len(text) <= 80
	)
	if follow_up:
		slots = dict(draft.get("slots") or {})
		slots.update(_extract_slots(text, draft["action"]))
		for key, value in _extract_slots("type " + text, draft["action"]).items():
			slots.setdefault(key, value)
		if re.fullmatch(r"https?://\S+", text, flags=re.I):
			slots["as2_url"] = text.rstrip(".,)")
		elif _normalize_type(text):
			kind = _normalize_type(text)
			slots.setdefault("partner_type", kind)
			slots.setdefault("instance_type", kind)
			slots.setdefault("owner_type", kind)
		elif draft["action"] == "create_partner" and not slots.get("partner_name") and " " in text:
			slots["partner_name"] = text
		elif draft["action"] == "create_partner" and slots.get("partner_name") and not slots.get("as2_id") and re.fullmatch(r"[A-Za-z0-9_\-]+", text):
			slots["as2_id"] = text
		return _prepare_write(draft["action"], slots, ctx)
	_cache_set(_draft_key(), None)
	return _read_intent("", normalized, ctx)


@frappe.whitelist()
def confirm_assistant_action(token: str | None = None) -> dict:
	"""Run the preview the user confirmed. Analysis is never a write."""
	_require_user()
	pending = _cache_get(_pending_key())
	if not pending or not token or token != pending.get("token"):
		return _reply("That confirmation expired. Ask again and review the preview.")
	action = pending.get("action") or ""
	slots = pending.get("slots") or {}
	_cache_set(_pending_key(), None)
	_cache_set(_draft_key(), None)
	result = _execute(action, slots)
	if result.get("kind") == "error" and action == "update_partner":
		key = next((item["key"] for item in PARTNER_GUIDE_FIELDS if item["key"] in slots), "")
		saved = _partner_edit_record(slots.get("name") or "")
		_cache_set(_pending_key(), pending)
		_cache_set(
			_draft_key(),
			{
				"action": "update_partner",
				"slots": slots,
				"guide": {
					"phase": "review",
					"field": key,
					"proposal": slots.get(key) or "",
					"current": _row_value(saved, key) if saved else "",
					"partner": slots.get("name") or "",
				},
			},
		)
	if result.get("kind") == "error" and action == "create_partner":
		_cache_set(_pending_key(), pending)
		_cache_set(
			_draft_key(),
			{
				"action": "create_partner",
				"slots": _partner_slots_only(slots),
				"guide": {
					"field": "",
					"phase": "review",
					"proposal": "",
					"accepted": [item["key"] for item in PARTNER_GUIDE_FIELDS],
				},
			},
		)
	if result.get("kind") == "error" and action == "create_certificate":
		_cache_set(_pending_key(), pending)
		_cache_set(
			_draft_key(),
			{
				"action": "create_certificate",
				"slots": _certificate_slots_only(slots),
				"guide": {
					"field": "",
					"phase": "review",
					"proposal": "",
					"accepted": [item["key"] for item in _certificate_guide_fields()],
				},
			},
		)
	if result.get("kind") == "error" and action == "update_configuration":
		key = next((field for field, _label in CONFIGURATION_EDIT_FIELDS if field in slots and field != "name"), "")
		saved = _configuration_edit_record(slots.get("name") or "")
		_cache_set(_pending_key(), pending)
		_cache_set(
			_draft_key(),
			{
				"action": "update_configuration",
				"slots": slots,
				"guide": {
					"phase": "review",
					"field": key,
					"proposal": slots.get(key) or "",
					"current": _row_value(saved, key) if saved else "",
					"configuration": slots.get("name") or "",
				},
			},
		)
	if result.get("kind") == "error" and action == "create_configuration":
		_cache_set(_pending_key(), pending)
		_cache_set(
			_draft_key(),
			{
				"action": "create_configuration",
				"slots": _configuration_slots_only(slots),
				"guide": {
					"field": "",
					"phase": "review",
					"proposal": "",
					"accepted": [item["key"] for item in _configuration_guide_fields(slots)],
				},
			},
		)
	if result.get("kind") == "error" and action == "create_partnership":
		_cache_set(_pending_key(), pending)
		_cache_set(
			_draft_key(),
			{
				"action": "create_partnership",
				"slots": _partnership_slots_only(slots),
				"guide": {
					"field": "",
					"phase": "review",
					"proposal": "",
					"accepted": [item["key"] for item in _partnership_guide_fields(slots)],
				},
			},
		)
	return result


@frappe.whitelist()
def cancel_assistant_action(token: str | None = None) -> dict:
	_require_user()
	pending = _cache_get(_pending_key())
	if pending and token and token != pending.get("token"):
		return _reply("That confirmation does not match the pending action.")
	_cache_set(_pending_key(), None)
	_cache_set(_draft_key(), None)
	return _reply("Cancelled. Nothing was changed.")


@frappe.whitelist()
def analyze_transaction(name: str | None = None) -> dict:
	"""Read-only analysis of one stored EDI document for the details view."""
	_require_user()
	name = (name or "").strip()
	if not name or not str(name).startswith("remote:"):
		frappe.throw(
			frappe._("Transaction analysis reads the OpenAS2 database. This id is not a remote message."),
			frappe.DoesNotExistError,
		)
	found = analyze_edi_record(name)
	summary = found["summary"]
	failure = found["failure"]
	sections = [
		{"title": "Transaction Summary", "body": _analysis_text(found).split("\n\n")[0]},
		{
			"title": "Processing Status",
			"body": f"{summary.get('status') or 'not stored'} · MDN {summary.get('mdn_status') or 'not stored'}",
		},
		{
			"title": "Failure / Issue",
			"body": failure.get("stage") or ("No failure is recorded." if summary.get("status") == "Success" else "Insufficient information to determine the cause."),
		},
		{
			"title": "Root Cause / Likely Cause",
			"body": (
				failure.get("cause")
				if failure.get("confidence") == "confirmed"
				else (
					f"Likely cause: {failure.get('cause')}"
					if failure.get("confidence") == "likely"
					else (failure.get("cause") or "Insufficient information to determine the cause.")
				)
			),
		},
		{"title": "Relevant Error", "body": failure.get("evidence") or "No error text is stored."},
		{"title": "Related Partner", "body": summary.get("partner") or summary.get("sent_from") or "Not stored."},
		{"title": "Related Partnership", "body": summary.get("partnership") or "No matching partnership record."},
		{"title": "MDN Analysis", "body": f"Stored MDN status: {summary.get('mdn_status') or 'not stored'}."},
		{"title": "Suggested Next Steps", "body": failure.get("fix") or "No change is suggested from the stored records."},
	]
	return {"summary": summary, "sections": sections}
