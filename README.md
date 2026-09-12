# Housing Simulator

Compare renting and buying over a configured period, accounting for household
income, invested savings, mortgage debt, home value, and housing expenses. The
Python simulator advances directly to dates when something changes and records
immutable snapshots for plotting. Configuration and execution are available
through Python, a YAML-to-CSV command line, and an optional Slint desktop editor.
The desktop can define the full configuration, run a comparison, and export results.

## Run a comparison

Requires Python 3.12 or newer. Install and run with uv:

```sh
uv sync
uv run house-simulator run examples/comparison.yaml --output results.csv
```

Alternatively, install with `python -m pip install -e .`, then run
`house-simulator run examples/comparison.yaml --output results.csv`.
`python -m house_simulator` and `python main.py` accept the same arguments after
installation.

The [example configuration](examples/comparison.yaml) includes monthly income,
rent and utilities, annual property tax, a mortgage, and a dated roof replacement.
Its 15-year comparison produces 182 snapshots: the initial state, 180 monthly
updates, and one additional date for the roof expense.

All amounts are dollars. Rates are decimal fractions: **0.03 means 3%**.
Income is take-home income. Returns and price changes are deterministic.

## Use the desktop editor

```sh
uv run --extra ui house-simulator ui
```

Alternatively, install with `python -m pip install -e '.[ui]'` and run
`house-simulator ui`. Slint is an optional dependency; the simulator and CSV CLI
work without it. The UI requires a desktop display. All `.slint` files are packaged
with the application and load independently of the current working directory.

Use the section navigation for **Simulation**, **Household**, **Renting**,
**Buying**, **One-time expenses**, and **Results**. Forms scroll independently of
the toolbar. Every field in the YAML schema is editable, including both lists of
recurring expenses, mortgage details, and one-time expense targets.

A new document starts with today's date, an end date fifteen calendar years later,
a 30-year mortgage term, zero optional rates/costs, and empty expense lists.
Required financial inputs start blank. Fields marked `*` are required; use `0`
when the amount really is zero. Run and Save become available once the complete
configuration is valid. Errors appear beside fields and in the validation summary.

**The form uses percentages, while YAML uses decimal fractions.** Enter `6.58` in
the mortgage percentage field to save `0.0658` in YAML. Monetary amounts and rates
stay as text until Python parses them into exact Decimal values; no binary-float
conversion or UI rounding is involved. Dates use `YYYY-MM-DD`. A blank recurring
expense first due date retains the simulator's automatic schedule. Clearing an
optional rate or cost uses zero while preserving the blank input in the draft.

Each expense has Add and Remove controls. Recurring expenses support monthly or
yearly schedules and annual percentage increases. One-time expenses can target
renting, buying, or both. Expense ordering is retained, and row identity is stable
while other expenses are removed.

### Load, save, and export

- **New** starts a blank document. **Load** reads an existing YAML file.
- **Save** updates the current document; **Save As** chooses another destination.
- **Export CSV**, in Results, writes the last run's committed snapshots.

These actions use path-entry dialogs. Type or paste a path, including `~` for your
home directory; the resolved absolute path is shown before continuing. Relative
paths resolve against the process's working directory. New destinations default
to your home directory, so personal files can stay outside the repository. Create
parent directories before saving.

An asterisk beside the document filename indicates unsaved edits. New, Load, and
Close confirm before discarding them. Replacing another existing destination also
requires confirmation. Failed loads do not replace the current form. YAML and CSV
writes are atomic: failure leaves the existing destination intact. CSV export
cannot replace the active YAML document.

Saved YAML contains validated configuration values, including exact decimals.
Comments and original formatting are not preserved. Incomplete drafts cannot be
saved as runnable YAML.

### Running and reading results

**Run** captures the current validated configuration and starts a Python worker.
Editing, saving, loading, and additional runs are disabled until it finishes;
section navigation remains available. Progress reports the last committed date
and snapshot count. **Cancel** requests a stop after the current simulation step.

Results compare cash, investments, home value, mortgage principal, accrued
interest, equity, net worth, estimated net worth after selling costs, cumulative
income, and housing cash outflows. Buyer-minus-renter differences are shown below
the comparison. No charts or manual stepping controls are included yet.

