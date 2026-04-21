from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Iterable

_REPO_ROOT = Path(__file__).resolve().parents[1]
_LOCAL_QT_LIB_DIR = Path("/tmp/tragedy-qt-libs/usr/lib/x86_64-linux-gnu")


def _configure_qt_platform_before_import() -> None:
    """Prefer XCB over Wayland before Qt is imported.

    Qt/Wayland can abort the whole process on strict protocol size-state
    mismatches. In a desktop session that also exposes X11/XWayland, XCB is
    more tolerant and is already the platform used by `scripts/run_ui_linux.sh`.
    """
    if not sys.platform.startswith("linux"):
        return
    if os.environ.get("QT_QPA_PLATFORM"):
        return
    if not os.environ.get("WAYLAND_DISPLAY") or not os.environ.get("DISPLAY"):
        return

    os.environ["QT_QPA_PLATFORM"] = "xcb"

    if not _LOCAL_QT_LIB_DIR.is_dir():
        return
    if os.environ.get("TRAGEDY_QT_XCB_REEXEC") == "1":
        return

    current_ld_path = os.environ.get("LD_LIBRARY_PATH", "")
    lib_dir_text = str(_LOCAL_QT_LIB_DIR)
    if lib_dir_text in current_ld_path.split(":"):
        return

    env = dict(os.environ)
    env["TRAGEDY_QT_XCB_REEXEC"] = "1"
    env["LD_LIBRARY_PATH"] = (
        f"{lib_dir_text}:{current_ld_path}"
        if current_ld_path
        else lib_dir_text
    )
    os.execvpe(sys.executable, [sys.executable, *sys.argv], env)


_configure_qt_platform_before_import()

from ui.main_window import MainWindow

try:  # pragma: no cover - runtime entry
    from PySide6.QtGui import QFont, QFontDatabase
    from PySide6.QtWidgets import QApplication
except Exception:  # pragma: no cover
    QApplication = None  # type: ignore[assignment]
    QFont = None  # type: ignore[assignment]
    QFontDatabase = None  # type: ignore[assignment]


def _pick_first_installed_family(candidates: Iterable[str]) -> str | None:
    if QFontDatabase is None:
        return None
    families = {family.lower(): family for family in QFontDatabase.families()}
    for candidate in candidates:
        matched = families.get(candidate.lower())
        if matched is not None:
            return matched
    return None


def _load_local_fonts() -> None:
    if QFontDatabase is None:
        return

    fonts_dir = _REPO_ROOT / ".local_fonts"
    if not fonts_dir.exists():
        return

    for font_path in sorted(fonts_dir.rglob("*")):
        if font_path.suffix.lower() not in {".ttf", ".otf", ".ttc"}:
            continue
        QFontDatabase.addApplicationFont(str(font_path))


def _configure_app_font(app: QApplication) -> None:
    if QFont is None or QFontDatabase is None:
        return

    _load_local_fonts()

    preferred_families = [
        "Noto Sans CJK SC",
        "Noto Sans CJK JP",
        "Noto Sans CJK KR",
        "Noto Sans CJK TC",
        "Noto Sans SC",
        "Noto Sans TC",
        "Source Han Sans SC",
        "Source Han Sans CN",
        "Microsoft YaHei",
        "PingFang SC",
        "WenQuanYi Zen Hei",
        "SimHei",
        "Arial Unicode MS",
    ]
    fallback_english_families = [
        "Ubuntu Sans",
        "Ubuntu",
        "Sans Serif",
    ]

    selected = _pick_first_installed_family(preferred_families)
    if selected is None:
        english_fallback = _pick_first_installed_family(fallback_english_families)
        if english_fallback is not None:
            app.setFont(QFont(english_fallback, 11))
        print(
            "Warning: no Chinese UI font detected. "
            "Install a CJK font such as `fonts-noto-cjk` to avoid tofu squares.",
            file=sys.stderr,
        )
        return

    app.setFont(QFont(selected, 11))


def _fit_window_to_screen(window: MainWindow, app: QApplication) -> None:
    screen = app.primaryScreen()
    if screen is None:
        return
    available = screen.availableGeometry()
    width = min(window.width(), max(800, int(available.width() * 0.9)))
    height = min(window.height(), max(600, int(available.height() * 0.85)))
    window.resize(width, height)


def run() -> int:
    if QApplication is None:
        raise RuntimeError("PySide6 is not installed")
    app = QApplication(sys.argv)
    _configure_app_font(app)
    window = MainWindow()
    _fit_window_to_screen(window, app)
    window.show()
    return app.exec()
