# Copyright (c) 2026, Lakshana and contributors
# For license information, please see license.txt

"""Safe TCP port allocation for provisioned OpenAS2 instances.

Reserves ports in Frappe DB (OpenAS2 Instance fields) and verifies the port
is bindable on this host before assignment. Does not start OpenAS2.
"""

from __future__ import annotations

import socket
from typing import Iterable

import frappe

# Type → (http_start, https_start, mdn_http_start, mdn_https_start, tracking_start, health_start)
PORT_POOLS = {
	"Shipper": (12080, 12443, 12081, 12444, 9292, 12099),
	"Broker": (10080, 10443, 10081, 10444, 9092, 10099),
	"Carrier": (11080, 11443, 11081, 11444, 9192, 11099),
	"CompanyC": (13080, 13443, 13081, 13444, 9392, 10199),
}

POOL_SIZE = 100

# Always treat as occupied (legacy + dangerous defaults), even if not in DocType yet.
STATIC_RESERVED_PORTS = frozenset(
	{
		# Shipper OpenAS20
		12080,
		12081,
		12443,
		12444,
		9292,
		# Broker OpenAS2A
		10080,
		10081,
		10443,
		10444,
		9092,
		# Carrier OpenAS2B
		11080,
		11081,
		11443,
		11444,
		9192,
		# CompanyC OpenAS2C
		13080,
		13081,
		13443,
		13444,
		9392,
		10199,
		# Shared defaults that would collide if enabled
		10099,
		8080,
	}
)

INSTANCE_PORT_FIELDS = (
	"port",
	"http_port",
	"https_port",
	"mdn_http_port",
	"mdn_https_port",
	"health_port",
	"tracking_port",
)


def _require_system_manager():
	if "System Manager" not in frappe.get_roles(frappe.session.user):
		frappe.throw(frappe._("Only System Managers may allocate OpenAS2 ports."), frappe.PermissionError)


def collect_used_ports(exclude_instance: str | None = None) -> set[int]:
	"""Ports already claimed by OpenAS2 Instance rows + static legacy set."""
	used: set[int] = set(STATIC_RESERVED_PORTS)
	filters = {}
	if exclude_instance:
		filters["name"] = ["!=", exclude_instance]

	rows = frappe.get_all(
		"OpenAS2 Instance",
		filters=filters,
		fields=list(INSTANCE_PORT_FIELDS),
	)
	for row in rows:
		for field in INSTANCE_PORT_FIELDS:
			val = row.get(field)
			if val in (None, ""):
				continue
			try:
				used.add(int(val))
			except (TypeError, ValueError):
				continue
	return used


def is_port_available(port: int, host: str = "127.0.0.1") -> bool:
	"""True if we can bind TCP on host:port (port not in use locally)."""
	if port < 1 or port > 65535:
		return False
	for family, proto in ((socket.AF_INET, socket.SOCK_STREAM),):
		sock = socket.socket(family, proto)
		try:
			sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
			sock.bind((host, port))
			return True
		except OSError:
			return False
		finally:
			sock.close()
	return False


def _candidates(start: int) -> Iterable[int]:
	for offset in range(POOL_SIZE):
		yield start + offset


def allocate_ports_for_type(
	instance_type: str,
	*,
	exclude_instance: str | None = None,
	host: str = "127.0.0.1",
) -> dict[str, int]:
	"""Allocate a unique, bindable port set for one instance type.

	Returns keys: http_port, https_port, mdn_http_port, mdn_https_port,
	tracking_port, health_port.
	"""
	_require_system_manager()
	if instance_type not in PORT_POOLS:
		frappe.throw(frappe._("Unknown instance type: {0}").format(instance_type))

	http0, https0, mdn_h0, mdn_s0, track0, health0 = PORT_POOLS[instance_type]
	used = collect_used_ports(exclude_instance=exclude_instance)

	def pick(start: int, label: str) -> int:
		for port in _candidates(start):
			if port in used:
				continue
			if not is_port_available(port, host=host):
				used.add(port)
				continue
			used.add(port)
			return port
		frappe.throw(
			frappe._("No available {0} ports left in pool starting at {1}.").format(label, start)
		)

	# Pick sequentially so reserved set grows within this allocation.
	http_port = pick(http0, "HTTP")
	https_port = pick(https0, "HTTPS")
	mdn_http_port = pick(mdn_h0, "MDN HTTP")
	mdn_https_port = pick(mdn_s0, "MDN HTTPS")
	tracking_port = pick(track0, "tracking")
	health_port = pick(health0, "health")

	return {
		"http_port": http_port,
		"https_port": https_port,
		"mdn_http_port": mdn_http_port,
		"mdn_https_port": mdn_https_port,
		"tracking_port": tracking_port,
		"health_port": health_port,
	}
