# Housing Simulator

Compare renting and buying over a configured period, accounting for household
income, invested savings, mortgage debt, home value, and housing expenses. The
Python simulator advances directly to dates when something changes and records
immutable snapshots for plotting. Configuration and execution are available
through Python and a YAML-to-CSV command line. An optional Slint desktop preview
demonstrates editing plain Python state; simulation execution remains in the CLI.

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

## Open the desktop preview

```sh
uv run --extra ui house-simulator ui
```

Alternatively, install with `python -m pip install -e '.[ui]'` and run
`house-simulator ui`. The optional extra pins Slint Python to `1.17.1b2`; the
simulation and CSV command do not require it. A desktop display is needed to open
the window. Slint supplies binary wheels for supported platforms, so no separate
Rust build or generated Python bindings are needed for this scaffold.

The window starts with **My housing comparison** and **15 years**. Edit the name
or duration (1–100 years) to update the summary immediately. Empty names display
**Untitled comparison**. Reset restores the defaults. Preview state is in memory;
the window does not load/save YAML or execute the simulation.

The `.slint` files ship with the Python package and load through package resources,
including relative imports between components. An installed `house-simulator ui`
works from any working directory.

### Python–Slint boundary

```text
Slint callback → feature adapter → Python controller → UI property refresh
```

`application/configuration_preview.py` owns a frozen `PreviewState` and a
`PreviewController` with `rename`, `set_duration`, `reset`, and a derived `summary`.
It imports no Slint code and has no knowledge of windows. Invalid durations are
rejected before replacing state.

`desktop/configuration_preview/bindings.py` defines a small `PreviewView` protocol
and `PreviewBindings`. The adapter assigns Python methods to Slint callbacks and
publishes state into the view's properties. It works with an ordinary Python fake
view in tests. There are no Slint base classes or decorators in the application
layer, and no generic observer framework.

`desktop/app.py` is the composition point and the only production module importing
Slint. It loads the packaged components, constructs the controller and adapter,
and runs the window on the main thread. The CLI imports this module only for the
`ui` command. UI work is synchronous in this initial scaffold.

Python fields do **not** automatically become reactive Slint properties. UI
callbacks explicitly invoke a controller command and then `refresh()`. When
Python initiates a change, publish it explicitly as well:

```python
from house_simulator.application.configuration_preview import PreviewController
from house_simulator.desktop.app import load_components
from house_simulator.desktop.configuration_preview.bindings import PreviewBindings

with load_components() as components:
    window = components.AppWindow()
    controller = PreviewController()
    bindings = PreviewBindings(window, controller)
    controller.rename("Our next home")
    bindings.refresh()
    window.run()
```

The adapter uses the [Slint Python callback and property APIs](https://docs.slint.dev/latest/docs/python/).
Slint's internal bindings connect the editor fields to window properties, while
callbacks communicate user intent to Python. Summary generation and state
validation stay in Python.

### Organizing another UI feature

1. Add a plain Python controller and state under `application/`, grouped by feature.
2. Add that feature's adapter and `.slint` components together under `desktop/`.
   The existing preview groups its editor and summary in separate components.
3. Export explicit component properties and callbacks. Compose them in the small
   `desktop/app.slint` window and wire the adapter in `desktop/app.py`.
4. Test the controller and adapter without Slint, then add a real component
   integration test for the binding surface.

Keep financial rules in the existing simulation modules when adding simulation
controls later. Adapt their results into presentation values at the desktop
boundary rather than introducing Slint types into the simulator.

### Desktop checks

```sh
uv run --extra ui pytest -m 'not ui'  # Includes compilation, without opening windows.
uv run --extra ui pytest -m ui       # Opens and closes a real test window.
uv build                            # Wheel and source distribution include .slint files.
```

Tests for controllers and adapters also run with the base dependencies alone.
Slint compilation tests skip when the optional package is absent; window tests
additionally skip on Linux when no desktop display is configured. The window test
exercises callbacks, property updates, explicit refresh, and event-loop shutdown.

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

The current version omits simulation controls in the desktop UI, plotting, random
returns, income/capital-gains tax rules, refinancing, and mortgage overpayments.
