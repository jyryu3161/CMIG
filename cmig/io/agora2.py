"""AGORA2 (VMH) reconstruction fetcher — catalogue, download, repair, namespace conversion.

CMIG does not curate or redistribute model catalogues (``docs/USER_GUIDE.md`` "Scope And
Limitations"); this module is the one exception's *mechanism*, not a change of that policy. It
fetches user-selected reconstructions from the publisher's own file server on demand, records
exactly what was retrieved, and writes nothing into the repository.

Three facts about the published files drive the whole design; each was measured against
``version2.01`` on 2026-09-02 and each is a hazard if left implicit:

1. **The individual SBML files are not valid UTF-8.** They declare ``encoding="UTF-8"`` but carry
   stray Latin-1 bytes in species *names* (``ß`` in "regorafenib-N-ß-glucuronide", ``è``,
   non-breaking spaces). libsbml refuses the document outright — "Badly formed XML" — so cobra
   raises ``No SBML model detected in file``. Measured: 5 such bytes in
   ``Faecalibacterium_prausnitzii_A2_165``, 9 in ``Bacteroides_thetaiotaomicron_VPI_5482``, 0 in
   ``Eubacterium_rectale_ATCC_33656``. Without the repair in :func:`repair_utf8` roughly half the
   catalogue cannot be opened at all, so the repair is on by default and is recorded per model.

2. **The ids are VMH-style, not BiGG-style**, in two independent ways. Compartments are
   ``EX_but(e)`` / ``but[e]`` where BiGG writes ``EX_but_e`` / ``but_e``, and an isomer descriptor
   is separated by one underscore (``glc_D``, ``ala_L``, ``26dap_M``) where BiGG uses two
   (``glc__D``). CMIG's namespace gate scores an unconverted AGORA2 model at **0 % coverage and
   blocks it**; with only the compartment half converted a defined medium silently loses
   D-glucose and every amino acid and the community solves at zero growth.
   :func:`convert_ids_to_bigg` rewrites both — syntactic, collision-checked notation, never a
   metabolite-identity guess.

3. **They are big.** 7,302 reconstructions, roughly 4-28 MB each (about 70 GB in total), because
   most of each file is RDF annotation. ``--format json`` re-serialises the loaded model as cobra
   JSON: measured on ``Eubacterium_rectale_ATCC_33656``, 14.0 MB -> 1.16 MB and 1.72 s -> 0.26 s
   per load. A combination search rebuilds the community once per candidate, so that ratio is the
   difference between an afternoon and half an hour.

Nothing here asserts a licence for the reconstructions. The manifest records the citation and the
retrieval URL; the terms are the publisher's and the user's responsibility.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable, Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cmig.io.atomic import atomic_write_text

#: Catalogue/version this module targets. A different version directory has a different file set,
#: so the version is recorded in every manifest rather than assumed.
AGORA2_VERSION = "2.01"
AGORA2_BASE_URL = f"https://www.vmh.life/files/reconstructions/AGORA2/version{AGORA2_VERSION}"
#: Per-strain SBML. The only directory that serves individual reconstructions.
AGORA2_INDIVIDUAL_URL = f"{AGORA2_BASE_URL}/sbml_files/individual_reconstructions"
#: Bulk archives, for the user who wants the whole set (documented, not downloaded by CMIG).
AGORA2_ARCHIVE_URLS = {
    "annotated_sbml_all": f"{AGORA2_BASE_URL}/sbml_files/zipped/AGORA2_annotatedSBML_all.zip",
    "sbml_fixed": f"{AGORA2_BASE_URL}/sbml_files_fixed/zipped/AGORA2_models/AGORA2_SBML.zip",
}
#: Every fetch is refused unless its URL starts with this. A typo in a flag must not turn CMIG
#: into a general-purpose downloader (same guard as scripts/download_human_gems.py).
ALLOWED_URL_PREFIX = "https://www.vmh.life/files/reconstructions/AGORA2/"
AGORA2_CITATION = (
    "Heinken A, Hertel J, Acharya G, Ravcheev DA, Nyga M, Okpala OE, Hogan M, Magnúsdóttir S, "
    "Martinelli F, Nap B, Preciat G, Edirisinghe JN, Henry CS, Fleming RMT, Thiele I. "
    "Genome-scale metabolic reconstruction of 7,302 human microorganisms for personalized "
    "medicine. Nat Biotechnol. 2023;41(9):1320-1331. doi:10.1038/s41587-022-01628-0"
)
AGORA2_LICENSE_NOTE = (
    "CMIG asserts no licence for these reconstructions and redistributes none of them: they are "
    "fetched from the publisher's server on demand. Check the terms at https://www.vmh.life/ "
    "before redistribution or commercial use, and cite the AGORA2 paper for any result."
)
#: Individual reconstructions come from the 2023-03 annotated upload. The 2024-07 "fixed" rebuild
#: is published only as a single archive, so a selective fetch cannot use it.
AGORA2_SET_NOTE = (
    "Individual reconstructions are the annotated SBML set uploaded 2023-03-23. The 2024-07-04 "
    "'sbml_files_fixed' rebuild is published only as one 2.0 GB archive "
    f"({AGORA2_ARCHIVE_URLS['sbml_fixed']}), so a per-strain fetch cannot serve it."
)
CATALOGUE_SCHEMA_VERSION = "1.0"
MANIFEST_SCHEMA_VERSION = "1.0"
MANIFEST_FILENAME = "agora2_manifest.json"
CATALOGUE_FILENAME = "agora2_catalogue.json"
#: Identifies CMIG in the publisher's logs; the default urllib agent is refused by some hosts.
USER_AGENT = "CMIG/agora2-fetch (+https://github.com/jyryu3161/CMIG)"
#: Rough per-model size used only to warn before a large fetch (measured mean of the catalogue).
_MEAN_MODEL_BYTES = 9_500_000

#: One Apache index row. Whitespace between tags is tolerated so a cosmetic reformat of the
#: published index does not silently empty the catalogue.
_INDEX_ROW = re.compile(
    r'<a\s+href="(?P<href>[^"?/][^"]*\.xml)"\s*>[^<]*</a>\s*</td>'
    r"\s*<td[^>]*>(?P<modified>[^<]*)</td>\s*<td[^>]*>(?P<size>[^<]*)</td>",
    re.IGNORECASE,
)
#: VMH compartment notation. Metabolites use ``base[c]``, reactions ``BASE(c)``.
_VMH_METABOLITE = re.compile(r"^(?P<base>.+)\[(?P<compartment>[A-Za-z][A-Za-z0-9]?)\]$")
_VMH_REACTION = re.compile(r"^(?P<base>.+)\((?P<compartment>[A-Za-z][A-Za-z0-9]?)\)$")
#: VMH separates a stereo/isomer descriptor with one underscore (``glc_D``, ``ala_L``,
#: ``26dap_M``, ``12ppd_S``); BiGG uses two (``glc__D``). The rule rewrites exactly that token.
#: Measured over the 645 distinct exchange metabolites of a 20-strain AGORA2 pool against the 144
#: BiGG ids in CMIG's shipped gut media: matches rise 93 -> 122, 50 ids change, 0 collisions.
#: Without it a defined medium silently applies almost none of its carbon sources — D-glucose and
#: every amino acid are in the 29 recovered — and the community solves at zero growth.
_VMH_STEREO_SUFFIX = re.compile(r"(?<!_)_(?P<token>[DLRSM])(?=_|$)")


class Agora2Error(RuntimeError):
    """AGORA2 catalogue/fetch failure that the caller must surface, never swallow."""


@dataclass(frozen=True)
class CatalogueEntry:
    """One reconstruction as the publisher's directory index lists it."""

    #: File stem, e.g. ``Faecalibacterium_prausnitzii_A2_165``. Used as the CMIG member id.
    id: str
    file: str
    published_size: str
    published_modified: str

    @property
    def url(self) -> str:
        return f"{AGORA2_INDIVIDUAL_URL}/{self.file}"

    @property
    def genus(self) -> str:
        return self.id.split("_", 1)[0]

    @property
    def species(self) -> str:
        """``Genus_species`` where the name has one, else the genus."""
        parts = self.id.split("_")
        return "_".join(parts[:2]) if len(parts) > 1 else self.id


