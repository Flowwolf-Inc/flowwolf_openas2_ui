# Copyright (c) 2026, Lakshana and contributors


def sync_companyc_openas2c() -> dict:
	"""Sync CompanyC OpenAS2C Instance UI fields from Downloads/OpenAS2C config.xml."""
	import frappe
	from openas2_manager.openas2.config_viewer import sync_instance_from_config

	frappe.set_user("Administrator")
	return sync_instance_from_config("CompanyC OpenAS2C")
