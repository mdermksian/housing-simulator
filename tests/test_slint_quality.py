"""Exercise the development checks with real tools and temporary source trees."""

import importlib.util
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/slint_quality.py"
spec = importlib.util.spec_from_file_location("slint_quality", SCRIPT)
quality = importlib.util.module_from_spec(spec)
spec.loader.exec_module(quality)


def test_format_check_diff_fix_and_idempotence(tmp_path, capsys):
    if shutil.which("slint-lsp") is None:
        pytest.skip("Install slint-lsp 1.17.1 to test Slint formatting")
    nested = tmp_path / "feature with spaces"
    nested.mkdir()
    source = nested / "example.slint"
    original = b"export component Example inherits Window{width:100px;}\n"
    source.write_bytes(original)
    unrelated = nested / "example.txt"
    unrelated.write_text("Leave this file alone")

    assert quality.format_sources(tmp_path, check=True) == 1
    assert source.read_bytes() == original
    output = capsys.readouterr()
    assert "(formatted)" in output.out
    assert "1 Slint file(s) need formatting" in output.err
    assert quality.format_sources(tmp_path, check=False) == 0
    formatted = source.read_bytes()
    assert formatted != original
    assert quality.format_sources(tmp_path, check=True) == 0
    assert quality.format_sources(tmp_path, check=False) == 0
    assert source.read_bytes() == formatted
    assert unrelated.read_text() == "Leave this file alone"


def test_formatter_failure_preserves_source(tmp_path, monkeypatch):
    source = tmp_path / "example.slint"
    source.write_text("original")

    def fail(*args, **kwargs):
        raise subprocess.CalledProcessError(1, args[0], stderr=b"Formatter failed\n")

    monkeypatch.setattr(quality.subprocess, "run", fail)
    with pytest.raises(subprocess.CalledProcessError):
        quality.format_sources(tmp_path, check=False)
    assert source.read_text() == "original"


def test_missing_formatter_has_installation_message(tmp_path, monkeypatch, capsys):
    source = tmp_path / "src"
    source.mkdir()
    (source / "example.slint").write_text("export component Example inherits Window {}")
    monkeypatch.setattr(quality, "ROOT", tmp_path)
    monkeypatch.setenv("PATH", "")
    assert quality.main(["format", "--check"]) == 1
    assert "Install slint-lsp 1.17.1" in capsys.readouterr().err


def test_lint_composes_imported_components(tmp_path, capsys):
    pytest.importorskip("slint")
    component = tmp_path / "field.slint"
    component.write_text("export component Field inherits Rectangle {}")
    app = tmp_path / "app.slint"
    app.write_text(
        'import { Field } from "field.slint";\n'
        "export component App inherits Window { Field {} }"
    )
    assert quality.lint(app) == 0
    assert capsys.readouterr().err == ""
    component.write_text("export component Field inherits Rectangle { unknown: 1; }")
    assert quality.lint(app) == 1
    errors = capsys.readouterr().err
    assert "error:" in errors
    assert "field.slint" in errors
    assert "unknown" in errors


def test_lint_rejects_warnings_even_when_compilation_succeeds(tmp_path, capsys):
    pytest.importorskip("slint")
    app = tmp_path / "app.slint"
    # Compiling a reusable component as a standalone window is deprecated.
    app.write_text("export component Example inherits Rectangle {}")
    assert quality.lint(app) == 1
    warnings = capsys.readouterr().err
    assert "warning:" in warnings
    assert "deprecated" in warnings
    assert "error:" not in warnings