@dataclass
class ConversionReport:
    """What :func:`convert_ids_to_bigg` changed, for the manifest."""

    metabolites_converted: int = 0
    reactions_converted: int = 0
    #: Of the converted metabolites, how many also had an isomer separator rewritten.
    stereo_renamed: int = 0
    metabolites_unconverted: list[str] = field(default_factory=list)
    reactions_unconverted: int = 0


@dataclass
class FetchedModel:
    """Provenance record for one downloaded reconstruction."""

    id: str
    file: str
    source_url: str
    source_sha256: str
    source_bytes: int
    sha256: str
    bytes: int
    encoding_repairs: int
    repaired_bytes: list[str]
    namespace: str
    format: str
    n_reactions: int | None = None
    n_metabolites: int | None = None
    n_genes: int | None = None
    n_exchanges: int | None = None
    objective_reactions: list[str] = field(default_factory=list)
    conversion: dict[str, Any] | None = None


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _open_url(url: str, *, timeout: float) -> bytes:
    """Fetch ``url`` after checking it against :data:`ALLOWED_URL_PREFIX`."""
    if not url.startswith(ALLOWED_URL_PREFIX):
        raise Agora2Error(f"refusing to fetch from an unexpected location: {url}")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            data: bytes = response.read()
    except (urllib.error.URLError, OSError, TimeoutError) as error:
        raise Agora2Error(f"download failed for {url}: {type(error).__name__}: {error}") from error
    return data


