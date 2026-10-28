# Copyright (c) 2026, Lakshana and contributors
# For license information, please see license.txt

"""OpenAS2 partnerships.xml proposal, preview, and explicit apply.

Safety rules:
- Saving OpenAS2 Partnership does not write XML.
- Apply requires an explicit administrator action.
- Never restarts OpenAS2.
- Never modifies config.xml or keystores.
- Only writes partnerships.xml under the instance openas2_home.
- Passwords / private keys are never stored or returned.
"""

from __future__ import annotations

import difflib
import os
import re
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from xml.dom import minidom

import frappe
from frappe.utils import now_datetime

from openas2_manager.openas2.config_viewer import (
	parse_partnerships_xml,
	read_text_readonly,
	redact_xml_text,
	resolve_openas2_home,
	safe_display_source,
)

ENCRYPT_ALG = "3DES"
SIGN_ALG = "SHA-256"
MDN_OPTIONS_SIGNED = (
	"signed-receipt-protocol=optional, pkcs7-signature; "
	"signed-receipt-micalg=optional, $attribute.sign$"
)


def get_partnerships_path(instance) -> Path:
	home = resolve_openas2_home(instance).resolve()
	path = (home / "config" / "partnerships.xml").resolve()
	assert_under_home(home, path)
	return path


def assert_under_home(home: Path, target: Path) -> None:
	"""Prevent path traversal outside the instance OpenAS2 home."""
	home_r = home.resolve()
	target_r = target.resolve()
	try:
		target_r.relative_to(home_r)
	except ValueError:
		frappe.throw(
			frappe._(
				"Refusing path outside OpenAS2 home. Target {0} is not under {1}."
			).format(frappe.bold(str(target_r)), frappe.bold(str(home_r)))
		)


def validate_xml(xml_text: str) -> ET.Element:
	try:
		return ET.fromstring(xml_text)
	except ET.ParseError as exc:
		frappe.throw(frappe._("Invalid partnerships XML: {0}").format(str(exc)))


def canonicalize_xml(root: ET.Element) -> str:
	"""Pretty-print XML for stable diffs (no password fields added)."""
	rough = ET.tostring(root, encoding="unicode")
	parsed = minidom.parseString(rough)
	pretty = parsed.toprettyxml(indent="    ")
	# Remove XML declaration noise / blank lines from minidom
	lines = [ln for ln in pretty.splitlines() if ln.strip()]
	if lines and lines[0].startswith("<?xml"):
		lines = lines[1:]
	return '<?xml version="1.0" encoding="UTF-8"?>\n' + "\n".join(lines) + "\n"


def make_unified_diff(current: str, proposed: str, fromfile="current", tofile="proposed") -> str:
	return "".join(
		difflib.unified_diff(
			current.splitlines(keepends=True),
			proposed.splitlines(keepends=True),
			fromfile=fromfile,
			tofile=tofile,
		)
	)


def _find_partner(root: ET.Element, name: str) -> ET.Element | None:
	for partner in root.findall("partner"):
		if partner.attrib.get("name") == name:
			return partner
	return None


def _find_partnership(root: ET.Element, name: str) -> ET.Element | None:
	for partnership in root.findall("partnership"):
		if partnership.attrib.get("name") == name:
			return partnership
	return None


def _upsert_partner(root: ET.Element, name: str, as2_id: str, x509_alias: str) -> None:
	partner = _find_partner(root, name)
	if partner is None:
		partner = ET.SubElement(root, "partner")
		# Insert partners before first partnership if possible
		partnerships = list(root.findall("partnership"))
		if partnerships:
			idx = list(root).index(partnerships[0])
			root.remove(partner)
			root.insert(idx, partner)
	partner.set("name", name)
	partner.set("as2_id", as2_id)
	partner.set("x509_alias", x509_alias)


def _set_attr(partnership: ET.Element, name: str, value: str | None) -> None:
	existing = None
	for attr in partnership.findall("attribute"):
		if attr.attrib.get("name") == name:
			existing = attr
			break
	if value is None:
		if existing is not None:
			partnership.remove(existing)
		return
	if existing is None:
		existing = ET.SubElement(partnership, "attribute")
		existing.set("name", name)
	existing.set("value", value)


