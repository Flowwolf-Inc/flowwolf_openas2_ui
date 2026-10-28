# Copyright (c) 2026, Lakshana and contributors
# For license information, please see license.txt

"""Persisted AI Assistant conversations.

Stores transcripts and the existing topic snapshot so a conversation can be
reopened. Does not classify questions or change assistant replies.
"""

from __future__ import annotations

import json
import re

import frappe
from frappe.utils import now_datetime

CONVERSATION = "OpenAS2 AI Conversation"
PAGE_SIZE = 30
MAX_MESSAGES = 400
MAX_TEXT = 20000
LINK_KEYS = ("type", "name", "title", "subtitle", "meta", "when", "partner", "search", "edi")
LINK_TYPES = {"partner", "partnership", "certificate", "configuration", "edi", "log"}
KINDS = {"message", "analysis", "error", "confirm"}
SECRET_KEYS = {
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
	"token",
	"confirm",
}

_FILLER = re.compile(
	r"^(?:please\s+|can you\s+|could you\s+|would you\s+|show me\s+|show\s+|list\s+|find\s+|get\s+|tell me\s+|i want to\s+|i need to\s+|give me\s+)+",
	flags=re.I,
)


def conversation_query(user: str | None = None) -> str:
	user = user or frappe.session.user
	if not user or user == "Guest":
		return "1=0"
	return f"`tabOpenAS2 AI Conversation`.user = {frappe.db.escape(user)}"


def conversation_has_permission(doc, ptype: str = "read", user: str | None = None) -> bool:
	user = user or frappe.session.user
	if not user or user == "Guest":
		return False
	if isinstance(doc, str):
		owner = frappe.db.get_value(CONVERSATION, doc, "user")
	else:
		owner = getattr(doc, "user", None) or getattr(doc, "owner", None)
	if ptype == "create" and not owner:
		return True
	return owner == user


def _require_user() -> str:
	user = frappe.session.user
	if user in (None, "", "Guest"):
		frappe.throw(frappe._("Please sign in."), frappe.PermissionError)
	return user


def _log_failure(title: str) -> None:
	try:
		frappe.log_error(title=title, message=frappe.get_traceback()[:8000])
	except Exception:
		frappe.logger("openas2_assistant").error(title)


def _clip(value: str | None, limit: int = MAX_TEXT) -> str:
	text = (value or "").strip()
	if len(text) <= limit:
		return text
	return text[: limit - 1].rstrip() + "…"


_SECRET_HISTORY = re.compile(
	r"-----BEGIN |PRIVATE KEY|keystore[_ ]password\s*[:=]",
	flags=re.I,
)


def _redact_secrets(text: str) -> str:
	if text and _SECRET_HISTORY.search(text):
		return "A secret was left out of chat history."
	return text


def conversation_title(text: str) -> str:
	"""Short title from the first useful request."""
	raw = re.sub(r"\s+", " ", (text or "").strip())
	raw = re.sub(r"[?.!]+$", "", raw).strip()
	cleaned = _FILLER.sub("", raw).strip() or raw
	cleaned = re.sub(r"^(?:a|an|the)\s+", "", cleaned, flags=re.I).strip() or cleaned
	words = []
	small = {"a", "an", "the", "of", "to", "for", "and", "or", "in", "on"}
	for word in cleaned.split():
		bare = word.strip(".,")
		if not bare:
			continue
		if re.fullmatch(r"\d{3}", bare):
			words.append(bare)
		elif bare.upper() in {"EDI", "AS2", "MDN", "HTTP", "HTTPS"}:
			words.append(bare.upper())
		elif words and bare.lower() in small:
			words.append(bare.lower())
		else:
			words.append(bare[:1].upper() + bare[1:])
	title = " ".join(words).strip() or "New chat"
	if len(title) > 48:
		short = title[:47].rsplit(" ", 1)[0].strip()
		title = (short or title[:47]).rstrip(".,") + "…"
	return title


def _parse_json(raw, fallback):
	if isinstance(raw, (dict, list)):
		return raw
	if isinstance(raw, str) and raw.strip():
		try:
			return json.loads(raw)
		except ValueError:
			return fallback
	return fallback


