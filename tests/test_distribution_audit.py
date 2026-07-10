"""Distribution allowlist regression tests."""

from __future__ import annotations

import tarfile
import zipfile
from io import BytesIO

import pytest

from scripts.audit_distribution import audit_archive


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
