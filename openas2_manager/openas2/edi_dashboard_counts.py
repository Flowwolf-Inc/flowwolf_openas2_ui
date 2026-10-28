"""Authoritative cache-backed counts for the four Home EDI panels (204/990/210/214).

Uses the external OpenAS2 ``msg_metadata`` database with the same SQL
classification rules as Monitoring (``remote_tracking.build_edi_card_*``).
Dashboard HTTP handlers never scan the full table; one daemon-thread refresh
at a time populates Redis.
"""

from __future__ import annotations

import hashlib
import secrets
import time
from datetime import datetime
from threading import Thread

import frappe

from openas2_manager.openas2 import remote_tracking as remote
from openas2_manager.openas2.remote_tracking import (
	EDI_CARD_CODES,
	EDI_TRANSACTION_COUNT_LIMITATION,
	REMOTE_READ_ERROR,
	_card_windows,
	bind_edi_card_counts,
	merge_card_count_rows,
	read_settings,
	remote_database_ping,
	remote_read_config_message,
	remote_reads_enabled,
	resolve_edi_dashboard_read_error,
	resolve_scope,
	unavailable_edi_counts,
	valid_card_cache,
	_card_count_chunk_on_conn,
	build_card_bounds_query,
	card_id_ranges,
	connect,
	_execute,
	_remote_error_summary,
	_unavailable,
	_warn,
)

PANEL_CACHE_PREFIX = "oa2_edi_panels:v3"
PANEL_CACHE_TTL_SECONDS = 6 * 60 * 60
PANEL_LOCK_TTL_SECONDS = 7200
PANEL_LOCK_IDLE_SECONDS = 120
PANEL_SCHEDULED_STALE_SECONDS = 180


def _cache_get(key: str):
	try:
		return frappe.cache().get_value(key)
	except Exception:
		return None


def _cache_set(key: str, value: dict, *, expires: int = PANEL_CACHE_TTL_SECONDS) -> None:
	try:
		frappe.cache().set_value(key, value, expires_in_sec=expires)
	except Exception as exc:
		_warn(f"OpenAS2 EDI panel cache could not be stored ({type(exc).__name__}).")


def _cache_delete(key: str) -> None:
	try:
		frappe.cache().delete_value(key)
	except Exception:
		return


def _scope_token(query_ids) -> str:
	if query_ids is None:
		return "*"
	return ",".join(sorted(str(item) for item in query_ids)) or "-"


def panel_cache_key(now: datetime | None = None) -> str | None:
	if not remote_reads_enabled():
		return None
	settings, _reason = read_settings()
	if not settings:
		return None
	scope = resolve_scope()
	if scope is None:
		return None
	last_7_start, _prev = _card_windows(now)
	stamp = last_7_start.strftime("%Y%m%d%H%M%S")
	return f"{PANEL_CACHE_PREFIX}:{stamp}:{_scope_token(scope['query_ids'])}"


def _lock_key(cache_key: str) -> str:
	return f"{cache_key}:lock"


def _last_key(cache_key: str) -> str:
	return f"{cache_key}:last"


def _sched_key(cache_key: str) -> str:
	return f"{cache_key}:scheduled"


def _error_key(cache_key: str) -> str:
	return f"{cache_key}:error"


def _lock_heartbeat(payload: dict | None) -> float:
	if not isinstance(payload, dict):
		return 0.0
	for name in ("heartbeat_at", "acquired_at"):
		try:
			return float(payload[name])
		except (KeyError, TypeError, ValueError):
			continue
	return 0.0


def _lock_is_stale(payload: dict | None, cache_key: str, now: float | None = None) -> bool:
	if not isinstance(payload, dict) or not payload.get("held"):
		return True
	now = time.time() if now is None else now
	heartbeat = _lock_heartbeat(payload)
	if now - heartbeat > PANEL_LOCK_IDLE_SECONDS and not _peek_cached(cache_key):
		return True
	return False


def _peek_cached(cache_key: str, *, allow_partial: bool = False) -> dict | None:
	for key in (cache_key, _last_key(cache_key)):
		raw = _cache_get(key)
		parsed = valid_card_cache(raw)
		if not parsed or not parsed.get("counts"):
			continue
		if isinstance(raw, dict) and raw.get("complete") is False and not allow_partial:
			parsed = dict(parsed)
			parsed["_partial"] = True
			return parsed
		return parsed
	return None


