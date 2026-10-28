# Copyright (c) 2026, Lakshana and contributors
# For license information, please see license.txt

"""Frappe ↔ OpenAS2 Runtime Agent client (Phase 2).

Talks only to a localhost agent with fixed actions. Never executes
user-supplied shell/BAT/paths. System Manager + confirmation for mutating ops.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import frappe
from frappe.utils import cint, now_datetime

from openas2_manager.openas2.paths import assert_under_directory, get_instances_root, to_windows_path

ALLOWED_ACTIONS = frozenset({"start", "stop", "restart", "status", "health", "logs", "ping"})
MUTATING = frozenset({"start", "stop", "restart"})


def _require_system_manager():
	if "System Manager" not in frappe.get_roles(frappe.session.user):
		frappe.throw(
			frappe._("Only System Managers may control OpenAS2 runtimes."),
			frappe.PermissionError,
		)


def agent_url() -> str:
	"""Return Runtime Agent base URL.

	Prefer site_config. On WSL, ``127.0.0.1`` is the Linux VM — not Windows.
	If unset URL is localhost and we detect WSL, use the Windows host gateway.
	"""
	configured = (frappe.conf.get("openas2_runtime_agent_url") or "").strip().rstrip("/")
	if configured and "127.0.0.1" not in configured and "localhost" not in configured:
		return configured

	# Auto-detect Windows host from WSL default route when using localhost config
	default = configured or "http://127.0.0.1:9475"
	host_ip = _windows_host_from_wsl()
	if host_ip:
		# Preserve port from configured/default URL
		from urllib.parse import urlparse

		parsed = urlparse(default if "://" in default else f"http://{default}")
		port = parsed.port or 9475
		return f"http://{host_ip}:{port}"
	return default


def _windows_host_from_wsl() -> str | None:
	"""Return Windows host IP as seen from WSL (default gateway), else None."""
	try:
		import platform

		if "microsoft" not in platform.release().lower() and "microsoft" not in platform.version().lower():
			# Also check /proc/version
			proc = Path("/proc/version")
			if not proc.is_file() or "microsoft" not in proc.read_text(encoding="utf-8", errors="ignore").lower():
				return None
	except Exception:
		return None

	try:
		import subprocess

		completed = subprocess.run(
			["ip", "route", "show", "default"],
			capture_output=True,
			text=True,
			timeout=3,
			check=False,
		)
		# default via 172.18.48.1 dev eth0
		for part in (completed.stdout or "").split():
			if part.count(".") == 3:
				return part
	except Exception:
		pass
	return None


def agent_token() -> str:
	token = (frappe.conf.get("openas2_runtime_agent_token") or "").strip()
	if not token:
		env_name = frappe.conf.get("openas2_runtime_agent_token_env") or "OPENAS2_AGENT_TOKEN"
		import os

		token = (os.environ.get(str(env_name)) or "").strip()
	return token


def write_manager_manifest(instance) -> Path:
	"""Write/refresh allowlist manifest inside the instance home (Agent reads this)."""
	slug = (instance.instance_slug or "").strip()
	if not slug:
		frappe.throw(frappe._("Instance slug is required for runtime control."))
	home = Path(instance.openas2_home).expanduser().resolve()
	assert_under_directory(get_instances_root(), home)
	payload = {
		"instance_name": instance.instance_name or instance.name,
		"frappe_name": instance.name,
		"slug": slug,
		"as2_id": instance.as2_id,
		"instance_type": instance.instance_type,
		"windows_home": instance.windows_home or to_windows_path(home),
		"http_port": int(instance.http_port or instance.port or 0),
		"https_port": int(instance.https_port or 0) if instance.https_port else None,
		"mdn_http_port": int(instance.mdn_http_port or 0) if instance.mdn_http_port else None,
		"service_name": instance.service_name,
		"control_mode": "agent",
		"written_at": str(now_datetime()),
	}
	path = home / "manager_manifest.json"
	assert_under_directory(home, path)
	path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
	return path


def call_agent(action: str, slug: str | None = None, extra: dict | None = None) -> dict:
	"""HTTP JSON call to the Runtime Agent."""
	action = (action or "").strip().lower()
	if action not in ALLOWED_ACTIONS:
		frappe.throw(frappe._("Unsupported runtime action: {0}").format(action))

	token = agent_token()
	if not token:
		frappe.throw(
			frappe._(
				"Runtime Agent token is not configured. "
				"Set openas2_runtime_agent_token in site_config."
			)
		)

	url = agent_url() + ("/v1/ping" if action == "ping" else "/v1/action")
	body: dict[str, Any] = {"action": action}
	if slug:
		body["slug"] = slug
	if extra:
		body.update(extra)

	req = urllib.request.Request(
		url,
		data=json.dumps(body).encode("utf-8"),
		headers={
			"Content-Type": "application/json",
			"Authorization": f"Bearer {token}",
			"Accept": "application/json",
		},
		method="POST",
	)
	try:
		with urllib.request.urlopen(req, timeout=90) as resp:  # noqa: S310 — configured localhost agent
			raw = resp.read().decode("utf-8", errors="replace")
			data = json.loads(raw or "{}")
	except urllib.error.HTTPError as exc:
		try:
			data = json.loads(exc.read().decode("utf-8", errors="replace") or "{}")
		except Exception:
			data = {"ok": False, "error": str(exc)}
		return {
			"ok": False,
			"error": data.get("error") or str(exc),
			"http_status": exc.code,
			"agent": data,
		}
	except urllib.error.URLError as exc:
		return {
			"ok": False,
			"error": (
				f"Runtime Agent unreachable at {agent_url()}: {exc.reason}. "
				"Start runtime_agent/agent.py on Windows first."
			),
			"http_status": 0,
		}
	except Exception as exc:  # noqa: BLE001
		return {"ok": False, "error": str(exc), "http_status": 0}

	if not data.get("ok", True) and data.get("error"):
		return {"ok": False, "error": data.get("error"), "agent": data}
	return {"ok": True, "agent": data}


def _load_instance(instance_name: str):
	if not instance_name:
		frappe.throw(frappe._("Instance is required."))
	if not frappe.db.exists("OpenAS2 Instance", instance_name):
		frappe.throw(frappe._("Unknown OpenAS2 Instance: {0}").format(instance_name))
	return frappe.get_doc("OpenAS2 Instance", instance_name)


def _assert_manager_provisioned(instance) -> None:
	if (instance.provision_source or "") != "Manager Provisioned":
		frappe.throw(
			frappe._(
				"Runtime Agent control is only enabled for Manager-provisioned instances. "
				"Legacy OpenAS20/A/B installs are not controlled in Phase 2."
			)
		)
	if not instance.instance_slug:
		frappe.throw(frappe._("Instance slug is missing; re-provision or set slug."))
	if not instance.openas2_home:
		frappe.throw(frappe._("OpenAS2 Home is missing."))


def _apply_status_fields(instance, agent_payload: dict) -> None:
	data = agent_payload.get("agent") or agent_payload
	lifecycle = data.get("lifecycle_status")
	if lifecycle:
		instance.db_set("lifecycle_status", lifecycle, update_modified=False)
	if "pid" in data:
		pid = data.get("pid")
		instance.db_set("runtime_pid", int(pid) if pid else 0, update_modified=False)
	if "process_running" in data:
		instance.db_set(
			"process_status",
			"Running" if data.get("process_running") else "Stopped",
			update_modified=False,
		)
	if "port_listening" in data:
		instance.db_set(
			"port_status",
			"Listening" if data.get("port_listening") else "Not Listening",
			update_modified=False,
		)
	if data.get("openas2_health"):
		instance.db_set("openas2_health", data.get("openas2_health"), update_modified=False)
	instance.db_set("last_health_check", now_datetime(), update_modified=False)
	instance.db_set("control_mode", "agent", update_modified=False)
	if lifecycle == "Failed" or agent_payload.get("ok") is False:
		err = agent_payload.get("error") or data.get("error") or ""
		if err:
			instance.db_set("last_error", str(err)[:500], update_modified=False)
	elif lifecycle == "Running":
		instance.db_set("last_error", "", update_modified=False)


def _write_runtime_log(
	*,
	instance,
	action: str,
	result: str,
	summary: str,
	agent_payload: dict | None = None,
	error: str | None = None,
) -> str:
	data = (agent_payload or {}).get("agent") or {}
	doc = frappe.get_doc(
		{
			"doctype": "OpenAS2 Runtime Log",
			"instance": instance.name,
			"action": action,
			"result": result,
			"requested_by": frappe.session.user,
			"requested_at": now_datetime(),
			"completed_at": now_datetime(),
			"lifecycle_status": data.get("lifecycle_status") or instance.lifecycle_status,
			"runtime_pid": data.get("pid"),
			"process_status": (
				"Running" if data.get("process_running") else "Stopped" if "process_running" in data else ""
			),
			"port_status": (
				"Listening"
				if data.get("port_listening")
				else "Not Listening"
				if "port_listening" in data
				else ""
			),
			"openas2_health": data.get("openas2_health"),
			"summary": summary[:1000],
			"error_message": (error or "")[:1000],
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


@frappe.whitelist()
def ping_runtime_agent() -> dict:
	_require_system_manager()
	result = call_agent("ping")
	return result


@frappe.whitelist()
def runtime_status(instance_name: str) -> dict:
	_require_system_manager()
	instance = _load_instance(instance_name)
	_assert_manager_provisioned(instance)
	write_manager_manifest(instance)
	result = call_agent("status", instance.instance_slug)
	if result.get("ok"):
		_apply_status_fields(instance, result)
	if not getattr(frappe.flags, "in_test", False):
		frappe.db.commit()
	return {
		**result,
		"instance": instance.name,
		"lifecycle_status": instance.lifecycle_status,
	}


@frappe.whitelist()
def runtime_health(instance_name: str) -> dict:
	_require_system_manager()
	instance = _load_instance(instance_name)
	_assert_manager_provisioned(instance)
	write_manager_manifest(instance)
	result = call_agent("health", instance.instance_slug)
	if result.get("ok"):
		_apply_status_fields(instance, result)
	log = _write_runtime_log(
		instance=instance,
		action="Health",
		result="Success" if result.get("ok") else "Failed",
		summary=f"Health check for {instance.name}",
		agent_payload=result,
		error=result.get("error"),
	)
	if not getattr(frappe.flags, "in_test", False):
		frappe.db.commit()
	return {**result, "runtime_log": log, "instance": instance.name}


@frappe.whitelist()
def runtime_logs(instance_name: str, lines: int | str = 200) -> dict:
	_require_system_manager()
	instance = _load_instance(instance_name)
	_assert_manager_provisioned(instance)
	write_manager_manifest(instance)
	result = call_agent("logs", instance.instance_slug, extra={"lines": int(lines or 200)})
	return {
		**result,
		"instance": instance.name,
		"lines": (result.get("agent") or {}).get("lines", ""),
		"source": (result.get("agent") or {}).get("source"),
	}


@frappe.whitelist()
def runtime_control(instance_name: str, action: str, confirmed: int | str = 0) -> dict:
	"""Start / Stop / Restart a Manager-provisioned instance via the Agent."""
	_require_system_manager()
	action = (action or "").strip().lower()
	if action not in MUTATING:
		frappe.throw(frappe._("Action must be start, stop, or restart."))
	if not cint(confirmed):
		frappe.throw(frappe._("Confirmation is required."))

	instance = _load_instance(instance_name)
	_assert_manager_provisioned(instance)
	write_manager_manifest(instance)

	# Optimistic lifecycle while waiting
	pending = {"start": "Starting", "stop": "Stopping", "restart": "Starting"}[action]
	instance.db_set("lifecycle_status", pending, update_modified=False)

	result = call_agent(action, instance.instance_slug)
	ok = bool(result.get("ok"))
	if ok:
		_apply_status_fields(instance, result)
	else:
		instance.db_set("lifecycle_status", "Failed", update_modified=False)
		instance.db_set("last_error", (result.get("error") or "")[:500], update_modified=False)

	log = _write_runtime_log(
		instance=instance,
		action=action.title(),
		result="Success" if ok else "Failed",
		summary=f"{action} for {instance.name}: {'ok' if ok else result.get('error')}",
		agent_payload=result,
		error=None if ok else result.get("error"),
	)

	# Also append to Restart Log for restart actions (backward compatible)
	if action == "restart":
		try:
			rl = frappe.get_doc(
				{
					"doctype": "OpenAS2 Restart Log",
					"instance": instance.name,
					"requested_by": frappe.session.user,
					"requested_at": now_datetime(),
					"completed_at": now_datetime(),
					"result": "Success" if ok else "Failed",
					"process_status": (result.get("agent") or {}).get("lifecycle_status") or "Unknown",
					"tcp_status": (
						"Reachable"
						if (result.get("agent") or {}).get("port_listening")
						else "Not Reachable"
					),
					"as2_status": "Not Verified",
					"summary": f"Agent restart for {instance.name}",
					"error_message": (result.get("error") or "")[:1000],
				}
			)
			rl.insert(ignore_permissions=True)
		except Exception:
			pass

	if not getattr(frappe.flags, "in_test", False):
		frappe.db.commit()

	agent = result.get("agent") or {}
	return {
		"ok": ok,
		"result": "Success" if ok else "Failed",
		"action": action,
		"instance": instance.name,
		"lifecycle_status": instance.lifecycle_status,
		"pid": agent.get("pid"),
		"port_listening": agent.get("port_listening"),
		"openas2_health": agent.get("openas2_health"),
		"as2_protocol": "Not Verified",
		"runtime_log": log,
		"message": (
			f"{action.title()} {'succeeded' if ok else 'failed'} for {instance.name}.\n"
			f"Lifecycle: {instance.lifecycle_status}\n"
			f"PID: {agent.get('pid')}\n"
			f"Port listening: {agent.get('port_listening')}\n"
			f"OpenAS2 health: {agent.get('openas2_health')}\n"
			f"AS2 protocol: Not Verified"
			+ (f"\nError: {result.get('error')}" if not ok else "")
		),
		"error": result.get("error"),
	}
