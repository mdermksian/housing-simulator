"""Household cash flow, investment allocation, and elapsed-time returns."""

from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal

from .configuration import HouseholdConfig
from .simulation.state import (
    ZERO,
    InsufficientFunds,
    ScenarioName,
    ScenarioState,
    SimulationState,
)


def grow(value: Decimal, annual_rate: Decimal, days: int) -> Decimal:
    if not value or not annual_rate or not days:
        return value
    return value * (1 + annual_rate) ** (Decimal(days) / 365)


def allocate_reserve(state: ScenarioState, reserve: Decimal) -> ScenarioState:
    surplus = max(ZERO, state.cash - reserve)
    return replace(
        state, cash=state.cash - surplus, investments=state.investments + surplus
    )


def receive_income(state: ScenarioState, amount: Decimal) -> ScenarioState:
    return replace(
        state,
        cash=state.cash + amount,
        cumulative_income=state.cumulative_income + amount,
    )


def pay(
    state: ScenarioState,
    amount: Decimal,
    *,
    scenario: ScenarioName,
    on: date,
    obligation: str,
    expense: Decimal | None = None,
) -> ScenarioState:
    """Fund a housing payment from cash, then investments; never borrow cash.

    ``expense`` separates consumed wealth from principal/down-payment transfers.
    """
    available = state.cash + state.investments
    if amount > available:
        raise InsufficientFunds(scenario, on, amount, available, obligation)
    sale = max(ZERO, amount - state.cash)
    return replace(
        state,
        cash=state.cash + sale - amount,
        investments=state.investments - sale,
        cumulative_housing_cash_outflows=(
            state.cumulative_housing_cash_outflows + amount
        ),
        cumulative_housing_expenses=(
            state.cumulative_housing_expenses + (amount if expense is None else expense)
        ),
    )


@dataclass(frozen=True)
class HouseholdGrowth:
    policy: HouseholdConfig

    def __call__(
        self, state: SimulationState, start: date, end: date
    ) -> SimulationState:
        days = (end - start).days
        for name in ("rent", "buy"):
            account = state.scenario(name)
            state = state.with_scenario(
                name,
                replace(
                    account,
                    cash=grow(account.cash, self.policy.savings_return, days),
                    investments=grow(
                        account.investments, self.policy.investment_return, days
                    ),
                ),
            )
        return state


@dataclass(frozen=True)
class ReserveAllocation:
    reserve: Decimal

    def __call__(
        self, state: SimulationState, scenarios: frozenset[ScenarioName]
    ) -> SimulationState:
        for name in ("rent", "buy"):
            if name in scenarios:
                state = state.with_scenario(
                    name, allocate_reserve(state.scenario(name), self.reserve)
                )
        return state
