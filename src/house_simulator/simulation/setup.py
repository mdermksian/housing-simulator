"""Compose financial features without coupling their rules to the event loop."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from ..configuration import SimulationConfig
from ..household import HouseholdGrowth, ReserveAllocation
from ..ownership import OwnershipGrowth, configure_ownership
from ..recurring import DatedExpense, add_cash_flow
from ..renting import configure_renting
from .events import Event, Phase
from .state import ScenarioName, ScenarioState, SimulationState

Accrual = Callable[[SimulationState, date, date], SimulationState]
Settlement = Callable[[SimulationState, frozenset[ScenarioName]], SimulationState]


@dataclass(frozen=True)
class Setup:
    state: SimulationState
    events: tuple[Event, ...]
    accruals: tuple[Accrual, ...]
    settle: Settlement


def build_setup(config: SimulationConfig) -> Setup:
    start, end = config.simulation.start, config.simulation.end
    account = ScenarioState(cash=config.household.starting_wealth)
    state = SimulationState(rent=account, buy=account)
    state, owner_events = configure_ownership(state, config.buy, start, end)
    state, renter_events = configure_renting(state, config.rent, start, end)
    events = owner_events + renter_events
    for name in ("rent", "buy"):
        state, income_events = add_cash_flow(
            state,
            scenario=name,
            key="income",
            amount=config.household.monthly_income,
            annual_increase=config.household.annual_income_increase,
            start=start,
            end=end,
            income=True,
        )
        events += income_events
    events += tuple(
        Event(expense.date, Phase.PAYMENT, DatedExpense(expense))
        for expense in config.one_time_expenses
        if expense.amount
    )
    return Setup(
        state,
        events,
        (HouseholdGrowth(config.household), OwnershipGrowth(config.buy, start)),
        ReserveAllocation(config.household.cash_reserve),
    )
