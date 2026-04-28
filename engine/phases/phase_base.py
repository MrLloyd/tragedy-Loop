"""惨剧轮回 — 阶段处理器基类与返回信号"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Optional

from engine.models.cards import CardPlacement, PlacementIntent
from engine.models.ability import Ability, AbilityLocationContext
from engine.models.effects import Condition, Effect
from engine.models.enums import AbilityTiming, AbilityType, AreaId, Attribute, CardType, EffectType, GamePhase, Outcome, PlayerRole, TokenType, Trait
from engine.models.selectors import (
    area_choice_selector,
    character_choice_selector,
    parse_target_selector,
    selector_area_id,
    selector_is_self_ref,
    selector_literal_value,
    selector_requires_choice,
)
from engine.resolvers.ability_resolver import AbilityCandidate, AbilityResolver
from engine.resolvers.atomic_resolver import ScopedEffect, ServantFollowChoiceRequest
from engine.resolvers.incident_resolver import IncidentResolver
from engine.rules.runtime_traits import has_trait

from engine.event_bus import GameEvent, GameEventType

if TYPE_CHECKING:
    from engine.game_state import GameState
    from engine.event_bus import EventBus
    from engine.resolvers.atomic_resolver import AtomicResolver


# ---------------------------------------------------------------------------
# 阶段返回信号
# ---------------------------------------------------------------------------
@dataclass
class PhaseComplete:
    """阶段完成，状态机可推进"""
    pass


@dataclass
class WaitForInput:
    """
    等待玩家输入。

    引擎挂起，UI 展示选项，玩家操作后调用 callback(choice) 继续。
    """
    input_type: str              # 输入类型标识
    prompt: str = ""             # 提示文本
    options: list[Any] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)
    player: str = "mastermind"   # 谁需要输入
    wait_id: int = 0
    callback: Optional[Callable] = None


@dataclass
class ForceLoopEnd:
    """强制结束本轮回"""
    reason: str = ""


# 阶段返回类型
PhaseSignal = PhaseComplete | WaitForInput | ForceLoopEnd


@dataclass
class PreparedAbilityCandidate:
    """阶段级强制窗口中已收集完目标选择的能力候选。"""

    candidate: AbilityCandidate
    owner_id: str
    location_context: AbilityLocationContext | None = None
    selected_targets: dict[int, str] = field(default_factory=dict)


@dataclass
class CompositeActionCard:
    target_type: str
    target_id: str
    placements: list[CardPlacement] = field(default_factory=list)
    movement_card_type: Optional[CardType] = None


@dataclass(frozen=True)
class EffectChoiceRequest:
    choice_kind: str  # "target" | "value" | "token" | "mode"
    options: list[str]


def _validate_action_target(state: GameState, intent: PlacementIntent) -> None:
    if intent.target_type == "character":
        ch = state.characters.get(intent.target_id)
        if ch is None:
            raise ValueError(f"target character {intent.target_id} not found")
        if not ch.is_active():
            raise ValueError(f"target character {intent.target_id} is not alive")
        if has_trait(state, intent.target_id, Trait.NO_ACTION_CARDS):
            raise ValueError(f"target character {intent.target_id} cannot receive action cards")
        return
    if intent.target_type == "board":
        try:
            from engine.models.enums import AreaId

            area_id = AreaId(intent.target_id)
        except ValueError:
            raise ValueError(f"invalid board target area: {intent.target_id}")
        if area_id == AreaId.FARAWAY:
            raise ValueError("faraway is not a valid board action target")
        return
    raise ValueError(f"invalid target_type: {intent.target_type}")


def _validate_action_slot(
    state: GameState,
    intent: PlacementIntent,
    *,
    block_against_roles: set[PlayerRole],
) -> None:
    for placement in state.placed_cards:
        if not placement.face_down:
            continue
        if placement.owner not in block_against_roles:
            continue
        if placement.target_type == intent.target_type and placement.target_id == intent.target_id:
            raise ValueError("cannot place another action card on the same target")


# ---------------------------------------------------------------------------
# PhaseHandler — 阶段处理器基类
# ---------------------------------------------------------------------------
class PhaseHandler(ABC):
    """
    每个游戏阶段对应一个 PhaseHandler 子类。

    execute() 返回 PhaseSignal：
      - PhaseComplete → 自动推进
      - WaitForInput  → 挂起等待
      - ForceLoopEnd  → 跳到 loop_end
    """

    phase: GamePhase  # 子类必须声明

    def __init__(self, event_bus: EventBus,
                 atomic_resolver: AtomicResolver) -> None:
        self.event_bus = event_bus
        self.atomic_resolver = atomic_resolver
        self.ability_resolver = AbilityResolver()

    @abstractmethod
    def execute(self, state: GameState) -> PhaseSignal:
        """执行本阶段逻辑"""
        ...

    def _emit_ability_declared(self, candidate: AbilityCandidate) -> None:
        payload = {
            "source_kind": candidate.source_kind,
            "source_id": candidate.source_id,
            "ability_id": candidate.ability.ability_id,
            "timing": candidate.ability.timing.value,
        }
        if candidate.identity_id is not None:
            payload["identity_id"] = candidate.identity_id
        self.event_bus.emit(GameEvent(GameEventType.ABILITY_DECLARED, payload))

    def _resolve_candidate(
        self,
        state: GameState,
        candidate: AbilityCandidate,
        *,
        location_context_override: AbilityLocationContext | None = None,
        next_signal_factory: Callable[[], PhaseSignal],
    ) -> PhaseSignal:
        owner_id = self._candidate_owner_id(candidate)
        location_options = self._candidate_location_options(
            state,
            candidate,
            owner_id=owner_id,
        )
        if location_context_override is None and len(location_options) > 1:
            return self._build_candidate_location_wait(
                state,
                candidate,
                owner_id=owner_id,
                location_options=location_options,
                next_signal_factory=next_signal_factory,
            )
        location_context = location_context_override or location_options[0][1]
        prepared = self._prepare_effects_for_resolution(
            state,
            candidate,
            owner_id=owner_id,
            location_context=location_context,
            next_signal_factory=next_signal_factory,
        )
        if isinstance(prepared, WaitForInput):
            return prepared

        def _before_resolve() -> None:
            self._emit_ability_declared(candidate)

        def _on_resolved(result: Any) -> PhaseSignal:
            self.ability_resolver.mark_ability_used(state, candidate)
            signal = self._resolution_result_to_signal(result, default_reason=candidate.ability.ability_id)
            if signal is not None:
                return signal
            return next_signal_factory()

        return self._resolve_effect_batch_with_servant_follow(
            state,
            prepared,
            sequential=candidate.ability.sequential,
            perpetrator_id=owner_id,
            location_context=location_context,
            before_resolve=_before_resolve,
            on_resolved=_on_resolved,
        )

    def _execute_mandatory_batch(
        self,
        state: GameState,
        candidates: list[AbilityCandidate],
        *,
        next_signal_factory: Callable[[], PhaseSignal],
    ) -> PhaseSignal:
        if not candidates:
            return next_signal_factory()
        prepared = [
            PreparedAbilityCandidate(
                candidate=candidate,
                owner_id=self._candidate_owner_id(candidate),
                location_context=self._candidate_location_context(
                    state,
                    candidate,
                    owner_id=self._candidate_owner_id(candidate),
                ),
            )
            for candidate in candidates
        ]
        planning_state = state.snapshot()
        return self._collect_mandatory_choices(
            state,
            planning_state,
            prepared,
            candidate_index=0,
            effect_index=0,
            next_signal_factory=next_signal_factory,
        )

    def _candidate_owner_id(self, candidate: AbilityCandidate) -> str:
        if candidate.source_kind in {"identity", "goodwill", "derived", "character_trait_ability"}:
            return candidate.source_id
        return ""

    def _candidate_location_options(
        self,
        state: GameState,
        candidate: AbilityCandidate,
        *,
        owner_id: str,
    ) -> list[tuple[str, AbilityLocationContext | None]]:
        owner = state.characters.get(owner_id)
        if owner is None:
            return [("", None)]

        default_context = AbilityLocationContext(
            owner_area=owner.area,
            owner_initial_area=owner.initial_area,
        )
        territory_area = getattr(owner, "territory_area", None)
        if (
            candidate.source_kind == "goodwill"
            and owner.character_id == "vip"
            and territory_area is not None
            and self._ability_uses_owner_area_context(candidate.ability)
        ):
            return [
                (
                    territory_area.value,
                    AbilityLocationContext(
                        owner_area=territory_area,
                        owner_initial_area=owner.initial_area,
                    ),
                )
            ]
        if (
            candidate.source_kind not in {"identity", "derived", "character_trait_ability"}
            or owner.character_id != "vip"
            or territory_area is None
            or territory_area == owner.area
            or not self._ability_uses_owner_area_context(candidate.ability)
        ):
            return [(owner.area.value, default_context)]

        return [
            (owner.area.value, default_context),
            (
                territory_area.value,
                AbilityLocationContext(
                    owner_area=territory_area,
                    owner_initial_area=owner.initial_area,
                ),
            ),
        ]

    def _candidate_location_context(
        self,
        state: GameState,
        candidate: AbilityCandidate,
        *,
        owner_id: str,
    ) -> AbilityLocationContext | None:
        location_options = self._candidate_location_options(
            state,
            candidate,
            owner_id=owner_id,
        )
        if len(location_options) > 1:
            return None
        return location_options[0][1]

    def _filter_candidates_with_available_targets(
        self,
        state: GameState,
        candidates: list[AbilityCandidate],
    ) -> list[AbilityCandidate]:
        filtered: list[AbilityCandidate] = []
        for candidate in candidates:
            owner_id = self._candidate_owner_id(candidate)
            location_options = self._candidate_location_options(
                state,
                candidate,
                owner_id=owner_id,
            )
            if any(
                self._candidate_has_available_targets_in_context(
                    state,
                    candidate,
                    owner_id=owner_id,
                    location_context=location_context,
                )
                for _, location_context in location_options
            ):
                filtered.append(candidate)
        return filtered

    def _candidate_has_available_targets_in_context(
        self,
        state: GameState,
        candidate: AbilityCandidate,
        *,
        owner_id: str,
        location_context: AbilityLocationContext | None,
    ) -> bool:
        if not self.ability_resolver.evaluate_condition(
            state,
            candidate.ability.condition,
            owner_id=owner_id,
            location_context=location_context,
        ):
            return False
        return all(
            (
                choice_request is None
                or bool(choice_request.options)
            )
            for idx, effect in enumerate(candidate.ability.effects)
            for choice_request in (
                self._resolve_effect_choice_options(
                    state,
                    owner_id=owner_id,
                    location_context=location_context,
                    effect=self._materialize_condition_target_effect(
                        state,
                        candidate.ability.effects,
                        idx,
                        effect,
                    ),
                ),
            )
        )

    def _build_candidate_location_wait(
        self,
        state: GameState,
        candidate: AbilityCandidate,
        *,
        owner_id: str,
        location_options: list[tuple[str, AbilityLocationContext | None]],
        next_signal_factory: Callable[[], PhaseSignal],
    ) -> WaitForInput:
        options = [area_id for area_id, _ in location_options]
        context_by_area = {area_id: context for area_id, context in location_options}

        def _on_choice(choice: Any) -> PhaseSignal:
            selected_area = self._coerce_area_choice(choice)
            if selected_area not in context_by_area:
                raise ValueError(f"invalid ability location: {choice!r}")
            return self._resolve_candidate(
                state,
                candidate,
                location_context_override=context_by_area[selected_area],
                next_signal_factory=next_signal_factory,
            )

        return WaitForInput(
            input_type="choose_ability_location",
            prompt=f"请选择 {candidate.ability.name} 的发动位置",
            options=options,
            player="mastermind",
            callback=_on_choice,
        )

    @staticmethod
    def _coerce_area_choice(choice: Any) -> str | None:
        selected_area = selector_area_id(choice)
        if selected_area is not None:
            return selected_area
        if isinstance(choice, str):
            try:
                return AreaId(choice).value
            except ValueError:
                return None
        return None

    def _ability_uses_owner_area_context(self, ability: Ability) -> bool:
        if self._condition_uses_owner_area_context(ability.condition):
            return True
        return any(self._effect_uses_owner_area_context(effect) for effect in ability.effects)

    def _effect_uses_owner_area_context(self, effect: Effect) -> bool:
        return (
            self._raw_uses_owner_area_context(effect.target)
            or self._raw_uses_owner_area_context(effect.value)
            or self._condition_uses_owner_area_context(effect.condition)
        )

    def _condition_uses_owner_area_context(self, condition: Condition | None) -> bool:
        if condition is None:
            return False
        if condition.condition_type in {"same_area_identity_token_check", "same_area_count"}:
            return True
        if condition.condition_type == "area_is":
            target = condition.params.get("target", {"ref": "self"})
            selector = parse_target_selector(target)
            if selector.ref == "self":
                return True
        return self._raw_uses_owner_area_context(condition.params)

    def _raw_uses_owner_area_context(self, raw: Any) -> bool:
        if isinstance(raw, dict):
            selector = parse_target_selector(raw)
            if selector.scope in {"same_area", "adjacent_area", "diagonal_area"}:
                return True
            return any(self._raw_uses_owner_area_context(value) for value in raw.values())
        if isinstance(raw, list):
            return any(self._raw_uses_owner_area_context(item) for item in raw)
        return False

    def _collect_mandatory_choices(
        self,
        state: GameState,
        planning_state: GameState,
        prepared: list[PreparedAbilityCandidate],
        *,
        candidate_index: int,
        effect_index: int,
        next_signal_factory: Callable[[], PhaseSignal],
    ) -> PhaseSignal:
        if candidate_index >= len(prepared):
            return self._execute_prepared_mandatory_batch(
                state,
                prepared,
                next_signal_factory=next_signal_factory,
            )

        current = prepared[candidate_index]
        if current.location_context is None:
            location_options = self._candidate_location_options(
                planning_state,
                current.candidate,
                owner_id=current.owner_id,
            )
            if len(location_options) > 1:
                options = [area_id for area_id, _ in location_options]
                context_by_area = {area_id: context for area_id, context in location_options}

                def _on_location_choice(
                    choice: Any,
                    *,
                    current_index: int = candidate_index,
                    allowed: tuple[str, ...] = tuple(options),
                ) -> PhaseSignal:
                    selected_area = self._coerce_area_choice(choice)
                    if selected_area not in allowed:
                        raise ValueError(f"invalid ability location: {choice!r}")
                    prepared[current_index].location_context = context_by_area[selected_area]
                    return self._collect_mandatory_choices(
                        state,
                        planning_state,
                        prepared,
                        candidate_index=current_index,
                        effect_index=effect_index,
                        next_signal_factory=next_signal_factory,
                    )

                return WaitForInput(
                    input_type="choose_ability_location",
                    prompt=f"请选择 {current.candidate.ability.name} 的发动位置",
                    options=options,
                    player="mastermind",
                    callback=_on_location_choice,
                )
            current.location_context = location_options[0][1]

        effects = current.candidate.ability.effects
        for index in range(effect_index, len(effects)):
            effect = self._materialize_condition_target_effect(
                planning_state,
                effects,
                index,
                effects[index],
            )
            effects[index] = effect
            choice_request = self._resolve_effect_choice_options(
                planning_state,
                owner_id=current.owner_id,
                location_context=current.location_context,
                effect=effect,
            )
            if choice_request is None or len(choice_request.options) <= 1:
                continue

            def _on_choice(
                choice: Any,
                *,
                current_index: int = candidate_index,
                effect_choice_index: int = index,
                allowed: tuple[str, ...] = tuple(choice_request.options),
            ) -> PhaseSignal:
                selected = str(choice)
                if selected not in allowed:
                    raise ValueError(f"invalid ability target: {selected!r}")
                bound_effect = self._apply_effect_choice(
                    prepared[current_index].candidate.ability.effects[effect_choice_index],
                    choice_kind=choice_request.choice_kind,
                    selected=selected,
                )
                prepared[current_index].candidate.ability.effects[effect_choice_index] = bound_effect
                return self._collect_mandatory_choices(
                    state,
                    planning_state,
                    prepared,
                    candidate_index=current_index,
                    effect_index=effect_choice_index + 1,
                    next_signal_factory=next_signal_factory,
                )

            return WaitForInput(
                input_type="choose_ability_target",
                prompt=f"请选择 {current.candidate.ability.name} 的目标",
                options=choice_request.options,
                player="mastermind",
                callback=_on_choice,
            )

        return self._collect_mandatory_choices(
            state,
            planning_state,
            prepared,
            candidate_index=candidate_index + 1,
            effect_index=0,
            next_signal_factory=next_signal_factory,
        )

    def _execute_prepared_mandatory_batch(
        self,
        state: GameState,
        prepared: list[PreparedAbilityCandidate],
        *,
        next_signal_factory: Callable[[], PhaseSignal],
    ) -> PhaseSignal:
        if not prepared:
            return next_signal_factory()

        round_effects: list[ScopedEffect] = []
        for item in prepared:
            round_effects.extend(self._bind_all_candidate_effects(item))

        def _before_resolve() -> None:
            for item in prepared:
                self._emit_ability_declared(item.candidate)

        def _on_resolved(result: Any) -> PhaseSignal:
            for item in prepared:
                self.ability_resolver.mark_ability_used(state, item.candidate)
            default_reason = (
                prepared[0].candidate.ability.ability_id
                if len(prepared) == 1
                else "mandatory_batch"
            )
            signal = self._resolution_result_to_signal(
                result,
                default_reason=default_reason,
            )
            if signal is not None:
                return signal
            return next_signal_factory()

        return self._resolve_effect_batch_with_servant_follow(
            state,
            round_effects,
            sequential=False,
            perpetrator_id="",
            location_context=None,
            before_resolve=_before_resolve,
            on_resolved=_on_resolved,
        )

    def _bind_all_candidate_effects(
        self,
        prepared: PreparedAbilityCandidate,
    ) -> list[ScopedEffect]:
        return [
            self._bind_candidate_effect(prepared, effect_index)
            for effect_index in range(len(prepared.candidate.ability.effects))
        ]

    def _bind_candidate_effect(
        self,
        prepared: PreparedAbilityCandidate,
        effect_index: int,
    ) -> ScopedEffect:
        effect = prepared.candidate.ability.effects[effect_index]
        return ScopedEffect(
            effect=effect,
            perpetrator_id=prepared.owner_id,
            location_context=prepared.location_context,
        )

    def _resolve_effect_batch_with_servant_follow(
        self,
        state: GameState,
        effects: list[Effect | ScopedEffect],
        *,
        sequential: bool,
        perpetrator_id: str,
        location_context: AbilityLocationContext | None,
        before_resolve: Callable[[], None] | None,
        on_resolved: Callable[[Any], PhaseSignal],
        servant_follow_choices: dict[str, str] | None = None,
    ) -> PhaseSignal:
        choices = dict(servant_follow_choices or {})
        request = self.atomic_resolver.next_servant_follow_choice(
            state,
            effects,
            sequential=sequential,
            perpetrator_id=perpetrator_id,
            location_context=location_context,
            servant_follow_choices=choices,
        )
        if request is not None:
            return self._build_servant_follow_wait(
                state,
                request,
                sequential=sequential,
                effects=effects,
                perpetrator_id=perpetrator_id,
                location_context=location_context,
                before_resolve=before_resolve,
                on_resolved=on_resolved,
                servant_follow_choices=choices,
            )

        if before_resolve is not None:
            before_resolve()
        result = self.atomic_resolver.resolve(
            state,
            effects,
            sequential=sequential,
            perpetrator_id=perpetrator_id,
            location_context=location_context,
            servant_follow_choices=choices,
        )
        return on_resolved(result)

    def _build_servant_follow_wait(
        self,
        state: GameState,
        request: ServantFollowChoiceRequest,
        *,
        sequential: bool,
        effects: list[Effect | ScopedEffect],
        perpetrator_id: str,
        location_context: AbilityLocationContext | None,
        before_resolve: Callable[[], None] | None,
        on_resolved: Callable[[Any], PhaseSignal],
        servant_follow_choices: dict[str, str],
    ) -> WaitForInput:
        servant = state.characters.get(request.servant_id)
        servant_name = servant.name if servant is not None else request.servant_id
        player = f"protagonist_{state.leader_index}"

        def _on_choice(choice: Any) -> PhaseSignal:
            selected = str(choice)
            if selected not in request.options:
                raise ValueError(f"invalid servant follow target: {selected!r}")
            updated_choices = dict(servant_follow_choices)
            updated_choices[request.servant_id] = selected
            return self._resolve_effect_batch_with_servant_follow(
                state,
                effects,
                sequential=sequential,
                perpetrator_id=perpetrator_id,
                location_context=location_context,
                before_resolve=before_resolve,
                on_resolved=on_resolved,
                servant_follow_choices=updated_choices,
            )

        return WaitForInput(
            input_type="choose_ability_target",
            prompt=f"请选择 {servant_name} 要跟随移动的角色",
            options=request.options,
            player=player,
            callback=_on_choice,
        )

    def _prepare_effects_for_resolution(
        self,
        state: GameState,
        candidate: AbilityCandidate,
        *,
        owner_id: str,
        location_context: AbilityLocationContext | None,
        next_signal_factory: Callable[[], PhaseSignal],
    ) -> list[Effect] | WaitForInput:
        effects = list(candidate.ability.effects)
        for index, effect in enumerate(effects):
            while True:
                current = self._materialize_condition_target_effect(
                    state,
                    effects,
                    index,
                    effects[index],
                )
                effects[index] = current
                choice_request = self._resolve_effect_choice_options(
                    state,
                    owner_id=owner_id,
                    location_context=location_context,
                    effect=current,
                )
                if choice_request is None:
                    break
                if not choice_request.options:
                    return []
                if len(choice_request.options) == 1:
                    effects[index] = self._apply_effect_choice(
                        current,
                        choice_kind=choice_request.choice_kind,
                        selected=choice_request.options[0],
                    )
                    continue

                request = choice_request
                current_effect = current

                def _on_choice(choice: Any, *, effect_index: int = index) -> PhaseSignal:
                    selected = str(choice)
                    if selected not in request.options:
                        raise ValueError(f"invalid ability target: {selected!r}")
                    updated = list(effects)
                    updated[effect_index] = self._apply_effect_choice(
                        current_effect,
                        choice_kind=request.choice_kind,
                        selected=selected,
                    )
                    follow_up = AbilityCandidate(
                        source_kind=candidate.source_kind,
                        source_id=candidate.source_id,
                        ability=Ability(
                            ability_id=candidate.ability.ability_id,
                            name=candidate.ability.name,
                            ability_type=candidate.ability.ability_type,
                            timing=candidate.ability.timing,
                            description=candidate.ability.description,
                            condition=candidate.ability.condition,
                            effects=updated,
                            sequential=candidate.ability.sequential,
                            goodwill_requirement=candidate.ability.goodwill_requirement,
                            once_per_loop=candidate.ability.once_per_loop,
                            once_per_day=candidate.ability.once_per_day,
                            can_be_refused=candidate.ability.can_be_refused,
                        ),
                        identity_id=candidate.identity_id,
                    )
                    return self._resolve_candidate(
                        state,
                        follow_up,
                        location_context_override=location_context,
                        next_signal_factory=next_signal_factory,
                    )

                return WaitForInput(
                    input_type="choose_ability_target",
                    prompt=f"请选择 {candidate.ability.name} 的目标",
                    options=request.options,
                    player="mastermind",
                    callback=_on_choice,
                )
        return effects

    def _resolve_effect_choice_options(
        self,
        state: GameState,
        *,
        owner_id: str,
        effect: Effect,
        location_context: AbilityLocationContext | None = None,
    ) -> EffectChoiceRequest | None:
        if (
            effect.condition is not None
            and not selector_requires_choice(effect.target)
            and not self.ability_resolver.evaluate_condition(
                state,
                effect.condition,
                owner_id=owner_id,
                location_context=location_context,
            )
        ):
            return None
        if selector_requires_choice(effect.target):
            choices = self.ability_resolver.resolve_targets(
                state,
                owner_id=owner_id,
                selector=effect.target,
                alive_only=True,
                location_context=location_context,
            )
            if effect.condition is not None:
                choices = [
                    target_id
                    for target_id in choices
                    if self.ability_resolver.evaluate_condition(
                        state,
                        effect.condition,
                        owner_id=owner_id,
                        other_id=target_id,
                        location_context=location_context,
                    )
                ]
            if effect.effect_type == EffectType.NULLIFY_CARD:
                choices = [
                    target_id
                    for target_id in choices
                    if self._matches_nullify_card_target(state, target_id=target_id, effect=effect)
                ]
            return EffectChoiceRequest(choice_kind="target", options=choices)
        if effect.effect_type == EffectType.MOVE_CHARACTER and selector_requires_choice(effect.value):
            choices = self._resolve_move_destination_options(
                state,
                owner_id=owner_id,
                location_context=location_context,
                effect=effect,
            )
            return EffectChoiceRequest(choice_kind="value", options=choices)
        value_choices = self._resolve_value_choice_options(state, effect)
        if value_choices is not None:
            return EffectChoiceRequest(choice_kind="value", options=value_choices)
        token_choices = self._resolve_token_choice_options(
            state,
            owner_id=owner_id,
            effect=effect,
        )
        if token_choices is not None:
            return EffectChoiceRequest(choice_kind="token", options=token_choices)
        if effect.effect_type in {EffectType.PLACE_TOKEN, EffectType.REMOVE_TOKEN} and effect.value == "choose_place_or_remove":
            return EffectChoiceRequest(choice_kind="mode", options=["place", "remove"])
        return None

    @staticmethod
    def _matches_nullify_card_target(
        state: GameState,
        *,
        target_id: str,
        effect: Effect,
    ) -> bool:
        if effect.effect_type != EffectType.NULLIFY_CARD:
            return True
        try:
            card_type = CardType(str(effect.value or ""))
        except ValueError:
            return False
        return any(
            not placement.nullified
            and placement.target_id == target_id
            and placement.card.card_type == card_type
            for placement in state.placed_cards
        )

    @staticmethod
    def _concretize_effect(effect: Effect, target_id: str) -> Effect:
        return Effect(
            effect_type=effect.effect_type,
            target=target_id,
            token_type=effect.token_type,
            amount=effect.amount,
            chooser=effect.chooser,
            value=effect.value,
            condition=PhaseHandler._materialize_effect_condition(effect.condition, target_id),
        )

    @staticmethod
    def _materialize_effect_condition(
        condition: Condition | None,
        target_id: str,
    ) -> Condition | None:
        if condition is None:
            return None
        return Condition(
            condition_type=condition.condition_type,
            params=PhaseHandler._materialize_condition_refs(condition.params, target_id),
        )

    @staticmethod
    def _materialize_condition_refs(value: Any, target_id: str) -> Any:
        if isinstance(value, dict):
            if value.get("ref") in {"other", "condition_target"}:
                return target_id
            return {
                key: PhaseHandler._materialize_condition_refs(item, target_id)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [PhaseHandler._materialize_condition_refs(item, target_id) for item in value]
        return value

    @staticmethod
    def _concretize_effect_value(effect: Effect, value: str) -> Effect:
        return Effect(
            effect_type=effect.effect_type,
            target=effect.target,
            token_type=effect.token_type,
            amount=effect.amount,
            chooser=effect.chooser,
            value=value,
            condition=effect.condition,
        )

    @staticmethod
    def _concretize_effect_token(effect: Effect, token_name: str) -> Effect:
        value = effect.value
        if value == "choose_token_type" or (
            isinstance(value, dict) and value.get("choice") == "choose_token_type"
        ):
            value = None
        return Effect(
            effect_type=effect.effect_type,
            target=effect.target,
            token_type=TokenType(token_name),
            amount=effect.amount,
            chooser=effect.chooser,
            value=value,
            condition=effect.condition,
        )

    @staticmethod
    def _concretize_effect_mode(effect: Effect, selected: str) -> Effect:
        effect_type = EffectType.PLACE_TOKEN if selected == "place" else EffectType.REMOVE_TOKEN
        return Effect(
            effect_type=effect_type,
            target=effect.target,
            token_type=effect.token_type,
            amount=effect.amount,
            chooser=effect.chooser,
            value=None,
            condition=effect.condition,
        )

    def _apply_effect_choice(
        self,
        effect: Effect,
        *,
        choice_kind: str,
        selected: str,
    ) -> Effect:
        if choice_kind == "target":
            return self._concretize_effect(effect, selected)
        if choice_kind == "value":
            return self._concretize_effect_value(effect, selected)
        if choice_kind == "token":
            return self._concretize_effect_token(effect, selected)
        if choice_kind == "mode":
            return self._concretize_effect_mode(effect, selected)
        raise ValueError(f"unknown effect choice kind: {choice_kind}")

    @staticmethod
    def _resolve_token_choice_options(
        state: GameState,
        *,
        owner_id: str,
        effect: Effect,
    ) -> list[str] | None:
        value = effect.value
        options: list[str] | None = None
        if value == "choose_token_type":
            options = [token.value for token in TokenType]
        elif isinstance(value, dict) and value.get("choice") == "choose_token_type":
            options = value.get("options", [])
            if not isinstance(options, list):
                return []
            options = [
                token_name
                for token_name in options
                if isinstance(token_name, str) and token_name in {token.value for token in TokenType}
            ]
        if options is None:
            return None
        if isinstance(value, dict) and value.get("only_available_on_self"):
            owner = state.characters.get(owner_id)
            if owner is None:
                return []
            options = [
                token_name
                for token_name in options
                if owner.tokens.get(TokenType(token_name)) > 0
            ]
        return options

    @staticmethod
    def _resolve_value_choice_options(
        state: GameState,
        effect: Effect,
    ) -> list[str] | None:
        value = effect.value
        if not isinstance(value, dict):
            return None
        choice = value.get("choice")
        if choice == "choose_ex_delta":
            options = value.get("options", ["1", "-1"])
            return [str(item) for item in options if str(item) in {"1", "-1"}]
        if choice == "choose_incident":
            return [schedule.incident_id for schedule in state.script.private_table.incidents]
        if choice == "choose_occurred_incident":
            return [
                schedule.incident_id
                for schedule in state.script.private_table.incidents
                if schedule.occurred or schedule.incident_id in state.incidents_occurred_this_loop
            ]
        if choice == "choose_return_card":
            leader_role = PlayerRole(f"protagonist_{state.leader_index}")
            return [
                str(index)
                for index, placement in enumerate(state.placed_cards)
                if (
                    not placement.face_down
                    and placement.owner == leader_role
                    and placement.card.once_per_loop
                    and placement.card.is_used_this_loop
                )
            ]
        return None

    @staticmethod
    def _materialize_condition_target_effect(
        state: GameState,
        effects: list[Effect],
        index: int,
        effect: Effect,
    ) -> Effect:
        if parse_target_selector(effect.target).ref != "condition_target":
            return effect
        previous_target = PhaseHandler._previous_character_target(state, effects, index)
        if previous_target is None:
            return effect
        return PhaseHandler._concretize_effect(effect, previous_target)

    @staticmethod
    def _previous_character_target(
        state: GameState,
        effects: list[Effect],
        index: int,
    ) -> str | None:
        for previous in reversed(effects[:index]):
            if isinstance(previous.target, str) and previous.target in state.characters:
                return previous.target
        return None

    def _resolve_move_destination_options(
        self,
        state: GameState,
        *,
        owner_id: str,
        location_context: AbilityLocationContext | None,
        effect: Effect,
    ) -> list[str]:
        mover_ids = self._resolve_move_effect_owners(state, owner_id=owner_id, effect=effect)
        if len(mover_ids) != 1:
            return []
        return state.available_enterable_areas(
            mover_ids[0],
            self.ability_resolver.resolve_targets(
                state,
                owner_id=owner_id,
                selector=effect.value,
                alive_only=False,
                location_context=location_context,
            ),
        )

    def _resolve_move_effect_owners(
        self,
        state: GameState,
        *,
        owner_id: str,
        effect: Effect,
    ) -> list[str]:
        target = effect.target
        if selector_is_self_ref(target):
            return [owner_id] if owner_id in state.characters else []
        literal = selector_literal_value(target)
        if literal in state.characters:
            return [literal]
        return []

    @staticmethod
    def _resolution_result_to_signal(result: Any, *, default_reason: str) -> ForceLoopEnd | None:
        if result.outcome in (Outcome.PROTAGONIST_DEATH, Outcome.PROTAGONIST_FAILURE):
            return ForceLoopEnd(reason=default_reason)
        if any(m.mutation_type == "force_loop_end" for m in result.mutations):
            return ForceLoopEnd(reason=default_reason)
        return None


# ---------------------------------------------------------------------------
# 具体阶段处理器（框架实现，后续逐步填充业务逻辑）
# ---------------------------------------------------------------------------
class GamePrepareHandler(PhaseHandler):
    phase = GamePhase.GAME_PREPARE

    def execute(self, state: GameState) -> PhaseSignal:
        if self._is_script_ready(state):
            state.init_protagonist_hands()
            return PhaseComplete()
        return self._build_script_setup_wait(state)

    @staticmethod
    def _is_script_ready(state: GameState) -> bool:
        return (
            state.script.private_table.rule_y is not None
            and bool(state.script.private_table.rules_x)
            and bool(state.script.private_table.characters)
            and bool(state.script.private_table.incidents)
        )

    def _build_script_setup_wait(
        self,
        state: GameState,
        *,
        errors: list[str] | None = None,
    ) -> WaitForInput:
        from engine.rules.module_loader import build_script_setup_context
        from engine.rules.script_validator import ScriptValidationError

        context = build_script_setup_context(
            state.script.private_table.module_id or "first_steps",
            loop_count=state.script.private_table.loop_count,
            days_per_loop=state.script.private_table.days_per_loop,
            errors=errors,
        )

        def _on_submit(choice: Any) -> PhaseSignal:
            from engine.rules.module_loader import apply_script_setup_payload

            if not isinstance(choice, dict):
                return self._build_script_setup_wait(
                    state,
                    errors=["非公开信息表提交格式错误：需要字典 payload"],
                )

            try:
                apply_script_setup_payload(state, choice)
            except ScriptValidationError as exc:
                return self._build_script_setup_wait(
                    state,
                    errors=[f"{issue.path}: {issue.message}" for issue in exc.issues],
                )
            except (FileNotFoundError, KeyError, TypeError, ValueError) as exc:
                return self._build_script_setup_wait(state, errors=[str(exc)])

            state.init_protagonist_hands()
            return PhaseComplete()

        return WaitForInput(
            input_type="script_setup",
            prompt="请填写非公开信息表",
            context=context,
            player="mastermind",
            callback=_on_submit,
        )


class LoopStartHandler(PhaseHandler):
    phase = GamePhase.LOOP_START

    def execute(self, state: GameState) -> PhaseSignal:
        initial_area_wait = self._request_loop_initial_area_choice(state)
        if initial_area_wait is not None:
            return initial_area_wait
        mandatory = self.ability_resolver.collect_abilities(
            state,
            timing=AbilityTiming.LOOP_START,
            ability_type=AbilityType.MANDATORY,
            alive_only=False,
        )
        return self._execute_mandatory_batch(
            state,
            mandatory,
            next_signal_factory=PhaseComplete,
        )

    def _request_loop_initial_area_choice(self, state: GameState) -> WaitForInput | None:
        from engine.models.enums import AreaId
        from engine.rules.character_loader import load_character_defs

        character_defs = load_character_defs()
        for character_id, character in state.characters.items():
            character_def = character_defs.get(character_id)
            if character_def is None:
                continue
            if character_def.initial_area_mode != "mastermind_each_loop":
                continue
            if character_id in state.loop_initial_area_choices_done:
                continue
            candidate_areas = list(character_def.initial_area_candidates) or [character_def.initial_area]
            option_values = [area.value for area in candidate_areas]
            option_selectors = [area_choice_selector(area.value) for area in candidate_areas]

            def _on_choice(choice: Any, *, target_id: str = character_id, allowed: set[str] = set(option_values)) -> PhaseSignal:
                selected_area = selector_area_id(choice)
                if selected_area is None and isinstance(choice, str):
                    selected_area = choice
                if selected_area not in allowed:
                    raise ValueError(f"invalid initial area choice for {target_id}: {selected_area!r}")
                area = AreaId(selected_area)
                target = state.characters[target_id]
                target.initial_area = area
                target.area = area
                state.loop_initial_area_choices_done.add(target_id)
                return self.execute(state)

            return WaitForInput(
                input_type="choose_initial_area",
                prompt=f"剧作家请选择 {character.name} 本轮初始区域",
                options=option_selectors,
                player="mastermind",
                callback=_on_choice,
            )
        return None


class TurnStartHandler(PhaseHandler):
    phase = GamePhase.TURN_START

    def execute(self, state: GameState) -> PhaseSignal:
        # 回合开始：结算回合开始触发效果
        return PhaseComplete()


class MastermindActionHandler(PhaseHandler):
    phase = GamePhase.MASTERMIND_ACTION

    def execute(self, state: GameState) -> PhaseSignal:
        return self._request_placement(state, placed_count=0)

    def _request_placement(self, state: GameState, *, placed_count: int) -> PhaseSignal:
        if placed_count >= 3:
            return PhaseComplete()

        available = [
            card for card in state.mastermind_hand.get_available()
            if all(
                not placement.face_down
                or placement.owner != PlayerRole.MASTERMIND
                or placement.card is not card
                for placement in state.placed_cards
            )
        ]

        def _on_choice(intent: Any) -> PhaseSignal:
            if not isinstance(intent, PlacementIntent):
                raise ValueError("mastermind must choose one placement intent each time")
            self._validate_placement_intent(
                state,
                intent,
                available_cards=available,
                block_against_roles={PlayerRole.MASTERMIND},
            )
            state.placed_cards.append(
                CardPlacement(
                    card=intent.card,
                    owner=PlayerRole.MASTERMIND,
                    target_type=intent.target_type,
                    target_id=intent.target_id,
                    face_down=True,
                )
            )
            return self._request_placement(state, placed_count=placed_count + 1)

        return WaitForInput(
            input_type="place_action_card",
            prompt=f"剧作家请放置第 {placed_count + 1} / 3 张行动牌",
            options=available,
            player="mastermind",
            callback=_on_choice,
        )

    @staticmethod
    def _validate_placement_intent(
        state: GameState,
        intent: PlacementIntent,
        *,
        available_cards: list[ActionCard],
        block_against_roles: set[PlayerRole],
    ) -> None:
        if intent.card not in available_cards:
            raise ValueError("selected card is not available")
        _validate_action_target(state, intent)
        _validate_action_slot(
            state,
            intent,
            block_against_roles=block_against_roles,
        )


class ProtagonistActionHandler(PhaseHandler):
    phase = GamePhase.PROTAGONIST_ACTION

    def execute(self, state: GameState) -> PhaseSignal:
        # 3 名主人公按队长起顺时针依次放牌（递归 callback 链）
        order = [(state.leader_index + i) % 3 for i in range(3)]
        return self._request_placement(state, order)

    def _request_placement(self, state: GameState, remaining: list[int]) -> PhaseSignal:
        """递归请求剩余主人公放牌"""
        if not remaining:
            return PhaseComplete()

        idx = remaining[0]
        rest = remaining[1:]
        hand = state.protagonist_hands[idx]
        available = hand.get_available()

        def _on_choice(intent: Any) -> PhaseSignal:
            if not isinstance(intent, PlacementIntent):
                raise ValueError("protagonist must choose one placement intent each time")
            MastermindActionHandler._validate_placement_intent(
                state,
                intent,
                available_cards=available,
                block_against_roles={
                    PlayerRole.PROTAGONIST_0,
                    PlayerRole.PROTAGONIST_1,
                    PlayerRole.PROTAGONIST_2,
                },
            )

            # 创建放置记录（不标记 is_used_this_loop）
            state.placed_cards.append(
                CardPlacement(
                    card=intent.card,
                    owner=hand.owner,
                    target_type=intent.target_type,
                    target_id=intent.target_id,
                    face_down=True,
                )
            )

            # 链接下一名主人公
            return self._request_placement(state, rest)

        return WaitForInput(
            input_type="place_action_card",
            prompt=f"主人公 {idx + 1} 请放置 1 张行动牌",
            options=available,
            player=f"protagonist_{idx}",
            callback=_on_choice,
        )


class ActionResolveHandler(PhaseHandler):
    phase = GamePhase.ACTION_RESOLVE
    _PHANTOM_CHARACTER_ID = "phantom"

    # CardType → (TokenType, delta)
    _TOKEN_EFFECTS: dict[CardType, tuple[TokenType, int]] = {
        CardType.INTRIGUE_PLUS_2:    (TokenType.INTRIGUE,  2),
        CardType.INTRIGUE_PLUS_1:    (TokenType.INTRIGUE,  1),
        CardType.PARANOIA_PLUS_1:    (TokenType.PARANOIA,  1),
        CardType.PARANOIA_PLUS_1_P:  (TokenType.PARANOIA,  1),
        CardType.PARANOIA_MINUS_1:   (TokenType.PARANOIA, -1),
        CardType.PARANOIA_MINUS_1_P: (TokenType.PARANOIA, -1),
        CardType.GOODWILL_PLUS_1:    (TokenType.GOODWILL,  1),
        CardType.GOODWILL_PLUS_1_MM: (TokenType.GOODWILL,  1),
        CardType.GOODWILL_PLUS_2:    (TokenType.GOODWILL,  2),
        CardType.DESPAIR_PLUS_1:     (TokenType.DESPAIR,   1),
        CardType.HOPE_PLUS_1:        (TokenType.HOPE,      1),
        CardType.PARANOIA_PLUS_2_P:  (TokenType.PARANOIA,  2),
    }
    # FORBID 牌 → 被禁止的 TokenType（None = 禁止移动）
    _FORBID_TOKEN: dict[CardType, Optional[TokenType]] = {
        CardType.FORBID_GOODWILL: TokenType.GOODWILL,
        CardType.FORBID_PARANOIA: TokenType.PARANOIA,
        CardType.FORBID_INTRIGUE: TokenType.INTRIGUE,
        CardType.FORBID_MOVEMENT: None,
    }
    _MOVEMENT_CARD_NORMALIZATION: dict[CardType, CardType] = {
        CardType.MOVE_HORIZONTAL: CardType.MOVE_HORIZONTAL,
        CardType.MOVE_HORIZONTAL_P: CardType.MOVE_HORIZONTAL,
        CardType.MOVE_VERTICAL: CardType.MOVE_VERTICAL,
        CardType.MOVE_VERTICAL_P: CardType.MOVE_VERTICAL,
        CardType.MOVE_DIAGONAL: CardType.MOVE_DIAGONAL,
    }
    _MOVEMENT_PAIR_COMPOSITION: dict[frozenset[CardType], CardType] = {
        frozenset({CardType.MOVE_HORIZONTAL, CardType.MOVE_VERTICAL}): CardType.MOVE_DIAGONAL,
        frozenset({CardType.MOVE_HORIZONTAL, CardType.MOVE_DIAGONAL}): CardType.MOVE_VERTICAL,
        frozenset({CardType.MOVE_VERTICAL, CardType.MOVE_DIAGONAL}): CardType.MOVE_HORIZONTAL,
    }

    def execute(self, state: GameState) -> PhaseSignal:
        placements = list(state.placed_cards)
        for placement in placements:
            placement.face_down = False

        mandatory = self._collect_action_resolve_candidates(
            state,
            ability_type=AbilityType.MANDATORY,
        )
        return self._execute_mandatory_batch(
            state,
            mandatory,
            next_signal_factory=lambda: self._request_optional_action_resolve_ability(state),
        )

    def _request_optional_action_resolve_ability(self, state: GameState) -> PhaseSignal:
        candidates = self._collect_action_resolve_candidates(
            state,
            ability_type=AbilityType.OPTIONAL,
        )
        if not candidates:
            return self._resolve_placed_cards(state)

        options: list[Any] = ["pass", *candidates]

        def _on_choice(choice: Any) -> PhaseSignal:
            if choice == "pass":
                return self._resolve_placed_cards(state)
            if choice not in candidates:
                raise ValueError("invalid action_resolve ability selection")
            return self._resolve_candidate(
                state,
                choice,
                next_signal_factory=lambda: self._request_optional_action_resolve_ability(state),
            )

        return WaitForInput(
            input_type="choose_action_resolve_ability",
            prompt="剧作家请选择行动结算阶段能力，或 pass",
            options=options,
            player="mastermind",
            callback=_on_choice,
        )

    def _collect_action_resolve_candidates(
        self,
        state: GameState,
        *,
        ability_type: AbilityType,
    ) -> list[AbilityCandidate]:
        candidates = self.ability_resolver.collect_abilities(
            state,
            timing=AbilityTiming.ACTION_RESOLVE,
            ability_type=ability_type,
        )
        return [
            candidate
            for candidate in candidates
            if self._is_action_resolve_candidate_effective(state, candidate)
        ]

    def _is_action_resolve_candidate_effective(
        self,
        state: GameState,
        candidate: AbilityCandidate,
    ) -> bool:
        if not candidate.ability.effects:
            return True

        owner_id = self._candidate_owner_id(candidate)
        for _, location_context in self._candidate_location_options(
            state,
            candidate,
            owner_id=owner_id,
        ):
            for effect in candidate.ability.effects:
                if effect.effect_type != EffectType.NULLIFY_CARD:
                    return True

                choice_request = self._resolve_effect_choice_options(
                    state,
                    owner_id=owner_id,
                    effect=effect,
                    location_context=location_context,
                )
                if choice_request is not None and bool(choice_request.options):
                    return True

                target_ids = self.ability_resolver.resolve_targets(
                    state,
                    owner_id=owner_id,
                    selector=effect.target,
                    alive_only=False,
                    location_context=location_context,
                )
                if any(
                    self._matches_nullify_card_target(state, target_id=target_id, effect=effect)
                    for target_id in target_ids
                ):
                    return True

        return False

    def _resolve_placed_cards(self, state: GameState) -> PhaseSignal:
        placements = list(state.placed_cards)
        if not placements:
            return PhaseComplete()

        self._apply_forbids(placements)

        for placement in placements:
            if placement.card.once_per_loop:
                placement.card.is_used_this_loop = True

        composites = self._build_composite_action_cards(placements)
        movement_effects = self._build_movement_effects(state, composites)
        movement_effects.extend(self._build_phantom_board_redirect_movement_effects(state, composites))
        if movement_effects:
            def _on_movement_resolved(result: Any) -> PhaseSignal:
                signal = self._resolution_result_to_signal(result, default_reason="action_resolve")
                if signal is not None:
                    return signal
                return self._resolve_non_movement_placed_cards(state, composites)

            return self._resolve_effect_batch_with_servant_follow(
                state,
                movement_effects,
                sequential=False,
                perpetrator_id="",
                location_context=None,
                before_resolve=None,
                on_resolved=_on_movement_resolved,
            )

        return self._resolve_non_movement_placed_cards(state, composites)

    def _resolve_non_movement_placed_cards(
        self,
        state: GameState,
        composites: list[CompositeActionCard],
    ) -> PhaseSignal:
        # phantom 的版图投影按批次重算：先吃移动批次，再在移动后的版图上吃非移动批次。
        non_movement_effects = self._build_non_movement_effects(composites)
        non_movement_effects.extend(self._build_phantom_board_redirect_non_movement_effects(state, composites))
        if not non_movement_effects:
            return PhaseComplete()
        result = self.atomic_resolver.resolve(state, non_movement_effects, sequential=False)
        signal = self._resolution_result_to_signal(result, default_reason="action_resolve")
        if signal is not None:
            return signal
        return PhaseComplete()

    def _build_composite_action_cards(
        self,
        placements: list[CardPlacement],
    ) -> list[CompositeActionCard]:
        groups: dict[tuple[str, str], list[CardPlacement]] = {}
        for placement in placements:
            if placement.nullified:
                continue
            key = (placement.target_type, placement.target_id)
            groups.setdefault(key, []).append(placement)

        composites: list[CompositeActionCard] = []
        for (target_type, target_id), grouped_placements in groups.items():
            composites.append(
                CompositeActionCard(
                    target_type=target_type,
                    target_id=target_id,
                    placements=grouped_placements,
                    movement_card_type=self._compose_movement_card_type(grouped_placements),
                )
            )
        return composites

    def _build_movement_effects(
        self,
        state: GameState,
        composites: list[CompositeActionCard],
    ) -> list[Effect]:
        effects: list[Effect] = []
        for composite in composites:
            if composite.movement_card_type is None or composite.target_type != "character":
                continue
            effect = self._movement_effect_for_target(
                state,
                target_id=composite.target_id,
                card_type=composite.movement_card_type,
            )
            if effect is not None:
                effects.append(effect)
        return effects

    def _build_phantom_board_redirect_movement_effects(
        self,
        state: GameState,
        composites: list[CompositeActionCard],
    ) -> list[Effect]:
        phantom = self._phantom_character(state)
        if phantom is None:
            return []

        effects: list[Effect] = []
        for composite in composites:
            if composite.target_type != "board" or composite.target_id != phantom.area.value:
                continue
            if composite.movement_card_type is None:
                continue
            effect = self._movement_effect_for_target(
                state,
                target_id=phantom.character_id,
                card_type=composite.movement_card_type,
            )
            if effect is not None:
                effects.append(effect)
        return effects

    def _build_non_movement_effects(
        self,
        composites: list[CompositeActionCard],
    ) -> list[Effect]:
        placements = [
            placement
            for composite in composites
            for placement in composite.placements
            if not placement.card.is_movement and placement.card.card_type not in self._FORBID_TOKEN
        ]
        return self._token_effects_from_placements(placements)

    def _build_phantom_board_redirect_non_movement_effects(
        self,
        state: GameState,
        composites: list[CompositeActionCard],
    ) -> list[Effect]:
        phantom = self._phantom_character(state)
        if phantom is None:
            return []

        placements = [
            placement
            for composite in composites
            if composite.target_type == "board" and composite.target_id == phantom.area.value
            for placement in composite.placements
            if not placement.nullified
            and not placement.card.is_movement
            and placement.card.card_type not in self._FORBID_TOKEN
        ]
        return self._token_effects_from_placements(placements, target_id=phantom.character_id)

    def _token_effects_from_placements(
        self,
        placements: list[CardPlacement],
        *,
        target_id: str | None = None,
    ) -> list[Effect]:
        hope_count = sum(1 for placement in placements if placement.card.card_type == CardType.HOPE_PLUS_1)

        effects: list[Effect] = []
        for placement in placements:
            token_info = self._token_effect_for_card(
                placement.card.card_type,
                treat_hope_as_goodwill=hope_count > 1,
            )
            if token_info is None:
                continue
            token_type, delta = token_info
            effects.append(
                Effect(
                    effect_type=EffectType.PLACE_TOKEN if delta > 0 else EffectType.REMOVE_TOKEN,
                    target=target_id or placement.target_id,
                    token_type=token_type,
                    amount=abs(delta),
                )
            )
        return effects

    def _movement_effect_for_target(
        self,
        state: GameState,
        *,
        target_id: str,
        card_type: CardType,
    ) -> Effect | None:
        dest = self._movement_destination(state, target_id, card_type)
        if dest is None:
            return None
        return Effect(
            effect_type=EffectType.MOVE_CHARACTER,
            target=target_id,
            value=dest,
        )

    @staticmethod
    def _phantom_character(state: GameState) -> Any | None:
        phantom = state.characters.get(ActionResolveHandler._PHANTOM_CHARACTER_ID)
        if phantom is None or not phantom.is_active():
            return None
        return phantom

    def _token_effect_for_card(
        self,
        card_type: CardType,
        *,
        treat_hope_as_goodwill: bool,
    ) -> tuple[TokenType, int] | None:
        if card_type == CardType.HOPE_PLUS_1 and treat_hope_as_goodwill:
            return (TokenType.GOODWILL, 1)
        return self._TOKEN_EFFECTS.get(card_type)

    def _compose_movement_card_type(
        self,
        placements: list[CardPlacement],
    ) -> Optional[CardType]:
        movement_types = [
            self._MOVEMENT_CARD_NORMALIZATION[placement.card.card_type]
            for placement in placements
            if placement.card.is_movement
        ]
        if not movement_types:
            return None

        composite = movement_types[0]
        for movement_type in movement_types[1:]:
            composite = self._combine_movement_card_types(composite, movement_type)
        return composite

    def _combine_movement_card_types(self, left: CardType, right: CardType) -> CardType:
        if left == right:
            return left
        return self._MOVEMENT_PAIR_COMPOSITION[frozenset({left, right})]

    def _apply_forbids(self, placements: list[CardPlacement]) -> None:
        """
        FORBID 预处理：
        - 禁止密谋是特殊结算：场上同时存在 2 张或以上时，这些禁止密谋全部失效
        - 其余禁止牌：生效后无效化同一位置对应类型的行动牌
        """
        forbid_intrigues = [
            placement
            for placement in placements
            if not placement.nullified and placement.card.card_type == CardType.FORBID_INTRIGUE
        ]
        if len(forbid_intrigues) >= 2:
            for placement in forbid_intrigues:
                placement.nullified = True

        for forbid in placements:
            if forbid.nullified:
                continue
            forbid_type = forbid.card.card_type
            if forbid_type not in self._FORBID_TOKEN:
                continue

            blocked_token = self._FORBID_TOKEN[forbid_type]
            for placement in placements:
                if placement is forbid or placement.nullified or placement.target_id != forbid.target_id:
                    continue
                if blocked_token is None:
                    if placement.card.is_movement:
                        placement.nullified = True
                    continue

                token_info = self._TOKEN_EFFECTS.get(placement.card.card_type)
                if token_info and token_info[0] == blocked_token:
                    placement.nullified = True

    def _movement_destination(
        self, state: GameState, char_id: str, card_type: CardType
    ) -> Optional[str]:
        """根据角色当前区域与牌类型，计算移动目标区域 ID"""
        ch = state.characters.get(char_id)
        if ch is None or not ch.is_active():
            return None
        board = state.board
        if card_type in (CardType.MOVE_HORIZONTAL, CardType.MOVE_HORIZONTAL_P):
            dest = board.get_horizontal_adjacent(ch.area)
        elif card_type in (CardType.MOVE_VERTICAL, CardType.MOVE_VERTICAL_P):
            dest = board.get_vertical_adjacent(ch.area)
        elif card_type == CardType.MOVE_DIAGONAL:
            dest = board.get_diagonal_adjacent(ch.area)
        else:
            return None
        return dest.value if dest else None


class PlaywrightAbilityHandler(PhaseHandler):
    phase = GamePhase.PLAYWRIGHT_ABILITY

    def execute(self, state: GameState) -> PhaseSignal:
        mandatory = self.ability_resolver.collect_abilities(
            state,
            timing=AbilityTiming.PLAYWRIGHT_ABILITY,
            ability_type=AbilityType.MANDATORY,
        )
        return self._execute_mandatory_batch(
            state,
            mandatory,
            next_signal_factory=lambda: self._request_optional_playwright_ability(state),
        )

    def _request_optional_playwright_ability(self, state: GameState) -> PhaseSignal:
        optional_candidates = [
            *self.ability_resolver.collect_abilities(
                state,
                timing=AbilityTiming.PLAYWRIGHT_ABILITY,
                ability_type=AbilityType.OPTIONAL,
            ),
            *self.ability_resolver.collect_playwright_goodwill_abilities(state),
        ]
        candidates = self._filter_candidates_with_available_targets(
            state,
            optional_candidates,
        )
        if not candidates:
            return PhaseComplete()

        options: list[Any] = ["pass", *candidates]

        def _on_choice(choice: Any) -> PhaseSignal:
            if choice == "pass":
                return PhaseComplete()
            if choice not in candidates:
                raise ValueError("invalid playwright ability selection")
            return self._resolve_candidate(
                state,
                choice,
                next_signal_factory=lambda: self._request_optional_playwright_ability(state),
            )

        return WaitForInput(
            input_type="choose_playwright_ability",
            prompt="剧作家请选择要声明的能力，或 pass",
            options=options,
            player="mastermind",
            callback=_on_choice,
        )


class ProtagonistAbilityHandler(PhaseHandler):
    phase = GamePhase.PROTAGONIST_ABILITY
    _AI_ABILITY_ID = "goodwill:ai:1"
    _INFORMANT_ABILITY_ID = "goodwill:informant:1"
    _APPRAISER_ABILITY_ID = "goodwill:appraiser:1"
    _SISTER_ABILITY_ID = "goodwill:sister:1"

    def execute(self, state: GameState) -> PhaseSignal:
        return self._request_goodwill_ability(state)

    def _request_goodwill_ability(self, state: GameState) -> PhaseSignal:
        candidates = self._filter_candidates_with_available_targets(
            state,
            self.ability_resolver.collect_goodwill_abilities(state),
        )
        if not candidates:
            return PhaseComplete()

        leader = f"protagonist_{state.leader_index}"
        options: list[Any] = ["pass", *candidates]

        def _on_choice(choice: Any) -> PhaseSignal:
            if choice == "pass":
                return PhaseComplete()
            if choice not in candidates:
                raise ValueError("invalid goodwill ability selection")
            return self._handle_goodwill_declaration(state, choice)

        return WaitForInput(
            input_type="choose_goodwill_ability",
            prompt="队长请选择要声明的友好能力，或 pass",
            options=options,
            player=leader,
            callback=_on_choice,
        )

    def _request_sister_goodwill_ability(self, state: GameState) -> PhaseSignal:
        owner = state.characters.get("sister")
        if owner is None or not owner.is_active():
            return PhaseComplete()

        options = [
            character_id
            for character_id, character in state.characters.items()
            if character_id != owner.character_id
            and character.is_active()
            and character.area == owner.area
            and Attribute.ADULT in character.attributes
        ]
        if not options:
            return PhaseComplete()

        def _on_choice(choice: Any) -> PhaseSignal:
            target_id = str(choice)
            if target_id not in options:
                raise ValueError(f"invalid sister target: {choice!r}")
            target_candidates = self._filter_candidates_with_available_targets(
                state,
                [
                    candidate
                    for candidate in self.ability_resolver.collect_goodwill_abilities(state)
                    if candidate.source_id == target_id
                ],
            )
            if not target_candidates:
                return PhaseComplete()
            sister_candidate = self._sister_candidate(owner)
            self._emit_ability_declared(sister_candidate)
            self.ability_resolver.mark_ability_used(state, sister_candidate)
            return self._request_sister_target_goodwill_ability(
                state,
                target_id=target_id,
                target_candidates=target_candidates,
            )

        return WaitForInput(
            input_type="choose_ability_target",
            prompt="请选择要被妹妹强制使用友好能力的成人角色",
            options=options,
            player=f"protagonist_{state.leader_index}",
            callback=_on_choice,
        )

    def _sister_candidate(self, owner: Any) -> AbilityCandidate:
        return AbilityCandidate(
            source_kind="goodwill",
            source_id=owner.character_id,
            ability=Ability(
                ability_id=self._SISTER_ABILITY_ID,
                name="妹妹 友好能力1",
                ability_type=AbilityType.OPTIONAL,
                timing=AbilityTiming.PROTAGONIST_ABILITY,
                description=owner.goodwill_ability_texts[0] if owner.goodwill_ability_texts else "",
                effects=[],
                goodwill_requirement=5,
                once_per_loop=True,
                can_be_refused=True,
            ),
        )

    def _request_sister_target_goodwill_ability(
        self,
        state: GameState,
        *,
        target_id: str,
        target_candidates: list[AbilityCandidate],
    ) -> PhaseSignal:
        if len(target_candidates) == 1:
            return self._resolve_candidate(
                state,
                target_candidates[0],
                next_signal_factory=PhaseComplete,
            )

        def _on_choice(choice: Any) -> PhaseSignal:
            candidate = choice
            if candidate not in target_candidates:
                raise ValueError("invalid sister goodwill ability selection")
            return self._resolve_candidate(
                state,
                candidate,
                next_signal_factory=PhaseComplete,
            )

        return WaitForInput(
            input_type="choose_goodwill_ability",
            prompt=f"请选择由 {state.characters[target_id].name} 使用的友好能力",
            options=target_candidates,
            player=f"protagonist_{state.leader_index}",
            callback=_on_choice,
        )

    def _handle_goodwill_declaration(
        self,
        state: GameState,
        candidate: AbilityCandidate,
    ) -> PhaseSignal:
        if candidate.ability.ability_id == self._SISTER_ABILITY_ID:
            return self._resolve_goodwill_ability(state, candidate)
        owner_id = candidate.source_id
        should_ignore = self.ability_resolver.goodwill_should_be_ignored(state, owner_id)
        if candidate.ability.can_be_refused and not should_ignore:
            def _on_refuse(choice: Any) -> PhaseSignal:
                if choice not in {"allow", "refuse"}:
                    raise ValueError("invalid goodwill response")
                if choice == "refuse":
                    self.event_bus.emit(GameEvent(
                        GameEventType.ABILITY_REFUSED,
                        {"character_id": owner_id, "ability_id": candidate.ability.ability_id},
                    ))
                    self.ability_resolver.mark_ability_used(state, candidate)
                    return self._request_goodwill_ability(state)
                return self._resolve_goodwill_ability(state, candidate)

            return WaitForInput(
                input_type="respond_goodwill_ability",
                prompt="剧作家是否拒绝该友好能力？",
                options=["allow", "refuse"],
                player="mastermind",
                callback=_on_refuse,
            )
        return self._resolve_goodwill_ability(state, candidate)

    def _resolve_goodwill_ability(
        self,
        state: GameState,
        candidate: AbilityCandidate,
    ) -> PhaseSignal:
        if candidate.ability.ability_id == self._SISTER_ABILITY_ID:
            return self._request_sister_goodwill_ability(state)
        if candidate.source_id not in state.characters:
            return self._request_goodwill_ability(state)
        if candidate.ability.ability_id == self._AI_ABILITY_ID:
            return self._resolve_ai_goodwill(
                state,
                candidate,
                next_signal_factory=lambda: self._request_goodwill_ability(state),
            )
        if candidate.ability.ability_id == self._INFORMANT_ABILITY_ID:
            return self._resolve_informant_goodwill(
                state,
                candidate,
                next_signal_factory=lambda: self._request_goodwill_ability(state),
            )
        if candidate.ability.ability_id == self._APPRAISER_ABILITY_ID:
            return self._resolve_appraiser_goodwill(
                state,
                candidate,
                next_signal_factory=lambda: self._request_goodwill_ability(state),
            )
        return self._resolve_candidate(
            state,
            candidate,
            next_signal_factory=lambda: self._request_goodwill_ability(state),
        )

    def _resolve_ai_goodwill(
        self,
        state: GameState,
        candidate: AbilityCandidate,
        *,
        next_signal_factory: Callable[[], PhaseSignal],
    ) -> PhaseSignal:
        owner = state.characters.get(candidate.source_id)
        if owner is None:
            return next_signal_factory()
        options = self._available_public_incident_options(state)
        if not options:
            self.ability_resolver.mark_ability_used(state, candidate)
            return next_signal_factory()
        self._emit_ability_declared(candidate)
        incident_resolver = IncidentResolver(self.event_bus, self.atomic_resolver)

        def _on_incident(choice: Any) -> PhaseSignal:
            public_index = self._coerce_public_incident_index(choice)
            if public_index is None:
                raise ValueError(f"invalid public incident choice: {choice!r}")
            selected = next(
                (option for option in options if int(option.get("public_incident_index", -1)) == public_index),
                None,
            )
            if selected is None:
                raise ValueError(f"invalid public incident choice: {choice!r}")
            schedule = self._build_ai_incident_schedule(
                state,
                public_index=public_index,
                perpetrator_id=owner.character_id,
            )
            if schedule is None:
                self.ability_resolver.mark_ability_used(state, candidate)
                return next_signal_factory()
            incident_def = state.incident_defs.get(schedule.incident_id)
            return self._continue_ai_incident_resolution(
                state,
                candidate,
                schedule=schedule,
                incident_def=incident_def,
                incident_resolver=incident_resolver,
                next_signal_factory=next_signal_factory,
            )

        return WaitForInput(
            input_type="choose_public_incident",
            prompt="队长请选择公开信息表中的事件",
            options=options,
            player=f"protagonist_{state.leader_index}",
            callback=_on_incident,
        )

    def _continue_ai_incident_resolution(
        self,
        state: GameState,
        candidate: AbilityCandidate,
        *,
        schedule,
        incident_def,
        incident_resolver: IncidentResolver,
        next_signal_factory: Callable[[], PhaseSignal],
    ) -> PhaseSignal:
        if incident_def is None:
            self.ability_resolver.mark_ability_used(state, candidate)
            return next_signal_factory()

        runtime_choice = incident_resolver.next_runtime_choice(state, schedule, incident_def)
        if runtime_choice is None:
            result = incident_resolver.resolve_effect_only(
                state,
                schedule,
                incident_def,
            )
            self.ability_resolver.mark_ability_used(state, candidate)
            signal = self._resolution_result_to_signal(
                result,
                default_reason=candidate.ability.ability_id,
            )
            if signal is not None:
                return signal
            return next_signal_factory()

        choice_kind, options = runtime_choice
        if not options:
            self.ability_resolver.mark_ability_used(state, candidate)
            return next_signal_factory()

        if choice_kind == "character":
            input_type = "choose_incident_character"
            prompt = "队长请选择事件角色目标"
        elif choice_kind == "area":
            input_type = "choose_incident_area"
            prompt = "队长请选择事件版图目标"
        elif choice_kind == "token":
            input_type = "choose_incident_token_type"
            prompt = "队长请选择事件指示物类型"
        else:
            raise ValueError(f"unsupported ai incident choice kind: {choice_kind}")

        def _on_choice(choice: Any) -> PhaseSignal:
            selected = str(choice)
            if selected not in options:
                raise ValueError(f"invalid ai incident {choice_kind}: {choice!r}")
            if choice_kind == "character":
                schedule.target_selectors.append(character_choice_selector(selected))
                schedule.target_character_ids.append(selected)
            elif choice_kind == "area":
                schedule.target_selectors.append(area_choice_selector(selected))
                schedule.target_area_ids.append(selected)
            else:
                schedule.chosen_token_types.append(selected)
            return self._continue_ai_incident_resolution(
                state,
                candidate,
                schedule=schedule,
                incident_def=incident_def,
                incident_resolver=incident_resolver,
                next_signal_factory=next_signal_factory,
            )

        return WaitForInput(
            input_type=input_type,
            prompt=prompt,
            options=options,
            player=f"protagonist_{state.leader_index}",
            callback=_on_choice,
        )

    @staticmethod
    def _available_public_incident_options(state: GameState) -> list[dict[str, Any]]:
        options: list[dict[str, Any]] = []
        for index in range(state.script.public_incident_count()):
            entry = state.script.public_incident_entry(index)
            ref = state.script.private_incident_ref_for_public_index(index)
            if entry is None or not ref or ref not in state.incident_defs:
                continue
            options.append(
                {
                    "kind": "public_incident",
                    "public_incident_index": index,
                    "name": str(entry.get("name", ref)),
                    "day": entry.get("day", "?"),
                }
            )
        return options

    @staticmethod
    def _coerce_public_incident_index(choice: Any) -> int | None:
        if isinstance(choice, dict):
            raw = choice.get("public_incident_index")
            if isinstance(raw, int):
                return raw
            if isinstance(raw, str) and raw.isdigit():
                return int(raw)
            return None
        if isinstance(choice, int):
            return choice
        if isinstance(choice, str) and choice.isdigit():
            return int(choice)
        return None

    @staticmethod
    def _build_ai_incident_schedule(
        state: GameState,
        *,
        public_index: int,
        perpetrator_id: str,
    ):
        ref = state.script.private_incident_ref_for_public_index(public_index)
        if not ref:
            return None
        entry = state.script.public_incident_entry(public_index) or {}
        day = entry.get("day", state.current_day)
        if not isinstance(day, int):
            day = state.current_day
        from engine.models.incident import IncidentSchedule
        return IncidentSchedule(
            ref,
            day=day,
            perpetrator_id=perpetrator_id,
        )

    def _resolve_informant_goodwill(
        self,
        state: GameState,
        candidate: AbilityCandidate,
        *,
        next_signal_factory: Callable[[], PhaseSignal],
    ) -> PhaseSignal:
        self._emit_ability_declared(candidate)
        if state.script.private_table.module_id == "first_steps":
            return self._reveal_informant_rule_x(
                state,
                candidate,
                rule_x_id=self._default_first_steps_rule_x_id(state),
                next_signal_factory=next_signal_factory,
            )

        available_rule_ids = self._available_module_rule_x_ids(state)
        if not available_rule_ids:
            self.ability_resolver.mark_ability_used(state, candidate)
            return next_signal_factory()

        def _on_declared(choice: Any) -> PhaseSignal:
            declared_rule_x_id = str(choice)
            if declared_rule_x_id not in available_rule_ids:
                raise ValueError(f"invalid declared rule_x: {choice!r}")
            return self._request_informant_reveal_choice(
                state,
                candidate,
                declared_rule_x_id=declared_rule_x_id,
                next_signal_factory=next_signal_factory,
            )

        return WaitForInput(
            input_type="choose_rule_x_declaration",
            prompt="队长请选择要声明的规则 X",
            options=available_rule_ids,
            player=f"protagonist_{state.leader_index}",
            callback=_on_declared,
        )

    def _request_informant_reveal_choice(
        self,
        state: GameState,
        candidate: AbilityCandidate,
        *,
        declared_rule_x_id: str,
        next_signal_factory: Callable[[], PhaseSignal],
    ) -> PhaseSignal:
        selected_rule_ids = [rule.rule_id for rule in state.script.private_table.rules_x]
        revealable = [
            rule_id for rule_id in selected_rule_ids
            if rule_id != declared_rule_x_id
        ]
        if not revealable:
            revealable = list(selected_rule_ids)
        if not revealable:
            self.ability_resolver.mark_ability_used(state, candidate)
            return next_signal_factory()
        if len(revealable) == 1:
            return self._reveal_informant_rule_x(
                state,
                candidate,
                rule_x_id=revealable[0],
                next_signal_factory=next_signal_factory,
            )

        def _on_reveal(choice: Any) -> PhaseSignal:
            revealed_rule_x_id = str(choice)
            if revealed_rule_x_id not in revealable:
                raise ValueError(f"invalid revealed rule_x: {choice!r}")
            return self._reveal_informant_rule_x(
                state,
                candidate,
                rule_x_id=revealed_rule_x_id,
                next_signal_factory=next_signal_factory,
            )

        return WaitForInput(
            input_type="choose_rule_x_reveal",
            prompt="剧作家请选择要公开的规则 X",
            options=revealable,
            player="mastermind",
            callback=_on_reveal,
        )

    def _reveal_informant_rule_x(
        self,
        state: GameState,
        candidate: AbilityCandidate,
        *,
        rule_x_id: str,
        next_signal_factory: Callable[[], PhaseSignal],
    ) -> PhaseSignal:
        if rule_x_id not in state.revealed_rule_x_ids:
            state.revealed_rule_x_ids.append(rule_x_id)
        self.event_bus.emit(GameEvent(GameEventType.RULE_X_REVEALED, {"rule_x_id": rule_x_id}))
        self.ability_resolver.mark_ability_used(state, candidate)
        return next_signal_factory()

    @staticmethod
    def _available_module_rule_x_ids(state: GameState) -> list[str]:
        if state.module_def is not None:
            return [rule.rule_id for rule in state.module_def.rules_x]
        return [rule.rule_id for rule in state.script.private_table.rules_x]

    @staticmethod
    def _default_first_steps_rule_x_id(state: GameState) -> str:
        if state.script.private_table.rules_x:
            return state.script.private_table.rules_x[0].rule_id
        available = ProtagonistAbilityHandler._available_module_rule_x_ids(state)
        if not available:
            raise ValueError("first_steps has no available rule_x")
        return available[0]

    def _resolve_appraiser_goodwill(
        self,
        state: GameState,
        candidate: AbilityCandidate,
        *,
        next_signal_factory: Callable[[], PhaseSignal],
    ) -> PhaseSignal:
        owner = state.characters.get(candidate.source_id)
        if owner is None:
            return next_signal_factory()
        options = [
            character_id
            for character_id, character in state.characters.items()
            if character_id != owner.character_id
            and character.area == owner.area
            and character.is_active()
        ]
        if len(options) < 2:
            self.ability_resolver.mark_ability_used(state, candidate)
            return next_signal_factory()
        self._emit_ability_declared(candidate)

        def _on_source(choice: Any) -> PhaseSignal:
            source_id = str(choice)
            if source_id not in options:
                raise ValueError(f"invalid appraiser source: {choice!r}")
            return self._request_appraiser_target(
                state,
                candidate,
                source_id=source_id,
                options=options,
                next_signal_factory=next_signal_factory,
            )

        return WaitForInput(
            input_type="choose_ability_target",
            prompt="请选择要移出指示物的角色 A",
            options=options,
            player=f"protagonist_{state.leader_index}",
            callback=_on_source,
        )

    def _request_appraiser_target(
        self,
        state: GameState,
        candidate: AbilityCandidate,
        *,
        source_id: str,
        options: list[str],
        next_signal_factory: Callable[[], PhaseSignal],
    ) -> PhaseSignal:
        target_options = [character_id for character_id in options if character_id != source_id]

        def _on_target(choice: Any) -> PhaseSignal:
            target_id = str(choice)
            if target_id not in target_options:
                raise ValueError(f"invalid appraiser target: {choice!r}")
            return self._request_appraiser_token_move(
                state,
                candidate,
                first_id=source_id,
                second_id=target_id,
                next_signal_factory=next_signal_factory,
            )

        return WaitForInput(
            input_type="choose_ability_target",
            prompt="请选择角色 B",
            options=target_options,
            player=f"protagonist_{state.leader_index}",
            callback=_on_target,
        )

    def _request_appraiser_token_move(
        self,
        state: GameState,
        candidate: AbilityCandidate,
        *,
        first_id: str,
        second_id: str,
        next_signal_factory: Callable[[], PhaseSignal],
    ) -> PhaseSignal:
        first = state.characters.get(first_id)
        second = state.characters.get(second_id)
        if first is None or second is None:
            self.ability_resolver.mark_ability_used(state, candidate)
            return next_signal_factory()
        move_options = self._appraiser_move_options(state, first_id=first_id, second_id=second_id)
        if not move_options:
            self.ability_resolver.mark_ability_used(state, candidate)
            return next_signal_factory()

        def _on_move(choice: Any) -> PhaseSignal:
            move_key = str(choice)
            move = self._parse_appraiser_move_option(move_key)
            if move is None or move_key not in move_options:
                raise ValueError(f"invalid appraiser token move: {choice!r}")
            source_id, token_name, target_id = move
            result = self.atomic_resolver.resolve(
                state,
                [
                    ScopedEffect(
                        effect=Effect(
                            effect_type=EffectType.MOVE_TOKEN,
                            target=target_id,
                            token_type=TokenType(token_name),
                            amount=1,
                        ),
                        perpetrator_id=source_id,
                    )
                ],
            )
            self.ability_resolver.mark_ability_used(state, candidate)
            signal = self._resolution_result_to_signal(
                result,
                default_reason=candidate.ability.ability_id,
            )
            if signal is not None:
                return signal
            return next_signal_factory()

        return WaitForInput(
            input_type="choose_ability_token_move",
            prompt="请选择要执行的指示物移动",
            options=move_options,
            player=f"protagonist_{state.leader_index}",
            callback=_on_move,
        )

    def _appraiser_move_options(
        self,
        state: GameState,
        *,
        first_id: str,
        second_id: str,
    ) -> list[str]:
        options: list[str] = []
        for source_id, target_id in ((first_id, second_id), (second_id, first_id)):
            source = state.characters.get(source_id)
            if source is None:
                continue
            for token in TokenType:
                if source.tokens.get(token) <= 0:
                    continue
                options.append(self._build_appraiser_move_option(
                    source_id=source_id,
                    token_name=token.value,
                    target_id=target_id,
                ))
        return options

    @staticmethod
    def _build_appraiser_move_option(
        *,
        source_id: str,
        token_name: str,
        target_id: str,
    ) -> str:
        return f"{source_id}|{token_name}|{target_id}"

    @staticmethod
    def _parse_appraiser_move_option(value: str) -> tuple[str, str, str] | None:
        parts = value.split("|")
        if len(parts) != 3:
            return None
        source_id, token_name, target_id = parts
        return source_id, token_name, target_id


class IncidentHandler(PhaseHandler):
    phase = GamePhase.INCIDENT

    def __init__(self, event_bus: EventBus,
                 atomic_resolver: AtomicResolver) -> None:
        super().__init__(event_bus, atomic_resolver)
        self.incident_resolver = IncidentResolver(event_bus, atomic_resolver)

    def execute(self, state: GameState) -> PhaseSignal:
        """
        事件阶段。

        阶段处理器只负责当天事件调度；事件触发判定、公开语义与
        效果结算由 IncidentResolver 统一负责。
        """
        schedules = state.get_incidents_for_day(state.current_day)
        return self._resolve_schedules(state, schedules, index=0)

    def _resolve_schedules(
        self,
        state: GameState,
        schedules: list[Any],
        *,
        index: int,
        servant_follow_choices: dict[str, str] | None = None,
    ) -> PhaseSignal:
        if index >= len(schedules):
            return PhaseComplete()

        schedule = schedules[index]
        choices = dict(servant_follow_choices or {})
        request = self.incident_resolver.next_servant_follow_choice(
            state,
            schedule,
            servant_follow_choices=choices,
        )
        if request is not None:
            return self._build_servant_follow_wait(
                state,
                request,
                schedules=schedules,
                schedule_index=index,
                servant_follow_choices=choices,
            )

        result = self.incident_resolver.resolve_schedule(
            state,
            schedule,
            servant_follow_choices=choices,
        )
        if result.outcome in (Outcome.PROTAGONIST_DEATH, Outcome.PROTAGONIST_FAILURE):
            return ForceLoopEnd(reason=schedule.incident_id)
        return self._resolve_schedules(state, schedules, index=index + 1)

    def _build_servant_follow_wait(
        self,
        state: GameState,
        request: ServantFollowChoiceRequest,
        *,
        schedules: list[Any] | None = None,
        schedule_index: int | None = None,
        servant_follow_choices: dict[str, str] | None = None,
        sequential: bool | None = None,
        effects: list[Effect | ScopedEffect] | None = None,
        perpetrator_id: str | None = None,
        location_context: AbilityLocationContext | None = None,
        before_resolve: Callable[[], None] | None = None,
        on_resolved: Callable[[Any], PhaseSignal] | None = None,
    ) -> WaitForInput:
        if schedules is None or schedule_index is None:
            return super()._build_servant_follow_wait(  # type: ignore[misc]
                state,
                request,
                sequential=bool(sequential),
                effects=effects or [],
                perpetrator_id=perpetrator_id or "",
                location_context=location_context,
                before_resolve=before_resolve,
                on_resolved=on_resolved or (lambda _result: PhaseComplete()),
                servant_follow_choices=servant_follow_choices or {},
            )

        servant = state.characters.get(request.servant_id)
        servant_name = servant.name if servant is not None else request.servant_id
        player = f"protagonist_{state.leader_index}"
        choices = dict(servant_follow_choices or {})

        def _on_choice(choice: Any) -> PhaseSignal:
            selected = str(choice)
            if selected not in request.options:
                raise ValueError(f"invalid servant follow target: {selected!r}")
            updated = dict(choices)
            updated[request.servant_id] = selected
            return self._resolve_schedules(
                state,
                schedules,
                index=schedule_index,
                servant_follow_choices=updated,
            )

        return WaitForInput(
            input_type="choose_ability_target",
            prompt=f"请选择 {servant_name} 要跟随移动的角色",
            options=request.options,
            player=player,
            callback=_on_choice,
        )


class LeaderRotateHandler(PhaseHandler):
    phase = GamePhase.LEADER_ROTATE

    def execute(self, state: GameState) -> PhaseSignal:
        state.rotate_leader()
        return PhaseComplete()


class TurnEndHandler(PhaseHandler):
    phase = GamePhase.TURN_END

    def execute(self, state: GameState) -> PhaseSignal:
        timings = [AbilityTiming.TURN_END]
        if state.is_final_day:
            timings.append(AbilityTiming.FINAL_DAY_TURN_END)

        mandatory: list[AbilityCandidate] = []
        for timing in timings:
            mandatory.extend(
                self.ability_resolver.collect_abilities(
                    state,
                    timing=timing,
                    ability_type=AbilityType.MANDATORY,
                )
            )
        return self._execute_mandatory_batch(
            state,
            mandatory,
            next_signal_factory=lambda: self._request_optional_turn_end_ability(state, timings),
        )

    def _request_optional_turn_end_ability(
        self,
        state: GameState,
        timings: list[AbilityTiming],
    ) -> PhaseSignal:
        candidates: list[AbilityCandidate] = []
        for timing in timings:
            candidates.extend(
                self.ability_resolver.collect_abilities(
                    state,
                    timing=timing,
                    ability_type=AbilityType.OPTIONAL,
                )
            )
        candidates = self._filter_candidates_with_available_targets(state, candidates)
        if not candidates:
            return PhaseComplete()

        options: list[Any] = ["pass", *candidates]

        def _on_choice(choice: Any) -> PhaseSignal:
            if choice == "pass":
                return PhaseComplete()
            if choice not in candidates:
                raise ValueError("invalid turn_end ability selection")
            return self._resolve_candidate(
                state,
                choice,
                next_signal_factory=lambda: self._request_optional_turn_end_ability(state, timings),
            )

        return WaitForInput(
            input_type="choose_turn_end_ability",
            prompt="剧作家请选择回合结束阶段能力，或 pass",
            options=options,
            player="mastermind",
            callback=_on_choice,
        )


class LoopEndHandler(PhaseHandler):
    phase = GamePhase.LOOP_END

    def execute(self, state: GameState) -> PhaseSignal:
        candidates = self.ability_resolver.collect_abilities(
            state,
            timing=AbilityTiming.LOOP_END,
            ability_type=None,
            alive_only=False,
        )
        return self._execute_loop_end_candidates(state, candidates)

    def _execute_loop_end_candidates(
        self,
        state: GameState,
        candidates: list[AbilityCandidate],
    ) -> PhaseSignal:
        if not candidates:
            return self._finalize_loop_end(state)

        candidate = candidates[0]
        owner_id = self._candidate_owner_id(candidate)
        location_options = self._candidate_location_options(
            state,
            candidate,
            owner_id=owner_id,
        )
        if len(location_options) > 1:
            return self._build_candidate_location_wait(
                state,
                candidate,
                owner_id=owner_id,
                location_options=location_options,
                next_signal_factory=lambda: self._execute_loop_end_candidates(state, candidates[1:]),
            )
        location_context = location_options[0][1]
        prepared = self._prepare_effects_for_resolution(
            state,
            candidate,
            owner_id=owner_id,
            location_context=location_context,
            next_signal_factory=lambda: self._execute_loop_end_candidates(state, candidates[1:]),
        )
        if isinstance(prepared, WaitForInput):
            return prepared

        self._emit_ability_declared(candidate)
        self.atomic_resolver.resolve(
            state,
            prepared,
            sequential=candidate.ability.sequential,
            perpetrator_id=owner_id,
            location_context=location_context,
        )
        self.ability_resolver.mark_ability_used(state, candidate)
        return self._execute_loop_end_candidates(state, candidates[1:])

    def _finalize_loop_end(self, state: GameState) -> PhaseSignal:
        self.event_bus.emit(GameEvent(
            GameEventType.LOOP_ENDED,
            {"loop": state.current_loop},
        ))
        state.save_loop_snapshot()
        return PhaseComplete()


class FinalGuessHandler(PhaseHandler):
    phase = GamePhase.FINAL_GUESS

    def execute(self, state: GameState) -> PhaseSignal:
        state.final_guess_correct = None
        return self._build_wait(state)

    def _build_wait(
        self,
        state: GameState,
        *,
        errors: list[str] | None = None,
    ) -> WaitForInput:
        context = {
            "errors": list(errors or []),
            "rule_y_id": state.script.private_table.rule_y.rule_id if state.script.private_table.rule_y is not None else None,
            "rule_x_ids": [rule.rule_id for rule in state.script.private_table.rules_x],
            "character_ids": [setup.character_id for setup in state.script.private_table.characters],
            "identity_ids": sorted(state.identity_defs.keys()),
        }

        def _on_choice(choice: Any) -> PhaseSignal:
            payload, error = self._normalize_final_guess_payload(state, choice)
            if error is not None:
                return self._build_wait(state, errors=[error])

            state.final_guess_correct = self._is_final_guess_correct(state, payload)
            return PhaseComplete()

        return WaitForInput(
            input_type="final_guess",
            prompt="最终决战：请推理所有角色身份与规则",
            context=context,
            player="protagonists",
            callback=_on_choice,
        )

    def _normalize_final_guess_payload(
        self,
        state: GameState,
        choice: Any,
    ) -> tuple[dict[str, Any], str | None]:
        if not isinstance(choice, dict):
            return {}, "最终决战提交格式错误：需要字典 payload"

        raw_rule_y_id = choice.get("rule_y_id")
        raw_rule_x_ids = choice.get("rule_x_ids")
        raw_character_identities = choice.get("character_identities")

        if not isinstance(raw_rule_y_id, str) or not raw_rule_y_id:
            return {}, "最终决战缺少 rule_y_id"
        if not isinstance(raw_rule_x_ids, list) or not all(isinstance(item, str) for item in raw_rule_x_ids):
            return {}, "最终决战缺少 rule_x_ids"
        if not isinstance(raw_character_identities, dict):
            return {}, "最终决战缺少 character_identities"

        expected_character_ids = [setup.character_id for setup in state.script.private_table.characters]
        guessed_character_ids = list(raw_character_identities.keys())
        if set(guessed_character_ids) != set(expected_character_ids):
            return {}, "最终决战需要为所有登场角色提交身份猜测"
        if not all(isinstance(identity_id, str) and identity_id for identity_id in raw_character_identities.values()):
            return {}, "最终决战身份猜测必须为非空字符串"

        return {
            "rule_y_id": raw_rule_y_id,
            "rule_x_ids": list(raw_rule_x_ids),
            "character_identities": {
                str(character_id): str(identity_id)
                for character_id, identity_id in raw_character_identities.items()
            },
        }, None

    @staticmethod
    def _is_final_guess_correct(state: GameState, payload: dict[str, Any]) -> bool:
        actual_rule_y_id = state.script.private_table.rule_y.rule_id if state.script.private_table.rule_y is not None else None
        if payload["rule_y_id"] != actual_rule_y_id:
            return False

        if set(payload["rule_x_ids"]) != {rule.rule_id for rule in state.script.private_table.rules_x}:
            return False

        actual_character_identities = {
            setup.character_id: state.characters[setup.character_id].original_identity_id
            for setup in state.script.private_table.characters
        }
        return payload["character_identities"] == actual_character_identities


# ---------------------------------------------------------------------------
# 阶段处理器注册表
# ---------------------------------------------------------------------------
def create_phase_handlers(event_bus: EventBus,
                          atomic_resolver: AtomicResolver
                          ) -> dict[GamePhase, PhaseHandler]:
    """创建所有阶段处理器的映射"""
    handlers: list[type[PhaseHandler]] = [
        GamePrepareHandler,
        LoopStartHandler,
        TurnStartHandler,
        MastermindActionHandler,
        ProtagonistActionHandler,
        ActionResolveHandler,
        PlaywrightAbilityHandler,
        ProtagonistAbilityHandler,
        IncidentHandler,
        LeaderRotateHandler,
        TurnEndHandler,
        LoopEndHandler,
        FinalGuessHandler,
    ]
    return {
        cls.phase: cls(event_bus, atomic_resolver)
        for cls in handlers
    }
