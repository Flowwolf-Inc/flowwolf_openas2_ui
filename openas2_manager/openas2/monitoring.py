# Copyright (c) 2026, Lakshana and contributors
# For license information, please see license.txt

"""OpenAS2 message / error monitoring.

Visible message lists read the remote ``msg_metadata`` table. Refresh re-reads
that table and does not copy files into OpenAS2 Message Log. TMS EDI sync and
the on-disk log parser remain available for their own sources.
Never modifies OpenAS2 files, config.xml, partnerships.xml, or payloads.
Never sends, resends, deletes, or restarts.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path

import frappe
from frappe.utils import get_datetime, getdate, now_datetime

from openas2_manager.openas2.config_viewer import (
	resolve_openas2_home,
	safe_display_source,
)

TRANSACTION_TYPES = ("204", "990", "214", "210", "810", "820")
MAX_LOG_FILES = 14
MAX_LOG_BYTES = 2_000_000
MAX_ERROR_TEXT = 800

SENSITIVE_PATTERNS = []  # kept for tests / extension; redact_sensitive uses explicit subs

LOG_LINE_RE = re.compile(
	r"^(?P<time>\d{2}:\d{2}:\d{2}\.\d{3})\s+\["
	r"(?P<thread>[^\]]+)\]\s+"
	r"(?P<level>\w+)\s+"
	r"(?P<logger>\S+)\s+--\s+"
	r"(?P<body>.*)$"
)
MSG_ID_IN_LINE_RE = re.compile(r"(\<[^\>]+\>)")
MSG_ID_BODY_RE = re.compile(r"^(\d{14}[+-]\d{4})-(\d+)-(.+)$")
TXN_RE = re.compile(r"(?:^|[_\-.])(204|990|214|210|810|820)(?:[_\-.]|$)", re.I)
INBOX_NAME_RE = re.compile(r"^([A-Za-z0-9_]+)-(\d+)-(.+)$")


def redact_sensitive(text: str | None) -> str:
	"""Remove password-like tokens from monitoring text."""
	if not text:
		return ""
	out = str(text)
	out = re.sub(r"(?i)(password|passwd|pwd)\s*[:=]\s*\S+", r"\1=[REDACTED]", out)
	out = re.sub(
		r"(?i)(storepass|keypass|secret|private[_\s-]?key)\s*[:=]\s*\S+",
		r"\1=[REDACTED]",
		out,
	)
	out = re.sub(r"(?i)jdbc:\S+", "jdbc:[REDACTED]", out)
	return out[:MAX_ERROR_TEXT]


def extract_transaction_type(file_name: str | None) -> str:
	if not file_name:
		return "Unknown"
	match = TXN_RE.search(file_name)
	return match.group(1) if match else "Unknown"


def normalize_message_id(message_id: str | None) -> str:
	"""Store Message-ID without angle brackets (Desk Data fields strip HTML-like tags)."""
	if not message_id:
		return ""
	return message_id.strip().strip("<>")[:240]


def display_message_id(message_id: str | None) -> str:
	mid = normalize_message_id(message_id)
	return f"<{mid}>" if mid else ""


def parse_message_id_parts(message_id: str, known_as2_ids: list[str] | None = None) -> dict:
	"""Parse OpenAS2 Message-ID into sender/receiver/filename when possible."""
	raw = normalize_message_id(message_id)
	match = MSG_ID_BODY_RE.match(raw)
	if not match:
		return {"sender": None, "receiver": None, "file_name": None}
	rest = match.group(3)
	ids = sorted({i for i in (known_as2_ids or []) if i}, key=len, reverse=True)
	for sender in ids:
		prefix = f"{sender}_"
		if not rest.startswith(prefix):
			continue
		rem = rest[len(prefix) :]
		for receiver in ids:
			rprefix = f"{receiver}_"
			if rem.startswith(rprefix):
				return {
					"sender": sender,
					"receiver": receiver,
					"file_name": rem[len(rprefix) :],
				}
	# Fallback: last underscore-separated segment as filename heuristic
	parts = rest.rsplit("_", 1)
	if len(parts) == 2:
		return {"sender": None, "receiver": None, "file_name": parts[1]}
	return {"sender": None, "receiver": None, "file_name": rest}


def _assert_under_home(home: Path, target: Path) -> None:
	try:
		target.resolve().relative_to(home.resolve())
	except ValueError:
		frappe.throw(frappe._("Refusing path outside OpenAS2 home: {0}").format(target))


def _combine_log_timestamp(log_date: str, time_part: str) -> datetime | None:
	"""log_date YYYYMMDD + HH:mm:ss.SSS → datetime."""
	try:
		base = datetime.strptime(log_date, "%Y%m%d")
		hh, mm, rest = time_part.split(":")
		ss, ms = rest.split(".")
		return base.replace(
			hour=int(hh), minute=int(mm), second=int(ss), microsecond=int(ms) * 1000
		)
	except (ValueError, TypeError):
		return None


def list_log_files(home: Path) -> list[Path]:
	logs_dir = home / "logs"
	if not logs_dir.is_dir():
		return []
	files = sorted(logs_dir.glob("log-*.txt"), reverse=True)
	return files[:MAX_LOG_FILES]


def parse_log_file(
	path: Path,
	*,
	home: Path,
	instance_as2_id: str | None = None,
	known_as2_ids: list[str] | None = None,
) -> tuple[dict[str, dict], list[dict]]:
	"""Parse one OpenAS2 log file.

	Returns (messages_by_id, orphan_errors).
	Never writes to the log file.
	"""
	_assert_under_home(home, path)
	messages: dict[str, dict] = {}
	orphan_errors: list[dict] = []
	last_message_id = ""

	name = path.name  # log-YYYYMMDD.txt
	date_match = re.match(r"log-(\d{8})\.txt$", name)
	if not date_match:
		return messages, orphan_errors
	log_date = date_match.group(1)

	try:
		# Bound read size; open read-only (never write).
		with path.open("r", encoding="utf-8", errors="replace") as handle:
			assert handle.mode.startswith("r") and not any(c in handle.mode for c in "wax+")
			raw = handle.read(MAX_LOG_BYTES)
	except OSError as exc:
		orphan_errors.append(
			{
				"timestamp": None,
				"status": "Failed",
				"error_message": redact_sensitive(f"Unreadable log: {path.name}: {exc}"),
				"source": "OpenAS2 log",
				"raw_reference": safe_display_source(path),
				"file_name": path.name,
				"direction": None,
				"message_id": "",
			}
		)
		return messages, orphan_errors

	for line in raw.splitlines():
		m = LOG_LINE_RE.match(line.strip())
		if not m:
			continue
		level = m.group("level").upper()
		body = m.group("body")
		ts = _combine_log_timestamp(log_date, m.group("time"))
		ids_found = MSG_ID_IN_LINE_RE.findall(body)
		message_id = normalize_message_id(ids_found[-1] if ids_found else "")
		lower = body.lower()
		if not message_id and last_message_id and (
			"mdn received successfully" in lower or "message sent and response received" in lower
		):
			message_id = last_message_id
		if message_id:
			last_message_id = message_id
		is_error = level == "ERROR" or "failed" in lower or "exception" in lower

		if not message_id:
			if is_error and not any(
				skip in lower for skip in ("retrieving config", "loading configuration")
			):
				# Skip noisy DB bootstrap / empty-table noise unless useful
				if "msg_metadata" in lower and "not found" in lower:
					continue
				orphan_errors.append(
					{
						"timestamp": ts,
						"status": "Failed",
						"error_message": redact_sensitive(body),
						"source": "OpenAS2 log",
						"raw_reference": safe_display_source(path),
						"file_name": None,
						"direction": None,
						"message_id": "",
						"transaction_type": "Unknown",
					}
				)
			continue

		rec = messages.setdefault(
			message_id,
			{
				"message_id": message_id,
				"timestamp": ts,
				"direction": None,
				"status": "Unknown",
				"mdn_status": "Unknown",
				"file_name": None,
				"local_as2_id": instance_as2_id,
				"remote_as2_id": None,
				"error_message": "",
				"source": "OpenAS2 log",
				"raw_reference": safe_display_source(path),
				"events": [],
			},
		)
		if ts and (not rec["timestamp"] or ts > rec["timestamp"]):
			rec["timestamp"] = ts
		rec["events"].append(lower)

		parts = parse_message_id_parts(message_id, known_as2_ids)
		if parts.get("file_name") and not rec["file_name"]:
			rec["file_name"] = parts["file_name"]
		if instance_as2_id and parts.get("sender") and parts.get("receiver"):
			if parts["sender"] == instance_as2_id:
				rec["direction"] = "Outbound"
				rec["local_as2_id"] = parts["sender"]
				rec["remote_as2_id"] = parts["receiver"]
			elif parts["receiver"] == instance_as2_id:
				rec["direction"] = "Inbound"
				rec["local_as2_id"] = parts["receiver"]
				rec["remote_as2_id"] = parts["sender"]

		if "file assigned to message" in lower or "processing file for sending" in lower:
			rec["direction"] = rec["direction"] or "Outbound"
			rec["status"] = "Sent" if rec["status"] in (None, "Unknown") else rec["status"]
		if "connecting to:" in lower or "message sent and response received" in lower:
			rec["direction"] = "Outbound"
			if rec["status"] not in ("Success", "Failed", "Duplicate"):
				rec["status"] = "Sent"
		if "stored message to" in lower or "received " in lower and "bytes" in lower:
			rec["direction"] = rec["direction"] or "Inbound"
			if rec["status"] not in ("Success", "Failed", "Duplicate"):
				rec["status"] = "Received"
		if "mdn received successfully" in lower or "; processed]" in lower:
			rec["mdn_status"] = "Received"
			if rec["direction"] == "Outbound":
				rec["status"] = "Success"
			elif rec["status"] in ("Received", "Unknown", "Sent"):
				# inbound with MDN sent OK often logged similarly
				if "mdn" in lower and "sent" in lower:
					rec["status"] = "Success"
		if "pending mdn" in lower and "deleted" in lower:
			rec["mdn_status"] = "Received"
		if "duplicate" in lower:
			rec["status"] = "Duplicate"
		if is_error:
			rec["status"] = "Failed"
			rec["error_message"] = redact_sensitive(body)
			if "mdn" in lower:
				rec["mdn_status"] = "Failed"

	# Finalize defaults
	for rec in messages.values():
		rec.pop("events", None)
		rec["transaction_type"] = extract_transaction_type(rec.get("file_name"))
		if rec.get("mdn_status") == "Unknown" and rec.get("status") == "Success":
			rec["mdn_status"] = "Received"
		if rec.get("status") == "Sent" and rec.get("mdn_status") == "Unknown":
			rec["mdn_status"] = "Pending"

	return messages, orphan_errors


def _is_recent_file(path: Path, *, days: int = 2, minutes: int | None = None) -> bool:
	try:
		mtime = datetime.fromtimestamp(path.stat().st_mtime)
	except OSError:
		return False
	if minutes is not None:
		return mtime >= datetime.now() - timedelta(minutes=minutes)
	return mtime >= datetime.now() - timedelta(days=days)


def _type_from_edi_file(path: Path) -> str:
	txn = extract_transaction_type(path.name)
	if txn != "Unknown":
		return txn
	try:
		if path.stat().st_size > 2_000_000:
			return "Unknown"
	except OSError:
		return "Unknown"
	peeked, _text = _read_edi_file(path)
	return peeked or "Unknown"


def scan_inbox_files(home: Path, instance_as2_id: str | None, recent_only: bool = False) -> list[dict]:
	"""Discover inbound files under data/inbox/{local}/inbox/{pending|processed|error}."""
	results = []
	inbox_root = home / "data" / "inbox"
	if not inbox_root.is_dir():
		return results

	status_folders = (
		("inbox", "Received"),
		("processed", "Success"),
		("error", "Failed"),
	)

	for local_dir in inbox_root.iterdir():
		if not local_dir.is_dir():
			continue
		local_id = local_dir.name
		base = local_dir / "inbox"
		if not base.is_dir():
			continue
		for folder_name, status in status_folders:
			folder = base if folder_name == "inbox" else base / folder_name
			if not folder.is_dir():
				continue
			try:
				entries = list(folder.iterdir())
			except OSError:
				continue
			for entry in entries:
				if not entry.is_file():
					continue
				if recent_only and not _is_recent_file(entry, minutes=3):
					continue
				try:
					_assert_under_home(home, entry)
				except Exception:
					continue
				remote = None
				file_name = entry.name
				m = INBOX_NAME_RE.match(entry.name)
				if m:
					remote = m.group(1)
					file_name = m.group(3)
				try:
					ts = datetime.fromtimestamp(entry.stat().st_mtime)
				except OSError:
					ts = now_datetime()
				results.append(
					{
						"message_id": "",
						"timestamp": ts,
						"direction": "Inbound",
						"status": status,
						"mdn_status": "Unknown",
						"file_name": file_name,
						"local_as2_id": local_id or instance_as2_id,
						"remote_as2_id": remote,
						"error_message": "Inbox error folder" if status == "Failed" else "",
						"source": "Inbox",
						"raw_reference": safe_display_source(entry),
						"transaction_type": _type_from_edi_file(entry) if extract_transaction_type(file_name) == "Unknown" else extract_transaction_type(file_name),
					}
				)
	return results


def scan_outbox_error_files(home: Path, instance_as2_id: str | None, recent_only: bool = False) -> list[dict]:
	"""Discover failed outbound files under data/outbox/error/."""
	results = []
	error_root = home / "data" / "outbox" / "error"
	if not error_root.is_dir():
		return results
	for day_dir in error_root.iterdir():
		if not day_dir.is_dir():
			continue
		if recent_only and not _is_recent_file(day_dir, days=3) and day_dir.name < (now_datetime() - timedelta(days=2)).strftime("%Y-%m-%d"):
			continue
		for remote_dir in day_dir.iterdir():
			if not remote_dir.is_dir():
				continue
			for entry in remote_dir.iterdir():
				if not entry.is_file():
					continue
				_assert_under_home(home, entry)
				mid = normalize_message_id(entry.name)
				parts = parse_message_id_parts(
					mid, [instance_as2_id, remote_dir.name] if instance_as2_id else [remote_dir.name]
				)
				try:
					ts = datetime.strptime(day_dir.name, "%Y-%m-%d")
				except ValueError:
					ts = datetime.fromtimestamp(entry.stat().st_mtime)
				results.append(
					{
						"message_id": mid if mid.startswith("<") else normalize_message_id(entry.name),
						"timestamp": ts,
						"direction": "Outbound",
						"status": "Failed",
						"mdn_status": "Failed",
						"file_name": parts.get("file_name") or entry.name,
						"local_as2_id": instance_as2_id or parts.get("sender"),
						"remote_as2_id": remote_dir.name,
						"error_message": "Outbound file in outbox/error",
						"source": "Outbox",
						"raw_reference": safe_display_source(entry),
						"transaction_type": extract_transaction_type(
							parts.get("file_name") or entry.name
						),
					}
				)
	return results


def find_partnership(instance_name: str, local_as2_id: str | None, remote_as2_id: str | None):
	if not local_as2_id or not remote_as2_id:
		return None
	name = frappe.db.get_value(
		"OpenAS2 Partnership",
		{
			"instance": instance_name,
			"local_as2_id": local_as2_id,
			"remote_as2_id": remote_as2_id,
		},
		"name",
	)
	return name


def find_related_edi_document(
	file_name: str | None,
	message_id: str | None = None,
	*,
	instance: str | None = None,
) -> str | None:
	"""Soft-link to EDI Document (local TMS DocType or mirrored OpenAS2 EDI Document)."""
	if frappe.db.exists("DocType", "EDI Document"):
		if file_name:
			name = frappe.db.get_value("EDI Document", {"file_name": file_name}, "name")
			if name:
				return name
		if message_id and frappe.db.has_column("EDI Document", "as2_message_id"):
			name = frappe.db.get_value("EDI Document", {"as2_message_id": message_id}, "name")
			if name:
				return name

	if frappe.db.exists("DocType", "OpenAS2 EDI Document"):
		from openas2_manager.openas2.tms_edi import find_mirrored_edi_document

		mirror = find_mirrored_edi_document(file_name, message_id, instance=instance)
		if mirror:
			return mirror.tms_doc_name
	return None


def _find_existing_log(instance_name: str, message_id: str, raw_reference: str | None) -> str | None:
	if message_id:
		return frappe.db.get_value(
			"OpenAS2 Message Log",
			{"instance": instance_name, "message_id": message_id},
			"name",
		)
	if raw_reference:
		return frappe.db.get_value(
			"OpenAS2 Message Log",
			{"instance": instance_name, "raw_reference": raw_reference},
			"name",
		)
	return None


def upsert_message_log(instance_name: str, data: dict) -> str:
	"""Insert or update a monitoring row. Does not store EDI payloads."""
	message_id = normalize_message_id(data.get("message_id"))
	raw_reference = (data.get("raw_reference") or "")[:255]
	existing = _find_existing_log(instance_name, message_id, raw_reference)

	partner = data.get("partner") or find_partnership(
		instance_name, data.get("local_as2_id"), data.get("remote_as2_id")
	)
	edi_doc = data.get("edi_document") or find_related_edi_document(
		data.get("file_name"), message_id, instance=instance_name
	)

	payload = {
		"instance": instance_name,
		"direction": data.get("direction") or "",
		"partner": partner,
		"local_as2_id": data.get("local_as2_id") or "",
		"remote_as2_id": data.get("remote_as2_id") or "",
		"transaction_type": data.get("transaction_type")
		or extract_transaction_type(data.get("file_name")),
		"message_id": message_id,
		"status": data.get("status") or "Unknown",
		"mdn_status": data.get("mdn_status") or "Unknown",
		"timestamp": data.get("timestamp") or now_datetime(),
		"file_name": (data.get("file_name") or "")[:140],
		"source": (data.get("source") or "OpenAS2 log")[:140],
		"raw_reference": raw_reference,
		"edi_document": edi_doc or "",
		"error_message": redact_sensitive(data.get("error_message")),
	}
	payload["summary"] = (
		f"{payload['direction'] or '?'} {payload['transaction_type']} "
		f"{payload['status']} {payload['file_name'] or payload['message_id']}"
	)[:140]

	if existing:
		doc = frappe.get_doc("OpenAS2 Message Log", existing)
		# Prefer stronger statuses
		rank = {
			"Unknown": 0,
			"Received": 1,
			"Sent": 2,
			"Pending": 2,
			"Success": 3,
			"Duplicate": 3,
			"Failed": 4,
		}
		if rank.get(payload["status"], 0) >= rank.get(doc.status or "Unknown", 0):
			doc.status = payload["status"]
		if payload["mdn_status"] and payload["mdn_status"] != "Unknown":
			doc.mdn_status = payload["mdn_status"]
		for key in (
			"direction",
			"partner",
			"local_as2_id",
			"remote_as2_id",
			"transaction_type",
			"file_name",
			"source",
			"raw_reference",
			"edi_document",
			"summary",
		):
			if payload.get(key):
				if (
					key == "transaction_type"
					and payload.get(key) == "Unknown"
					and doc.transaction_type
					and doc.transaction_type != "Unknown"
				):
					continue
				setattr(doc, key, payload[key])
		if payload["error_message"]:
			doc.error_message = payload["error_message"]
		if payload["timestamp"] and (
			not doc.timestamp or get_datetime(payload["timestamp"]) >= get_datetime(doc.timestamp)
		):
			doc.timestamp = payload["timestamp"]
		doc.flags.ignore_permissions = True
		doc.flags.ignore_version = True
		doc.save(ignore_permissions=True)
		return doc.name

	doc = frappe.get_doc({"doctype": "OpenAS2 Message Log", **payload})
	doc.flags.ignore_permissions = True
	doc.insert(ignore_permissions=True)
	return doc.name


def discover_instance_messages(instance, recent_only: bool = False, log_only: bool = False) -> dict:
	"""Read-only discovery for one OpenAS2 Instance."""
	stats = {"messages": 0, "errors": 0, "missing_logs": False, "notes": []}
	try:
		home = resolve_openas2_home(instance).resolve()
	except Exception as exc:
		stats["notes"].append(str(exc))
		return stats

	if not home.is_dir():
		stats["notes"].append(f"OpenAS2 home not found: {safe_display_source(home)}")
		stats["missing_logs"] = True
		return stats

	known = frappe.get_all("OpenAS2 Instance", pluck="as2_id")
	known = [k for k in known if k]
	if instance.as2_id and instance.as2_id not in known:
		known.append(instance.as2_id)

	log_files = list_log_files(home)
	if recent_only:
		log_files = log_files[:1]
	if not log_files:
		stats["missing_logs"] = True
		stats["notes"].append("No OpenAS2 log files found under logs/")

	aggregated: dict[str, dict] = {}
	for log_path in log_files:
		try:
			msgs, orphans = parse_log_file(
				log_path,
				home=home,
				instance_as2_id=instance.as2_id,
				known_as2_ids=known,
			)
		except OSError as exc:
			upsert_message_log(
				instance.name,
				{
					"status": "Failed",
					"error_message": f"Unreadable log: {exc}",
					"source": "OpenAS2 log",
					"raw_reference": safe_display_source(log_path),
					"direction": "",
					"transaction_type": "Unknown",
				},
			)
			stats["errors"] += 1
			continue
		for mid, rec in msgs.items():
			prev = aggregated.get(mid)
			if not prev:
				aggregated[mid] = rec
			else:
				# merge preferring Failed/Success
				if rec.get("status") == "Failed" or prev.get("status") != "Failed":
					if rec.get("status") in ("Failed", "Success", "Duplicate") or prev.get(
						"status"
					) in ("Unknown", "Received", "Sent"):
						prev["status"] = rec.get("status") or prev.get("status")
				if rec.get("mdn_status") in ("Received", "Failed"):
					prev["mdn_status"] = rec["mdn_status"]
				for k in (
					"direction",
					"file_name",
					"local_as2_id",
					"remote_as2_id",
					"error_message",
					"timestamp",
				):
					if rec.get(k):
						prev[k] = rec[k]
		for orphan in orphans:
			stamp = orphan.get("timestamp")
			if recent_only and stamp and stamp < datetime.now() - timedelta(minutes=3):
				continue
			upsert_message_log(instance.name, orphan)
			stats["errors"] += 1

	fresh_after = datetime.now() - timedelta(minutes=3) if recent_only else None
	for rec in aggregated.values():
		if fresh_after is not None:
			stamp = rec.get("timestamp")
			if stamp and stamp < fresh_after:
				continue
		upsert_message_log(instance.name, rec)
		if log_only:
			_ensure_edi_from_log(instance, rec)
		stats["messages"] += 1

	if log_only:
		stats["edi_documents"] = stats["messages"]
		return stats

	for rec in scan_inbox_files(home, instance.as2_id, recent_only=recent_only):
		# Prefer message_id matches from logs; otherwise path-based
		if rec.get("message_id"):
			upsert_message_log(instance.name, rec)
		else:
			upsert_message_log(instance.name, rec)
		stats["messages"] += 1

	for rec in scan_outbox_error_files(home, instance.as2_id, recent_only=recent_only):
		upsert_message_log(instance.name, rec)
		stats["errors"] += 1
		stats["messages"] += 1

	stats["edi_documents"] = sync_local_edi_documents(instance, home, recent_only=recent_only)
	return stats


def _party_names(local_as2_id: str, remote_as2_id: str, direction: str) -> tuple[str, str, str]:
	"""Return sent_from, received_by, and the other party for this direction."""
	local_label = _party_label(local_as2_id) if local_as2_id else ""
	remote_label = _party_label(remote_as2_id) if remote_as2_id else ""
	if direction == "Outbound":
		return local_label, remote_label, remote_label
	return remote_label, local_label, remote_label


def _payload_dirs(home: Path, local_id: str, remote_id: str) -> list[Path]:
	data = home / "data"
	inbox = data / "inbox" / local_id / "inbox" if local_id else None
	dirs = []
	if inbox is not None:
		dirs.extend([inbox / "processed", inbox, inbox / "error"])
	if remote_id:
		dirs.append(data / "outbox" / remote_id)
	if local_id and remote_id:
		dirs.append(data / f"{remote_id}-{local_id}" / "inbox")
		dirs.append(data / f"{local_id}-{remote_id}" / "inbox")
	return dirs


def _match_payload(folder: Path, file_name: str) -> Path | None:
	if not folder.is_dir():
		return None
	direct = folder / file_name
	if direct.is_file():
		return direct
	suffix = f"-{file_name}"
	try:
		for entry in folder.iterdir():
			if entry.is_file() and entry.name.endswith(suffix):
				return entry
	except OSError:
		return None
	return None


def _read_payload_text(instance, rec: dict) -> str:
	"""Read one EDI file from the known inbox or outbox folder. Does not walk the tree."""
	file_name = rec.get("file_name") or ""
	local_id = rec.get("local_as2_id") or instance.as2_id or ""
	remote_id = rec.get("remote_as2_id") or ""
	if not file_name:
		return ""
	homes = [(instance, local_id, remote_id)]
	if remote_id:
		other_name = frappe.db.get_value("OpenAS2 Instance", {"as2_id": remote_id}, "name")
		if other_name and other_name != instance.name:
			homes.append((frappe.get_doc("OpenAS2 Instance", other_name), remote_id, local_id))
	for owner, local, remote in homes:
		try:
			home = resolve_openas2_home(owner)
		except Exception:
			continue
		for folder in _payload_dirs(home, local, remote):
			path = _match_payload(folder, file_name)
			if not path:
				continue
			_txn, text = _read_edi_file(path)
			if text:
				return text
	return ""


def _ensure_edi_from_log(instance, rec: dict) -> None:
	"""Create the transaction row from the log line, with both parties and the EDI text."""
	if not frappe.db.exists("DocType", "OpenAS2 EDI Document"):
		return
	file_name = (rec.get("file_name") or "")[:140]
	direction = rec.get("direction") or ""
	if not file_name or direction not in ("Inbound", "Outbound"):
		return
	txn = rec.get("transaction_type") or extract_transaction_type(file_name)
	if txn in ("", "Unknown"):
		txn = extract_transaction_type(file_name)
	if txn in ("", "Unknown"):
		return
	tms = (instance.instance_type or "").strip()
	if tms not in ("Shipper", "Broker", "Carrier", "CompanyC"):
		tms = "Broker"
	sent_from, received_by, partner_name = _party_names(
		rec.get("local_as2_id") or instance.as2_id or "",
		rec.get("remote_as2_id") or "",
		direction,
	)
	existing = frappe.db.get_value(
		"OpenAS2 EDI Document",
		{"instance": instance.name, "file_name": file_name, "direction": direction},
		"name",
	)
	doc = frappe.get_doc("OpenAS2 EDI Document", existing) if existing else None
	if doc and doc.sent_from and doc.received_by and doc.edi_content:
		return
	text = ""
	if not (doc and doc.edi_content):
		text = _read_payload_text(instance, rec)
	from openas2_manager.openas2.tms_edi import edi_content_to_json

	values = {
		"tms": tms,
		"instance": instance.name,
		"file_name": file_name,
		"transaction_type": txn,
		"status": rec.get("status") or "Success",
		"direction": direction,
		"sent_from": sent_from,
		"received_by": received_by,
		"partner_name": partner_name,
		"as2_message_id": (rec.get("message_id") or "")[:255],
		"as2_status": rec.get("status") or "Success",
		"mdn_status": rec.get("mdn_status") or "Unknown",
		"document_timestamp": rec.get("timestamp") or now_datetime(),
		"last_synced": now_datetime(),
		"summary": f"{txn} {sent_from} to {received_by}"[:140],
	}
	if text:
		values["edi_content"] = text
		values["json_content"] = edi_content_to_json(text, transaction_type=txn)
	if doc:
		fill = {}
		for key, value in values.items():
			if not value:
				continue
			if key in ("sent_from", "received_by", "partner_name", "edi_content", "json_content", "summary"):
				if not getattr(doc, key, None):
					fill[key] = value
			elif key == "status" and doc.status in (None, "", "Received", "Sent", "Unknown"):
				fill[key] = value
		if not fill:
			return
		doc.flags.ignore_permissions = True
		doc.flags.ignore_version = True
		doc.update(fill)
		doc.save(ignore_permissions=True)
		return
	doc = frappe.get_doc(
		{
			"doctype": "OpenAS2 EDI Document",
			"tms_doc_name": (rec.get("message_id") or file_name)[:140],
			**values,
		}
	)
	doc.flags.ignore_permissions = True
	doc.insert(ignore_permissions=True)


def _repair_incomplete_edi(instance_names: list[str]) -> None:
	"""Fill parties and EDI text on recent rows the log-only sync created."""
	if not instance_names or not frappe.db.exists("DocType", "OpenAS2 EDI Document"):
		return
	since = now_datetime() - timedelta(hours=6)
	rows = frappe.db.sql(
		"""select name, instance, direction, as2_message_id
		   from `tabOpenAS2 EDI Document`
		   where instance in %(instances)s
		     and document_timestamp >= %(since)s
		     and (
		       ifnull(sent_from, '') = ''
		       or ifnull(received_by, '') = ''
		       or ifnull(edi_content, '') = ''
		     )
		   order by document_timestamp desc
		   limit 40""",
		{"instances": instance_names, "since": since},
		as_dict=True,
	)
	for row in rows:
		log = frappe.db.get_value(
			"OpenAS2 Message Log",
			{
				"instance": row.instance,
				"message_id": row.as2_message_id,
				"direction": row.direction,
			},
			[
				"file_name",
				"local_as2_id",
				"remote_as2_id",
				"direction",
				"message_id",
				"transaction_type",
				"status",
				"mdn_status",
				"timestamp",
			],
			as_dict=True,
		)
		if not log or not log.file_name:
			continue
		_ensure_edi_from_log(frappe.get_doc("OpenAS2 Instance", row.instance), log)


def _sync_recent_logs(instance_names: list[str], *, publish: bool = True) -> dict:
	"""Read only the newest log file and rows from the last 3 minutes."""
	results = []
	for name in instance_names:
		try:
			stats = discover_instance_messages(
				frappe.get_doc("OpenAS2 Instance", name),
				recent_only=True,
				log_only=True,
			)
			results.append({"instance": name, **stats})
		except Exception as exc:
			results.append({"instance": name, "messages": 0, "errors": 0, "notes": [str(exc)]})
	try:
		_repair_incomplete_edi(instance_names)
	except Exception:
		pass
	if not getattr(frappe.flags, "in_test", False):
		frappe.db.commit()
	if publish:
		try:
			frappe.publish_realtime(
				"openas2_monitoring_updated",
				{"instances": len(results)},
				after_commit=True,
			)
		except Exception:
			pass
	return {
		"refreshed_at": str(now_datetime()),
		"instances": results,
		"openas2_modified": False,
	}


def _split_as2_pair(folder_name: str, known_ids: list[str]) -> tuple[str | None, str | None]:
	ids = sorted({i for i in known_ids if i}, key=len, reverse=True)
	for sender in ids:
		prefix = f"{sender}-"
		if folder_name.startswith(prefix):
			receiver = folder_name[len(prefix) :]
			if receiver in ids:
				return sender, receiver
	return None, None


def _read_edi_file(path: Path) -> tuple[str, str]:
	"""Return (transaction_type, text) when the file is X12. Type may be empty."""
	try:
		text = path.read_text(encoding="utf-8", errors="replace")
	except OSError:
		return "", ""
	if "ISA*" not in text and "ST*" not in text:
		return "", ""
	match = re.search(r"ST\*(\d{3})\*", text)
	txn = match.group(1) if match and match.group(1) in TRANSACTION_TYPES else ""
	if not txn:
		txn = extract_transaction_type(path.name)
		if txn == "Unknown":
			txn = ""
	return txn, text[:500_000]


def _party_label(as2_id: str) -> str:
	name = frappe.db.get_value("AS2 Partner", {"as2_id": as2_id}, "partner_name")
	return (name or as2_id or "")[:140]


def sync_local_edi_documents(instance, home: Path, recent_only: bool = False) -> int:
	"""Create one OpenAS2 EDI Document per EDI file stored by this instance.

	OpenAS2 writes received payloads under data/<sender>-<receiver>/inbox.
	The Transactions list reads OpenAS2 EDI Document, not those folders.
	"""
	if not frappe.db.exists("DocType", "OpenAS2 EDI Document"):
		return 0
	data = home / "data"
	if not data.is_dir():
		return 0

	tms = (instance.instance_type or "").strip()
	if tms not in ("Shipper", "Broker", "Carrier", "CompanyC"):
		tms = "Broker"
	known = [row for row in frappe.get_all("OpenAS2 Instance", pluck="as2_id") if row]
	created = 0

	def save_doc(owner, path: Path, sender: str, receiver: str, direction: str, status: str, mdn: str) -> None:
		nonlocal created
		try:
			_assert_under_home(home, path)
		except Exception:
			return
		owner_tms = (owner.instance_type or "").strip()
		if owner_tms not in ("Shipper", "Broker", "Carrier", "CompanyC"):
			owner_tms = tms
		if recent_only and not _is_recent_file(path, minutes=3):
			return
		txn, text = _read_edi_file(path)
		if not text:
			return
		short_name = path.name
		named = INBOX_NAME_RE.match(path.name)
		if named:
			short_name = named.group(3)
		message_id = normalize_message_id(path.name)
		key = (message_id or path.name)[:140]
		existing = None
		if message_id:
			existing = frappe.db.get_value(
				"OpenAS2 EDI Document",
				{"instance": owner.name, "as2_message_id": message_id, "direction": direction},
				"name",
			)
		if not existing:
			existing = frappe.db.get_value(
				"OpenAS2 EDI Document",
				{"instance": owner.name, "tms_doc_name": key, "direction": direction},
				"name",
			)
		from openas2_manager.openas2.tms_edi import edi_content_to_json

		sent_from = _party_label(sender)
		received_by = _party_label(receiver)
		values = {
			"tms": owner_tms,
			"instance": owner.name,
			"tms_doc_name": key,
			"file_name": (short_name or path.name)[:140],
			"transaction_type": txn,
			"status": status,
			"direction": direction,
			"sent_from": sent_from,
			"received_by": received_by,
			"partner_name": received_by if direction == "Outbound" else sent_from,
			"as2_message_id": message_id[:255],
			"as2_status": status,
			"mdn_status": mdn,
			"document_timestamp": datetime.fromtimestamp(path.stat().st_mtime),
			"last_synced": now_datetime(),
			"summary": f"{txn or 'EDI'} {sent_from} to {received_by}"[:140],
			"edi_content": text,
			"json_content": edi_content_to_json(text, transaction_type=txn),
		}
		if existing:
			doc = frappe.get_doc("OpenAS2 EDI Document", existing)
			doc.update(values)
			doc.flags.ignore_permissions = True
			doc.flags.ignore_version = True
			doc.save(ignore_permissions=True)
		else:
			doc = frappe.get_doc({"doctype": "OpenAS2 EDI Document", **values})
			doc.flags.ignore_permissions = True
			doc.flags.ignore_version = True
			doc.insert(ignore_permissions=True)
		if txn and short_name:
			frappe.db.sql(
				"""update `tabOpenAS2 Message Log`
				   set transaction_type=%s
				   where file_name=%s
				     and ifnull(transaction_type, 'Unknown') in ('', 'Unknown')""",
				(txn, short_name[:140]),
			)
		created += 1

	for folder in data.iterdir():
		if not folder.is_dir():
			continue
		sender, receiver = _split_as2_pair(folder.name, known)
		inbox = folder / "inbox"
		if not sender or not inbox.is_dir():
			continue
		local = instance.as2_id or ""
		if local == receiver:
			direction = "Inbound"
		elif local == sender:
			direction = "Outbound"
		else:
			continue
		for entry in inbox.iterdir():
			if entry.is_file():
				mdn = "Received" if (folder / "mdn").is_dir() else "Unknown"
				save_doc(instance, entry, sender, receiver, direction, "Success", mdn)
				if direction == "Inbound":
					sender_name = frappe.db.get_value("OpenAS2 Instance", {"as2_id": sender}, "name")
					if sender_name and sender_name != instance.name:
						save_doc(
							frappe.get_doc("OpenAS2 Instance", sender_name),
							entry,
							sender,
							receiver,
							"Outbound",
							"Success",
							mdn,
						)

	# Received AS2 payloads land in data/inbox/{receiver}/inbox[/processed].
	inbox_root = data / "inbox"
	local_id = instance.as2_id or ""
	if inbox_root.is_dir() and local_id:
		received_root = inbox_root / local_id / "inbox"
		for folder_name, status, mdn in (
			("inbox", "Received", "Pending"),
			("processed", "Success", "Received"),
			("error", "Failed", "Failed"),
		):
			folder = received_root if folder_name == "inbox" else received_root / folder_name
			if not folder.is_dir():
				continue
			for entry in folder.iterdir():
				if not entry.is_file():
					continue
				match = INBOX_NAME_RE.match(entry.name)
				sender = match.group(1) if match else ""
				if not sender:
					continue
				save_doc(instance, entry, sender, local_id, "Inbound", status, mdn)
				sender_name = frappe.db.get_value("OpenAS2 Instance", {"as2_id": sender}, "name")
				if sender_name and sender_name != instance.name:
					save_doc(
						frappe.get_doc("OpenAS2 Instance", sender_name),
						entry,
						sender,
						local_id,
						"Outbound",
						status,
						mdn,
					)

	error_root = data / "outbox" / "error"
	if error_root.is_dir() and instance.as2_id:
		for day_dir in error_root.iterdir():
			if not day_dir.is_dir():
				continue
			for remote_dir in day_dir.iterdir():
				if not remote_dir.is_dir():
					continue
				for entry in remote_dir.iterdir():
					if entry.is_file():
						save_doc(
							instance,
							entry,
							instance.as2_id,
							remote_dir.name,
							"Outbound",
							"Failed",
							"Failed",
						)
	return created


@frappe.whitelist()
def refresh_monitoring(instance_name: str | None = None) -> dict:
	"""Re-read msg_metadata. Does not scan files or copy TMS documents.

	A failed database read is not a success and is not filled from local logs.
	"""
	if "System Manager" not in frappe.get_roles(frappe.session.user):
		frappe.throw(frappe._("Only System Managers may refresh monitoring."), frappe.PermissionError)

	from openas2_manager.openas2.remote_tracking import REMOTE_READ_ERROR, list_live_messages

	live = list_live_messages(
		instance=instance_name if instance_name not in ("", "All") else None,
		limit=1,
	)
	if live is None:
		return {
			"ok": False,
			"refreshed": False,
			"error": REMOTE_READ_ERROR,
			"openas2_modified": False,
			"message": REMOTE_READ_ERROR,
		}
	from openas2_manager.openas2.edi_dashboard_counts import run_controlled_panel_refresh

	run_controlled_panel_refresh()
	return {
		"ok": True,
		"refreshed": True,
		"refreshed_at": str(now_datetime()),
		"openas2_modified": False,
		"message": "Refreshed monitoring from the OpenAS2 database. OpenAS2 files were not modified.",
	}


def _live_instance_names() -> list[str]:
	"""Instances the signed-in company can see, plus the partners they exchange with."""
	from openas2_manager.access import get_allowed_instance_names

	allowed = get_allowed_instance_names()
	if allowed is None:
		names = [
			"Shipper OpenAS20",
			"Broker OpenAS2A",
			"Carrier OpenAS2B",
			"CompanyC OpenAS2C",
		]
		return [name for name in names if frappe.db.exists("OpenAS2 Instance", name)]
	names = set(allowed)
	if not names:
		return []
	rows = frappe.get_all(
		"OpenAS2 Partnership",
		filters={"instance": ["in", list(names)]},
		fields=["local_as2_id", "remote_as2_id"],
	)
	as2_ids = {row.local_as2_id for row in rows if row.local_as2_id}
	as2_ids.update(row.remote_as2_id for row in rows if row.remote_as2_id)
	if as2_ids:
		for other in frappe.get_all(
			"OpenAS2 Instance", filters={"as2_id": ["in", list(as2_ids)]}, pluck="name"
		):
			names.add(other)
	return list(names)


@frappe.whitelist()
def sync_live_activity() -> dict:
	"""Visible messages are read from msg_metadata. Do not scan files into Message Log."""
	return {"ok": True, "file_scan": False, "message_logs_written": 0}


def scheduled_monitoring_sync() -> dict:
	"""Background job no longer copies OpenAS2 files into OpenAS2 Message Log.

	Visible message data is read from msg_metadata when a page asks for it.
	"""
	return {"ok": True, "file_scan": False, "message_logs_written": 0}


def _run_monitoring_sync(
	instance_name: str | None = None,
	*,
	commit: bool = True,
	publish: bool = False,
	recent_only: bool = False,
	instance_names: list[str] | None = None,
) -> dict:
	"""File discovery plus TMS sync. The Refresh action does not call this."""
	if instance_names is not None:
		instances = list(instance_names)
	else:
		filters = {}
		if instance_name and instance_name not in ("", "All"):
			filters["name"] = instance_name
		instances = frappe.get_all("OpenAS2 Instance", filters=filters, pluck="name")
	results = []
	for name in instances:
		try:
			inst = frappe.get_doc("OpenAS2 Instance", name)
			stats = discover_instance_messages(inst, recent_only=recent_only)
			results.append({"instance": name, **stats})
		except Exception as exc:
			results.append({"instance": name, "messages": 0, "errors": 0, "notes": [str(exc)]})

	from openas2_manager.openas2.tms_edi import sync_all_tms_edi_documents

	try:
		edi_results = sync_all_tms_edi_documents(instance_name)
	except Exception as exc:
		edi_results = [{"edi_documents": 0, "notes": [str(exc)]}]
	edi_count = sum(int(r.get("edi_documents") or 0) for r in edi_results)

	if commit and not getattr(frappe.flags, "in_test", False):
		frappe.db.commit()

	if publish:
		try:
			frappe.publish_realtime(
				"openas2_monitoring_updated",
				{"edi_count": edi_count, "instances": len(results)},
				after_commit=True,
			)
		except Exception:
			pass

	return {
		"refreshed_at": str(now_datetime()),
		"instances": results,
		"edi_documents": edi_results,
		"openas2_modified": False,
		"message": (
			f"Refreshed monitoring for {len(results)} instance(s)"
			f" ({edi_count} EDI document(s) from TMS). OpenAS2 files were not modified."
		),
	}


@frappe.whitelist()
def get_monitoring_filter_options(
	instance: str | None = None,
	date_from: str | None = None,
	date_to: str | None = None,
) -> dict:
	"""Distinct partners, statuses, and EDI types for Monitoring filter dropdowns."""
	from openas2_manager.openas2.remote_tracking import monitoring_filter_options

	return monitoring_filter_options(instance=instance, date_from=date_from, date_to=date_to)


@frappe.whitelist()
def get_messages(
	instance: str | None = None,
	direction: str | None = None,
	transaction_type: str | None = None,
	status: str | None = None,
	date_from: str | None = None,
	date_to: str | None = None,
	errors_only: int | str = 0,
	limit: int | str = 200,
	partner: str | None = None,
	search: str | None = None,
) -> dict:
	"""Filtered message list for the monitoring page."""
	from openas2_manager.openas2.remote_tracking import list_live_messages

	live = list_live_messages(
		instance=instance,
		direction=direction,
		transaction_type=transaction_type,
		status=status,
		date_from=date_from,
		date_to=date_to,
		errors_only=errors_only,
		limit=limit,
		partner=partner,
		search=search,
	)
	if live is None:
		from openas2_manager.openas2.remote_tracking import REMOTE_READ_ERROR

		return {"ok": False, "rows": [], "count": 0, "error": REMOTE_READ_ERROR}
	return live


@frappe.whitelist()
def get_list_total(
	transaction_type: str | None = None,
	status: str | None = None,
	date_from: str | None = None,
	date_to: str | None = None,
	errors_only: int | str = 0,
	partner: str | None = None,
	search: str | None = None,
) -> dict:
	"""Total rows for the selected monitoring list. A failed read leaves total unset."""
	from openas2_manager.openas2.remote_tracking import count_live_messages

	return count_live_messages(
		transaction_type=transaction_type,
		status=status,
		date_from=date_from,
		date_to=date_to,
		errors_only=errors_only,
		partner=partner,
		search=search,
	)


@frappe.whitelist()
def get_message_details(name: str) -> dict:
	if name and str(name).startswith("remote:"):
		from openas2_manager.openas2.remote_tracking import (
			REMOTE_READ_ERROR,
			RemoteAccessDenied,
			RemoteMessageNotFound,
			remote_message_details,
		)

		try:
			detail = remote_message_details(name)
		except RemoteMessageNotFound:
			frappe.throw(frappe._("Message log not found."))
		except RemoteAccessDenied:
			frappe.throw(
				frappe._("Not permitted to access this message."),
				frappe.PermissionError,
			)
		if not detail:
			frappe.throw(frappe._(REMOTE_READ_ERROR))
		detail.setdefault("edi_document_route", None)
		return detail
	if not name or not frappe.db.exists("OpenAS2 Message Log", name):
		frappe.throw(frappe._("Message log not found."))
	from openas2_manager.access import assert_instance_access

	doc = frappe.get_doc("OpenAS2 Message Log", name)
	if doc.instance:
		assert_instance_access(doc.instance)
	inst = frappe.get_doc("OpenAS2 Instance", doc.instance) if doc.instance else None
	edi_route = None
	if doc.edi_document and frappe.db.exists("DocType", "EDI Document"):
		edi_route = f"/app/edi-document/{doc.edi_document}"
	elif doc.edi_document and frappe.db.exists("DocType", "OpenAS2 EDI Document"):
		from openas2_manager.openas2.tms_edi import (
			edi_document_desk_url,
			find_mirrored_edi_document,
			resolve_tms_url,
		)

		mirror = find_mirrored_edi_document(
			doc.file_name, doc.message_id, instance=doc.instance
		)
		if not mirror:
			mirror = frappe.db.get_value(
				"OpenAS2 EDI Document",
				{"tms_doc_name": doc.edi_document},
				["tms_url", "tms_doc_name"],
				as_dict=True,
			)
		if mirror and mirror.get("tms_url"):
			edi_route = mirror.tms_url
		elif inst:
			edi_route = edi_document_desk_url(resolve_tms_url(inst), doc.edi_document) or None
	return {
		"name": doc.name,
		"instance": doc.instance,
		"instance_type": inst.instance_type if inst else None,
		"instance_label": inst.instance_name if inst else doc.instance,
		"direction": doc.direction,
		"partner": doc.partner,
		"local_as2_id": doc.local_as2_id,
		"remote_as2_id": doc.remote_as2_id,
		"transaction_type": doc.transaction_type,
		"message_id": doc.message_id,
		"message_id_display": display_message_id(doc.message_id),
		"timestamp": doc.timestamp,
		"status": doc.status,
		"mdn_status": doc.mdn_status,
		"file_name": doc.file_name,
		"source": doc.source,
		"raw_reference": doc.raw_reference,
		"error_message": redact_sensitive(doc.error_message),
		"edi_document": doc.edi_document,
		"edi_document_route": edi_route,
		"read_only": True,
	}


@frappe.whitelist()
def get_remote_message_payload(name: str, full: int | str = 0) -> dict:
	"""EDI preview for one remote message. The monitoring list does not call this.

	Requires a logged-in user. The id is validated before any query, and the
	remote account is read-only. The payload is not written to a document or log.
	``full`` requests the capped full body instead of the 1,200 character preview.
	"""
	from openas2_manager.openas2.remote_tracking import (
		RemoteAccessDenied,
		parse_remote_row_id,
		remote_message_payload,
	)

	row_id = parse_remote_row_id(name)
	if row_id is None:
		frappe.throw(frappe._("Message log not found."))
	want_full = str(full or "").strip().lower() in {"1", "true", "yes"}
	try:
		result = remote_message_payload(name, full=want_full)
	except RemoteAccessDenied:
		frappe.throw(
			frappe._("Not permitted to access this message."),
			frappe.PermissionError,
		)
	if result is None:
		return {
			"name": f"remote:{row_id}",
			"payload": "",
			"available": False,
			"reason": "unavailable",
			"payload_chars": 0,
			"transaction_type": "",
		}
	return result


@frappe.whitelist()
def convert_message_payload_json(payload: str | None = None) -> dict:
	"""JSON view of one EDI payload already loaded for Message Details.

	Login is required. The text is not written, logged, or sent back to OpenAS2.
	"""
	from openas2_manager.openas2.remote_tracking import PAYLOAD_FULL_CHARS
	from openas2_manager.openas2.x12_json import x12_message_json

	if payload is None:
		text = ""
	elif isinstance(payload, str):
		text = payload
	else:
		frappe.throw(frappe._("Invalid EDI payload."))
	if len(text) > PAYLOAD_FULL_CHARS:
		frappe.throw(frappe._("Payload is too large."))
	try:
		return x12_message_json(text)
	except Exception:
		return {
			"available": False,
			"reason": "invalid",
			"message": "JSON conversion is unavailable because this message is not a supported X12 EDI payload.",
			"transaction_type": "",
			"json": "",
		}


@frappe.whitelist()
def get_errors(
	instance: str | None = None,
	date_from: str | None = None,
	date_to: str | None = None,
	limit: int | str = 200,
) -> dict:
	return get_messages(
		instance=instance,
		status="Failed",
		date_from=date_from,
		date_to=date_to,
		limit=limit,
	)


def _pct_change(current: int, previous: int) -> float:
	if previous <= 0:
		return 100.0 if current > 0 else 0.0
	return round(((current - previous) / previous) * 100.0, 1)


def _initials(name: str | None) -> str:
	parts = [p for p in (name or "").strip().split() if p]
	if not parts:
		return "?"
	if len(parts) == 1:
		return parts[0][:2].upper()
	return (parts[0][0] + parts[-1][0]).upper()


@frappe.whitelist()
def get_edi_transactions_counts() -> dict:
	"""EDI Transactions chart data from the live OpenAS2 ``msg_metadata`` database."""
	from openas2_manager.openas2.edi_home_chart import get_edi_home_chart_response

	return get_edi_home_chart_response()


@frappe.whitelist()
def get_dashboard_summary(
	kpis_only: int | str = 0,
	activity_only: int | str = 0,
) -> dict:
	"""Dashboard KPIs, lists, and status breakdowns for the home UI.

	``kpis_only`` skips the remote activity read and uses cached EDI totals.
	``activity_only`` skips EDI counting and returns recent remote activity only.
	With neither flag, both sections run (legacy callers).
	"""
	from openas2_manager.access import get_allowed_instance_names, visible_partner_names

	now = now_datetime()
	allowed_instances = get_allowed_instance_names()
	instance_in = None
	if allowed_instances is not None:
		instance_in = ["in", allowed_instances or ["__none__"]]
	partner_names = visible_partner_names()
	partner_in = None
	if partner_names is not None:
		partner_in = ["in", partner_names or ["__none__"]]

	kpis_only_flag = str(kpis_only or "").strip().lower() in {"1", "true", "yes"}
	activity_only_flag = str(activity_only or "").strip().lower() in {"1", "true", "yes"}
	skip_remote_activity = kpis_only_flag and not activity_only_flag
	skip_edi_counts = activity_only_flag and not kpis_only_flag

	summary = {"as_of": str(now)}
	live_activity = None
	messages_error = None
	if not skip_remote_activity:
		from openas2_manager.openas2.remote_tracking import dashboard_activity

		live_activity = dashboard_activity()
		live_counts = live_activity.get("counts") if live_activity else None
		if live_counts:
			summary.update(
				{
					"messages_today": live_counts["messages_today"],
					"inbound": live_counts["inbound"],
					"outbound": live_counts["outbound"],
					"successful": live_counts["successful"],
					"processed": live_counts.get("processed", 0),
					"failed": live_counts["failed"],
					"pending_mdn": live_counts["pending_mdn"],
				}
			)
		elif live_activity is None:
			from openas2_manager.openas2.remote_tracking import REMOTE_READ_ERROR

			messages_error = REMOTE_READ_ERROR
			summary["messages_error"] = messages_error
		else:
			summary["messages_counts_unavailable"] = True

	if not skip_edi_counts:
		from openas2_manager.openas2.edi_dashboard_counts import attach_dashboard_edi_panels

		attach_dashboard_edi_panels(summary)

	include_local_cards = not (activity_only_flag and not kpis_only_flag)
	if include_local_cards:
		# Instance / config badges (Home KPI path and legacy full summary)
		instance_filters = {"name": instance_in} if instance_in else {}
		instances = frappe.get_all(
			"OpenAS2 Instance",
			filters=instance_filters,
			fields=["name", "instance_name", "instance_type", "status", "lifecycle_status"],
			order_by="modified desc",
			limit_page_length=20,
		)
		active_instances = [i for i in instances if (i.status or "") == "Active"]
		summary["config"] = {
			"active_count": len(active_instances),
			"total_count": len(instances),
			"types": sorted({i.instance_type for i in instances if i.instance_type}),
			"status": "Active" if active_instances else ("Draft" if instances else "None"),
		}

		partner_filters = {"name": partner_in} if partner_in else {}
		summary["recent_partners"] = []
		summary["partner_stats"] = {
			"total": frappe.db.count("AS2 Partner", partner_filters),
			"active": frappe.db.count("AS2 Partner", {**partner_filters, "status": "Active"}),
		}

		cert_filters: dict = {}
		if instance_in:
			cert_filters["openas2_instance"] = instance_in
		summary["recent_certificates"] = []
		summary["certificate_stats"] = {
			"total": frappe.db.count("AS2 Certificate", cert_filters),
			"active": frappe.db.count("AS2 Certificate", {**cert_filters, "status": "Active"}),
			"signing": frappe.db.count(
				"AS2 Certificate",
				{**cert_filters, "certificate_type": ["in", ["Signing", "Both"]]},
			),
		}

	if not skip_remote_activity:
		messages = live_activity["recent"] if live_activity is not None else []
		for m in messages:
			partner_name = None
			if m.partner and frappe.db.exists("OpenAS2 Partnership", m.partner):
				partner_name = frappe.db.get_value(
					"OpenAS2 Partnership", m.partner, "remote_partner_name"
				) or frappe.db.get_value("OpenAS2 Partnership", m.partner, "partnership_name")
			if not partner_name and m.remote_as2_id:
				partner_name = (
					frappe.db.get_value("AS2 Partner", {"as2_id": m.remote_as2_id}, "partner_name")
					or m.remote_as2_id
				)
			m["partner_label"] = partner_name or m.remote_as2_id or "—"
			m["initials"] = _initials(m["partner_label"])
			m["message_id_display"] = display_message_id(m.get("message_id")) or (m.name or "")
		summary["recent_messages"] = messages
	elif kpis_only_flag:
		summary["recent_messages"] = []

	return summary


def _attach_known_edi(detail: dict) -> None:
	"""Keep an existing Frappe EDI link when the same Message-ID was already logged."""
	message_id = detail.get("message_id")
	if not message_id or not frappe.db.exists("DocType", "OpenAS2 Message Log"):
		detail.setdefault("edi_document_route", None)
		return
	log = frappe.db.get_value(
		"OpenAS2 Message Log",
		{"message_id": message_id},
		["edi_document", "instance", "file_name"],
		as_dict=True,
	)
	if not log or not log.edi_document:
		detail.setdefault("edi_document_route", None)
		return
	from openas2_manager.access import get_allowed_instance_names

	allowed = get_allowed_instance_names()
	if allowed is not None and log.instance and log.instance not in allowed:
		detail.setdefault("edi_document_route", None)
		return
	detail["edi_document"] = log.edi_document
	detail["edi_document_route"] = None
	if frappe.db.exists("DocType", "EDI Document"):
		detail["edi_document_route"] = f"/app/edi-document/{log.edi_document}"
	elif frappe.db.exists("DocType", "OpenAS2 EDI Document"):
		from openas2_manager.openas2.tms_edi import (
			edi_document_desk_url,
			find_mirrored_edi_document,
			resolve_tms_url,
		)

		mirror = find_mirrored_edi_document(
			log.file_name or detail.get("file_name"),
			message_id,
			instance=log.instance,
		)
		if not mirror:
			mirror = frappe.db.get_value(
				"OpenAS2 EDI Document",
				{"tms_doc_name": log.edi_document},
				["tms_url", "tms_doc_name"],
				as_dict=True,
			)
		if mirror and mirror.get("tms_url"):
			detail["edi_document_route"] = mirror.tms_url
		elif log.instance and frappe.db.exists("OpenAS2 Instance", log.instance):
			inst = frappe.get_doc("OpenAS2 Instance", log.instance)
			detail["edi_document_route"] = (
				edi_document_desk_url(resolve_tms_url(inst), log.edi_document) or None
			)
