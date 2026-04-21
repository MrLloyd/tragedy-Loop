from __future__ import annotations

from engine.game_controller import GameController
from engine.models.enums import AreaId, CardType, Outcome, PlayerRole
from ui.controllers.game_session_controller import GameSessionController
from ui.controllers.new_game_controller import NewGameController, default_phase5_draft


def test_ui_session_minimal_playable_chain_reaches_game_over() -> None:
    session = GameSessionController()
    controller = GameController(ui_callback=session)
    session.bind(controller)

    controller.start_game("first_steps", loop_count=3, days_per_loop=3)

    for _ in range(200):
        if session.view_state.outcome is not None:
            break
        wait = session.view_state.current_wait
        assert wait is not None
        _respond(session)

    assert session.view_state.outcome == Outcome.MASTERMIND_WIN
    assert session.view_state.announcements
    snapshot = session.read_debug_snapshot()
    assert snapshot["current_phase"] == "game_end"


def _respond(session: GameSessionController) -> None:
    wait = session.view_state.current_wait
    assert wait is not None

    if wait.input_type == "script_setup":
        session.submit_script_setup(
            NewGameController.build_payload(default_phase5_draft())
        )
        return

    if wait.input_type == "place_action_cards":
        paranoia_card = next(
            card for card in wait.options
            if card.card_type == CardType.PARANOIA_PLUS_1
        )
        fillers = [card for card in wait.options if card is not paranoia_card][:2]
        session.submit_place_action_cards(
            [
                (paranoia_card, "character", "female_student"),
                (fillers[0], "board", AreaId.CITY.value),
                (fillers[1], "board", AreaId.SCHOOL.value),
            ]
        )
        return

    if wait.input_type == "place_action_card":
        if wait.player == "mastermind":
            used_slots = {
                (placement.target_type, placement.target_id)
                for placement in session.game_controller.state.placed_cards
                if placement.owner == PlayerRole.MASTERMIND
            }
            card = (
                next(
                    card for card in wait.options
                    if card.card_type == CardType.PARANOIA_PLUS_1
                )
                if not used_slots
                else wait.options[0]
            )
            for target_type, target_id in (
                ("character", "female_student"),
                ("board", AreaId.CITY.value),
                ("board", AreaId.SCHOOL.value),
            ):
                if (target_type, target_id) not in used_slots:
                    session.submit_place_action_card(
                        card=card,
                        target_type=target_type,
                        target_id=target_id,
                    )
                    return

        protagonist_slots = {
            (placement.target_type, placement.target_id)
            for placement in session.game_controller.state.placed_cards
            if placement.owner in {
                PlayerRole.PROTAGONIST_0,
                PlayerRole.PROTAGONIST_1,
                PlayerRole.PROTAGONIST_2,
            }
        }
        for target_id in (AreaId.CITY.value, AreaId.SCHOOL.value, AreaId.HOSPITAL.value):
            if ("board", target_id) not in protagonist_slots:
                session.submit_place_action_card(
                    card=wait.options[0],
                    target_type="board",
                    target_id=target_id,
                )
                return
        session.submit_place_action_card(
            card=wait.options[0],
            target_type="board",
            target_id=AreaId.SHRINE.value,
        )
        return

    if wait.input_type == "respond_goodwill_ability":
        session.submit_goodwill_response(allow=True)
        return

    if "pass" in wait.options:
        session.submit_pass()
        return

    if not wait.options:
        session.submit_confirm()
        return

    session.submit_input(wait.options[0])
