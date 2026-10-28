# Copyright (c) 2026, Lakshana and contributors
# For license information, please see license.txt

"""Pull EDI Document rows from remote Shipper / Broker / Carrier TMS sites.

This OpenAS2 Manager bench does not host the TMS EDI Document DocType.
Refresh reads each configured TMS via Frappe REST and mirrors metadata +
payload (edi_content / derived JSON) into OpenAS2 EDI Document (read-only).
"""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

import frappe
from frappe.utils import cint, get_datetime, now_datetime

# Match TMS EDI Document schema (all types: 204/990/214/210/810/820).
# Do not request as2_message_id — it does not exist on TMS and breaks the query.
ALL_EDI_TYPES = ("204", "990", "214", "210", "810", "820")
DEFAULT_EDI_FIELDS = [
	"name",
	"file_name",
	"status",
	"transaction_type",
	"direction",
	"trading_partner_id",
	"reference_number",
	"control_number",
	"as2_status",
	"mdn_status",
	"processed_on",
	"scac",
	"modified",
	"creation",
]
# Payload is fetched on demand (drawer) or via webhook — not on list Refresh.
DEFAULT_EDI_FIELDS_NO_PAYLOAD = list(DEFAULT_EDI_FIELDS)
MINIMAL_EDI_FIELDS = ["name", "transaction_type", "direction", "status", "file_name", "modified", "creation"]
MAX_EDI_ROWS = 200
MAX_EDI_CONTENT_CHARS = 500_000
TMS_HTTP_TIMEOUT = 8


def edi_content_to_json(edi_content: str | None, *, transaction_type: str | None = None) -> str:
	"""Convert raw X12 / EDI text into a structured JSON string for the Monitoring UI."""
	raw = (edi_content or "").strip()
	if not raw:
		return ""
	# Normalize segment terminators
	normalized = raw.replace("\r\n", "\n").replace("\r", "\n")
	parts = []
	for chunk in normalized.split("~"):
		chunk = chunk.strip()
		if not chunk:
			continue
		# Drop pure newline-only leftovers; keep multi-line segment text joined
		chunk = " ".join(line.strip() for line in chunk.split("\n") if line.strip())
		if not chunk:
			continue
		elements = chunk.split("*")
		tag = (elements[0] or "").strip()
		parts.append({"tag": tag, "elements": [e.strip() for e in elements[1:]]})
	payload = {
		"transaction_type": (transaction_type or "").strip() or None,
		"segment_count": len(parts),
		"segments": parts,
	}
	return json.dumps(payload, indent=2)


def resolve_sent_from_received_by(
	*,
	tms: str,
	direction: str | None,
	partner: str | None,
	sent_from: str | None = None,
	received_by: str | None = None,
) -> tuple[str, str]:
	"""Derive Sent From / Received By from direction + trading partner when not provided."""
	sf = (sent_from or "").strip()
	rb = (received_by or "").strip()
	if sf and rb:
		return sf[:140], rb[:140]
	partner_s = (partner or "").strip()
	tms_s = (tms or "").strip()
	direction_s = (direction or "").strip().lower()
	if direction_s == "outbound":
		sf = sf or tms_s
		rb = rb or partner_s
	elif direction_s == "inbound":
		sf = sf or partner_s
		rb = rb or tms_s
	else:
		sf = sf or partner_s or tms_s
		rb = rb or tms_s or partner_s
	return sf[:140], rb[:140]


def get_tms_site_config(tms: str) -> dict[str, Any]:
	"""Return {url, api_key, api_secret, fields?} for a TMS type from site_config."""
	sites = frappe.conf.get("tms_sites") or {}
	if not isinstance(sites, dict):
		return {}
	entry = sites.get(tms) or sites.get((tms or "").lower()) or {}
	return entry if isinstance(entry, dict) else {}


