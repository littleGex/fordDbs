from datetime import date
from app.core.scheduler import calculate_age


def test_age_calculation_logic():
    # Scenario: Child born Nov 1, 2015
    dob = date(2015, 11, 1)

    # Test Case A: Date is Feb 1, 2026 (Still 10 years old)
    today_feb = date(2026, 2, 1)
    age_feb = calculate_age(dob, reference_date=today_feb)
    assert age_feb == 10
    assert (age_feb * 0.5) == 5.0

    # Test Case B: Date is Nov 2, 2026 (Now 11 years old)
    today_nov = date(2026, 11, 2)
    age_nov = calculate_age(dob, reference_date=today_nov)
    assert age_nov == 11
    assert (age_nov * 0.5) == 5.5
