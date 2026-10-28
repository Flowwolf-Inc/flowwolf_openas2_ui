# Copyright (c) 2026, Lakshana and contributors
# For license information, please see license.txt

"""
OpenAS2 Runtime Agent (Windows)

Localhost-only control plane for Manager-provisioned OpenAS2 instances.

Fixed operations only:
  start | stop | restart | status | health | logs | ping

Security:
  - Binds to 127.0.0.1 only
  - Bearer token required
  - Operates only under C:\\OpenAS2\\instances\\<slug>\\ with manager_manifest.json
  - Never accepts user-supplied executables, shell, or arbitrary paths
  - Never returns keystore passwords
  - Stops only the PID owned by that instance (never taskkill /IM java.exe)

Phase 2 process model: background Java process + PID file.
Windows Service install via prunsrv is documented but NOT auto-installed here.
"""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# ---------------------------------------------------------------------------
# Configuration (env / defaults)
# ---------------------------------------------------------------------------

AGENT_HOST = os.environ.get("OPENAS2_AGENT_HOST", "127.0.0.1")
AGENT_PORT = int(os.environ.get("OPENAS2_AGENT_PORT", "9475"))
AGENT_TOKEN = os.environ.get("OPENAS2_AGENT_TOKEN", "").strip()
OPENAS2_ROOT = Path(os.environ.get("OPENAS2_ROOT", r"C:\OpenAS2"))
INSTANCES_ROOT = Path(os.environ.get("OPENAS2_INSTANCES_ROOT", str(OPENAS2_ROOT / "instances")))
RUNTIME_ROOT = Path(os.environ.get("OPENAS2_RUNTIME_ROOT", str(OPENAS2_ROOT / "runtime")))
JAVA_HOME = os.environ.get(
	"OPENAS2_JAVA_HOME",
	r"C:\Program Files\Eclipse Adoptium\jdk-17.0.19.10-hotspot",
)
JAVA_EXE = Path(os.environ.get("OPENAS2_JAVA_EXE", str(Path(JAVA_HOME) / "bin" / "java.exe")))

PID_NAME = "OpenAS2.pid"
MANIFEST_NAME = "manager_manifest.json"
ALLOWED_ACTIONS = frozenset({"start", "stop", "restart", "status", "health", "logs", "ping"})
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_]{0,79}$")
STARTUP_WAIT_SEC = 25
SHUTDOWN_WAIT_SEC = 20
LOG_TAIL_LINES = 200


class AgentError(Exception):
	def __init__(self, message: str, http_status: int = 400):
		super().__init__(message)
		self.http_status = http_status


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict) -> None:
	body = json.dumps(payload, default=str).encode("utf-8")
	handler.send_response(status)
	handler.send_header("Content-Type", "application/json; charset=utf-8")
	handler.send_header("Content-Length", str(len(body)))
	handler.send_header("Cache-Control", "no-store")
	handler.end_headers()
	handler.wfile.write(body)


def _require_auth(handler: BaseHTTPRequestHandler) -> None:
	if not AGENT_TOKEN:
		raise AgentError("Agent token is not configured on the server.", 503)
	auth = handler.headers.get("Authorization", "")
	if not auth.startswith("Bearer "):
		raise AgentError("Missing bearer token.", 401)
	token = auth[len("Bearer ") :].strip()
	if not token or token != AGENT_TOKEN:
		raise AgentError("Invalid bearer token.", 401)


def _validate_slug(slug: str) -> str:
	slug = (slug or "").strip().lower()
	if not SLUG_RE.match(slug):
		raise AgentError("Invalid instance slug.")
	if ".." in slug or "/" in slug or "\\" in slug:
		raise AgentError("Invalid instance slug.")
	return slug


def _instance_home(slug: str) -> Path:
	home = (INSTANCES_ROOT / slug).resolve()
	try:
		home.relative_to(INSTANCES_ROOT.resolve())
	except ValueError as exc:
		raise AgentError("Instance path escapes instances root.", 403) from exc
	return home