#: Injection seam: tests and offline callers pass their own fetcher.
UrlFetcher = Callable[[str], bytes]


def default_fetcher(timeout: float = 120.0) -> UrlFetcher:
    return lambda url: _open_url(url, timeout=timeout)


# ── catalogue ────────────────────────────────────────────────────────────────────────────────


def parse_catalogue(html: str) -> list[CatalogueEntry]:
    """Parse the publisher's Apache directory index into catalogue entries.

    Refuses an empty parse rather than returning ``[]``: a silently empty catalogue would look
    like "no models matched your filter" when the real cause is a changed index format.
    """
    entries = [
        CatalogueEntry(
            id=match.group("href")[: -len(".xml")],
            file=match.group("href"),
            published_size=match.group("size").strip(),
            published_modified=match.group("modified").strip(),
        )
        for match in _INDEX_ROW.finditer(html)
    ]
    if not entries:
        raise Agora2Error(
            "AGORA2 directory index contained no .xml entries — the published index format has "
            f"changed, or the response was an error page ({AGORA2_INDIVIDUAL_URL})"
        )
    return sorted(entries, key=lambda entry: entry.id)


def fetch_catalogue(fetcher: UrlFetcher | None = None) -> list[CatalogueEntry]:
    """Download and parse the individual-reconstruction index."""
    fetch = fetcher or default_fetcher()
    html = fetch(f"{AGORA2_INDIVIDUAL_URL}/").decode("utf-8", errors="replace")
    return parse_catalogue(html)


def catalogue_payload(entries: Sequence[CatalogueEntry]) -> dict[str, Any]:
    return {
        "schema_version": CATALOGUE_SCHEMA_VERSION,
        "resource": {
            "name": "AGORA2",
            "version": AGORA2_VERSION,
            "index_url": f"{AGORA2_INDIVIDUAL_URL}/",
            "citation": AGORA2_CITATION,
            "license_note": AGORA2_LICENSE_NOTE,
            "set_note": AGORA2_SET_NOTE,
        },
        "retrieved_utc": _utcnow(),
        "n_models": len(entries),
        "models": [asdict(entry) for entry in entries],
    }


