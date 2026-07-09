"""CMIG desktop GUI launcher.

Two equivalent entry points resolve to :func:`main`:

- console script ``cmig-gui`` (see ``[project.scripts]`` in ``pyproject.toml``)
- ``python -m cmig.gui`` / ``uv run cmig gui``

Keeps PySide6 imports lazy so the pure-logic core and the CLI stay importable
without the ``gui`` extra installed.
"""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    """Build and run the CMIG main window. Returns the Qt event-loop exit code."""
    parser = argparse.ArgumentParser(
        prog="cmig-gui", description="Launch the CMIG desktop GUI."
    )
    parser.add_argument(
        "--lang", default="en", choices=["en", "ko"], help="UI language (default: en)"
    )
    parser.add_argument("--width", type=int, default=1500, help="initial window width")
    parser.add_argument("--height", type=int, default=950, help="initial window height")
    args = parser.parse_args(argv)

    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print(
            "CMIG GUI requires the gui extra: uv sync --extra gui --extra engine",
            file=sys.stderr,
        )
        return 2

    from cmig.gui.app import build_main_window

    app = QApplication.instance() or QApplication(sys.argv[:1])
    window = build_main_window(lang=args.lang)
    window.resize(args.width, args.height)
    window.show()
    return int(app.exec())


if __name__ == "__main__":
    raise SystemExit(main())