def _load_manifest(slug: str) -> dict:
	home = _instance_home(slug)
	manifest_path = home / MANIFEST_NAME
	if not manifest_path.is_file():
		raise AgentError(
			f"Instance '{slug}' is not registered (missing {MANIFEST_NAME}).",
			404,
		)
	try:
		data = json.loads(manifest_path.read_text(encoding="utf-8"))
	except (OSError, json.JSONDecodeError) as exc:
		raise AgentError(f"Invalid manifest for '{slug}': {exc}") from exc
	if data.get("slug") != slug:
		raise AgentError("Manifest slug mismatch.", 403)
	win_home = Path(str(data.get("windows_home") or home))
	if win_home.resolve() != home.resolve():
		# Allow manifest windows_home to match resolved home
		if str(win_home).lower().rstrip("\\") != str(home).lower().rstrip("\\"):
			raise AgentError("Manifest windows_home does not match instance directory.", 403)
	return data


def _pid_path(home: Path) -> Path:
	runtime_dir = home / "runtime"
	runtime_dir.mkdir(parents=True, exist_ok=True)
	return runtime_dir / PID_NAME


def _read_pid(home: Path) -> int | None:
	path = _pid_path(home)
	if not path.is_file():
		return None
	try:
		text = path.read_text(encoding="utf-8").strip().splitlines()[0].strip()
		pid = int(text)
		return pid if pid > 1 else None
	except (OSError, ValueError, IndexError):
		return None


def _write_pid(home: Path, pid: int) -> None:
	_pid_path(home).write_text(f"{pid}\n", encoding="utf-8")


def _clear_pid(home: Path) -> None:
	path = _pid_path(home)
	try:
		path.unlink(missing_ok=True)
	except OSError:
		pass


def _pid_alive(pid: int) -> bool:
	# Windows: use tasklist
	try:
		completed = subprocess.run(
			["tasklist", "/FI", f"PID eq {pid}", "/NH"],
			capture_output=True,
			text=True,
			timeout=10,
			check=False,
		)
		out = (completed.stdout or "").strip()
		if not out or "No tasks are running" in out:
			return False
		return str(pid) in out
	except (OSError, subprocess.SubprocessError):
		return False


def _cmdline_for_pid(pid: int) -> str:
	"""Best-effort command line via WMIC / PowerShell."""
	# Prefer PowerShell CIM (available on modern Windows)
	ps = (
		f"(Get-CimInstance Win32_Process -Filter \"ProcessId={pid}\")"
		f".CommandLine"
	)
	try:
		completed = subprocess.run(
			["powershell", "-NoProfile", "-Command", ps],
			capture_output=True,
			text=True,
			timeout=15,
			check=False,
		)
		return (completed.stdout or "").strip()
	except (OSError, subprocess.SubprocessError):
		return ""


def _pid_belongs_to_instance(pid: int, home: Path, config_xml: Path) -> bool:
	if not _pid_alive(pid):
		return False
	cmd = _cmdline_for_pid(pid).lower()
	if not cmd:
		return False
	markers = ("org.openas2.app.openas2server", "openas2")
	if not any(m in cmd for m in markers):
		return False
	home_s = str(home).lower().replace("/", "\\")
	config_s = str(config_xml).lower().replace("/", "\\")
	# Require config path or instance home in cmdline so we never kill another instance
	return config_s in cmd or home_s in cmd


def _port_listening(port: int, host: str = "127.0.0.1") -> bool:
	try:
		with socket.create_connection((host, int(port)), timeout=1.5):
			return True
	except OSError:
		return False


def _port_free_for_bind(port: int, host: str = "127.0.0.1") -> bool:
	sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	try:
		sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
		sock.bind((host, int(port)))
		return True
	except OSError:
		return False
	finally:
		sock.close()


def _find_openas2_jar(lib_dir: Path) -> Path | None:
	if not lib_dir.is_dir():
		return None
	jars = sorted(lib_dir.glob("openas2-server-*.jar"))
	return jars[-1] if jars else None


def _build_classpath(lib_dir: Path, config_dir: Path) -> str:
	jars = sorted(lib_dir.glob("*.jar"))
	if not jars:
		raise AgentError(f"No JARs found in runtime lib: {lib_dir}", 503)
	parts = [str(p) for p in jars]
	parts.append(str(config_dir))
	return ";".join(parts)


