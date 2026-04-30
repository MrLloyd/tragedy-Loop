"""惨剧轮回 — 游戏控制器

调度中枢：协调状态机、阶段处理器、结算引擎。

核心循环：
  1. 状态机决定当前阶段
  2. 阶段处理器执行逻辑，返回信号
  3. 根据信号推进、挂起或跳转
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from engine.event_bus import EventBus, GameEvent, GameEventType
from engine.game_state import GameState
from engine.models.enums import AreaId, GamePhase, Outcome
from engine.models.incident import IncidentSchedule
from engine.models.script import CharacterSetup
from engine.phases.phase_base import (
    ForceLoopEnd, PhaseComplete, PhaseHandler, PhaseSignal, WaitForInput,
    create_phase_handlers,
)
from engine.resolvers.atomic_resolver import AtomicResolver
from engine.resolvers.death_resolver import DeathResolver
from engine.rules.persistent_effects import settle_persistent_effects
from engine.state_machine import StateMachine
from engine.visibility import Visibility, VisibleGameState


# ---------------------------------------------------------------------------
# UI 回调接口
# ---------------------------------------------------------------------------
class UICallback:
    """UI 层需要实现的回调接口"""

    def on_phase_changed(self, phase: GamePhase, visible_state: VisibleGameState) -> None:
        """阶段切换通知"""
        pass

    def on_wait_for_input(self, wait: WaitForInput) -> None:
        """引擎挂起，等待玩家输入"""
        pass

    def on_state_changed(
        self,
        protagonist_visible_state: VisibleGameState,
        mastermind_visible_state: VisibleGameState,
    ) -> None:
        """状态变化通知（用于原子结算后的即时刷新）"""
        pass

    def on_announcement(self, text: str) -> None:
        """结算公告"""
        pass

    def on_game_over(self, outcome: Outcome) -> None:
        """游戏结束"""
        pass


@dataclass
class RuntimeDebugState:
    current_signal: str = ""
    input_in_progress: bool = False
    has_pending_callback: bool = False
    pending_wait_id: int = 0
    last_input_summary: str = ""
    last_error: str = ""
    trace_tail: deque[str] = field(default_factory=lambda: deque(maxlen=50))


# ---------------------------------------------------------------------------
# GameController — 游戏控制器
# ---------------------------------------------------------------------------
class GameController:

    def __init__(self, ui_callback: Optional[UICallback] = None) -> None:
        # 核心组件
        self.event_bus = EventBus()
        self.death_resolver = DeathResolver()
        self.atomic_resolver = AtomicResolver(self.event_bus, self.death_resolver)
        self.state_machine = StateMachine()
        self.state = GameState()
        self.visibility = Visibility()

        # 阶段处理器
        self.phase_handlers = create_phase_handlers(
            self.event_bus, self.atomic_resolver
        )

        # UI
        self.ui_callback = ui_callback or UICallback()

        # 当前挂起的回调
        self._pending_callback: Optional[Callable] = None
        self._wait_sequence = 0
        self.runtime_debug = RuntimeDebugState()
        self._wire_ui_announcements()

    # ==================================================================
    # 游戏生命周期
    # ==================================================================

    def start_game(
        self,
        module_id: str,
        *,
        loop_count: int | None = None,
        days_per_loop: int | None = None,
        character_setups: list[CharacterSetup] | None = None,
        incidents: list[IncidentSchedule] | None = None,
        rule_y_id: str | None = None,
        rule_x_ids: list[str] | None = None,
    ) -> None:
        """从 `data/modules/{module_id}.json` 加载并开局。"""
        from engine.rules.module_loader import build_game_state_from_module

        self.state = build_game_state_from_module(
            module_id,
            loop_count=loop_count,
            days_per_loop=days_per_loop,
            character_setups=character_setups,
            incidents=incidents,
            rule_y_id=rule_y_id,
            rule_x_ids=rule_x_ids,
            skip_script_validation=(
                character_setups is None
                or incidents is None
                or rule_y_id is None
                or rule_x_ids is None
            ),
        )
        self.state_machine.reset()
        self.state.current_phase = GamePhase.GAME_PREPARE
        self._run_phase()

    def provide_input(self, choice: Any) -> None:
        """
        玩家提供输入（响应 WaitForInput）。

        由 UI 层调用，将玩家选择传回引擎继续执行。
        """
        if self._pending_callback is None:
            self._record_runtime_error("provide_input without pending callback")
            raise RuntimeError("No pending input callback; engine is not waiting for input")

        callback = self._pending_callback
        self._pending_callback = None
        self.runtime_debug.input_in_progress = True
        self.runtime_debug.has_pending_callback = False
        self.runtime_debug.last_input_summary = self._summarize_input(choice)
        self._append_trace(
            f"provide_input wait#{self.runtime_debug.pending_wait_id} {self.runtime_debug.last_input_summary}"
        )
        try:
            result = callback(choice)
        except Exception:
            self._pending_callback = callback
            self.runtime_debug.has_pending_callback = True
            self._record_runtime_error("callback raised; restored pending callback")
            raise
        finally:
            self.runtime_debug.input_in_progress = False
        if result is not None:
            self._handle_signal(result)

    # ==================================================================
    # 核心调度循环
    # ==================================================================

    def _run_phase(self) -> None:
        """执行当前阶段并处理返回信号"""
        phase = self.state_machine.current_phase
        self.state.current_phase = phase
        self._append_trace(f"run_phase {phase.value}")
        settle_persistent_effects(self.state)
        self._sync_entry_characters_for_phase(phase)

        # 通知 UI
        self._notify_phase_change()

        # 阶段变更事件
        self.event_bus.emit(GameEvent(GameEventType.PHASE_CHANGED, {"phase": phase.value}))

        # 游戏结束检查
        if phase == GamePhase.GAME_END:
            self._handle_game_end()
            return

        # NEXT_LOOP：重置状态后自动推进
        if phase == GamePhase.NEXT_LOOP:
            self.state.reset_for_new_loop()
            self._sync_entry_characters_for_phase(GamePhase.LOOP_START)
            self.event_bus.emit(GameEvent(GameEventType.LOOP_STARTED, {"loop": self.state.current_loop}))
            self._advance_and_run()
            return

        # 获取阶段处理器
        handler = self.phase_handlers.get(phase)
        if handler is None:
            # 无处理器的阶段直接推进
            self._advance_and_run()
            return

        # 执行阶段逻辑
        signal = handler.execute(self.state)
        self._handle_signal(signal)

    def _handle_signal(self, signal: PhaseSignal) -> None:
        """处理阶段返回信号"""
        self.runtime_debug.current_signal = type(signal).__name__
        self._append_trace(f"handle_signal {self.runtime_debug.current_signal}")
        match signal:
            case PhaseComplete():
                self.runtime_debug.last_error = ""
                self.runtime_debug.has_pending_callback = False
                self.runtime_debug.pending_wait_id = 0
                self._advance_and_run()

            case WaitForInput() as wait:
                if wait.callback is None:
                    self._record_runtime_error(f"WaitForInput({wait.input_type}) missing callback")
                    raise RuntimeError(
                        f"WaitForInput({wait.input_type}) missing callback"
                    )
                self._wait_sequence += 1
                wait.wait_id = self._wait_sequence
                self._pending_callback = wait.callback
                self.runtime_debug.has_pending_callback = True
                self.runtime_debug.pending_wait_id = wait.wait_id
                self.runtime_debug.last_error = ""
                self._append_trace(
                    f"wait #{wait.wait_id} {wait.input_type} player={wait.player}"
                )
                self.ui_callback.on_wait_for_input(wait)

            case ForceLoopEnd() as fle:
                self.runtime_debug.last_error = ""
                self.runtime_debug.has_pending_callback = False
                self.runtime_debug.pending_wait_id = 0
                self._append_trace(f"force_loop_end {fle.reason}")
                self.event_bus.emit(GameEvent(
                    GameEventType.LOOP_END_FORCED,
                    {"reason": fle.reason},
                ))
                self.state_machine.force_loop_end()
                self._advance_and_run()

    def get_runtime_debug_snapshot(self) -> dict[str, Any]:
        return {
            "engine_phase": self.state_machine.current_phase.value,
            "state_current_phase": self.state.current_phase.value,
            "current_signal": self.runtime_debug.current_signal,
            "input_in_progress": self.runtime_debug.input_in_progress,
            "has_pending_callback": self.runtime_debug.has_pending_callback,
            "pending_wait_id": self.runtime_debug.pending_wait_id,
            "last_input_summary": self.runtime_debug.last_input_summary,
            "last_error": self.runtime_debug.last_error,
            "trace_tail": list(self.runtime_debug.trace_tail),
        }

    def _append_trace(self, message: str) -> None:
        self.runtime_debug.trace_tail.append(message)

    def _sync_entry_characters_for_phase(self, phase: GamePhase) -> None:
        if phase == GamePhase.GAME_PREPARE:
            deity = self.state.characters.get("deity")
            if deity is not None and (deity.entry_loop or 0) > 0:
                deity.mark_removed()
            transfer_student = self.state.characters.get("transfer_student")
            if transfer_student is not None and transfer_student.entry_day:
                transfer_student.mark_removed()
            return
        if phase == GamePhase.LOOP_START:
            deity = self.state.characters.get("deity")
            if deity is not None:
                entry_loop = deity.entry_loop or 0
                if entry_loop > 0 and self.state.current_loop >= entry_loop:
                    deity.mark_alive()
                else:
                    deity.mark_removed()

            transfer_student = self.state.characters.get("transfer_student")
            if transfer_student is not None and transfer_student.entry_day:
                transfer_student.mark_removed()
            return

        if phase == GamePhase.TURN_START:
            transfer_student = self.state.characters.get("transfer_student")
            if transfer_student is not None:
                entry_day = transfer_student.entry_day or 0
                if entry_day > 0 and self.state.current_day >= entry_day:
                    transfer_student.mark_alive()
                elif entry_day > 0:
                    transfer_student.mark_removed()

            temp_worker = self.state.characters.get("temp_worker")
            temp_worker_alt = self.state.characters.get("temp_worker_alt")
            if temp_worker is not None and temp_worker_alt is not None and temp_worker.is_dead():
                temp_worker_alt.mark_alive()
                temp_worker_alt.area = AreaId.CITY

    def _record_runtime_error(self, message: str) -> None:
        self.runtime_debug.last_error = message
        self._append_trace(f"error {message}")

    @staticmethod
    def _summarize_input(choice: Any) -> str:
        if choice is None:
            return "None"
        if isinstance(choice, str):
            return choice
        target_type = getattr(choice, "target_type", None)
        target_id = getattr(choice, "target_id", None)
        if target_type is not None and target_id is not None:
            card = getattr(choice, "card", None)
            card_type = getattr(card, "card_type", None)
            card_name = getattr(card_type, "value", str(card_type)) if card_type is not None else "unknown_card"
            return f"{card_name}:{target_type}:{target_id}"
        if isinstance(choice, dict):
            return f"dict(keys={sorted(choice.keys())})"
        if isinstance(choice, list):
            return f"list(len={len(choice)})"
        return type(choice).__name__

    def _advance_and_run(self) -> None:
        """推进状态机并执行下一阶段"""
        prev_phase = self.state_machine.current_phase  # 保存推进前的阶段

        phase = self.state_machine.advance(
            is_final_day=(self.state.current_day >= self.state.max_days),
            failure_reached=bool(self.state.failure_flags),
            is_last_loop=self.state.is_last_loop,
            protagonist_dead=self.state.protagonist_dead,
            has_final_guess=self.state.has_final_guess,
        )

        # 推进日期：从 TURN_END 推进到 TURN_START 时，说明开始新的一天
        if prev_phase == GamePhase.TURN_END and phase == GamePhase.TURN_START:
            self.state.advance_day()

        self._run_phase()

    # ==================================================================
    # 游戏结束
    # ==================================================================

    def _handle_game_end(self) -> None:
        """判定最终胜负"""
        if self.state.final_guess_correct is True:
            outcome = Outcome.PROTAGONIST_WIN
        elif self.state.final_guess_correct is False:
            outcome = Outcome.MASTERMIND_WIN
        elif self.state.protagonist_dead:
            outcome = Outcome.MASTERMIND_WIN
        elif self.state.failure_flags:
            outcome = Outcome.MASTERMIND_WIN
        else:
            outcome = Outcome.PROTAGONIST_WIN

        self.event_bus.emit(GameEvent(GameEventType.GAME_ENDED, {"outcome": outcome.value}))
        self.ui_callback.on_game_over(outcome)

    # ==================================================================
    # UI 通知
    # ==================================================================

    def _notify_phase_change(self) -> None:
        """通知 UI 阶段变化"""
        # 默认使用主人公视角（热座模式下由 UI 层决定当前视角）
        from engine.models.enums import PlayerRole
        visible = self.visibility.filter_for_role(
            self.state, PlayerRole.PROTAGONIST_0
        )
        mastermind_visible = self.visibility.filter_for_role(
            self.state, PlayerRole.MASTERMIND
        )
        self.ui_callback.on_phase_changed(
            self.state_machine.current_phase, visible
        )
        self.ui_callback.on_state_changed(visible, mastermind_visible)

    def _wire_ui_announcements(self) -> None:
        event_map = {
            GameEventType.TOKEN_CHANGED: "token_change",
            GameEventType.CHARACTER_DEATH: "character_death",
            GameEventType.CHARACTER_MOVED: "character_move",
            GameEventType.PROTAGONIST_DEATH: "protagonist_death",
            GameEventType.PROTAGONIST_FAILURE: "protagonist_failure",
            GameEventType.IDENTITY_REVEALED: "reveal_identity",
            GameEventType.INCIDENT_REVEALED: "reveal_incident",
            GameEventType.INCIDENT_OCCURRED: "incident_occurred",
            GameEventType.INCIDENT_PHENOMENON_REPORTED: "incident_phenomenon",
            GameEventType.RULE_X_REVEALED: "reveal_rule_x",
            GameEventType.LOOP_ENDED: "loop_ended",
            GameEventType.GAME_ENDED: "game_ended",
            GameEventType.ABILITY_REFUSED: "ability_refused",
        }
        state_update_events = {
            GameEventType.TOKEN_CHANGED,
            GameEventType.CHARACTER_DEATH,
            GameEventType.CHARACTER_MOVED,
            GameEventType.PROTAGONIST_DEATH,
            GameEventType.PROTAGONIST_FAILURE,
            GameEventType.IDENTITY_REVEALED,
            GameEventType.INCIDENT_REVEALED,
            GameEventType.INCIDENT_OCCURRED,
            GameEventType.INCIDENT_PHENOMENON_REPORTED,
            GameEventType.RULE_X_REVEALED,
            GameEventType.LOOP_STARTED,
            GameEventType.LOOP_ENDED,
            GameEventType.GAME_ENDED,
            GameEventType.ABILITY_DECLARED,
            GameEventType.ABILITY_REFUSED,
        }
        for event_type, announcement_type in event_map.items():
            self.event_bus.subscribe(
                event_type,
                lambda event, announcement_type=announcement_type: self._forward_announcement(
                    announcement_type,
                    event.data,
                ),
            )
        for event_type in state_update_events:
            self.event_bus.subscribe(
                event_type,
                lambda _event: self._notify_state_changed(),
            )

    def _forward_announcement(self, announcement_type: str, details: dict[str, Any]) -> None:
        text = Visibility.create_announcement(announcement_type, details)
        if text:
            self.ui_callback.on_announcement(text)

    def _notify_state_changed(self) -> None:
        from engine.models.enums import PlayerRole

        protagonist_visible = self.visibility.filter_for_role(
            self.state, PlayerRole.PROTAGONIST_0
        )
        mastermind_visible = self.visibility.filter_for_role(
            self.state, PlayerRole.MASTERMIND
        )
        self.ui_callback.on_state_changed(
            protagonist_visible,
            mastermind_visible,
        )

    def get_visible_state(self, role) -> VisibleGameState:
        """获取指定角色的可见状态"""
        return self.visibility.filter_for_role(self.state, role)
