"""常驻能力闭环刷新。"""

from __future__ import annotations

from engine.game_state import GameState
from engine.models.effects import Effect
from engine.models.enums import AbilityTiming, AbilityType, EffectType

MAX_PERSISTENT_EFFECT_ITERATIONS = 10


def sync_persistent_effects(state: GameState) -> bool:
    """执行一轮常驻能力同步，返回是否发生状态变更。"""
    from engine.resolvers.ability_resolver import AbilityResolver
    from engine.rules.runtime_identities import apply_identity_change

    resolver = AbilityResolver()
    changed = False
    for rule in _persistent_rules(state):
        for ability in rule.abilities:
            if ability.timing != AbilityTiming.ALWAYS:
                continue
            if ability.ability_type != AbilityType.MANDATORY:
                continue
            for effect in ability.effects:
                for target_id in _persistent_targets(resolver, state, effect):
                    if not resolver.evaluate_condition(
                        state,
                        effect.condition,
                        owner_id=target_id,
                    ):
                        continue
                    if effect.effect_type != EffectType.CHANGE_IDENTITY:
                        continue
                    identity_id = str(effect.value or "")
                    character = state.characters.get(target_id)
                    if character is None or character.identity_id == identity_id:
                        continue
                    apply_identity_change(
                        state,
                        target_id,
                        identity_id=identity_id,
                        reason=character.identity_change_reason,
                    )
                    changed = True
    return changed


def settle_persistent_effects(state: GameState) -> None:
    """重复刷新常驻能力，直到状态稳定。"""
    for _ in range(MAX_PERSISTENT_EFFECT_ITERATIONS):
        if not sync_persistent_effects(state):
            return
    raise RuntimeError("Persistent effects did not settle")


def _persistent_rules(state: GameState):
    if state.script.private_table.rule_y is not None:
        yield state.script.private_table.rule_y
    yield from state.script.private_table.rules_x


def _persistent_targets(resolver, state: GameState, effect: Effect) -> list[str]:
    return resolver.resolve_targets(
        state,
        owner_id="",
        selector=effect.target,
        alive_only=False,
    )
