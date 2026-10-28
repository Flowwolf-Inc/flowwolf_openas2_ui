# Copyright (c) 2026, Lakshana and contributors
# For license information, please see license.txt

"""Unified OpenAS2 system + EDI activity logs for the Logs desk page.

AS2 message rows are read from the remote ``msg_metadata`` table. Runtime,
restart, provisioning, and configuration-change rows stay in Manager audit
DocTypes. A failed remote read is not filled from OpenAS2 Message Log.
"""

from __future__ import annotations

from datetime import datetime

import frappe
from frappe.utils import cint, get_datetime, getdate


def _parse_date_range(date_from: str | None, date_to: str | None) -> tuple[datetime | None, datetime | None]:
	start = get_datetime(date_from) if date_from else None
	end = None
	if date_to:
		end = get_datetime(date_to)
		if isinstance(date_to, str) and len(str(date_to).strip()) <= 10:
			end = datetime.combine(getdate(date_to), datetime.max.time())
	return start, end


def _in_range(ts, start, end) -> bool:
	if not ts:
		return not start and not end
	try:
		dt = get_datetime(ts)
	except Exception:
		return False
	if start and dt < start:
		return False
	if end and dt > end:
		return False
	return True


def _match_search(row: dict, search: str) -> bool:
	if not search:
		return True
	q = search.lower()
	hay = " ".join(
		str(row.get(k) or "")
		for k in ("event", "source", "status", "level", "component", "name", "instance")
	).lower()
	return q in hay


def _level_from_status(status: str | None, *, failed_tokens=None, warn_tokens=None) -> str:
	s = (status or "").strip()
	failed_tokens = failed_tokens or ("Failed", "Error", "Stopped")
	warn_tokens = warn_tokens or ("Duplicate", "Pending", "Not Available", "Proposed", "Rolled Back")
	if s in failed_tokens:
		return "Error"
	if s in warn_tokens:
		return "Warning"
	return "Info"


def _fmt_ts(ts) -> str:
	if not ts:
		return ""
	try:
		return str(get_datetime(ts))
	except Exception:
		return str(ts)


def _instance_filters() -> dict:
	from openas2_manager.access import get_allowed_instance_names

	allowed = get_allowed_instance_names()
	if allowed is None:
		return {}
	return {"instance": ["in", allowed or ["__none__"]]}


def _collect_message_logs(
	limit: int,
	date_from: str | None = None,
	date_to: str | None = None,
) -> tuple[list[dict], str | None]:
	"""Remote message activity. ``None`` error means the read succeeded."""
	from openas2_manager.openas2.remote_tracking import REMOTE_READ_ERROR, list_live_messages

	live = list_live_messages(date_from=date_from, date_to=date_to, limit=limit)
	if live is None:
		return [], REMOTE_READ_ERROR
	out = []
	for r in live.get("rows") or []:
		status = r.get("status") or "Unknown"
		parts = [
			r.get("direction"),
			r.get("transaction_type"),
			r.get("partner") or r.get("file_name"),
			r.get("error_message"),
		]
		event = " · ".join(str(p) for p in parts if p) or (r.get("message_id") or r.get("name") or "")
		out.append(
			{
				"name": r.get("name"),
				"doctype": "OpenAS2 Message Log",
				"timestamp": r.get("timestamp"),
				"timestamp_display": _fmt_ts(r.get("timestamp")),
				"level": _level_from_status(status),
				"event": event,
				"source": "EDI / Message",
				"component": r.get("instance") or "OpenAS2 database",
				"status": status,
				"instance": r.get("instance"),
			}
		)
	return out, None


def _collect_runtime_logs(limit: int) -> list[dict]:
	if not frappe.has_permission("OpenAS2 Runtime Log", "read"):
		return []
	rows = frappe.get_all(
		"OpenAS2 Runtime Log",
		filters=_instance_filters(),
		fields=[
			"name",
			"requested_at",
			"completed_at",
			"action",
			"result",
			"summary",
			"error_message",
			"instance",
			"lifecycle_status",
		],
		order_by="requested_at desc",
		limit_page_length=limit,
	)
	out = []
	for r in rows:
		result = r.get("result") or "Unknown"
		ts = r.get("completed_at") or r.get("requested_at")
		event = " · ".join(
			str(p) for p in (r.get("action"), r.get("summary") or r.get("error_message")) if p
		) or r.name
		out.append(
			{
				"name": r.name,
				"doctype": "OpenAS2 Runtime Log",
				"timestamp": ts,
				"timestamp_display": _fmt_ts(ts),
				"level": _level_from_status(result),
				"event": event,
				"source": "Runtime",
				"component": r.get("instance") or "Runtime Agent",
				"status": result,
				"instance": r.get("instance"),
			}
		)
	return out


def _collect_restart_logs(limit: int) -> list[dict]:
	if not frappe.has_permission("OpenAS2 Restart Log", "read"):
		return []
	rows = frappe.get_all(
		"OpenAS2 Restart Log",
		filters=_instance_filters(),
		fields=[
			"name",
			"requested_at",
			"completed_at",
			"result",
			"summary",
			"error_message",
			"instance",
			"process_status",
		],
		order_by="requested_at desc",
		limit_page_length=limit,
	)
	out = []
	for r in rows:
		result = r.get("result") or "Unknown"
		ts = r.get("completed_at") or r.get("requested_at")
		event = r.get("summary") or r.get("error_message") or f"Restart · {result}"
		out.append(
			{
				"name": r.name,
				"doctype": "OpenAS2 Restart Log",
				"timestamp": ts,
				"timestamp_display": _fmt_ts(ts),
				"level": _level_from_status(result),
				"event": event,
				"source": "Restart",
				"component": r.get("instance") or "OpenAS2",
				"status": result,
				"instance": r.get("instance"),
			}
		)
	return out


