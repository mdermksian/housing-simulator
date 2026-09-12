"""Expense row mapping is kept out of application state."""

from ...application.editing import EditorController
from ..configuration.bindings import error_text
from ..models import ModelBinding


class ExpenseBindings(ModelBinding):
    def __init__(self, group, model_factory, row_factory) -> None:
        super().__init__(model_factory, row_factory, "id")
        self.group = group

    def refresh(self, editor: EditorController) -> None:
        values = []
        for row in editor.draft.rows(self.group):
            value = {"id": row.id}
            for name in ("name", "amount", "annual_increase", "date", "first_due"):
                value[name] = getattr(row, name, "")
                key = f"{self.group}/{row.id}/{name}"
                value[f"{name}_error"] = error_text(key, editor.errors.get(key, ""))
            if self.group == "one_time":
                choices, selection = ("rent", "buy", "both"), row.target
            else:
                choices, selection = ("monthly", "yearly"), row.schedule
            value["selection"] = choices.index(selection) if selection in choices else 0
            values.append(value)
        self.update(values)
