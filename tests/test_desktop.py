import importlib.util
import os
import subprocess
import sys
import textwrap
from importlib.resources import files
from pathlib import Path
from types import SimpleNamespace

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
        from house_simulator.application.workspace import WorkspaceController
        from house_simulator.desktop.bindings import WorkspaceBindings
        from house_simulator.cli import main

        assert not WorkspaceController().can_run
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
        "configuration/form.slint",
        "configuration/field.slint",
        "expenses/list.slint",
        "documents/dialog.slint",
        "results/summary.slint",
    ):
        assert root.joinpath(relative).is_file()


def test_slint_tree_compiles_outside_repository(tmp_path, monkeypatch):
    if importlib.util.find_spec("slint") is None:
        pytest.skip("Install the ui extra to compile Slint components")
    monkeypatch.chdir(tmp_path)
    with load_components() as components:
        assert callable(components.AppWindow)


def test_bindings_without_slint_update_only_affected_rows(config):
    from house_simulator.application.editing import ConfigurationDraft, EditorController
    from house_simulator.application.workspace import WorkspaceController
    from house_simulator.desktop.bindings import WorkspaceBindings

    class FakeWindow:
        section = 0
        closed = False

        def hide(self):
            self.closed = True

    types = SimpleNamespace(
        FieldData=SimpleNamespace,
        ExpenseData=SimpleNamespace,
        ResultData=SimpleNamespace,
    )
    workspace = WorkspaceController()
    workspace.document.editor = EditorController(ConfigurationDraft.from_config(config))
    window = FakeWindow()
    bindings = WorkspaceBindings(window, workspace, list, types)
    unchanged = window.fields[0]
    window.field_edited("rent.monthly_rent", "10")
    assert window.fields[0] is unchanged
    assert workspace.document.editor.config.rent.monthly_rent == 10
    assert window.can_run
    window.expense_add("buy")
    row_id = window.buy_expenses[0].id
    assert not window.can_run
    assert row_id not in window.validation
    window.expense_edited("buy", row_id, "name", "Tax")
    window.expense_edited("buy", row_id, "amount", "25")
    assert window.can_run
    assert window.buy_expenses[0].name == "Tax"
    window.expense_add("buy")
    second = window.buy_expenses[1].id
    window.expense_remove("buy", row_id)
    assert window.buy_expenses[0].id == second
    window.expense_remove("buy", second)
    assert window.can_run
    window.command("new")
    assert window.dialog_kind == "confirm"
    assert not window.editable
    window.dialog_dismiss()
    assert window.editable
    workspace.document.editor.edit("rent.monthly_rent", "20")
    bindings.refresh()
    assert (
        next(row for row in window.fields if row.key == "rent.monthly_rent").value
        == "20"
    )


def test_summary_matches_committed_result(config):
    from house_simulator import Simulation
    from house_simulator.application.execution import RunUpdate
    from house_simulator.desktop.results.bindings import ResultBindings, status_text

    result = Simulation(config).run()
    binding = ResultBindings(list, SimpleNamespace)
    update = RunUpdate(
        "completed", result.snapshots[-1].date, len(result.snapshots), result=result
    )
    binding.refresh(update)
    net_worth = next(row for row in binding.model if row.label == "Net worth")
    assert net_worth.rent == "$100,000.00"
    assert net_worth.buy == "$100,000.00"
    assert "$0.00" in binding.difference
    assert "Last committed date" in status_text(update)
    assert "Incomplete" in status_text(RunUpdate("failed"))


def test_percentage_errors_use_display_units(config):
    from house_simulator.application.editing import ConfigurationDraft, EditorController
    from house_simulator.desktop.configuration.bindings import FieldBindings
    from house_simulator.desktop.expenses.bindings import ExpenseBindings

    editor = EditorController(ConfigurationDraft.from_config(config))
    editor.edit("buy.appreciation", "-100")
    fields = FieldBindings(list, SimpleNamespace)
    fields.refresh(editor)
    error = next(row.error for row in fields.model if row.key == "buy.appreciation")
    assert error == "must be greater than -100%"
    editor.edit("buy.appreciation", "0")
    editor.edit("buy.selling_cost_fraction", "101")
    fields.refresh(editor)
    error = next(
        row.error for row in fields.model if row.key == "buy.selling_cost_fraction"
    )
    assert error == "must be between 0% and 100%"
    editor.edit("buy.selling_cost_fraction", "0")
    row = editor.add_expense("rent")
    for key, value in (
        ("name", "Parking"),
        ("amount", "1"),
        ("annual_increase", "-100"),
    ):
        editor.edit(f"rent/{row.id}/{key}", value)
    expenses = ExpenseBindings("rent", list, SimpleNamespace)
    expenses.refresh(editor)
    assert expenses.model[0].annual_increase_error == "must be greater than -100%"


def require_desktop():
    if importlib.util.find_spec("slint") is None:
        pytest.skip("Install the ui extra to test the Slint window")
    if sys.platform.startswith("linux") and not (
        os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    ):
        pytest.skip("Slint window integration requires a desktop display")


