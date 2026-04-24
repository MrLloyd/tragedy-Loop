from __future__ import annotations

from engine.display_names import character_name, identity_name
from engine.event_bus import GameEvent, GameEventType
from engine.game_controller import GameController
from engine.models.enums import AreaId, CardType, GamePhase
from engine.phases.phase_base import WaitForInput
from ui.controllers.game_session_controller import GameSessionController
from ui.controllers.new_game_controller import NewGameController, default_phase5_draft
from ui.screens.game_screen import GameScreenModel
from ui.screens.new_game_screen import NewGameScreenModel


def _boot_with_script_setup() -> tuple[GameSessionController, GameController]:
    session = GameSessionController()
    controller = GameController(ui_callback=session)
    session.bind(controller)
    session.bind_new_game_model(NewGameScreenModel())

    controller.start_game("first_steps", loop_count=1, days_per_loop=1)
    session.submit_script_setup(NewGameController.build_payload(default_phase5_draft()))
    return session, controller


def test_script_setup_wait_context_syncs_to_new_game_model() -> None:
    model = NewGameScreenModel()
    session = GameSessionController()
    session.bind_new_game_model(model)
    controller = GameController(ui_callback=session)
    session.bind(controller)

    controller.start_game("first_steps", loop_count=1, days_per_loop=1)

    assert session.current_wait_input_type() == "script_setup"
    assert "available_rule_y_ids" in model.wait_context
    assert model.wait_context["module_id"] == "first_steps"


def test_game_screen_model_renders_mastermind_wait_snapshot() -> None:
    session, _ = _boot_with_script_setup()
    model = GameScreenModel()

    model.sync_from_session(session.view_state)
    snapshot = model.snapshot

    assert snapshot.phase == "剧作家行动阶段"
    assert snapshot.wait_input_type == "place_action_card"
    assert snapshot.wait_option_labels
    assert "card:" not in snapshot.wait_option_labels[0]
    assert snapshot.characters
    assert snapshot.loop_text == "第 1 / 3 轮"
    assert snapshot.day_text == "第 1 / 3 天"
    assert snapshot.leader_text == "主人公 1"
    assert snapshot.characters[0].area == "学校"
    assert snapshot.characters[0].identity == "未公开"
    assert "阶段切换：剧作家行动阶段" in snapshot.protagonist_announcements
    assert "阶段切换：剧作家行动阶段" in snapshot.mastermind_announcements


def test_submit_place_action_cards_helper_advances_phase() -> None:
    session, _ = _boot_with_script_setup()
    wait = session.view_state.current_wait
    assert wait is not None
    assert wait.input_type == "place_action_card"

    cards = wait.options[:3]
    session.submit_place_action_cards(
        [
            (cards[0], "board", AreaId.SCHOOL.value),
            (cards[1], "board", AreaId.HOSPITAL.value),
            (cards[2], "board", AreaId.SHRINE.value),
        ]
    )

    assert session.view_state.current_phase == GamePhase.PROTAGONIST_ACTION
    assert session.current_wait_input_type() == "place_action_card"


def test_invalid_mastermind_overlap_keeps_input_callback_for_retry() -> None:
    session, controller = _boot_with_script_setup()
    wait = session.view_state.current_wait
    assert wait is not None
    assert wait.input_type == "place_action_card"

    session.submit_place_action_card(
        card=wait.options[0],
        target_type="board",
        target_id=AreaId.SCHOOL.value,
    )

    retry_wait = session.view_state.current_wait
    assert retry_wait is not None
    assert retry_wait.input_type == "place_action_card"
    try:
        session.submit_place_action_card(
            card=retry_wait.options[0],
            target_type="board",
            target_id=AreaId.SCHOOL.value,
        )
    except ValueError as exc:
        assert "same target" in str(exc)
    else:
        raise AssertionError("expected duplicate slot to be rejected")

    assert session.view_state.current_wait is retry_wait
    assert controller._pending_callback is not None

    session.submit_place_action_card(
        card=retry_wait.options[0],
        target_type="board",
        target_id=AreaId.HOSPITAL.value,
    )
    assert session.current_wait_input_type() == "place_action_card"


