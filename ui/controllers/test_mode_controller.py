from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any

from engine.debug import (
    DebugCharacterSetup,
    DebugSetup,
    DebugSession,
    apply_debug_setup,
    build_debug_state,
    get_debug_snapshot,
    list_debug_abilities,
    trigger_debug_ability,
    trigger_debug_incident,
)
from engine.display_names import (
    area_name,
    character_option_label,
    incident_option_label,
    module_option_label,
    phase_name,
    rule_option_label,
    token_name,
)
from engine.models.enums import AreaId, GamePhase, TokenType
from engine.models.incident import IncidentSchedule
from engine.models.selectors import (
    area_choice_selector,
    character_choice_selector,
    selector_is_self_ref,
    selector_literal_value,
    selector_requires_choice,
)
from engine.models.script import CharacterSetup
from engine.phases.phase_base import ForceLoopEnd, PhaseComplete, WaitForInput, create_phase_handlers
from engine.rules.persistent_effects import settle_persistent_effects
from engine.rules.module_loader import build_script_setup_context
from engine.state_machine import StateMachine

TEST_MODE_LOOP_COUNT = 3
TEST_MODE_DAYS_PER_LOOP = 3


@dataclass(frozen=True)
class TestCharacterDraft:
    __test__ = False

    character_id: str
    identity_id: str = "平民"
    area: str = AreaId.CITY.value
    is_alive: bool = True
    is_removed: bool = False
    revealed: bool = False
    tokens: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class TestModeDraft:
    __test__ = False

    module_id: str = "first_steps"
    rule_y_id: str = ""
    rule_x_ids: list[str] = field(default_factory=list)
    current_loop: int = 1
    current_day: int = 1
    current_phase: str = GamePhase.PLAYWRIGHT_ABILITY.value
    characters: list[TestCharacterDraft] = field(default_factory=list)
    board_tokens: dict[str, dict[str, int]] = field(default_factory=dict)


