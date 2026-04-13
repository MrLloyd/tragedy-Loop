from __future__ import annotations

import pytest

from engine.game_controller import GameController, UICallback
from engine.game_state import GameState
from engine.models.enums import GamePhase
from engine.phases.phase_base import WaitForInput


class _StubUI(UICallback):
    def __init__(self) -> None:
        self.waits: list[WaitForInput] = []

    def on_wait_for_input(self, wait: WaitForInput) -> None:
        self.waits.append(wait)


def test_wait_for_input_resume_advances_flow() -> None:
    ui = _StubUI()
    controller = GameController(ui_callback=ui)
    state = GameState()

    controller.start_game(state)

    # 进入第一处输入阶段（剧作家行动）
    assert controller.state_machine.current_phase == GamePhase.MASTERMIND_ACTION
    assert ui.waits, "expected at least one wait request"
    first_wait = ui.waits[-1]
    assert first_wait.callback is not None
    assert first_wait.options, "expected non-empty options for action cards"

    # 回填输入后应继续执行并进入下一处输入阶段（主人公行动）
    controller.provide_input(first_wait.options[0])
    assert controller.state_machine.current_phase == GamePhase.PROTAGONIST_ACTION
    assert len(ui.waits) >= 2
    assert ui.waits[-1].callback is not None


def test_provide_input_raises_without_pending_callback() -> None:
    controller = GameController()
    with pytest.raises(RuntimeError, match="No pending input callback"):
        controller.provide_input("anything")


def test_wait_for_input_without_callback_raises() -> None:
    controller = GameController()
    with pytest.raises(RuntimeError, match="missing callback"):
        controller._handle_signal(WaitForInput(input_type="broken"))
