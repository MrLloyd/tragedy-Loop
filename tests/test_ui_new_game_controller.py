from __future__ import annotations

from engine.game_controller import GameController
from engine.models.enums import AreaId, GamePhase
from ui.controllers.game_session_controller import GameSessionController
from ui.controllers.new_game_controller import NewGameController, default_phase5_draft
from ui.screens.new_game_screen import NewGameScreenModel


def test_default_phase5_draft_matches_plan() -> None:
    draft = default_phase5_draft()

    assert draft.module_id == "first_steps"
    assert draft.loop_count == 3
    assert draft.days_per_loop == 3
    assert draft.rule_y_id == "fs_murder_plan"
    assert draft.rule_x_ids == ["fs_ripper_shadow"]
    assert [(item.character_id, item.identity_id) for item in draft.characters] == [
        ("male_student", "mastermind"),
        ("female_student", "key_person"),
        ("idol", "rumormonger"),
        ("office_worker", "killer"),
        ("shrine_maiden", "serial_killer"),
    ]
    assert [(item.incident_id, item.day, item.perpetrator_id) for item in draft.incidents] == [
        ("", 1, ""),
        ("", 2, ""),
        ("suicide", 3, "female_student"),
    ]


def test_new_game_screen_model_starts_with_phase5_default() -> None:
    model = NewGameScreenModel()

    assert model.draft == default_phase5_draft()
    assert model.available_ids("available_incidents")
    assert "suicide" in model.available_ids("available_incidents")
    assert "mastermind" in model.available_ids("available_identities")
    assert model.rule_x_count() == 1


def test_new_game_screen_model_validates_phase5_default() -> None:
    model = NewGameScreenModel()

    assert model.validate() == []


def test_new_game_screen_model_rejects_invalid_incident_perpetrator() -> None:
    model = NewGameScreenModel()
    model.update_incident(2, perpetrator_id="ghost")

    assert "事件 suicide 的当事人不在角色列表中" in model.validate()


def test_new_game_screen_model_rejects_duplicate_rule_x_and_perpetrators() -> None:
    model = NewGameScreenModel()
    model.set_basic(
        module_id="basic_tragedy_x",
        rule_x_ids=["btx_causal_line", "btx_causal_line"],
    )
    model.refresh_available_options(module_id="basic_tragedy_x")
    model.update_incident(0, incident_id="murder", perpetrator_id="female_student")
    model.update_incident(1, incident_id="suicide", perpetrator_id="female_student")

    issues = model.validate()

    assert "规则 X 不能重复" in issues
    assert "不同天的事件当事人不能重复" in issues


def test_new_game_controller_builds_engine_input_payload() -> None:
    payload = NewGameController.build_payload(default_phase5_draft())

    assert payload["module_id"] == "first_steps"
    assert payload["loop_count"] == 3
    assert payload["days_per_loop"] == 3
    assert payload["rule_y_id"] == "fs_murder_plan"
    assert payload["rule_x_ids"] == ["fs_ripper_shadow"]
    assert [(item.character_id, item.identity_id) for item in payload["character_setups"]] == [
        ("male_student", "mastermind"),
        ("female_student", "key_person"),
        ("idol", "rumormonger"),
        ("office_worker", "killer"),
        ("shrine_maiden", "serial_killer"),
    ]
    assert [(item.incident_id, item.day, item.perpetrator_id) for item in payload["incidents"]] == [
        ("suicide", 3, "female_student"),
    ]


def test_game_session_controller_receives_wait_and_submits_input() -> None:
    session = GameSessionController()
    controller = GameController(ui_callback=session)
    session.bind(controller)

    controller.start_game("first_steps", loop_count=1, days_per_loop=1)

    assert session.view_state.current_phase == GamePhase.GAME_PREPARE
    assert session.view_state.current_wait is not None
    assert session.view_state.current_wait.input_type == "script_setup"

    session.submit_input(NewGameController.build_payload(default_phase5_draft()))

    assert session.view_state.current_phase == GamePhase.MASTERMIND_ACTION
    assert session.view_state.current_wait is not None
    first_wait = session.view_state.current_wait
    cards = first_wait.options[:3]

    session.submit_place_action_cards([
        (cards[0], "board", AreaId.SCHOOL.value),
        (cards[1], "board", AreaId.HOSPITAL.value),
        (cards[2], "board", AreaId.SHRINE.value),
    ])

    assert session.view_state.current_phase == GamePhase.PROTAGONIST_ACTION
    assert session.view_state.current_wait is not None
