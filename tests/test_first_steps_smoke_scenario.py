from __future__ import annotations

from engine.game_controller import GameController, UICallback
from engine.models.cards import PlacementIntent
from engine.models.enums import AreaId, CardType, GamePhase, Outcome, PlayerRole
from engine.models.incident import IncidentSchedule
from engine.models.script import CharacterSetup
from engine.phases.phase_base import WaitForInput
from engine.rules.module_loader import build_game_state_from_module


class _ScenarioUI(UICallback):
    def __init__(self) -> None:
        self.waits: list[WaitForInput] = []
        self.phases: list[GamePhase] = []
        self.outcome: Outcome | None = None

    def on_phase_changed(self, phase: GamePhase, visible_state) -> None:
        self.phases.append(phase)

    def on_wait_for_input(self, wait: WaitForInput) -> None:
        self.waits.append(wait)

    def on_game_over(self, outcome: Outcome) -> None:
        self.outcome = outcome


def test_first_steps_three_loop_three_day_suicide_scenario_closes() -> None:
    state = build_game_state_from_module(
        "first_steps",
        loop_count=3,
        days_per_loop=3,
        rule_y_id="fs_murder_plan",
        rule_x_ids=["fs_ripper_shadow"],
        character_setups=[
            CharacterSetup("male_student", "mastermind"),
            CharacterSetup("female_student", "key_person"),
            CharacterSetup("idol", "rumormonger"),
            CharacterSetup("office_worker", "killer"),
            CharacterSetup("shrine_maiden", "serial_killer"),
        ],
        incidents=[
            IncidentSchedule("suicide", day=3, perpetrator_id="female_student"),
        ],
    )
    ui = _ScenarioUI()
    controller = GameController(ui_callback=ui)
    controller.state = state
    controller.state_machine.reset()
    controller._run_phase()

    for _ in range(200):
        if controller.state_machine.current_phase == GamePhase.GAME_END:
            break
        assert controller._pending_callback is not None
        wait = ui.waits[-1]
        controller.provide_input(_choice_for(wait, controller))

    assert controller.state_machine.current_phase == GamePhase.GAME_END
    assert ui.outcome == Outcome.MASTERMIND_WIN
    assert len(controller.state.loop_history) == 3
    assert all(
        snapshot.incidents_occurred == ["suicide"]
        for snapshot in controller.state.loop_history
    )
    assert GamePhase.NEXT_LOOP in ui.phases
    assert GamePhase.INCIDENT in ui.phases


def _choice_for(wait: WaitForInput, controller: GameController):
    if wait.input_type == "place_action_card":
        if wait.player == "mastermind":
            used_slots = {
                (placement.target_type, placement.target_id)
                for placement in controller.state.placed_cards
                if placement.owner == PlayerRole.MASTERMIND
            }
            card = (
                _card(wait.options, CardType.PARANOIA_PLUS_1)
                if not used_slots
                else wait.options[0]
            )
            for target_type, target_id in (
                ("character", "female_student"),
                ("board", AreaId.CITY.value),
                ("board", AreaId.SCHOOL.value),
            ):
                if (target_type, target_id) not in used_slots:
                    return PlacementIntent(card, target_type, target_id)

        protagonist_slots = {
            (placement.target_type, placement.target_id)
            for placement in controller.state.placed_cards
            if placement.owner in {
                PlayerRole.PROTAGONIST_0,
                PlayerRole.PROTAGONIST_1,
                PlayerRole.PROTAGONIST_2,
            }
        }
        for target_id in (AreaId.CITY.value, AreaId.SCHOOL.value, AreaId.HOSPITAL.value):
            if ("board", target_id) not in protagonist_slots:
                return PlacementIntent(wait.options[0], "board", target_id)
        return PlacementIntent(
            card=wait.options[0],
            target_type="board",
            target_id=AreaId.SHRINE.value,
        )
    if "pass" in wait.options:
        return "pass"
    return wait.options[0]


def _card(cards: list, card_type: CardType):
    return next(card for card in cards if card.card_type == card_type)
