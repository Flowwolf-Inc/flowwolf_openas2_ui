# Copyright (c) 2026, Lakshana and contributors
# For license information, please see license.txt

"""Controlled OpenAS2 restart helper.

Safety rules:
- Explicit user confirmation required (``confirmed=1``).
- System Manager only.
- Never executes UI-supplied commands, paths, or PIDs.
- Only operates on the selected OpenAS2 Instance's ``openas2_home``.
- Does not restart automatically after configuration Apply.
- Does not claim AS2 protocol health from TCP alone.
- If this Frappe host cannot safely control the process, returns Not Available
  instead of faking a restart.
"""

from __future__ import annotations

import os
import signal
import subprocess
import time
from pathlib import Path

import frappe
from frappe.utils import cint, now_datetime

from openas2_manager.openas2.config_viewer import resolve_openas2_home, safe_display_source
from openas2_manager.openas2.connection import tcp_reachability_check

# Fixed, known OpenAS2 script names — never taken from UI input.
ALLOWED_START_SCRIPT = "start-openas2.sh"
ALLOWED_PID_NAME = "OpenAS2.pid"
SHUTDOWN_WAIT_SECONDS = 15
STARTUP_WAIT_SECONDS = 20
TCP_RETRIES = 5
TCP_RETRY_DELAY = 1.0


def _require_system_manager():
	if "System Manager" not in frappe.get_roles(frappe.session.user):
		frappe.throw(
			frappe._("Only System Managers may restart OpenAS2."),
			frappe.PermissionError,
		)


def _assert_under_home(home: Path, target: Path) -> None:
	home_r = home.resolve()
	target_r = target.resolve()
	try:
		target_r.relative_to(home_r)
	except ValueError:
		frappe.throw(
			frappe._("Refusing path outside OpenAS2 home: {0}").format(target_r)
		)


def _is_windows_mounted_path(path: Path) -> bool:
	"""True for WSL mounts of Windows drives (e.g. /mnt/c/...)."""
	try:
		resolved = str(path.resolve())
	except OSError:
		resolved = str(path)
	return resolved.startswith("/mnt/")


def _linux_java_available() -> bool:
	from shutil import which

	return bool(which("java"))


def _read_pid_file(pid_path: Path) -> int | None:
	if not pid_path.is_file():
		return None
	try:
		text = pid_path.read_text(encoding="utf-8").strip().splitlines()[0].strip()
		pid = int(text)
		return pid if pid > 1 else None
	except (OSError, ValueError, IndexError):
		return None


def _pid_alive(pid: int) -> bool:
	try:
		os.kill(pid, 0)
		return True
	except ProcessLookupError:
		return False
	except PermissionError:
		# Process exists but we cannot signal it
		return True


def _cmdline_for_pid(pid: int) -> str:
	try:
		return Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\x00", b" ").decode("utf-8", "replace")
	except OSError:
		return ""


def _pid_belongs_to_instance(pid: int, home: Path) -> bool:
	"""Verify PID looks like OpenAS2 for this home (no arbitrary PID kill)."""
	cmd = _cmdline_for_pid(pid).lower()
	if not cmd:
		return False
	home_s = str(home.resolve()).lower()
	markers = ("org.openas2.app.openas2server", "openas2", "openas2-server")
	if not any(m in cmd for m in markers):
		return False
	# Prefer config path binding when present
	if "openas2.config.file" in cmd or "config.xml" in cmd:
		return home_s in cmd or home.name.lower() in cmd
	return True


