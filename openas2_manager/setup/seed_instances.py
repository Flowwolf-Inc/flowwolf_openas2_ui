# Copyright (c) 2026, Lakshana and contributors
# For license information, please see license.txt

"""Idempotent seed for discovered local OpenAS2 instances (metadata only)."""

from __future__ import annotations

import frappe

# Values discovered from existing installs on this machine (read-only inspection).
# Does not modify OpenAS2 config.xml or restart servers.
DEMO_INSTANCES = [
	{
		"instance_name": "Shipper OpenAS20",
		"instance_type": "Shipper",
		"as2_id": "SHIPPER_AS2ID",
		"host": "localhost",
		"port": 12443,
		"protocol": "HTTPS",
		"http_port": 12080,
		"https_port": 12443,
		"mdn_http_port": 12081,
		"mdn_https_port": 12444,
		"health_port": 10099,
		"tracking_port": 9292,
		"openas2_home": "/mnt/c/Users/laksh/Downloads/OpenAS20",
		"windows_home": r"C:\Users\laksh\Downloads\OpenAS20",
		"inbox_path": "/mnt/c/Users/laksh/Downloads/OpenAS20/data/inbox/SHIPPER_AS2ID/inbox",
		"outbox_path": "/mnt/c/Users/laksh/Downloads/OpenAS20/data/outbox/BROKER_AS2ID",
		"x509_alias": "shipper",
		"certificate_status": "Configured",
		"mdn_enabled": 1,
		"status": "Active",
		"provision_source": "External",
		"description": (
			"OpenAS2 4.8.3 (jar). "
			"Home: /mnt/c/Users/laksh/Downloads/OpenAS20. "
			"HTTPS receiver port 12443; HTTP 12080. Metadata only."
		),
	},
	{
		"instance_name": "Broker OpenAS2A",
		"instance_type": "Broker",
		"as2_id": "BROKER_AS2ID",
		"host": "localhost",
		"port": 10443,
		"protocol": "HTTPS",
		"http_port": 10080,
		"https_port": 10443,
		"mdn_http_port": 10081,
		"mdn_https_port": 10444,
		"health_port": 10099,
		"tracking_port": 9092,
		"openas2_home": "/mnt/c/Users/laksh/Downloads/OpenAS2A",
		"windows_home": r"C:\Users\laksh\Downloads\OpenAS2A",
		"inbox_path": "/mnt/c/Users/laksh/Downloads/OpenAS2A/data/inbox/BROKER_AS2ID/inbox",
		"outbox_path": "/mnt/c/Users/laksh/Downloads/OpenAS2A/data/outbox/CARRIER_AS2ID",
		"x509_alias": "broker",
		"certificate_status": "Configured",
		"mdn_enabled": 1,
		"status": "Active",
		"provision_source": "External",
		"description": (
			"Broker instance mapped to OpenAS2A. "
			"Home: C:\\Users\\laksh\\Downloads\\OpenAS2A. "
			"HTTPS 10443; HTTP 10080; MDN 10081/10444. Metadata synced from config.xml."
		),
	},
	{
		"instance_name": "Carrier OpenAS2B",
		"instance_type": "Carrier",
		"as2_id": "CARRIER_AS2ID",
		"host": "localhost",
		"port": 11443,
		"protocol": "HTTPS",
		"http_port": 11080,
		"https_port": 11443,
		"mdn_http_port": 11081,
		"mdn_https_port": 11444,
		"health_port": 10099,
		"tracking_port": 9192,
		"openas2_home": "/mnt/c/Users/laksh/Downloads/OpenAS2B",
		"windows_home": r"C:\Users\laksh\Downloads\OpenAS2B",
		"inbox_path": "/mnt/c/Users/laksh/Downloads/OpenAS2B/data/inbox/CARRIER_AS2ID/inbox",
		"outbox_path": "/mnt/c/Users/laksh/Downloads/OpenAS2B/data/outbox/BROKER_AS2ID",
		"x509_alias": "carrier",
		"certificate_status": "Configured",
		"mdn_enabled": 1,
		"status": "Active",
		"provision_source": "External",
		"description": (
			"OpenAS2 4.8.3 (jar). "
			"Home: /mnt/c/Users/laksh/Downloads/OpenAS2B. "
			"HTTPS receiver port 11443; HTTP 11080. Metadata only."
		),
	},
	{
		"instance_name": "CompanyC OpenAS2C",
		"instance_type": "CompanyC",
		"as2_id": "OPENAS2C_AS2ID",
		"host": "localhost",
		"port": 13443,
		"protocol": "HTTPS",
		"http_port": 13080,
		"https_port": 13443,
		"mdn_http_port": 13081,
		"mdn_https_port": 13444,
		"health_port": 10199,
		"tracking_port": 9392,
		"openas2_home": "/mnt/c/Users/laksh/Downloads/OpenAS2C",
		"windows_home": r"C:\Users\laksh\Downloads\OpenAS2C",
		"inbox_path": "/mnt/c/Users/laksh/Downloads/OpenAS2C/data/inbox/OPENAS2C_AS2ID/inbox",
		"outbox_path": "/mnt/c/Users/laksh/Downloads/OpenAS2C/data/outbox/BROKER_AS2ID",
		"x509_alias": "shipper",
		"certificate_status": "Configured",
		"mdn_enabled": 1,
		"status": "Active",
		"provision_source": "External",
		"description": (
			"CompanyC mapped to OpenAS2C. "
			"Home: C:\\Users\\laksh\\Downloads\\OpenAS2C. "
			"HTTPS 13443; HTTP 13080; AS2 ID OPENAS2C_AS2ID."
		),
	},
]

# Fields backfilled on existing External / discovered rows (does not touch Manager Provisioned ports).
BACKFILL_FIELDS = (
	"openas2_home",
	"windows_home",
	"inbox_path",
	"outbox_path",
	"host",
	"port",
	"protocol",
	"http_port",
	"https_port",
	"mdn_http_port",
	"mdn_https_port",
	"health_port",
	"tracking_port",
	"x509_alias",
	"certificate_status",
	"mdn_enabled",
	"provision_source",
	"description",
)


def seed_demo_instances() -> dict:
	"""Create or backfill demo OpenAS2 Instance rows (matched by instance_name / as2_id).

	Usage:
	        bench --site openas2.local execute openas2_manager.setup.seed_instances.seed_demo_instances
	"""
	created = []
	updated = []
	skipped = []

	for row in DEMO_INSTANCES:
		name = row["instance_name"]
		as2_id = row["as2_id"]
		existing = frappe.db.exists("OpenAS2 Instance", name) or frappe.db.exists(
			"OpenAS2 Instance", {"as2_id": as2_id}
		)
		if existing:
			doc = frappe.get_doc("OpenAS2 Instance", existing)
			# Never overwrite Manager-provisioned runtime homes via seed.
			if doc.provision_source == "Manager Provisioned":
				skipped.append(doc.name)
				continue
			changed = False
			for field in BACKFILL_FIELDS:
				new_val = row.get(field)
				if new_val in (None, ""):
					continue
				if getattr(doc, field, None) != new_val:
					setattr(doc, field, new_val)
					changed = True
			if changed:
				doc.save(ignore_permissions=True)
				updated.append(doc.name)
			else:
				skipped.append(doc.name)
			continue

		frappe.get_doc({"doctype": "OpenAS2 Instance", **row}).insert(ignore_permissions=True)
		created.append(name)

	frappe.db.commit()
	return {
		"created": created,
		"updated": updated,
		"skipped": skipped,
		"message": (
			f"Created {len(created)}; updated {len(updated)}; skipped {len(skipped)}."
		),
	}
