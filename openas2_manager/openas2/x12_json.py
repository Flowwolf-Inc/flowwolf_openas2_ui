# Copyright (c) 2026, Lakshana and contributors
# For license information, please see license.txt

"""Parse one X12 EDI payload into JSON for Message Details.

Delimiters come from the fixed-length ISA header. Transaction bodies keep
element positions from the parsed segments. Field names are limited to the
interchange, group, and transaction envelopes defined by X12. Unsupported
transaction sets are refused instead of being renamed or guessed.
"""

from __future__ import annotations

import email
import json
import re
from email import policy

SUPPORTED_TRANSACTIONS = ("204", "990", "214", "210", "810", "820", "997")
_TAG_RE = re.compile(r"^[A-Z][A-Z0-9]{1,2}$")
_ISA_WIDTHS = (2, 10, 2, 10, 2, 15, 2, 15, 6, 4, 1, 5, 9, 1, 1, 1)


def x12_message_json(payload: str | None) -> dict:
	"""Return a JSON conversion result. Never includes the raw payload on failure."""
	text = payload if isinstance(payload, str) else ""
	if not text.strip():
		return _unavailable("empty", "This message has no EDI payload.")
	try:
		parts = extract_edi_interchanges(text)
		if len(parts) > 1:
			documents = [_document(part) for part in parts]
			kinds = {doc.get("transaction_type") or "" for doc in documents}
			return {
				"available": True,
				"reason": "",
				"message": "",
				"transaction_type": next(iter(kinds)) if len(kinds) == 1 else "",
				"json": json.dumps(documents, indent=2),
			}
		document = _document(parts[0] if parts else edi_payload_text(text))
	except ValueError as exc:
		code = str(exc)
		if code.startswith("unsupported:"):
			txn = code.split(":", 1)[1] or "unknown"
			return _unavailable(
				"unsupported",
				f"JSON conversion is unavailable for EDI transaction type {txn}.",
				txn if txn != "unknown" else "",
			)
		if code == "incomplete":
			return _unavailable(
				"incomplete",
				"JSON conversion is unavailable because the EDI payload is incomplete.",
			)
		if code == "no-transaction":
			return _unavailable(
				"unsupported",
				"JSON conversion is unavailable because the EDI payload has no supported transaction set.",
			)
		return _unavailable(
			"invalid",
			"JSON conversion is unavailable because this message is not a supported X12 EDI payload.",
		)
	return {
		"available": True,
		"reason": "",
		"message": "",
		"transaction_type": document.get("transaction_type") or "",
		"json": json.dumps(document, indent=2),
	}


def _unavailable(reason: str, message: str, transaction_type: str = "") -> dict:
	return {
		"available": False,
		"reason": reason,
		"message": message,
		"transaction_type": transaction_type,
		"json": "",
	}


def edi_payload_text(payload: str | None) -> str:
	"""Return the EDI body after MIME and transfer-encoding are removed.

	A raw interchange is returned unchanged, aside from a leading byte-order
	mark or whitespace. MIME headers, signatures, and non-EDI wrappers are not
	returned as the interchange.
	"""
	text = payload if isinstance(payload, str) else ""
	if not text.strip():
		return ""
	parts = extract_edi_interchanges(text)
	if parts:
		return "\n\n".join(parts)
	body = _mime_body(text)
	if body is None:
		return text.lstrip("\ufeff").lstrip()
	return body


def _looks_like_mime(text: str) -> bool:
	head = text.lstrip("\ufeff").lstrip()
	lowered = head[:800].lower()
	if lowered.startswith("content-type:") or lowered.startswith("mime-version:"):
		return True
	if lowered.startswith("as2-") and "content-type:" in lowered:
		return True
	if lowered.startswith("--") and "content-type:" in lowered and "content-transfer-encoding:" in lowered:
		return True
	return False


def _mime_body(text: str) -> str | None:
	"""Decoded first EDI part, or None when the text is not a MIME message."""
	if not _looks_like_mime(text):
		return None
	message = _parse_mime(text)
	if message is None:
		return ""
	fallback = ""
	for part in message.walk():
		if part.get_content_maintype() == "multipart":
			continue
		ctype = (part.get_content_type() or "").lower()
		if "pkcs7" in ctype or ctype.endswith("signature"):
			continue
		body = _part_text(part).lstrip("\ufeff").lstrip()
		if not body:
			continue
		if _read_isa(body) or body.startswith("ISA"):
			return body
		if not fallback:
			fallback = body
	return fallback


