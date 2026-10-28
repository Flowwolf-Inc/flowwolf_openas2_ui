# Copyright (c) 2026, Lakshana and contributors
# For license information, please see license.txt

"""Read-only access to the live OpenAS2 tracking database.

Uses site config ``openas2_remote_read`` and the environment variable named
by ``password_env``. Never logs the password or a connection string.
"""

from __future__ import annotations

import hashlib
import os
import re
import secrets
import time
from datetime import datetime, timedelta
from threading import Thread, local

import frappe

from openas2_manager.openas2.monitoring import (
	TRANSACTION_TYPES,
	display_message_id,
	extract_transaction_type,
	normalize_message_id,
	redact_sensitive,
)

REMOTE_NAME_PREFIX = "remote:"
TABLE_NAME = "msg_metadata"
# List and detail queries use only these columns. Payload columns stay out.
SAFE_COLUMNS = (
	"id",
	"msg_id",
	"direction",
	"sender_id",
	"receiver_id",
	"status",
	"state",
	"file_name",
	"create_dt",
	"update_dt",
	"signature_algorithm",
	"encryption_algorithm",
	"mdn_id",
	"resend_count",
)
PAYLOAD_COLUMNS = ("msg_data", "msg_headers", "mdn_response")
ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
REMOTE_ID_RE = re.compile(r"[1-9][0-9]*")
RECENT_ROW_LIMIT = 8
PAYLOAD_PREVIEW_CHARS = 1200
PAYLOAD_FULL_CHARS = 200_000
DETAIL_TXN_CODES = ("204", "990", "214", "210", "810", "820", "997")
# Segment boundary, then ST, then a common element separator, then the code.
# Whitespace may surround the separator. This is not an exact "ST*" match.
_ST_RE = re.compile(
	r"(?:^|[~\r\n|'\x1c])\s*ST\s*[*|~^\\]\s*("
	+ "|".join(DETAIL_TXN_CODES)
	+ r")(?!\d)",
	re.IGNORECASE,
)


class RemoteAccessDenied(Exception):
	"""The signed-in user cannot see this remote message."""


class RemoteMessageNotFound(Exception):
	"""The remote query succeeded and did not return this message."""


# Shown only while a status aggregation is missing. A successful read clears it.
# The figures are AS2 messages, including resends, not unique business documents.
EDI_TRANSACTION_COUNT_LIMITATION = (
	"EDI status totals are not available from msg_metadata yet. "
	"Displayed totals count AS2 messages, including resends, and are not "
	"one unique business transaction."
)


def unavailable_edi_counts() -> dict:
	"""Card and donut payload before a msg_metadata status aggregation is ready."""
	labels = (
		("204", "Load Tender"),
		("990", "Ack"),
		("210", "Invoice"),
		("214", "Status"),
	)
	kpis = []
	by_type = {}
	for code, label in labels:
		kpis.append(
			{
				"code": code,
				"label": label,
				"count": None,
				"last_7": None,
				"change_pct": None,
				"available": False,
				"summary": "",
				"note": EDI_TRANSACTION_COUNT_LIMITATION,
			}
		)
		by_type[code] = {
			"total": None,
			"success": None,
			"in_progress": None,
			"failure": None,
			"available": False,
		}
	return {
		"kpis": kpis,
		"edi_status_by_type": by_type,
		"edi_counts_available": False,
		"edi_counts_limitation": EDI_TRANSACTION_COUNT_LIMITATION,
		"transaction_summary": {},
		"transactions_total": None,
		"status_breakdown": {},
	}


def remote_reads_enabled() -> bool:
	"""Unit tests stay on the Frappe log unless they opt in."""
	if getattr(frappe.flags, "in_test", False) and not getattr(frappe.flags, "oa2_remote_read", False):
		return False
	return True


def _warn(message: str) -> None:
	"""Log a fixed message. Callers must not include passwords or SQL."""
	frappe.logger("openas2_manager").warning(message)


def read_settings(conf=None, environ=None) -> tuple[dict | None, str | None]:
	"""Return (settings, reason). Reason is config, password, or driver."""
	if conf is None:
		conf = frappe.conf
	if environ is None:
		environ = os.environ
	block = conf.get("openas2_remote_read") if conf is not None else None
	if not isinstance(block, dict):
		return None, "config"
	db_type = str(block.get("db_type") or "mariadb").strip().lower()
	if db_type not in ("mariadb", "mysql"):
		return None, "driver"
	env_name = str(block.get("password_env") or "").strip()
	host = str(block.get("host") or "").strip()
	database = str(block.get("database") or "").strip()
	user = str(block.get("user") or "").strip()
	if not host or not database or not user or not ENV_NAME_RE.match(env_name):
		return None, "config"
	password = environ.get(env_name) or ""
	if not password:
		password = _password_from_file(env_name, environ)
	if not password:
		return None, "password"
	try:
		port = int(block.get("port") or 3306)
	except (TypeError, ValueError):
		return None, "config"
	return (
		{
			"host": host,
			"port": port,
			"database": database,
			"user": user,
			"password": password,
		},
		None,
	)


def _password_from_file(env_name: str, environ: dict) -> str:
	"""Read one variable from the remote env file. Never log the value.

	An explicit environ mapping that does not name a file is left empty so
	tests do not read the developer file. The live process uses its own
	environment and the standard file when the variable was not exported.
	"""
	if "OPENAS2_REMOTE_READ_ENV" in environ:
		path = str(environ.get("OPENAS2_REMOTE_READ_ENV") or "").strip()
	elif environ is os.environ:
		path = os.path.expanduser("~/.config/openas2/remote_read.env")
	else:
		return ""
	if not path:
		return ""
	try:
		with open(path, encoding="utf-8") as handle:
			lines = handle.read().splitlines()
	except OSError:
		return ""
	for line in lines:
		stripped = line.strip()
		if not stripped or stripped.startswith("#"):
			continue
		if stripped.startswith("export "):
			stripped = stripped[len("export ") :].strip()
		if "=" not in stripped:
			continue
		name, value = stripped.split("=", 1)
		if name.strip() != env_name:
			continue
		value = value.strip()
		if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
			value = value[1:-1]
		return value
	return ""


def connect(settings: dict, read_timeout: int = 60):
	"""Open a short-lived connection. The caller must close it."""
	import pymysql
	from pymysql.cursors import DictCursor

	return pymysql.connect(
		host=settings["host"],
		port=settings["port"],
		user=settings["user"],
		password=settings["password"],
		database=settings["database"],
		charset="utf8mb4",
		connect_timeout=5,
		# A 2000-row monitoring read takes longer than a few seconds on the
		# remote link. A timeout becomes an error on the page. It is not
		# replaced with a local message log.
		read_timeout=int(read_timeout),
		cursorclass=DictCursor,
		autocommit=True,
	)


def map_direction(direction: str | None) -> str:
	value = (direction or "").strip().upper()
	if value in ("IN", "INBOUND", "RECEIVE", "RECV", "RECEIVED"):
		return "Inbound"
	if value in ("OUT", "OUTBOUND", "SEND", "SENT"):
		return "Outbound"
	if (direction or "").strip() in ("Inbound", "Outbound"):
		return direction.strip()
	return ""


def map_status(status: str | None, state: str | None) -> str:
	"""Map OpenAS2 status/state onto the monitoring status labels.

	``cleanup`` is a normal post-processing state, not a failure.
	"""
	status_l = (status or "").strip().lower()
	state_l = (state or "").strip().lower()
	state_failed = any(token in state_l for token in ("error", "fail", "exception")) and "ok" not in state_l
	if status_l == "cleanup":
		return "Failed" if state_failed else "Processed"
	if status_l in ("error", "failed", "fail", "exception", "terminated") or state_failed:
		return "Failed"
	if "mdn" in state_l and "ok" in state_l:
		return "Success"
	if status_l in ("ok", "success"):
		return "Success"
	if status_l in ("sent", "send"):
		return "Sent"
	if status_l in ("received", "receive"):
		return "Received"
	if status_l == "duplicate":
		return "Duplicate"
	if status_l in ("initializing", "resend", "pending", "sending", "queued"):
		return "Queued"
	known = (status or "").strip()
	if known in ("Success", "Failed", "Received", "Sent", "Duplicate", "Queued", "Processed", "MDN Received"):
		return known
	return known[:40] if known else "Unknown"


def map_mdn_status(status: str | None, state: str | None) -> str:
	"""MDN result only. The raw OpenAS2 state stays in its own field."""
	state_l = (state or "").strip().lower()
	if "mdn" in state_l and any(token in state_l for token in ("error", "fail")):
		return "Failed"
	if "mdn" in state_l and "ok" in state_l:
		return "Received"
	if "pending" in state_l or (status or "").strip().lower() in ("initializing", "pending", "queued"):
		return "Pending"
	return ""


def _optional_text(value) -> str | None:
	"""Return a trimmed string, or None when the remote column is blank."""
	if value is None:
		return None
	text = str(value).strip()
	return text or None


def _format_timestamp(value) -> str | None:
	if value is None or value == "":
		return None
	if isinstance(value, datetime):
		return value.strftime("%Y-%m-%d %H:%M:%S")
	return str(value)[:19]


def assign_parties(
	record: dict,
	*,
	instances_by_as2: dict,
	allowed_as2: list[str] | None,
	preferred_as2: list[str] | None,
) -> dict | None:
	"""Pick the local instance for a row, or None when it is out of scope."""
	sender = str(record.get("sender_id") or "")
	receiver = str(record.get("receiver_id") or "")
	preferred = set(preferred_as2 or [])
	allowed = None if allowed_as2 is None else set(allowed_as2)
	direction = map_direction(record.get("direction"))

	if preferred:
		if sender in preferred:
			local, remote, direction = sender, receiver, "Outbound"
		elif receiver in preferred:
			local, remote, direction = receiver, sender, "Inbound"
		else:
			return None
	elif direction == "Inbound":
		local, remote = receiver, sender
	else:
		local, remote = sender, receiver
		if direction == "":
			direction = "Outbound" if sender else ""

	if allowed is not None:
		if sender not in allowed and receiver not in allowed:
			return None
		if local not in allowed:
			if sender in allowed:
				local, remote, direction = sender, receiver, "Outbound"
			else:
				local, remote, direction = receiver, sender, "Inbound"

	instance = instances_by_as2.get(local) or {}
	return {
		"direction": direction,
		"local_as2_id": local,
		"remote_as2_id": remote,
		"instance": instance.get("name") or "",
		"instance_type": instance.get("instance_type"),
		"instance_label": instance.get("instance_name") or instance.get("name") or "",
	}


def to_message_row(record: dict, parties: dict, partners_by_as2: dict | None = None) -> dict:
	status = map_status(record.get("status"), record.get("state"))
	state = (record.get("state") or "").strip()
	remote_id = parties.get("remote_as2_id") or ""
	partner = (partners_by_as2 or {}).get(remote_id) or remote_id
	message_id = normalize_message_id(record.get("msg_id"))
	file_name = record.get("file_name") or ""
	error = ""
	if status == "Failed":
		detail = ": ".join(part for part in (str(record.get("status") or ""), state) if part)
		error = redact_sensitive(detail)
	row_id = record.get("id")
	row = {
		"name": f"{REMOTE_NAME_PREFIX}{row_id}",
		"instance": parties.get("instance") or "",
		"instance_type": parties.get("instance_type"),
		"instance_label": parties.get("instance_label") or parties.get("instance") or "",
		"direction": parties.get("direction") or "",
		"partner": partner,
		"local_as2_id": parties.get("local_as2_id") or "",
		"remote_as2_id": remote_id,
		"transaction_type": extract_transaction_type(file_name),
		"message_id": message_id,
		"message_id_display": display_message_id(message_id),
		"status": status,
		"mdn_status": map_mdn_status(record.get("status"), state),
		"state": state,
		"timestamp": _format_timestamp(record.get("update_dt") or record.get("create_dt")),
		"file_name": file_name,
		"source": "OpenAS2 database",
		"error_message": error,
		"edi_document": None,
		"raw_reference": f"msg_metadata:{row_id}",
	}
	for key in ("signature_algorithm", "encryption_algorithm", "mdn_id"):
		text = _optional_text(record.get(key))
		if text is not None:
			row[key] = text
	resend_count = record.get("resend_count")
	if resend_count is not None and resend_count != "":
		row["resend_count"] = resend_count
	return row


def to_transaction_row(row: dict) -> dict:
	"""One AS2 message in the Transactions table shape.

	Parties come from the message sender and receiver. A reference number and
	TMS document id are not columns on msg_metadata, so those fields stay blank.
	"""
	local_label = row.get("instance_label") or row.get("local_as2_id") or ""
	remote_label = row.get("partner") or row.get("remote_as2_id") or ""
	if row.get("direction") == "Inbound":
		sent_from, received_by = remote_label, local_label
	else:
		sent_from, received_by = local_label, remote_label
	return {
		"name": row.get("name") or "",
		"tms": row.get("instance_type") or "",
		"instance": row.get("instance") or "",
		"tms_doc_name": "",
		"file_name": row.get("file_name") or "",
		"transaction_type": row.get("transaction_type") or "Unknown",
		"transaction_type_label": row.get("transaction_type_label")
		or format_transaction_type_label(row.get("transaction_type")),
		"status": row.get("status") or "",
		"direction": row.get("direction") or "",
		"partner_name": remote_label,
		"reference_number": "",
		"as2_message_id": row.get("message_id") or "",
		"as2_status": row.get("status") or "",
		"mdn_status": row.get("mdn_status") or "",
		"document_timestamp": row.get("timestamp"),
		"sent_from": sent_from,
		"received_by": received_by,
		"tms_url": "",
		"source": "OpenAS2 database",
	}


def allowed_instance_names_from_scope(scope: dict) -> list[str] | None:
	"""Instance names the caller may read. None means unrestricted."""
	allowed_as2 = scope.get("allowed_as2")
	if allowed_as2 is None:
		return None
	names = []
	by_as2 = scope.get("instances_by_as2") or {}
	for as2_id in allowed_as2:
		name = (by_as2.get(as2_id) or {}).get("name")
		if name and name not in names:
			names.append(name)
	return names


def transaction_type_from_documents(row: dict, documents, allowed_names: list[str] | None) -> str:
	"""Use a known EDI type from an accessible document matched by file or Message-ID."""
	allowed = None if allowed_names is None else set(allowed_names)
	filename = row.get("file_name") or ""
	message_id = row.get("message_id") or ""
	instance = row.get("instance") or ""

	def known_code(doc) -> str:
		instance_name = doc.get("instance") or ""
		if allowed is not None and instance_name not in allowed:
			return ""
		if instance and instance_name != instance:
			return ""
		code = str(doc.get("transaction_type") or "").strip()
		return code if code in TRANSACTION_TYPES else ""

	if filename:
		for doc in documents or []:
			if (doc.get("file_name") or "") == filename:
				code = known_code(doc)
				if code:
					return code
	if message_id:
		for doc in documents or []:
			if (doc.get("as2_message_id") or "") == message_id:
				code = known_code(doc)
				if code:
					return code
	return "Unknown"