@pytest.mark.ui
def test_real_editor_expenses_run_and_export(tmp_path):
    require_desktop()
    example = Path(__file__).resolve().parents[1] / "examples/comparison.yaml"
    script = textwrap.dedent("""
        from datetime import timedelta
        from decimal import Decimal
        from pathlib import Path
        from threading import Event
        import sys
        import traceback
        import slint
        from house_simulator import Simulation
        from house_simulator.application.execution import RunController
        from house_simulator.application.workspace import WorkspaceController
        from house_simulator.desktop.app import load_components
        from house_simulator.desktop.bindings import WorkspaceBindings

        with load_components() as components:
            window = components.AppWindow()
            workspace = WorkspaceController()
            bindings = WorkspaceBindings(window, workspace, slint.ListModel, components)
            assert not window.can_run
            window.field_edited('household.starting_wealth', '123')
            window.command('load')
            window.dialog_path_edited(sys.argv[1])
            window.dialog_accept()
            assert window.dialog_kind == 'confirm'
            window.dialog_accept()
            assert window.can_run
            rate = workspace.document.editor.config.buy.mortgage.annual_rate
            assert rate == Decimal('0.0658')
            window.expense_add('rent')
            row_id = workspace.document.editor.draft.rent_expenses[-1].id
            assert not window.can_run
            window.expense_edited('rent', row_id, 'name', 'Parking')
            window.expense_edited('rent', row_id, 'amount', '25')
            window.expense_edited('rent', row_id, 'schedule', 'yearly')
            window.expense_edited('rent', row_id, 'annual_increase', '2')
            assert window.can_run
            window.expense_remove('rent', row_id)
            window.command('run')
            assert window.running
            assert not window.editable
            errors = []
            timer = slint.Timer()
            def check():
                try:
                    bindings.poll()
                    if workspace.runner.running:
                        return
                    timer.stop()
                    update = workspace.runner.update
                    assert update.phase == 'completed', update.message
                    assert len(window.results) == 10
                    assert window.can_export
                    window.command('export')
                    window.dialog_path_edited(sys.argv[2])
                    window.dialog_accept()
                    csv = Path(sys.argv[2]).read_text()
                    assert csv.startswith('date,elapsed_days,')
                    entered, release = Event(), Event()
                    class PausedSimulation(Simulation):
                        def step(self):
                            entered.set()
                            assert release.wait(5)
                            return super().step()
                    workspace.runner = RunController(PausedSimulation)
                    window.command('run')
                    try:
                        assert entered.wait(5)
                        window.command('cancel')
                    finally:
                        release.set()
                        workspace.runner.close()
                    bindings.refresh()
                    assert workspace.runner.update.phase == 'cancelled'
                    assert len(workspace.runner.update.result.snapshots) == 2
                    assert window.can_export
                    assert 'Incomplete' in window.run_status
                    window.command('close')
                    assert window.dialog_kind == 'confirm'
                    window.dialog_dismiss()
                    assert not workspace.should_close
                    window.command('close')
                    window.dialog_accept()
                    assert workspace.should_close
                except Exception as error:
                    errors.append(traceback.format_exc())
                    window.hide()
            timer.start(slint.TimerMode.Repeated, timedelta(milliseconds=50), check)
            window.run()
            timer.stop()
            workspace.close()
            assert not errors, errors
            print('Editor, expenses, execution, cancel, export and close passed')
    """)
    result = subprocess.run(
        [sys.executable, "-c", script, str(example), str(tmp_path / "results.csv")],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    assert "export and close passed" in result.stdout


@pytest.mark.ui
def test_native_close_reopens_confirmation_and_can_cancel():
    require_desktop()
    script = textwrap.dedent("""
        from contextlib import contextmanager
        from datetime import timedelta
        import slint
        from house_simulator.application.workspace import WorkspaceController
        from house_simulator.desktop import app

        with app.load_components() as components:
            window = components.AppWindow()
            workspace = WorkspaceController()
            workspace.edit('household.starting_wealth', '100')
            @contextmanager
            def existing():
                yield components
            components.AppWindow = lambda: window
            app.load_components = existing
            app.WorkspaceController = lambda: workspace
            errors = []
            def confirm():
                try:
                    assert workspace.dialog.kind == 'confirm'
                    window.dialog_dismiss()
                    assert not workspace.should_close
                    window.command('close')
                    window.dialog_accept()
                except Exception as error:
                    errors.append(error)
                    workspace.should_close = True
                    window.hide()
            slint.Timer.single_shot(timedelta(milliseconds=100), window.hide)
            slint.Timer.single_shot(timedelta(milliseconds=350), confirm)
            app.run()
            assert workspace.should_close
            assert not errors, errors
            print('Native close confirmation passed')
    """)
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, timeout=20
    )
    assert result.returncode == 0, result.stderr
    assert "Native close confirmation passed" in result.stdout
