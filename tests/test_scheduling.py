from dataclasses import FrozenInstanceError, dataclass, replace
from datetime import date
from decimal import Decimal

import pytest

from house_simulator import (
    OneTimeExpense,
    RecurringExpense,
    Simulation,
    TimelineConfig,
)
from house_simulator.simulation.calendar import add_months
from house_simulator.simulation.events import Effect, Event, EventQueue, Phase


@dataclass(frozen=True)
class Observe:
    def apply(self, state, on):
        return Effect(state)


@pytest.mark.parametrize(
    ("anchor", "offset", "expected"),
    [
        (date(2026, 1, 31), 1, date(2026, 2, 28)),
        (date(2026, 1, 31), 2, date(2026, 3, 31)),
        (date(2024, 1, 31), 1, date(2024, 2, 29)),
        (date(2024, 2, 29), 12, date(2025, 2, 28)),
        (date(2024, 2, 29), 48, date(2028, 2, 29)),
    ],
)
def test_calendar_anchors(anchor, offset, expected):
    assert add_months(anchor, offset) == expected


def test_empty_simulation_only_has_initial_and_final(config):
    simulator = Simulation(config)
    assert len(simulator.history) == 1
    assert simulator.step().date == config.simulation.end
    assert simulator.step() is None
    assert simulator.completed


def test_monthly_steps_and_partial_final_date(config):
    config = replace(
        config,
        simulation=TimelineConfig(date(2026, 1, 31), date(2026, 4, 15)),
        rent=replace(config.rent, monthly_rent="100"),
    )
    snapshots = Simulation(config).run().snapshots
    assert [item.date for item in snapshots] == [
        date(2026, 1, 31),
        date(2026, 2, 28),
        date(2026, 3, 31),
        date(2026, 4, 15),
    ]
    assert snapshots[-1].state.rent.cumulative_housing_cash_outflows == 200


def test_yearly_only_has_no_monthly_steps_and_uses_anniversary_increase(config):
    config = replace(
        config,
        simulation=replace(config.simulation, end=date(2028, 1, 31)),
        rent=replace(
            config.rent,
            expenses=(RecurringExpense("insurance", "100", "yearly", "0.1"),),
        ),
    )
    snapshots = Simulation(config).run().snapshots
    assert [item.date for item in snapshots] == [
        date(2026, 1, 31),
        date(2027, 1, 31),
        date(2028, 1, 31),
    ]
    assert snapshots[-1].state.rent.cumulative_housing_expenses == 231


def test_mixed_schedules_and_one_time_expenses(config):
    config = replace(
        config,
        rent=replace(config.rent, monthly_rent="100"),
        buy=replace(
            config.buy,
            expenses=(
                RecurringExpense("tax", "300", "yearly", first_due=date(2026, 6, 1)),
            ),
        ),
        one_time_expenses=(
            OneTimeExpense("repair", date(2026, 6, 15), "200", "buy"),
            OneTimeExpense("moving", date(2026, 2, 28), "10", "both"),
            OneTimeExpense("zero", date(2026, 8, 10), "0"),
        ),
    )
    snapshots = Simulation(config).run().snapshots
    dates = [item.date for item in snapshots]
    assert len(dates) == 15
    assert dates.count(date(2026, 2, 28)) == 1
    assert date(2026, 6, 1) in dates
    assert date(2026, 6, 15) in dates
    assert date(2026, 8, 10) not in dates
    assert snapshots[-1].state.buy.cumulative_housing_cash_outflows == 510
    assert snapshots[-1].state.rent.cumulative_housing_cash_outflows == 1210


def test_explicit_month_end_anchor_does_not_drift(config):
    config = replace(
        config,
        simulation=TimelineConfig(date(2024, 1, 1), date(2024, 4, 30)),
        rent=replace(
            config.rent,
            expenses=(RecurringExpense("bill", "10", first_due=date(2024, 1, 31)),),
        ),
    )
    assert [s.date for s in Simulation(config).run().snapshots] == [
        date(2024, 1, 1),
        date(2024, 1, 31),
        date(2024, 2, 29),
        date(2024, 3, 31),
        date(2024, 4, 30),
    ]


