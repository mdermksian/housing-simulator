from dataclasses import replace
from datetime import date
from threading import Event
from time import monotonic, sleep

import pytest

from house_simulator import OneTimeExpense, Simulation, load_config
from house_simulator.application.documents import resolve_path
from house_simulator.application.editing import ConfigurationDraft, EditorController
from house_simulator.application.execution import RunController
from house_simulator.application.workspace import WorkspaceController


def finish(runner):
    deadline = monotonic() + 5
    while runner.running and monotonic() < deadline:
        runner.poll()
        sleep(0.001)
    assert not runner.running
    runner.close()
    return runner.update


def workspace_with_config(config):
    workspace = WorkspaceController()
    workspace.document.editor = EditorController(ConfigurationDraft.from_config(config))
    return workspace


def test_worker_matches_simulator_and_retains_config(config):
    runner = RunController()
    runner.start(config)
    with pytest.raises(RuntimeError, match="already running"):
        runner.start(config)
    update = finish(runner)
    assert update.phase == "completed"
    assert update.result == Simulation(config).run()
    assert update.snapshot_count == len(update.result.snapshots)
    assert runner.config is config
    runner.start(config)
    assert finish(runner).result == update.result


def test_cancel_between_steps_and_close_joins_worker(config):
    entered, release = Event(), Event()

    class PausedSimulation(Simulation):
        def step(self):
            entered.set()
            assert release.wait(5)
            return super().step()

    runner = RunController(PausedSimulation)
    runner.start(config)
    assert entered.wait(5)
    runner.cancel()
    release.set()
    update = finish(runner)
    # Use a configuration with later events for cancellation before completion.
    assert update.phase == "completed"
    assert update.result.completed
    assert not runner._thread.is_alive()


def test_cancel_preserves_partial_history(config):
    config = replace(config, rent=replace(config.rent, monthly_rent="100"))
    entered, release = Event(), Event()

    class PausedSimulation(Simulation):
        def step(self):
            entered.set()
            assert release.wait(5)
            return super().step()

    runner = RunController(PausedSimulation)
    runner.start(config)
    assert entered.wait(5)
    runner.cancel()
    release.set()
    update = finish(runner)
    assert update.phase == "cancelled"
    assert not update.result.completed
    assert update.result.failure is None
    assert len(update.result.snapshots) == 2


@pytest.mark.parametrize("opening", [False, True])
def test_worker_financial_failures(config, opening):
    config = replace(
        config,
        household=replace(config.household, starting_wealth="100"),
        one_time_expenses=(
            OneTimeExpense(
                "Repair",
                config.simulation.start if opening else date(2026, 3, 1),
                "101",
            ),
        ),
    )
    runner = RunController()
    runner.start(config)
    update = finish(runner)
    assert update.phase == "failed"
    assert "requires 101.00" in update.message
    assert len(update.result.snapshots) == (0 if opening else 1)
    assert update.result.failure is not None


def test_unexpected_error_retains_committed_state(config):
    class BrokenSimulation(Simulation):
        def step(self):
            raise RuntimeError("Example worker error")

    runner = RunController(BrokenSimulation)
    runner.start(config)
    update = finish(runner)
    assert update.phase == "failed"
    assert update.message == "Example worker error"
    assert len(update.result.snapshots) == 1


def test_progress_mailbox_is_bounded(config):
    config = replace(config, rent=replace(config.rent, monthly_rent="1"))
    runner = RunController()
    runner.start(config)
    runner._thread.join(timeout=5)
    assert runner._updates.qsize() == 1
    assert runner.poll().phase == "completed"
    runner.close()


