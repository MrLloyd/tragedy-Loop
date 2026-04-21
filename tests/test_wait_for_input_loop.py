from __future__ import annotations

import pytest

from engine.game_controller import GameController, UICallback
from engine.models.cards import PlacementIntent
from engine.models.enums import AreaId, GamePhase, PlayerRole
from engine.phases.phase_base import WaitForInput
from ui.controllers.new_game_controller import NewGameController, default_phase5_draft


class _StubUI(UICallback):
    def __init__(self) -> None:
        self.waits: list[WaitForInput] = []
        self.phases: list[GamePhase] = []

    def on_phase_changed(self, phase: GamePhase, visible_state) -> None:
        self.phases.append(phase)

    def on_wait_for_input(self, wait: WaitForInput) -> None:
        self.waits.append(wait)


def test_wait_for_input_resume_advances_flow() -> None:
    ui = _StubUI()
    controller = GameController(ui_callback=ui)
    controller.start_game("first_steps", loop_count=1, days_per_loop=1)

    # 第一处输入阶段：GAME_PREPARE 的非公开信息表
    assert controller.state_machine.current_phase == GamePhase.GAME_PREPARE
    assert ui.waits, "expected at least one wait request"
    first_wait = ui.waits[-1]
    assert first_wait.callback is not None
    assert first_wait.input_type == "script_setup"
    assert "available_rule_y_ids" in first_wait.context

    controller.provide_input(NewGameController.build_payload(default_phase5_draft()))

    # 进入下一处输入阶段（剧作家行动）
    assert controller.state_machine.current_phase == GamePhase.MASTERMIND_ACTION
    assert len(ui.waits) >= 2
    assert ui.waits[-1].callback is not None


def test_invalid_script_setup_reprompts_with_errors() -> None:
    ui = _StubUI()
    controller = GameController(ui_callback=ui)
    controller.start_game("first_steps", loop_count=1, days_per_loop=1)

    bad_payload = NewGameController.build_payload(default_phase5_draft())
    bad_payload["rule_x_ids"] = []
    controller.provide_input(bad_payload)

    assert controller.state_machine.current_phase == GamePhase.GAME_PREPARE
    assert ui.waits[-1].input_type == "script_setup"
    assert ui.waits[-1].context["errors"]


def test_provide_input_raises_without_pending_callback() -> None:
    controller = GameController()
    with pytest.raises(RuntimeError, match="No pending input callback"):
        controller.provide_input("anything")


def test_wait_for_input_without_callback_raises() -> None:
    controller = GameController()
    with pytest.raises(RuntimeError, match="missing callback"):
        controller._handle_signal(WaitForInput(input_type="broken"))


def test_game_loop_completes_game_prepare_to_loop_end_check() -> None:
    """
    验证完整游戏循环：
    1. 从 GAME_PREPARE 开始
    2. 自动回填所有 WaitForInput
    3. 推进到 LOOP_END_CHECK

    流程：
      GAME_PREPARE
      → LOOP_START, TURN_START
      → [天数循环] MASTERMIND_ACTION(等) → PROTAGONIST_ACTION(等)
      → ACTION_RESOLVE → PLAYWRIGHT_ABILITY → PROTAGONIST_ABILITY
      → INCIDENT → LEADER_ROTATE → TURN_END
      → (如非最终日则重复，否则进入 LOOP_END)
      → LOOP_END
      → LOOP_END_CHECK ✓
    """
    ui = _StubUI()
    controller = GameController(ui_callback=ui)
    controller.start_game(
        "first_steps",
        loop_count=1,      # 1 个轮回（不触发 NEXT_LOOP）
        days_per_loop=1,   # 1 天（直接到最终日）
    )

    # 循环回填所有 WaitForInput 直到游戏到达目标阶段或结束
    max_iterations = 200  # 防止无限循环；剧作家逐张放牌会产生更多等待
    iteration = 0

    while (controller.state_machine.current_phase != GamePhase.LOOP_END_CHECK
           and controller.state_machine.current_phase != GamePhase.GAME_END
           and iteration < max_iterations):

        # 如果有待处理的等待，回填输入
        if controller._pending_callback is not None:
            last_wait = ui.waits[-1]

            # 根据输入类型生成不同的输入
            if last_wait.input_type == "script_setup":
                controller.provide_input(NewGameController.build_payload(default_phase5_draft()))
            elif last_wait.input_type == "place_action_card":
                controller.provide_input(_placement_for_wait(controller, last_wait))
            else:
                assert last_wait.options, f"No options for {last_wait.input_type}"
                # 其他输入类型（final_guess）：直接提交第一个选项
                controller.provide_input(last_wait.options[0])

        iteration += 1

    # LOOP_END_CHECK 可能在一次 provide_input 的同步递归里立即推进到 GAME_END，
    # 因此 current_phase 常为 GAME_END；以 phase 通知历史为准。
    phases_visited = ui.phases
    assert GamePhase.LOOP_END_CHECK in phases_visited, (
        f"Expected LOOP_END_CHECK in phase history, got phases={phases_visited}, "
        f"current_phase={controller.state_machine.current_phase} after {iteration} iterations"
    )
    assert controller.state_machine.current_phase in (
        GamePhase.LOOP_END_CHECK,
        GamePhase.GAME_END,
    )

    # 额外验证：确保经过了 Stub 处理器
    assert GamePhase.ACTION_RESOLVE in phases_visited, "Should have visited ACTION_RESOLVE"
    assert GamePhase.INCIDENT in phases_visited, "Should have visited INCIDENT"


def _placement_for_wait(controller: GameController, wait: WaitForInput) -> PlacementIntent:
    if wait.player == "mastermind":
        used_slots = {
            (placement.target_type, placement.target_id)
            for placement in controller.state.placed_cards
            if placement.owner == PlayerRole.MASTERMIND
        }
        for target_id in (AreaId.SCHOOL.value, AreaId.HOSPITAL.value, AreaId.SHRINE.value):
            if ("board", target_id) not in used_slots:
                return PlacementIntent(wait.options[0], "board", target_id)

    protagonist_slots = {
        (placement.target_type, placement.target_id)
        for placement in controller.state.placed_cards
        if placement.owner in {
            PlayerRole.PROTAGONIST_0,
            PlayerRole.PROTAGONIST_1,
            PlayerRole.PROTAGONIST_2,
        }
    }
    for target_id in (AreaId.SCHOOL.value, AreaId.HOSPITAL.value, AreaId.SHRINE.value):
        if ("board", target_id) not in protagonist_slots:
            return PlacementIntent(wait.options[0], "board", target_id)
    return PlacementIntent(wait.options[0], "board", AreaId.CITY.value)
