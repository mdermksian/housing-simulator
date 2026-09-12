"""Raw form drafts and lossless conversion to the shared configuration schema."""

from dataclasses import asdict, dataclass, field, replace
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Literal

from ..configuration import ConfigurationError, SimulationConfig, config_from_mapping
from ..simulation.calendar import add_months
from .expenses import ExpenseDraft, OneTimeExpenseDraft, RecurringExpenseDraft


@dataclass(frozen=True)
class FieldSpec:
    key: str
    label: str
    section: int
    kind: Literal["money", "percent", "date", "integer"]
    default: str = ""
    required: bool = True


FIELDS = (
    FieldSpec("simulation.start", "Start date (YYYY-MM-DD)", 0, "date"),
    FieldSpec("simulation.end", "End date (YYYY-MM-DD)", 0, "date"),
    FieldSpec("household.starting_wealth", "Starting wealth ($)", 1, "money"),
    FieldSpec("household.monthly_income", "Monthly take-home income ($)", 1, "money"),
    FieldSpec("household.cash_reserve", "Cash reserve ($)", 1, "money"),
    FieldSpec(
        "household.annual_income_increase",
        "Annual income increase (%)",
        1,
        "percent",
        "0",
        False,
    ),
    FieldSpec(
        "household.savings_return",
        "Savings return (% effective annual)",
        1,
        "percent",
        "0",
        False,
    ),
    FieldSpec(
        "household.investment_return",
        "Investment return (% effective annual)",
        1,
        "percent",
        "0",
        False,
    ),
    FieldSpec("rent.monthly_rent", "Monthly rent ($)", 2, "money"),
    FieldSpec(
        "rent.annual_increase", "Annual rent increase (%)", 2, "percent", "0", False
    ),
    FieldSpec("buy.purchase_price", "Purchase price ($)", 3, "money"),
    FieldSpec("buy.down_payment", "Down payment ($)", 3, "money"),
    FieldSpec(
        "buy.purchase_closing_costs",
        "Purchase closing costs ($)",
        3,
        "money",
        "0",
        False,
    ),
    FieldSpec(
        "buy.mortgage.annual_rate", "Mortgage rate (% nominal annual)", 3, "percent"
    ),
    FieldSpec("buy.mortgage.term_years", "Mortgage term (years)", 3, "integer", "30"),
    FieldSpec(
        "buy.appreciation",
        "Home appreciation (% effective annual)",
        3,
        "percent",
        "0",
        False,
    ),
    FieldSpec(
        "buy.selling_cost_fraction",
        "Estimated selling costs (%)",
        3,
        "percent",
        "0",
        False,
    ),
)
FIELD_BY_KEY = {item.key: item for item in FIELDS}
GROUP_PATHS = {
    "rent": "rent.expenses",
    "buy": "buy.expenses",
    "one_time": "one_time_expenses",
}


def shift_decimal(value: Decimal, places: int) -> Decimal:
    """Move the decimal point without depending on the caller's precision."""
    sign, digits, exponent = value.as_tuple()
    return Decimal((sign, digits, exponent + places))


def parse_input(text: str, kind: str):
    value = text.strip()
    if not value:
        raise ValueError("Required")
    if kind == "integer":
        if not value.isascii() or not value.lstrip("+-").isdigit():
            raise ValueError("Enter a whole number")
        return int(value)
    if kind == "date":
        try:
            parsed = date.fromisoformat(value)
            if parsed.isoformat() == value:
                return value
        except ValueError:
            pass
        raise ValueError("Enter a valid date as YYYY-MM-DD")
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("Enter a decimal number") from exc
    if not number.is_finite():
        raise ValueError("Must be finite")
    return shift_decimal(number, -2) if kind == "percent" else number


def _put(mapping: dict, path: str, value) -> None:
    parts = path.split(".")
    for part in parts[:-1]:
        mapping = mapping.setdefault(part, {})
    mapping[parts[-1]] = value


def _get(mapping: dict, path: str):
    for part in path.split("."):
        mapping = mapping[part]
    return mapping


