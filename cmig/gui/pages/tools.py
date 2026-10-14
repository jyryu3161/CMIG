"""Tools (Medium Editor, Sweep, Constraint Sandbox, Compare Runs) in the common page frame.

The tools keep their own controls and buttons; the frame gives them the same title, place
and results area as every analysis page.
"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from cmig.gui.analysis_page import AnalysisPage


class ToolPage(AnalysisPage):
    def __init__(self, title: str, description: str, content: QWidget, *,
                 results: bool) -> None:
        super().__init__(title, description, cancel=False)
        self.content = content
        self.inputs.addWidget(content)
        self.run_btn.setVisible(False)
        self.advanced.setVisible(False)
        self.results.setVisible(results)
