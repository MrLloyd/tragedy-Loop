"""惨剧轮回 — 事件结算器

事件结算器负责事件专属语义：
  1. 判定事件是否发生
  2. 标记事件发生并发布内部事件
  3. 维护公开结果语义
  4. 将已定义的事件效果交给 AtomicResolver 执行

AtomicResolver 仍只负责通用 effect/mutation/trigger 的原子结算。
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any

from engine.event_bus import GameEvent, GameEventType
from engine.models.effects import Effect
from engine.models.enums import EffectType, Outcome, TokenType
from engine.models.incident import IncidentPublicResult
from engine.models.selectors import (
    area_choice_selector,
    character_choice_selector,
    parse_target_selector,
    selector_area_id,
    selector_character_id,
    selector_is_character_choice,
    selector_is_self_ref,
    selector_literal_value,
    selector_requires_choice,
)
from engine.resolvers.ability_resolver import AbilityResolver

if TYPE_CHECKING:
    from engine.event_bus import EventBus
    from engine.game_state import GameState
    from engine.models.incident import IncidentDef, IncidentSchedule
    from engine.resolvers.atomic_resolver import AtomicResolver, Mutation, ServantFollowChoiceRequest

@dataclass
class IncidentResolution:
    """单个事件的完整结算结果。"""

    schedule: IncidentSchedule
    incident_def: IncidentDef | None = None
    occurred: bool = False
    has_phenomenon: bool = False
    outcome: Outcome = Outcome.NONE
    mutations: list[Mutation] = field(default_factory=list)
    public_result: IncidentPublicResult | None = None


class IncidentResolver:
    """事件专属结算入口。"""

    _TOKEN_CHOICE_VALUES = (
        TokenType.GOODWILL,
        TokenType.PARANOIA,
        TokenType.INTRIGUE,
    )

    def __init__(self, event_bus: EventBus, atomic_resolver: AtomicResolver) -> None:
        self.event_bus = event_bus
        self.atomic_resolver = atomic_resolver
        self.condition_resolver = AbilityResolver()

    def resolve_schedule(
        self,
        state: GameState,
        schedule: IncidentSchedule,
        *,
        servant_follow_choices: dict[str, str] | None = None,
    ) -> IncidentResolution:
        incident_def = state.incident_defs.get(schedule.incident_id)
        resolution = IncidentResolution(schedule=schedule, incident_def=incident_def)

        if not self.can_occur(state, schedule, incident_def):
            resolution.public_result = self._build_public_result(
                state,
                schedule,
                occurred=False,
                has_phenomenon=False,
            )
            self._record_public_result(state, resolution.public_result)
            return resolution

        self._mark_occurred(state, schedule)
        self._emit_occurred(state, schedule)
        resolution.occurred = True

        if incident_def is None:
            resolution.public_result = self._build_public_result(
                state,
                schedule,
                occurred=True,
                has_phenomenon=False,
            )
            self._record_public_result(state, resolution.public_result)
            return resolution

        effective_incident_def = self._incident_def_with_perpetrator_overrides(
            state,
            schedule,
            incident_def,
        )

        if self.next_runtime_choice(state, schedule, effective_incident_def) is not None:
            resolution.public_result = self._build_public_result(
                state,
                schedule,
                occurred=True,
                has_phenomenon=False,
            )
            self._record_public_result(state, resolution.public_result)
            return resolution

        effects = self._materialize_effects(state, schedule, effective_incident_def.effects)
        result = self.atomic_resolver.resolve(
            state,
            effects,
            sequential=effective_incident_def.sequential,
            perpetrator_id=schedule.perpetrator_id,
            servant_follow_choices=servant_follow_choices,
        )

        resolution.mutations = result.mutations
        resolution.outcome = result.outcome
        resolution.has_phenomenon = len(result.mutations) > 0
        resolution.public_result = self._build_public_result(
            state,
            schedule,
            occurred=True,
            has_phenomenon=resolution.has_phenomenon,
        )
        self._record_public_result(state, resolution.public_result)
        return resolution

    def resolve_effect_only(
        self,
        state: GameState,
        schedule: IncidentSchedule,
        incident_def: IncidentDef | None = None,
        *,
        servant_follow_choices: dict[str, str] | None = None,
    ) -> IncidentResolution:
        """仅执行事件效果，不标记事件已发生，也不写公开记录。"""
        resolved_incident_def = incident_def or state.incident_defs.get(schedule.incident_id)
        resolution = IncidentResolution(schedule=schedule, incident_def=resolved_incident_def)
        if resolved_incident_def is None:
            return resolution

        effective_incident_def = self._incident_def_with_perpetrator_overrides(
            state,
            schedule,
            resolved_incident_def,
        )

        if self.next_runtime_choice(state, schedule, effective_incident_def) is not None:
            return resolution

        effects = self._materialize_effects(state, schedule, effective_incident_def.effects)
        result = self.atomic_resolver.resolve(
            state,
            effects,
            sequential=effective_incident_def.sequential,
            perpetrator_id=schedule.perpetrator_id,
            servant_follow_choices=servant_follow_choices,
        )

        resolution.mutations = result.mutations
        resolution.outcome = result.outcome
        resolution.has_phenomenon = len(result.mutations) > 0
        return resolution

    def next_servant_follow_choice(
        self,
        state: GameState,
        schedule: IncidentSchedule,
        *,
        servant_follow_choices: dict[str, str] | None = None,
    ) -> ServantFollowChoiceRequest | None:
        incident_def = state.incident_defs.get(schedule.incident_id)
        if not self.can_occur(state, schedule, incident_def):
            return None
        if incident_def is None:
            return None
        effective_incident_def = self._incident_def_with_perpetrator_overrides(
            state,
            schedule,
            incident_def,
        )
        if self.next_runtime_choice(state, schedule, effective_incident_def) is not None:
            return None
        effects = self._materialize_effects(state, schedule, effective_incident_def.effects)
        return self.atomic_resolver.next_servant_follow_choice(
            state,
            effects,
            sequential=effective_incident_def.sequential,
            perpetrator_id=schedule.perpetrator_id,
            servant_follow_choices=servant_follow_choices,
        )

    def can_occur(
        self,
        state: GameState,
        schedule: IncidentSchedule,
        incident_def: IncidentDef | None = None,
    ) -> bool:
        if self._incident_is_blocked(state, schedule):
            return False

        if self._incident_is_forced(state, schedule, incident_def):
            return True

        return self._passes_normal_incident_check(state, schedule, incident_def)

    def _incident_is_blocked(self, state: GameState, schedule: IncidentSchedule) -> bool:
        if schedule.occurred:
            return True

        if schedule.perpetrator_id in state.suppressed_incident_perpetrators:
            return True

        perpetrator = state.characters.get(schedule.perpetrator_id)
        if perpetrator is None or not perpetrator.is_active():
            return True

        return False

    def _incident_is_forced(
        self,
        state: GameState,
        schedule: IncidentSchedule,
        incident_def: IncidentDef | None,
    ) -> bool:
        return False

    def _passes_normal_incident_check(
        self,
        state: GameState,
        schedule: IncidentSchedule,
        incident_def: IncidentDef | None = None,
    ) -> bool:
        if self._incident_check_value(state, schedule) < self._incident_threshold(state, schedule, incident_def):
            return False

        if incident_def is not None and incident_def.extra_condition is not None:
            return self.condition_resolver.evaluate_condition(
                state,
                incident_def.extra_condition,
                owner_id=schedule.perpetrator_id,
            )

        return True

    def _incident_check_value(self, state: GameState, schedule: IncidentSchedule) -> int:
        """事件触发判定值；默认使用当事人不安，后续可替换为密谋等机制。"""
        perpetrator = state.characters[schedule.perpetrator_id]
        if perpetrator.character_id == "ai":
            return perpetrator.tokens.total()
        return perpetrator.tokens.paranoia

    def _incident_threshold(
        self,
        state: GameState,
        schedule: IncidentSchedule,
        incident_def: IncidentDef | None,
    ) -> int:
        """事件触发阈值；默认使用当事人不安限度，预留事件/身份修正入口。"""
        perpetrator = state.characters[schedule.perpetrator_id]
        threshold = perpetrator.paranoia_limit
        if incident_def is not None:
            threshold += incident_def.modifies_paranoia_limit
        return threshold

    def _incident_def_with_perpetrator_overrides(
        self,
        state: GameState,
        schedule: IncidentSchedule,
        incident_def: IncidentDef,
    ) -> IncidentDef:
        """
        事件覆写钩子（角色级）。

        目前仅落地 black_cat：其为当事人时，事件效果统一覆写为 NO_EFFECT。
        其他角色扩展（结算次数、判定区域替代等）在此入口追加即可。
        """
        perpetrator = state.characters.get(schedule.perpetrator_id)
        if perpetrator is None:
            return incident_def

        if perpetrator.character_id == "black_cat":
            return replace(
                incident_def,
                effects=[Effect(effect_type=EffectType.NO_EFFECT)],
            )

        return incident_def

    def _mark_occurred(self, state: GameState, schedule: IncidentSchedule) -> None:
        schedule.occurred = True
        state.incidents_occurred_this_loop.append(schedule.incident_id)

    def _emit_occurred(self, state: GameState, schedule: IncidentSchedule) -> None:
        self.event_bus.emit(GameEvent(
            GameEventType.INCIDENT_OCCURRED,
            {
                "incident_id": schedule.incident_id,
                "perpetrator_id": schedule.perpetrator_id,
                "day": state.current_day,
            },
        ))

    def _build_public_result(
        self,
        state: GameState,
        schedule: IncidentSchedule,
        *,
        occurred: bool,
        has_phenomenon: bool,
    ) -> IncidentPublicResult:
        return IncidentPublicResult(
            incident_id=schedule.incident_id,
            day=state.current_day,
            occurred=occurred,
            has_phenomenon=has_phenomenon,
            result_tags=["phenomenon"] if has_phenomenon else ["no_phenomenon"],
        )

    def _record_public_result(self, state: GameState, public_result: IncidentPublicResult | None) -> None:
        if public_result is not None:
            state.incident_results_this_loop.append(public_result)

    def next_runtime_choice(
        self,
        state: GameState,
        schedule: IncidentSchedule,
        incident_def: IncidentDef,
    ) -> tuple[str, list[str]] | None:
        target_selectors: deque[Any] = deque(schedule.target_selectors)
        character_choices: deque[str] = deque(schedule.target_character_ids)
        area_choices: deque[str] = deque(schedule.target_area_ids)
        token_choices: deque[str] = deque(schedule.chosen_token_types)
        chosen_characters: list[str] = []

        for effect in incident_def.effects:
            if selector_is_character_choice(effect.target):
                candidates = self._resolve_character_candidates(
                    state,
                    schedule,
                    effect,
                    selector=effect.target,
                    chosen_characters=chosen_characters,
                )
                selected_character = self._consume_matching_target_choice(
                    target_selectors,
                    legacy_choices=character_choices,
                    candidates=candidates,
                    choice_kind="character",
                )
                if selected_character is not None:
                    chosen_characters.append(selected_character)
                elif candidates:
                    return "character", sorted(candidates)

            if effect.effect_type.name == "MOVE_CHARACTER" and selector_requires_choice(effect.value):
                candidates = self._resolve_move_area_candidates(
                    state,
                    schedule,
                    effect,
                    chosen_characters=chosen_characters,
                )
                selected_area = self._consume_matching_target_choice(
                    target_selectors,
                    legacy_choices=area_choices,
                    candidates=candidates,
                    choice_kind="area",
                )
                if selected_area is None and candidates:
                    return "area", sorted(candidates)

            if effect.token_type is None and effect.value == "choose_token_type":
                candidates = [token_type.value for token_type in self._TOKEN_CHOICE_VALUES]
                selected_token = self._consume_matching_choice(token_choices, candidates)
                if selected_token is None:
                    return "token", candidates

        return None

    def _materialize_effects(
        self,
        state: GameState,
        schedule: IncidentSchedule,
        effects: list[Effect],
    ) -> list[Effect]:
        target_selectors: deque[Any] = deque(schedule.target_selectors)
        character_choices: deque[str] = deque(schedule.target_character_ids)
        area_choices: deque[str] = deque(schedule.target_area_ids)
        token_choices: deque[str] = deque(schedule.chosen_token_types)
        chosen_characters: list[str] = []
        concretized: list[Effect] = []

        for effect in effects:
            updated = replace(effect)
            chosen_token_type: TokenType | None = None
            if effect.token_type is None and effect.value == "choose_token_type":
                chosen_token_type = self._resolve_token_choice(token_choices)
            updated.target = self._resolve_effect_target(
                state,
                schedule,
                effect,
                target_selectors=target_selectors,
                character_choices=character_choices,
                chosen_characters=chosen_characters,
            )
            resolved_target_character = updated.target if isinstance(updated.target, str) and updated.target in state.characters else None
            updated.value = self._resolve_effect_value(
                state,
                schedule,
                effect,
                target_selectors=target_selectors,
                area_choices=area_choices,
                chosen_token_type=chosen_token_type,
                chosen_characters=[
                    *chosen_characters,
                    *([resolved_target_character] if resolved_target_character is not None else []),
                ],
            )
            if chosen_token_type is not None:
                updated.token_type = chosen_token_type
            if selector_is_character_choice(effect.target):
                updated.condition = None
            concretized.append(updated)
            if resolved_target_character is not None:
                chosen_characters.append(resolved_target_character)

        return concretized

    def _resolve_effect_target(
        self,
        state: GameState,
        schedule: IncidentSchedule,
        effect: Effect,
        *,
        target_selectors: deque[Any],
        character_choices: deque[str],
        chosen_characters: list[str],
    ) -> Any:
        selector = effect.target
        if not selector_is_character_choice(selector):
            return selector

        candidates = self._resolve_character_candidates(
            state,
            schedule,
            effect,
            selector=selector,
            chosen_characters=chosen_characters,
        )
        if not candidates:
            return {"ref": "none"}

        selected_character = self._consume_matching_target_choice(
            target_selectors,
            legacy_choices=character_choices,
            candidates=candidates,
            choice_kind="character",
        )
        if selected_character is not None:
            return selected_character

        return {"ref": "none"}

    def _resolve_effect_value(
        self,
        state: GameState,
        schedule: IncidentSchedule,
        effect: Effect,
        *,
        target_selectors: deque[Any],
        area_choices: deque[str],
        chosen_token_type: TokenType | None,
        chosen_characters: list[str],
    ) -> object:
        if effect.effect_type.name == "MOVE_CHARACTER" and selector_requires_choice(effect.value):
            candidates = self._resolve_move_area_candidates(
                state,
                schedule,
                    effect,
                    chosen_characters=chosen_characters,
                )
            scripted_choice = self._peek_matching_target_choice(
                target_selectors,
                legacy_choices=area_choices,
                candidates=candidates,
                choice_kind="area",
            )
            if scripted_choice is not None:
                self._consume_matching_target_choice(
                    target_selectors,
                    legacy_choices=area_choices,
                    candidates=candidates,
                    choice_kind="area",
                )
                return scripted_choice
            return sorted(candidates)[0] if candidates else effect.value
        if chosen_token_type is not None:
            return chosen_token_type.value
        return effect.value

    def _resolve_token_choice(self, token_choices: deque[str]) -> TokenType:
        if token_choices:
            raw = token_choices.popleft()
            try:
                return TokenType(raw)
            except ValueError:
                pass
        return TokenType.GOODWILL

    def _resolve_character_candidates(
        self,
        state: GameState,
        schedule: IncidentSchedule,
        effect: Effect,
        *,
        selector: str,
        chosen_characters: list[str],
    ) -> list[str]:
        owner_id = schedule.perpetrator_id
        if parse_target_selector(selector).ref == "another_character":
            if not chosen_characters:
                return []
            base_candidates = self.condition_resolver.resolve_targets(
                state,
                owner_id=owner_id,
                selector={"scope": "any_area", "subject": "character"},
            )
            if chosen_characters:
                base_candidates = [cid for cid in base_candidates if cid != chosen_characters[-1]]
        else:
            base_candidates = self.condition_resolver.resolve_targets(
                state,
                owner_id=owner_id,
                selector=selector,
            )

        result: list[str] = []
        for candidate in base_candidates:
            if effect.condition is not None and not self.condition_resolver.evaluate_condition(
                state,
                effect.condition,
                owner_id=owner_id,
                other_id=candidate,
            ):
                continue
            result.append(candidate)
        return result

    def _resolve_move_area_candidates(
        self,
        state: GameState,
        schedule: IncidentSchedule,
        effect: Effect,
        *,
        chosen_characters: list[str],
    ) -> list[str]:
        mover_ids = self._resolve_move_target_characters(
            state,
            schedule,
            effect,
            chosen_characters=chosen_characters,
        )
        if len(mover_ids) != 1:
            return []
        all_areas = self.condition_resolver.resolve_targets(
            state,
            owner_id=schedule.perpetrator_id,
            selector=effect.value,
            alive_only=False,
        )
        return state.available_enterable_areas(mover_ids[0], all_areas)

    def _resolve_move_target_characters(
        self,
        state: GameState,
        schedule: IncidentSchedule,
        effect: Effect,
        *,
        chosen_characters: list[str],
    ) -> list[str]:
        if selector_is_self_ref(effect.target):
            return [schedule.perpetrator_id]
        literal = selector_literal_value(effect.target)
        if literal in state.characters:
            return [literal]
        if selector_is_character_choice(effect.target):
            resolved = self._resolve_effect_target(
                state,
                schedule,
                effect,
                target_selectors=deque(schedule.target_selectors),
                character_choices=deque(schedule.target_character_ids),
                chosen_characters=chosen_characters,
            )
            if resolved in state.characters:
                return [resolved]
        return []

    @staticmethod
    def _consume_matching_choice(
        choices: deque[str],
        candidates: list[str],
    ) -> str | None:
        while choices:
            choice = choices.popleft()
            if choice in candidates:
                return choice
        return None

    @staticmethod
    def _peek_matching_target_choice(
        target_selectors: deque[Any],
        *,
        legacy_choices: deque[str],
        candidates: list[str],
        choice_kind: str,
    ) -> str | None:
        if target_selectors:
            value = IncidentResolver._selector_choice_value(target_selectors[0], choice_kind)
            if value in candidates:
                return value
            return None
        return legacy_choices[0] if legacy_choices and legacy_choices[0] in candidates else None

    @staticmethod
    def _consume_matching_target_choice(
        target_selectors: deque[Any],
        *,
        legacy_choices: deque[str],
        candidates: list[str],
        choice_kind: str,
    ) -> str | None:
        if target_selectors:
            value = IncidentResolver._selector_choice_value(target_selectors[0], choice_kind)
            if value in candidates:
                target_selectors.popleft()
                return value
            return None
        return IncidentResolver._consume_matching_choice(legacy_choices, candidates)

    @staticmethod
    def _selector_choice_value(raw: Any, choice_kind: str) -> str | None:
        if choice_kind == "character":
            return selector_character_id(raw)
        if choice_kind == "area":
            return selector_area_id(raw)
        return None
