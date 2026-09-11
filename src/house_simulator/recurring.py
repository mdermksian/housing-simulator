"""Shared billing behavior used by rent, owner expenses, and household income."""

from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal

from .configuration import OneTimeExpense, RecurringExpense
from .household import pay, receive_income
from .simulation.calendar import occurrence
from .simulation.events import Effect, Event, Phase
from .simulation.state import ScenarioName, SimulationState


@dataclass(frozen=True)
class Recurrence:
    anchor: date
    months: int
    index: int
    end: date

    @property
    def date(self) -> date | None:
        return occurrence(self.anchor, self.months * self.index, self.end)

    def next(self) -> "Recurrence":
        return replace(self, index=self.index + 1)


@dataclass(frozen=True)
class ScheduledPayment:
    scenario: ScenarioName
    key: str
    recurrence: Recurrence
    income: bool = False

    def event(self) -> tuple[Event, ...]:
        on = self.recurrence.date
        phase = Phase.INCOME if self.income else Phase.PAYMENT
        return (Event(on, phase, self),) if on is not None else ()

    def apply(self, state: SimulationState, on: date) -> Effect:
        account = state.scenario(self.scenario)
        amount = account.amount(self.key)
        if self.income:
            account = receive_income(account, amount)
        else:
            account = pay(
                account, amount, scenario=self.scenario, on=on, obligation=self.key
            )
        successor = replace(self, recurrence=self.recurrence.next())
        return Effect(
            state.with_scenario(self.scenario, account),
            successor.event(),
            frozenset((self.scenario,)),
        )


@dataclass(frozen=True)
class AnnualIncrease:
    scenario: ScenarioName
    key: str
    rate: Decimal
    recurrence: Recurrence

    def event(self) -> tuple[Event, ...]:
        on = self.recurrence.date
        return (Event(on, Phase.ADJUSTMENT, self),) if on is not None else ()

    def apply(self, state: SimulationState, on: date) -> Effect:
        account = state.scenario(self.scenario)
        account = account.with_amount(
            self.key, account.amount(self.key) * (1 + self.rate)
        )
        successor = replace(self, recurrence=self.recurrence.next())
        return Effect(state.with_scenario(self.scenario, account), successor.event())


def add_cash_flow(
    state: SimulationState,
    *,
    scenario: ScenarioName,
    key: str,
    amount: Decimal,
    annual_increase: Decimal,
    start: date,
    end: date,
    months: int = 1,
    first_due: date | None = None,
    income: bool = False,
) -> tuple[SimulationState, tuple[Event, ...]]:
    account = state.scenario(scenario).with_amount(key, amount)
    state = state.with_scenario(scenario, account)
    if not amount:
        return state, ()
    recurrence = Recurrence(
        anchor=first_due if first_due is not None else start,
        months=months,
        index=0 if first_due is not None else 1,
        end=end,
    )
    events = ScheduledPayment(scenario, key, recurrence, income).event()
    if annual_increase:
        events += AnnualIncrease(
            scenario, key, annual_increase, Recurrence(start, 12, 1, end)
        ).event()
    return state, events


def add_expenses(
    state: SimulationState,
    scenario: ScenarioName,
    expenses: tuple[RecurringExpense, ...],
    start: date,
    end: date,
) -> tuple[SimulationState, tuple[Event, ...]]:
    events = ()
    for expense in expenses:
        state, added = add_cash_flow(
            state,
            scenario=scenario,
            key=f"expense:{expense.name}",
            amount=expense.amount,
            annual_increase=expense.annual_increase,
            start=start,
            end=end,
            months=1 if expense.schedule == "monthly" else 12,
            first_due=expense.first_due,
        )
        events += added
    return state, events


@dataclass(frozen=True)
class DatedExpense:
    config: OneTimeExpense

    def apply(self, state: SimulationState, on: date) -> Effect:
        scenarios = (
            ("rent", "buy") if self.config.target == "both" else (self.config.target,)
        )
        for name in scenarios:
            account = pay(
                state.scenario(name),
                self.config.amount,
                scenario=name,
                on=on,
                obligation=self.config.name,
            )
            state = state.with_scenario(name, account)
        return Effect(state, settle=frozenset(scenarios))