def resolve_tms_url(instance) -> str:
	"""Prefer OpenAS2 Instance.tms_site_url, else site_config.tms_sites[TMS].url."""
	url = (getattr(instance, "tms_site_url", None) or "").strip().rstrip("/")
	if url:
		return url
	cfg = get_tms_site_config(getattr(instance, "instance_type", "") or "")
	return (cfg.get("url") or "").strip().rstrip("/")


def resolve_tms_auth(tms: str) -> tuple[str, str]:
	cfg = get_tms_site_config(tms)
	return (cfg.get("api_key") or "").strip(), (cfg.get("api_secret") or "").strip()


def edi_document_desk_url(base_url: str, doc_name: str) -> str:
	base = (base_url or "").rstrip("/")
	name = urllib.parse.quote(doc_name or "", safe="")
	return f"{base}/app/edi-document/{name}" if base and name else ""


def _basic_auth_header(api_key: str, api_secret: str) -> str:
	token = base64.b64encode(f"{api_key}:{api_secret}".encode()).decode()
	return f"Basic {token}"


def fetch_edi_documents_from_tms(
	base_url: str,
	api_key: str,
	api_secret: str,
	*,
	limit: int = MAX_EDI_ROWS,
	fields: list[str] | None = None,
) -> list[dict]:
	"""GET /api/resource/EDI Document from a remote Frappe TMS site."""
	if not base_url:
		raise frappe.ValidationError("TMS site URL is not configured.")
	if not api_key or not api_secret:
		raise frappe.ValidationError(
			"TMS API key/secret missing. Set site_config.tms_sites.<TMS>.api_key/api_secret."
		)

	field_sets = [
		fields or DEFAULT_EDI_FIELDS,
		MINIMAL_EDI_FIELDS,
	]
	last_error: Exception | None = None
	for field_list in field_sets:
		try:
			return _get_list(base_url, api_key, api_secret, field_list, limit)
		except Exception as exc:
			last_error = exc
			# Retry with fewer fields if the DocType schema differs
			if "Unknown column" in str(exc) or "does not exist" in str(exc).lower():
				continue
			if isinstance(exc, urllib.error.HTTPError) and exc.code in (400, 417):
				continue
			raise
	if last_error:
		raise last_error
	return []


def _get_list(
	base_url: str,
	api_key: str,
	api_secret: str,
	fields: list[str],
	limit: int,
) -> list[dict]:
	# No transaction_type filter — sync every EDI type from the TMS site
	params = urllib.parse.urlencode(
		{
			"fields": json.dumps(fields),
			"limit_page_length": min(int(limit or MAX_EDI_ROWS), 500),
			"order_by": "modified desc",
		}
	)
	url = f"{base_url.rstrip('/')}/api/resource/EDI%20Document?{params}"
	req = urllib.request.Request(
		url,
		headers={
			"Authorization": _basic_auth_header(api_key, api_secret),
			"Accept": "application/json",
		},
		method="GET",
	)
	try:
		with urllib.request.urlopen(req, timeout=TMS_HTTP_TIMEOUT) as resp:  # noqa: S310 — configured TMS URL
			payload = json.loads(resp.read().decode("utf-8", errors="replace"))
	except urllib.error.HTTPError as exc:
		body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
		raise frappe.ValidationError(
			f"TMS EDI Document fetch failed ({exc.code}): {body[:400] or exc.reason}"
		) from exc
	except urllib.error.URLError as exc:
		raise frappe.ValidationError(f"TMS site unreachable: {exc.reason}") from exc
	except TimeoutError as exc:
		raise frappe.ValidationError("TMS EDI Document fetch timed out.") from exc

	data = payload.get("data") if isinstance(payload, dict) else None
	if not isinstance(data, list):
		raise frappe.ValidationError("Unexpected TMS EDI Document response.")
	return data


