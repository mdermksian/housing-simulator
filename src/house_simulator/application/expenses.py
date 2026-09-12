"""Editable expense rows retain identity independently of their list position."""

from dataclasses import dataclass, field
from uuid import uuid4


@dataclass(frozen=True)
class RecurringExpenseDraft:
    id: str = field(default_factory=lambda: uuid4().hex)
    name: str = ""
    amount: str = ""
    schedule: str = "monthly"
    annual_increase: str = "0"
    first_due: str = ""


@dataclass(frozen=True)
class OneTimeExpenseDraft:
    id: str = field(default_factory=lambda: uuid4().hex)
    name: str = ""
    date: str = ""
    amount: str = ""
    target: str = "both"


ExpenseDraft = RecurringExpenseDraft | OneTimeExpenseDraft