def _cache_is_final(cached: dict | None) -> bool:
	if not cached or not cached.get("ok"):
		return False
	if cached.get("_partial"):
		return False
	return True


def panel_read_error(cache_key: str | None = None) -> str | None:
	cache_key = cache_key or panel_cache_key()
	if not cache_key:
		return None
	payload = _cache_get(_error_key(cache_key))
	if not isinstance(payload, dict):
		return None
	message = payload.get("message")
	return str(message).strip() if message else None


def panel_refresh_in_progress(cache_key: str | None = None) -> bool:
	cache_key = cache_key or panel_cache_key()
	if not cache_key:
		return False
	payload = _cache_get(_lock_key(cache_key))
	if payload is None:
		return False
	if _lock_is_stale(payload, cache_key):
		_cache_delete(_lock_key(cache_key))
		return False
	return True


def _clear_stale_scheduled(cache_key: str) -> None:
	payload = _cache_get(_sched_key(cache_key))
	if not isinstance(payload, dict):
		return
	try:
		started = float(payload.get("at") or 0)
	except (TypeError, ValueError):
		_cache_delete(_sched_key(cache_key))
		return
	if time.time() - started > PANEL_SCHEDULED_STALE_SECONDS:
		_cache_delete(_sched_key(cache_key))


def _acquire_lock(cache_key: str, *, force: bool = False) -> bool:
	lock_key = _lock_key(cache_key)
	now = time.time()
	existing = _cache_get(lock_key)
	if existing is not None and not _lock_is_stale(existing, cache_key, now):
		if not force:
			return False
	_cache_delete(lock_key)
	token = secrets.token_hex(16)
	payload = {"held": 1, "token": token, "acquired_at": now, "heartbeat_at": now}
	_cache_set(lock_key, payload, expires=PANEL_LOCK_TTL_SECONDS)
	stored = _cache_get(lock_key)
	return isinstance(stored, dict) and stored.get("token") == token


def _touch_lock(cache_key: str, token: str) -> None:
	lock_key = _lock_key(cache_key)
	stored = _cache_get(lock_key)
	if not isinstance(stored, dict) or stored.get("token") != token:
		return
	updated = dict(stored)
	updated["heartbeat_at"] = time.time()
	_cache_set(lock_key, updated, expires=PANEL_LOCK_TTL_SECONDS)


def _release_lock(cache_key: str, token: str | None) -> None:
	if not token:
		return
	lock_key = _lock_key(cache_key)
	stored = _cache_get(lock_key)
	if isinstance(stored, dict) and stored.get("token") == token:
		_cache_delete(lock_key)


def store_panel_aggregation(cache_key: str, result: dict, *, complete: bool = True) -> None:
	if not result.get("ok"):
		_cache_set(
			_error_key(cache_key),
			{"at": time.time(), "message": REMOTE_READ_ERROR},
			expires=3600,
		)
		return
	stored = dict(result)
	stored["computed_at"] = time.time()
	stored["complete"] = complete
	_cache_set(cache_key, stored)
	_cache_set(_last_key(cache_key), stored)
	_cache_delete(_error_key(cache_key))


def read_panel_cache(now: datetime | None = None) -> dict:
	"""Cache-only read for dashboard handlers. Never queries msg_metadata."""
	from openas2_manager.openas2.remote_tracking import _empty_card_counts, _failed_card_counts

	if not remote_reads_enabled():
		return _failed_card_counts()
	settings, reason = read_settings()
	if not settings:
		_unavailable(reason)
		return _failed_card_counts()
	scope = resolve_scope()
	if scope is None:
		return _empty_card_counts()
	key = panel_cache_key(now)
	if not key:
		return _failed_card_counts()
	parsed = _peek_cached(key)
	if parsed:
		return parsed
	return _failed_card_counts()