def _clean_links(raw) -> list[dict]:
	data = _parse_json(raw, [])
	if not isinstance(data, list):
		return []
	cleaned = []
	for item in data[:30]:
		if not isinstance(item, dict):
			continue
		kind = str(item.get("type") or "").strip()
		if kind not in LINK_TYPES:
			continue
		link = {}
		for key in LINK_KEYS:
			if key in SECRET_KEYS:
				continue
			value = item.get(key)
			if value in (None, ""):
				continue
			link[key] = _clip(str(value), 500)
		if link.get("type") and (link.get("name") or kind == "log"):
			cleaned.append(link)
	return cleaned


def _clean_topic(raw) -> dict:
	data = _parse_json(raw, {})
	if not isinstance(data, dict):
		return {}
	filters = data.get("filters") if isinstance(data.get("filters"), dict) else {}
	safe_filters = {}
	for key, value in filters.items():
		if str(key) in SECRET_KEYS or value in (None, ""):
			continue
		safe_filters[str(key)[:40]] = _clip(str(value), 200)
	results = []
	for row in (data.get("results") or [])[:30]:
		if not isinstance(row, dict):
			continue
		results.append(
			{
				"name": _clip(str(row.get("name") or ""), 140),
				"file_name": _clip(str(row.get("file_name") or ""), 180),
				"status": _clip(str(row.get("status") or ""), 40),
				"transaction_type": _clip(str(row.get("transaction_type") or ""), 20),
			}
		)
	topic = {
		"action": _clip(str(data.get("action") or ""), 40),
		"filters": safe_filters,
		"transaction_type": _clip(str(data.get("transaction_type") or safe_filters.get("transaction_type") or ""), 20),
		"limit": data.get("limit") or safe_filters.get("limit") or 0,
		"failed": bool(data.get("failed") or safe_filters.get("status") == "Failed"),
		"results": [row for row in results if row.get("name")],
	}
	try:
		topic["limit"] = max(0, min(int(topic["limit"]), 30))
	except (TypeError, ValueError):
		topic["limit"] = 0
	if not topic["action"] and not topic["results"] and not topic["filters"]:
		return {}
	return topic


def _current_topic() -> dict:
	from openas2_manager.openas2.assistant import _cache_get, _topic_key

	return _clean_topic(_cache_get(_topic_key()))


def _restore_topic(topic: dict | None) -> None:
	from openas2_manager.openas2.assistant import _cache_set, _topic_key

	_cache_set(_topic_key(), topic or None)


def _clear_pending() -> None:
	from openas2_manager.openas2.assistant import _cache_set, _draft_key, _pending_key

	_cache_set(_pending_key(), None)
	_cache_set(_draft_key(), None)


def _owned(name: str):
	name = (name or "").strip()
	if not name or not frappe.db.exists(CONVERSATION, name):
		return None
	owner = frappe.db.get_value(CONVERSATION, name, "user")
	if owner != frappe.session.user:
		return None
	return frappe.get_doc(CONVERSATION, name)


def _message_payload(row) -> dict:
	return {
		"role": row.role,
		"content": row.content or "",
		"kind": row.kind or "message",
		"sent_at": str(row.sent_at or row.creation or ""),
		"links": _clean_links(row.links_json),
	}


def _summary(doc) -> dict:
	return {
		"name": doc.name,
		"title": doc.title,
		"modified": str(doc.modified),
		"creation": str(doc.creation),
	}


@frappe.whitelist()
def list_conversations(start: int | str = 0, limit: int | str = PAGE_SIZE) -> dict:
	"""Conversation titles only. Messages load when one conversation is opened."""
	user = _require_user()
	try:
		start_at = max(0, int(start or 0))
		page = max(1, min(int(limit or PAGE_SIZE), PAGE_SIZE))
	except (TypeError, ValueError):
		start_at, page = 0, PAGE_SIZE
	rows = frappe.get_all(
		CONVERSATION,
		filters={"user": user},
		fields=["name", "title", "modified", "creation"],
		order_by="modified desc",
		limit_start=start_at,
		limit_page_length=page + 1,
	)
	has_more = len(rows) > page
	return {
		"ok": True,
		"conversations": rows[:page],
		"has_more": has_more,
		"next_start": start_at + page if has_more else None,
	}


