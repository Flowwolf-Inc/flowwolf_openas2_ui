# Copyright (c) 2026, Lakshana and contributors
# For license information, please see license.txt

"""Idempotent demo/seed helpers for OpenAS2 Manager."""

from __future__ import annotations

import frappe

DEMO_PARTNERS = [
	{
		"partner_name": "Shipper",
		"as2_id": "SHIPPER_AS2ID",
		"partner_type": "Shipper",
		"as2_url": "https://shipper.example.local/as2",
		"encryption_enabled": 1,
		"signing_enabled": 1,
		"mdn_enabled": 1,
		"mdn_mode": "Synchronous",
		"status": "Active",
		"description": "Demo Shipper TMS AS2 partner (configuration only).",
	},
	{
		"partner_name": "Broker",
		"as2_id": "BROKER_AS2ID",
		"partner_type": "Broker",
		"as2_url": "https://broker.example.local/as2",
		"encryption_enabled": 1,
		"signing_enabled": 1,
		"mdn_enabled": 1,
		"mdn_mode": "Synchronous",
		"status": "Active",
		"description": "Demo Broker TMS AS2 partner (configuration only).",
	},
	{
		"partner_name": "Carrier",
		"as2_id": "CARRIER_AS2ID",
		"partner_type": "Carrier",
		"as2_url": "https://carrier.example.local/as2",
		"encryption_enabled": 1,
		"signing_enabled": 1,
		"mdn_enabled": 1,
		"mdn_mode": "Synchronous",
		"status": "Active",
		"description": "Demo Carrier TMS AS2 partner (configuration only).",
	},
]


def seed_demo_partners() -> dict:
	"""Create demo AS2 Partner records if they do not already exist.

	Safe to run repeatedly: existing partners (matched by as2_id / name)
	are left unchanged.

	Usage:
	        bench --site openas2.local execute openas2_manager.setup.seed.seed_demo_partners
	"""
	created = []
	skipped = []

	for partner in DEMO_PARTNERS:
		as2_id = partner["as2_id"]
		if frappe.db.exists("AS2 Partner", as2_id) or frappe.db.exists(
			"AS2 Partner", {"as2_id": as2_id}
		):
			skipped.append(as2_id)
			continue

		doc = frappe.get_doc({"doctype": "AS2 Partner", **partner})
		doc.insert(ignore_permissions=True)
		created.append(as2_id)

	frappe.db.commit()
	return {
		"created": created,
		"skipped": skipped,
		"message": f"Created {len(created)} partner(s); skipped {len(skipped)} existing.",
	}