def schedule_panel_refresh(cache_key: str | None = None) -> None:
	"""Start one daemon-thread refresh (no RQ dependency)."""
	cache_key = cache_key or panel_cache_key()
	if not cache_key:
		return
	if panel_refresh_in_progress(cache_key):
		return
	_clear_stale_scheduled(cache_key)
	sched = _cache_get(_sched_key(cache_key))
	if isinstance(sched, dict):
		try:
			if time.time() - float(sched.get("at") or 0) < PANEL_SCHEDULED_STALE_SECONDS:
				return
		except (TypeError, ValueError):
			pass
	_cache_set(_sched_key(cache_key), {"at": time.time()}, expires=PANEL_SCHEDULED_STALE_SECONDS + 60)
	try:
		user = frappe.session.user
		site = frappe.local.site
	except RuntimeError:
		user = "Administrator"
		site = getattr(getattr(frappe, "local", None), "site", None)
	Thread(
		target=_run_panel_refresh_thread,
		args=(cache_key,),
		kwargs={"user": user, "site": site},
		daemon=True,
	).start()


def _run_panel_refresh_thread(cache_key: str, *, user: str, site: str) -> None:
	try:
		frappe.init(site=site)
		frappe.connect()
		frappe.set_user(user)
		frappe.flags.oa2_remote_read = True
		run_panel_refresh(cache_key=cache_key)
	except Exception as exc:
		_cache_set(
			_error_key(cache_key),
			{"at": time.time(), "message": _remote_error_summary(exc)},
			expires=3600,
		)
		_warn(f"OpenAS2 EDI panel refresh failed ({type(exc).__name__}).")
	finally:
		_cache_delete(_sched_key(cache_key))
		try:
			frappe.db.close()
		except Exception:
			pass


def run_panel_refresh(*, cache_key: str | None = None, force: bool = False) -> dict:
	"""Compute counts once and store under ``cache_key``."""
	from openas2_manager.openas2.remote_tracking import _failed_card_counts

	cache_key = cache_key or panel_cache_key()
	if not cache_key:
		return {"ok": False, "error": "scope_unavailable"}
	token = None
	if not _acquire_lock(cache_key, force=force):
		return {"ok": False, "skipped": True}
	stored = _cache_get(_lock_key(cache_key))
	token = stored.get("token") if isinstance(stored, dict) else None
	try:
		result = _compute_chunked_with_progress(cache_key, token)
		store_panel_aggregation(cache_key, result, complete=True)
		return result
	except Exception as exc:
		_cache_set(
			_error_key(cache_key),
			{"at": time.time(), "message": _remote_error_summary(exc)},
			expires=3600,
		)
		raise
	finally:
		_release_lock(cache_key, token)


def _compute_chunked_with_progress(cache_key: str, token: str | None) -> dict:
	"""Chunked aggregation with partial cache writes after each id range."""

	def _partial(merged: dict) -> None:
		if token:
			_touch_lock(cache_key, token)
		if merged.get("ok"):
			store_panel_aggregation(cache_key, merged, complete=False)

	return remote.aggregate_edi_cards_chunked(cache_key=cache_key, on_partial=_partial)


def probe_panel_classification() -> dict:
	"""Bounded live read: bounds + first primary-key chunk only."""
	from openas2_manager.openas2.remote_tracking import _failed_card_counts

	if not remote_reads_enabled():
		return {"ok": False, "error": "remote_disabled"}
	settings, reason = read_settings()
	if not settings:
		return {"ok": False, "error": remote_read_config_message(reason)}
	ping = remote_database_ping(settings)
	if ping:
		return {"ok": False, "error": ping}
	scope = resolve_scope()
	if scope is None:
		return {"ok": False, "error": "empty_scope"}
	last_7_start, prev_7_start = _card_windows()
	bounds_sql, bounds_params = build_card_bounds_query(scope["query_ids"])
	conn = connect(settings, read_timeout=120)
	try:
		bound_rows = _execute(conn, bounds_sql, bounds_params)
		bound = bound_rows[0] if bound_rows else {}
		low, high = bound.get("lo"), bound.get("hi")
		if low is None or high is None:
			return {"ok": True, "counts": {c: 0 for c in EDI_CARD_CODES}, "probe": "empty_table"}
		ranges = card_id_ranges(int(low), int(high))
		if not ranges:
			return {"ok": True, "counts": {c: 0 for c in EDI_CARD_CODES}, "probe": "empty_range"}
		id_from, id_to = ranges[0]
		raw = _card_count_chunk_on_conn(
			conn,
			scope["query_ids"],
			last_7_start,
			prev_7_start,
			id_from,
			id_to,
			read_timeout=120,
		)
		merged = merge_card_count_rows([raw])
		return {
			"ok": True,
			"probe": "first_chunk",
			"id_from": id_from,
			"id_to": id_to,
			"counts": merged.get("counts"),
		}
	except Exception as exc:
		return {"ok": False, "error": _remote_error_summary(exc, settings.get("password") or "")}
	finally:
		conn.close()


