import importlib.util
import os
import subprocess
import sys
import textwrap
from importlib.resources import files

import pytest

from house_simulator.cli import main
from house_simulator.desktop.app import load_components

# A fresh interpreter proves that even an installed Slint cannot be imported by
# the core application or CSV command. This is stronger than checking sys.modules
# in a test suite that may already have loaded GUI tests.
BLOCK_SLINT = """
import importlib.abc
import sys

class BlockSlint(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'slint' or fullname.startswith('slint.'):
            raise ModuleNotFoundError('Slint blocked for test', name=fullname)

sys.meta_path.insert(0, BlockSlint())
"""


def test_core_cli_and_plain_bindings_work_without_slint(tmp_path):
    config = tmp_path / "comparison.yaml"
    config.write_text(
        """simulation: {start: 2026-01-01, end: 2026-02-01}
household: {starting_wealth: 1000, monthly_income: 100, cash_reserve: 100}
rent: {monthly_rent: 100}
buy:
  purchase_price: 0
  down_payment: 0
  mortgage: {annual_rate: 0, term_years: 1}
"""
    )
    output = tmp_path / "result.csv"
    script = BLOCK_SLINT + textwrap.dedent("""
        import house_simulator
        from house_simulator.application.configuration_preview import PreviewController
        from house_simulator.desktop.configuration_preview.bindings import (
            PreviewBindings,
        )
        from house_simulator.cli import main

        assert PreviewController().state.duration_years == 15
        assert main(['run', sys.argv[1], '--output', sys.argv[2]]) == 0
        assert 'slint' not in sys.modules
        assert 'house_simulator.desktop.app' not in sys.modules
    """)
    result = subprocess.run(
        [sys.executable, "-c", script, str(config), str(output)],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    assert output.read_text().startswith("date,elapsed_days,")


def test_ui_missing_extra_has_actionable_error():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            BLOCK_SLINT
            + "from house_simulator.cli import main; raise SystemExit(main(['ui']))",
        ],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 2
    assert "uv run --extra ui house-simulator ui" in result.stderr
    assert "house-simulator[ui]" in result.stderr
    assert "Traceback" not in result.stderr


def test_ui_command_dispatch(monkeypatch):
    from house_simulator.desktop import app

    calls = []
    monkeypatch.setattr(app, "run", lambda: calls.append("opened"))
    assert main(["ui"]) == 0
    assert calls == ["opened"]


def test_ui_resource_tree_is_packaged():
    root = files("house_simulator.desktop")
    for relative in (
        "app.slint",
        "configuration_preview/editor.slint",
        "configuration_preview/summary.slint",
    ):
        assert root.joinpath(relative).is_file()


def test_slint_tree_compiles_outside_repository(tmp_path, monkeypatch):
    if importlib.util.find_spec("slint") is None:
        pytest.skip("Install the ui extra to compile Slint components")
    monkeypatch.chdir(tmp_path)
    with load_components() as components:
        assert callable(components.AppWindow)


@pytest.mark.ui
def test_real_window_callback_round_trip_and_lifecycle(tmp_path):
    if importlib.util.find_spec("slint") is None:
        pytest.skip("Install the ui extra to test the Slint window")
    if sys.platform.startswith("linux") and not (
        os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    ):
        pytest.skip("Slint window integration requires a desktop display")

    # Run on a fresh main thread and terminate on timeout if lifecycle breaks.
    script = textwrap.dedent("""
        from datetime import timedelta
        import slint
        from house_simulator.application.configuration_preview import PreviewController
        from house_simulator.desktop.app import load_components
        from house_simulator.desktop.configuration_preview.bindings import (
            PreviewBindings,
        )

        with load_components() as components:
            window = components.AppWindow()
            controller = PreviewController()
            bindings = PreviewBindings(window, controller)
            assert window.comparison_name == 'My housing comparison'
            assert window.duration_years == 15
            window.name_edited('First home')
            window.duration_edited(25)
            assert controller.state.comparison_name == 'First home'
            assert controller.state.duration_years == 25
            assert window.summary == 'First home · 25 years'
            window.name_edited('')
            assert window.summary == 'Untitled comparison · 25 years'
            window.reset_requested()
            assert window.duration_years == 15
            assert window.comparison_name == 'My housing comparison'
            controller.rename('Changed from Python')
            bindings.refresh()
            assert window.comparison_name == 'Changed from Python'
            assert window.summary == controller.summary
            slint.Timer.single_shot(timedelta(milliseconds=100), window.hide)
            window.run()
            print('Window opened and closed')
    """)
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    assert "Window opened and closed" in result.stdout
