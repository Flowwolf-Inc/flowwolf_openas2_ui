# Copyright (c) 2026, Lakshana and contributors
# For license information, please see license.txt

"""Prepare shared OpenAS2 runtime lib for Phase 2 (copy jars, never modify Downloads sources)."""

from __future__ import annotations

import shutil
from pathlib import Path

import frappe

from openas2_manager.openas2.paths import get_runtime_root

# Read-only source candidates (never written).
DEFAULT_LIB_SOURCES = (
	Path("/mnt/c/Users/laksh/Downloads/OpenAS20/lib"),
	Path("/mnt/c/Users/laksh/Downloads/OpenAS2A/lib"),
	Path("/mnt/c/Users/laksh/Downloads/OpenAS2B/lib"),
)


def _require_system_manager():
	if "System Manager" not in frappe.get_roles(frappe.session.user):
		frappe.throw(
			frappe._("Only System Managers may prepare the OpenAS2 runtime."),
			frappe.PermissionError,
		)


def resolve_lib_source() -> Path:
	configured = frappe.conf.get("openas2_lib_source")
	if configured:
		path = Path(str(configured)).expanduser()
		if path.is_dir():
			return path
		frappe.throw(frappe._("Configured openas2_lib_source is not a directory: {0}").format(path))
	for candidate in DEFAULT_LIB_SOURCES:
		if candidate.is_dir() and list(candidate.glob("openas2-server-*.jar")):
			return candidate
	frappe.throw(
		frappe._(
			"No OpenAS2 lib source found. Set site_config openas2_lib_source "
			"or ensure Downloads OpenAS20/lib is readable."
		)
	)


@frappe.whitelist()
def prepare_shared_runtime(force: int | str = 0) -> dict:
	"""Copy OpenAS2 jars into C:\\OpenAS2\\runtime\\lib (WSL path). Source is read-only."""
	_require_system_manager()
	source = resolve_lib_source()
	runtime = get_runtime_root()
	lib_dest = runtime / "lib"
	lib_dest.mkdir(parents=True, exist_ok=True)

	existing = list(lib_dest.glob("openas2-server-*.jar"))
	if existing and not int(force or 0):
		return {
			"result": "Skipped",
			"message": f"Runtime lib already present ({existing[-1].name}). Pass force=1 to refresh.",
			"lib_dest": str(lib_dest),
			"source": str(source),
			"jar_count": len(list(lib_dest.glob("*.jar"))),
		}

	copied = 0
	for jar in source.glob("*.jar"):
		shutil.copy2(jar, lib_dest / jar.name)
		copied += 1

	jars = sorted(lib_dest.glob("openas2-server-*.jar"))
	if not jars:
		frappe.throw(frappe._("Copy finished but openas2-server jar is missing in {0}").format(lib_dest))

	readme = runtime / "README.txt"
	readme.write_text(
		"Shared OpenAS2 runtime (Phase 2).\n"
		f"lib copied from {source} (source not modified).\n"
		"Instance config/data/logs live under instances/<slug>/.\n",
		encoding="utf-8",
	)

	return {
		"result": "Success",
		"message": f"Copied {copied} jars into shared runtime lib.",
		"lib_dest": str(lib_dest),
		"source": str(source),
		"openas2_server_jar": jars[-1].name,
		"jar_count": copied,
		"source_modified": False,
	}
