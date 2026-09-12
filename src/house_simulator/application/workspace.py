"""User commands and confirmation flow, independent of any GUI toolkit."""

from dataclasses import dataclass, replace
from pathlib import Path

from ..configuration import ConfigurationError
from ..file_io import atomic_destination
from ..reporting import write_csv
from .documents import DocumentController, resolve_path
from .execution import RunController


@dataclass(frozen=True)
class Request:
    action: str
    path: Path | None = None
    discard: bool = False
    overwrite: bool = False


@dataclass(frozen=True)
class DialogState:
    kind: str = ""
    title: str = ""
    path: str = ""
    message: str = ""
    request: Request | None = None


class WorkspaceController:
    def __init__(self, runner: RunController | None = None) -> None:
        self.document = DocumentController()
        self.runner = runner if runner is not None else RunController()
        self.dialog = DialogState()
        self.message = ""
        self.should_close = False

    @property
    def editable(self) -> bool:
        return (
            not self.should_close and not self.runner.running and not self.dialog.kind
        )

    @property
    def can_run(self) -> bool:
        return self.editable and self.document.editor.config is not None

    @property
    def can_export(self) -> bool:
        result = self.runner.update.result
        return self.editable and result is not None and bool(result.snapshots)

    @property
    def results_stale(self) -> bool:
        return (
            self.runner.config is not None
            and self.runner.config != self.document.editor.config
        )

    def edit(self, key: str, text: str) -> None:
        if self.editable:
            self.document.editor.edit(key, text)

    def add_expense(self, group: str) -> None:
        if self.editable:
            self.document.editor.add_expense(group)

    def remove_expense(self, group: str, row_id: str) -> None:
        if self.editable:
            self.document.editor.remove_expense(group, row_id)

    def request(self, action: str) -> None:
        if self.should_close or self.dialog.kind:
            return
        if action == "cancel":
            self.runner.cancel()
            return
        if action == "close":
            self._execute(Request(action))
            return
        if not self.editable:
            return
        self.message = ""
        if action == "run":
            if self.can_run:
                self.runner.start(self.document.editor.config)
            return
        if action in ("save", "save_as") and not self.can_run:
            self.message = "Complete the configuration before saving"
            return
        if action == "export" and not self.can_export:
            return
        if action == "save" and self.document.path is not None:
            self._execute(Request(action, self.document.path))
        elif action in ("load", "save", "save_as", "export"):
            parent = self.document.path.parent if self.document.path else Path.home()
            filename = "results.csv" if action == "export" else "comparison.yaml"
            titles = {
                "load": "Load YAML",
                "save": "Save YAML",
                "save_as": "Save YAML as",
                "export": "Export CSV",
            }
            self.dialog = DialogState(
                "path", titles[action], str(parent / filename), request=Request(action)
            )
        elif action == "new":
            self._execute(Request(action))
        else:
            raise ValueError(f"Unknown command: {action}")

    def update_path(self, text: str) -> None:
        if self.dialog.kind == "path":
            self.dialog = replace(self.dialog, path=text, message="")

    @property
    def resolved_dialog_path(self) -> str:
        try:
            return (
                str(resolve_path(self.dialog.path))
                if self.dialog.kind == "path"
                else ""
            )
        except (ValueError, OSError, RuntimeError) as exc:
            return str(exc)

    def dismiss_dialog(self) -> None:
        self.dialog = DialogState()

    def accept_dialog(self) -> None:
        dialog = self.dialog
        if dialog.request is None:
            return
        try:
            request = dialog.request
            if dialog.kind == "path":
                request = replace(request, path=resolve_path(dialog.path))
            self.dialog = DialogState()
            self._execute(request)
        except (ValueError, OSError, RuntimeError) as exc:
            self.dialog = replace(dialog, message=str(exc))

    def _execute(self, request: Request) -> None:
        action, path = request.action, request.path
        if (
            action in ("new", "load", "close")
            and not request.discard
            and (self.document.dirty or self.runner.running)
        ):
            message = (
                "Discard unsaved configuration changes?" if self.document.dirty else ""
            )
            if self.runner.running:
                message += " Stop the running simulation and close?"
            self.dialog = DialogState(
                "confirm",
                "Confirm",
                message=message.strip(),
                request=replace(request, discard=True),
            )
            return
        if action == "export" and path == self.document.path:
            self.message = "CSV output cannot replace the active YAML document"
            return
        if action in ("save", "save_as", "export") and path is not None:
            if (
                path.exists()
                and not request.overwrite
                and (action == "export" or path != self.document.path)
            ):
                self.dialog = DialogState(
                    "confirm",
                    "Replace existing file?",
                    message=str(path),
                    request=replace(request, overwrite=True),
                )
                return
        try:
            if action == "new":
                self.document.new()
            elif action == "load":
                self.document.load(path)
                self.message = f"Loaded {path}"
            elif action in ("save", "save_as"):
                self.document.save(path)
                self.message = f"Saved {path}"
            elif action == "export":
                with atomic_destination(path) as temporary:
                    write_csv(self.runner.update.result, temporary)
                self.message = f"Exported {path}"
            elif action == "close":
                self.runner.cancel()
                self.should_close = True
        except (ConfigurationError, OSError, ValueError) as exc:
            self.message = str(exc)

    def close(self) -> None:
        self.runner.close()
