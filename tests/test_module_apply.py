"""模组装配到 GameState 与 has_final_guess 行为"""

from __future__ import annotations

from engine.game_controller import GameController
from engine.game_state import GameState
from engine.models.enums import GamePhase
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
