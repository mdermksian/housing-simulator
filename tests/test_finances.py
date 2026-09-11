from dataclasses import replace
from datetime import date
from decimal import Decimal, localcontext

import pytest

from house_simulator import (
    InsufficientFunds,
    MortgageConfig,
    OneTimeExpense,
    Simulation,
    TimelineConfig,
)
from house_simulator.household import grow
from house_simulator.ownership import mortgage_payment
from house_simulator.simulation.engine import ARITHMETIC
from house_simulator.simulation.events import Effect, Event, Phase


def test_opening_accounting_and_estimated_selling_costs(config):
    config = replace(
        config,
        household=replace(config.household, cash_reserve="10000"),
        buy=replace(
            config.buy,
            purchase_price="200000",
            down_payment="40000",
            purchase_closing_costs="5000",
            selling_cost_fraction="0.06",
        ),
    )
    state = Simulation(config).state
    assert state.rent.cash == 10000
    assert state.rent.investments == 90000
    assert state.rent.net_worth == 100000
    assert state.buy.cash == 10000
    assert state.buy.investments == 45000
    assert state.buy.mortgage_principal == 160000
    assert state.buy.equity == 40000
    assert state.buy.net_worth == 95000
    assert state.buy.net_worth_after_selling_costs == 83000
    assert state.buy.cumulative_housing_cash_outflows == 45000
    assert state.buy.cumulative_housing_expenses == 5000


def test_payments_can_use_reserve_then_sell_investments(config):
    config = replace(
        config,
        simulation=replace(config.simulation, end=date(2026, 2, 28)),
        household=replace(config.household, starting_wealth="1000", cash_reserve="100"),
        rent=replace(config.rent, monthly_rent="150"),
    )
    state = Simulation(config).run().snapshots[-1].state.rent
    assert state.cash == 0
    assert state.investments == 850
    assert state.cumulative_housing_expenses == 150


def test_surplus_invested_once_after_all_transactions(config):
    config = replace(
        config,
        simulation=replace(config.simulation, end=date(2026, 2, 28)),
        household=replace(
            config.household,
            starting_wealth="100",
            cash_reserve="100",
            monthly_income="300",
        ),
        rent=replace(config.rent, monthly_rent="150"),
    )
    state = Simulation(config).run().snapshots[-1].state.rent
    assert state.cash == 100
    assert state.investments == 150


def test_insolvency_rolls_back_both_scenarios_and_stops(config):
    config = replace(
        config,
        household=replace(config.household, starting_wealth="100", monthly_income="50"),
        rent=replace(config.rent, monthly_rent="200"),
        buy=replace(config.buy, purchase_price="120", down_payment="0"),
    )
    simulator = Simulation(config)
    initial = simulator.history
    with pytest.raises(InsufficientFunds) as failure:
        simulator.step()
    error = failure.value
    assert error.scenario == "rent"
    assert error.date == date(2026, 2, 28)
    assert error.required == 200
    assert error.available == 150
    assert simulator.history == initial
    assert simulator.state.buy.mortgage_principal == 120
    assert simulator.state.buy.cumulative_income == 0
    assert simulator.result.failure is error
    assert not simulator.completed
    with pytest.raises(InsufficientFunds) as again:
        simulator.run()
    assert again.value is error


def test_failure_after_success_retains_only_committed_dates(config):
    config = replace(
        config,
        household=replace(config.household, starting_wealth="250"),
        rent=replace(config.rent, monthly_rent="100"),
    )
    simulator = Simulation(config)
    with pytest.raises(InsufficientFunds):
        simulator.run()
    assert simulator.current_date == date(2026, 3, 31)
    assert len(simulator.history) == 3
    assert simulator.state.rent.cash == 50


def test_monthly_mortgage_payment_known_value():
    assert mortgage_payment(Decimal(100000), Decimal("0.06"), 360).quantize(
        Decimal("0.01")
    ) == Decimal("599.55")


