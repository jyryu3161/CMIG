"""Build the literature-grounded gut medium overlays in ``medium_presets/``.

Run from the repository root::

    python -m scripts.build_gut_media            # rewrite medium_presets/gut_overlay_*.csv
    python -m scripts.build_gut_media --check    # fail if a shipped overlay is stale
    python -m scripts.build_gut_media --report   # per-model coverage + fibre coverage

Everything the build needs is mirrored under ``medium_presets/sources/`` so the overlays are
reproducible offline; the network is never touched. ``--report`` additionally reads the bundled SBML
models in ``models/`` (cobra required) for exchange coverage.

Why "overlay" and not "diet"
----------------------------
CMIG applies ``--medium`` by **merging** onto whatever the community already offers
(``apply_medium_translated(..., exact=False)``), so a CSV does not *replace* the medium; it overlays
it. Measured on a MICOM community of ``iML1515 + iYO844``, applying a glucose-only spec leaves 23
other uptakes wide open, including ``EX_o2_m = 999999.0``. A file that does not name a metabolite
therefore inherits MICOM's permissive default for it — which for oxygen means an **aerobic colon**.

Two consequences, both handled here:

* every overlay carries an explicit ``EX_o2_m`` row (MICOM's own published 0.001, see
  :data:`MICOM_ANAEROBIC_O2`), and
* every overlay carries a **background closure block**: each metabolite that any bundled model's
  default medium leaves open, and that the diet does not name, is emitted with
  ``uptake_limit = 0.0``. A zero row is how a CSV expresses "the environment does not supply this"
  under merge semantics — verified: it drives the community exchange to ``lower_bound = -0.0``.

The word "overlay" is in every filename so the semantics cannot be mistaken for exact-medium
semantics. See ``medium_presets/PROVENANCE_gut_media.md``.

Units
-----
``cmig.core.medium_spec.MediumSpec`` is ``{exchange_id: uptake_limit}`` with ``uptake_limit >= 0``,
an unsigned magnitude in **mmol gDW⁻¹ h⁻¹** applied as ``lower_bound = -uptake_limit``.

Two independent source families are used, deliberately:

1. **AGORA Supplementary Table 12** (Magnúsdóttir et al. 2017, doi:10.1038/nbt.3703) is titled
   "Uptake rates (mmol gDW⁻¹ h⁻¹) for dietary compounds implemented to simulate Western and high
   fiber diet" — i.e. **already in CMIG's units**, for both arms of the contrast. No conversion, no
   biomass assumption. Multiplied by MICOM's per-reaction small-intestinal dilution factor.
2. **VMH diet-designer exports** are in **mmol person⁻¹ day⁻¹** and need the conversion in
   :func:`build_vmh_overlay`. Kept because they are an *independent* derivation: their converted
   glucose lands within 1.5x of AGORA's published bound, which is the only end-to-end check on the
   conversion arithmetic that exists.

Namespace
---------
Exchange ids are emitted as ``EX_<met>_m`` — the form a MICOM community exposes, and the form
micom's own ``MicomMedium[Global]`` artifacts use. CMIG matches a medium onto a model by
*metabolite*, so ``EX_glc__D_m`` also reaches ``EX_glc__D_e`` in a member model. Emitting both forms
for one metabolite is refused by ``MediumSpec.validate`` (round 5), so exactly one compartment
suffix is used per file.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRESETS = ROOT / "medium_presets"
SOURCES = PRESETS / "sources"
MODELS = ROOT / "models"

BUNDLED_MODELS = ("iAF987", "iHN637", "iML1515", "iSFV_1184", "iYO844")

# ── Conversion constants (VMH family only; the AGORA family needs none) ───────────────────────
HOURS_PER_DAY = 24.0

#: Colonic bacterial dry biomass the VMH diet is normalised against, in gDW.
#: Sender, Fuchs & Milo 2016 (PLoS Biol 14:e1002533, doi:10.1371/journal.pbio.1002533) report
#: "3.8·10^13 bacteria in the colon" and "an average mass of a gut bacterium of about 5 pg (wet
#: weight, corresponding to a dry weight of 1–2 pg)", and separately "the total dry weight of
#: bacteria in the body is about 50–100 g". 3.8e13 * 1.5 pg = 57 gDW sits inside both statements.
#: The 1.5 pg midpoint is an ASSUMPTION; the cited 1–2 pg range maps to 38–76 gDW, a ±33 % band.
#: Note 38 gDW (the 1.0 pg end) is what reproduces AGORA's published glucose bound — PROVENANCE §4.
BIOMASS_GDW = 57.0

#: Fraction of an ingested metabolite reaching the colon. Diener, Gibbons & Resendis-Antonio 2020
#: (mSystems 5:e00606-19): "To account for uptake in the small intestine, we reduced all import
#: fluxes for metabolites commonly absorbed in the small intestine by a factor of 10."
#: "Commonly absorbed" is operationalised exactly as micom-dev/media does it: host-absorbable iff
#: Recon3D has an exchange for it (``sources/recon3d_host_absorbed.txt``).
F_COLON_ABSORBED = 0.1
F_COLON_OTHER = 1.0

#: VMH's web export truncates to four decimals, so a small genuine intake prints as 0.
#: micom-dev/media substitutes 1e-4 ("bug in VMH designer where everything <1e-4 gets truncated to
#: 0" — recipes/vmh_high_fiber.ipynb). Applied to the *pre-conversion* value.
VMH_TRUNCATION_FLOOR = 1e-4

#: MICOM's anaerobic-colon term. AGORA Supp Table 12 has no oxygen row at all; MICOM added
#: ``EX_o2_e`` with flux 1 and dilution 0.001 (``sources/micom_paper_western_diet.csv``), i.e.
#: 0.001 mmol gDW⁻¹ h⁻¹, describing it as "deplete oxygen since the lower gut is mostly anaerobic"
#: and "a minuscule amount of oxygen" (micom-dev/media recipes). Biological basis: Espey 2013,
#: Free Radic Biol Med 55:130–140 — intestinal oxygen gradients "plunge to near anoxia at the
#: luminal midpoint". Left at a trace rather than hard zero so obligate-O2 models are not
#: hard-infeasible.
MICOM_ANAEROBIC_O2 = 0.001

#: Trace micronutrients present in neither source family. **ASSUMPTION — no literature value.**
#: Ni²⁺ is a urease/[NiFe]-hydrogenase cofactor present in every defined bacterial medium; VMH does
#: not track it and AGORA Table 12 omits it. The flux is the one MICOM gives its other trace metals
#: (cobalt2, mn2, zn2, mobd). Measured effect of removing it: ``micom.media.complete_medium`` names
#: ``EX_ni2_e`` as a required addition for iHN637, iML1515 and iSFV_1184.
TRACE_MICRONUTRIENTS = {"ni2": 0.1}

#: Held back from every overlay except the verbatim MICOM one. A **modelling choice, not a sourced
#: value**: at MICOM's 0.1 mmol gDW⁻¹ h⁻¹ these are ~10x the diet's entire glucose supply and would
#: open an anaerobic-respiration route that outcompetes the fermentation these overlays exist to
#: study. ``gut_overlay_micom_western.csv`` keeps MICOM's ``EX_no2_m,0.1`` verbatim so the effect is
#: measurable rather than assumed.
EXCLUDED_ELECTRON_ACCEPTORS = frozenset({"no2", "no3", "tsul"})

#: A single dimensionless factor applied uniformly to every entry, emitted as a ``*_x100.csv``
#: variant. **ENGINEERING RESCALE — not a literature value.** It preserves every ratio, so the
#: dietary contrast is untouched. It exists because the literature-scale diet (~1 mmol C gDW⁻¹ h⁻¹
#: total carbon) sits *below* the non-growth maintenance ATP floor hard-coded in the bundled models
#: (ATPM lower bound: iHN637 0.45, iAF987 0.81, iSFV_1184 3.15, iML1515 6.86, iYO844 9.0), which
#: makes every one of them infeasible as a single-model exact medium — MICOM's own published gut
#: medium included. See PROVENANCE §5.
FBA_RESCALE = 100.0

#: AGORA/VMH ids whose BiGG counterpart the ``__`` -> ``_`` bridge cannot recover.
EXPLICIT_ID_ALIASES = {"H2": "h2"}

#: AGORA ids MICOM renamed in its own copy of the diet, used only to look up the dilution factor.
MICOM_DILUTION_ALIASES = {"glc_D": "glc", "adocbl": "adpcbl", "H2": "h2"}

CONSTANTS = {
    "HOURS_PER_DAY": (HOURS_PER_DAY, "definition"),
    "BIOMASS_GDW": (BIOMASS_GDW, "Sender/Fuchs/Milo 2016 + assumption (1.5 pg cell dry weight)"),
    "F_COLON_ABSORBED": (F_COLON_ABSORBED, "Diener et al. 2020 mSystems (factor-of-10 reduction)"),
    "F_COLON_OTHER": (F_COLON_OTHER, "definition (not host-absorbed -> undiluted)"),
    "VMH_TRUNCATION_FLOOR": (VMH_TRUNCATION_FLOOR, "micom-dev/media recipe (VMH export artefact)"),
    "MICOM_ANAEROBIC_O2": (MICOM_ANAEROBIC_O2, "MICOM paper diet file (flux 1 x dilution 0.001)"),
    "TRACE_MICRONUTRIENTS": (TRACE_MICRONUTRIENTS, "ASSUMPTION (no source; MICOM trace flux)"),
    "FBA_RESCALE": (FBA_RESCALE, "ENGINEERING RESCALE (no source; maintenance-ATP compatibility)"),
}

#: Carbon-free BiGG metabolite ids relevant to these overlays. Only used to separate "inorganic
#: medium salt" from "diet macronutrient"; anything not listed is treated as carbon-bearing.
CARBON_FREE = frozenset(
    {
        "ca2", "cd2", "cl", "co2", "cobalt2", "cro4", "cu", "cu2", "fe2", "fe3", "h", "h2", "h2o",
        "h2s", "i", "k", "mg2", "mn2", "mobd", "n2", "na1", "nh4", "ni2", "no2", "no3", "o2", "pi",
        "sel", "slnt", "so3", "so4", "tungs", "tsul", "zn2",
    }
)

#: AGORA Table 12's own ``class`` column marks 24 rows as fibre. Used by ``--report``.
FIBER_CLASS = "fiber"


# ── Source readers ────────────────────────────────────────────────────────────────────────────

def read_host_absorbed() -> set[str]:
    """Recon3D-derived host-absorbable metabolite ids, in the VMH single-underscore form."""
    lines = (SOURCES / "recon3d_host_absorbed.txt").read_text().splitlines()
    return {line.strip() for line in lines if line.strip() and not line.startswith("#")}


def read_vmh_diet(name: str) -> list[tuple[str, float]]:
    """A VMH diet-designer export → ``[(vmh_metabolite_id, mmol person⁻¹ day⁻¹)]``.

    The export writes ``EX_glc_D[e]`` or ``EX_mn2(e)`` inconsistently; both suffixes are stripped.
    """
    rows: list[tuple[str, float]] = []
    for line in (SOURCES / name).read_text().splitlines()[1:]:
        if not line.strip():
            continue
        reaction, flux = line.split("\t")
        met = reaction.removeprefix("EX_").removesuffix("[e]").removesuffix("(e)")
        rows.append((met, float(flux)))
    return rows


def read_agora_table12() -> list[dict[str, str]]:
    """AGORA Supplementary Table 12, transcribed from the supplementary PDF.

    ``sources/agora_supp_table12.csv``, 164 rows: ``metabolite_id``, ``exchange_reaction_id``,
    ``metabolite_name``, ``class``, ``western_diet``, ``high_fiber_diet``. Units are printed in the
    table's own title: **mmol gDW⁻¹ h⁻¹**.

    The transcription is machine-checked against MICOM's independently published copy of the same
    Western column by
    ``tests/test_medium_presets_gut.py::test_agora_table12_transcription_matches_micoms_copy``.
    """
    with open(SOURCES / "agora_supp_table12.csv", newline="") as handle:
        return list(csv.DictReader(handle))


def read_micom_dilutions() -> dict[str, tuple[float, float]]:
    """MICOM's per-reaction ``(flux, dilution)`` for the western diet, keyed by AGORA metabolite id.

    ``sources/micom_paper_western_diet.csv``, mirrored from
    ``micom-dev/paper/data/western_diet.csv``. ``flux`` is AGORA Table 12's Western column
    (rounded); ``dilution`` is the small-intestinal factor MICOM multiplies by. 140 rows carry 0.1,
    29 carry 1.0 (the polysaccharides, not absorbed upstream) and ``o2`` carries 0.001.
    """
    out: dict[str, tuple[float, float]] = {}
    with open(SOURCES / "micom_paper_western_diet.csv", newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            met = row["reaction"].removeprefix("EX_").removesuffix("_e")
            out[met] = (float(row["flux"]), float(row["dilution"]))
    return out


def read_micom_western() -> dict[str, float]:
    """MICOM's published western-diet gut medium in BiGG ids → mmol gDW⁻¹ h⁻¹.

    ``sources/carveme_skeleton.csv``, mirrored from micom-dev/media (``data/carveme_skeleton.csv``,
    identical to the published ``media/western_diet_gut_carveme.qza``). Its ``flux`` column is
    already the diluted per-gDW-per-hour value and ``metabolite`` is already a BiGG id.
    """
    out: dict[str, float] = {}
    with open(SOURCES / "carveme_skeleton.csv", newline="") as handle:
        for row in csv.DictReader(handle):
            out[row["metabolite"].removesuffix("_m")] = max(
                float(row["flux"]), VMH_TRUNCATION_FLOOR
            )
    return out


# ── Model pool ────────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Pool:
    """What the bundled model pool can take up, and what it leaves open by default."""

    exchanges: dict[str, set[str]]      # BiGG metabolite -> models exposing an exchange
    background: dict[str, float]        # BiGG metabolite -> largest default-medium uptake bound

    def to_bigg(self) -> dict[str, str]:
        """``{agora_or_vmh_id: bigg_id}``. Raises if the ``__`` -> ``_`` collapse is ambiguous."""
        mapping: dict[str, str] = {}
        for met in sorted(self.exchanges):
            key = met.replace("__", "_")
            if key in mapping and mapping[key] != met:
                raise ValueError(
                    f"ambiguous AGORA/VMH -> BiGG collapse: {key!r} <- {mapping[key]!r} and "
                    f"{met!r}. The single-underscore bridge is not injective for this pool; the "
                    "mapping must be made explicit before an overlay can be built."
                )
            mapping[key] = met
        for source, target in EXPLICIT_ID_ALIASES.items():
            if target in self.exchanges:
                mapping[source] = target
        return mapping


def load_pool() -> Pool:
    """Read the bundled models once: exchange index + default-medium background."""
    import cobra

    exchanges: dict[str, set[str]] = {}
    background: dict[str, float] = {}
    for name in BUNDLED_MODELS:
        model = cobra.io.read_sbml_model(str(MODELS / f"{name}.xml"))
        for reaction in model.exchanges:
            exchanges.setdefault(_exchange_metabolite(str(reaction.id)), set()).add(name)
        for exchange, bound in dict(model.medium).items():
            met = _exchange_metabolite(str(exchange))
            background[met] = max(background.get(met, 0.0), float(bound))
    return Pool(exchanges=exchanges, background=background)


def _exchange_metabolite(exchange_id: str) -> str:
    name = exchange_id.removeprefix("EX_")
    head, sep, _tail = name.rpartition("_")
    return head if sep else name


# ── Overlay construction ──────────────────────────────────────────────────────────────────────

ORIGINS = frozenset(
    {
        "agora_table12",                    # AGORA Supp Table 12 x MICOM dilution
        "vmh_diet",                         # VMH mmol person-1 day-1, converted
        "micom_western",                    # MICOM's BiGG medium, verbatim
        "micom_western_inorganic",          # carbon-free top-up from MICOM's BiGG medium
        "micom_anaerobic_o2",               # the 0.001 oxygen term
        "assumption_trace_micronutrient",   # ni2
        "background_closure",               # 0.0 — "the environment does not supply this"
    }
)


@dataclass(frozen=True)
class Row:
    """One overlay row, with where its number came from."""

    bigg: str
    limit: float
    origin: str
    raw: float | None = None       # pre-conversion / pre-dilution source value
    factor: float | None = None    # f_colon (VMH) or MICOM dilution (AGORA)


@dataclass(frozen=True)
class Overlay:
    filename: str
    title: str
    rows: tuple[Row, ...]
    dropped: tuple[tuple[str, float], ...] = ()
    scale: float = 1.0

    def scaled(self, factor: float, filename: str, title: str) -> Overlay:
        """Uniform rescale of the *dietary* rows only.

        ``micom_anaerobic_o2`` and ``background_closure`` rows are held fixed: they are
        environmental boundary conditions, not dietary fluxes. Rescaling the diet does not make the
        colon less anoxic, and 0 x factor is 0 anyway.
        """
        held = {"micom_anaerobic_o2", "background_closure"}
        return Overlay(
            filename,
            title,
            tuple(
                Row(
                    r.bigg,
                    r.limit if r.origin in held else r.limit * factor,
                    r.origin,
                    r.raw,
                    r.factor,
                )
                for r in self.rows
            ),
            self.dropped,
            factor,
        )


def _finish(
    filename: str,
    title: str,
    rows: list[Row],
    dropped: list[tuple[str, float]],
    pool: Pool,
) -> Overlay:
    """Add the oxygen term, the trace micronutrient and the background closure block."""
    covered = {row.bigg for row in rows}
    if "o2" in pool.exchanges and "o2" not in covered:
        rows.append(Row("o2", MICOM_ANAEROBIC_O2, "micom_anaerobic_o2"))
        covered.add("o2")
    for bigg, flux in sorted(TRACE_MICRONUTRIENTS.items()):
        if bigg not in covered and bigg in pool.exchanges:
            rows.append(Row(bigg, flux, "assumption_trace_micronutrient"))
            covered.add(bigg)
    for bigg in sorted(pool.background):
        if bigg not in covered and bigg in pool.exchanges:
            rows.append(Row(bigg, 0.0, "background_closure"))
    return Overlay(filename, title, tuple(sorted(rows, key=lambda r: r.bigg)), tuple(dropped))


def build_agora_overlay(column: str, filename: str, title: str, *, pool: Pool) -> Overlay:
    """AGORA Supp Table 12 (already mmol gDW⁻¹ h⁻¹) x MICOM's small-intestinal dilution."""
    to_bigg = pool.to_bigg()
    dilutions = read_micom_dilutions()
    rows: list[Row] = []
    dropped: list[tuple[str, float]] = []
    for entry in read_agora_table12():
        agora_id = entry["metabolite_id"]
        published = float(entry[column])
        if agora_id in EXCLUDED_ELECTRON_ACCEPTORS:
            continue
        bigg = to_bigg.get(agora_id)
        if bigg is None:
            dropped.append((agora_id, published))
            continue
        lookup = MICOM_DILUTION_ALIASES.get(agora_id, agora_id)
        dilution = dilutions.get(lookup, (None, F_COLON_OTHER))[1]
        rows.append(Row(bigg, published * dilution, "agora_table12", published, dilution))
    return _finish(filename, title, rows, dropped, pool)


