"""Rent payments, rent increases, and renter-specific recurring expenses."""

from datetime import date

from .configuration import RentConfig
from .recurring import add_cash_flow, add_expenses
from .simulation.events import Event
from .simulation.state import SimulationState


def configure_renting(
    state: SimulationState, config: RentConfig, start: date, end: date
) -> tuple[SimulationState, tuple[Event, ...]]:
    state, rent_events = add_cash_flow(
        state,
        scenario="rent",
        key="rent",
        amount=config.monthly_rent,
        annual_increase=config.annual_increase,
        start=start,
        end=end,
    )
    state, expense_events = add_expenses(state, "rent", config.expenses, start, end)
    return state, rent_events + expense_events
