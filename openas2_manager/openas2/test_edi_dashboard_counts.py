import time
import unittest
from datetime import datetime
from unittest.mock import patch

from openas2_manager.openas2 import edi_dashboard_counts as panels
from openas2_manager.openas2 import remote_tracking as remote


class TestEdiDashboardCounts(unittest.TestCase):
	def test_panel_cache_key_uses_v3_prefix(self):
		with (
			patch.object(panels, "remote_reads_enabled", return_value=True),
			patch.object(panels, "read_settings", return_value=({"password": ""}, None)),
			patch.object(panels, "resolve_scope", return_value={"query_ids": None}),
			patch.object(panels, "_card_windows", return_value=(datetime(2026, 10, 20), datetime(2026, 10, 13))),
		):
			key = panels.panel_cache_key()
		self.assertTrue(key.startswith("oa2_edi_panels:v3:"))

	def test_read_panel_cache_hit_without_remote_scan(self):
		key = "oa2_edi_panels:v3:20261020000000:*"
		stored = {
			"ok": True,
			"counts": {"204": 5, "990": 0, "210": 2, "214": 1},
			"last_7": {"204": 1, "990": 0, "210": 0, "214": 0},
			"previous_7": {"204": 0, "990": 0, "210": 0, "214": 0},
			"computed_at": time.time(),
			"status_by_type": remote._status_by_type(
				{"204": 5, "990": 0, "210": 2, "214": 1},
				{"204": 4, "990": 0, "210": 2, "214": 1},
				{"204": 0, "990": 0, "210": 0, "214": 0},
			),
		}
		with (
			patch.object(panels, "remote_reads_enabled", return_value=True),
			patch.object(panels, "read_settings", return_value=({"password": ""}, None)),
			patch.object(panels, "resolve_scope", return_value={"query_ids": None}),
			patch.object(panels, "panel_cache_key", return_value=key),
			patch.object(panels, "_cache_get", return_value=stored),
		):
			cached = panels.read_panel_cache()
		self.assertTrue(cached.get("ok"))
		self.assertEqual(cached["counts"]["204"], 5)
		self.assertEqual(cached["counts"]["990"], 0)

	def test_schedule_refresh_skips_when_lock_held(self):
		key = "oa2_edi_panels:v3:test:*"
		with (
			patch.object(panels, "panel_cache_key", return_value=key),
			patch.object(panels, "panel_refresh_in_progress", return_value=True),
			patch.object(panels, "Thread", side_effect=AssertionError("no thread")),
		):
			panels.schedule_panel_refresh(key)

	def test_attach_dashboard_sets_available_on_valid_cache(self):
		summary = remote.unavailable_edi_counts()
		cached = {
			"ok": True,
			"counts": {"204": 1, "990": 2, "210": 3, "214": 4},
			"last_7": {"204": 0, "990": 0, "210": 0, "214": 0},
			"previous_7": {"204": 0, "990": 0, "210": 0, "214": 0},
		}
		with (
			patch.object(panels, "read_panel_cache", return_value=cached),
			patch.object(panels, "panel_cache_key", return_value="k"),
			patch.object(panels, "panel_refresh_in_progress", return_value=False),
			patch.object(panels, "schedule_panel_refresh"),
			patch.object(panels, "resolve_edi_dashboard_read_error", return_value=""),
		):
			panels.attach_dashboard_edi_panels(summary)
		self.assertTrue(summary["edi_counts_available"])
		self.assertEqual(summary["kpis"][0]["count"], 1)


if __name__ == "__main__":
	unittest.main()