def test_dirty_discard_load_and_save_flow(config, tmp_path):
    workspace = workspace_with_config(config)
    workspace.edit("rent.monthly_rent", "25")
    assert workspace.document.dirty
    workspace.request("new")
    assert workspace.dialog.kind == "confirm"
    workspace.dismiss_dialog()
    assert workspace.document.editor.config.rent.monthly_rent == 25
    workspace.request("save_as")
    destination = tmp_path / "saved.yaml"
    workspace.update_path(str(destination))
    assert workspace.resolved_dialog_path == str(destination)
    workspace.accept_dialog()
    assert workspace.document.path == destination
    assert not workspace.document.dirty
    assert load_config(destination).rent.monthly_rent == 25
    workspace.edit("rent.monthly_rent", "30")
    workspace.request("load")
    workspace.update_path(str(destination))
    workspace.accept_dialog()
    assert workspace.dialog.kind == "confirm"
    workspace.accept_dialog()
    assert workspace.document.editor.config.rent.monthly_rent == 25
    assert not workspace.document.dirty


def test_failed_load_and_write_preserve_document(config, tmp_path, monkeypatch):
    workspace = workspace_with_config(config)
    editor = workspace.document.editor
    bad = tmp_path / "bad.yaml"
    bad.write_text("invalid: true")
    workspace.request("load")
    workspace.update_path(str(bad))
    workspace.accept_dialog()
    assert workspace.document.editor is editor
    assert "unknown" in workspace.message
    destination = tmp_path / "existing.yaml"
    destination.write_text("original contents")
    workspace.edit("rent.monthly_rent", "1")
    workspace.request("save_as")
    workspace.update_path(str(destination))
    workspace.accept_dialog()
    assert workspace.dialog.kind == "confirm"
    workspace.dismiss_dialog()
    assert destination.read_text() == "original contents"
    workspace.request("save_as")
    workspace.update_path(str(destination))
    workspace.accept_dialog()

    def fail_replace(*args):
        raise OSError("Cannot replace file")

    monkeypatch.setattr("house_simulator.file_io.os.replace", fail_replace)
    workspace.accept_dialog()
    assert workspace.document.dirty
    assert workspace.document.path is None
    assert destination.read_text() == "original contents"
    assert "Cannot replace" in workspace.message


def test_results_provenance_export_and_overwrite(config, tmp_path):
    workspace = workspace_with_config(config)
    path = tmp_path / "config.yaml"
    workspace.document.save(path)
    workspace.request("run")
    workspace.edit("rent.monthly_rent", "100")
    assert workspace.document.editor.config == config
    assert not workspace.can_run
    finish(workspace.runner)
    assert workspace.can_export
    assert not workspace.results_stale
    workspace.edit("rent.monthly_rent", "100")
    assert workspace.results_stale
    assert workspace.runner.config == config
    workspace.request("export")
    workspace.update_path(str(path))
    workspace.accept_dialog()
    assert "cannot replace" in workspace.message
    assert load_config(path) == config
    output = tmp_path / "result.csv"
    output.write_text("prior output")
    workspace.request("export")
    workspace.update_path(str(output))
    workspace.accept_dialog()
    assert workspace.dialog.kind == "confirm"
    workspace.accept_dialog()
    assert output.read_text().startswith("date,elapsed_days,")
    assert workspace.results_stale


def test_close_confirmation_and_file_dialog_cancel(config):
    workspace = workspace_with_config(config)
    workspace.request("load")
    workspace.dismiss_dialog()
    assert workspace.document.editor.config == config
    workspace.edit("rent.monthly_rent", "10")
    workspace.request("close")
    assert not workspace.should_close
    workspace.dismiss_dialog()
    workspace.request("close")
    workspace.accept_dialog()
    assert workspace.should_close
    workspace.close()


def test_path_resolution(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert resolve_path("my.yaml") == tmp_path / "my.yaml"
    assert resolve_path("~/my.yaml").is_absolute()
    with pytest.raises(ValueError, match="file path"):
        resolve_path(" ")


def test_partial_results_can_export(config):
    config = replace(
        config,
        household=replace(config.household, starting_wealth="0"),
        rent=replace(config.rent, monthly_rent="1"),
    )
    workspace = workspace_with_config(config)
    workspace.request("run")
    finish(workspace.runner)
    assert workspace.runner.update.phase == "failed"
    assert workspace.can_export