def _fetch_edi_type_rows(file_names: list[str], message_ids: list[str], allowed_names: list[str] | None):
	"""One read of existing EDI documents. Does not insert."""
	if not file_names and not message_ids:
		return []
	if not frappe.db.exists("DocType", "OpenAS2 EDI Document"):
		return []
	filters = []
	if allowed_names is not None:
		if not allowed_names:
			return []
		filters.append(["instance", "in", allowed_names])
	or_filters = []
	if file_names:
		or_filters.append(["file_name", "in", file_names])
	if message_ids:
		or_filters.append(["as2_message_id", "in", message_ids])
	return frappe.get_all(
		"OpenAS2 EDI Document",
		filters=filters,
		or_filters=or_filters,
		fields=["instance", "file_name", "as2_message_id", "transaction_type"],
		limit_page_length=max(len(file_names) + len(message_ids), 1),
	)


def apply_known_edi_types(rows: list[dict], scope: dict, fetch=None) -> None:
	"""Fill Unknown types from accessible EDI documents. Coded filenames are left alone."""
	pending = [row for row in rows if (row.get("transaction_type") or "Unknown") == "Unknown"]
	if not pending:
		return
	allowed_names = allowed_instance_names_from_scope(scope)
	file_names = sorted({row.get("file_name") for row in pending if row.get("file_name")})
	message_ids = sorted({row.get("message_id") for row in pending if row.get("message_id")})
	documents = []
	if file_names or message_ids:
		fetcher = fetch or _fetch_edi_type_rows
		try:
			documents = fetcher(file_names, message_ids, allowed_names) or []
		except Exception:
			documents = []
	for row in pending:
		row["transaction_type"] = transaction_type_from_documents(row, documents, allowed_names)


def matches_filters(row: dict, *, direction=None, transaction_type=None, status=None, errors_only=0) -> bool:
	if int(errors_only or 0) or status == "Failed":
		if row.get("status") != "Failed":
			return False
	elif status == "MDN Received":
		mdn = row.get("mdn_status")
		if mdn not in ("Received", "MDN Received") and row.get("status") != "MDN Received":
			return False
	elif status and status not in ("", "All") and row.get("status") != status:
		return False
	if direction and direction not in ("", "All") and row.get("direction") != direction:
		return False
	if transaction_type and transaction_type not in ("", "All") and row.get("transaction_type") != transaction_type:
		return False
	return True


def _select_sql(columns: str = ", ".join(SAFE_COLUMNS)) -> str:
	for blocked in PAYLOAD_COLUMNS:
		if blocked in columns:
			raise RuntimeError("Refusing to select payload columns")
	return columns


def _failed_sql() -> tuple[str, list]:
	return (
		"("
		"LOWER(status) IN ('error','failed','fail','exception','terminated') "
		"OR ("
		"(LOWER(IFNULL(state,'')) LIKE %s OR LOWER(IFNULL(state,'')) LIKE %s "
		"OR LOWER(IFNULL(state,'')) LIKE %s) "
		"AND LOWER(IFNULL(state,'')) NOT LIKE %s"
		")"
		")",
		["%error%", "%fail%", "%exception%", "%ok%"],
	)


def _processed_sql() -> tuple[str, list]:
	failed, params = _failed_sql()
	return f"(LOWER(status) = 'cleanup' AND NOT {failed})", params


def _success_sql() -> tuple[str, list]:
	failed, params = _failed_sql()
	sql = (
		f"(NOT {failed} AND LOWER(status) <> 'cleanup' AND ("
		"LOWER(status) IN ('ok','success') "
		"OR (LOWER(IFNULL(state,'')) LIKE %s AND LOWER(IFNULL(state,'')) LIKE %s)"
		"))"
	)
	return sql, params + ["%mdn%", "%ok%"]


def _mdn_received_sql() -> tuple[str, list]:
	return (
		"("
		"LOWER(IFNULL(state,'')) LIKE %s AND LOWER(IFNULL(state,'')) LIKE %s "
		"AND LOWER(IFNULL(state,'')) NOT LIKE %s AND LOWER(IFNULL(state,'')) NOT LIKE %s"
		")",
		["%mdn%", "%ok%", "%error%", "%fail%"],
	)


def _pending_mdn_sql() -> tuple[str, list]:
	return (
		"("
		"(LOWER(IFNULL(state,'')) LIKE %s OR LOWER(status) IN ('initializing','pending','queued')) "
		"AND NOT (LOWER(IFNULL(state,'')) LIKE %s AND LOWER(IFNULL(state,'')) LIKE %s) "
		"AND NOT (LOWER(IFNULL(state,'')) LIKE %s AND LOWER(IFNULL(state,'')) LIKE %s) "
		"AND NOT (LOWER(IFNULL(state,'')) LIKE %s AND LOWER(IFNULL(state,'')) LIKE %s)"
		")",
		["%pending%", "%mdn%", "%error%", "%mdn%", "%fail%", "%mdn%", "%ok%"],
	)


def _status_clause(status: str | None, failed_only: bool = False) -> tuple[str, list] | None:
	if failed_only or status == "Failed":
		return _failed_sql()
	if not status or status in ("", "All"):
		return None
	if status == "Success":
		return _success_sql()
	if status == "MDN Received":
		return _mdn_received_sql()
	if status == "Processed":
		return _processed_sql()
	if status == "Sent":
		failed, params = _failed_sql()
		sql = (
			"(LOWER(status) IN ('sent','send') AND NOT "
			f"{failed} AND NOT (LOWER(IFNULL(state,'')) LIKE %s AND LOWER(IFNULL(state,'')) LIKE %s))"
		)
		return sql, params + ["%mdn%", "%ok%"]
	if status == "Received":
		failed, params = _failed_sql()
		sql = (
			"(LOWER(status) IN ('received','receive') AND NOT "
			f"{failed} AND NOT (LOWER(IFNULL(state,'')) LIKE %s AND LOWER(IFNULL(state,'')) LIKE %s))"
		)
		return sql, params + ["%mdn%", "%ok%"]
	if status == "Duplicate":
		failed, params = _failed_sql()
		return f"(LOWER(status) = 'duplicate' AND NOT {failed})", params
	if status == "Queued":
		failed, params = _failed_sql()
		sql = (
			"(LOWER(status) IN ('initializing','resend','pending','sending','queued') AND NOT "
			f"{failed} AND NOT (LOWER(IFNULL(state,'')) LIKE %s AND LOWER(IFNULL(state,'')) LIKE %s))"
		)
		return sql, params + ["%mdn%", "%ok%"]
	return None


def _transaction_clause(transaction_type: str | None) -> tuple[str, list] | None:
	code = str(transaction_type or "")
	if code not in TRANSACTION_TYPES:
		return None
	return "IFNULL(file_name,'') REGEXP %s", [f"(^|[_.-]){code}([_.-]|$)"]


def _message_id_variants(message_id: str | None) -> list[str]:
	"""Exact stored forms of one Message-ID. The value stays a query parameter."""
	text = str(message_id or "").strip()
	if not text:
		return []
	variants = [text]
	if text.startswith("<") and text.endswith(">") and len(text) > 2:
		inner = text[1:-1].strip()
		if inner:
			variants.append(inner)
	else:
		variants.append(f"<{text}>")
	unique = []
	for item in variants:
		if item not in unique:
			unique.append(item)
	return unique


def _party_clause(as2_ids: list[str] | None) -> tuple[str, list] | None:
	if as2_ids is None:
		return None
	if not as2_ids:
		return "1=0", []
	holders = ", ".join(["%s"] * len(as2_ids))
	return (
		f"(sender_id IN ({holders}) OR receiver_id IN ({holders}))",
		list(as2_ids) + list(as2_ids),
	)


def _message_where(
	*,
	as2_ids: list[str] | None,
	date_from=None,
	date_to=None,
	status: str | None = None,
	transaction_type: str | None = None,
	message_id: str | None = None,
	failed_only: bool = False,
	partner_ids: list[str] | None = None,
	partner_local_as2_ids: list[str] | None = None,
	search: str | None = None,
) -> tuple[str, list]:
	"""Shared metadata predicate. Payload columns are never referenced."""
	where = []
	params: list = []
	party = _party_clause(as2_ids)
	if party:
		where.append(party[0])
		params.extend(party[1])
	if date_from is not None:
		where.append("create_dt >= %s")
		params.append(date_from)
	if date_to is not None:
		where.append("create_dt <= %s")
		params.append(date_to)
	status_filter = _status_clause(status, failed_only)
	if status_filter:
		where.append(status_filter[0])
		params.extend(status_filter[1])
	txn_filter = _transaction_clause(transaction_type)
	if txn_filter:
		where.append(txn_filter[0])
		params.extend(txn_filter[1])
	message_ids = _message_id_variants(message_id)
	if message_ids:
		holders = ", ".join(["%s"] * len(message_ids))
		where.append(f"msg_id IN ({holders})")
		params.extend(message_ids)
	local_for_partner = partner_local_as2_ids
	if local_for_partner is None and partner_ids is not None and as2_ids is not None:
		local_for_partner = as2_ids
	partner_filter = _partner_id_clause(partner_ids, local_as2_ids=local_for_partner)
	if partner_filter:
		where.append(partner_filter[0])
		params.extend(partner_filter[1])
	search_filter = _search_clause(search)
	if search_filter:
		where.append(search_filter[0])
		params.extend(search_filter[1])
	clause = " AND ".join(where) if where else "1=1"
	for blocked in PAYLOAD_COLUMNS:
		if blocked in clause:
			raise RuntimeError("Refusing to filter on payload columns")
	return clause, params


def _partner_id_clause(
	partner_ids: list[str] | None,
	*,
	local_as2_ids: list[str] | None = None,
) -> tuple[str, list] | None:
	"""Match rows whose Monitoring Partner Name is the selected remote party."""
	if partner_ids is None:
		return None
	remote_ids = []
	for item in partner_ids:
		text = str(item or "").strip()
		if text and text not in remote_ids:
			remote_ids.append(text)
	if not remote_ids:
		return "1=0", []
	remote_holders = ", ".join(["%s"] * len(remote_ids))
	local_ids = []
	for item in local_as2_ids or []:
		text = str(item or "").strip()
		if text and text not in local_ids:
			local_ids.append(text)
	if local_ids:
		local_holders = ", ".join(["%s"] * len(local_ids))
		sql = (
			f"((sender_id IN ({local_holders}) AND receiver_id IN ({remote_holders})) "
			f"OR (receiver_id IN ({local_holders}) AND sender_id IN ({remote_holders})))"
		)
		return sql, local_ids + remote_ids + local_ids + remote_ids
	return f"(sender_id IN ({remote_holders}) OR receiver_id IN ({remote_holders}))", remote_ids + remote_ids


def _search_clause(search: str | None) -> tuple[str, list] | None:
	"""Match list search text on metadata columns. Does not read msg_data."""
	text = str(search or "").strip()
	if not text:
		return None
	like = "%" + text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
	parts = [
		f"IFNULL({column},'') LIKE %s ESCAPE '\\\\'"
		for column in ("file_name", "msg_id", "sender_id", "receiver_id", "status", "state")
	]
	params: list = [like, like, like, like, like, like]
	if text in TRANSACTION_TYPES:
		txn_sql, txn_params = _transaction_clause(text)
		parts.append(txn_sql)
		params.extend(txn_params)
	mapped = {
		"success": "Success",
		"failed": "Failed",
		"processed": "Processed",
		"sent": "Sent",
		"received": "Received",
		"duplicate": "Duplicate",
		"queued": "Queued",
		"mdn received": "MDN Received",
	}.get(text.casefold())
	if mapped:
		status_sql, status_params = _status_clause(mapped, failed_only=(mapped == "Failed"))
		if status_sql:
			parts.append(status_sql)
			params.extend(status_params)
		if mapped == "Received":
			mdn_sql, mdn_params = _mdn_received_sql()
			parts.append(mdn_sql)
			params.extend(mdn_params)
	return "(" + " OR ".join(parts) + ")", params


def _partner_display_label(as2_id: str, partners_by_as2: dict | None) -> str:
	"""Same label shown in the Monitoring table for a remote AS2 id."""
	text = str(as2_id or "").strip()
	if not text:
		return ""
	return str((partners_by_as2 or {}).get(text) or text).strip()


def _partner_ids_for_filter(partner: str | None, partners_by_as2: dict) -> list[str]:
	"""AS2 ids for the partner label selected on the monitoring page."""
	needle = str(partner or "").strip()
	if not needle:
		return []
	needle_fold = needle.casefold()
	ids: list[str] = []
	for as2_id, name in (partners_by_as2 or {}).items():
		text = str(as2_id or "").strip()
		if not text:
			continue
		display = str(name or text).strip()
		if display.casefold() == needle_fold or text.casefold() == needle_fold:
			if text not in ids:
				ids.append(text)
	if ids:
		return ids
	# Trading partner id shown in the list when it is not registered as AS2 Partner.
	return [needle]


MONITORING_STATUS_OPTIONS = (
	"Success",
	"Failed",
	"Received",
	"Sent",
	"Duplicate",
	"Queued",
	"Processed",
	"MDN Received",
)
FILTER_OPTIONS_CACHE_TTL = 3600
FILTER_OPTIONS_READ_TIMEOUT = 240
FILTER_PARTNER_CHUNK_WIDTH = 200000


def build_list_query(
	*,
	as2_ids: list[str] | None,
	date_from=None,
	date_to=None,
	status: str | None = None,
	transaction_type: str | None = None,
	message_id: str | None = None,
	failed_only: bool = False,
	partner_ids: list[str] | None = None,
	search: str | None = None,
	limit: int = 200,
) -> tuple[str, list]:
	"""Parameterized list query. ``as2_ids`` None means no party restriction.

	Status and EDI type are applied before LIMIT so older matches are not hidden
	by a newer unmatched window.
	"""
	clause, params = _message_where(
		as2_ids=as2_ids,
		date_from=date_from,
		date_to=date_to,
		status=status,
		transaction_type=transaction_type,
		message_id=message_id,
		failed_only=failed_only,
		partner_ids=partner_ids,
		search=search,
	)
	sql = (
		f"SELECT {_select_sql()} FROM {TABLE_NAME} "
		f"WHERE {clause} ORDER BY id DESC LIMIT %s"
	)
	params.append(int(limit))
	return sql, params


def _filter_options_cache_key(scope: dict, date_from, date_to) -> str:
	ids = scope.get("query_ids")
	if ids is None:
		scope_part = "*"
	else:
		scope_part = ",".join(sorted(str(item) for item in ids)) or "-"
	df = str(date_from or "")
	dt = str(date_to or "")
	return f"oa2_monitor_filter_opts:v5:{scope_part}:{df}:{dt}"


def _partner_labels_from_remote_ids(
	remote_ids: list[str], partners_by_as2: dict, *, local_ids: set[str]
) -> list[str]:
	labels: dict[str, str] = {}
	for remote_id in remote_ids:
		text = str(remote_id or "").strip()
		if not text or text in local_ids:
			continue
		label = (partners_by_as2 or {}).get(text) or text
		key = label.casefold()
		if key not in labels:
			labels[key] = label
	return sorted(labels.values(), key=lambda item: item.casefold())


