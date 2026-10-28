# Copyright (c) 2026, Lakshana and contributors
# For license information, please see license.txt

"""Safe diagnostics for OpenAS2 Instance listener reachability.

This module performs host/port validation and an optional short TCP connect.
It does **not**:

- send EDI or AS2 protocol messages
- perform TLS/AS2 handshake verification beyond TCP open
- edit OpenAS2 config.xml / partnerships.xml
- restart OpenAS2
- read or return keystore / database passwords
"""

from __future__ import annotations

import socket

import frappe
from frappe.utils import now_datetime

TCP_TIMEOUT_SECONDS = 3.0


def validate_host_port(host: str, port) -> None:
	if not host or not str(host).strip():
		frappe.throw(frappe._("Host is required for connection testing."))
	try:
		port_num = int(port)
	except (TypeError, ValueError):
		frappe.throw(frappe._("Port must be an integer."))
	if port_num < 1 or port_num > 65535:
		frappe.throw(frappe._("Port must be between 1 and 65535."))


def tcp_reachability_check(host: str, port: int, timeout: float = TCP_TIMEOUT_SECONDS) -> dict:
	"""Attempt a TCP connect only. Does not speak HTTP/HTTPS/AS2."""
	sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	sock.settimeout(timeout)
	try:
		sock.connect((host, int(port)))
		return {
			"reachable": True,
			"error": None,
			"check_type": "tcp_connect",
		}
	except OSError as exc:
		return {
			"reachable": False,
			"error": str(exc),
			"check_type": "tcp_connect",
		}
	finally:
		sock.close()


@frappe.whitelist()
def test_instance_connection(name: str) -> dict:
	"""Desk Test Connection entry point.

	Records ``connection_status`` and ``last_tested`` on the document.
	``Connected`` means the TCP port accepted a connection — not that an
	AS2 handshake or EDI exchange succeeded.
	"""
	if not name:
		frappe.throw(frappe._("OpenAS2 Instance name is required."))

	doc = frappe.get_doc("OpenAS2 Instance", name)
	validate_host_port(doc.host, doc.port)

	result = tcp_reachability_check(doc.host, int(doc.port))
	tested_at = now_datetime()

	if result["reachable"]:
		connection_status = "Connected"
		message = (
			f"TCP reachability OK for {doc.protocol}://{doc.host}:{int(doc.port)}.\n\n"
			"This confirms the host:port accepted a TCP connection only.\n"
			"It does NOT verify TLS, AS2 protocol, MDN, certificates, or EDI.\n"
			"Full OpenAS2 endpoint verification remains integration-pending."
		)
	else:
		connection_status = "Failed"
		message = (
			f"TCP reachability FAILED for {doc.protocol}://{doc.host}:{int(doc.port)}.\n\n"
			f"Error: {result['error']}\n\n"
			"No EDI was sent and OpenAS2 configuration was not changed.\n"
			"If the OpenAS2 process is not running, start it outside this UI and retest."
		)

	doc.db_set(
		{
			"connection_status": connection_status,
			"last_tested": tested_at,
		},
		update_modified=True,
	)

	return {
		"instance": doc.name,
		"host": doc.host,
		"port": int(doc.port),
		"protocol": doc.protocol,
		"connection_status": connection_status,
		"last_tested": str(tested_at),
		"check_type": result["check_type"],
		"as2_protocol_verified": False,
		"edi_sent": False,
		"config_modified": False,
		"message": message,
	}