class TestModeController:
    """测试模式最小控制器：基于受控 debug API 构造调试局。"""

    __test__ = False

    def __init__(self, module_id: str = "first_steps") -> None:
        self._context: dict[str, object] = {}
        self.draft = TestModeDraft(module_id=module_id)
        self.session: DebugSession | None = None
        self.state_machine: StateMachine | None = None
        self.phase_handlers: dict[GamePhase, Any] = {}
        self.pending_wait: WaitForInput | None = None
        self.status_message = ""
        self._wait_sequence = 0
        self._current_signal = ""
        self._input_in_progress = False
        self._last_input_summary = ""
        self._last_error = ""
        self._trace_tail: deque[str] = deque(maxlen=50)
        self.set_module(module_id)
        if not self.draft.characters:
            self.add_character()
        self.rebuild_session()

    @property
    def available_modules(self) -> list[str]:
        raw = self._context.get("available_modules", [])
        return [str(item) for item in raw] if isinstance(raw, list) else []

    @property
    def available_character_ids(self) -> list[str]:
        raw = self._context.get("available_characters", [])
        return [str(item) for item in raw] if isinstance(raw, list) else []

    @property
    def available_identity_ids(self) -> list[str]:
        raw = self._context.get("available_identities", [])
        identities = [str(item) for item in raw] if isinstance(raw, list) else []
        if "平民" not in identities:
            identities.insert(0, "平民")
        return identities

    @property
    def available_incident_ids(self) -> list[str]:
        raw = self._context.get("available_incidents", [])
        return [str(item) for item in raw] if isinstance(raw, list) else []

    def available_incident_target_options(
        self,
        *,
        incident_id: str,
        perpetrator_id: str,
        target_selectors: list[dict[str, str]] | None = None,
        target_character_ids: list[str] | None = None,
        target_area_ids: list[str] | None = None,
        chosen_token_types: list[str] | None = None,
    ) -> dict[str, list[list[tuple[str, str]]]]:
        groups: dict[str, list[list[tuple[str, str]]]] = {
            "character": [],
            "area": [],
            "token": [],
        }
        if self.session is None or not incident_id or not perpetrator_id:
            return groups

        incident_def = self.session.state.incident_defs.get(incident_id)
        if incident_def is None:
            return groups

        selected_characters = [item for item in (target_character_ids or []) if item]
        selected_areas = [item for item in (target_area_ids or []) if item]
        selected_tokens = [item for item in (chosen_token_types or []) if item]
        accepted_selectors: list[dict[str, str]] = list(target_selectors or [])
        accepted_characters: list[str] = []
        accepted_areas: list[str] = []
        accepted_tokens: list[str] = []
        character_index = 0
        area_index = 0
        token_index = 0

        for _ in range(len(incident_def.effects) + 4):
            schedule = IncidentSchedule(
                incident_id=incident_id,
                day=self.session.state.current_day,
                perpetrator_id=perpetrator_id,
                target_selectors=list(accepted_selectors),
                target_character_ids=list(accepted_characters),
                target_area_ids=list(accepted_areas),
                chosen_token_types=list(accepted_tokens),
            )
            next_choice = self.session.incident_resolver.next_runtime_choice(
                self.session.state,
                schedule,
                incident_def,
            )
            if next_choice is None:
                break

            choice_type, candidates = next_choice
            groups[choice_type].append(
                [(candidate_id, self._target_option_label(candidate_id)) for candidate_id in candidates]
            )

            if choice_type == "character":
                selected = selected_characters[character_index] if character_index < len(selected_characters) else ""
                character_index += 1
                if selected in candidates:
                    accepted_selectors.append(character_choice_selector(selected))
                    accepted_characters.append(selected)
                    continue
                break
            if choice_type == "area":
                selected = selected_areas[area_index] if area_index < len(selected_areas) else ""
                area_index += 1
                if selected in candidates:
                    accepted_selectors.append(area_choice_selector(selected))
                    accepted_areas.append(selected)
                    continue
                break
            if choice_type == "token":
                selected = selected_tokens[token_index] if token_index < len(selected_tokens) else ""
                token_index += 1
                if selected in candidates:
                    accepted_tokens.append(selected)
                    continue
                break

            break

        return groups

    @property
    def available_rule_y_ids(self) -> list[str]:
        raw = self._context.get("available_rule_y_ids", [])
        return [str(item) for item in raw] if isinstance(raw, list) else []

    @property
    def available_rule_x_ids(self) -> list[str]:
        raw = self._context.get("available_rule_x_ids", [])
        return [str(item) for item in raw] if isinstance(raw, list) else []

    @property
    def rule_x_count(self) -> int:
        raw = self._context.get("rule_x_count", 0)
        return max(0, int(raw)) if isinstance(raw, int) else 0

    @property
    def available_phase_ids(self) -> list[str]:
        return [phase.value for phase in GamePhase]

    @staticmethod
    def available_area_ids() -> list[str]:
        return [area.value for area in AreaId if area != AreaId.FARAWAY]

    @staticmethod
    def available_token_ids() -> list[str]:
        return [token.value for token in TokenType]

    def set_module(self, module_id: str) -> None:
        self._context = build_script_setup_context(
            module_id,
            loop_count=TEST_MODE_LOOP_COUNT,
            days_per_loop=TEST_MODE_DAYS_PER_LOOP,
            errors=[],
        )
        characters = self.draft.characters or []
        self.draft = TestModeDraft(
            module_id=module_id,
            rule_y_id=self._normalize_rule_y_id(self.draft.rule_y_id),
            rule_x_ids=self._normalize_rule_x_ids(self.draft.rule_x_ids),
            current_loop=self.draft.current_loop,
            current_day=self.draft.current_day,
            current_phase=self.draft.current_phase,
            characters=[self._normalize_character(item) for item in characters],
            board_tokens=self._normalize_board_tokens(self.draft.board_tokens),
        )

    def set_rules(self, *, rule_y_id: str, rule_x_ids: list[str]) -> None:
        self.draft = TestModeDraft(
            module_id=self.draft.module_id,
            rule_y_id=self._normalize_rule_y_id(rule_y_id),
            rule_x_ids=self._normalize_rule_x_ids(rule_x_ids),
            current_loop=self.draft.current_loop,
            current_day=self.draft.current_day,
            current_phase=self.draft.current_phase,
            characters=list(self.draft.characters),
            board_tokens=self._normalize_board_tokens(self.draft.board_tokens),
        )

    def set_runtime(self, *, current_loop: int, current_day: int, current_phase: str) -> None:
        self.draft = TestModeDraft(
            module_id=self.draft.module_id,
            rule_y_id=self.draft.rule_y_id,
            rule_x_ids=list(self.draft.rule_x_ids),
            current_loop=max(1, min(TEST_MODE_LOOP_COUNT, int(current_loop))),
            current_day=max(1, min(TEST_MODE_DAYS_PER_LOOP, int(current_day))),
            current_phase=current_phase,
            characters=list(self.draft.characters),
            board_tokens=self._normalize_board_tokens(self.draft.board_tokens),
        )

    def replace_characters(self, characters: list[TestCharacterDraft]) -> None:
        self.draft = TestModeDraft(
            module_id=self.draft.module_id,
            rule_y_id=self.draft.rule_y_id,
            rule_x_ids=list(self.draft.rule_x_ids),
            current_loop=self.draft.current_loop,
            current_day=self.draft.current_day,
            current_phase=self.draft.current_phase,
            characters=[self._normalize_character(item) for item in characters],
            board_tokens=self._normalize_board_tokens(self.draft.board_tokens),
        )

    def replace_board_tokens(self, board_tokens: dict[str, dict[str, int]]) -> None:
        self.draft = TestModeDraft(
            module_id=self.draft.module_id,
            rule_y_id=self.draft.rule_y_id,
            rule_x_ids=list(self.draft.rule_x_ids),
            current_loop=self.draft.current_loop,
            current_day=self.draft.current_day,
            current_phase=self.draft.current_phase,
            characters=list(self.draft.characters),
            board_tokens=self._normalize_board_tokens(board_tokens),
        )

    def add_character(self) -> None:
        character_id = self._default_character_id(exclude={item.character_id for item in self.draft.characters if item.character_id})
        if not character_id:
            return
        rows = list(self.draft.characters)
        rows.append(
            TestCharacterDraft(
                character_id=character_id,
                identity_id="平民",
                area=self._default_area_for(character_id),
                tokens={},
            )
        )
        self.replace_characters(rows)

    def remove_character(self) -> None:
        rows = list(self.draft.characters)
        if not rows:
            return
        rows.pop()
        self.replace_characters(rows)

    def rebuild_session(self) -> None:
        character_setups = [
            CharacterSetup(item.character_id, item.identity_id)
            for item in self.draft.characters
            if item.character_id
        ]
        self.session = build_debug_state(
            self.draft.module_id,
            loop_count=TEST_MODE_LOOP_COUNT,
            days_per_loop=TEST_MODE_DAYS_PER_LOOP,
            rule_y_id=self.draft.rule_y_id or None,
            rule_x_ids=[rule_id for rule_id in self.draft.rule_x_ids if rule_id] or None,
            character_setups=character_setups,
            incidents=[],
            skip_script_validation=True,
        )
        apply_debug_setup(
            self.session,
            DebugSetup(
                current_loop=self.draft.current_loop,
                current_day=self.draft.current_day,
                current_phase=self.draft.current_phase,
                characters=[
                    DebugCharacterSetup(
                        character_id=item.character_id,
                        area=item.area,
                        tokens=dict(item.tokens),
                        is_alive=item.is_alive,
                        is_removed=item.is_removed,
                        revealed=item.revealed,
                        identity_id=item.identity_id,
                        current_as_original=True,
                    )
                    for item in self.draft.characters
                    if item.character_id
                ],
                board_tokens=self._normalize_board_tokens(self.draft.board_tokens),
            ),
        )
        self._reset_phase_runtime()
        self.status_message = f"调试局已重建：{module_option_label(self.draft.module_id)}"

    def apply_rules_and_rebuild(
        self,
        *,
        rule_y_id: str,
        rule_x_ids: list[str],
    ) -> None:
        self.set_rules(rule_y_id=rule_y_id, rule_x_ids=rule_x_ids)
        self.rebuild_session()
        current_rule_y = self.draft.rule_y_id
        current_rule_x = [rule_id for rule_id in self.draft.rule_x_ids if rule_id]
        self.status_message = (
            "规则已更新并重建调试局："
            f"Y={rule_option_label(current_rule_y) if current_rule_y else '无'}"
            f"｜X={self._rule_x_summary(current_rule_x)}"
        )

    def available_perpetrator_ids(self) -> list[str]:
        return [item.character_id for item in self.draft.characters if item.character_id]

    def available_identity_abilities(
        self,
        *,
        actor_id: str | None = None,
        timing: str | None = None,
    ) -> list[tuple[str, str]]:
        result: list[tuple[str, str]] = []
        for candidate in self._list_debug_ability_candidates(
            source_kinds=("identity", "derived"),
            source_id=actor_id,
            timing=timing,
        ):
            label = f"{candidate.ability.name}｜{candidate.ability.timing.value}｜{candidate.ability.ability_id}"
            result.append((candidate.ability.ability_id, label))
        return result

    def available_rule_abilities(
        self,
        *,
        timing: str | None = None,
    ) -> list[tuple[str, str]]:
        result: list[tuple[str, str]] = []
        for candidate in self._list_debug_ability_candidates(
            source_kind="rule",
            timing=timing,
        ):
            label = (
                f"{rule_option_label(candidate.source_id)}"
                f"｜{candidate.ability.name}"
                f"｜{candidate.ability.timing.value}"
                f"｜{candidate.ability.ability_id}"
            )
            result.append((candidate.ability.ability_id, label))
        return result

    def available_identity_ability_target_options(
        self,
        *,
        actor_id: str,
        ability_id: str,
        timing: str | None = None,
    ) -> list[list[tuple[str, str]]]:
        candidate = self._find_debug_ability_candidate(
            source_kinds=("identity", "derived"),
            source_id=actor_id,
            ability_id=ability_id,
            timing=timing,
        )
        return self._ability_target_options(candidate)

    def available_rule_ability_target_options(
        self,
        *,
        ability_id: str,
        timing: str | None = None,
    ) -> list[list[tuple[str, str]]]:
        candidate = self._find_debug_ability_candidate(
            source_kind="rule",
            ability_id=ability_id,
            timing=timing,
        )
        return self._ability_target_options(candidate)

    def _ability_target_options(self, candidate: Any | None) -> list[list[tuple[str, str]]]:
        if candidate is None or self.session is None:
            return []
        option_groups: list[list[tuple[str, str]]] = []
        owner_id = self._candidate_owner_id(candidate)
        for effect in candidate.ability.effects:
            options = self._ability_effect_options(owner_id=owner_id, effect=effect)
            if not options:
                continue
            option_groups.append(
                [(option_id, self._target_option_label(option_id)) for option_id in options]
            )
        return option_groups

    def _ability_effect_options(
        self,
        *,
        owner_id: str,
        effect: Any,
    ) -> list[str]:
        if self.session is None:
            return []
        selector = effect.target
        if selector_requires_choice(selector):
            return self.session.ability_resolver.resolve_targets(
                self.session.state,
                owner_id=owner_id,
                selector=selector,
                alive_only=True,
            )
        move_options = self._ability_move_area_options(owner_id=owner_id, effect=effect)
        if move_options:
            return move_options
        token_options = self._ability_token_options(effect)
        if token_options:
            return token_options
        if effect.effect_type.name in {"PLACE_TOKEN", "REMOVE_TOKEN"} and effect.value == "choose_place_or_remove":
            return ["place", "remove"]
        return []

    def _ability_move_area_options(
        self,
        *,
        owner_id: str,
        effect: Any,
    ) -> list[str]:
        if self.session is None:
            return []
        if effect.effect_type.name != "MOVE_CHARACTER" or not selector_requires_choice(effect.value):
            return []
        mover_id = owner_id if selector_is_self_ref(effect.target) else selector_literal_value(effect.target)
        if mover_id not in self.session.state.characters:
            return []
        all_areas = self.session.ability_resolver.resolve_targets(
            self.session.state,
            owner_id=owner_id,
            selector=effect.value,
            alive_only=False,
        )
        return self.session.state.available_enterable_areas(mover_id, all_areas)

    def trigger_incident(
        self,
        *,
        incident_id: str,
        perpetrator_id: str,
        target_selectors: list[dict[str, str]] | None = None,
        target_character_ids: list[str] | None = None,
        target_area_ids: list[str] | None = None,
        chosen_token_types: list[str] | None = None,
    ) -> None:
        if self.session is None:
            raise RuntimeError("调试局尚未建立")
        before_flags, before_protagonist_dead = self._capture_failure_state()
        result = trigger_debug_incident(
            self.session,
            incident_id=incident_id,
            perpetrator_id=perpetrator_id,
            target_selectors=target_selectors,
            target_character_ids=target_character_ids,
            target_area_ids=target_area_ids,
            chosen_token_types=chosen_token_types,
        )
        if not result.resolution.occurred:
            status = "未发生"
        elif result.resolution.has_phenomenon:
            status = "发生｜有现象"
        else:
            status = "发生｜无现象"
        self.status_message = self._append_failure_status(
            f"事件触发：{incident_option_label(incident_id)}｜{status}",
            before_flags=before_flags,
            before_protagonist_dead=before_protagonist_dead,
        )

    def trigger_identity_ability(
        self,
        *,
        actor_id: str,
        ability_id: str,
        timing: str | None = None,
        target_choices: list[str] | None = None,
    ) -> None:
        if self.session is None:
            raise RuntimeError("调试局尚未建立")
        before_flags, before_protagonist_dead = self._capture_failure_state()
        result = trigger_debug_ability(
            self.session,
            actor_id=actor_id,
            ability_id=ability_id,
            timing=timing,
            target_choices=target_choices,
        )
        self.status_message = self._append_failure_status(
            f"身份能力触发：{ability_id}｜{result.resolution.outcome.value}",
            before_flags=before_flags,
            before_protagonist_dead=before_protagonist_dead,
        )

    def trigger_rule_ability(
        self,
        *,
        ability_id: str,
        timing: str | None = None,
        target_choices: list[str] | None = None,
    ) -> None:
        if self.session is None:
            raise RuntimeError("调试局尚未建立")
        candidate = self._find_debug_ability_candidate(
            source_kind="rule",
            ability_id=ability_id,
            timing=timing,
        )
        if candidate is None:
            raise ValueError(f"规则能力不可用：{ability_id}")
        before_flags, before_protagonist_dead = self._capture_failure_state()
        result = trigger_debug_ability(
            self.session,
            actor_id=candidate.source_id,
            ability_id=ability_id,
            timing=timing,
            target_choices=target_choices,
        )
        self.status_message = self._append_failure_status(
            f"规则能力触发：{rule_option_label(candidate.source_id)}｜{ability_id}｜{result.resolution.outcome.value}",
            before_flags=before_flags,
            before_protagonist_dead=before_protagonist_dead,
        )

    def snapshot(self) -> dict[str, Any]:
        if self.session is None:
            return {}
        snapshot = get_debug_snapshot(self.session)
        snapshot["rule_y_id"] = self.draft.rule_y_id
        snapshot["rule_x_ids"] = list(self.draft.rule_x_ids)
        if self.pending_wait is not None:
            snapshot["pending_wait"] = {
                "input_type": self.pending_wait.input_type,
                "player": self.pending_wait.player,
                "prompt": self.pending_wait.prompt,
            }
        else:
            snapshot["pending_wait"] = None
        return snapshot

    def snapshot_text(self) -> str:
        snapshot = self.snapshot()
        if not snapshot:
            return "调试局未建立"
        lines = [
            f"模组：{module_option_label(self.draft.module_id)}",
            f"轮回：{snapshot.get('current_loop', '?')}",
            f"天数：{snapshot.get('current_day', '?')}",
            f"阶段：{phase_name(str(snapshot.get('current_phase', '')))}",
            f"状态：{self.status_message or '空闲'}",
            "",
            "角色：",
        ]
        characters = snapshot.get("characters", {})
        if isinstance(characters, dict):
            for character_id in sorted(characters):
                item = characters[character_id]
                if not isinstance(item, dict):
                    continue
                token_text = ", ".join(
                    f"{token_name(token_id)}={amount}"
                    for token_id, amount in sorted(dict(item.get("tokens", {})).items())
                ) or "无"
                lines.append(
                    f"- {character_option_label(character_id)}｜区域={area_name(str(item.get('area', '')))}"
                    f"｜身份={item.get('identity_id', '?')}｜存活={item.get('is_alive', False)}"
                    f"｜公开={item.get('revealed', False)}｜标记={token_text}"
                )
        lines.append("")
        lines.append("最近调试日志：")
        debug_log = snapshot.get("debug_log", [])
        if isinstance(debug_log, list) and debug_log:
            for item in debug_log[-5:]:
                lines.append(f"- {item}")
        else:
            lines.append("- 暂无")
        return "\n".join(lines)

    def read_debug_snapshot(self) -> dict[str, Any]:
        return self.snapshot()

    def submit_input(self, choice: Any) -> None:
        wait = self.pending_wait
        if wait is None or wait.callback is None:
            self._record_runtime_error("provide_input without pending callback")
            raise RuntimeError("No pending input callback; test mode is not waiting for input")

        callback = wait.callback
        self.pending_wait = None
        self._input_in_progress = True
        self._last_input_summary = self._summarize_input(choice)
        self._last_error = ""
        self._append_trace(
            f"provide_input wait#{wait.wait_id} {self._last_input_summary}"
        )
        try:
            result = callback(choice)
        except Exception:
            self.pending_wait = wait
            self._record_runtime_error("callback raised; restored pending callback")
            raise
        finally:
            self._input_in_progress = False
        if result is not None:
            self._handle_phase_signal(result)
        self._sync_runtime_from_session()

    def get_runtime_debug_snapshot(self) -> dict[str, Any]:
        engine_phase = ""
        state_current_phase = ""
        if self.state_machine is not None:
            engine_phase = self.state_machine.current_phase.value
        if self.session is not None:
            state_current_phase = self.session.state.current_phase.value
        return {
            "engine_phase": engine_phase,
            "state_current_phase": state_current_phase,
            "current_signal": self._current_signal,
            "input_in_progress": self._input_in_progress,
            "has_pending_callback": self.pending_wait is not None and self.pending_wait.callback is not None,
            "pending_wait_id": self.pending_wait.wait_id if self.pending_wait is not None else 0,
            "last_input_summary": self._last_input_summary,
            "last_error": self._last_error,
            "trace_tail": list(self._trace_tail),
        }

    def execute_current_phase(self) -> None:
        if self.session is None or self.state_machine is None:
            raise RuntimeError("调试局尚未建立")
        if self.pending_wait is not None:
            raise RuntimeError("当前阶段正在等待输入，最小版暂不支持直接继续")

        phase = self.state_machine.current_phase
        state = self.session.state
        state.current_phase = phase
        settle_persistent_effects(state)

        if phase == GamePhase.GAME_END:
            self.status_message = "当前已是游戏结束阶段"
            return
        if phase == GamePhase.NEXT_LOOP:
            state.reset_for_new_loop()
            self._sync_runtime_from_session()
            self.session.debug_log.append({
                "action": "execute_test_phase",
                "phase": phase.value,
                "result": "loop_reset",
            })
            self.status_message = "已执行下一轮回重置，可继续推进到下一阶段"
            return

        handler = self.phase_handlers.get(phase)
        if handler is None:
            self.session.debug_log.append({
                "action": "execute_test_phase",
                "phase": phase.value,
                "result": "no_handler",
            })
            self.status_message = f"当前阶段无独立执行器：{phase_name(phase.value)}"
            return

        before_flags, before_protagonist_dead = self._capture_failure_state()
        signal = handler.execute(state)
        self._handle_phase_signal(signal)
        self.status_message = self._append_failure_status(
            self.status_message,
            before_flags=before_flags,
            before_protagonist_dead=before_protagonist_dead,
        )
        self._sync_runtime_from_session()

    def advance_phase(self) -> None:
        if self.session is None or self.state_machine is None:
            raise RuntimeError("调试局尚未建立")
        if self.pending_wait is not None:
            raise RuntimeError("当前阶段正在等待输入，不能直接推进")
        if self.state_machine.current_phase == GamePhase.GAME_END:
            self.status_message = "当前已是游戏结束阶段"
            return

        prev_phase = self.state_machine.current_phase
        if prev_phase == GamePhase.NEXT_LOOP:
            self.session.state.reset_for_new_loop()

        next_phase = self.state_machine.advance(
            is_final_day=(self.session.state.current_day >= self.session.state.script.days_per_loop),
            failure_reached=bool(self.session.state.failure_flags),
            is_last_loop=self.session.state.is_last_loop,
            protagonist_dead=self.session.state.protagonist_dead,
            has_final_guess=self.session.state.has_final_guess,
        )
        if prev_phase == GamePhase.TURN_END and next_phase == GamePhase.TURN_START:
            self.session.state.advance_day()

        self.session.state.current_phase = next_phase
        self.pending_wait = None
        self._sync_runtime_from_session()
        self.session.debug_log.append({
            "action": "advance_test_phase",
            "from_phase": prev_phase.value,
            "to_phase": next_phase.value,
            "current_loop": self.session.state.current_loop,
            "current_day": self.session.state.current_day,
        })
        self.status_message = f"阶段已推进：{phase_name(prev_phase.value)} → {phase_name(next_phase.value)}"

    @staticmethod
    def _ability_token_options(effect: Any) -> list[str]:
        value = getattr(effect, "value", None)
        if value == "choose_token_type":
            return [token.value for token in TokenType]
        if isinstance(value, dict) and value.get("choice") == "choose_token_type":
            options = value.get("options", [])
            if not isinstance(options, list):
                return []
            valid = {token.value for token in TokenType}
            return [item for item in options if isinstance(item, str) and item in valid]
        return []

    def _list_debug_ability_candidates(
        self,
        *,
        source_kind: str | None = None,
        source_kinds: tuple[str, ...] | None = None,
        source_id: str | None = None,
        timing: str | None = None,
    ) -> list[Any]:
        if self.session is None:
            return []
        candidates = list_debug_abilities(
            self.session,
            actor_id=source_id,
            timing=timing,
            alive_only=False,
        )
        allowed_kinds = source_kinds or ((source_kind,) if source_kind else ())
        if not allowed_kinds:
            return candidates
        return [candidate for candidate in candidates if candidate.source_kind in allowed_kinds]

    def _find_debug_ability_candidate(
        self,
        *,
        source_kind: str | None = None,
        source_kinds: tuple[str, ...] | None = None,
        source_id: str | None = None,
        ability_id: str,
        timing: str | None = None,
    ) -> Any | None:
        for candidate in self._list_debug_ability_candidates(
            source_kind=source_kind,
            source_kinds=source_kinds,
            source_id=source_id,
            timing=timing,
        ):
            if candidate.ability.ability_id == ability_id:
                return candidate
        return None

    @staticmethod
    def _candidate_owner_id(candidate: Any) -> str:
        if getattr(candidate, "source_kind", "") == "rule":
            return ""
        return str(getattr(candidate, "source_id", ""))

    def _target_option_label(self, option_id: str) -> str:
        if option_id in self.available_character_ids:
            return character_option_label(option_id)
        if option_id in self.available_area_ids():
            return area_name(option_id)
        if option_id in self.available_token_ids():
            return token_name(option_id)
        return option_id

    def _normalize_character(self, item: TestCharacterDraft) -> TestCharacterDraft:
        character_id = item.character_id if item.character_id in self.available_character_ids else self._default_character_id()
        identity_id = item.identity_id if item.identity_id in self.available_identity_ids else "平民"
        area = item.area if item.area in self.available_area_ids() else self._default_area_for(character_id)
        tokens = {
            token_id: max(0, int(amount))
            for token_id, amount in item.tokens.items()
            if token_id in self.available_token_ids() and int(amount) > 0
        }
        return TestCharacterDraft(
            character_id=character_id,
            identity_id=identity_id,
            area=area,
            is_alive=item.is_alive,
            is_removed=item.is_removed,
            revealed=item.revealed,
            tokens=tokens,
        )

    def _normalize_board_tokens(
        self,
        board_tokens: dict[str, dict[str, int]] | None,
    ) -> dict[str, dict[str, int]]:
        normalized: dict[str, dict[str, int]] = {}
        source = board_tokens or {}
        for area_id in self.available_area_ids():
            raw_tokens = source.get(area_id, {})
            if not isinstance(raw_tokens, dict):
                raw_tokens = {}
            intrigue = max(0, min(3, int(raw_tokens.get(TokenType.INTRIGUE.value, 0))))
            normalized[area_id] = (
                {TokenType.INTRIGUE.value: intrigue}
                if intrigue > 0
                else {}
            )
        return normalized

    def _default_character_id(self, *, exclude: set[str] | None = None) -> str:
        exclude = exclude or set()
        for character_id in self.available_character_ids:
            if character_id not in exclude:
                return character_id
        return self.available_character_ids[0] if self.available_character_ids else ""

    def _default_area_for(self, character_id: str) -> str:
        snapshot = build_script_setup_context(
            self.draft.module_id,
            loop_count=TEST_MODE_LOOP_COUNT,
            days_per_loop=TEST_MODE_DAYS_PER_LOOP,
            errors=[],
        )
        del snapshot  # 只为保持接口对齐，不额外依赖角色详情
        from engine.rules.character_loader import load_character_defs

        character_defs = load_character_defs()
        character = character_defs.get(character_id)
        if character is None:
            return AreaId.CITY.value
        return character.initial_area.value

    def _normalize_rule_y_id(self, rule_y_id: str) -> str:
        return rule_y_id if rule_y_id in self.available_rule_y_ids else ""

    def _normalize_rule_x_ids(self, rule_x_ids: list[str]) -> list[str]:
        valid_ids = set(self.available_rule_x_ids)
        normalized: list[str] = []
        seen: set[str] = set()
        for rule_id in rule_x_ids:
            if rule_id not in valid_ids or rule_id in seen:
                normalized.append("")
                continue
            normalized.append(rule_id)
            seen.add(rule_id)
        while len(normalized) < self.rule_x_count:
            normalized.append("")
        return normalized[:self.rule_x_count]

    @staticmethod
    def _rule_x_summary(rule_x_ids: list[str]) -> str:
        if not rule_x_ids:
            return "无"
        return "、".join(rule_option_label(rule_id) for rule_id in rule_x_ids)

    def _capture_failure_state(self) -> tuple[set[str], bool]:
        if self.session is None:
            return set(), False
        return set(self.session.state.failure_flags), self.session.state.protagonist_dead

    def _append_failure_status(
        self,
        base_message: str,
        *,
        before_flags: set[str],
        before_protagonist_dead: bool,
    ) -> str:
        if self.session is None:
            return base_message
        current_flags = set(self.session.state.failure_flags)
        new_flags = sorted(current_flags - before_flags)
        became_dead = self.session.state.protagonist_dead and not before_protagonist_dead
        notices: list[str] = []
        if new_flags:
            notices.append(f"触发失败条件：{'、'.join(new_flags)}")
        if became_dead:
            notices.append("主人公死亡")
        if not notices:
            return base_message
        return f"{base_message}｜{'｜'.join(notices)}"

    def _reset_phase_runtime(self) -> None:
        if self.session is None:
            self.state_machine = None
            self.phase_handlers = {}
            self.pending_wait = None
            return
        self.state_machine = StateMachine()
        self.state_machine.current_phase = GamePhase(self.session.state.current_phase.value)
        self.phase_handlers = create_phase_handlers(
            self.session.event_bus,
            self.session.atomic_resolver,
        )
        self.pending_wait = None
        self._wait_sequence = 0
        self._current_signal = ""
        self._input_in_progress = False
        self._last_input_summary = ""
        self._last_error = ""
        self._trace_tail.clear()
        self._append_trace(f"reset_phase_runtime {self.state_machine.current_phase.value}")
        self._sync_runtime_from_session()

    def _sync_runtime_from_session(self) -> None:
        if self.session is None or self.state_machine is None:
            return
        phase = self.state_machine.current_phase.value
        self.draft = TestModeDraft(
            module_id=self.draft.module_id,
            rule_y_id=self.draft.rule_y_id,
            rule_x_ids=list(self.draft.rule_x_ids),
            current_loop=self.session.state.current_loop,
            current_day=self.session.state.current_day,
            current_phase=phase,
            characters=list(self.draft.characters),
            board_tokens=self._normalize_board_tokens(self.draft.board_tokens),
        )
        self.session.state.current_phase = GamePhase(phase)

    def _handle_phase_signal(self, signal: Any) -> None:
        if self.session is None:
            return
        phase = self.state_machine.current_phase.value if self.state_machine is not None else "unknown"
        self._current_signal = type(signal).__name__
        self._append_trace(f"handle_signal {self._current_signal}")
        match signal:
            case PhaseComplete():
                self.pending_wait = None
                self._last_error = ""
                self.session.debug_log.append({
                    "action": "execute_test_phase",
                    "phase": phase,
                    "result": "complete",
                })
                self.status_message = f"阶段执行完成：{phase_name(phase)}；可继续推进"
            case WaitForInput() as wait:
                if wait.callback is None:
                    self._record_runtime_error(f"WaitForInput({wait.input_type}) missing callback")
                    raise RuntimeError(f"WaitForInput({wait.input_type}) missing callback")
                self._wait_sequence += 1
                wait.wait_id = self._wait_sequence
                self.pending_wait = wait
                self._last_error = ""
                self._append_trace(
                    f"wait #{wait.wait_id} {wait.input_type} player={wait.player}"
                )
                self.session.debug_log.append({
                    "action": "execute_test_phase",
                    "phase": phase,
                    "result": "wait",
                    "input_type": wait.input_type,
                    "player": wait.player,
                })
                self.status_message = f"阶段等待输入：{wait.input_type}（{wait.player}）"
            case ForceLoopEnd() as forced:
                self.pending_wait = None
                self._last_error = ""
                if self.state_machine is not None:
                    self.state_machine.force_loop_end()
                self._append_trace(f"force_loop_end {forced.reason}")
                self.session.debug_log.append({
                    "action": "execute_test_phase",
                    "phase": phase,
                    "result": "force_loop_end",
                    "reason": forced.reason,
                })
                self.status_message = f"阶段触发强制轮回结束：{forced.reason or phase_name(phase)}"
            case _:
                raise RuntimeError(f"unsupported phase signal: {type(signal).__name__}")

    def _append_trace(self, message: str) -> None:
        self._trace_tail.append(message)

    def _record_runtime_error(self, message: str) -> None:
        self._last_error = message
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
        ability = getattr(choice, "ability", None)
        if ability is not None and hasattr(ability, "ability_id"):
            return str(ability.ability_id)
        return type(choice).__name__