def _monitoring_local_as2_ids(scope: dict) -> set[str]:
	"""Local instance AS2 ids (not shown as partner labels)."""
	local: set[str] = set()
	allowed = scope.get("allowed_as2")
	if allowed is not None:
		local.update(str(item).strip() for item in allowed if str(item or "").strip())
	query_ids = scope.get("query_ids")
	if query_ids is not None:
		local.update(str(item).strip() for item in query_ids if str(item or "").strip())
	return local


def _monitoring_filter_values_from_chunked_scan(
	conn,
	*,
	scope: dict,
	base_clause: str,
	base_params: list,
	local_ids: set[str],
	partners_by_as2: dict,
) -> tuple[list[str], list[str], list[str]]:
	"""Distinct partners, statuses, and EDI types over the eligible dataset."""
	labels: dict[str, str] = {}
	statuses_seen: set[str] = set()
	txn_codes: set[str] = set()
	bounds_sql, bounds_params = build_card_bounds_query(scope.get("query_ids"))
	bound_rows = _execute(conn, bounds_sql, bounds_params)
	bound = bound_rows[0] if bound_rows else {}
	low, high = bound.get("lo"), bound.get("hi")
	if low is None or high is None:
		return [], [], []
	for id_from, id_to in card_id_ranges(
		int(low), int(high), width=FILTER_PARTNER_CHUNK_WIDTH
	):
		chunk_clause = f"({base_clause}) AND id >= %s AND id < %s"
		chunk_params = list(base_params) + [id_from, id_to]
		sql = (
			f"SELECT sender_id, receiver_id, file_name, status, state FROM {TABLE_NAME} "
			f"WHERE {chunk_clause}"
		)
		try:
			rows = _execute(conn, sql, chunk_params)
		except Exception:
			continue
		for row in rows or []:
			parties = assign_parties(
				row,
				instances_by_as2=scope["instances_by_as2"],
				allowed_as2=scope["allowed_as2"],
				preferred_as2=scope.get("preferred_as2"),
			)
			if not parties:
				continue
			message = to_message_row(row, parties, partners_by_as2)
			partner = str(message.get("partner") or "").strip()
			if partner:
				fold = partner.casefold()
				if fold not in labels:
					labels[fold] = partner
			status_label = str(message.get("status") or "").strip()
			if status_label:
				statuses_seen.add(status_label)
			if matches_filters(message, status="MDN Received"):
				statuses_seen.add("MDN Received")
			code = str(message.get("transaction_type") or "").strip()
			if code in TRANSACTION_TYPES:
				txn_codes.add(code)
	partners = sorted(labels.values(), key=lambda item: item.casefold())
	statuses = [label for label in MONITORING_STATUS_OPTIONS if label in statuses_seen]
	for extra in sorted(statuses_seen):
		if extra not in statuses:
			statuses.append(extra)
	txn_sorted = [code for code in TRANSACTION_TYPES if code in txn_codes]
	return partners, statuses, txn_sorted


def _distinct_values_from_monitoring_rows(records: list[dict], scope: dict) -> dict:
	partners_by_as2 = scope.get("partners_by_as2") or {}
	partner_labels: dict[str, str] = {}
	statuses_seen: set[str] = set()
	txn_codes: set[str] = set()

	for record in records:
		parties = assign_parties(
			record,
			instances_by_as2=scope["instances_by_as2"],
			allowed_as2=scope["allowed_as2"],
			preferred_as2=scope.get("preferred_as2"),
		)
		if not parties:
			continue
		row = to_message_row(record, parties, partners_by_as2)
		partner = str(row.get("partner") or "").strip()
		if partner:
			partner_labels[partner.casefold()] = partner
		status = str(row.get("status") or "").strip()
		if status:
			statuses_seen.add(status)
		if matches_filters(row, status="MDN Received"):
			statuses_seen.add("MDN Received")
		code = str(row.get("transaction_type") or "").strip()
		if code in TRANSACTION_TYPES:
			txn_codes.add(code)

	statuses = [label for label in MONITORING_STATUS_OPTIONS if label in statuses_seen]
	for extra in sorted(statuses_seen):
		if extra not in statuses:
			statuses.append(extra)
	transaction_types = [
		{"code": code, "label": format_transaction_type_label(code)}
		for code in TRANSACTION_TYPES
		if code in txn_codes
	]
	return {
		"partners": sorted(partner_labels.values(), key=lambda item: item.casefold()),
		"statuses": statuses,
		"transaction_types": transaction_types,
	}


def _monitoring_filter_options_from_db(
	conn,
	*,
	scope: dict,
	date_from,
	date_to,
) -> dict:
	start, end = _date_bounds(date_from, date_to)
	base_clause, base_params = _message_where(
		as2_ids=scope["query_ids"],
		date_from=start,
		date_to=end,
	)
	local_ids = _monitoring_local_as2_ids(scope)
	partners_by_as2 = scope.get("partners_by_as2") or {}
	partners, statuses, codes = _monitoring_filter_values_from_chunked_scan(
		conn,
		scope=scope,
		base_clause=base_clause,
		base_params=base_params,
		local_ids=local_ids,
		partners_by_as2=partners_by_as2,
	)
	transaction_types = [
		{"code": code, "label": format_transaction_type_label(code)} for code in codes
	]
	return {
		"ok": True,
		"partners": partners,
		"statuses": statuses,
		"transaction_types": transaction_types,
	}


def monitoring_filter_options(
	instance: str | None = None,
	date_from: str | None = None,
	date_to: str | None = None,
) -> dict:
	"""Distinct Monitoring filter values for the current scope and date window."""
	if not remote_reads_enabled():
		return {"ok": False, "error": REMOTE_READ_ERROR}
	settings, reason = read_settings()
	if not settings:
		_unavailable(reason)
		return {"ok": False, "error": REMOTE_READ_ERROR}
	scope = resolve_scope(instance)
	if scope is None:
		return {"ok": True, "partners": [], "statuses": [], "transaction_types": []}

	cache_key = _filter_options_cache_key(scope, date_from, date_to)
	cached = _card_cache_get(cache_key)
	if isinstance(cached, dict) and cached.get("ok"):
		return cached

	result: dict | None = None
	try:
		conn = connect(settings, read_timeout=FILTER_OPTIONS_READ_TIMEOUT)
	except Exception as exc:
		_unavailable(None, exc, settings.get("password") or "")
		return {"ok": False, "error": REMOTE_READ_ERROR}
	try:
		try:
			_execute(conn, "SET SESSION net_read_timeout = %s", [FILTER_OPTIONS_READ_TIMEOUT])
		except Exception:
			pass
		result = _monitoring_filter_options_from_db(
			conn, scope=scope, date_from=date_from, date_to=date_to
		)
	except Exception as exc:
		_unavailable(None, exc, settings.get("password") or "")
		return {
			"ok": False,
			"error": REMOTE_READ_ERROR,
			"partners": [],
			"statuses": [],
			"transaction_types": [],
		}
	finally:
		conn.close()
	if result and result.get("ok"):
		_card_cache_set(cache_key, result, expires_in_sec=FILTER_OPTIONS_CACHE_TTL)
	return result or {"ok": False, "error": REMOTE_READ_ERROR}


def build_count_query(
	*,
	as2_ids: list[str] | None,
	date_from=None,
	date_to=None,
	status: str | None = None,
	transaction_type: str | None = None,
	message_id: str | None = None,
	failed_only: bool = False,
	partner_ids: list[str] | None = None,
	search: str | None = None,
) -> tuple[str, list]:
	"""COUNT(*) for the same metadata filters as the list. No payload columns and no LIMIT."""
	clause, params = _message_where(
		as2_ids=as2_ids,
		date_from=date_from,
		date_to=date_to,
		status=status,
		transaction_type=transaction_type,
		message_id=message_id,
		failed_only=failed_only,
		partner_ids=partner_ids,
		search=search,
	)
	sql = f"SELECT COUNT(*) AS total FROM {TABLE_NAME} WHERE {clause}"
	for blocked in PAYLOAD_COLUMNS:
		if blocked in sql:
			raise RuntimeError("Refusing to select payload columns")
	if "LIMIT" in sql.upper():
		raise RuntimeError("Refusing to limit a total count")
	return sql, params


EDI_CARD_CODES = ("204", "990", "210", "214")


def _filename_type_pattern() -> str:
	"""Same file-name rule as ``extract_transaction_type``."""
	return "(^|[_.-])(" + "|".join(TRANSACTION_TYPES) + ")([_.-]|$)"


def _payload_type_pattern() -> str:
	"""Plaintext ST rule used on the same prefix the message list reads.

	This matches ``transaction_type_from_payload`` when the ST segment is in
	the first preview characters, including a MIME body that still contains it.
	"""
	return (
		r"(^|[~[:cntrl:]|'])[[:space:]]*ST[[:space:]]*[*|~^\\][[:space:]]*("
		+ "|".join(DETAIL_TXN_CODES)
		+ r")([^0-9]|$)"
	)


def _card_windows(now=None) -> tuple[datetime, datetime]:
	"""Latest seven site-local days, and the seven days before that.

	The boundary is local midnight. ``create_dt`` is compared the same way the
	message list compares a date filter.
	"""
	if now is None:
		from frappe.utils import now_datetime

		now = now_datetime()
	today = now.date() if isinstance(now, datetime) else now
	last_7_start = datetime.combine(today, datetime.min.time()) - timedelta(days=7)
	return last_7_start, last_7_start - timedelta(days=7)


def card_change_pct(current, previous):
	"""Percent change versus the previous seven days.

	Zero on either side has no meaningful percentage. Callers show an em dash
	instead of 0%, 100%, or -100%.
	"""
	if current is None or previous is None:
		return None
	try:
		current_n = int(current)
		previous_n = int(previous)
	except (TypeError, ValueError):
		return None
	if current_n <= 0 or previous_n <= 0:
		return None
	return round((current_n - previous_n) / previous_n * 100.0, 1)


def detected_card_type(file_name, payload: str = "") -> str:
	"""Card code for one message, using the message-list type rules.

	A recognized file name wins. Otherwise the ST segment in the payload is
	used, after the existing MIME unwrapping. 810, 820, and 997 are detected
	and are not one of the four cards.
	"""
	named = extract_transaction_type(file_name)
	if named in TRANSACTION_TYPES:
		return named if named in EDI_CARD_CODES else ""
	found = transaction_type_from_payload(payload or "")
	return found if found in EDI_CARD_CODES else ""


def _card_group_exprs() -> tuple[str, str, list, list]:
	"""Success and failure predicates already used for message activity.

	Success is an MDN-ok or ok/success message, or cleanup that ``map_status``
	calls Processed. Failure is the existing failed predicate. Those two do
	not overlap. Sent, received, queued, duplicate, and any other mapped
	status stay outside both, so the chart's third group is that remainder.
	"""
	failed_sql, failed_params = _failed_sql()
	success_sql, success_params = _success_sql()
	processed_sql, processed_params = _processed_sql()
	success_expr = f"(({success_sql}) OR ({processed_sql}))"
	return success_expr, f"({failed_sql})", success_params + processed_params, list(failed_params)


def build_edi_card_count_query(
	*,
	as2_ids: list[str] | None,
	last_7_start,
	prev_7_start,
	id_from: int | None = None,
	id_to: int | None = None,
) -> tuple[str, list]:
	"""One unpaged count of messages by detected EDI type.

	Each database row is classified once: file name first, then the leading
	payload characters when the file name has no type. Status and state are
	read with that row so each message lands in one status group. There is
	no join and no LIMIT, so a row is not counted twice.
	"""
	file_expr = "REGEXP_SUBSTR(IFNULL(file_name, ''), %s)"
	prefix = f"SUBSTRING(IFNULL(msg_data, ''), 1, {int(PAYLOAD_PREVIEW_CHARS)})"
	st_expr = (
		f"CASE WHEN {file_expr} <> '' THEN '' "
		f"ELSE IFNULL(REGEXP_SUBSTR({prefix}, %s), '') END"
	)
	code_expr = (
		"CASE "
		"WHEN file_match LIKE '%%204%%' THEN '204' "
		"WHEN file_match LIKE '%%990%%' THEN '990' "
		"WHEN file_match LIKE '%%214%%' THEN '214' "
		"WHEN file_match LIKE '%%210%%' THEN '210' "
		"WHEN file_match LIKE '%%810%%' OR file_match LIKE '%%820%%' THEN '' "
		"WHEN st_match LIKE '%%204%%' THEN '204' "
		"WHEN st_match LIKE '%%990%%' THEN '990' "
		"WHEN st_match LIKE '%%214%%' THEN '214' "
		"WHEN st_match LIKE '%%210%%' THEN '210' "
		"ELSE '' END"
	)
	success_expr, failed_expr, success_params, failed_params = _card_group_exprs()
	selects = []
	params: list = []
	for code in EDI_CARD_CODES:
		selects.append(f"SUM(CASE WHEN code = '{code}' THEN 1 ELSE 0 END) AS n{code}")
		selects.append(
			f"SUM(CASE WHEN code = '{code}' AND create_dt >= %s THEN 1 ELSE 0 END) AS d{code}"
		)
		params.append(last_7_start)
		selects.append(
			"SUM(CASE WHEN code = '{0}' AND create_dt >= %s AND create_dt < %s "
			"THEN 1 ELSE 0 END) AS p{0}".format(code)
		)
		params.extend([prev_7_start, last_7_start])
		selects.append(
			f"SUM(CASE WHEN code = '{code}' AND {success_expr} THEN 1 ELSE 0 END) AS s{code}"
		)
		params.extend(success_params)
		selects.append(
			f"SUM(CASE WHEN code = '{code}' AND {failed_expr} THEN 1 ELSE 0 END) AS f{code}"
		)
		params.extend(failed_params)
	where = ["1=1"]
	where_params: list = []
	party = _party_clause(as2_ids)
	if party:
		where = [party[0]]
		where_params.extend(party[1])
	if id_from is not None:
		where.append("id >= %s")
		where_params.append(_card_bound(id_from))
	if id_to is not None:
		where.append("id < %s")
		where_params.append(_card_bound(id_to))
	params.extend([_filename_type_pattern(), _filename_type_pattern(), _payload_type_pattern()])
	params.extend(where_params)
	sql = (
		f"SELECT {', '.join(selects)} FROM ("
		f"SELECT create_dt, status, state, {code_expr} AS code FROM ("
		f"SELECT create_dt, status, state, {file_expr} AS file_match, {st_expr} AS st_match "
		f"FROM {TABLE_NAME} WHERE {' AND '.join(where)}"
		") src) typed"
	)
	if "msg_headers" in sql or "mdn_response" in sql:
		raise RuntimeError("Refusing to select payload columns")
	if sql.count("msg_data") != 1 or prefix not in sql:
		raise RuntimeError("Refusing to select payload columns")
	if "LIMIT" in sql.upper() or " JOIN " in sql.upper():
		raise RuntimeError("Refusing to limit or join a card count")
	return sql, params


