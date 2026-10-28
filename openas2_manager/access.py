# Copyright (c) 2026, Lakshana and contributors
# For license information, please see license.txt

"""Company-scoped access for OpenAS2 Manager (Broker / Shipper / Carrier)."""

from __future__ import annotations

import frappe

COMPANY_ROLES = {
	"Broker": "OpenAS2 Broker User",
	"Shipper": "OpenAS2 Shipper User",
	"Carrier": "OpenAS2 Carrier User",
	"CompanyC": "OpenAS2 CompanyC User",
}

ROLE_TO_INSTANCE_TYPE = {role: company for company, role in COMPANY_ROLES.items()}

INSTANCE_BY_TYPE = {
	"Broker": "Broker OpenAS2A",
	"Shipper": "Shipper OpenAS20",
	"Carrier": "Carrier OpenAS2B",
	"CompanyC": "CompanyC OpenAS2C",
}

DEFAULT_COMPANY_PASSWORD = "NEWPASSWORD"


def is_system_manager(user: str | None = None) -> bool:
	user = user or frappe.session.user
	if user in ("Administrator", "Guest"):
		return user == "Administrator"
	return "System Manager" in frappe.get_roles(user)


def get_user_company_types(user: str | None = None) -> list[str]:
	"""Return instance types the user may access via company roles."""
	user = user or frappe.session.user
	if is_system_manager(user):
		return list(COMPANY_ROLES.keys())
	roles = set(frappe.get_roles(user))
	return [ROLE_TO_INSTANCE_TYPE[r] for r in COMPANY_ROLES.values() if r in roles]


def get_allowed_instance_names(user: str | None = None) -> list[str] | None:
	"""None means unrestricted (System Manager). Empty list means no access."""
	user = user or frappe.session.user
	if is_system_manager(user):
		return None

	# Prefer explicit User Permissions on OpenAS2 Instance when present.
	up_values = frappe.get_all(
		"User Permission",
		filters={"user": user, "allow": "OpenAS2 Instance"},
		pluck="for_value",
	)
	if up_values:
		# Keep only existing docs
		existing = frappe.get_all(
			"OpenAS2 Instance",
			filters={"name": ["in", up_values]},
			pluck="name",
		)
		return existing

	types = get_user_company_types(user)
	if not types:
		return []

	names = frappe.get_all(
		"OpenAS2 Instance",
		filters={"instance_type": ["in", types]},
		pluck="name",
	)
	preferred = [INSTANCE_BY_TYPE[t] for t in types if INSTANCE_BY_TYPE.get(t)]
	ordered = []
	for name in preferred + names:
		if name in names and name not in ordered:
			ordered.append(name)
	return ordered


def assert_instance_access(instance_name: str, user: str | None = None) -> None:
	"""Throw PermissionError if user cannot access this OpenAS2 Instance."""
	user = user or frappe.session.user
	allowed = get_allowed_instance_names(user)
	if allowed is None:
		return
	if instance_name not in allowed:
		frappe.throw(
			frappe._("Not permitted to access OpenAS2 Instance {0}.").format(
				frappe.bold(instance_name)
			),
			frappe.PermissionError,
		)


def openas2_instance_query(user: str | None = None) -> str:
	"""permission_query_conditions for OpenAS2 Instance."""
	user = user or frappe.session.user
	allowed = get_allowed_instance_names(user)
	if allowed is None:
		return ""
	if not allowed:
		return "1=0"
	escaped = ", ".join(frappe.db.escape(n) for n in allowed)
	return f"`tabOpenAS2 Instance`.name in ({escaped})"


def openas2_instance_has_permission(doc, ptype: str = "read", user: str | None = None) -> bool:
	user = user or frappe.session.user
	if is_system_manager(user):
		return True
	allowed = get_allowed_instance_names(user)
	if not allowed:
		return False
	name = doc if isinstance(doc, str) else doc.name
	return name in allowed


def openas2_partnership_query(user: str | None = None) -> str:
	user = user or frappe.session.user
	allowed = get_allowed_instance_names(user)
	if allowed is None:
		return ""
	if not allowed:
		return "1=0"
	escaped = ", ".join(frappe.db.escape(n) for n in allowed)
	return f"`tabOpenAS2 Partnership`.instance in ({escaped})"


def openas2_partnership_has_permission(doc, ptype: str = "read", user: str | None = None) -> bool:
	user = user or frappe.session.user
	if is_system_manager(user):
		return True
	allowed = get_allowed_instance_names(user)
	if not allowed:
		return False
	if isinstance(doc, str):
		return True
	instance = getattr(doc, "instance", None)
	if not instance:
		return ptype in ("create", "read", "write", "select")
	return instance in allowed


