# Copyright (c) 2026, Lakshana and contributors
# For license information, please see license.txt

"""Remote tracking tests. Database connections are mocked."""

from __future__ import annotations

import json
import time
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from openas2_manager.openas2 import monitoring as mon
from openas2_manager.openas2 import remote_tracking as remote
from openas2_manager.openas2.test_x12_json import _interchange, _txn


INSTANCES = {
	"SHIPPER_AS2ID": {
		"name": "Shipper OpenAS20",
		"as2_id": "SHIPPER_AS2ID",
		"instance_type": "Shipper",
		"instance_name": "Shipper",
	},
	"BROKER_AS2ID": {
		"name": "Broker OpenAS2A",
		"as2_id": "BROKER_AS2ID",
		"instance_type": "Broker",
		"instance_name": "Broker",
	},
}

SCOPE = {
	"allowed_as2": ["SHIPPER_AS2ID"],
	"preferred_as2": [],
	"query_ids": ["SHIPPER_AS2ID"],
	"instances_by_as2": INSTANCES,
	"partners_by_as2": {"BROKER_AS2ID": "Broker"},
}


class FakeCursor:
	def __init__(self, conn):
		self.conn = conn

	def __enter__(self):
		return self

	def __exit__(self, exc_type, exc, tb):
		return False

	def execute(self, sql, params=None):
		self.conn.statements.append((sql, params))

	def fetchall(self):
		return self.conn.rows


class FakeConnection:
	def __init__(self, rows):
		self.rows = rows
		self.statements = []
		self.closed = False

	def cursor(self):
		return FakeCursor(self)

	def close(self):
		self.closed = True


class _QueuedConnection(FakeConnection):
	"""Return a different result set for each query."""

	def __init__(self, batches):
		super().__init__([])
		self.batches = list(batches)

	def cursor(self):
		connection = self

		class QueuedCursor(FakeCursor):
			def fetchall(self):
				return connection.batches.pop(0)

		return QueuedCursor(self)


def _record(**overrides):
	row = {
		"id": 15,
		"msg_id": "<abc@openas2>",
		"direction": "SEND",
		"sender_id": "SHIPPER_AS2ID",
		"receiver_id": "BROKER_AS2ID",
		"status": "ok",
		"state": "msg_sent_mdn_received_ok",
		"file_name": "LOAD054_204.edi",
		"create_dt": "2026-10-15 09:00:00",
		"update_dt": "2026-10-15 09:01:00",
	}
	row.update(overrides)
	return row


class TestRemoteMapping(unittest.TestCase):
	def test_transport_fields_keep_real_values_and_skip_blanks(self):
		parties = remote.assign_parties(
			_record(),
			instances_by_as2=INSTANCES,
			allowed_as2=["SHIPPER_AS2ID"],
			preferred_as2=[],
		)
		row = remote.to_message_row(
			_record(
				signature_algorithm="SHA-256",
				encryption_algorithm="  ",
				mdn_id=None,
				resend_count=0,
			),
			parties,
		)
		self.assertEqual(row["signature_algorithm"], "SHA-256")
		self.assertNotIn("encryption_algorithm", row)
		self.assertNotIn("mdn_id", row)
		self.assertEqual(row["resend_count"], 0)
		blank = remote.to_message_row(_record(), parties)
		for key in ("signature_algorithm", "encryption_algorithm", "mdn_id", "resend_count"):
			self.assertNotIn(key, blank)

	def test_list_and_detail_queries_select_transport_fields_without_payloads(self):
		list_sql, _params = remote.build_list_query(as2_ids=["SHIPPER_AS2ID"], limit=5)
		detail_sql, _params = remote.build_detail_query(15, ["SHIPPER_AS2ID"])
		for sql in (list_sql, detail_sql):
			self.assertIn("signature_algorithm", sql)
			self.assertIn("encryption_algorithm", sql)
			self.assertIn("mdn_id", sql)
			self.assertIn("resend_count", sql)
			self.assertNotIn("msg_data", sql)
			self.assertNotIn("msg_headers", sql)
			self.assertNotIn("mdn_response", sql)

	def test_cleanup_is_not_a_failure(self):
		self.assertEqual(remote.map_status("cleanup", "msg_sent_mdn_received_ok"), "Processed")
		self.assertNotEqual(remote.map_status("cleanup", ""), "Failed")

	def test_cleanup_with_error_state_is_failed(self):
		self.assertEqual(remote.map_status("cleanup", "msg_send_fail"), "Failed")

	def test_error_status_is_failed_and_state_is_kept(self):
		self.assertEqual(remote.map_status("error", "msg_sent_mdn_received_error"), "Failed")
		parties = remote.assign_parties(
			_record(status="error", state="msg_sent_mdn_received_error"),
			instances_by_as2=INSTANCES,
			allowed_as2=["SHIPPER_AS2ID"],
			preferred_as2=[],
		)
		row = remote.to_message_row(
			_record(status="error", state="msg_sent_mdn_received_error"),
			parties,
		)
		self.assertEqual(row["status"], "Failed")
		self.assertEqual(row["state"], "msg_sent_mdn_received_error")
		self.assertIn("msg_sent_mdn_received_error", row["error_message"])

	def test_direction_and_instance_mapping(self):
		self.assertEqual(remote.map_direction("SEND"), "Outbound")
		self.assertEqual(remote.map_direction("RECEIVE"), "Inbound")
		outbound = remote.assign_parties(
			_record(),
			instances_by_as2=INSTANCES,
			allowed_as2=["SHIPPER_AS2ID"],
			preferred_as2=[],
		)
		self.assertEqual(outbound["instance"], "Shipper OpenAS20")
		self.assertEqual(outbound["direction"], "Outbound")
		self.assertEqual(outbound["local_as2_id"], "SHIPPER_AS2ID")
		self.assertEqual(outbound["remote_as2_id"], "BROKER_AS2ID")

		inbound = remote.assign_parties(
			_record(direction="RECEIVE", sender_id="BROKER_AS2ID", receiver_id="SHIPPER_AS2ID"),
			instances_by_as2=INSTANCES,
			allowed_as2=["SHIPPER_AS2ID"],
			preferred_as2=[],
		)
		self.assertEqual(inbound["direction"], "Inbound")
		self.assertEqual(inbound["instance"], "Shipper OpenAS20")

	def test_other_instance_is_hidden(self):
		hidden = remote.assign_parties(
			_record(sender_id="BROKER_AS2ID", receiver_id="CARRIER_AS2ID"),
			instances_by_as2=INSTANCES,
			allowed_as2=["SHIPPER_AS2ID"],
			preferred_as2=[],
		)
		self.assertIsNone(hidden)

	def test_row_shape_and_transaction_filter(self):
		parties = remote.assign_parties(
			_record(),
			instances_by_as2=INSTANCES,
			allowed_as2=["SHIPPER_AS2ID"],
			preferred_as2=[],
		)
		row = remote.to_message_row(_record(), parties, {"BROKER_AS2ID": "Broker"})
		self.assertEqual(row["name"], "remote:15")
		self.assertEqual(row["message_id"], "abc@openas2")
		self.assertEqual(row["message_id_display"], "<abc@openas2>")
		self.assertEqual(row["file_name"], "LOAD054_204.edi")
		self.assertEqual(row["transaction_type"], "204")
		self.assertEqual(row["timestamp"], "2026-10-15 09:01:00")
		self.assertEqual(row["partner"], "Broker")
		self.assertEqual(row["status"], "Success")
		self.assertEqual(row["mdn_status"], "Received")
		self.assertTrue(
			remote.matches_filters(row, transaction_type="204", direction="Outbound", status="Success")
		)
		self.assertFalse(remote.matches_filters(row, transaction_type="990"))
		self.assertFalse(remote.matches_filters(row, status="Failed"))
		self.assertTrue(remote.matches_filters(row, status="MDN Received"))
		self.assertEqual(row["state"], "msg_sent_mdn_received_ok")
		self.assertNotEqual(row["status"], row["state"])
		self.assertEqual(row["mdn_status"], "Received")

	def test_mdn_received_filter_matches_successful_live_rows(self):
		parties = remote.assign_parties(
			_record(),
			instances_by_as2=INSTANCES,
			allowed_as2=["SHIPPER_AS2ID"],
			preferred_as2=[],
		)
		received = remote.to_message_row(_record(), parties)
		plain = remote.to_message_row(
			_record(id=16, status="ok", state="msg_sent"),
			parties,
		)
		failed = remote.to_message_row(
			_record(id=17, status="error", state="msg_sent_mdn_received_error"),
			parties,
		)
		self.assertTrue(remote.matches_filters(received, status="MDN Received"))
		self.assertTrue(remote.matches_filters(received, status="Success"))
		self.assertFalse(remote.matches_filters(plain, status="MDN Received"))
		self.assertTrue(remote.matches_filters(plain, status="Success"))
		self.assertFalse(remote.matches_filters(failed, status="MDN Received"))
		self.assertEqual(failed["mdn_status"], "Failed")
		self.assertEqual(failed["state"], "msg_sent_mdn_received_error")

	def test_processed_messages_count_as_successful(self):
		totals = remote.activity_totals(
			[
				{"status": "Success", "direction": "Outbound", "mdn_status": "Received"},
				{"status": "Processed", "direction": "Inbound", "mdn_status": "Received"},
				{"status": "Failed", "direction": "Outbound", "mdn_status": "Failed"},
			]
		)
		self.assertEqual(totals["messages_today"], 3)
		self.assertEqual(totals["successful"], 2)
		self.assertEqual(totals["processed"], 1)
		self.assertEqual(totals["failed"], 1)
		self.assertEqual(totals["inbound"], 1)
		self.assertEqual(totals["outbound"], 2)

	def test_filtered_queries_keep_access_and_placeholder_counts(self):
		for builder, args in (
			(
				remote.build_list_query,
				{"as2_ids": ["SHIPPER_AS2ID"], "status": "Failed", "transaction_type": "204", "limit": 25},
			),
			(
				remote.build_list_query,
				{"as2_ids": ["SHIPPER_AS2ID"], "status": "MDN Received", "limit": 25},
			),
			(remote.build_detail_query, (15, ["SHIPPER_AS2ID"])),
			(
				remote.build_summary_query,
				{"as2_ids": ["SHIPPER_AS2ID", "BROKER_AS2ID"], "date_from": datetime(2026, 10, 15)},
			),
		):
			if isinstance(args, dict):
				sql, params = builder(**args)
			else:
				sql, params = builder(*args)
			self.assertEqual(sql.count("%s"), len(params), sql)
			self.assertIn("SHIPPER_AS2ID", params)
			self.assertNotIn("SHIPPER_AS2ID", sql)
			self.assertNotIn("msg_data", sql)
			self.assertNotIn("msg_headers", sql)
			self.assertNotIn("mdn_response", sql)
		failed_sql, failed_params = remote.build_list_query(
			as2_ids=["SHIPPER_AS2ID"],
			status="Failed",
			transaction_type="990",
			limit=10,
		)
		self.assertLess(failed_sql.index("WHERE"), failed_sql.index("ORDER BY id DESC LIMIT"))
		self.assertIn("error", failed_sql)
		self.assertIn("(^|[_.-])990([_.-]|$)", failed_params)
		summary_sql, _summary_params = remote.build_summary_query(
			as2_ids=["SHIPPER_AS2ID"],
			date_from=datetime(2026, 10, 15),
		)
		self.assertIn("create_dt >= %s", summary_sql)
		self.assertIn("cleanup", summary_sql)

	def test_list_total_is_unpaged_and_fails_closed(self):
		counted, params = remote.build_count_query(
			as2_ids=["SHIPPER_AS2ID"],
			status="Failed",
			transaction_type="204",
			partner_ids=["BROKER_AS2ID"],
			search="LOAD_204",
		)
		self.assertIn("SELECT COUNT(*) AS total", counted)
		self.assertNotIn("LIMIT", counted.upper())
		self.assertNotIn("msg_data", counted)
		self.assertNotIn("msg_headers", counted)
		self.assertNotIn("mdn_response", counted)
		self.assertNotIn("LOAD_204", counted)
		self.assertNotIn("BROKER_AS2ID", counted)
		self.assertIn("BROKER_AS2ID", params)
		self.assertIn("SHIPPER_AS2ID", params)
		self.assertEqual(counted.count("%s"), len(params))
		listed, _list_params = remote.build_list_query(
			as2_ids=["SHIPPER_AS2ID"], status="Failed", transaction_type="204", limit=100
		)
		self.assertIn("sender_id IN (%s)", listed)
		self.assertIn("sender_id IN (%s)", counted)

		connection = FakeConnection([{"total": 125}])
		with (
			patch.object(remote, "remote_reads_enabled", return_value=True),
			patch.object(remote, "read_settings", return_value=({"password": "secret"}, None)),
			patch.object(remote, "resolve_scope", return_value=SCOPE),
			patch.object(remote, "connect", return_value=connection),
		):
			found = remote.count_live_messages(partner="Broker", search="204", status="Success")
		self.assertEqual(found, {"ok": True, "total": 125})
		count_sql = [sql for sql, _params in connection.statements if "COUNT(*)" in sql][-1]
		self.assertNotIn("msg_data", count_sql)
		self.assertIn("SET SESSION TRANSACTION READ ONLY", connection.statements[0][0])

		with (
			patch.object(remote, "remote_reads_enabled", return_value=True),
			patch.object(remote, "read_settings", return_value=({"password": "secret"}, None)),
			patch.object(remote, "resolve_scope", return_value=SCOPE),
			patch.object(remote, "connect", return_value=FakeConnection([{"total": 0}])),
		):
			empty = remote.count_live_messages(search="missing-file")
		self.assertEqual(empty["total"], 0)
		self.assertTrue(empty["ok"])

		with (
			patch.object(remote, "remote_reads_enabled", return_value=True),
			patch.object(remote, "read_settings", return_value=({"password": "secret"}, None)),
			patch.object(remote, "resolve_scope", return_value=SCOPE),
			patch.object(remote, "connect", side_effect=TimeoutError("timed out")),
		):
			failed = remote.count_live_messages()
		self.assertFalse(failed["ok"])
		self.assertIsNone(failed["total"])
		self.assertEqual(failed["error"], remote.REMOTE_READ_ERROR)

		import pymysql

		with (
			patch.object(remote, "remote_reads_enabled", return_value=True),
			patch.object(remote, "read_settings", return_value=({"password": "secret-value"}, None)),
			patch.object(remote, "resolve_scope", return_value=SCOPE),
			patch.object(
				remote,
				"connect",
				side_effect=pymysql.err.OperationalError(
					2013,
					"Lost connection to MySQL server during query (timed out) secret-value",
				),
			),
			patch.object(remote, "_warn") as warn,
		):
			timed_out = remote.count_live_messages(status="Success")
		self.assertFalse(timed_out["ok"])
		self.assertIsNone(timed_out["total"])
		logged = warn.call_args[0][0]
		self.assertIn("2013", logged)
		self.assertIn("timed out", logged)
		self.assertNotIn("secret-value", logged)

		with (
			patch.object(remote, "remote_reads_enabled", return_value=True),
			patch.object(remote, "read_settings", return_value=({"password": "secret"}, None)),
			patch.object(remote, "resolve_scope", return_value=None),
		):
			blocked = remote.count_live_messages()
		self.assertEqual(blocked, {"ok": True, "total": 0})

		page = (
			Path(__file__).resolve().parents[1]
			/ "openas2_manager"
			/ "page"
			/ "openas2_messages"
			/ "openas2_messages.js"
		).read_text(encoding="utf-8")
		self.assertIn("if (!background) this.load_list_total();", page)
		self.assertIn("openas2_manager.openas2.monitoring.get_list_total", page)
		render = page.split("render_list_total(tab, message)", 1)[1].split("load_list_total()", 1)[0]
		self.assertIn("Total Messages", page)
		self.assertIn("message.total", render)
		self.assertIn("Unavailable", render)
		self.assertNotIn("rows.length", render)

	def _edi_scope(self):
		return {"allowed_as2": ["SHIPPER_AS2ID"], "instances_by_as2": INSTANCES}

	def test_coded_filename_skips_edi_lookup(self):
		parties = remote.assign_parties(
			_record(),
			instances_by_as2=INSTANCES,
			allowed_as2=["SHIPPER_AS2ID"],
			preferred_as2=[],
		)
		row = remote.to_message_row(_record(), parties)
		self.assertEqual(row["transaction_type"], "204")

		def fetch(*_args, **_kwargs):
			raise AssertionError("EDI lookup")

		remote.apply_known_edi_types([row], self._edi_scope(), fetch=fetch)
		self.assertEqual(row["transaction_type"], "204")

	def test_uncoded_filename_uses_accessible_edi_document(self):
		row = {
			"transaction_type": "Unknown",
			"file_name": "plain.edi",
			"message_id": "mid-1",
			"instance": "Shipper OpenAS20",
		}

		def fetch(file_names, message_ids, allowed_names):
			self.assertIn("plain.edi", file_names)
			self.assertIn("mid-1", message_ids)
			self.assertEqual(allowed_names, ["Shipper OpenAS20"])
			return [
				{
					"instance": "Shipper OpenAS20",
					"file_name": "plain.edi",
					"as2_message_id": "mid-1",
					"transaction_type": "214",
				}
			]

		remote.apply_known_edi_types([row], self._edi_scope(), fetch=fetch)
		self.assertEqual(row["transaction_type"], "214")

	def test_no_edi_match_stays_unknown_and_does_not_insert(self):
		row = {
			"transaction_type": "Unknown",
			"file_name": "plain.edi",
			"message_id": "mid-1",
			"instance": "Shipper OpenAS20",
		}
		with patch.object(remote.frappe, "get_doc", side_effect=AssertionError("insert")):
			remote.apply_known_edi_types([row], self._edi_scope(), fetch=lambda *_args: [])
		self.assertEqual(row["transaction_type"], "Unknown")

	def test_unsupported_or_empty_edi_type_stays_unknown(self):
		row = {
			"transaction_type": "Unknown",
			"file_name": "plain.edi",
			"message_id": "",
			"instance": "Shipper OpenAS20",
		}
		for bad_type in ("", "999", "EDI"):
			row["transaction_type"] = "Unknown"
			docs = [
				{
					"instance": "Shipper OpenAS20",
					"file_name": "plain.edi",
					"as2_message_id": "",
					"transaction_type": bad_type,
				}
			]
			remote.apply_known_edi_types([row], self._edi_scope(), fetch=lambda *_args, docs=docs: docs)
			self.assertEqual(row["transaction_type"], "Unknown")

	def test_inaccessible_edi_document_does_not_leak_type(self):
		row = {
			"transaction_type": "Unknown",
			"file_name": "plain.edi",
			"message_id": "mid-1",
			"instance": "Shipper OpenAS20",
		}
		docs = [
			{
				"instance": "Broker OpenAS2A",
				"file_name": "plain.edi",
				"as2_message_id": "mid-1",
				"transaction_type": "810",
			}
		]
		remote.apply_known_edi_types([row], self._edi_scope(), fetch=lambda *_args: docs)
		self.assertEqual(row["transaction_type"], "Unknown")

	def test_query_is_parameterized_and_skips_payloads(self):
		as2_id = "SHIPPER' OR 1=1"
		sql, params = remote.build_list_query(as2_ids=[as2_id], date_from="2026-10-15", limit=25)
		self.assertNotIn(as2_id, sql)
		self.assertIn(as2_id, params)
		self.assertNotIn("msg_data", sql)
		self.assertNotIn("msg_headers", sql)
		self.assertNotIn("mdn_response", sql)
		self.assertIn("ORDER BY id DESC LIMIT %s", sql)
		for column in remote.SAFE_COLUMNS:
			self.assertIn(column, sql)