def _card_count_id_where(
	*,
	as2_ids: list[str] | None,
	id_from: int | None,
	id_to: int | None,
) -> tuple[list[str], list]:
	where = ["1=1"]
	where_params: list = []
	party = _party_clause(as2_ids)
	if party:
		where = [party[0]]
		where_params.extend(party[1])
	if id_from is not None:
		where.append("id >= %s")
		where_params.append(_card_bound(id_from))
	if id_to is not None:
		where.append("id < %s")
		where_params.append(_card_bound(id_to))
	return where, where_params


def _edi_card_count_sum_select(
	last_7_start,
	prev_7_start,
) -> tuple[list[str], list, str, str, list, list]:
	success_expr, failed_expr, success_params, failed_params = _card_group_exprs()
	selects = []
	params: list = []
	for code in EDI_CARD_CODES:
		selects.append(f"SUM(CASE WHEN code = '{code}' THEN 1 ELSE 0 END) AS n{code}")
		selects.append(
			f"SUM(CASE WHEN code = '{code}' AND create_dt >= %s THEN 1 ELSE 0 END) AS d{code}"
		)
		params.append(last_7_start)
		selects.append(
			"SUM(CASE WHEN code = '{0}' AND create_dt >= %s AND create_dt < %s "
			"THEN 1 ELSE 0 END) AS p{0}".format(code)
		)
		params.extend([prev_7_start, last_7_start])
		selects.append(
			f"SUM(CASE WHEN code = '{code}' AND {success_expr} THEN 1 ELSE 0 END) AS s{code}"
		)
		params.extend(success_params)
		selects.append(
			f"SUM(CASE WHEN code = '{code}' AND {failed_expr} THEN 1 ELSE 0 END) AS f{code}"
		)
		params.extend(failed_params)
	return selects, params, success_expr, failed_expr, success_params, failed_params


def build_edi_card_count_query_filename(
	*,
	as2_ids: list[str] | None,
	last_7_start,
	prev_7_start,
	id_from: int | None = None,
	id_to: int | None = None,
) -> tuple[str, list]:
	"""Classify rows from file names only. Does not read ``msg_data``."""
	file_expr = "REGEXP_SUBSTR(IFNULL(file_name, ''), %s)"
	code_expr = (
		"CASE "
		"WHEN file_match LIKE '%%204%%' THEN '204' "
		"WHEN file_match LIKE '%%990%%' THEN '990' "
		"WHEN file_match LIKE '%%214%%' THEN '214' "
		"WHEN file_match LIKE '%%210%%' THEN '210' "
		"WHEN file_match LIKE '%%810%%' OR file_match LIKE '%%820%%' THEN '' "
		"ELSE '' END"
	)
	selects, params, *_rest = _edi_card_count_sum_select(last_7_start, prev_7_start)
	where, where_params = _card_count_id_where(as2_ids=as2_ids, id_from=id_from, id_to=id_to)
	params.append(_filename_type_pattern())
	params.extend(where_params)
	sql = (
		f"SELECT {', '.join(selects)} FROM ("
		f"SELECT create_dt, status, state, {code_expr} AS code FROM ("
		f"SELECT create_dt, status, state, {file_expr} AS file_match "
		f"FROM {TABLE_NAME} WHERE {' AND '.join(where)}"
		") src) typed"
	)
	if "msg_data" in sql or "msg_headers" in sql or "mdn_response" in sql:
		raise RuntimeError("Refusing to select payload columns")
	if "LIMIT" in sql.upper() or " JOIN " in sql.upper():
		raise RuntimeError("Refusing to limit or join a card count")
	return sql, params


def build_edi_card_count_query_payload(
	*,
	as2_ids: list[str] | None,
	last_7_start,
	prev_7_start,
	id_from: int | None = None,
	id_to: int | None = None,
) -> tuple[str, list]:
	"""Classify rows from payload ST when the file name has no transaction token.

	Only rows with an empty file-name type match are scanned, matching
	``detected_card_type`` on the message list.
	"""
	file_expr = "REGEXP_SUBSTR(IFNULL(file_name, ''), %s)"
	prefix = f"SUBSTRING(IFNULL(msg_data, ''), 1, {int(PAYLOAD_PREVIEW_CHARS)})"
	st_expr = f"IFNULL(REGEXP_SUBSTR({prefix}, %s), '')"
	code_expr = (
		"CASE "
		"WHEN st_match LIKE '%%204%%' THEN '204' "
		"WHEN st_match LIKE '%%990%%' THEN '990' "
		"WHEN st_match LIKE '%%214%%' THEN '214' "
		"WHEN st_match LIKE '%%210%%' THEN '210' "
		"ELSE '' END"
	)
	selects, params, *_rest = _edi_card_count_sum_select(last_7_start, prev_7_start)
	where, where_params = _card_count_id_where(as2_ids=as2_ids, id_from=id_from, id_to=id_to)
	where.append(f"IFNULL({file_expr}, '') = ''")
	params.append(_payload_type_pattern())
	params.append(_filename_type_pattern())
	params.extend(where_params)
	sql = (
		f"SELECT {', '.join(selects)} FROM ("
		f"SELECT create_dt, status, state, {code_expr} AS code FROM ("
		f"SELECT create_dt, status, state, {st_expr} AS st_match "
		f"FROM {TABLE_NAME} WHERE {' AND '.join(where)}"
		") src) typed"
	)
	if sql.count("msg_data") != 1 or prefix not in sql:
		raise RuntimeError("Refusing to select payload columns")
	if "msg_headers" in sql or "mdn_response" in sql:
		raise RuntimeError("Refusing to select payload columns")
	if "LIMIT" in sql.upper() or " JOIN " in sql.upper():
		raise RuntimeError("Refusing to limit or join a card count")
	return sql, params


def build_detail_query(row_id: int, as2_ids: list[str] | None) -> tuple[str, list]:
	"""One metadata row, restricted to the caller's AS2 IDs when set."""
	where = ["id = %s"]
	params: list = [int(row_id)]
	party = _party_clause(as2_ids)
	if party:
		where.append(party[0])
		params.extend(party[1])
	sql = f"SELECT {_select_sql()} FROM {TABLE_NAME} WHERE {' AND '.join(where)} LIMIT 1"
	return sql, params


def parse_remote_row_id(name) -> int | None:
	"""Accept ``remote:123`` or ``123``. Reject anything that is not one positive id."""
	text = str(name or "").strip()
	if text.startswith(REMOTE_NAME_PREFIX):
		text = text[len(REMOTE_NAME_PREFIX) :]
	if not REMOTE_ID_RE.fullmatch(text):
		return None
	return int(text)


def transaction_type_from_payload(payload: str) -> str:
	"""Return a recognized X12 transaction code from an ST segment, or ''."""
	from openas2_manager.openas2.x12_json import edi_payload_text

	text = edi_payload_text(_payload_text(payload))
	match = _ST_RE.search(text)
	return match.group(1) if match else ""


# Names for codes this app already recognizes. The code stays the stored value.
EDI_TYPE_LABELS = {
	"204": "Load Tender",
	"990": "Response",
	"214": "Status",
	"210": "Freight Invoice",
	"810": "Invoice",
	"820": "Payment",
	"997": "Functional Acknowledgment",
}


def format_transaction_type_label(code: str | None) -> str:
	"""Visible EDI type. Unrecognized, blank, and invalid codes stay Unknown."""
	text = str(code or "").strip()
	name = EDI_TYPE_LABELS.get(text)
	if not name:
		return "Unknown"
	return f"{text} \u2013 {name}"


def _payload_limit(limit) -> int:
	"""Default preview stays 1,200 characters. An explicit full read is capped."""
	if limit is None:
		return PAYLOAD_PREVIEW_CHARS
	try:
		size = int(limit)
	except (TypeError, ValueError):
		return PAYLOAD_PREVIEW_CHARS
	if isinstance(limit, bool) or size < 1:
		return PAYLOAD_PREVIEW_CHARS
	return min(size, PAYLOAD_FULL_CHARS)


def build_payload_query(row_id: int, as2_ids: list[str] | None, limit=None) -> tuple[str, list]:
	"""One message body. Column names are fixed; only the id and AS2 scope are parameters.

	This does not go through ``_select_sql``. List and metadata queries keep refusing
	payload columns. The default length is the 1,200 character preview.
	"""
	if isinstance(row_id, bool) or not isinstance(row_id, int) or row_id < 1:
		raise ValueError("invalid message id")
	where = ["id = %s"]
	params: list = [_payload_limit(limit), int(row_id)]
	party = _party_clause(as2_ids)
	if party:
		where.append(party[0])
		params.extend(party[1])
	sql = (
		"SELECT id, sender_id, receiver_id, "
		"CHAR_LENGTH(msg_data) AS payload_chars, "
		"SUBSTRING(msg_data, 1, %s) AS msg_data "
		f"FROM {TABLE_NAME} WHERE {' AND '.join(where)} LIMIT 1"
	)
	if "msg_headers" in sql or "mdn_response" in sql:
		raise RuntimeError("Refusing to select extra payload columns")
	return sql, params


def _payload_text(value) -> str:
	if value is None:
		return ""
	if isinstance(value, bytes):
		return value.decode("utf-8", errors="replace")
	return str(value)


_INBOUND_SQL = "('IN','INBOUND','RECEIVE','RECV','RECEIVED')"


def _direction_sums(as2_ids: list[str] | None) -> tuple[str, str, list]:
	if not as2_ids:
		inbound = f"SUM(CASE WHEN UPPER(IFNULL(direction,'')) IN {_INBOUND_SQL} THEN 1 ELSE 0 END)"
		outbound = (
			"SUM(CASE WHEN UPPER(IFNULL(direction,'')) IN ('OUT','OUTBOUND','SEND','SENT') "
			"OR IFNULL(direction,'') = '' THEN 1 ELSE 0 END)"
		)
		return inbound, outbound, []
	holders = ", ".join(["%s"] * len(as2_ids))
	ids = list(as2_ids)
	inbound = (
		"SUM(CASE "
		f"WHEN UPPER(IFNULL(direction,'')) IN {_INBOUND_SQL} AND receiver_id IN ({holders}) THEN 1 "
		f"WHEN UPPER(IFNULL(direction,'')) NOT IN {_INBOUND_SQL} "
		f"AND sender_id NOT IN ({holders}) AND receiver_id IN ({holders}) THEN 1 ELSE 0 END)"
	)
	outbound = (
		"SUM(CASE "
		f"WHEN UPPER(IFNULL(direction,'')) IN {_INBOUND_SQL} "
		f"AND receiver_id NOT IN ({holders}) AND sender_id IN ({holders}) THEN 1 "
		f"WHEN UPPER(IFNULL(direction,'')) NOT IN {_INBOUND_SQL} AND sender_id IN ({holders}) THEN 1 "
		"ELSE 0 END)"
	)
	return inbound, outbound, ids + ids + ids + ids + ids + ids


def build_summary_query(*, as2_ids: list[str] | None, date_from) -> tuple[str, list]:
	"""Today's totals. The date predicate keeps this off a full-table count."""
	success_sql, success_params = _success_sql()
	processed_sql, processed_params = _processed_sql()
	failed_sql, failed_params = _failed_sql()
	pending_sql, pending_params = _pending_mdn_sql()
	inbound_sql, outbound_sql, direction_params = _direction_sums(as2_ids)
	params: list = []
	params.extend(direction_params)
	params.extend(success_params)
	params.extend(processed_params)
	params.extend(processed_params)
	params.extend(failed_params)
	params.extend(pending_params)
	where = ["create_dt >= %s"]
	where_params: list = [date_from]
	party = _party_clause(as2_ids)
	if party:
		where.append(party[0])
		where_params.extend(party[1])
	params.extend(where_params)
	sql = (
		"SELECT COUNT(*) AS messages_today, "
		f"{inbound_sql} AS inbound, {outbound_sql} AS outbound, "
		f"SUM(CASE WHEN {success_sql} OR {processed_sql} THEN 1 ELSE 0 END) AS successful, "
		f"SUM(CASE WHEN {processed_sql} THEN 1 ELSE 0 END) AS processed, "
		f"SUM(CASE WHEN {failed_sql} THEN 1 ELSE 0 END) AS failed, "
		f"SUM(CASE WHEN {pending_sql} THEN 1 ELSE 0 END) AS pending_mdn "
		f"FROM {TABLE_NAME} WHERE {' AND '.join(where)}"
	)
	for blocked in PAYLOAD_COLUMNS:
		if blocked in sql:
			raise RuntimeError("Refusing to select payload columns")
	return sql, params


def activity_totals(rows) -> dict:
	"""Count mapped rows. Processed cleanup is successful, not failed."""
	processed = success = failed = inbound = outbound = pending = 0
	for row in rows or []:
		status = row.get("status")
		if status == "Processed":
			processed += 1
		elif status == "Success":
			success += 1
		elif status == "Failed":
			failed += 1
		if row.get("direction") == "Inbound":
			inbound += 1
		elif row.get("direction") == "Outbound":
			outbound += 1
		if row.get("mdn_status") == "Pending":
			pending += 1
	return {
		"messages_today": len(rows or []),
		"inbound": inbound,
		"outbound": outbound,
		"successful": success + processed,
		"processed": processed,
		"failed": failed,
		"pending_mdn": pending,
	}


def _execute(conn, sql: str, params: list):
	with conn.cursor() as cursor:
		cursor.execute("SET SESSION TRANSACTION READ ONLY")
		cursor.execute(sql, params)
		return cursor.fetchall()


def _column_indexed(conn, column: str) -> bool:
	"""True when a remote column has an index. Avoids a full-table predicate."""
	rows = _execute(conn, f"SHOW INDEX FROM {TABLE_NAME}", [])
	return any((row.get("Column_name") or "") == column for row in rows)


def resolve_scope(instance: str | None = None) -> dict | None:
	"""AS2 IDs the user may see. None means return an empty list (no access)."""
	from openas2_manager.access import company_as2_ids, get_allowed_instance_names

	allowed_names = get_allowed_instance_names()
	allowed_as2 = company_as2_ids()
	if allowed_as2 is not None and not allowed_as2:
		return None

	instances = frappe.get_all(
		"OpenAS2 Instance",
		fields=["name", "as2_id", "instance_type", "instance_name"],
		limit_page_length=0,
	)
	by_name = {row.name: row for row in instances}
	by_as2 = {row.as2_id: row for row in instances if row.as2_id}
	partners = frappe.get_all(
		"AS2 Partner",
		fields=["as2_id", "partner_name", "name"],
		limit_page_length=0,
	)
	partners_by_as2 = {
		row.as2_id: (row.partner_name or row.name)
		for row in partners
		if row.as2_id
	}

	preferred: list[str] = []
	if instance and instance not in ("", "All"):
		if instance in by_name:
			if allowed_names is not None and instance not in allowed_names:
				return None
			as2_id = by_name[instance].as2_id
			if not as2_id:
				return None
			preferred = [as2_id]
		else:
			names = [row.name for row in instances if row.instance_type == instance]
			if allowed_names is not None:
				names = [name for name in names if name in allowed_names]
			preferred = [by_name[name].as2_id for name in names if by_name[name].as2_id]
			if not preferred:
				return None

	if allowed_as2 is not None and preferred:
		preferred = [as2_id for as2_id in preferred if as2_id in set(allowed_as2)]
		if not preferred:
			return None

	query_ids = preferred or allowed_as2
	return {
		"allowed_as2": list(allowed_as2) if allowed_as2 is not None else None,
		"preferred_as2": preferred,
		"query_ids": list(query_ids) if query_ids is not None else None,
		"instances_by_as2": by_as2,
		"partners_by_as2": partners_by_as2,
	}


