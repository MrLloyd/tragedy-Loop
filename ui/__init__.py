from ui.main_window import MainWindow

__all__ = ["MainWindow", "run"]


def run() -> int:
    from ui.app import run as _run

    return _run()
