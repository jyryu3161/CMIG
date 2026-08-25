"""R Render Service (별도 프로세스, GPL 격리). Design Ref: §9 / FR-2.5.

CMIG(Apache/own) 는 R 을 import/link 하지 않고 subprocess 로만 호출한다(§2 라이선스 격리).
"""

from cmig.render.client import FigureSpec, RenderClient, RenderError, render_profile
from cmig.render.composer import FigureComposer, PanelSpec, render_panels_from_run

__all__ = [
    "FigureComposer",
    "FigureSpec",
    "PanelSpec",
    "RenderClient",
    "RenderError",
    "render_panels_from_run",
    "render_profile",
]