def build_vmh_overlay(source: str, filename: str, title: str, *, pool: Pool) -> Overlay:
    """Convert a VMH diet and top it up with the carbon-free part of MICOM's gut medium.

    ``v = D * f_colon / (B_gDW * 24)``. The VMH food database lists 91 food-derived metabolites but
    omits inorganic micronutrients that every defined bacterial medium contains, and it does not
    model the colonic gas phase. Rather than invent values, every **carbon-free** component of
    MICOM's published gut medium that the VMH diet does not cover is imported at MICOM's own
    published flux. The carbon-free test is objective and keeps every macronutrient — i.e. every
    part of the diet *contrast* — diet-derived.
    """
    host_absorbed = read_host_absorbed()
    to_bigg = pool.to_bigg()
    micom = read_micom_western()

    rows: list[Row] = []
    dropped: list[tuple[str, float]] = []
    covered: set[str] = set()
    for met, intake in read_vmh_diet(source):
        bigg = to_bigg.get(met)
        if bigg is None:
            dropped.append((met, intake))
            continue
        raw = intake if intake > 0 else VMH_TRUNCATION_FLOOR
        f_colon = F_COLON_ABSORBED if met in host_absorbed else F_COLON_OTHER
        limit = raw * f_colon / (BIOMASS_GDW * HOURS_PER_DAY)
        rows.append(Row(bigg, limit, "vmh_diet", raw, f_colon))
        covered.add(bigg)

    for bigg, flux in sorted(micom.items()):
        if bigg in covered or bigg not in pool.exchanges:
            continue
        if bigg not in CARBON_FREE or bigg in EXCLUDED_ELECTRON_ACCEPTORS or bigg == "o2":
            continue
        rows.append(Row(bigg, flux, "micom_western_inorganic"))
        covered.add(bigg)

    return _finish(filename, title, rows, dropped, pool)


