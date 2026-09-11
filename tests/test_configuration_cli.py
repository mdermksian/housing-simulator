import csv
import subprocess
import sys
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from house_simulator import (
    ConfigurationError,
    OneTimeExpense,
    RecurringExpense,
    Simulation,
    load_config,
    write_csv,
)
from house_simulator.cli import main
from house_simulator.reporting import CSV_COLUMNS

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "comparison.yaml"


@pytest.fixture
def document():
    return {
        "simulation": {"start": "2026-01-31", "end": "2026-03-15"},
        "household": {
            "starting_wealth": 1000,
            "monthly_income": 100,
            "cash_reserve": 1000,
        },
        "rent": {"monthly_rent": 100},
        "buy": {
            "purchase_price": 0,
            "down_payment": 0,
            "mortgage": {"annual_rate": 0, "term_years": 1},
        },
    }


def write_yaml(tmp_path, document):
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(document), encoding="utf-8")
    return path


def test_example_loads_and_completes():
    config = load_config(EXAMPLE)
    assert config.buy.mortgage.annual_rate == Decimal("0.0658")
    result = Simulation(config).run()
    assert result.completed
    assert len(result.snapshots) == 182
    assert result.snapshots[-1].date == date(2041, 1, 31)


def test_yaml_preserves_decimal_precision(tmp_path, document):
    path = write_yaml(tmp_path, document)
    text = path.read_text().replace(
        "monthly_rent: 100", "monthly_rent: 0.12345678901234567890123456789"
    )
    path.write_text(text)
    assert load_config(path).rent.monthly_rent == Decimal(
        "0.12345678901234567890123456789"
    )


def test_missing_field_has_config_path(tmp_path, document):
    del document["buy"]["mortgage"]["annual_rate"]
    with pytest.raises(
        ConfigurationError, match=r"config.buy.mortgage.annual_rate: required field"
    ):
        load_config(write_yaml(tmp_path, document))


@pytest.mark.parametrize("value", [float("inf"), float("-inf"), float("nan")])
def test_nonfinite_yaml_numbers_have_config_paths(tmp_path, document, value):
    document["rent"]["monthly_rent"] = value
    with pytest.raises(
        ConfigurationError, match=r"config.rent.monthly_rent: must be finite"
    ):
        load_config(write_yaml(tmp_path, document))


@pytest.mark.parametrize(
    ("section", "key", "value", "error"),
    [
        ("rent", "unknown", 1, "config.rent.unknown"),
        ("rent", "monthly_rent", -1, "config.rent.monthly_rent"),
        ("rent", "monthly_rent", True, "config.rent.monthly_rent"),
        ("rent", "monthly_rent", "NaN", "config.rent.monthly_rent"),
        ("household", "investment_return", -1, "config.household.investment_return"),
        ("simulation", "start", "2026-02-30", "config.simulation.start"),
        ("simulation", "end", "2025-01-01", "config.simulation.end"),
        ("buy", "selling_cost_fraction", "1.1", "config.buy.selling_cost_fraction"),
        ("buy", "down_payment", 1, "config.buy.down_payment"),
        ("rent", "expenses", {}, "config.rent.expenses"),
    ],
)
def test_validation_paths(tmp_path, document, section, key, value, error):
    document[section][key] = value
    with pytest.raises(ConfigurationError, match=error):
        load_config(write_yaml(tmp_path, document))


@pytest.mark.parametrize(
    ("expense", "error"),
    [
        ({"name": "tax", "amount": 10, "schedule": "weekly"}, "schedule"),
        ({"name": "tax", "amount": 10, "first_due": "2025-01-01"}, "first_due"),
        ({"name": "", "amount": 10}, "name"),
        ({"name": "tax", "amount": "Infinity"}, "amount"),
    ],
)
def test_invalid_expenses(tmp_path, document, expense, error):
    document["buy"]["expenses"] = [expense]
    with pytest.raises(ConfigurationError, match=error):
        load_config(write_yaml(tmp_path, document))


@pytest.mark.parametrize("term", [0, -1, True, "30", 1.5])
def test_mortgage_term_validation(tmp_path, document, term):
    document["buy"]["mortgage"]["term_years"] = term
    with pytest.raises(ConfigurationError, match="term_years"):
        load_config(write_yaml(tmp_path, document))


