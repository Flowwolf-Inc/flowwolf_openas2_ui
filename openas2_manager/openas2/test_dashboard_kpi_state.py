import unittest

from openas2_manager.openas2 import dashboard_kpi_state as state


def _valid_response(counts: dict) -> list[dict]:
	return [
		{
			"code": code,
			"label": label,
			"count": counts[code],
			"last_7": 1,
			"change_pct": 0,
			"available": True,
		}
		for code, label in (
			("204", "Load Tender"),
			("990", "Ack"),
			("210", "Invoice"),
			("214", "Status"),
		)
	]


def _unavailable_response() -> list[dict]:
	return [
		{
			"code": code,
			"label": label,
			"count": None,
			"last_7": None,
			"change_pct": None,
			"available": False,
		}
		for code, label in (
			("204", "Load Tender"),
			("990", "Ack"),
			("210", "Invoice"),
			("214", "Status"),
		)
	]


class TestDashboardKpiState(unittest.TestCase):
	def test_valid_counts_then_failed_request_keeps_numbers(self):
		by_code: dict = {}
		shells = None
		counts = {"204": 10, "990": 20, "210": 30, "214": 40}
		display, shells = state.kpis_for_display(by_code, shells, _valid_response(counts))
		self.assertEqual([k["count"] for k in display], [10, 20, 30, 40])

		display, shells = state.kpis_for_display(by_code, shells, _unavailable_response())
		self.assertEqual([k["count"] for k in display], [10, 20, 30, 40])

	def test_refresh_in_progress_without_counts_keeps_numbers(self):
		by_code: dict = {}
		shells = None
		counts = {"204": 5, "990": 0, "210": 2, "214": 7}
		display, shells = state.kpis_for_display(by_code, shells, _valid_response(counts))
		self.assertEqual(display[1]["count"], 0)

		display, shells = state.kpis_for_display(by_code, shells, _unavailable_response())
		self.assertEqual([k["count"] for k in display], [5, 0, 2, 7])

	def test_later_success_updates_counts(self):
		by_code: dict = {}
		shells = None
		display, shells = state.kpis_for_display(
			by_code, shells, _valid_response({"204": 1, "990": 2, "210": 3, "214": 4})
		)
		display, shells = state.kpis_for_display(by_code, shells, _unavailable_response())
		display, shells = state.kpis_for_display(
			by_code, shells, _valid_response({"204": 9, "990": 8, "210": 7, "214": 6})
		)
		self.assertEqual([k["count"] for k in display], [9, 8, 7, 6])

	def test_zero_is_valid_count(self):
		self.assertTrue(state.kpi_count_valid(0))
		by_code: dict = {}
		display, _ = state.kpis_for_display(
			by_code,
			None,
			_valid_response({"204": 0, "990": 0, "210": 0, "214": 0}),
		)
		self.assertEqual([k["count"] for k in display], [0, 0, 0, 0])

	def test_initial_load_failure_stays_unavailable(self):
		by_code: dict = {}
		display, _ = state.kpis_for_display(by_code, None, _unavailable_response())
		self.assertTrue(all(k["count"] is None for k in display))

	def test_empty_incoming_with_snapshot_preserves_after_failure(self):
		by_code: dict = {}
		shells = None
		_, shells = state.kpis_for_display(
			by_code, shells, _valid_response({"204": 3, "990": 4, "210": 5, "214": 6})
		)
		display, shells = state.kpis_for_display(by_code, shells, [])
		self.assertEqual([k["count"] for k in display], [3, 4, 5, 6])

	def test_edi_chart_endpoint_can_seed_snapshot_without_summary(self):
		by_code: dict = {}
		payload = {
			"edi_counts_available": True,
			"edi_status_by_type": {
				"204": {"total": 11, "success": 11, "in_progress": 0, "failure": 0},
				"990": {"total": 0, "success": 0, "in_progress": 0, "failure": 0},
				"210": {"total": 2, "success": 2, "in_progress": 0, "failure": 0},
				"214": {"total": 4, "success": 4, "in_progress": 0, "failure": 0},
			},
		}
		self.assertTrue(state.ingest_edi_chart_totals(by_code, payload))
		display, _ = state.kpis_for_display(by_code, None, _unavailable_response())
		self.assertEqual([k["count"] for k in display], [11, 0, 2, 4])

	def test_refresh_in_progress_payload_does_not_clear_chart_seeded_counts(self):
		by_code: dict = {}
		state.ingest_edi_chart_totals(
			by_code,
			{
				"edi_counts_available": True,
				"edi_status_by_type": {
					"204": {"total": 100, "success": 100, "in_progress": 0, "failure": 0},
					"990": {"total": 1, "success": 1, "in_progress": 0, "failure": 0},
					"210": {"total": 2, "success": 2, "in_progress": 0, "failure": 0},
					"214": {"total": 3, "success": 3, "in_progress": 0, "failure": 0},
				},
			},
		)
		display, _ = state.kpis_for_display(by_code, None, _unavailable_response())
		self.assertEqual([k["count"] for k in display], [100, 1, 2, 3])
		self.assertFalse(state.ingest_edi_chart_totals(by_code, {"edi_counts_available": False, "edi_refresh_in_progress": True}))


if __name__ == "__main__":
	unittest.main()