def build_micom_overlay(filename: str, title: str, *, pool: Pool) -> Overlay:
    """MICOM's published western-diet gut medium, verbatim, restricted to the bundled pool."""
    rows: list[Row] = []
    dropped: list[tuple[str, float]] = []
    for bigg, flux in sorted(read_micom_western().items()):
        if bigg in pool.exchanges:
            rows.append(Row(bigg, flux, "micom_western"))
        else:
            dropped.append((bigg, flux))
    return _finish(filename, title, rows, dropped, pool)


OVERLAY_SPECS = (
    ("agora:western_diet", "gut_overlay_agora_western.csv",
     "AGORA Supp Table 12 Western diet x MICOM small-intestinal dilution"),
    ("agora:high_fiber_diet", "gut_overlay_agora_high_fiber.csv",
     "AGORA Supp Table 12 high fibre diet x MICOM small-intestinal dilution"),
    ("vmh:vmh_high_fat_low_carb.tsv", "gut_overlay_vmh_high_fat_low_carb.csv",
     "VMH 'High fat, low carb' diet, converted from mmol person-1 day-1"),
    ("vmh:vmh_high_fiber.tsv", "gut_overlay_vmh_high_fiber.csv",
     "VMH 'High fiber' diet, converted from mmol person-1 day-1"),
    ("micom", "gut_overlay_micom_western.csv",
     "MICOM western-diet gut medium (BiGG/CarveMe), verbatim"),
)


