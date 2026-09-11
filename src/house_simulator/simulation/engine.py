"""Advance straight to required updates and commit a whole date atomically."""

from datetime import date
from decimal import Context, localcontext

from ..configuration import SimulationConfig
from .events import Event, EventQueue
from .setup import build_setup
from .state import (
    InsufficientFunds,
    ScenarioName,
    SimulationResult,
    SimulationState,
    Snapshot,
)

ARITHMETIC = Context(prec=40)


class Simulation:
    def __init__(self, config: SimulationConfig) -> None:
        self._config = config
        self._history: list[Snapshot] = []
        self._failure: InsufficientFunds | None = None
        self._date = config.simulation.start
        self._queue = EventQueue(config.simulation.end)
        with localcontext(ARITHMETIC):
            setup = build_setup(config)
            self._state = setup.state
            self._accruals = setup.accruals
            self._settle = setup.settle
            for event in setup.events:
                self._queue.schedule(event)
            # Opening transactions and any explicit start-date bills belong to
            # the initial snapshot, before the first call to step().
            self._commit_date(self._date, frozenset(("rent", "buy")))

    @property
    def config(self) -> SimulationConfig:
        return self._config

    @property
    def state(self) -> SimulationState:
        return self._state

    @property
    def current_date(self) -> date:
        return self._date

    @property
    def history(self) -> tuple[Snapshot, ...]:
        return tuple(self._history)

    @property
    def completed(self) -> bool:
        return self._date == self.config.simulation.end and self._failure is None

    @property
    def result(self) -> SimulationResult:
        return SimulationResult(self.history, self.completed, self._failure)

    def schedule(self, event: Event) -> None:
        """Add a Python domain action strictly after the last committed date.

        Actions must be pure: effects and future events are staged until the
        entire date succeeds. Events beyond the configured horizon are ignored.
        """
        if self._failure is not None or self.completed:
            raise RuntimeError("Cannot schedule events on a finished simulation")
        self._queue.schedule(event, after=self.current_date)

    def _commit_date(
        self, on: date, settle: frozenset[ScenarioName] = frozenset()
    ) -> Snapshot:
        state = self._state
        queue = self._queue.copy()
        for accrue in self._accruals:
            state = accrue(state, self.current_date, on)
        for event in queue.pop_on(on):
            effect = event.action.apply(state, on)
            state = effect.state
            settle |= effect.settle
            for successor in effect.successors:
                queue.schedule(successor, after=on)
        state = self._settle(state, settle)
        snapshot = Snapshot(on, (on - self.config.simulation.start).days, state)
        self._state, self._queue, self._date = state, queue, on
        self._history.append(snapshot)
        return snapshot

    def step(self) -> Snapshot | None:
        if self._failure is not None:
            raise self._failure
        if self.completed:
            return None
        try:
            with localcontext(ARITHMETIC):
                return self._commit_date(self._queue.next_date)
        except InsufficientFunds as exc:
            self._failure = exc
            raise

    def run(self) -> SimulationResult:
        while self.step() is not None:
            pass
        return self.result
