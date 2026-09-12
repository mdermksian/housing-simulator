"""One worker owns its simulator. Immutable progress crosses the thread boundary."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from queue import Empty, Full, Queue
from threading import Event, Thread
from typing import Literal

from ..configuration import SimulationConfig
from ..simulation.engine import Simulation
from ..simulation.state import InsufficientFunds, SimulationResult

RunPhase = Literal["idle", "running", "completed", "cancelled", "failed"]


@dataclass(frozen=True)
class RunUpdate:
    phase: RunPhase = "idle"
    date: date | None = None
    snapshot_count: int = 0
    message: str = ""
    result: SimulationResult | None = None


class RunController:
    def __init__(self, factory: Callable = Simulation) -> None:
        self._factory = factory
        self._updates: Queue[RunUpdate] = Queue(maxsize=1)
        self._cancel = Event()
        self._thread: Thread | None = None
        self.config: SimulationConfig | None = None
        self.update = RunUpdate()

    @property
    def running(self) -> bool:
        # Remain busy until the UI consumes the terminal update.
        return self.update.phase == "running"

    def start(self, config: SimulationConfig) -> None:
        if self.running:
            raise RuntimeError("A simulation is already running")
        if self._thread is not None:
            self._thread.join()
        self.config = config
        self._cancel.clear()
        self.update = RunUpdate("running", message="Starting simulation…")
        self._thread = Thread(
            target=self._work, args=(config,), name="housing-simulation"
        )
        self._thread.start()

    def _publish(self, update: RunUpdate) -> None:
        # Progress is a latest-value mailbox, not an ever-growing event log.
        try:
            self._updates.put_nowait(update)
        except Full:
            try:
                self._updates.get_nowait()
            except Empty:
                pass
            self._updates.put_nowait(update)

    def _work(self, config: SimulationConfig) -> None:
        simulator = None
        count = 0
        on = None
        try:
            simulator = self._factory(config)
            count, on = 1, simulator.current_date
            self._publish(RunUpdate("running", on, count))
            while not self._cancel.is_set():
                snapshot = simulator.step()
                if snapshot is None:
                    break
                count += 1
                on = snapshot.date
                self._publish(RunUpdate("running", on, count))
            result = simulator.result
            phase = "completed" if result.completed else "cancelled"
            self._publish(RunUpdate(phase, on, count, result=result))
        except Exception as exc:
            result = (
                simulator.result
                if simulator is not None
                else SimulationResult(
                    (), False, exc if isinstance(exc, InsufficientFunds) else None
                )
            )
            self._publish(RunUpdate("failed", on, count, str(exc), result))

    def poll(self) -> RunUpdate:
        try:
            self.update = self._updates.get_nowait()
        except Empty:
            pass
        return self.update

    def cancel(self) -> None:
        self._cancel.set()

    def close(self) -> None:
        self.cancel()
        if self._thread is not None:
            self._thread.join()
        self.poll()