REMOTE_READ_ERROR = "The OpenAS2 database could not be read."
# A filtered count cannot use an index, so it outlives the server's 30s
# net_read_timeout and the previous 60s client timeout.
COUNT_READ_TIMEOUT = 120
# One full classification reads payload text for rows whose file name has no
# type. That scan is split on the primary key so each statement can finish.
CARD_COUNT_READ_TIMEOUT = 3600
CARD_CHUNK_READ_TIMEOUT = 240
CARD_COUNT_ID_WIDTH = 500000
# One payload aggregation per primary-key chunk (filename pass stays separate).
CARD_COUNT_PAYLOAD_ID_WIDTH = CARD_COUNT_ID_WIDTH
# One remote connection per refresh avoids server "too many connections" errors.
CARD_COUNT_WORKERS = 1
CARD_CACHE_TTL_SECONDS = 3600
CARD_CACHE_KEEP_SECONDS = 6 * 60 * 60
# Full-table refresh can run for well over an hour; rely on per-chunk heartbeats.
CARD_LOCK_STALE_SECONDS = 10800
# A holder that never heartbeats after acquire is treated as abandoned.
CARD_LOCK_ORPHAN_SECONDS = 600
CARD_LOCK_CACHE_SECONDS = 7200
# A scheduled marker without a live lock should not block new refreshes forever.
CARD_SCHEDULED_STALE_SECONDS = 180
# Enqueued job with no worker lock and no cache is treated as abandoned.
CARD_SCHEDULED_ORPHAN_SECONDS = 45
# Refresh holder with no cached result and no heartbeat progress (abandoned worker).
CARD_LOCK_NO_CACHE_IDLE_SECONDS = 120

_card_lock_state = local()


def _remote_error_summary(exc: Exception, secret: str = "") -> str:
	"""Database errno and server text. Other exception text is omitted.

	A payload or password can be embedded in a generic exception. Only the
	integer MariaDB/pymysql error code is followed by its server message.
	"""
	args = getattr(exc, "args", ()) or ()
	errno = args[0] if args and isinstance(args[0], int) and not isinstance(args[0], bool) else ""
	detail = ""
	if errno != "" and len(args) > 1 and isinstance(args[1], str):
		detail = args[1]
	text = f"{type(exc).__name__} {errno}: {detail}".strip(" :")
	if secret and detail:
		text = text.replace(str(secret), "***")
	return text[:400]


def _unavailable(reason: str | None, exc: Exception | None = None, secret: str = "") -> None:
	if reason == "password":
		_warn("OpenAS2 remote read password is not set.")
	elif reason == "driver":
		_warn("OpenAS2 remote read driver is not supported.")
	elif exc is not None:
		_warn(f"OpenAS2 remote read failed ({_remote_error_summary(exc, secret)}).")
	else:
		_warn("OpenAS2 remote read is not configured.")


def remote_read_config_message(reason: str | None) -> str:
	if reason == "password":
		return "OpenAS2 remote read password is not configured."
	if reason == "driver":
		return "OpenAS2 remote read database driver is not supported."
	return "OpenAS2 remote read is not configured."


def remote_database_ping(settings: dict | None = None, *, read_timeout: int = 30) -> str | None:
	"""Return None when ``msg_metadata`` is reachable; otherwise a safe error summary."""
	if settings is None:
		settings, reason = read_settings()
		if not settings:
			return remote_read_config_message(reason)
	secret = settings.get("password") or ""
	try:
		conn = connect(settings, read_timeout=read_timeout)
		try:
			_execute(conn, "SELECT 1 AS ok", [])
		finally:
			conn.close()
	except Exception as exc:
		return _remote_error_summary(exc, secret)
	return None


def resolve_edi_dashboard_read_error(
	cache_key: str | None,
	result: dict | None = None,
) -> str:
	"""User-facing EDI dashboard error. Do not blame the database when only cache is empty."""
	if cache_key:
		try:
			if edi_card_refresh_in_progress():
				return "EDI totals are refreshing in the background."
		except RuntimeError:
			pass
	settings, reason = read_settings()
	if not settings:
		return remote_read_config_message(reason)
	ping_error = remote_database_ping(settings)
	if ping_error:
		return f"{REMOTE_READ_ERROR} ({ping_error})"
	if cache_key:
		stored = edi_card_read_error(cache_key)
		if stored and stored != REMOTE_READ_ERROR:
			return stored
		if stored == REMOTE_READ_ERROR:
			_clear_card_refresh_error(cache_key)
	if result and result.get("ok") and result.get("counts"):
		return EDI_TRANSACTION_COUNT_LIMITATION
	return EDI_TRANSACTION_COUNT_LIMITATION


def _map_records(records, scope: dict, **filters) -> list[dict]:
	rows = []
	for record in records or []:
		parties = assign_parties(
			record,
			instances_by_as2=scope["instances_by_as2"],
			allowed_as2=scope["allowed_as2"],
			preferred_as2=scope["preferred_as2"],
		)
		if not parties:
			continue
		row = to_message_row(record, parties, scope.get("partners_by_as2"))
		rows.append(row)
	return [row for row in rows if matches_filters(row, **filters)]


def list_live_messages(
	instance: str | None = None,
	direction: str | None = None,
	transaction_type: str | None = None,
	status: str | None = None,
	date_from: str | None = None,
	date_to: str | None = None,
	message_id: str | None = None,
	errors_only: int | str = 0,
	limit: int | str = 200,
	include_type_preview: bool = True,
	partner: str | None = None,
	search: str | None = None,
) -> dict | None:
	"""Live message list, or None when the database could not be read."""
	if not remote_reads_enabled():
		return None
	settings, reason = read_settings()
	if not settings:
		_unavailable(reason)
		return None
	scope = resolve_scope(instance)
	if scope is None:
		return {"rows": [], "count": 0}

	start, end = _date_bounds(date_from, date_to)
	failed_only = bool(int(errors_only or 0) or status == "Failed")
	row_limit = min(int(limit or 2000), 2000)
	txn = transaction_type if transaction_type not in ("", "All", None) else None
	partner_ids = None
	if str(partner or "").strip():
		partner_ids = _partner_ids_for_filter(partner, scope.get("partners_by_as2") or {})
	sql, params = build_list_query(
		as2_ids=scope["query_ids"],
		date_from=start,
		date_to=end,
		status=None if failed_only or not status or status in ("", "All") else status,
		transaction_type=txn,
		message_id=message_id,
		failed_only=failed_only,
		partner_ids=partner_ids,
		search=search,
		limit=row_limit,
	)
	try:
		conn = connect(settings)
	except Exception as exc:
		_unavailable(None, exc, settings.get("password") or "")
		return None
	try:
		try:
			records = _execute(conn, sql, params)
		except Exception as exc:
			_unavailable(None, exc, settings.get("password") or "")
			return None
		# Status, EDI type, and failure filters are already in the SQL WHERE clause.
		rows = _map_records(records, scope, direction=direction)
		if include_type_preview:
			_fill_unknown_transaction_types(conn, rows, scope.get("query_ids"))
	finally:
		conn.close()
	rows = rows[:row_limit]
	return {"rows": rows, "count": len(rows)}


def count_live_messages(
	instance: str | None = None,
	transaction_type: str | None = None,
	status: str | None = None,
	date_from: str | None = None,
	date_to: str | None = None,
	errors_only: int | str = 0,
	partner: str | None = None,
	search: str | None = None,
	*,
	read_timeout: int = COUNT_READ_TIMEOUT,
) -> dict:
	"""Total metadata rows for the current list filters.

	``total`` is None when the database could not be read or the count timed out.
	A successful query that matches nothing returns 0. The count does not select
	payload columns and is not limited to one page.
	"""
	if not remote_reads_enabled():
		return {"ok": False, "total": None, "error": REMOTE_READ_ERROR}
	settings, reason = read_settings()
	if not settings:
		_unavailable(reason)
		return {"ok": False, "total": None, "error": REMOTE_READ_ERROR}
	scope = resolve_scope(instance)
	if scope is None:
		return {"ok": True, "total": 0}

	partner_ids = None
	if str(partner or "").strip():
		partner_ids = _partner_ids_for_filter(partner, scope.get("partners_by_as2") or {})
	start, end = _date_bounds(date_from, date_to)
	failed_only = bool(int(errors_only or 0) or status == "Failed")
	sql, params = build_count_query(
		as2_ids=scope["query_ids"],
		date_from=start,
		date_to=end,
		status=None if failed_only or not status or status in ("", "All") else status,
		transaction_type=transaction_type if transaction_type not in ("", "All", None) else None,
		failed_only=failed_only,
		partner_ids=partner_ids,
		search=search,
	)
	secret = settings.get("password") or ""
	try:
		conn = connect(settings, read_timeout=read_timeout)
		try:
			# The server default net_read_timeout is 30s. A filtered COUNT(*)
			# has no index and is dropped before it can return.
			try:
				_execute(conn, "SET SESSION net_read_timeout = %s", [read_timeout])
			except Exception as exc:
				_warn(
					"OpenAS2 remote count could not extend the read timeout "
					f"({_remote_error_summary(exc, secret)})."
				)
			records = _execute(conn, sql, params)
		finally:
			conn.close()
	except Exception as exc:
		_unavailable(None, exc, secret)
		return {"ok": False, "total": None, "error": REMOTE_READ_ERROR}
	raw = records[0].get("total") if records else 0
	return {"ok": True, "total": int(raw or 0)}


def _count_cell(raw: dict, name: str) -> int:
	if not raw:
		return 0
	if name in raw:
		value = raw.get(name)
	else:
		folded = name.lower()
		value = next((item for key, item in raw.items() if str(key).lower() == folded), 0)
	return int(value or 0)


def _card_bound(value) -> int:
	if isinstance(value, bool) or not isinstance(value, int) or value < 0:
		raise ValueError("invalid message id bound")
	return value


def card_id_ranges(low: int, high: int, width: int = CARD_COUNT_ID_WIDTH) -> list[tuple[int, int]]:
	"""Half-open primary-key ranges covering every id from low through high once."""
	start = _card_bound(low)
	last = _card_bound(high)
	step = _card_bound(width)
	if step < 1:
		raise ValueError("invalid card count width")
	if last < start:
		return []
	ranges: list[tuple[int, int]] = []
	stop_at = last + 1
	while start < stop_at:
		stop = min(start + step, stop_at)
		ranges.append((start, stop))
		start = stop
	return ranges


def build_card_bounds_query(as2_ids: list[str] | None) -> tuple[str, list]:
	"""Indexed min and max id for the caller's messages. No payload columns."""
	where = ["1=1"]
	params: list = []
	party = _party_clause(as2_ids)
	if party:
		where = [party[0]]
		params.extend(party[1])
	sql = f"SELECT MIN(id) AS lo, MAX(id) AS hi FROM {TABLE_NAME} WHERE {' AND '.join(where)}"
	if "msg_data" in sql or "msg_headers" in sql or "mdn_response" in sql:
		raise RuntimeError("Refusing to select payload columns")
	return sql, params


def _status_by_type(counts: dict, success: dict, failure: dict) -> dict:
	"""One status group per EDI type. In progress is the remainder, not a second total."""
	status = {}
	for code in EDI_CARD_CODES:
		total = int(counts[code])
		ok = int(success[code])
		bad = int(failure[code])
		if ok < 0 or bad < 0 or ok + bad > total:
			raise ValueError("inconsistent EDI status count")
		status[code] = {
			"total": total,
			"success": ok,
			"failure": bad,
			"in_progress": total - ok - bad,
			"available": True,
		}
	return status


def merge_card_count_rows(rows) -> dict:
	"""Add per-range totals. Each row is one disjoint id range, so ids are not repeated."""
	counts = {code: 0 for code in EDI_CARD_CODES}
	last_7 = {code: 0 for code in EDI_CARD_CODES}
	previous_7 = {code: 0 for code in EDI_CARD_CODES}
	success = {code: 0 for code in EDI_CARD_CODES}
	failure = {code: 0 for code in EDI_CARD_CODES}
	for raw in rows or []:
		for code in EDI_CARD_CODES:
			counts[code] += _count_cell(raw, f"n{code}")
			last_7[code] += _count_cell(raw, f"d{code}")
			previous_7[code] += _count_cell(raw, f"p{code}")
			success[code] += _count_cell(raw, f"s{code}")
			failure[code] += _count_cell(raw, f"f{code}")
	return {
		"ok": True,
		"counts": counts,
		"last_7": last_7,
		"previous_7": previous_7,
		"status_by_type": _status_by_type(counts, success, failure),
	}


def _merge_raw_card_count_rows(*rows) -> dict:
	"""Sum disjoint SQL aggregation rows (``n204``, ``d204``, …) into one row."""
	out: dict[str, int] = {}
	for raw in rows:
		if not raw:
			continue
		for code in EDI_CARD_CODES:
			for prefix in ("n", "d", "p", "s", "f"):
				key = f"{prefix}{code}"
				out[key] = out.get(key, 0) + _count_cell(raw, key)
	return out


def _card_last_good_cache_key(cache_key: str) -> str:
	return f"{cache_key}:last"


def _cache_has_display_counts(cache_key: str | None) -> bool:
	if not cache_key:
		return False
	for key in (cache_key, _card_last_good_cache_key(cache_key)):
		parsed = valid_card_cache(_card_cache_get(key))
		if parsed and parsed.get("counts"):
			return True
	return False


def _card_scope_key(query_ids, last_7_start) -> str:
	if query_ids is None:
		scope = "*"
	else:
		scope = ",".join(sorted(str(item) for item in query_ids)) or "-"
	stamp = last_7_start.strftime("%Y%m%d%H%M%S")
	# v2 includes per-type Success / In Progress / Failure buckets.
	return f"oa2_edi_card_counts:v2:{stamp}:{scope}"


