from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from engine.display_names import card_name, character_name, display_target_name
from engine.debug import DebugSession, get_debug_snapshot
from engine.game_controller import GameController, UICallback
from engine.models.cards import ActionCard, PlacementIntent
from engine.models.enums import GamePhase, Outcome
from engine.phases.phase_base import WaitForInput
from engine.resolvers.ability_resolver import AbilityResolver
from engine.resolvers.incident_resolver import IncidentResolver
from engine.visibility import VisibleGameState

if TYPE_CHECKING:
    from ui.screens.new_game_screen import NewGameScreenModel


@dataclass
class SessionViewState:
    current_phase: GamePhase | None = None
    visible_state: VisibleGameState | None = None
    current_wait: WaitForInput | None = None
    announcements: list[str] = field(default_factory=list)
    outcome: Outcome | None = None


class GameSessionController(UICallback):
    """UI ↔ engine 最小适配器；只走 `UICallback` 与 `provide_input`。"""

    def __init__(self) -> None:
        self.game_controller: GameController | None = None
        self.view_state = SessionViewState()
        self.new_game_model: NewGameScreenModel | None = None

    def bind(self, controller: GameController) -> None:
        self.game_controller = controller

    def bind_new_game_model(self, model: NewGameScreenModel) -> None:
        self.new_game_model = model

    def on_phase_changed(self, phase: GamePhase, visible_state: VisibleGameState) -> None:
        self.view_state.current_phase = phase
        self.view_state.visible_state = visible_state

    def on_wait_for_input(self, wait: WaitForInput) -> None:
        self.view_state.current_wait = wait
        if wait.input_type == "script_setup" and self.new_game_model is not None:
            self.new_game_model.apply_wait_context(wait.context)

    def on_announcement(self, text: str) -> None:
        self.view_state.announcements.append(text)

    def on_game_over(self, outcome: Outcome) -> None:
        self.view_state.outcome = outcome
        self.view_state.current_wait = None

    def can_submit(self) -> bool:
        return self.game_controller is not None and self.view_state.current_wait is not None

    def current_wait_input_type(self) -> str | None:
        wait = self.view_state.current_wait
        return wait.input_type if wait is not None else None

    def wait_option_labels(self) -> list[str]:
        wait = self.view_state.current_wait
        if wait is None:
            return []
        return [self._format_wait_option(option) for option in wait.options]

    def submit_script_setup(self, payload: dict[str, object]) -> None:
        self._require_wait("script_setup")
        self.submit_input(payload)

    def submit_place_action_cards(
        self,
        selections: list[tuple[ActionCard, str, str]],
    ) -> None:
        wait = self.view_state.current_wait
        if wait is None:
            raise RuntimeError("No current WaitForInput to respond to")

        if wait.input_type == "place_action_cards":
            intents = [
                PlacementIntent(card=card, target_type=target_type, target_id=target_id)
                for card, target_type, target_id in selections
            ]
            self.submit_input(intents)
            return

        if wait.input_type == "place_action_card" and wait.player == "mastermind":
            for card, target_type, target_id in selections:
                self.submit_place_action_card(
                    card=card,
                    target_type=target_type,
                    target_id=target_id,
                )
            return

        raise RuntimeError(f"Current wait({wait.input_type}) does not support batch placements")

    def submit_place_action_card(
        self,
        *,
        card: ActionCard,
        target_type: str,
        target_id: str,
    ) -> None:
        self._require_wait("place_action_card")
        self.submit_input(
            PlacementIntent(card=card, target_type=target_type, target_id=target_id)
        )

    def submit_pass(self) -> None:
        wait = self.view_state.current_wait
        if wait is None:
            raise RuntimeError("No current WaitForInput to respond to")
        if "pass" not in wait.options:
            raise RuntimeError(f"Current wait({wait.input_type}) does not support pass")
        self.submit_input("pass")

    def submit_goodwill_response(self, *, allow: bool) -> None:
        self._require_wait("respond_goodwill_ability")
        self.submit_input("allow" if allow else "refuse")

    def submit_confirm(self) -> None:
        wait = self.view_state.current_wait
        if wait is None:
            raise RuntimeError("No current WaitForInput to respond to")
        if wait.options:
            raise RuntimeError(f"Current wait({wait.input_type}) requires an explicit selection")
        self.submit_input(None)

    def submit_input(self, choice: Any) -> None:
        if self.game_controller is None:
            raise RuntimeError("GameSessionController is not bound to a GameController")
        if self.view_state.current_wait is None:
            raise RuntimeError("No current WaitForInput to respond to")
        self.view_state.current_wait = None
        self.game_controller.provide_input(choice)

    def read_debug_snapshot(self) -> dict[str, Any]:
        if self.game_controller is None:
            return {}
        controller = self.game_controller
        debug_session = DebugSession(
            state=controller.state,
            event_bus=controller.event_bus,
            death_resolver=controller.death_resolver,
            atomic_resolver=controller.atomic_resolver,
            ability_resolver=AbilityResolver(),
            incident_resolver=IncidentResolver(
                controller.event_bus,
                controller.atomic_resolver,
            ),
            debug_log=[],
        )
        return get_debug_snapshot(debug_session)

    def _require_wait(self, input_type: str) -> WaitForInput:
        wait = self.view_state.current_wait
        if wait is None:
            raise RuntimeError("No current WaitForInput to respond to")
        if wait.input_type != input_type:
            raise RuntimeError(
                f"Expected wait type {input_type}, got {wait.input_type}"
            )
        return wait

    @staticmethod
    def _format_wait_option(option: Any) -> str:
        if isinstance(option, str):
            if option == "pass":
                return "放弃 / 结束声明"
            return display_target_name(option)
        card_type = getattr(option, "card_type", None)
        if card_type is not None:
            return card_name(card_type.value)
        ability = getattr(option, "ability", None)
        source_id = getattr(option, "source_id", "")
        if ability is not None and hasattr(ability, "name"):
            if source_id:
                return f"{character_name(source_id)}：{ability.name}"
            return f"ability:{ability.name}"
        return str(option)
