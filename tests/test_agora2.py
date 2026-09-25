"""AGORA2 fetcher — catalogue parsing, selection, encoding repair, VMH->BiGG conversion.

Every test here is offline: the network is reached only through the injected ``fetcher`` seam,
so CI never depends on vmh.life being up. The published-file hazards these tests pin
(Latin-1 bytes in a UTF-8 document, ``EX_but(e)`` ids, ``glc_D`` vs ``glc__D``) were measured
against version 2.01 on 2026-09-02 and are recorded in ``cmig/io/agora2.py``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cmig.io.agora2 import (
    AGORA2_INDIVIDUAL_URL,
    Agora2Error,
    CatalogueEntry,
    bigg_stereo,
    catalogue_payload,
    convert_ids_to_bigg,
    estimated_bytes,
    fetch_catalogue,
    fetch_model,
    human_bytes,
    load_or_fetch_catalogue,
    manifest_payload,
    parse_catalogue,
    read_catalogue,
    repair_utf8,
    select_entries,
    write_catalogue,
)

# The publisher serves an Apache directory index; one <tr> per reconstruction.
_ICON = '<td valign="top"><img src="/icons/text.gif" alt="[TXT]"></td>'
_MODIFIED = "2023-03-23 19:16"


def _row(name: str, size: str) -> str:
    return (
        f"<tr>{_ICON}<td>"
        f'<a href="{name}">{name}</a></td>'
        f'<td align="right">{_MODIFIED}  </td>'
        f'<td align="right">{size}</td><td>&nbsp;</td></tr>'
    )


_INDEX_HTML = "\n".join([
    "<html><body><h1>Index of /files</h1><table>",
    '<tr><td valign="top"><img src="/icons/back.gif" alt="[PARENTDIR]"></td><td>'
    '<a href="/files/reconstructions/AGORA2/">Parent Directory</a></td>'
    '<td>&nbsp;</td><td align="right">  - </td><td>&nbsp;</td></tr>',
    _row('Roseburia_intestinalis_L1_82.xml', ' 15M'),
    _row('Faecalibacterium_prausnitzii_A2_165.xml', ' 15M'),
    _row('Roseburia_faecis_M72.xml', '7.6M'),
    _row('Escherichia_coli_ED1a.xml', ' 13M'),
    "</table></body></html>",
])


def _entries() -> list[CatalogueEntry]:
    return parse_catalogue(_INDEX_HTML)


# ── catalogue ────────────────────────────────────────────────────────────────────────────────


def test_parse_catalogue_reads_id_size_and_url() -> None:
    entries = _entries()
    assert [e.id for e in entries] == [
        "Escherichia_coli_ED1a",
        "Faecalibacterium_prausnitzii_A2_165",
        "Roseburia_faecis_M72",
        "Roseburia_intestinalis_L1_82",
    ]
    first = entries[1]
    assert first.file == "Faecalibacterium_prausnitzii_A2_165.xml"
    assert first.published_size == "15M"
    assert first.genus == "Faecalibacterium"
    assert first.species == "Faecalibacterium_prausnitzii"
    assert first.url == f"{AGORA2_INDIVIDUAL_URL}/Faecalibacterium_prausnitzii_A2_165.xml"
    # The parent-directory row is not a model.
    assert all(not e.id.startswith("/") for e in entries)


def test_parse_catalogue_refuses_an_index_it_does_not_recognise() -> None:
    """An empty parse must be an error, not 'no model matched your filter'."""
    with pytest.raises(Agora2Error, match="index format has changed"):
        parse_catalogue("<html><body>503 Service Unavailable</body></html>")


def test_fetch_catalogue_uses_the_injected_fetcher_and_round_trips(tmp_path: Path) -> None:
    calls: list[str] = []

    def fake(url: str) -> bytes:
        calls.append(url)
        return _INDEX_HTML.encode("utf-8")

    entries = fetch_catalogue(fake)
    assert calls == [f"{AGORA2_INDIVIDUAL_URL}/"]
    path = tmp_path / "catalogue.json"
    write_catalogue(entries, path)
    assert [e.id for e in read_catalogue(path)] == [e.id for e in entries]
    payload = json.loads(path.read_text())
    assert payload["n_models"] == 4
    assert "10.1038/s41587-022-01628-0" in payload["resource"]["citation"]


def test_load_or_fetch_catalogue_caches_then_refreshes(tmp_path: Path) -> None:
    calls = {"n": 0}

    def fake(_url: str) -> bytes:
        calls["n"] += 1
        return _INDEX_HTML.encode("utf-8")

    path = tmp_path / "catalogue.json"
    _first, fetched = load_or_fetch_catalogue(path, fetcher=fake)
    assert fetched is True and calls["n"] == 1
    _second, fetched = load_or_fetch_catalogue(path, fetcher=fake)
    assert fetched is False and calls["n"] == 1  # served from the cache
    _third, fetched = load_or_fetch_catalogue(path, refresh=True, fetcher=fake)
    assert fetched is True and calls["n"] == 2


def test_catalogue_payload_states_the_set_it_describes() -> None:
    resource = catalogue_payload(_entries())["resource"]
    assert resource["version"] == "2.01"
    # The 2024 "fixed" rebuild is archive-only; a per-strain fetch cannot serve it, and saying so
    # is the difference between a reproducible record and a misleading one.
    assert "2024-07-04" in resource["set_note"]


# ── selection ────────────────────────────────────────────────────────────────────────────────


def test_select_by_genus_and_regular_expression() -> None:
    entries = _entries()
    assert [e.id for e in select_entries(entries, genera=["roseburia"])] == [
        "Roseburia_faecis_M72",
        "Roseburia_intestinalis_L1_82",
    ]
    assert [e.id for e in select_entries(entries, pattern="prausnitz")] == [
        "Faecalibacterium_prausnitzii_A2_165"
    ]
    assert select_entries(entries, pattern="Roseburia", exclude_pattern="_M72") == [
        e for e in entries if e.id == "Roseburia_intestinalis_L1_82"
    ]


def test_select_by_id_preserves_order_and_names_what_is_missing() -> None:
    entries = _entries()
    picked = select_entries(entries, ids=["Roseburia_faecis_M72", "Escherichia_coli_ED1a"])
    assert [e.id for e in picked] == ["Roseburia_faecis_M72", "Escherichia_coli_ED1a"]
    with pytest.raises(Agora2Error, match="not in the AGORA2 catalogue"):
        select_entries(entries, ids=["Roseburia_faecis_M72", "Nosuch_strain_1"])


def test_one_per_genus_is_what_makes_a_sample_diverse() -> None:
    """Two Roseburia strains collapse to one, so a sample spans genera not strains."""
    entries = _entries()
    genera = [e.genus for e in select_entries(entries, one_per_genus=True)]
    assert genera == ["Escherichia", "Faecalibacterium", "Roseburia"]


def test_sampling_is_deterministic_for_a_seed() -> None:
    entries = _entries()
    first = [e.id for e in select_entries(entries, sample=2, seed=11)]
    again = [e.id for e in select_entries(entries, sample=2, seed=11)]
    assert first == again and len(first) == 2
    assert first == sorted(first)  # id-ordered output, so downstream taxonomy order is stable
    with pytest.raises(Agora2Error, match="--sample must be a positive"):
        select_entries(entries, sample=0)


def test_estimated_size_reads_the_published_column() -> None:
    expected = int((15 + 15 + 7.6 + 13) * 1024**2)
    assert estimated_bytes(_entries()) == pytest.approx(expected, rel=1e-6)
    assert human_bytes(1536) == "1.5 KB"


# ── encoding repair ──────────────────────────────────────────────────────────────────────────


def test_repair_utf8_transcodes_only_the_offending_bytes() -> None:
    """The published SBML declares UTF-8 and carries Latin-1; libsbml rejects the whole file."""
    data = b'<species name="regorafenib-N-\xdf-glucuronide"/><p>caf\xe8</p>'
    with pytest.raises(UnicodeDecodeError):
        data.decode("utf-8")
    repaired, repairs = repair_utf8(data)
    assert repaired.decode("utf-8") == '<species name="regorafenib-N-ß-glucuronide"/><p>cafè</p>'
    assert len(repairs) == 2
    assert repairs[0].endswith(":df:ß")


def test_repair_utf8_leaves_a_clean_document_byte_identical() -> None:
    clean = "<species name='β-glucan'/>".encode()
    repaired, repairs = repair_utf8(clean)
    assert repaired == clean and repairs == []


# ── VMH -> BiGG conversion ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "vmh, bigg",
    [
        ("glc_D", "glc__D"),
        ("ala_L", "ala__L"),
        ("26dap_M", "26dap__M"),
        ("12ppd_S", "12ppd__S"),
        ("pnto_R", "pnto__R"),
        ("but", "but"),          # no isomer token
        ("lac__D", "lac__D"),    # already BiGG: idempotent
        ("acgam", "acgam"),
    ],
)
def test_bigg_stereo_rewrites_only_a_lone_isomer_token(vmh: str, bigg: str) -> None:
    assert bigg_stereo(vmh) == bigg
    assert bigg_stereo(bigg_stereo(vmh)) == bigg


def _vmh_model():
    cobra = pytest.importorskip("cobra")

    model = cobra.Model("M_Test_strain_1")
    glc_e = cobra.Metabolite("glc_D[e]", compartment="e")
    glc_c = cobra.Metabolite("glc_D[c]", compartment="c")
    but_e = cobra.Metabolite("but[e]", compartment="e")
    but_c = cobra.Metabolite("but[c]", compartment="c")

    def reaction(rid, stoich, lower=0.0, upper=1000.0):
        rxn = cobra.Reaction(rid)
        rxn.bounds = (lower, upper)
        rxn.add_metabolites(stoich)
        return rxn

    biomass = reaction("biomass205", {glc_c: -1.0, but_c: 1.0})
    model.add_reactions([
        reaction("EX_glc_D(e)", {glc_e: -1.0}, lower=-10.0),
        reaction("GLCabc", {glc_e: -1.0, glc_c: 1.0}),
        biomass,
        reaction("BUTt2r", {but_c: -1.0, but_e: 1.0}),
        reaction("EX_but(e)", {but_e: -1.0}, lower=-10.0),
        reaction("DM_but(c)", {but_c: -1.0}),
    ])
    model.objective = biomass
    return model


def test_conversion_rewrites_compartment_and_isomer_notation() -> None:
    model = _vmh_model()
    report = convert_ids_to_bigg(model)

    assert {m.id for m in model.metabolites} == {"glc__D_e", "glc__D_c", "but_e", "but_c"}
    assert "EX_but_e" in {r.id for r in model.reactions}
    # The exchange a `--target but` / medium file has to match:
    assert "EX_glc__D_e" in {r.id for r in model.reactions}
    assert "DM_but_c" in {r.id for r in model.reactions}
    # Internal reactions keep the publisher's names.
    assert "GLCabc" in {r.id for r in model.reactions}
    assert "biomass205" in {r.id for r in model.reactions}
    assert report.metabolites_converted == 4
    assert report.stereo_renamed == 2
    assert report.reactions_converted == 3
    assert report.reactions_unconverted == 3
    # The reaction network still balances through the renamed metabolites.
    assert model.optimize().status == "optimal"


def test_conversion_refuses_to_merge_two_metabolites() -> None:
    """A collision would fabricate a reaction network; the model is refused instead."""
    cobra = pytest.importorskip("cobra")
    model = _vmh_model()
    # `glc__D_e` already exists as a distinct species, so converting `glc_D[e]` would merge them.
    model.add_metabolites([cobra.Metabolite("glc__D_e", compartment="e")])
    with pytest.raises(Agora2Error, match="would collide with the existing metabolite"):
        convert_ids_to_bigg(model)


# ── fetch ────────────────────────────────────────────────────────────────────────────────────


def _sbml_bytes_with_latin1(model) -> bytes:
    cobra = pytest.importorskip("cobra")
    import tempfile

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "m.xml"
        cobra.io.write_sbml_model(model, str(path))
        data = path.read_bytes()
    # Inject the published files' defect: a Latin-1 byte inside a UTF-8 document.
    return data.replace(b"<listOfSpecies>", b"<!-- caf\xe8 --><listOfSpecies>", 1)


def test_fetch_model_repairs_converts_and_records_provenance(tmp_path: Path) -> None:
    pytest.importorskip("cobra")
    payload = _sbml_bytes_with_latin1(_vmh_model())
    with pytest.raises(UnicodeDecodeError):
        payload.decode("utf-8")
    entry = _entries()[1]

    record = fetch_model(entry, tmp_path, namespace="bigg", file_format="json",
                         fetcher=lambda _url: payload)

    written = tmp_path / f"{entry.id}.json"
    assert written.exists() and record.file == written.name
    assert record.encoding_repairs == 1 and record.repaired_bytes[0].endswith(":e8:è")
    assert record.namespace == "bigg" and record.format == "json"
    assert record.source_url == entry.url
    assert record.source_sha256 != record.sha256  # repaired + converted + reserialised
    assert record.objective_reactions == ["biomass205"]
    assert record.conversion["stereo_renamed"] == 2
    model = __import__("cobra.io", fromlist=["io"]).load_json_model(str(written))
    assert "EX_but_e" in {r.id for r in model.exchanges}
    # No staging file is left behind.
    assert [p.name for p in tmp_path.iterdir()] == [written.name]


def test_fetch_model_vmh_namespace_keeps_the_published_ids(tmp_path: Path) -> None:
    pytest.importorskip("cobra")
    payload = _sbml_bytes_with_latin1(_vmh_model())
    entry = _entries()[1]

    record = fetch_model(entry, tmp_path, namespace="vmh", file_format="sbml",
                         fetcher=lambda _url: payload)

    written = (tmp_path / record.file).read_bytes()
    assert b"EX_but__40__e__41__" in written or b"EX_but(e)" in written
    assert record.conversion is None
    # Only the encoding repair separates the artifact from the published bytes.
    assert repair_utf8(payload)[0] == written


def test_fetch_model_vmh_sbml_without_fchmod(tmp_path: Path, monkeypatch) -> None:
    """Direct publisher bytes still publish on platforms without descriptor chmod."""
    import cmig.io.atomic as atomic

    entry = CatalogueEntry("safe", "safe.xml", "1M", "")
    payload = _sbml_bytes_with_latin1(_vmh_model())
    target = tmp_path / "safe.xml"
    target.write_bytes(b"previous model")
    monkeypatch.delattr(atomic.os, "fchmod", raising=False)

    record = fetch_model(
        entry, tmp_path, namespace="vmh", file_format="sbml",
        fetcher=lambda _url: payload,
    )

    published = repair_utf8(payload)[0]
    assert target.read_bytes() == published
    assert record.bytes == len(published)
    assert [path.name for path in tmp_path.iterdir()] == [target.name]


def test_fetch_model_rejects_an_unknown_namespace_or_format(tmp_path: Path) -> None:
    entry = _entries()[1]
    with pytest.raises(Agora2Error, match="unknown namespace"):
        fetch_model(entry, tmp_path, namespace="kegg", fetcher=lambda _url: b"")
    with pytest.raises(Agora2Error, match="unknown format"):
        fetch_model(entry, tmp_path, file_format="mat", fetcher=lambda _url: b"")


def test_fetch_model_refuses_a_url_outside_the_publisher(tmp_path: Path) -> None:
    calls: list[str] = []
    for filename in ("../../../etc/passwd", "../../../../etc/passwd", "..%2fsecret.xml"):
        rogue = CatalogueEntry("x", filename, "1M", "")
        with pytest.raises(Agora2Error, match="unsafe AGORA2 filename"):
            fetch_model(rogue, tmp_path, fetcher=lambda url: calls.append(url) or b"")
    assert calls == []


@pytest.mark.parametrize(
    "bad_id", ["../escaped", "/absolute", r"..\escaped", "C:drive", "x%2fy", "x\x85y"]
)
def test_fetch_model_rejects_unsafe_id_before_fetch(tmp_path: Path, bad_id: str) -> None:
    victim = tmp_path / "escaped.xml"
    victim.write_bytes(b"original user data")
    calls: list[str] = []
    entry = CatalogueEntry(bad_id, "safe.xml", "1M", "")
    with pytest.raises(Agora2Error, match="unsafe AGORA2 id"):
        fetch_model(
            entry, tmp_path / "out", namespace="vmh", file_format="sbml",
            fetcher=lambda url: calls.append(url) or b"<sbml/>",
        )
    assert calls == []
    assert victim.read_bytes() == b"original user data"


def test_cached_catalogue_rejects_unsafe_entries(tmp_path: Path) -> None:
    path = tmp_path / "catalogue.json"
    path.write_text(json.dumps({"models": [{"id": "../escaped", "file": "safe.xml"}]}))
    with pytest.raises(Agora2Error, match="unsafe AGORA2 id"):
        read_catalogue(path)
    path.write_text(json.dumps({"models": [{"id": "safe", "file": r"..\bad.xml"}]}))
    with pytest.raises(Agora2Error, match="unsafe AGORA2 filename"):
        read_catalogue(path)


@pytest.mark.parametrize("file_format", ["sbml", "json"])
def test_existing_symlink_target_is_rejected_without_fetch(
    tmp_path: Path, file_format: str
) -> None:
    out = tmp_path / "out"
    out.mkdir()
    victim = tmp_path / "victim.xml"
    victim.write_bytes(b"keep me")
    suffix = ".json" if file_format == "json" else ".xml"
    (out / f"safe{suffix}").symlink_to(victim)
    entry = CatalogueEntry("safe", "safe.xml", "1M", "")
    with pytest.raises(Agora2Error, match="unsafe AGORA2 output"):
        fetch_model(entry, out, namespace="vmh", file_format=file_format,
                    fetcher=lambda _: b"<sbml/>")
    assert victim.read_bytes() == b"keep me"


def test_repaired_model_staging_never_uses_predictable_entry_name(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    victim = tmp_path / "victim.xml"
    victim.write_bytes(b"keep me")
    (out / ".safe.agora2-staging.xml").symlink_to(victim)
    entry = CatalogueEntry("safe", "safe.xml", "1M", "")
    with pytest.raises(Agora2Error, match="still does not parse"):
        fetch_model(entry, out, namespace="bigg", file_format="json", fetcher=lambda _: b"invalid")
    assert victim.read_bytes() == b"keep me"


def test_failed_conversion_preserves_existing_output(tmp_path: Path) -> None:
    entry = CatalogueEntry("safe", "safe.xml", "1M", "")
    target = tmp_path / "safe.json"
    target.write_bytes(b"previous good model")
    with pytest.raises(Agora2Error, match="still does not parse"):
        fetch_model(entry, tmp_path, namespace="bigg", file_format="json",
                    fetcher=lambda _: b"invalid")
    assert target.read_bytes() == b"previous good model"


def test_publisher_url_guard_rejects_bad_routes_before_transport(monkeypatch) -> None:
    import cmig.io.agora2 as agora2

    opened: list[str] = []
    class FakeOpener:
        def open(self, request, *, timeout):
            opened.append(request.full_url)
            raise AssertionError("transport should not run")

    monkeypatch.setattr(agora2.urllib.request, "build_opener", lambda *_: FakeOpener())
    bad_urls = [
        f"{AGORA2_INDIVIDUAL_URL}/../../../../etc/passwd",
        f"{AGORA2_INDIVIDUAL_URL}/safe%2f..%2fsecret.xml",
        "https://www.vmh.life:443/files/reconstructions/AGORA2/version2.01/sbml_files/individual_reconstructions/safe.xml",
        "https://evil.test/files/reconstructions/AGORA2/version2.01/sbml_files/individual_reconstructions/safe.xml",
    ]
    for url in bad_urls:
        with pytest.raises(Agora2Error):
            agora2._open_url(url, timeout=1)
    assert opened == []


def test_redirect_targets_are_checked_before_following() -> None:
    from urllib.request import Request

    import cmig.io.agora2 as agora2

    source = Request(f"{AGORA2_INDIVIDUAL_URL}/safe.xml")
    handler = agora2._GuardedRedirectHandler()
    allowed = handler.redirect_request(source, None, 302, "Found", {}, "other.xml")
    assert allowed is not None and allowed.full_url == f"{AGORA2_INDIVIDUAL_URL}/other.xml"
    for target in (
        "https://evil.test/other.xml",
        "http://www.vmh.life/other.xml",
        "../../../../etc/passwd",
        "other%2f..%2fsecret.xml",
    ):
        with pytest.raises(Agora2Error):
            handler.redirect_request(source, None, 302, "Found", {}, target)


def test_effective_url_is_recorded_and_checked_offline(monkeypatch, tmp_path: Path) -> None:
    import cmig.io.agora2 as agora2

    entry = CatalogueEntry("safe", "safe.xml", "1M", "")
    redirected = f"{AGORA2_INDIVIDUAL_URL}/other.xml"

    class FakeResponse:
        def __init__(self, final_url: str) -> None:
            self.final_url = final_url

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def geturl(self) -> str:
            return self.final_url

        def read(self) -> bytes:
            return b"<sbml/>"

    class FakeOpener:
        final_url = redirected

        def open(self, request, *, timeout):
            assert request.full_url == entry.url
            return FakeResponse(self.final_url)

    opener = FakeOpener()
    monkeypatch.setattr(agora2.urllib.request, "build_opener", lambda *_: opener)
    record = fetch_model(entry, tmp_path, namespace="vmh", fetcher=agora2.default_fetcher())
    assert record.source_url == entry.url
    assert record.effective_url == redirected
    opener.final_url = "https://evil.test/other.xml"
    with pytest.raises(Agora2Error, match="unexpected location"):
        fetch_model(entry, tmp_path, namespace="vmh", fetcher=agora2.default_fetcher())
    assert (tmp_path / "safe.xml").read_bytes() == b"<sbml/>"


def test_redirect_handler_never_transmits_to_rejected_target(monkeypatch) -> None:
    from email.message import Message
    from io import BytesIO
    from urllib.request import HTTPSHandler
    from urllib.response import addinfourl

    import cmig.io.agora2 as agora2

    source = f"{AGORA2_INDIVIDUAL_URL}/safe.xml"
    requested: list[str] = []
    redirects: dict[str, str] = {}

    class OfflineHTTPS(HTTPSHandler):
        def https_open(self, request):
            requested.append(request.full_url)
            headers = Message()
            location = redirects.get(request.full_url)
            if location is None:
                response = addinfourl(BytesIO(b"<sbml/>"), headers, request.full_url, 200)
                response.msg = "OK"
            else:
                headers["Location"] = location
                response = addinfourl(BytesIO(b""), headers, request.full_url, 302)
                response.msg = "Found"
            return response

    original_builder = agora2.urllib.request.build_opener
    monkeypatch.setattr(
        agora2.urllib.request, "build_opener",
        lambda *handlers: original_builder(OfflineHTTPS(), *handlers),
    )
    redirects[source] = "other.xml"
    body = agora2._open_url(source, timeout=1)
    assert body == b"<sbml/>"
    assert body.effective_url == f"{AGORA2_INDIVIDUAL_URL}/other.xml"
    assert requested == [source, f"{AGORA2_INDIVIDUAL_URL}/other.xml"]

    for target in ("https://evil.test/other.xml", "http://www.vmh.life/other.xml",
                   "../../../../etc/passwd", "other%2f..%2fsecret.xml"):
        requested.clear()
        redirects[source] = target
        with pytest.raises(Agora2Error):
            agora2._open_url(source, timeout=1)
        assert requested == [source]

    requested.clear()
    redirects[source] = "safe.xml"
    with pytest.raises(Agora2Error, match="download failed"):
        agora2._open_url(source, timeout=1)
    assert requested and set(requested) == {source}


def test_manifest_records_the_repair_and_conversion_that_were_applied() -> None:
    payload = manifest_payload([], namespace="bigg", file_format="json", repair_encoding=True)
    assert payload["encoding_repair"] == "latin1_to_utf8"
    assert "isomer separator" in payload["namespace_conversion"]
    assert "10.1038/s41587-022-01628-0" in payload["resource"]["citation"]
    assert "asserts no licence" in payload["resource"]["license_note"]

    kept = manifest_payload([], namespace="vmh", file_format="sbml", repair_encoding=False)
    assert kept["encoding_repair"] == "none"
    assert "namespace gate blocks these" in kept["namespace_conversion"]


# ── CLI ──────────────────────────────────────────────────────────────────────────────────────


def test_agora2_list_filters_from_a_cached_catalogue(tmp_path, capsys) -> None:
    from cmig.cli.main import main

    catalogue = tmp_path / "catalogue.json"
    write_catalogue(_entries(), catalogue)
    rc = main(["agora2-list", "--catalogue", str(catalogue), "--genus", "Roseburia",
               "--format", "json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["n_selected"] == 2
    assert payload["catalogue_refreshed"] is False
    assert [m["id"] for m in payload["models"]] == [
        "Roseburia_faecis_M72", "Roseburia_intestinalis_L1_82"
    ]


def test_agora2_fetch_refuses_the_whole_catalogue_without_all(tmp_path, capsys) -> None:
    from cmig.cli.main import main

    catalogue = tmp_path / "catalogue.json"
    write_catalogue(_entries(), catalogue)
    rc = main(["agora2-fetch", "--catalogue", str(catalogue), "--out", str(tmp_path / "pool")])
    assert rc == 2
    assert "without --all" in capsys.readouterr().err


def test_agora2_fetch_dry_run_downloads_nothing(tmp_path, capsys) -> None:
    from cmig.cli.main import main

    catalogue = tmp_path / "catalogue.json"
    write_catalogue(_entries(), catalogue)
    out = tmp_path / "pool"
    rc = main(["agora2-fetch", "--catalogue", str(catalogue), "--genus", "Roseburia",
               "--dry-run", "--out", str(out)])
    assert rc == 0
    assert "would fetch Roseburia_faecis_M72" in capsys.readouterr().out
    assert not out.exists()


def test_agora2_fetch_warns_that_vmh_ids_are_blocked_by_the_gate(tmp_path, capsys) -> None:
    from cmig.cli.main import main

    catalogue = tmp_path / "catalogue.json"
    write_catalogue(_entries(), catalogue)
    rc = main(["agora2-fetch", "--catalogue", str(catalogue), "--genus", "Roseburia",
               "--namespace", "vmh", "--dry-run", "--out", str(tmp_path / "pool")])
    assert rc == 0
    assert "namespace gate" in capsys.readouterr().err