Completed, cancelled, and failed runs are distinguished explicitly. Cancelled and
failed runs retain their committed snapshots for viewing and CSV export. A failure
before the initial snapshot reports that there is no committed state and disables
export. Insufficient-funds failures identify the date, scenario, obligation,
required amount, and available funds.

Each run retains its exact configuration. Editing or loading another configuration
marks older results accordingly; exporting still exports that earlier run. Run
again to produce results for the edited form.

Close requests cancellation and waits for the worker's current step to finish.
The pinned Slint Python API has no native close-request hook: when closing through
the OS window controls with unsaved edits or an active run, the window briefly
reopens to show confirmation. The toolbar's **Close** button confirms directly.
Cancelling that confirmation leaves the editor and run intact.

### Python–Slint boundary

```text
Slint callbacks → desktop feature adapters → plain Python application controllers
                                ↑
                 property/model updates on the UI thread
```

The `application` package groups behavior into configuration editing, expense
rows, documents, execution, and workspace commands. `ConfigurationDraft` retains
raw input strings; `EditorController` converts them through the same validation
entry point used by YAML. `ConfigurationError.path` identifies fields without
parsing human-readable messages. The public `config_from_mapping(mapping)` and
`save_config(config, path)` functions support non-UI clients too.

A `RunController` owns one worker thread and a bounded latest-progress mailbox.
Only that worker touches the running simulator. It checks cancellation between
steps and transfers an immutable result at completion. No application or simulator
module imports Slint.

Desktop adapters publish fields, expense rows, and results into Slint models.
Updates replace only changed model rows, preserving other controls and keyboard
focus. Python draft fields do not automatically become reactive Slint properties:
adapters refresh after commands, and a desktop timer polls worker progress on the
UI thread. Slint model factories are injected, so adapters can be tested with
ordinary Python lists and objects.

The root window composes functional Slint modules for configuration fields,
expense lists, document dialogs, and results. Add future features in the matching
application and desktop groups rather than adding financial rules to the root
window. `desktop/app.py` owns Slint loading, its timer, and window lifecycle.

### Desktop checks

```sh
uv run --extra ui pytest -m 'not ui'  # Application tests and Slint compilation.
uv run --extra ui pytest -m ui       # Real-window workflow and lifecycle tests.
uv run ruff check .
uv run ruff format --check .
uv build                            # Includes the complete Slint resource tree.
```

Core and adapter tests work with base dependencies alone. Compilation tests skip
when Slint is absent; window tests additionally skip on Linux without a configured
display. Real-window tests exercise form callbacks, expense editing, loading,
Run, Cancel, CSV export, and close confirmations. Background cancellation and failure
paths are independently tested with controllable Python workers.

### Quality checks and CI

The GitHub Actions **Quality** workflow runs on pushes, pull requests, and manual
dispatch. It checks Python formatting and lint with Ruff, Slint formatting with
`slint-lsp`, Slint compiler diagnostics, and the full test suite. It uses Python
from `.python-version` and the dependencies in `uv.lock`.

Install the development and UI dependencies before running the checks locally:

```sh
uv sync --locked --dev --extra ui
```

