"""Home dashboard EDI Transactions chart — single backend pipeline.

Reads ``msg_metadata`` on the configured external OpenAS2 database using the
same SQL classification and status rules as Monitoring
(``remote_tracking.aggregate_edi_cards_chunked``). One optional Redis snapshot
after a successful full aggregation; HTTP handlers never scan the table.
"""

from __future__ import annotations

import time
from threading import Thread

import frappe

from openas2_manager.openas2.remote_tracking import (
	EDI_CARD_CODES,
	EDI_TRANSACTION_COUNT_LIMITATION,
	REMOTE_READ_ERROR,
	aggregate_edi_cards_chunked,
	read_settings,
	remote_database_ping,
	remote_read_config_message,
	remote_reads_enabled,
	resolve_scope,
	_remote_error_summary,
	_unavailable,
	_warn,
)

CHART_CACHE_PREFIX = "oa2_edi_home_chart:v1"
CHART_CACHE_TTL_SECONDS = 3600
REFRESH_FLAG_TTL_SECONDS = 7200


def _scope_token(query_ids) -> str:
	if query_ids is None:
		return "*"
	return ",".join(sorted(str(item) for item in query_ids)) or "-"


def chart_cache_key() -> str | None:
	if not remote_reads_enabled():
		return None
	settings, _reason = read_settings()
	if not settings:
		return None
	scope = resolve_scope()
	if scope is None:
		return None
	return f"{CHART_CACHE_PREFIX}:{_scope_token(scope['query_ids'])}"


def _refresh_flag_key(cache_key: str) -> str:
	return f"{cache_key}:refreshing"


def _error_key(cache_key: str) -> str:
	return f"{cache_key}:error"


def _cache_get(key: str):
	try:
		return frappe.cache().get_value(key)
	except Exception:
		return None


def _cache_set(key: str, value: dict, *, expires: int) -> None:
	try:
		frappe.cache().set_value(key, value, expires_in_sec=expires)
	except Exception as exc:
		_warn(f"OpenAS2 EDI chart cache could not be stored ({type(exc).__name__}).")


def _cache_delete(key: str) -> None:
	try:
		frappe.cache().delete_value(key)
	except Exception:
		return


def _read_snapshot() -> dict | None:
	key = chart_cache_key()
	if not key:
		return None
	payload = _cache_get(key)
	if not isinstance(payload, dict) or not payload.get("status_by_type"):
		return None
	if payload.get("complete") is False:
		return None
	if not _status_totals_consistent(payload["status_by_type"]):
		return None
	return payload


def _status_totals_consistent(by_type: dict) -> bool:
	for code in EDI_CARD_CODES:
		row = by_type.get(code)
		if not isinstance(row, dict):
			return False
		try:
			total = int(row["total"])
			success = int(row["success"])
			progress = int(row["in_progress"])
			failure = int(row["failure"])
		except (KeyError, TypeError, ValueError):
			return False
		if success + progress + failure != total:
			return False
		if total < 0 or success < 0 or progress < 0 or failure < 0:
			return False
	return True


def _rollup(status_by_type: dict) -> tuple[int, int, int, int]:
	total = success = progress = failure = 0
	for code in EDI_CARD_CODES:
		row = status_by_type[code]
		total += int(row["total"])
		success += int(row["success"])
		progress += int(row["in_progress"])
		failure += int(row["failure"])
	return total, success, progress, failure


def format_chart_response(
	snapshot: dict | None,
	*,
	refreshing: bool = False,
	error: str | None = None,
) -> dict:
	"""Shape expected by ``openas2_dashboard.js`` ``apply_edi_transactions``."""
	out = {
		"ok": False,
		"edi_counts_available": False,
		"edi_refresh_in_progress": refreshing,
		"transactions_total": None,
		"success": None,
		"in_progress": None,
		"failure": None,
		"edi_status_by_type": {
			code: {
				"total": None,
				"success": None,
				"in_progress": None,
				"failure": None,
				"available": False,
			}
			for code in EDI_CARD_CODES
		},
		"edi_counts_limitation": error or EDI_TRANSACTION_COUNT_LIMITATION,
		"error": error,
		"computed_at": None,
	}
	if not snapshot or not snapshot.get("status_by_type"):
		return out
	by_type = snapshot["status_by_type"]
	if not _status_totals_consistent(by_type):
		out["error"] = "EDI chart totals were inconsistent after aggregation."
		out["edi_counts_limitation"] = out["error"]
		return out
	total, success, progress, failure = _rollup(by_type)
	out.update(
		{
			"ok": True,
			"edi_counts_available": True,
			"edi_refresh_in_progress": bool(refreshing),
			"transactions_total": total,
			"success": success,
			"in_progress": progress,
			"failure": failure,
			"edi_status_by_type": by_type,
			"edi_counts_limitation": "",
			"error": None,
			"computed_at": snapshot.get("computed_at"),
		}
	)
	return out