def write_catalogue(entries: Sequence[CatalogueEntry], path: str | Path) -> Path:
    return atomic_write_text(
        path,
        json.dumps(catalogue_payload(entries), indent=2, sort_keys=True, ensure_ascii=True) + "\n",
    )


def read_catalogue(path: str | Path) -> list[CatalogueEntry]:
    """Load a catalogue written by :func:`write_catalogue`."""
    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise Agora2Error(f"cannot read AGORA2 catalogue {source}: {error}") from error
    models = payload.get("models")
    if not isinstance(models, list) or not models:
        raise Agora2Error(f"AGORA2 catalogue {source} holds no models")
    return [
        CatalogueEntry(
            id=str(record["id"]),
            file=str(record["file"]),
            published_size=str(record.get("published_size", "")),
            published_modified=str(record.get("published_modified", "")),
        )
        for record in models
    ]


def load_or_fetch_catalogue(
    path: str | Path, *, refresh: bool = False, fetcher: UrlFetcher | None = None
) -> tuple[list[CatalogueEntry], bool]:
    """Cached catalogue, refetching when asked or when the cache is absent.

    Returns ``(entries, fetched)`` so the caller can report which happened.
    """
    target = Path(path)
    if not refresh and target.exists():
        return read_catalogue(target), False
    entries = fetch_catalogue(fetcher)
    write_catalogue(entries, target)
    return entries, True


# ── selection ────────────────────────────────────────────────────────────────────────────────


def select_entries(
    entries: Sequence[CatalogueEntry],
    *,
    ids: Iterable[str] | None = None,
    genera: Iterable[str] | None = None,
    pattern: str | None = None,
    exclude_pattern: str | None = None,
    sample: int | None = None,
    seed: int = 0,
    one_per_genus: bool = False,
    limit: int | None = None,
) -> list[CatalogueEntry]:
    """Filter the catalogue. Every filter is a conjunction; ``ids`` must all resolve.

    ``sample`` draws deterministically from the filtered set (``seed``); ``one_per_genus`` keeps
    the first entry of each genus (id order) *before* sampling, which is what makes "20 diverse
    models" a diverse set rather than 20 strains of Escherichia (999 of the 7,302 are
    Escherichia). ``exclude_pattern`` drops ids the user does not want in that first-per-genus
    draw — ``uncultured_|_ERR[0-9]`` keeps named isolates rather than metagenome bins.
    """
    selected = list(entries)
    if ids is not None:
        wanted = [str(value) for value in ids]
        by_id = {entry.id: entry for entry in entries}
        missing = [value for value in wanted if value not in by_id]
        if missing:
            raise Agora2Error(
                f"not in the AGORA2 catalogue: {missing[:8]}"
                + (f" (+{len(missing) - 8} more)" if len(missing) > 8 else "")
                + " — check `cmig agora2-list --match <substring>` for the exact strain id"
            )
        selected = [by_id[value] for value in wanted]
    if genera:
        wanted_genera = {str(value).lower() for value in genera}
        selected = [entry for entry in selected if entry.genus.lower() in wanted_genera]
    if pattern:
        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error as error:
            raise Agora2Error(f"invalid --match regular expression: {error}") from error
        selected = [entry for entry in selected if regex.search(entry.id)]
    if exclude_pattern:
        try:
            excluded = re.compile(exclude_pattern, re.IGNORECASE)
        except re.error as error:
            raise Agora2Error(f"invalid --exclude-match regular expression: {error}") from error
        selected = [entry for entry in selected if not excluded.search(entry.id)]
    if one_per_genus:
        seen: set[str] = set()
        unique: list[CatalogueEntry] = []
        for entry in selected:
            if entry.genus.lower() not in seen:
                seen.add(entry.genus.lower())
                unique.append(entry)
        selected = unique
    if sample is not None:
        if sample <= 0:
            raise Agora2Error("--sample must be a positive number of models")
        if sample < len(selected):
            selected = random.Random(seed).sample(selected, sample)
            selected.sort(key=lambda entry: entry.id)
    if limit is not None and limit < len(selected):
        selected = selected[:limit]
    return selected


