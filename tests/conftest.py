from datetime import date
from decimal import Decimal

import pytest

from house_simulator import (
    BuyConfig,
    HouseholdConfig,
    MortgageConfig,
    RentConfig,
    SimulationConfig,
    TimelineConfig,
)


@pytest.fixture
def config():
    return SimulationConfig(
        simulation=TimelineConfig(date(2026, 1, 31), date(2027, 1, 31)),
        household=HouseholdConfig(
            starting_wealth=Decimal("100000"),
            monthly_income=Decimal(0),
            cash_reserve=Decimal("100000"),
        ),
        rent=RentConfig(monthly_rent=Decimal(0)),
        buy=BuyConfig(
            purchase_price=Decimal(0),
            down_payment=Decimal(0),
            mortgage=MortgageConfig(annual_rate=Decimal(0), term_years=1),
        ),
    )
