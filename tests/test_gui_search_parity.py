"""GUI/CLI parity for the Search tab: per-target rows, advanced settings and defaults.

Every test records the argv the GUI hands to `cmig.cli.main.main`; the GUI itself never
computes anything, so the argv (and the SearchControl it installs) is the whole contract.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QApplication  # noqa: E402

from cmig.gui.app import build_main_window  # noqa: E402
from cmig.gui.builder import SearchView  # noqa: E402
from cmig.service import JobRunner, JobStatus  # noqa: E402


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _subparser(name: str) -> argparse.ArgumentParser:
    from cmig.cli.main import build_parser

    parser = build_parser()
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action.choices[name]
    raise AssertionError("no subcommands")


def _defaults(name: str) -> dict[str, Any]:
    return {a.dest: a.default for a in _subparser(name)._actions}


class _Recorder:
    def __init__(self, monkeypatch: pytest.MonkeyPatch, rc: int = 0) -> None:
        import cmig.cli.main

        self.calls: list[list[str]] = []
        self.controls: list[Any] = []
        self.rc = rc
        monkeypatch.setattr(cmig.cli.main, "main", self)

    def __call__(self, argv: list[str]) -> int:
        from cmig.service.search_service import current_search_control

        self.calls.append(list(argv))
        self.controls.append(current_search_control())
        out = Path(argv[argv.index("--out") + 1])
        out.mkdir(parents=True, exist_ok=True)
        name = {
            "search": "search_summary.json",
            "gene-ko-search": "gene_ko_summary.json",
            "strain-growth": "strain_growth_summary.json",
            "abundance-impact": "abundance_impact_summary.json",
        }[argv[0]]
        (out / name).write_text(json.dumps({"strategy": "exhaustive", "target": "ac",
                                            "top_ranked": [], "warnings": []}))
        return self.rc


@pytest.fixture
def window(tmp_path):
    _app()
    runner = JobRunner(max_workers=1)
    w = build_main_window(runner=runner)
    w.search_view.model_dir_input.setText(str(tmp_path))
    yield w
    w.close()
    runner.shutdown()


def _run(w, method: str = "run_search_fixture") -> str:
    jid = getattr(w, method)()
    if jid:
        w.runner.result(jid, timeout=10)
    return jid


def _value(argv: list[str], flag: str) -> str:
    return argv[argv.index(flag) + 1]


# ---------------------------------------------------------------------- target table


def test_target_table_replaces_comma_box_direction_and_references():
    _app()
    view = SearchView()
    for removed in ("targets_input", "direction_combo", "target_scales_input", "top_k_spin"):
        assert not hasattr(view, removed)
    assert view.target_table.columnCount() == 4
    headers = [view.target_table.horizontalHeaderItem(i).text() for i in range(4)]
    assert headers == ["Target", "Direction", "Weight", "Reference"]
    view.add_target_row("ac")
    combo = view.target_direction_combo(1)
    assert combo.currentText() == "max_secretion"
    assert [combo.itemText(i) for i in range(combo.count())] == [
        "max_secretion", "min_secretion", "max_uptake", "min_uptake"]
    assert view.target_rows()[1] == ("ac", "max_secretion", "1", "")
    view.close()


def test_single_row_uses_target_and_direction_only(window, monkeypatch):
    rec = _Recorder(monkeypatch)
    window.search_view.set_target_rows([("ac", "min_uptake", "2", "7")])
    assert _run(window)
    argv = rec.calls[0]
    assert _value(argv, "--target") == "ac"
    assert _value(argv, "--direction") == "min_uptake"
    for flag in ("--targets", "--target-directions", "--target-weights", "--target-scales",
                 "--multi-metric", "--pareto-resolution"):
        assert flag not in argv


def test_multi_row_argv_carries_every_row_in_order(window, monkeypatch):
    rec = _Recorder(monkeypatch)
    window.search_view.set_target_rows([
        ("ac", "max_secretion", "2", "10"), ("but", "min_secretion", "1.5", "5"),
    ])
    assert _run(window)
    argv = rec.calls[0]
    assert _value(argv, "--targets") == "ac,but"
    assert _value(argv, "--target-directions") == "max_secretion,min_secretion"
    assert _value(argv, "--target-weights") == "2,1.5"
    assert _value(argv, "--target-scales") == "ac=10,but=5"
    assert _value(argv, "--multi-metric") == "normalized_weighted"
    assert "--target" not in argv and "--direction" not in argv
    assert "--pareto-resolution" not in argv


def test_pareto_disables_weights_and_forwards_resolution(window, monkeypatch):
    rec = _Recorder(monkeypatch)
    view = window.search_view
    view.set_target_rows([("ac",), ("but",)])
    view.multi_metric_combo.setCurrentText("pareto")
    view.pareto_resolution_spin.setValue(7)
    assert not view.weight_note.isHidden()
    assert "Weights do not affect Pareto ranking" in view.weight_note.text()
    from PySide6.QtCore import Qt

    assert not (view.target_table.item(0, 2).flags() & Qt.ItemFlag.ItemIsEnabled)
    assert _run(window)
    argv = rec.calls[0]
    assert "--target-weights" not in argv
    assert _value(argv, "--pareto-resolution") == "7"
    assert "--target-scales" not in argv
    view.multi_metric_combo.setCurrentText("raw_sum")
    assert view.weight_note.isHidden()
    assert view.target_table.item(0, 2).flags() & Qt.ItemFlag.ItemIsEnabled


@pytest.mark.parametrize("rows", [
    [("",)],
    [],
    [("ac",), ("",)],
    [("ac",), ("ac",)],
    [("ac,but",)],
    [("ac", "max_secretion", "x"), ("but",)],
    [("ac", "max_secretion", ""), ("but",)],
    [("ac", "max_secretion", "nan"), ("but",)],
    [("ac", "max_secretion", "1", "abc"), ("but", "max_secretion", "1", "5")],
    [("ac", "max_secretion", "1", "10"), ("but",)],
    [("ac", "max_secretion", "1", "0"), ("but", "max_secretion", "1", "5")],
    [("ac", "max_secretion", "1", "-1"), ("but", "max_secretion", "1", "5")],
    [("ac", "max_secretion", "1", "inf"), ("but", "max_secretion", "1", "5")],
])
def test_bad_target_rows_are_refused_before_running(window, monkeypatch, rows):
    rec = _Recorder(monkeypatch)
    window.search_view.set_target_rows(rows)
    assert window.run_search_fixture() == ""
    assert rec.calls == []
    assert window.search_view.status.text().strip()


def test_preset_fills_editable_rows_and_argv_uses_rows(window, monkeypatch):
    from cmig.core.targets import preset_targets

    rec = _Recorder(monkeypatch)
    view = window.search_view
    index = view.target_preset_combo.findData("scfa")
    assert index > 0
    view.target_preset_combo.setCurrentIndex(index)
    view.target_preset_combo.activated.emit(index)
    expected = preset_targets("scfa")
    assert [row[0] for row in view.target_rows()] == expected
    assert {row[1] for row in view.target_rows()} == {"max_secretion"}
    view.target_table.item(0, 0).setText("ac")  # still an ordinary editable row
    view.target_direction_combo(1).setCurrentText("min_secretion")
    assert _run(window)
    argv = rec.calls[0]
    assert "--target-preset" not in argv
    assert _value(argv, "--targets").split(",")[0] == "ac"
    assert _value(argv, "--target-directions").split(",")[1] == "min_secretion"


# ---------------------------------------------------------------- advanced settings


def test_advanced_settings_collapsed_by_default():
    _app()
    view = SearchView()
    assert view.advanced_box.isHidden()
    view.advanced_toggle.setChecked(True)
    assert not view.advanced_box.isHidden()
    assert "Search only" in view.advanced_toggle.text()
    view.close()


GA_FLAGS = ("--ga-pop-size", "--ga-generations", "--ga-mutation-rate",
            "--ga-immigrant-fraction", "--ga-tournament-k", "--ga-elitism",
            "--ga-local-search-fraction")


@pytest.mark.parametrize("strategy", ["auto", "exhaustive", "random", "ga"])
def test_strategy_options_only_when_applicable(window, monkeypatch, strategy):
    rec = _Recorder(monkeypatch)
    view = window.search_view
    view.strategy_combo.setCurrentText(strategy)
    view.exhaustive_max_spin.setValue(55)
    view.n_samples_spin.setValue(77)
    view.ga_pop_size_spin.setValue(12)
    view.ga_budget_spin.setValue(300)
    view.ga_patience_spin.setValue(4)
    view.ga_restart_after_spin.setValue(6)
    view.ga_preserve_common_check.setChecked(True)
    view.set_target_rows([("ac", "max_secretion", "2", "1"), ("but", "min_uptake", "1", "3")])
    view.medium_input.setText("m.csv")
    view.allow_unknown_medium_check.setChecked(True)
    assert _run(window)
    argv = rec.calls[0]
    from cmig.cli.main import build_parser

    build_parser().parse_args(argv)  # the GUI argv is a valid `cmig search` request
    assert ("--exhaustive-max" in argv) == (strategy == "auto")
    assert ("--n-samples" in argv) == (strategy == "random")
    ga = strategy in ("auto", "ga")
    for flag in GA_FLAGS + ("--ga-max-evaluations", "--ga-patience", "--ga-restart-after",
                            "--ga-preserve-common"):
        assert (flag in argv) == ga, flag
    if strategy == "auto":
        assert _value(argv, "--exhaustive-max") == "55"
    if strategy == "random":
        assert _value(argv, "--n-samples") == "77"
    if ga:
        assert _value(argv, "--ga-pop-size") == "12"
        assert _value(argv, "--ga-max-evaluations") == "300"
        assert _value(argv, "--ga-patience") == "4"
        assert _value(argv, "--ga-restart-after") == "6"


def test_optional_ga_limits_have_an_off_value(window, monkeypatch):
    rec = _Recorder(monkeypatch)
    view = window.search_view
    view.strategy_combo.setCurrentText("ga")
    for spin in (view.ga_budget_spin, view.ga_patience_spin, view.ga_restart_after_spin):
        spin.setValue(0)
        assert spin.specialValueText()
    assert _run(window)
    argv = rec.calls[0]
    for flag in ("--ga-max-evaluations", "--ga-patience", "--ga-restart-after",
                 "--ga-preserve-common"):
        assert flag not in argv
    assert "--ga-pop-size" in argv


def test_taxonomy_and_recursive_are_search_only(window, monkeypatch, tmp_path):
    rec = _Recorder(monkeypatch)
    view = window.search_view
    view.recursive_check.setChecked(True)
    assert _run(window)
    assert "--recursive" in rec.calls[-1]
    assert _value(rec.calls[-1], "--model-dir") == str(tmp_path)
    taxonomy = tmp_path / "pool.csv"
    view.model_source_combo.setCurrentIndex(view.model_source_combo.findData("taxonomy"))
    assert not view.recursive_check.isEnabled()
    view.taxonomy_input.setText("")
    assert window.run_search_fixture() == ""
    view.taxonomy_input.setText(str(taxonomy))
    assert _run(window)
    argv = rec.calls[-1]
    assert _value(argv, "--taxonomy") == str(taxonomy)
    assert "--model-dir" not in argv and "--recursive" not in argv
    # Gene KO / Strain Growth / Ratio never use the taxonomy in place of the model folder.
    view.model_dir_input.setText("")
    view.ko_members_input.setText("a,b")
    view.growth_member_input.setText("a")
    n = len(rec.calls)
    assert window.run_gene_ko_search() == ""
    assert window.run_strain_growth_report() == ""
    assert window.run_abundance_impact() == ""
    assert len(rec.calls) == n


def test_solver_threads_reach_argv_and_search_control(window, monkeypatch):
    rec = _Recorder(monkeypatch)
    window.search_view.solver_threads_spin.setValue(4)
    window.search_view.workers_spin.setValue(2)
    assert _run(window)
    assert _value(rec.calls[0], "--solver-threads") == "4"
    control = rec.controls[0]
    assert control is not None
    assert control.solver_threads == 4
    assert control.workers == 2


def test_medium_mode_exact_merge_and_unknown(window, monkeypatch, tmp_path):
    rec = _Recorder(monkeypatch)
    view = window.search_view
    assert view.medium_mode_combo.currentData() == "exact"
    # no medium file: neither mode nor unknown flag applies
    view.allow_unknown_medium_check.setChecked(True)
    assert "not applied" in view.medium_mode_note.text()
    assert _run(window)
    argv = rec.calls[-1]
    for flag in ("--medium", "--exact-medium", "--allow-unknown-medium"):
        assert flag not in argv
    medium = str(tmp_path / "medium.csv")
    view.medium_input.setText(medium)
    view.allow_unknown_medium_check.setChecked(False)
    assert _run(window)
    argv = rec.calls[-1]
    assert _value(argv, "--medium") == medium and "--exact-medium" in argv
    assert "--allow-unknown-medium" not in argv
    view.medium_mode_combo.setCurrentIndex(view.medium_mode_combo.findData("merge"))
    assert "stay at the model defaults" in view.medium_mode_note.text()
    assert "use exact for reported results" in view.medium_mode_note.text()
    view.allow_unknown_medium_check.setChecked(True)
    assert "degraded" in view.allow_unknown_note.text()
    assert not view.allow_unknown_note.isHidden()
    assert _run(window)
    argv = rec.calls[-1]
    assert _value(argv, "--medium") == medium
    assert "--exact-medium" not in argv
    assert "--allow-unknown-medium" in argv
    # other workflows keep exact medium and never inherit merge/unknown
    view.set_target_rows([("ac",)])
    view.ko_members_input.setText("a,b")
    view.growth_member_input.setText("a")
    for method in ("run_gene_ko_search", "run_strain_growth_report", "run_abundance_impact"):
        assert _run(window, method)
        argv = rec.calls[-1]
        assert "--exact-medium" in argv, method
        assert "--allow-unknown-medium" not in argv, method


# ------------------------------------------------------------------------- defaults


def test_gui_search_defaults_equal_cli_parser_defaults():
    from cmig.core.search_ga import GAConfig

    _app()
    view = SearchView()
    d = _defaults("search")
    ga = GAConfig()
    assert view.target_rows() == [(d["target"], d["direction"], "1", "")]
    assert d["target_weights"] is None and d["target_scales"] is None
    assert view.strategy_combo.currentText() == d["strategy"]
    assert view.multi_metric_combo.currentText() == d["multi_metric"] == "normalized_weighted"
    assert view.min_size_spin.value() == d["min_size"]
    assert view.max_size_spin.value() == d["max_size"]
    assert view.search_top_k_spin.value() == d["top_k"] == 10
    assert view.seed_spin.value() == d["seed"]
    assert view.workers_spin.value() == d["workers"]
    assert view.solver_threads_spin.value() == d["solver_threads"]
    assert view.growth_fraction_spin.value() == pytest.approx(d["growth_fraction"])
    assert view.min_member_growth_spin.value() == pytest.approx(d["min_member_growth"])
    assert view.min_community_growth_spin.value() == pytest.approx(d["min_community_growth"])
    assert view.validation_top_spin.value() == d["validate_top"]
    assert d["solve_timeout"] is None and view.solve_timeout_spin.value() == 0
    assert view.exhaustive_max_spin.value() == d["exhaustive_max"]
    assert view.n_samples_spin.value() == d["n_samples"]
    assert view.ga_pop_size_spin.value() == d["ga_pop_size"] == ga.pop_size
    assert view.ga_generations_spin.value() == d["ga_generations"] == ga.generations
    assert view.ga_mutation_rate_spin.value() == pytest.approx(d["ga_mutation_rate"])
    assert view.ga_immigrant_fraction_spin.value() == pytest.approx(d["ga_immigrant_fraction"])
    assert view.ga_tournament_k_spin.value() == d["ga_tournament_k"]
    assert view.ga_elitism_spin.value() == d["ga_elitism"]
    assert d["ga_max_evaluations"] is None and view.ga_budget_spin.value() == 0
    assert d["ga_patience"] is None and view.ga_patience_spin.value() == 0
    assert d["ga_restart_after"] is None and view.ga_restart_after_spin.value() == 0
    assert view.ga_local_search_fraction_spin.value() == pytest.approx(
        d["ga_local_search_fraction"])
    assert view.ga_preserve_common_check.isChecked() is d["ga_preserve_common"]
    assert view.pareto_resolution_spin.value() == d["pareto_resolution"]
    assert view.recursive_check.isChecked() is d["recursive"]
    assert view.robustness_check.isChecked() is d["robustness_fva"]
    assert view.allow_unknown_medium_check.isChecked() is d["allow_unknown_medium"]
    assert view.resume_check.isChecked() is d["resume"]
    assert d["checkpoint"] is None and view.checkpoint_input.text() == ""
    assert d["medium"] is None and view.medium_input.text() == ""
    assert view.model_source_combo.currentData() == "model_dir"
    # exact medium is the GUI default by design (spec: exact is the default).
    assert view.medium_mode_combo.currentData() == "exact"
    view.close()


def test_search_top_k_bounds():
    _app()
    view = SearchView()
    assert view.search_top_k_spin.minimum() == 1
    assert view.search_top_k_spin.maximum() > 100_000
    view.search_top_k_spin.setValue(0)
    assert view.search_top_k_spin.value() == 1
    view.close()


def test_gene_ko_top_k_is_separate_default_twenty(window, monkeypatch):
    rec = _Recorder(monkeypatch)
    view = window.search_view
    assert view.ko_top_k_spin.value() == _defaults("gene-ko-search")["top_k"] == 20
    view.set_target_rows([("ac", "min_uptake")])
    view.ko_members_input.setText("a,b")
    view.search_top_k_spin.setValue(3)
    medium = "m.csv"
    view.medium_input.setText(medium)
    view.medium_mode_combo.setCurrentIndex(view.medium_mode_combo.findData("merge"))
    assert _run(window, "run_gene_ko_search")
    argv = rec.calls[-1]
    assert _value(argv, "--top-k") == "20"
    assert _value(argv, "--direction") == "min_uptake"
    assert _value(argv, "--target") == "ac"
    assert "--exact-medium" in argv
    assert "ko_top_k" in SearchView.REQUEST_FIELDS["gene_ko"]
    assert "top_k" not in SearchView.REQUEST_FIELDS["gene_ko"]
    assert "ko_top_k" not in SearchView.REQUEST_FIELDS["search"]


@pytest.mark.parametrize("kind", ["search", "gene_ko"])
def test_top_k_invalidation_is_scoped(tmp_path, kind):
    _app()
    view = SearchView()
    view.load_summary({"top_ranked": [], "strategy": kind}, run_dir=tmp_path,
                      workflow_kind=kind, executed_request=view.request_fields(kind))
    other, own = ((view.ko_top_k_spin, view.search_top_k_spin) if kind == "search"
                  else (view.search_top_k_spin, view.ko_top_k_spin))
    other.setValue(other.value() + 1)
    assert view.current_run_dir == tmp_path.resolve()
    own.setValue(own.value() + 1)
    assert view.current_run_dir is None
    view.close()


def test_new_search_settings_invalidate_search_result(tmp_path):
    _app()
    view = SearchView()
    edits = [
        lambda: view.target_direction_combo(0).setCurrentText("min_uptake"),
        lambda: view.target_table.item(0, 2).setText("3"),
        lambda: view.target_table.item(0, 3).setText("4"),
        lambda: view.add_target_row("ac"),
        lambda: view.solver_threads_spin.setValue(3),
        lambda: view.ga_patience_spin.setValue(2),
        lambda: view.medium_mode_combo.setCurrentIndex(1),
        lambda: view.allow_unknown_medium_check.setChecked(True),
        lambda: view.recursive_check.setChecked(True),
        lambda: view.taxonomy_input.setText("t.csv"),
        lambda: view.pareto_resolution_spin.setValue(9),
        lambda: view.exhaustive_max_spin.setValue(9),
        lambda: view.n_samples_spin.setValue(9),
        lambda: view.ga_preserve_common_check.setChecked(True),
    ]
    for edit in edits:
        view.set_target_rows([("but",)])
        view.load_summary({"top_ranked": [], "strategy": "x"}, run_dir=tmp_path,
                          workflow_kind="search",
                          executed_request=view.request_fields("search"))
        assert view.current_run_dir is not None
        edit()
        assert view.current_run_dir is None
    # Search-only settings do not invalidate a Gene KO result.
    view.set_target_rows([("but",)])
    view.load_summary({"top_ranked": [], "strategy": "x"}, run_dir=tmp_path,
                      workflow_kind="gene_ko", executed_request=view.request_fields("gene_ko"))
    view.solver_threads_spin.setValue(5)
    view.medium_mode_combo.setCurrentIndex(0)
    view.allow_unknown_medium_check.setChecked(False)
    assert view.current_run_dir == tmp_path.resolve()
    view.close()


# -------------------------------------------------------------- one-row workflows


@pytest.mark.parametrize("method", ["run_gene_ko_search", "run_abundance_impact"])
def test_gene_ko_and_ratio_need_exactly_one_row(window, monkeypatch, method):
    rec = _Recorder(monkeypatch)
    view = window.search_view
    view.ko_members_input.setText("a,b")
    view.growth_member_input.setText("a")
    view.set_target_rows([("ac",), ("but",)])
    assert getattr(window, method)() == ""
    assert view.status.text() == "Gene KO and Ratio Impact need exactly one target row."
    view.set_target_rows([("",)])
    assert getattr(window, method)() == ""
    assert rec.calls == []
    view.set_target_rows([("succ", "max_uptake")])
    assert _run(window, method)
    assert _value(rec.calls[-1], "--target") == "succ"


# ------------------------------------------------------------------ warnings / errors


def test_normalized_without_references_warns_but_runs(window, monkeypatch):
    rec = _Recorder(monkeypatch)
    view = window.search_view
    text = ("If the search runs as GA or random, normalized_weighted needs a Reference for "
            "every target.")
    view.set_target_rows([("ac",), ("but",)])
    for strategy in ("auto", "ga", "random"):
        view.strategy_combo.setCurrentText(strategy)
        assert text in view.reference_warning()
        assert not view.reference_warning_label.isHidden()
    jid = window.run_search_fixture()
    assert jid
    assert text in view.status.text()
    window.runner.result(jid, timeout=10)
    assert rec.calls
    view.strategy_combo.setCurrentText("exhaustive")
    assert view.reference_warning() == ""
    assert view.reference_warning_label.isHidden()
    view.strategy_combo.setCurrentText("ga")
    view.set_target_rows([("ac", "max_secretion", "1", "2"), ("but", "max_secretion", "1", "3")])
    assert view.reference_warning() == ""
    view.set_target_rows([("ac",), ("but",)])
    view.multi_metric_combo.setCurrentText("raw_sum")
    assert view.reference_warning() == ""
    view.multi_metric_combo.setCurrentText("normalized_weighted")
    view.set_target_rows([("ac",)])
    assert view.reference_warning() == ""


def test_rc2_shows_this_jobs_cli_cause_without_other_threads_output(monkeypatch, tmp_path):
    import cmig.cli.main
    from cmig.service.jobrunner import JobFailed

    cause = "normalized_weighted GA search needs --target-scales for every target"
    noise = "UNRELATED OUTPUT FROM ANOTHER THREAD"

    def fake_main(argv):
        def other() -> None:
            print(noise, file=sys.stderr)

        worker = threading.Thread(target=other)
        worker.start()
        worker.join()
        print(cause, file=sys.stderr)
        return 2

    monkeypatch.setattr(cmig.cli.main, "main", fake_main)
    _app()
    runner = JobRunner(max_workers=1)
    w = build_main_window(runner=runner)
    w.search_view.model_dir_input.setText(str(tmp_path))
    w.search_view.set_target_rows([("ac",), ("but",)])
    jid = w.run_search_fixture()
    with pytest.raises(JobFailed):
        runner.result(jid, timeout=10)
    w._poll_completed_jobs()
    assert runner.poll(jid).status is JobStatus.FAILED
    status = w.search_view.status.text()
    details = w.search_view.details.toPlainText()
    assert "search failed (rc=2)" in status
    assert cause in status
    assert cause in details
    assert noise not in status and noise not in details
    assert cause in (runner.poll(jid).error or "")
    w.close()
    runner.shutdown()


# ------------------------------------------------------------------ ko / geometry


def test_korean_mode_new_paths_do_not_raise(monkeypatch, tmp_path):
    _app()
    rec = _Recorder(monkeypatch)
    runner = JobRunner(max_workers=1)
    w = build_main_window(runner=runner, lang="ko")
    view = w.search_view
    view.model_dir_input.setText(str(tmp_path))
    view.advanced_toggle.setChecked(True)
    view.set_target_rows([("ac",), ("ac",)])
    assert w.run_search_fixture() == ""
    view.set_target_rows([("ac",), ("but",)])
    view.ko_members_input.setText("a,b")
    assert w.run_gene_ko_search() == ""
    jid = w.run_search_fixture()
    assert jid
    runner.result(jid, timeout=10)
    w._poll_completed_jobs()
    assert rec.calls
    w.close()
    runner.shutdown()


def test_window_fits_with_advanced_settings_expanded():
    app = _app()
    for lang in ("en", "ko"):
        window = build_main_window(lang=lang)
        window.search_view.advanced_toggle.setChecked(True)
        window.search_view.set_target_rows([("ac",), ("but",), ("succ",), ("ppa",)])
        window.search_view.multi_metric_combo.setCurrentText("pareto")
        window.search_view.medium_input.setText("x" * 200)
        window.search_view.medium_mode_combo.setCurrentIndex(1)
        window.search_view.allow_unknown_medium_check.setChecked(True)
        window.tabs.setCurrentWidget(window.search_view)
        for size in ((1280, 800), (1500, 950)):
            window.resize(*size)
            window.show()
            app.processEvents()
            assert (window.width(), window.height()) == size
        window.close()