def _build_partnership_element(doc) -> ET.Element:
	el = ET.Element("partnership", {"name": doc.partnership_name})
	sender = ET.SubElement(el, "sender")
	sender.set("name", doc.local_partner_name)
	receiver = ET.SubElement(el, "receiver")
	receiver.set("name", doc.remote_partner_name)
	poller = ET.SubElement(el, "pollerConfig")
	poller.set("enabled", "true" if doc.status != "Inactive" else "false")

	_set_attr(el, "protocol", "as2")
	_set_attr(el, "content_transfer_encoding", "binary")
	_set_attr(el, "subject", "EDI")
	_set_attr(el, "as2_url", doc.remote_url)
	if doc.encryption_enabled:
		_set_attr(el, "encrypt", ENCRYPT_ALG)
	else:
		_set_attr(el, "encrypt", None)
	if doc.signing_enabled:
		_set_attr(el, "sign", SIGN_ALG)
	else:
		_set_attr(el, "sign", None)
	if doc.mdn_enabled:
		mdn_box = re.sub(r"[^a-z0-9.-]", "", (doc.local_partner_name or "local").lower()) or "local"
		_set_attr(el, "as2_mdn_to", f"edi@{mdn_box}.com")
		_set_attr(el, "as2_mdn_options", MDN_OPTIONS_SIGNED)
		if doc.mdn_mode == "Asynchronous":
			_set_attr(el, "as2_receipt_option", "$properties.as2_async_mdn_url$")
		else:
			_set_attr(el, "as2_receipt_option", None)
	else:
		_set_attr(el, "as2_mdn_options", "none")
		_set_attr(el, "as2_mdn_to", None)
		_set_attr(el, "as2_receipt_option", None)
	return el


def apply_partnership_to_tree(root: ET.Element, doc, change_type: str) -> str:
	"""Mutate partnerships root for Add/Modify/Remove. Returns resolved change_type."""
	existing = _find_partnership(root, doc.partnership_name)

	if change_type == "Remove":
		if existing is not None:
			root.remove(existing)
		return "Remove"

	# Ensure partner definitions exist/updated
	_upsert_partner(root, doc.local_partner_name, doc.local_as2_id, doc.local_x509_alias)
	_upsert_partner(root, doc.remote_partner_name, doc.remote_as2_id, doc.remote_x509_alias)

	new_el = _build_partnership_element(doc)
	if existing is None:
		root.append(new_el)
		return "Add"

	# Replace existing partnership element in place
	idx = list(root).index(existing)
	root.remove(existing)
	root.insert(idx, new_el)
	return "Modify"


def detect_change_type(root: ET.Element, partnership_name: str) -> str:
	return "Modify" if _find_partnership(root, partnership_name) is not None else "Add"


def classify_diff(current_xml: str, proposed_xml: str, partnership_name: str) -> dict:
	cur_root = validate_xml(current_xml) if current_xml.strip() else ET.Element("partnerships")
	prop_root = validate_xml(proposed_xml)
	cur_names = {p.attrib.get("name") for p in cur_root.findall("partnership")}
	prop_names = {p.attrib.get("name") for p in prop_root.findall("partnership")}
	added = sorted(prop_names - cur_names)
	removed = sorted(cur_names - prop_names)
	modified = []
	for name in sorted(cur_names & prop_names):
		# Compare serialized snippets
		c = canonicalize_xml(_find_partnership(cur_root, name))
		p = canonicalize_xml(_find_partnership(prop_root, name))
		if c != p:
			modified.append(name)
	return {
		"added": added,
		"modified": modified,
		"removed": removed,
		"focus": partnership_name,
	}


