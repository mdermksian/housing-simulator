"""Development-only formatting and compiler checks for the Slint source tree."""

import argparse
import difflib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "src/house_simulator/desktop/app.slint"


def format_sources(source: Path, *, check: bool) -> int:
    paths = sorted(source.rglob("*.slint"))
    if not paths:
        raise ValueError(f"No Slint files found beneath {source}")
    changed = 0
    for path in paths:
        original = path.read_bytes()
        result = subprocess.run(
            ["slint-lsp", "format", str(path)],
            capture_output=True,
            check=True,
            timeout=30,
        )
        if result.stderr:
            print(result.stderr.decode("utf-8"), file=sys.stderr, end="")
        if result.stdout == original:
            continue
        changed += 1
        if check:
            print(
                "".join(
                    difflib.unified_diff(
                        original.decode("utf-8").splitlines(keepends=True),
                        result.stdout.decode("utf-8").splitlines(keepends=True),
                        fromfile=str(path),
                        tofile=f"{path} (formatted)",
                    )
                ),
                end="",
            )
        else:
            path.write_bytes(result.stdout)
            print(f"Formatted {path}")
    if check and changed:
        print(f"{changed} Slint file(s) need formatting", file=sys.stderr)
        return 1
    print(f"Checked {len(paths)} Slint file(s)")
    return 0


def lint(entrypoint: Path) -> int:
    # Import here so formatting does not require Slint's Python UI dependency.
    try:
        from slint import native
    except ModuleNotFoundError as exc:
        if exc.name != "slint":
            raise
        raise ValueError(
            "Slint lint requires the UI extra: uv sync --locked --dev --extra ui"
        ) from exc

    compiler = native.Compiler()
    compiler.style = "fluent"
    result = compiler.build_from_path(entrypoint)
    failed = False
    for diagnostic in result.diagnostics:
        if diagnostic.level == native.DiagnosticLevel.Error:
            severity = "error"
        elif diagnostic.level == native.DiagnosticLevel.Warning:
            severity = "warning"
        else:
            severity = "note"
        print(f"{severity}: {diagnostic}", file=sys.stderr)
        failed |= severity in ("warning", "error")
    if failed:
        return 1
    if not result.component_names:
        raise ValueError(f"No exported components found in {entrypoint}")
    print(f"Slint lint passed: {entrypoint} and its imports")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    formatter = commands.add_parser("format", help="Format every .slint file in src/")
    formatter.add_argument("--check", action="store_true", help="Check without writing")
    commands.add_parser("lint", help="Fail on Slint compiler warnings or errors")
    args = parser.parse_args(argv)
    try:
        if args.command == "format":
            return format_sources(ROOT / "src", check=args.check)
        return lint(ENTRYPOINT)
    except FileNotFoundError as exc:
        if exc.filename == "slint-lsp":
            print(
                "Install slint-lsp 1.17.1 and add it to PATH; see README.md",
                file=sys.stderr,
            )
        else:
            print(exc, file=sys.stderr)
    except subprocess.CalledProcessError as exc:
        print(f"Slint formatter failed: {exc}", file=sys.stderr)
        if exc.stderr:
            print(exc.stderr.decode("utf-8"), file=sys.stderr, end="")
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        print(exc, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
