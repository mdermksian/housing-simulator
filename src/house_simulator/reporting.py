"""A stable, wide CSV suitable for plotting both scenarios on one time axis."""

import csv
from decimal import Decimal, localcontext
from pathlib import Path

from .simulation.engine import ARITHMETIC
from .simulation.state import SimulationResult

METRICS = (
    "cash",
    "investments",
    "home_value",
    "mortgage_principal",
    "accrued_mortgage_interest",
    "equity",
    "net_worth",
    "net_worth_after_selling_costs",
    "cumulative_income",
    "cumulative_housing_cash_outflows",
    "cumulative_housing_expenses",
)
CSV_COLUMNS = (
    "date",
    "elapsed_days",
    *(f"{name}_{metric}" for name in ("rent", "buy") for metric in METRICS),
    "net_worth_difference",
    "net_worth_after_selling_costs_difference",
)


def _money(value: Decimal) -> str:
    rounded = value.quantize(Decimal("0.01"))
    return format(rounded if rounded else abs(rounded), ".2f")


def write_csv(result: SimulationResult, path: str | Path) -> None:
    with (
        Path(path).open("w", newline="", encoding="utf-8") as output,
        localcontext(ARITHMETIC),
    ):
        writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for snapshot in result.snapshots:
            row = {
                "date": snapshot.date.isoformat(),
                "elapsed_days": snapshot.elapsed_days,
            }
            for name in ("rent", "buy"):
                account = snapshot.state.scenario(name)
                for metric in METRICS:
                    row[f"{name}_{metric}"] = _money(getattr(account, metric))
            row["net_worth_difference"] = _money(snapshot.net_worth_difference)
            row["net_worth_after_selling_costs_difference"] = _money(
                snapshot.net_worth_after_selling_costs_difference
            )
            writer.writerow(row)
