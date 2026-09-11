"""Command-line configuration, execution, and CSV export."""

import argparse
import sys
from pathlib import Path

from .configuration import ConfigurationError, load_config
from .reporting import write_csv
from .simulation.engine import Simulation
from .simulation.state import InsufficientFunds, SimulationResult


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare renting with buying a home")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="Run a YAML configuration and export CSV")
    run.add_argument("config", type=Path)
    run.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    simulator = None
    try:
        if args.config.resolve() == args.output.resolve():
            raise ConfigurationError("The output path must differ from the YAML input")
        config = load_config(args.config)
        try:
            simulator = Simulation(config)
            result = simulator.run()
        except InsufficientFunds as exc:
            # An opening-date failure has no committed snapshots yet.
            result = (
                simulator.result
                if simulator is not None
                else SimulationResult((), completed=False, failure=exc)
            )
            write_csv(result, args.output)
            print(f"Simulation stopped: {exc}", file=sys.stderr)
            print(
                f"Wrote {len(result.snapshots)} committed snapshots to {args.output}",
                file=sys.stderr,
            )
            return 1
        write_csv(result, args.output)
    except (ConfigurationError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    print(f"Wrote {len(result.snapshots)} snapshots to {args.output}")
    return 0
