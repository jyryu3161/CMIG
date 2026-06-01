"""Test session 공통 설정.

Design Ref(hardening): track-A — Qt offscreen 강제. Qt 가 import 되기 전에
QT_QPA_PLATFORM=offscreen 과 QtWebEngine Chromium 플래그를 설정해야 하므로
conftest import 시점(=가장 이른 시점)에 환경변수를 박아둔다. 디스플레이/ GPU 없는
헤드리스 CI 에서도 위젯이 실제로 실행되도록 한다(시각 QA 아님 — 실행+산출 증거).
"""

import os

# Qt offscreen platform — display 없이 위젯 생성/렌더.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# QtWebEngine(Chromium) 헤드리스: GPU/sandbox 비활성 (offscreen 렌더 안정화).
os.environ.setdefault(
    "QTWEBENGINE_CHROMIUM_FLAGS",
    "--no-sandbox --disable-gpu --disable-software-rasterizer",
)