def discover_restart_capability(instance) -> dict:
	"""Inspect instance home and decide whether this host can safely restart it."""
	notes = []
	try:
		home = resolve_openas2_home(instance).resolve()
	except Exception as exc:
		return {
			"available": False,
			"reason": f"OpenAS2 home could not be resolved: {exc}",
			"home_display": None,
			"start_script": None,
			"pid_file": None,
			"config_xml": None,
			"notes": [str(exc)],
			"control_mode": None,
		}

	bin_dir = home / "bin"
	config_xml = home / "config" / "config.xml"
	partnerships = home / "config" / "partnerships.xml"
	start_sh = bin_dir / ALLOWED_START_SCRIPT
	start_bat = bin_dir / "start-openas2.bat"
	pid_file = bin_dir / ALLOWED_PID_NAME

	notes.append(f"home={safe_display_source(home)}")
	notes.append(f"config_xml_exists={config_xml.is_file()}")
	notes.append(f"partnerships_exists={partnerships.is_file()}")
	notes.append(f"start_sh_exists={start_sh.is_file()}")
	notes.append(f"start_bat_exists={start_bat.is_file()}")
	notes.append(f"pid_file_exists={pid_file.is_file()}")
	notes.append(f"linux_java={_linux_java_available()}")
	notes.append(f"windows_mount={_is_windows_mounted_path(home)}")

	if not home.is_dir():
		return {
			"available": False,
			"reason": "OpenAS2 installation directory not found.",
			"home_display": safe_display_source(home),
			"start_script": None,
			"pid_file": str(pid_file) if pid_file else None,
			"config_xml": None,
			"notes": notes,
			"control_mode": None,
		}

	if not config_xml.is_file():
		return {
			"available": False,
			"reason": "Configuration file not found (config.xml).",
			"home_display": safe_display_source(home),
			"start_script": None,
			"pid_file": str(pid_file),
			"config_xml": str(config_xml),
			"notes": notes,
			"control_mode": None,
		}

	# Primary safe mode: Linux daemon via fixed start-openas2.sh + PID file under home.
	# Windows-mounted installs controlled from WSL without Linux Java are NOT safe to
	# restart from this Frappe host (would require arbitrary Windows process control).
	if _is_windows_mounted_path(home) and not _linux_java_available():
		return {
			"available": False,
			"reason": (
				"Restart is not available from this Frappe host. Manual restart required. "
				"OpenAS2 appears installed on a Windows path while this host has no Linux Java "
				"to run start-openas2.sh safely."
			),
			"home_display": safe_display_source(home),
			"start_script": safe_display_source(start_bat if start_bat.is_file() else start_sh),
			"pid_file": safe_display_source(pid_file),
			"config_xml": safe_display_source(config_xml),
			"manual_hint": (
				f"On Windows, start/stop using the OpenAS2 scripts under "
				f"{safe_display_source(bin_dir)} (e.g. start-openas2.bat). "
				"Do not paste commands into this UI."
			),
			"notes": notes,
			"control_mode": None,
		}

	if not start_sh.is_file():
		return {
			"available": False,
			"reason": (
				"Restart is not available from this Frappe host. Manual restart required. "
				f"Fixed start script {ALLOWED_START_SCRIPT} was not found under the instance home."
			),
			"home_display": safe_display_source(home),
			"start_script": None,
			"pid_file": safe_display_source(pid_file),
			"config_xml": safe_display_source(config_xml),
			"notes": notes,
			"control_mode": None,
		}

	if not _linux_java_available():
		return {
			"available": False,
			"reason": (
				"Restart is not available from this Frappe host. Manual restart required. "
				"Linux Java runtime was not found for start-openas2.sh."
			),
			"home_display": safe_display_source(home),
			"start_script": safe_display_source(start_sh),
			"pid_file": safe_display_source(pid_file),
			"config_xml": safe_display_source(config_xml),
			"notes": notes,
			"control_mode": None,
		}

	return {
		"available": True,
		"reason": "Linux OpenAS2 start script and Java are available under the instance home.",
		"home_display": safe_display_source(home),
		"start_script": str(start_sh.resolve()),
		"pid_file": str(pid_file.resolve()),
		"config_xml": str(config_xml.resolve()),
		"notes": notes,
		"control_mode": "linux_start_script",
		"home": str(home),
	}


def _stop_instance(home: Path, pid_file: Path) -> dict:
	"""Stop only the PID recorded for this instance, after ownership checks."""
	_assert_under_home(home, pid_file)
	pid = _read_pid_file(pid_file)
	if pid is None:
		return {"process_status": "Stopped", "detail": "No PID file / already stopped"}

	if not _pid_alive(pid):
		try:
			pid_file.unlink(missing_ok=True)
		except OSError:
			pass
		return {"process_status": "Stopped", "detail": f"Stale PID {pid}"}

	if not _pid_belongs_to_instance(pid, home):
		frappe.throw(
			frappe._(
				"Refusing to stop PID {0}: process does not look like OpenAS2 for this instance."
			).format(pid)
		)

	os.kill(pid, signal.SIGTERM)
	deadline = time.time() + SHUTDOWN_WAIT_SECONDS
	while time.time() < deadline:
		if not _pid_alive(pid):
			break
		time.sleep(0.5)

	if _pid_alive(pid):
		# Still running — do not escalate to SIGKILL automatically (safer)
		return {
			"process_status": "Failed",
			"detail": f"Process {pid} did not stop within {SHUTDOWN_WAIT_SECONDS}s after SIGTERM",
		}

	try:
		pid_file.unlink(missing_ok=True)
	except OSError:
		pass
	return {"process_status": "Stopped", "detail": f"Stopped PID {pid}"}