def create_backup(partnerships_path: Path, home: Path) -> Path:
	assert_under_home(home, partnerships_path)
	backup_dir = (home / "config" / "backups").resolve()
	assert_under_home(home, backup_dir)
	backup_dir.mkdir(parents=True, exist_ok=True)
	stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
	backup_path = (backup_dir / f"partnerships.xml.{stamp}.bak").resolve()
	assert_under_home(home, backup_path)
	data = read_text_readonly(partnerships_path)
	# Write backup under home only
	with backup_path.open("w", encoding="utf-8") as handle:
		handle.write(data)
	if not backup_path.is_file() or backup_path.stat().st_size == 0:
		frappe.throw(frappe._("Backup creation failed for {0}.").format(backup_path))
	return backup_path


def atomic_write_xml(target: Path, content: str, home: Path) -> None:
	assert_under_home(home, target)
	validate_xml(content)
	target_dir = target.parent
	assert_under_home(home, target_dir)
	fd, tmp_name = tempfile.mkstemp(prefix="partnerships_", suffix=".xml.tmp", dir=str(target_dir))
	tmp_path = Path(tmp_name).resolve()
	assert_under_home(home, tmp_path)
	try:
		with os.fdopen(fd, "w", encoding="utf-8") as handle:
			handle.write(content)
			handle.flush()
			os.fsync(handle.fileno())
		os.replace(tmp_path, target)
	except Exception:
		if tmp_path.exists():
			tmp_path.unlink(missing_ok=True)
		raise


def restore_backup(backup_path: Path, target: Path, home: Path) -> None:
	assert_under_home(home, backup_path)
	assert_under_home(home, target)
	content = read_text_readonly(backup_path)
	atomic_write_xml(target, content, home)


def _empty_partnerships_xml() -> str:
	return '<?xml version="1.0" encoding="UTF-8"?>\n<partnerships>\n</partnerships>\n'


def build_proposal_for_partnership(doc, change_type: str | None = None) -> dict:
	instance = frappe.get_doc("OpenAS2 Instance", doc.instance)
	home = resolve_openas2_home(instance).resolve()
	path = get_partnerships_path(instance)

	if path.exists():
		current_xml = read_text_readonly(path)
	else:
		current_xml = _empty_partnerships_xml()

	root = validate_xml(current_xml)
	# Work on a deep copy via re-parse
	working = validate_xml(current_xml)
	resolved_type = change_type or detect_change_type(working, doc.partnership_name)
	if resolved_type == "Remove":
		existing = _find_partnership(working, doc.partnership_name)
		if existing is not None:
			working.remove(existing)
	else:
		resolved_type = apply_partnership_to_tree(working, doc, resolved_type)

	proposed_xml = canonicalize_xml(working)
	# Normalize current for fair diff
	current_canon = canonicalize_xml(root)
	diff = make_unified_diff(current_canon, proposed_xml, "partnerships.xml (current)", "partnerships.xml (proposed)")
	classification = classify_diff(current_canon, proposed_xml, doc.partnership_name)

	return {
		"instance": instance.name,
		"partnership": doc.name,
		"partnership_name": doc.partnership_name,
		"change_type": resolved_type,
		"partnerships_path": str(path),
		"partnerships_path_display": safe_display_source(path),
		"openas2_home_display": safe_display_source(home),
		"current_xml": current_canon,
		"proposed_xml": proposed_xml,
		"diff": diff,
		"classification": classification,
		"restart_openas2": False,
		"read_only_viewer_unaffected": True,
	}


@frappe.whitelist()
def list_instance_partnerships(instance_name: str) -> dict:
	"""List current XML partnerships + Frappe OpenAS2 Partnership drafts for an instance."""
	if not instance_name:
		frappe.throw(frappe._("Instance is required."))
	from openas2_manager.access import assert_instance_access

	assert_instance_access(instance_name)
	instance = frappe.get_doc("OpenAS2 Instance", instance_name)
	path = get_partnerships_path(instance)
	xml_rows = []
	xml_error = None
	if not path.exists():
		xml_error = "Partnership configuration not found."
	else:
		try:
			raw = read_text_readonly(path)
			parsed = parse_partnerships_xml(raw, local_as2_id=instance.as2_id)
			xml_rows = parsed["partnerships"]
		except Exception as exc:
			xml_error = str(exc)

	frappe_rows = frappe.get_all(
		"OpenAS2 Partnership",
		filters={"instance": instance_name},
		fields=[
			"name",
			"partnership_name",
			"local_as2_id",
			"remote_as2_id",
			"remote_url",
			"encryption_enabled",
			"signing_enabled",
			"mdn_enabled",
			"status",
		],
		order_by="modified desc",
	)
	proposed = frappe.get_all(
		"OpenAS2 Configuration Change",
		filters={"instance": instance_name, "status": "Proposed"},
		fields=["name", "change_type", "partnership", "summary", "requested_at", "requested_by"],
		order_by="creation desc",
	)
	return {
		"instance": instance_name,
		"xml_partnerships": xml_rows,
		"xml_error": xml_error,
		"frappe_partnerships": frappe_rows,
		"proposed_changes": proposed,
		"source": safe_display_source(path),
	}


