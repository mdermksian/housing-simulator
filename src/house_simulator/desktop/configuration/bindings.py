"""Publish form fields with user-facing units and field-specific errors."""

from ...application.editing import FIELD_BY_KEY, FIELDS, EditorController
from ..models import ModelBinding


def error_text(key: str, message: str) -> str:
    """Translate domain units and field names only at the presentation boundary."""
    spec = FIELD_BY_KEY.get(key)
    if (spec is not None and spec.kind == "percent") or key.endswith(
        "/annual_increase"
    ):
        message = {
            "must be greater than -1": "must be greater than -100%",
            "must be between 0 and 1": "must be between 0% and 100%",
        }.get(message, message)
    return message.replace("household.starting_wealth", "starting wealth").replace(
        "purchase_price", "purchase price"
    )


class FieldBindings(ModelBinding):
    def __init__(self, model_factory, row_factory) -> None:
        super().__init__(model_factory, row_factory, "key")

    def refresh(self, editor: EditorController) -> None:
        self.update(
            [
                {
                    "key": spec.key,
                    "label": spec.label + (" *" if spec.required else ""),
                    "value": editor.draft.values[spec.key],
                    "error": error_text(spec.key, editor.errors.get(spec.key, "")),
                    "section": spec.section,
                }
                for spec in FIELDS
            ]
        )