@pytest.mark.parametrize("annual_rate", ["0", "0.06"])
def test_mortgage_amortization_and_payoff(config, annual_rate):
    config = replace(
        config,
        buy=replace(
            config.buy,
            purchase_price="1200",
            down_payment="0",
            mortgage=MortgageConfig(annual_rate, 1),
        ),
        simulation=replace(config.simulation, end=date(2028, 1, 31)),
    )
    result = Simulation(config).run()
    final = result.snapshots[-1].state.buy
    # Initial + twelve payments + the later terminal boundary, no paid-off ticks.
    assert len(result.snapshots) == 14
    assert final.mortgage_principal == 0
    assert final.accrued_mortgage_interest == 0
    assert final.equity == 1200
    assert final.net_worth == pytest.approx(
        Decimal(100000) - final.cumulative_housing_expenses, abs=Decimal("1e-20")
    )
    if annual_rate == "0":
        assert final.cumulative_housing_cash_outflows == 1200
        assert final.cumulative_housing_expenses == 0
    else:
        first = result.snapshots[1].state.buy
        assert first.cumulative_housing_expenses == Decimal("6")
        assert first.mortgage_principal < 1200
        assert final.cumulative_housing_expenses > 0


def test_final_partial_month_interest_is_a_liability(config):
    config = replace(
        config,
        simulation=TimelineConfig(date(2026, 1, 31), date(2026, 2, 14)),
        buy=replace(
            config.buy,
            purchase_price="1200",
            down_payment="0",
            mortgage=MortgageConfig("0.12", 1),
        ),
    )
    final = Simulation(config).run().snapshots[-1].state.buy
    assert final.accrued_mortgage_interest == 6
    assert final.mortgage_principal == 1200
    assert final.net_worth == 99994
    assert final.cumulative_housing_cash_outflows == 0


def test_long_mortgage_payoff_clears_decimal_residue(config):
    config = replace(
        config,
        household=replace(config.household, starting_wealth="500000"),
        simulation=replace(config.simulation, end=date(2057, 1, 31)),
        buy=replace(
            config.buy,
            purchase_price="123456.78",
            down_payment="0",
            mortgage=MortgageConfig("0.0658", 30),
        ),
    )
    snapshots = Simulation(config).run().snapshots
    assert len(snapshots) == 362
    assert snapshots[-2].date == date(2056, 1, 31)
    assert snapshots[-1].state.buy.mortgage_principal == 0
    assert snapshots[-1].state.buy.accrued_mortgage_interest == 0


def test_growth_uses_elapsed_days_and_allows_losses():
    assert grow(Decimal(100), Decimal("0.1"), 365) == 110
    assert grow(Decimal(100), Decimal("-0.1"), 365) == 90
    assert grow(Decimal(0), Decimal("0.1"), 365) == 0


def test_observation_does_not_change_growth_or_mortgage(config):
    class Observe:
        def apply(self, state, on):
            return Effect(state)

    config = replace(
        config,
        household=replace(
            config.household,
            cash_reserve="10000",
            savings_return="0.03",
            investment_return="0.07",
        ),
        buy=replace(
            config.buy,
            purchase_price="12000",
            down_payment="2000",
            mortgage=MortgageConfig("0.06", 1),
            appreciation="0.04",
        ),
    )
    expected = Simulation(config).run().snapshots[-1].state
    observed = Simulation(config)
    for on in (date(2026, 2, 7), date(2026, 2, 14), date(2026, 5, 8)):
        observed.schedule(Event(on, Phase.ADJUSTMENT, Observe()))
    actual = observed.run().snapshots[-1].state
    for name in ("rent", "buy"):
        for metric in (
            "cash",
            "investments",
            "home_value",
            "mortgage_principal",
            "accrued_mortgage_interest",
            "net_worth",
        ):
            assert getattr(actual.scenario(name), metric) == pytest.approx(
                getattr(expected.scenario(name), metric), abs=Decimal("1e-20")
            )


def test_unrelated_buyer_expense_does_not_rebalance_renter(config):
    config = replace(
        config,
        household=replace(
            config.household,
            cash_reserve="10000",
            savings_return="0.03",
            investment_return="0.07",
        ),
    )
    expected = Simulation(config).run().snapshots[-1].state.rent
    config = replace(
        config,
        one_time_expenses=(OneTimeExpense("repair", date(2026, 6, 15), "100", "buy"),),
    )
    actual = Simulation(config).run().snapshots[-1].state.rent
    assert actual.cash == pytest.approx(expected.cash, abs=Decimal("1e-20"))
    assert actual.investments == pytest.approx(
        expected.investments, abs=Decimal("1e-20")
    )
    assert actual.cash > config.household.cash_reserve


def test_arithmetic_does_not_depend_on_callers_decimal_context(config):
    config = replace(
        config,
        household=replace(config.household, investment_return="0.07", cash_reserve="0"),
    )
    expected = Simulation(config).run()
    with localcontext() as context:
        context.prec = 6
        actual = Simulation(config).run()
    assert actual == expected
    assert ARITHMETIC.prec == 40