def build_all(pool: Pool) -> list[Overlay]:
    overlays: list[Overlay] = []
    for source, filename, title in OVERLAY_SPECS:
        if source == "micom":
            overlays.append(build_micom_overlay(filename, title, pool=pool))
            continue
        kind, name = source.split(":", 1)
        if kind == "agora":
            # No rescale: AGORA's published bounds already give a 3-member community ~0.14 h-1.
            # x100 would put it at 5.15 h-1, which is not biology.
            overlays.append(build_agora_overlay(name, filename, title, pool=pool))
            continue
        overlay = build_vmh_overlay(name, filename, title, pool=pool)
        overlays.append(overlay)
        overlays.append(
            overlay.scaled(
                FBA_RESCALE,
                filename.replace(".csv", "_x100.csv"),
                f"{title} — dietary rows uniformly rescaled x{FBA_RESCALE:g} "
                "(engineering, not literature)",
            )
        )
    return overlays


def render(overlay: Overlay) -> str:
    lines = ["exchange_id,uptake_limit"]
    for row in overlay.rows:
        lines.append(f"EX_{row.bigg}_m,{row.limit!r}")
    return "\n".join(lines) + "\n"


PROVENANCE_ROWS = PRESETS / "provenance_rows.csv"


def render_provenance(overlays: Iterable[Overlay]) -> str:
    """Row-level provenance for every shipped overlay, as a tracked CSV.

    One row per (overlay, exchange): where the number came from, the pre-conversion source value and
    the factor applied. This is the audit trail for the CSV overlays, which by format can only carry
    ``exchange_id,uptake_limit``.
    """
    lines = ["preset,exchange_id,uptake_limit,origin,source_value,factor,scale"]
    for overlay in overlays:
        for row in overlay.rows:
            raw = "" if row.raw is None else repr(row.raw)
            factor = "" if row.factor is None else repr(row.factor)
            lines.append(
                f"{overlay.filename},EX_{row.bigg}_m,{row.limit!r},{row.origin},"
                f"{raw},{factor},{overlay.scale!r}"
            )
    return "\n".join(lines) + "\n"