# ── file repair and namespace conversion ─────────────────────────────────────────────────────


def repair_utf8(data: bytes) -> tuple[bytes, list[str]]:
    """Re-encode stray Latin-1 bytes so the XML is the UTF-8 it declares itself to be.

    Only the individual offending bytes are transcoded; the rest of the document is copied
    verbatim. Decoding the whole file as Latin-1 instead would corrupt any genuine multi-byte
    UTF-8 (measured: these files contain none, but a future upload may).

    Returns the repaired bytes and one ``offset:hex:char`` record per repair, for the manifest.
    """
    out = bytearray()
    repairs: list[str] = []
    index = 0
    while index < len(data):
        try:
            data[index:].decode("utf-8")
        except UnicodeDecodeError as error:
            out += data[index : index + error.start]
            offending = data[index + error.start : index + error.end]
            replacement = offending.decode("latin-1")
            out += replacement.encode("utf-8")
            repairs.append(f"{index + error.start}:{offending.hex()}:{replacement}")
            index += error.end
            continue
        out += data[index:]
        break
    return bytes(out), repairs


def bigg_stereo(base: str) -> str:
    """``glc_D`` -> ``glc__D``. Rewrites only a lone D/L/R/S/M isomer token (see the regex note)."""
    return _VMH_STEREO_SUFFIX.sub(lambda m: f"__{m.group('token')}", base)


def convert_ids_to_bigg(model: Any) -> ConversionReport:
    """Rewrite VMH identifier conventions to BiGG in place.

    Two conventions differ, and both are pure notation — no name mapping, no synonym table and no
    metabolite-identity guess is involved:

    * compartment: ``but[e]`` -> ``but_e``, ``EX_but(e)`` -> ``EX_but_e``;
    * isomer separator: ``glc_D`` -> ``glc__D`` (see :data:`_VMH_STEREO_SUFFIX` for the measured
      effect — without it a defined medium loses D-glucose and every amino acid).

    The isomer rule is applied to metabolites and to boundary reactions (exchange/demand/sink),
    which is where the namespace has to line up with a medium file and a ``--target``; internal
    reaction ids are notation of their own and are left alone.

    Fail-closed on collision: if two distinct ids would converge on one converted id the model is
    refused rather than silently merged, because a merged metabolite is a fabricated reaction
    network. Ids that do not carry VMH compartment notation (``biomass205``, ``BUTt2r``) are left
    exactly as they are and counted as unconverted.
    """
    report = ConversionReport()

    metabolite_map: dict[str, str] = {}
    for metabolite in model.metabolites:
        current = str(metabolite.id)
        match = _VMH_METABOLITE.match(current)
        if match is None:
            report.metabolites_unconverted.append(current)
            continue
        converted = f"{bigg_stereo(match.group('base'))}_{match.group('compartment')}"
        if converted != current:
            metabolite_map[current] = converted
            report.stereo_renamed += int(bigg_stereo(match.group("base"))
                                         != match.group("base"))
    _refuse_collisions("metabolite", metabolite_map, {str(m.id) for m in model.metabolites})

    boundary = {str(r.id) for r in model.reactions if r.boundary}
    reaction_map: dict[str, str] = {}
    for reaction in model.reactions:
        current = str(reaction.id)
        match = _VMH_REACTION.match(current)
        if match is None:
            report.reactions_unconverted += 1
            continue
        base = match.group("base")
        if current in boundary:
            base = bigg_stereo(base)
        converted = f"{base}_{match.group('compartment')}"
        if converted != current:
            reaction_map[current] = converted
    _refuse_collisions("reaction", reaction_map, {str(r.id) for r in model.reactions})

    for metabolite in model.metabolites:
        new_id = metabolite_map.get(str(metabolite.id))
        if new_id is not None:
            metabolite.id = new_id
    for reaction in model.reactions:
        new_id = reaction_map.get(str(reaction.id))
        if new_id is not None:
            reaction.id = new_id
    model.repair()
    report.metabolites_converted = len(metabolite_map)
    report.reactions_converted = len(reaction_map)
    # Only the first few unconverted metabolite ids are worth recording; the count is the signal.
    report.metabolites_unconverted = report.metabolites_unconverted[:20]
    return report


