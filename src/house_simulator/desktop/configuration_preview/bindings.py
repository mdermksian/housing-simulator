"""Explicit callbacks and property publication for the configuration preview.

The protocol describes only the feature's view surface. It can be implemented
by a Slint window or an ordinary Python fake without loading a GUI runtime.
"""

from collections.abc import Callable
from typing import Protocol

from ...application.configuration_preview import PreviewController


class PreviewView(Protocol):
    comparison_name: str
    duration_years: int
    summary: str
    name_edited: Callable[[str], None]
    duration_edited: Callable[[int], None]
    reset_requested: Callable[[], None]


class PreviewBindings:
    def __init__(self, view: PreviewView, controller: PreviewController) -> None:
        self._view = view
        self._controller = controller
        view.name_edited = self._rename
        view.duration_edited = self._set_duration
        view.reset_requested = self._reset
        self.refresh()

    def refresh(self) -> None:
        """Publish Python state, including changes initiated outside UI callbacks."""
        state = self._controller.state
        self._view.comparison_name = state.comparison_name
        self._view.duration_years = state.duration_years
        self._view.summary = self._controller.summary

    def _rename(self, name: str) -> None:
        self._controller.rename(name)
        self.refresh()

    def _set_duration(self, years: int) -> None:
        self._controller.set_duration(years)
        self.refresh()

    def _reset(self) -> None:
        self._controller.reset()
        self.refresh()
