"""Distribution allowlist regression tests."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tarfile
import zipfile
from io import BytesIO
from pathlib import Path

import pytest

from scripts.audit_distribution import audit_archive

ROOT = Path(__file__).resolve().parent.parent


def test_wheel_allowlist_accepts_package_and_metadata(tmp_path):
    wheel = tmp_path / "cmig-0.1.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as handle:
        handle.writestr("cmig/__init__.py", "")
        handle.writestr("cmig-0.1.0.dist-info/METADATA", "Name: cmig\n")
        handle.writestr("cmig-0.1.0.dist-info/licenses/LICENSE", "Apache-2.0\n")
    audit_archive(wheel)


def test_wheel_allowlist_rejects_model_data(tmp_path):
    wheel = tmp_path / "cmig-0.1.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as handle:
        handle.writestr("cmig/__init__.py", "")
        handle.writestr("models/iML1515.xml", "external model")
    with pytest.raises(ValueError, match="forbidden member"):
        audit_archive(wheel)


def test_wheel_with_editor_requires_packaged_presets(tmp_path):
    wheel = tmp_path / "cmig-0.1.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as handle:
        handle.writestr("cmig/__init__.py", "")
        handle.writestr("cmig/gui/editors.py", "")
    with pytest.raises(ValueError, match="missing installed medium resources"):
        audit_archive(wheel)


def test_sdist_allows_publication_doc_and_rejects_extra_docs(tmp_path):
    good = tmp_path / "cmig-0.1.0.tar.gz"
    with tarfile.open(good, "w:gz") as handle:
        content = b"validation"
        info = tarfile.TarInfo("cmig-0.1.0/docs/PUBLICATION_VALIDATION.md")
        info.size = len(content)
        handle.addfile(info, BytesIO(content))
    audit_archive(good)

    bad = tmp_path / "cmig-0.1.1.tar.gz"
    with tarfile.open(bad, "w:gz") as handle:
        content = b"private"
        info = tarfile.TarInfo("cmig-0.1.1/docs/internal.md")
        info.size = len(content)
        handle.addfile(info, BytesIO(content))
    with pytest.raises(ValueError, match="documentation outside allowlist"):
        audit_archive(bad)


def test_sdist_rejects_broken_readme_local_link(tmp_path):
    archive = tmp_path / "cmig-0.1.0.tar.gz"
    with tarfile.open(archive, "w:gz") as handle:
        content = b"[Missing tutorial](docs/missing.html)\n"
        info = tarfile.TarInfo("cmig-0.1.0/README.md")
        info.size = len(content)
        handle.addfile(info, BytesIO(content))
    with pytest.raises(ValueError, match="README has missing local links"):
        audit_archive(archive)


def test_packaged_presets_match_the_canonical_source() -> None:
    source = ROOT / "medium_presets"
    packaged = ROOT / "cmig" / "resources" / "medium_presets"
    relative_files = {path.relative_to(source) for path in source.rglob("*") if path.is_file()}
    assert relative_files
    assert relative_files == {
        path.relative_to(packaged) for path in packaged.rglob("*") if path.is_file()
    }
    for relative in relative_files:
        assert (packaged / relative).read_bytes() == (source / relative).read_bytes()


def test_fresh_distribution_has_preset_resources_and_readme_links(tmp_path) -> None:
    result = subprocess.run(
        ["uv", "build", "--out-dir", str(tmp_path / "dist")],
        cwd=ROOT, text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    wheel = next((tmp_path / "dist").glob("*.whl"))
    sdist = next((tmp_path / "dist").glob("*.tar.gz"))
    audit_archive(wheel)
    audit_archive(sdist)

    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        preset = "cmig/resources/medium_presets/gut_overlay_agora_western.csv"
        provenance = "cmig/resources/medium_presets/provenance_rows.csv"
        assert preset in names and provenance in names
        source_preset = ROOT / "medium_presets" / "gut_overlay_agora_western.csv"
        assert archive.read(preset) == source_preset.read_bytes()

    with tarfile.open(sdist, "r:gz") as archive:
        members = {Path(member.name).relative_to(Path(member.name).parts[0]).as_posix(): member
                   for member in archive.getmembers() if member.isfile()}
        readme = archive.extractfile(members["README.md"])
        assert readme is not None
        text = readme.read().decode("utf-8")
        for target in re.findall(r"\]\(([^)]+)\)", text):
            if "://" in target or target.startswith("#"):
                continue
            assert target in members, f"sdist README link is missing: {target}"
        assert "cmig/resources/medium_presets/gut_overlay_agora_western.csv" in members

    installed = tmp_path / "installed"
    installed.mkdir()
    with zipfile.ZipFile(wheel) as archive:
        archive.extractall(installed)
    outside = tmp_path / "outside"
    outside.mkdir()
    env = os.environ.copy()
    env["PYTHONPATH"] = str(installed)
    env["QT_QPA_PLATFORM"] = "offscreen"
    smoke = subprocess.run(
        [sys.executable, "-c", "\n".join([
            "from pathlib import Path",
            "import cmig",
            f"assert Path(cmig.__file__).is_relative_to({str(installed)!r})",
            "from PySide6.QtWidgets import QApplication",
            "from cmig.gui.editors import MediumEditor",
            "app = QApplication([])",
            "editor = MediumEditor()",
            "index = editor.preset_combo.findText('gut_overlay_agora_western.csv')",
            "assert index > 0",
            "editor.preset_combo.setCurrentIndex(index)",
            "assert editor.load_selected_preset()",
            "assert editor.table.rowCount() > 10",
            "assert editor.table.item(0, 2).text() in {'nutrient', 'pool_closure'}",
        ])],
        cwd=outside, env=env, text=True, capture_output=True, check=False,
    )
    assert smoke.returncode == 0, smoke.stdout + smoke.stderr