def _refresh_in_progress(cache_key: str) -> bool:
	flag = _cache_get(_refresh_flag_key(cache_key))
	if not isinstance(flag, dict):
		return False
	try:
		started = float(flag.get("started_at") or 0)
	except (TypeError, ValueError):
		_cache_delete(_refresh_flag_key(cache_key))
		return False
	if time.time() - started > REFRESH_FLAG_TTL_SECONDS:
		_cache_delete(_refresh_flag_key(cache_key))
		return False
	return True


def _mark_refresh_started(cache_key: str) -> bool:
	if _refresh_in_progress(cache_key):
		return False
	_cache_set(
		_refresh_flag_key(cache_key),
		{"started_at": time.time()},
		expires=REFRESH_FLAG_TTL_SECONDS,
	)
	return True


def _mark_refresh_finished(cache_key: str) -> None:
	_cache_delete(_refresh_flag_key(cache_key))


def chart_read_error(cache_key: str | None = None) -> str | None:
	cache_key = cache_key or chart_cache_key()
	if not cache_key:
		return None
	payload = _cache_get(_error_key(cache_key))
	if not isinstance(payload, dict):
		return None
	message = payload.get("message")
	return str(message).strip() if message else None


def _store_refresh_error(cache_key: str, exc: BaseException | None) -> None:
	summary = _remote_error_summary(exc) if exc is not None else REMOTE_READ_ERROR
	_cache_set(
		_error_key(cache_key),
		{"at": time.time(), "message": summary or REMOTE_READ_ERROR},
		expires=3600,
	)


def _clear_refresh_error(cache_key: str) -> None:
	_cache_delete(_error_key(cache_key))


def aggregate_msg_metadata_chart() -> dict:
	"""Full-table chunked aggregation (Monitoring rules). For background refresh only."""
	cache_key = chart_cache_key()

	def _partial(merged: dict) -> None:
		if not cache_key or not merged.get("status_by_type"):
			return
		_store_snapshot(
			{
				"status_by_type": merged["status_by_type"],
				"computed_at": time.time(),
				"complete": False,
			}
		)

	try:
		merged = aggregate_edi_cards_chunked(on_partial=_partial)
	except Exception as exc:
		if cache_key:
			_store_refresh_error(cache_key, exc)
		_unavailable(None, exc)
		return {"ok": False, "error": _remote_error_summary(exc)}
	if not merged.get("ok"):
		err = chart_read_error(cache_key) or REMOTE_READ_ERROR
		return {"ok": False, "error": err}
	status = merged.get("status_by_type")
	if not status:
		return {"ok": False, "error": "empty_aggregation"}
	if cache_key:
		_clear_refresh_error(cache_key)
	return {
		"ok": True,
		"status_by_type": status,
		"computed_at": time.time(),
		"complete": True,
	}


def _store_snapshot(snapshot: dict) -> None:
	key = chart_cache_key()
	if not key:
		return
	_cache_set(key, snapshot, expires=CHART_CACHE_TTL_SECONDS)


def run_chart_refresh_sync(*, force: bool = False) -> dict:
	"""Ops / verification: compute and store one chart snapshot."""
	frappe.flags.oa2_remote_read = True
	cache_key = chart_cache_key()
	if not cache_key:
		return {"ok": False, "error": "scope_unavailable"}
	if not force and not _mark_refresh_started(cache_key):
		return {"ok": False, "skipped": True, "error": "refresh_in_progress"}
	if force:
		_cache_delete(_refresh_flag_key(cache_key))
		_mark_refresh_started(cache_key)
	try:
		result = aggregate_msg_metadata_chart()
		if result.get("ok") and result.get("status_by_type"):
			stored = {
				"status_by_type": result["status_by_type"],
				"computed_at": result.get("computed_at") or time.time(),
				"complete": True,
			}
			_store_snapshot(stored)
		elif not result.get("ok") and cache_key:
			_store_refresh_error(cache_key, Exception(result.get("error") or REMOTE_READ_ERROR))
		return result
	finally:
		_mark_refresh_finished(cache_key)