def as2_certificate_query(user: str | None = None, doctype: str | None = None) -> str:
	"""Company users only see certificates attached to their OpenAS2 instance."""
	user = user or frappe.session.user
	if is_system_manager(user):
		return ""
	allowed = get_allowed_instance_names(user)
	if not allowed:
		return "1=0"
	escaped = ", ".join(frappe.db.escape(n) for n in allowed)
	return f"`tabAS2 Certificate`.openas2_instance in ({escaped})"


def as2_certificate_has_permission(doc, ptype: str = "read", user: str | None = None) -> bool:
	"""Allow company users to create/read/write certificates for their TMS only.

	Create is always allowed for company-role users (owner_type is enforced in
	validate). Existing docs must match the user's company in owner_type.
	"""
	user = user or frappe.session.user
	if is_system_manager(user):
		return True
	types = get_user_company_types(user)
	if not types:
		return False

	# DocType-level create / select (no document instance)
	if isinstance(doc, str):
		return True

	# Always allow create for company users — validate() locks owner_type
	if ptype == "create":
		return True

	owner = getattr(doc, "owner_type", None) or None
	name = getattr(doc, "name", None)
	instance = getattr(doc, "openas2_instance", None) or None

	# Unsaved draft (name often None) — allow so the New form can open
	if not name:
		return True

	allowed = get_allowed_instance_names(user) or []
	if not instance or instance not in allowed:
		return False
	if not owner:
		return ptype in ("read", "write", "select")

	return owner in types


def company_as2_ids(user: str | None = None) -> list[str] | None:
	"""AS2 IDs for the user's instances. None means unrestricted."""
	allowed = get_allowed_instance_names(user)
	if allowed is None:
		return None
	if not allowed:
		return []
	return [
		as2_id
		for as2_id in frappe.get_all(
			"OpenAS2 Instance",
			filters={"name": ["in", allowed]},
			pluck="as2_id",
		)
		if as2_id
	]


def visible_partner_names(user: str | None = None) -> list[str] | None:
	"""Partners on the user's instances, plus partners they exchange with.

	None means unrestricted (System Manager).
	"""
	as2_ids = company_as2_ids(user)
	if as2_ids is None:
		return None
	if not as2_ids:
		return []

	names = set(
		frappe.get_all("AS2 Partner", filters={"as2_id": ["in", as2_ids]}, pluck="name")
	)
	rows = frappe.get_all(
		"OpenAS2 Partnership",
		or_filters=[
			["local_as2_id", "in", as2_ids],
			["remote_as2_id", "in", as2_ids],
		],
		fields=["local_partner", "remote_partner"],
		limit_page_length=0,
	)
	for row in rows:
		if row.local_partner:
			names.add(row.local_partner)
		if row.remote_partner:
			names.add(row.remote_partner)
	return sorted(names)


def as2_partner_query(user: str | None = None, doctype: str | None = None) -> str:
	"""Company users see their own partner and the partners they trade with."""
	names = visible_partner_names(user)
	if names is None:
		return ""
	if not names:
		return "1=0"
	escaped = ", ".join(frappe.db.escape(n) for n in names)
	return f"`tabAS2 Partner`.name in ({escaped})"


def as2_partner_has_permission(doc, ptype: str = "read", user: str | None = None) -> bool:
	user = user or frappe.session.user
	if is_system_manager(user):
		return True
	if isinstance(doc, str) or ptype == "create":
		return True
	name = getattr(doc, "name", None)
	if not name:
		return True
	return name in (visible_partner_names(user) or [])


def openas2_message_log_query(user: str | None = None, doctype: str | None = None) -> str:
	user = user or frappe.session.user
	allowed = get_allowed_instance_names(user)
	if allowed is None:
		return ""
	if not allowed:
		return "1=0"
	escaped = ", ".join(frappe.db.escape(n) for n in allowed)
	return f"`tabOpenAS2 Message Log`.instance in ({escaped})"


def openas2_message_log_has_permission(doc, ptype: str = "read", user: str | None = None) -> bool:
	user = user or frappe.session.user
	if is_system_manager(user):
		return True
	allowed = get_allowed_instance_names(user) or []
	if isinstance(doc, str):
		return bool(allowed)
	instance = getattr(doc, "instance", None)
	if not instance:
		return ptype in ("create", "read", "write", "select")
	return instance in allowed
