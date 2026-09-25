"""Release guard compatibility regressions for supported Python and Windows locales."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import types
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

from scripts import check_release_versions as guard

ROOT = Path(__file__).resolve().parent.parent


def test_python310_tomli_fallback(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "tomllib", None)
    monkeypatch.setitem(sys.modules, "tomli", types.SimpleNamespace(loads=tomllib.loads))
    spec = importlib.util.spec_from_file_location("release_guard_py310", guard.__file__)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module._pyproject_version() == "0.3.0"
    assert module._lock_version() == "0.3.0"


def test_every_release_input_is_read_as_utf8(monkeypatch) -> None:
    original = Path.read_text
    paths: list[Path] = []

    def checked(self: Path, *args, **kwargs) -> str:
        assert kwargs.get("encoding") == "utf-8", self
        paths.append(self)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", checked)
    guard._pyproject_version()
    guard._package_version()
    guard._citation()
    guard._zenodo_version()
    guard._marketplace_version()
    guard._lock_version()
    guard._changelog_heading_version()
    assert len(paths) == 7


def test_non_ascii_fixture_survives_non_utf_default(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nversion = "0.3.0"\ndescription = "한글 설명"\n', encoding="utf-8"
    )
    monkeypatch.setattr(guard, "ROOT", tmp_path)
    original = Path.read_text

    def windows_default(self: Path, *args, **kwargs) -> str:
        if "encoding" not in kwargs:
            kwargs["encoding"] = "cp1252"
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", windows_default)
    assert guard._pyproject_version() == "0.3.0"


def test_version_and_tag_mismatch_still_fail(monkeypatch, capsys) -> None:
    monkeypatch.setattr(guard, "_package_version", lambda: "9.9.9")
    monkeypatch.setattr(sys, "argv", ["check_release_versions.py", "v0.3.0"])
    assert guard.main() == 1
    captured = capsys.readouterr()
    assert "VERSION MISMATCH" in captured.err
    assert "tag v0.3.0 does not match metadata" in captured.err


def test_tag_output_survives_windows_console_encoding() -> None:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "cp1252:strict"
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_release_versions.py"), "v0.3.0"],
        cwd=ROOT, env=env, capture_output=True, text=True, encoding="cp1252", check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "tag v0.3.0 -> release build checks for 0.3.0" in result.stdout