def _start_instance(home: Path, start_script: Path) -> dict:
	"""Start OpenAS2 using ONLY the fixed start-openas2.sh under instance home."""
	_assert_under_home(home, start_script)
	if start_script.name != ALLOWED_START_SCRIPT:
		frappe.throw(frappe._("Refusing to execute non-approved start script."))

	env = os.environ.copy()
	env["OPENAS2_AS_DAEMON"] = "true"
	env["OPENAS2_CONFIG_FILE"] = str((home / "config" / "config.xml").resolve())
	# Never pass UI/user EXTRA args — empty argv after script path.
	proc = subprocess.Popen(  # nosec B603 — fixed executable path, no shell, no user args
		[str(start_script)],
		cwd=str(home / "bin"),
		env=env,
		stdout=subprocess.DEVNULL,
		stderr=subprocess.DEVNULL,
		start_new_session=True,
	)
	# Parent of daemonized start script may exit quickly
	try:
		proc.wait(timeout=5)
	except subprocess.TimeoutExpired:
		pass

	pid_file = home / "bin" / ALLOWED_PID_NAME
	deadline = time.time() + STARTUP_WAIT_SECONDS
	while time.time() < deadline:
		pid = _read_pid_file(pid_file)
		if pid and _pid_alive(pid) and _pid_belongs_to_instance(pid, home):
			return {"process_status": "Running", "detail": f"Started PID {pid}", "pid": pid}
		time.sleep(0.5)

	# Fallback: script returned but pid file missing
	return {
		"process_status": "Failed",
		"detail": "Start script ran but OpenAS2 PID was not observed.",
		"pid": None,
	}


def _check_tcp(instance) -> str:
	host = instance.host or "127.0.0.1"
	port = int(instance.port)
	for _ in range(TCP_RETRIES):
		result = tcp_reachability_check(host, port)
		if result.get("reachable"):
			return "Reachable"
		time.sleep(TCP_RETRY_DELAY)
	return "Not Reachable"


@frappe.whitelist()
def get_restart_capability(instance_name: str) -> dict:
	"""Return whether restart is available for an instance (no side effects)."""
	_require_system_manager()
	if not instance_name:
		frappe.throw(frappe._("Instance is required."))
	if not frappe.db.exists("OpenAS2 Instance", instance_name):
		frappe.throw(frappe._("Unknown OpenAS2 Instance: {0}").format(instance_name))
	instance = frappe.get_doc("OpenAS2 Instance", instance_name)
	cap = discover_restart_capability(instance)
	# Never return absolute secrets; strip raw home from response
	cap.pop("home", None)
	if cap.get("start_script") and str(cap["start_script"]).startswith("/"):
		cap["start_script"] = safe_display_source(cap["start_script"])
	if cap.get("pid_file") and str(cap["pid_file"]).startswith("/") and "OpenAS2.pid" in str(cap["pid_file"]):
		cap["pid_file"] = safe_display_source(cap["pid_file"])
	if cap.get("config_xml") and str(cap["config_xml"]).startswith("/"):
		cap["config_xml"] = safe_display_source(cap["config_xml"])
	return cap


