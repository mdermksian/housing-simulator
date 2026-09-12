"""In-memory configuration preview, independent of Slint and the simulation."""

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class PreviewState:
    comparison_name: str = "My housing comparison"
    duration_years: int = 15

    def __post_init__(self) -> None:
        if not isinstance(self.comparison_name, str):
            raise ValueError("Comparison name must be a string")
        if type(self.duration_years) is not int or not 1 <= self.duration_years <= 100:
            raise ValueError("Duration must be a whole number between 1 and 100 years")


class PreviewController:
    def __init__(self, state: PreviewState | None = None) -> None:
        self._state = state if state is not None else PreviewState()

    @property
    def state(self) -> PreviewState:
        return self._state

    @property
    def summary(self) -> str:
        name = self.state.comparison_name.strip() or "Untitled comparison"
        years = self.state.duration_years
        unit = "year" if years == 1 else "years"
        return f"{name} · {years} {unit}"

    def rename(self, name: str) -> None:
        self._state = replace(self.state, comparison_name=name)

    def set_duration(self, years: int) -> None:
        self._state = replace(self.state, duration_years=years)

    def reset(self) -> None:
        self._state = PreviewState()