def _parse_mime(text: str):
	sample = text.lstrip("\ufeff").lstrip()
	try:
		if sample.startswith("--"):
			boundary = sample.splitlines()[0].strip()[2:]
			if boundary.endswith("--"):
				boundary = boundary[:-2]
			sample = f'Content-Type: multipart/mixed; boundary="{boundary}"\n\n{sample}'
		return email.message_from_string(sample, policy=policy.default)
	except Exception:
		return None


def _part_text(part) -> str:
	try:
		raw = part.get_payload(decode=True)
	except Exception:
		raw = None
	if isinstance(raw, bytes):
		return raw.decode("utf-8", errors="replace")
	if isinstance(raw, str):
		return raw
	return ""


def _document(text: str) -> dict:
	raw = text.lstrip("\ufeff").lstrip()
	header = _read_isa(raw)
	if header is None:
		raise ValueError("invalid")
	segments = _segments(raw, header)
	groups, transaction_type = _transactions(segments)
	return {
		"format": "X12",
		"transaction_type": transaction_type,
		"delimiters": {
			"element": header["element_separator"],
			"component": header["component_separator"].strip(),
			"segment": header["segment_terminator"],
		},
		"interchange": _interchange(header["fields"]),
		"functional_groups": groups,
	}


def _read_isa(raw: str) -> dict | None:
	if len(raw) < 106 or raw[:3] != "ISA":
		return None
	separator = raw[3]
	if separator.isalnum() or separator in "\r\n":
		return None
	position = 4
	fields: list[str] = []
	for index, width in enumerate(_ISA_WIDTHS):
		end = position + width
		if end > len(raw):
			return None
		fields.append(raw[position:end])
		position = end
		if index < len(_ISA_WIDTHS) - 1:
			if position >= len(raw) or raw[position] != separator:
				return None
			position += 1
	if position >= len(raw):
		return None
	terminator = raw[position]
	if terminator.isalnum() or terminator == separator:
		return None
	if position + 1 != 106:
		return None
	component = fields[15]
	if not component.strip() or component == separator or component.isalnum():
		return None
	return {
		"element_separator": separator,
		"component_separator": component,
		"segment_terminator": terminator,
		"fields": fields[:15],
		"rest_at": 106,
	}


def extract_edi_interchanges(payload: str | None) -> list[str]:
	"""Exact ISA-through-IEA slices, one per EDI attachment.

	MIME headers and signature parts are skipped. Each slice is the original
	interchange text, including its own segment terminator. Separate attachments
	are not merged into one slice.
	"""
	text = payload if isinstance(payload, str) else ""
	if not text.strip():
		return []
	found: list[str] = []
	for body in _attachment_bodies(text):
		found.extend(_interchanges_in(body))
	return found


def _attachment_bodies(text: str) -> list[str]:
	if not _looks_like_mime(text):
		return [text.lstrip("\ufeff")]
	message = _parse_mime(text)
	if message is None:
		return []
	bodies: list[str] = []
	for part in message.walk():
		if part.get_content_maintype() == "multipart":
			continue
		ctype = (part.get_content_type() or "").lower()
		if "pkcs7" in ctype or ctype.endswith("signature"):
			continue
		body = _part_text(part)
		if body.strip():
			bodies.append(body)
	return bodies


def _interchanges_in(text: str) -> list[str]:
	found: list[str] = []
	cursor = 0
	while cursor < len(text):
		start = text.find("ISA", cursor)
		if start < 0:
			break
		header = _read_isa(text[start:])
		if header is None:
			cursor = start + 3
			continue
		end = _interchange_end(text, start, header)
		if end is None:
			cursor = start + 3
			continue
		found.append(text[start:end])
		cursor = end
	return found


def _interchange_end(text: str, start: int, header: dict) -> int | None:
	"""Index just after the IEA segment terminator. None when the trailer is absent."""
	terminator = header["segment_terminator"]
	separator = header["element_separator"]
	position = start + header["rest_at"]
	while position <= len(text):
		mark = text.find(terminator, position)
		if mark < 0:
			return None
		piece = text[position:mark].strip("\r\n \t")
		tag = piece.split(separator, 1)[0].strip().upper() if piece else ""
		end = mark + len(terminator)
		if tag == "IEA":
			if terminator == "\r" and text[end : end + 1] == "\n":
				end += 1
			return end
		position = end
	return None


def _element(value: str, component: str, separator: str):
	if component and component != separator and component in value:
		return [part.strip() for part in value.split(component)]
	return value.strip()