def valid_card_cache(payload):
	"""A successful remote aggregation, or None when the payload cannot be shown."""
	if not isinstance(payload, dict) or payload.get("ok") is not True:
		return None

	def cells(block):
		if not isinstance(block, dict):
			raise TypeError
		values = {}
		for code in EDI_CARD_CODES:
			value = block[code]
			if isinstance(value, bool) or not isinstance(value, int) or value < 0:
				raise TypeError
			values[code] = value
		return values

	try:
		computed = float(payload["computed_at"])
		parsed = {
			"ok": True,
			"counts": cells(payload.get("counts")),
			"last_7": cells(payload.get("last_7")),
			"previous_7": cells(payload.get("previous_7")),
			"computed_at": computed,
		}
	except (KeyError, TypeError, ValueError):
		return None
	try:
		parsed["status_by_type"] = _status_cells(payload.get("status_by_type"))
	except (KeyError, TypeError, ValueError):
		parsed["status_by_type"] = None
	return parsed


def _status_cells(block):
	"""Status buckets that sum to each type total, or None when they were not stored."""
	if block is None:
		return None
	if not isinstance(block, dict):
		raise TypeError
	parsed = {}
	for code in EDI_CARD_CODES:
		row = block[code]
		if not isinstance(row, dict):
			raise TypeError
		values = {}
		for name in ("total", "success", "in_progress", "failure"):
			value = row[name]
			if isinstance(value, bool) or not isinstance(value, int) or value < 0:
				raise TypeError
			values[name] = value
		if values["success"] + values["in_progress"] + values["failure"] != values["total"]:
			raise TypeError
		values["available"] = True
		parsed[code] = values
	return parsed


def card_cache_is_fresh(payload, now_ts) -> bool:
	try:
		return float(now_ts) - float(payload["computed_at"]) < CARD_CACHE_TTL_SECONDS
	except (KeyError, TypeError, ValueError):
		return False


def _card_cache_get(key: str):
	try:
		return frappe.cache().get_value(key)
	except Exception:
		return None


def _card_cache_set(key: str, value: dict, expires_in_sec: int = CARD_CACHE_KEEP_SECONDS) -> None:
	try:
		frappe.cache().set_value(key, value, expires_in_sec=expires_in_sec)
	except Exception as exc:
		_warn(f"OpenAS2 EDI card count could not be stored ({type(exc).__name__}).")


def _card_cache_delete(key: str) -> None:
	try:
		frappe.cache().delete_value(key)
	except Exception:
		return


def _card_lock_key(cache_key: str) -> str:
	return f"{cache_key}:lock"


def _lock_heartbeat(payload: dict | None) -> float:
	if not isinstance(payload, dict):
		return 0.0
	for name in ("heartbeat_at", "acquired_at"):
		try:
			return float(payload[name])
		except (KeyError, TypeError, ValueError):
			continue
	return 0.0


def _lock_is_stale(
	payload: dict | None,
	now: float | None = None,
	*,
	cache_key: str | None = None,
) -> bool:
	if not isinstance(payload, dict) or not payload.get("held"):
		return True
	now = time.time() if now is None else now
	heartbeat = _lock_heartbeat(payload)
	if heartbeat > now + 60:
		return True
	if now - heartbeat > CARD_LOCK_STALE_SECONDS:
		return True
	try:
		acquired = float(payload.get("acquired_at") or heartbeat)
	except (TypeError, ValueError):
		acquired = heartbeat
	if abs(heartbeat - acquired) < 5 and now - heartbeat > CARD_LOCK_ORPHAN_SECONDS:
		return True
	if cache_key and not _cache_has_display_counts(cache_key):
		if now - heartbeat > CARD_LOCK_NO_CACHE_IDLE_SECONDS:
			return True
	return False


def _scheduled_is_stale(payload: dict | None, now: float | None = None) -> bool:
	if not isinstance(payload, dict):
		return True
	now = time.time() if now is None else now
	try:
		started = float(payload.get("at") or 0)
	except (TypeError, ValueError):
		return True
	return now - started > CARD_SCHEDULED_STALE_SECONDS


def _clear_stale_card_lock(cache_key: str) -> bool:
	"""Drop an expired lock. Returns True when a stale lock was removed."""
	lock_key = _card_lock_key(cache_key)
	payload = _card_cache_get(lock_key)
	if payload is None:
		return False
	if not _lock_is_stale(payload, cache_key=cache_key):
		return False
	_card_cache_delete(lock_key)
	return True


def _prepare_card_refresh_lock(cache_key: str) -> None:
	_clear_stale_card_lock(cache_key)
	_clear_stale_card_scheduled(cache_key)


def _clear_stale_card_scheduled(cache_key: str) -> bool:
	sched_key = _card_refresh_scheduled_key(cache_key)
	payload = _card_cache_get(sched_key)
	if payload is None:
		return False
	if not _scheduled_is_stale(payload):
		return False
	_card_cache_delete(sched_key)
	return True


def _scheduled_refresh_is_orphaned(cache_key: str, now: float | None = None) -> bool:
	"""True when a schedule marker exists but no refresh is actually running."""
	now = time.time() if now is None else now
	sched_key = _card_refresh_scheduled_key(cache_key)
	sched_payload = _card_cache_get(sched_key)
	if not isinstance(sched_payload, dict):
		return False
	if _scheduled_is_stale(sched_payload, now):
		return True
	lock_payload = _card_cache_get(_card_lock_key(cache_key))
	if lock_payload is not None and not _lock_is_stale(lock_payload, now, cache_key=cache_key):
		return False
	if _cache_has_display_counts(cache_key):
		return False
	try:
		started = float(sched_payload.get("at") or 0)
	except (TypeError, ValueError):
		return True
	return now - started > CARD_SCHEDULED_ORPHAN_SECONDS


def _acquire_card_lock(key: str) -> bool:
	"""Take the refresh lock for this process, reclaiming only stale holders."""
	now = time.time()
	lock_key = _card_lock_key(key)
	existing = _card_cache_get(lock_key)
	if existing is not None:
		if not _lock_is_stale(existing, now, cache_key=key):
			return False
		_clear_stale_card_lock(key)
		existing = _card_cache_get(lock_key)
		if existing is not None and not _lock_is_stale(existing, now, cache_key=key):
			return False
	for _attempt in range(15):
		token = secrets.token_hex(16)
		payload = {"held": 1, "token": token, "acquired_at": now, "heartbeat_at": now}
		_card_cache_set(lock_key, payload, expires_in_sec=CARD_LOCK_CACHE_SECONDS)
		stored = _card_cache_get(lock_key)
		if isinstance(stored, dict) and stored.get("token") == token:
			_card_lock_state.token = token
			_card_lock_state.key = key
			return True
		time.sleep(0.1)
	return False


def _acquire_card_lock_force(key: str) -> bool:
	"""Take the refresh lock even when another holder exists (maintenance refresh only)."""
	now = time.time()
	lock_key = _card_lock_key(key)
	_card_cache_delete(lock_key)
	for _attempt in range(5):
		token = secrets.token_hex(16)
		payload = {"held": 1, "token": token, "acquired_at": now, "heartbeat_at": now}
		_card_cache_set(lock_key, payload, expires_in_sec=CARD_LOCK_CACHE_SECONDS)
		stored = _card_cache_get(lock_key)
		if isinstance(stored, dict) and stored.get("token") == token:
			_card_lock_state.token = token
			_card_lock_state.key = key
			return True
		time.sleep(0.05)
	return False


def _touch_card_lock(key: str) -> None:
	token = getattr(_card_lock_state, "token", None)
	if not token or getattr(_card_lock_state, "key", None) != key:
		return
	lock_key = _card_lock_key(key)
	stored = _card_cache_get(lock_key)
	if not isinstance(stored, dict) or stored.get("token") != token:
		return
	updated = dict(stored)
	updated["heartbeat_at"] = time.time()
	_card_cache_set(lock_key, updated, expires_in_sec=CARD_LOCK_CACHE_SECONDS)


def _release_card_lock(key: str) -> None:
	lock_key = _card_lock_key(key)
	token = getattr(_card_lock_state, "token", None)
	if token and getattr(_card_lock_state, "key", None) == key:
		stored = _card_cache_get(lock_key)
		if isinstance(stored, dict) and stored.get("token") == token:
			_card_cache_delete(lock_key)
	_card_lock_state.token = None
	_card_lock_state.key = None


def _card_refresh_scheduled_key(cache_key: str) -> str:
	return f"{cache_key}:scheduled"


def _card_refresh_error_key(cache_key: str) -> str:
	return f"{cache_key}:error"


def _clear_card_refresh_error(cache_key: str) -> None:
	_card_cache_delete(_card_refresh_error_key(cache_key))


def _store_card_refresh_error(cache_key: str, exc: Exception | None, *, skipped: bool = False) -> None:
	if skipped:
		return
	summary = _remote_error_summary(exc) if exc is not None else REMOTE_READ_ERROR
	_card_cache_set(
		_card_refresh_error_key(cache_key),
		{"at": time.time(), "message": summary or REMOTE_READ_ERROR},
		expires_in_sec=3600,
	)


def edi_card_read_error(cache_key: str | None = None) -> str | None:
	"""Last refresh failure for the dashboard reader, if any."""
	from openas2_manager.openas2.edi_dashboard_counts import panel_read_error

	return panel_read_error(cache_key or current_edi_card_cache_key())


def current_edi_card_cache_key(now=None) -> str | None:
	"""Cache key for the current user's EDI panel aggregation (v3), if scope is known."""
	from openas2_manager.openas2.edi_dashboard_counts import panel_cache_key

	return panel_cache_key(now)


def edi_card_refresh_in_progress(now=None) -> bool:
	"""True only while a v3 panel refresh holds a live (non-stale) lock."""
	from openas2_manager.openas2.edi_dashboard_counts import panel_refresh_in_progress

	return panel_refresh_in_progress(current_edi_card_cache_key(now))


def _store_edi_card_refresh_result(cache_key: str, result: dict) -> None:
	if result.get("ok"):
		stored = dict(result)
		stored["computed_at"] = time.time()
		_card_cache_set(cache_key, stored)
		_card_cache_set(_card_last_good_cache_key(cache_key), stored)
		_clear_card_refresh_error(cache_key)
		return
	_store_card_refresh_error(cache_key, None, skipped=bool(result.get("skipped")))
	if valid_card_cache(_card_cache_get(cache_key)) is None:
		_card_cache_delete(cache_key)


def run_edi_card_refresh_job(cache_key: str, user: str | None = None) -> None:
	"""Legacy RQ entry; forwards to the v3 panel refresh implementation."""
	from openas2_manager.openas2.edi_dashboard_counts import run_panel_refresh

	if user:
		frappe.set_user(user)
	frappe.flags.oa2_remote_read = True
	key = current_edi_card_cache_key() or cache_key
	run_panel_refresh(cache_key=key, force=False)


def _run_card_refresh_job(cache_key: str, *, user: str, site: str) -> None:
	"""Populate the EDI card cache in a daemon thread when no RQ worker is available."""
	try:
		frappe.init(site=site)
		frappe.connect()
		run_edi_card_refresh_job(cache_key, user=user)
	except Exception as exc:
		_store_card_refresh_error(cache_key, exc)
		_warn(f"OpenAS2 EDI card refresh failed ({type(exc).__name__}).")
	finally:
		try:
			frappe.db.close()
		except Exception:
			pass


def _edi_card_refresh_job_name(cache_key: str) -> str:
	digest = hashlib.sha256(cache_key.encode("utf-8")).hexdigest()[:32]
	return f"oa2_edi_cards_{digest}"


def _schedule_card_refresh(cache_key: str) -> None:
	"""Start one daemon-thread panel refresh (legacy name; v3 cache keys only)."""
	from openas2_manager.openas2.edi_dashboard_counts import schedule_panel_refresh

	schedule_panel_refresh(cache_key)


def count_edi_cards_fast(now=None) -> dict:
	"""Aggregate card totals in two SQL passes (file name, then payload-only rows).

	Uses the same classification rules as Monitoring. No primary-key chunking.
	"""
	if not remote_reads_enabled():
		return _failed_card_counts()
	settings, reason = read_settings()
	if not settings:
		_unavailable(reason)
		return _failed_card_counts()
	scope = resolve_scope()
	if scope is None:
		return _empty_card_counts()
	last_7_start, prev_7_start = _card_windows(now)
	secret = settings.get("password") or ""
	common = {
		"as2_ids": scope["query_ids"],
		"last_7_start": last_7_start,
		"prev_7_start": prev_7_start,
	}
	try:
		name_sql, name_params = build_edi_card_count_query_filename(**common)
		payload_sql, payload_params = build_edi_card_count_query_payload(**common)
		by_name = _execute_card_count_query(
			settings, name_sql, name_params, read_timeout=CARD_COUNT_READ_TIMEOUT
		)
		by_payload = _execute_card_count_query(
			settings, payload_sql, payload_params, read_timeout=CARD_COUNT_READ_TIMEOUT
		)
		return merge_card_count_rows([_merge_raw_card_count_rows(by_name, by_payload)])
	except Exception as exc:
		_unavailable(None, exc, secret)
		return _failed_card_counts()


def _peek_card_cache_keys(cache_key: str) -> dict | None:
	for key in (cache_key, _card_last_good_cache_key(cache_key)):
		parsed = valid_card_cache(_card_cache_get(key))
		if parsed and parsed.get("counts"):
			return parsed
	return None


def peek_edi_kpi_counts(now=None) -> dict:
	"""Return cached card totals for the Home KPI row. Never scans msg_metadata."""
	from openas2_manager.openas2.edi_dashboard_counts import read_panel_cache

	return read_panel_cache(now)


def build_edi_transactions_api_response(
	result: dict | None,
	*,
	cache_key: str | None = None,
	read_error: str | None = None,
) -> dict:
	"""Legacy test helper; chart HTTP responses use ``edi_home_chart.format_chart_response``."""
	from openas2_manager.openas2.edi_home_chart import format_chart_response

	refreshing = False
	if cache_key:
		try:
			from openas2_manager.openas2.edi_home_chart import chart_read_error

			refreshing = edi_card_refresh_in_progress()
			if not read_error:
				read_error = chart_read_error(cache_key)
		except RuntimeError:
			refreshing = False
	snapshot = None
	if result and result.get("ok") and result.get("status_by_type"):
		snapshot = {
			"status_by_type": result["status_by_type"],
			"computed_at": result.get("computed_at"),
		}
	if snapshot:
		return format_chart_response(snapshot)
	return format_chart_response(None, refreshing=refreshing, error=read_error)


def _execute_card_count_query(
	settings, sql: str, params: list, *, read_timeout: int = CARD_CHUNK_READ_TIMEOUT
) -> dict:
	conn = connect(settings, read_timeout=read_timeout)
	try:
		return _execute_card_count_query_on_conn(conn, sql, params, read_timeout=read_timeout)
	finally:
		conn.close()


def _execute_card_count_query_on_conn(
	conn, sql: str, params: list, *, read_timeout: int = CARD_CHUNK_READ_TIMEOUT
) -> dict:
	try:
		_execute(conn, "SET SESSION net_read_timeout = %s", [read_timeout])
	except Exception:
		pass
	records = _execute(conn, sql, params)
	return records[0] if records else {}