def _refuse_collisions(kind: str, mapping: dict[str, str], existing: set[str]) -> None:
    converted: dict[str, str] = {}
    for source, target in mapping.items():
        if target in converted:
            raise Agora2Error(
                f"VMH->BiGG conversion would merge two {kind}s onto {target!r} "
                f"({converted[target]!r} and {source!r}); refusing to rewrite this model"
            )
        if target in existing and target not in mapping:
            raise Agora2Error(
                f"VMH->BiGG conversion of {source!r} would collide with the existing {kind} "
                f"{target!r}; refusing to rewrite this model"
            )
        converted[target] = source


def _normalize_model_id(model: Any, entry_id: str) -> None:
    """Use the strain name as the model id.

    The SBML carries ``M_<strain>`` (libsbml's identifier prefix), which would otherwise reach
    manifests and figures as part of the organism's name.
    """
    current = str(getattr(model, "id", "") or "")
    model.id = current[2:] if current.startswith("M_") else (current or entry_id)


# ── fetch ────────────────────────────────────────────────────────────────────────────────────


def estimated_bytes(entries: Sequence[CatalogueEntry]) -> int:
    """Rough download size, from the published sizes when parseable."""
    total = 0
    for entry in entries:
        text = entry.published_size.strip().upper()
        match = re.match(r"^([\d.]+)([KMG])?$", text)
        if match is None:
            total += _MEAN_MODEL_BYTES
            continue
        scale = {"K": 1024, "M": 1024**2, "G": 1024**3, None: 1}[match.group(2)]
        total += int(float(match.group(1)) * scale)
    return total