class TestRemoteAccess(unittest.TestCase):
	def _list(self, rows, scope=None):
		connection = FakeConnection(rows)
		with (
			patch.object(remote, "remote_reads_enabled", return_value=True),
			patch.object(remote, "read_settings", return_value=({"password": "secret"}, None)),
			patch.object(remote, "resolve_scope", return_value=SCOPE if scope is None else scope),
			patch.object(remote, "connect", return_value=connection),
		):
			result = remote.list_live_messages(limit=10)
		return result, connection

	def test_list_maps_visible_rows_and_sets_read_only(self):
		result, connection = self._list([_record(), _record(id=16, sender_id="OTHER", receiver_id="NOPE")])
		self.assertEqual(result["count"], 1)
		self.assertEqual(result["rows"][0]["instance"], "Shipper OpenAS20")
		joined = "\n".join(sql for sql, _params in connection.statements)
		self.assertIn("SET SESSION TRANSACTION READ ONLY", joined)
		self.assertNotIn("msg_data", joined)
		self.assertTrue(connection.closed)
		self.assertNotIn("secret", joined)

	def test_no_access_skips_the_database(self):
		with (
			patch.object(remote, "remote_reads_enabled", return_value=True),
			patch.object(remote, "read_settings", return_value=({"password": "secret"}, None)),
			patch.object(remote, "resolve_scope", return_value=None),
			patch.object(remote, "connect") as connect,
		):
			result = remote.list_live_messages()
		self.assertEqual(result, {"rows": [], "count": 0})
		connect.assert_not_called()

	def test_password_file_is_used_when_the_process_env_is_empty(self):
		import tempfile

		with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
			handle.write('export OPENAS2_REMOTE_READ_PASSWORD="secret-value"\n')
			path = handle.name
		try:
			settings, reason = remote.read_settings(
				{
					"openas2_remote_read": {
						"db_type": "mariadb",
						"host": "db.example",
						"port": 3306,
						"database": "openas2",
						"user": "openas2_ro",
						"password_env": "OPENAS2_REMOTE_READ_PASSWORD",
					}
				},
				{"OPENAS2_REMOTE_READ_ENV": path},
			)
		finally:
			Path(path).unlink(missing_ok=True)
		self.assertIsNone(reason)
		self.assertEqual(settings["password"], "secret-value")
		self.assertNotIn("secret-value", path)

	def test_missing_password_falls_back_without_leaking_it(self):
		settings, reason = remote.read_settings(
			{
				"openas2_remote_read": {
					"db_type": "mariadb",
					"host": "db.example",
					"port": 3306,
					"database": "openas2",
					"user": "openas2_ro",
					"password_env": "OPENAS2_REMOTE_READ_PASSWORD",
				}
			},
			{},
		)
		self.assertIsNone(settings)
		self.assertEqual(reason, "password")
		with (
			patch.object(remote, "remote_reads_enabled", return_value=True),
			patch.object(remote, "read_settings", return_value=(None, "password")),
			patch.object(remote, "_warn") as warn,
		):
			self.assertIsNone(remote.list_live_messages())
		message = warn.call_args[0][0]
		self.assertIn("password is not set", message)
		self.assertNotIn("OPENAS2_REMOTE_READ_PASSWORD=", message)

	def test_connection_failure_falls_back_without_secrets(self):
		with (
			patch.object(remote, "remote_reads_enabled", return_value=True),
			patch.object(remote, "read_settings", return_value=({"password": "secret-value"}, None)),
			patch.object(remote, "resolve_scope", return_value=SCOPE),
			patch.object(remote, "connect", side_effect=OSError("secret-value at db.example")),
			patch.object(remote, "_warn") as warn,
		):
			self.assertIsNone(remote.list_live_messages())
		message = warn.call_args[0][0]
		self.assertIn("OSError", message)
		self.assertNotIn("secret-value", message)
		self.assertNotIn("db.example", message)

	def test_status_filter(self):
		result, _connection = self._list(
			[
				_record(id=1, status="ok", state="msg_sent_mdn_received_ok"),
				_record(id=2, status="error", state="msg_send_fail"),
			]
		)
		failed = [row for row in result["rows"] if row["status"] == "Failed"]
		self.assertEqual([row["name"] for row in failed], ["remote:2"])
		with (
			patch.object(remote, "remote_reads_enabled", return_value=True),
			patch.object(remote, "read_settings", return_value=({"password": "secret"}, None)),
			patch.object(remote, "resolve_scope", return_value=SCOPE),
			patch.object(
				remote,
				"connect",
				return_value=FakeConnection(
					[
						_record(id=1, status="cleanup", state="msg_sent_mdn_received_ok"),
						_record(id=2, status="error", state="msg_send_fail"),
					]
				),
			),
		):
			failed_only = remote.list_live_messages(status="Failed", limit=10)
		self.assertEqual([row["name"] for row in failed_only["rows"]], ["remote:2"])

	def test_remote_details_and_frappe_name_stays_on_frappe(self):
		connection = FakeConnection([_record()])
		with (
			patch.object(remote, "remote_reads_enabled", return_value=True),
			patch.object(remote, "read_settings", return_value=({"password": "secret"}, None)),
			patch.object(remote, "resolve_scope", return_value=SCOPE),
			patch.object(remote, "connect", return_value=connection),
			patch.object(mon, "_attach_known_edi", return_value=None),
		):
			detail = mon.get_message_details.__wrapped__("remote:15")
		self.assertEqual(detail["name"], "remote:15")
		self.assertTrue(detail["read_only"])
		self.assertIn("SET SESSION TRANSACTION READ ONLY", connection.statements[0][0])

		with patch.object(remote, "connect") as connect:
			self.assertIsNone(remote.remote_message_details("MSG-0001"))
			connect.assert_not_called()

	def test_get_messages_does_not_substitute_frappe_logs(self):
		with (
			patch.object(remote, "list_live_messages", return_value=None),
			patch.object(mon.frappe, "get_all") as get_all,
		):
			result = mon.get_messages.__wrapped__()
		get_all.assert_not_called()
		self.assertFalse(result["ok"])
		self.assertEqual(result["rows"], [])
		self.assertEqual(result["error"], remote.REMOTE_READ_ERROR)

	def test_status_and_edi_filters_are_applied_in_sql(self):
		connection = FakeConnection(
			[
				_record(id=1, status="ok", state="msg_sent_mdn_received_ok", file_name="LOAD_204.edi"),
				_record(id=2, status="error", state="msg_send_fail", file_name="LOAD_990.edi"),
				_record(id=3, status="cleanup", state="msg_sent_mdn_received_ok", file_name="OLD_204.edi"),
			]
		)
		with (
			patch.object(remote, "remote_reads_enabled", return_value=True),
			patch.object(remote, "read_settings", return_value=({"password": "secret"}, None)),
			patch.object(remote, "resolve_scope", return_value=SCOPE),
			patch.object(remote, "connect", return_value=connection),
		):
			result = remote.list_live_messages(status="MDN Received", transaction_type="204", limit=10)
		sql, params = connection.statements[-1]
		self.assertIn("REGEXP", sql)
		self.assertIn("%mdn%", params)
		self.assertIn("(^|[_.-])204([_.-]|$)", params)
		self.assertIn("SHIPPER_AS2ID", params)
		self.assertNotIn("SHIPPER_AS2ID", sql)
		self.assertEqual([row["name"] for row in result["rows"]], ["remote:1", "remote:3"])
		self.assertTrue(all(row["status"] != "Failed" for row in result["rows"]))

	def test_list_query_applies_partner_and_search_in_sql(self):
		sql, params = remote.build_list_query(
			as2_ids=["SHIPPER_AS2ID"],
			partner_ids=["BROKER_AS2ID"],
			search="LOAD",
			limit=5,
		)
		self.assertIn("sender_id IN", sql)
		self.assertIn("file_name", sql)
		self.assertIn("BROKER_AS2ID", params)
		self.assertIn("%LOAD%", params)

	def test_distinct_values_from_monitoring_rows(self):
		records = [
			_record(file_name="LOAD_204.edi"),
			_record(
				id=16,
				status="error",
				state="msg_send_fail",
				file_name="ACK_990.edi",
			),
		]
		distinct = remote._distinct_values_from_monitoring_rows(records, SCOPE)
		self.assertEqual(distinct["partners"], ["Broker"])
		self.assertIn("Success", distinct["statuses"])
		self.assertIn("Failed", distinct["statuses"])
		codes = {item["code"] for item in distinct["transaction_types"]}
		self.assertEqual(codes, {"204", "990"})

	def test_monitoring_filter_options_uses_distinct_and_exists_probes(self):
		class _FilterOptionsConnection(FakeConnection):
			def cursor(self):
				conn = self

				class _Cursor(FakeCursor):
					def fetchall(self):
						sql = conn.statements[-1][0]
						if "MIN(id)" in sql:
							return [{"lo": 1, "hi": 1000}]
						if "sender_id, receiver_id" in sql:
							return [
								{
									"sender_id": "SHIPPER_AS2ID",
									"receiver_id": "BROKER_AS2ID",
									"file_name": "LOAD054_204.edi",
									"status": "ok",
									"state": "msg_sent_mdn_received_ok",
								}
							]
						return []

				return _Cursor(self)

		connection = _FilterOptionsConnection([])
		with (
			patch.object(remote, "remote_reads_enabled", return_value=True),
			patch.object(remote, "read_settings", return_value=({"password": "secret"}, None)),
			patch.object(remote, "resolve_scope", return_value=SCOPE),
			patch.object(remote, "connect", return_value=connection),
			patch.object(remote, "_card_cache_get", return_value=None),
			patch.object(remote, "_card_cache_set"),
		):
			result = remote.monitoring_filter_options()
		joined = " ".join(sql for sql, _params in connection.statements)
		self.assertIn("sender_id, receiver_id, file_name", joined)
		self.assertNotIn("msg_data", joined)
		self.assertTrue(result["ok"])
		self.assertEqual(result["partners"], ["Broker"])
		self.assertIn("Success", result["statuses"])
		self.assertEqual(
			{row["code"] for row in result["transaction_types"]},
			{"204"},
		)

	def test_partner_ids_for_filter_matches_display_labels(self):
		self.assertEqual(
			remote._partner_ids_for_filter("Broker", SCOPE["partners_by_as2"]),
			["BROKER_AS2ID"],
		)
		self.assertEqual(
			remote._partner_ids_for_filter("BROKER_AS2ID", SCOPE["partners_by_as2"]),
			["BROKER_AS2ID"],
		)
		self.assertEqual(remote._partner_ids_for_filter("VENDOR_XYZ", {}), ["VENDOR_XYZ"])

	def test_get_monitoring_filter_options_whitelist(self):
		payload = {
			"ok": True,
			"partners": ["Broker"],
			"statuses": ["Success"],
			"transaction_types": [{"code": "204", "label": "204 – Load Tender"}],
		}
		with patch.object(
			remote, "monitoring_filter_options", return_value=payload
		) as load:
			out = mon.get_monitoring_filter_options()
		load.assert_called_once()
		self.assertEqual(out, payload)

	def test_partner_labels_deduplicate_by_name(self):
		labels = remote._partner_labels_from_remote_ids(
			["BROKER_AS2ID", "BROKER_AS2ID"],
			{"BROKER_AS2ID": "Broker"},
			local_ids={"SHIPPER_AS2ID"},
		)
		self.assertEqual(labels, ["Broker"])

	def test_detail_query_enforces_instance_access(self):
		connection = FakeConnection([_record()])
		with (
			patch.object(remote, "remote_reads_enabled", return_value=True),
			patch.object(remote, "read_settings", return_value=({"password": "secret"}, None)),
			patch.object(remote, "resolve_scope", return_value=SCOPE),
			patch.object(remote, "connect", return_value=connection),
		):
			detail = remote.remote_message_details("remote:15")
		sql, params = connection.statements[-1]
		self.assertIn("id = %s", sql)
		self.assertIn("sender_id IN (%s)", sql)
		self.assertIn(15, params)
		self.assertIn("SHIPPER_AS2ID", params)
		self.assertEqual(detail["instance"], "Shipper OpenAS20")
		self.assertNotIn("msg_data", sql)

	def test_dashboard_keeps_the_remote_message_id(self):
		source = Path(remote.__file__).read_text(encoding="utf-8")
		self.assertNotIn("_prefer_frappe_names", source)
		self.assertNotIn("OpenAS2 Message Log", source.split("def dashboard_activity", 1)[1])

	def test_dashboard_opens_live_message_in_monitoring_drawer(self):
		page_root = Path(__file__).resolve().parents[1] / "openas2_manager" / "page"
		dashboard = (page_root / "openas2_dashboard" / "openas2_dashboard.js").read_text(encoding="utf-8")
		messages = (page_root / "openas2_messages" / "openas2_messages.js").read_text(encoding="utf-8")
		remote_branch, _frappe_branch = dashboard.split('indexOf("remote:")', 1)[1].split(
			"openas2-message-log", 1
		)
		self.assertIn("data-remote-message", remote_branch)
		self.assertNotIn("openas2-message-log", remote_branch)
		self.assertIn("oa2_open_message", dashboard)
		self.assertIn("oa2_open_message", messages)
		self.assertIn("show_message_page(openMessage)", messages)
		self.assertIn("/app/openas2-message-log/", dashboard)

	def test_monitoring_list_stays_bounded_during_background_refresh(self):
		page = (
			Path(__file__).resolve().parents[1]
			/ "openas2_manager"
			/ "page"
			/ "openas2_messages"
			/ "openas2_messages.js"
		).read_text(encoding="utf-8")
		self.assertIn("message_page_size = 100", page)
		self.assertNotIn("limit: 2000", page)
		self.assertIn("load_rows({ background: true })", page)
		self.assertIn("if (!this._rows_shown)", page)
		self.assertNotIn("sync_live_activity", page)
		self.assertNotIn("sync_files()", page)
		self.assertIn("kpis_only: 1", page)
		self.assertIn("get_monitoring_filter_options", page)
		self.assertIn("load_monitoring_filter_options", page)
		self.assertNotIn("frappe.client.get_list", page)
		self.assertNotIn('option value="204">204', page)
		self.assertNotIn("this.pull_live();", page.split("start_live_updates()", 1)[1].split("pull_live()", 1)[0])
		monitoring = (Path(__file__).resolve().parents[1] / "openas2" / "monitoring.py").read_text(encoding="utf-8")
		self.assertIn("skip_remote_activity", monitoring)
		self.assertIn("activity_only", monitoring)

	def test_blank_transaction_type_displays_as_unknown(self):
		page = (
			Path(__file__).resolve().parents[1]
			/ "openas2_manager"
			/ "page"
			/ "openas2_messages"
			/ "openas2_messages.js"
		).read_text(encoding="utf-8")
		self.assertNotIn('transaction_type || "—"', page)
		self.assertGreaterEqual(page.count('transaction_type || __("Unknown")'), 3)

	def test_get_messages_uses_live_rows(self):
		live = {"rows": [{"name": "remote:3", "status": "Processed"}], "count": 1}
		with patch.object(remote, "list_live_messages", return_value=live):
			result = mon.get_messages.__wrapped__(status="Processed")
		self.assertEqual(result, live)

	def test_read_timeout_covers_the_monitoring_page_size(self):
		with patch("pymysql.connect") as connect:
			remote.connect(
				{
					"host": "db.example",
					"port": 3306,
					"user": "reader",
					"password": "secret",
					"database": "openas2",
				}
			)
		self.assertGreaterEqual(connect.call_args.kwargs["read_timeout"], 60)

	def test_dashboard_does_not_scan_when_create_dt_is_not_indexed(self):
		connection = _QueuedConnection(
			[
				[{"Column_name": "id"}, {"Column_name": "msg_id"}],
				[_record(id=4695698)],
			]
		)
		with (
			patch.object(remote, "remote_reads_enabled", return_value=True),
			patch.object(remote, "read_settings", return_value=({"password": "secret"}, None)),
			patch.object(remote, "resolve_scope", return_value=SCOPE),
			patch.object(remote, "connect", return_value=connection),
		):
			result = remote.dashboard_activity()
		joined = "\n".join(sql for sql, _params in connection.statements)
		self.assertNotIn("COUNT(*)", joined)
		self.assertIn("SHOW INDEX", joined)
		self.assertIn("LIMIT", joined)
		self.assertIsNone(result["counts"])
		self.assertEqual(result["recent"][0]["name"], "remote:4695698")
		self.assertTrue(connection.closed)

	def test_dashboard_counts_when_create_dt_is_indexed(self):
		connection = _QueuedConnection(
			[
				[{"Column_name": "create_dt"}],
				[{"messages_today": 4, "inbound": 3, "outbound": 1, "successful": 4, "processed": 4, "failed": 0, "pending_mdn": 0}],
				[_record(id=9)],
			]
		)
		with (
			patch.object(remote, "remote_reads_enabled", return_value=True),
			patch.object(remote, "read_settings", return_value=({"password": "secret"}, None)),
			patch.object(remote, "resolve_scope", return_value=SCOPE),
			patch.object(remote, "connect", return_value=connection),
			patch("frappe.utils.getdate", return_value=datetime(2026, 10, 15).date()),
			patch("frappe.utils.now_datetime", return_value=datetime(2026, 10, 15, 12, 0, 0)),
		):
			result = remote.dashboard_activity()
		joined = "\n".join(sql for sql, _params in connection.statements)
		self.assertIn("COUNT(*)", joined)
		self.assertEqual(result["counts"]["messages_today"], 4)
		self.assertEqual(result["recent"][0]["name"], "remote:9")
		self.assertEqual(result["recent"][0]["transaction_type"], "204")
		self.assertEqual(result["recent"][0]["transaction_type_label"], "204 \u2013 Load Tender")

	def test_dashboard_recent_edi_types_come_from_payload(self):
		"""Home recent messages use ST01, including MIME, and do not guess."""
		import base64

		def st(code):
			return f"ISA*00*~\r\nST*{code}*0001~\r\nSE*2*0001~"

		encoded = base64.b64encode(b"ISA*00*~\nST*990*0001~\n").decode()
		mime_990 = (
			"Content-Type: application/EDI-X12\n"
			"Content-Transfer-Encoding: base64\n"
			"\n" + encoded
		)
		multipart_214 = (
			"------=_Part_9\n"
			"Content-Type: application/edi-x12\n"
			"Content-Transfer-Encoding: binary\n"
			"Content-Disposition: attachment; filename=204_load.txt\n"
			"\n"
			"ISA*00*~\nST*214*0001~\n"
		)
		cases = [
			(31, None, st("204"), "204", "204 \u2013 Load Tender"),
			(32, "", mime_990, "990", "990 \u2013 Response"),
			(33, "notes.txt", multipart_214, "214", "214 \u2013 Status"),
			(34, "invoice.edi", st("210"), "210", "210 \u2013 Freight Invoice"),
			(35, "freight.dat", st("810"), "810", "810 \u2013 Invoice"),
			(36, "remit.dat", st("820"), "820", "820 \u2013 Payment"),
			(37, "ack.dat", st("997"), "997", "997 \u2013 Functional Acknowledgment"),
			(38, "empty.dat", None, "Unknown", "Unknown"),
			(39, "bad.dat", "ISA*00*~\r\nST*999*0001~\r\n", "Unknown", "Unknown"),
			(40, "other.dat", "ISA*00*~\r\nST*850*0001~\r\n", "Unknown", "Unknown"),
			(43, "garbage.dat", "this is not edi", "Unknown", "Unknown"),
			(42, "plain.edi", st("990"), "990", "990 \u2013 Response"),
			(41, "LOAD_214.edi", st("204"), "214", "214 \u2013 Status"),
		]
		records = []
		prefixes = []
		for row_id, file_name, payload, _code, _label in cases:
			message_id = "<204-do-not-guess@openas2>" if row_id == 42 else "<abc@openas2>"
			records.append(_record(id=row_id, file_name=file_name, msg_id=message_id))
			if row_id != 41:
				prefixes.append({"id": row_id, "msg_data": payload})
		records.append(
			_record(id=99, sender_id="OTHER", receiver_id="NOPE", file_name="hidden_204.edi")
		)
		connection = _QueuedConnection(
			[
				[{"Column_name": "id"}],
				records,
				prefixes,
			]
		)
		with (
			patch.object(remote, "remote_reads_enabled", return_value=True),
			patch.object(remote, "read_settings", return_value=({"password": "secret"}, None)),
			patch.object(remote, "resolve_scope", return_value=SCOPE),
			patch.object(remote, "connect", return_value=connection),
			patch.object(remote, "_fetch_edi_type_rows", return_value=[]),
			patch.object(remote.frappe, "get_all", side_effect=AssertionError("local message log")),
		):
			result = remote.dashboard_activity()

		by_name = {row["name"]: row for row in result["recent"]}
		self.assertNotIn("remote:99", by_name)
		for row_id, _file_name, _payload, code, label in cases:
			row = by_name[f"remote:{row_id}"]
			self.assertEqual(row["transaction_type"], code, row_id)
			self.assertEqual(row["transaction_type_label"], label, row_id)
		self.assertNotEqual(by_name["remote:42"]["transaction_type"], "204")

		statements = [(sql, params) for sql, params in connection.statements]
		list_sql, list_params = next(item for item in statements if "ORDER BY id DESC" in item[0])
		prefix_sql, prefix_params = next(item for item in statements if "SUBSTRING(msg_data, 1, %s)" in item[0])
		self.assertNotIn("msg_data", list_sql)
		self.assertNotIn("msg_headers", list_sql)
		self.assertNotIn("mdn_response", list_sql)
		self.assertEqual(list_params[-1], remote.RECENT_ROW_LIMIT)
		self.assertEqual(prefix_params[0], remote.PAYLOAD_PREVIEW_CHARS)
		self.assertLess(remote.PAYLOAD_PREVIEW_CHARS, remote.PAYLOAD_FULL_CHARS)
		self.assertNotIn(41, prefix_params)
		self.assertNotIn(99, prefix_params)
		self.assertIn(31, prefix_params)
		self.assertIn("sender_id IN (%s)", prefix_sql)
		self.assertIn("SHIPPER_AS2ID", prefix_params)
		self.assertNotIn("SHIPPER_AS2ID", prefix_sql)
		self.assertNotIn("msg_headers", prefix_sql)
		self.assertNotIn("mdn_response", prefix_sql)
		self.assertEqual(sum("SUBSTRING(msg_data, 1, %s)" in sql for sql, _params in statements), 1)
		for code in ("", None, "Unknown", "999", "850", "2040"):
			self.assertEqual(remote.format_transaction_type_label(code), "Unknown")

		page = (
			Path(__file__).resolve().parents[1]
			/ "openas2_manager"
			/ "page"
			/ "openas2_dashboard"
			/ "openas2_dashboard.js"
		).read_text(encoding="utf-8")
		render = page.split("render_messages(rows, errorText)")[1].split("refresh_transactions()")[0]
		self.assertIn("transaction_type_label", render)
		self.assertIn('colspan="7"', render)
		self.assertNotIn('m.transaction_type || "—"', render)

	def test_edi_transaction_totals_are_not_invented_from_messages(self):
		cards = remote.unavailable_edi_counts()
		self.assertFalse(cards["edi_counts_available"])
		self.assertIsNone(cards["transactions_total"])
		self.assertIn("msg_metadata", cards["edi_counts_limitation"])
		self.assertIn("business transaction", cards["edi_counts_limitation"])
		self.assertEqual([card["code"] for card in cards["kpis"]], ["204", "990", "210", "214"])
		for card in cards["kpis"]:
			self.assertFalse(card["available"])
			self.assertIsNone(card["count"])
			self.assertIsNone(card["last_7"])
			self.assertIsNone(card["change_pct"])
		body = Path(mon.__file__).read_text(encoding="utf-8").split("def get_dashboard_summary", 1)[1]
		body = body.split("def _attach_known_edi", 1)[0]
		self.assertNotIn("OpenAS2 EDI Document", body)
		self.assertNotIn("OpenAS2 Message Log", body)
		page = (
			Path(__file__).resolve().parents[1]
			/ "openas2_manager"
			/ "page"
			/ "openas2_dashboard"
			/ "openas2_dashboard.js"
		).read_text(encoding="utf-8")
		self.assertIn("countMissing", page)
		self.assertIn("edi_counts_available", page)
		self.assertNotIn("Not stored in msg_metadata", page)

	def test_edi_card_counts_bind_only_the_number(self):
		now = datetime(2026, 10, 22, 15, 0, 0)
		last_7, prev_7 = remote._card_windows(now)
		self.assertEqual(last_7, datetime(2026, 10, 15, 0, 0, 0))
		self.assertEqual(prev_7, datetime(2026, 10, 8, 0, 0, 0))
		sql, params = remote.build_edi_card_count_query(
			as2_ids=["SHIPPER_AS2ID"],
			last_7_start=last_7,
			prev_7_start=prev_7,
		)
		self.assertEqual(sql.count("REGEXP_SUBSTR"), 3)
		self.assertNotIn("LIMIT", sql.upper())
		self.assertNotIn(" JOIN ", sql.upper())
		self.assertNotIn("msg_headers", sql)
		self.assertNotIn("mdn_response", sql)
		self.assertEqual(sql.count("msg_data"), 1)
		self.assertIn(f"SUBSTRING(IFNULL(msg_data, ''), 1, {remote.PAYLOAD_PREVIEW_CHARS})", sql)
		self.assertIn("sender_id IN (%s)", sql)
		self.assertIn("SHIPPER_AS2ID", params)
		self.assertNotIn("SHIPPER_AS2ID", sql)
		self.assertEqual(sql.count("%s"), len(params))
		self.assertEqual(params.count(last_7), 8)
		self.assertEqual(params.count(prev_7), 4)
		self.assertIn(" AS s204", sql)
		self.assertIn(" AS f204", sql)
		self.assertIn("LOWER(status)", sql)
		self.assertIn("state", sql)
		self.assertIn("%error%", params)
		self.assertNotIn("%error%", sql)
		self.assertNotIn("cannot be calculated", remote.EDI_TRANSACTION_COUNT_LIMITATION)
		pattern = remote._filename_type_pattern()
		self.assertEqual(params.count(pattern), 2)
		self.assertIn("810", pattern)
		self.assertIn("820", pattern)
		self.assertIn("ST", remote._payload_type_pattern())
		for code in ("204", "990", "210", "214"):
			self.assertIn(f"%%{code}%%", sql)
			self.assertEqual(remote.extract_transaction_type(f"LOAD_{code}.edi"), code)
		self.assertEqual(remote.detected_card_type("LOAD_204.edi", "ST*990*0001~"), "204")
		self.assertEqual(remote.detected_card_type("hub_810_204.edi", "ST*204*0001~"), "")
		self.assertEqual(remote.detected_card_type("", "ISA*00*~\nST*210*0001~\n"), "210")
		self.assertEqual(remote.detected_card_type(None, "ST*2040*0001~"), "")
		mime = (
			"Content-Type: application/edi-x12\n"
			"Content-Transfer-Encoding: binary\n"
			"\n"
			"ISA*00*~\nST*990*0001~\n"
		)
		self.assertEqual(remote.detected_card_type("", mime), "990")
		import base64
		encoded = base64.b64encode(b"ISA*00*~\nST*214*0001~\n").decode()
		wrapped = "Content-Type: application/EDI-X12\nContent-Transfer-Encoding: base64\n\n" + encoded
		self.assertEqual(remote.detected_card_type("notes.txt", wrapped), "214")
		self.assertIsNone(remote.card_change_pct(0, 10))
		self.assertIsNone(remote.card_change_pct(10, 0))
		self.assertIsNone(remote.card_change_pct(0, 0))
		self.assertEqual(remote.card_change_pct(15, 10), 50.0)
		self.assertEqual(remote.card_change_pct(5, 10), -50.0)
		bounded, bounded_params = remote.build_edi_card_count_query(
			as2_ids=["SHIPPER_AS2ID"],
			last_7_start=last_7,
			prev_7_start=prev_7,
			id_from=10,
			id_to=20,
		)
		self.assertEqual(bounded.count("id >= %s"), 1)
		self.assertEqual(bounded.count("id < %s"), 1)
		self.assertEqual(bounded_params[-2:], [10, 20])
		self.assertIn("SHIPPER_AS2ID", bounded_params)
		self.assertNotIn("SHIPPER_AS2ID", bounded)
		self.assertEqual(bounded.count("msg_data"), 1)
		ranges = remote.card_id_ranges(1, 250, 100)
		covered = [item for start, stop in ranges for item in range(start, stop)]
		self.assertEqual(ranges, [(1, 101), (101, 201), (201, 251)])
		self.assertEqual(covered, list(range(1, 251)))
		self.assertEqual(len(covered), len(set(covered)))
		merged = remote.merge_card_count_rows(
			[
				{"n204": 2, "d204": 1, "p204": 4, "s204": 1, "f204": 1,
				 "n990": 0, "d990": 0, "p990": 0, "s990": 0, "f990": 0,
				 "n210": 0, "d210": 0, "p210": 0, "s210": 0, "f210": 0,
				 "n214": 1, "d214": 0, "p214": 0, "s214": 0, "f214": 1},
				{"n204": 5, "d204": 0, "p204": 1, "s204": 4, "f204": 0,
				 "n990": 3, "d990": 0, "p990": 0, "s990": 3, "f990": 0,
				 "n210": 0, "d210": 0, "p210": 0, "s210": 0, "f210": 0,
				 "n214": 1, "d214": 1, "p214": 1, "s214": 1, "f214": 0},
			]
		)
		self.assertEqual(merged["counts"]["204"], 7)
		self.assertEqual(merged["last_7"]["204"], 1)
		self.assertEqual(merged["previous_7"]["204"], 5)
		self.assertEqual(merged["counts"]["214"], 2)
		self.assertEqual(merged["status_by_type"]["204"]["success"], 5)
		self.assertEqual(merged["status_by_type"]["204"]["failure"], 1)
		self.assertEqual(merged["status_by_type"]["204"]["in_progress"], 1)
		self.assertEqual(
			merged["status_by_type"]["204"]["success"]
			+ merged["status_by_type"]["204"]["in_progress"]
			+ merged["status_by_type"]["204"]["failure"],
			merged["counts"]["204"],
		)
		self.assertEqual(merged["status_by_type"]["990"]["success"], 3)
		self.assertEqual(merged["status_by_type"]["990"]["failure"], 0)
		listed, _listed_params = remote.build_list_query(
			as2_ids=["SHIPPER_AS2ID"], transaction_type="204", limit=100
		)
		self.assertIn("LIMIT %s", listed)

		cards = remote.unavailable_edi_counts()["kpis"]
		connection = FakeConnection(
			[
				{
					"n204": 831,
					"d204": 10,
					"p204": 20,
					"n990": 500,
					"d990": 0,
					"p990": 4,
					"n210": 0,
					"d210": 0,
					"p210": 0,
					"n214": 797,
					"d214": 3,
					"p214": 3,
				}
			]
		)
		with (
			patch.object(remote, "remote_reads_enabled", return_value=True),
			patch.object(remote, "read_settings", return_value=({"password": "secret-value"}, None)),
			patch.object(remote, "resolve_scope", return_value=SCOPE),
			patch.object(remote, "connect", return_value=connection),
			patch.object(remote, "list_live_messages", side_effect=AssertionError("page count")),
		):
			bound = remote.bind_edi_card_counts(cards, now=now)
		by_code = {card["code"]: card for card in bound}
		self.assertEqual([card["code"] for card in bound], ["204", "990", "210", "214"])
		self.assertEqual(
			[card["label"] for card in bound],
			["Load Tender", "Ack", "Invoice", "Status"],
		)
		self.assertNotIn("BOL", [card["label"] for card in bound])
		self.assertEqual(by_code["204"]["count"], 831)
		self.assertEqual(by_code["204"]["last_7"], 10)
		self.assertEqual(by_code["204"]["change_pct"], -50.0)
		self.assertEqual(by_code["990"]["count"], 500)
		self.assertEqual(by_code["990"]["last_7"], 0)
		self.assertIsNone(by_code["990"]["change_pct"])
		self.assertEqual(by_code["210"]["count"], 0)
		self.assertIsNone(by_code["210"]["change_pct"])
		self.assertEqual(by_code["214"]["count"], 797)
		self.assertEqual(by_code["214"]["change_pct"], 0.0)
		self.assertNotEqual(by_code["204"]["count"], 100)
		for card in bound:
			self.assertTrue(card["available"])
			self.assertEqual(card["summary"], "")
			self.assertNotEqual(card["summary"], "Not stored in msg_metadata")
		count_sql = [text for text, _params in connection.statements if "n204" in text][-1]
		self.assertNotIn("LIMIT", count_sql.upper())
		self.assertNotIn(" JOIN ", count_sql.upper())
		self.assertEqual(count_sql.count("msg_data"), 1)

		with (
			patch.object(remote, "remote_reads_enabled", return_value=True),
			patch.object(remote, "read_settings", return_value=({"password": "secret-value"}, None)),
			patch.object(remote, "resolve_scope", return_value=SCOPE),
			patch.object(remote, "connect", return_value=FakeConnection([{}])),
		):
			empty = remote.bind_edi_card_counts(remote.unavailable_edi_counts()["kpis"], now=now)
		self.assertEqual([card["count"] for card in empty], [0, 0, 0, 0])
		self.assertEqual(len(empty), 4)
		for card in empty:
			self.assertTrue(card["available"])
			self.assertEqual(card["count"], 0)
			self.assertIsNone(card["change_pct"])

		import pymysql

		failed_cards = remote.unavailable_edi_counts()["kpis"]
		with (
			patch.object(remote, "remote_reads_enabled", return_value=True),
			patch.object(remote, "read_settings", return_value=({"password": "secret-value"}, None)),
			patch.object(remote, "resolve_scope", return_value=SCOPE),
			patch.object(
				remote,
				"connect",
				side_effect=pymysql.err.OperationalError(
					2013,
					"Lost connection to MySQL server during query (timed out) secret-value",
				),
			),
			patch.object(remote, "_warn") as warn,
		):
			failed = remote.bind_edi_card_counts(failed_cards, now=now)
		self.assertEqual(len(failed), 4)
		for card in failed:
			self.assertIsNone(card["count"])
			self.assertFalse(card["available"])
			self.assertIsNone(card["last_7"])
			self.assertIsNone(card["change_pct"])
		logged = warn.call_args[0][0]
		self.assertIn("2013", logged)
		self.assertIn("timed out", logged)
		self.assertNotIn("secret-value", logged)

		with (
			patch.object(remote, "remote_reads_enabled", return_value=True),
			patch.object(remote, "read_settings", return_value=({"password": "secret-value"}, None)),
			patch.object(remote, "resolve_scope", return_value=None),
			patch.object(remote, "connect", side_effect=AssertionError("no access still queried")),
		):
			blocked = remote.bind_edi_card_counts(remote.unavailable_edi_counts()["kpis"], now=now)
		self.assertEqual([card["count"] for card in blocked], [0, 0, 0, 0])

		body = Path(mon.__file__).read_text(encoding="utf-8").split("def get_dashboard_summary", 1)[1]
		body = body.split("def _attach_known_edi", 1)[0]
		self.assertIn("bind_edi_card_counts", body)
		self.assertIn("attach_dashboard_edi_panels", body)
		self.assertNotIn("bind_edi_status_chart", body)
		self.assertNotIn("OpenAS2 EDI Document", body)
		self.assertNotIn("OpenAS2 Message Log", body)
		page = (
			Path(__file__).resolve().parents[1]
			/ "openas2_manager"
			/ "page"
			/ "openas2_dashboard"
			/ "openas2_dashboard.js"
		).read_text(encoding="utf-8")
		render = page.split("render_kpis(kpis)")[1].split("render_action_cards")[0]
		self.assertIn("countMissing", render)
		self.assertIn("oa2-kpi-value", render)
		self.assertIn("in the last 7 days", render)
		self.assertIn("change_badge(null)", render)
		self.assertNotIn("Not stored in msg_metadata", render)
		self.assertEqual(render.count("<article"), 1)

	def test_dashboard_edi_cards_use_cached_remote_counts(self):
		window = (datetime(2026, 10, 15, 0, 0, 0), datetime(2026, 10, 8, 0, 0, 0))
		fresh = {
			"ok": True,
			"counts": {"204": 3, "990": 0, "210": 1, "214": 4},
			"last_7": {"204": 2, "990": 0, "210": 0, "214": 1},
			"previous_7": {"204": 1, "990": 0, "210": 0, "214": 1},
			"computed_at": time.time(),
			"status_by_type": remote._status_by_type(
				{"204": 3, "990": 0, "210": 1, "214": 4},
				{"204": 2, "990": 0, "210": 0, "214": 1},
				{"204": 0, "990": 0, "210": 0, "214": 0},
			),
		}
		self.assertIsNone(remote.valid_card_cache({"ok": False}))
		self.assertIsNone(remote.valid_card_cache({"ok": True, "counts": {"204": True}}))
		with (
			patch.object(remote, "remote_reads_enabled", return_value=True),
			patch.object(remote, "read_settings", return_value=({"password": "secret-value"}, None)),
			patch.object(remote, "resolve_scope", return_value=SCOPE),
			patch.object(remote, "_card_windows", return_value=window),
			patch.object(remote, "_card_cache_get", return_value=fresh),
			patch.object(remote, "count_edi_cards_chunked", side_effect=AssertionError("page scanned the remote table")),
		):
			bound = remote.bind_edi_card_counts(remote.unavailable_edi_counts()["kpis"])
		by_code = {card["code"]: card for card in bound}
		self.assertEqual(len(bound), 4)
		self.assertEqual(by_code["204"]["count"], 3)
		self.assertEqual(by_code["204"]["change_pct"], 100.0)
		self.assertEqual(by_code["214"]["change_pct"], 0.0)
		self.assertIsNone(by_code["990"]["change_pct"])
		self.assertTrue(all(card["available"] for card in bound))

		stale = dict(fresh)
		stale["computed_at"] = time.time() - remote.CARD_CACHE_TTL_SECONDS - 5
		with (
			patch.object(remote, "remote_reads_enabled", return_value=True),
			patch.object(remote, "read_settings", return_value=({"password": "secret-value"}, None)),
			patch.object(remote, "resolve_scope", return_value=SCOPE),
			patch.object(remote, "_card_windows", return_value=window),
			patch.object(remote, "_card_cache_get", return_value=stale),
			patch.object(remote, "count_edi_cards_chunked", side_effect=AssertionError("page scanned the remote table")),
		):
			aged = remote.bind_edi_card_counts(remote.unavailable_edi_counts()["kpis"])
		self.assertEqual([card["count"] for card in aged], [3, 0, 1, 4])

		with (
			patch.object(remote, "remote_reads_enabled", return_value=True),
			patch.object(remote, "read_settings", return_value=({"password": "secret-value"}, None)),
			patch.object(remote, "resolve_scope", return_value=SCOPE),
			patch.object(remote, "_card_windows", return_value=window),
			patch.object(remote, "_card_cache_get", return_value=None),
			patch.object(remote, "_acquire_card_lock", return_value=True),
			patch.object(remote, "_release_card_lock"),
			patch.object(remote, "count_edi_cards_chunked", return_value=remote._failed_card_counts()),
		):
			missing = remote.bind_edi_card_counts(remote.unavailable_edi_counts()["kpis"])
		self.assertEqual(len(missing), 4)
		self.assertEqual([card["count"] for card in missing], [None, None, None, None])
		self.assertTrue(all(card["available"] is False for card in missing))

	def test_edi_status_chart_uses_the_same_message_groups(self):
		now = datetime(2026, 10, 22, 15, 0, 0)
		row = {
			"n204": 8, "d204": 0, "p204": 0, "s204": 6, "f204": 1,
			"n990": 4, "d990": 0, "p990": 0, "s990": 0, "f990": 4,
			"n210": 0, "d210": 0, "p210": 0, "s210": 0, "f210": 0,
			"n214": 3, "d214": 0, "p214": 0, "s214": 1, "f214": 0,
		}
		connection = FakeConnection([row])
		summary = remote.unavailable_edi_counts()
		with (
			patch.object(remote, "remote_reads_enabled", return_value=True),
			patch.object(remote, "read_settings", return_value=({"password": "secret-value"}, None)),
			patch.object(remote, "resolve_scope", return_value=SCOPE),
			patch.object(remote, "connect", return_value=connection),
		):
			remote.bind_edi_status_chart(summary, now=now)
		self.assertTrue(summary["edi_counts_available"])
		self.assertEqual(summary["edi_counts_limitation"], "")
		self.assertEqual(summary["transactions_total"], 15)
		chart = summary["edi_status_by_type"]
		self.assertEqual(
			[chart[code]["total"] for code in ("204", "990", "210", "214")],
			[8, 4, 0, 3],
		)
		self.assertEqual(chart["204"]["success"], 6)
		self.assertEqual(chart["204"]["failure"], 1)
		self.assertEqual(chart["204"]["in_progress"], 1)
		self.assertEqual(chart["990"]["success"], 0)
		self.assertEqual(chart["990"]["failure"], 4)
		self.assertEqual(chart["990"]["in_progress"], 0)
		self.assertEqual(chart["214"]["success"], 1)
		self.assertEqual(chart["214"]["failure"], 0)
		self.assertEqual(chart["214"]["in_progress"], 2)
		self.assertNotIn("810", chart)
		self.assertNotIn("997", chart)
		for code in ("204", "990", "210", "214"):
			item = chart[code]
			self.assertEqual(item["success"] + item["in_progress"] + item["failure"], item["total"])
		count_sql = connection.statements[-1][0]
		self.assertEqual(count_sql.count(" AS s204"), 1)
		self.assertEqual(count_sql.count(" AS f204"), 1)
		self.assertNotIn("LIMIT", count_sql.upper())
		self.assertNotIn(" JOIN ", count_sql.upper())
		self.assertEqual(count_sql.count("msg_data"), 1)

		failed = remote.unavailable_edi_counts()
		import pymysql

		with (
			patch.object(remote, "remote_reads_enabled", return_value=True),
			patch.object(remote, "read_settings", return_value=({"password": "secret-value"}, None)),
			patch.object(remote, "resolve_scope", return_value=SCOPE),
			patch.object(
				remote,
				"connect",
				side_effect=pymysql.err.OperationalError(2013, "Lost connection secret-value"),
			),
		):
			remote.bind_edi_status_chart(failed, now=now)
		self.assertFalse(failed["edi_counts_available"])
		self.assertIn("business transaction", failed["edi_counts_limitation"])
		self.assertIsNone(failed["edi_status_by_type"]["204"]["success"])

		window = (datetime(2026, 10, 15, 0, 0, 0), datetime(2026, 10, 8, 0, 0, 0))
		counts = {"204": 8, "990": 4, "210": 0, "214": 3}
		cached = {
			"ok": True,
			"counts": counts,
			"last_7": {"204": 0, "990": 0, "210": 0, "214": 0},
			"previous_7": {"204": 0, "990": 0, "210": 0, "214": 0},
			"computed_at": time.time(),
			"status_by_type": remote._status_by_type(
				counts,
				{"204": 6, "990": 0, "210": 0, "214": 1},
				{"204": 1, "990": 4, "210": 0, "214": 0},
			),
		}
		from openas2_manager.openas2 import edi_dashboard_counts as panels

		pending = remote.unavailable_edi_counts()
		with (
			patch.object(panels, "read_panel_cache", return_value=remote._failed_card_counts()),
			patch.object(remote, "count_edi_cards_chunked", side_effect=AssertionError("page scanned the remote table")),
		):
			aggregated = panels.read_panel_cache()
			remote.bind_edi_status_chart(pending, counts=aggregated)
			cards = remote.bind_edi_card_counts(pending["kpis"], counts=aggregated)
		self.assertFalse(pending["edi_counts_available"])
		self.assertIsNone(pending["edi_status_by_type"]["204"]["total"])
		self.assertEqual([card["count"] for card in cards], [None, None, None, None])

		ready = remote.unavailable_edi_counts()
		with patch.object(
			remote, "count_edi_cards_chunked", side_effect=AssertionError("page scanned the remote table")
		):
			remote.bind_edi_status_chart(ready, counts=cached)
			remote.bind_edi_card_counts(ready["kpis"], counts=cached)
		self.assertTrue(ready["edi_counts_available"])
		self.assertEqual(ready["edi_counts_limitation"], "")
		self.assertEqual(ready["transactions_total"], 15)
		self.assertEqual(ready["edi_status_by_type"]["204"]["in_progress"], 1)
		self.assertEqual(ready["kpis"][0]["count"], 8)

		page = (
			Path(__file__).resolve().parents[1]
			/ "openas2_manager"
			/ "page"
			/ "openas2_dashboard"
			/ "openas2_dashboard.js"
		).read_text(encoding="utf-8")
		chart = page.split("apply_edi_transactions(payload)")[1].split("status_tone(status)")[0]
		self.assertIn("Load Tender", chart)
		self.assertIn("Ack", chart)
		self.assertIn("Invoice", chart)
		self.assertIn("Status", chart)
		self.assertIn("Success", chart)
		self.assertIn("In Progress", chart)
		self.assertIn("Failure", chart)
		self.assertIn("edi_counts_available", chart)
		self.assertIn("oa2-txn-legend", chart)
		self.assertIn("oa2-edi-breakdown", page)
		self.assertIn("edi_refresh_in_progress", page)
		self.assertIn("load_edi_transactions", page)
		self.assertIn("get_edi_transactions_counts", page)
		self.assertIn("maybe_retry_edi_chart", page)

	def test_home_dashboard_splits_kpis_and_activity_requests(self):
		page = (
			Path(__file__).resolve().parents[1]
			/ "openas2_manager"
			/ "page"
			/ "openas2_dashboard"
			/ "openas2_dashboard.js"
		).read_text(encoding="utf-8")
		self.assertIn("load_kpis()", page)
		self.assertIn("load_edi_transactions()", page)
		self.assertIn("load_activity()", page)
		self.assertIn("kpis_only: 1", page)
		self.assertIn("activity_only: 1", page)
		self.assertIn("stop_polling()", page)
		self.assertIn("start_polling()", page)
		self.assertIn("maybe_retry_kpis", page)
		self.assertNotIn("refresh_transactions()", page)

	def test_home_kpi_cards_preserve_last_valid_counts_on_stale_response(self):
		page = (
			Path(__file__).resolve().parents[1]
			/ "openas2_manager"
			/ "page"
			/ "openas2_dashboard"
			/ "openas2_dashboard.js"
		).read_text(encoding="utf-8")
		load = page.split("load_kpis() {", 1)[1].split("load_activity()", 1)[0]
		self.assertIn("kpis_for_display", load)
		self.assertIn("render_kpis(displayKpis)", load)
		self.assertNotIn("render_kpis(s.kpis)", load)
		self.assertIn("kpi_count_valid", page)
		self.assertIn("_kpi_by_code", page)
		self.assertIn("ingest_edi_kpi_totals", page)
		body = page.split("kpi_count_valid(count)")[1].split("default_kpi_cards", 1)[0]
		self.assertIn("count !== null", body)
		self.assertIn("count !== undefined", body)
		merge = page.split("kpis_for_display(incoming)")[1].split("set_kpi_notice", 1)[0]
		self.assertIn("this._kpi_by_code[code]", merge)
		self.assertIn("kpi_count_valid(k.count)", merge)

	def test_get_dashboard_summary_activity_only_skips_edi_counts(self):
		body = Path(mon.__file__).read_text(encoding="utf-8").split("def get_dashboard_summary", 1)[1]
		body = body.split("def _attach_known_edi", 1)[0]
		self.assertIn("activity_only", body)
		self.assertIn("skip_edi_counts", body)
		self.assertIn("attach_dashboard_edi_panels", body)
		self.assertNotIn("count_live_messages", body)
		self.assertNotIn("bind_edi_status_chart", body)

	def test_get_edi_transactions_counts_uses_cache_peek(self):
		body = Path(mon.__file__).read_text(encoding="utf-8").split("def get_edi_transactions_counts", 1)[1]
		body = body.split("def get_dashboard_summary", 1)[0]
		self.assertIn("get_edi_home_chart_response", body)
		self.assertNotIn("get_edi_transactions_chart_payload", body)
		self.assertNotIn("dashboard_edi_transactions_counts", body)

	def test_refresh_monitoring_refreshes_edi_cache_without_summary(self):
		body = Path(mon.__file__).read_text(encoding="utf-8").split("def refresh_monitoring", 1)[1]
		body = body.split("def _live_instance_names", 1)[0]
		self.assertIn("refresh_edi_card_counts", body)
		self.assertNotIn("get_dashboard_summary", body)
		self.assertNotIn("count_edi_cards_chunked", body)

	def test_home_kpi_path_uses_cached_card_counts_without_live_scan(self):
		kpis = remote.unavailable_edi_counts()["kpis"]
		cached = {
			"ok": True,
			"counts": {"204": 42, "990": 17, "210": 9, "214": 3},
			"last_7": {"204": 3, "990": 0, "210": 0, "214": 1},
			"previous_7": {"204": 1, "990": 0, "210": 0, "214": 0},
			"computed_at": time.time(),
			"status_by_type": remote._status_by_type(
				{"204": 42, "990": 17, "210": 9, "214": 3},
				{"204": 40, "990": 15, "210": 9, "214": 2},
				{"204": 1, "990": 2, "210": 0, "214": 0},
			),
		}
		with patch.object(remote, "count_live_messages", side_effect=AssertionError("no live scan")):
			remote.bind_edi_card_counts(kpis, counts=cached)
		by_code = {card["code"]: card for card in kpis}
		self.assertEqual(by_code["204"]["count"], 42)
		self.assertEqual(by_code["990"]["count"], 17)
		self.assertTrue(all(card["available"] for card in kpis))

	def test_bind_edi_990_ack_uses_monitoring_count(self):
		kpis = remote.unavailable_edi_counts()["kpis"]
		with patch.object(
			remote,
			"dashboard_edi_990_counts",
			return_value={"ok": True, "count": 17},
		):
			remote.bind_edi_990_ack_kpi(kpis)
		by_code = {card["code"]: card for card in kpis}
		self.assertEqual(by_code["990"]["count"], 17)
		self.assertTrue(by_code["990"]["available"])
		self.assertEqual(by_code["204"]["count"], None)

	def test_bind_edi_210_invoice_uses_monitoring_count(self):
		kpis = remote.unavailable_edi_counts()["kpis"]
		with patch.object(remote, "dashboard_edi_210_counts", return_value={"ok": True, "count": 9}):
			remote.bind_edi_210_invoice_kpi(kpis)
		by_code = {card["code"]: card for card in kpis}
		self.assertEqual(by_code["210"]["count"], 9)
		self.assertTrue(by_code["210"]["available"])

	def test_orphan_card_lock_is_stale_without_heartbeat(self):
		now = time.time()
		payload = {"held": 1, "acquired_at": now - 700, "heartbeat_at": now - 700}
		self.assertTrue(remote._lock_is_stale(payload, now))

	def test_lock_without_cache_becomes_stale_after_idle_window(self):
		now = time.time()
		cache_key = "oa2_edi_card_counts:v2:test:scope"
		payload = {"held": 1, "acquired_at": now - 130, "heartbeat_at": now - 130}
		with patch.object(remote, "_cache_has_display_counts", return_value=False):
			self.assertTrue(remote._lock_is_stale(payload, now, cache_key=cache_key))
		with patch.object(remote, "_cache_has_display_counts", return_value=True):
			self.assertFalse(remote._lock_is_stale(payload, now, cache_key=cache_key))

	def test_peek_edi_kpi_counts_uses_last_good_cache(self):
		now = time.time()
		key = "oa2_edi_card_counts:v2:20260101000000:test"
		stored = {
			"ok": True,
			"counts": {"204": 1, "990": 2, "210": 3, "214": 4},
			"last_7": {"204": 0, "990": 0, "210": 0, "214": 0},
			"previous_7": {"204": 0, "990": 0, "210": 0, "214": 0},
			"computed_at": now,
			"status_by_type": remote._status_by_type(
				{"204": 1, "990": 2, "210": 3, "214": 4},
				{"204": 1, "990": 2, "210": 3, "214": 4},
				{"204": 0, "990": 0, "210": 0, "214": 0},
			),
		}
		with (
			patch.object(remote, "remote_reads_enabled", return_value=True),
			patch.object(remote, "read_settings", return_value=({"password": ""}, None)),
			patch.object(remote, "resolve_scope", return_value={"query_ids": ["A"]}),
			patch.object(remote, "_card_windows", return_value=(datetime(2026, 1, 1), datetime(2025, 12, 25))),
			patch.object(remote, "_card_scope_key", return_value=key),
			patch.object(remote, "_prepare_card_refresh_lock"),
			patch.object(remote, "_card_cache_get", side_effect=lambda k: stored if k == remote._card_last_good_cache_key(key) else None),
		):
			peeked = remote.peek_edi_kpi_counts()
		self.assertTrue(peeked.get("ok"))
		self.assertEqual(peeked["counts"]["204"], 1)

	def test_build_edi_transactions_api_response_shape(self):
		merged = {
			"ok": True,
			"computed_at": 1000.0,
			"status_by_type": remote._status_by_type(
				{"204": 10, "990": 0, "210": 5, "214": 3},
				{"204": 6, "990": 0, "210": 2, "214": 1},
				{"204": 1, "990": 0, "210": 1, "214": 0},
			),
		}
		payload = remote.build_edi_transactions_api_response(merged)
		self.assertTrue(payload["ok"])
		self.assertTrue(payload["edi_counts_available"])
		self.assertEqual(payload["transactions_total"], 18)
		self.assertEqual(payload["success"], 9)
		self.assertEqual(payload["failure"], 2)
		self.assertEqual(payload["in_progress"], 7)
		self.assertEqual(payload["edi_status_by_type"]["204"]["in_progress"], 3)

	def test_bind_edi_214_status_uses_monitoring_count(self):
		kpis = remote.unavailable_edi_counts()["kpis"]
		with patch.object(remote, "dashboard_edi_214_counts", return_value={"ok": True, "count": 11}):
			remote.bind_edi_214_status_kpi(kpis)
		by_code = {card["code"]: card for card in kpis}
		self.assertEqual(by_code["214"]["count"], 11)
		self.assertTrue(by_code["214"]["available"])

	def test_bind_edi_card_counts_use_panel_cache_without_remote_scan(self):
		from openas2_manager.openas2 import edi_dashboard_counts as panels

		counts = {"204": 1, "990": 0, "210": 0, "214": 0}
		cached = {
			"ok": True,
			"counts": counts,
			"last_7": dict(counts),
			"previous_7": dict(counts),
			"computed_at": time.time(),
			"status_by_type": remote._status_by_type(counts, counts, dict.fromkeys(counts, 0)),
		}
		kpis = remote.unavailable_edi_counts()["kpis"]
		with (
			patch.object(panels, "read_panel_cache", return_value=cached),
			patch.object(remote, "count_edi_cards_chunked", side_effect=AssertionError("sync scan")),
		):
			remote.bind_edi_card_counts(kpis)
		self.assertEqual(kpis[0]["count"], 1)

	def test_schedule_card_refresh_enqueues_long_job(self):
		with (
			patch.object(remote, "_card_cache_get", return_value=None),
			patch.object(remote, "_card_cache_set"),
			patch.object(remote.frappe, "enqueue") as enqueue,
			patch.object(remote, "Thread") as thread_cls,
		):
			remote._schedule_card_refresh("oa2_edi_card_counts:v2:test")
		enqueue.assert_called_once()
		self.assertEqual(enqueue.call_args.kwargs.get("queue"), "long")
		thread_cls.assert_not_called()

	def test_schedule_card_refresh_falls_back_to_thread_when_enqueue_fails(self):
		with (
			patch.object(remote, "_card_cache_get", return_value=None),
			patch.object(remote, "_card_cache_set"),
			patch.object(remote.frappe, "enqueue", side_effect=RuntimeError("no worker")),
			patch.object(remote, "Thread") as thread_cls,
		):
			remote._schedule_card_refresh("oa2_edi_card_counts:v2:test")
		thread_cls.assert_called_once()
		kwargs = thread_cls.call_args.kwargs
		self.assertTrue(kwargs.get("daemon"))
		self.assertIs(kwargs.get("target"), remote._run_card_refresh_job)

	def test_refresh_edi_card_counts_stores_under_explicit_cache_key(self):
		window = (datetime(2026, 10, 15, 0, 0, 0), datetime(2026, 10, 8, 0, 0, 0))
		cache_key = remote._card_scope_key(SCOPE["query_ids"], window[0])
		counts = {"204": 5, "990": 1, "210": 0, "214": 2}
		merged = {
			"ok": True,
			"counts": counts,
			"last_7": dict(counts),
			"previous_7": dict(counts),
			"status_by_type": remote._status_by_type(
				counts,
				{"204": 4, "990": 1, "210": 0, "214": 1},
				{"204": 0, "990": 0, "210": 0, "214": 0},
			),
		}
		stored = {}

		def capture_set(key, value, expires_in_sec=remote.CARD_CACHE_KEEP_SECONDS):
			stored[key] = value

		flags = type("_Flags", (), {"oa2_edi_card_refresh_force": False})()
		with (
			patch.object(remote, "remote_reads_enabled", return_value=True),
			patch.object(remote, "resolve_scope", return_value=SCOPE),
			patch.object(remote, "_acquire_card_lock", return_value=True),
			patch.object(remote, "_release_card_lock"),
			patch.object(remote, "count_edi_cards_chunked", return_value=merged),
			patch.object(remote, "_card_cache_set", side_effect=capture_set),
			patch.object(remote, "_card_cache_get", return_value=None),
			patch.object(remote, "_card_cache_delete"),
			patch.object(remote.frappe, "flags", flags),
		):
			result = remote.refresh_edi_card_counts(cache_key=cache_key)
		self.assertTrue(result.get("ok"))
		self.assertIn(cache_key, stored)
		parsed = remote.valid_card_cache(stored[cache_key])
		self.assertIsNotNone(parsed)
		self.assertEqual(parsed["counts"]["204"], 5)
		self.assertEqual(parsed["status_by_type"]["214"]["total"], 2)

	def test_edi_card_count_split_queries_cover_filename_and_payload(self):
		now = datetime(2026, 10, 22, 15, 0, 0)
		last_7, prev_7 = remote._card_windows(now)
		common = {
			"as2_ids": ["SHIPPER_AS2ID"],
			"last_7_start": last_7,
			"prev_7_start": prev_7,
			"id_from": 1,
			"id_to": 100,
		}
		name_sql, _name_params = remote.build_edi_card_count_query_filename(**common)
		payload_sql, payload_params = remote.build_edi_card_count_query_payload(**common)
		self.assertNotIn("msg_data", name_sql)
		self.assertEqual(payload_sql.count("msg_data"), 1)
		self.assertIn("IFNULL(REGEXP_SUBSTR(IFNULL(file_name, ''), %s), '') = ''", payload_sql)
		self.assertEqual(payload_params.count(remote._filename_type_pattern()), 1)
		name_row = {"n204": 3, "d204": 1, "p204": 0, "s204": 2, "f204": 0,
			"n990": 0, "d990": 0, "p990": 0, "s990": 0, "f990": 0,
			"n210": 0, "d210": 0, "p210": 0, "s210": 0, "f210": 0,
			"n214": 0, "d214": 0, "p214": 0, "s214": 0, "f214": 0}
		payload_row = {"n204": 0, "d204": 0, "p204": 0, "s204": 0, "f204": 0,
			"n990": 0, "d990": 0, "p990": 0, "s990": 0, "f990": 0,
			"n210": 1, "d210": 0, "p210": 0, "s210": 1, "f210": 0,
			"n214": 0, "d214": 0, "p214": 0, "s214": 0, "f214": 0}
		merged = remote.merge_card_count_rows([name_row, payload_row])
		raw = remote._merge_raw_card_count_rows(name_row, payload_row)
		self.assertEqual(merged["counts"]["204"], raw["n204"])
		self.assertEqual(merged["counts"]["210"], raw["n210"])
		self.assertEqual(merged["status_by_type"]["204"]["success"], raw["s204"])

	def _card_cache_store(self):
		store = {}

		def get_value(key):
			return store.get(key)

		def set_value(key, value, expires_in_sec=3600):
			store[key] = value

		def delete_value(key):
			store.pop(key, None)

		return store, get_value, set_value, delete_value

	def test_stale_card_lock_is_reclaimed_and_released(self):
		key = "oa2_edi_card_counts:v2:test"
		store, get_value, set_value, delete_value = self._card_cache_store()
		stale_at = time.time() - remote.CARD_LOCK_STALE_SECONDS - 10
		store[remote._card_lock_key(key)] = {
			"held": 1,
			"token": "old",
			"acquired_at": stale_at,
			"heartbeat_at": stale_at,
		}
		with (
			patch.object(remote, "_card_cache_get", side_effect=get_value),
			patch.object(remote, "_card_cache_set", side_effect=set_value),
			patch.object(remote, "_card_cache_delete", side_effect=delete_value),
		):
			self.assertTrue(remote._acquire_card_lock(key))
			self.assertIn(remote._card_lock_key(key), store)
			remote._release_card_lock(key)
		self.assertNotIn(remote._card_lock_key(key), store)

	def test_active_card_lock_blocks_second_acquire(self):
		key = "oa2_edi_card_counts:v2:test"
		store, get_value, set_value, delete_value = self._card_cache_store()
		now = time.time()
		store[remote._card_lock_key(key)] = {
			"held": 1,
			"token": "live",
			"acquired_at": now,
			"heartbeat_at": now,
		}
		with (
			patch.object(remote, "_card_cache_get", side_effect=get_value),
			patch.object(remote, "_card_cache_set", side_effect=set_value),
			patch.object(remote, "_card_cache_delete", side_effect=delete_value),
		):
			self.assertFalse(remote._acquire_card_lock(key))

	def test_release_card_lock_only_drops_own_token(self):
		key = "oa2_edi_card_counts:v2:test"
		store, get_value, set_value, delete_value = self._card_cache_store()
		now = time.time()
		store[remote._card_lock_key(key)] = {
			"held": 1,
			"token": "other",
			"acquired_at": now,
			"heartbeat_at": now,
		}
		remote._card_lock_state.token = "mine"
		remote._card_lock_state.key = key
		with (
			patch.object(remote, "_card_cache_get", side_effect=get_value),
			patch.object(remote, "_card_cache_delete", side_effect=delete_value),
		):
			remote._release_card_lock(key)
		self.assertIn(remote._card_lock_key(key), store)

	def test_refresh_releases_lock_when_aggregation_raises(self):
		cache_key = "oa2_edi_card_counts:v2:fail"
		store, get_value, set_value, delete_value = self._card_cache_store()
		with (
			patch.object(remote, "remote_reads_enabled", return_value=True),
			patch.object(remote, "resolve_scope", return_value=SCOPE),
			patch.object(remote, "_card_cache_get", side_effect=get_value),
			patch.object(remote, "_card_cache_set", side_effect=set_value),
			patch.object(remote, "_card_cache_delete", side_effect=delete_value),
			patch.object(remote, "count_edi_cards_chunked", side_effect=RuntimeError("boom")),
		):
			with self.assertRaises(RuntimeError):
				remote.refresh_edi_card_counts(cache_key=cache_key)
		self.assertNotIn(remote._card_lock_key(cache_key), store)

	def test_edi_card_refresh_in_progress_follows_lock_and_scheduled(self):
		key = "oa2_edi_card_counts:v2:prog"
		store, get_value, set_value, delete_value = self._card_cache_store()
		now = time.time()
		with (
			patch.object(remote, "remote_reads_enabled", return_value=True),
			patch.object(remote, "read_settings", return_value=({"password": "x"}, None)),
			patch.object(remote, "resolve_scope", return_value=SCOPE),
			patch.object(remote, "_card_windows", return_value=(datetime(2026, 10, 15), datetime(2026, 10, 8))),
			patch.object(remote, "_card_scope_key", return_value=key),
			patch.object(remote, "_card_cache_get", side_effect=get_value),
			patch.object(remote, "_card_cache_set", side_effect=set_value),
			patch.object(remote, "_card_cache_delete", side_effect=delete_value),
		):
			self.assertFalse(remote.edi_card_refresh_in_progress())
			store[remote._card_lock_key(key)] = {
				"held": 1,
				"token": "live",
				"acquired_at": now,
				"heartbeat_at": now,
			}
			self.assertTrue(remote.edi_card_refresh_in_progress())
			delete_value(remote._card_lock_key(key))
			store[remote._card_refresh_scheduled_key(key)] = {"at": now}
			self.assertFalse(remote.edi_card_refresh_in_progress())

	def test_orphan_scheduled_marker_without_lock_allows_reschedule(self):
		cache_key = "oa2_edi_card_counts:v2:orphan"
		store, get_value, set_value, delete_value = self._card_cache_store()
		recent = time.time() - remote.CARD_SCHEDULED_ORPHAN_SECONDS - 5
		store[remote._card_refresh_scheduled_key(cache_key)] = {"at": recent}
		with (
			patch.object(remote, "_card_cache_get", side_effect=get_value),
			patch.object(remote, "_card_cache_set", side_effect=set_value),
			patch.object(remote, "_card_cache_delete", side_effect=delete_value),
			patch.object(remote, "_cache_has_display_counts", return_value=False),
			patch.object(remote.frappe, "enqueue") as enqueue,
		):
			remote._schedule_card_refresh(cache_key)
		enqueue.assert_called_once()

	def test_stale_scheduled_marker_allows_new_refresh_job(self):
		cache_key = "oa2_edi_card_counts:v2:sched"
		store, get_value, set_value, delete_value = self._card_cache_store()
		stale = time.time() - remote.CARD_SCHEDULED_STALE_SECONDS - 5
		store[remote._card_refresh_scheduled_key(cache_key)] = {"at": stale}
		with (
			patch.object(remote, "_card_cache_get", side_effect=get_value),
			patch.object(remote, "_card_cache_set", side_effect=set_value),
			patch.object(remote, "_card_cache_delete", side_effect=delete_value),
			patch.object(remote.frappe, "enqueue") as enqueue,
		):
			remote._schedule_card_refresh(cache_key)
		enqueue.assert_called_once()

	def test_concurrent_refresh_skips_when_lock_held(self):
		cache_key = "oa2_edi_card_counts:v2:busy"
		now = time.time()
		store, get_value, set_value, delete_value = self._card_cache_store()
		store[remote._card_lock_key(cache_key)] = {
			"held": 1,
			"token": "busy",
			"acquired_at": now,
			"heartbeat_at": now,
		}
		with (
			patch.object(remote, "remote_reads_enabled", return_value=True),
			patch.object(remote, "resolve_scope", return_value=SCOPE),
			patch.object(remote, "_card_cache_get", side_effect=get_value),
			patch.object(remote, "_card_cache_set", side_effect=set_value),
			patch.object(remote, "_card_cache_delete", side_effect=delete_value),
			patch.object(remote, "count_edi_cards_chunked", side_effect=AssertionError("scan")),
		):
			result = remote.refresh_edi_card_counts(cache_key=cache_key)
		self.assertTrue(result.get("skipped"))

	def test_transaction_list_reads_remote_messages_and_reports_failures(self):
		from openas2_manager.openas2 import tms_edi

		message = {
			"name": "remote:31",
			"instance_type": "Shipper",
			"instance": "Shipper OpenAS20",
			"instance_label": "Shipper",
			"direction": "Outbound",
			"partner": "Broker",
			"local_as2_id": "SHIPPER_AS2ID",
			"remote_as2_id": "BROKER_AS2ID",
			"transaction_type": "204",
			"status": "Success",
			"message_id": "abc@openas2",
			"mdn_status": "Received",
			"timestamp": "2026-10-15 09:01:00",
			"file_name": "LOAD054_204.edi",
		}
		with (
			patch.object(remote, "list_live_messages", return_value={"rows": [message], "count": 1}) as listed_live,
			patch.object(tms_edi.frappe, "get_all") as get_all,
		):
			listed = tms_edi.get_edi_documents.__wrapped__(transaction_type="204", limit=10)
		get_all.assert_not_called()
		self.assertTrue(listed["ok"])
		self.assertEqual(listed["source"], "OpenAS2 database")
		self.assertEqual(listed["rows"][0]["name"], "remote:31")
		self.assertEqual(listed["rows"][0]["transaction_type"], "204")
		self.assertEqual(listed["rows"][0]["sent_from"], "Shipper")
		self.assertEqual(listed["rows"][0]["received_by"], "Broker")
		self.assertEqual(listed["rows"][0]["reference_number"], "")
		self.assertEqual(listed["rows"][0]["tms_url"], "")
		self.assertIn("not one unique business transaction", listed["limitation"])
		listed_live.assert_called_once()
		self.assertEqual(listed_live.call_args.kwargs["transaction_type"], "204")

		with (
			patch.object(remote, "list_live_messages", return_value=None),
			patch.object(tms_edi.frappe, "get_all") as get_all,
		):
			failed = tms_edi.get_edi_documents.__wrapped__()
		get_all.assert_not_called()
		self.assertFalse(failed["ok"])
		self.assertEqual(failed["rows"], [])
		self.assertEqual(failed["error"], remote.REMOTE_READ_ERROR)

	def test_remote_transaction_details_load_payload_on_demand(self):
		from openas2_manager.openas2 import tms_edi

		detail = FakeConnection(
			[
				_record(id=31, file_name="plain.edi"),
			]
		)
		payload = FakeConnection(
			[
				{
					"id": 31,
					"sender_id": "SHIPPER_AS2ID",
					"receiver_id": "BROKER_AS2ID",
					"payload_chars": 40,
					"msg_data": "ISA*00*~\r\nST*210*0001~\r\n",
				}
			]
		)
		connections = [detail, payload]

		def connect(_settings):
			return connections.pop(0)

		with (
			patch.object(remote, "remote_reads_enabled", return_value=True),
			patch.object(remote, "read_settings", return_value=({"password": "secret"}, None)),
			patch.object(remote, "resolve_scope", return_value=SCOPE),
			patch.object(remote, "connect", side_effect=connect),
			patch.object(tms_edi.frappe, "throw", side_effect=RuntimeError("rejected")),
		):
			row = tms_edi.get_edi_document_details.__wrapped__("remote:31")
		self.assertEqual(row["transaction_type"], "210")
		self.assertIn("ST*210*", row["edi_content"])
		self.assertIn("210", row["json_content"])
		self.assertEqual(row["reference_number"], "")
		self.assertNotIn("msg_data", detail.statements[-1][0])
		self.assertIn("SUBSTRING(msg_data, 1, %s)", payload.statements[-1][0])

		with (
			patch.object(remote, "remote_reads_enabled", return_value=True),
			patch.object(remote, "read_settings", return_value=({"password": "secret"}, None)),
			patch.object(remote, "resolve_scope", return_value=SCOPE),
			patch.object(remote, "connect", return_value=FakeConnection([])),
		):
			with self.assertRaises(remote.RemoteMessageNotFound):
				remote.remote_message_details("remote:99")

		with (
			patch.object(remote, "remote_reads_enabled", return_value=True),
			patch.object(remote, "read_settings", return_value=({"password": "secret"}, None)),
			patch.object(remote, "resolve_scope", return_value=SCOPE),
			patch.object(remote, "connect", side_effect=TimeoutError("timed out")),
		):
			self.assertIsNone(remote.remote_message_details("remote:31"))

		with patch.object(tms_edi.frappe, "throw", side_effect=RuntimeError("rejected")):
			with self.assertRaises(RuntimeError):
				tms_edi.get_edi_document_details.__wrapped__("OED-2026-00001")

	def test_payload_id_is_strict_and_does_not_query(self):
		self.assertEqual(remote.parse_remote_row_id("remote:4695698"), 4695698)
		self.assertEqual(remote.parse_remote_row_id("15"), 15)
		for bad in ("", "remote:", "remote:0", "remote:15 OR 1=1", "MSG-0001", "remote:15;drop", "remote:-1"):
			self.assertIsNone(remote.parse_remote_row_id(bad))
		with patch.object(remote, "connect") as connect:
			with self.assertRaises(ValueError):
				remote.remote_message_payload("remote:15 OR 1=1")
		connect.assert_not_called()

	def test_payload_query_is_one_parameterized_message(self):
		with self.assertRaises(RuntimeError):
			remote._select_sql("id, msg_data")
		list_sql, _list_params = remote.build_list_query(as2_ids=["SHIPPER_AS2ID"], limit=5)
		detail_sql, _detail_params = remote.build_detail_query(15, ["SHIPPER_AS2ID"])
		self.assertNotIn("msg_data", list_sql)
		self.assertNotIn("msg_data", detail_sql)
		sql, params = remote.build_payload_query(4695698, ["SHIPPER_AS2ID"])
		self.assertIn("SUBSTRING(msg_data, 1, %s)", sql)
		self.assertIn("id = %s", sql)
		self.assertNotIn("msg_headers", sql)
		self.assertNotIn("mdn_response", sql)
		self.assertNotIn("SHIPPER_AS2ID", sql)
		self.assertEqual(params[0], remote.PAYLOAD_PREVIEW_CHARS)
		self.assertEqual(params[1], 4695698)
		self.assertIn("SHIPPER_AS2ID", params)

	def test_payload_requires_access_and_returns_one_body(self):
		connection = FakeConnection(
			[
				{
					"id": 15,
					"sender_id": "SHIPPER_AS2ID",
					"receiver_id": "BROKER_AS2ID",
					"payload_chars": 18,
					"msg_data": "ISA*00*TEST~ST*204~",
				}
			]
		)
		with (
			patch.object(remote, "remote_reads_enabled", return_value=True),
			patch.object(remote, "read_settings", return_value=({"password": "secret"}, None)),
			patch.object(remote, "resolve_scope", return_value=SCOPE),
			patch.object(remote, "connect", return_value=connection),
		):
			result = remote.remote_message_payload("remote:15")
		sql = connection.statements[-1][0]
		self.assertIn("msg_data", sql)
		self.assertNotIn("msg_headers", sql)
		self.assertTrue(result["available"])
		self.assertEqual(result["payload"], "ISA*00*TEST~ST*204~")
		self.assertEqual(result["transaction_type"], "204")
		self.assertEqual(result["name"], "remote:15")
		self.assertNotIn("secret", sql)

	def test_payload_view_strips_mime_for_both_directions(self):
		edi = _interchange(_txn("990", ["B1*LOAD9*20260101*A"]))
		wrapped = (
			"------=_Part_9\r\n"
			"Content-Type: application/edi-x12\r\n"
			"Content-Transfer-Encoding: binary\r\n"
			"Content-Disposition: attachment; filename=load.edi\r\n"
			"\r\n"
			f"{edi}\r\n"
			"------=_Part_9\r\n"
			"Content-Type: application/pkcs7-signature\r\n"
			"Content-Transfer-Encoding: base64\r\n"
			"\r\n"
			"U0lHTkFUVVJF\r\n"
			"------=_Part_9--\r\n"
		)
		for direction, sender, receiver in (
			("SEND", "SHIPPER_AS2ID", "BROKER_AS2ID"),
			("RECEIVE", "BROKER_AS2ID", "SHIPPER_AS2ID"),
		):
			connection = FakeConnection(
				[
					{
						"id": 15,
						"sender_id": sender,
						"receiver_id": receiver,
						"payload_chars": len(wrapped),
						"msg_data": wrapped,
					}
				]
			)
			with (
				patch.object(remote, "remote_reads_enabled", return_value=True),
				patch.object(remote, "read_settings", return_value=({"password": "secret"}, None)),
				patch.object(remote, "resolve_scope", return_value=SCOPE),
				patch.object(remote, "connect", return_value=connection),
			):
				result = remote.remote_message_payload("remote:15")
			self.assertTrue(result["available"], direction)
			self.assertEqual(result["payload"], edi)
			self.assertTrue(result["payload"].startswith("ISA"))
			self.assertIn("IEA*", result["payload"])
			self.assertNotIn("Content-Type", result["payload"])
			self.assertNotIn("Content-Disposition", result["payload"])
			self.assertNotIn("U0lHTkFUVVJF", result["payload"])
			self.assertEqual(result["transaction_type"], "990")

	def test_mime_without_an_interchange_is_not_shown_as_edi(self):
		wrapped = (
			"------=_Part_9\r\n"
			"Content-Type: text/plain\r\n"
			"Content-Transfer-Encoding: binary\r\n"
			"\r\n"
			"Not an EDI file\r\n"
			"------=_Part_9--\r\n"
		)
		connection = FakeConnection(
			[
				{
					"id": 15,
					"sender_id": "SHIPPER_AS2ID",
					"receiver_id": "BROKER_AS2ID",
					"payload_chars": len(wrapped),
					"msg_data": wrapped,
				}
			]
		)
		with (
			patch.object(remote, "remote_reads_enabled", return_value=True),
			patch.object(remote, "read_settings", return_value=({"password": "secret"}, None)),
			patch.object(remote, "resolve_scope", return_value=SCOPE),
			patch.object(remote, "connect", return_value=connection),
		):
			result = remote.remote_message_payload("remote:15")
		self.assertFalse(result["available"])
		self.assertEqual(result["payload"], "")
		self.assertEqual(result["reason"], "not_edi")
		self.assertNotIn("Content-Type", result["message"])
		self.assertNotIn("Not an EDI", result["message"])

	def test_full_payload_is_capped_and_st_detection_ignores_filenames(self):
		preview_sql, preview_params = remote.build_payload_query(15, ["SHIPPER_AS2ID"])
		full_sql, full_params = remote.build_payload_query(
			15, ["SHIPPER_AS2ID"], remote.PAYLOAD_FULL_CHARS + 50
		)
		self.assertEqual(preview_params[0], remote.PAYLOAD_PREVIEW_CHARS)
		self.assertEqual(full_params[0], remote.PAYLOAD_FULL_CHARS)
		self.assertIn("SUBSTRING(msg_data, 1, %s)", full_sql)
		self.assertNotIn(str(remote.PAYLOAD_FULL_CHARS), full_sql)
		self.assertNotIn("msg_headers", full_sql)
		self.assertEqual(
			remote.transaction_type_from_payload("ISA*00*~\r\nST*997*0001~\r\nSE*2*0001~"),
			"997",
		)
		self.assertEqual(remote.transaction_type_from_payload("load_997.edi"), "")
		self.assertEqual(remote.transaction_type_from_payload("ST*999*0001~"), "")

	def test_payload_empty_and_out_of_scope(self):
		empty = FakeConnection(
			[
				{
					"id": 15,
					"sender_id": "SHIPPER_AS2ID",
					"receiver_id": "BROKER_AS2ID",
					"payload_chars": 0,
					"msg_data": "",
				}
			]
		)
		with (
			patch.object(remote, "remote_reads_enabled", return_value=True),
			patch.object(remote, "read_settings", return_value=({"password": "secret"}, None)),
			patch.object(remote, "resolve_scope", return_value=SCOPE),
			patch.object(remote, "connect", return_value=empty),
		):
			result = remote.remote_message_payload("remote:15")
		self.assertFalse(result["available"])
		self.assertEqual(result["payload"], "")
		self.assertEqual(result["reason"], "empty")

		hidden = FakeConnection(
			[
				{
					"id": 15,
					"sender_id": "OTHER",
					"receiver_id": "NOPE",
					"payload_chars": 8,
					"msg_data": "ISA*HIDDEN",
				}
			]
		)
		with (
			patch.object(remote, "remote_reads_enabled", return_value=True),
			patch.object(remote, "read_settings", return_value=({"password": "secret"}, None)),
			patch.object(remote, "resolve_scope", return_value=SCOPE),
			patch.object(remote, "connect", return_value=hidden),
		):
			with self.assertRaises(remote.RemoteAccessDenied):
				remote.remote_message_payload("remote:15")

		with (
			patch.object(remote, "remote_reads_enabled", return_value=True),
			patch.object(remote, "read_settings", return_value=({"password": "secret"}, None)),
			patch.object(remote, "resolve_scope", return_value=None),
			patch.object(remote, "connect") as connect,
		):
			with self.assertRaises(remote.RemoteAccessDenied):
				remote.remote_message_payload("remote:15")
		connect.assert_not_called()

	def test_payload_connection_failure_does_not_echo_the_body(self):
		with (
			patch.object(remote, "remote_reads_enabled", return_value=True),
			patch.object(remote, "read_settings", return_value=({"password": "secret"}, None)),
			patch.object(remote, "resolve_scope", return_value=SCOPE),
			patch.object(remote, "connect", side_effect=RuntimeError("ISA*SECRET payload")),
			patch.object(remote, "_warn") as warn,
		):
			result = remote.remote_message_payload("remote:15")
		self.assertIsNone(result)
		message = warn.call_args[0][0]
		self.assertNotIn("ISA*", message)
		self.assertNotIn("SECRET", message)

	def test_payload_api_rejects_a_bad_id_without_connecting(self):
		with (
			patch.object(remote, "connect") as connect,
			patch.object(mon.frappe, "throw", side_effect=RuntimeError("rejected")),
		):
			with self.assertRaises(RuntimeError):
				mon.get_remote_message_payload.__wrapped__("remote:nope")
		connect.assert_not_called()

	def test_drawer_requests_remote_payload_separately(self):
		page = (
			Path(__file__).resolve().parents[1]
			/ "openas2_manager"
			/ "page"
			/ "openas2_messages"
			/ "openas2_messages.js"
		).read_text(encoding="utf-8")
		self.assertIn("get_remote_message_payload", page)
		self.assertIn("load_remote_payload", page)
		self.assertIn("$pre.text(text)", page)
		self.assertNotIn("fromRemote ? d.error_message", page)
		load_rows = page.split("load_rows()")[1].split("load_edi_documents()")[0]
		self.assertNotIn("get_remote_message_payload", load_rows)
		self.assertNotIn("convert_message_payload_json", load_rows)
		self.assertIn('role="tablist"', page)
		self.assertIn('role="tab"', page)
		self.assertIn('data-mode="raw"', page)
		self.assertIn('data-mode="json"', page)
		self.assertIn('>${__("Raw EDI")}</button>', page)
		self.assertIn('>${__("JSON")}</button>', page)
		self.assertIn('data-download="edi"', page)
		self.assertIn('data-download="json"', page)
		self.assertIn("convert_message_payload_json", page)
		self.assertIn("JSON conversion is unavailable because the EDI payload could not be retrieved.", page)
		self.assertNotIn(".html(text)", page)
		self.assertNotIn(".html(message.json)", page)
		self.assertIn("_download_after_load", page)
		self.assertIn("finish_download", page)
		download = page.split("download_payload(kind) {")[1].split("finish_download(kind) {")[0]
		self.assertLess(
			download.index('this._download_after_load = "edi"'),
			download.index("load_remote_payload(this._details_name, true)"),
		)
		self.assertIn("JSON.parse(parsed.json)", page)

	def test_detail_tabs_convert_each_supported_type_from_extracted_edi(self):
		samples = {
			"204": ["B2**SCAC**LOAD1"],
			"990": ["B1*SCAC*LOAD1*20260101*A"],
			"214": ["B10*SHIP1*LOAD1*SCAC"],
			"210": ["B3**INV1*LOAD1*CC"],
			"810": ["BIG*20260101*INV1"],
			"820": ["BPR*I*10.00"],
			"997": ["AK1*SM*1", "AK9*A*1*1*1"],
		}
		for code, segments in samples.items():
			edi = _interchange(_txn(code, segments))
			wrapped = (
				"------=_Part_1\r\n"
				"Content-Type: application/edi-x12\r\n"
				"Content-Transfer-Encoding: binary\r\n"
				"\r\n"
				f"{edi}\r\n"
				"------=_Part_1\r\n"
				"Content-Type: application/pkcs7-signature\r\n"
				"Content-Transfer-Encoding: base64\r\n"
				"\r\n"
				"U0lHTkFUVVJF\r\n"
				"------=_Part_1--\r\n"
			)
			raw = remote._edi_payload_result(f"remote:{code}", wrapped, len(wrapped), full=True)
			self.assertTrue(raw["available"], code)
			self.assertEqual(raw["transaction_type"], code)
			self.assertNotIn("Content-Type", raw["payload"])
			self.assertNotIn("pkcs7", raw["payload"])
			self.assertNotIn("U0lHTkFUVVJF", raw["payload"])
			self.assertTrue(raw["payload"].startswith("ISA"))
			converted = mon.convert_message_payload_json.__wrapped__(raw["payload"])
			self.assertTrue(converted["available"], converted.get("message"))
			self.assertEqual(converted["transaction_type"], code)
			self.assertTrue(converted["json"].startswith("{\n"))
			parsed = json.loads(converted["json"])
			self.assertEqual(parsed["transaction_type"], code)
			transaction = parsed["functional_groups"][0]["transactions"][0]
			self.assertEqual(transaction["transaction_set"], code)
			self.assertEqual(transaction["segments"][0]["id"], segments[0].split("*", 1)[0])
			self.assertNotIn("shipment_id", converted["json"])
		missing = mon.convert_message_payload_json.__wrapped__(
			_interchange(_txn("999", ["AK2*204*0001"]))
		)
		self.assertFalse(missing["available"])
		self.assertEqual(missing["json"], "")
		self.assertIn("unavailable", missing["message"])

	def test_json_conversion_refuses_empty_invalid_and_oversized(self):
		empty = mon.convert_message_payload_json.__wrapped__("   ")
		self.assertEqual(empty["reason"], "empty")
		self.assertEqual(empty["json"], "")
		invalid = mon.convert_message_payload_json.__wrapped__("<html><body>Not EDI</body></html>")
		self.assertEqual(invalid["reason"], "invalid")
		self.assertEqual(invalid["json"], "")
		self.assertNotIn("<html>", invalid["message"])
		unsupported = mon.convert_message_payload_json.__wrapped__(
			_interchange(_txn("999", ["AK2*204*0001"]))
		)
		self.assertEqual(unsupported["reason"], "unsupported")
		self.assertEqual(unsupported["transaction_type"], "999")
		self.assertEqual(unsupported["json"], "")
		with patch.object(mon.frappe, "throw", side_effect=RuntimeError("rejected")):
			with self.assertRaises(RuntimeError):
				mon.convert_message_payload_json.__wrapped__(123)
			with self.assertRaises(RuntimeError):
				mon.convert_message_payload_json.__wrapped__("x" * (remote.PAYLOAD_FULL_CHARS + 1))



	def test_st_segment_detection_accepts_delimiters_and_whitespace(self):
		samples = {
			"204": "ISA*00*          *00*~\r\nST*204*0001~\r\nSE*2*0001~",
			"990": "GS*GF*A*B*20260101*1200*1*X*004010~\n ST * 990 *0001~\n",
			"214": "ISA|00|~\nST|214|0001~\n",
			"210": "~\r\nST* 210 *0001~\r\n",
		}
		for code, payload in samples.items():
			self.assertEqual(remote.transaction_type_from_payload(payload), code, payload)
		mime = (
			"------=_Part_1\r\n"
			"Content-Type: application/edi-x12; name=load.txt\r\n"
			"Content-Transfer-Encoding: binary\r\n"
			"Content-Disposition: attachment; filename=204_load.txt\r\n"
			"\r\n"
			"ISA*00*~\n"
			"GS*SM*SENDER*RECEIVER*20260101*1200*1*X*004010\n"
			"ST*204*2799\n"
		)
		self.assertEqual(remote.transaction_type_from_payload(mime), "204")
		import base64
		encoded = base64.b64encode(b"ISA*00*~\nST*990*0001~\n").decode()
		wrapped = (
			"Content-Type: application/EDI-X12\n"
			"Content-Transfer-Encoding: base64\n"
			"\n" + encoded
		)
		self.assertEqual(remote.transaction_type_from_payload(wrapped), "990")

	def test_undetectable_payloads_stay_blank(self):
		for payload in ("", "   ", "load_210.edi", "ST*999*0001~", "hello", "ST*2040*0001~"):
			self.assertEqual(remote.transaction_type_from_payload(payload), "", payload)

	def test_list_detects_types_for_inbound_and_outbound_without_filenames(self):
		inbound = _record(
			id=21,
			direction="RECEIVE",
			sender_id="BROKER_AS2ID",
			receiver_id="SHIPPER_AS2ID",
			file_name=None,
			status="ok",
			state="msg_received_mdn_sent_ok",
		)
		outbound = _record(
			id=22,
			direction="SEND",
			sender_id="SHIPPER_AS2ID",
			receiver_id="BROKER_AS2ID",
			file_name="",
			status="ok",
			state="msg_sent_mdn_received_ok",
		)
		unknown = _record(id=23, file_name="notes.txt", direction="SEND")
		mime = (
			"------=_Part_9\n"
			"Content-Type: application/edi-x12\n"
			"Content-Transfer-Encoding: binary\n"
			"\n"
			"ISA*00*~\nST*210*0001~\n"
		)
		connection = _QueuedConnection(
			[
				[inbound, outbound, unknown],
				[
					{"id": 21, "msg_data": "ISA*00*~\r\nST*214*0001~\r\n"},
					{"id": 22, "msg_data": mime},
					{"id": 23, "msg_data": "not an edi payload"},
				],
			]
		)
		with (
			patch.object(remote, "remote_reads_enabled", return_value=True),
			patch.object(remote, "read_settings", return_value=({"password": "secret"}, None)),
			patch.object(remote, "resolve_scope", return_value=SCOPE),
			patch.object(remote, "connect", return_value=connection),
			patch.object(remote, "_fetch_edi_type_rows", return_value=[]),
		):
			result = remote.list_live_messages(limit=10)
		by_name = {row["name"]: row for row in result["rows"]}
		self.assertEqual(by_name["remote:21"]["direction"], "Inbound")
		self.assertEqual(by_name["remote:21"]["transaction_type"], "214")
		self.assertEqual(by_name["remote:22"]["direction"], "Outbound")
		self.assertEqual(by_name["remote:22"]["transaction_type"], "210")
		self.assertEqual(by_name["remote:23"]["transaction_type"], "Unknown")
		statements = [sql for sql, _params in connection.statements]
		list_sql = next(sql for sql in statements if "ORDER BY id DESC" in sql)
		prefix_sql = next(sql for sql in statements if "SUBSTRING(msg_data, 1, %s)" in sql)
		self.assertNotIn("msg_data", list_sql)
		self.assertNotIn("msg_headers", prefix_sql)
		self.assertNotIn("mdn_response", prefix_sql)
		self.assertEqual(statements.count("SET SESSION TRANSACTION READ ONLY"), 2)


