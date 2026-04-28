from __future__ import annotations

import pytest

from engine.game_controller import GameController, UICallback
from engine.models.cards import PlacementIntent
from engine.models.enums import AreaId, GamePhase, PlayerRole
from engine.models.selectors import area_choice_selector
from engine.models.script import CharacterSetup
from engine.phases.phase_base import ForceLoopEnd, WaitForInput
from engine.rules.module_loader import build_game_state_from_module
from ui.controllers.new_game_controller import CharacterDraft, NewGameController, NewGameDraft, default_phase5_draft


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


def test_loop_start_requests_henchman_initial_area_choice() -> None:
    ui = _StubUI()
    controller = GameController(ui_callback=ui)
    controller.start_game("first_steps", loop_count=1, days_per_loop=1)

    draft = default_phase5_draft()
    payload = NewGameController.build_payload(NewGameDraft(
        module_id=draft.module_id,
        loop_count=draft.loop_count,
        days_per_loop=draft.days_per_loop,
        rule_y_id=draft.rule_y_id,
        rule_x_ids=list(draft.rule_x_ids),
        characters=[
            CharacterDraft("male_student", "mastermind"),
            CharacterDraft("female_student", "key_person"),
            CharacterDraft("idol", "rumormonger"),
            CharacterDraft("henchman", "killer"),
            CharacterDraft("shrine_maiden", "serial_killer"),
        ],
        incidents=list(draft.incidents),
    ))

    controller.provide_input(payload)

    assert controller.state_machine.current_phase == GamePhase.LOOP_START
    assert ui.waits[-1].input_type == "choose_initial_area"
    assert ui.waits[-1].options == [
        area_choice_selector(AreaId.HOSPITAL.value),
        area_choice_selector(AreaId.SHRINE.value),
        area_choice_selector(AreaId.CITY.value),
        area_choice_selector(AreaId.SCHOOL.value),
    ]

    controller.provide_input(area_choice_selector(AreaId.SCHOOL.value))

    assert controller.state.characters["henchman"].initial_area == AreaId.SCHOOL
    assert controller.state.characters["henchman"].area == AreaId.SCHOOL
    assert controller.state_machine.current_phase == GamePhase.MASTERMIND_ACTION


def test_provide_input_raises_without_pending_callback() -> None:
    controller = GameController()
    with pytest.raises(RuntimeError, match="No pending input callback"):
        controller.provide_input("anything")


def test_wait_for_input_without_callback_raises() -> None:
    controller = GameController()
    with pytest.raises(RuntimeError, match="missing callback"):
        controller._handle_signal(WaitForInput(input_type="broken"))


def test_game_loop_completes_game_prepare_through_loop_end() -> None:
    """
    验证完整游戏循环：
    1. 从 GAME_PREPARE 开始
    2. 自动回填所有 WaitForInput
    3. 推进到 LOOP_END 并完成末尾分流

    流程：
      GAME_PREPARE
      → LOOP_START, TURN_START
      → [天数循环] MASTERMIND_ACTION(等) → PROTAGONIST_ACTION(等)
      → ACTION_RESOLVE → PLAYWRIGHT_ABILITY → PROTAGONIST_ABILITY
      → INCIDENT → LEADER_ROTATE → TURN_END
      → (如非最终日则重复，否则进入 LOOP_END)
      → LOOP_END
      → GAME_END / NEXT_LOOP / FINAL_GUESS ✓
    """
    ui = _StubUI()
    controller = GameController(ui_callback=ui)
    controller.start_game(
        "first_steps",
        loop_count=1,      # 1 个轮回（不触发 NEXT_LOOP）
        days_per_loop=1,   # 1 天（直接到最终日）
    )

    # 循环回填所有 WaitForInput 直到游戏结束
    max_iterations = 200  # 防止无限循环；剧作家逐张放牌会产生更多等待
    iteration = 0

    while (controller.state_machine.current_phase != GamePhase.GAME_END
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

    # LOOP_END 末尾直接分流；以 phase 通知历史验证结算入口。
    phases_visited = ui.phases
    assert GamePhase.LOOP_END in phases_visited, (
        f"Expected LOOP_END in phase history, got phases={phases_visited}, "
        f"current_phase={controller.state_machine.current_phase} after {iteration} iterations"
    )
    assert controller.state_machine.current_phase == GamePhase.GAME_END

    # 额外验证：确保经过了 Stub 处理器
    assert GamePhase.ACTION_RESOLVE in phases_visited, "Should have visited ACTION_RESOLVE"
    assert GamePhase.INCIDENT in phases_visited, "Should have visited INCIDENT"


def test_forced_loop_end_still_runs_loop_end_resolution() -> None:
    ui = _StubUI()
    controller = GameController(ui_callback=ui)
    controller.state = build_game_state_from_module(
        "basic_tragedy_x",
        loop_count=2,
        days_per_loop=3,
        rule_y_id="btx_murder_plan",
        rule_x_ids=["btx_rumors", "btx_latent_serial_killer"],
        character_setups=[
            CharacterSetup("female_student", "key_person"),
            CharacterSetup("doctor", "friend"),
        ],
        incidents=[],
        skip_script_validation=True,
    )
    controller.state.characters["doctor"].mark_dead()
    controller.state.failure_flags.add("key_person_dead")
    controller.state_machine.current_phase = GamePhase.INCIDENT

    controller._handle_signal(ForceLoopEnd(reason="key_person_dead"))

    phases_visited = ui.phases
    assert GamePhase.LOOP_END in phases_visited
    assert controller.state.characters["doctor"].revealed is True
    assert controller.state.cross_loop_memory.revealed_identities_last_loop["doctor"] is True
    assert controller.state.current_loop == 2


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
