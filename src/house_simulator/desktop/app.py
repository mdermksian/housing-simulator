"""Desktop composition and lifecycle; the only module that imports Slint."""

from collections.abc import Generator
from contextlib import contextmanager
from datetime import timedelta
from importlib.resources import as_file, files
from types import SimpleNamespace

from ..application.workspace import WorkspaceController
from .bindings import WorkspaceBindings


class MissingUI(RuntimeError):
    pass


@contextmanager
def load_components() -> Generator[SimpleNamespace]:
    """Keep the resource directory alive, including relative Slint imports."""
    try:
        import slint
    except ModuleNotFoundError as exc:
        if exc.name != "slint":
            raise
        raise MissingUI(
            "The desktop UI requires the optional Slint dependency. "
            "Run 'uv run --extra ui house-simulator ui' from the project, "
            "or install 'house-simulator[ui]' with pip."
        ) from exc

    with as_file(files("house_simulator.desktop")) as directory:
        yield slint.load_file(str(directory / "app.slint"))


def run() -> None:
    with load_components() as components:
        import slint

        window = components.AppWindow()
        workspace = WorkspaceController()
        bindings = WorkspaceBindings(window, workspace, slint.ListModel, components)
        timer = slint.Timer()
        timer.start(slint.TimerMode.Repeated, timedelta(milliseconds=50), bindings.poll)
        try:
            while not workspace.should_close:
                window.run()
                if not workspace.should_close:
                    # Python Slint 1.17 has no native close-request hook. On an
                    # OS close, show the same window again with confirmation if
                    # edits or an active run need protection.
                    workspace.dismiss_dialog()
                    workspace.request("close")
                    bindings.refresh()
        finally:
            timer.stop()
            workspace.close()
