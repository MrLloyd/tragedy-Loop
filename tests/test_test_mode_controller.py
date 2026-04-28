from __future__ import annotations

from engine.display_names import area_name
from engine.display_names import character_option_label
from engine.models.cards import ActionCard, CardPlacement
from engine.models.enums import AreaId, CharacterLifeState, GamePhase, TokenType
from engine.models.enums import CardType, PlayerRole
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
    assert controller.session.state.characters["office_worker"].life_state == CharacterLifeState.DEAD


def test_test_mode_controller_can_trigger_cultist_action_resolve_ability() -> None:
    controller = TestModeController("basic_tragedy_x")
    controller.replace_characters(
        [
            TestCharacterDraft(
                character_id="cult_leader",
                identity_id="cultist",
                area="school",
            ),
            TestCharacterDraft(
                character_id="ai",
                identity_id="平民",
                area="school",
            ),
        ]
    )
    controller.set_runtime(
        current_loop=1,
        current_day=1,
        current_phase=GamePhase.ACTION_RESOLVE.value,
    )
    controller.rebuild_session()

    assert controller.session is not None
    controller.session.state.placed_cards = [
        CardPlacement(
            ActionCard(CardType.FORBID_INTRIGUE, PlayerRole.PROTAGONIST_0),
            PlayerRole.PROTAGONIST_0,
            "character",
            "ai",
            face_down=False,
        ),
        CardPlacement(
            ActionCard(CardType.INTRIGUE_PLUS_1, PlayerRole.MASTERMIND),
            PlayerRole.MASTERMIND,
            "character",
            "ai",
            face_down=False,
        ),
    ]

    controller.trigger_identity_ability(
        actor_id="cult_leader",
        ability_id="cultist_action_resolve_nullify_forbid_intrigue_character",
        timing="action_resolve",
        target_choices=["ai"],
    )

    assert controller.session.state.placed_cards[0].nullified is True
    assert controller.session.state.placed_cards[1].nullified is False


def test_test_mode_controller_lists_spiritual_contamination_for_basic_tragedy_x() -> None:
    controller = TestModeController("basic_tragedy_x")

    assert "spiritual_contamination" in controller.available_incident_ids


def test_test_mode_controller_can_apply_board_tokens_for_rule_checks() -> None:
    controller = TestModeController("first_steps")
    controller.apply_rules_and_rebuild(
        rule_y_id="fs_protect_this_place",
        rule_x_ids=[],
    )
    controller.replace_board_tokens(
        {
            "school": {"intrigue": 2},
        }
    )
    controller.set_runtime(
        current_loop=1,
        current_day=1,
        current_phase=GamePhase.LOOP_END.value,
    )
    controller.rebuild_session()

    assert controller.session is not None
    assert controller.session.state.board.areas[AreaId.SCHOOL].tokens.get(TokenType.INTRIGUE) == 2

    ability_ids = [
        ability_id
        for ability_id, _label in controller.available_rule_abilities(timing="loop_end")
    ]
    assert "fs_fail_mastermind_initial_area_intrigue_2_protect" in ability_ids


def test_test_mode_controller_board_tokens_only_keep_intrigue_and_cap_at_three() -> None:
    controller = TestModeController("first_steps")
    controller.replace_board_tokens(
        {
            "school": {
                "intrigue": 9,
                "paranoia": 2,
                "goodwill": 1,
            },
        }
    )

    assert controller.draft.board_tokens["school"] == {"intrigue": 3}


