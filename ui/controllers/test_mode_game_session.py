from __future__ import annotations

from typing import Any

from engine.event_bus import GameEvent
from engine.display_names import phase_name
from engine.models.enums import GamePhase, Outcome, PlayerRole
from engine.visibility import Visibility
from ui.controllers.game_session_controller import GameSessionController, SessionViewState
from ui.controllers.test_mode_controller import TestModeController


class _EmptyEventBus:
    log: list[GameEvent] = []


_EMPTY_EVENT_BUS = _EmptyEventBus()


class _TestModeGameControllerProxy:
    def __init__(self, controller: TestModeController) -> None:
        self._controller = controller

    @property
    def event_bus(self):
        session = self._controller.session
        return session.event_bus if session is not None else _EMPTY_EVENT_BUS

    @property
    def state(self):
        session = self._controller.session
        return session.state if session is not None else None

    @property
    def death_resolver(self):
        session = self._controller.session
        return session.death_resolver if session is not None else None

    @property
    def atomic_resolver(self):
        session = self._controller.session
        return session.atomic_resolver if session is not None else None

    @property
    def _pending_callback(self):
        wait = self._controller.pending_wait
        return wait.callback if wait is not None else None

    def provide_input(self, choice: Any) -> None:
        self._controller.submit_input(choice)

    def get_visible_state(self, role: PlayerRole):
        session = self._controller.session
        if session is None:
            raise RuntimeError("Test session is not ready")
        return Visibility.filter_for_role(session.state, role)

    def get_runtime_debug_snapshot(self) -> dict[str, Any]:
        return self._controller.get_runtime_debug_snapshot()


class TestModeGameSessionController(GameSessionController):
    """把测试模式阶段等待适配到正式 `GameScreen` 所需接口。"""

    def __init__(self, controller: TestModeController) -> None:
        super().__init__()
        self._test_controller = controller
        self._proxy = _TestModeGameControllerProxy(controller)
        self.game_controller = self._proxy  # type: ignore[assignment]
        self._session_marker = 0
        self._last_event_log_index = 0
        self.refresh_from_test_mode(notify=False)

    def refresh_from_test_mode(self, *, notify: bool = True) -> None:
        session = self._test_controller.session
        if session is None:
            self.view_state = SessionViewState()
            self._session_marker = 0
            self._last_event_log_index = 0
            if notify:
                self._notify_state_updated()
            return

        marker = id(session)
        if marker != self._session_marker:
            self.view_state = SessionViewState()
            self._session_marker = marker
            self._last_event_log_index = 0

        phase = self._current_phase()
        previous_phase = self.view_state.current_phase
        self.view_state.current_phase = phase
        self.view_state.protagonist_visible_state = Visibility.filter_for_role(
            session.state,
            PlayerRole.PROTAGONIST_0,
        )
        self.view_state.mastermind_visible_state = Visibility.filter_for_role(
            session.state,
            PlayerRole.MASTERMIND,
        )
        self.view_state.current_wait = self._test_controller.pending_wait
        self.view_state.outcome = self._compute_outcome(phase)
        if previous_phase != phase and phase is not None:
            phase_line = f"阶段切换：{phase_name(phase.value)}"
            self.view_state.protagonist_announcements.append(phase_line)
            self.view_state.mastermind_announcements.append(phase_line)
        self._sync_event_log_updates()
        if notify:
            self._notify_state_updated()

    def submit_input(self, choice: Any) -> None:
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
            self._test_controller.submit_input(choice)
        except Exception:
            self.view_state.current_wait = current_wait
            self.refresh_from_test_mode()
            raise
        finally:
            self._is_submitting = False
        self.refresh_from_test_mode()

    def read_debug_snapshot(self) -> dict[str, Any]:
        snapshot = self._test_controller.read_debug_snapshot()
        wait = self.view_state.current_wait
        snapshot["current_wait"] = {
            "input_type": wait.input_type,
            "prompt": wait.prompt,
            "player": wait.player,
            "wait_id": wait.wait_id,
            "options": [self._format_wait_option(option) for option in wait.options],
            "has_callback": wait.callback is not None,
            "engine_has_pending_callback": self._test_controller.pending_wait is not None,
        } if wait is not None else None
        snapshot["engine_runtime"] = self._test_controller.get_runtime_debug_snapshot()
        return snapshot

    def _runtime_snapshot_for_submit(self, current_wait) -> dict[str, Any]:
        del current_wait
        return self._test_controller.get_runtime_debug_snapshot()

    def _current_phase(self) -> GamePhase | None:
        if self._test_controller.state_machine is not None:
            return self._test_controller.state_machine.current_phase
        if self._test_controller.session is not None:
            return self._test_controller.session.state.current_phase
        return None

    def _sync_event_log_updates(self) -> None:
        controller = self.game_controller
        if controller is None:
            return
        log = controller.event_bus.log
        if len(log) < self._last_event_log_index:
            self._last_event_log_index = 0
        for event in log[self._last_event_log_index:]:
            public_message = self._format_public_event(event)
            if public_message:
                self.view_state.protagonist_announcements.append(public_message)
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

    def _compute_outcome(self, phase: GamePhase | None) -> Outcome | None:
        session = self._test_controller.session
        if session is None or phase != GamePhase.GAME_END:
            return None
        state = session.state
        if state.final_guess_correct is True:
            return Outcome.PROTAGONIST_WIN
        if state.final_guess_correct is False or state.protagonist_dead or state.failure_flags:
            return Outcome.MASTERMIND_WIN
        return Outcome.PROTAGONIST_WIN

    @staticmethod
    def _format_public_event(event: GameEvent) -> str:
        mapping = {
            "TOKEN_CHANGED": "token_change",
            "CHARACTER_DEATH": "character_death",
            "CHARACTER_MOVED": "character_move",
            "PROTAGONIST_DEATH": "protagonist_death",
            "PROTAGONIST_FAILURE": "protagonist_failure",
            "IDENTITY_REVEALED": "reveal_identity",
            "INCIDENT_REVEALED": "reveal_incident",
            "INCIDENT_OCCURRED": "incident_occurred",
            "INCIDENT_PHENOMENON_REPORTED": "incident_phenomenon",
            "LOOP_ENDED": "loop_ended",
            "GAME_ENDED": "game_ended",
            "ABILITY_REFUSED": "ability_refused",
        }
        announcement_type = mapping.get(event.event_type.name)
        if announcement_type is None:
            return ""
        return Visibility.create_announcement(announcement_type, event.data)