@dataclass
class ConfigurationDraft:
    values: dict[str, str]
    rent_expenses: list[RecurringExpenseDraft] = field(default_factory=list)
    buy_expenses: list[RecurringExpenseDraft] = field(default_factory=list)
    one_time_expenses: list[OneTimeExpenseDraft] = field(default_factory=list)

    def rows(self, group: str) -> list:
        if group not in GROUP_PATHS:
            raise ValueError(f"Unknown expense group: {group}")
        return getattr(self, f"{group}_expenses")

    @classmethod
    def new(cls, today: date | None = None) -> "ConfigurationDraft":
        today = today or date.today()
        values = {item.key: item.default for item in FIELDS}
        values["simulation.start"] = today.isoformat()
        values["simulation.end"] = add_months(today, 180).isoformat()
        return cls(values)

    @classmethod
    def from_config(cls, config: SimulationConfig) -> "ConfigurationDraft":
        mapping = asdict(config)
        values = {}
        for spec in FIELDS:
            value = _get(mapping, spec.key)
            if spec.kind == "percent":
                value = shift_decimal(value, 2)
            values[spec.key] = str(value)
        draft = cls(values)
        for group, path in GROUP_PATHS.items():
            for expense in _get(mapping, path):
                fields = {
                    key: "" if value is None else str(value)
                    for key, value in expense.items()
                }
                if group != "one_time":
                    fields["annual_increase"] = str(
                        shift_decimal(expense["annual_increase"], 2)
                    )
                row_type = (
                    OneTimeExpenseDraft
                    if group == "one_time"
                    else RecurringExpenseDraft
                )
                draft.rows(group).append(row_type(**fields))
        return draft

    def validate(self) -> tuple[SimulationConfig | None, dict[str, str]]:
        mapping, errors, locations = {}, {}, {}

        def convert(text, kind, ui_key, config_key):
            locations[f"config.{config_key}"] = ui_key
            try:
                return parse_input(text, kind)
            except ValueError as exc:
                errors[ui_key] = str(exc)
                return None

        for spec in FIELDS:
            text = self.values[spec.key]
            if not spec.required and not text.strip():
                text = spec.default
            _put(
                mapping,
                spec.key,
                convert(text, spec.kind, spec.key, spec.key),
            )
        for group, path in GROUP_PATHS.items():
            rows = []
            for index, row in enumerate(self.rows(group)):
                fields = asdict(row)
                fields.pop("id")
                for key, text in fields.items():
                    config_key = f"{path}[{index}].{key}"
                    ui_key = f"{group}/{row.id}/{key}"
                    locations[f"config.{config_key}"] = ui_key
                    if key == "first_due" and not text.strip():
                        fields[key] = None
                    elif key in ("amount", "annual_increase", "date", "first_due"):
                        if key == "annual_increase" and not text.strip():
                            text = "0"
                        kind = {
                            "amount": "money",
                            "annual_increase": "percent",
                            "date": "date",
                            "first_due": "date",
                        }[key]
                        fields[key] = convert(text, kind, ui_key, config_key)
                rows.append(fields)
            _put(mapping, path, rows)
        if errors:
            return None, errors
        try:
            return config_from_mapping(mapping), {}
        except ConfigurationError as exc:
            key = locations.get(exc.path, exc.path.removeprefix("config."))
            return None, {key: exc.message}


class EditorController:
    def __init__(self, draft: ConfigurationDraft | None = None) -> None:
        self.draft = draft if draft is not None else ConfigurationDraft.new()
        self.revision = 0
        self.config, self.errors = self.draft.validate()

    def _changed(self) -> None:
        self.revision += 1
        self.config, self.errors = self.draft.validate()

    def edit(self, key: str, text: str) -> None:
        if key in FIELD_BY_KEY:
            if self.draft.values[key] == text:
                return
            self.draft.values[key] = text
        else:
            group, row_id, name = key.split("/")
            rows = self.draft.rows(group)
            index = next((i for i, row in enumerate(rows) if row.id == row_id), None)
            if index is None:
                return  # Ignore callbacks from a row that was just removed.
            row = rows[index]
            if name == "id" or name not in asdict(row):
                raise ValueError(f"Unknown expense field: {name}")
            if getattr(row, name) == text:
                return
            rows[index] = replace(row, **{name: text})
        self._changed()

    def add_expense(self, group: str) -> ExpenseDraft:
        row = OneTimeExpenseDraft() if group == "one_time" else RecurringExpenseDraft()
        self.draft.rows(group).append(row)
        self._changed()
        return row

    def remove_expense(self, group: str, row_id: str) -> None:
        rows = self.draft.rows(group)
        for index, row in enumerate(rows):
            if row.id == row_id:
                del rows[index]
                self._changed()
                return