def fetch_single_edi_document_from_tms(
	base_url: str,
	api_key: str,
	api_secret: str,
	doc_name: str,
) -> dict:
	"""GET one EDI Document (includes edi_content) from a remote TMS."""
	if not base_url or not doc_name:
		return {}
	if not api_key or not api_secret:
		return {}
	encoded = urllib.parse.quote(doc_name, safe="")
	url = f"{base_url.rstrip('/')}/api/resource/EDI%20Document/{encoded}"
	req = urllib.request.Request(
		url,
		headers={
			"Authorization": _basic_auth_header(api_key, api_secret),
			"Accept": "application/json",
		},
		method="GET",
	)
	try:
		with urllib.request.urlopen(req, timeout=TMS_HTTP_TIMEOUT) as resp:  # noqa: S310
			payload = json.loads(resp.read().decode("utf-8", errors="replace"))
	except Exception:
		return {}
	data = payload.get("data") if isinstance(payload, dict) else None
	return data if isinstance(data, dict) else {}


def upsert_edi_mirror(instance, row: dict) -> str:
	"""Insert/update OpenAS2 EDI Document from a remote TMS row."""
	tms = instance.instance_type
	tms_doc_name = (row.get("name") or "").strip()
	if not tms_doc_name:
		return ""

	base_url = resolve_tms_url(instance)
	existing = frappe.db.get_value(
		"OpenAS2 EDI Document",
		{"tms": tms, "tms_doc_name": tms_doc_name},
		"name",
	)

	partner = (
		row.get("trading_partner_id")
		or row.get("partner_name")
		or row.get("partner")
		or row.get("trading_partner")
		or ""
	)
	ts = (
		row.get("processed_on")
		or row.get("modified")
		or row.get("creation")
		or now_datetime()
	)
	try:
		ts = get_datetime(ts)
	except Exception:
		ts = now_datetime()

	txn = (row.get("transaction_type") or row.get("transaction") or "").strip()
	if txn and txn not in ALL_EDI_TYPES:
		# Still mirror unknown types so Monitoring stays complete
		pass

	direction = (row.get("direction") or "")[:40]
	sent_from, received_by = resolve_sent_from_received_by(
		tms=tms,
		direction=direction,
		partner=str(partner),
		sent_from=row.get("sent_from"),
		received_by=row.get("received_by"),
	)

	edi_content = row.get("edi_content") or row.get("content") or ""
	if not isinstance(edi_content, str):
		edi_content = str(edi_content or "")
	if len(edi_content) > MAX_EDI_CONTENT_CHARS:
		edi_content = edi_content[:MAX_EDI_CONTENT_CHARS]

	json_content = row.get("json_content") or ""
	if not isinstance(json_content, str):
		json_content = str(json_content or "")
	if not json_content and edi_content:
		json_content = edi_content_to_json(edi_content, transaction_type=txn)

	payload = {
		"tms": tms,
		"instance": instance.name,
		"tms_doc_name": tms_doc_name,
		"file_name": (row.get("file_name") or "")[:140],
		"transaction_type": txn[:40],
		"status": (row.get("status") or "")[:80],
		"direction": direction,
		"sent_from": sent_from,
		"received_by": received_by,
		"partner_name": str(partner)[:140],
		"reference_number": (row.get("reference_number") or "")[:140],
		"as2_status": (row.get("as2_status") or "")[:40],
		"mdn_status": (row.get("mdn_status") or "")[:40],
		"as2_message_id": (row.get("as2_message_id") or row.get("message_id") or "")[:255],
		"document_timestamp": ts,
		"last_synced": now_datetime(),
		"tms_url": edi_document_desk_url(base_url, tms_doc_name)[:255],
		"edi_content": edi_content,
		"json_content": json_content,
	}
	# Only set optional columns that exist (pre-migrate safety)
	meta_fields = {f.fieldname for f in frappe.get_meta("OpenAS2 EDI Document").fields}
	payload = {k: v for k, v in payload.items() if k in meta_fields or k in ("tms", "instance", "tms_doc_name")}
	if "summary" in meta_fields:
		payload["summary"] = (
			f"{tms} {payload.get('transaction_type') or 'EDI'} "
			f"{payload.get('file_name') or tms_doc_name}"
		)[:140]

	if existing:
		doc = frappe.get_doc("OpenAS2 EDI Document", existing)
		for key, value in payload.items():
			# Don't wipe existing payload if this sync row omitted content
			if key in ("edi_content", "json_content") and not value and getattr(doc, key, None):
				continue
			setattr(doc, key, value)
		doc.flags.ignore_permissions = True
		doc.save(ignore_permissions=True)
		return doc.name

	doc = frappe.get_doc({"doctype": "OpenAS2 EDI Document", **payload})
	doc.flags.ignore_permissions = True
	doc.insert(ignore_permissions=True)
	return doc.name