class TestSystemLogsRemoteMessages(unittest.TestCase):
	def _logs(self, **kwargs):
		from openas2_manager.openas2.system_logs import get_system_logs

		return get_system_logs.__wrapped__(**kwargs)

	def test_message_rows_use_remote_ids(self):
		live = {
			"rows": [
				{
					"name": "remote:15",
					"direction": "Outbound",
					"transaction_type": "204",
					"partner": "Broker",
					"status": "Success",
					"timestamp": "2026-10-15 09:01:00",
					"instance": "Shipper OpenAS20",
					"file_name": "LOAD054_204.edi",
					"message_id": "<abc@openas2>",
					"source": "OpenAS2 database",
				}
			],
			"count": 1,
		}
		with patch("openas2_manager.openas2.remote_tracking.list_live_messages", return_value=live) as listed:
			result = self._logs(source="EDI / Message", limit=50)
		listed.assert_called_once()
		self.assertTrue(result["ok"])
		self.assertNotIn("error", result)
		self.assertEqual(result["rows"][0]["name"], "remote:15")
		self.assertEqual(result["rows"][0]["source"], "EDI / Message")
		self.assertEqual(result["rows"][0]["status"], "Success")

	def test_zero_remote_rows_are_empty_not_an_error(self):
		with patch(
			"openas2_manager.openas2.remote_tracking.list_live_messages",
			return_value={"rows": [], "count": 0},
		):
			result = self._logs(source="EDI / Message")
		self.assertTrue(result["ok"])
		self.assertEqual(result["rows"], [])
		self.assertNotIn("error", result)

	def test_remote_failure_does_not_read_message_log(self):
		with (
			patch("openas2_manager.openas2.remote_tracking.list_live_messages", return_value=None),
			patch("openas2_manager.openas2.system_logs.frappe.get_all") as get_all,
		):
			result = self._logs(source="EDI / Message", search="Broker")
		get_all.assert_not_called()
		self.assertFalse(result["ok"])
		self.assertEqual(result["rows"], [])
		self.assertEqual(result["error"], remote.REMOTE_READ_ERROR)

	def test_runtime_source_does_not_query_the_message_database(self):
		with (
			patch("openas2_manager.openas2.remote_tracking.list_live_messages") as listed,
			patch("openas2_manager.openas2.system_logs._collect_runtime_logs", return_value=[]),
		):
			result = self._logs(source="Runtime")
		listed.assert_not_called()
		self.assertTrue(result["ok"])
		self.assertNotIn("error", result)

	def test_logs_refresh_failure_is_not_success(self):
		from openas2_manager.openas2.system_logs import refresh_system_logs

		with (
			patch("openas2_manager.openas2.remote_tracking.list_live_messages", return_value=None),
			patch("openas2_manager.openas2.monitoring.discover_instance_messages") as discover,
		):
			result = refresh_system_logs.__wrapped__()
		discover.assert_not_called()
		self.assertFalse(result["ok"])
		self.assertEqual(result["error"], remote.REMOTE_READ_ERROR)

	def test_logs_refresh_empty_database_is_success(self):
		from openas2_manager.openas2.system_logs import refresh_system_logs

		with patch(
			"openas2_manager.openas2.remote_tracking.list_live_messages",
			return_value={"rows": [], "count": 0},
		):
			result = refresh_system_logs.__wrapped__()
		self.assertTrue(result["ok"])
		self.assertTrue(result["refreshed"])
		self.assertNotIn("error", result)

	def test_message_id_filter_is_parameterized_and_skips_payload(self):
		message_id = "<abc@openas2>"
		sql, params = remote.build_list_query(as2_ids=["SHIPPER_AS2ID"], message_id=message_id, limit=5)
		self.assertNotIn(message_id, sql)
		self.assertIn(message_id, params)
		self.assertIn("abc@openas2", params)
		self.assertIn("msg_id IN (%s, %s)", sql)
		self.assertNotIn("msg_data", sql)
		self.assertNotIn("msg_headers", sql)
		self.assertNotIn("mdn_response", sql)

	def test_logs_page_keeps_empty_copy_and_shows_database_error(self):
		page = (
			Path(__file__).resolve().parents[1]
			/ "openas2_manager"
			/ "page"
			/ "openas2_logs"
			/ "openas2_logs.js"
		).read_text(encoding="utf-8")
		self.assertIn("No logs found", page)
		self.assertIn("msg.error", page)
		self.assertIn("oa2_open_message", page)
		self.assertNotIn("OpenAS2 Message Log", page.split("get_system_logs", 1)[1])


