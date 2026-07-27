#!/usr/bin/env python
"""Fetch and verify the external human GEMs that CMIG uses as a host model.

The SBML files are large (15-29 MB uncompressed) and are distributed by BiGG Models under a
custom UCSD **non-commercial** licence, not an open-source one -- see ``data/gems/README.md``.
They are therefore gitignored and fetched on demand; this script plus
``data/gems/GEM_SOURCES.json`` are the tracked provenance record.

    python scripts/download_human_gems.py            # download any missing model, then verify
    python scripts/download_human_gems.py --verify    # verify what is on disk, download nothing
    python scripts/download_human_gems.py --model Recon3D

Verification compares the SHA-256 of the bytes on disk against ``GEM_SOURCES.json``. A mismatch
is a hard failure: a host result computed from unidentified model bytes has no provenance, so the
script refuses rather than proceeding with a warning.

``--verify --counts`` additionally loads each model with cobra and re-measures the reaction /
metabolite / gene counts and the shipped default objective recorded in the manifest. That is the
check that would catch BiGG silently republishing a model under the same id.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

GEMS_DIR = Path(__file__).resolve().parents[1] / "data" / "gems"
MANIFEST = GEMS_DIR / "GEM_SOURCES.json"
#: BiGG serves plain HTTP only; an https:// URL is refused at the TCP level. Recorded here so a
#: future "just use https" edit is a visible change to a documented fact, not a silent breakage.
_ALLOWED_URL_PREFIX = "http://bigg.ucsd.edu/static/models/"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_manifest() -> dict:
    if not MANIFEST.exists():
        raise SystemExit(f"provenance manifest missing: {MANIFEST}")
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _download(record: dict, dest_dir: Path) -> Path:
    url = str(record["source_url"])
    if not url.startswith(_ALLOWED_URL_PREFIX):
        raise SystemExit(f"refusing to fetch from an unexpected host: {url}")
    archive = dest_dir / str(record["archive_file"])
    xml = dest_dir / str(record["file"])
    dest_dir.mkdir(parents=True, exist_ok=True)
    if not archive.exists():
        print(f"downloading {url} -> {archive}")
        try:
            with urllib.request.urlopen(url) as response:  # noqa: S310 - prefix-checked above
                archive.write_bytes(response.read())
        except (urllib.error.URLError, OSError) as error:
            raise SystemExit(f"download failed for {record['id']}: {error}") from error
    actual_archive = _sha256(archive)
    if actual_archive != str(record["archive_sha256"]):
        raise SystemExit(
            f"{archive.name} SHA-256 mismatch\n  expected {record['archive_sha256']}\n"
            f"  actual   {actual_archive}\n"
            "BiGG may have republished this model id. Do not use these bytes for a result until "
            "GEM_SOURCES.json is updated with a re-verified retrieval."
        )
    if not xml.exists():
        print(f"decompressing {archive.name} -> {xml.name}")
        with gzip.open(archive, "rb") as source:
            xml.write_bytes(source.read())
    return xml


def _verify_counts(record: dict, xml: Path) -> list[str]:
    """Re-measure the recorded structural counts and default objective with cobra."""
    try:
        import cobra.io
        from cobra.util.solver import linear_reaction_coefficients
    except ImportError:
        return [f"{record['id']}: cobra not installed; --counts skipped"]
    model = cobra.io.read_sbml_model(str(xml))
    counts = dict(record.get("counts") or {})
    measured = {
        "reactions": len(model.reactions),
        "metabolites": len(model.metabolites),
        "genes": len(model.genes),
        "boundary_reactions": len([r for r in model.reactions if r.boundary]),
        "exchange_reactions_EX_prefix": len(
            [r for r in model.reactions if str(r.id).startswith("EX_")]
        ),
        "compartments": sorted(model.compartments),
    }
    problems = [
        f"{record['id']}.counts.{key}: manifest {counts[key]!r} != measured {value!r}"
        for key, value in measured.items()
        if key in counts and counts[key] != value
    ]
    objective = sorted(str(r.id) for r in linear_reaction_coefficients(model))
    declared = [str((record.get("shipped_default_objective") or {}).get("reaction", ""))]
    if objective != [d for d in declared if d]:
        problems.append(
            f"{record['id']}: shipped default objective is {objective!r}, manifest records "
            f"{declared!r}"
        )
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=None, help="only this BiGG id (default: all)")
    parser.add_argument(
        "--verify", action="store_true", help="verify files already on disk; download nothing"
    )
    parser.add_argument(
        "--counts", action="store_true",
        help="also reload each model with cobra and re-measure the recorded counts/objective",
    )
    parser.add_argument(
        "--dir", default=str(GEMS_DIR), help=f"destination directory (default: {GEMS_DIR})"
    )
    args = parser.parse_args(argv)

    manifest = _load_manifest()
    dest_dir = Path(args.dir).expanduser()
    records = [
        record for record in manifest["models"]
        if args.model is None or str(record["id"]) == args.model
    ]
    if not records:
        print(f"no model named {args.model!r} in {MANIFEST}", file=sys.stderr)
        return 2

    print(f"licence: {manifest['resource']['license_name']}")
    print(f"         {manifest['resource']['license_url']}")
    problems: list[str] = []
    for record in records:
        xml = dest_dir / str(record["file"])
        if args.verify:
            if not xml.exists():
                problems.append(f"{record['id']}: {xml} is missing (run without --verify)")
                continue
        else:
            xml = _download(record, dest_dir)
        actual = _sha256(xml)
        if actual != str(record["sha256"]):
            problems.append(
                f"{record['id']}: {xml.name} SHA-256 {actual} != manifest {record['sha256']}"
            )
            continue
        print(f"ok  {record['id']:8s} {xml}  sha256={actual[:16]}…")
        print(f"    default objective: {record['shipped_default_objective']['reaction']} — "
              f"{record['shipped_default_objective']['warning'][:90]}…")
        if args.counts:
            problems.extend(_verify_counts(record, xml))

    if problems:
        print("\nFAILED:", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1
    print("\nall requested models verified against data/gems/GEM_SOURCES.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
