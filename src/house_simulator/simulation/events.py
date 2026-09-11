"""Domain-independent actions and a deterministic, bounded event queue."""

import heapq
from dataclasses import dataclass, field
from datetime import date
from enum import IntEnum
from typing import Protocol

from .state import ScenarioName, SimulationState


class Phase(IntEnum):
    ADJUSTMENT = 0
    INCOME = 1
    PAYMENT = 2


class Action(Protocol):
    def apply(self, state: SimulationState, on: date) -> "Effect": ...


@dataclass(frozen=True)
class Event:
    date: date
    phase: Phase
    action: Action


@dataclass(frozen=True)
class Effect:
    state: SimulationState
    successors: tuple[Event, ...] = ()
    # Only cash transactions trigger reserve allocation. Merely observing or
    # repricing an account must not introduce a new investment transaction.
    settle: frozenset[ScenarioName] = frozenset()


@dataclass(order=True, frozen=True)
class _QueuedEvent:
    date: date
    phase: Phase
    sequence: int
    event: Event = field(compare=False)


class EventQueue:
    def __init__(self, end: date) -> None:
        self.end = end
        self._heap: list[_QueuedEvent] = []
        self._sequence = 0

    def copy(self) -> "EventQueue":
        result = EventQueue(self.end)
        result._heap = self._heap.copy()
        result._sequence = self._sequence
        return result

    def schedule(self, event: Event, *, after: date | None = None) -> None:
        if after is not None and event.date <= after:
            raise ValueError("Events must be scheduled strictly after the current date")
        if event.date > self.end:
            return
        heapq.heappush(
            self._heap,
            _QueuedEvent(event.date, event.phase, self._sequence, event),
        )
        self._sequence += 1

    @property
    def next_date(self) -> date:
        return self._heap[0].date if self._heap else self.end

    def pop_on(self, on: date) -> tuple[Event, ...]:
        events = []
        while self._heap and self._heap[0].date == on:
            events.append(heapq.heappop(self._heap).event)
        return tuple(events)