def test_test_mode_controller_lists_derived_identity_abilities_for_unstable_factor() -> None:
    controller = TestModeController("basic_tragedy_x")
    controller.replace_characters(
        [
            TestCharacterDraft(
                character_id="ai",
                identity_id="unstable_factor",
                area="school",
            ),
            TestCharacterDraft(
                character_id="doctor",
                identity_id="平民",
                area="school",
            ),
        ]
    )
    controller.replace_board_tokens(
        {
            "school": {"intrigue": 2},
        }
    )
    controller.rebuild_session()

    ability_ids = [
        ability_id
        for ability_id, _label in controller.available_identity_abilities(
            actor_id="ai",
            timing="playwright_ability",
        )
    ]
    assert "rumormonger_playwright_place_paranoia" in ability_ids

    option_groups = controller.available_identity_ability_target_options(
        actor_id="ai",
        ability_id="rumormonger_playwright_place_paranoia",
        timing="playwright_ability",
    )
    assert len(option_groups) == 1
    assert ("doctor", character_option_label("doctor")) in option_groups[0]


def test_test_mode_controller_incident_target_options_follow_runtime_choices() -> None:
    controller = TestModeController("first_steps")
    controller.replace_characters(
        [
            TestCharacterDraft(
                character_id="office_worker",
                identity_id="平民",
                area="school",
                tokens={"paranoia": 2},
            ),
            TestCharacterDraft(
                character_id="ai",
                identity_id="平民",
                area="school",
            ),
            TestCharacterDraft(
                character_id="shrine_maiden",
                identity_id="平民",
                area="city",
            ),
        ]
    )
    controller.rebuild_session()

    murder = controller.available_incident_target_options(
        incident_id="murder",
        perpetrator_id="office_worker",
    )
    assert len(murder["character"]) == 1
    assert murder["character"][0] == [("ai", character_option_label("ai"))]
    assert murder["area"] == []
    assert murder["token"] == []

    disappearance = controller.available_incident_target_options(
        incident_id="disappearance",
        perpetrator_id="office_worker",
    )
    assert disappearance["character"] == []
    assert len(disappearance["area"]) == 1
    assert ("school", area_name("school")) not in disappearance["area"][0]
    assert ("hospital", area_name("hospital")) in disappearance["area"][0]

    btx_controller = TestModeController("basic_tragedy_x")
    btx_controller.replace_characters(
        [
            TestCharacterDraft(
                character_id="office_worker",
                identity_id="平民",
                area="school",
                tokens={"paranoia": 2},
            ),
            TestCharacterDraft(
                character_id="ai",
                identity_id="平民",
                area="school",
            ),
        ]
    )
    btx_controller.rebuild_session()

    butterfly = btx_controller.available_incident_target_options(
        incident_id="butterfly_effect",
        perpetrator_id="office_worker",
    )
    assert len(butterfly["character"]) == 1
    assert butterfly["token"] == []

    butterfly_after_character = btx_controller.available_incident_target_options(
        incident_id="butterfly_effect",
        perpetrator_id="office_worker",
        target_character_ids=["ai"],
    )
    assert len(butterfly_after_character["token"]) == 1


def test_test_mode_controller_trigger_incident_distinguishes_not_occurred_status() -> None:
    controller = TestModeController("first_steps")
    controller.replace_characters(
        [
            TestCharacterDraft(
                character_id="office_worker",
                identity_id="平民",
                area="school",
                tokens={"paranoia": 1},
            ),
            TestCharacterDraft(
                character_id="ai",
                identity_id="平民",
                area="school",
            ),
        ]
    )
    controller.rebuild_session()

    controller.trigger_incident(
        incident_id="murder",
        perpetrator_id="office_worker",
        target_character_ids=["ai"],
    )

    assert "未发生" in controller.status_message


def test_test_mode_controller_snapshot_shows_spiritual_contamination_for_ai_total_tokens() -> None:
    controller = TestModeController("basic_tragedy_x")
    controller.replace_characters(
        [
            TestCharacterDraft(
                character_id="ai",
                identity_id="unstable_factor",
                area="city",
                tokens={"intrigue": 4},
            ),
            TestCharacterDraft(
                character_id="shrine_maiden",
                identity_id="平民",
                area="shrine",
            ),
        ]
    )
    controller.rebuild_session()

    controller.trigger_incident(
        incident_id="spiritual_contamination",
        perpetrator_id="ai",
    )

    snapshot = controller.snapshot()
    assert snapshot["board_tokens"]["shrine"]["intrigue"] == 2
    assert "发生｜有现象" in controller.status_message


