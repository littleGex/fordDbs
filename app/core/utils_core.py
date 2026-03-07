from collections import defaultdict
from datetime import datetime
from typing import List, Dict, Any


def _parse_reading_value(value: str) -> float:
    """Safely casts a string reading to a float."""
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0


def _group_readings_by_date(
        raw_readings: List[Any]) -> Dict[str, Dict[str, float]]:
    """Pivots narrow DB rows into a dictionary grouped by date."""
    grouped_data = defaultdict(dict)

    for row in raw_readings:
        # Handle both datetime objects and strings
        date_str = row.reading_date.strftime("%Y-%m-%d") if isinstance(
            row.reading_date, datetime) else str(
            row.reading_date)
        grouped_data[date_str][row.utility_name] = _parse_reading_value(
            row.reading_value)

    return grouped_data


def _calculate_deltas_and_net(
        grouped_data: Dict[str, Dict[str, float]]) -> List[Dict[str, Any]]:
    """
    Calculates usage (deltas) and net electricity from chronological readings.
    """
    # Sort chronologically to ensure accurate delta calculation
    sorted_dates = sorted(grouped_data.keys())
    processed_records = []
    previous_readings = {}

    for date_str in sorted_dates:
        current_readings = grouped_data[date_str]

        record = {
            "date": date_str,
            "is_february": date_str.split("-")[1] == "02",
            "readings": current_readings,
            "usage": {}
        }

        # Calculate difference from the previous reading
        for util in ["water", "gas", "elect_p", "elect_u"]:
            current_val = current_readings.get(util)
            prev_val = previous_readings.get(util)

            if current_val is not None and prev_val is not None:
                record["usage"][util] = round(current_val - prev_val, 2)
            else:
                record["usage"][util] = 0.0

            if current_val is not None:
                previous_readings[util] = current_val

        # Calculate Net Electricity
        elect_used = record["usage"].get("elect_u", 0.0)
        elect_prod = record["usage"].get("elect_p", 0.0)
        record["usage"]["net_elect"] = round(elect_used - elect_prod, 2)

        processed_records.append(record)

    return processed_records


def prepare_dashboard_data(
        raw_readings: List[Any]) -> Dict[str, Any]:
    """
    Orchestrates the transformation of raw utility readings into
    dashboard data.
    """
    if not raw_readings:
        return {"latest": {}, "history": []}

    # 1. Group the raw data
    grouped_data = _group_readings_by_date(raw_readings)

    # 2. Perform calculations
    history_records = _calculate_deltas_and_net(grouped_data)

    # 3. Format output (reverse so the newest is at index 0 for the UI)
    history_records.reverse()

    return {
        "latest": history_records[0] if history_records else {},
        "history": history_records
    }