def _chunk_has_untyped_filename_rows(
	conn, as2_ids, id_from: int, id_to: int, *, read_timeout: int = CARD_COUNT_READ_TIMEOUT
) -> bool:
	"""True when this id range may need a payload ST read (Monitoring rules)."""
	where, where_params = _card_count_id_where(as2_ids=as2_ids, id_from=id_from, id_to=id_to)
	file_expr = "REGEXP_SUBSTR(IFNULL(file_name, ''), %s)"
	sql = (
		f"SELECT 1 AS hit FROM {TABLE_NAME} WHERE {' AND '.join(where)} "
		f"AND IFNULL({file_expr}, '') = '' LIMIT 1"
	)
	params = [_filename_type_pattern(), *where_params]
	try:
		_execute(conn, "SET SESSION net_read_timeout = %s", [min(read_timeout, 120)])
	except Exception:
		pass
	return bool(_execute(conn, sql, params))


def _card_count_chunk_on_conn(
	conn,
	as2_ids,
	last_7_start,
	prev_7_start,
	id_from: int,
	id_to: int,
	*,
	read_timeout: int = CARD_COUNT_READ_TIMEOUT,
):
	common = {
		"as2_ids": as2_ids,
		"last_7_start": last_7_start,
		"prev_7_start": prev_7_start,
	}
	name_sql, name_params = build_edi_card_count_query_filename(
		**common,
		id_from=id_from,
		id_to=id_to,
	)
	by_name = _execute_card_count_query_on_conn(
		conn, name_sql, name_params, read_timeout=read_timeout
	)
	if _chunk_has_untyped_filename_rows(conn, as2_ids, id_from, id_to, read_timeout=read_timeout):
		payload_sql, payload_params = build_edi_card_count_query_payload(
			**common,
			id_from=id_from,
			id_to=id_to,
		)
		by_payload = _execute_card_count_query_on_conn(
			conn, payload_sql, payload_params, read_timeout=read_timeout
		)
	else:
		by_payload = {}
	return _merge_raw_card_count_rows(by_name, by_payload)


def aggregate_edi_cards_chunked(
	now=None,
	*,
	cache_key: str | None = None,
	on_partial: callable | None = None,
) -> dict:
	"""Count the four EDI types over disjoint primary-key ranges on ``msg_metadata``.

	Each range is aggregated in SQL (file name, then payload ST when needed).
	``on_partial`` receives a merged snapshot after each range for cache progress.
	"""
	if not remote_reads_enabled():
		return _failed_card_counts()
	settings, reason = read_settings()
	if not settings:
		_unavailable(reason)
		return _failed_card_counts()
	scope = resolve_scope()
	if scope is None:
		return _empty_card_counts()
	last_7_start, prev_7_start = _card_windows(now)
	secret = settings.get("password") or ""
	read_timeout = CARD_COUNT_READ_TIMEOUT
	try:
		bounds_sql, bounds_params = build_card_bounds_query(scope["query_ids"])
		conn = connect(settings, read_timeout=read_timeout)
		try:
			try:
				_execute(conn, "SET SESSION net_read_timeout = %s", [read_timeout])
			except Exception as exc:
				_warn(
					"OpenAS2 remote count could not extend the read timeout "
					f"({_remote_error_summary(exc, secret)})."
				)
			bound_rows = _execute(conn, bounds_sql, bounds_params)
			bound = bound_rows[0] if bound_rows else {}
			low = bound.get("lo")
			high = bound.get("hi")
			if low is None or high is None:
				return _empty_card_counts()
			ranges = card_id_ranges(int(low), int(high))
			rows = []
			for id_from, id_to in ranges:
				try:
					rows.append(
						_card_count_chunk_on_conn(
							conn,
							scope["query_ids"],
							last_7_start,
							prev_7_start,
							id_from,
							id_to,
							read_timeout=read_timeout,
						)
					)
				except Exception as exc:
					_unavailable(None, exc, secret)
					if cache_key:
						_store_card_refresh_error(cache_key, exc)
					break
				if cache_key:
					_touch_card_lock(cache_key)
				if on_partial and rows:
					try:
						on_partial(merge_card_count_rows(list(rows)))
					except ValueError:
						pass
		finally:
			conn.close()
	except Exception as exc:
		_unavailable(None, exc, secret)
		if cache_key:
			_store_card_refresh_error(cache_key, exc)
		return _failed_card_counts()
	if not rows:
		return _failed_card_counts()
	try:
		return merge_card_count_rows(rows)
	except ValueError:
		_unavailable(None, Exception("inconsistent totals"), secret)
		return _failed_card_counts()


def count_edi_cards_chunked(now=None, *, cache_key: str | None = None) -> dict:
	"""Count the four card types over disjoint primary-key ranges."""
	return aggregate_edi_cards_chunked(now, cache_key=cache_key)


def _lock_holder_is_active(payload: dict | None, cache_key: str, now: float | None = None) -> bool:
	"""True only when another process is heartbeating a long-running refresh."""
	if not isinstance(payload, dict) or not payload.get("held"):
		return False
	now = time.time() if now is None else now
	if _lock_is_stale(payload, now, cache_key=cache_key):
		return False
	try:
		acquired = float(payload.get("acquired_at") or _lock_heartbeat(payload))
	except (TypeError, ValueError):
		acquired = _lock_heartbeat(payload)
	heartbeat = _lock_heartbeat(payload)
	return heartbeat - acquired > 15


def run_controlled_edi_card_refresh() -> dict:
	"""Run one EDI panel refresh for ops (delegates to ``edi_dashboard_counts``)."""
	from openas2_manager.openas2.edi_dashboard_counts import run_controlled_panel_refresh

	frappe.flags.oa2_remote_read = True
	return run_controlled_panel_refresh()


def refresh_edi_card_counts(cache_key: str | None = None) -> dict:
	"""Recompute panel counts (delegates to ``edi_dashboard_counts``)."""
	from openas2_manager.openas2.edi_dashboard_counts import run_panel_refresh

	force = bool(getattr(frappe.flags, "oa2_edi_card_refresh_force", False))
	return run_panel_refresh(cache_key=cache_key, force=force)


def _empty_card_counts() -> dict:
	zeros = {code: 0 for code in EDI_CARD_CODES}
	return {
		"ok": True,
		"counts": dict(zeros),
		"last_7": dict(zeros),
		"previous_7": dict(zeros),
		"status_by_type": _status_by_type(zeros, zeros, zeros),
	}


def _failed_card_counts() -> dict:
	missing = {code: None for code in EDI_CARD_CODES}
	return {"ok": False, "counts": missing, "last_7": dict(missing), "previous_7": dict(missing)}


def edi_card_counts(now=None) -> dict:
	"""Totals and seven-day windows for the four dashboard cards.

	``ok`` False leaves every count None. A successful query that matches
	nothing returns 0. Company and instance access use the message-list filter.
	"""
	if not remote_reads_enabled():
		return _failed_card_counts()
	settings, reason = read_settings()
	if not settings:
		_unavailable(reason)
		return _failed_card_counts()
	scope = resolve_scope()
	if scope is None:
		return _empty_card_counts()
	last_7_start, prev_7_start = _card_windows(now)
	sql, params = build_edi_card_count_query(
		as2_ids=scope["query_ids"],
		last_7_start=last_7_start,
		prev_7_start=prev_7_start,
	)
	secret = settings.get("password") or ""
	try:
		conn = connect(settings, read_timeout=CARD_COUNT_READ_TIMEOUT)
		try:
			try:
				_execute(conn, "SET SESSION net_read_timeout = %s", [CARD_COUNT_READ_TIMEOUT])
			except Exception as exc:
				_warn(
					"OpenAS2 remote count could not extend the read timeout "
					f"({_remote_error_summary(exc, secret)})."
				)
			records = _execute(conn, sql, params)
		finally:
			conn.close()
	except Exception as exc:
		_unavailable(None, exc, secret)
		return _failed_card_counts()
	raw = records[0] if records else {}
	try:
		return merge_card_count_rows([raw])
	except ValueError:
		_warn("OpenAS2 EDI card count returned inconsistent status totals.")
		return _failed_card_counts()


def _edi_204_kpi_cache_key(query_ids, last_7_start) -> str:
	if query_ids is None:
		scope = "*"
	else:
		scope = ",".join(sorted(str(item) for item in query_ids)) or "-"
	stamp = last_7_start.strftime("%Y%m%d%H%M%S")
	return f"oa2_edi_kpi_204:v1:{stamp}:{scope}"


def dashboard_edi_204_counts(now=None) -> dict:
	"""Cached total for EDI 204 using the same filter as the Monitoring list."""
	if not remote_reads_enabled():
		return {"ok": False, "error": REMOTE_READ_ERROR}
	scope = resolve_scope()
	if scope is None:
		return {"ok": True, "count": 0, "last_7": 0, "previous_7": 0}
	last_7_start, prev_7_start = _card_windows(now)
	key = _edi_204_kpi_cache_key(scope["query_ids"], last_7_start)
	cached = _card_cache_get(key)
	if isinstance(cached, dict) and cached.get("ok") and card_cache_is_fresh(cached, time.time()):
		return cached
	_clear_stale_card_lock(key)
	owned_lock = _acquire_card_lock(key)
	if not owned_lock:
		cached = _card_cache_get(key)
		if isinstance(cached, dict) and cached.get("ok"):
			return cached
	try:
		total = count_live_messages(transaction_type="204", read_timeout=CARD_COUNT_READ_TIMEOUT)
		if not total.get("ok"):
			return {"ok": False, "error": total.get("error") or REMOTE_READ_ERROR}
		result = {
			"ok": True,
			"count": int(total.get("total") or 0),
			"computed_at": time.time(),
		}
		_card_cache_set(key, result)
		return result
	except Exception as exc:
		_unavailable(None, exc, (read_settings()[0] or {}).get("password") or "")
		return {"ok": False, "error": REMOTE_READ_ERROR}
	finally:
		if owned_lock:
			_release_card_lock(key)


def bind_edi_204_load_tender_kpi(kpis: list[dict], now=None) -> None:
	"""Fill only the 204 Load Tender card from Monitoring-style remote counts."""
	data = dashboard_edi_204_counts(now=now)
	for card in kpis or []:
		if str(card.get("code") or "") != "204":
			continue
		card["label"] = "Load Tender"
		if not data.get("ok"):
			card["note"] = data.get("error") or EDI_TRANSACTION_COUNT_LIMITATION
			break
		card["count"] = int(data["count"])
		card["available"] = True
		if data.get("last_7") is not None:
			card["last_7"] = int(data["last_7"])
			card["change_pct"] = card_change_pct(card["last_7"], data.get("previous_7"))
		break


def _edi_990_kpi_cache_key(query_ids, last_7_start) -> str:
	if query_ids is None:
		scope = "*"
	else:
		scope = ",".join(sorted(str(item) for item in query_ids)) or "-"
	stamp = last_7_start.strftime("%Y%m%d%H%M%S")
	return f"oa2_edi_kpi_990:v1:{stamp}:{scope}"


def dashboard_edi_990_counts(now=None) -> dict:
	"""Cached total for EDI 990 using the same filter as the Monitoring list."""
	if not remote_reads_enabled():
		return {"ok": False, "error": REMOTE_READ_ERROR}
	scope = resolve_scope()
	if scope is None:
		return {"ok": True, "count": 0}
	last_7_start, _prev_7_start = _card_windows(now)
	key = _edi_990_kpi_cache_key(scope["query_ids"], last_7_start)
	cached = _card_cache_get(key)
	if isinstance(cached, dict) and cached.get("ok") and card_cache_is_fresh(cached, time.time()):
		return cached
	_clear_stale_card_lock(key)
	owned_lock = _acquire_card_lock(key)
	if not owned_lock:
		cached = _card_cache_get(key)
		if isinstance(cached, dict) and cached.get("ok"):
			return cached
	try:
		total = count_live_messages(transaction_type="990", read_timeout=CARD_COUNT_READ_TIMEOUT)
		if not total.get("ok"):
			return {"ok": False, "error": total.get("error") or REMOTE_READ_ERROR}
		result = {
			"ok": True,
			"count": int(total.get("total") or 0),
			"computed_at": time.time(),
		}
		_card_cache_set(key, result)
		return result
	except Exception as exc:
		_unavailable(None, exc, (read_settings()[0] or {}).get("password") or "")
		return {"ok": False, "error": REMOTE_READ_ERROR}
	finally:
		if owned_lock:
			_release_card_lock(key)


def bind_edi_990_ack_kpi(kpis: list[dict], now=None) -> None:
	"""Fill only the 990 Ack card from Monitoring-style remote counts."""
	data = dashboard_edi_990_counts(now=now)
	for card in kpis or []:
		if str(card.get("code") or "") != "990":
			continue
		card["label"] = "Ack"
		if not data.get("ok"):
			card["note"] = data.get("error") or EDI_TRANSACTION_COUNT_LIMITATION
			break
		card["count"] = int(data["count"])
		card["available"] = True
		if data.get("last_7") is not None:
			card["last_7"] = int(data["last_7"])
			card["change_pct"] = card_change_pct(card["last_7"], data.get("previous_7"))
		break


def _edi_210_kpi_cache_key(query_ids, last_7_start) -> str:
	if query_ids is None:
		scope = "*"
	else:
		scope = ",".join(sorted(str(item) for item in query_ids)) or "-"
	stamp = last_7_start.strftime("%Y%m%d%H%M%S")
	return f"oa2_edi_kpi_210:v1:{stamp}:{scope}"


def dashboard_edi_210_counts(now=None) -> dict:
	"""Cached total for EDI 210 using the same filter as the Monitoring list."""
	if not remote_reads_enabled():
		return {"ok": False, "error": REMOTE_READ_ERROR}
	scope = resolve_scope()
	if scope is None:
		return {"ok": True, "count": 0}
	last_7_start, _prev_7_start = _card_windows(now)
	key = _edi_210_kpi_cache_key(scope["query_ids"], last_7_start)
	cached = _card_cache_get(key)
	if isinstance(cached, dict) and cached.get("ok") and card_cache_is_fresh(cached, time.time()):
		return cached
	_clear_stale_card_lock(key)
	owned_lock = _acquire_card_lock(key)
	if not owned_lock:
		cached = _card_cache_get(key)
		if isinstance(cached, dict) and cached.get("ok"):
			return cached
	try:
		total = count_live_messages(transaction_type="210", read_timeout=CARD_COUNT_READ_TIMEOUT)
		if not total.get("ok"):
			return {"ok": False, "error": total.get("error") or REMOTE_READ_ERROR}
		result = {
			"ok": True,
			"count": int(total.get("total") or 0),
			"computed_at": time.time(),
		}
		_card_cache_set(key, result)
		return result
	except Exception as exc:
		_unavailable(None, exc, (read_settings()[0] or {}).get("password") or "")
		return {"ok": False, "error": REMOTE_READ_ERROR}
	finally:
		if owned_lock:
			_release_card_lock(key)


