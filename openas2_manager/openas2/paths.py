# Copyright (c) 2026, Lakshana and contributors
# For license information, please see license.txt

"""Path helpers for OpenAS2 instance provisioning.

Managed layout (defaults; overridable via site_config):

  C:\\OpenAS2\\runtime\\          shared immutable lib/bin (optional link)
  C:\\OpenAS2\\instances\\<slug>\\ per-instance config/data/logs/keystore

Frappe runs in WSL and uses /mnt/c/... equivalents.
"""

from __future__ import annotations

import re
from pathlib import Path

import frappe

DEFAULT_WINDOWS_ROOT = r"C:\OpenAS2"
DEFAULT_WSL_ROOT = "/mnt/c/OpenAS2"

# Legacy installs — never written by provisioning; ports reserved.
LEGACY_OPENAS2_HOMES_WSL = (
	"/mnt/c/Users/laksh/Downloads/OpenAS20",
	"/mnt/c/Users/laksh/Downloads/OpenAS2A",
	"/mnt/c/Users/laksh/Downloads/OpenAS2B",
	"/mnt/c/Users/laksh/Downloads/OpenAS2C",
)

SLUG_RE = re.compile(r"[^a-z0-9]+")


def get_windows_root() -> str:
	return (frappe.conf.get("openas2_windows_root") or DEFAULT_WINDOWS_ROOT).rstrip("\\/")


def get_wsl_root() -> Path:
	configured = frappe.conf.get("openas2_wsl_root")
	if configured:
		return Path(str(configured)).expanduser()
	return Path(DEFAULT_WSL_ROOT)


def get_instances_root() -> Path:
	configured = frappe.conf.get("openas2_instances_root")
	if configured:
		return Path(str(configured)).expanduser().resolve()
	return (get_wsl_root() / "instances").resolve()


def get_runtime_root() -> Path:
	configured = frappe.conf.get("openas2_runtime_root")
	if configured:
		return Path(str(configured)).expanduser().resolve()
	return (get_wsl_root() / "runtime").resolve()


def windows_instances_root() -> str:
	return f"{get_windows_root()}\\instances"


def slugify_instance_name(name: str) -> str:
	"""Filesystem-safe slug; stable and path-traversal safe."""
	raw = (name or "").strip().lower()
	slug = SLUG_RE.sub("_", raw).strip("_")
	if not slug:
		frappe.throw(frappe._("Instance Name does not produce a valid directory slug."))
	if len(slug) > 80:
		slug = slug[:80].rstrip("_")
	if ".." in slug or "/" in slug or "\\" in slug:
		frappe.throw(frappe._("Invalid instance slug."))
	return slug


def instance_paths(slug: str) -> dict[str, Path]:
	"""Return absolute paths under the instances root for one slug."""
	root = get_instances_root()
	home = (root / slug).resolve()
	try:
		home.relative_to(root.resolve())
	except ValueError:
		frappe.throw(frappe._("Refusing instance path outside managed instances root."))

	config = home / "config"
	data = home / "data"
	logs = home / "logs"
	keystore = home / "keystore"
	return {
		"home": home,
		"config": config,
		"data": data,
		"logs": logs,
		"keystore": keystore,
		"inbox": data / "inbox",
		"outbox": data / "outbox",
		"resend": data / "resend",
		"temp": data / "temp",
		"pending_mdn": data / "pendingMDN3",
		"pending_mdn_info": data / "pendinginfoMDN3",
	}


def to_windows_path(wsl_path: Path | str) -> str:
	"""Best-effort WSL /mnt/c/... → C:\\... for display / Agent later."""
	text = str(wsl_path)
	if text.startswith("/mnt/"):
		# /mnt/c/OpenAS2/instances/x → C:\OpenAS2\instances\x
		rest = text[len("/mnt/") :]
		if len(rest) >= 2 and rest[1] == "/":
			drive = rest[0].upper()
			tail = rest[2:].replace("/", "\\")
			return f"{drive}:\\{tail}"
	# Already windows-ish or custom mount
	return text.replace("/", "\\")


def assert_under_directory(base: Path, target: Path) -> None:
	base_r = base.resolve()
	target_r = target.resolve()
	try:
		target_r.relative_to(base_r)
	except ValueError:
		frappe.throw(
			frappe._("Refusing path outside managed root: {0}").format(target_r)
		)