class TestAssistantMessageSummary(unittest.TestCase):
	def test_log_analysis_returns_remote_error(self):
		from openas2_manager.openas2 import assistant

		with patch.object(
			assistant,
			"get_logs",
			return_value={"ok": False, "rows": [], "error": remote.REMOTE_READ_ERROR},
		):
			text, links = assistant._log_analysis()
		self.assertEqual(text, remote.REMOTE_READ_ERROR)
		self.assertEqual(links, [])

	def test_log_analysis_empty_result_is_not_an_error(self):
		from openas2_manager.openas2 import assistant

		with patch.object(assistant, "get_logs", return_value={"rows": [], "count": 0}):
			text, links = assistant._log_analysis()
		self.assertEqual(text, "No failed or error message logs are stored for your instances.")
		self.assertEqual(links, [])
		self.assertNotEqual(text, remote.REMOTE_READ_ERROR)

	def test_related_logs_do_not_read_message_log_on_failure(self):
		from openas2_manager.openas2 import assistant

		with (
			patch("openas2_manager.openas2.remote_tracking.list_live_messages", return_value=None) as listed,
			patch("openas2_manager.openas2.assistant.frappe.get_all") as get_all,
		):
			result = assistant._related_logs("<abc@openas2>", None)
		listed.assert_called_once()
		self.assertFalse(listed.call_args.kwargs.get("include_type_preview", True))
		get_all.assert_not_called()
		self.assertEqual(result["rows"], [])
		self.assertEqual(result["error"], remote.REMOTE_READ_ERROR)

	def test_related_logs_empty_query_has_no_error(self):
		from openas2_manager.openas2 import assistant

		with patch(
			"openas2_manager.openas2.remote_tracking.list_live_messages",
			return_value={"rows": [], "count": 0},
		):
			result = assistant._related_logs("abc@openas2", None)
		self.assertEqual(result["rows"], [])
		self.assertIsNone(result["error"])

	def test_get_logs_reads_remote_messages(self):
		from openas2_manager.openas2 import assistant

		source = Path(assistant.__file__).read_text(encoding="utf-8")
		start = source.split("def get_logs", 1)[1].split("\ndef ", 1)[0]
		self.assertIn("get_messages", start)
		self.assertNotIn("OpenAS2 Message Log", start)
		related = source.split("def _related_logs", 1)[1].split("\ndef ", 1)[0]
		self.assertIn("list_live_messages", related)
		self.assertNotIn("OpenAS2 Message Log", related)


if __name__ == "__main__":
	unittest.main()
