"""Purchase accounting, fixed-rate mortgages, appreciation, and owner expenses."""

from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal

from .configuration import BuyConfig
from .household import grow, pay
from .recurring import Recurrence, add_expenses
from .simulation.calendar import period_bounds
from .simulation.events import Effect, Event, Phase
from .simulation.state import ZERO, SimulationState


def mortgage_payment(principal: Decimal, annual_rate: Decimal, months: int) -> Decimal:
    """Unrounded level monthly payment; the final payment clears any residue."""
    if months <= 0 or principal < 0 or annual_rate < 0:
        raise ValueError("Mortgage requires nonnegative amounts and positive months")
    if not annual_rate:
        return principal / months
    rate = annual_rate / 12
    return principal * rate / (1 - (1 + rate) ** -months)


@dataclass(frozen=True)
class MortgagePayment:
    amount: Decimal
    term_months: int
    recurrence: Recurrence

    def event(self) -> tuple[Event, ...]:
        on = self.recurrence.date
        return (Event(on, Phase.PAYMENT, self),) if on is not None else ()

    def apply(self, state: SimulationState, on: date) -> Effect:
        account = state.buy
        debt = account.mortgage_principal + account.accrued_mortgage_interest
        amount = min(self.amount, debt)
        if self.recurrence.index == self.term_months:
            amount = debt
        interest_paid = min(amount, account.accrued_mortgage_interest)
        account = pay(
            account,
            amount,
            scenario="buy",
            on=on,
            obligation="mortgage",
            expense=interest_paid,
        )
        account = replace(
            account,
            mortgage_principal=(
                ZERO
                if amount == debt
                else account.mortgage_principal - (amount - interest_paid)
            ),
            accrued_mortgage_interest=(
                ZERO
                if amount == debt
                else account.accrued_mortgage_interest - interest_paid
            ),
        )
        successor = replace(self, recurrence=self.recurrence.next())
        events = successor.event() if account.mortgage_principal else ()
        return Effect(replace(state, buy=account), events, frozenset(("buy",)))


@dataclass(frozen=True)
class OwnershipGrowth:
    config: BuyConfig
    anchor: date

    def __call__(
        self, state: SimulationState, start: date, end: date
    ) -> SimulationState:
        account = state.buy
        days = (end - start).days
        interest = ZERO
        if account.mortgage_principal and self.config.mortgage.annual_rate and days:
            period_start, period_end = period_bounds(self.anchor, start)
            if end > period_end:
                raise ValueError("Mortgage accrual cannot skip a payment boundary")
            interest = (
                account.mortgage_principal
                * self.config.mortgage.annual_rate
                / 12
                * Decimal(days)
                / Decimal((period_end - period_start).days)
            )
        return replace(
            state,
            buy=replace(
                account,
                home_value=grow(account.home_value, self.config.appreciation, days),
                accrued_mortgage_interest=account.accrued_mortgage_interest + interest,
            ),
        )


def configure_ownership(
    state: SimulationState, config: BuyConfig, start: date, end: date
) -> tuple[SimulationState, tuple[Event, ...]]:
    account = pay(
        state.buy,
        config.down_payment + config.purchase_closing_costs,
        scenario="buy",
        on=start,
        obligation="purchase",
        expense=config.purchase_closing_costs,
    )
    principal = config.purchase_price - config.down_payment
    state = replace(
        state,
        buy=replace(
            account,
            home_value=config.purchase_price,
            mortgage_principal=principal,
            selling_cost_fraction=config.selling_cost_fraction,
        ),
    )
    events = ()
    if principal:
        months = config.mortgage.term_years * 12
        events = MortgagePayment(
            mortgage_payment(principal, config.mortgage.annual_rate, months),
            months,
            Recurrence(start, 1, 1, end),
        ).event()
    state, expense_events = add_expenses(state, "buy", config.expenses, start, end)
    return state, events + expense_events
