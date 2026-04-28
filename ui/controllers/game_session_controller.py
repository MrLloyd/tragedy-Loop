from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

from engine.display_names import (
    card_name,
    character_name,
    display_target_name,
    identity_name,
    incident_name,
    outcome_name,
    phase_name,
    player_name,
    revealed_incident_message,
    revealed_identity_message,
    token_name,
)
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


@dataclass
class SessionViewState:
    current_phase: GamePhase | None = None
    protagonist_visible_state: VisibleGameState | None = None
    mastermind_visible_state: VisibleGameState | None = None
    current_wait: WaitForInput | None = None
    protagonist_announcements: list[str] = field(default_factory=list)
    mastermind_announcements: list[str] = field(default_factory=list)
    revealed_identity_messages: list[str] = field(default_factory=list)
    revealed_incident_messages: list[str] = field(default_factory=list)
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
        self._is_submitting = False

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
        phase_line = f"阶段切换：{phase_name(phase.value)}"
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
        if self._is_submitting:
            raise RuntimeError("Input submission is already in progress")
        current_wait = self.view_state.current_wait
        if current_wait is None:
            raise RuntimeError("No current WaitForInput to respond to")
        runtime = self._runtime_snapshot_for_submit(current_wait)
        pending_wait_id = int(runtime["pending_wait_id"])
        if not runtime["has_pending_callback"]:
            raise RuntimeError("Current input is stale: engine has no pending callback")
        if current_wait.wait_id != pending_wait_id:
            raise RuntimeError(
                f"Current input is stale: wait_id={current_wait.wait_id}, pending_wait_id={pending_wait_id}"
            )
        self.view_state.current_wait = None
        self._is_submitting = True
        try:
            self.game_controller.provide_input(choice)
        except Exception:
            self.view_state.current_wait = current_wait
            self._notify_state_updated()
            raise
        finally:
            self._is_submitting = False

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
            "wait_id": wait.wait_id,
            "options": [self._format_wait_option(option) for option in wait.options],
            "has_callback": wait.callback is not None,
            "engine_has_pending_callback": controller._pending_callback is not None,
        } if wait is not None else None
        snapshot["engine_runtime"] = controller.get_runtime_debug_snapshot()
        snapshot["public_script"] = controller.state.script.public_table.to_dict()
        snapshot["private_script"] = {
            "module_id": controller.state.script.private_table.module_id,
            "loop_count": controller.state.script.private_table.loop_count,
            "days_per_loop": controller.state.script.private_table.days_per_loop,
            "rule_y_id": controller.state.script.private_table.rule_y.rule_id if controller.state.script.private_table.rule_y is not None else "",
            "rule_x_ids": [rule.rule_id for rule in controller.state.script.private_table.rules_x],
            "incidents": [
                {
                    "incident_id": incident.incident_id,
                    "day": incident.day,
                    "perpetrator_id": incident.perpetrator_id,
                    "target_selectors": list(incident.target_selectors),
                    "target_character_ids": list(incident.target_character_ids),
                    "target_area_ids": list(incident.target_area_ids),
                    "chosen_token_types": list(incident.chosen_token_types),
                }
                for incident in controller.state.script.private_table.incidents
            ],
        }
        snapshot["script"] = dict(snapshot["private_script"])
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

    def _runtime_snapshot_for_submit(self, current_wait: WaitForInput) -> dict[str, Any]:
        controller = self.game_controller
        if controller is None:
            return {"has_pending_callback": False, "pending_wait_id": 0}
        getter = getattr(controller, "get_runtime_debug_snapshot", None)
        if callable(getter):
            return getter()
        return {
            "has_pending_callback": True,
            "pending_wait_id": current_wait.wait_id,
        }

    @staticmethod
    def _format_wait_option(option: Any) -> str:
        if isinstance(option, str):
            if option == "pass":
                return "放弃 / 结束声明"
            if option in {"goodwill", "paranoia", "intrigue", "hope", "despair", "guard"}:
                return token_name(option)
            return display_target_name(option)
        if isinstance(option, dict):
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
            reveal_message = self._format_revealed_identity_message(event)
            if reveal_message:
                self.view_state.revealed_identity_messages.append(reveal_message)
            incident_reveal_message = self._format_revealed_incident_message(event)
            if incident_reveal_message:
                self.view_state.revealed_incident_messages.append(incident_reveal_message)
            message = self._format_mastermind_event(event)
            if message:
                self.view_state.mastermind_announcements.append(message)
        self._last_event_log_index = len(log)

    def _notify_state_updated(self) -> None:
        if self._state_updated_callback is not None:
            self._state_updated_callback()

    @staticmethod
    def _format_mastermind_event(event: GameEvent) -> str:
        event_name = _EVENT_TYPE_NAMES.get(event.event_type.name, event.event_type.name)
        details = ", ".join(
            f"{_EVENT_DATA_KEY_NAMES.get(key, key)}={_format_event_value(key, value)}"
            for key, value in sorted(event.data.items())
        )
        return f"{event_name}: {details}" if details else event_name

    @staticmethod
    def _format_revealed_identity_message(event: GameEvent) -> str:
        if event.event_type.name != "IDENTITY_REVEALED":
            return ""
        character_id = str(event.data.get("character_id", "") or "")
        identity_id = str(event.data.get("identity_id", "") or "")
        if not character_id or not identity_id:
            return ""
        return revealed_identity_message(character_id, identity_id)

    @staticmethod
    def _format_revealed_incident_message(event: GameEvent) -> str:
        if event.event_type.name != "INCIDENT_REVEALED":
            return ""
        incident_id = str(event.data.get("incident_id", "") or "")
        perpetrator_id = str(event.data.get("perpetrator_id", "") or "")
        if not incident_id or not perpetrator_id:
            return ""
        return revealed_incident_message(incident_id, perpetrator_id)


