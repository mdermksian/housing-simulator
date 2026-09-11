"""Typed configuration and strict, precision-preserving YAML loading.

All rates are decimal fractions. Python callers may supply Decimal, integer,
or string amounts; binary floats are rejected instead of silently approximated.
"""

import types
from dataclasses import MISSING, dataclass, fields, is_dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Literal, get_args, get_origin, get_type_hints

import yaml

ZERO = Decimal(0)


class ConfigurationError(ValueError):
    pass


def _decimal(value: object, path: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (Decimal, int, str)):
        raise ConfigurationError(f"{path}: expected a decimal number (not a float)")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise ConfigurationError(f"{path}: expected a decimal number") from exc
    if not result.is_finite():
        raise ConfigurationError(f"{path}: must be finite")
    return result


def _numbers(instance: object, **limits: str) -> None:
    for name, limit in limits.items():
        value = _decimal(getattr(instance, name), name)
        if limit == "nonnegative" and value < 0:
            raise ConfigurationError(f"{name}: must be nonnegative")
        if limit == "growth" and value <= -1:
            raise ConfigurationError(f"{name}: must be greater than -1")
        if limit == "fraction" and not 0 <= value <= 1:
            raise ConfigurationError(f"{name}: must be between 0 and 1")
        object.__setattr__(instance, name, value)


def _date(value: object, path: str) -> date:
    if type(value) is date:
        return value
    if isinstance(value, str):
        try:
            parsed = date.fromisoformat(value)
            if parsed.isoformat() == value:
                return parsed
        except ValueError:
            pass
    raise ConfigurationError(f"{path}: expected an ISO date (YYYY-MM-DD)")


@dataclass(frozen=True)
class TimelineConfig:
    start: date
    end: date

    def __post_init__(self) -> None:
        object.__setattr__(self, "start", _date(self.start, "start"))
        object.__setattr__(self, "end", _date(self.end, "end"))
        if self.end <= self.start:
            raise ConfigurationError("end: must be after start")


@dataclass(frozen=True)
class HouseholdConfig:
    starting_wealth: Decimal
    monthly_income: Decimal
    cash_reserve: Decimal
    annual_income_increase: Decimal = ZERO
    savings_return: Decimal = ZERO
    investment_return: Decimal = ZERO

    def __post_init__(self) -> None:
        _numbers(
            self,
            starting_wealth="nonnegative",
            monthly_income="nonnegative",
            cash_reserve="nonnegative",
            annual_income_increase="growth",
            savings_return="growth",
            investment_return="growth",
        )


@dataclass(frozen=True)
class RecurringExpense:
    name: str
    amount: Decimal
    schedule: Literal["monthly", "yearly"] = "monthly"
    annual_increase: Decimal = ZERO
    first_due: date | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ConfigurationError("name: must be a nonempty string")
        _numbers(self, amount="nonnegative", annual_increase="growth")
        if self.schedule not in ("monthly", "yearly"):
            raise ConfigurationError("schedule: must be monthly or yearly")
        if self.first_due is not None:
            object.__setattr__(self, "first_due", _date(self.first_due, "first_due"))


def _expenses(instance: "RentConfig | BuyConfig") -> None:
    expenses = tuple(instance.expenses)
    if any(not isinstance(item, RecurringExpense) for item in expenses):
        raise ConfigurationError("expenses: expected RecurringExpense values")
    names = [item.name for item in expenses]
    if len(names) != len(set(names)):
        raise ConfigurationError("expenses: names must be unique within each scenario")
    object.__setattr__(instance, "expenses", expenses)


@dataclass(frozen=True)
class RentConfig:
    monthly_rent: Decimal
    annual_increase: Decimal = ZERO
    expenses: tuple[RecurringExpense, ...] = ()

    def __post_init__(self) -> None:
        _numbers(self, monthly_rent="nonnegative", annual_increase="growth")
        _expenses(self)


@dataclass(frozen=True)
class MortgageConfig:
    annual_rate: Decimal
    term_years: int

    def __post_init__(self) -> None:
        _numbers(self, annual_rate="nonnegative")
        if type(self.term_years) is not int or self.term_years <= 0:
            raise ConfigurationError("term_years: must be a positive integer")


@dataclass(frozen=True)
class BuyConfig:
    purchase_price: Decimal
    down_payment: Decimal
    mortgage: MortgageConfig
    purchase_closing_costs: Decimal = ZERO
    appreciation: Decimal = ZERO
    selling_cost_fraction: Decimal = ZERO
    expenses: tuple[RecurringExpense, ...] = ()

    def __post_init__(self) -> None:
        _numbers(
            self,
            purchase_price="nonnegative",
            down_payment="nonnegative",
            purchase_closing_costs="nonnegative",
            appreciation="growth",
            selling_cost_fraction="fraction",
        )
        if self.down_payment > self.purchase_price:
            raise ConfigurationError("down_payment: cannot exceed purchase_price")
        if not isinstance(self.mortgage, MortgageConfig):
            raise ConfigurationError("mortgage: expected MortgageConfig")
        _expenses(self)


