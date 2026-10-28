import time
import unittest
from unittest.mock import patch

from openas2_manager.openas2 import edi_home_chart as chart
from openas2_manager.openas2 import remote_tracking as remote


class TestEdiHomeChart(unittest.TestCase):
	def _sample_status(self):
		return remote._status_by_type(
			{"204": 72, "990": 31, "210": 20, "214": 45},
			{"204": 68, "990": 28, "210": 17, "214": 40},
			{"204": 1, "990": 1, "210": 1, "214": 1},
		)

	def test_format_chart_response_matches_reference_totals(self):
		snapshot = {"status_by_type": self._sample_status(), "computed_at": time.time()}
		payload = chart.format_chart_response(snapshot)
		self.assertTrue(payload["edi_counts_available"])
		self.assertEqual(payload["transactions_total"], 168)
		self.assertEqual(payload["success"], 153)
		self.assertEqual(payload["in_progress"], 11)
		self.assertEqual(payload["failure"], 4)
		self.assertEqual(payload["edi_status_by_type"]["204"]["total"], 72)

	def test_format_chart_empty_is_not_available(self):
		payload = chart.format_chart_response(None, refreshing=True, error="computing")
		self.assertFalse(payload["edi_counts_available"])
		self.assertTrue(payload["edi_refresh_in_progress"])
		self.assertIsNone(payload["transactions_total"])

	def test_status_consistency_validation(self):
		bad = dict(self._sample_status())
		bad["204"] = dict(bad["204"])
		bad["204"]["success"] = 999
		self.assertFalse(chart._status_totals_consistent(bad))

	def test_partial_snapshot_is_not_served(self):
		snapshot = {
			"status_by_type": self._sample_status(),
			"computed_at": 1.0,
			"complete": False,
		}
		key = "oa2_edi_home_chart:v1:test"
		with (
			patch.object(chart, "chart_cache_key", return_value=key),
			patch.object(chart, "_cache_get", return_value=snapshot),
		):
			self.assertIsNone(chart._read_snapshot())

	def test_zero_counts_are_valid(self):
		zeros = {code: 0 for code in remote.EDI_CARD_CODES}
		status = remote._status_by_type(zeros, zeros, zeros)
		payload = chart.format_chart_response({"status_by_type": status, "computed_at": 1.0})
		self.assertTrue(payload["edi_counts_available"])
		self.assertEqual(payload["transactions_total"], 0)


if __name__ == "__main__":
	unittest.main()