def test_opening_date_expenses_included_in_initial_snapshot(config):
    config = replace(
        config,
        one_time_expenses=(
            OneTimeExpense("moving", config.simulation.start, "30", "rent"),
        ),
        rent=replace(
            config.rent,
            expenses=(
                RecurringExpense("bill", "20", first_due=config.simulation.start),
            ),
        ),
    )
    simulator = Simulation(config)
    assert simulator.history[0].state.rent.cash == 99950
    assert simulator.step().date == date(2026, 2, 28)


def test_anniversary_adjustments_precede_income_and_bills(config):
    config = replace(
        config,
        household=replace(
            config.household,
            starting_wealth="0",
            monthly_income="100",
            annual_income_increase="0.1",
        ),
        rent=replace(config.rent, monthly_rent="100", annual_increase="0.1"),
    )
    final = Simulation(config).run().snapshots[-1]
    assert final.state.rent.cash == 0
    assert final.state.rent.cumulative_income == 1210
    assert final.state.rent.cumulative_housing_cash_outflows == 1210
    assert final.state.rent.amount("rent") == 110


def test_annual_adjustment_gets_own_date_when_payment_is_off_cycle(config):
    config = replace(
        config,
        rent=replace(
            config.rent,
            expenses=(
                RecurringExpense("bill", "100", "yearly", "0.1", date(2026, 6, 1)),
            ),
        ),
        simulation=replace(config.simulation, end=date(2027, 6, 1)),
    )
    snapshots = Simulation(config).run().snapshots
    assert [s.date for s in snapshots] == [
        date(2026, 1, 31),
        date(2026, 6, 1),
        date(2027, 1, 31),
        date(2027, 6, 1),
    ]
    assert snapshots[-1].state.rent.cumulative_housing_cash_outflows == 210


def test_queue_phase_then_insertion_order_and_horizon():
    on = date(2026, 2, 1)
    queue = EventQueue(on)
    payment1 = Event(on, Phase.PAYMENT, Observe())
    payment2 = Event(on, Phase.PAYMENT, Observe())
    income = Event(on, Phase.INCOME, Observe())
    adjustment = Event(on, Phase.ADJUSTMENT, Observe())
    for event in (payment1, income, payment2, adjustment):
        queue.schedule(event)
    queue.schedule(Event(date(2026, 3, 1), Phase.PAYMENT, Observe()))
    events = queue.pop_on(on)
    assert events == (adjustment, income, payment1, payment2)
    assert events[2] is payment1
    assert events[3] is payment2


@pytest.mark.parametrize("offset", [-1, 0])
def test_scheduler_rejects_nonfuture_events(config, offset):
    simulator = Simulation(config)
    on = date(2026, 1, 31 + offset)
    with pytest.raises(ValueError, match="strictly after"):
        simulator.schedule(Event(on, Phase.PAYMENT, Observe()))


def test_invalid_successor_rolls_back_date(config):
    @dataclass(frozen=True)
    class InvalidSuccessor:
        def apply(self, state, on):
            return Effect(state, (Event(on, Phase.PAYMENT, self),))

    simulator = Simulation(config)
    before = simulator.result
    simulator.schedule(Event(date(2026, 2, 1), Phase.PAYMENT, InvalidSuccessor()))
    with pytest.raises(ValueError, match="strictly after"):
        simulator.step()
    assert simulator.result == before


def test_step_run_equivalence_and_history_is_immutable(config):
    config = replace(config, rent=replace(config.rent, monthly_rent="100"))
    expected = Simulation(config).run()
    stepped = Simulation(config)
    initial = stepped.history
    stepped.step()
    stepped.step()
    assert stepped.run() == expected
    assert len(initial) == 1
    assert initial[0].state.rent.cash == Decimal("100000")
    assert stepped.run() == expected
    with pytest.raises(FrozenInstanceError):
        initial[0].state.rent.cash = Decimal(0)
    with pytest.raises(AttributeError):
        stepped.state = initial[0].state
    with pytest.raises(RuntimeError, match="finished"):
        stepped.schedule(Event(date(2027, 2, 1), Phase.PAYMENT, Observe()))
