# Copyright (c) 2026, Lakshana and contributors
# One-shot helper for desk setup; safe to call via bench execute.

from __future__ import annotations

import frappe


def sync_broker_openas2a() -> dict:
	"""Sync Broker OpenAS2A Instance UI fields from Downloads/OpenAS2A config.xml."""
	frappe.set_user("Administrator")
	from openas2_manager.openas2.config_viewer import sync_instance_from_config

	return sync_instance_from_config("Broker OpenAS2A")
