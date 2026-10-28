# Copyright (c) 2026, Lakshana and contributors
# For license information, please see license.txt

"""One-shot Phase 1 demo provisioner for local verification."""

from __future__ import annotations

import json

from openas2_manager.openas2.provisioning import provision_openas2_instance


def main():
	result = provision_openas2_instance(
		instance_name="Broker ABC Demo",
		instance_type="Broker",
		as2_id="BROKER_ABC_DEMO",
		mdn_enabled=1,
		host="localhost",
	)
	print(json.dumps(result, indent=2, default=str))
	return result
