# Copyright (c) 2026, Lakshana and contributors
# For license information, please see license.txt

"""Settings page API — real OpenAS2 Instance fields and config.xml reads.

Does not invent values. Passwords are never returned.
"""

from __future__ import annotations

import json
from pathlib import Path

import frappe
from frappe.utils import cint

WRITABLE = (
	"instance_name",
	"instance_type",
	"status",
	"host",
	"description",
	"provision_source",
	"control_mode",
	"as2_id",
	"protocol",
	"x509_alias",
	"http_enabled",
	"http_port",
	"https_enabled",
	"https_port",
	"port",
	"health_port",
	"tracking_port",
	"mdn_enabled",
	"mdn_mode",
	"mdn_http_enabled",
	"mdn_http_port",
	"mdn_https_enabled",
	"mdn_https_port",
	"async_mdn_url",
	"as2_keystore_path",
	"ssl_keystore_path",
	"certificate_status",
	"openas2_home",
	"inbox_path",
	"outbox_path",
)

READONLY = (
	"name",
	"published_as2_url",
	"lifecycle_status",
	"connection_status",
	"windows_home",
	"instance_slug",
	"service_name",
	"last_error",
	"process_status",
	"port_status",
	"openas2_health",
)

CHECKS = {
	"http_enabled",
	"https_enabled",
	"mdn_enabled",
	"mdn_http_enabled",
	"mdn_https_enabled",
}

INTS = {
	"http_port",
	"https_port",
	"port",
	"health_port",
	"tracking_port",
	"mdn_http_port",
	"mdn_https_port",
}


def _instance_payload(doc) -> dict:
	out = {}
	for field in WRITABLE + READONLY:
		val = doc.get(field)
		if field in CHECKS:
			out[field] = 1 if val else 0
		else:
			out[field] = val if val not in (None, "") else ""
	return out


def _log_props(parsed: dict) -> dict:
	props = parsed.get("properties_safe") or {}
	logs = {}
	for key, value in props.items():
		lk = str(key).lower()
		if "log" in lk or "debug" in lk:
			logs[key] = value
	return logs


@frappe.whitelist()
def get_settings(instance_name: str | None = None) -> dict:
	from openas2_manager.openas2.config_viewer import (
		get_instance_configuration,
		list_instances_for_viewer,
		parse_config_xml,
		read_text_readonly,
		resolve_openas2_home,
	)

	instances = list_instances_for_viewer()
	if not instance_name and instances:
		instance_name = instances[0]["name"]
	if not instance_name or not frappe.db.exists("OpenAS2 Instance", instance_name):
		return {"instances": instances, "settings": None, "xml": None}

	from openas2_manager.access import assert_instance_access

	assert_instance_access(instance_name)
	doc = frappe.get_doc("OpenAS2 Instance", instance_name)
	xml = {
		"errors": [],
		"server": {},
		"mdn": {},
		"certificate": {},
		"directories": {},
		"security": [],
		"logging": {},
		"storage_base_dir": "",
		"version": None,
		"source": "",
	}
	try:
		cfg = get_instance_configuration(instance_name)
		xml["errors"] = cfg.get("errors") or []
		xml["server"] = cfg.get("server") or {}
		xml["mdn"] = cfg.get("mdn") or {}
		xml["certificate"] = cfg.get("certificate") or {}
		xml["directories"] = cfg.get("directories") or {}
		xml["version"] = cfg.get("openas2_version")
		xml["source"] = cfg.get("configuration_source")
		seen = set()
		for row in cfg.get("partnerships") or []:
			enc = row.get("encryption") or "—"
			sig = row.get("signing") or "—"
			key = (enc, sig)
			if key in seen or (enc == "—" and sig == "—"):
				continue
			seen.add(key)
			xml["security"].append(
				{
					"partnership": row.get("partnership_name"),
					"encryption": enc,
					"signing": sig,
				}
			)
	except Exception as exc:
		xml["errors"].append(str(exc))

	try:
		home = resolve_openas2_home(doc)
		config_path = Path(home) / "config" / "config.xml"
		if config_path.exists():
			parsed = parse_config_xml(read_text_readonly(config_path))
			xml["logging"] = _log_props(parsed)
			xml["storage_base_dir"] = parsed.get("storage_base_dir") or ""
	except Exception as exc:
		xml["errors"].append(str(exc))

	return {"instances": instances, "settings": _instance_payload(doc), "xml": xml}


@frappe.whitelist()
def save_settings(instance_name: str, values: str | dict | None = None) -> dict:
	if not instance_name or not frappe.db.exists("OpenAS2 Instance", instance_name):
		frappe.throw(frappe._("OpenAS2 Instance not found."))
	if not frappe.has_permission("OpenAS2 Instance", "write", instance_name):
		frappe.throw(frappe._("Not permitted to update this instance."), frappe.PermissionError)

	from openas2_manager.access import assert_instance_access

	assert_instance_access(instance_name)

	if isinstance(values, str):
		try:
			values = json.loads(values or "{}")
		except json.JSONDecodeError:
			frappe.throw(frappe._("Invalid settings payload."))
	if not isinstance(values, dict):
		frappe.throw(frappe._("Invalid settings payload."))

	doc = frappe.get_doc("OpenAS2 Instance", instance_name)
	for field in WRITABLE:
		if field not in values:
			continue
		raw = values.get(field)
		if field in CHECKS:
			doc.set(field, 1 if cint(raw) else 0)
		elif field in INTS:
			if raw in (None, ""):
				doc.set(field, None)
			else:
				doc.set(field, cint(raw))
		else:
			doc.set(field, "" if raw is None else str(raw))
	doc.save()
	frappe.db.commit()
	return get_settings(instance_name)
