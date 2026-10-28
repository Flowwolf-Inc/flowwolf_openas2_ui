# Copyright (c) 2026, Lakshana and contributors
# For license information, please see license.txt

"""Desk boot / session hooks for OpenAS2 Manager."""

from __future__ import annotations

import frappe


DASHBOARD_PAGE = "openas2-dashboard"
DASHBOARD_ROUTE = "/app/openas2-dashboard"


def boot_session(bootinfo):
	"""Open the EDI AS2 dashboard as Desk home (app-style login landing)."""
	if frappe.session.user == "Guest":
		return
	if not frappe.db.exists("Page", DASHBOARD_PAGE):
		return

	bootinfo["home_page"] = DASHBOARD_PAGE

	# Stop Desk from preferring a Workspace over the dashboard Page.
	user = bootinfo.get("user")
	if isinstance(user, dict):
		user["default_workspace"] = None


def on_session_creation(login_manager=None):
	"""Prefer the OpenAS2 dashboard after login.

	Do not monkey-patch LoginManager — it uses __slots__ and assignment
	raises AttributeError, which breaks login entirely.

	Note: LoginManager.set_user_info may overwrite response["home_page"] when
	the user has default_workspace set. ensure_dashboard_home clears that.
	When default_workspace is empty, set_user_info uses get_default_path(),
	which returns add_to_apps_screen.route for default_app=openas2_manager.
	"""
	user = getattr(login_manager, "user", None) or frappe.session.user
	if not user or user == "Guest":
		return
	if not frappe.db.exists("Page", DASHBOARD_PAGE):
		return

	frappe.cache.hset("redirect_after_login", user, DASHBOARD_ROUTE)

	if getattr(frappe.local, "response", None) is not None:
		frappe.local.response["home_page"] = DASHBOARD_ROUTE


def has_app_permission() -> bool:
	"""Show OpenAS2 Manager on the apps switcher for any Desk user."""
	return frappe.session.user != "Guest"


def ensure_dashboard_home():
	"""Persist Desk defaults so login lands on the dashboard like an app."""
	if not frappe.db.exists("Page", DASHBOARD_PAGE):
		return

	frappe.db.set_default("desktop:home_page", DASHBOARD_PAGE)

	# default_workspace wins over get_default_path() on login — clear it.
	frappe.db.sql(
		"""
		UPDATE `tabUser`
		SET default_workspace = NULL
		WHERE IFNULL(default_workspace, '') != ''
		"""
	)

	# Hide the Workspace so it is less likely to be used as the app front.
	if frappe.db.exists("Workspace", "OpenAS2 Manager"):
		frappe.db.set_value("Workspace", "OpenAS2 Manager", "is_hidden", 1, update_modified=False)

	try:
		if frappe.get_meta("System Settings").has_field("default_app"):
			frappe.db.set_single_value("System Settings", "default_app", "openas2_manager")
	except Exception:
		frappe.log_error(title="OpenAS2 Manager: could not set default_app")

	try:
		if frappe.get_meta("User").has_field("default_app"):
			frappe.db.sql(
				"""
				UPDATE `tabUser`
				SET default_app = %s
				WHERE user_type = 'System User'
					AND name not in ('Guest')
					AND IFNULL(default_app, '') = ''
				""",
				("openas2_manager",),
			)
			if frappe.db.exists("User", "Administrator"):
				frappe.db.set_value(
					"User", "Administrator", "default_app", "openas2_manager", update_modified=False
				)
	except Exception:
		frappe.log_error(title="OpenAS2 Manager: could not set user default_app")


def after_migrate():
	ensure_dashboard_home()
	frappe.clear_cache()