@frappe.whitelist()
def restart_openas2_instance(instance_name: str, confirmed: int | str = 0) -> dict:
	"""Explicitly restart one OpenAS2 Instance after confirmation.

	Does not accept command/path/PID input from the UI.
	"""
	_require_system_manager()
	if not instance_name:
		frappe.throw(frappe._("Instance is required."))
	if not frappe.db.exists("OpenAS2 Instance", instance_name):
		frappe.throw(frappe._("Unknown OpenAS2 Instance: {0}").format(instance_name))
	if not cint(confirmed):
		frappe.throw(
			frappe._(
				"Restart confirmation is required. Confirm the dialog before restarting."
			)
		)

	instance = frappe.get_doc("OpenAS2 Instance", instance_name)
	requested_at = now_datetime()
	log = frappe.get_doc(
		{
			"doctype": "OpenAS2 Restart Log",
			"instance": instance.name,
			"requested_by": frappe.session.user,
			"requested_at": requested_at,
			"result": "Failed",
			"process_status": "Unknown",
			"tcp_status": "Not Checked",
			"as2_status": "Not Verified",
			"summary": f"Restart requested for {instance.name}",
		}
	)
	log.insert(ignore_permissions=True)

	cap = discover_restart_capability(instance)
	log.db_set("discovery_notes", "\n".join(cap.get("notes") or [])[:1000], update_modified=False)

	if not cap.get("available"):
		log.db_set(
			{
				"result": "Not Available",
				"process_status": "Unknown",
				"tcp_status": "Not Checked",
				"as2_status": "Not Verified",
				"completed_at": now_datetime(),
				"error_message": (cap.get("reason") or "")[:1000],
				"summary": f"Restart not available for {instance.name}",
			}
		)
		if not getattr(frappe.flags, "in_test", False):
			frappe.db.commit()
		return {
			"result": "Not Available",
			"instance": instance.name,
			"process_status": "Unknown",
			"tcp_status": "Not Checked",
			"as2_status": "Not Verified",
			"restarted_at": None,
			"restart_log": log.name,
			"message": cap.get("reason"),
			"manual_hint": cap.get("manual_hint"),
			"discovery": {
				"home_display": cap.get("home_display"),
				"start_script": cap.get("start_script"),
				"config_xml": cap.get("config_xml"),
				"notes": cap.get("notes"),
			},
			"openas2_restarted": False,
		}

	started_at = now_datetime()
	log.db_set("started_at", started_at, update_modified=False)

	try:
		home = Path(cap["home"]).resolve()
		start_script = Path(cap["start_script"]).resolve()
		pid_file = Path(cap["pid_file"]).resolve()
		_assert_under_home(home, start_script)
		_assert_under_home(home, pid_file)

		# Pre-checks
		if not (home / "config" / "config.xml").is_file():
			raise RuntimeError("Missing configuration file config.xml")

		stop_info = _stop_instance(home, pid_file)
		if stop_info["process_status"] == "Failed":
			raise RuntimeError(stop_info["detail"])

		start_info = _start_instance(home, start_script)
		process_status = start_info["process_status"]
		if process_status != "Running":
			raise RuntimeError(start_info["detail"])

		tcp_status = _check_tcp(instance)
		completed_at = now_datetime()
		result = "Success" if tcp_status == "Reachable" else "Failed"
		error = "" if result == "Success" else "Process running but TCP listener not reachable"

		log.db_set(
			{
				"result": result,
				"process_status": process_status,
				"tcp_status": tcp_status,
				"as2_status": "Not Verified",
				"completed_at": completed_at,
				"error_message": error,
				"summary": (
					f"Restart {result} for {instance.name}: process={process_status}, "
					f"tcp={tcp_status}, as2=Not Verified"
				),
			}
		)
		if not getattr(frappe.flags, "in_test", False):
			frappe.db.commit()

		return {
			"result": result,
			"instance": instance.name,
			"process_status": process_status,
			"tcp_status": tcp_status,
			"as2_status": "Not Verified",
			"restarted_at": str(completed_at),
			"restart_log": log.name,
			"message": (
				f"Restart Result\n"
				f"--------------\n"
				f"Instance: {instance.instance_name or instance.name}\n"
				f"Process: {process_status}\n"
				f"TCP: {tcp_status}\n"
				f"AS2 Protocol: Not Verified\n"
				f"Restarted At: {completed_at}"
			),
			"openas2_restarted": result == "Success",
		}
	except Exception as exc:
		completed_at = now_datetime()
		log.db_set(
			{
				"result": "Failed",
				"process_status": "Failed",
				"tcp_status": "Not Checked",
				"as2_status": "Not Verified",
				"completed_at": completed_at,
				"error_message": str(exc)[:1000],
				"summary": f"Restart Failed for {instance.name}",
			}
		)
		if not getattr(frappe.flags, "in_test", False):
			frappe.db.commit()
		return {
			"result": "Failed",
			"instance": instance.name,
			"process_status": "Failed",
			"tcp_status": "Not Checked",
			"as2_status": "Not Verified",
			"restarted_at": str(completed_at),
			"restart_log": log.name,
			"message": f"Restart failed: {exc}",
			"openas2_restarted": False,
		}
