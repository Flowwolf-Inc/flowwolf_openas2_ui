# Copyright (c) 2026, Lakshana and contributors
# For license information, please see license.txt

"""Manual Phase 2 smoke: Start → Status → Stop via Frappe client (Agent on Windows)."""

from __future__ import annotations

import json

from openas2_manager.openas2.runtime_control import runtime_control, runtime_status


def main():
	name = "Broker ABC Demo"
	print("STATUS before:", json.dumps(runtime_status(name), indent=2, default=str))
	print("START:", json.dumps(runtime_control(name, "start", confirmed=1), indent=2, default=str))
	print("STATUS running:", json.dumps(runtime_status(name), indent=2, default=str))
	print("STOP:", json.dumps(runtime_control(name, "stop", confirmed=1), indent=2, default=str))
	print("STATUS after:", json.dumps(runtime_status(name), indent=2, default=str))
