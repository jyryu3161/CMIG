from __future__ import annotations

from cmig.gui.find import FindRow, build_table, find, footer_lines

ROWS = {
    "a": [("metabolite", "glc__D_e", "D-Glucose"), ("reaction", "GLCpts", "glucose transport"),
          ("reaction", "EX_glc__D_e", "D-Glucose exchange"), ("gene", "b2417", "crr")],
    "b": [("metabolite", "glc__D_e", "D-Glucose"), ("reaction", "PGI", "isomerase")],
}


def _table(**kw):  # type: ignore[no-untyped-def]
    return build_table(
        [("a", "a.xml"), ("glc_model", "glc_model.xml")], ROWS,
        [("preset:western_diet", "western_diet", ["EX_glc__D_m", "EX_fru_m"])],
        [("/p/runs/search-1", "search-1", "Search · glc__D_e · 10:31 · ok")], **kw,
    )


def test_short_queries_find_nothing() -> None:
    assert find(_table(), "g") == []


def test_groups_in_order_with_rank() -> None:
    groups = find(_table(), "glc__d_e")
    assert [g.title for g in groups] == ["Metabolites", "Reactions", "Runs"]
    metabolites = groups[0]
    assert [r.text for r in metabolites.rows] == ["glc__D_e · a — D-Glucose",
                                                  "glc__D_e · b — D-Glucose"]
    assert metabolites.rows[0] == FindRow("metabolite", "glc__D_e",
                                          "glc__D_e · a — D-Glucose", "a")
    reactions = groups[1]
    assert reactions.rows[0].key == "EX_glc__D_e"


def test_exact_then_prefix_then_substring() -> None:
    rows = {"m": [("reaction", "GLC", ""), ("reaction", "GLCpts", ""),
                  ("reaction", "EX_GLC", "")]}
    groups = find(build_table([], rows, [], []), "glc")
    assert [r.key for r in groups[0].rows] == ["GLC", "GLCpts", "EX_GLC"]


def test_models_media_and_runs() -> None:
    groups = {g.kind: g for g in find(_table(), "glc")}
    assert [r.key for r in groups["model"].rows] == ["glc_model"]
    assert groups["medium"].rows[0].key == "preset:western_diet"  # found by its exchange id
    assert groups["run"].rows[0].key == "/p/runs/search-1"


def test_find_caps_rows_and_reports_more() -> None:
    rows = {f"m{i:03d}": [("metabolite", "ac_e", "Acetate")] for i in range(20)}
    (group,) = find(build_table([], rows, [], []), "ac_e")
    assert len(group.rows) == 8 and group.more == 12


def test_search_table_dedupes_across_models() -> None:
    shared = [("metabolite", f"m{i}", f"name {i}") for i in range(1000)]
    table = build_table([], {f"model{j}": shared for j in range(300)}, [], [])
    assert len(table.entities) == 1000
    assert len(table.entities[("metabolite", "m5")][1]) == 300


def test_footer() -> None:
    assert footer_lines(_table(indexing=2, unreadable=1)) == [
        "2 models still indexing", "1 model could not be searched",
    ]
    assert footer_lines(_table()) == []