def human_bytes(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def fetch_model(
    entry: CatalogueEntry,
    out_dir: str | Path,
    *,
    namespace: str = "bigg",
    file_format: str = "sbml",
    repair_encoding: bool = True,
    fetcher: UrlFetcher | None = None,
) -> FetchedModel:
    """Download one reconstruction, repair it, optionally convert ids, and write it.

    ``namespace='vmh'`` keeps the published ids (and, with ``file_format='sbml'``, the published
    bytes apart from the encoding repair). ``namespace='bigg'`` is what the rest of CMIG can
    actually consume — see the module docstring.
    """
    if namespace not in {"bigg", "vmh"}:
        raise Agora2Error(f"unknown namespace {namespace!r} (expected 'bigg' or 'vmh')")
    if file_format not in {"sbml", "json"}:
        raise Agora2Error(f"unknown format {file_format!r} (expected 'sbml' or 'json')")

    fetch = fetcher or default_fetcher()
    raw = fetch(entry.url)
    source_sha = sha256_bytes(raw)
    body, repairs = (repair_utf8(raw) if repair_encoding else (raw, []))

    destination = Path(out_dir)
    destination.mkdir(parents=True, exist_ok=True)
    suffix = ".json" if file_format == "json" else ".xml"
    target = destination / f"{entry.id}{suffix}"

    if namespace == "vmh" and file_format == "sbml":
        # Nothing to reparse: the repaired bytes are the artifact.
        target.write_bytes(body)
        return FetchedModel(
            id=entry.id, file=target.name, source_url=entry.url, source_sha256=source_sha,
            source_bytes=len(raw), sha256=sha256_bytes(body), bytes=len(body),
            encoding_repairs=len(repairs), repaired_bytes=repairs,
            namespace=namespace, format=file_format,
        )

    model = _load_repaired_model(body, entry, destination)
    conversion: ConversionReport | None = None
    if namespace == "bigg":
        conversion = convert_ids_to_bigg(model)
    _normalize_model_id(model, entry.id)
    _write_model(model, target, file_format)

    written = target.read_bytes()
    from cobra.util.solver import linear_reaction_coefficients

    return FetchedModel(
        id=entry.id, file=target.name, source_url=entry.url, source_sha256=source_sha,
        source_bytes=len(raw), sha256=sha256_bytes(written), bytes=len(written),
        encoding_repairs=len(repairs), repaired_bytes=repairs,
        namespace=namespace, format=file_format,
        n_reactions=len(model.reactions), n_metabolites=len(model.metabolites),
        n_genes=len(model.genes), n_exchanges=len(model.exchanges),
        objective_reactions=sorted(str(r.id) for r in linear_reaction_coefficients(model)),
        conversion=None if conversion is None else asdict(conversion),
    )


def _load_repaired_model(body: bytes, entry: CatalogueEntry, workdir: Path) -> Any:
    """Parse the repaired SBML through a temporary file (cobra reads paths, not buffers)."""
    try:
        import cobra.io
    except ImportError as error:  # pragma: no cover - env-dependent
        raise Agora2Error(
            "reading AGORA2 SBML needs the engine stack: uv sync --extra engine"
        ) from error
    staging = workdir / f".{entry.id}.agora2-staging.xml"
    try:
        staging.write_bytes(body)
        return cobra.io.read_sbml_model(str(staging))
    except Exception as error:  # noqa: BLE001 - libsbml/cobra expose an open error set
        raise Agora2Error(
            f"{entry.id}: repaired SBML still does not parse ({type(error).__name__}: "
            f"{str(error)[:200]})"
        ) from error
    finally:
        staging.unlink(missing_ok=True)


def _write_model(model: Any, target: Path, file_format: str) -> None:
    import cobra.io

    from cmig.io.atomic import atomic_write_path

    if file_format == "json":
        atomic_write_path(target, lambda tmp: cobra.io.save_json_model(model, str(tmp)))
    else:
        atomic_write_path(target, lambda tmp: cobra.io.write_sbml_model(model, str(tmp)))


def manifest_payload(
    models: Sequence[FetchedModel], *, namespace: str, file_format: str, repair_encoding: bool
) -> dict[str, Any]:
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "purpose": (
            "Provenance for AGORA2 reconstructions fetched by `cmig agora2-fetch`. The model "
            "files are not redistributed by CMIG; source_sha256 fingerprints the bytes as "
            "served, sha256 the bytes on disk after the recorded repair/conversion."
        ),
        "resource": {
            "name": "AGORA2",
            "version": AGORA2_VERSION,
            "individual_reconstructions_url": f"{AGORA2_INDIVIDUAL_URL}/",
            "archive_urls": dict(AGORA2_ARCHIVE_URLS),
            "citation": AGORA2_CITATION,
            "license_note": AGORA2_LICENSE_NOTE,
            "set_note": AGORA2_SET_NOTE,
        },
        "retrieved_utc": _utcnow(),
        "namespace": namespace,
        "format": file_format,
        "encoding_repair": "latin1_to_utf8" if repair_encoding else "none",
        "namespace_conversion": (
            "vmh_to_bigg: compartment notation (metabolite 'x[c]'->'x_c', reaction "
            "'R(c)'->'R_c') AND isomer separator on metabolites/boundary reactions "
            "('glc_D'->'glc__D'); collision-checked, no identity mapping"
            if namespace == "bigg"
            else "none (published VMH ids kept; CMIG's namespace gate blocks these)"
        ),
        "n_models": len(models),
        "models": [asdict(model) for model in models],
    }


def write_manifest(
    models: Sequence[FetchedModel],
    out_dir: str | Path,
    *,
    namespace: str,
    file_format: str,
    repair_encoding: bool,
) -> Path:
    payload = manifest_payload(
        models, namespace=namespace, file_format=file_format, repair_encoding=repair_encoding
    )
    return atomic_write_text(
        Path(out_dir) / MANIFEST_FILENAME,
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
    )


def read_manifest(out_dir: str | Path) -> dict[str, Any]:
    path = Path(out_dir) / MANIFEST_FILENAME
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}