def sync_instance_edi_documents(instance, *, limit: int = MAX_EDI_ROWS) -> dict:
	"""Fetch EDI Documents from the instance's TMS and mirror locally."""
	stats = {"edi_documents": 0, "notes": [], "skipped": False}
	if not frappe.db.exists("DocType", "OpenAS2 EDI Document"):
		stats["skipped"] = True
		stats["notes"].append("OpenAS2 EDI Document DocType is not installed. Run bench migrate.")
		return stats

	base_url = resolve_tms_url(instance)
	if not base_url:
		stats["skipped"] = True
		stats["notes"].append(
			f"No TMS URL for {instance.instance_type}. "
			"Set OpenAS2 Instance.tms_site_url or site_config.tms_sites."
		)
		return stats

	api_key, api_secret = resolve_tms_auth(instance.instance_type)
	cfg = get_tms_site_config(instance.instance_type)
	fields = cfg.get("fields") if isinstance(cfg.get("fields"), list) else None

	try:
		rows = fetch_edi_documents_from_tms(
			base_url, api_key, api_secret, limit=limit, fields=fields
		)
	except Exception as exc:
		stats["notes"].append(str(exc))
		return stats

	for row in rows:
		if not isinstance(row, dict):
			continue
		upsert_edi_mirror(instance, row)
		stats["edi_documents"] += 1

	link_message_logs_to_edi(instance.name)
	return stats


def sync_all_tms_edi_documents(instance_name: str | None = None) -> list[dict]:
	filters = {}
	if instance_name and instance_name not in ("", "All"):
		filters["name"] = instance_name
	results = []
	for name in frappe.get_all("OpenAS2 Instance", filters=filters, pluck="name"):
		inst = frappe.get_doc("OpenAS2 Instance", name)
		stats = sync_instance_edi_documents(inst)
		results.append({"instance": name, "tms": inst.instance_type, **stats})
	return results


def find_mirrored_edi_document(
	file_name: str | None = None,
	message_id: str | None = None,
	*,
	instance: str | None = None,
) -> dict | None:
	"""Look up a synced OpenAS2 EDI Document by file name or AS2 message id."""
	filters: dict[str, Any] = {}
	if instance:
		filters["instance"] = instance
	if file_name:
		name = frappe.db.get_value(
			"OpenAS2 EDI Document",
			{**filters, "file_name": file_name},
			["name", "tms_doc_name", "tms_url"],
			as_dict=True,
		)
		if name:
			return name
	if message_id:
		return frappe.db.get_value(
			"OpenAS2 EDI Document",
			{**filters, "as2_message_id": message_id},
			["name", "tms_doc_name", "tms_url"],
			as_dict=True,
		)
	return None