def _validate_runtime_ready(home: Path, manifest: dict) -> dict:
	config_xml = home / "config" / "config.xml"
	if not config_xml.is_file():
		raise AgentError("config.xml missing.")
	lib_dir = RUNTIME_ROOT / "lib"
	jar = _find_openas2_jar(lib_dir)
	if not jar:
		raise AgentError(
			f"Shared runtime lib missing openas2-server jar under {lib_dir}. "
			"Copy OpenAS2 4.8.3 lib/ into C:\\OpenAS2\\runtime\\lib (do not modify Downloads installs).",
			503,
		)
	if not JAVA_EXE.is_file():
		raise AgentError(f"Java not found at {JAVA_EXE}", 503)
	keystore = home / "keystore" / "as2.p12"
	http_port = int(manifest.get("http_port") or 0)
	return {
		"config_xml": config_xml,
		"lib_dir": lib_dir,
		"jar": jar,
		"keystore_present": keystore.is_file(),
		"http_port": http_port,
	}


def action_status(slug: str) -> dict:
	manifest = _load_manifest(slug)
	home = _instance_home(slug)
	config_xml = home / "config" / "config.xml"
	pid = _read_pid(home)
	process_running = False
	owned = False
	if pid:
		process_running = _pid_alive(pid)
		if process_running:
			owned = _pid_belongs_to_instance(pid, home, config_xml)
			if not owned:
				process_running = False
		else:
			_clear_pid(home)
			pid = None

	http_port = int(manifest.get("http_port") or 0)
	port_listening = _port_listening(http_port) if http_port else False

	if process_running and port_listening:
		lifecycle = "Running"
		openas2_health = "Process+Port OK"
	elif process_running and not port_listening:
		lifecycle = "Starting" if process_running else "Failed"
		# Process up but port not yet / failed
		lifecycle = "Running"
		openas2_health = "Process only"
	elif not process_running and port_listening:
		lifecycle = "Unknown"
		openas2_health = "Port only (foreign?)"
	else:
		lifecycle = "Stopped"
		openas2_health = "Stopped"

	return {
		"ok": True,
		"slug": slug,
		"instance": manifest.get("instance_name"),
		"lifecycle_status": lifecycle,
		"process_running": bool(process_running and owned),
		"pid": pid if (process_running and owned) else None,
		"http_port": http_port,
		"port_listening": port_listening,
		"openas2_health": openas2_health,
		"as2_protocol": "Not Verified",
		"windows_home": str(home),
		"keystore_present": (home / "keystore" / "as2.p12").is_file(),
	}


def action_health(slug: str) -> dict:
	st = action_status(slug)
	st["health"] = {
		"process_running": st["process_running"],
		"port_listening": st["port_listening"],
		"openas2_healthy": st["process_running"] and st["port_listening"],
		"as2_protocol": "Not Verified",
	}
	return st