Install **slint-lsp 1.17.1**, matching the project's Slint release series. Download
the prebuilt archive for your operating system from the
[official release](https://github.com/slint-ui/slint/releases/tag/v1.17.1), verify
the SHA-256 shown beside the asset, and put the extracted `slint-lsp` executable
on your `PATH`. No Rust compilation is needed. For Linux x86-64, the archive is
`slint-lsp-x86_64-unknown-linux-gnu.tar.gz` and its SHA-256 is:

```text
6f363163c4deafea085191c2c3cb80d8af8a71510370dac6a1dca21177b571fa
```

Confirm `slint-lsp --version` reports `1.17.1`, then run:

```sh
uv run --no-sync ruff format --check .
uv run --no-sync ruff check .
uv run --no-sync python scripts/slint_quality.py format --check
uv run --no-sync python scripts/slint_quality.py lint
uv run --no-sync pytest -ra
```

`--no-sync` reuses the environment installed above, including its UI extra. The
Slint format check discovers every `.slint` file beneath `src/` and prints diffs
without changing files. To apply formatting locally, run:

```sh
uv run --no-sync ruff format .
uv run --no-sync python scripts/slint_quality.py format
```

Slint lint fails on **warnings as well as errors**, including compiler-reported
deprecations. It compiles the application entry point and its imported components
without creating a window. Reusable components are checked through those imports,
so they are not incorrectly treated as standalone windows. The quality helper is
development tooling; it does not add Slint dependencies to the simulator core.

CI runs window tests using Xvfb and Slint's software renderer. To reproduce that
on Ubuntu, install the desktop runtime and run:

```sh
sudo apt-get install -y xvfb xauth libx11-xcb1 libxkbcommon-x11-0 \
  libxcb-shape0 libxcb-xfixes0 libinput10 libgbm1 fonts-dejavu-core
SLINT_BACKEND=winit-software SLINT_STYLE=fluent \
  xvfb-run -a -s "-screen 0 1280x1024x24" uv run --no-sync pytest -ra
```

Without Slint, the formatter, or a display, their respective integration tests
skip locally; CI installs all three so these tests execute.

## YAML configuration

Required sections and fields:

| Section | Required fields |
| --- | --- |
| `simulation` | `start`, `end` as `YYYY-MM-DD`; end must be after start |
| `household` | `starting_wealth`, `monthly_income`, `cash_reserve` |
| `rent` | `monthly_rent` |
| `buy` | `purchase_price`, `down_payment`, `mortgage` |
| `buy.mortgage` | `annual_rate`, positive integer `term_years` |

Optional fields default to zero or empty lists:

| Section | Optional fields |
| --- | --- |
| `household` | `annual_income_increase`, `savings_return`, `investment_return` |
| `rent` | `annual_increase`, `expenses` |
| `buy` | `purchase_closing_costs`, `appreciation`, `selling_cost_fraction`, `expenses` |
| Root | `one_time_expenses` |

Purchase closing costs are a fixed dollar amount. Selling costs are a fraction of
the home's current value. Property tax, insurance, maintenance, and utilities are
explicitly supplied expenses; they are not inferred from the purchase price.

Each recurring expense has `name`, `amount`, and optional `schedule` (`monthly`
by default, or `yearly`), `annual_increase`, and `first_due`:

```yaml
expenses:
  - name: property tax
    amount: 6000
    schedule: yearly
    annual_increase: 0.02
    first_due: 2026-12-01
```

Names must be unique within each scenario. Without `first_due`, the first payment
falls one complete recurrence after the simulation starts. An explicit first due
date anchors all later payments and may equal the simulation start. A first due
date beyond the horizon is allowed. Annual amount changes always follow the
simulation's anniversary, regardless of the payment anchor; an anniversary
payment uses the increased amount.

One-time expenses use `name`, `date`, `amount`, and `target` (`rent`, `buy`, or
`both`, which is the default). Dates must fall within the inclusive simulation
period. An expense targeting both charges its full amount to each scenario.

```yaml
one_time_expenses:
  - name: moving
    date: 2026-02-15
    amount: 2000
    target: both
```

Unknown fields, duplicate YAML keys, negative amounts, nonfinite numbers, invalid
dates or schedules, and unaffordable down payments plus closing costs are rejected.
Growth/increase rates must be greater than -1; mortgage rates must be nonnegative;
selling-cost fractions must be between 0 and 1. YAML decimal values retain their
precision without an intermediate binary float conversion.

## Stepping from Python

```python
from house_simulator import Simulation, load_config, write_csv

simulation = Simulation(load_config("examples/comparison.yaml"))
initial = simulation.history[0]
next_snapshot = simulation.step()  # All updates on the next required date.
print(next_snapshot.date, next_snapshot.state.buy.net_worth)

result = simulation.run()  # Continue from the current state.
write_csv(result, "results.csv")
```

The package also exports the frozen configuration dataclasses for direct Python
configuration. Use `Decimal`, integers, or decimal strings for monetary and rate
fields; binary floats are rejected. Use `dataclasses.replace` to derive a changed
configuration and construct a new simulation to rerun it.

`state`, `current_date`, `config`, and `history` are read-only properties.
`history` is a tuple of immutable snapshots. `step()` returns a snapshot, or
`None` once complete. `run()` includes the entire history, including earlier
manual steps, and repeated completed runs return equivalent results.
`result` exposes committed history, completion status, and any financial failure.

## Time and accounting rules

The event queue orders actions by date, phase, and insertion order. A step accrues
growth since the previous date, applies annual amount changes, receives income,
pays obligations, allocates surplus cash, and commits both scenarios together.
Income can therefore fund a bill due on the same date. Each date appears once.

Monthly schedules preserve their original day: January 31 → February 28 →
March 31. Leap-day yearly schedules return to February 29 in leap years. Dates
with no scheduled activity are skipped. There are always initial and final
snapshots; the final boundary accrues growth and interest even between payments.
There is no extra prorated rent or salary payment at that boundary. Explicit
start-date bills are processed before the initial snapshot. Zero-valued cash
flows create no events.

Savings, investments, and home values grow by
`value × (1 + effective_annual_rate) ** (elapsed_days / 365)`, including leap-year
days. Internal arithmetic uses a local 40-digit Decimal context and retains
unrounded amounts. CSV output rounds to cents using half-even rounding. Monthly
payments and returns are modeling values, not a lender's cent-rounded statement.

Both scenarios receive the same initial liquid wealth and income. The buyer first
pays the down payment and closing costs. Each retains up to the configured cash
reserve and invests the rest. Bills consume cash, then sell only the investments
needed to cover any shortfall. The reserve is spendable and is replenished from
later income, not by automatically selling additional investments.

Surplus cash is invested once after all of a scenario's cash transactions on a
date. Merely observing a scenario, repricing a future bill, or reaching the final
boundary does not trigger a transfer. This prevents unrelated events in the
other scenario from changing investment timing. Cash interest may consequently
leave cash above the reserve until the next transaction. Elapsed-time growth is
invariant to extra observation dates within Decimal precision.

The mortgage uses a fixed monthly payment and nominal annual rate divided by 12.
Interest for each payment period is accrued in proportion to elapsed days within
that anchored calendar period. Payments cover interest then principal; the final
payment clears the remaining debt, including numerical residue. A zero-rate
mortgage repays equal principal installments. No mortgage events remain after
payoff.

Net worth equals cash + investments + home value − mortgage principal − accrued
mortgage interest. Equity excludes accrued interest: home value − principal.
Estimated net worth after selling costs subtracts the configured fraction of home
value; the simulator never forces a sale. Housing cash outflows include down
payments, closing costs, mortgage payments, and expenses. Cumulative housing
expenses include costs and **paid** mortgage interest, excluding down payments
and principal transfers. Unpaid interest is tracked separately as a liability.

If either scenario cannot pay, `step()`/`run()` raises `InsufficientFunds` with
`scenario`, `date`, `required`, `available`, and `obligation`. Neither scenario's
changes on that date are committed. History remains available through
`simulation.result`; further stepping raises the same failure. The CLI exports
committed history and reports the failed obligation on stderr. An opening-date
failure has no snapshots, so its CSV contains only a header.

## CSV output

Each row contains `date`, `elapsed_days`, and `rent_`/`buy_` columns for:

- `cash`, `investments`, `home_value`, `mortgage_principal`,
  `accrued_mortgage_interest`, and `equity`.
- `net_worth` and `net_worth_after_selling_costs`.
- `cumulative_income`, `cumulative_housing_cash_outflows`, and
  `cumulative_housing_expenses`.

`net_worth_difference` and `net_worth_after_selling_costs_difference` are buyer
minus renter; positive values favor buying under the supplied assumptions.
Plot using the date column: row spacing is not necessarily uniform.

CLI exit codes: `0` completed, `1` insufficient funds with committed history
exported, `2` invalid configuration or file I/O failure.

## Extending and testing

The package groups code by behavior: `household`, `renting`, `ownership`, shared
`recurring` cash flows, `configuration`, `reporting`, and `simulation`. Financial
rules are pure functions and immutable actions. `simulation/setup.py` composes
them; `simulation/engine.py` only coordinates growth, events, settlement, and
snapshots.

To add behavior, implement an action's `apply(state, on) -> Effect` and schedule
an `Event` using `Simulation.schedule`. An effect returns new state, future
events, and the scenarios needing reserve allocation after cash transactions.
Actions must avoid external side effects so an entire date can be rolled back.
Successors must be strictly later than their triggering date; events beyond the
horizon are ignored. Add a pure elapsed-time accrual provider in the composition
module for a new growth model. Neither extension requires changing the event loop.

```sh
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

The current version omits charts and manual stepping controls in the desktop UI,
random returns, income/capital-gains tax rules, refinancing, and mortgage overpayments.
