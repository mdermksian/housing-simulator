"""Format committed results without converting monetary values to floats."""

from decimal import localcontext

from ...application.execution import RunUpdate
from ...simulation.engine import ARITHMETIC
from ..models import ModelBinding

METRICS = (
    ("cash", "Cash"),
    ("investments", "Investments"),
    ("home_value", "Home value"),
    ("mortgage_principal", "Mortgage principal"),
    ("accrued_mortgage_interest", "Accrued mortgage interest"),
    ("equity", "Home equity"),
    ("net_worth", "Net worth"),
    ("net_worth_after_selling_costs", "Net worth after selling costs"),
    ("cumulative_income", "Cumulative income"),
    ("cumulative_housing_cash_outflows", "Housing cash outflows"),
)


def status_text(update: RunUpdate) -> str:
    if update.phase == "idle":
        return "Complete the configuration and press Run. * marks required fields."
    status = update.phase.capitalize()
    if update.date is not None:
        status += (
            f" · Last committed date: {update.date} · {update.snapshot_count} snapshots"
        )
    elif update.phase == "failed":
        status += " · No committed state"
    if update.phase in ("cancelled", "failed"):
        status += " · Incomplete results"
    if update.message:
        status += f"\n{update.message}"
    return status


class ResultBindings(ModelBinding):
    def __init__(self, model_factory, row_factory) -> None:
        super().__init__(model_factory, row_factory, "label")
        self.difference = ""
        self._result = None

    def refresh(self, update: RunUpdate) -> None:
        if update.result is self._result:
            return
        self._result = update.result
        self.difference = ""
        rows = []
        if update.result is not None and update.result.snapshots:
            snapshot = update.result.snapshots[-1]
            with localcontext(ARITHMETIC):
                for metric, label in METRICS:
                    rows.append(
                        {
                            "label": label,
                            "rent": f"${getattr(snapshot.state.rent, metric):,.2f}",
                            "buy": f"${getattr(snapshot.state.buy, metric):,.2f}",
                        }
                    )
                self.difference = (
                    "Buyer minus renter net worth: "
                    f"${snapshot.net_worth_difference:,.2f}\n"
                    "After estimated selling costs: "
                    f"${snapshot.net_worth_after_selling_costs_difference:,.2f}"
                )
        self.update(rows)
