# Copyright (c) 2026, Lakshana and contributors
# For license information, please see license.txt

"""Queue an outbound transaction for OpenAS2's existing directory poller.

The original tracking row and stored payload are not changed or deleted.
OpenAS2 signs, encrypts, and applies its own duplicate checks when it
picks the new file up from the partner outbox.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from pathlib import Path

import frappe

from openas2_manager.openas2.x12_json import extract_edi_interchanges

SAFE_AS2_ID = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
SAFE_FILE = re.compile(r"^reprocess-[0-9]+-[0-9]+-[0-9]+\.edi$")


def assess_reprocess(detail: dict | None, payload: dict | None) -> tuple[str, list[str]]:
	"""Return an error message, or an empty string and the EDI attachments to queue."""
	if not detail:
		return "Message log not found.", []
	if detail.get("direction") != "Outbound":
		return "Only outbound transactions can be processed again.", []
	status = detail.get("status") or ""
	if status == "Queued":
		return "This transaction is already queued.", []
	if status == "Duplicate":
		return "Duplicate transactions are not processed again.", []
	if not detail.get("instance"):
		return "This transaction is not linked to an OpenAS2 instance.", []
	if not detail.get("remote_as2_id"):
		return "This transaction has no receiver to process.", []
	if not payload or payload.get("reason") in ("not_found", "unavailable", "empty"):
		return "The message could not be read.", []
	if not payload.get("available"):
		return payload.get("message") or "This message does not contain an X12 EDI attachment.", []
	parts = extract_edi_interchanges(payload.get("payload") or "")
	if not parts:
		return "This message does not contain an X12 EDI attachment.", []
	return "", parts


def queue_outbound_files(home: Path, receiver_as2_id: str, parts: list[str], token: str) -> int:
	"""Write each interchange into an existing outbox. Never creates folders or overwrites."""
	if not SAFE_AS2_ID.fullmatch(receiver_as2_id or "") or receiver_as2_id in {".", ".."}:
		raise ValueError("invalid receiver")
	if not parts:
		raise ValueError("no edi")
	home_root = home.expanduser().resolve()
	outbox_root = (home_root / "data" / "outbox").resolve()
	outbox = (outbox_root / receiver_as2_id).resolve()
	if outbox.parent != outbox_root or outbox.name != receiver_as2_id:
		raise ValueError("invalid receiver")
	outbox.relative_to(home_root)
	if not outbox.is_dir():
		raise FileNotFoundError
	paths: list[tuple[Path, str]] = []
	for index, edi in enumerate(parts, start=1):
		if not edi.startswith("ISA"):
			raise ValueError("not edi")
		filename = f"reprocess-{token}-{index}.edi"
		if not SAFE_FILE.fullmatch(filename):
			raise ValueError("bad name")
		path = (outbox / filename).resolve()
		path.relative_to(outbox)
		if path.exists():
			raise FileExistsError
		paths.append((path, edi))
	for path, edi in paths:
		fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
		try:
			os.write(fd, edi.encode("utf-8"))
		finally:
			os.close(fd)
	return len(paths)


def _fail(name: str, message: str) -> dict:
	return {"ok": False, "name": name, "queued": 0, "message": message}


def _token(name: str) -> str:
	from openas2_manager.openas2.remote_tracking import parse_remote_row_id

	row_id = parse_remote_row_id(name) or 0
	stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
	return f"{row_id}-{stamp}"


def perform_reprocess(name: str | None = None) -> dict:
	"""Queue the selected outbound message for OpenAS2 to process again."""
	from openas2_manager.access import assert_instance_access
	from openas2_manager.openas2.remote_tracking import (
		RemoteAccessDenied,
		remote_message_details,
		remote_message_payload,
	)

	label = str(name or "").strip()
	if not label.startswith("remote:"):
		return _fail(label, frappe._("Message log not found."))
	try:
		detail = remote_message_details(label)
	except RemoteAccessDenied:
		frappe.throw(
			frappe._("Not permitted to access this message."),
			frappe.PermissionError,
		)
	if not detail:
		return _fail(label, frappe._("Message log not found."))
	if detail.get("instance"):
		assert_instance_access(detail["instance"])
	payload = remote_message_payload(label, full=True)
	error, parts = assess_reprocess(detail, payload)
	if error:
		return _fail(label, frappe._(error))
	from openas2_manager.openas2.config_viewer import resolve_openas2_home

	instance = frappe.get_doc("OpenAS2 Instance", detail["instance"])
	local_id = detail.get("local_as2_id") or ""
	if instance.as2_id and local_id and instance.as2_id != local_id:
		return _fail(label, frappe._("This transaction does not belong to the selected instance."))
	try:
		home = resolve_openas2_home(instance)
	except frappe.ValidationError:
		return _fail(label, frappe._("OpenAS2 home is not configured for this instance."))
	try:
		count = queue_outbound_files(
			home,
			detail["remote_as2_id"],
			parts,
			_token(label),
		)
	except FileNotFoundError:
		return _fail(label, frappe._("The OpenAS2 outbox for this partner is not set up."))
	except (ValueError, FileExistsError, OSError):
		return _fail(label, frappe._("The transaction could not be queued."))
	if count == 1:
		message = frappe._(
			"The transaction was queued for OpenAS2 to process again. The original message was not changed."
		)
	else:
		message = frappe._(
			"{0} transactions were queued separately. The original message was not changed."
		).format(count)
	return {"ok": True, "name": label, "queued": count, "message": message}


@frappe.whitelist()
def reprocess_message(name: str | None = None) -> dict:
	return perform_reprocess(name)