def bind_edi_210_invoice_kpi(kpis: list[dict], now=None) -> None:
	"""Fill only the 210 Invoice card from Monitoring-style remote counts."""
	data = dashboard_edi_210_counts(now=now)
	for card in kpis or []:
		if str(card.get("code") or "") != "210":
			continue
		card["label"] = "Invoice"
		if not data.get("ok"):
			card["note"] = data.get("error") or EDI_TRANSACTION_COUNT_LIMITATION
			break
		card["count"] = int(data["count"])
		card["available"] = True
		if data.get("last_7") is not None:
			card["last_7"] = int(data["last_7"])
			card["change_pct"] = card_change_pct(card["last_7"], data.get("previous_7"))
		break


def _edi_214_kpi_cache_key(query_ids, last_7_start) -> str:
	if query_ids is None:
		scope = "*"
	else:
		scope = ",".join(sorted(str(item) for item in query_ids)) or "-"
	stamp = last_7_start.strftime("%Y%m%d%H%M%S")
	return f"oa2_edi_kpi_214:v1:{stamp}:{scope}"


def dashboard_edi_214_counts(now=None) -> dict:
	"""Cached total for EDI 214 using the same filter as the Monitoring list."""
	if not remote_reads_enabled():
		return {"ok": False, "error": REMOTE_READ_ERROR}
	scope = resolve_scope()
	if scope is None:
		return {"ok": True, "count": 0}
	last_7_start, _prev_7_start = _card_windows(now)
	key = _edi_214_kpi_cache_key(scope["query_ids"], last_7_start)
	cached = _card_cache_get(key)
	if isinstance(cached, dict) and cached.get("ok") and card_cache_is_fresh(cached, time.time()):
		return cached
	_clear_stale_card_lock(key)
	owned_lock = _acquire_card_lock(key)
	if not owned_lock:
		cached = _card_cache_get(key)
		if isinstance(cached, dict) and cached.get("ok"):
			return cached
	try:
		total = count_live_messages(transaction_type="214", read_timeout=CARD_COUNT_READ_TIMEOUT)
		if not total.get("ok"):
			return {"ok": False, "error": total.get("error") or REMOTE_READ_ERROR}
		result = {
			"ok": True,
			"count": int(total.get("total") or 0),
			"computed_at": time.time(),
		}
		_card_cache_set(key, result)
		return result
	except Exception as exc:
		_unavailable(None, exc, (read_settings()[0] or {}).get("password") or "")
		return {"ok": False, "error": REMOTE_READ_ERROR}
	finally:
		if owned_lock:
			_release_card_lock(key)


def bind_edi_214_status_kpi(kpis: list[dict], now=None) -> None:
	"""Fill only the 214 Status card from Monitoring-style remote counts."""
	data = dashboard_edi_214_counts(now=now)
	for card in kpis or []:
		if str(card.get("code") or "") != "214":
			continue
		card["label"] = "Status"
		if not data.get("ok"):
			card["note"] = data.get("error") or EDI_TRANSACTION_COUNT_LIMITATION
			break
		card["count"] = int(data["count"])
		card["available"] = True
		if data.get("last_7") is not None:
			card["last_7"] = int(data["last_7"])
			card["change_pct"] = card_change_pct(card["last_7"], data.get("previous_7"))
		break


def bind_edi_card_counts(kpis: list[dict], now=None, counts: dict | None = None) -> list[dict]:
	"""Fill the existing cards from remote message counts.

	Labels, the count, and the seven-day percentage are updated. A failed
	read leaves the count empty. The cards themselves stay in the list.
	"""
	if counts is not None:
		result = counts
	elif now is not None:
		result = edi_card_counts(now=now)
	else:
		from openas2_manager.openas2.edi_dashboard_counts import read_panel_cache

		result = read_panel_cache()
	labels = {
		"204": "Load Tender",
		"990": "Ack",
		"210": "Invoice",
		"214": "Status",
	}
	for card in kpis or []:
		code = str(card.get("code") or "")
		if code in labels:
			card["label"] = labels[code]
		card["summary"] = ""
		if not result.get("ok"):
			card["count"] = None
			card["last_7"] = None
			card["change_pct"] = None
			card["available"] = False
			continue
		card["count"] = int(result["counts"].get(code) or 0)
		card["last_7"] = int(result["last_7"].get(code) or 0)
		card["change_pct"] = card_change_pct(card["last_7"], result["previous_7"].get(code))
		card["available"] = True
	return kpis


def bind_edi_status_chart(summary: dict, now=None, counts: dict | None = None) -> dict:
	"""Fill the EDI Transactions chart from the same message aggregation as the cards.

	The chart stays unavailable until every displayed type has status counts
	that sum to its total. A missing or failed read does not invent a split.
	"""
	if counts is not None:
		result = counts
	elif now is not None:
		result = edi_card_counts(now=now)
	else:
		from openas2_manager.openas2.edi_dashboard_counts import read_panel_cache

		result = read_panel_cache()
	status = result.get("status_by_type") if result.get("ok") else None
	if not status:
		return summary
	by_type = {}
	total = 0
	for code in EDI_CARD_CODES:
		row = status.get(code) or {}
		try:
			item = {
				"total": int(row["total"]),
				"success": int(row["success"]),
				"in_progress": int(row["in_progress"]),
				"failure": int(row["failure"]),
				"available": True,
			}
		except (KeyError, TypeError, ValueError):
			return summary
		if item["success"] + item["in_progress"] + item["failure"] != item["total"]:
			return summary
		if item["total"] < 0:
			return summary
		by_type[code] = item
		total += item["total"]
	summary["edi_status_by_type"] = by_type
	summary["edi_counts_available"] = True
	summary["edi_counts_limitation"] = ""
	summary["transactions_total"] = total
	return summary


def build_type_prefix_query(row_ids: list[int], as2_ids: list[str] | None) -> tuple[str, list]:
	"""One indexed read of the leading payload characters for known message ids.

	The monitoring list does not select ``msg_data``. Transaction detection uses
	this short prefix instead of loading a full payload per row.
	"""
	ids: list[int] = []
	for row_id in row_ids:
		if isinstance(row_id, bool) or not isinstance(row_id, int) or row_id < 1:
			continue
		if row_id not in ids:
			ids.append(row_id)
	if not ids:
		raise ValueError("invalid message id")
	holders = ", ".join(["%s"] * len(ids))
	where = [f"id IN ({holders})"]
	params: list = [PAYLOAD_PREVIEW_CHARS, *ids]
	party = _party_clause(as2_ids)
	if party:
		where.append(party[0])
		params.extend(party[1])
	sql = (
		"SELECT id, SUBSTRING(msg_data, 1, %s) AS msg_data "
		f"FROM {TABLE_NAME} WHERE {' AND '.join(where)}"
	)
	if "msg_headers" in sql or "mdn_response" in sql:
		raise RuntimeError("Refusing to select extra payload columns")
	return sql, params


def apply_payload_transaction_types(rows: list[dict], prefixes) -> None:
	"""Set Unknown rows from an ST segment in a payload prefix. Leave real misses Unknown."""
	found: dict[int, str] = {}
	for record in prefixes or []:
		try:
			row_id = int(record.get("id"))
		except (TypeError, ValueError):
			continue
		code = transaction_type_from_payload(_payload_text(record.get("msg_data")))
		if code:
			found[row_id] = code
	for row in rows or []:
		if (row.get("transaction_type") or "Unknown") != "Unknown":
			continue
		row_id = parse_remote_row_id(row.get("name"))
		if row_id is None:
			continue
		code = found.get(row_id)
		if code:
			row["transaction_type"] = code


def _fill_unknown_transaction_types(conn, rows: list[dict], as2_ids) -> None:
	"""Fill list rows whose filename has no transaction code. One prefix query."""
	ids: list[int] = []
	for row in rows or []:
		if (row.get("transaction_type") or "Unknown") != "Unknown":
			continue
		row_id = parse_remote_row_id(row.get("name"))
		if row_id is not None:
			ids.append(row_id)
	if not ids:
		return
	try:
		sql, params = build_type_prefix_query(ids, as2_ids)
		prefixes = _execute(conn, sql, params)
	except Exception:
		_warn("OpenAS2 transaction type preview could not be read.")
		return
	apply_payload_transaction_types(rows, prefixes)


def _date_bounds(date_from, date_to):
	from frappe.utils import get_datetime, getdate

	start = get_datetime(date_from) if date_from else None
	end = None
	if date_to:
		end = get_datetime(date_to)
		if isinstance(date_to, str) and len(str(date_to).strip()) <= 10:
			end = datetime.combine(getdate(date_to), datetime.max.time()).replace(microsecond=0)
	return start, end


def remote_message_details(name: str) -> dict | None:
	"""One remote row. None means the database could not be read.

	A query that succeeds with no row raises RemoteMessageNotFound.
	"""
	if not name or not str(name).startswith(REMOTE_NAME_PREFIX):
		return None
	raw_id = str(name)[len(REMOTE_NAME_PREFIX) :]
	if not raw_id.isdigit():
		return None
	if not remote_reads_enabled():
		return None
	settings, reason = read_settings()
	if not settings:
		_unavailable(reason)
		return None
	scope = resolve_scope()
	if scope is None:
		raise RemoteAccessDenied()
	sql, params = build_detail_query(int(raw_id), scope["query_ids"])
	try:
		conn = connect(settings)
		try:
			records = _execute(conn, sql, params)
		finally:
			conn.close()
	except Exception as exc:
		_unavailable(None, exc)
		return None
	if not records:
		raise RemoteMessageNotFound()
	record = records[0]
	parties = assign_parties(
		record,
		instances_by_as2=scope["instances_by_as2"],
		allowed_as2=scope["allowed_as2"],
		preferred_as2=[],
	)
	if not parties:
		raise RemoteAccessDenied()
	row = to_message_row(record, parties, scope.get("partners_by_as2"))
	row["read_only"] = True
	row["edi_document_route"] = None
	return row


def _edi_payload_result(label: str, text: str, chars: int, full: bool = False) -> dict:
	"""Raw view text: each X12 attachment from ISA through IEA, or a clear miss.

	A non-MIME body that is not a complete interchange is returned unchanged so
	short previews keep their original text. MIME and AS2 wrappers are not shown
	as EDI.
	"""
	from openas2_manager.openas2.x12_json import _looks_like_mime, extract_edi_interchanges

	interchanges = extract_edi_interchanges(text)
	if interchanges:
		shown = interchanges[0] if len(interchanges) == 1 else "\n\n".join(interchanges)
		return {
			"name": label,
			"payload": shown,
			"available": True,
			"reason": "",
			"payload_chars": len(shown),
			"transaction_type": transaction_type_from_payload(shown),
		}
	wrapped = _looks_like_mime(text)
	if not full and chars > len(text) and (wrapped or text.lstrip().startswith("ISA")):
		return {
			"name": label,
			"payload": "",
			"available": False,
			"reason": "truncated",
			"payload_chars": chars,
			"transaction_type": transaction_type_from_payload(text),
		}
	if wrapped:
		return {
			"name": label,
			"payload": "",
			"available": False,
			"reason": "not_edi",
			"payload_chars": chars,
			"transaction_type": "",
			"message": "This message does not contain an X12 EDI attachment.",
		}
	return {
		"name": label,
		"payload": text,
		"available": True,
		"reason": "",
		"payload_chars": chars,
		"transaction_type": transaction_type_from_payload(text),
	}


def remote_message_payload(name: str, full: bool = False) -> dict | None:
	"""EDI preview for one remote row.

	None means the remote database could not be read. The payload is never logged.
	``full`` raises the read cap from the preview length to PAYLOAD_FULL_CHARS.
	"""
	row_id = parse_remote_row_id(name)
	if row_id is None:
		raise ValueError("invalid message id")
	if not remote_reads_enabled():
		return None
	settings, reason = read_settings()
	if not settings:
		_unavailable(reason)
		return None
	scope = resolve_scope()
	if scope is None:
		raise RemoteAccessDenied()
	sql, params = build_payload_query(
		row_id,
		scope["query_ids"],
		PAYLOAD_FULL_CHARS if full else None,
	)
	try:
		conn = connect(settings)
		try:
			records = _execute(conn, sql, params)
		finally:
			conn.close()
	except Exception as exc:
		_unavailable(None, exc)
		return None
	label = f"{REMOTE_NAME_PREFIX}{row_id}"
	if not records:
		return {
			"name": label,
			"payload": "",
			"available": False,
			"reason": "not_found",
			"payload_chars": 0,
			"transaction_type": "",
		}
	record = records[0]
	parties = assign_parties(
		record,
		instances_by_as2=scope["instances_by_as2"],
		allowed_as2=scope["allowed_as2"],
		preferred_as2=[],
	)
	if not parties:
		raise RemoteAccessDenied()
	text = _payload_text(record.get("msg_data"))
	chars = int(record.get("payload_chars") or 0)
	if chars <= 0 or not text.strip():
		return {
			"name": label,
			"payload": "",
			"available": False,
			"reason": "empty",
			"payload_chars": 0,
			"transaction_type": "",
		}
	return _edi_payload_result(label, text, chars, full=full)


def dashboard_activity() -> dict | None:
	"""Latest remote messages, or None when the database could not be read."""
	if not remote_reads_enabled():
		return None
	settings, reason = read_settings()
	if not settings:
		_unavailable(reason)
		return None
	scope = resolve_scope()
	if scope is None:
		return {"rows_today": [], "recent": []}

	recent_sql, recent_params = build_list_query(
		as2_ids=scope["query_ids"],
		limit=RECENT_ROW_LIMIT,
	)
	try:
		conn = connect(settings)
		try:
			# create_dt is not indexed on the live table. Counting today's rows
			# would read every metadata row and hit the socket timeout.
			summary_rows = None
			if _column_indexed(conn, "create_dt"):
				from frappe.utils import getdate, now_datetime

				start_today = datetime.combine(getdate(now_datetime()), datetime.min.time())
				summary_sql, summary_params = build_summary_query(
					as2_ids=scope["query_ids"],
					date_from=start_today,
				)
				summary_rows = _execute(conn, summary_sql, summary_params)
			recent_records = _execute(conn, recent_sql, recent_params)
			# Filename or an already stored code wins. Remaining rows use one
			# short payload prefix so the list query never selects msg_data.
			recent = _map_records(recent_records, scope)
			_fill_unknown_transaction_types(conn, recent, scope.get("query_ids"))
		finally:
			conn.close()
	except Exception as exc:
		_unavailable(None, exc)
		return None

	counts = None
	if summary_rows is not None:
		raw_counts = summary_rows[0] if summary_rows else {}
		counts = {
			"messages_today": int(raw_counts.get("messages_today") or 0),
			"inbound": int(raw_counts.get("inbound") or 0),
			"outbound": int(raw_counts.get("outbound") or 0),
			"successful": int(raw_counts.get("successful") or 0),
			"processed": int(raw_counts.get("processed") or 0),
			"failed": int(raw_counts.get("failed") or 0),
			"pending_mdn": int(raw_counts.get("pending_mdn") or 0),
		}
	for row in recent:
		row["transaction_type_label"] = format_transaction_type_label(row.get("transaction_type"))
	recent = [frappe._dict(row) for row in recent]
	return {"rows_today": [], "recent": recent, "counts": counts}