def test_test_mode_controller_can_list_and_trigger_rule_ability() -> None:
    controller = TestModeController("first_steps")
    controller.apply_rules_and_rebuild(
        rule_y_id="fs_murder_plan",
        rule_x_ids=["fs_rumors"],
    )

    ability_ids = [
        ability_id
        for ability_id, _label in controller.available_rule_abilities(timing="playwright_ability")
    ]
    assert "fs_rumors_playwright_place_intrigue" in ability_ids

    option_groups = controller.available_rule_ability_target_options(
        ability_id="fs_rumors_playwright_place_intrigue",
        timing="playwright_ability",
    )
    assert len(option_groups) == 1
    assert ("school", area_name("school")) in option_groups[0]

    controller.trigger_rule_ability(
        ability_id="fs_rumors_playwright_place_intrigue",
        timing="playwright_ability",
        target_choices=["school"],
    )

    assert controller.session is not None
    assert controller.session.state.board.areas[AreaId.SCHOOL].tokens.get(TokenType.INTRIGUE) == 1
    assert "规则能力触发" in controller.status_message


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


def test_test_mode_controller_can_resume_wait_with_phase_input() -> None:
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
                identity_id="mastermind",
                area="school",
            ),
            TestCharacterDraft(
                character_id="ai",
                identity_id="平民",
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

    wait = controller.pending_wait
    assert wait is not None
    ability = next(
        option
        for option in wait.options
        if getattr(getattr(option, "ability", None), "ability_id", "") == "mastermind_playwright_place_intrigue_character"
    )

    controller.submit_input(ability)

    target_wait = controller.pending_wait
    assert target_wait is not None
    assert target_wait.input_type == "choose_ability_target"
    assert "ai" in target_wait.options
    assert "shrine_maiden" in target_wait.options

    controller.submit_input("ai")

    assert controller.session is not None
    assert controller.session.state.characters["ai"].tokens.get(TokenType.INTRIGUE) == 1


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
                life_state=CharacterLifeState.DEAD.value,
                revealed=False,
            ),
        ]
    )
    controller.rebuild_session()

    controller.execute_current_phase()

    assert controller.session is not None
    assert "friend_dead" in controller.session.state.failure_flags
    assert "触发失败条件：friend_dead" in controller.status_message


def test_test_mode_controller_incident_death_triggers_derived_on_death_failure() -> None:
    controller = TestModeController("basic_tragedy_x")
    controller.set_runtime(
        current_loop=1,
        current_day=1,
        current_phase=GamePhase.INCIDENT.value,
    )
    controller.replace_characters(
        [
            TestCharacterDraft(
                character_id="ai",
                identity_id="unstable_factor",
                area="school",
            ),
            TestCharacterDraft(
                character_id="doctor",
                identity_id="平民",
                area="school",
                tokens={"paranoia": 2},
            ),
        ]
    )
    controller.replace_board_tokens(
        {
            "school": {"intrigue": 2},
            "city": {"intrigue": 2},
        }
    )
    controller.rebuild_session()

    controller.trigger_incident(
        incident_id="murder",
        perpetrator_id="doctor",
        target_character_ids=["ai"],
    )

    assert controller.session is not None
    assert controller.session.state.characters["ai"].life_state == CharacterLifeState.DEAD
    assert "key_person_dead" in controller.session.state.failure_flags
    assert any(
        event["event_type"] == "ABILITY_DECLARED"
        and event["data"].get("ability_id") == "key_person_on_death"
        and event["data"].get("source_kind") == "derived"
        for event in controller.snapshot()["event_log"]
        if isinstance(event, dict)
    )
    assert "触发失败条件：key_person_dead" in controller.status_message
