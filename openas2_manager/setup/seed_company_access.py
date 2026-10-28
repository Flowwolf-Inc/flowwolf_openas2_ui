# Copyright (c) 2026, Lakshana and contributors
# For license information, please see license.txt

"""Seed company roles, users, and User Permissions for scoped OpenAS2 UI access."""

from __future__ import annotations

import frappe
from frappe.utils.password import update_password

from openas2_manager.access import (
	COMPANY_ROLES,
	DEFAULT_COMPANY_PASSWORD,
	INSTANCE_BY_TYPE,
)

COMPANY_USERS = (
	{
		"email": "broker@openas2.local",
		"first_name": "Broker",
		"company": "Broker",
		"instance": INSTANCE_BY_TYPE["Broker"],
	},
	{
		"email": "shipper@openas2.local",
		"first_name": "Shipper",
		"company": "Shipper",
		"instance": INSTANCE_BY_TYPE["Shipper"],
	},
	{
		"email": "carrier@openas2.local",
		"first_name": "Carrier",
		"company": "Carrier",
		"instance": INSTANCE_BY_TYPE["Carrier"],
	},
	{
		"email": "companyc@openas2.local",
		"first_name": "CompanyC",
		"company": "CompanyC",
		"instance": INSTANCE_BY_TYPE["CompanyC"],
	},
)

SCOPED_DOCTYPES = (
	"OpenAS2 Instance",
	"OpenAS2 Partnership",
	"AS2 Partner",
	"AS2 Certificate",
	"OpenAS2 Message Log",
	"OpenAS2 Runtime Log",
	"OpenAS2 Configuration Change",
	"OpenAS2 Restart Log",
	"OpenAS2 Provisioning Log",
)

PAGE_NAMES = (
	"openas2-configuration",
	"openas2-partners",
	"openas2-certificates",
	"openas2-partnerships",
	"openas2-dashboard",
	"openas2-messages",
	"openas2-errors",
)


def _ensure_role(role_name: str) -> None:
	if frappe.db.exists("Role", role_name):
		return
	frappe.get_doc(
		{
			"doctype": "Role",
			"role_name": role_name,
			"desk_access": 1,
			"is_custom": 1,
		}
	).insert(ignore_permissions=True)


def _ensure_custom_docperm(doctype: str, role: str) -> None:
	"""Grant perms via Custom DocPerm (works without developer_mode)."""
	if not frappe.db.exists("DocType", doctype):
		return

	filters = {"parent": doctype, "role": role, "permlevel": 0}
	if frappe.db.exists("Custom DocPerm", filters):
		return

	# Also skip if already on standard DocType permissions
	if frappe.db.exists("DocPerm", filters):
		return

	create = 0 if doctype == "OpenAS2 Instance" else 1
	frappe.get_doc(
		{
			"doctype": "Custom DocPerm",
			"parent": doctype,
			"role": role,
			"permlevel": 0,
			"read": 1,
			"write": 1,
			"create": create,
			"delete": 0,
			"submit": 0,
			"cancel": 0,
			"amend": 0,
			"report": 1,
			"export": 1,
			"import": 0,
			"share": 0,
			"print": 1,
			"email": 0,
		}
	).insert(ignore_permissions=True)


def _ensure_page_role(page_name: str, role: str) -> None:
	if not frappe.db.exists("Page", page_name):
		return
	# Has Role child table on Page
	exists = frappe.db.exists("Has Role", {"parent": page_name, "role": role})
	if exists:
		return
	# Some sites store page roles differently — try document API with developer override
	try:
		page = frappe.get_doc("Page", page_name)
		if any(r.role == role for r in page.roles):
			return
		page.append("roles", {"role": role})
		page.flags.ignore_permissions = True
		page.flags.ignore_links = True
		# Page is standard; allow update in seed context
		frappe.flags.in_patch = True
		page.save(ignore_permissions=True)
	except Exception:
		frappe.db.sql(
			"""
			insert into `tabHas Role` (name, parent, parenttype, parentfield, role, idx)
			values (%s, %s, 'Page', 'roles', %s,
				ifnull((select max(idx)+1 from `tabHas Role` hr where hr.parent=%s), 1))
			""",
			(frappe.generate_hash(length=10), page_name, role, page_name),
		)


