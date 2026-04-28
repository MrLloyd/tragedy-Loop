"""惨剧轮回 — 原子结算引擎

实现规则文档定义的"读-写-触发"三步法。

6 种原子结算类型：
  ① 同阶段全部强制能力
  ② 一张行动牌效果
  ③ 一次剧作家任意能力
  ④ 一次主人公友好能力
  ⑤ 一个事件的完整效果
  ⑥ 回合结束强制能力（杀人狂等）
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Optional

from engine.models.ability import AbilityLocationContext
from engine.models.enums import AbilityTiming, AreaId, CardType, DeathResult, EffectType, Outcome, TokenType, Trait
from engine.event_bus import EventBus, GameEvent, GameEventType
from engine.resolvers.ability_resolver import AbilityResolver
from engine.rules.persistent_effects import settle_persistent_effects
from engine.rules.runtime_identities import apply_identity_change

if TYPE_CHECKING:
    from engine.game_state import GameState
    from engine.models.effects import Effect
    from engine.resolvers.death_resolver import DeathResolver


# ---------------------------------------------------------------------------
# Mutation — 单个状态变更记录
# ---------------------------------------------------------------------------
@dataclass
class Mutation:
    mutation_type: str           # "token_change" | "character_death" | "character_move" | ...
    target_id: str               # character_id 或 area_id
    details: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Trigger — 触发效果（死亡触发等）
# ---------------------------------------------------------------------------
@dataclass
class Trigger:
    trigger_type: str            # "on_death" | "protagonist_death" | "protagonist_failure" | ...
    source_id: str = ""          # 触发来源角色
    is_terminal: bool = False    # 是否为终局效果
    effects: list = field(default_factory=list)
    sequential: bool = False
    location_context: AbilityLocationContext | None = None


# ---------------------------------------------------------------------------
# ResolutionResult — 原子结算结果
# ---------------------------------------------------------------------------
@dataclass
class ResolutionResult:
    mutations: list[Mutation] = field(default_factory=list)
    outcome: Outcome = Outcome.NONE
    announcements: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ScopedEffect:
    """附带 effect 所属角色上下文的效果包装。"""

    effect: Effect
    perpetrator_id: str = ""
    location_context: AbilityLocationContext | None = None


# ---------------------------------------------------------------------------
# AtomicResolver — 原子结算器
# ---------------------------------------------------------------------------
class AtomicResolver:
    """
    三步法：
      1. 读（plan）：在快照上确定所有效果的目标和数值
      2. 写（apply）：批量应用到真实状态
      3. 触发（trigger）：处理死亡等链式效果，队列式非递归
    """

    def __init__(self, event_bus: EventBus, death_resolver: DeathResolver) -> None:
        self.event_bus = event_bus
        self.death_resolver = death_resolver
        self.ability_resolver = AbilityResolver()

    def resolve(self, state: GameState, effects: list[Effect | ScopedEffect],
                sequential: bool = False,
                perpetrator_id: str = "",
                location_context: AbilityLocationContext | None = None) -> ResolutionResult:
        """
        执行一次原子结算。

        Args:
            state: 真实游戏状态（会被修改）
            effects: 待执行的效果列表
            sequential: True=有"随后"，逐个结算；False=同时生效
            perpetrator_id: 事件当事人 ID，用于解析 same_area_* 等符号目标
        """
        if sequential:
            return self._resolve_sequential(
                state,
                effects,
                perpetrator_id,
                location_context=location_context,
            )
        return self._resolve_simultaneous(
            state,
            effects,
            perpetrator_id,
            location_context=location_context,
        )

    # ==================================================================
    # 同时生效结算
    # ==================================================================

    def _resolve_simultaneous(self, state: GameState,
                              effects: list[Effect | ScopedEffect],
                              perpetrator_id: str = "",
                              location_context: AbilityLocationContext | None = None) -> ResolutionResult:
        planned_mutations = self._apply_effect_batch(
            state,
            effects,
            perpetrator_id=perpetrator_id,
            location_context=location_context,
        )

        # ③ 触发：收集并处理链式效果
        return self._process_triggers(state, planned_mutations)

    # ==================================================================
    # 顺序结算（含"随后"）
    # ==================================================================

    def _resolve_sequential(self, state: GameState,
                            effects: list[Effect | ScopedEffect],
                            perpetrator_id: str = "",
                            location_context: AbilityLocationContext | None = None) -> ResolutionResult:
        all_mutations: list[Mutation] = []
        final_outcome = Outcome.NONE

        for effect in effects:
            # 每步独立走完三步法
            sub_result = self._resolve_simultaneous(
                state,
                [effect],
                perpetrator_id,
                location_context=location_context,
            )
            all_mutations.extend(sub_result.mutations)

            # 如果产生终局效果，记录但继续（后续步骤基于新状态）
            if sub_result.outcome != Outcome.NONE:
                final_outcome = sub_result.outcome

        return ResolutionResult(
            mutations=all_mutations,
            outcome=final_outcome,
        )

    @staticmethod
    def _coerce_scoped_effect(
        effect: Effect | ScopedEffect,
        *,
        default_perpetrator_id: str,
        default_location_context: AbilityLocationContext | None,
    ) -> ScopedEffect:
        if isinstance(effect, ScopedEffect):
            return effect
        return ScopedEffect(
            effect=effect,
            perpetrator_id=default_perpetrator_id,
            location_context=default_location_context,
        )

    # ==================================================================
    # 第一步：读 — 在快照上规划变更
    # ==================================================================

    def _resolve_target_ids(self, snapshot: GameState, target: Any,
                            perpetrator_id: str,
                            location_context: AbilityLocationContext | None = None) -> list[str]:
        return self.ability_resolver.resolve_targets(
            snapshot,
            owner_id=perpetrator_id,
            selector=target,
            alive_only=True,
            location_context=location_context,
        )

    def _plan_effect(self, snapshot: GameState, effect: Effect,
                     perpetrator_id: str = "",
                     location_context: AbilityLocationContext | None = None) -> list[Mutation]:
        """根据效果类型规划 mutations（不修改状态）"""
        if effect.condition is not None and not self.ability_resolver.evaluate_condition(
            snapshot,
            effect.condition,
            owner_id=perpetrator_id,
            location_context=location_context,
        ):
            return []
        mutations = []

        match effect.effect_type:

            case EffectType.PLACE_TOKEN:
                for tid in self._resolve_target_ids(
                    snapshot,
                    effect.target,
                    perpetrator_id,
                    location_context,
                ):
                    mutations.append(Mutation(
                        mutation_type="token_change",
                        target_id=tid,
                        details={
                            "token_type": effect.token_type.value if effect.token_type else "",
                            "delta": effect.amount,
                        },
                    ))

            case EffectType.REMOVE_TOKEN:
                for tid in self._resolve_target_ids(
                    snapshot,
                    effect.target,
                    perpetrator_id,
                    location_context,
                ):
                    mutations.append(Mutation(
                        mutation_type="token_change",
                        target_id=tid,
                        details={
                            "token_type": effect.token_type.value if effect.token_type else "",
                            "delta": -effect.amount,
                        },
                    ))

            case EffectType.REMOVE_ALL_TOKENS:
                for tid in self._resolve_target_ids(
                    snapshot,
                    effect.target,
                    perpetrator_id,
                    location_context,
                ):
                    if tid in snapshot.characters:
                        ch = snapshot.characters[tid]
                        token_types = [effect.token_type] if effect.token_type else list(TokenType)
                        for token_type in token_types:
                            if token_type is None:
                                continue
                            current = ch.tokens.get(token_type)
                            if current <= 0:
                                continue
                            mutations.append(Mutation(
                                mutation_type="token_change",
                                target_id=tid,
                                details={
                                    "token_type": token_type.value,
                                    "delta": -current,
                                },
                            ))

            case EffectType.MOVE_TOKEN:
                if effect.token_type is None or perpetrator_id not in snapshot.characters:
                    return mutations
                source = snapshot.characters[perpetrator_id]
                remaining = source.tokens.get(effect.token_type)
                if remaining <= 0:
                    return mutations
                for tid in self._resolve_target_ids(
                    snapshot,
                    effect.target,
                    perpetrator_id,
                    location_context,
                ):
                    if remaining <= 0:
                        break
                    moved = min(effect.amount or 1, remaining)
                    mutations.append(Mutation(
                        mutation_type="token_move",
                        target_id=tid,
                        details={
                            "source_id": perpetrator_id,
                            "token_type": effect.token_type.value,
                            "amount": moved,
                        },
                    ))
                    remaining -= moved

            case EffectType.KILL_CHARACTER:
                for tid in self._resolve_target_ids(
                    snapshot,
                    effect.target,
                    perpetrator_id,
                    location_context,
                ):
                    mutations.append(Mutation(
                        mutation_type="character_death",
                        target_id=tid,
                        details={"cause": "effect"},
                    ))

            case EffectType.REVIVE_CHARACTER:
                for tid in self._resolve_target_ids(
                    snapshot,
                    effect.target,
                    perpetrator_id,
                    location_context,
                ):
                    if tid not in snapshot.characters:
                        continue
                    mutations.append(Mutation(
                        mutation_type="character_revive",
                        target_id=tid,
                        details={},
                    ))

            case EffectType.MOVE_CHARACTER:
                destination = effect.value
                if destination in (None, ""):
                    return mutations
                try:
                    destination_area = AreaId(str(destination))
                except ValueError:
                    return mutations
                for tid in self._resolve_target_ids(
                    snapshot,
                    effect.target,
                    perpetrator_id,
                    location_context,
                ):
                    if tid not in snapshot.characters:
                        continue
                    if not snapshot.can_character_enter_area(tid, destination_area):
                        continue
                    mutations.append(Mutation(
                        mutation_type="character_move",
                        target_id=tid,
                        details={"destination": destination_area.value},
                    ))

            case EffectType.LIFT_FORBIDDEN_AREAS:
                for tid in self._resolve_target_ids(
                    snapshot,
                    effect.target,
                    perpetrator_id,
                    location_context,
                ):
                    if tid not in snapshot.characters:
                        continue
                    mutations.append(Mutation(
                        mutation_type="lift_forbidden_areas",
                        target_id=tid,
                        details={},
                    ))

            case EffectType.PROTAGONIST_PROTECT:
                mutations.append(Mutation(
                    mutation_type="protagonist_protect",
                    target_id="",
                    details={},
                ))

            case EffectType.PROTAGONIST_DEATH:
                mutations.append(Mutation(
                    mutation_type="protagonist_death",
                    target_id="",
                    details={"cause": effect.value or "effect"},
                ))

            case EffectType.PROTAGONIST_FAILURE:
                mutations.append(Mutation(
                    mutation_type="protagonist_failure",
                    target_id="",
                    details={"cause": effect.value or "effect"},
                ))

            case EffectType.FORCE_LOOP_END:
                mutations.append(Mutation(
                    mutation_type="force_loop_end",
                    target_id="",
                    details={"cause": effect.value or "effect"},
                ))

            case EffectType.REVEAL_IDENTITY:
                for tid in self._resolve_target_ids(
                    snapshot,
                    effect.target,
                    perpetrator_id,
                    location_context,
                ):
                    mutations.append(Mutation(
                        mutation_type="reveal_identity",
                        target_id=tid,
                        details={},
                    ))

            case EffectType.REVEAL_INCIDENT:
                incident_id = str(effect.value or "")
                if incident_id:
                    mutations.append(Mutation(
                        mutation_type="reveal_incident",
                        target_id=incident_id,
                        details={"incident_id": incident_id},
                    ))

            case EffectType.CHANGE_IDENTITY:
                identity_id = str(effect.value or "")
                for tid in self._resolve_target_ids(
                    snapshot,
                    effect.target,
                    perpetrator_id,
                    location_context,
                ):
                    mutations.append(Mutation(
                        mutation_type="identity_change",
                        target_id=tid,
                        details={"identity_id": identity_id},
                    ))

            case EffectType.NULLIFY_CARD:
                try:
                    card_type = CardType(str(effect.value or ""))
                except ValueError:
                    return mutations
                target_ids = set(
                    self._resolve_target_ids(
                        snapshot,
                        effect.target,
                        perpetrator_id,
                        location_context,
                    )
                )
                for index, placement in enumerate(snapshot.placed_cards):
                    if placement.nullified:
                        continue
                    if placement.target_id not in target_ids:
                        continue
                    if placement.card.card_type != card_type:
                        continue
                    mutations.append(Mutation(
                        mutation_type="card_nullify",
                        target_id=str(index),
                        details={"placement_index": index},
                    ))

            case EffectType.MODIFY_EX_GAUGE:
                delta = effect.amount
                if delta == 0:
                    try:
                        delta = int(effect.value or 0)
                    except (TypeError, ValueError):
                        delta = 0
                mutations.append(Mutation(
                    mutation_type="ex_gauge_change",
                    target_id="",
                    details={"delta": delta},
                ))

            case EffectType.RETURN_CARD:
                try:
                    placement_index = int(str(effect.value or ""))
                except ValueError:
                    return mutations
                if 0 <= placement_index < len(snapshot.placed_cards):
                    mutations.append(Mutation(
                        mutation_type="card_return",
                        target_id=str(placement_index),
                        details={"placement_index": placement_index},
                    ))

            case EffectType.REMOVE_CHARACTER:
                for tid in self._resolve_target_ids(
                    snapshot,
                    effect.target,
                    perpetrator_id,
                    location_context,
                ):
                    if tid not in snapshot.characters:
                        continue
                    mutations.append(Mutation(
                        mutation_type="character_remove",
                        target_id=tid,
                        details={},
                    ))

            case EffectType.SUPPRESS_INCIDENT:
                for tid in self._resolve_target_ids(
                    snapshot,
                    effect.target,
                    perpetrator_id,
                    location_context,
                ):
                    if tid not in snapshot.characters:
                        continue
                    mutations.append(Mutation(
                        mutation_type="incident_suppress",
                        target_id=tid,
                        details={},
                    ))

            case EffectType.NO_EFFECT:
                pass  # 事件发生但无现象

            case _:
                pass  # 其他类型后续扩展

        return mutations

    # ==================================================================
    # 第二步：写 — 批量应用到真实状态
    # ==================================================================

    def _apply_mutation(self, state: GameState, mutation: Mutation) -> None:
        """将单个 mutation 写入真实状态"""

        match mutation.mutation_type:

            case "token_change":
                target_id = mutation.target_id
                token_type = TokenType(mutation.details["token_type"])
                delta = mutation.details["delta"]

                # 目标可能是角色或版图
                if target_id in state.characters:
                    state.characters[target_id].tokens.add(token_type, delta)
                    self.event_bus.emit(GameEvent(
                        GameEventType.TOKEN_CHANGED,
                        {"target_id": target_id, "token_type": token_type.value,
                         "delta": delta},
                    ))
                elif hasattr(AreaId, target_id.upper()):
                    area_id = AreaId(target_id)
                    if area_id in state.board.areas:
                        state.board.areas[area_id].tokens.add(token_type, delta)
                        self.event_bus.emit(GameEvent(
                            GameEventType.TOKEN_CHANGED,
                            {"target_id": target_id, "token_type": token_type.value,
                             "delta": delta},
                        ))

            case "token_move":
                source_id = mutation.details["source_id"]
                token_type = TokenType(mutation.details["token_type"])
                amount = int(mutation.details["amount"])
                if amount <= 0 or source_id not in state.characters:
                    return
                removed = state.characters[source_id].tokens.remove(token_type, amount)
                if removed <= 0:
                    return
                target_id = mutation.target_id
                if target_id in state.characters:
                    state.characters[target_id].tokens.add(token_type, removed)
                elif hasattr(AreaId, target_id.upper()):
                    area_id = AreaId(target_id)
                    if area_id in state.board.areas:
                        state.board.areas[area_id].tokens.add(token_type, removed)
                self.event_bus.emit(GameEvent(
                    GameEventType.TOKEN_CHANGED,
                    {"target_id": source_id, "token_type": token_type.value, "delta": -removed},
                ))
                self.event_bus.emit(GameEvent(
                    GameEventType.TOKEN_CHANGED,
                    {"target_id": target_id, "token_type": token_type.value, "delta": removed},
                ))

            case "character_death":
                cid = mutation.target_id
                if cid in state.characters:
                    ch = state.characters[cid]
                    if ch.is_active():
                        result = self.death_resolver.process_death(ch, state)
                        mutation.details["death_result"] = result

            case "character_move":
                cid = mutation.target_id
                dest = mutation.details["destination"]
                if cid in state.characters:
                    moved = state.move_character(cid, dest)
                    if not moved:
                        return
                    ch = state.characters[cid]
                    self.event_bus.emit(GameEvent(
                        GameEventType.CHARACTER_MOVED,
                        {"character_id": cid, "destination": str(ch.area.value)},
                    ))

            case "character_revive":
                cid = mutation.target_id
                if cid in state.characters:
                    ch = state.characters[cid]
                    ch.mark_alive()

            case "character_remove":
                cid = mutation.target_id
                if cid in state.characters:
                    state.characters[cid].mark_removed()
                    self.event_bus.emit(GameEvent(
                        GameEventType.CHARACTER_REMOVED,
                        {"character_id": cid},
                    ))

            case "lift_forbidden_areas":
                cid = mutation.target_id
                if cid in state.characters:
                    state.characters[cid].clear_forbidden_areas()

            case "protagonist_protect":
                state.soldier_protection_active = True

            case "protagonist_death":
                if not state.soldier_protection_active:
                    state.protagonist_dead = True

            case "protagonist_failure":
                state.failure_flags.add(mutation.details.get("cause", "unknown"))

            case "force_loop_end":
                pass  # 由 GameController 处理

            case "reveal_identity":
                cid = mutation.target_id
                if cid in state.characters:
                    ch = state.characters[cid]
                    ch.revealed = True
                    self.event_bus.emit(GameEvent(
                        GameEventType.IDENTITY_REVEALED,
                        {"character_id": cid, "identity_id": ch.identity_id},
                    ))

            case "reveal_incident":
                incident_id = str(mutation.details["incident_id"])
                schedule = next(
                    (item for item in state.script.incidents if item.incident_id == incident_id),
                    None,
                )
                if schedule is not None:
                    state.revealed_incident_perpetrators_this_loop.append(
                        {
                            "incident_id": incident_id,
                            "perpetrator_id": schedule.perpetrator_id,
                            "day": schedule.day,
                        }
                    )
                    self.event_bus.emit(GameEvent(
                        GameEventType.INCIDENT_REVEALED,
                        {
                            "incident_id": incident_id,
                            "perpetrator_id": schedule.perpetrator_id,
                            "day": schedule.day,
                        },
                    ))

            case "identity_change":
                cid = mutation.target_id
                identity_id = mutation.details["identity_id"]
                apply_identity_change(
                    state,
                    cid,
                    identity_id=identity_id,
                    reason="effect",
                )

            case "card_nullify":
                index = int(mutation.details["placement_index"])
                if 0 <= index < len(state.placed_cards):
                    state.placed_cards[index].nullified = True

            case "card_return":
                index = int(mutation.details["placement_index"])
                if 0 <= index < len(state.placed_cards):
                    placement = state.placed_cards.pop(index)
                    placement.card.is_used_this_loop = False

            case "ex_gauge_change":
                delta = mutation.details["delta"]
                state.ex_gauge = max(0, state.ex_gauge + delta)
                self.event_bus.emit(GameEvent(
                    GameEventType.EX_GAUGE_CHANGED,
                    {"delta": delta, "new_value": state.ex_gauge},
                ))

            case "incident_suppress":
                state.suppressed_incident_perpetrators.add(mutation.target_id)

    def _apply_effect_batch(
        self,
        state: GameState,
        effects: list[Effect | ScopedEffect],
        *,
        perpetrator_id: str = "",
        location_context: AbilityLocationContext | None = None,
    ) -> list[Mutation]:
        """仅执行读写两步，不进入触发处理。"""
        settle_persistent_effects(state)
        snapshot = state.snapshot()
        planned_mutations: list[Mutation] = []
        for effect in effects:
            scoped = self._coerce_scoped_effect(
                effect,
                default_perpetrator_id=perpetrator_id,
                default_location_context=location_context,
            )
            planned_mutations.extend(
                self._plan_effect(
                    snapshot,
                    scoped.effect,
                    scoped.perpetrator_id,
                    scoped.location_context,
                )
            )

        for mutation in planned_mutations:
            self._apply_mutation(state, mutation)
        settle_persistent_effects(state)
        return planned_mutations

    # ==================================================================
    # 第三步：触发 — 处理链式效果（队列式）
    # ==================================================================

    def _process_triggers(self, state: GameState,
                          mutations: list[Mutation]) -> ResolutionResult:
        """收集死亡等触发，队列式处理，最后统一裁定终局效果"""
        trigger_queue: deque[Trigger] = deque()
        terminal_effects: list[Trigger] = []

        # 收集初始触发
        for m in mutations:
            triggers = self._collect_triggers_from_mutation(m, state)
            trigger_queue.extend(triggers)

        # 队列式处理
        while trigger_queue:
            trigger = trigger_queue.popleft()

            if trigger.is_terminal:
                terminal_effects.append(trigger)
            else:
                # 非终局触发：按 sequential 语义执行效果，可能产生新触发
                effect_batches = (
                    [[effect] for effect in trigger.effects]
                    if trigger.sequential
                    else [trigger.effects]
                )
                for effect_batch in effect_batches:
                    sub_mutations = self._apply_effect_batch(
                        state,
                        effect_batch,
                        perpetrator_id=trigger.source_id,
                        location_context=trigger.location_context,
                    )
                    for sm in sub_mutations:
                        new_triggers = self._collect_triggers_from_mutation(sm, state)
                        trigger_queue.extend(new_triggers)

        # 统一裁定终局
        outcome = self._adjudicate(terminal_effects, state)
        settle_persistent_effects(state)

        # 裁定后发布终局事件
        if outcome == Outcome.PROTAGONIST_DEATH:
            self.event_bus.emit(GameEvent(GameEventType.PROTAGONIST_DEATH, {"cause": "adjudication"}))
        elif outcome == Outcome.PROTAGONIST_FAILURE:
            self.event_bus.emit(GameEvent(GameEventType.PROTAGONIST_FAILURE, {"cause": "adjudication"}))

        # 如果有强制结束轮回的 mutation，标记到结果
        has_force_end = any(m.mutation_type == "force_loop_end" for m in mutations)
        if has_force_end and outcome == Outcome.NONE:
            outcome = Outcome.PROTAGONIST_FAILURE

        return ResolutionResult(mutations=mutations, outcome=outcome)

    def _collect_triggers_from_mutation(
        self,
        mutation: Mutation,
        state: GameState,
    ) -> list[Trigger]:
        """从单个 mutation 收集触发"""
        triggers = []

        if mutation.mutation_type == "character_death":
            death_result = mutation.details.get("death_result")
            if death_result == DeathResult.DIED:
                cid = mutation.target_id
                self.event_bus.emit(GameEvent(
                    GameEventType.CHARACTER_DEATH,
                    {"character_id": cid},
                ))
                # 接入身份 ON_DEATH 能力触发入口
                ch = state.characters.get(cid)
                if ch and ch.identity_id:
                    identity_def = state.identity_defs.get(ch.identity_id)
                    if identity_def:
                        for ability in identity_def.abilities:
                            if ability.timing == AbilityTiming.ON_DEATH:
                                self.event_bus.emit(GameEvent(
                                    GameEventType.ABILITY_DECLARED,
                                    {
                                        "source_kind": "character",
                                        "character_id": cid,
                                        "identity_id": ch.identity_id,
                                        "ability_id": ability.ability_id,
                                        "timing": AbilityTiming.ON_DEATH.value,
                                    },
                                ))
                                triggers.append(Trigger(
                                    trigger_type="on_death",
                                    source_id=cid,
                                    is_terminal=False,
                                    effects=ability.effects,
                                    sequential=ability.sequential,
                                ))
                for candidate in self.ability_resolver.collect_derived_abilities(
                    state,
                    timing=AbilityTiming.ON_DEATH,
                    alive_only=False,
                ):
                    if candidate.source_id != cid:
                        continue
                    self.event_bus.emit(GameEvent(
                        GameEventType.ABILITY_DECLARED,
                        {
                            "source_kind": "derived",
                            "character_id": cid,
                            "identity_id": candidate.identity_id,
                            "ability_id": candidate.ability.ability_id,
                            "timing": AbilityTiming.ON_DEATH.value,
                        },
                    ))
                    triggers.append(Trigger(
                        trigger_type="on_death",
                        source_id=cid,
                        is_terminal=False,
                        effects=candidate.ability.effects,
                        sequential=candidate.ability.sequential,
                    ))
                for owner in state.characters.values():
                    if owner.character_id == cid or not owner.is_active():
                        continue
                    identity_def = state.identity_defs.get(owner.identity_id)
                    if identity_def is None:
                        continue
                    for ability in identity_def.abilities:
                        if ability.timing != AbilityTiming.ON_OTHER_DEATH:
                            continue
                        if not self.ability_resolver.evaluate_condition(
                            state,
                            ability.condition,
                            owner_id=owner.character_id,
                            other_id=cid,
                        ):
                            continue
                        self.event_bus.emit(GameEvent(
                            GameEventType.ABILITY_DECLARED,
                            {
                                "source_kind": "character",
                                "character_id": owner.character_id,
                                "identity_id": owner.identity_id,
                                "ability_id": ability.ability_id,
                                "timing": AbilityTiming.ON_OTHER_DEATH.value,
                                "other_character_id": cid,
                            },
                        ))
                        triggers.append(Trigger(
                            trigger_type="on_other_death",
                            source_id=owner.character_id,
                            is_terminal=False,
                            effects=ability.effects,
                            sequential=ability.sequential,
                        ))

        if mutation.mutation_type == "identity_change":
            settle_persistent_effects(state)

        if mutation.mutation_type == "protagonist_death":
            if state.protagonist_dead:
                triggers.append(Trigger(
                    trigger_type="protagonist_death",
                    is_terminal=True,
                ))

        if mutation.mutation_type == "protagonist_failure":
            triggers.append(Trigger(
                trigger_type="protagonist_failure",
                is_terminal=True,
            ))

        return triggers

    # ==================================================================
    # 同时裁定
    # ==================================================================

    @staticmethod
    def _adjudicate(terminal_effects: list[Trigger],
                    state: GameState) -> Outcome:
        """
        同时裁定规则（rules.md:179）：
        - 同时产生死亡+失败 → 仅报送死亡
        - 死亡被阻止（军人）且有失败 → 报送失败
        - 死亡被阻止且无失败 → 无终局效果
        """
        has_death = any(t.trigger_type == "protagonist_death" for t in terminal_effects)
        has_failure = any(t.trigger_type == "protagonist_failure" for t in terminal_effects)

        if not has_death and not has_failure:
            return Outcome.NONE

        if has_death:
            if not state.soldier_protection_active:
                return Outcome.PROTAGONIST_DEATH
            else:
                # 死亡被军人阻止
                state.protagonist_dead = False
                if has_failure:
                    return Outcome.PROTAGONIST_FAILURE
                return Outcome.NONE

        if has_failure:
            return Outcome.PROTAGONIST_FAILURE

        return Outcome.NONE
