import unittest
from unittest.mock import patch

from openas2_manager.openas2 import remote_tracking as remote


class TestRemoteDatabaseRead(unittest.TestCase):
	def test_remote_database_ping_success(self):
		class FakeConn:
			def close(self):
				return None

		with (
			patch.object(remote, "connect", return_value=FakeConn()),
			patch.object(remote, "_execute", return_value=[{"ok": 1}]),
		):
			self.assertIsNone(remote.remote_database_ping({"password": "x"}))

	def test_remote_database_ping_reports_safe_summary(self):
		with patch.object(remote, "connect", side_effect=OSError("secret-host refused")):
			msg = remote.remote_database_ping({"password": "secret"})
		self.assertIn("OSError", msg)
		self.assertNotIn("secret", msg)

	def test_resolve_edi_dashboard_read_error_clears_stale_generic_db_error(self):
		with (
			patch.object(remote, "edi_card_refresh_in_progress", return_value=False),
			patch.object(remote, "read_settings", return_value=({"password": ""}, None)),
			patch.object(remote, "remote_database_ping", return_value=None),
			patch.object(remote, "edi_card_read_error", return_value=remote.REMOTE_READ_ERROR),
			patch.object(remote, "_clear_card_refresh_error") as cleared,
		):
			msg = remote.resolve_edi_dashboard_read_error("k", result={"ok": False})
		cleared.assert_called_once_with("k")
		self.assertIn("msg_metadata", msg)

	def test_resolve_edi_dashboard_read_error_cache_miss_not_database_blame(self):
		cache_key = "oa2_edi_card_counts:v2:test:*"
		with (
			patch.object(remote, "edi_card_refresh_in_progress", return_value=False),
			patch.object(remote, "read_settings", return_value=({"password": ""}, None)),
			patch.object(remote, "remote_database_ping", return_value=None),
			patch.object(remote, "edi_card_read_error", return_value=None),
		):
			msg = remote.resolve_edi_dashboard_read_error(cache_key, result={"ok": False})
		self.assertNotEqual(msg, remote.REMOTE_READ_ERROR)
		self.assertIn("msg_metadata", msg)

	def test_resolve_edi_dashboard_read_error_when_ping_fails(self):
		with (
			patch.object(remote, "edi_card_refresh_in_progress", return_value=False),
			patch.object(remote, "read_settings", return_value=({"password": ""}, None)),
			patch.object(remote, "remote_database_ping", return_value="OperationalError 2003: refused"),
		):
			msg = remote.resolve_edi_dashboard_read_error("k", result=None)
		self.assertIn(remote.REMOTE_READ_ERROR, msg)
		self.assertIn("OperationalError", msg)

	def test_build_edi_transactions_api_response_from_cached_external_read(self):
		cached = {
			"ok": True,
			"counts": {"204": 1, "990": 0, "210": 0, "214": 0},
			"last_7": {"204": 0, "990": 0, "210": 0, "214": 0},
			"previous_7": {"204": 0, "990": 0, "210": 0, "214": 0},
			"computed_at": 1.0,
			"status_by_type": remote._status_by_type(
				{"204": 1, "990": 0, "210": 0, "214": 0},
				{"204": 1, "990": 0, "210": 0, "214": 0},
				{"204": 0, "990": 0, "210": 0, "214": 0},
			),
		}
		payload = remote.build_edi_transactions_api_response(cached, cache_key="k", read_error=None)
		self.assertTrue(payload["ok"])
		self.assertTrue(payload["edi_counts_available"])
		self.assertEqual(payload["transactions_total"], 1)
		self.assertNotEqual(payload.get("error"), remote.REMOTE_READ_ERROR)


if __name__ == "__main__":
	unittest.main()