def _collect_provisioning_logs(limit: int) -> list[dict]:
	if not frappe.has_permission("OpenAS2 Provisioning Log", "read"):
		return []
	rows = frappe.get_all(
		"OpenAS2 Provisioning Log",
		filters=_instance_filters(),
		fields=[
			"name",
			"requested_at",
			"completed_at",
			"result",
			"summary",
			"error_message",
			"instance",
			"instance_name",
			"instance_type",
		],
		order_by="requested_at desc",
		limit_page_length=limit,
	)
	out = []
	for r in rows:
		result = r.get("result") or "Unknown"
		ts = r.get("completed_at") or r.get("requested_at")
		label = r.get("instance_name") or r.get("instance")
		event = r.get("summary") or r.get("error_message") or f"Provision {label} · {result}"
		out.append(
			{
				"name": r.name,
				"doctype": "OpenAS2 Provisioning Log",
				"timestamp": ts,
				"timestamp_display": _fmt_ts(ts),
				"level": _level_from_status(result),
				"event": event,
				"source": "Provisioning",
				"component": label or "Provisioning",
				"status": result,
				"instance": r.get("instance"),
			}
		)
	return out


def _collect_config_changes(limit: int) -> list[dict]:
	if not frappe.has_permission("OpenAS2 Configuration Change", "read"):
		return []
	rows = frappe.get_all(
		"OpenAS2 Configuration Change",
		filters=_instance_filters(),
		fields=[
			"name",
			"requested_at",
			"change_type",
			"status",
			"summary",
			"error_message",
			"instance",
			"partnership",
		],
		order_by="requested_at desc",
		limit_page_length=limit,
	)
	out = []
	for r in rows:
		status = r.get("status") or "Unknown"
		ts = r.get("requested_at")
		event = " · ".join(
			str(p)
			for p in (
				r.get("change_type"),
				r.get("partnership"),
				r.get("summary") or r.get("error_message"),
			)
			if p
		) or r.name
		out.append(
			{
				"name": r.name,
				"doctype": "OpenAS2 Configuration Change",
				"timestamp": ts,
				"timestamp_display": _fmt_ts(ts),
				"level": _level_from_status(status),
				"event": event,
				"source": "Configuration",
				"component": r.get("instance") or "partnerships.xml",
				"status": status,
				"instance": r.get("instance"),
			}
		)
	return out


@frappe.whitelist()
def get_system_logs(
	search: str | None = None,
	level: str | None = None,
	date_from: str | None = None,
	date_to: str | None = None,
	source: str | None = None,
	limit: int | str = 50,
	offset: int | str = 0,
) -> dict:
	"""Unified log feed for the OpenAS2 Logs page."""
	page_size = max(1, min(cint(limit) or 50, 200))
	page_offset = max(0, cint(offset) or 0)
	start, end = _parse_date_range(date_from, date_to)
	level_f = (level or "").strip()
	source_f = (source or "").strip()
	search_f = (search or "").strip()

	# Pull enough from each source to fill filters + pagination
	fetch_n = min(500, max(page_size * 4, 100))
	rows: list[dict] = []

	want_all_sources = not source_f or source_f in ("", "All")
	messages_error = None
	want_messages = want_all_sources or source_f in ("EDI / Message", "Message", "EDI")
	if want_messages:
		message_rows, messages_error = _collect_message_logs(
			fetch_n, date_from=date_from, date_to=date_to
		)
		rows.extend(message_rows)
	if want_all_sources or source_f == "Runtime":
		rows.extend(_collect_runtime_logs(fetch_n))
	if want_all_sources or source_f == "Restart":
		rows.extend(_collect_restart_logs(fetch_n))
	if want_all_sources or source_f == "Provisioning":
		rows.extend(_collect_provisioning_logs(fetch_n))
	if want_all_sources or source_f == "Configuration":
		rows.extend(_collect_config_changes(fetch_n))

	filtered = []
	for row in rows:
		if not _in_range(row.get("timestamp"), start, end):
			continue
		if level_f and level_f not in ("", "All") and row.get("level") != level_f:
			continue
		if not _match_search(row, search_f):
			continue
		filtered.append(row)

	def _sort_key(r):
		ts = r.get("timestamp")
		try:
			return get_datetime(ts) if ts else datetime.min
		except Exception:
			return datetime.min

	filtered.sort(key=_sort_key, reverse=True)
	total = len(filtered)
	page = filtered[page_offset : page_offset + page_size]

	result = {
		"rows": page,
		"count": len(page),
		"total": total,
		"limit": page_size,
		"offset": page_offset,
		"has_more": (page_offset + page_size) < total,
		"ok": messages_error is None,
	}
	if messages_error:
		result["error"] = messages_error
	return result


@frappe.whitelist()
def refresh_system_logs(instance_name: str | None = None) -> dict:
	"""Re-read msg_metadata for the Logs page. Does not scan files or report a failed read as success."""
	from openas2_manager.openas2.remote_tracking import REMOTE_READ_ERROR, list_live_messages

	live = list_live_messages(
		instance=instance_name if instance_name not in ("", "All") else None,
		limit=1,
	)
	if live is None:
		return {"ok": False, "refreshed": False, "error": REMOTE_READ_ERROR}
	return {"ok": True, "refreshed": True}
