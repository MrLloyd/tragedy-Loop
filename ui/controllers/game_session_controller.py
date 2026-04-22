from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

from engine.display_names import card_name, character_name, display_target_name
from engine.debug import DebugSession, get_debug_snapshot
from engine.event_bus import GameEvent
from engine.game_controller import GameController, UICallback
from engine.models.cards import ActionCard, PlacementIntent
from engine.models.enums import GamePhase, Outcome, PlayerRole
from engine.phases.phase_base import WaitForInput
from engine.resolvers.ability_resolver import AbilityResolver
from engine.resolvers.incident_resolver import IncidentResolver
from engine.visibility import VisibleGameState

if TYPE_CHECKING:
    from ui.screens.new_game_screen import NewGameScreenModel

try:  # pragma: no cover - optional in test env
    from PySide6.QtWidgets import QApplication
except Exception:  # pragma: no cover
    QApplication = None  # type: ignore[assignment]


@dataclass
class SessionViewState:
    current_phase: GamePhase | None = None
    protagonist_visible_state: VisibleGameState | None = None
    mastermind_visible_state: VisibleGameState | None = None
    current_wait: WaitForInput | None = None
    protagonist_announcements: list[str] = field(default_factory=list)
    mastermind_announcements: list[str] = field(default_factory=list)
    outcome: Outcome | None = None

    @property
    def visible_state(self) -> VisibleGameState | None:
        return self.protagonist_visible_state

    @property
    def announcements(self) -> list[str]:
        return self.protagonist_announcements


class GameSessionController(UICallback):
    """UI ↔ engine 最小适配器；只走 `UICallback` 与 `provide_input`。"""

    def __init__(self) -> None:
        self.game_controller: GameController | None = None
        self.view_state = SessionViewState()
        self.new_game_model: NewGameScreenModel | None = None
        self._state_updated_callback: Callable[[], None] | None = None
        self._last_event_log_index = 0

    def bind(self, controller: GameController) -> None:
        self.game_controller = controller
        self._last_event_log_index = len(controller.event_bus.log)

    def bind_new_game_model(self, model: NewGameScreenModel) -> None:
        self.new_game_model = model

    def set_state_updated_callback(self, callback: Callable[[], None] | None) -> None:
        self._state_updated_callback = callback

    def on_phase_changed(self, phase: GamePhase, visible_state: VisibleGameState) -> None:
        self.view_state.current_phase = phase
        self.view_state.protagonist_visible_state = visible_state
        if self.game_controller is not None:
            self.view_state.mastermind_visible_state = self.game_controller.get_visible_state(PlayerRole.MASTERMIND)
        phase_line = f"阶段切换：{phase.value}"
        if not self.view_state.protagonist_announcements or self.view_state.protagonist_announcements[-1] != phase_line:
            self.view_state.protagonist_announcements.append(phase_line)
        if not self.view_state.mastermind_announcements or self.view_state.mastermind_announcements[-1] != phase_line:
            self.view_state.mastermind_announcements.append(phase_line)
        self._notify_state_updated()

    def on_state_changed(
        self,
        protagonist_visible_state: VisibleGameState,
        mastermind_visible_state: VisibleGameState,
    ) -> None:
        self.view_state.protagonist_visible_state = protagonist_visible_state
        self.view_state.mastermind_visible_state = mastermind_visible_state
        self._consume_event_log_updates()
        self._notify_state_updated()

    def on_wait_for_input(self, wait: WaitForInput) -> None:
        self.view_state.current_wait = wait
        if wait.input_type == "script_setup" and self.new_game_model is not None:
            self.new_game_model.apply_wait_context(wait.context)
        self._notify_state_updated()

    def on_announcement(self, text: str) -> None:
        self.view_state.protagonist_announcements.append(text)
        self._notify_state_updated()

    def on_game_over(self, outcome: Outcome) -> None:
        self.view_state.outcome = outcome
        self.view_state.current_wait = None
        self._notify_state_updated()

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
        current_wait = self.view_state.current_wait
        if current_wait is None:
            raise RuntimeError("No current WaitForInput to respond to")
        self.view_state.current_wait = None
        try:
            self.game_controller.provide_input(choice)
        except Exception:
            self.view_state.current_wait = current_wait
            self._notify_state_updated()
            raise

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
        snapshot = get_debug_snapshot(debug_session)
        wait = self.view_state.current_wait
        snapshot["current_wait"] = {
            "input_type": wait.input_type,
            "prompt": wait.prompt,
            "player": wait.player,
            "options": [self._format_wait_option(option) for option in wait.options],
        } if wait is not None else None
        snapshot["script"] = {
            "module_id": controller.state.script.module_id,
            "loop_count": controller.state.script.loop_count,
            "days_per_loop": controller.state.script.days_per_loop,
            "rule_y_id": controller.state.script.rule_y.rule_id if controller.state.script.rule_y is not None else "",
            "rule_x_ids": [rule.rule_id for rule in controller.state.script.rules_x],
            "incidents": [
                {
                    "incident_id": incident.incident_id,
                    "day": incident.day,
                    "perpetrator_id": incident.perpetrator_id,
                    "target_character_ids": list(incident.target_character_ids),
                    "target_area_ids": list(incident.target_area_ids),
                    "chosen_token_types": list(incident.chosen_token_types),
                }
                for incident in controller.state.script.incidents
            ],
        }
        return snapshot

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

    def _consume_event_log_updates(self) -> None:
        if self.game_controller is None:
            return
        log = self.game_controller.event_bus.log
        for event in log[self._last_event_log_index:]:
            message = self._format_mastermind_event(event)
            if message:
                self.view_state.mastermind_announcements.append(message)
        self._last_event_log_index = len(log)

    def _notify_state_updated(self) -> None:
        if self._state_updated_callback is not None:
            self._state_updated_callback()
        if QApplication is not None:
            app = QApplication.instance()
            if app is not None:
                app.processEvents()

    @staticmethod
    def _format_mastermind_event(event: GameEvent) -> str:
        event_name = event.event_type.name
        details = ", ".join(
            f"{key}={value}"
            for key, value in sorted(event.data.items())
        )
        return f"{event_name}: {details}" if details else event_name