# ── Reporting ─────────────────────────────────────────────────────────────────────────────────

def fiber_coverage(pool: Pool) -> tuple[list[tuple[str, str, list[str]]], list[str]]:
    """AGORA's 24 fibre entries split into (reachable in this pool) and (unreachable)."""
    to_bigg = pool.to_bigg()
    entries = [row for row in read_agora_table12() if row["class"] == FIBER_CLASS]
    reachable: list[tuple[str, str, list[str]]] = []
    unreachable: list[str] = []
    for entry in entries:
        agora_id = entry["metabolite_id"]
        bigg = to_bigg.get(agora_id)
        models = sorted(pool.exchanges.get(bigg, ())) if bigg else []
        if models:
            reachable.append((agora_id, bigg or "", models))
        else:
            unreachable.append(agora_id)
    return reachable, unreachable


def _report(overlays: list[Overlay], pool: Pool) -> None:
    print(f"\nconstants: {CONSTANTS}")
    header = f"{'overlay':46s} {'rows':>5s} " + " ".join(f"{m:>10s}" for m in BUNDLED_MODELS)
    print("\n" + header)
    for overlay in overlays:
        counts = [
            sum(1 for r in overlay.rows if model in pool.exchanges[r.bigg])
            for model in BUNDLED_MODELS
        ]
        print(
            f"{overlay.filename:46s} {len(overlay.rows):5d} "
            + " ".join(f"{c:10d}" for c in counts)
        )

    reachable, unreachable = fiber_coverage(pool)
    total = len(reachable) + len(unreachable)
    print(f"\n── fibre coverage (AGORA Table 12 class=='fiber', {total} entries) ──")
    print(f"  {len(reachable)}/{total} have an exchange in ANY bundled model")
    for agora_id, bigg, models in reachable:
        print(f"    {agora_id:16s} -> EX_{bigg}_m   {models}")
    print("  unreachable: " + ", ".join(unreachable))
    print("  per-model: " + ", ".join(
        f"{model}={sum(1 for _a, _b, ms in reachable if model in ms)}/{total}"
        for model in BUNDLED_MODELS
    ))

    for overlay in overlays:
        if overlay.dropped and overlay.scale == 1.0:
            print(
                f"\n{overlay.filename}: {len(overlay.dropped)} source entries dropped "
                "(no exchange in any bundled model):\n  "
                + ", ".join(f"{m}={v:g}" for m, v in overlay.dropped)
            )


# ── CLI ───────────────────────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if a shipped overlay is stale")
    parser.add_argument("--report", action="store_true", help="print coverage tables")
    args = parser.parse_args(argv)

    pool = load_pool()
    overlays = build_all(pool)

    wanted = {overlay.filename: render(overlay) for overlay in overlays}
    wanted[PROVENANCE_ROWS.name] = render_provenance(overlays)
    stale = []
    for filename, text in wanted.items():
        path = PRESETS / filename
        if args.check:
            if not path.exists() or path.read_text() != text:
                stale.append(filename)
        else:
            path.write_text(text)
            print(f"wrote {path.relative_to(ROOT)}  ({text.count(chr(10)) - 1} rows)")

    if args.report:
        _report(overlays, pool)

    if stale:
        print("stale overlays (re-run without --check): " + ", ".join(stale), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
