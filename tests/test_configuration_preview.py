from dataclasses import FrozenInstanceError

import pytest

from house_simulator.application.configuration_preview import (
    PreviewController,
    PreviewState,
)
from house_simulator.desktop.configuration_preview.bindings import PreviewBindings


def test_defaults_and_immutable_state():
    controller = PreviewController()
    assert controller.state == PreviewState("My housing comparison", 15)
    assert controller.summary == "My housing comparison · 15 years"
    with pytest.raises(FrozenInstanceError):
        controller.state.duration_years = 20
    with pytest.raises(AttributeError):
        controller.state = PreviewState()


def test_edits_replace_state_and_reset_restores_defaults():
    controller = PreviewController(PreviewState("Initial", 30))
    original = controller.state
    controller.rename("Our next home")
    controller.set_duration(1)
    assert controller.summary == "Our next home · 1 year"
    assert original == PreviewState("Initial", 30)
    controller.reset()
    assert controller.state == PreviewState()


@pytest.mark.parametrize("name", ["", "   ", "\t\n"])
def test_empty_name_has_display_fallback(name):
    controller = PreviewController()
    controller.rename(name)
    assert controller.state.comparison_name == name
    assert controller.summary == "Untitled comparison · 15 years"


@pytest.mark.parametrize("years", [1, 100])
def test_duration_boundaries(years):
    controller = PreviewController()
    controller.set_duration(years)
    assert controller.state.duration_years == years


@pytest.mark.parametrize("years", [0, -1, 101, 1.5, True, "15", None])
def test_invalid_duration_cannot_change_state(years):
    controller = PreviewController()
    original = controller.state
    with pytest.raises(ValueError, match="between 1 and 100"):
        controller.set_duration(years)
    assert controller.state is original
    with pytest.raises(ValueError, match="between 1 and 100"):
        PreviewState(duration_years=years)


def test_invalid_name_cannot_change_state():
    controller = PreviewController()
    with pytest.raises(ValueError, match="string"):
        controller.rename(None)
    assert controller.state == PreviewState()


class FakeView:
    """Binding tests deliberately need no Slint module or window."""


def test_adapter_publishes_initial_state_and_handles_callbacks():
    view = FakeView()
    controller = PreviewController(PreviewState("Starter", 10))
    PreviewBindings(view, controller)
    assert view.comparison_name == "Starter"
    assert view.duration_years == 10
    assert view.summary == "Starter · 10 years"

    view.name_edited("New name")
    assert controller.state.comparison_name == "New name"
    assert view.comparison_name == "New name"
    assert view.summary == "New name · 10 years"

    view.duration_edited(1)
    assert controller.state.duration_years == 1
    assert view.duration_years == 1
    assert view.summary == "New name · 1 year"

    view.reset_requested()
    assert controller.state == PreviewState()
    assert view.comparison_name == "My housing comparison"
    assert view.duration_years == 15
    assert view.summary == controller.summary


def test_python_changes_are_published_by_explicit_refresh():
    view = FakeView()
    controller = PreviewController()
    bindings = PreviewBindings(view, controller)
    controller.rename("Changed from Python")
    controller.set_duration(20)
    assert view.comparison_name == "My housing comparison"
    bindings.refresh()
    assert view.comparison_name == "Changed from Python"
    assert view.duration_years == 20
    assert view.summary == controller.summary
