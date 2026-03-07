import pytest
from app.core.utils_core import (
    _parse_reading_value,
    _group_readings_by_date,
    _calculate_deltas_and_net
)


# Mock object to simulate SQLAlchemy row results
class MockReading:
    def __init__(self, reading_date, utility_name, reading_value):
        self.reading_date = reading_date
        self.utility_name = utility_name
        self.reading_value = reading_value


def test_parse_reading_value():
    """Verify string to float conversion and error handling."""
    assert _parse_reading_value("123.45") == 123.45
    assert _parse_reading_value("invalid") == 0.0
    assert _parse_reading_value(None) == 0.0


def test_group_readings_by_date():
    """Verify that multiple narrow rows are pivoted into a single date group."""
    raw_data = [
        MockReading("2026-01-01", "water", "100.0"),
        MockReading("2026-01-01", "gas", "50.0"),
        MockReading("2026-02-01", "water", "110.0")
    ]
    grouped = _group_readings_by_date(raw_data)

    assert "2026-01-01" in grouped
    assert grouped["2026-01-01"]["water"] == 100.0
    assert grouped["2026-01-01"]["gas"] == 50.0
    assert grouped["2026-02-01"]["water"] == 110.0


def test_calculate_deltas_and_net():
    """Verify that usage (deltas) and net electricity are calculated correctly."""
    grouped_data = {
        "2026-01-01": {
            "water": 100.0,
            "elect_u": 50.0,
            "elect_p": 10.0
        },
        "2026-02-01": {
            "water": 110.0,
            "elect_u": 65.0,
            "elect_p": 20.0
        }
    }

    results = _calculate_deltas_and_net(grouped_data)

    # The result should be sorted chronologically internally
    feb_record = results[1]  # Feb is the second entry

    # Water Delta: 110 - 100 = 10
    assert feb_record["usage"]["water"] == 10.0

    # Elect Usage Delta: 65 - 50 = 15
    # Elect Produced Delta: 20 - 10 = 10
    # Net: 15 - 10 = 5
    assert feb_record["usage"]["net_elect"] == 5.0
    assert feb_record["is_february"] is True


def test_calculate_deltas_first_entry():
    """Verify the first entry results in 0.0 usage (baseline)."""
    grouped_data = {"2026-01-01": {"water": 100.0}}
    results = _calculate_deltas_and_net(grouped_data)

    assert results[0]["usage"]["water"] == 0.0
