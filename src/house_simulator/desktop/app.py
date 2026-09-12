"""Desktop composition and lifecycle; the only module that imports Slint."""

from collections.abc import Generator
from contextlib import contextmanager
from importlib.resources import as_file, files
from types import SimpleNamespace

from ..application.configuration_preview import PreviewController
from .configuration_preview.bindings import PreviewBindings


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
        window = components.AppWindow()
        controller = PreviewController()
        # Retain the adapter for the complete lifetime of the window.
        _bindings = PreviewBindings(window, controller)
        window.run()
