"""Round 6 track M — the shipped gut medium overlays must stay defensible.

Every assertion exists because a specific way of shipping a broken medium was *observed*, mostly in
``micom-dev/media`` itself or in CMIG's own merge semantics (see
``medium_presets/PROVENANCE_gut_media.md``):

* CMIG merges a medium onto MICOM's permissive default instead of replacing it, so a metabolite
  the file does not name keeps its default — for oxygen ``EX_o2_m = 999999.0``, an aerobic colon.
  Measured: the legacy glucose-only preset gives community growth 1.2678 h⁻¹ with the inherited open
  oxygen and 0.6990 h⁻¹ with the anaerobic term, an 81 % overestimate.
  → :func:`test_oxygen_is_a_trace_term`, :func:`test_background_is_fully_closed`
* a preset hand-edited so it no longer matches its cited source
  → :func:`test_overlays_are_regenerable_from_their_sources`
* a table transcribed from a PDF with a typo
  → :func:`test_agora_table12_transcription_matches_micoms_copy`
* a diet left in ``mmol person⁻¹ day⁻¹``, or divided by 24 h but not by the biomass normaliser
  → :func:`test_no_unconverted_source_value_survives`, :func:`test_magnitude_band`
* two namespace aliases for one metabolite in one file (round 5, exit 2)
  → :func:`test_no_conflicting_namespace_aliases`
* an entry whose exchange exists in no pool member, i.e. a row that silently does nothing
  → :func:`test_every_exchange_exists_in_a_bundled_model`
* a "high fibre" medium whose fibre the model pool cannot metabolise
  → :func:`test_fibre_coverage_is_recorded`
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from cmig.core.medium_spec import exchange_metabolite, load_medium

ROOT = Path(__file__).resolve().parent.parent
PRESETS = ROOT / "medium_presets"
SOURCES = PRESETS / "sources"
MODELS = ROOT / "models"

BUNDLED_MODELS = ("iAF987", "iHN637", "iML1515", "iSFV_1184", "iYO844")

#: The overlays this module governs. The two legacy one-row files are deliberately excluded — they
#: are audited in PROVENANCE §1 and kept only as a smoke fixture, not as diets.
GUT_OVERLAYS = (
    "gut_overlay_agora_western.csv",
    "gut_overlay_agora_high_fiber.csv",
    "gut_overlay_vmh_high_fat_low_carb.csv",
    "gut_overlay_vmh_high_fat_low_carb_x100.csv",
    "gut_overlay_vmh_high_fiber.csv",
    "gut_overlay_vmh_high_fiber_x100.csv",
    "gut_overlay_micom_western.csv",
)

VMH_SOURCES = ("vmh_eu_average.tsv", "vmh_high_fat_low_carb.tsv", "vmh_high_fiber.tsv")

# ── Magnitude band ────────────────────────────────────────────────────────────────────────────
# Bounds, not taste. Justification in PROVENANCE §4/§5:
#   * the largest shipped entry is water in the x100 VMH overlays, 1328;
#   * VMH prints water as 181671 mmol person⁻¹ day⁻¹, which is still 7570 after dividing by 24 h.
#     MAX_ANY therefore rejects both a raw diet and a diet missing the biomass normaliser.
MAX_ANY = 2000.0
#   * the largest carbon-bearing entry is 0.18 (AGORA glycerol) and 1.84 (VMH x100); a build that
#     divided by 24 h but forgot the 57 gDW normaliser would put glucose at 5.0 and sucrose at 8.4.
MAX_CARBON_BEARING = 3.0
#: Methanol is exempt: AGORA Supplementary Table 12 and MICOM's medium both publish it at 10
#: mmol gDW-1 h-1 (undiluted), which is ~670x their own glucose bound. Faithfully transcribed and
#: flagged in PROVENANCE §6 as an oddity of the published diet, not something introduced here.
CARBON_CAP_EXEMPT = frozenset({"meoh"})

#: Carbon-free BiGG metabolite ids appearing in the shipped overlays. Local to the test so it does
#: not import the builder's table.
CARBON_FREE = frozenset(
    {
        "ca2", "cd2", "cl", "co2", "cobalt2", "cro4", "cu", "cu2", "fe2", "fe3", "h", "h2", "h2o",
        "h2s", "i", "k", "mg2", "mn2", "mobd", "n2", "na1", "nh4", "ni2", "no2", "no3", "o2", "pi",
        "sel", "slnt", "so3", "so4", "tungs", "tsul", "zn2",
    }
)

BIOMASS_GDW = 57.0
HOURS_PER_DAY = 24.0
ANAEROBIC_O2 = 0.001


@pytest.fixture(scope="module")
def pool():
    """The bundled pool: exchange index + default-medium background. Same source as the builder."""
    pytest.importorskip("cobra")
    from scripts.build_gut_media import load_pool

    return load_pool()


def _specs() -> dict[str, dict[str, float]]:
    return {name: load_medium(PRESETS / name).uptake for name in GUT_OVERLAYS}


def _overlay_rows(name: str) -> list[dict[str, str]]:
    with open(PRESETS / name, newline="") as handle:
        return list(csv.DictReader(handle))


# ── Structure ─────────────────────────────────────────────────────────────────────────────────

def test_every_declared_overlay_is_shipped_and_parses():
    for name in GUT_OVERLAYS:
        path = PRESETS / name
        assert path.exists(), f"declared overlay missing: {name}"
        spec = load_medium(path)
        spec.validate()
        assert spec.uptake, f"{name} is empty"
        assert all(v >= 0 for v in spec.uptake.values()), name


def test_filenames_say_overlay_not_diet():
    """CMIG merges rather than replaces, so these files are overlays. The name must not lie.

    Globs the directory rather than trusting :data:`GUT_OVERLAYS`, so a newly added `gut_*.csv`
    cannot slip in undeclared or with a name that promises exact-medium semantics.
    """
    on_disk = sorted(path.name for path in PRESETS.glob("gut_*.csv"))
    assert on_disk, "no gut overlays found at all"
    for name in on_disk:
        assert name.startswith("gut_overlay_"), (
            f"{name}: a `--medium` file is applied by merging onto MICOM's default, so it overlays "
            "the medium rather than defining it. Keep `overlay` in the name."
        )
    assert on_disk == sorted(GUT_OVERLAYS), (
        f"medium_presets/ holds {on_disk} but this module governs {sorted(GUT_OVERLAYS)} — an "
        "overlay was added or removed without updating the tests and the provenance document."
    )


def test_no_conflicting_namespace_aliases():
    """One exchange id per metabolite, one compartment suffix per file.

    ``MediumSpec.validate`` only refuses aliases that request *different* limits; aliases that agree
    are merged. An overlay must not rely on that — round 5 showed that hedging ``EX_x_m`` and
    ``EX_x_e`` in one file changed the answer without changing ``medium_checksum``.
    """
    for name, uptake in _specs().items():
        by_metabolite: dict[str, list[str]] = {}
        for exchange in uptake:
            by_metabolite.setdefault(exchange_metabolite(exchange), []).append(exchange)
        duplicated = {met: ids for met, ids in by_metabolite.items() if len(ids) > 1}
        assert not duplicated, f"{name} has aliased exchange ids: {duplicated}"

        suffixes = {exchange.rsplit("_", 1)[-1] for exchange in uptake}
        assert suffixes == {"m"}, f"{name} mixes compartment suffixes: {sorted(suffixes)}"


def test_every_exchange_exists_in_a_bundled_model(pool):
    """A row whose exchange exists in no pool member is a row that does nothing."""
    for name, uptake in _specs().items():
        orphans = sorted(
            exchange for exchange in uptake if exchange_metabolite(exchange) not in pool.exchanges
        )
        assert not orphans, f"{name}: no bundled model can take up {orphans}"


def test_coverage_is_nontrivial(pool):
    """Each overlay must be usable by more than a token fraction of the pool."""
    for name, uptake in _specs().items():
        for model in BUNDLED_MODELS:
            covered = sum(
                1 for exchange in uptake if model in pool.exchanges[exchange_metabolite(exchange)]
            )
            assert covered >= 20, f"{name}: only {covered}/{len(uptake)} entries reach {model}"


# ── Background closure — the round-6 headline ─────────────────────────────────────────────────

def test_oxygen_is_a_trace_term():
    """The colonic lumen is near-anoxic (PROVENANCE S8), so every overlay must pin O2 low.

    Without an explicit row the community inherits MICOM's default ``EX_o2_m = 999999.0``. Measured
    on ``iML1515 + iYO844 + iHN637``: the legacy glucose-only preset gives 1.2678 h⁻¹ with that
    default and 0.6990 h⁻¹ with ``EX_o2_m = 0.001``.
    """
    for name, uptake in _specs().items():
        assert "EX_o2_m" in uptake, (
            f"{name} has no oxygen row, so the community inherits MICOM's default 999999 and the "
            "colon is aerobic"
        )
        assert uptake["EX_o2_m"] <= ANAEROBIC_O2, (
            f"{name}: EX_o2_m = {uptake['EX_o2_m']} exceeds the anaerobic term {ANAEROBIC_O2}. The "
            "x100 rescale must NOT scale the oxygen row — it is an environmental boundary "
            "condition, not a dietary flux."
        )


def test_background_is_fully_closed(pool):
    """Every metabolite the pool leaves open by default must be named, so nothing leaks.

    CMIG applies ``--medium`` with ``exact=False``: unnamed metabolites keep MICOM's default bound.
    Naming a metabolite with ``uptake_limit = 0`` is how a CSV says "the environment does not supply
    this" under merge semantics.
    """
    for name, uptake in _specs().items():
        named = {exchange_metabolite(exchange) for exchange in uptake}
        leaking = sorted(
            met for met in pool.background if met in pool.exchanges and met not in named
        )
        assert not leaking, (
            f"{name} leaves {leaking} at the pool's permissive default because it does not name "
            "them. Add a background-closure row (uptake_limit 0) for each."
        )


def test_closure_rows_are_exactly_zero():
    """A closure row must be 0, not merely small — and must survive the x100 rescale as 0."""
    with open(PRESETS / "provenance_rows.csv", newline="") as handle:
        rows = [r for r in csv.DictReader(handle) if r["origin"] == "background_closure"]
    assert rows, "no background_closure rows at all — the closure block is gone"
    offenders = [(r["preset"], r["exchange_id"], r["uptake_limit"]) for r in rows
                 if float(r["uptake_limit"]) != 0.0]
    assert not offenders, f"background_closure rows must be 0.0: {offenders}"


def test_pool_closure_marker_completely_identifies_the_block(pool):
    """``row_role=pool_closure`` must identify all and only bundled-pool bookkeeping rows."""
    from scripts.build_gut_media import (
        NUTRIENT_ROW_ROLE,
        POOL_CLOSURE_ROW_ROLE,
        ROW_ROLES,
    )

    with open(PRESETS / "provenance_rows.csv", newline="") as handle:
        provenance = list(csv.DictReader(handle))

    for name in GUT_OVERLAYS:
        rows = _overlay_rows(name)
        roles = {row["row_role"] for row in rows}
        assert roles == ROW_ROLES, f"{name}: expected both row roles, found {sorted(roles)}"

        nutrient_metabolites = {
            exchange_metabolite(row["exchange_id"])
            for row in rows
            if row["row_role"] == NUTRIENT_ROW_ROLE
        }
        marked = {
            exchange_metabolite(row["exchange_id"])
            for row in rows
            if row["row_role"] == POOL_CLOSURE_ROW_ROLE
        }
        expected = {
            met
            for met in pool.background
            if met in pool.exchanges and met not in nutrient_metabolites
        }
        assert marked == expected, (
            f"{name}: pool_closure marker mismatch "
            f"(missing {sorted(expected - marked)}, extra {sorted(marked - expected)})"
        )

        origins = {
            row["exchange_id"]: row["origin"]
            for row in provenance
            if row["preset"] == name
        }
        for row in rows:
            expected_role = (
                POOL_CLOSURE_ROW_ROLE
                if origins[row["exchange_id"]] == "background_closure"
                else NUTRIENT_ROW_ROLE
            )
            assert row["row_role"] == expected_role, (
                f"{name}/{row['exchange_id']}: marker {row['row_role']!r} disagrees with "
                f"origin {origins[row['exchange_id']]!r}"
            )


def test_stripping_pool_closure_yields_a_nutrient_only_medium(tmp_path):
    """Filtering the marker produces a valid exact-mode CSV with every scientific row intact."""
    from scripts.build_gut_media import NUTRIENT_ROW_ROLE, POOL_CLOSURE_ROW_ROLE

    for name in GUT_OVERLAYS:
        rows = _overlay_rows(name)
        nutrient_rows = [row for row in rows if row["row_role"] == NUTRIENT_ROW_ROLE]
        closure_ids = {
            row["exchange_id"]
            for row in rows
            if row["row_role"] == POOL_CLOSURE_ROW_ROLE
        }
        stripped = tmp_path / name
        with open(stripped, "w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["exchange_id", "uptake_limit"])
            writer.writeheader()
            writer.writerows(
                {"exchange_id": row["exchange_id"], "uptake_limit": row["uptake_limit"]}
                for row in nutrient_rows
            )

        uptake = load_medium(stripped).uptake
        expected = {row["exchange_id"]: float(row["uptake_limit"]) for row in nutrient_rows}
        assert uptake == expected, f"{name}: stripping closure changed a nutrient value"
        assert set(uptake).isdisjoint(closure_ids), f"{name}: a pool_closure row survived filtering"


def test_builder_check_catches_a_hand_edited_closure_row(
    tmp_path, monkeypatch, capsys, pool
):
    """The staleness gate must reject edits inside the newly marked closure section."""
    import scripts.build_gut_media as builder

    monkeypatch.setattr(builder, "PRESETS", tmp_path)
    monkeypatch.setattr(builder, "PROVENANCE_ROWS", tmp_path / "provenance_rows.csv")
    monkeypatch.setattr(builder, "load_pool", lambda: pool)
    overlays = builder.build_all(pool)
    for overlay in overlays:
        (tmp_path / overlay.filename).write_text(builder.render(overlay))
    builder.PROVENANCE_ROWS.write_text(builder.render_provenance(overlays))

    path = tmp_path / GUT_OVERLAYS[0]
    with open(path, newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames
        rows = list(reader)
    assert fieldnames is not None
    closure = next(row for row in rows if row["row_role"] == builder.POOL_CLOSURE_ROW_ROLE)
    closure["uptake_limit"] = "1.0"
    with open(path, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    assert builder.main(["--check"]) == 1
    captured = capsys.readouterr()
    assert GUT_OVERLAYS[0] in captured.err


# ── Units ─────────────────────────────────────────────────────────────────────────────────────

def test_magnitude_band():
    for name, uptake in _specs().items():
        worst = max(uptake.values())
        assert worst <= MAX_ANY, (
            f"{name}: largest uptake_limit {worst:g} exceeds {MAX_ANY:g} mmol gDW-1 h-1 — that is "
            "the signature of a diet left in mmol person-1 day-1, or one divided by 24 h but "
            "not by the colonic biomass. See PROVENANCE_gut_media.md §3."
        )
        over = {
            exchange: value
            for exchange, value in uptake.items()
            if exchange_metabolite(exchange) not in CARBON_FREE
            and exchange_metabolite(exchange) not in CARBON_CAP_EXEMPT
            and value > MAX_CARBON_BEARING
        }
        assert not over, (
            f"{name}: carbon-bearing entries above {MAX_CARBON_BEARING:g} mmol gDW-1 h-1: {over}. "
            "A colonic diet supplies ~1 mmol C gDW-1 h-1 per metabolite at most."
        )


def test_no_unconverted_source_value_survives():
    """No shipped number may be a raw ``mmol person⁻¹ day⁻¹`` value copied straight through.

    This is the exact failure in ``micom-dev/media``'s own ``vmh_high_fiber`` recipe, whose shipped
    artifact carries ``etoh = 4.5584`` (the day value x dilution, never divided by 24 h or by the
    biomass) and ``h2o = 36334`` labelled mmol gDW⁻¹ h⁻¹.
    """
    raw: set[float] = set()
    for source in VMH_SOURCES:
        for line in (SOURCES / source).read_text().splitlines()[1:]:
            if line.strip():
                value = float(line.split("\t")[1])
                if value > 1.0:          # below 1 a coincidence is meaningless
                    raw.add(value)
    assert raw, "no VMH source values read — the mirrored sources are missing"
    for name, uptake in _specs().items():
        leaked = {ex: v for ex, v in uptake.items() if v in raw}
        assert not leaked, f"{name} carries unconverted source values: {leaked}"


def test_worked_examples_reproduce_shipped_values():
    """The worked examples in PROVENANCE §3.1/§3.2 must reproduce the CSVs exactly.

    VMH family: ``v = D * f_colon / (B_gDW * 24)``.
    AGORA family: ``v = published * micom_dilution`` — no conversion, the table is already in
    mmol gDW⁻¹ h⁻¹.
    """
    vmh = load_medium(PRESETS / "gut_overlay_vmh_high_fiber.csv").uptake
    for exchange, intake, f_colon in [
        ("EX_glc__D_m", 120.210995032636, 0.1),
        ("EX_h2o_m", 181671.336776337, 0.1),
        ("EX_etoh_m", 22.792195952106, 0.1),
        ("EX_ca2_m", 33.0201107839713, 1.0),
        ("EX_fol_m", 0.000272645010836998, 0.1),
    ]:
        expected = intake * f_colon / (BIOMASS_GDW * HOURS_PER_DAY)
        assert vmh[exchange] == expected, (
            f"{exchange}: shipped {vmh[exchange]!r} != {intake!r} * {f_colon} / "
            f"({BIOMASS_GDW} * {HOURS_PER_DAY}) = {expected!r}"
        )

    agora = load_medium(PRESETS / "gut_overlay_agora_western.csv").uptake
    fiber = load_medium(PRESETS / "gut_overlay_agora_high_fiber.csv").uptake
    for exchange, western, high_fiber, dilution in [
        ("EX_glc__D_m", 0.14898579, 0.03947368, 0.1),
        ("EX_raffin_m", 0.00470194, 0.10416667, 1.0),
        ("EX_ala__L_m", 1.0, 1.0, 0.1),
    ]:
        assert agora[exchange] == western * dilution, exchange
        assert fiber[exchange] == high_fiber * dilution, exchange

    source = {
        line.split("\t")[0]: line.split("\t")[1]
        for line in (SOURCES / "vmh_high_fiber.tsv").read_text().splitlines()[1:]
        if line.strip()
    }
    assert float(source["EX_glc_D[e]"]) == 120.210995032636
    assert float(source["EX_ca2[e]"]) == 33.0201107839713


def test_agora_table12_transcription_matches_micoms_copy():
    """The PDF transcription is validated against MICOM's independent copy of the same column.

    ``micom-dev/paper/data/western_diet.csv``'s ``flux`` column is AGORA Supplementary Table 12's
    Western column, rounded to ~3 significant figures; conversely the PDF truncates a few values
    MICOM carries at higher precision (``bglc``: 7e-08 printed vs 7.05e-08). 2 % relative agreement
    is therefore the tightest bound the two representations support. It still catches any
    single-digit transcription error, which moves a value by >=10 %.
    """
    from scripts.build_gut_media import (
        MICOM_DILUTION_ALIASES,
        read_agora_table12,
        read_micom_dilutions,
    )

    table = read_agora_table12()
    assert len(table) == 164, f"AGORA Table 12 should have 164 rows, found {len(table)}"
    micom = read_micom_dilutions()
    mismatches = []
    compared = 0
    for entry in table:
        key = MICOM_DILUTION_ALIASES.get(entry["metabolite_id"], entry["metabolite_id"])
        if key not in micom:
            continue
        compared += 1
        published = float(entry["western_diet"])
        flux = micom[key][0]
        if published and abs(published - flux) / published > 2e-2:
            mismatches.append((entry["metabolite_id"], published, flux))
    assert compared >= 160, f"only {compared} rows could be cross-checked"
    assert not mismatches, f"transcription disagrees with MICOM's copy: {mismatches}"


def test_x100_variants_rescale_only_the_dietary_rows():
    """The rescale must preserve every dietary ratio and leave the environment alone."""
    with open(PRESETS / "provenance_rows.csv", newline="") as handle:
        rows = list(csv.DictReader(handle))
    held = {"micom_anaerobic_o2", "background_closure"}
    for base in ("gut_overlay_vmh_high_fat_low_carb", "gut_overlay_vmh_high_fiber"):
        plain = load_medium(PRESETS / f"{base}.csv").uptake
        scaled = load_medium(PRESETS / f"{base}_x100.csv").uptake
        assert set(plain) == set(scaled), base
        origins = {r["exchange_id"]: r["origin"] for r in rows if r["preset"] == f"{base}.csv"}
        for exchange, value in plain.items():
            factor = 1.0 if origins[exchange] in held else 100.0
            assert scaled[exchange] == pytest.approx(value * factor, rel=1e-12), (
                f"{base}_x100 at {exchange}: origin {origins[exchange]!r} expected factor {factor}"
            )


# ── Biology ───────────────────────────────────────────────────────────────────────────────────

def test_the_diet_contrast_actually_exists():
    """Both contrast pairs must differ where their diets differ, else the pair is inert."""
    agora_w = load_medium(PRESETS / "gut_overlay_agora_western.csv").uptake
    agora_f = load_medium(PRESETS / "gut_overlay_agora_high_fiber.csv").uptake
    for sugar in ("EX_glc__D_m", "EX_fru_m", "EX_sucr_m", "EX_lcts_m"):
        assert agora_w[sugar] > agora_f[sugar] * 2.0, f"AGORA sugar contrast gone at {sugar}"
    assert agora_f["EX_raffin_m"] > agora_w["EX_raffin_m"] * 5.0, "AGORA fibre contrast gone"

    vmh_f = load_medium(PRESETS / "gut_overlay_vmh_high_fiber.csv").uptake
    vmh_x = load_medium(PRESETS / "gut_overlay_vmh_high_fat_low_carb.csv").uptake
    for sugar in ("EX_glc__D_m", "EX_fru_m", "EX_sucr_m", "EX_lcts_m"):
        assert vmh_f[sugar] > vmh_x[sugar] * 1.5, f"VMH carbohydrate contrast gone at {sugar}"
    for fat in ("EX_hdca_m", "EX_ocdcea_m"):
        assert vmh_x[fat] > vmh_f[fat] * 1.5, f"VMH lipid contrast gone at {fat}"


def test_fibre_coverage_is_recorded(pool):
    """AGORA's 24 fibre entries: only raffinose is metabolisable by this pool. Say so.

    If this fails because the model pool changed, the finding in PROVENANCE §6 ("with this pool the
    high-fibre overlay is not a fibre-degradation contrast") must be re-measured and rewritten.
    """
    from scripts.build_gut_media import fiber_coverage

    reachable, unreachable = fiber_coverage(pool)
    assert len(reachable) + len(unreachable) == 24
    assert [entry[0] for entry in reachable] == ["raffin"], (
        f"fibre coverage changed: reachable = {reachable}. Update PROVENANCE §6."
    )
    doc = (PRESETS / "PROVENANCE_gut_media.md").read_text()
    assert "1/24" in doc, "PROVENANCE must state the measured fibre coverage"


# ── Provenance ────────────────────────────────────────────────────────────────────────────────

def test_every_overlay_has_row_level_provenance():
    from scripts.build_gut_media import ORIGINS

    with open(PRESETS / "provenance_rows.csv", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for name, uptake in _specs().items():
        recorded = {r["exchange_id"]: r for r in rows if r["preset"] == name}
        assert set(recorded) == set(uptake), (
            f"provenance_rows.csv does not describe {name} exactly "
            f"(missing {sorted(set(uptake) - set(recorded))}, "
            f"extra {sorted(set(recorded) - set(uptake))})"
        )
        for exchange, limit in uptake.items():
            row = recorded[exchange]
            assert float(row["uptake_limit"]) == limit, f"{name}/{exchange} value disagrees"
            assert row["origin"] in ORIGINS, f"{name}/{exchange} bad origin {row['origin']!r}"


def test_provenance_document_names_every_overlay_and_its_sources():
    doc = (PRESETS / "PROVENANCE_gut_media.md").read_text()
    for name in GUT_OVERLAYS:
        assert name in doc or name.replace("_x100", "") in doc, f"{name} undocumented"
    for doi in (
        "10.1038/nbt.3703",                     # AGORA Supp Table 12 — the primary source
        "10.1093/nar/gky992",                   # VMH units
        "10.1128/mSystems.00606-19",            # small-intestinal factor + flux unit
        "10.1371/journal.pbio.1002533",         # colonic bacterial dry biomass
        "10.1016/j.freeradbiomed.2012.10.554",  # near-anoxic lumen
    ):
        assert doi in doc, f"provenance document lost its citation for {doi}"
    for source in (
        *VMH_SOURCES,
        "agora_supp_table12.csv",
        "micom_paper_western_diet.csv",
        "carveme_skeleton.csv",
        "recon3d_host_absorbed.txt",
    ):
        assert (SOURCES / source).exists(), f"mirrored source missing: {source}"


def test_overlays_are_regenerable_from_their_sources():
    """The strongest check: re-derive every number from ``sources/`` and compare byte-for-byte."""
    pytest.importorskip("cobra")
    from scripts.build_gut_media import main

    assert main(["--check"]) == 0, (
        "a shipped overlay no longer matches what scripts/build_gut_media.py derives from "
        "medium_presets/sources/. Re-run `python -m scripts.build_gut_media`."
    )