def _refresh_thread(cache_key: str, *, user: str, site: str) -> None:
	try:
		frappe.init(site=site)
		frappe.connect()
		frappe.set_user(user)
		frappe.flags.oa2_remote_read = True
		result = aggregate_msg_metadata_chart()
		if result.get("ok") and result.get("status_by_type"):
			_store_snapshot(
				{
					"status_by_type": result["status_by_type"],
					"computed_at": result.get("computed_at") or time.time(),
					"complete": True,
				}
			)
		elif not result.get("ok"):
			_store_refresh_error(cache_key, Exception(result.get("error") or REMOTE_READ_ERROR))
			_warn(f"OpenAS2 EDI chart refresh failed ({result.get('error')}).")
	except Exception as exc:
		_store_refresh_error(cache_key, exc)
		_warn(f"OpenAS2 EDI chart refresh failed ({type(exc).__name__}).")
	finally:
		_mark_refresh_finished(cache_key)
		try:
			frappe.db.close()
		except Exception:
			pass


def _schedule_refresh() -> None:
	cache_key = chart_cache_key()
	if not cache_key or _refresh_in_progress(cache_key):
		return
	if not _mark_refresh_started(cache_key):
		return
	try:
		user = frappe.session.user
		site = frappe.local.site
	except RuntimeError:
		user = "Administrator"
		site = getattr(getattr(frappe, "local", None), "site", None)
	Thread(
		target=_refresh_thread,
		args=(cache_key,),
		kwargs={"user": user, "site": site},
		daemon=True,
	).start()


def _panel_chart_snapshot(*, allow_partial: bool = False) -> dict | None:
	"""Reuse panel Redis aggregation (final or in-progress partial scan)."""
	from openas2_manager.openas2.edi_dashboard_counts import (
		_cache_is_final,
		panel_cache_key,
		_peek_cached,
	)

	key = panel_cache_key()
	if not key:
		return None
	cached = _peek_cached(key, allow_partial=allow_partial)
	if not cached or not cached.get("status_by_type"):
		return None
	if not _status_totals_consistent(cached["status_by_type"]):
		return None
	if not allow_partial and not _cache_is_final(cached):
		return None
	partial = bool(cached.get("_partial"))
	return {
		"status_by_type": cached["status_by_type"],
		"computed_at": cached.get("computed_at"),
		"complete": not partial and _cache_is_final(cached),
		"_partial": partial,
	}


def _log_chart_api_ms(started: float, outcome: str) -> None:
	ms = (time.perf_counter() - started) * 1000
	frappe.logger("openas2_edi_chart").info(
		f"get_edi_transactions_counts {outcome} {ms:.1f}ms"
	)


def get_edi_home_chart_response() -> dict:
	"""Whitelist handler for ``get_edi_transactions_counts`` (cache-only; no table scan)."""
	started = time.perf_counter()
	if not remote_reads_enabled():
		out = format_chart_response(None, error="OpenAS2 remote reads are disabled.")
		_log_chart_api_ms(started, "remote_disabled")
		return out
	settings, reason = read_settings()
	if not settings:
		out = format_chart_response(None, error=remote_read_config_message(reason))
		_log_chart_api_ms(started, "config_missing")
		return out

	from openas2_manager.openas2.edi_dashboard_counts import (
		panel_cache_key,
		panel_read_error,
		panel_refresh_in_progress,
		schedule_panel_refresh,
	)

	snapshot = _read_snapshot() or _panel_chart_snapshot(allow_partial=True)
	if snapshot:
		partial = snapshot.get("_partial") or snapshot.get("complete") is False
		pcache = panel_cache_key()
		refreshing = partial or panel_refresh_in_progress(pcache)
		out = format_chart_response(snapshot, refreshing=refreshing)
		_log_chart_api_ms(started, "cache_hit" if not partial else "partial_hit")
		return out

	pcache = panel_cache_key()
	refreshing = panel_refresh_in_progress(pcache)
	if pcache and not refreshing:
		schedule_panel_refresh(pcache)
		refreshing = panel_refresh_in_progress(pcache)

	read_error = panel_read_error(pcache)
	if read_error and not refreshing:
		out = format_chart_response(None, error=read_error)
		_log_chart_api_ms(started, "panel_error")
		return out
	out = format_chart_response(
		None,
		refreshing=refreshing,
		error=(
			"EDI chart totals are being computed from msg_metadata. "
			"This may take several minutes on first load."
		),
	)
	_log_chart_api_ms(started, "miss_scheduled" if refreshing else "miss_idle")
	return out
