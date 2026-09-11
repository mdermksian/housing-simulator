from typing import Protocol

from house_simulator import SimulationState


class Event(Protocol):
    def apply(self, state: SimulationState) -> SimulationState: ...

    def next_event(self, state: SimulationState) -> "Event": ...
