"""Immutable public snapshots; no domain action mutates committed history."""

from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from typing import Literal

ZERO = Decimal(0)
ScenarioName = Literal["rent", "buy"]


@dataclass(frozen=True)
class ScenarioState:
    cash: Decimal = ZERO
    investments: Decimal = ZERO
    home_value: Decimal = ZERO
    mortgage_principal: Decimal = ZERO
    accrued_mortgage_interest: Decimal = ZERO
    selling_cost_fraction: Decimal = ZERO
    cumulative_income: Decimal = ZERO
    cumulative_housing_cash_outflows: Decimal = ZERO
    cumulative_housing_expenses: Decimal = ZERO
    amounts: tuple[tuple[str, Decimal], ...] = ()

    @property
    def equity(self) -> Decimal:
        return self.home_value - self.mortgage_principal

    @property
    def net_worth(self) -> Decimal:
        return (
            self.cash + self.investments + self.equity - self.accrued_mortgage_interest
        )

    @property
    def net_worth_after_selling_costs(self) -> Decimal:
        return self.net_worth - self.home_value * self.selling_cost_fraction

    def amount(self, key: str) -> Decimal:
        return dict(self.amounts)[key]

    def with_amount(self, key: str, amount: Decimal) -> "ScenarioState":
        amounts = dict(self.amounts)
        amounts[key] = amount
        return replace(self, amounts=tuple(amounts.items()))


@dataclass(frozen=True)
class SimulationState:
    rent: ScenarioState
    buy: ScenarioState

    def scenario(self, name: ScenarioName) -> ScenarioState:
        return getattr(self, name)

    def with_scenario(
        self, name: ScenarioName, value: ScenarioState
    ) -> "SimulationState":
        return replace(self, **{name: value})


@dataclass(frozen=True)
class Snapshot:
    date: date
    elapsed_days: int
    state: SimulationState

    @property
    def net_worth_difference(self) -> Decimal:
        return self.state.buy.net_worth - self.state.rent.net_worth

    @property
    def net_worth_after_selling_costs_difference(self) -> Decimal:
        return (
            self.state.buy.net_worth_after_selling_costs
            - self.state.rent.net_worth_after_selling_costs
        )


@dataclass(frozen=True)
class SimulationResult:
    snapshots: tuple[Snapshot, ...]
    completed: bool
    failure: "InsufficientFunds | None" = None


class InsufficientFunds(Exception):
    """A failed obligation. The simulator retains its last committed date."""

    def __init__(
        self,
        scenario: ScenarioName,
        on: date,
        required: Decimal,
        available: Decimal,
        obligation: str,
    ) -> None:
        self.scenario = scenario
        self.date = on
        self.required = required
        self.available = available
        self.obligation = obligation
        super().__init__(
            f"{scenario} on {on}: {obligation} requires {required:.2f}, "
            f"but only {available:.2f} is available"
        )
