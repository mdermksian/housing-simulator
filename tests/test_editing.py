from dataclasses import asdict, replace
from datetime import date
from decimal import localcontext

import pytest

from house_simulator import (
    ConfigurationError,
    OneTimeExpense,
    RecurringExpense,
    config_from_mapping,
    load_config,
    save_config,
)
from house_simulator.application.editing import (
    FIELDS,
    ConfigurationDraft,
    EditorController,
)


def test_new_draft_dates_required_financial_fields_and_defaults():
    draft = ConfigurationDraft.new(date(2024, 2, 29))
    assert draft.values["simulation.end"] == "2039-02-28"
    assert draft.values["buy.mortgage.term_years"] == "30"
    assert draft.values["household.starting_wealth"] == ""
    assert draft.values["buy.mortgage.annual_rate"] == ""
    assert draft.values["buy.appreciation"] == "0"
    config, errors = draft.validate()
    assert config is None
    assert errors["household.monthly_income"] == "Required"
    assert not draft.rent_expenses


def test_all_fields_and_expense_types_round_trip(config, tmp_path):
    config = replace(
        config,
        household=replace(
            config.household, savings_return="0.012345678901234567890123456789123456789"
        ),
        rent=replace(
            config.rent,
            expenses=(
                RecurringExpense(
                    "Insurance", "50", "yearly", "0.0123", date(2026, 6, 1)
                ),
            ),
        ),
        buy=replace(
            config.buy,
            expenses=(
                RecurringExpense("Maintenance", "30.12345678901234567890123456789"),
            ),
        ),
        one_time_expenses=tuple(
            OneTimeExpense(target, date(2026, 3, 1), "10", target)
            for target in ("rent", "buy", "both")
        ),
    )
    with localcontext() as context:
        context.prec = 6
        draft = ConfigurationDraft.from_config(config)
        rebuilt, errors = draft.validate()
    assert not errors
    assert rebuilt == config
    assert (
        draft.values["household.savings_return"]
        == "1.2345678901234567890123456789123456789"
    )
    path = tmp_path / "config.yaml"
    save_config(rebuilt, path)
    assert load_config(path) == config

    # Every non-expense leaf in the schema has a field, with no toy UI metadata.
    def leaves(mapping, prefix=""):
        result = set()
        for key, value in mapping.items():
            path = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                result |= leaves(value, path)
            elif not isinstance(value, tuple):
                result.add(path)
        return result

    assert {spec.key for spec in FIELDS} == leaves(asdict(config))


@pytest.mark.parametrize(
    ("key", "text", "message"),
    [
        ("household.monthly_income", "-", "decimal"),
        ("household.monthly_income", "-10", "nonnegative"),
        ("buy.appreciation", "-100", "greater than -1"),
        ("buy.selling_cost_fraction", "101", "between 0 and 1"),
        ("buy.mortgage.term_years", "0", "positive integer"),
        ("buy.mortgage.term_years", "1.5", "whole number"),
        ("simulation.end", "2026-02-30", "valid date"),
        ("household.savings_return", "NaN", "finite"),
    ],
)
def test_invalid_inputs_remain_editable(config, key, text, message):
    editor = EditorController(ConfigurationDraft.from_config(config))
    editor.edit(key, text)
    assert editor.draft.values[key] == text
    assert editor.config is None
    assert message in editor.errors[key]


def test_structured_errors_for_dataclass_and_nested_mapping(config):
    with pytest.raises(ConfigurationError) as error:
        replace(config.rent, monthly_rent="-1")
    assert error.value.path == "monthly_rent"
    mapping = asdict(config)
    # Decoder accepts lists as in YAML.
    mapping["rent"]["expenses"] = []
    mapping["buy"]["expenses"] = []
    mapping["one_time_expenses"] = []
    mapping["buy"]["mortgage"]["annual_rate"] = "-1"
    with pytest.raises(ConfigurationError) as error:
        config_from_mapping(mapping)
    assert error.value.path == "config.buy.mortgage.annual_rate"
    assert "nonnegative" in str(error.value)


def test_row_identity_errors_and_late_callbacks_after_removal(config):
    editor = EditorController(ConfigurationDraft.from_config(config))
    first = editor.add_expense("rent")
    second = editor.add_expense("rent")
    editor.edit(f"rent/{second.id}/name", "Parking")
    editor.edit(f"rent/{second.id}/amount", "-5")
    editor.remove_expense("rent", first.id)
    assert list(editor.errors) == [f"rent/{second.id}/amount"]
    editor.edit(f"rent/{first.id}/amount", "999")
    assert editor.draft.rent_expenses[0].id == second.id
    editor.edit(f"rent/{second.id}/amount", "25")
    assert editor.config.rent.expenses[0].amount == 25
    assert editor.config.rent.expenses[0].first_due is None


def test_cross_field_errors(config):
    editor = EditorController(ConfigurationDraft.from_config(config))
    editor.edit("buy.purchase_price", "200000")
    editor.edit("buy.down_payment", "100000")
    editor.edit("buy.purchase_closing_costs", "1")
    assert editor.config is None
    assert "starting_wealth" in next(iter(editor.errors.values()))
    editor.edit("buy.purchase_closing_costs", "0")
    assert editor.config is not None
    for _ in range(2):
        row = editor.add_expense("buy")
        editor.edit(f"buy/{row.id}/name", "Tax")
        editor.edit(f"buy/{row.id}/amount", "20")
    assert "unique" in editor.errors["buy.expenses"]


def test_one_time_date_error_maps_to_stable_row(config):
    editor = EditorController(ConfigurationDraft.from_config(config))
    row = editor.add_expense("one_time")
    for key, value in (("name", "Repair"), ("amount", "50"), ("date", "2030-01-01")):
        editor.edit(f"one_time/{row.id}/{key}", value)
    assert "within the simulation" in editor.errors[f"one_time/{row.id}/date"]


def test_optional_numbers_can_be_cleared_without_losing_raw_input(config):
    editor = EditorController(ConfigurationDraft.from_config(config))
    editor.edit("buy.appreciation", "")
    row = editor.add_expense("rent")
    for key, value in (("name", "Parking"), ("amount", "20"), ("annual_increase", "")):
        editor.edit(f"rent/{row.id}/{key}", value)
    assert editor.config.buy.appreciation == 0
    assert editor.config.rent.expenses[0].annual_increase == 0
    assert editor.draft.values["buy.appreciation"] == ""
    assert editor.draft.rent_expenses[0].annual_increase == ""


def test_mapping_keys_have_structured_error():
    with pytest.raises(ConfigurationError) as error:
        config_from_mapping({1: None, "invalid": None})
    assert error.value.path == "config"
    assert "field names" in error.value.message