def _rollup_status_for_chart(status_by_type: dict) -> tuple[dict, int, int, int, int]:
	total = success = progress = failure = 0
	for code in EDI_CARD_CODES:
		row = status_by_type.get(code) or {}
		total += int(row.get("total") or 0)
		success += int(row.get("success") or 0)
		progress += int(row.get("in_progress") or 0)
		failure += int(row.get("failure") or 0)
	return status_by_type, total, success, progress, failure


def attach_dashboard_edi_panels(summary: dict) -> None:
	"""Fill ``summary`` KPI fields for the four EDI panels (cache-only HTTP path)."""
	summary.update(unavailable_edi_counts())
	cache_key = panel_cache_key()
	cached = read_panel_cache()
	if not (cached.get("ok") and cached.get("counts")):
		if cache_key and not panel_refresh_in_progress(cache_key):
			schedule_panel_refresh(cache_key)
	final = _cache_is_final(cached)
	bind_edi_card_counts(summary["kpis"], counts=cached if cached.get("ok") and final else None)
	if final:
		summary["edi_counts_available"] = True
		summary["edi_counts_limitation"] = ""
		if cached.get("status_by_type"):
			by_type, total, success, progress, failure = _rollup_status_for_chart(cached["status_by_type"])
			summary["edi_status_by_type"] = by_type
			summary["transactions_total"] = total
			summary["success"] = success
			summary["in_progress"] = progress
			summary["failure"] = failure
	else:
		summary["edi_counts_available"] = False
		if cached.get("status_by_type") and cached.get("_partial"):
			from openas2_manager.openas2.edi_home_chart import _status_totals_consistent

			if _status_totals_consistent(cached["status_by_type"]):
				by_type, total, success, progress, failure = _rollup_status_for_chart(
					cached["status_by_type"]
				)
				summary["edi_chart_ready"] = True
				summary["edi_status_by_type"] = by_type
				summary["transactions_total"] = total
				summary["success"] = success
				summary["in_progress"] = progress
				summary["failure"] = failure
	refreshing = bool(cache_key and (panel_refresh_in_progress(cache_key) or cached.get("_partial")))
	summary["edi_refresh_in_progress"] = refreshing
	read_error = resolve_edi_dashboard_read_error(cache_key, result=cached if final else None)
	if cached.get("_partial") and not final:
		read_error = "EDI totals are refreshing in the background."
	if read_error and not summary.get("edi_counts_available"):
		summary["edi_counts_limitation"] = read_error
		for card in summary.get("kpis") or []:
			if card.get("count") is None:
				card["note"] = read_error


def run_controlled_panel_refresh() -> dict:
	"""Ops entry: one forced refresh when no active heartbeating holder."""
	frappe.flags.oa2_remote_read = True
	cache_key = panel_cache_key()
	if not cache_key:
		return {"ok": False, "error": "scope_unavailable"}
	cached = _peek_cached(cache_key)
	if cached:
		return cached
	lock = _cache_get(_lock_key(cache_key))
	if lock is not None:
		heartbeat = _lock_heartbeat(lock)
		active = time.time() - heartbeat < PANEL_LOCK_IDLE_SECONDS
		if active:
			return {"ok": False, "skipped": True, "error": "refresh_in_progress"}
	_cache_delete(_lock_key(cache_key))
	_cache_delete(_sched_key(cache_key))
	return run_panel_refresh(cache_key=cache_key, force=True)
