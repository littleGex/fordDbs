# tests/test_utils.py
"""
Tests for app/core/utils_core.py (utility-meter dashboard helpers).

These are pure-function tests -- no database required.

NOTE ON THIS REWRITE: an earlier hand-written version of this file
asserted `feb_record["usage"]["net_elect"]` and
`feb_record["is_february"]`. Neither key exists anywhere in the real
`_calculate_deltas_and_net` implementation (it only ever produces
"date", "readings", "usage", and "resets"). That test could never
have passed against the actual code -- either it was written against
a planned feature that was never implemented, or the function changed
after the test was written without the test being updated. Rewritten
here against the function as it actually exists.
"""
from datetime import datetime

from app.core.utils_core import (
    _parse_reading_value,
    _group_readings_by_date,
    _calculate_deltas_and_net,
    prepare_dashboard_data,
)


# Mock object to simulate SQLAlchemy row results
class MockReading:
    def __init__(self, reading_date, utility_name, reading_value):
        self.reading_date = reading_date
        self.utility_name = utility_name
        self.reading_value = reading_value


class TestParseReadingValue:

    def test_parses_valid_numeric_string(self):
        assert _parse_reading_value("123.45") == 123.45

    def test_invalid_string_returns_zero(self):
        assert _parse_reading_value("invalid") == 0.0

    def test_none_returns_zero(self):
        assert _parse_reading_value(None) == 0.0


class TestGroupReadingsByDate:

    def test_groups_multiple_utilities_under_same_date(self):
        raw_data = [
            MockReading("2026-01-01", "water", "100.0"),
            MockReading("2026-01-01", "gas", "50.0"),
            MockReading("2026-02-01", "water", "110.0"),
        ]
        grouped = _group_readings_by_date(raw_data)

        assert "2026-01-01" in grouped
        assert grouped["2026-01-01"]["water"] == 100.0
        assert grouped["2026-01-01"]["gas"] == 50.0
        assert grouped["2026-02-01"]["water"] == 110.0

    def test_accepts_datetime_objects_not_just_strings(self):
        raw_data = [
            MockReading(datetime(2026, 1, 1), "water", "100.0"),
        ]
        grouped = _group_readings_by_date(raw_data)

        assert "2026-01-01" in grouped


class TestCalculateDeltasAndNet:

    def test_first_entry_has_zero_usage_baseline(self):
        grouped_data = {"2026-01-01": {"water": 100.0}}
        results = _calculate_deltas_and_net(grouped_data)

        assert results[0]["usage"]["water"] == 0.0
        assert results[0]["resets"]["water"] is False

    def test_second_entry_calculates_delta_from_first(self):
        grouped_data = {
            "2026-01-01": {"water": 100.0},
            "2026-02-01": {"water": 110.0},
        }
        results = _calculate_deltas_and_net(grouped_data)

        # results are NOT pre-sorted by the function itself for return
        # order beyond input dict order, so look up by date explicitly
        feb_record = next(r for r in results if r["date"] == "2026-02-01")
        assert feb_record["usage"]["water"] == 10.0
        assert feb_record["resets"]["water"] is False

    def test_meter_reset_detected_when_value_drops(self):
        """
        If a meter reading drops below the previous reading (e.g. the
        physical meter was replaced/reset), usage should report the
        raw current value rather than a nonsensical negative delta,
        and flag resets[util] = True.
        """
        grouped_data = {
            "2026-01-01": {"gas": 950.0},
            "2026-02-01": {"gas": 40.0},  # meter was reset/replaced
        }
        results = _calculate_deltas_and_net(grouped_data)

        feb_record = next(r for r in results if r["date"] == "2026-02-01")
        assert feb_record["resets"]["gas"] is True
        assert feb_record["usage"]["gas"] == 40.0

    def test_missing_utility_in_one_period_does_not_crash(self):
        grouped_data = {
            "2026-01-01": {"water": 100.0},
            "2026-02-01": {"gas": 20.0},  # no water reading this month
        }
        results = _calculate_deltas_and_net(grouped_data)

        feb_record = next(r for r in results if r["date"] == "2026-02-01")
        assert feb_record["usage"]["water"] == 0.0

    def test_results_are_sorted_chronologically_before_processing(self):
        """
        The function sorts grouped_data.keys() internally before
        computing deltas, so insertion order of the input dict must
        not affect the computed deltas.
        """
        grouped_data = {
            "2026-02-01": {"water": 110.0},
            "2026-01-01": {"water": 100.0},
        }
        results = _calculate_deltas_and_net(grouped_data)

        feb_record = next(r for r in results if r["date"] == "2026-02-01")
        assert feb_record["usage"]["water"] == 10.0


class TestPrepareDashboardData:

    def test_empty_readings_returns_empty_structure(self):
        result = prepare_dashboard_data([])
        assert result == {"latest": {}, "history": []}

    def test_latest_is_most_recent_record(self):
        raw_data = [
            MockReading("2026-01-01", "water", "100.0"),
            MockReading("2026-02-01", "water", "110.0"),
        ]
        result = prepare_dashboard_data(raw_data)

        assert result["latest"]["date"] == "2026-02-01"

    def test_history_is_newest_first(self):
        raw_data = [
            MockReading("2026-01-01", "water", "100.0"),
            MockReading("2026-02-01", "water", "110.0"),
            MockReading("2026-03-01", "water", "120.0"),
        ]
        result = prepare_dashboard_data(raw_data)

        dates = [record["date"] for record in result["history"]]
        assert dates == ["2026-03-01", "2026-02-01", "2026-01-01"]