def link_message_logs_to_edi(instance_name: str | None = None) -> int:
	"""Fill OpenAS2 Message Log.edi_document from mirrored TMS docs."""
	filters: dict[str, Any] = [["edi_document", "in", ["", None]]]
	if instance_name:
		filters.append(["instance", "=", instance_name])

	updated = 0
	logs = frappe.get_all(
		"OpenAS2 Message Log",
		filters=filters,
		fields=["name", "instance", "file_name", "message_id"],
		limit_page_length=500,
	)
	for log in logs:
		mirror = find_mirrored_edi_document(
			log.file_name, log.message_id, instance=log.instance
		)
		if not mirror:
			mirror = find_mirrored_edi_document(log.file_name, log.message_id)
		if not mirror:
			continue
		frappe.db.set_value(
			"OpenAS2 Message Log",
			log.name,
			"edi_document",
			mirror.tms_doc_name,
			update_modified=False,
		)
		updated += 1
	return updated


TRANSACTION_LIST_LIMITATION = (
	"Each row is one AS2 message from msg_metadata. "
	"The table does not store a business reference or TMS document id, "
	"and one message is not one unique business transaction."
)


@frappe.whitelist()
def get_edi_documents(
	tms: str | None = None,
	status: str | None = None,
	transaction_type: str | None = None,
	date_from: str | None = None,
	date_to: str | None = None,
	limit: int | str = 300,
	partner: str | None = None,
) -> dict:
	"""List remote AS2 messages for the Monitoring EDI Transactions tab.

	EDI type comes from the filename or a short payload prefix. A failed
	database read returns an error and does not read the local EDI mirror.
	"""
	from openas2_manager.openas2.remote_tracking import (
		REMOTE_READ_ERROR,
		list_live_messages,
		to_transaction_row,
	)

	live = list_live_messages(
		instance=tms if tms not in ("", "All", None) else None,
		transaction_type=transaction_type,
		status=status if status not in ("", "All", None) else None,
		date_from=date_from,
		date_to=date_to,
		limit=min(cint(limit) or 200, 2000),
		partner=partner,
	)
	if live is None:
		return {
			"ok": False,
			"rows": [],
			"count": 0,
			"error": REMOTE_READ_ERROR,
			"edi_types": list(ALL_EDI_TYPES),
			"source": "OpenAS2 database",
			"limitation": TRANSACTION_LIST_LIMITATION,
		}
	rows = [to_transaction_row(row) for row in live.get("rows") or []]
	return {
		"ok": True,
		"rows": rows,
		"count": len(rows),
		"edi_types": list(ALL_EDI_TYPES),
		"source": "OpenAS2 database",
		"limitation": TRANSACTION_LIST_LIMITATION,
	}


def _remote_transaction_details(name: str) -> dict:
	"""One remote message plus its payload, loaded on demand."""
	from openas2_manager.openas2.remote_tracking import (
		REMOTE_READ_ERROR,
		RemoteAccessDenied,
		RemoteMessageNotFound,
		remote_message_details,
		remote_message_payload,
		to_transaction_row,
	)

	try:
		detail = remote_message_details(name)
	except RemoteMessageNotFound:
		frappe.throw(frappe._("Message not found."), frappe.DoesNotExistError)
	except RemoteAccessDenied:
		frappe.throw(frappe._("Not permitted to access this message."), frappe.PermissionError)
	if not detail:
		frappe.throw(frappe._(REMOTE_READ_ERROR))
	payload = remote_message_payload(name, full=True)
	if payload is None:
		frappe.throw(frappe._(REMOTE_READ_ERROR))
	row = to_transaction_row(detail)
	text = payload.get("payload") or ""
	code = payload.get("transaction_type") or ""
	if code:
		row["transaction_type"] = code
	row["edi_content"] = text
	row["json_content"] = edi_content_to_json(text, transaction_type=row.get("transaction_type")) if text else ""
	row["summary"] = ""
	row["limitation"] = TRANSACTION_LIST_LIMITATION
	if payload.get("reason") and not text:
		row["payload_reason"] = payload.get("reason")
	return row



