"""Compose feature bindings. All calls happen on the desktop's main thread."""

from collections.abc import Callable
from typing import Protocol

from ..application.editing import FIELD_BY_KEY
from ..application.workspace import WorkspaceController
from .configuration.bindings import FieldBindings, error_text
from .expenses.bindings import ExpenseBindings
from .results.bindings import ResultBindings, status_text


class WorkspaceView(Protocol):
    fields: object
    rent_expenses: object
    buy_expenses: object
    one_time_expenses: object
    results: object
    document_label: str
    editable: bool
    can_run: bool
    running: bool
    can_export: bool
    stale: bool
    run_status: str
    difference: str
    message: str
    validation: str
    dialog_kind: str
    dialog_title: str
    dialog_path: str
    dialog_resolved: str
    dialog_message: str
    field_edited: Callable[[str, str], None]
    expense_edited: Callable[[str, str, str, str], None]
    expense_add: Callable[[str], None]
    expense_remove: Callable[[str, str], None]
    command: Callable[[str], None]
    dialog_path_edited: Callable[[str], None]
    dialog_accept: Callable[[], None]
    dialog_dismiss: Callable[[], None]
    section: int

    def hide(self) -> None: ...


class WorkspaceBindings:
    def __init__(
        self, view: WorkspaceView, workspace: WorkspaceController, model_factory, types
    ) -> None:
        self.view, self.workspace = view, workspace
        self.fields = FieldBindings(model_factory, types.FieldData)
        self.expenses = {
            group: ExpenseBindings(group, model_factory, types.ExpenseData)
            for group in ("rent", "buy", "one_time")
        }
        self.results = ResultBindings(model_factory, types.ResultData)
        view.fields = self.fields.model
        for group, binding in self.expenses.items():
            setattr(view, f"{group}_expenses", binding.model)
        view.results = self.results.model
        view.field_edited = self._edit
        view.expense_edited = lambda group, row, key, text: self._edit(
            f"{group}/{row}/{key}", text
        )
        view.expense_add = lambda group: self._call(workspace.add_expense, group)
        view.expense_remove = lambda group, row: self._call(
            workspace.remove_expense, group, row
        )
        view.command = self._command
        view.dialog_path_edited = lambda text: self._call(workspace.update_path, text)
        view.dialog_accept = lambda: self._call(workspace.accept_dialog)
        view.dialog_dismiss = lambda: self._call(workspace.dismiss_dialog)
        self.refresh()

    def _call(self, action, *args) -> None:
        action(*args)
        self.refresh()

    def _edit(self, key, text) -> None:
        self._call(self.workspace.edit, key, text)

    def _command(self, action: str) -> None:
        self.workspace.request(action)
        if action == "run" and self.workspace.runner.running:
            self.view.section = 5
        self.refresh()

    def poll(self) -> None:
        previous = self.workspace.runner.update
        if self.workspace.runner.poll() is not previous:
            self.refresh()

    def refresh(self) -> None:
        workspace, view = self.workspace, self.view
        document, editor = workspace.document, workspace.document.editor
        self.fields.refresh(editor)
        for binding in self.expenses.values():
            binding.refresh(editor)
        self.results.refresh(workspace.runner.update)
        view.document_label = (
            str(document.path) if document.path else "New comparison"
        ) + (" *" if document.dirty else "")
        view.editable = workspace.editable
        view.can_run = workspace.can_run
        view.running = workspace.runner.running
        view.can_export = workspace.can_export
        view.stale = workspace.results_stale
        view.run_status = status_text(workspace.runner.update)
        if workspace.runner.update.phase == "idle" and editor.config is not None:
            view.run_status = "Ready to run. * marks required fields."
        view.difference = self.results.difference
        view.message = workspace.message
        if editor.errors:
            key, message = next(iter(editor.errors.items()))
            message = error_text(key, message)
            if key in FIELD_BY_KEY:
                label = FIELD_BY_KEY[key].label
            elif "/" in key:
                group, row_id, field = key.split("/")
                index = next(
                    i
                    for i, row in enumerate(editor.draft.rows(group))
                    if row.id == row_id
                )
                group_label = {
                    "rent": "Renter",
                    "buy": "Owner",
                    "one_time": "One-time",
                }[group]
                label = f"{group_label} expense {index + 1}, {field.replace('_', ' ')}"
            else:
                label = key.replace(".", " / ").replace("_", " ")
            view.validation = (
                f"{len(editor.errors)} configuration issue(s). {label}: {message}"
            )
        else:
            view.validation = ""
        view.dialog_kind = workspace.dialog.kind
        view.dialog_title = workspace.dialog.title
        view.dialog_path = workspace.dialog.path
        view.dialog_resolved = workspace.resolved_dialog_path
        view.dialog_message = workspace.dialog.message
        if workspace.should_close:
            view.hide()