def action_start(slug: str) -> dict:
	manifest = _load_manifest(slug)
	home = _instance_home(slug)
	ready = _validate_runtime_ready(home, manifest)
	config_xml: Path = ready["config_xml"]
	lib_dir: Path = ready["lib_dir"]
	http_port = ready["http_port"]

	current = action_status(slug)
	if current.get("process_running"):
		raise AgentError("Instance is already running.", 409)

	if not ready["keystore_present"]:
		raise AgentError(
			"AS2 keystore missing (keystore\\as2.p12). "
			"Phase 2 does not generate certificates; place a PKCS12 before Start "
			"(Phase 3 will automate this).",
			400,
		)

	if http_port and not _port_free_for_bind(http_port):
		# If something else holds the port, fail
		raise AgentError(f"HTTP port {http_port} is not available.", 409)

	classpath = _build_classpath(lib_dir, home / "config")
	log_dir = home / "logs"
	log_dir.mkdir(parents=True, exist_ok=True)
	stdout_log = home / "runtime" / "stdout.log"
	stderr_log = home / "runtime" / "stderr.log"
	(home / "runtime").mkdir(parents=True, exist_ok=True)

	cmd = [
		str(JAVA_EXE),
		"-Xms32m",
		"-Xmx384m",
		f"-DOPENAS2_LOG_DIR={log_dir}",
		"-Dopenas2.config.file=" + str(config_xml),
		"-cp",
		classpath,
		"org.openas2.app.OpenAS2Server",
		str(config_xml),
	]

	# Start detached; do not use shell
	creationflags = 0
	if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
		creationflags |= subprocess.CREATE_NEW_PROCESS_GROUP
	if hasattr(subprocess, "DETACHED_PROCESS"):
		creationflags |= subprocess.DETACHED_PROCESS

	with open(stdout_log, "a", encoding="utf-8") as out, open(
		stderr_log, "a", encoding="utf-8"
	) as err:
		proc = subprocess.Popen(  # noqa: S603 — fixed argv, no shell, no user input
			cmd,
			cwd=str(home),
			stdout=out,
			stderr=err,
			stdin=subprocess.DEVNULL,
			creationflags=creationflags,
			close_fds=True,
		)

	pid = proc.pid
	_write_pid(home, pid)

	# Wait for process + port
	deadline = time.time() + STARTUP_WAIT_SEC
	port_ok = False
	while time.time() < deadline:
		if not _pid_alive(pid):
			_clear_pid(home)
			err_tail = ""
			try:
				err_tail = stderr_log.read_text(encoding="utf-8", errors="replace")[-1500:]
			except OSError:
				pass
			raise AgentError(
				"OpenAS2 process exited during startup. "
				+ (f"stderr tail: {err_tail}" if err_tail else "Check runtime\\stderr.log"),
				500,
			)
		if http_port and _port_listening(http_port):
			port_ok = True
			break
		time.sleep(0.5)

	owned = _pid_belongs_to_instance(pid, home, config_xml)
	if not owned and _pid_alive(pid):
		# Process exists; cmdline check may lag on Windows — keep PID if alive
		owned = True

	st = action_status(slug)
	if not st.get("process_running"):
		raise AgentError("Start launched but process ownership could not be confirmed.", 500)

	return {
		"ok": True,
		"action": "start",
		"slug": slug,
		"lifecycle_status": "Running" if (st["process_running"] and (port_ok or st["port_listening"])) else "Starting",
		"pid": st.get("pid"),
		"http_port": http_port,
		"port_listening": st.get("port_listening"),
		"openas2_health": st.get("openas2_health"),
		"as2_protocol": "Not Verified",
		"keystore_present": True,
	}


def action_stop(slug: str) -> dict:
	manifest = _load_manifest(slug)
	home = _instance_home(slug)
	config_xml = home / "config" / "config.xml"
	pid = _read_pid(home)
	if not pid or not _pid_alive(pid):
		_clear_pid(home)
		return {
			"ok": True,
			"action": "stop",
			"slug": slug,
			"lifecycle_status": "Stopped",
			"pid": None,
			"detail": "Already stopped",
		}

	if not _pid_belongs_to_instance(pid, home, config_xml):
		raise AgentError(
			f"Refusing to stop PID {pid}: not verified as this OpenAS2 instance.",
			403,
		)

	# Graceful terminate — PID-specific only
	subprocess.run(
		["taskkill", "/PID", str(pid)],
		capture_output=True,
		text=True,
		timeout=30,
		check=False,
	)

	deadline = time.time() + SHUTDOWN_WAIT_SEC
	while time.time() < deadline:
		if not _pid_alive(pid):
			break
		time.sleep(0.4)

	if _pid_alive(pid):
		# Still running — escalate once to /T tree for this PID only (not /IM java)
		subprocess.run(
			["taskkill", "/PID", str(pid), "/T", "/F"],
			capture_output=True,
			text=True,
			timeout=30,
			check=False,
		)
		time.sleep(0.5)

	if _pid_alive(pid):
		raise AgentError(f"Failed to stop PID {pid}.", 500)

	_clear_pid(home)
	return {
		"ok": True,
		"action": "stop",
		"slug": slug,
		"lifecycle_status": "Stopped",
		"pid": None,
		"instance": manifest.get("instance_name"),
	}


def action_restart(slug: str) -> dict:
	action_stop(slug)
	# brief settle
	time.sleep(1.0)
	started = action_start(slug)
	started["action"] = "restart"
	return started