def _segments(raw: str, header: dict) -> list[tuple[str, list]]:
	separator = header["element_separator"]
	terminator = header["segment_terminator"]
	component = header["component_separator"]
	segments = [("ISA", [_element(field, component, separator) for field in header["fields"]])]
	for piece in raw[header["rest_at"] :].split(terminator):
		piece = piece.strip("\r\n \t")
		if not piece:
			continue
		parts = piece.split(separator)
		tag = parts[0].strip().upper()
		if not _TAG_RE.fullmatch(tag):
			raise ValueError("invalid")
		elements = [_element(part, component, separator) for part in parts[1:]]
		while elements and elements[-1] == "":
			elements.pop()
		segments.append((tag, elements))
	return segments


def _at(elements: list, index: int) -> str:
	if index >= len(elements):
		return ""
	value = elements[index]
	if isinstance(value, list):
		return ""
	return str(value).strip()


def _clean(values: dict) -> dict:
	return {key: value for key, value in values.items() if value not in ("", None, [])}


def _interchange(fields: list[str]) -> dict:
	version = fields[11].strip()
	standards_key = (
		"repetition_separator" if version[:3] >= "004" else "interchange_control_standards_identifier"
	)
	return _clean(
		{
			"authorization_information_qualifier": fields[0].strip(),
			"authorization_information": fields[1].strip(),
			"security_information_qualifier": fields[2].strip(),
			"security_information": fields[3].strip(),
			"sender_id_qualifier": fields[4].strip(),
			"sender_id": fields[5].strip(),
			"receiver_id_qualifier": fields[6].strip(),
			"receiver_id": fields[7].strip(),
			"date": fields[8].strip(),
			"time": fields[9].strip(),
			standards_key: fields[10].strip(),
			"version": version,
			"control_number": fields[12].strip(),
			"acknowledgment_requested": fields[13].strip(),
			"usage_indicator": fields[14].strip(),
		}
	)


def _group_header(elements: list) -> dict:
	return _clean(
		{
			"functional_identifier_code": _at(elements, 0),
			"application_sender_code": _at(elements, 1),
			"application_receiver_code": _at(elements, 2),
			"date": _at(elements, 3),
			"time": _at(elements, 4),
			"group_control_number": _at(elements, 5),
			"responsible_agency_code": _at(elements, 6),
			"version": _at(elements, 7),
		}
	)


def _same_count(reported: str, expected: int) -> bool:
	if reported == str(expected):
		return True
	return reported.isdigit() and int(reported) == expected


def _transactions(segments: list[tuple[str, list]]) -> tuple[list[dict], str]:
	groups: list[dict] = []
	group: dict | None = None
	pending: list[dict] = []
	current: dict | None = None

	def close_transaction() -> None:
		nonlocal current
		if current is None:
			return
		if not current.pop("closed"):
			raise ValueError("incomplete")
		pending.append(current)
		current = None

	def close_group() -> None:
		nonlocal group
		close_transaction()
		if group is None and not pending:
			return
		header = group or {}
		header["transactions"] = list(pending)
		pending.clear()
		groups.append(header)
		group = None

	for tag, elements in segments:
		if tag == "ISA":
			continue
		if tag == "GS":
			close_group()
			group = _group_header(elements)
			continue
		if tag == "ST":
			close_transaction()
			code = _at(elements, 0)
			if code not in SUPPORTED_TRANSACTIONS:
				raise ValueError(f"unsupported:{code or 'unknown'}")
			if group is None:
				group = {}
			current = {
				"transaction_set": code,
				"control_number": _at(elements, 1),
				"segments": [],
				"closed": False,
			}
			convention = _at(elements, 2)
			if convention:
				current["implementation_convention"] = convention
			continue
		if tag == "SE":
			if current is None:
				raise ValueError("incomplete")
			control = _at(elements, 1)
			if current["control_number"] and control and control != current["control_number"]:
				raise ValueError("incomplete")
			expected = len(current["segments"]) + 2
			reported = _at(elements, 0)
			if reported and not _same_count(reported, expected):
				raise ValueError("incomplete")
			current["closed"] = True
			close_transaction()
			continue
		if tag in {"GE", "IEA"}:
			close_group()
			continue
		if current is None:
			raise ValueError("invalid")
		current["segments"].append({"id": tag, "elements": elements})

	close_group()
	transactions = [txn for item in groups for txn in item.get("transactions", [])]
	if not transactions:
		raise ValueError("no-transaction")
	codes = list(dict.fromkeys(txn["transaction_set"] for txn in transactions))
	return groups, codes[0] if len(codes) == 1 else ""