@frappe.whitelist()
def preview_partnership_change(partnership_name: str, change_type: str | None = None) -> dict:
	"""Build proposal + audit record (Proposed). Does not write partnerships.xml."""
	if not partnership_name:
		frappe.throw(frappe._("Partnership is required."))
	doc = frappe.get_doc("OpenAS2 Partnership", partnership_name)
	if change_type and change_type not in ("Add", "Modify", "Remove"):
		frappe.throw(frappe._("Invalid change type."))

	proposal = build_proposal_for_partnership(doc, change_type=change_type)

	# Cancel older Proposed rows for same partnership to avoid ambiguity
	for old in frappe.get_all(
		"OpenAS2 Configuration Change",
		filters={"partnership": doc.name, "status": "Proposed"},
		pluck="name",
	):
		frappe.db.set_value("OpenAS2 Configuration Change", old, "status", "Rolled Back")

	audit = frappe.get_doc(
		{
			"doctype": "OpenAS2 Configuration Change",
			"instance": doc.instance,
			"change_type": proposal["change_type"],
			"partnership": doc.name,
			"status": "Proposed",
			"requested_by": frappe.session.user,
			"requested_at": now_datetime(),
			"summary": (
				f"{proposal['change_type']} partnership {doc.partnership_name} "
				f"on instance {doc.instance}"
			),
			"current_xml": redact_xml_text(proposal["current_xml"]),
			"proposed_xml": redact_xml_text(proposal["proposed_xml"]),
			"diff_text": redact_xml_text(proposal["diff"]),
		}
	)
	audit.insert(ignore_permissions=True)
	if not getattr(frappe.flags, "in_test", False):
		frappe.db.commit()

	# API response must never include plaintext secrets — only redacted XML.
	return {
		"instance": proposal["instance"],
		"partnership": proposal["partnership"],
		"partnership_name": proposal["partnership_name"],
		"change_type": proposal["change_type"],
		"partnerships_path_display": proposal["partnerships_path_display"],
		"openas2_home_display": proposal["openas2_home_display"],
		"classification": proposal["classification"],
		"restart_openas2": False,
		"read_only_viewer_unaffected": True,
		"current_xml_redacted": redact_xml_text(proposal["current_xml"]),
		"proposed_xml_redacted": redact_xml_text(proposal["proposed_xml"]),
		"diff_redacted": redact_xml_text(proposal["diff"]),
		"configuration_change": audit.name,
		"writes_performed": False,
		"openas2_restarted": False,
		"message": (
			"Proposal created. Review CURRENT / PROPOSED / DIFF, then click "
			"Apply Configuration explicitly. OpenAS2 will NOT be restarted."
		),
	}