_EVENT_TYPE_NAMES = {
    "CHARACTER_DEATH": "角色死亡",
    "CHARACTER_REVIVED": "角色复活",
    "CHARACTER_MOVED": "角色移动",
    "CHARACTER_REMOVED": "角色移除",
    "TOKEN_CHANGED": "标记物变化",
    "PROTAGONIST_DEATH": "主人公死亡",
    "PROTAGONIST_FAILURE": "主人公失败",
    "LOOP_END_FORCED": "强制结束轮回",
    "IDENTITY_REVEALED": "身份公开",
    "INCIDENT_REVEALED": "当事人公开",
    "INCIDENT_OCCURRED": "事件发生",
    "RULE_X_REVEALED": "规则 X 公开",
    "PHASE_CHANGED": "阶段切换",
    "LOOP_STARTED": "轮回开始",
    "LOOP_ENDED": "轮回结束",
    "GAME_ENDED": "游戏结束",
    "ABILITY_DECLARED": "能力声明",
    "ABILITY_REFUSED": "能力被拒绝",
    "EX_GAUGE_CHANGED": "EX 槽变化",
    "WORLD_MOVED": "世界移动",
}

_EVENT_DATA_KEY_NAMES = {
    "ability_id": "能力",
    "cause": "原因",
    "character_id": "角色",
    "delta": "变化",
    "destination": "目的地",
    "identity_id": "身份",
    "incident_id": "事件",
    "rule_x_id": "规则 X",
    "loop": "轮回",
    "new_value": "新值",
    "other_character_id": "死亡角色",
    "outcome": "结果",
    "phase": "阶段",
    "perpetrator_id": "当事人",
    "reason": "原因",
    "source_kind": "来源类型",
    "target_id": "目标",
    "timing": "时点",
    "token_type": "标记物",
}


def _format_event_value(key: str, value: Any) -> str:
    if key in {"character_id", "target_id", "other_character_id", "perpetrator_id"}:
        return display_target_name(str(value))
    if key == "destination":
        return display_target_name(str(value))
    if key == "identity_id":
        return identity_name(str(value))
    if key == "incident_id":
        return incident_name(str(value))
    if key == "outcome":
        return outcome_name(str(value))
    if key == "phase":
        return phase_name(str(value))
    if key == "player":
        return player_name(str(value))
    if key == "token_type":
        return token_name(str(value))
    if key == "source_kind":
        return {"character": "角色", "rule": "规则", "incident": "事件"}.get(str(value), str(value))
    return str(value)