@dataclass(frozen=True)
class OneTimeExpense:
    name: str
    date: date
    amount: Decimal
    target: Literal["rent", "buy", "both"] = "both"

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ConfigurationError("name: must be a nonempty string")
        _numbers(self, amount="nonnegative")
        object.__setattr__(self, "date", _date(self.date, "date"))
        if self.target not in ("rent", "buy", "both"):
            raise ConfigurationError("target: must be rent, buy, or both")


@dataclass(frozen=True)
class SimulationConfig:
    simulation: TimelineConfig
    household: HouseholdConfig
    rent: RentConfig
    buy: BuyConfig
    one_time_expenses: tuple[OneTimeExpense, ...] = ()

    def __post_init__(self) -> None:
        for name, cls in (
            ("simulation", TimelineConfig),
            ("household", HouseholdConfig),
            ("rent", RentConfig),
            ("buy", BuyConfig),
        ):
            if not isinstance(getattr(self, name), cls):
                raise ConfigurationError(f"{name}: expected {cls.__name__}")
        if (
            self.buy.down_payment + self.buy.purchase_closing_costs
            > self.household.starting_wealth
        ):
            raise ConfigurationError(
                "buy.down_payment + buy.purchase_closing_costs: "
                "cannot exceed household.starting_wealth"
            )
        for scenario in ("rent", "buy"):
            for index, expense in enumerate(getattr(self, scenario).expenses):
                if expense.first_due and expense.first_due < self.simulation.start:
                    raise ConfigurationError(
                        f"{scenario}.expenses[{index}].first_due: cannot precede start"
                    )
        expenses = tuple(self.one_time_expenses)
        for index, expense in enumerate(expenses):
            if not isinstance(expense, OneTimeExpense):
                raise ConfigurationError(
                    f"one_time_expenses[{index}]: expected OneTimeExpense"
                )
            if not self.simulation.start <= expense.date <= self.simulation.end:
                raise ConfigurationError(
                    f"one_time_expenses[{index}].date: must be within the simulation"
                )
        object.__setattr__(self, "one_time_expenses", expenses)


class _DecimalLoader(yaml.SafeLoader):
    """SafeLoader with exact decimals, date strings, and duplicate-key rejection."""

    def construct_mapping(self, node, deep=False):
        result = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str):
                raise ConfigurationError("YAML field names must be strings")
            if key in result:
                raise ConfigurationError(f"{key}: duplicate YAML field")
            result[key] = self.construct_object(value_node, deep=deep)
        return result


def _yaml_decimal(loader, node):
    # Preserve nonfinite values until field validation can identify their path.
    value = loader.construct_scalar(node).replace("_", "")
    special = value.lower().lstrip("+-")
    if special == ".inf":
        return Decimal("-Infinity" if value.startswith("-") else "Infinity")
    if special == ".nan":
        return Decimal("NaN")
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise ConfigurationError(
            f"line {node.start_mark.line + 1}: expected a decimal number"
        ) from exc


_DecimalLoader.add_constructor("tag:yaml.org,2002:float", _yaml_decimal)
_DecimalLoader.add_constructor(
    "tag:yaml.org,2002:timestamp", yaml.SafeLoader.construct_scalar
)


def _decode(expected, value, path: str):
    """Decode only the small set of types used by our configuration dataclasses."""
    origin = get_origin(expected)
    if origin is types.UnionType:
        if value is None and type(None) in get_args(expected):
            return None
        return _decode(get_args(expected)[0], value, path)
    if origin is Literal:
        if value not in get_args(expected):
            raise ConfigurationError(f"{path}: expected one of {get_args(expected)}")
        return value
    if origin is tuple:
        if not isinstance(value, list):
            raise ConfigurationError(f"{path}: expected a list")
        return tuple(
            _decode(get_args(expected)[0], item, f"{path}[{index}]")
            for index, item in enumerate(value)
        )
    if is_dataclass(expected):
        if not isinstance(value, dict):
            raise ConfigurationError(f"{path}: expected a mapping")
        valid = {item.name for item in fields(expected)}
        if unknown := value.keys() - valid:
            name = sorted(unknown)[0]
            raise ConfigurationError(f"{path}.{name}: unknown field")
        for item in fields(expected):
            if (
                item.name not in value
                and item.default is MISSING
                and item.default_factory is MISSING
            ):
                raise ConfigurationError(f"{path}.{item.name}: required field")
        hints = get_type_hints(expected)
        kwargs = {
            name: _decode(hints[name], item, f"{path}.{name}")
            for name, item in value.items()
        }
        try:
            return expected(**kwargs)
        except (ConfigurationError, TypeError) as exc:
            raise ConfigurationError(f"{path}.{exc}") from exc
    if expected is Decimal:
        return _decimal(value, path)
    if expected is date:
        return _date(value, path)
    if type(value) is not expected:
        raise ConfigurationError(f"{path}: expected {expected.__name__}")
    return value


def load_config(path: str | Path) -> SimulationConfig:
    try:
        with Path(path).open(encoding="utf-8") as source:
            document = yaml.load(source, Loader=_DecimalLoader)
        return _decode(SimulationConfig, document, "config")
    except yaml.YAMLError as exc:
        raise ConfigurationError(f"Invalid YAML: {exc}") from exc