def _ensure_user(email: str, first_name: str, roles: list[str], password: str) -> str:
	if frappe.db.exists("User", email):
		user = frappe.get_doc("User", email)
		user.enabled = 1
		existing = {r.role for r in user.roles}
		for role in roles:
			if role not in existing:
				user.append("roles", {"role": role})
		user.save(ignore_permissions=True)
	else:
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": first_name,
				"send_welcome_email": 0,
				"user_type": "System User",
			}
		)
		for role in roles:
			user.append("roles", {"role": role})
		user.insert(ignore_permissions=True)

	update_password(email, password)
	return email


def _ensure_user_permission(user: str, instance_name: str) -> None:
	"""Restrict OpenAS2 Instance (and partnership) only — not all DocTypes.

	apply_to_all_doctypes=1 breaks AS2 Certificate create when openas2_instance
	is empty (User Permission treats None as denied).
	"""
	if not frappe.db.exists("OpenAS2 Instance", instance_name):
		frappe.throw(
			frappe._(
				"OpenAS2 Instance {0} not found. Run seed_demo_instances first."
			).format(frappe.bold(instance_name))
		)

	# Fix legacy rows that blocked Certificate / Partner create
	legacy = frappe.get_all(
		"User Permission",
		filters={"user": user, "allow": "OpenAS2 Instance", "for_value": instance_name},
		fields=["name", "apply_to_all_doctypes", "applicable_for"],
	)
	for row in legacy:
		doc = frappe.get_doc("User Permission", row.name)
		if doc.apply_to_all_doctypes or not doc.applicable_for:
			doc.apply_to_all_doctypes = 0
			doc.applicable_for = "OpenAS2 Instance"
			doc.save(ignore_permissions=True)

	filters = {
		"user": user,
		"allow": "OpenAS2 Instance",
		"for_value": instance_name,
		"applicable_for": "OpenAS2 Instance",
	}
	if not frappe.db.exists("User Permission", filters):
		frappe.get_doc(
			{
				"doctype": "User Permission",
				"user": user,
				"allow": "OpenAS2 Instance",
				"for_value": instance_name,
				"apply_to_all_doctypes": 0,
				"applicable_for": "OpenAS2 Instance",
			}
		).insert(ignore_permissions=True)

	# Partnerships are scoped by instance link
	p_filters = {
		"user": user,
		"allow": "OpenAS2 Instance",
		"for_value": instance_name,
		"applicable_for": "OpenAS2 Partnership",
	}
	if not frappe.db.exists("User Permission", p_filters):
		frappe.get_doc(
			{
				"doctype": "User Permission",
				"user": user,
				"allow": "OpenAS2 Instance",
				"for_value": instance_name,
				"apply_to_all_doctypes": 0,
				"applicable_for": "OpenAS2 Partnership",
			}
		).insert(ignore_permissions=True)


def seed_company_access(password: str | None = None) -> dict:
	"""Create Broker/Shipper/Carrier roles, users, and instance User Permissions.

	Usage:
	        bench --site openas2.local execute openas2_manager.setup.seed_company_access.seed_company_access
	"""
	password = password or DEFAULT_COMPANY_PASSWORD
	created_roles = []
	updated_users = []
	permissions = []

	from openas2_manager.setup.seed_instances import seed_demo_instances

	seed_demo_instances()

	for company, role in COMPANY_ROLES.items():
		_ensure_role(role)
		created_roles.append(role)
		for doctype in SCOPED_DOCTYPES:
			_ensure_custom_docperm(doctype, role)
		for page in PAGE_NAMES:
			_ensure_page_role(page, role)

	for row in COMPANY_USERS:
		role = COMPANY_ROLES[row["company"]]
		email = _ensure_user(
			row["email"],
			row["first_name"],
			roles=["Desk User", role],
			password=password,
		)
		_ensure_user_permission(email, row["instance"])
		updated_users.append(email)
		permissions.append(f"{email} -> {row['instance']}")

	frappe.clear_cache()
	frappe.db.commit()

	return {
		"roles": created_roles,
		"users": updated_users,
		"user_permissions": permissions,
		"password": password,
		"message": (
			"Company users can only open their own OpenAS2 Instance. "
			f"Login examples: broker@openas2.local / {password}"
		),
	}
