"""Set each analysis' inputs through the GUI and start it; the argv parity test records argv.

Only this file changes when a page moves (phase 2): the expected argv in
test_phase2_argv_parity.py must not.
"""

from __future__ import annotations

from typing import Any


def search_default(w: Any) -> str:
    v = w.search_view
    v.model_picker.set_selected(["a", "b"])
    v.medium_picker.set_ref("preset:western_diet")
    return w.run_search_fixture()


def search_advanced(w: Any) -> str:
    v = w.search_view
    v.model_picker.set_selected(["a", "b", "host"])
    v.set_target_rows([["but", "max_secretion", "1", "2"], ["ac", "max_secretion", "2", "3"]])
    v.multi_metric_combo.setCurrentText("raw_sum")
    v.min_size_spin.setValue(1)
    v.max_size_spin.setValue(3)
    v.strategy_combo.setCurrentText("exhaustive")
    v.search_top_k_spin.setValue(5)
    v.seed_spin.setValue(7)
    v.growth_fraction_spin.setValue(0.25)
    v.min_member_growth_spin.setValue(0.01)
    v.validation_top_spin.setValue(2)
    return w.run_search_fixture()


def gene_ko(w: Any) -> str:
    v = w.gene_ko_page
    v.model_picker.set_selected(["a", "b", "host"])
    v.medium_picker.set_ref("preset:high_fiber")
    v.target_input.setText("ac")
    v.direction_combo.setCurrentText("min_uptake")
    v.members_picker.set_selected(["a", "b"])
    v.member_combo.setCurrentText("a")
    v.max_genes_spin.setValue(10)
    v.top_k_spin.setValue(5)
    v.growth_fraction_spin.setValue(0.3)
    return w.run_gene_ko_search()


def strain_growth(w: Any) -> str:
    v = w.strain_growth_page
    v.model_picker.set_selected(["a", "b"])
    v.medium_picker.set_ref("preset:high_fiber")
    v.cooperative_tradeoff_spin.setValue(0.4)
    return w.run_strain_growth_report()


def ratio_impact(w: Any) -> str:
    v = w.ratio_impact_page
    v.model_picker.set_selected(["a", "b"])
    v.target_input.setText("but")
    v.member_combo.setCurrentText("b")
    v.fractions_input.setText("0.2,0.8")
    v.cooperative_tradeoff_spin.setValue(0.6)
    return w.run_abundance_impact()


def community(w: Any) -> str:
    v = w.community_builder
    v.model_picker.set_selected(["a", "b"])
    v.set_abundance("a", 0.25)
    v.assume_bigg_check.setChecked(True)
    v.f_slider.setValue(30)
    return w.run_community_solve()


def _host_common(v: Any) -> None:
    v.host_picker.set_selected(["host"])
    v.model_picker.set_selected(["a", "b"])
    v.host_medium_picker.set_ref("preset:western_diet")
    v.biomass_basis_kind_combo.setCurrentText("measured")
    v.biomass_basis_source_input.setText("lab record 12")
    v.microbial_biomass_spin.setValue(0.5)
    v.host_biomass_spin.setValue(10.0)
    v.tradeoff_spin.setValue(0.7)
    v.keep_host_uptake_check.setChecked(True)


def host(w: Any) -> str:
    _host_common(w.host_view)
    return w.run_host_microbe_bigg()


def host_search(w: Any) -> str:
    v = w.host_view
    _host_common(v)
    v.search_target_input.setText("but")
    v.search_metric_combo.setCurrentText("objective_value")
    v.min_size_spin.setValue(1)
    v.max_size_spin.setValue(2)
    return w.run_host_search_bigg()


def dfba(w: Any) -> str:
    v = w.dynamics_view
    v.model_picker.set_selected(["a"])
    v.initial_input.setText("EX_glc__D_e=5,EX_o2_e=10")
    v.t_end_spin.setValue(2.0)
    v.dt_spin.setValue(0.05)
    v.biomass_spin.setValue(0.02)
    v.close_untracked_check.setChecked(True)
    return w.run_dfba()


def spatial(w: Any) -> str:
    v = w.dynamics_view
    v.spatial_metabolite_input.setText("EX_ac_e")
    v.grid_size_spin.setValue(16)
    v.steps_spin.setValue(10)
    v.spatial_dt_spin.setValue(0.2)
    v.diffusion_spin.setValue(0.3)
    v.source_combo.setCurrentText("top")
    v.sink_combo.setCurrentText("bottom")
    return w.run_spatial_preview()


def medium_growth(w: Any) -> str:
    v = w.medium_editor
    v.model_picker.set_selected(["a", "b"])
    v.clear_rows()
    v.add_row("EX_glc__D_e", 10.0)
    v.exact_medium_check.setChecked(True)
    v.assume_bigg_check.setChecked(True)
    return w.run_medium_growth_check()


def minimal_medium(w: Any) -> str:
    v = w.medium_editor
    v.single_model_picker.set_selected(["a"])
    v.clear_rows()
    v.add_row("EX_glc__D_e", 10.0)
    v.assume_bigg_check.setChecked(True)
    v.min_growth_spin.setValue(0.1)
    return w.run_minimal_medium()


def sweep(w: Any) -> str:
    v = w.sweep_view
    v.model_picker.set_selected(["a", "b"])
    v.tradeoff_fs_input.setText("0.2,0.4")
    v.assume_bigg_check.setChecked(True)
    v.fva_check.setChecked(True)
    return w.run_sweep()


DRIVERS = {
    "search_default": search_default,
    "search_advanced": search_advanced,
    "gene_ko": gene_ko,
    "strain_growth": strain_growth,
    "ratio_impact": ratio_impact,
    "community": community,
    "host": host,
    "host_search": host_search,
    "dfba": dfba,
    "spatial": spatial,
    "medium_growth": medium_growth,
    "minimal_medium": minimal_medium,
    "sweep": sweep,
}