def test_insufficient_purchase_funding(tmp_path, document):
    document["buy"]["purchase_price"] = 10000
    document["buy"]["down_payment"] = 1000
    document["buy"]["purchase_closing_costs"] = 1
    with pytest.raises(ConfigurationError, match="starting_wealth"):
        load_config(write_yaml(tmp_path, document))


def test_duplicate_expense_names(tmp_path, document):
    document["rent"]["expenses"] = [
        {"name": "bill", "amount": 10},
        {"name": "bill", "amount": 20},
    ]
    with pytest.raises(ConfigurationError, match="names must be unique"):
        load_config(write_yaml(tmp_path, document))


@pytest.mark.parametrize(
    "text",
    [
        "rent: {}\nrent: {}\n",
        "rent: [unterminated",
        "!!python/object/apply:os.system ['false']",
        "rent:\n  monthly_rent: .inf\n",
        "rent:\n  monthly_rent: .nan\n",
        "",
        "- list\n- root\n",
        "1: invalid key\n",
    ],
)
def test_yaml_rejects_duplicate_unsafe_and_malformed_documents(tmp_path, text):
    path = tmp_path / "bad.yaml"
    path.write_text(text)
    with pytest.raises(ConfigurationError):
        load_config(path)


def test_python_configuration_is_validated_and_immutable(config):
    with pytest.raises(ConfigurationError, match="float"):
        replace(config.rent, monthly_rent=0.1)
    with pytest.raises(ConfigurationError, match="within the simulation"):
        replace(
            config,
            one_time_expenses=(OneTimeExpense("late", date(2030, 1, 1), "10"),),
        )
    original = [RecurringExpense("bill", "10")]
    updated = replace(config.rent, expenses=original)
    original.clear()
    assert len(updated.expenses) == 1


def test_csv_values_and_columns(tmp_path, document):
    result = Simulation(load_config(write_yaml(tmp_path, document))).run()
    output = tmp_path / "results.csv"
    write_csv(result, output)
    with output.open(newline="") as source:
        reader = csv.DictReader(source)
        assert tuple(reader.fieldnames) == CSV_COLUMNS
        rows = list(reader)
    assert [row["date"] for row in rows] == ["2026-01-31", "2026-02-28", "2026-03-15"]
    assert [row["elapsed_days"] for row in rows] == ["0", "28", "43"]
    assert rows[-1]["rent_cash"] == "1000.00"
    assert rows[-1]["buy_cash"] == "1000.00"
    assert rows[-1]["buy_investments"] == "100.00"
    assert rows[-1]["rent_cumulative_housing_cash_outflows"] == "100.00"
    assert rows[-1]["net_worth_difference"] == "100.00"


def test_cli_subprocess(tmp_path, document):
    config_path = write_yaml(tmp_path, document)
    output = tmp_path / "output.csv"
    process = subprocess.run(
        [
            sys.executable,
            "-m",
            "house_simulator",
            "run",
            str(config_path),
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert process.returncode == 0, process.stderr
    assert "3 snapshots" in process.stdout
    assert output.exists()


def test_cli_failure_exports_only_committed_history(tmp_path, document, capsys):
    document["household"]["starting_wealth"] = 100
    document["household"]["monthly_income"] = 0
    document["simulation"]["end"] = "2026-04-30"
    output = tmp_path / "output.csv"
    assert (
        main(["run", str(write_yaml(tmp_path, document)), "--output", str(output)]) == 1
    )
    with output.open() as source:
        rows = list(csv.DictReader(source))
    assert [row["date"] for row in rows] == ["2026-01-31", "2026-02-28"]
    message = capsys.readouterr().err
    assert "rent on 2026-03-31" in message
    assert "requires 100.00" in message


def test_cli_opening_failure_exports_header(tmp_path, document, capsys):
    document["one_time_expenses"] = [
        {"name": "moving", "date": "2026-01-31", "amount": 2000}
    ]
    output = tmp_path / "output.csv"
    assert (
        main(["run", str(write_yaml(tmp_path, document)), "--output", str(output)]) == 1
    )
    with output.open() as source:
        assert list(csv.DictReader(source)) == []
    assert "0 committed snapshots" in capsys.readouterr().err


def test_cli_configuration_and_io_errors(tmp_path, document, capsys):
    path = write_yaml(tmp_path, document)
    before = path.read_text()
    assert main(["run", str(path), "--output", str(path)]) == 2
    assert path.read_text() == before
    output = tmp_path / "missing" / "result.csv"
    assert main(["run", str(path), "--output", str(output)]) == 2
    assert "Error:" in capsys.readouterr().err
