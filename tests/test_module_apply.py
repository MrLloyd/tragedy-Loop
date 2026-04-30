"""模组装配到 GameState 与 has_final_guess 行为"""

from __future__ import annotations

from engine.game_controller import GameController, UICallback
from engine.game_state import GameState
from engine.models.enums import GamePhase, Outcome, PlayerRole
from engine.models.incident import IncidentSchedule
from engine.models.script import CharacterSetup
from engine.phases.phase_base import WaitForInput
from engine.rules.module_loader import (
    apply_loaded_module,
    build_game_state_from_module,
    load_module,
)
from ui.controllers.new_game_controller import NewGameController, default_phase5_draft


def test_apply_loaded_module_first_steps_sets_module_def_and_defs() -> None:
    state = GameState()
    loaded = load_module("first_steps")

    apply_loaded_module(state, loaded)

    assert state.module_def is loaded.module_def
    assert state.module_def.module_id == "first_steps"
    assert state.script.module_id == "first_steps"
    assert state.module_def.has_final_guess is False
    assert state.has_final_guess is False
    assert len(state.identity_defs) > 0
    assert state.ex_gauge_resets_per_loop == loaded.module_def.ex_gauge_resets_per_loop
    assert state.script.special_rules_text == list(loaded.module_def.special_rules)


def test_apply_loaded_module_basic_tragedy_x_has_final_guess_true() -> None:
    state = GameState()
    loaded = load_module("basic_tragedy_x")

    apply_loaded_module(state, loaded)

    assert state.module_def.has_final_guess is True
    assert state.has_final_guess is True


def test_game_state_default_has_final_guess_when_no_module() -> None:
    state = GameState()
    assert state.module_def is None
    assert state.has_final_guess is True


def test_build_game_state_from_module_first_steps() -> None:
    state = build_game_state_from_module("first_steps", loop_count=1, days_per_loop=1)
    assert state.module_def is not None
    assert state.module_def.module_id == "first_steps"
    assert state.script.loop_count == 1
    assert state.script.days_per_loop == 1
    assert len(state.protagonist_hands) == 3


def test_runtime_reads_private_script_table_while_visibility_reads_public_script_table() -> None:
    state = GameState.create_minimal_test_state(loop_count=2, days_per_loop=3)
    state.script.public_table.module_id = "public_only"
    state.script.public_table.loop_count = 9
    state.script.public_table.days_per_loop = 8
    state.script.public_table.special_rules = ["公开规则"]

    assert state.max_loops == 2
    assert state.max_days == 3

    visible = GameController().visibility.filter_for_role(state, PlayerRole.PROTAGONIST_0)
    assert visible.public_info["module_id"] == "public_only"
    assert visible.public_info["loop_count"] == 9
    assert visible.public_info["days_per_loop"] == 8
    assert visible.public_info["special_rules"] == ["公开规则"]


def test_script_public_incident_ref_defaults_to_private_incident_index() -> None:
    state = build_game_state_from_module(
        "basic_tragedy_x",
        loop_count=1,
        days_per_loop=3,
        incidents=[IncidentSchedule("suicide", day=3, perpetrator_id="female_student")],
    )
    state.script.private_table.public_incident_refs = []

    assert state.script.private_incident_ref_for_public_index(0) == "suicide"


def test_start_game_waits_for_script_setup_without_instance_input() -> None:
    controller = GameController()
    controller.start_game("first_steps", loop_count=1, days_per_loop=1)
    assert controller.state.module_def is not None
    assert controller.state_machine.current_phase == GamePhase.GAME_PREPARE
    assert controller._pending_callback is not None


def test_start_game_reaches_playable_phase_with_prepared_script() -> None:
    draft = default_phase5_draft()
    payload = NewGameController.build_payload(draft)

    controller = GameController()
    controller.start_game(
        payload["module_id"],
        loop_count=payload["loop_count"],
        days_per_loop=payload["days_per_loop"],
        character_setups=payload["character_setups"],
        incidents=payload["incidents"],
        rule_y_id=payload["rule_y_id"],
        rule_x_ids=payload["rule_x_ids"],
    )

    assert controller.state.module_def is not None
    assert controller.state_machine.current_phase == GamePhase.MASTERMIND_ACTION


class _FinalGuessUI(UICallback):
    def __init__(self) -> None:
        self.waits: list[WaitForInput] = []
        self.outcomes: list[Outcome] = []

    def on_wait_for_input(self, wait: WaitForInput) -> None:
        self.waits.append(wait)

    def on_game_over(self, outcome: Outcome) -> None:
        self.outcomes.append(outcome)


def test_final_guess_correct_guess_leads_to_protagonist_win() -> None:
    ui = _FinalGuessUI()
    controller = GameController(ui_callback=ui)
    controller.state = build_game_state_from_module(
        "basic_tragedy_x",
        loop_count=1,
        days_per_loop=1,
        rule_y_id="btx_murder_plan",
        rule_x_ids=["btx_rumors", "btx_latent_serial_killer"],
        character_setups=[
            CharacterSetup("male_student", "mastermind"),
            CharacterSetup("female_student", "key_person"),
            CharacterSetup("idol", "rumormonger"),
            CharacterSetup("office_worker", "killer"),
            CharacterSetup("shrine_maiden", "serial_killer"),
            CharacterSetup("doctor", "friend"),
        ],
        incidents=[],
    )
    controller.state.failure_flags.add("loop_failed")
    controller.state_machine.current_phase = GamePhase.FINAL_GUESS

    controller._run_phase()

    wait = ui.waits[-1]
    controller.provide_input(
        {
            "rule_y_id": "btx_murder_plan",
            "rule_x_ids": ["btx_rumors", "btx_latent_serial_killer"],
            "character_identities": {
                character.character_id: character.identity_id
                for character in controller.state.characters.values()
            },
        }
    )

    assert wait.input_type == "final_guess"
    assert controller.state.final_guess_correct is True
    assert ui.outcomes[-1] == Outcome.PROTAGONIST_WIN