def test_session_read_debug_snapshot_reads_current_runtime_state() -> None:
    session, _ = _boot_with_script_setup()

    snapshot = session.read_debug_snapshot()

    assert snapshot["current_phase"] == GamePhase.MASTERMIND_ACTION.value
    assert snapshot["current_loop"] == 1
    assert "male_student" in snapshot["characters"]
    assert snapshot["script"]["rule_y_id"] == "fs_murder_plan"
    assert snapshot["current_wait"]["input_type"] == "place_action_card"
    assert snapshot["current_wait"]["wait_id"] == 2
    assert snapshot["current_wait"]["has_callback"] is True
    assert snapshot["current_wait"]["engine_has_pending_callback"] is True
    assert snapshot["engine_runtime"]["engine_phase"] == GamePhase.MASTERMIND_ACTION.value
    assert snapshot["engine_runtime"]["pending_wait_id"] == 2
    assert snapshot["engine_runtime"]["has_pending_callback"] is True
    assert snapshot["engine_runtime"]["trace_tail"]


def test_session_rejects_reentrant_input_submission() -> None:
    session, _ = _boot_with_script_setup()
    wait = session.view_state.current_wait
    assert wait is not None

    original_callback = wait.callback
    assert original_callback is not None

    def _reentrant_callback(choice):
        session.view_state.current_wait = wait
        try:
            session.submit_input(choice)
        except RuntimeError as exc:
            assert str(exc) == "Input submission is already in progress"
        else:
            raise AssertionError("expected reentrant submission to be rejected")
        return original_callback(choice)

    wait.callback = _reentrant_callback
    session.game_controller._pending_callback = _reentrant_callback

    session.submit_place_action_card(
        card=wait.options[0],
        target_type="board",
        target_id=AreaId.SCHOOL.value,
    )


def test_session_rejects_stale_wait_submission() -> None:
    session, controller = _boot_with_script_setup()
    stale_wait = session.view_state.current_wait
    assert stale_wait is not None

    session.submit_place_action_card(
        card=stale_wait.options[0],
        target_type="board",
        target_id=AreaId.SCHOOL.value,
    )

    assert session.view_state.current_wait is not None
    assert session.view_state.current_wait.wait_id != stale_wait.wait_id

    session.view_state.current_wait = stale_wait
    try:
        session.submit_input(stale_wait.options[0])
    except RuntimeError as exc:
        assert "Current input is stale" in str(exc)
    else:
        raise AssertionError("expected stale wait submission to be rejected")

    assert controller._pending_callback is not None


def test_game_screen_board_targets_are_four_board_areas() -> None:
    assert GameScreenModel.board_target_options() == [
        AreaId.HOSPITAL.value,
        AreaId.SHRINE.value,
        AreaId.CITY.value,
        AreaId.SCHOOL.value,
    ]


def test_session_announcements_sync_into_game_screen_snapshot() -> None:
    session, _ = _boot_with_script_setup()
    wait = session.view_state.current_wait
    assert wait is not None

    paranoia_card = next(card for card in wait.options if card.card_type == CardType.PARANOIA_PLUS_1)
    fillers = [card for card in wait.options if card is not paranoia_card][:2]
    session.submit_place_action_cards(
        [
            (paranoia_card, "character", "female_student"),
            (fillers[0], "board", AreaId.CITY.value),
            (fillers[1], "board", AreaId.SCHOOL.value),
        ]
    )
    for target_area in (AreaId.HOSPITAL.value, AreaId.SHRINE.value, AreaId.CITY.value):
        protagonist_wait = session.view_state.current_wait
        assert protagonist_wait is not None
        assert protagonist_wait.input_type == "place_action_card"
        session.submit_place_action_card(
            card=protagonist_wait.options[0],
            target_type="board",
            target_id=target_area,
        )

    assert session.view_state.announcements
    assert any("标记物变化" in item for item in session.view_state.mastermind_announcements)
    model = GameScreenModel()
    model.sync_from_session(session.view_state)

    assert model.snapshot.announcements


def test_session_collects_identity_revealed_popup_message() -> None:
    session, controller = _boot_with_script_setup()

    controller.event_bus.emit(GameEvent(
        GameEventType.IDENTITY_REVEALED,
        {"character_id": "male_student", "identity_id": "mastermind"},
    ))
    session._consume_event_log_updates()

    assert session.view_state.revealed_identity_messages[-1] == (
        f"{character_name('male_student')}的身份是{identity_name('mastermind')}"
    )


def test_submit_confirm_sends_none_for_confirm_only_wait() -> None:
    class _DummyController:
        def __init__(self) -> None:
            self.received = object()

        def provide_input(self, choice) -> None:
            self.received = choice

    session = GameSessionController()
    dummy = _DummyController()
    session.game_controller = dummy  # type: ignore[assignment]
    session.view_state.current_wait = WaitForInput(
        input_type="final_guess",
        prompt="确认继续",
        options=[],
    )

    session.submit_confirm()

    assert dummy.received is None
    assert session.view_state.current_wait is None