@frappe.whitelist()
def get_edi_document_details(name: str | None = None) -> dict:
	"""Return one remote message, including the EDI payload loaded on demand."""
	name = (name or "").strip()
	if not name:
		frappe.throw(frappe._("Document name is required."))
	if not str(name).startswith("remote:"):
		frappe.throw(
			frappe._("This view reads the OpenAS2 database. {0} is not a remote message.").format(name),
			frappe.DoesNotExistError,
		)
	return _remote_transaction_details(name)



def _webhook_token_ok() -> bool:
	expected = (frappe.conf.get("openas2_tms_webhook_token") or "").strip()
	if not expected:
		return False
	provided = (
		frappe.get_request_header("X-OpenAS2-Token")
		or frappe.form_dict.get("token")
		or ""
	).strip()
	return bool(provided) and provided == expected


def _instance_for_tms(tms: str):
	name = frappe.db.get_value("OpenAS2 Instance", {"instance_type": tms}, "name")
	if not name:
		return None
	return frappe.get_doc("OpenAS2 Instance", name)


@frappe.whitelist(allow_guest=True)
def ingest_tms_edi_document(
	tms: str | None = None,
	name: str | None = None,
	file_name: str | None = None,
	status: str | None = None,
	transaction_type: str | None = None,
	direction: str | None = None,
	partner: str | None = None,
	as2_message_id: str | None = None,
	modified: str | None = None,
	edi_content: str | None = None,
	sent_from: str | None = None,
	received_by: str | None = None,
	json_content: str | None = None,
) -> dict:
	"""Push hook for TMS sites: call when an EDI Document is sent or received.

	Auth: header ``X-OpenAS2-Token`` (or form ``token``) must match
	``site_config.openas2_tms_webhook_token``.

	Example from TMS (doc_events on EDI Document):
	  POST /api/method/openas2_manager.openas2.tms_edi.ingest_tms_edi_document
	"""
	if not _webhook_token_ok():
		frappe.throw(frappe._("Invalid or missing OpenAS2 webhook token."), frappe.PermissionError)

	tms = (tms or "").strip()
	doc_name = (name or frappe.form_dict.get("doc_name") or "").strip()
	if tms not in ("Shipper", "Broker", "Carrier", "CompanyC"):
		frappe.throw(frappe._("tms must be Shipper, Broker, Carrier, or CompanyC."))
	if not doc_name:
		frappe.throw(frappe._("EDI Document name is required."))

	instance = _instance_for_tms(tms)
	if not instance:
		frappe.throw(frappe._("No OpenAS2 Instance configured for TMS {0}.").format(tms))

	content = edi_content if edi_content is not None else frappe.form_dict.get("edi_content")
	if content is None:
		content = ""
	elif not isinstance(content, str):
		content = str(content)

	row = {
		"name": doc_name,
		"file_name": file_name or frappe.form_dict.get("file_name"),
		"status": status or frappe.form_dict.get("status"),
		"transaction_type": transaction_type or frappe.form_dict.get("transaction_type"),
		"direction": direction or frappe.form_dict.get("direction"),
		"partner": partner or frappe.form_dict.get("partner"),
		"as2_message_id": as2_message_id or frappe.form_dict.get("as2_message_id"),
		"modified": modified or frappe.form_dict.get("modified") or now_datetime(),
		"edi_content": content,
		"sent_from": sent_from or frappe.form_dict.get("sent_from"),
		"received_by": received_by or frappe.form_dict.get("received_by"),
		"json_content": json_content or frappe.form_dict.get("json_content") or "",
	}
	mirror_name = upsert_edi_mirror(instance, row)
	link_message_logs_to_edi(instance.name)
	if not getattr(frappe.flags, "in_test", False):
		frappe.db.commit()
	try:
		frappe.publish_realtime(
			"openas2_monitoring_updated",
			{"tms": tms, "edi_document": doc_name, "source": "webhook"},
			after_commit=True,
		)
	except Exception:
		pass
	return {"ok": True, "name": mirror_name, "tms_doc_name": doc_name, "tms": tms}
