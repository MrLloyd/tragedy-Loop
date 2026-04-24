from __future__ import annotations

from engine.display_names import character_option_label
from engine.models.enums import GamePhase, TokenType
from ui.controllers.test_mode_controller import (
    TEST_MODE_DAYS_PER_LOOP,
    TEST_MODE_LOOP_COUNT,
    TestCharacterDraft,
    TestModeController,
)


def test_test_mode_controller_rebuilds_debug_session_without_rules() -> None:
    controller = TestModeController("first_steps")
    controller.set_runtime(
        current_loop=2,
        current_day=3,
        current_phase=GamePhase.PLAYWRIGHT_ABILITY.value,
    )
    controller.replace_characters(
        [
            TestCharacterDraft(
                character_id="office_worker",
                identity_id="mastermind",
                area="school",
                tokens={"intrigue": 1},
                revealed=True,
            ),
            TestCharacterDraft(
                character_id="ai",
                identity_id="平民",
                area="school",
            ),
        ]
    )

    controller.rebuild_session()

    assert controller.session is not None
    assert controller.session.state.script.rule_y is None
    assert controller.session.state.script.rules_x == []
    assert controller.session.state.current_loop == 2
    assert controller.session.state.current_day == 3
    assert controller.session.state.current_phase == GamePhase.PLAYWRIGHT_ABILITY
    assert controller.session.state.script.loop_count == TEST_MODE_LOOP_COUNT
    assert controller.session.state.script.days_per_loop == TEST_MODE_DAYS_PER_LOOP
    assert controller.session.state.characters["office_worker"].identity_id == "mastermind"
    assert controller.session.state.characters["office_worker"].tokens.get(TokenType.INTRIGUE) == 1
    assert controller.session.state.characters["office_worker"].revealed is True


def test_test_mode_controller_can_trigger_identity_ability_and_incident() -> None:
    controller = TestModeController("first_steps")
    controller.replace_characters(
        [
            TestCharacterDraft(
                character_id="office_worker",
                identity_id="mastermind",
                area="school",
            ),
            TestCharacterDraft(
                character_id="ai",
                identity_id="平民",
                area="school",
                tokens={"paranoia": 99},
            ),
        ]
    )
    controller.rebuild_session()

    ability_ids = [ability_id for ability_id, _label in controller.available_identity_abilities(actor_id="office_worker", timing="playwright_ability")]
    assert "mastermind_playwright_place_intrigue_character" in ability_ids

    controller.trigger_identity_ability(
        actor_id="office_worker",
        ability_id="mastermind_playwright_place_intrigue_character",
        timing="playwright_ability",
        target_choices=["ai"],
    )
    assert controller.session is not None
    assert controller.session.state.characters["ai"].tokens.get(TokenType.INTRIGUE) == 1

    controller.trigger_incident(
        incident_id="murder",
        perpetrator_id="ai",
        target_character_ids=["office_worker"],
    )
    assert controller.session.state.characters["office_worker"].is_alive is False


def test_test_mode_controller_runtime_is_clamped_to_fixed_loop_and_day() -> None:
    controller = TestModeController("first_steps")

    controller.set_runtime(
        current_loop=99,
        current_day=99,
        current_phase=GamePhase.INCIDENT.value,
    )

    assert controller.draft.current_loop == TEST_MODE_LOOP_COUNT
    assert controller.draft.current_day == TEST_MODE_DAYS_PER_LOOP


def test_test_mode_controller_lists_identity_target_options_for_dropdowns() -> None:
    controller = TestModeController("first_steps")
    controller.replace_characters(
        [
            TestCharacterDraft(
                character_id="office_worker",
                identity_id="mastermind",
                area="school",
            ),
            TestCharacterDraft(
                character_id="ai",
                identity_id="平民",
                area="school",
            ),
        ]
    )
    controller.rebuild_session()

    option_groups = controller.available_identity_ability_target_options(
        actor_id="office_worker",
        ability_id="mastermind_playwright_place_intrigue_character",
        timing="playwright_ability",
    )

    assert len(option_groups) == 1
    assert ("ai", character_option_label("ai")) in option_groups[0]


def test_test_mode_controller_can_apply_rules_and_rebuild_session() -> None:
    controller = TestModeController("first_steps")

    controller.apply_rules_and_rebuild(
        rule_y_id="fs_murder_plan",
        rule_x_ids=["fs_ripper_shadow"],
    )

    assert controller.session is not None
    assert controller.session.state.script.rule_y is not None
    assert controller.session.state.script.rule_y.rule_id == "fs_murder_plan"
    assert [rule.rule_id for rule in controller.session.state.script.rules_x] == ["fs_ripper_shadow"]
    assert controller.draft.rule_y_id == "fs_murder_plan"
    assert controller.draft.rule_x_ids == ["fs_ripper_shadow"]


def test_test_mode_controller_can_execute_and_advance_phase() -> None:
    controller = TestModeController("first_steps")
    controller.set_runtime(
        current_loop=1,
        current_day=1,
        current_phase=GamePhase.LEADER_ROTATE.value,
    )
    controller.rebuild_session()

    assert controller.session is not None
    assert controller.session.state.leader_index == 0

    controller.execute_current_phase()

    assert controller.session.state.leader_index == 1
    assert controller.session.state.current_phase == GamePhase.LEADER_ROTATE
    assert controller.pending_wait is None

    controller.advance_phase()

    assert controller.session.state.current_phase == GamePhase.TURN_END
    assert controller.draft.current_phase == GamePhase.TURN_END.value


def test_test_mode_controller_execute_phase_records_wait_for_input() -> None:
    controller = TestModeController("first_steps")
    controller.set_runtime(
        current_loop=1,
        current_day=1,
        current_phase=GamePhase.PLAYWRIGHT_ABILITY.value,
    )
    controller.replace_characters(
        [
            TestCharacterDraft(
                character_id="office_worker",
                identity_id="rumormonger",
                area="school",
            ),
            TestCharacterDraft(
                character_id="shrine_maiden",
                identity_id="平民",
                area="school",
            ),
        ]
    )
    controller.rebuild_session()

    controller.execute_current_phase()

    assert controller.pending_wait is not None
    assert controller.pending_wait.input_type == "choose_playwright_ability"
    snapshot = controller.snapshot()
    assert snapshot["pending_wait"] == {
        "input_type": "choose_playwright_ability",
        "player": "mastermind",
        "prompt": "剧作家请选择要声明的能力，或 pass",
    }


def test_test_mode_controller_execute_loop_end_reports_triggered_failure_condition() -> None:
    controller = TestModeController("basic_tragedy_x")
    controller.set_runtime(
        current_loop=1,
        current_day=1,
        current_phase=GamePhase.LOOP_END.value,
    )
    controller.replace_characters(
        [
            TestCharacterDraft(
                character_id="friend",
                identity_id="friend",
                area="school",
                is_alive=False,
                revealed=False,
            ),
        ]
    )
    controller.rebuild_session()

    controller.execute_current_phase()

    assert controller.session is not None
    assert "friend_dead" in controller.session.state.failure_flags
    assert "触发失败条件：friend_dead" in controller.status_message