def action_logs(slug: str, lines: int = LOG_TAIL_LINES) -> dict:
	_load_manifest(slug)
	home = _instance_home(slug)
	logs_dir = home / "logs"
	content = ""
	source = None
	if logs_dir.is_dir():
		candidates = sorted(logs_dir.glob("log-*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)
		if candidates:
			source = str(candidates[0])
			try:
				text = candidates[0].read_text(encoding="utf-8", errors="replace")
				parts = text.splitlines()
				content = "\n".join(parts[-max(1, min(lines, 2000)) :])
			except OSError as exc:
				raise AgentError(f"Cannot read log: {exc}") from exc
	# Also include stderr tail if OpenAS2 log empty
	if not content:
		stderr = home / "runtime" / "stderr.log"
		if stderr.is_file():
			source = str(stderr)
			text = stderr.read_text(encoding="utf-8", errors="replace")
			parts = text.splitlines()
			content = "\n".join(parts[-max(1, min(lines, 2000)) :])

	# Redact common password patterns
	content = re.sub(
		r"(password\s*[=:]\s*)(\S+)",
		r"\1********",
		content,
		flags=re.I,
	)

	return {
		"ok": True,
		"slug": slug,
		"source": source,
		"lines": content,
	}


def dispatch(action: str, slug: str | None, params: dict) -> dict:
	action = (action or "").strip().lower()
	if action not in ALLOWED_ACTIONS:
		raise AgentError(f"Unsupported action: {action}")
	if action == "ping":
		return {
			"ok": True,
			"action": "ping",
			"agent": "openas2-runtime-agent",
			"instances_root": str(INSTANCES_ROOT),
			"runtime_root": str(RUNTIME_ROOT),
			"java_exists": JAVA_EXE.is_file(),
		}
	if not slug:
		raise AgentError("instance slug is required.")
	slug = _validate_slug(slug)
	if action == "start":
		return action_start(slug)
	if action == "stop":
		return action_stop(slug)
	if action == "restart":
		return action_restart(slug)
	if action == "status":
		return action_status(slug)
	if action == "health":
		return action_health(slug)
	if action == "logs":
		lines = int(params.get("lines", [LOG_TAIL_LINES])[0])
		return action_logs(slug, lines=lines)
	raise AgentError(f"Unsupported action: {action}")


class Handler(BaseHTTPRequestHandler):
	server_version = "OpenAS2RuntimeAgent/2.0"

	def log_message(self, fmt: str, *args) -> None:
		sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

	def _handle(self) -> None:
		try:
			_require_auth(self)
			parsed = urlparse(self.path)
			if parsed.path not in ("/v1/action", "/v1/ping"):
				raise AgentError("Not found.", 404)

			length = int(self.headers.get("Content-Length") or 0)
			raw = self.rfile.read(length) if length > 0 else b"{}"
			try:
				body = json.loads(raw.decode("utf-8") or "{}")
			except json.JSONDecodeError as exc:
				raise AgentError("Invalid JSON body.") from exc

			qs = parse_qs(parsed.query)
			action = body.get("action") or (qs.get("action") or [None])[0]
			slug = body.get("slug") or (qs.get("slug") or [None])[0]
			if parsed.path == "/v1/ping":
				action = "ping"

			# Merge body scalars into params for logs lines etc.
			merged = dict(qs)
			if "lines" in body:
				merged["lines"] = [body.get("lines")]

			result = dispatch(action, slug, merged)
			_json_response(self, 200, result)
		except AgentError as exc:
			_json_response(self, exc.http_status, {"ok": False, "error": str(exc)})
		except Exception as exc:  # noqa: BLE001 — last-resort agent boundary
			_json_response(
				self,
				500,
				{"ok": False, "error": f"Internal agent error: {exc}", "trace": traceback.format_exc()[-1000:]},
			)

	def do_GET(self) -> None:  # noqa: N802
		self._handle()

	def do_POST(self) -> None:  # noqa: N802
		self._handle()


def main() -> int:
	if not AGENT_TOKEN:
		print("ERROR: Set OPENAS2_AGENT_TOKEN before starting the agent.", file=sys.stderr)
		return 2
	INSTANCES_ROOT.mkdir(parents=True, exist_ok=True)
	RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
	print(f"OpenAS2 Runtime Agent listening on http://{AGENT_HOST}:{AGENT_PORT}")
	print(f"instances_root={INSTANCES_ROOT}")
	print(f"runtime_root={RUNTIME_ROOT}")
	print(f"java={JAVA_EXE} exists={JAVA_EXE.is_file()}")
	httpd = ThreadingHTTPServer((AGENT_HOST, AGENT_PORT), Handler)
	try:
		httpd.serve_forever()
	except KeyboardInterrupt:
		print("Shutting down agent.")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