@frappe.whitelist()
def apply_configuration_change(configuration_change: str) -> dict:
	"""Explicitly apply a Proposed change to partnerships.xml with backup/rollback."""
	if not configuration_change:
		frappe.throw(frappe._("Configuration Change is required."))

	# Require System Manager
	if "System Manager" not in frappe.get_roles(frappe.session.user):
		frappe.throw(frappe._("Only System Managers can apply OpenAS2 configuration changes."), frappe.PermissionError)

	change = frappe.get_doc("OpenAS2 Configuration Change", configuration_change)
	if change.status != "Proposed":
		frappe.throw(frappe._("Only Proposed changes can be applied (current status: {0}).").format(change.status))

	if not change.partnership:
		frappe.throw(frappe._("Configuration Change has no linked partnership."))

	doc = frappe.get_doc("OpenAS2 Partnership", change.partnership)
	instance = frappe.get_doc("OpenAS2 Instance", change.instance)
	home = resolve_openas2_home(instance).resolve()
	path = get_partnerships_path(instance)

	# Rebuild proposal from current disk state at apply time
	proposal = build_proposal_for_partnership(doc, change_type=change.change_type)
	proposed_xml = proposal["proposed_xml"]
	validate_xml(proposed_xml)

	backup_path = None
	try:
		if not path.exists():
			# Ensure parent config dir exists only under home
			assert_under_home(home, path.parent)
			path.parent.mkdir(parents=True, exist_ok=True)
			atomic_write_xml(path, _empty_partnerships_xml(), home)

		backup_path = create_backup(path, home)
		change.db_set("backup_path", str(backup_path), update_modified=False)

		atomic_write_xml(path, proposed_xml, home)

		# Verify
		written = read_text_readonly(path)
		written_root = validate_xml(written)
		if change.change_type == "Remove":
			if _find_partnership(written_root, doc.partnership_name) is not None:
				raise RuntimeError("Partnership still present after Remove.")
		else:
			if _find_partnership(written_root, doc.partnership_name) is None:
				raise RuntimeError("Partnership missing after Apply.")

		# Mark applied; update partnership status if Active/Draft
		change.db_set(
			{
				"status": "Applied",
				"error_message": "",
				"summary": f"Applied {change.change_type} for {doc.partnership_name}",
				"current_xml": redact_xml_text(proposal["current_xml"]),
				"proposed_xml": redact_xml_text(proposed_xml),
				"diff_text": redact_xml_text(proposal["diff"]),
			}
		)
		if change.change_type != "Remove" and doc.status == "Draft":
			doc.db_set("status", "Active")
		elif change.change_type == "Remove":
			doc.db_set("status", "Inactive")

		if not getattr(frappe.flags, "in_test", False):
			frappe.db.commit()
		return {
			"status": "Applied",
			"configuration_change": change.name,
			"backup_path_display": safe_display_source(backup_path) if backup_path else None,
			"partnerships_path_display": safe_display_source(path),
			"openas2_restarted": False,
			"offer_restart": True,
			"instance": instance.name,
			"message": (
				"Configuration applied successfully.\n"
				"OpenAS2 may need to be restarted to load the changes."
			),
		}
	except Exception as exc:
		# Rollback if we have a backup and target may be partial
		rolled_back = False
		err = str(exc)
		try:
			if backup_path and Path(backup_path).is_file():
				restore_backup(Path(backup_path), path, home)
				rolled_back = True
		except Exception as restore_exc:
			err = f"{err}; restore also failed: {restore_exc}"

		change.db_set(
			{
				"status": "Rolled Back" if rolled_back else "Failed",
				"error_message": err[:1000],
				"backup_path": str(backup_path) if backup_path else change.backup_path,
			}
		)
		if not getattr(frappe.flags, "in_test", False):
			frappe.db.commit()
		frappe.throw(
			frappe._("Apply failed: {0}").format(err)
		)


@frappe.whitelist()
def apply_all_proposed_for_instance(instance_name: str) -> dict:
	"""Apply all Proposed changes for an instance, oldest first."""
	if not instance_name:
		frappe.throw(frappe._("Instance is required."))
	names = frappe.get_all(
		"OpenAS2 Configuration Change",
		filters={"instance": instance_name, "status": "Proposed"},
		order_by="creation asc",
		pluck="name",
	)
	results = []
	for name in names:
		results.append(apply_configuration_change(name))
	return {
		"applied": len(results),
		"results": results,
		"openas2_restarted": False,
		"offer_restart": True,
		"instance": instance_name,
		"message": (
			f"Configuration applied successfully ({len(results)} change(s)).\n"
			"OpenAS2 may need to be restarted to load the changes."
		),
	}