@frappe.whitelist()
def get_conversation(name: str | None = None) -> dict:
	"""Load one owned conversation and restore its topic for follow-up questions."""
	_require_user()
	doc = _owned(name or "")
	if not doc:
		return {"ok": False, "error": "That conversation is not available."}
	topic = _clean_topic(doc.topic_json)
	_restore_topic(topic)
	_clear_pending()
	return {
		"ok": True,
		"name": doc.name,
		"title": doc.title,
		"modified": str(doc.modified),
		"creation": str(doc.creation),
		"messages": [_message_payload(row) for row in doc.messages],
	}


@frappe.whitelist()
def start_conversation() -> dict:
	"""Begin a new conversation without deleting older ones."""
	user = _require_user()
	try:
		_restore_topic(None)
		_clear_pending()
		doc = frappe.get_doc({"doctype": CONVERSATION, "user": user, "title": "New chat"})
		doc.insert(ignore_permissions=True)
		return {"ok": True, **_summary(doc)}
	except Exception:
		_log_failure("OpenAS2 AI history start")
		return {"ok": False, "error": "Couldn't start a new conversation."}


@frappe.whitelist()
def clear_conversation_context() -> dict:
	"""Drop the live follow-up topic so a new chat does not reuse the previous one."""
	_require_user()
	try:
		_restore_topic(None)
		_clear_pending()
		return {"ok": True}
	except Exception:
		_log_failure("OpenAS2 AI history clear")
		return {"ok": False}


@frappe.whitelist()
def record_turn(
	conversation: str | None = None,
	user_message: str | None = None,
	reply: str | None = None,
	kind: str | None = None,
	links=None,
) -> dict:
	"""Append a turn after the existing chat flow. Failures stay out of the chat UI."""
	user = _require_user()
	user_text = _redact_secrets(_clip(user_message)) if user_message else ""
	assistant_text = _redact_secrets(_clip(reply)) if reply is not None and str(reply).strip() else ""
	safe_links = _clean_links(links)
	if not user_text and not assistant_text and not safe_links:
		return {"ok": False, "error": "Nothing to save."}
	try:
		doc = _owned(conversation or "")
		if not doc:
			title = conversation_title(user_text or assistant_text)
			doc = frappe.get_doc({"doctype": CONVERSATION, "user": user, "title": title})
			doc.insert(ignore_permissions=True)
		elif (not doc.title or doc.title == "New chat") and user_text:
			doc.title = conversation_title(user_text)
		stamp = now_datetime()
		if len(doc.messages) >= MAX_MESSAGES:
			return {"ok": False, "error": "This conversation is full.", "name": doc.name, "title": doc.title}
		if user_text:
			doc.append(
				"messages",
				{"role": "user", "kind": "message", "content": user_text, "sent_at": stamp, "links_json": ""},
			)
		if assistant_text or safe_links:
			safe_kind = kind if kind in KINDS else "message"
			doc.append(
				"messages",
				{
					"role": "assistant",
					"kind": safe_kind,
					"content": assistant_text,
					"sent_at": stamp,
					"links_json": json.dumps(safe_links),
				},
			)
		topic = _current_topic()
		doc.topic_json = json.dumps(topic) if topic else ""
		doc.save(ignore_permissions=True)
		return {"ok": True, **_summary(doc)}
	except Exception:
		_log_failure("OpenAS2 AI history save")
		return {"ok": False, "error": "Couldn't save this conversation."}


@frappe.whitelist()
def rename_conversation(name: str | None = None, title: str | None = None) -> dict:
	_require_user()
	doc = _owned(name or "")
	if not doc:
		return {"ok": False, "error": "That conversation is not available."}
	cleaned = conversation_title(title or "")
	if not cleaned or cleaned == "New chat":
		return {"ok": False, "error": "Enter a conversation title."}
	try:
		doc.title = cleaned
		doc.save(ignore_permissions=True)
		return {"ok": True, **_summary(doc)}
	except Exception:
		_log_failure("OpenAS2 AI history rename")
		return {"ok": False, "error": "Couldn't rename that conversation."}


@frappe.whitelist()
def delete_conversation(name: str | None = None) -> dict:
	_require_user()
	doc = _owned(name or "")
	if not doc:
		return {"ok": False, "error": "That conversation is not available."}
	try:
		frappe.delete_doc(CONVERSATION, doc.name, ignore_permissions=True)
		return {"ok": True, "name": doc.name}
	except Exception:
		_log_failure("OpenAS2 AI history delete")
		return {"ok": False, "error": "Couldn't delete that conversation."}
