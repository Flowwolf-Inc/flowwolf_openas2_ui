"""Pure KPI merge logic for the Home dashboard (mirrors openas2_dashboard.js)."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

KPI_CODES = ("204", "990", "210", "214")


def kpi_count_valid(count: Any) -> bool:
	return count is not None


def default_kpi_cards() -> list[dict]:
	labels = {
		"204": "Load Tender",
		"990": "Ack",
		"210": "Invoice",
		"214": "Status",
	}
	return [
		{
			"code": code,
			"label": labels[code],
			"count": None,
			"last_7": None,
			"change_pct": None,
			"available": False,
		}
		for code in KPI_CODES
	]


def store_kpi_snapshot(by_code: dict[str, dict], kpis: list[dict] | None) -> None:
	for k in kpis or []:
		code = str(k.get("code") or "")
		if not code or not kpi_count_valid(k.get("count")):
			continue
		by_code[code] = deepcopy(k)


def kpis_for_display(
	by_code: dict[str, dict],
	last_shells: list[dict] | None,
	incoming: list[dict] | None,
) -> tuple[list[dict], list[dict] | None]:
	list_in = incoming or []
	shells_out = last_shells
	if list_in:
		has_any_valid = any(kpi_count_valid(k.get("count")) for k in list_in)
		has_snapshot = bool(by_code)
		if has_any_valid or not has_snapshot:
			shells_out = [deepcopy(k) for k in list_in]
	store_kpi_snapshot(by_code, list_in)
	shells = (
		list_in
		if list_in
		else shells_out
		if shells_out
		else default_kpi_cards()
	)
	display: list[dict] = []
	for k in shells:
		code = str(k.get("code") or "")
		held = by_code.get(code)
		if not held or kpi_count_valid(k.get("count")):
			display.append(k)
			continue
		merged = deepcopy(k)
		merged["count"] = held["count"]
		if held.get("last_7") is not None:
			merged["last_7"] = held["last_7"]
		if held.get("change_pct") is not None:
			merged["change_pct"] = held["change_pct"]
		if held.get("available") is not False:
			merged["available"] = True
		display.append(merged)
	return display, shells_out


def ingest_edi_chart_totals(by_code: dict[str, dict], payload: dict) -> bool:
	if payload.get("edi_counts_available") is not True:
		return False
	by_type = payload.get("edi_status_by_type") or {}
	labels = {
		"204": "Load Tender",
		"990": "Ack",
		"210": "Invoice",
		"214": "Status",
	}
	updated = False
	for code in KPI_CODES:
		row = by_type.get(code) or {}
		total = row.get("total")
		if not kpi_count_valid(total):
			continue
		try:
			count = int(total)
		except (TypeError, ValueError):
			continue
		prev = by_code.get(code) or {}
		by_code[code] = {
			**prev,
			"code": code,
			"label": prev.get("label") or labels[code],
			"count": count,
			"available": True,
		}
		updated = True
	return updated
